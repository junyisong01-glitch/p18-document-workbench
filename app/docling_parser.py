"""Optional Docling DOCX extraction adapter; PDF/XLSX remain on the original backends.

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
    return os.environ.get('P18_PARSER', 'legacy').strip().lower() == BACKEND


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
    # Optional backend is conservative on verbatim code and unsupported notes.
    # Fail before normalization rather than silently altering code indentation.
    from docx import Document
    from docx.text.paragraph import Paragraph
    from zipfile import ZipFile
    original = Document(path)
    for node in original.element.body.xpath('.//w:p'):
        paragraph = Paragraph(node, original._body)
        text = paragraph.text
        if text.startswith((' ', '\t')) or '\n ' in text or '\n\t' in text or 'code' in paragraph.style.name.lower():
            raise ValueError('Docling 可选模式未保证逐字代码缩进，请使用 legacy 解析该文档。')
    with ZipFile(path) as archive:
        if any(name in archive.namelist() for name in ('word/footnotes.xml','word/endnotes.xml')):
            raise ValueError('Docling 可选模式未验证脚注/尾注来源，请使用 legacy 解析该文档。')
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
