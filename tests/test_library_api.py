import json
from dataclasses import asdict
from unittest.mock import Mock
import pytest
from fastapi.testclient import TestClient
from app import main, library_store
from app.library_policy import LibraryMetadata

HEADERS = {'X-P18-Client': 'workbench'}

@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DATA', tmp_path)
    monkeypatch.setattr(main, 'DB', tmp_path / 'workbench.sqlite3')
    monkeypatch.setenv('P18_SEMANTIC_ENABLED', '0')
    monkeypatch.setattr(main, 'public', lambda d, *a: d)
    with TestClient(main.app) as client:
        docs = [dict(id='public', state='held', created_at='1'), dict(id='secret', state='held', created_at='2'), dict(id='archive', state='held', created_at='3'), dict(id='unclassified', state='held', created_at='4')]
        with main.connect() as conn:
            for d in docs:
                conn.execute('INSERT INTO documents VALUES (?,?)', (d['id'], json.dumps(d)))
            library_store.enable(conn)
            meta = LibraryMetadata('A','测试','公共制度','人力资源部','制度','公开','V1','现行有效')
            library_store.write(conn, 'public', meta, 0)
            secret = LibraryMetadata('B','薪资','人力资源','人力资源部','报表','机密','V1','现行有效',('人力资源总监',))
            library_store.write(conn, 'secret', secret, 0)
            archive = LibraryMetadata('A','旧版','已废止','人力资源部','制度','公开','V0','已废止')
            library_store.write(conn, 'archive', archive, 0)
            tokens = {name: library_store.issue_session(conn, identity, manager=manager) for name,identity,manager in [('rd','研发部员工',False),('hr','人力资源总监',False),('admin','总经理',True)]}
        yield client, {k:dict(HEADERS, Authorization='Bearer '+v) for k,v in tokens.items()}, docs


def test_auth_cannot_be_replaced_by_role_header(setup):
    client,headers,_ = setup
    assert client.get('/api/documents', headers={'X-P18-Identity':'gm'}).status_code == 401
    assert client.get('/api/library/me', headers=headers['rd']).json() == {'identity':'研发部员工','manager':False}


def test_list_and_all_direct_document_routes_deny(setup):
    c,h,_ = setup
    assert {d['id'] for d in c.get('/api/documents',headers=h['rd']).json()} == {'public','archive'}
    assert 'secret' in {d['id'] for d in c.get('/api/documents',headers=h['hr']).json()}
    for suffix in ['', '/chunks','/index','/file/original','/preview/original/meta','/preview/original/1','/source?revision=1&index_token=x&chunk_id=y','/source/highlight?revision=1&index_token=x&chunk_id=y']:
        assert c.get('/api/documents/secret'+suffix,headers=h['rd']).status_code == 404
    assert c.get('/api/library/documents/secret',headers=h['rd']).status_code == 404
    assert c.get('/api/library/documents/secret/preview',headers=h['rd']).status_code == 404


def test_viewer_cannot_mutate_or_grant(setup):
    c,h,_=setup
    for path in ['/api/documents/secret/external-permission','/api/documents/public/reparse','/api/documents']:
        assert c.post(path,headers=h['rd'],json={}).status_code == 403
    assert c.delete('/api/documents/public',headers=h['rd']).status_code == 403


def test_metadata_persistence_and_conflict(setup):
    c,h,_=setup
    response=c.get('/api/library/documents/public',headers=h['admin']).json()
    body=dict(response['metadata'], expected_version=response['version'],folder='新文件夹')
    assert c.put('/api/library/documents/public',headers=h['admin'],json=body).status_code == 200
    assert c.put('/api/library/documents/public',headers=h['admin'],json=body).status_code == 409
    with main.connect() as conn:
        _,meta=library_store.read(conn,'public')
        assert meta.folder=='新文件夹' and meta.department=='人力资源部'
    body['expected_version']=2
    body['classification']='内部'
    assert c.put('/api/library/documents/public',headers=h['admin'],json=body).status_code == 200
    assert c.get('/api/library/documents/public',headers=h['rd']).status_code == 404


def test_search_filters_before_selection(setup,monkeypatch):
    c,h,docs=setup
    service=Mock()
    service.search.side_effect=lambda *a,**kw: {'ids':[d['id'] for d in docs if kw['document_filter'](d)]}
    monkeypatch.setattr(main,'require_semantic',lambda:service)
    assert c.post('/api/search',headers=h['rd'],json={'query':'测试'}).json()['ids']==['public']
    assert c.post('/api/search',headers=h['rd'],json={'query':'测试','document_id':'secret'}).status_code==404


def test_rag_requires_valid_session(setup):
    c,h,_=setup
    assert c.post('/api/rag/answer',headers=h['rd'],json={'ticket':'unknown','consent':True}).status_code==409
    with main.connect() as conn:
        conn.execute('UPDATE library_sessions SET expires=0')
    assert c.get('/api/documents',headers=h['rd']).status_code==401


def test_unclassified_not_searchable_and_confidential_not_external(setup):
    c,h,_=setup
    assert c.post('/api/documents/unclassified/external-permission',headers=h['admin'],json={}).status_code==403
    # Even a manager gets no implicit content access to a confidential document.
    assert c.get('/api/documents/secret',headers=h['admin']).status_code==404


@pytest.mark.parametrize('identity,manager', [('研发部员工', False), ('人力资源总监', False), ('总经理', True)])
def test_visible_ids_matches_per_document_decisions(setup, identity, manager):
    import hashlib
    from app import library_api
    client, headers, _ = setup
    with main.connect() as conn:
        token = library_store.issue_session(conn, identity, manager=manager)
    digest = hashlib.sha256(token.encode()).hexdigest()
    user = {'identity': identity, 'manager': manager, 'session_digest': digest,
            'demo': False, 'expires': 0}
    marker = library_api.principal.set(user)
    try:
        candidates = list(main.all_docs())
        expected = {doc['id'] for doc in candidates if library_api.visible(main, doc)}
        assert library_api.visible_ids(main, candidates) == expected
    finally:
        library_api.principal.reset(marker)
