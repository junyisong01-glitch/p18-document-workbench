"""Local XLSX structure extraction. Uses saved formula values; never evaluates code."""
from datetime import date, datetime, time
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

VERSION = 'excel-structure-v2'
MAX_SHEETS, MAX_ROWS, MAX_COLUMNS, MAX_CELLS = 50, 20000, 256, 100000


def cell_text(cell):
    value = cell.value
    if value is None: return ''
    if isinstance(value, (datetime, date, time)): return value.isoformat()
    if isinstance(value, bool): return 'TRUE' if value else 'FALSE'
    if isinstance(value, int) and cell.number_format and set(cell.number_format) == {'0'}:
        return str(value).zfill(len(cell.number_format))
    return str(value)


def runs(columns):
    result = []
    for col in columns:
        if result and result[-1][-1] == col - 1: result[-1].append(col)
        else: result.append([col])
    return result


def header_candidates(sheet):
    """Transparent heuristics, not probabilities. No document/row-name special cases."""
    candidates = []
    for r in range(1, sheet.max_row + 1):
        cols = [c.column for c in sheet[r] if c.value is not None]
        for group in runs(cols):
            cells = [sheet.cell(r, c) for c in group]
            labels = [cell_text(c).strip() for c in cells]
            if len(cells) < 2 or not all(c.data_type == 's' and 0 < len(v) <= 40 for c, v in zip(cells, labels)): continue
            below = [n for n in range(r+1, min(sheet.max_row, r+4)+1)
                     if sum(sheet.cell(n,c).value is not None for c in group) >= len(group)*.7]
            if not below: continue
            bold = sum(bool(c.font.bold) for c in cells)/len(cells)
            fill = sum(c.fill.patternType == 'solid' for c in cells)/len(cells)
            previous = [sheet.cell(r-1,c).value for c in group] if r > 1 else []
            position = r == 1 or sum(v is not None for v in previous) <= 1
            reasons = ['字段为短文字', '下方列结构一致']
            score = 2 + (2 if len(below)>=2 else 1)
            if bold >= .7: score += 3; reasons.append('字段统一加粗')
            if fill >= .7: score += 2; reasons.append('字段有底色')
            if position: score += 1; reasons.append('上方为空行或说明')
            if len(set(labels)) != len(labels): score -= 3; reasons.append('字段重复')
            candidates.append(dict(row=r, start=group[0], end=group[-1], labels=labels, score=score, reasons=reasons))
    # Strongest independent column regions first. Later strong headers may start a new table below.
    chosen = []
    for c in sorted(candidates, key=lambda x:(-x['score'], x['row'])):
        if any(not (c['end'] < p['start'] or c['start'] > p['end']) and not (c['score']>=7 and p['score']>=7 and c['row']!=p['row'] and c['start']==p['start'] and c['end']==p['end']) for p in chosen): continue
        chosen.append(c)
    return sorted(chosen,key=lambda x:(x['row'],x['start']))


def parse_excel(path):
    from app.parser import MAX_TEXT, issue
    book = load_workbook(path, data_only=False, keep_links=False)
    cache = load_workbook(path, data_only=True, keep_links=False)
    blocks, issues, views, total = [], [], [], 0
    try:
        if len(book.worksheets) > MAX_SHEETS: raise ValueError('Excel 超过50个工作表限制。')
        count = 0
        for number, sheet in enumerate(book.worksheets, 1):
            if sheet.max_row > MAX_ROWS or sheet.max_column > MAX_COLUMNS: raise ValueError('Excel 超过20000行或256列限制。')
            count += sheet.max_row*sheet.max_column
            if count > MAX_CELLS: raise ValueError('Excel 超过10万个单元格范围限制。')
            candidates = header_candidates(sheet)
            first_header = min((h['row'] for h in candidates), default=1)
            view = dict(name=sheet.title, metadata=[], tables=[], other_rows=[], merges=[str(x) for x in sheet.merged_cells.ranges])
            views.append(view)
            if sheet.sheet_state != 'visible': issues.append(issue('structure', f'工作表「{sheet.title}」隐藏，需核对使用范围。'))
            if sheet.merged_cells.ranges: issues.append(issue('table', f'「{sheet.title}」存在合并区域，需核对表头层级和对应关系。'))
            if sheet._charts or sheet._images: issues.append(issue('image', f'「{sheet.title}」包含未提取的图表或图片。'))
            used = set()

            def read(c):
                formula = c.value if c.data_type == 'f' else None
                cached = cache[sheet.title][c.coordinate]
                display = cell_text(cached) if formula else cell_text(c)
                warning = ''
                if formula and (cached.value is None or cached.data_type == 'e'):
                    display = '待确认（公式无有效缓存值）'; warning = '公式没有可用的已保存计算结果'
                if not formula and c.data_type == 'e': warning = '单元格含错误值'
                return dict(coordinate=c.coordinate, text=display, formula=formula,
                            formula_cached=bool(formula and not warning), warning=warning)

            def emit(kind, r, text, cells, table_id=None, review=False, **extra):
                nonlocal total
                bid = f'sheet-{number}-row-{r}-'+(table_id or kind)
                blocks.append(dict(id=bid,kind=kind,text=text,sheet=sheet.title,section=sheet.title,
                    label=f'工作表「{sheet.title}」 · 第{r}行',row_start=r,row_end=r,table_id=table_id,
                    cells=cells,review_required=review,**extra))
                total += len(text)
                if total > MAX_TEXT: raise ValueError('提取内容超过200万字符，请拆分文件。')
                for c in cells:
                    if c['warning']: issues.append(issue('formula' if c['formula'] else 'characters',f"{sheet.title}!{c['coordinate']}：{c['warning']}",block=bid))

            for r in range(1, first_header):
                cells=[read(c) for c in sheet[r] if c.value is not None]
                if cells:
                    view['metadata'].append(dict(row=r,cells=cells))
                    emit('excel_metadata',r,'；'.join(c['text'] for c in cells),cells)
                    used.update((r,c.column) for c in sheet[r] if c.value is not None)

            for index,h in enumerate(candidates,1):
                tid=f'table-{number}-{index}'
                review=h['score'] < 7 or bool(sheet.merged_cells.ranges)
                if review: issues.append(issue('table',f"「{sheet.title}」候选表头第{h['row']}行需复核："+'、'.join(h['reasons'])))
                table=dict(id=tid,header_row=h['row'],header_confirmed=not review,reasons=h['reasons'],
                    range=f"{get_column_letter(h['start'])}{h['row']}:{get_column_letter(h['end'])}{sheet.max_row}",
                    headers=h['labels'],rows=[],summary_rows=[])
                view['tables'].append(table)
                used.update((h['row'],col) for col in range(h['start'],h['end']+1))
                end_row=min([p['row']-1 for p in candidates if p['row']>h['row'] and not(p['end']<h['start'] or p['start']>h['end'])]+[sheet.max_row])
                for r in range(h['row']+1,end_row+1):
                    cells=[read(sheet.cell(r,c)) for c in range(h['start'],h['end']+1)]
                    populated=[c for c in cells if sheet[c['coordinate']].value is not None]
                    if not populated: break
                    used.update((r,c) for c in range(h['start'],h['end']+1))
                    summary=any(c['text'].strip() in {'合计','总计','小计'} for c in cells[:2])
                    row_review=review or any(c['warning'] for c in cells)
                    text='；'.join(f'{label}：{c["text"] or "未填写"}'+('（此值由公式计算，读取已保存结果）' if c['formula_cached'] else '') for label,c in zip(h['labels'],cells))
                    if review: text='需要复核：以下字段对应关系尚未确认。'+text
                    if summary: text='汇总记录；'+text
                    record=dict(row=r,cells=cells,review_required=row_review)
                    table['summary_rows' if summary else 'rows'].append(record)
                    emit('excel_summary' if summary else 'excel_record',r,text,cells,tid,row_review,header_row=h['row'])
                    if summary: break
                last=max([x['row'] for x in table['rows']+table['summary_rows']]+[h['row']])
                table['range']=f"{get_column_letter(h['start'])}{h['row']}:{get_column_letter(h['end'])}{last}"
            # Keep unassigned cells as separate notes/parameters, never attach a side table to employee rows.
            for r in range(first_header,sheet.max_row+1):
                cells=[read(c) for c in sheet[r] if c.value is not None and (r,c.column) not in used]
                if not cells: continue
                review=not candidates
                if review: issues.append(issue('table',f'「{sheet.title}」第{r}行未能可靠识别字段，请复核。'))
                view['other_rows'].append(dict(row=r,cells=cells,review_required=review))
                # Coordinates remain in source metadata only; do not invent field names.
                emit('excel_note',r,('需要复核；' if review else '补充说明；')+'；'.join(c['text'] for c in cells),cells,review=review)
        return dict(blocks=blocks,issues=issues,pages=[],characters=total,excel_sheets=views,
                    excel_parser_version=VERSION,excel_review_policy='record-warning-v1')
    finally:
        book.close(); cache.close()
