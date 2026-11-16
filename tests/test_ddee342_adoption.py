"""Delivery adaptations: synthetic identities and records, no external calls."""
import json,hashlib
from types import SimpleNamespace
import pytest
from app import main,library_api,library_store
from test_library_api import setup


def test_default_closed_without_initialized_permissions(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(main,'DATA',tmp_path);monkeypatch.setattr(main,'DB',tmp_path/'workbench.sqlite3');monkeypatch.setenv('P18_SEMANTIC_ENABLED','0');monkeypatch.delenv('P18_ALLOW_LEGACY_OPEN',raising=False)
    with TestClient(main.app)as c:
        assert c.get('/api/documents').status_code==503
        assert c.get('/api/config').status_code==200
        assert c.post('/api/search',json={'query':'synthetic'}).status_code==503


def test_logged_in_automatic_prepare_is_disabled(setup,monkeypatch):
    c,h,_=setup
    monkeypatch.setattr(main,'rag_call',lambda *a:pytest.fail('automatic prepare must not run'))
    assert c.post('/api/rag/prepare',headers=h['rd'],json={'question':'合成问题'}).status_code==404


def test_upload_cannot_disclose_or_replace_hidden_document(setup,monkeypatch):
    c,h,docs=setup;raw=b'synthetic same file'
    monkeypatch.setattr(main,'POOL',SimpleNamespace(submit=lambda *a:None))
    with main.connect()as conn:
        for d in docs:
            d.update(name=d['id']+'.docx',sha256=hashlib.sha256(raw if d['id']=='secret'else d['id'].encode()).hexdigest(),revision=1)
            conn.execute('UPDATE documents SET body=? WHERE id=?',(json.dumps(d),d['id']))
    r=c.post('/api/documents',headers=h['admin'],files={'files':('secret.docx',raw)},data={'mode':'replace','replace_id':'secret'})
    assert r.status_code==200 and r.json()[0]['status']=='rejected' and 'id'not in r.json()[0]
    r=c.post('/api/documents',headers=h['admin'],files={'files':('secret.docx',raw)})
    assert r.status_code==200 and r.json()[0]['status']=='accepted'
    assert main.get('secret')['state']=='held'


def test_deleted_metadata_cannot_be_read_or_changed(setup):
    c,h,_=setup
    d=main.get('public');d['state']='deleted';d['revision']=1;main.save(d)
    assert c.get('/api/library/documents/public',headers=h['admin']).status_code==404
    assert c.put('/api/library/documents/public',headers=h['admin'],json={'expected_version':1,'code':'A','name':'测试','folder':'公开','department':'研发部','doc_type':'文档','classification':'公开','version':'V1','lifecycle':'现行有效'}).status_code==404


def test_search_rechecks_all_members_and_session(setup,monkeypatch):
    c,h,_=setup
    def search(*a,document_filter=None,**kwargs):
        assert document_filter(main.get('public')) and not document_filter(main.get('secret'))
        # Dedup representative looks public; one member is forbidden.
        return {'results':[{'document_id':'public','members':[{'document_id':'public'},{'document_id':'secret'}]}]}
    monkeypatch.setattr(main,'require_semantic',lambda:SimpleNamespace(search=search))
    assert c.post('/api/search',headers=h['rd'],json={'query':'synthetic'}).json()['results']==[]
    def revoke(*a,**k):
        with main.connect()as conn:conn.execute('UPDATE library_sessions SET expires=0')
        return {'results':[{'document_id':'public'}]}
    monkeypatch.setattr(main,'require_semantic',lambda:SimpleNamespace(search=revoke))
    assert c.post('/api/search',headers=h['rd'],json={'query':'synthetic'}).json()['results']==[]


def test_evidence_visibility_is_scalar_equivalent(setup):
    c,h,docs=setup
    with main.connect()as conn:user=library_store.resolve_session(conn,h['admin']['Authorization'][7:])
    marker=library_api.principal.set(user)
    try:assert library_api.visible_ids(main,docs,evidence=True)=={d['id']for d in docs if library_api.visible(main,d,evidence=True)}
    finally:library_api.principal.reset(marker)
