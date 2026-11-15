"""Run with optional Docling environment; default runtime explicitly skips these."""
from pathlib import Path
import pytest
from docx import Document
from app import docling_parser
from app.parser import parse_word_selected
from app.chunking import prepare,configuration
pytestmark=pytest.mark.skipif(not docling_parser.available(),reason='Optional Docling dependency not installed in this interpreter')


def fixture(path):
    d=Document();d.add_heading('虚构仪器参数',0);d.add_heading('1 设置',1);d.add_paragraph('表格适用晨间模式，单位：分钟。');t=d.add_table(rows=3,cols=2)
    for row,values in zip(t.rows,[['模式','时长'],['晨间','18'],['夜间','24']]):
        for cell,text in zip(row.cells,values):cell.text=text
    m=d.add_table(rows=2,cols=2);m.cell(0,0).merge(m.cell(0,1)).text='合并标题';m.cell(1,0).text='左';m.cell(1,1).text='右';d.save(path);return path


def test_real_docling_docx_preserves_table_hierarchy_and_e2_sources(tmp_path,monkeypatch):
    monkeypatch.setenv('P18_PARSER','docling');p=fixture(tmp_path/'x.docx');r=parse_word_selected(p)
    assert r['parser_version'].startswith('word-structure-v2+docling-2.150.1')
    tables=[b for b in r['blocks']if b['kind']=='table'];assert tables[0]['tables'][0]['rows']==[['模式','时长'],['晨间','18'],['夜间','24']]
    assert any(c['text']=='合并标题'and c['colspan']==2 for c in tables[1]['tables'][0]['cells'])
    d={'id':'optional-docling-fixture','ext':'.docx','name':'x.docx','revision':1,'state':'ready','quality':'clear','characters':r['characters'],'result':r}
    _,chunks=prepare(d,configuration());assert any('单位：分钟'in c['text']and'18'in c['evidence_text']for c in chunks if c['kind']=='table');assert all(s.get('block_id')for c in chunks for s in c['sources'])
    assert all(len(c['text'])<=configuration()['target_chars']for c in chunks)


def test_docling_code_fails_closed_and_legacy_still_preserves_it(tmp_path,monkeypatch):
    d=Document();d.add_paragraph('    code_call()');p=tmp_path/'code.docx';d.save(p)
    monkeypatch.setenv('P18_PARSER','docling')
    with pytest.raises(ValueError,match='缩进'):parse_word_selected(p)
    monkeypatch.setenv('P18_PARSER','legacy');assert parse_word_selected(p)['blocks'][0]['text']=='    code_call()'


def test_installing_docling_does_not_select_it(tmp_path,monkeypatch):
    monkeypatch.delenv('P18_PARSER',raising=False);r=parse_word_selected(fixture(tmp_path/'legacy.docx'));assert 'parser_version'not in r
