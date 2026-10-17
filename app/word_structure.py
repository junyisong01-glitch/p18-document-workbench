"""Physical Word cells and conservative converted-preview text anchors."""
import re
from docx.oxml.ns import qn
from docx.table import _Cell
import pymupdf as fitz

PARSER_VERSION = 'word-structure-v2'

def table_structure(table, identifier):
    cells, rows, active = [], [], {}
    for r, tr in enumerate(table._tbl.tr_lst, 1):
        before = tr.find('./' + qn('w:trPr') + '/' + qn('w:gridBefore'))
        col = int(before.get(qn('w:val'), '0')) if before is not None else 0
        row, next_active = [''] * col, {}
        for tc in tr.tc_lst:
            span = tc.grid_span
            merge = tc.vMerge
            text = _Cell(tc, table).text
            key = (col, span)
            anchor = active.get(key) if merge == 'continue' else None
            # Unexpected content in continuation cells must never be discarded.
            if anchor is not None and not text.strip():
                anchor['rowspan'] += 1
                next_active[key] = anchor
                row.extend([None] * span)
            else:
                cell = dict(id=f'{identifier}-r{r}-c{col+1}', row=r, column=col+1,
                            rowspan=1, colspan=span, text=text)
                cells.append(cell)
                row.extend([text] + [None] * (span-1))
                if merge in ('restart', 'continue'):
                    next_active[key] = cell
            col += span
        rows.append(row)
        active = next_active
    width = max([len(row) for row in rows] + [0])
    rows = [row + [''] * (width-len(row)) for row in rows]
    return dict(rows=rows, cells=cells, columns=width)

def table_text(table):
    return '\n'.join('\t'.join(str(c) for c in row if c is not None) for row in table['rows'])

def normalized(text):
    return re.sub(r'\s+', '', text or '')

def associate_preview(blocks, path, variant):
    with fitz.open(path) as pdf:
        pages = [normalized(p.get_text(sort=True)) for p in pdf]
    for block in blocks:
        for item in [block] + [c for t in block.get('tables', []) for c in t.get('cells', [])]:
            needle = normalized(item.get('text'))
            counts = [p.count(needle) for p in pages] if len(needle) >= 8 else []
            mapping = item.setdefault('preview_pages', {})
            if sum(counts) == 1:
                mapping[variant] = counts.index(1) + 1
    return pages

def compatibility_copy(source, destination):
    """Change fonts only in a disposable preview copy, including inherited runs."""
    import zipfile
    from lxml import etree
    font = 'Arial Unicode MS'
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(destination, 'w') as out:
        for entry in src.infolist():
            data = src.read(entry.filename)
            if entry.filename.startswith('word/') and entry.filename.endswith('.xml'):
                root = etree.fromstring(data)
                for run in root.iter(qn('w:r')):
                    props = run.find(qn('w:rPr'))
                    if props is None:
                        props = etree.Element(qn('w:rPr')); run.insert(0, props)
                    fonts = props.find(qn('w:rFonts'))
                    if fonts is None:
                        fonts = etree.SubElement(props, qn('w:rFonts'))
                    fonts.attrib.clear()
                    for key in ('ascii', 'hAnsi', 'eastAsia', 'cs'):
                        fonts.set(qn('w:' + key), font)
                data = etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)
            out.writestr(entry, data)
