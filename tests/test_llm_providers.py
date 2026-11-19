import json,sys
from types import SimpleNamespace
import pytest
from app.llm import BaseLLMProvider,DeepSeekProvider,OllamaProvider,RoutedClient,ClientAdapter,guard,load_env,startup_check
from app.rag import RagError,RagService,config,UNKNOWN,SYSTEM
from test_rag import rig

def test_sdk_exact_destination_model_and_no_retries(monkeypatch):
    seen={}
    class SDK:
        def __init__(self,**kw):seen.update(kw);self.chat=SimpleNamespace(completions=self)
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def create(self,**kw):seen['body']=kw;return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content='{}'))])
    monkeypatch.setitem(sys.modules,'openai',SimpleNamespace(OpenAI=SDK))
    assert DeepSeekProvider(key='fictional-key').generate('公开虚构问题')=='{}'
    assert seen['base_url']=='https://api.deepseek.com' and seen['max_retries']==0
    assert seen['body']['model']=='deepseek-flash'
    assert seen['body']['messages'][0]['content']==SYSTEM
    assert seen['http_client'].follow_redirects is False and seen['http_client']._trust_env is False

def test_ollama_exact_payload_and_context(monkeypatch):
    calls=[]
    def transport(path,body=None,timeout=2):
        calls.append((path,body))
        return {'models':[{'name':'qwen2.5:7b'}]} if path=='/api/tags' else {'done':True,'done_reason':'stop','message':{'content':'{}'}}
    monkeypatch.setattr('app.llm.local_json',transport)
    assert OllamaProvider().generate('公开虚构问题')=='{}'
    path,body=calls[-1];assert path=='/api/chat' and body['options']['num_ctx']==16384
    assert body['stream'] is False and body['truncate'] is False
    assert body['think'] is False and body['keep_alive']==0
    assert body['options']['temperature']==0 and body['options']['seed']==42
    assert body['messages'][0]['content']==SYSTEM

@pytest.mark.parametrize('source',['qichen','qichen30','business'])
def test_qichen_guard_before_transport(source,monkeypatch):
    monkeypatch.setenv('LLM_PROVIDER','deepseek');c=RoutedClient(source_library=source)
    with pytest.raises(RagError,match='禁止'):c.provider(c.configuration(config()))
    with pytest.raises(RagError,match='禁止'):c.confirm_fallback()

def test_unavailable_never_silently_falls_back(monkeypatch):
    monkeypatch.setenv('LLM_PROVIDER','ollama')
    def unavailable(*a,**kw):raise RagError('ollama_unavailable','offline')
    monkeypatch.setattr('app.llm.local_json',unavailable)
    c=RoutedClient();assert not c.configured and c.name=='ollama'
    assert startup_check()['available'] is False
    with pytest.raises(RagError):c.complete(RagService.messages('公开虚构',[],[]),c.configuration(config()))
    assert c.name=='ollama'
    old=c.configuration(config());c.confirm_fallback();assert c.name=='deepseek' and old!=c.configuration(config())

def test_missing_model_and_truncated_output(monkeypatch):
    monkeypatch.setattr('app.llm.local_json',lambda *a,**kw:{'models':[]})
    with pytest.raises(RagError,match='未安装'):OllamaProvider().health()
    monkeypatch.setattr(OllamaProvider,'health',lambda self:True)
    monkeypatch.setattr('app.llm.local_json',lambda *a,**kw:{'done':True,'done_reason':'length','message':{'content':'partial'}})
    with pytest.raises(RagError,match='截断'):OllamaProvider().generate('公开虚构')

@pytest.mark.parametrize('value',['8192','bad'])
def test_no_small_or_invalid_context(monkeypatch,value):
    monkeypatch.setenv('OLLAMA_NUM_CTX',value)
    with pytest.raises(RagError):OllamaProvider()

def test_plain_and_serialized_prompt_share_system():
    from app.llm import messages
    assert '知识库中未找到相关内容' in SYSTEM and '末尾' in SYSTEM
    with pytest.raises(RagError):messages(json.dumps([{'role':'user','content':'bypass'}]))
    assert messages(json.dumps(RagService.messages('q',[],[]),ensure_ascii=False))==RagService.messages('q',[],[])
    assert UNKNOWN=='知识库中未找到相关内容'

def test_literal_env_no_shell_and_no_override(tmp_path,monkeypatch):
    monkeypatch.setenv('LLM_PROVIDER','deepseek');monkeypatch.delenv('OLLAMA_MODEL',raising=False)
    f=tmp_path/'.env';f.write_text('LLM_PROVIDER=ollama\nOLLAMA_MODEL="qwen2.5:7b"\nHOME=evil\n')
    import os
    before=os.environ.get('HOME');load_env(f)
    assert os.environ['LLM_PROVIDER']=='deepseek' and os.environ['OLLAMA_MODEL']=='qwen2.5:7b' and os.environ.get('HOME')==before

def test_rag_dispatch_guard_independent_of_client(rig,monkeypatch):
    rig.grant(['a']);prepared=rig.rag.prepare('test')
    rig.rag.source_library='qichen'
    with pytest.raises(RagError,match='禁止'):rig.rag.answer(prepared['ticket'],True)
    assert rig.provider.requests==[]

def test_route_change_invalidates_confirmed_ticket(rig,monkeypatch):
    rig.grant(['a']);prepared=rig.rag.prepare('test')
    monkeypatch.setenv('LLM_PROVIDER','ollama');rig.rag.client=RoutedClient()
    with pytest.raises(RagError,match='变化'):rig.rag.answer(prepared['ticket'],True)
    assert rig.provider.requests==[]

def test_local_rag_still_requires_source_validation(rig,monkeypatch):
    from app.datasets import LocalRag
    monkeypatch.setenv('LLM_PROVIDER','ollama')
    # The existing rig's service exposes the native store; no real DB or model involved.
    r=LocalRag(rig.rag.store,lambda **kw:None)
    monkeypatch.setattr(r,'can_read',lambda doc:doc['id']=='a')
    assert r.source_library=='qichen' and r.external_allowed({'id':'a'}) and not r.external_allowed({'id':'secret'})

from test_library_api import setup

def test_explicit_provider_choice_is_session_local_and_never_dispatches(monkeypatch):
    monkeypatch.setenv('LLM_PROVIDER','ollama')
    monkeypatch.setattr(OllamaProvider,'health',lambda self:True)
    a,b=RoutedClient(session=True),RoutedClient(session=True)
    with pytest.raises(RagError,match='确认'):a.select_provider('deepseek')
    assert a.name=='ollama'
    a.select_provider('deepseek',True)
    assert a.name=='deepseek' and b.name=='ollama' and not a.configured
    a.set_key('synthetic-session-key')
    assert a.configured
    a.select_provider('ollama')
    assert a.name=='ollama' and b.name=='ollama'
    with pytest.raises(RagError):a.select_provider('unapproved')

@pytest.mark.parametrize('source',['qichen','qichen30','business'])
def test_explicit_qichen_provider_selection_cannot_bypass_guard(source,monkeypatch):
    monkeypatch.setenv('LLM_PROVIDER','ollama');client=RoutedClient(source_library=source)
    with pytest.raises(RagError,match='禁止'):client.select_provider('deepseek',True)
    assert client.name=='ollama'

def test_provider_api_confirms_invalidates_and_isolates_sessions(setup,monkeypatch):
    from app import main
    from httpx import URL
    import hashlib
    c,h,_=setup;c.base_url=URL('https://testserver')
    monkeypatch.setenv('LLM_PROVIDER','ollama');monkeypatch.delenv('DEEPSEEK_API_KEY',raising=False);main.MANAGED_RAG.clear()
    monkeypatch.setattr(OllamaProvider,'health',lambda self:True)
    url='/api/rag/provider'
    assert c.post(url,json={'provider':'deepseek','confirm_external':True}).status_code==401
    for body in [{'provider':'deepseek'},{'provider':'deepseek','confirm_external':False},{'provider':'deepseek','confirm_external':1},{'provider':'other','confirm_external':True}]:
        assert c.post(url,headers=h['rd'],json=body).status_code==422
    assert c.get('/api/rag',headers=h['rd']).json()['provider_switch_supported'] is True
    assert c.get('/api/rag',headers=h['hr']).json()['local'] is True
    service=main.MANAGED_RAG[hashlib.sha256(h['rd']['Authorization'][7:].encode()).hexdigest()]
    for store in [service.tickets,service.drafts,service.receipts]:store['old']={}
    service.sessions['old']={}
    assert c.post(url,headers=h['rd'],json={'provider':'deepseek','confirm_external':True}).status_code==200
    assert all(not store for store in [service.tickets,service.drafts,service.sessions,service.receipts])
    assert c.get('/api/rag',headers=h['rd']).json()['local'] is False
    assert c.get('/api/rag',headers=h['hr']).json()['local'] is True
    service.sessions['working']={'busy':True}
    assert c.post(url,headers=h['rd'],json={'provider':'ollama'}).status_code==409
    assert service.client.name=='deepseek'
    service.sessions.clear()
    assert c.post(url,headers=h['rd'],json={'provider':'ollama'}).status_code==200
    assert service.client.name=='ollama'
    service.source_library='qichen';service.client.source_library='qichen'
    assert c.post(url,headers=h['rd'],json={'provider':'deepseek','confirm_external':True}).status_code==403


def test_fallback_api_requires_explicit_confirmation_and_invalidates_snapshots(setup,monkeypatch):
    from app import main
    from httpx import URL
    import hashlib
    c,h,_=setup;c.base_url=URL('https://testserver')
    monkeypatch.setenv('LLM_PROVIDER','ollama');main.MANAGED_RAG.clear()
    monkeypatch.setattr(OllamaProvider,'health',lambda self:(_ for _ in ()).throw(RagError('offline','offline')))
    assert c.post('/api/rag/fallback',json={'confirm_external_fallback':True}).status_code==401
    for body in [{},{'confirm_external_fallback':False},{'confirm_external_fallback':1}]:
        assert c.post('/api/rag/fallback',headers=h['rd'],json=body).status_code==422
    assert c.get('/api/rag',headers=h['rd']).json()['fallback_available'] is True
    service=main.MANAGED_RAG[hashlib.sha256(h['rd']['Authorization'][7:].encode()).hexdigest()]
    service.tickets['stale']={};service.drafts['stale']={}
    assert c.post('/api/rag/fallback',headers=h['rd'],json={'confirm_external_fallback':True}).status_code==200
    assert not service.tickets and not service.drafts and not service.sessions
    assert c.get('/api/rag',headers=h['rd']).json()['local'] is False

def test_context_budget_rejected_without_io(monkeypatch):
    monkeypatch.setattr('app.llm.local_json',lambda *a,**kw:pytest.fail('must reject before transport'))
    with pytest.raises(RagError,match='容量'):OllamaProvider().generate('汉'*20000)

def test_actual_sdk_serialization_with_memory_transport(monkeypatch):
    pytest.importorskip('openai')
    import httpx
    original=httpx.Client;captured=[]
    def handle(request):
        body=json.loads(request.content);captured.append(body)
        assert str(request.url)=='https://api.deepseek.com/chat/completions'
        assert request.headers['authorization']=='Bearer synthetic-local-key'
        return httpx.Response(200,json={'id':'synthetic','object':'chat.completion','created':0,'model':'deepseek-flash','choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':'{"status":"insufficient_evidence","answer":"知识库中未找到相关内容","citations":[]}'}}]})
    class MemoryClient(original):
        def __init__(self,**kw):super().__init__(transport=httpx.MockTransport(handle),**kw)
    monkeypatch.setattr(httpx,'Client',MemoryClient)
    result=DeepSeekProvider(key='synthetic-local-key').generate('公开虚构资料')
    assert json.loads(result)['status']=='insufficient_evidence' and len(captured)==1
    assert captured[0]['model']=='deepseek-flash'

def test_qichen_local_generation_uses_native_ticket_and_validated_citations(rig,monkeypatch):
    from app.datasets import LocalRag
    monkeypatch.setenv('LLM_PROVIDER','ollama')
    monkeypatch.setattr(OllamaProvider,'health',lambda self:True)
    sent=[]
    def generate(self,prompt):
        sent.append(json.loads(prompt));return json.dumps({'status':'answered','answer':'仅虚构测试结论。[S1]','citations':['S1']},ensure_ascii=False)
    monkeypatch.setattr(OllamaProvider,'generate',generate)
    service=LocalRag(rig.rag.store,lambda **kw:None)
    monkeypatch.setattr(service,'can_read',lambda doc:doc['id']=='a')
    prepared=service.prepare('test')
    result=service.answer(prepared['ticket'],True)
    assert len(sent)==1 and sent[0][0]['content']==SYSTEM
    assert result['answer'].endswith('来源片段：[S1]') and len(result['citations'])==1
    assert 'UNAUTHORIZED_PRIVATE'not in json.dumps(sent)

def test_local_defaults_keep_candidates_and_manual_selection(rig,monkeypatch):
    from test_rag_boundaries import install_ranked_fictional_documents
    monkeypatch.setenv('LLM_PROVIDER','ollama');monkeypatch.setattr(OllamaProvider,'health',lambda self:True)
    install_ranked_fictional_documents(rig,['公开虚构甲。','公开虚构乙。','公开虚构丙。'])
    rig.rag.client=RoutedClient();monkeypatch.setattr(rig.rag,'can_read',lambda doc:True)
    d=rig.rag.draft('虚构问题？')
    assert len(d['candidates'])==3 and len(d['default_candidate_ids'])==3
    assert d['budget']['group_limit']==8 and 'default_group_limit' not in d['budget']
    p=rig.rag.selection(d['draft_id'],0,[c['candidate_id']for c in d['candidates']])
    assert len(p['evidence'])==3 and p['budget']['message_bytes']<=p['budget']['byte_limit']

def test_local_byte_budget_rejects_before_ticket_or_dispatch(rig,monkeypatch):
    from test_rag_boundaries import install_ranked_fictional_documents
    monkeypatch.setenv('LLM_PROVIDER','ollama');monkeypatch.setattr(OllamaProvider,'health',lambda self:True)
    install_ranked_fictional_documents(rig,['虚构甲。'+'甲'*1500,'虚构乙。'+'乙'*1500,'虚构丙。'+'丙'*1500])
    rig.rag.client=RoutedClient();monkeypatch.setattr(rig.rag,'can_read',lambda doc:True)
    d=rig.rag.draft('虚构问题？')
    with pytest.raises(RagError)as e:rig.rag.selection(d['draft_id'],0,[c['candidate_id']for c in d['candidates']])
    assert e.value.code=='evidence_budget_exceeded'
    b=e.value.details['budget'];assert b['message_chars']<b['context_limit'] and b['message_bytes']>b['byte_limit']
    assert not rig.rag.tickets and rig.provider.requests==[]
