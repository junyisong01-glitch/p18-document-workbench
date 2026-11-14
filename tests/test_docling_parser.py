"""Optional Docling DOCX backend. Skipped when the package is not installed.

The fixture is synthetic; it mirrors the E2 structure used elsewhere (numbered
headings, an unlabeled unit note, a simple table and a merged-cell table).
"""
from pathlib import Path

import pytest
from docx import Document

from app import docling_word
from app.chunking import configuration, prepare
from app.parser import PARSER_VERSION, parse_word_selected

pytestmark = pytest.mark.skipif(not docling_word.available(), reason='未安装 docling，跳过可选后端测试')


def build(path):
    doc = Document()
    doc.add_heading('虚构澄星ZX8说明', 0)
    doc.add_heading('1 设备参数', 1)
    doc.add_paragraph('本资料完全虚构，仅供本地软件测试。')
    doc.add_heading('1.1 校准时长', 2)
    doc.add_paragraph('下表为校准时长；单位：分钟。')
    table = doc.add_table(rows=3, cols=2)
    for row, values in zip(table.rows, [['模式', '时长'], ['晨间', '18'], ['夜间', '24']]):
        for cell, value in zip(row.cells, values):
            cell.text = value
    merged = doc.add_table(rows=3, cols=3)
    merged.cell(0, 0).merge(merged.cell(0, 2)).text = '横向标题'
    merged.cell(1, 0).merge(merged.cell(2, 0)).text = '纵向内容'
    merged.cell(1, 1).text = merged.cell(1, 2).text = '相同文字'
    doc.add_heading('2 操作步骤', 1)
    doc.add_paragraph('1. 检查虚构电源。')
    doc.save(path)
    return path


def test_blocks_keep_contract_shape(tmp_path):
    result = docling_word.extract(build(tmp_path / 'x.docx'))
    assert result['characters'] > 0
    assert result['parser_version'].startswith(PARSER_VERSION + '+docling-')
    assert result['pages'] == []
    first = result['blocks'][0]
    assert first['kind'] == 'paragraph' and first['text'] == '虚构澄星ZX8说明'
    assert first['heading_level'] == 1
    headings = [b for b in result['blocks'] if b.get('heading_level') is not None]
    assert [b['heading_level'] for b in headings] == [1, 2, 3, 2]
    # Section scope follows the most recent heading, like parse_word.
    note = next(b for b in result['blocks'] if '单位：分钟' in b['text'])
    assert note['section'] == '1.1 校准时长'
    table = next(b for b in result['blocks'] if b['kind'] == 'table')
    cells = table['tables'][0]['cells']
    assert {(c['row'], c['column']): c['text'] for c in cells}[(2, 1)] == '晨间'
    assert table['tables'][0]['rows'][0] == ['模式', '时长']


def test_merged_cells_are_not_duplicated(tmp_path):
    result = docling_word.extract(build(tmp_path / 'x.docx'))
    merged = [b for b in result['blocks'] if b['kind'] == 'table'][1]['tables'][0]
    assert merged['columns'] == 3
    spanning = next(c for c in merged['cells'] if c['text'] == '横向标题')
    assert (spanning['rowspan'], spanning['colspan']) == (1, 3)
    vertical = next(c for c in merged['cells'] if c['text'] == '纵向内容')
    assert vertical['rowspan'] == 2
    assert sum(1 for c in merged['cells'] if c['text'] == '横向标题') == 1
    assert '横向标题' in [c for row in merged['rows'] for c in row]
    # Review trigger must survive the backend swap.
    assert any(issue['kind'] == 'table' for issue in result['issues'])


def test_e2_context_still_works_on_docling_blocks(tmp_path):
    result = docling_word.extract(build(tmp_path / 'x.docx'))
    doc = {'id': '3dd7d9cc-ccce-4e9c-a1e2-17e9ec61652b', 'name': '虚构澄星ZX8说明.docx',
           'ext': '.docx', 'revision': 1, 'quality': 'clear', 'state': 'ready',
           'characters': result['characters'], 'result': result}
    _, chunks = prepare(doc, configuration())
    table = next(c for c in chunks if c['kind'] == 'table')
    assert '【表格局部上下文】' in table['text']
    assert '单位：分钟' in table['text'] and '18' in table['evidence_text']
    assert all(len(c['text']) <= configuration()['target_chars'] for c in chunks)
    assert not any(c['text'].strip() in {'1 设备参数', '1.1 校准时长'} for c in chunks)


def test_backend_is_opt_in_and_fails_loudly(tmp_path, monkeypatch):
    path = build(tmp_path / 'x.docx')
    monkeypatch.delenv('P18_PARSER', raising=False)
    legacy = parse_word_selected(path, '.docx')
    assert 'parser_version' not in legacy and legacy['blocks'][0]['style'] == 'Title'
    monkeypatch.setenv('P18_PARSER', 'docling')
    optional = parse_word_selected(path, '.docx')
    assert optional['parser_version'].startswith(PARSER_VERSION + '+docling-')
    assert optional['blocks'][0]['style'] == 'title'
    monkeypatch.setattr(docling_word, 'available', lambda: False)
    with pytest.raises(ValueError, match='未安装 docling'):
        parse_word_selected(path, '.docx')
