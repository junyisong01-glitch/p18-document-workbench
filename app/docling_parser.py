"""Docling extraction backend for DOCX/DOC and PDF (see P18_PARSER).

Docling emits a DoclingDocument (title/section_header/text/table items with
page provenance and row/column spans); this module only maps that structure
onto the block schema already consumed by chunking, preview association,
review and library preview. XLSX stays on openpyxl: Docling's spreadsheet
output carries no sheet name, row number or cell coordinate, and those are
product data here, not formatting.

No statement is made about structure Docling did not extract.
"""
from __future__ import annotations

import os

from app.word_structure import PARSER_VERSION

BACKEND = 'docling'
MAX_TEXT = 2_000_000
MAX_PAGES = 200

_CONVERTERS = {}


def available():
    """Cheap probe: never imports docling (or torch) just to answer this."""
    import importlib.util
    try:
        return importlib.util.find_spec('docling') is not None
    except (ImportError, ValueError):
        return False


def _version():
    try:
        import importlib.metadata as metadata
        return metadata.version('docling')
    except Exception:
        return 'unknown'


def configured():
    return os.environ.get('P18_PARSER', '').strip().lower() == BACKEND


def _converter(fmt):
    if fmt not in _CONVERTERS:
        from docling.datamodel.base_models import InputFormat
        from docling.document_converter import DocumentConverter
        _CONVERTERS[fmt] = DocumentConverter(allowed_formats=[getattr(InputFormat, fmt)])
    return _CONVERTERS[fmt]


def _convert(path, fmt):
    try:
        return _converter(fmt).convert(str(path)).document
    except Exception as exc:  # missing model cache, offline download, decode failure
        raise ValueError('Docling 解析失败：本地模型缓存缺失或文件无法解码；'
                         '请确认已完成离线模型准备后重试。') from exc


def _structure(data, identifier):
    """Same shape as word_structure.table_structure, built from Docling cells."""
    rows = [[''] * data.num_cols for _ in range(data.num_rows)]
    filled = [[False] * data.num_cols for _ in range(data.num_rows)]
    cells = []
    for cell in data.table_cells:
        row, column = cell.start_row_offset_idx, cell.start_col_offset_idx
        if row >= data.num_rows or column >= data.num_cols:
            continue
        if filled[row][column]:
            # Continuation of a merged cell already recorded above; never a second cell.
            continue
        rowspan = max(1, cell.end_row_offset_idx - row)
        colspan = max(1, cell.end_col_offset_idx - column)
        cells.append({'id': f'{identifier}-r{row + 1}-c{column + 1}', 'row': row + 1,
                      'column': column + 1, 'rowspan': rowspan, 'colspan': colspan,
                      'text': cell.text})
        for r in range(row, min(row + rowspan, data.num_rows)):
            for c in range(column, min(column + colspan, data.num_cols)):
                filled[r][c] = True
                rows[r][c] = cell.text if (r == row and c == column) else None
    return {'rows': rows, 'cells': cells, 'columns': data.num_cols}


def _table_text(structure):
    return '\n'.join('\t'.join(str(value) for value in row if value is not None)
                     for row in structure['rows'])


def _labels():
    from docling_core.types.doc import DocItemLabel
    return DocItemLabel


def _page_of(item):
    prov = getattr(item, 'prov', None) or []
    return prov[0].page_no if prov else None


def extract_word(path):
    """Return the same result dict keys as parser.parse_word."""
    label = _labels()
    document = _convert(path, 'DOCX')

    blocks, issues = [], []
    section = '正文'
    paragraph_count = table_count = total = 0
    stack = []  # (docling tree level, title) for section-header ancestry

    for item, level in document.iterate_items():
        kind = getattr(item, 'label', None)
        text = (getattr(item, 'text', '') or '').strip()
        if kind in {label.PICTURE}:
            issues.append({'kind': 'image', 'message': '含图片，图片文字未识别，请核对内容完整性。',
                           'page': None, 'block': None})
            continue
        if kind in {label.FORMULA}:
            paragraph_count += 1
            if text:
                blocks.append({'id': f'paragraph-{paragraph_count}', 'kind': 'paragraph',
                               'label': f'{section} · 段落 {paragraph_count}', 'text': text,
                               'tables': [], 'section': section, 'style': 'formula',
                               'has_objects': True, 'heading_level': None})
                total += len(text)
            issues.append({'kind': 'formula', 'message': '含公式对象，请查看原文；当前不保证公式还原。',
                           'page': None, 'block': None})
            continue
        if kind in {label.TABLE}:
            table_count += 1
            identifier = f'table-{table_count}'
            structure = _structure(item.data, identifier)
            body = _table_text(structure)
            total += len(body)
            blocks.append({'id': identifier, 'kind': 'table',
                           'label': f'{section} · 表格 {table_count}', 'text': body,
                           'section': section, 'tables': [{**structure, 'index': table_count}]})
            if any(c['rowspan'] > 1 or c['colspan'] > 1 for c in structure['cells']):
                # Same review trigger as the legacy DOCX backend: merged geometry
                # is preserved but not interpreted.
                issues.append({'kind': 'table',
                               'message': f'表格 {table_count} 存在合并单元格或嵌套结构，请核对行列对应关系。',
                               'page': None, 'block': identifier})
            continue
        if kind in {label.TITLE, label.SECTION_HEADER}:
            while stack and stack[-1][0] >= level:
                stack.pop()
            heading_level = len(stack) + 1
            stack.append((level, text))
            section = text or section
            paragraph_count += 1
            blocks.append({'id': f'paragraph-{paragraph_count}', 'kind': 'paragraph',
                           'label': f'{section} · 段落 {paragraph_count}', 'text': text,
                           'tables': [], 'section': section, 'style': str(kind).lower(),
                           'has_objects': False, 'heading_level': heading_level})
            total += len(text)
            continue
        if not text:
            continue
        paragraph_count += 1
        style = 'code' if kind in {label.CODE} else str(kind).lower()
        blocks.append({'id': f'paragraph-{paragraph_count}', 'kind': 'paragraph',
                       'label': f'{section} · 段落 {paragraph_count}', 'text': text,
                       'tables': [], 'section': section, 'style': style,
                       'has_objects': False, 'heading_level': None})
        total += len(text)

    if total > MAX_TEXT:
        raise ValueError('提取内容超过 200 万字符，请拆分文档。')
    return {'blocks': blocks, 'issues': issues, 'pages': [], 'characters': total,
            'parser_version': f'{PARSER_VERSION}+{BACKEND}-{_version()}'}


def extract_pdf(path):
    """Return the same result dict keys as parser.parse_pdf (page-aware blocks)."""
    import pymupdf as fitz

    with fitz.open(path) as raw:
        page_count = raw.page_count
    if page_count > MAX_PAGES:
        raise ValueError(f'PDF 超过 {MAX_PAGES} 页限制。')

    label = _labels()
    document = _convert(path, 'PDF')

    blocks, issues = [], []
    section = '正文'
    paragraph_count = table_count = total = 0
    per_page = {}
    stack = []

    for item, level in document.iterate_items():
        kind = getattr(item, 'label', None)
        text = (getattr(item, 'text', '') or '').strip()
        page = _page_of(item)
        where = {'page': page, 'block': None}
        if kind in {label.PICTURE}:
            issues.append({'kind': 'image', 'message': '本页包含图片，图片文字未识别，请核对内容是否完整。', **where})
            continue
        if kind in {label.FORMULA}:
            issues.append({'kind': 'formula', 'message': '含公式对象，请查看原文；当前不保证公式还原。', **where})
            continue
        if kind in {label.TABLE}:
            table_count += 1
            identifier = f'table-{table_count}'
            structure = _structure(item.data, identifier)
            body = _table_text(structure)
            total += len(body)
            per_page[page] = per_page.get(page, 0) + len(body)
            blocks.append({'id': identifier, 'kind': 'table', 'page': page,
                           'label': f'第 {page} 页 · 表格 {table_count}' if page else f'表格 {table_count}',
                           'text': body, 'section': section,
                           'tables': [{**structure, 'index': table_count}]})
            if any(c['rowspan'] > 1 or c['colspan'] > 1 for c in structure['cells']):
                issues.append({'kind': 'table',
                               'message': f'表格 {table_count} 可能包含合并或缺失单元格，请核对行列对应关系。',
                               **where})
            continue
        if not text:
            continue
        if kind in {label.TITLE, label.SECTION_HEADER}:
            while stack and stack[-1][0] >= level:
                stack.pop()
            heading_level = len(stack) + 1
            stack.append((level, text))
            section = text or section
        else:
            heading_level = None
        paragraph_count += 1
        total += len(text)
        per_page[page] = per_page.get(page, 0) + len(text)
        blocks.append({'id': f'paragraph-{paragraph_count}', 'kind': 'paragraph', 'page': page,
                       'label': f'第 {page} 页 · 段落 {paragraph_count}' if page else f'段落 {paragraph_count}',
                       'text': text, 'tables': [], 'section': section,
                       'style': str(kind).lower() if kind is not None else '',
                       'has_objects': False, 'heading_level': heading_level})

    if total > MAX_TEXT:
        raise ValueError('提取内容超过 200 万字符，请拆分文档。')
    # A page with no extracted text is one review signal, not two: the legacy
    # PDF path reports no_text there and never also reports its picture.
    issues = [issue for issue in issues
              if not (issue['kind'] == 'image' and not per_page.get(issue['page']))]
    pages = []
    for number in range(1, page_count + 1):
        characters = per_page.get(number, 0)
        entry = {'page': number, 'characters': characters}
        if not characters:
            entry['blank'] = True
            issues.append({'kind': 'no_text',
                           'message': '未提取到文字，可能包含扫描内容；请核对是否遗漏。',
                           'page': number, 'block': None})
        pages.append(entry)
    return {'blocks': blocks, 'issues': issues, 'pages': pages, 'characters': total,
            'parser_version': f'{PARSER_VERSION}+{BACKEND}-{_version()}'}
