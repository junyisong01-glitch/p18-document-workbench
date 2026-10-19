"""Guarded source reads use fictional snapshots and temporary files only."""
from copy import deepcopy
import pytest
from app import main
from test_workbench import client, upload, wait

@pytest.fixture
def source_fixture(client,monkeypatch):
    from types import SimpleNamespace
    d=wait(client,upload(client)['id']);chunk={'id':'fictional-chunk','text':'fixture evidence'}
    state={'token':'fixture-token','current':True,'complete':True}
    service=SimpleNamespace(snapshot=lambda i:{'doc':main.get(i),'token':state['token'],'chunks':[chunk]},
      read=lambda i:{'status':'complete' if state['complete'] else 'failed'},
      valid=lambda r,s:state['current'],current_config=lambda:state['current'])
    monkeypatch.setattr(main,'require_semantic',lambda:service)
    params={'revision':d['revision'],'index_token':'fixture-token','chunk_id':chunk['id']}
    return client,d,chunk,state,params

def test_guarded_source_returns_current_canonical_chunk(source_fixture,monkeypatch):
    c,d,chunk,state,p=source_fixture
    # public() uses actual document metadata, source guard uses controlled index snapshot.
    r=c.get('/api/documents/'+d['id']+'/source',params=p)
    assert r.status_code==200 and r.json()['source']==chunk
    assert c.get('/api/documents/'+d['id']+'/preview/original/meta',params=p).status_code==200
    assert c.get('/api/documents/'+d['id']+'/preview/original/1',params=p).status_code==200
    assert c.get('/api/documents/'+d['id']+'/file/original',params=p).status_code==200

@pytest.mark.parametrize('change',['revision','token','chunk','config','failed'])
def test_stale_source_blocks_text_preview_and_download(source_fixture,change):
    c,d,chunk,state,p=source_fixture
    if change=='revision':p['revision']+=1
    if change=='token':p['index_token']='wrong'
    if change=='chunk':p['chunk_id']='other'
    if change=='config':state['current']=False
    if change=='failed':state['complete']=False
    for suffix in ['/source','/preview/original/meta','/preview/original/1','/file/original']:
        r=c.get('/api/documents/'+d['id']+suffix,params=p)
        assert r.status_code==409 and r.json()['detail']['code']=='source_stale'

def test_partial_identity_and_legacy_preview(source_fixture):
    c,d,chunk,state,p=source_fixture
    assert c.get('/api/documents/'+d['id']+'/preview/original/meta').status_code==200
    assert c.get('/api/documents/'+d['id']+'/preview/original/meta',params={'revision':d['revision']}).status_code==200
    assert c.get('/api/documents/'+d['id']+'/preview/original/meta',params={'chunk_id':chunk['id']}).status_code==409
