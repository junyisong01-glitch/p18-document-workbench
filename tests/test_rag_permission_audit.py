"""Offline permission-generation and request-correlation regressions; fictional data only."""
import json
import sqlite3
from copy import deepcopy

import pytest
from app import egress, main
from app.rag_context import model_evidence
from app.rag import RagError, digest
from test_rag import rig
from test_external_permission import audit, grant_rig, CHECKS


def change_grant(r, identifier, regrant=True):
    doc=r.docs[identifier]
    egress.update(r.store.DATA,doc,doc['revision'],egress.fingerprint(doc),revoke=True)
    if regrant:
        egress.update(r.store.DATA,doc,doc['revision'],egress.fingerprint(doc),'public_verified',CHECKS)


def two_rounds(r, path='selection'):
    grant_rig(r)
    search=r.service.search
    lane=['a']
    def restricted(*args, **kwargs):
        result=search(*args,**kwargs)
        result['results']=[s for s in result['results'] if s['document_id'] in lane]
        return result
    r.service.search=restricted
    r.provider.reply={'status':'answered','answer':'虚构测试结论。[S1]','citations':['S1']}
    first=r.rag.prepare('虚构第一轮问题')
    r.rag.answer(first['ticket'],True)
    lane[:]=['b']
    if path=='prepare':
        second=r.rag.prepare('虚构第二轮问题',first['session_id'])
        return first,None,second
    draft=r.rag.draft('虚构第二轮问题',first['session_id'])
    second=r.rag.selection(draft['draft_id'],0,draft['default_candidate_ids'])
    assert [s['document_id'] for s in second['evidence']]==['b'] and len(second['history'])==1
    return first,draft,second


@pytest.mark.parametrize('path',['prepare','selection'])
@pytest.mark.parametrize('identifier',['a','b'])
@pytest.mark.parametrize('regrant',[False,True])
def test_current_and_historical_grant_change_invalidates_ticket(rig,path,identifier,regrant):
    _,_,p=two_rounds(rig,path)
    change_grant(rig,identifier,regrant)
    with pytest.raises(RagError) as exc:rig.rag.answer(p['ticket'],True)
    assert exc.value.code=='evidence_stale'
    assert len(rig.provider.requests)==1
    action,row=audit(rig.store.DATA)[-1]
    assert action=='egress_blocked' and row['request_id']==p['request_id']


@pytest.mark.parametrize('identifier',['a','b'])
def test_draft_cannot_refresh_changed_grant_into_new_ticket(rig,identifier):
    _,d,_=two_rounds(rig)
    change_grant(rig,identifier)
    with pytest.raises(RagError) as exc:
        rig.rag.selection(d['draft_id'],1,d['default_candidate_ids'])
    assert exc.value.code=='evidence_stale' and len(rig.provider.requests)==1
    assert audit(rig.store.DATA)[-1][1]['request_id']==d['request_id']


@pytest.mark.parametrize('path',['prepare','selection'])
def test_regranted_history_cannot_be_silently_reused_on_new_preparation(rig,path):
    first,_,_=two_rounds(rig)
    change_grant(rig,'a')
    operation=rig.rag.prepare if path=='prepare' else rig.rag.draft
    with pytest.raises(RagError) as exc:operation('虚构第三轮问题',first['session_id'])
    assert exc.value.code=='history_invalid' and len(rig.provider.requests)==1


@pytest.mark.parametrize('path',['prepare','selection'])
def test_inflight_history_regrant_blocks_publication(rig,path):
    _,_,p=two_rounds(rig,path)
    rig.provider.hook=lambda:change_grant(rig,'a')
    with pytest.raises(RagError) as exc:rig.rag.answer(p['ticket'],True)
    assert exc.value.code=='evidence_stale' and len(rig.provider.requests)==2
    assert audit(rig.store.DATA)[-1][1]['request_id']==p['request_id']
    assert audit(rig.store.DATA)[-1][1]['code']=='evidence_stale'


@pytest.mark.parametrize('path',['prepare','selection'])
def test_success_metadata_snapshot_and_all_phases_correlate(rig,path,monkeypatch):
    monkeypatch.setenv('P18_DEEPSEEK_BASE_URL','https://receiver.example.test/v1')
    _,d,p=two_rounds(rig,path)
    # No model call during preparation or selection.
    assert len(rig.provider.requests)==1
    rig.rag.answer(p['ticket'],True)
    records=[(a,b) for a,b in audit(rig.store.DATA) if b.get('request_id')==p['request_id']]
    actions=[a for a,b in records]
    expected=['egress_prepared','egress_confirmed','egress_allowed','send_attempt','send_result']
    assert actions==(['egress_drafted'] if d else [])+expected
    sent=rig.provider.requests[-1]
    for action,row in records:
        assert row['model']=='deepseek-flash'
        assert row['request_endpoint']=='https://receiver.example.test/v1/chat/completions'
        if action=='egress_drafted':
            assert row['snapshot_stage']=='provisional' and row['messages_hash'] is None
        else:
            assert row['snapshot_stage']=='final' and row['messages_hash']==digest(sent)
            assert {s['document_id'] for s in row['sources']}=={'a','b'}
            assert all(s['grant_id'] for s in row['sources'])
        assert '虚构第二轮问题' not in json.dumps(row,ensure_ascii=False)
        assert 'UNAUTHORIZED_PRIVATE' not in json.dumps(row)
    payload=json.loads(sent[1]['content'])
    assert payload['question']==p['question'] and payload['history_for_reference_only']==p['history']
    assert payload['untrusted_evidence']==model_evidence(p['evidence'])


def test_selection_edits_failure_and_consumed_ticket_keep_request_id(rig):
    grant_rig(rig);d=rig.rag.draft('虚构问题')
    p=rig.rag.selection(d['draft_id'],0,d['default_candidate_ids'])
    secret=next(c for c in d['candidates'] if not c['selectable'])
    with pytest.raises(RagError):rig.rag.selection(d['draft_id'],1,[secret['candidate_id']])
    assert audit(rig.store.DATA)[-1][1]['selection_version']==2
    with pytest.raises(RagError):rig.rag.answer(p['ticket'],True)
    rows=[b for a,b in audit(rig.store.DATA) if a.startswith('egress_')]
    assert {r['request_id'] for r in rows}=={d['request_id']}
    assert not rig.provider.requests


def test_network_failure_correlates_no_retry_or_response_body(rig):
    grant_rig(rig);p=rig.rag.prepare('虚构问题')
    def fail(messages,cfg):
        rig.provider.requests.append(deepcopy(messages))
        raise RagError('api_timeout','offline timeout')
    rig.provider.complete=fail
    with pytest.raises(RagError):rig.rag.answer(p['ticket'],True)
    rows=[b for a,b in audit(rig.store.DATA) if b.get('request_id')==p['request_id']]
    assert len(rig.provider.requests)==1 and rows[-1]['code']=='api_timeout'
    assert all(r['messages_hash']==digest(rig.provider.requests[0]) for r in rows)
    assert all('answer' not in r and 'messages' not in r for r in rows)


@pytest.mark.parametrize('action',['egress_prepared','egress_confirmed','egress_allowed','send_attempt'])
def test_required_audit_failure_never_dispatches(rig,monkeypatch,action):
    grant_rig(rig)
    original=__import__('app.rag',fromlist=['egress_audit']).egress_audit
    def guarded(data,event,details):
        if event==action:raise sqlite3.OperationalError('offline audit unavailable')
        return original(data,event,details)
    p=None
    if action!='egress_prepared':p=rig.rag.prepare('虚构问题')
    monkeypatch.setattr('app.rag.egress_audit',guarded)
    with pytest.raises(sqlite3.OperationalError):
        if p:rig.rag.answer(p['ticket'],True)
        else:rig.rag.prepare('虚构问题')
    assert not rig.provider.requests


def test_api_wrapper_does_not_duplicate_or_lose_audit(rig,monkeypatch):
    grant_rig(rig);monkeypatch.setattr(main,'RAG_SERVICE',rig.rag)
    d=main.rag_call('draft','虚构问题',None,None)
    p=main.rag_call('selection',d['draft_id'],0,d['default_candidate_ids'])
    assert [a for a,b in audit(rig.store.DATA) if b.get('request_id')==d['request_id']]==['egress_drafted','egress_prepared']
    assert p['request_id']==d['request_id'] and not rig.provider.requests


@pytest.mark.parametrize('path',['prepare','selection'])
def test_history_budget_binds_only_actual_sent_history(rig,path):
    first,_,_=two_rounds(rig)
    # Offline fixture models a long old answer; normal context budgeting removes it.
    rig.rag.sessions[first['session_id']]['turns'][0]['answer']='虚构长历史'*3000
    if path=='prepare':p=rig.rag.prepare('虚构新问题',first['session_id'])
    else:
        d=rig.rag.draft('虚构新问题',first['session_id'])
        p=rig.rag.selection(d['draft_id'],0,d['default_candidate_ids'])
    assert p['history']==[]
    change_grant(rig,'a')
    rig.rag.answer(p['ticket'],True)
    assert json.loads(rig.provider.requests[-1][1]['content'])['history_for_reference_only']==[]


def test_multisource_history_grant_is_bound(rig):
    grant_rig(rig);search=rig.service.search
    def merged(*args,**kwargs):
        r=search(*args,**kwargs)
        hits=[s for s in r['results'] if s['document_id']!='secret']
        if len(hits)>1:r['results']=[dict(hits[0],members=hits)]
        return r
    rig.service.search=merged
    rig.provider.reply={'status':'answered','answer':'虚构结论。[S1]','citations':['S1']}
    p=rig.rag.prepare('虚构第一轮');rig.rag.answer(p['ticket'],True)
    q=rig.rag.prepare('虚构第二轮',p['session_id'])
    assert len(q['evidence'][0]['members'])==2
    change_grant(rig,'b')
    with pytest.raises(RagError):rig.rag.answer(q['ticket'],True)
    assert len(rig.provider.requests)==1


def test_source_dependency_survives_history_window(rig):
    first,_,second=two_rounds(rig)
    rig.rag.answer(second['ticket'],True)
    for _ in range(4):
        p=rig.rag.prepare('虚构后续问题',first['session_id'])
        rig.rag.answer(p['ticket'],True)
    # A's original round has left the three-turn window, but later answers used it.
    assert all(t['question']!='虚构第一轮问题' for t in rig.rag.sessions[first['session_id']]['turns'])
    p=rig.rag.prepare('虚构最后问题',first['session_id'])
    change_grant(rig,'a')
    count=len(rig.provider.requests)
    with pytest.raises(RagError) as exc:rig.rag.answer(p['ticket'],True)
    assert exc.value.code=='evidence_stale' and len(rig.provider.requests)==count


@pytest.mark.parametrize('path',['prepare','selection'])
def test_history_grant_change_during_retrieval_is_not_rebound(rig,path):
    first,_,_=two_rounds(rig)
    search=rig.service.search
    changed=[]
    def changing(*args,**kwargs):
        if not changed:
            change_grant(rig,'a');changed.append(True)
        return search(*args,**kwargs)
    rig.service.search=changing
    with pytest.raises(RagError) as exc:
        if path=='prepare':rig.rag.prepare('虚构新问题',first['session_id'])
        else:
            d=rig.rag.draft('虚构新问题',first['session_id'])
            rig.rag.selection(d['draft_id'],0,d['default_candidate_ids'])
    assert exc.value.code=='evidence_stale' and len(rig.provider.requests)==1


@pytest.mark.parametrize('path',['prepare','selection'])
@pytest.mark.parametrize('identifier',['a','b'])
def test_concurrent_regrant_before_prepared_audit_keeps_bound_snapshot(rig,path,identifier):
    """A writer acquires store.LOCK after validation, before the prepared audit."""
    import threading
    first,_,_=two_rounds(rig)
    old_grant=egress.record(rig.store.DATA,rig.docs[identifier])['grant_id']
    entered=threading.Event();finished=threading.Event();errors=[]
    original=rig.rag.audit_request
    triggered=[]
    def writer():
        try:
            assert entered.wait(3)
            with rig.store.LOCK:change_grant(rig,identifier)
        except BaseException as exc:errors.append(exc)
        finally:finished.set()
    worker=threading.Thread(target=writer)
    worker.start()
    def interleaved(action,ticket=None,code=None):
        if action=='egress_prepared' and not triggered:
            triggered.append(True);entered.set()
            assert finished.wait(3), 'permission writer must not need the RAG lock'
        return original(action,ticket,code)
    rig.rag.audit_request=interleaved
    try:
        if path=='prepare':p=rig.rag.prepare('虚构并发问题',first['session_id'])
        else:
            d=rig.rag.draft('虚构并发问题',first['session_id'])
            p=rig.rag.selection(d['draft_id'],0,d['default_candidate_ids'])
    finally:
        entered.set();worker.join(3)
    assert not worker.is_alive() and not errors
    ticket=rig.rag.tickets[p['ticket']]
    assert ticket['permission_hash']!=rig.rag.permission_hash(ticket['evidence']+ticket['historical'])
    assert egress.record(rig.store.DATA,rig.docs[identifier])['grant_id']!=old_grant
    with pytest.raises(RagError) as exc:rig.rag.answer(p['ticket'],True)
    assert exc.value.code=='evidence_stale' and len(rig.provider.requests)==1
    records=[(a,b) for a,b in audit(rig.store.DATA) if b.get('request_id')==p['request_id']]
    for action,row in records:
        if row['snapshot_stage']!='final':continue
        assert row['permission_hash']==ticket['permission_hash']
        assert row['sources']==ticket['audit_sources']
        assert all(s['grant_id']==old_grant for s in row['sources'] if s['document_id']==identifier)
    assert records[-1][0]=='egress_blocked'
    # A second use is invalid; its metadata-only receipt still describes the old grant.
    with pytest.raises(RagError):rig.rag.answer(p['ticket'],True)
    assert audit(rig.store.DATA)[-1][1]['sources']==ticket['audit_sources']


@pytest.mark.parametrize('failure',[False,True])
def test_dispatch_audits_do_not_switch_grants_after_validation(rig,failure):
    _,_,p=two_rounds(rig)
    ticket=rig.rag.tickets[p['ticket']]
    frozen=deepcopy(ticket['audit_sources'])
    original=rig.rag.audit_request
    changed=[]
    def interleaved(action,ticket=None,code=None):
        if action=='egress_allowed' and not changed:
            with rig.store.LOCK:change_grant(rig,'a')
            changed.append(True)
        return original(action,ticket,code)
    rig.rag.audit_request=interleaved
    if failure:
        def fail(messages,cfg):
            rig.provider.requests.append(deepcopy(messages))
            raise RagError('api_timeout','offline timeout')
        rig.provider.complete=fail
    # Scheme A's pre-dispatch gap remains; audit identity must still be truthful.
    with pytest.raises(RagError) as exc:rig.rag.answer(p['ticket'],True)
    assert exc.value.code==('api_timeout' if failure else 'evidence_stale')
    rows=[b for a,b in audit(rig.store.DATA) if b.get('request_id')==p['request_id']]
    assert len(rig.provider.requests)==2
    assert all(row['sources']==frozen and row['permission_hash']==ticket['permission_hash']
               for row in rows if row['snapshot_stage']=='final')


@pytest.mark.parametrize('path',['prepare','selection'])
def test_final_audit_never_rereads_permission_records(rig,monkeypatch,path):
    grant_rig(rig)
    original=rig.rag.audit_request
    def frozen_only(action,ticket=None,code=None):
        if ticket and ticket.get('snapshot_stage')=='final':
            def forbidden(*args):raise AssertionError('final audit must use frozen grant metadata')
            with monkeypatch.context() as patch:
                patch.setattr('app.rag.permission_record',forbidden)
                return original(action,ticket,code)
        return original(action,ticket,code)
    rig.rag.audit_request=frozen_only
    if path=='prepare':p=rig.rag.prepare('虚构正常问题')
    else:
        d=rig.rag.draft('虚构正常问题')
        p=rig.rag.selection(d['draft_id'],0,d['default_candidate_ids'])
    assert rig.rag.answer(p['ticket'],True)['status']=='answered'
    assert len(rig.provider.requests)==1
