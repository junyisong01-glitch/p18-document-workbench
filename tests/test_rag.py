"""RAG protocol/security tests. Provider responses and retrieval boundary are simulated;
real embedding and browser retrieval are verified separately on fictional isolated data.
"""
from copy import deepcopy
import json
from types import SimpleNamespace
import threading
from unittest.mock import patch
from urllib.error import HTTPError,URLError

import pytest
from fastapi import HTTPException
from app.rag import RagService,RagError,DeepSeekClient,UNKNOWN,config,permission_fingerprint


class Provider:
    label='模拟API测试';configured=True
    def __init__(self):self.requests=[];self.reply={'status':'answered','answer':'林晓岚负责项目。[S2]','citations':['S2']};self.hook=lambda:None
    def complete(self,messages,cfg):self.requests.append(messages);self.hook();return json.dumps(self.reply,ensure_ascii=False)


@pytest.fixture
def rig(tmp_path):
    docs={id:{'id':id,'name':id+'.docx','revision':1,'state':'ready','sha256':id,'result':{'blocks':[{'text':'fictional '+id}]}} for id in ['a','b','secret']}
    chunks={id:{'id':'chunk-'+id,'document_id':id,'text':('项目负责人：林晓岚（虚构）；项目导师：林晓岚。' if id=='b' else 'UNAUTHORIZED_PRIVATE' if id=='secret' else '仅为测试标题，不含答案。')} for id in docs}
    def available(id):
        if id not in docs or docs[id]['state']=='deleted':raise HTTPException(404)
        return docs[id]
    def snapshot(id):
        if id not in docs or docs[id]['state']!='ready':return None
        return {'token':'token-'+id+'-'+str(docs[id]['revision']),'doc':docs[id],'chunks':[dict(chunks[id],revision=docs[id]['revision'])]}
    def search(query,top_k,document_filter=None):
        assert top_k==20
        values=[]
        for id in docs:
            if not snapshot(id) or (document_filter and not document_filter(docs[id])):continue
            values.append({'document_id':id,'document_name':docs[id]['name'],'chunk_id':chunks[id]['id'],'revision':docs[id]['revision'],
                           'index_token':snapshot(id)['token'],'text':chunks[id]['text'],'section':'正文','sources':[{'block_id':'p1'}],'risk':{'incomplete':False}})
        return {'results':values}
    service=SimpleNamespace(search=search,snapshot=snapshot,read=lambda id:{'status':'complete'},valid=lambda run,snap:bool(snap),current_config=lambda:True)
    store=SimpleNamespace(DATA=tmp_path,LOCK=threading.RLock(),HTTPException=HTTPException,available=available,require_semantic=lambda:service)
    provider=Provider();rag=RagService(store,provider)
    def grant(ids):
        values={id:{'revision':docs[id]['revision'],'fingerprint':permission_fingerprint(docs[id]),'classification':'fictional','reviewer':'虚构样例测试人员','allow_external':True} for id in ids}
        (tmp_path/'rag-permissions.json').write_text(json.dumps(values))
    return SimpleNamespace(docs=docs,chunks=chunks,rag=rag,provider=provider,grant=grant,service=service,store=store)


def test_default_no_permission_never_calls(rig):
    result=rig.rag.prepare('项目负责人是谁？');assert result['status']=='no_evidence';assert not rig.provider.requests


def test_second_evidence_and_explicit_consent(rig):
    rig.grant(['a','b']);p=rig.rag.prepare('项目负责人是谁？')
    assert len(p['evidence'])==2 and p['blocked_count']==0
    with pytest.raises(RagError,match='明确同意'):rig.rag.answer(p['ticket'],False)
    result=rig.rag.answer(p['ticket'],True);assert result['citations'][0]['document_id']=='b'
    sent=json.dumps(rig.provider.requests,ensure_ascii=False);assert 'UNAUTHORIZED_PRIVATE' not in sent and 'secret.docx' not in sent
    with pytest.raises(RagError,match='已使用'):rig.rag.answer(p['ticket'],True)


def test_followup_has_current_evidence_and_bounded_history(rig):
    rig.grant(['a','b']);p=rig.rag.prepare('项目负责人是谁？');rig.rag.answer(p['ticket'],True)
    q=rig.rag.prepare('那他同时也是项目导师吗？',p['session_id']);assert len(q['history'])==1
    assert '[S2]' not in q['history'][0]['answer'];assert q['evidence']
    rig.rag.answer(q['ticket'],True);assert len(rig.provider.requests)==2


def test_ambiguous_pronoun_without_context_clarifies(rig):
    rig.grant(['b']);assert rig.rag.prepare('那他是谁？')['status']=='clarify';assert not rig.provider.requests


@pytest.mark.parametrize('change',['revision','delete','review','revoke','result','index'])
def test_invalidated_evidence_prevents_dispatch(rig,change):
    rig.grant(['b']);p=rig.rag.prepare('负责人是谁？')
    if change=='revision':rig.docs['b']['revision']+=1
    elif change=='delete':rig.docs['b']['state']='deleted'
    elif change=='review':rig.docs['b']['state']='review'
    elif change=='revoke':rig.grant([])
    elif change=='result':rig.docs['b']['result']['blocks'][0]['text']='changed'
    else:rig.service.current_config=lambda:False
    with pytest.raises(RagError,match='失效'):rig.rag.answer(p['ticket'],True)
    assert not rig.provider.requests


def test_history_egress_permission_rechecked(rig):
    rig.grant(['a','b']);p=rig.rag.prepare('项目负责人是谁？');rig.rag.answer(p['ticket'],True);rig.grant(['a'])
    with pytest.raises(RagError,match='历史'):rig.rag.prepare('那他是谁？',p['session_id'])
    assert len(rig.provider.requests)==1


def test_invalidated_during_request_suppresses_answer(rig):
    rig.grant(['a','b']);p=rig.rag.prepare('负责人？');rig.provider.hook=lambda:rig.docs['b'].update(state='review')
    with pytest.raises(RagError,match='无法撤回'):rig.rag.answer(p['ticket'],True)


@pytest.mark.parametrize('reply',[{'status':'answered','answer':'林某[S99]','citations':['S99']},{'status':'answered','answer':'无引用事实','citations':[]},{'status':'answered','answer':'看第999页[S1]','citations':['S1']},{'status':'answered','answer':'看invented.pdf[S1]','citations':['S1']},{'status':'answered','answer':'林某[S1]','citations':['S2']}])
def test_invalid_citations_never_published(rig,reply):
    rig.grant(['a','b']);p=rig.rag.prepare('负责人？');rig.provider.reply=reply
    with pytest.raises(RagError):rig.rag.answer(p['ticket'],True)


def test_no_answer_is_explicit(rig):
    rig.grant(['a']);p=rig.rag.prepare('不存在的事实？');rig.provider.reply={'status':'insufficient_evidence','answer':UNKNOWN,'citations':[]}
    r=rig.rag.answer(p['ticket'],True);assert r['answer']==UNKNOWN and not r['citations']


def test_destination_change_requires_new_consent(rig,monkeypatch):
    rig.grant(['a']);p=rig.rag.prepare('问题？');monkeypatch.setenv('P18_DEEPSEEK_BASE_URL','https://other.example')
    with pytest.raises(RagError,match='地址'):rig.rag.answer(p['ticket'],True)
    assert not rig.provider.requests


@pytest.mark.parametrize('failure,code',[(ConnectionResetError(),'api_network'),(URLError(TimeoutError()),'api_timeout'),(TimeoutError(),'api_timeout'),(URLError('network'),'api_network'),(HTTPError('https://api.deepseek.com',429,'limited',{},None),'api_rate_limit'),(HTTPError('https://api.deepseek.com',401,'secret-key-dont-print',{},None),'api_auth')])
def test_transport_failures_sanitized(monkeypatch,failure,code):
    monkeypatch.setenv('DEEPSEEK_API_KEY','test-only-secret')
    with patch('app.rag.secure_urlopen',side_effect=failure):
        with pytest.raises(RagError) as e:DeepSeekClient().complete([],config())
    assert e.value.code==code and 'secret' not in str(e.value)


def test_missing_key_and_unsafe_url(monkeypatch):
    monkeypatch.delenv('DEEPSEEK_API_KEY',raising=False)
    with pytest.raises(RagError,match='密钥'):DeepSeekClient().complete([],config())
    monkeypatch.setenv('P18_DEEPSEEK_BASE_URL','http://insecure.example')
    with pytest.raises(RagError):config()


def test_operator_grant_binds_exact_revision(tmp_path):
    import sqlite3
    from scripts.rag_permissions import grant
    doc={'id':'fictional','revision':1,'state':'ready','sha256':'a','result':{'text':'仅虚构'}}
    with sqlite3.connect(tmp_path/'workbench.sqlite3') as c:c.execute('create table documents(id text,body text)');c.execute('insert into documents values (?,?)',('fictional',json.dumps(doc)))
    with pytest.raises(ValueError):grant(tmp_path,'fictional',1,'测试人','fictional',False)
    path=grant(tmp_path,'fictional',1,'测试人','fictional',True)
    from app.rag import allowed
    assert allowed(tmp_path,doc)
    changed=deepcopy(doc);changed['revision']=2;assert not allowed(tmp_path,changed)
    assert path.stat().st_mode & 0o777==0o600


def test_multi_entity_history_requests_clarification(rig):
    rig.grant(['a','b']);p=rig.rag.prepare('项目负责人和联系人分别是谁？');rig.rag.answer(p['ticket'],True)
    assert rig.rag.prepare('那他是谁？',p['session_id'])['status']=='clarify'


def test_redirect_is_blocked_without_forwarding():
    from app.rag import NoRedirect
    with pytest.raises(RagError,match='重定向'):
        NoRedirect().redirect_request(None,None,302,'m',{},'https://evil.example')


def test_successful_transport_payload_never_exposes_key(monkeypatch):
    from unittest.mock import MagicMock
    monkeypatch.setenv('DEEPSEEK_API_KEY','test-secret-only')
    response=MagicMock();response.__enter__.return_value=response
    response.read.return_value=json.dumps({'choices':[{'finish_reason':'stop','message':{'content':'{"status":"insufficient_evidence","answer":"'+UNKNOWN+'","citations":[]}'}}]}).encode()
    with patch('app.rag.secure_urlopen',return_value=response) as send:
        content=DeepSeekClient().complete([{'role':'system','content':'JSON'}],config())
    req=send.call_args.args[0];payload=json.loads(req.data)
    assert req.full_url=='https://api.deepseek.com/chat/completions'
    assert payload['stream'] is False and payload['model']=='deepseek-flash' and 'test-secret-only' not in json.dumps(payload)
    assert json.loads(content)['citations']==[]


def test_grouped_evidence_preserves_only_authorized_members(rig):
    original=rig.service.search('test',20)['results']
    rig.service.search=lambda query,top_k,document_filter=None:{'results':[dict(original[0],members=original)]}
    rig.grant(['a','b']);p=rig.rag.prepare('负责人是谁？')
    assert len(p['evidence'])==1 and len(p['evidence'][0]['members'])==2
    assert p['blocked_count']==1
    rig.provider.reply={'status':'answered','answer':'林晓岚。[S1]','citations':['S1']}
    result=rig.rag.answer(p['ticket'],True)
    assert len(result['citations'][0]['members'])==2
    assert 'UNAUTHORIZED_PRIVATE' not in json.dumps(rig.provider.requests)


def test_session_window_is_bounded(rig):
    rig.grant(['a','b']);sid=None
    for n in range(5):
        p=rig.rag.prepare(f'第{n}轮项目负责人是谁？',sid);sid=p['session_id'];rig.rag.answer(p['ticket'],True)
    assert len(rig.rag.sessions[sid]['turns'])==3
    assert len(rig.rag.prepare('下一个明确问题',sid)['history'])==3


def test_authorized_evidence_not_starved_by_twenty_higher_unlicensed_hits(rig):
    # Simulate retrieval cutoff AFTER applying the caller's document scope.
    original=rig.service.search
    hits=original('q',20)['results']
    high=[dict(hits[-1],chunk_id=f'private-{i}') for i in range(25)]
    ranked=high+[hits[1]]
    scopes=[]
    def scoped_search(query,top_k,document_filter=None):
        scopes.append(document_filter)
        values=[h for h in ranked if document_filter is None or document_filter(rig.docs[h['document_id']])]
        return {'results':values[:top_k]}
    rig.service.search=scoped_search;rig.grant(['b'])
    p=rig.rag.prepare('项目负责人是谁？')
    assert scopes[0] is not None
    assert [s['chunk_id'] for s in p['evidence']]==['chunk-b']
    rig.provider.reply={'status':'answered','answer':'林晓岚。[S1]','citations':['S1']}
    rig.rag.answer(p['ticket'],True)
    assert 'UNAUTHORIZED_PRIVATE' not in json.dumps(rig.provider.requests)


def test_network_wait_does_not_block_other_sessions_and_ticket_is_single_use(rig):
    from concurrent.futures import ThreadPoolExecutor
    entered=threading.Event();release=threading.Event()
    rig.grant(['a','b']);first=rig.rag.prepare('项目负责人是谁？')
    sibling=rig.rag.prepare('另一个问题',first['session_id'])
    def wait():
        if threading.current_thread().name.startswith('slow'):
            entered.set();assert release.wait(5)
    rig.provider.hook=wait
    with ThreadPoolExecutor(1,thread_name_prefix='slow') as slow, ThreadPoolExecutor(1) as other:
        pending=slow.submit(rig.rag.answer,first['ticket'],True)
        try:
            assert entered.wait(2)
            # Busy sessions must survive pruning while a request is in flight.
            rig.rag.sessions[first['session_id']]['at']-=2000
            def unrelated():
                p=rig.rag.prepare('另一会话的项目负责人？')
                return rig.rag.answer(p['ticket'],True)
            assert other.submit(unrelated).result(timeout=2)['status']=='answered'
            with pytest.raises(RagError) as reused:rig.rag.answer(first['ticket'],True)
            assert reused.value.code=='ticket_expired'
            with pytest.raises(RagError) as busy:rig.rag.prepare('追问',first['session_id'])
            assert busy.value.code=='session_busy'
            with pytest.raises(RagError) as duplicate:rig.rag.answer(sibling['ticket'],True)
            assert duplicate.value.code=='session_busy'
            assert rig.rag.sessions[first['session_id']]['turns']==[]
        finally:release.set()
        assert pending.result(timeout=2)['status']=='answered'
    assert len(rig.rag.sessions[first['session_id']]['turns'])==1
    assert len(rig.provider.requests)==2
    assert not rig.rag.sessions[first['session_id']]['busy']
    assert rig.rag.prepare('完成后的问题',first['session_id'])['status']=='prepared'


def test_failed_request_releases_session_without_reusing_ticket(rig):
    rig.grant(['a','b']);p=rig.rag.prepare('负责人？')
    def fail():raise RagError('api_timeout','测试超时')
    rig.provider.hook=fail
    with pytest.raises(RagError):rig.rag.answer(p['ticket'],True)
    assert not rig.rag.sessions[p['session_id']]['busy']
    assert rig.rag.sessions[p['session_id']]['turns']==[]
    with pytest.raises(RagError) as used:rig.rag.answer(p['ticket'],True)
    assert used.value.code=='ticket_expired'
    rig.provider.hook=lambda:None
    next_turn=rig.rag.prepare('重试负责人？',p['session_id'])
    assert rig.rag.answer(next_turn['ticket'],True)['status']=='answered'


@pytest.mark.parametrize('state',['answered','partial'])
def test_answer_states_preserve_verified_citations(rig,state):
    rig.grant(['a','b']);p=rig.rag.prepare('负责人及未知事项？')
    text='林晓岚负责项目。[S2]'+('其他部分证据不足。' if state=='partial' else '')
    rig.provider.reply={'status':state,'answer':text,'citations':['S2']}
    result=rig.rag.answer(p['ticket'],True)
    assert result['answer_status']==state and result['answer']==text
    assert result['citations'][0]['chunk_id']=='chunk-b'


@pytest.mark.parametrize('text,ids',[
    ('抱歉，材料没有提及，无法回答。',[]),
    ('\n现有证据不足。\n',[]),
    ('当前检索材料不包含该值。[S1][S2]',['S1','S2']),
    ('任意模型生成内容必须全部丢弃，即使夹带错误事实。[S2]',['S2']),
])
def test_insufficient_evidence_always_canonicalizes_whole_answer(rig,text,ids):
    rig.grant(['a','b']);p=rig.rag.prepare('duration示例值？')
    rig.provider.reply={'status':'insufficient_evidence','answer':text,'citations':ids}
    result=rig.rag.answer(p['ticket'],True)
    assert result['answer_status']=='insufficient_evidence'
    assert result['answer']==UNKNOWN and result['citations']==[]
    assert result['evidence']==p['evidence'] # still available via 查看检索依据
    assert rig.rag.sessions[p['session_id']]['turns'][0]['answer']==UNKNOWN


@pytest.mark.parametrize('raw,code',[
    ('not-json','answer_format'),
    ('[]','answer_format'),
    ('{"answer":"x","citations":[]}','answer_format'),
    ('{"status":"partial","answer":3,"citations":[]}','answer_format'),
    ('{"status":"answered","answer":"x","citations":[3]}','answer_format'),
    ('{"status":"other","answer":"x","citations":[]}','answer_status'),
    ('{"status":[],"answer":"x","citations":[]}','answer_status'),
    ('{"status":"answered","answer":"事实[S99]","citations":["S99"]}','citation_unknown'),
    ('{"status":"insufficient_evidence","answer":"不足[S99]","citations":["S99"]}','citation_unknown'),
    ('{"status":"partial","answer":"事实[S1]","citations":["S2"]}','citation_mismatch'),
    ('{"status":"insufficient_evidence","answer":"不足[S1]","citations":[]}','citation_mismatch'),
    ('{"status":"answered","answer":"根据当前可用的文档证据，无法确定。","citations":[]}','citation_required'),
    ('{"status":"partial","answer":"部分事实","citations":[]}','citation_required'),
    ('{"status":"answered","answer":"见第99页[S1]","citations":["S1"]}','answer_location'),
])
def test_protocol_errors_have_safe_specific_codes(rig,raw,code):
    rig.grant(['a','b']);p=rig.rag.prepare('问题？')
    rig.provider.complete=lambda *args:raw
    with pytest.raises(RagError) as error:rig.rag.answer(p['ticket'],True)
    assert error.value.code==code and raw not in str(error.value)
    assert not rig.rag.sessions[p['session_id']]['turns']
    assert not rig.rag.sessions[p['session_id']]['busy']


@pytest.mark.parametrize('state',['answered','partial','insufficient_evidence'])
@pytest.mark.parametrize('when',['before','during'])
def test_all_states_still_reject_revoked_evidence(rig,state,when):
    rig.grant(['a','b']);p=rig.rag.prepare('未知问题？')
    rig.provider.reply={'status':state,'answer':'原文结论[S2]','citations':['S2']}
    if when=='before':rig.grant([])
    else:rig.provider.hook=lambda:rig.grant([])
    with pytest.raises(RagError) as error:rig.rag.answer(p['ticket'],True)
    assert error.value.code=='evidence_stale'
    assert len(rig.provider.requests)==(0 if when=='before' else 1)
    assert not rig.rag.sessions[p['session_id']]['turns']


def test_prompt_and_demo_follow_same_status_protocol(rig):
    from app.rag import SYSTEM
    from scripts.serve_rag_demo import SimulatedClient
    for state in ['answered','partial','insufficient_evidence']:assert state in SYSTEM
    payload={'question':'不存在的问题','untrusted_evidence':[]}
    response=json.loads(SimulatedClient().complete([{'content':json.dumps(payload)}],config()))
    assert response=={'status':'insufficient_evidence','answer':UNKNOWN,'citations':[]}
