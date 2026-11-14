import json
import sqlite3
from dataclasses import replace
import pytest
from app import main, library_store, library_api
from app.rag import RagService, RagError
from test_library_api import setup, HEADERS
from test_rag import rig


def test_login_cookie_logout_and_disabled_account(setup):
    c,h,_=setup
    with main.connect() as conn:
        library_store.create_account(conn,'reader','fictional-test-password','研发部员工')
    assert c.post('/api/library/login',json={'username':'reader','password':'wrong'},headers=HEADERS).status_code==401
    # Login cannot bypass the same-origin/client-header protection.
    assert c.post('/api/library/login',json={'username':'reader','password':'fictional-test-password'}).status_code==403
    response=c.post('/api/library/login',json={'username':'reader','password':'fictional-test-password'},headers=HEADERS)
    assert response.status_code==200 and 'HttpOnly' in response.headers['set-cookie'] and 'SameSite=strict' in response.headers['set-cookie']
    assert 'password' not in response.text and 'token' not in response.text
    assert c.get('/api/library/me').json()['identity']=='研发部员工'
    assert c.post('/api/library/logout',headers=HEADERS).status_code==200
    assert c.get('/api/documents').status_code==401
    c.post('/api/library/login',json={'username':'reader','password':'fictional-test-password'},headers=HEADERS)
    with main.connect() as conn:
        conn.execute("UPDATE library_accounts SET active=0 WHERE username='reader'")
    assert c.get('/api/documents').status_code==401
    assert c.get('/login').status_code==200


def test_login_rate_limit(setup):
    c,_,_=setup
    with main.connect() as conn:
        library_store.create_account(conn,'reader','fictional-test-password','研发部员工')
    for _ in range(5):
        assert c.post('/api/library/login',headers=HEADERS,json={'username':'reader','password':'wrong'}).status_code==401
    assert c.post('/api/library/login',headers=HEADERS,json={'username':'reader','password':'fictional-test-password'}).status_code==401


def test_http_rag_pool_separates_sessions_and_tickets(setup,monkeypatch):
    c,h,_=setup
    from types import SimpleNamespace
    monkeypatch.setattr(main,'require_semantic',lambda:SimpleNamespace(search=lambda *a,**kw:{'results':[]}))
    draft=c.post('/api/rag/drafts',headers=h['rd'],json={'question':'测试问题'}).json()
    assert 'draft_id' in draft, draft
    other=c.post('/api/rag/drafts',headers=h['hr'],json={'question':'测试问题','session_id':draft['session_id']})
    assert other.status_code==409 and other.json()['detail']['code']=='session_expired'
    other=c.post('/api/rag/selection',headers=h['hr'],json={'draft_id':draft['draft_id'],'selection_version':0,'candidate_ids':[]})
    assert other.status_code==409
    assert len(main.MANAGED_RAG)==2
    services=list(main.MANAGED_RAG.values())
    services[0].tickets['owner-only']={'at':__import__('time').monotonic()}
    other=c.post('/api/rag/answer',headers=h['hr'],json={'ticket':'owner-only','consent':True})
    assert other.status_code==409 and other.json()['detail']['code']=='ticket_expired'
    assert 'owner-only' in services[0].tickets
    c.post('/api/library/logout',headers=h['rd'])
    assert len(main.MANAGED_RAG)==1


@pytest.fixture
def managed_rig(rig):
    from app.library_policy import LibraryMetadata
    def connect():
        return sqlite3.connect(rig.store.DATA/'workbench.sqlite3')
    rig.store.connect=connect
    with connect() as conn:
        library_store.initialize(conn)
        library_store.enable(conn)
        token=library_store.issue_session(conn,'研发部员工')
        user=library_store.resolve_session(conn,token)
        for key in rig.docs:
            meta=LibraryMetadata(key,key,'研发','研发部','技术文档','内部','V1','现行有效')
            if key=='secret':meta=replace(meta,classification='机密',viewers=('人力资源总监',))
            library_store.write(conn,key,meta,0)
    rig.grant(['a','b','secret'])
    context=library_api.principal.set(user)
    try:yield rig
    finally:library_api.principal.reset(context)


def test_rag_both_lanes_filter_and_revalidate_permission(managed_rig):
    r=managed_rig
    draft=r.rag.draft('项目负责人是谁？')
    assert 'UNAUTHORIZED_PRIVATE' not in json.dumps(draft)
    prepared=r.rag.prepare('项目负责人是谁？')
    with r.store.connect() as conn:
        version,meta=library_store.read(conn,'b')
        library_store.write(conn,'b',replace(meta,department='财务部'),version)
    with pytest.raises(RagError,match='失效'):
        r.rag.answer(prepared['ticket'],True)
    assert not r.provider.requests


def test_confidential_locally_visible_never_sent(managed_rig):
    r=managed_rig
    with r.store.connect() as conn:
        version,meta=library_store.read(conn,'secret')
        library_store.write(conn,'secret',replace(meta,viewers=('研发部员工',)),version)
    draft=r.rag.draft('项目负责人是谁？')
    secret=[x for x in draft['candidates'] if x['evidence']['document_id']=='secret']
    assert secret and not secret[0]['selectable']
    p=r.rag.prepare('项目负责人是谁？')
    r.rag.answer(p['ticket'],True)
    assert 'UNAUTHORIZED_PRIVATE' not in json.dumps(r.provider.requests)


def test_logout_during_provider_call_suppresses_response(managed_rig):
    r=managed_rig
    prepared=r.rag.prepare('项目负责人是谁？')
    def revoke():
        with r.store.connect() as conn:conn.execute('DELETE FROM library_sessions')
    r.provider.hook=revoke
    with pytest.raises(RagError,match='无法撤回'):
        r.rag.answer(prepared['ticket'],True)


def test_history_rejected_after_department_change(managed_rig):
    r=managed_rig
    p=r.rag.prepare('项目负责人是谁？')
    r.rag.answer(p['ticket'],True)
    with r.store.connect() as conn:
        version,meta=library_store.read(conn,'b')
        library_store.write(conn,'b',replace(meta,department='财务部'),version)
    with pytest.raises(RagError,match='历史'):
        r.rag.prepare('那他是谁？',p['session_id'])
    assert len(r.provider.requests)==1


def test_identity_change_invalidates_old_session(setup):
    c,_,_=setup
    with main.connect() as conn:
        library_store.create_account(conn,'reader','fictional-test-password','研发部员工')
    c.post('/api/library/login',headers=HEADERS,json={'username':'reader','password':'fictional-test-password'})
    assert c.get('/api/documents').headers['cache-control']=='no-store'
    with main.connect() as conn:
        conn.execute("UPDATE library_accounts SET identity='财务总监' WHERE username='reader'")
    assert c.get('/api/documents').status_code==401
