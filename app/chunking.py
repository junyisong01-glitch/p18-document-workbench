"""Local, deterministic preparation. Sources always refer to extraction blocks.

No OCR, model calls, code execution or inferred cross-page joins.
"""
from bisect import bisect_right
import hashlib
import json
import os
import re
import uuid

METHOD = 'local-rules-word-e1'
LEGACY_METHOD = 'local-rules-v3'


def configuration():
    try:
        target = int(os.environ.get('P18_CHUNK_TARGET', '500'))
        overlap = int(os.environ.get('P18_CHUNK_OVERLAP', '50'))
    except ValueError as exc:
        raise ValueError('切分参数必须为整数，请检查 P18_CHUNK_TARGET / P18_CHUNK_OVERLAP。') from exc
    if not 80 <= target <= 20000 or not 0 <= overlap < target // 2:
        raise ValueError('目标长度需为 80–20000 字符，重叠需非负且小于目标长度的一半。')
    return {'method': METHOD, 'target_chars': target, 'overlap_chars': overlap, 'unit': 'unicode_characters'}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _content_fingerprint(doc):
    return digest({'revision': doc['revision'], 'result': doc.get('result'),
                   'incomplete': doc.get('admission', {}).get('incomplete'), 'quality': doc.get('quality')})


TABLE_CONTEXT_METHOD = 'word-table-local-context-e2'


def fingerprint(doc):
    content = _content_fingerprint(doc)
    if doc.get('ext') in {'.docx', '.doc'} and any(
            b.get('kind') == 'table' for b in doc.get('result', {}).get('blocks', [])):
        return digest({'content': content, 'word_table_context': TABLE_CONTEXT_METHOD})
    return content


def tidy(text):
    # Preserve indentation, tabs, technical symbols and every non-whitespace char.
    return re.sub(r'\n[ \t]*\n(?:[ \t]*\n)+', '\n\n', text.replace('\r\n', '\n').replace('\r', '\n')).strip('\n')


HEADING = re.compile(r'^(?:#{1,6}\s+|第[一二三四五六七八九十百\d]+[章节篇]\s*|[一二三四五六七八九十]+[、．]\s*|\d+(?:\.\d+)*\s+\S)')
STEP = re.compile(r'^\s*(?:\d+[.)、]\s*|第[一二三四五六七八九十\d]+步|步骤\s*\d+)')
CODE = re.compile(r'^\s*(?:```|~~~|(?:async\s+)?def\s+\w+\s*\(|class\s+\w+|function\s+\w*\s*\(|(?:public|private|protected)\s+|(?:GET|POST|PUT|PATCH|DELETE)\s+/)')


def source_for(doc, block, start=0, end=None):
    src = {'block_id': block.get('id'), 'label': block.get('label', '文档级来源'),
           'variant': 'converted' if doc['ext'] == '.doc' else 'original'}
    for key in ('sheet','row_start','row_end'):
        if key in block: src[key]=block[key]
    if block.get('preview_pages'):
        src['preview_pages'] = block['preview_pages']
    if block.get('page') is not None:
        src['page'] = block['page']
    if isinstance(block.get('text'), str):
        src.update(raw_start=start, raw_end=len(block['text']) if end is None else end)
    return src


def units_from(doc):
    units, warnings = [], []
    section = '正文'
    inside_fence = None
    source_section = None
    for block in (doc.get('result') or {}).get('blocks', []):
        raw = block.get('text', '')
        title = block.get('section') or block.get('label', '').split(' · ')[0]
        if block.get('kind') == 'paragraph' and not inside_fence:
            # Unchanged parent metadata must not erase a numbered subheading.
            if title and title != source_section:
                if title != '正文':
                    section = title
                source_section = title
        if block.get('kind') == 'table':
            caption = units[-1] if units and re.match(r'^\s*(?:表\s*\d+|Table\s+\d+)', units[-1]['text'], re.I) else None
            units.append({'kind': 'table', 'text': raw, 'section': section,
                          'sources': ([source_for(doc, block)] + (caption['sources'] if caption else [])), 'tables': block.get('tables', []), 'table_title': caption['text'] if caption else section})
            continue
        if block.get('kind') == 'page' and block.get('tables'):
            # Existing PDF extraction has no table/text offset alignment. Do not
            # guess which text to remove, or append the table text a second time.
            units.append({'kind': 'pdf_page', 'text': raw, 'section': section,
                          'sources': [source_for(doc, block)], 'tables': block['tables']})
            warnings.append('PDF 表格与页内正文缺少可靠位置映射：整页保留并关联已提取表格，不按行拆分、不去重。')
            continue
        if not raw.strip():
            units.append({'kind':'blank','text':raw,'section':section,'sources':[source_for(doc,block)]})
            continue
        # Preserve a complete multi-line code paragraph, including its blank lines.
        code_like = (inside_fence or CODE.search(raw) or block.get('style', '').lower() in {'code', 'source code'}
                     or raw.strip() in {'{','['}
                     or ('\n' in raw and raw.lstrip().startswith(('{', '['))))
        if block.get('kind') == 'page' and not code_like:
            # Fence state changes within a page. Keep blank lines inside code.
            parts = [(m.start(), m.start() + len(m.group().removesuffix('\n')), m.group().removesuffix('\n'))
                     for m in re.finditer(r'[^\n]*(?:\n|$)', raw) if m.start() < len(raw)]
        else:
            parts = [(0, len(raw), raw)] if code_like else [(m.start(), m.end(), m.group()) for m in re.finditer(r'[^\n]+(?:\n(?![ \t]*\n)[^\n]+)*', raw)]
        for start, end, text in parts:
            part_code = (code_like or inside_fence or CODE.search(text)) if block.get('kind') == 'page' else code_like
            if not text.strip() and not inside_fence:
                continue
            is_heading = (not inside_fence and not part_code and (block.get('heading_level') is not None or (len(text) < 100 and '\n' not in text and HEADING.match(text) and not (doc['ext'] in {'.docx','.doc'} and re.match(r'^(?:19|20)\d{2}\s+年', text)))))
            if is_heading:
                section = text.strip()
            if text.lstrip().startswith(('```', '~~~')):
                marker = text.lstrip()[:3]
                if inside_fence == marker:
                    inside_fence = None
                elif not inside_fence and text.count(marker) == 1:
                    inside_fence = marker
            kind = 'heading' if is_heading else 'code' if part_code else 'steps' if STEP.match(text) else 'text'
            units.append({'kind': kind, 'text': text if kind == 'code' else tidy(text),
                          'section': section, 'sources': [source_for(doc, block, start, end)]})
    if doc['ext'] == '.doc':
        warnings.append('DOC 来源位置对应转换后的 DOCX 段落和表格；若转换已丢失表格结构，切分只能保留实际提取文字，不能恢复原始行列。')
    if doc['ext'] == '.pdf':
        warnings.append('PDF 标题与段落仅按已有文字和明确编号识别；不推断双栏阅读顺序，不自动跨页衔接。')
    # Join explicit fenced blocks and adjacent code/step paragraphs without
    # normalization. Unknown structures remain complete rather than guessed.
    grouped = []
    fenced = None
    for unit in units:
        text = unit['text']
        if fenced:
            fenced['text'] += '\n' + text
            fenced['sources'].extend(unit['sources'])
            if text.strip().startswith(fenced.pop('_fence', '```')):
                grouped.append(fenced); fenced = None
            else:
                fenced['_fence'] = '~~~' if fenced['text'].lstrip().startswith('~~~') else '```'
            continue
        if unit['kind'] == 'blank':
            if grouped and grouped[-1]['kind']=='code':
                grouped[-1]['text'] += '\n'+text
                grouped[-1]['sources'].extend(unit['sources'])
            continue
        if grouped and grouped[-1]['kind']=='steps' and unit['kind']=='text' and unit['section']==grouped[-1]['section'] and unit['sources'][0].get('page')==grouped[-1]['sources'][-1].get('page'):
            unit['kind']='steps'
        if grouped and grouped[-1]['kind']=='code' and unit['kind']=='text' and (text.startswith((' ', '\t')) or text.strip() in {'}', ']', ');'}):
            unit['kind']='code'
        if unit['kind'] == 'code' and text.lstrip().startswith(('```', '~~~')) and text.count(text.lstrip()[:3]) == 1:
            fenced = dict(unit, _fence=text.lstrip()[:3]); continue
        if grouped and unit['kind'] == grouped[-1]['kind'] and unit['kind'] in {'code', 'steps'} and unit['section'] == grouped[-1]['section'] and unit['sources'][0].get('page') == grouped[-1]['sources'][-1].get('page'):
            grouped[-1]['text'] += '\n' + text
            grouped[-1]['sources'].extend(unit['sources'])
        else:
            grouped.append(unit)
    if fenced:
        fenced.pop('_fence', None);grouped.append(fenced)
        warnings.append('代码围栏未闭合，保守保留剩余内容；未执行或补写代码。')
    return grouped, list(dict.fromkeys(warnings))


def split_text(text, target):
    """Ordered spans; prefer paragraph/sentence boundaries, force only very long runs."""
    if len(text) <= target:
        return [(0, len(text))]
    bounds = [m.end() for m in re.finditer(r'[。！？!?；;](?:[”’"\']?)(?:[ \t]*|$)|(?<=[.!?])\s+|\n', text)]
    spans, start = [], 0
    while start < len(text):
        if len(text) - start <= target:
            end = len(text)
        else:
            index = bisect_right(bounds, start + target)
            before = bounds[index - 1] if index and bounds[index - 1] > start else None
            after = bounds[index] if index < len(bounds) and bounds[index] <= start + target * 2 else None
            if before:
                end = before
            elif after:
                end = after
            else:
                end = start + target
        spans.append((start, end));start = end
    return spans


def _prepare_legacy(doc, config):
    if doc.get('ext') == '.xlsx' and doc.get('result',{}).get('excel_parser_version'):
        return prepare_excel(doc,config)
    units, warnings = units_from(doc)
    target, overlap = config['target_chars'], config['overlap_chars']
    normalized = {'units': units, 'warnings': warnings}
    chunks, pending = [], None
    risk = {'incomplete': doc.get('admission', {}).get('incomplete', False),
            'quality': doc.get('quality'), 'issues': (doc.get('result') or {}).get('issues', []),
            'preview_warnings': (doc.get('result') or {}).get('preview_warnings', [])}

    def emit(unit, text=None, **extra):
        chunks.append({'kind': unit['kind'], 'text': unit['text'] if text is None else text,
                       'section': unit['section'], 'sources': unit['sources'], 'overlap_chars': unit.get('overlap_chars', 0),
                       **({'table_title':unit['table_title']} if unit.get('table_title') else {}), **extra})

    def flush():
        nonlocal pending
        if pending:
            emit(pending);pending = None

    for unit in units:
        kind = unit['kind']
        if kind in {'code', 'pdf_page', 'table', 'steps'}:
            flush()
            if kind == 'table' and unit.get('tables'):
                rows = unit['tables'][0].get('rows', [])
                if unit['tables'][0].get('cells') or len(unit['text']) <= target or len(rows) < 3:
                    emit(unit, tables=unit['tables'])
                    continue
                # First row is repeated context, never an inferred semantic header.
                header, batch, first = rows[0], [], 2
                warnings.append('长表格分组时重复提取结果首行作为上下文，不断言它一定是真实表头；合并单元格风险保留。')
                def render(values):
                    return '\n'.join('\t'.join('〔空单元格〕' if cell is None else str(cell) for cell in row) for row in values)
                for number, row in enumerate(rows[1:], 2):
                    if batch and len(render([header]+batch+[row])) > target:
                        emit(unit, render([header]+batch), tables=[{'rows': [header]+batch}], row_start=first, row_end=number-1, repeated_first_row=True)
                        batch=[];first=number
                    batch.append(row)
                if batch:
                    emit(unit, render([header]+batch), tables=[{'rows': [header]+batch}], row_start=first, row_end=len(rows), repeated_first_row=True)
            elif kind == 'steps' and len(unit['text']) > target:
                # Only split between explicit numbered steps. Never inside a step.
                steps = re.split(r'\n(?=\s*(?:\d+[.)、]|第[一二三四五六七八九十\d]+步|步骤\s*\d+))', unit['text'])
                group = ''
                for step in steps:
                    if group and len(group)+len(step)+1 > target:
                        emit(unit, group);group=''
                    group += ('\n' if group else '')+step
                if group:emit(unit, group)
            else:
                emit(unit, **({'tables': unit['tables']} if unit.get('tables') else {}))
            continue
        if kind == 'heading':
            flush()
        spans = split_text(unit['text'], target)
        for a, b in spans:
            part = dict(unit, text=unit['text'][a:b])
            if len(spans) > 1:
                # Raw paragraph/page block is reliable; cleaned text offsets are
                # not presented as exact raw offsets after normalization.
                part['sources'] = [dict(src) for src in unit['sources']]
                part['unit_range'] = [a, b]
            compatible = pending and pending['section'] == part['section'] and pending['sources'][-1].get('page') == part['sources'][0].get('page')
            if compatible and len(pending['text'])+len(part['text'])+2 <= target:
                pending['text'] += '\n\n'+part['text'];pending['sources'].extend(part['sources'])
            else:
                previous = pending
                flush()
                prefix = ''
                if compatible and previous and overlap:
                    sentences = re.findall(r'[^。！？!?\n]*[。！？!?]|[^\n]+$', previous['text'])
                    if sentences and len(sentences[-1]) <= overlap:
                        prefix=sentences[-1]+'\n\n'
                pending = dict(part, text=prefix+part['text'], kind='text',
                               sources=(previous['sources'][-1:] if prefix else [])+part['sources'], overlap_chars=len(prefix.rstrip('\n')))
    flush()
    generation = digest({'document': doc['id'], 'revision': doc['revision'], 'input': _content_fingerprint(doc), 'config': config})
    for order, chunk in enumerate(chunks, 1):
        chunk.update(id=str(uuid.uuid5(uuid.NAMESPACE_URL, f'p18:{generation}:{order}')),
                     document_id=doc['id'], revision=doc['revision'], order=order,
                     risk=risk, method=METHOD, config=config)
        # Preserve order while removing duplicate location references only.
        chunk['sources'] = list({json.dumps(src, sort_keys=True): src for src in chunk['sources']}.values())
    normalized['warnings'] = list(dict.fromkeys(warnings))
    risk['preparation_warnings'] = normalized['warnings']
    if not chunks:
        raise ValueError('提取结果没有可切分内容，请核对原文或重新解析。')
    return normalized, chunks


def prepare_excel(doc, config):
    """Pack whole field-labelled records; source positions stay outside searchable text."""
    blocks = (doc.get('result') or {}).get('blocks', [])
    normalized = {'units': blocks, 'warnings': []}
    chunks, batch, key = [], [], None
    def flush():
        if not batch: return
        title = f"文档：{doc['name']}；工作表：{batch[0]['sheet']}"
        text = title + '\n' + '\n'.join(b['text'] for b in batch)
        risk = {'incomplete': any(c.get('warning') for b in batch for c in b.get('cells',[])),
                'quality': 'review' if any(b.get('review_required') for b in batch) else 'clear',
                'review_required': any(b.get('review_required') for b in batch),
                'issues': [x for x in doc['result'].get('issues',[]) if x.get('block') in {b['id'] for b in batch}],
                'preparation_warnings': [], 'preview_warnings': []}
        chunks.append(dict(kind='table' if batch[0]['kind'] in {'excel_record','excel_summary'} else 'text',
            text=text, section=batch[0]['sheet'], sources=[dict(source_for(doc,b),cells=[c['coordinate'] for c in b.get('cells',[])]) for b in batch],
            table_id=batch[0].get('table_id'), risk=risk, overlap_chars=0,
            records=[{'block_id':b['id'],'text':b['text'],'row':b['row_start']} for b in batch]))
        batch.clear()
    for b in blocks:
        current = (b['sheet'], b.get('table_id'), b['kind'])
        if batch and (key != current or sum(len(x['text'])+1 for x in batch)+len(b['text'])+len(doc['name'])+len(b['sheet'])+12 > config['target_chars']): flush()
        key = current
        batch.append(b)
    flush()
    generation = digest({'document':doc['id'],'revision':doc['revision'],'input':fingerprint(doc),'config':config})
    for order,c in enumerate(chunks,1):
        c.update(id=str(uuid.uuid5(uuid.NAMESPACE_URL,f'p18:{generation}:{order}')),document_id=doc['id'],revision=doc['revision'],order=order,
                 method=config['method'],config=config)
    if not chunks: raise ValueError('没有可切分的Excel记录。')
    return normalized,chunks



def _prepare_word_e1(doc, config):
    """E1: attach orphan Word headings to their own content; no table-note expansion.

    Mechanism reference: Docling Core HierarchicalChunker heading scope and
    content-only emission (48c57f17260c370f8ac7d2f8bcacb0e83c17fd80).
    Implemented against P18 sources; no third-party source code copied.
    """
    if doc['ext'] not in {'.docx', '.doc'}:
        return _prepare_legacy(doc, config)
    # Reserve space for an actual heading without changing the total budget.
    max_heading = max([len(b.get('text','')) + 2 for b in doc.get('result',{}).get('blocks',[]) if b.get('heading_level') is not None or (len(b.get('text','')) < 100 and HEADING.match(b.get('text','')))] + [0])
    legacy_config = dict(config, target_chars=max(40, config['target_chars'] - min(max_heading, config['target_chars']//3)))
    normalized, original = _prepare_legacy(doc, legacy_config)
    blocks = doc.get('result', {}).get('blocks', [])
    nonempty = [b for b in blocks if b.get('text', '').strip()]
    first = nonempty[0] if nonempty and nonempty[0]['kind'] == 'paragraph' else None
    # Only headings identified from structure/numbering, never a length filter.
    headings = {u['text'].strip() for u in normalized['units'] if u['kind'] == 'heading'}
    path_by_block, stack = {}, []
    for block in blocks:
        raw = block.get('text', '').strip()
        if raw in headings:
            level = block.get('heading_level') or 1
            stack = [(n, title) for n, title in stack if n < level]
            stack.append((level, raw))
        path_by_block[block['id']] = [title for _, title in stack]
    output, navigation = [], []
    for index, chunk in enumerate(original):
        title = chunk['text'].strip()
        sources = chunk['sources']
        is_document_title = bool(first and first.get('heading_level') is None and first['text'].strip() not in headings and title == first['text'].strip()
                                 and {x['block_id'] for x in sources} == {first['id']}
                                 and (first.get('style','').lower() == 'title' or
                                      re.sub(r'[\s_.-]', '', title) in re.sub(r'[\s_.-]', '', doc.get('name',''))))
        is_orphan = title in headings and '\n' not in title
        if is_document_title or is_orphan:
            navigation.append({'text': chunk['text'], 'sources': sources,
                               'heading_path': path_by_block.get(sources[0]['block_id'], [])})
            if is_document_title:
                continue
            following = original[index + 1] if index + 1 < len(original) else None
            if (following and following['section'] == chunk['section']
                    and following['text'].strip() not in headings
                    and following['kind'] != 'code'
                    and len(chunk['text']) + 2 + len(following['text']) <= config['target_chars']):
                # Each real source retains its own original raw offsets/pages.
                following['text'] = chunk['text'] + '\n\n' + following['text']
                following['sources'] = sources + following['sources']
            continue
        chunk['heading_path'] = path_by_block.get(sources[0]['block_id'], [])
        output.append(chunk)
    # Heading-only documents stay navigable but cannot silently lose all content.
    if not output:
        raise ValueError('Word仅包含导航标题，没有可作为事实证据的正文。')
    generation = digest({'document': doc['id'], 'revision': doc['revision'],
                         'input': _content_fingerprint(doc), 'config': config, 'word_structure': METHOD})
    for order, chunk in enumerate(output, 1):
        chunk.update(order=order, id=str(uuid.uuid5(uuid.NAMESPACE_URL, f'p18:{generation}:{order}')),
                     method=METHOD, config=config)
    normalized['navigation'] = navigation
    return normalized, output


def prepare(doc, config):
    """Attach proven local Word context, keeping original table data and sources.

    Mechanism reference: Docling Core BaseChunker.contextualize and heading
    scope, commit 48c57f17260c370f8ac7d2f8bcacb0e83c17fd80. No source copied.
    """
    normalized, chunks = _prepare_word_e1(doc, config)
    if doc.get('ext') not in {'.docx', '.doc'}:
        return normalized, chunks
    blocks = doc.get('result', {}).get('blocks', [])
    positions = {b['id']: i for i, b in enumerate(blocks)}
    for chunk in chunks:
        if chunk['kind'] != 'table' or chunk.get('repeated_first_row'):
            continue
        tables = [blocks[positions[s['block_id']]] for s in chunk['sources']
                  if s.get('block_id') in positions and blocks[positions[s['block_id']]]['kind'] == 'table']
        if len(tables) != 1:
            continue
        table = tables[0]
        index = positions[table['id']]
        context = []
        heading = (chunk.get('heading_path') or [None])[-1]
        if heading:
            title = next((b for b in reversed(blocks[:index])
                          if b['kind'] == 'paragraph' and b['text'].strip() == heading), None)
            if title:
                context.append(title)
        previous = next((b for b in reversed(blocks[:index]) if b.get('text', '').strip()), None)
        if (previous and previous['kind'] == 'paragraph'
                and previous.get('section') == table.get('section')
                and previous['text'].strip() != heading
                and re.search(r'单位|如下|下表|明细|(?:表|Table)\s*\d+|[：:]\s*$', previous['text'], re.I)):
            context.append(previous)
        present = {s['block_id'] for s in chunk['sources']}
        context = [b for b in context if b['id'] not in present]
        if not context:
            continue
        original = chunk['text']
        text = '【表格局部上下文】\n' + '\n'.join(b['text'] for b in context) + '\n【原始表格证据】\n' + original
        if len(text) > config['target_chars']:
            normalized['warnings'].append('表格原文与局部上下文超过字符预算，保留原表和原特殊切分策略，未截断单元格或金额。')
            continue
        chunk.update(text=text, evidence_text=original, original_table_text=table['text'],
                     retrieval_context=[dict(text=b['text'], sources=[source_for(doc, b)]) for b in context],
                     context_method=TABLE_CONTEXT_METHOD)
        chunk['sources'] += [source_for(doc, b) for b in context]
        chunk['id'] = str(uuid.uuid5(uuid.NAMESPACE_URL, digest({
            'base_chunk_id': chunk['id'], 'text': text, 'sources': chunk['sources'],
            'context_method': TABLE_CONTEXT_METHOD})))
    return normalized, chunks
