from app.qa_facts import checked_answer, contains_anchor, parts


def source(number, title, text):
    return dict(id=f'S{number}', document_name=title, text=text)


def test_independent_values_times_and_versions_are_bound_to_their_sources():
    question = 'E4291 的 V2.3 调用上限是多少，工单 EX-TKT-903 在 15:42 实际多少次？'
    plan = parts(question)
    wrong_version = source(1, '错误码手册', 'E4291\n设备监控平台 V2.1 按每个 token 每分钟最多 80 次调用。')
    rule = source(2, '错误码手册', 'E4291\n设备监控平台 V2.3 按每个 token 每分钟最多 160 次调用。')
    wrong_ticket = source(3, '工单复盘', '15:42 出现 HTTP 429 和 E4291，按同一 token 一分钟合计 710 次')
    ticket = source(4, '工单复盘', '15:40 出现 HTTP 429 和 E4291，按同一 token 一分钟合计 190 次\n'
                    '15:42 出现 HTTP 429 和 E4291，按同一 token 一分钟合计 180 次')
    result = checked_answer(plan, [wrong_version, rule, wrong_ticket, ticket], lambda evidence, _: evidence is ticket)
    assert result['status'] == 'answered'
    assert result['citations'] == ['S2', 'S4']
    assert '160 次调用。[S2]' in result['answer'] and '180 次。[S4]' in result['answer']
    assert '710' not in result['answer'] and '190' not in result['answer']
    assert not contains_anchor('EX-TKT-9030', 'EX-TKT-903')


def test_missing_or_conflicting_conditions_are_not_presented_as_verified():
    plan = parts('状态上报间隔是多久？持续离线多久提交工单？')
    report = source(1, '总体架构', '状态每 20 秒上报一次。')
    ambiguous = source(2, '设备离线排查手册', '离线 1 秒后刷新监控页。')
    assert checked_answer(plan, [report, ambiguous], lambda *_: False)['status'] == 'partial'
    offline = source(3, '设备离线排查手册', '持续离线达到 3 分钟仍未恢复时提交 IT 工单。')
    offline_other = source(4, '设备离线排查手册', '持续离线达到 5 分钟仍未恢复时提交 IT 工单。')
    result = checked_answer(plan, [report, offline, offline_other], lambda *_: False)
    assert result['status'] == 'partial'
    assert result['citations'] == ['S1']
    assert '资料记录有差异' in result['answer']
    assert '3 分钟' not in result['answer'] and '5 分钟' not in result['answer']
    assert not parts('网关 V1.3 状态多久上报，离线多久转单？')
