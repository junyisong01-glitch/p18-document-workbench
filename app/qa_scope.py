"""Product names, technical fields, and source priorities for Qichen QA."""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Product:
    name: str
    source_code: str


@dataclass(frozen=True)
class Topic:
    product: Product
    version: str = ''


PLATFORM = Product('设备监控平台', 'QC-RD-API-001')
GATEWAY = Product('设备数据采集网关', 'QC-RD-GW-041')
_FOLLOWUP = re.compile(r'^(?:那|那么|那就|再问|那关于)')
_HISTORY = re.compile(r'旧版|历史版|旧版本|废止版')
_GATEWAY_OLD = re.compile(r'(?<![A-Za-z0-9])[Vv]\s*1\.0(?!\d|\.\d)')
_VERSION = re.compile(r'(?<![A-Za-z0-9])[Vv]\s*\d+(?:\.\d+)+')
_QUOTA = re.compile(r'限流|配额|调用频率|QPS|请求频率', re.I)
_QUOTA_VALUE = re.compile(r'\d+(?:\.\d+)?\s*QPS|每(?:个\s*token\s*)?分钟.{0,8}\d+\s*次', re.I)
_BATCH = re.compile(r'(?:单批|每批|单次).{0,14}(?:上报|遥测|条)|(?:上报|遥测).{0,14}(?:单批|每批|单次|多少条)')
_BATCH_VALUE = re.compile(r'\d+\s*条')
_PAGING = re.compile(r'分页|page_size', re.I)
_PAGING_VALUE = re.compile(r'(?:分页|page_size).{0,45}默认.{0,6}\d+.{0,12}最大.{0,6}\d+', re.I)
_AUTH = re.compile(r'(?:token|令牌).{0,16}(?:有效期|过期)|(?:鉴权|认证).{0,8}多久', re.I)
_AUTH_VALUE = re.compile(r'(?:有效期|过期).{0,14}\d+\s*(?:分钟|小时)')
_REPORT = re.compile(r'(?:状态上报频率|多久(?:上报|报一次))')
_REPORT_VALUE = re.compile(r'状态上报.{0,20}\d+\s*秒')
_NAMED_SOURCES = (
    ('QC-RD-MIG-032', re.compile(r'迁移说明'), re.compile(r'\d+\s*条')),
    ('QC-RD-TST-031', re.compile(r'集成验收报告'), re.compile(r'(?:补传|缺失).{0,90}(?:待验证|未验证|日志|完整性)', re.S)),
    ('QC-RD-GW-041', re.compile(r'网关接口\s*[Vv]?\s*\d'), re.compile(r'错误码|HTTP|QPS', re.I)),
    ('QC-RD-SUP-022', re.compile(r'错误码(?:处理)?手册'), _QUOTA_VALUE),
)


def products(text):
    matches = []
    if re.search(r'设备监控平台|监控平台|E4291', text, re.I):
        matches.append(PLATFORM)
    if re.search(r'设备数据采集网关|数据采集网关|采集网关|网关\s*[Vv]\s*\d|单应用', text, re.I):
        matches.append(GATEWAY)
    return matches


def parameter(text):
    for name, pattern in (
        ('quota', _QUOTA), ('batch', _BATCH), ('paging', _PAGING),
        ('auth', _AUTH), ('report', _REPORT),
    ):
        if pattern.search(text):
            return name
    return None


def source_ranker(query, catalog):
    """Return a priority for direct normative evidence, leaving other hits ordered."""
    scopes = products(query)
    field = parameter(query)
    named = [(code, signals) for code, title, signals in _NAMED_SOURCES if title.search(query)]
    if len(named) >= 2:
        requested = dict(named)
        identifiers = re.findall(r'\b[A-Z]+-\d+(?:-\d+)*\b|(?<!\d)\d{4,6}(?!\d)', query)

        def compound_priority(hit):
            code, version = catalog.get(hit['document_id'], ('', ''))
            if code == GATEWAY.source_code and bool(_GATEWAY_OLD.search(query)) != bool(_GATEWAY_OLD.search(version)):
                return 0
            pattern = requested.get(code)
            if pattern is None or not pattern.search(hit['text']):
                return 0
            return 1 + any(term in hit['text'] for term in identifiers)

        return compound_priority
    if len(scopes) != 1 or not field or re.search(r'分别|对比|相比|和旧|前后', query):
        return None
    source = scopes[0]
    matches_value = {
        'quota': _QUOTA_VALUE, 'batch': _BATCH_VALUE, 'paging': _PAGING_VALUE,
        'auth': _AUTH_VALUE, 'report': _REPORT_VALUE,
    }[field]

    def priority(hit):
        code, version = catalog.get(hit['document_id'], ('', ''))
        if code != source.source_code:
            return 0
        if source == GATEWAY and bool(_GATEWAY_OLD.search(query)) != bool(_GATEWAY_OLD.search(version)):
            # A version mismatch must never gain priority over matching evidence.
            return 0
        return 2 if matches_value.search(hit['text']) else 0

    return priority


def resolve(question, previous, visible_products):
    """Keep single-turn questions intact and resolve short follow-ups locally."""
    scopes = products(question)
    inherited = previous if not scopes and _FOLLOWUP.search(question) else None
    version = _VERSION.search(question)
    topic = Topic(scopes[0], version.group() if version else '') if len(scopes) == 1 else inherited
    if inherited and version:
        topic = Topic(inherited.product, version.group())
    if topic is None and not scopes and parameter(question) == 'quota' and len(visible_products) > 1:
        return None, None, '你想查哪个产品的接口限流？请输入「设备监控平台限流」或「设备数据采集网关限流」。'
    if topic and topic.product == GATEWAY and (_HISTORY.search(question) or _GATEWAY_OLD.search(topic.version)):
        return None, Topic(GATEWAY, 'V1.0'), '你问的是历史版本。请在「文档管理 → 历史归档 → 查正文」中按当前权限查阅。'
    if inherited:
        if _HISTORY.search(question):
            return None, topic, '你问的是历史版本。请在「文档管理 → 历史归档 → 查正文」中按当前权限查阅。'
        return f'{topic.product.name} {topic.version}。{question}', topic, ''
    return question, topic, ''
