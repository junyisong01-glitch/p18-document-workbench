import io
import subprocess
from pathlib import Path
import pytest
from PIL import Image
from app.parser import process, validate
from app.chunking import prepare,configuration


def chunks(result,ext):
    return prepare(dict(id='formats',name='研发说明'+ext,ext=ext,revision=1,quality='clear',result=result),configuration())[1]


@pytest.mark.parametrize('encoding',['utf-8-sig','gb18030','utf-16'])
def test_text_encodings_and_source_lines(tmp_path,encoding):
    (tmp_path/'original.txt').write_bytes('网关故障\r\n\r\n设备编号 000047，重试等待 15 秒。'.encode(encoding))
    r=process(tmp_path,'.txt')
    assert r['issues']==[] and '000047' in r['blocks'][-1]['text']
    assert r['blocks'][-1]['line_start']==3
    assert any(s['line_start']==3 for c in chunks(r,'.txt') for s in c['sources'])


def test_markdown_preserves_code_tables_and_inert_markup(tmp_path):
    text='# 网关接入\n\n## 重试\n\n等待 15 秒。\n\n```python\n# literal heading\nprint("<script>alert(1)</script>")\n```\n\n| 参数 | 值 |\n| --- | --- |\n| 重试 | 15 秒 |\n\n<script>alert(2)</script>\n'
    (tmp_path/'original.md').write_text(text)
    r=process(tmp_path,'.md')
    assert r['issues']==[]
    table=next(b for b in r['blocks'] if b['kind']=='table')
    assert table['tables'][0]['rows']==[['参数','值'],['重试','15 秒']]
    assert any(b.get('style')=='Code' and '# literal heading' in b['text'] for b in r['blocks'])
    assert any('alert(2)' in b['text'] for b in r['blocks'])
    assert any(c['kind']=='code' and 'print(' in c['text'] for c in chunks(r,'.md'))


@pytest.mark.parametrize('ext',['.txt','.md','.csv'])
def test_empty_or_binary_text_not_publishable(tmp_path,ext):
    path=tmp_path/('original'+ext);path.write_bytes(b'\x00binary')
    with pytest.raises(ValueError,match='乱码'):process(tmp_path,ext)
    path.write_text('   \n')
    assert process(tmp_path,ext).get('error')


def test_csv_quotes_multiline_leading_zero_and_formula_text(tmp_path):
    (tmp_path/'original.csv').write_text('编号,说明,值\n000047,"第一行\n第二行",=1+1\n000048,"包含,逗号",0\n')
    r=process(tmp_path,'.csv')
    cells=[c for b in r['blocks'] for c in b['cells']]
    assert any(c['text']=='000047' for c in cells)
    assert any(c['text']=='第一行\n第二行' for c in cells)
    assert any(c['text']=='=1+1' and not c['formula'] for c in cells)
    assert any(c['text']=='0' for c in cells)
    assert any(b['line_start']==2 and b['line_end']==3 for b in r['blocks'])
    assert any(c.get('records') for c in chunks(r,'.csv'))
    assert r['excel_sheets']


def test_csv_ragged_and_limits_are_not_silently_truncated(tmp_path,monkeypatch):
    import app.text_formats as reader
    p=tmp_path/'original.csv';p.write_text('名称,值\n甲,1,额外字段\n')
    r=process(tmp_path,'.csv')
    assert any('额外字段' in b['text'] for b in r['blocks'])
    monkeypatch.setattr(reader,'MAX_ROWS',1)
    with pytest.raises(ValueError,match='记录'):process(tmp_path,'.csv')


def test_xls_saved_values_positions_and_limitations(tmp_path):
    import xlwt
    book=xlwt.Workbook();s=book.add_sheet('设备')
    bold=xlwt.easyxf('font: bold on')
    for c,value in enumerate(['设备编号','名称','等待']):s.write(0,c,value,bold)
    s.write(1,0,47,xlwt.easyxf(num_format_str='000000'));s.write(1,1,'网关');s.write(1,2,15)
    book.save(str(tmp_path/'original.xls'))
    r=process(tmp_path,'.xls')
    assert any('000047' in b['text'] and '等待：15' in b['text'] for b in r['blocks'])
    assert any(i['kind']=='objects' for i in r['issues'])
    assert r['excel_sheets'][0]['name']=='设备'
    assert chunks(r,'.xls')[0]['sources'][0]['sheet']=='设备'


@pytest.mark.parametrize('ext,fmt',[('.png','PNG'),('.jpg','JPEG')])
def test_image_reuses_ocr_and_preserves_download(tmp_path,monkeypatch,ext,fmt):
    from app import parser
    p=tmp_path/('original'+ext);Image.new('RGB',(200,100),'white').save(p,format=fmt)
    original=p.read_bytes()
    monkeypatch.setattr(parser.PdfOcr,'recognize',lambda *_:[dict(text='重试等待 15 秒',confidence=.98)])
    r=process(tmp_path,ext)
    assert p.read_bytes()==original and '15 秒' in r['blocks'][0]['text']
    assert r['preview']['original']=='image-preview.pdf'
    assert chunks(r,ext)[0]['sources'][0]['page']==1
    monkeypatch.setattr(parser.PdfOcr,'recognize',lambda *_:[])
    assert process(tmp_path,ext)['error']


def test_image_format_and_pixel_limit(tmp_path):
    p=tmp_path/'original.png';Image.new('RGB',(100,100)).save(p,format='JPEG')
    with pytest.raises(ValueError,match='不一致'):validate(p,'.png')
    Image.new('1',(5000,5000)).save(p,format='PNG')
    with pytest.raises(ValueError,match='像素'):validate(p,'.png')


def test_cpu_ocr_command_threads_confidence_and_missing_dependency(tmp_path,monkeypatch):
    from app import pdf_ocr
    import pymupdf as fitz
    monkeypatch.setenv('P18_OCR_BACKEND','tesseract')
    monkeypatch.setattr(pdf_ocr.shutil,'which',lambda _:None)
    with fitz.open() as pdf:
        page=pdf.new_page()
        with pytest.raises(pdf_ocr.OcrError,match='未安装'):pdf_ocr.PdfOcr(tmp_path).recognize(page)
        monkeypatch.setattr(pdf_ocr.shutil,'which',lambda _:'/usr/bin/tesseract')
        def run(args,**kwargs):
            assert args[-3:]==['-l','chi_sim+eng','tsv']
            assert kwargs['env']['OMP_THREAD_LIMIT']=='1'
            assert kwargs['timeout']<=30
            return subprocess.CompletedProcess(args,0,b'level\tpage_num\tblock_num\tpar_num\tline_num\tconf\ttext\n5\t1\t1\t1\t1\t92\tGateway\n5\t1\t1\t1\t1\t50\t15\n')
        monkeypatch.setattr(pdf_ocr.subprocess,'run',run)
        assert pdf_ocr.PdfOcr(tmp_path).recognize(page)==[dict(text='Gateway 15',confidence=.5)]


def test_vision_helper_compiles_once_across_documents(tmp_path,monkeypatch):
    from app import pdf_ocr
    import pymupdf as fitz
    monkeypatch.setenv('P18_OCR_BACKEND','vision')
    monkeypatch.setenv('P18_DATA_DIR',str(tmp_path/'runtime'))
    monkeypatch.delenv('P18_PDF_OCR_HELPER',raising=False)
    monkeypatch.setattr(pdf_ocr.sys,'platform','darwin')
    compilations=[]
    def run(args,**kwargs):
        if args[0]=='/usr/bin/swiftc':
            compilations.append(args)
            Path(args[-1]).write_text('test executable');Path(args[-1]).chmod(0o700)
            return subprocess.CompletedProcess(args,0,b'')
        return subprocess.CompletedProcess(args,0,b'[{"text":"15 seconds","confidence":0.99}]')
    monkeypatch.setattr(pdf_ocr.subprocess,'run',run)
    with fitz.open() as pdf:
        page=pdf.new_page()
        for name in ['first','second']:
            folder=tmp_path/name;folder.mkdir()
            assert pdf_ocr.PdfOcr(folder).recognize(page)[0]['text']=='15 seconds'
    assert len(compilations)==1
