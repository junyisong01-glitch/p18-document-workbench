"""Synthetic/offline cache and RAG diagnostics, not model-quality evaluations."""
from types import SimpleNamespace
import threading
import pytest
from app import semantic, library_api
from app.semantic import IndexService
from app.rag import RagError
from test_rag import rig
from test_external_permission import grant_rig


def service():
    s=IndexService.__new__(IndexService);s.config_hash='synthetic-config';s.config={'dimension':2};s._init_query_cache();calls=[]
    def encode(texts,query):calls.append((texts,query));return [[1.0,0.0]]
    s.provider=SimpleNamespace(encode=encode)
    return s,calls


def test_cache_reuses_vector_not_mutable_callers(monkeypatch):
    monkeypatch.setenv('P18_QUERY_VECTOR_CACHE','1');s,calls=service()
    a=s._query_vector('fixture');a[0]=99
    assert s._query_vector('fixture')==[1.0,0.0] and len(calls)==1


def test_cache_expiry_and_config_boundary(monkeypatch):
    monkeypatch.setenv('P18_QUERY_VECTOR_CACHE','1');clock=[0];monkeypatch.setattr(semantic.time,'monotonic',lambda:clock[0]);s,calls=service()
    s._query_vector('fixture');clock[0]=301;s._query_vector('fixture');s.config_hash='different-model';s._query_vector('fixture')
    assert len(calls)==3


def test_cache_disabled_and_instances_are_isolated(monkeypatch):
    s,calls=service();t,other=service();s._query_vector('fixture');t._query_vector('fixture')
    assert len(calls)==len(other)==1
    monkeypatch.setenv('P18_QUERY_VECTOR_CACHE','0');s._query_vector('fixture');s._query_vector('fixture');assert len(calls)==3


def test_failed_encode_is_not_cached_and_cache_is_bounded():
    s,calls=service();real=s.provider.encode
    def fail(*a,**k):raise ValueError('synthetic failure')
    s.provider.encode=fail
    with pytest.raises(ValueError):s._query_vector('fixture')
    assert not s._query_cache
    s.provider.encode=real;s.QUERY_CACHE_LIMIT=3
    for i in range(5):s._query_vector(str(i))
    assert len(s._query_cache)==3


def test_repeated_search_rechecks_permissions_and_source(monkeypatch):
    # A real search invocation with a controlled synthetic vector backend.
    s,calls=service();allowed=[True];revision=[1]
    s.store=SimpleNamespace(LOCK=threading.RLock());s.current_config=lambda:True;s.vector_lock=threading.RLock();s.collection='fake'
    snap={'doc':{'id':'a','name':'fixture.docx','revision':1},'token':'t'}
    chunk={'id':'c','order':1,'text':'fixture','section':'s','sources':[],'kind':'text','risk':{},'chunk_config_hash':'c','config':{},'revision':1}
    def candidates(identifier=None,document_filter=None):
        doc=snap['doc'];doc['revision']=revision[0];chunk['revision']=revision[0]
        return {'p':(snap,chunk)} if allowed[0] and(not document_filter or document_filter(doc))else {}
    s.candidates=candidates
    s.client=SimpleNamespace(query_points=lambda *a,**k:SimpleNamespace(points=[SimpleNamespace(id='p',score=1.0,payload={'chunk_id':'c','token':'t'})]))
    # Supply the native model-types filter objects used by IndexService.search.
    from qdrant_client import models
    s.models=models
    first=s.search('fixture',mode='vector');second=s.search('fixture',mode='vector');assert first==second and len(calls)==1
    allowed[0]=False;assert not s.search('fixture',mode='vector')['results']
    allowed[0]=True;revision[0]=2;third=s.search('fixture',mode='vector');assert third['results'][0]['revision']==2 and len(calls)==1


def test_readonly_index_uses_cache_without_writing_vectors(tmp_path):
    from app.read_only_index import ReadOnlyIndex
    from app.chunking import digest
    from qdrant_client import QdrantClient,models
    import hashlib
    cfg={'dimension':2};collection='p18_'+digest(cfg);data=tmp_path/'data';client=QdrantClient(path=str(data/'qdrant'));client.create_collection(collection,vectors_config=models.VectorParams(size=2,distance=models.Distance.COSINE));client.close()
    before={str(p.relative_to(data)):hashlib.sha256(p.read_bytes()).hexdigest()for p in data.rglob('*')if p.is_file()}
    calls=[];provider=SimpleNamespace(config=cfg,encode=lambda t,query:(calls.append(t)or [[1.0,0.0]]));index=ReadOnlyIndex(SimpleNamespace(DATA=data),provider)
    try:assert index._query_vector('fixture')==index._query_vector('fixture') and len(calls)==1
    finally:index.close()
    assert before=={str(p.relative_to(data)):hashlib.sha256(p.read_bytes()).hexdigest()for p in data.rglob('*')if p.is_file()}


def test_policy_explanation_does_not_make_candidate_sendable(rig,monkeypatch):
    grant_rig(rig);monkeypatch.setattr(rig.rag,'external_allowed',lambda d:False)
    # Authenticated local lane still offers readable candidates, never selectable.
    token=library_api.principal.set({'identity':'fictional'})
    monkeypatch.setattr(library_api,'visible',lambda *a,**k:True)
    try:
        draft=rig.rag.draft('虚构问题');approved=[c for c in draft['candidates']if c['evidence']['document_id']in {'a','b'}]
        assert approved and all(not c['selectable'] and c['permission_reason']=='deployment_policy'for c in approved)
        assert not draft['default_candidate_ids'] and not rig.provider.requests
    finally:library_api.principal.reset(token)


def test_budget_diagnostic_keeps_default_selection_and_never_truncates(rig,monkeypatch):
    grant_rig(rig);monkeypatch.setenv('P18_RAG_CONTEXT_CHARS','2000');rig.chunks['a']['text']='界'*4000
    draft=rig.rag.draft('虚构问题');assert draft['budget_skipped']>0
    excluded=[c for c in draft['candidates']if c.get('default_reason')=='context_limit'];assert excluded and excluded[0]['evidence']['text']=='界'*4000
    p=rig.rag.prepare('虚构问题');assert p['budget_skipped']>0 and all(e['document_id']!='a'for e in p['evidence'])
    assert not rig.provider.requests
