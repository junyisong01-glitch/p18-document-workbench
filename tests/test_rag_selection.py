"""Fictional in-memory retrieval, temporary grants, capture-only provider. No network/keys."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import json
import threading

import pytest
from app.rag_context import model_evidence
from app.rag import RagError, DeepSeekClient, UNKNOWN
from app import main
from test_rag import rig
from test_workbench import client, HEADERS
from test_rag_boundaries import install_ranked_fictional_documents


@pytest.fixture(autouse=True)
def forbid_real_client(monkeypatch):
    def forbidden(*args):
        pytest.fail('Real DeepSeek client must not be consulted in selection tests')
    monkeypatch.setattr(DeepSeekClient, 'complete', forbidden)
    monkeypatch.setattr(DeepSeekClient, 'configured', property(forbidden))


def candidate(draft, document_id):
    return next(c for c in draft['candidates'] if c['evidence']['document_id']==document_id)


def select(rig, draft, ids=None, version=0):
    return rig.rag.selection(draft['draft_id'],version,ids if ids is not None else draft['default_candidate_ids'])


def test_local_candidates_do_not_grant_permission_or_send(rig):
    draft=rig.rag.draft('虚构负责人是谁？')
    assert len(draft['candidates'])==3
    assert all(not c['selectable'] and c['default_reason']=='local_only' for c in draft['candidates'])
    assert not draft['default_candidate_ids'] and not rig.rag.tickets and not rig.provider.requests
    with pytest.raises(RagError) as error:select(rig,draft,[draft['candidates'][0]['candidate_id']])
    assert error.value.code=='selection_forbidden'
    assert not rig.provider.requests and not rig.rag.tickets


def test_selected_preview_equals_captured_request_and_only_confirm_sends(rig):
    rig.grant(['a','b']);draft=rig.rag.draft('虚构负责人是谁？')
    p=select(rig,draft,[candidate(draft,'b')['candidate_id']])
    assert not rig.provider.requests
    with pytest.raises(RagError) as error:rig.rag.answer(p['ticket'],False)
    assert error.value.code=='consent_required' and not rig.provider.requests
    # Returned data is not the stored snapshot, including nested text/messages.
    expected=deepcopy(p);p['messages'][1]['content']='client edited';p['evidence'][0]['text']='client edited'
    rig.provider.reply={'status':'answered','answer':'林晓岚。[S1]','citations':['S1']}
    result=rig.rag.answer(p['ticket'],True)
    assert rig.provider.requests==[expected['messages']]
    body=json.loads(rig.provider.requests[0][1]['content'])
    assert body['untrusted_evidence']==model_evidence(expected['evidence'])
    assert [s['document_id'] for s in body['untrusted_evidence']]==['b']
    assert result['citations']==expected['evidence']
    assert expected['budget']['message_chars']==len(json.dumps(expected['messages'],ensure_ascii=False))
    assert 'secret.docx' not in json.dumps(body) and 'UNAUTHORIZED_PRIVATE' not in json.dumps(body)
    with pytest.raises(RagError) as error:rig.rag.answer(p['ticket'],True)
    assert error.value.code=='ticket_expired' and len(rig.provider.requests)==1


@pytest.mark.parametrize('edit,code',[
    ('empty','selection_empty'),('local','selection_forbidden'),('unknown','selection_unknown'),
    ('duplicate','bad_selection'),('valid',None)
])
def test_acknowledged_edits_invalidate_previous_ticket_even_on_error(rig,edit,code):
    rig.grant(['a','b']);d=rig.rag.draft('虚构负责人？');old=select(rig,d)
    bid=candidate(d,'b')['candidate_id'];local=candidate(d,'secret')['candidate_id']
    ids={'empty':[],'local':[local],'unknown':['unknown'],'duplicate':[bid,bid],'valid':[bid]}[edit]
    if code:
        with pytest.raises(RagError) as error:select(rig,d,ids,version=1)
        assert error.value.code==code and error.value.details['selection_version']==2
    else:
        new=select(rig,d,ids,version=1)
        assert new['ticket']!=old['ticket'] and len(new['evidence'])==1
    with pytest.raises(RagError) as error:rig.rag.answer(old['ticket'],True)
    assert error.value.code=='ticket_expired' and not rig.provider.requests


def test_unknown_and_cross_draft_ids_are_not_accepted(rig):
    rig.grant(['b']);first=rig.rag.draft('虚构问题一？');other=rig.rag.draft('虚构问题二？')
    with pytest.raises(RagError) as error:select(rig,first,other['default_candidate_ids'])
    assert error.value.code=='selection_unknown' and not rig.provider.requests


def test_old_selection_version_cannot_invalidate_new_preview(rig):
    rig.grant(['b']);d=rig.rag.draft('虚构问题？');p=select(rig,d)
    with pytest.raises(RagError) as error:select(rig,d,[],version=0)
    assert error.value.code=='selection_changed' and error.value.details['selection_version']==1
    assert p['ticket'] in rig.rag.tickets


def test_new_draft_supersedes_old_pending_selection_in_same_session(rig):
    rig.grant(['b']);d=rig.rag.draft('虚构问题？');p=select(rig,d)
    rig.rag.draft('另一个明确问题？',d['session_id'])
    with pytest.raises(RagError) as error:select(rig,d,version=1)
    assert error.value.code=='session_changed'
    with pytest.raises(RagError):rig.rag.answer(p['ticket'],True)
    assert not rig.provider.requests


def test_group_limit_keeps_all_candidates_and_can_choose_ninth(rig,monkeypatch):
    monkeypatch.setenv('P18_RAG_EVIDENCE_COUNT','10') # New manual protocol still caps at eight.
    install_ranked_fictional_documents(rig,[f'完全虚构第{i}段。' for i in range(9)])
    d=rig.rag.draft('虚构目标？');ids=[c['candidate_id'] for c in d['candidates']]
    assert len(ids)==9 and len(d['default_candidate_ids'])==8
    assert d['candidates'][8]['default_reason']=='group_limit'
    with pytest.raises(RagError) as error:select(rig,d,ids)
    assert error.value.code=='evidence_budget_exceeded'
    assert error.value.details['reasons']==['group_limit']
    assert error.value.details['budget']['groups']==9 and error.value.details['budget']['group_limit']==8
    assert not rig.rag.tickets and not rig.provider.requests
    p=select(rig,d,ids[1:],version=1)
    assert len(p['evidence'])==8 and p['evidence'][-1]['chunk_id']=='chunk-g08'
    assert [s['id'] for s in p['evidence']]==[f'S{i}' for i in range(1,9)]


def test_context_limit_returns_usage_and_does_not_trim_selected_structure(rig,monkeypatch):
    monkeypatch.setenv('P18_RAG_CONTEXT_CHARS','2000')
    long='完全虚构表格参数对应关系。'*500
    install_ranked_fictional_documents(rig,['虚构短段落。',long,'虚构尾段。'])
    d=rig.rag.draft('虚构目标？');ids=[c['candidate_id'] for c in d['candidates']]
    assert d['candidates'][1]['evidence']['text']==long
    assert d['candidates'][1]['default_reason']=='context_limit'
    with pytest.raises(RagError) as error:select(rig,d,ids)
    detail=error.value.details
    assert error.value.code=='evidence_budget_exceeded' and 'context_limit' in detail['reasons']
    assert detail['budget']['message_chars']>2000 and detail['budget']['context_limit']==2000
    assert detail['budget']['groups']==3 and not rig.rag.tickets and not rig.provider.requests
    p=select(rig,d,[ids[0],ids[2]],version=1)
    assert [e['text'] for e in p['evidence']]==['虚构短段落。','虚构尾段。']


def test_total_context_including_history_and_json_is_measured(rig):
    rig.grant(['b']);rig.provider.reply={'status':'partial','answer':'林晓岚。[S1]其他信息无法确定。','citations':['S1']}
    d=rig.rag.draft('虚构负责人？');p=select(rig,d);rig.rag.answer(p['ticket'],True)
    next_d=rig.rag.draft('那她同时是导师吗？',d['session_id']);next_p=select(rig,next_d)
    assert len(next_p['history'])==1 and '[S1]' not in next_p['history'][0]['answer']
    usage=next_p['budget']['message_chars']
    assert usage==len(json.dumps(next_p['messages'],ensure_ascii=False))
    assert usage>sum(len(e['text']) for e in next_p['evidence'])
    assert len(rig.provider.requests)==1 # Follow-up draft/selection do not send.


@pytest.mark.parametrize('when',['selection','answer'])
@pytest.mark.parametrize('change',['revision','delete','review','revoke','result','index','text'])
def test_source_changes_block_selection_or_dispatch(rig,when,change):
    rig.grant(['b']);d=rig.rag.draft('虚构问题？')
    if when=='answer':p=select(rig,d)
    if change=='revision':rig.docs['b']['revision']+=1
    elif change=='delete':rig.docs['b']['state']='deleted'
    elif change=='review':rig.docs['b']['state']='review'
    elif change=='revoke':rig.grant([])
    elif change=='result':rig.docs['b']['result']['blocks'][0]['text']='虚构新解析'
    elif change=='index':rig.service.current_config=lambda:False
    else:rig.chunks['b']['text']='虚构新片段'
    with pytest.raises(RagError) as error:
        select(rig,d) if when=='selection' else rig.rag.answer(p['ticket'],True)
    assert error.value.code=='evidence_stale' and not rig.provider.requests


def grouped_search(rig):
    original=rig.service.search
    for identifier in rig.docs:
        rig.chunks[identifier]['text']='完全虚构项目负责人：林晓岚。'
        rig.docs[identifier]['result']={'blocks':[{'text':rig.chunks[identifier]['text']}]}
    def search(query,top_k,document_filter=None):
        values=original(query,top_k,document_filter)['results']
        return {'results':[dict(values[0],members=values)] if values else [],'retrieval_mode':'hybrid_dedup'}
    rig.service.search=search


def test_mixed_permission_multisource_group_is_split_and_never_leaks(rig):
    grouped_search(rig);rig.grant(['a','b'])
    d=rig.rag.draft('虚构负责人？')
    assert len(d['candidates'])==2
    authorized=next(c for c in d['candidates'] if c['selectable'])
    local=next(c for c in d['candidates'] if not c['selectable'])
    assert local['evidence']['document_id']=='secret'
    assert [m['document_id'] for m in authorized['evidence']['members']]==['a','b']
    p=select(rig,d);rig.provider.reply={'status':'answered','answer':'林晓岚。[S1]','citations':['S1']}
    r=rig.rag.answer(p['ticket'],True)
    members=r['citations'][0]['members']
    assert [m['document_id'] for m in members]==['a','b']
    assert all(m['revision']==1 and m['index_token']=='token-'+m['document_id']+'-1' for m in members)
    assert all(m['sources']==[{'block_id':'p1'}] for m in members)
    assert rig.provider.requests==[p['messages']]
    assert 'secret.docx' not in json.dumps(rig.provider.requests)


def test_revoked_group_member_is_not_silently_removed(rig):
    grouped_search(rig);rig.grant(['a','b']);d=rig.rag.draft('虚构问题？');rig.grant(['a'])
    with pytest.raises(RagError) as error:select(rig,d)
    assert error.value.code=='evidence_stale' and not rig.rag.tickets


def test_authorized_lane_survives_twenty_high_local_only_candidates(rig):
    install_ranked_fictional_documents(rig,[f'完全虚构第{i}段。' for i in range(26)])
    rig.grant(['g25']);original=rig.service.search;scopes=[]
    def search(query,top_k,document_filter=None):
        scopes.append(document_filter is not None)
        return {'results':original(query,top_k,document_filter)['results'][:top_k]}
    rig.service.search=search
    d=rig.rag.draft('虚构目标？')
    assert scopes==[True,False] and candidate(d,'g25')['selectable']
    assert len(d['candidates'])==21 and len(d['default_candidate_ids'])==1
    assert not rig.provider.requests


def test_client_edited_draft_does_not_modify_server_candidate(rig):
    rig.grant(['b']);d=rig.rag.draft('虚构问题？');c=candidate(d,'b');original=c['evidence']['text']
    c['evidence']['text']='client forged text';c['selectable']=False
    p=select(rig,d,[c['candidate_id']]);assert p['evidence'][0]['text']==original


def test_stale_draft_and_configuration_changes_fail_closed(rig,monkeypatch):
    rig.grant(['b']);d=rig.rag.draft('虚构问题？')
    rig.rag.drafts[d['draft_id']]['at']-=181
    with pytest.raises(RagError) as error:select(rig,d)
    assert error.value.code=='draft_expired'
    d=rig.rag.draft('虚构问题？');p=select(rig,d)
    monkeypatch.setenv('P18_DEEPSEEK_MODEL','another-model')
    with pytest.raises(RagError) as error:select(rig,d,version=1)
    assert error.value.code=='config_changed'
    with pytest.raises(RagError):rig.rag.answer(p['ticket'],True)
    assert not rig.provider.requests


def test_concurrent_selection_versions_accept_only_one_update(rig):
    rig.grant(['b']);d=rig.rag.draft('虚构问题？')
    def update():
        try:return select(rig,d)
        except RagError as e:return e
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:update(),range(2)))
    assert sum(isinstance(r,RagError) for r in results)==1
    assert next(r for r in results if isinstance(r,RagError)).code=='selection_changed'
    assert len(rig.rag.tickets)==1 and not rig.provider.requests


def test_dispatch_does_not_block_unrelated_session_or_accept_busy_edit(rig):
    rig.grant(['b']);d=rig.rag.draft('虚构问题？');p=select(rig,d)
    rig.provider.reply={'status':'answered','answer':'林晓岚。[S1]','citations':['S1']}
    entered=threading.Event();release=threading.Event()
    def wait():
        if threading.current_thread().name.startswith('slow'):
            entered.set();assert release.wait(5)
    rig.provider.hook=wait
    with ThreadPoolExecutor(1,thread_name_prefix='slow') as pool:
        future=pool.submit(rig.rag.answer,p['ticket'],True)
        try:
            assert entered.wait(2)
            with pytest.raises(RagError) as error:select(rig,d,version=1)
            assert error.value.code=='session_busy'
            other=rig.rag.draft('另一个会话？');next_p=select(rig,other)
            assert rig.rag.answer(next_p['ticket'],True)['answer_status']=='answered'
        finally:release.set()
        assert future.result(timeout=2)['answer_status']=='answered'
    assert len(rig.provider.requests)==2


@pytest.mark.parametrize('state',['answered','partial','insufficient_evidence'])
def test_selected_evidence_uses_existing_answer_state_validation(rig,state):
    rig.grant(['b']);d=rig.rag.draft('虚构问题？');p=select(rig,d)
    rig.provider.reply={'status':state,'answer':'林晓岚。[S1]','citations':['S1']}
    result=rig.rag.answer(p['ticket'],True)
    assert result['answer_status']==state
    if state=='insufficient_evidence':assert result['answer']==UNKNOWN and result['citations']==[]
    else:assert result['citations']==p['evidence']


def test_unselected_but_authorized_evidence_is_not_a_valid_citation(rig):
    rig.grant(['a','b']);d=rig.rag.draft('虚构问题？');p=select(rig,d,[candidate(d,'b')['candidate_id']])
    rig.provider.reply={'status':'answered','answer':'不能引用未选片段[S2]','citations':['S2']}
    with pytest.raises(RagError) as error:rig.rag.answer(p['ticket'],True)
    assert error.value.code=='citation_unknown'


def test_api_selection_contract_and_capture(client,rig,monkeypatch):
    monkeypatch.setattr(main,'RAG_SERVICE',rig.rag);rig.grant(['b'])
    assert client.post('/api/rag/drafts',json={'question':'虚构问题？'}).status_code==403
    draft=client.post('/api/rag/drafts',headers=HEADERS,json={'question':'虚构问题？'}).json()
    body={'draft_id':draft['draft_id'],'selection_version':0,'candidate_ids':draft['default_candidate_ids']}
    for extra in [{'text':'forged'},{'authorized':True},{'history':[]}]:
        assert client.post('/api/rag/selection',headers=HEADERS,json={**body,**extra}).status_code==422
    assert client.post('/api/rag/selection',headers=HEADERS,json={**body,'selection_version':False}).status_code==422
    p=client.post('/api/rag/selection',headers=HEADERS,json=body).json()
    assert not rig.provider.requests
    rig.provider.reply={'status':'answered','answer':'林晓岚。[S1]','citations':['S1']}
    result=client.post('/api/rag/answer',headers=HEADERS,json={'ticket':p['ticket'],'consent':True})
    assert result.status_code==200 and rig.provider.requests==[p['messages']]


def test_api_budget_errors_include_usage_and_next_selection_version(client,rig,monkeypatch):
    monkeypatch.setattr(main,'RAG_SERVICE',rig.rag)
    install_ranked_fictional_documents(rig,[f'完全虚构第{i}段。' for i in range(9)])
    d=client.post('/api/rag/drafts',headers=HEADERS,json={'question':'虚构目标？'}).json()
    response=client.post('/api/rag/selection',headers=HEADERS,json={'draft_id':d['draft_id'],
        'selection_version':0,'candidate_ids':[c['candidate_id'] for c in d['candidates']]})
    detail=response.json()['detail']
    assert response.status_code==409 and detail['code']=='evidence_budget_exceeded'
    assert detail['details']['budget']['groups']==9
    assert detail['details']['selection_version']==1
    assert not rig.provider.requests


def test_mutated_stored_message_snapshot_cannot_be_dispatched(rig):
    rig.grant(['b']);d=rig.rag.draft('虚构问题？');p=select(rig,d)
    rig.rag.tickets[p['ticket']]['messages'][1]['content']='unexpected internal mutation'
    with pytest.raises(RagError) as error:rig.rag.answer(p['ticket'],True)
    assert error.value.code=='selection_changed' and not rig.provider.requests


def test_combined_budget_rejects_groups_that_fit_individually(rig,monkeypatch):
    monkeypatch.setenv('P18_RAG_CONTEXT_CHARS','2000')
    install_ranked_fictional_documents(rig,['虚构甲段。'+'甲'*500,'虚构乙段。'+'乙'*500])
    from app.rag import config
    hits=rig.service.search('虚构目标？',20)['results']
    fields=['document_id','document_name','chunk_id','revision','index_token','text','section','sources','risk']
    single=[dict({k:h[k] for k in fields},id='S1')for h in hits]
    limit=max(2000,max(rig.rag.selection_budget('虚构目标？',[],[source],config())['message_chars'] for source in single)+32)
    monkeypatch.setenv('P18_RAG_CONTEXT_CHARS',str(limit))
    d=rig.rag.draft('虚构目标？');ids=[c['candidate_id'] for c in d['candidates']]
    assert all(rig.rag.selection_budget(d['question'],[],[dict(c['evidence'],id='S1')],
        rig.rag.drafts[d['draft_id']]['config'])['message_chars']<=limit for c in d['candidates'])
    with pytest.raises(RagError) as error:select(rig,d,ids)
    assert error.value.code=='evidence_budget_exceeded'
    assert error.value.details['budget']['groups']==2 and error.value.details['budget']['message_chars']>limit
    assert not rig.provider.requests and not rig.rag.tickets


def test_grant_after_local_draft_requires_new_retrieval(rig):
    d=rig.rag.draft('虚构问题？');rig.grant(['b'])
    with pytest.raises(RagError) as error:select(rig,d,[candidate(d,'b')['candidate_id']])
    assert error.value.code=='selection_forbidden'
    new=rig.rag.draft('虚构问题？',d['session_id'])
    assert candidate(new,'b')['selectable']


def test_api_draft_rejects_forged_history_or_permissions(client,rig,monkeypatch):
    monkeypatch.setattr(main,'RAG_SERVICE',rig.rag)
    for extra in [{'history':[]},{'allowed':True},{'evidence':[]}]:
        assert client.post('/api/rag/drafts',headers=HEADERS,json={'question':'虚构问题？',**extra}).status_code==422
    for ids in [[3],['x'*101]]:
        assert client.post('/api/rag/selection',headers=HEADERS,json={
            'draft_id':'unknown','selection_version':0,'candidate_ids':ids}).status_code==422
    assert not rig.provider.requests and not rig.rag.drafts


def test_draft_capacity_blocks_new_drafts_but_not_existing_confirmation(rig):
    rig.grant(['b']);d=rig.rag.draft('虚构问题？')
    snapshot=rig.rag.drafts[d['draft_id']]
    for i in range(127):rig.rag.drafts[f'capacity-{i}']=deepcopy(snapshot)
    with pytest.raises(RagError) as error:rig.rag.draft('另一个明确问题？',d['session_id'])
    assert error.value.code=='rag_busy'
    assert select(rig,d)['status']=='prepared' and not rig.provider.requests
