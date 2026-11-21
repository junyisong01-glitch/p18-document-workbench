from app.qa_scope import GATEWAY, PLATFORM, Topic, resolve, source_ranker


def test_quota_clarification_only_names_visible_products():
    assert '限流' in resolve('接口限流是多少', None, {PLATFORM, GATEWAY})[2]
    assert resolve('接口限流是多少', None, {PLATFORM})[0] == '接口限流是多少'


def test_followup_retains_topic_and_history_is_routed_out_of_current_qa():
    assert resolve('那限流呢？', Topic(GATEWAY, 'V1.3'), set())[0].startswith(GATEWAY.name)
    history = resolve('那旧版呢？', Topic(GATEWAY, 'V1.3'), set())
    assert history[0] is None
    assert resolve('那限流呢？', history[1], set())[0] is None
    assert '历史归档' in resolve('数据采集网关V1.0的限流是多少？', None, set())[2]
    assert resolve('设备离线怎么处理？', Topic(GATEWAY), set())[1] is None


def test_priority_requires_normative_evidence_and_correct_version():
    catalog = {'new': ('QC-RD-GW-041', 'V1.3'), 'old': ('QC-RD-GW-041', 'V1.0')}
    rank = source_ranker('网关 V1.3 单应用配额是多少？', catalog)
    assert rank({'document_id': 'new', 'text': '单应用 20 QPS'}) > 0
    assert rank({'document_id': 'old', 'text': '单应用 50 QPS'}) == 0
    assert rank({'document_id': 'new', 'text': '参考限流规则'}) == 0
    assert rank({'document_id': 'ticket', 'text': '单应用 20 QPS'}) == 0
    assert source_ranker('设备监控平台和设备数据采集网关限流分别是多少？', catalog) is None
