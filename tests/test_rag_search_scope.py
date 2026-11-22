"""Candidate-scope protocol tests, not embedding quality experiments."""
from types import SimpleNamespace as NS
import threading

import pytest
from app.semantic import IndexService


@pytest.mark.parametrize('mode',['vector','hybrid','hybrid_dedup'])
def test_search_filters_before_vector_and_lexical_cutoffs_and_rechecks(mode,monkeypatch):
    models=pytest.importorskip('qdrant_client.models')
    docs=[{'id':str(i),'name':str(i)} for i in range(26)]
    def snapshot(identifier):
        doc=docs[int(identifier)]
        chunk={'id':'c'+identifier,'revision':1,'order':1,'text':'负责人 测试 '+identifier,
               'section':'正文','sources':[],'risk':{},'kind':'text','config':{}}
        return {'doc':doc,'token':'v1','chunks':[chunk]}
    service=IndexService.__new__(IndexService)
    service.store=NS(LOCK=threading.RLock(),all_docs=lambda:docs,available=lambda id:docs[int(id)])
    service.snapshot=snapshot;service.read=lambda id:{'status':'complete'}
    service.valid=lambda run,snap:True;service.current_config=lambda:True
    service.point_id=lambda snap,chunk:snap['doc']['id'];service.config={};service.collection='test'
    service.vector_lock=threading.RLock();service.models=models
    service.provider=NS(encode=lambda *args,**kwargs:[[1.0]]) # transport stub, no model-quality claim
    queries=[];revoked=False
    def query_points(collection,**kwargs):
        ids=kwargs['query_filter'].must[0].has_id
        queries.append(ids)
        return NS(points=[NS(id=id,payload={'chunk_id':'c'+id,'token':'v1'},score=0.5) for id in ids[:kwargs['limit']]])
    service.client=NS(query_points=query_points)
    import app.retrieval
    original=app.retrieval.bm25;lexical_scopes=[]
    def lexical(query,records):
        lexical_scopes.append([r['document_id'] for r in records]);return original(query,records)
    monkeypatch.setattr(app.retrieval,'bm25',lexical)
    predicate=lambda doc:doc['id']=='25' and not revoked
    result=service.search('负责人',top_k=20,mode=mode,document_filter=predicate)
    assert [h['document_id'] for h in result['results']]==['25']
    assert all(ids==['25'] for ids in queries)
    if mode!='vector':assert lexical_scopes==[['25']]
    def revoke_during_query(collection,**kwargs):
        nonlocal revoked
        hits=query_points(collection,**kwargs);revoked=True;return hits
    service.client.query_points=revoke_during_query
    assert service.search('负责人',top_k=20,mode=mode,document_filter=predicate)['results']==[]
    # Optional filter must not change the unscoped knowledge-search behavior.
    assert len(service.search('负责人',top_k=20,mode=mode)['results'])==20
    service.client.query_points=query_points
    chunk_filter=lambda chunk:chunk['text'].endswith(' 测试 25')
    exact=service.search('负责人',top_k=1,mode=mode,chunk_filter=chunk_filter)
    assert [hit['document_id'] for hit in exact['results']]==['25']
    before=len(queries)
    denied=service.search('负责人',top_k=1,mode=mode,
                          document_filter=lambda doc:doc['id']!='25',chunk_filter=chunk_filter)
    assert denied['status']=='no_results' and denied['results']==[]
    assert len(queries)==before
