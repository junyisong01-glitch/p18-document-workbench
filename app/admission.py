"""Admission policy and durable build intent; actual index status is resolved by the API."""
CATEGORY_LABELS = {
    'preview': '仅预览异常', 'missing': '局部内容未提取',
    'structure': '结构或对应关系存疑', 'text': '文字内容疑似损坏',
    'unusable': '整份文件不可用',
}
REQUIREMENTS = {
    'preview': ('preview_checked', '我已对照下载的原文件，确认提取内容可用'),
    'missing': ('accept_incomplete', '我接受仅使用已提取内容，并保留内容不完整提示'),
    'structure': ('structure_correct', '我已核对相关段落和表格，确认结构及对应关系正确'),
    'text': ('text_correct', '我已核对疑似乱码位置，确认提取文字正确、可用'),
}
MISSING = {'no_text', 'image', 'formula', 'objects', 'notes'}


def categories(doc):
    result = doc.get('result') or {}
    found = set()
    if result.get('preview_warnings'):
        found.add('preview')
    for item in result.get('issues', []):
        kind = item.get('kind')
        found.add('missing' if kind in MISSING else 'text' if kind == 'characters' else 'structure')
    if doc.get('state') == 'failed' or result.get('error'):
        found.add('unusable')
    elif doc.get('state') in {'ready', 'review', 'held'} and not doc.get('characters', 0):
        found.add('unusable')
    return [key for key in CATEGORY_LABELS if key in found]


def requirements(doc):
    return [{'key': REQUIREMENTS[c][0], 'label': REQUIREMENTS[c][1]}
            for c in categories(doc) if c in REQUIREMENTS]


def confirmed(doc):
    review = doc.get('review_decision') or {}
    return (review.get('revision') == doc['revision'] and review.get('outcome') == 'accepted'
            and all(review.get('checks', {}).get(r['key']) is True for r in requirements(doc)))


def only_preview_warning(doc):
    result = doc.get('result') or {}
    return (doc['state'] == 'review' and doc.get('characters', 0) > 0
            and bool(result.get('preview_warnings')) and not result.get('issues') and not result.get('error'))


def sync_admission(doc):
    kinds = categories(doc)
    needs_review = bool(kinds) or doc.get('quality') == 'review'
    excel_warning_mode = (doc.get('ext') == '.xlsx' and (doc.get('result') or {}).get('excel_review_policy') == 'record-warning-v1')
    eligible = (doc['state'] == 'ready' and doc.get('characters', 0) > 0
                and 'unusable' not in kinds and (not needs_review or confirmed(doc)))
    if doc.get('publication_rules') == 1 and only_preview_warning(doc):
        eligible = True
    if excel_warning_mode and doc['state'] in {'ready','review'} and doc.get('characters',0)>0 and 'unusable' not in kinds:
        eligible = True  # Explicit user policy: retain review flags; never override held/failed.
    doc['admission'] = {
        'eligible': eligible,
        'categories': [{'code': c, 'label': CATEGORY_LABELS[c]} for c in kinds],
        'requirements': requirements(doc),
        'incomplete': 'missing' in kinds,
        'review_required': needs_review,
    }
    # One deterministic intent per extraction revision; saves/restarts cannot
    # enqueue duplicates. A future dispatcher must recheck admission before use.
    doc['build'] = {
        'status': 'waiting' if eligible else 'blocked' if doc['state'] in {'review', 'held', 'failed'} else 'not_started',
        'request_id': f"{doc['id']}:{doc['revision']}" if eligible else None,
        'revision': doc['revision'],
        'reason': 'awaiting_index' if eligible else 'admission_not_met',
        'message': '符合入库条件；是否可检索以当前向量索引状态为准。' if eligible else '尚不符合入库条件，不触发知识库构建。',
        'searchable': False,
    }
