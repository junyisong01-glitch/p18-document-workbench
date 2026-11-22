"""Bounded local text/table readers. No executable HTML, formulas or network calls."""
import csv
import io
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font
from app.excel_parser import MAX_CELLS, MAX_COLUMNS, MAX_ROWS, MAX_SHEETS, parse_workbooks

MAX_TEXT = 2_000_000


def read_text(path):
    raw = Path(path).read_bytes()
    encodings = ('utf-16',) if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else ('utf-8-sig', 'gb18030')
    for encoding in encodings:
        try:
            text = raw.decode(encoding)
            break
        except UnicodeError:
            continue
    else:
        raise ValueError('文字编码无法识别，请另存为 UTF-8 后上传。')
    if any(ord(c) < 32 and c not in '\t\r\n' for c in text) or '\ufffd' in text:
        raise ValueError('文本含控制字符或乱码，请确认文件格式并另存为 UTF-8。')
    if len(text) > MAX_TEXT:
        raise ValueError('提取内容超过200万字符，请拆分文件。')
    return text.replace('\r\n', '\n').replace('\r', '\n'), encoding


def parse_text(path, markdown=False):
    text, encoding = read_text(path)
    lines = text.splitlines(keepends=True)
    blocks, section = [], '正文'
    def emit(start, end, **extra):
        raw = ''.join(lines[start:end]).rstrip('\n')
        if raw.strip():
            blocks.append(dict(id=f'lines-{start+1}-{end}', kind='paragraph', text=raw,
                label=f'第 {start+1}—{end} 行', section=section,
                line_start=start+1, line_end=end, tables=[], **extra))
    if markdown:
        from markdown_it import MarkdownIt
        tokens = MarkdownIt('commonmark', {'html': False}).enable('table').parse(text)
        # Top-level spans preserve all original source text, including HTML and code as inert text.
        cursor = 0
        for i, token in enumerate(tokens):
            if token.map is None or token.level != 0 or token.nesting == -1:
                continue
            start, end = token.map
            if start < cursor:
                continue
            emit(cursor, start)
            if token.type == 'heading_open':
                section = tokens[i+1].content
                emit(start,end,heading_level=int(token.tag[1:]))
            elif token.type == 'table_open':
                rows=[]
                for child in tokens[i+1:]:
                    if child.type=='table_close':break
                    if child.type=='tr_open':rows.append([])
                    if child.type=='inline' and rows:rows[-1].append(child.content)
                emit(start,end)
                blocks[-1].update(kind='table',tables=[{'rows':rows}])
            elif token.type in {'fence','code_block'}:
                emit(start,end,style='Code')
            else:
                emit(start,end)
            cursor=end
        emit(cursor,len(lines))
    else:
        start=0
        for i,line in enumerate(lines):
            if not line.strip() or i-start>=100:
                emit(start,i);start=i if line.strip() else i+1
        emit(start,len(lines))
    return dict(blocks=blocks,issues=[],pages=[],characters=len(text.strip()),encoding=encoding,
                parser_version='local-text-v1')


def parse_csv(path):
    text, encoding = read_text(path)
    try:
        dialect=csv.Sniffer().sniff(text[:65536],delimiters=',;\t|')
    except csv.Error:
        dialect=csv.excel
    book=Workbook();sheet=book.active;sheet.title='CSV 数据'
    cells=0;record_lines=[]
    reader=csv.reader(io.StringIO(text,newline=''),dialect=dialect,strict=True)
    try:
        previous=0
        for number,row in enumerate(reader,1):
            if number>MAX_ROWS or len(row)>MAX_COLUMNS:
                raise ValueError('CSV 超过20000条记录或256列限制，请拆分文件。')
            cells+=len(row)
            if cells>MAX_CELLS:raise ValueError('CSV 超过10万个单元格限制，请拆分文件。')
            record_lines.append((previous+1,reader.line_num));previous=reader.line_num
            for column,value in enumerate(row,1):
                # CSV strings such as =1+1 and 00123 are original text, never Excel formulas/numbers.
                cell=sheet.cell(number,column,value);cell.data_type='s'
    except csv.Error as exc:
        raise ValueError('CSV 引号、分隔符或字段长度异常，请重新导出。') from exc
    result=parse_workbooks(book,book)
    if not any(c['text'].strip() for b in result['blocks'] for c in b.get('cells',[])):
        result['characters']=0
    for block in result['blocks']:
        start,end=record_lines[block['row_start']-1]
        block.update(line_start=start,line_end=end)
        block['label']=f"CSV 第{block['row_start']}条记录 · 原文件第{start}—{end}行"
    result.update(encoding=encoding,parser_version='local-csv-v1')
    return result


def parse_xls(path):
    import xlrd
    try:
        source=xlrd.open_workbook(path,formatting_info=True,on_demand=True)
    except (xlrd.XLRDError, ValueError) as exc:
        raise ValueError('XLS 无法读取，请检查是否加密、损坏或实际为其他格式。') from exc
    book=Workbook();book.remove(book.active);count=0
    try:
        if source.nsheets>MAX_SHEETS:raise ValueError('Excel 超过50个工作表限制。')
        for index in range(source.nsheets):
            original=source.sheet_by_index(index)
            if original.nrows>MAX_ROWS or original.ncols>MAX_COLUMNS:
                raise ValueError('Excel 超过20000行或256列限制。')
            count+=original.nrows*original.ncols
            if count>MAX_CELLS:raise ValueError('Excel 超过10万个单元格范围限制。')
            sheet=book.create_sheet(original.name);sheet.sheet_state='hidden' if original.visibility else 'visible'
            for r in range(original.nrows):
                for c in range(original.ncols):
                    old=original.cell(r,c)
                    if old.ctype in (xlrd.XL_CELL_EMPTY,xlrd.XL_CELL_BLANK):continue
                    value=old.value
                    if old.ctype==xlrd.XL_CELL_DATE:
                        value=xlrd.xldate_as_datetime(value,source.datemode)
                    elif old.ctype==xlrd.XL_CELL_BOOLEAN:value=bool(value)
                    elif old.ctype==xlrd.XL_CELL_NUMBER and value==int(value):value=int(value)
                    elif old.ctype==xlrd.XL_CELL_ERROR:value=xlrd.error_text_from_code.get(value,'#VALUE!')
                    cell=sheet.cell(r+1,c+1,value)
                    if old.ctype==xlrd.XL_CELL_TEXT:cell.data_type='s'
                    if old.ctype==xlrd.XL_CELL_ERROR:cell.data_type='e'
                    xf=source.xf_list[original.cell_xf_index(r,c)]
                    cell.number_format=source.format_map[xf.format_key].format_str
                    cell.font=Font(bold=bool(source.font_list[xf.font_index].bold))
            for r0,r1,c0,c1 in original.merged_cells:
                sheet.merge_cells(start_row=r0+1,end_row=r1,start_column=c0+1,end_column=c1)
            source.unload_sheet(index)
    finally:
        source.release_resources()
    result=parse_workbooks(book,book)
    result['parser_version']='local-xls-v1'
    # xlrd cannot expose formula expressions, charts or embedded images. Require source review.
    result['issues'].append(dict(kind='objects',message='旧版 XLS 仅读取单元格已保存值，不还原公式、图表或嵌入对象，请核对原文件。',page=None,block=None))
    return result
