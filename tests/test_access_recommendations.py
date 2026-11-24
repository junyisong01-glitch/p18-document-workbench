import json
import pytest
from app.access_recommendations import validate, arrange, classify
from app.rag import RagError

TEXT='设备持续离线达到 10 分钟且仍未恢复时，提交 IT 工单并转交平台运维。'
ITEMS=[dict(id=str(i),name='文档'+str(i),section='条件',excerpt=TEXT) for i in range(5)]

def response(rows):return json.dumps({'items':rows},ensure_ascii=False)
def rows():return [dict(index=i,support='related',quote='') for i in range(5)]

def test_exact_quotes_and_stable_priority_limit():
    data=rows()
    for i in [1,3,4]:data[i].update(support='direct',quote=TEXT)
    quotes=validate(response(data),ITEMS)
    result=arrange(ITEMS,quotes)
    assert [i['id'] for i in result]==['1','3','4','0','2']
    assert [i['id'] for i in result if i['priority']]==['1','3']
    assert result[0]['support_quote']==TEXT
    assert '尚未确认' in result[-1]['reason']
    assert 'priority' not in ITEMS[0]

@pytest.mark.parametrize('quote',[TEXT.replace('10','20'),'离线10分钟就报障','不存在的原文，提交IT工单并转交平台运维。',None,123])
def test_fabricated_or_invalid_quotes_do_not_gain_priority(quote):
    data=rows();data[0].update(support='direct',quote=quote)
    assert validate(response(data),ITEMS)=={}

@pytest.mark.parametrize('data',[[],[{'index':0}]*5,[dict(index=True,support='direct',quote=TEXT)]*5,rows()[:-1],rows()+[{}], [dict(index=i,support='approved',quote=TEXT) for i in range(5)]])
def test_malformed_batch_rejected(data):
    with pytest.raises(ValueError):validate(response(data),ITEMS)

def test_transport_is_loopback_only_and_fallback_keeps_candidates(monkeypatch):
    def fail(path,body,timeout):
        assert path=='/api/chat' and timeout==30
        assert body['truncate'] is False and body['think'] is False
        assert len(body['messages'])==2
        raise RagError('ollama_unavailable','offline')
    monkeypatch.setattr('app.access_recommendations.local_json',fail)
    quotes,checked=classify('离线多久提交工单？','生产排障',ITEMS)
    assert not checked and quotes=={}
    result=arrange(ITEMS,quotes)
    assert [i['id'] for i in result]==[i['id'] for i in ITEMS]
    assert not any(i['priority'] for i in result)

@pytest.mark.parametrize('output',[{'done':False},{'done':True,'done_reason':'length'}, {'done':True,'done_reason':'stop','message':{'content':'invalid'}}])
def test_incomplete_model_output_falls_back(monkeypatch,output):
    monkeypatch.setattr('app.access_recommendations.local_json',lambda *a,**k:output)
    assert classify('问题','用途',ITEMS)==({},False)


def test_complete_local_model_response_validated(monkeypatch):
    data=rows();data[0].update(support='direct',quote=TEXT)
    def complete(path,body,timeout):
        assert body['format']['properties']['items']['minItems']==5
        assert body['format']['properties']['items']['maxItems']==5
        return {'done':True,'done_reason':'stop','message':{'content':response(data)}}
    monkeypatch.setattr('app.access_recommendations.local_json',complete)
    assert classify('问题','用途',ITEMS)==({'0':TEXT},True)


@pytest.mark.parametrize('question',[
    '设备离线多久应提交IT工单，恢复后由谁审核？',
    '住宿报销上限是多少，以及审批负责人？',
    '说明离线排查流程并列出升级条件',
])
def test_compound_questions_never_promote_partial_support(monkeypatch,question):
    def unexpected(*a,**k):raise AssertionError('compound requests must remain unconfirmed')
    monkeypatch.setattr('app.access_recommendations.local_json',unexpected)
    assert classify(question,'处理现场问题',ITEMS)==({},False)
