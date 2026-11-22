"""Release checks for one extraction revision, with redacted reasons."""
import re
import unicodedata

from app.admission import only_preview_warning

_ID = re.compile(r'(?<![0-9A-Za-z])\d{17}[\dXx](?![0-9A-Za-z])')
_WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
_CUSTOMER = re.compile(r'(?:客户名称|客户全称|客户姓名|客户名)\s*[:：]\s*([^；;，,。\n|]{2,80})')
_FIELD_LABEL = re.compile(r'(?:客户名称|客户全称|客户姓名|客户名|报价|报价金额|含税报价|客户报价|投标报价|合同金额)')
_QUOTE = re.compile(r'(?:含税报价|客户报价|报价金额|报价|投标报价|合同金额)\s*[:：]?\s*(?:人民币|[¥￥$])?\s*\d[\d,.]*\s*(?:万?元|美元|人民币)|(?:报价金额|合同金额)\s*[:：]\s*(?:[¥￥$]\s*)?\d[\d,.]*')
_EMPTY_CUSTOMER = re.compile(
    r'^(?:请?填写|输入|请勿|用于|指的是)|'
    r'^(?:客户(?:名称|全称|姓名)?|示例|无|暂无|未填写|待填|保密|不适用|字段|说明|格式|必填)(?:$|[（( :：])'
)


def technical_ready(doc):
    return doc['state'] == 'ready' or doc.get('publication_rules') == 1 and only_preview_warning(doc)


def text_to_check(block):
    yield block.get('text', '')
    for table in block.get('tables', []):
        rows = table.get('rows', [])
        if not rows:
            continue
        def field(value):
            return unicodedata.normalize('NFKC', str(value or '')).strip()
        headers = {column: field(cell) for column, cell in enumerate(rows[0])
                   if _FIELD_LABEL.fullmatch(field(cell))}
        for row in rows[1:]:
            for column, header in headers.items():
                if column < len(row) and row[column] is not None:
                    yield f'{header}：{row[column]}'
        for row in rows:
            if len(row)==2 and _FIELD_LABEL.fullmatch(field(row[0])) and row[1] is not None:
                yield f'{field(row[0])}：{row[1]}'


def review_reasons(doc, workflow):
    reasons = {}
    if workflow.get('restricted'):
        reasons['confidential'] = '标为机密'
    if (doc.get('admission') or {}).get('incomplete'):
        reasons['incomplete'] = '部分内容未提取，需对照原件检查敏感信息'
    for block in (doc.get('result') or {}).get('blocks', []):
        # Excel record text already associates column labels and values.
        text = unicodedata.normalize('NFKC', '\n'.join(text_to_check(block)))
        label = f"第 {block['page']} 页" if block.get('page') else '正文'
        if block.get('row_start'):
            label = f"工作表第 {block['row_start']} 行"
        elif block.get('kind') == 'table':
            label = '表格'
        for match in _ID.finditer(text):
            value = match[0].upper()
            if value[-1] == '10X98765432'[sum(int(a) * b for a, b in zip(value[:17], _WEIGHTS)) % 11]:
                reasons.setdefault('identity_number', f'{label}疑似含身份证号码')
                break
        for match in _CUSTOMER.finditer(text):
            name = match[1].strip()
            if name and not _EMPTY_CUSTOMER.match(name) and not re.fullmatch(r'[xX*×…_□ -]+', name):
                reasons.setdefault('customer', f'{label}含客户名称或姓名')
                break
        if _QUOTE.search(text):
            reasons.setdefault('quote', f'{label}含具体报价或合同金额')
    return list(reasons.values())
