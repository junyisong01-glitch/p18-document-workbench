"""Resolve supported compound support questions using exact, citable facts."""
from dataclasses import dataclass
import re
import unicodedata


@dataclass(frozen=True)
class Part:
    label: str
    query: str
    document: str
    value: re.Pattern
    version: str = ''
    anchor: str = ''
    time: str = ''
    required_term: str = ''

    def extract(self, source, document_has_anchor):
        if not re.search(self.document, source['document_name']):
            return None
        if self.required_term and not contains_anchor(source['text'], self.required_term):
            return None
        if self.anchor and not document_has_anchor(source, self.anchor):
            return None
        claims = {}
        for raw in source['text'].splitlines():
            line = ' '.join(unicodedata.normalize('NFKC', raw).split()).strip()
            if self.time and not line.startswith(self.time + ' '):
                continue
            for match in self.value.finditer(line):
                if self.version and not re.search(rf'(?<![A-Za-z0-9_.]){re.escape(self.version)}(?![\d.])', match[0], re.I):
                    continue
                key = tuple((value or '').replace(' ', '').lower() for value in match.groups())
                claims.setdefault(key, match[0].strip())
        return claims


_RATE = re.compile(r'(?:启辰)?设备监控平台\s*(V\d+(?:\.\d+)+)\s*按每个\s*(token)\s*每(分钟|秒|小时)\s*(?:最多|不超过)\s*(\d+)\s*次(?:调用)?(?:限制请求)?', re.I)
_INCIDENT = re.compile(r'^((?:[01]?\d|2[0-3]):[0-5]\d)\s+[^。\n]*?出现\s+HTTP\s*429\s*和\s*E4291\b[^。\n]*?(同一\s*token)[^。\n]*?(一?分钟|一?秒|一?小时)\s*(?:共|合计|共计)\s*(\d+)\s*次', re.I | re.ASCII)
_REPORT = re.compile(r'状态\s*(?:按[^；。]{0,14})?每\s*(\d+)\s*(秒|分钟|小时)\s*上报(?:一次)?')
_OFFLINE = re.compile(r'(持续离线(?:达到|超过))\s*(\d+)\s*(秒|分钟|小时)\s*(仍未恢复)时\s*(?:提交|发起)\s*(?:IT\s*)?工单(?:[,，]转平台运维)?')
_TICKET = re.compile(r'(?<![\w-])(?:[A-Z][A-Z0-9]*-)*TKT-\d+(?:-\d+)*(?![\w-])', re.I | re.ASCII)
_TICKET_DASHES = str.maketrans({dash: '-' for dash in '‐‑‒–—−'})


def ticket_lookup(question):
    """Apply the exact gate to a direct lookup of one ticket's recorded fields."""
    text = unicodedata.normalize('NFKC', question).translate(_TICKET_DASHES)
    tickets = {match[0].upper() for match in _TICKET.finditer(text)}
    if (len(tickets) == 1 and re.search(r'转交|转单|转派|接手|恢复|发现|报障时间|处理记录|工单状态', text)
            and not re.search(r'对比|比较|相比|对照|指南|手册|规则|制度|按流程|一般|通常|应该|应当', text)):
        return next(iter(tickets))
    return None


def parts(question):
    """Recognize independently answerable fields, preserving requested version and event."""
    text = unicodedata.normalize('NFKC', question)
    ticket = re.search(r'(?<![\w-])([A-Z][A-Z0-9-]*TKT-\d+)(?![\w-])', text, re.I | re.ASCII)
    if (ticket and not re.search(r'网关|恢复后|降频后|合并轮询后|对比|相比', text)
            and re.search(r'E4291|错误码手册', text, re.I)
            and re.search(r'限流|配额|上限|最多', text)
            and re.search(r'合计|总量|总调用|实际|实测|共多少|多少次', text)):
        version = re.search(r'(?<![A-Za-z0-9])[Vv]\d+(?:\.\d+)+', text)
        time = re.search(r'(?:[01]?\d|2[0-3]):[0-5]\d', text)
        return (
            Part('手册规定的调用上限', '设备监控平台 E4291 错误码处理手册 每个 token 每分钟最多调用次数 ' + (version[0] if version else ''),
                 '错误码.*手册', _RATE, version=version[0] if version else '', required_term='E4291'),
            Part('工单记录的实际调用量', f'{ticket[0]} 工单复盘 时间线 HTTP 429 E4291 同一 token 多实例 合计',
                 '工单.*复盘|工单记录', _INCIDENT, anchor=ticket[0].upper(), time=time[0] if time else ''),
        )
    if (re.search(r'上报频率|上报间隔|多久.{0,4}上报|上报.{0,6}(?:多久|一次)|每隔多久.{0,4}报', text)
            and re.search(r'离线.{0,20}(?:转单|工单|转派|升级)|(?:转单|工单).{0,10}离线', text)
            and not re.search(r'网关|旧版|[Vv]\d+\.\d+|对比|相比', text)):
        return (
            Part('状态上报间隔', '总体架构 数据路径 设备状态每隔多久上报一次', '总体架构', _REPORT),
            Part('离线转单条件', '设备离线排查操作手册 持续离线仍未恢复 多久提交 IT 工单', '离线.*手册', _OFFLINE),
        )
    return ()


def matches(part, group, document_has_anchor):
    for source in group.get('members', [group]):
        for key, quote in (part.extract(source, document_has_anchor) or {}).items():
            yield key, quote


def contains_anchor(text, anchor):
    text = unicodedata.normalize('NFKC', text).translate(_TICKET_DASHES)
    return re.search(rf'(?<![\w-]){re.escape(anchor)}(?![\w-])', text, re.I | re.ASCII) is not None


def checked_answer(plan, evidence, document_has_anchor):
    """Keep each claim with its own passage and withhold conflicting values."""
    lines, citations = [], []
    for part in plan:
        facts = {}
        for group in evidence:
            for key, quote in matches(part, group, document_has_anchor):
                facts.setdefault(key, (quote, group['id']))
        if len(facts) == 1:
            quote, citation = next(iter(facts.values()))
            lines.append(f'{part.label}：{quote}。[{citation}]')
            if citation not in citations:
                citations.append(citation)
        elif len(facts) > 1:
            lines.append(f'{part.label}：资料记录有差异，暂无法确认。')
        else:
            lines.append(f'{part.label}：当前资料中缺少可核对的依据。')
    if not citations:
        return dict(status='insufficient_evidence', answer='知识库中未找到相关内容', citations=[])
    status = 'answered' if all(re.search(r'\[S\d+\]$', line) for line in lines) else 'partial'
    return dict(status=status, answer='\n\n'.join(lines), citations=citations)
