from openpyxl import Workbook
import pytest
from app.parser import process
from app.chunking import prepare,configuration


def test_excel_rows_sources_values_and_formula_are_preserved(tmp_path):
    w=Workbook();s=w.active;s.title='通讯录'
    s.append(['编号','姓名','金额','日期']);s.append([7,'测试甲',0,None]);s['A2'].number_format='0000'
    s['C3']='=SUM(C2:C2)';s.merge_cells('A4:B4');s['A4']='合并标题'
    w.create_sheet('隐藏表').sheet_state='hidden'
    w.save(tmp_path/'original.xlsx')
    r=process(tmp_path,'.xlsx')
    assert any('0007' in b['text'] and '金额：0' in b['text'] for b in r['blocks'])
    assert any(c['formula']=='=SUM(C2:C2)' and c['warning'] for b in r['blocks'] for c in b['cells'])
    assert not any('=SUM' in b['text'] for b in r['blocks'])
    assert {i['kind'] for i in r['issues']} >= {'formula','table','structure'}
    doc={'id':'xlsx','name':'测试通讯录','ext':'.xlsx','revision':1,'quality':'review','result':r}
    _,chunks=prepare(doc,configuration())
    assert chunks
    assert all(c['sources'][0]['block_id'].startswith('sheet-') for c in chunks)
    assert any('第2行' in c['sources'][0]['label'] for c in chunks)
    assert r['preview']=={} and r['pages']==[]


def test_invalid_empty_and_oversized_excel(tmp_path):
    p=tmp_path/'original.xlsx';p.write_bytes(b'not excel')
    with pytest.raises(ValueError):process(tmp_path,'.xlsx')
    w=Workbook();w.save(p)
    assert process(tmp_path,'.xlsx')['error']
    w.active.cell(20001,1,'beyond limit');w.save(p)
    with pytest.raises(ValueError):process(tmp_path,'.xlsx')


def test_styled_fourth_row_side_table_total_and_parameter(tmp_path):
    from openpyxl.styles import Font,PatternFill
    w=Workbook();s=w.active
    s['A1']='文档标题';s['A2']='说明';
    for col,label in enumerate(['编号','姓名','金额'],1):
        c=s.cell(4,col,label);c.font=Font(bold=True);c.fill=PatternFill('solid',fgColor='DDE6F0')
    s['E4']='等级';s['F4']='系数'
    for c in ['E4','F4']:s[c].font=Font(bold=True)
    for i in range(5,9):
        s.cell(i,1,i);s.cell(i,2,'人员'+str(i));s.cell(i,3,0)
    s['E5']='A';s['F5']=1;s['E6']='B';s['F6']=0
    s['E8']='奖金比例';s['F8']=.3
    s['B9']='合计';s['C9']=0
    w.save(tmp_path/'original.xlsx');r=process(tmp_path,'.xlsx')
    v=r['excel_sheets'][0]
    assert len(v['metadata'])==2
    assert [(t['header_row'],len(t['rows']),len(t['summary_rows'])) for t in v['tables']]==[(4,4,1),(4,2,0)]
    assert v['tables'][1]['range']=='E4:F6'
    assert [n['row'] for n in v['other_rows']]==[8]
    assert not any('系数' in b['text'] for b in r['blocks'] if b.get('table_id')=='table-1-1')
    _,chunks=prepare({'id':'a','ext':'.xlsx','revision':1,'name':'测试表','quality':'clear','result':r},configuration())
    assert all(c['text'].count('文档：')==1 and c['text'].count('工作表：')==1 for c in chunks)
    assert all(not __import__('re').search(r'\[[A-Z]+[0-9]+\]',c['text']) for c in chunks)
    assert any(len(c['records'])>1 for c in chunks)


def test_formula_saved_cache_and_missing_zero(tmp_path):
    import zipfile
    from lxml import etree
    w=Workbook();s=w.active;s.append(['姓名','金额']);s.append(['甲','=1-1']);s.append(['乙','=1+1']);w.save(tmp_path/'original.xlsx')
    path=tmp_path/'original.xlsx'
    with zipfile.ZipFile(path) as z: parts={n:z.read(n) for n in z.namelist()}
    ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    root=etree.fromstring(parts['xl/worksheets/sheet1.xml']);root.find('.//s:c[@r="B2"]/s:v',ns).text='0'
    parts['xl/worksheets/sheet1.xml']=etree.tostring(root)
    with zipfile.ZipFile(path,'w') as z:
        for n,b in parts.items():z.writestr(n,b)
    r=process(tmp_path,'.xlsx')
    cells={c['coordinate']:c for b in r['blocks'] for c in b['cells']}
    assert cells['B2']['text']=='0' and cells['B2']['formula_cached'] and not cells['B2']['warning']
    assert cells['B3']['warning'] and not cells['B3']['formula_cached']


def test_review_records_searchable_but_hold_and_failed_not(tmp_path):
    from app.admission import sync_admission
    w=Workbook();s=w.active;s.append(['姓名','金额']);s.append(['甲','=1+1']);w.save(tmp_path/'original.xlsx')
    result=process(tmp_path,'.xlsx')
    doc=dict(id='x',ext='.xlsx',revision=1,state='review',quality='review',characters=result['characters'],result=result)
    sync_admission(doc)
    assert doc['admission']['eligible'] and doc['admission']['review_required']
    for state in ['held','failed']:
        doc['state']=state;sync_admission(doc);assert not doc['admission']['eligible']


def test_no_header_and_uncertain_labels_are_reviewable(tmp_path):
    w=Workbook();s=w.active;s['A1']='孤立说明';s['C4']=12;w.save(tmp_path/'original.xlsx')
    r=process(tmp_path,'.xlsx')
    assert r['issues'] and all(b['review_required'] for b in r['blocks'])
    assert sum(len(b['cells']) for b in r['blocks'])==2
