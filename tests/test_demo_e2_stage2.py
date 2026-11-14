"""New fictional structure checks; not the frozen E2 or independent exam."""
from pathlib import Path
import importlib.util,copy
from docx import Document
from openpyxl import Workbook
import pymupdf
from app.parser import parse_word,parse_pdf,process
from app.chunking import prepare,configuration
ROOT=Path(__file__).resolve().parents[1]
def doc(result,ext):
    return {'id':'3dd7d9cc-ccce-4e9c-a1e2-17e9ec61652a','name':'虚构澄星ZX8说明'+ext,'ext':ext,'revision':1,'quality':'clear','state':'ready','characters':result['characters'],'result':result}
def test_e2_real_word_context_and_original_source_offsets(tmp_path):
    w=Document();w.add_heading('虚构澄星ZX8说明',0);w.add_heading('1 设备参数',1)
    w.add_paragraph('本资料完全虚构，仅供本地软件测试。')
    w.add_heading('1.1 校准时长',2);w.add_paragraph('下表为校准时长；单位：分钟。')
    t=w.add_table(rows=3,cols=2)
    for row,values in zip(t.rows,[['模式','时长'],['晨间','18'],['夜间','24']]):
        for c,v in zip(row.cells,values):c.text=v
    w.add_heading('2 操作步骤',1);w.add_paragraph('1. 检查虚构电源。');w.add_paragraph('2. 按下虚构确认键。')
    w.add_heading('3 代码',1);w.add_paragraph('def fictional_device():\n    return 17')
    p=tmp_path/'x.docx';w.save(p);r=parse_word(p);before=copy.deepcopy(r)
    n,ch=prepare(doc(r,'.docx'),configuration());assert r==before
    table=next(c for c in ch if c['kind']=='table')
    assert '【表格局部上下文】' in table['text'] and '单位：分钟' in table['text']
    assert table['evidence_text'] in table['text'] and '18' in table['evidence_text'] and '24' in table['evidence_text']
    assert table['retrieval_context'] and table['original_table_text']
    assert all(len(c['text'])<=500 for c in ch)
    lookup={b['id']:b for b in r['blocks']}
    for c in ch:
        for s in c['sources']:
            assert 0<=s['raw_start']<=s['raw_end']<=len(lookup[s['block_id']]['text'])
    table_sources=[s for s in table['sources'] if lookup[s['block_id']]['kind']=='table']
    assert table_sources and table['tables'][0]['cells']==lookup[table_sources[0]['block_id']]['tables'][0]['cells']
    assert all(cell['row']>=1 and cell['column']>=1 for cell in table['tables'][0]['cells'])
    titles={b['text'].strip() for b in r['blocks'] if b.get('heading_level') is not None}
    assert not any(c['text'].strip() in titles for c in ch)
    assert any('检查虚构电源' in c['text'] and c['section'].startswith('2') for c in ch)
    assert any('    return 17' in c['text'] for c in ch)
def test_pdf_excel_content_stable_but_global_method_changes_ids(tmp_path):
    p=tmp_path/'page.pdf';w=pymupdf.open();page=w.new_page();page.insert_text((40,60),'Fictional ZX8 calibration cycle is 18 minutes.');w.save(p);w.close()
    pdf=doc(parse_pdf(p),'.pdf')
    wb=Workbook();s=wb.active;s.append(['设备','时长']);s.append(['ZX8',18]);wb.save(tmp_path/'original.xlsx')
    excel=doc(process(tmp_path,'.xlsx'),'.xlsx')
    spec=importlib.util.spec_from_file_location('stage1_chunking',ROOT/'tests/support/pre_e2_chunking.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    rows=[]
    for d in [pdf,excel]:
        _,a=old.prepare(copy.deepcopy(d),old.configuration());_,b=prepare(copy.deepcopy(d),configuration())
        assert [c['text'] for c in a]==[c['text'] for c in b]
        assert [c['sources'] for c in a]==[c['sources'] for c in b]
        assert [c['id'] for c in a]!=[c['id'] for c in b]
        if d['ext']=='.pdf':assert all(s['page']==1 for c in b for s in c['sources'])
        rows.append({'ext':d['ext'],'old_ids':[c['id'] for c in a],'new_ids':[c['id'] for c in b],'text_and_sources_unchanged':True})
    import json
    (tmp_path/'non-word-id-impact.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
