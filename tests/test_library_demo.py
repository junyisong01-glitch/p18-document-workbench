from test_library_api import setup,HEADERS
from app import main,library_store


def enable_demo(monkeypatch):
    monkeypatch.setenv('P18_LIBRARY_DEMO','1')
    with main.connect() as conn:conn.execute("INSERT OR REPLACE INTO library_settings VALUES ('demo','1')")


def test_demo_requires_both_switches_and_never_manager(setup,monkeypatch):
    c,h,_=setup
    assert c.post('/api/library/demo-session',headers=HEADERS,json={'identity':'总经理'}).status_code==404
    monkeypatch.setenv('P18_LIBRARY_DEMO','1')
    assert c.post('/api/library/demo-session',headers=HEADERS,json={'identity':'总经理'}).status_code==404
    enable_demo(monkeypatch)
    assert c.get('/demo').status_code==200
    r=c.post('/api/library/demo-session',headers=HEADERS,json={'identity':'总经理'})
    assert r.status_code==200 and r.json()['manager'] is False
    assert c.post('/api/library/catalog/folders',headers=HEADERS,json={'name':'x'}).status_code==200
    assert any(f['name']=='x' for f in c.get('/api/library/catalog/folders').json())
    assert c.delete('/api/documents/public',headers=HEADERS).status_code==403
    assert c.post('/api/library/catalog/types',headers=HEADERS,json={'name':'x'}).status_code==403
    assert c.get('/api/documents/secret').status_code==404
    assert c.post('/api/library/demo-session',headers=HEADERS,json={'identity':'人力资源总监','manager':True}).status_code==422
    monkeypatch.delenv('P18_LIBRARY_DEMO')
    assert c.get('/api/library/me').status_code==401


def test_switch_revokes_previous_session_and_rag(setup,monkeypatch):
    c,h,_=setup
    enable_demo(monkeypatch)
    assert c.post('/api/library/demo-session',headers=HEADERS,json={'identity':'人力资源总监'}).status_code==200
    old=c.cookies.get('p18_session')
    with main.connect() as conn:digest=library_store.resolve_session(conn,old)['session_digest']
    main.MANAGED_RAG[digest]=object()
    assert c.get('/api/documents/secret').status_code==200
    assert c.post('/api/library/demo-session',headers=HEADERS,json={'identity':'研发部员工'}).status_code==200
    assert digest not in main.MANAGED_RAG
    assert c.get('/api/library/me',headers={'Authorization':'Bearer '+old}).status_code==401
    assert c.get('/api/documents/secret').status_code==404


def test_demo_upload_still_checks_visibility(setup,monkeypatch):
    import json
    from test_workbench import pdf_bytes
    c,_,_=setup
    enable_demo(monkeypatch)
    c.post('/api/library/demo-session',headers=HEADERS,json={'identity':'研发部员工'})
    with main.connect() as conn:conn.execute('DELETE FROM documents')
    meta=dict(expected_version=0,code='DEMO',name='演示资料',folder='平台项目',department='财务部',doc_type='报告',classification='内部',version='V1',lifecycle='现行有效',viewers=[])
    def upload():return c.post('/api/library/upload',headers=HEADERS,data={'metadata_json':json.dumps(meta)},files={'file':('demo.pdf',pdf_bytes())})
    assert upload().status_code==422
    meta['department']='研发部'
    assert upload().status_code==200
