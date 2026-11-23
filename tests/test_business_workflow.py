"""Isolated workflow tests: fake technical index, real SQLite/auth/HTTP guards.
Actual parsing/embedding/browser verification is a separate local acceptance.
"""
import importlib.util,sys,json,uuid,sqlite3,threading
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from app import library_store,business,business_roles
from app.library_policy import LibraryMetadata

@pytest.fixture
def rig(tmp_path,monkeypatch):
    root=Path(__file__).resolve().parents[1]
    spec=importlib.util.spec_from_file_location('app._test_business',root/'app/main.py');q=importlib.util.module_from_spec(spec);sys.modules[spec.name]=q;spec.loader.exec_module(q)
    q.DATA=tmp_path;q.DB=tmp_path/'workbench.sqlite3';q.initialize()
    with q.connect()as c:
        library_store.enable(c);business_roles.initialize(c)
        for name,identity,role,dept,job in [('boss','总经理','boss','管理层',''),('rd','启辰研发岗位','employee','研发部','研发'),('qa','启辰测试岗位','employee','研发部','测试'),('ops','启辰运维岗位','employee','研发部','运维'),('head','研发部员工','supervisor','研发部',''),('prd','启辰生产岗位','employee','生产制造部','生产'),('otherhead','生产制造部员工','supervisor','生产制造部',''),('guest','行政安全部员工','guest','','')]:
            library_store.create_account(c,name,'synthetic-password-123',identity,manager=name=='boss');business_roles.assign(c,name,role,dept,job);c.execute('UPDATE business_profiles SET is_demo=1 WHERE username=?',(name,))
    monkeypatch.setenv('P18_SEMANTIC_ENABLED','0')
    index_states={}
    q.index_status=lambda identifier:dict(index_states.get(identifier,{'status':'complete','searchable':True}))
    q.public=lambda d,detailed=False:{'id':d['id'],'index':{},'build':{},'external_permission':{}}
    scheduled=[];q.schedule_chunks=lambda d,retry_failed=False:scheduled.append(d['id'])
    ids=[]
    def create(owner='rd',dept='研发部',status='published',restricted=False,legacy=False):
        identifier=str(uuid.uuid4());d=dict(id=identifier,name='虚构样例.docx',ext='.docx',state='ready',created_at='1',revision=1,result={'blocks':[]},sha256='synthetic')
        meta=LibraryMetadata('SAMPLE','虚构样例',dept,dept,'文档','内部','V1','现行有效')
        b=dict(version=0,owner=owner,department=dept,series=identifier,status=status,archived=False,deleted=False,company_public=False,restricted=restricted,legacy=legacy,replaces=None)
        with q.connect()as c:
            c.execute('INSERT INTO documents VALUES (?,?)',(identifier,json.dumps(d)));library_store.write(c,identifier,meta,0)
            c.execute('INSERT INTO business_documents VALUES (?,?)',(identifier,json.dumps(b)))
        ids.append(identifier);return identifier
    business.install(q,q,{})
    async def upload(files,mode,replace_id):
        id=create(status='submitted')
        with q.connect()as conn:
            conn.execute('DELETE FROM library_metadata WHERE document_id=?',(id,));conn.execute('DELETE FROM business_documents WHERE document_id=?',(id,))
        return [{'id':id,'status':'accepted'}]
    q.upload=upload
    c=TestClient(q.app,base_url='http://127.0.0.1')
    headers={}
    for name in ['boss','rd','qa','ops','head','prd','otherhead','guest']:
        with q.connect()as conn:token=library_store.login(conn,name,'synthetic-password-123')
        headers[name]={'Authorization':'Bearer '+token,'X-P18-Client':'workbench'}
    def action(id,name,a,**kw):
        b=q.business_read(id)
        return c.post('/api/business/documents/'+id+'/action',headers=headers[name],json={'action':a,'expected':b['version'],**kw})
    yield SimpleNamespace(q=q,c=c,h=headers,create=create,action=action,scheduled=scheduled,index_states=index_states)
    c.close();q.POOL.shutdown(wait=True)

def test_pending_scope_and_direct_routes(rig):
    r=rig;id=r.create(status='submitted')
    for who in ['rd','head','boss']:assert r.c.get('/api/documents/'+id,headers=r.h[who]).status_code==200
    for who in ['qa','prd','otherhead','guest']:
        for suffix in ['', '/chunks','/file/original','/preview/original/1','/source?revision=1&index_token=x&chunk_id=y']:
            assert r.c.get('/api/documents/'+id+suffix,headers=r.h[who]).status_code==404
    for who in ['rd','head','boss']:
        from app.library_api import principal
        with r.q.connect()as c:u=library_store.session_by_digest(c,__import__('hashlib').sha256(r.h[who]['Authorization'][7:].encode()).hexdigest())
        assert not r.q.authorize_document(r.q.get(id),u,evidence=True)

def test_scoped_manager_self_approval_no_cross_department_and_publication(rig):
    r=rig;id=r.create(status='submitted')
    assert r.action(id,'rd','approve').status_code==403
    assert r.action(id,'otherhead','approve').status_code in {403,404}
    assert r.action(id,'head','publish').status_code==409
    assert r.action(id,'head','approve').status_code==200 and id in r.scheduled
    assert r.c.get('/api/documents/'+id,headers=r.h['qa']).status_code==404
    assert r.action(id,'head','publish').status_code==200
    assert r.c.get('/api/documents/'+id,headers=r.h['qa']).status_code==200
    own=r.create(owner='head',status='submitted');assert r.action(own,'head','approve').status_code==200
    assert r.action(own,'head','publish').status_code==200
    boss_own=r.create(owner='boss',status='submitted');assert r.action(boss_own,'boss','approve').status_code==200

def test_grants_public_guest_and_revocation(rig):
    r=rig;id=r.create()
    assert r.c.get('/api/documents/'+id,headers=r.h['prd']).status_code==404
    assert r.action(id,'head','make_public').status_code==403
    assert r.action(id,'head','share',username='prd').status_code==200
    assert r.c.get('/api/documents/'+id,headers=r.h['prd']).status_code==200
    assert r.action(id,'head','revoke_share',username='prd').status_code==200
    assert r.c.get('/api/documents/'+id,headers=r.h['prd']).status_code==404
    assert r.action(id,'head','share',username='guest').status_code==403
    assert r.c.get('/api/documents/'+id,headers=r.h['guest']).status_code==404
    assert r.action(id,'boss','make_public').status_code==200
    assert r.c.get('/api/documents/'+id,headers=r.h['guest']).status_code==200
    assert r.c.get('/api/documents/'+id,headers=r.h['prd']).status_code==200
    assert r.action(id,'boss','revoke_public').status_code==200
    assert r.c.get('/api/documents/'+id,headers=r.h['prd']).status_code==404


def test_compound_qa_respects_publication_grant_revocation_and_archive(rig, monkeypatch):
    from app.external_model import QuestionOnlyRag
    from app.library_api import principal
    from app.llm import RoutedClient

    r = rig
    monkeypatch.setenv('LLM_PROVIDER', 'ollama')
    monkeypatch.setattr(RoutedClient, 'configured', property(lambda _: False))
    monkeypatch.setattr(RoutedClient, 'complete', lambda *_: pytest.fail('结构化回答应直接核对原文'))
    records = {}

    def evidence(name, text, **kwargs):
        identifier = r.create(**kwargs)
        doc = r.q.get(identifier)
        doc['name'] = name
        r.q.save(doc)
        folder = r.q.folder_for(identifier)
        folder.mkdir(parents=True)
        (folder/'original.docx').write_bytes(b'fictional source')
        records[identifier] = dict(document_id=identifier, document_name=name, chunk_id='chunk-'+identifier,
                                   revision=1, index_token='index-'+identifier, text=text,
                                   section='合成测试正文', sources=[{'block_id':'p1'}], risk={})
        return identifier

    arch = evidence('设备总体架构.docx', '状态每 24 秒上报一次。')
    private = evidence('设备离线排查手册.docx', '持续离线达到 9 分钟仍未恢复时提交 IT 工单。', status='submitted')
    assert r.action(arch, 'boss', 'make_public').status_code == 200
    monitored = []

    def search(query, top_k, document_filter):
        visible = {identifier for identifier in records if document_filter(r.q.get(identifier))}
        monitored.append((query, visible))
        return {'status':'ok', 'results':[value for identifier, value in records.items() if identifier in visible]}

    def snapshot(identifier):
        record = records[identifier]
        return {'token':record['index_token'], 'chunks':[dict(record,id=record['chunk_id'])]}

    r.q.require_semantic = lambda: SimpleNamespace(search=search, snapshot=snapshot, read=lambda _: {'status':'complete'},
                                                   valid=lambda run, snap: bool(run and snap), current_config=lambda: True)
    services = {}

    def current_rag():
        user = principal.get()['username']
        if user not in services:
            services[user] = QuestionOnlyRag(r.q,r.q)
        return services[user]

    r.q.current_rag = current_rag
    question = '状态上报间隔是多少，持续离线多久转工单？'
    locator = {k:records[private][k] for k in ('revision','index_token','chunk_id')}

    def prepare(who, allowed):
        monitored.clear()
        response = r.c.post('/api/rag/drafts', headers=r.h[who], json={'question':question})
        assert response.status_code == 200, response.text
        draft = response.json()
        assert len({query for query, _ in monitored}) == 3
        assert all(visible == allowed for _, visible in monitored)
        assert {e['evidence']['document_id'] for e in draft['candidates']} == allowed
        response = r.c.post('/api/rag/selection', headers=r.h[who], json={
            'draft_id':draft['draft_id'], 'selection_version':draft['selection_version'],
            'candidate_ids':draft['default_candidate_ids']})
        assert response.status_code == 200, response.text
        assert response.json()['configured'] is True
        return response.json()['ticket']

    def answer(who, ticket):
        return r.c.post('/api/rag/answer', headers=r.h[who], json={'ticket':ticket,'consent':True})

    def verify(who, allowed, original_visible):
        response = answer(who, prepare(who, allowed))
        assert response.status_code == 200, response.text
        result = response.json()
        assert result['provider'] == '本地证据核对'
        assert result['answer_status'] == ('answered' if private in allowed else 'partial')
        assert ('9 分钟' in result['answer']) == (private in allowed)
        assert {source['document_id'] for source in result['citations']} == allowed
        for endpoint in ('source','file/original'):
            original = r.c.get(f'/api/documents/{private}/{endpoint}', headers=r.h[who], params=locator)
            assert original.status_code == (200 if original_visible else 404)

    for who in ('rd','prd','guest'):
        verify(who, {arch}, who == 'rd')
    assert r.action(private, 'head', 'approve').status_code == 200
    verify('rd', {arch}, True)
    assert r.action(private, 'head', 'publish').status_code == 200
    verify('rd', {arch,private}, True)
    for who in ('prd','guest'):
        verify(who, {arch}, False)
    assert r.action(private, 'head', 'share', username='prd').status_code == 200
    verify('prd', {arch,private}, True)
    verify('guest', {arch}, False)
    ticket = prepare('prd', {arch,private})
    assert r.action(private, 'head', 'revoke_share', username='prd').status_code == 200
    stale = answer('prd', ticket)
    assert stale.status_code == 409 and stale.json()['detail']['code'] == 'evidence_stale'
    verify('prd', {arch}, False)
    assert r.action(private, 'head', 'archive').status_code == 200
    verify('rd', {arch}, True)
    verify('guest', {arch}, False)

def test_native_mutations_and_external_egress_are_blocked(rig):
    r=rig;id=r.create()
    for name in r.h:
        for path in ['/api/rag/answer','/api/library/upload','/api/documents/'+id+'/reparse','/api/documents/'+id+'/external-permission']:
            assert r.c.post(path,headers=r.h[name],json={}).status_code==403
        assert r.c.delete('/api/documents/'+id,headers=r.h[name]).status_code==403

def test_archive_trash_and_stale_actions(rig):
    r=rig;id=r.create()
    assert r.action(id,'rd','trash').status_code==403
    assert r.action(id,'head','archive').status_code==200
    assert r.action(id,'head','trash').status_code==200
    assert r.c.get('/api/documents/'+id,headers=r.h['rd']).status_code==404
    assert r.action(id,'head','purge',confirm=id).status_code==403
    assert r.action(id,'head','restore').status_code==200
    assert r.c.post('/api/business/documents/'+id+'/action',headers=r.h['boss'],json={'action':'make_public','expected':0}).status_code==409

def test_unique_boss_and_revoked_profile_sessions(rig):
    r=rig
    with r.q.connect()as c:
        with pytest.raises(sqlite3.IntegrityError):business_roles.assign(c,'rd','boss','管理层')
    with r.q.connect()as c:business_roles.assign(c,'rd','employee','财务部')
    assert r.c.get('/api/business/documents',headers=r.h['rd']).status_code==401

def test_upload_does_not_allow_forged_department_public_or_guest(rig):
    r=rig
    m={'name':'虚构','code':'X','version':'V1','department':'研发部','classification':'内部'}
    def upload(who,data):return r.c.post('/api/business/upload',headers=r.h[who],files={'file':('sample.docx',b'synthetic')},data={'metadata_json':json.dumps(data)})
    assert upload('rd',{**m,'department':'财务部'}).status_code==422
    assert upload('rd',{**m,'classification':'公开'}).status_code==422
    assert upload('guest',m).status_code==403
    response=upload('rd',m);assert response.status_code==200
    assert response.json()['workflow']['owner']=='rd' and response.json()['workflow']['status']=='published'

def test_returned_submission_can_be_corrected_without_overwriting_original(rig):
    r=rig;old=r.create(status='submitted')
    assert r.action(old,'head','return',note='请提交修订版本').status_code==200
    body={'name':'虚构修订','code':'SAMPLE','version':'V2','department':'研发部','classification':'内部','replaces':old}
    response=r.c.post('/api/business/upload',headers=r.h['rd'],files={'file':('same.docx',b'fictional-revision')},data={'metadata_json':json.dumps(body)})
    assert response.status_code==200,response.text
    new=response.json()['id']
    assert r.q.business_read(old)['archived']and r.q.business_read(old)['status']=='withdrawn'
    assert r.q.get(old)['state']=='ready' and r.q.business_read(new)['status']=='published'
    assert r.q.business_read(new)['series']==r.q.business_read(old)['series']

def test_new_version_switch_is_atomic_and_old_source_record_remains(rig):
    r=rig;old=r.create()
    body={'name':'虚构V2','code':'SAMPLE','version':'V2','department':'研发部','replaces':old}
    response=r.c.post('/api/business/upload',headers=r.h['rd'],files={'file':('same.docx',b'fictional-v2')},data={'metadata_json':json.dumps(body)})
    assert response.status_code==200,response.text
    new=response.json()['id'];assert r.q.business_read(new)['status']=='published'
    assert r.q.business_read(old)['archived'] and not r.q.business_read(new)['archived']
    assert r.q.get(old)['state']=='ready'

def test_changed_source_after_approval_cannot_be_published(rig):
    r=rig;id=r.create(status='submitted')
    assert r.action(id,'head','approve').status_code==200
    d=r.q.get(id);d['revision']+=1
    with r.q.connect()as c:c.execute('UPDATE documents SET body=? WHERE id=?',(json.dumps(d),id))
    assert r.action(id,'head','publish').status_code==409
    assert r.q.business_read(id)['status']=='approved'

def test_boss_purge_cleans_document_tables_and_leaves_audit(rig):
    r=rig;id=r.create()
    folder=r.q.folder_for(id);folder.mkdir(parents=True);(folder/'original.docx').write_bytes(b'fictional')
    assert r.action(id,'head','trash').status_code==200
    assert r.action(id,'boss','purge',confirm='wrong').status_code==403
    response=r.action(id,'boss','purge',confirm=id);assert response.status_code==200,response.text
    assert not folder.exists()
    with r.q.connect()as c:
        assert not c.execute('SELECT 1 FROM library_metadata WHERE document_id=?',(id,)).fetchone()
        assert c.execute("SELECT 1 FROM business_events WHERE document_id=? AND action='purged'",(id,)).fetchone()
    assert r.c.get('/api/documents/'+id,headers=r.h['boss']).status_code==404


def test_demo_shortcuts_are_explicit_local_only_and_boss_requires_password(rig):
    r=rig;r.q.MANAGED_RAG={};business_roles.install_api(r.q)
    flag=r.q.DATA/'business-demo-enabled.json'
    with TestClient(r.q.app,base_url='http://127.0.0.1',client=('127.0.0.1',51000))as local:
        assert local.get('/api/library/demo-accounts').json()==[]
        flag.write_text('{"enabled":true}')
        accounts=local.get('/api/library/demo-accounts').json()
        assert next(a for a in accounts if a['username']=='boss')['password_required']
        assert all(set(a)=={'username','role','department','job','password_required'}for a in accounts)
        assert local.post('/api/library/demo-login',headers={'X-P18-Client':'workbench'},json={'username':'boss'}).status_code==403
        assert local.post('/api/library/demo-login',json={'username':'rd'}).status_code==403
        assert local.post('/api/library/demo-login',headers={'X-P18-Client':'workbench','Origin':'https://foreign.invalid'},json={'username':'rd'}).status_code==403
        assert local.post('/api/library/demo-login',headers={'X-P18-Client':'workbench'},json={'username':'rd','role':'boss'}).status_code==422
        response=local.post('/api/library/demo-login',headers={'X-P18-Client':'workbench'},json={'username':'rd'})
        assert response.status_code==200
        me=local.get('/api/library/me').json()
        assert me['username']=='rd' and me['role']=='employee'
    with TestClient(r.q.app,base_url='http://127.0.0.1',client=('192.0.2.10',51001))as remote:
        assert remote.get('/api/library/demo-accounts').json()==[]
        assert remote.post('/api/library/demo-login',headers={'X-P18-Client':'workbench'},json={'username':'rd'}).status_code==404


def test_only_boss_can_appoint_and_prior_sessions_are_invalidated(rig):
    r=rig;business_roles.install_api(r.q)
    body={'username':'qa','role':'supervisor','department':'研发部'}
    assert r.c.put('/api/business/people',headers=r.h['head'],json=body).status_code==403
    assert r.c.put('/api/business/people',headers=r.h['boss'],json={**body,'role':'boss'}).status_code==403
    assert r.c.put('/api/business/people',headers=r.h['boss'],json=body).status_code==200
    assert r.c.get('/api/library/me',headers=r.h['qa']).status_code==401
    with r.q.connect()as c:
        assert business_roles.profile(c,'qa')['role']=='supervisor'
        assert c.execute('SELECT count(*) FROM business_profiles WHERE role="boss"').fetchone()[0]==1


def test_new_versions_keep_job_restrictions(rig):
    r=rig;old=r.create()
    with r.q.connect()as c:
        b=r.q.business_read(old);b['read_jobs']=['研发','测试'];c.execute('UPDATE business_documents SET body=?WHERE document_id=?',(json.dumps(b),old))
    assert r.c.get('/api/documents/'+old,headers=r.h['ops']).status_code==404
    body={'name':'虚构修订','code':'SAMPLE','version':'V2','department':'研发部','classification':'内部','replaces':old}
    response=r.c.post('/api/business/upload',headers=r.h['rd'],files={'file':('same.docx',b'fictional-v2')},data={'metadata_json':json.dumps(body)})
    assert response.status_code==200,response.text
    new=response.json()['id'];assert r.q.business_read(new)['read_jobs']==['研发','测试']
    assert r.q.business_read(new)['status']=='published'
    assert r.c.get('/api/documents/'+new,headers=r.h['qa']).status_code==200
    assert r.c.get('/api/documents/'+new,headers=r.h['ops']).status_code==404
    assert r.action(new,'head','share',username='ops').status_code==200
    assert r.c.get('/api/documents/'+new,headers=r.h['ops']).status_code==200

def test_new_version_cannot_silently_downgrade_confidentiality(rig):
    r=rig;old=r.create(restricted=True)
    with r.q.connect()as c:
        version,meta=library_store.read(c,old)
        library_store.write(c,old,__import__('dataclasses').replace(meta,classification='机密'),version)
    body={'name':'虚构修订','code':'SAMPLE','version':'V2','department':'研发部','classification':'内部','replaces':old}
    response=r.c.post('/api/business/upload',headers=r.h['rd'],files={'file':('same.docx',b'fictional-v2')},data={'metadata_json':json.dumps(body)})
    assert response.status_code==422
    assert not r.q.business_read(old)['archived']


def test_demo_fill_requires_submit_and_is_cookie_bound_single_use(rig):
    r=rig;r.q.MANAGED_RAG={};business_roles.install_api(r.q)
    (r.q.DATA/'business-demo-enabled.json').write_text('{"enabled":true}')
    with TestClient(r.q.app,base_url='http://127.0.0.1',client=('127.0.0.1',52000))as local,TestClient(r.q.app,base_url='http://127.0.0.1',client=('127.0.0.1',52001))as other:
        for username in ['boss','rd']:
            local.cookies.clear()
            response=local.post('/api/library/demo-fill',headers={'X-P18-Client':'workbench'},json={'username':username})
            assert response.status_code==200
            filled=response.json()
            assert local.get('/api/library/me').status_code==401
            assert other.post('/api/library/login',headers={'X-P18-Client':'workbench'},json={'username':username,'password':filled['password']}).status_code==401
            result=local.post('/api/library/login',headers={'X-P18-Client':'workbench'},json={'username':username,'password':filled['password']})
            assert result.status_code==200
            assert local.get('/api/library/me').json()['username']==username
            assert local.post('/api/library/login',headers={'X-P18-Client':'workbench'},json={'username':username,'password':filled['password']}).status_code==401
    with TestClient(r.q.app,base_url='http://127.0.0.1',client=('192.0.2.10',52002))as remote:
        assert remote.post('/api/library/demo-fill',headers={'X-P18-Client':'workbench'},json={'username':'boss'}).status_code==404


def test_demo_fill_expiration_and_role_changes_invalidate_password(rig,monkeypatch):
    r=rig;r.q.MANAGED_RAG={};business_roles.install_api(r.q)
    (r.q.DATA/'business-demo-enabled.json').write_text('{"enabled":true}')
    with TestClient(r.q.app,base_url='http://127.0.0.1',client=('127.0.0.1',53000))as local:
        def fill():return local.post('/api/library/demo-fill',headers={'X-P18-Client':'workbench'},json={'username':'rd'}).json()['password']
        password=fill()
        with r.q.connect()as c:business_roles.assign(c,'rd','guest','')
        assert local.post('/api/library/login',headers={'X-P18-Client':'workbench'},json={'username':'rd','password':password}).status_code==401
        password=fill();now=business_roles.time.time()
        monkeypatch.setattr(business_roles.time,'time',lambda:now+121)
        assert local.post('/api/library/login',headers={'X-P18-Client':'workbench'},json={'username':'rd','password':password}).status_code==401


def test_two_libraries_and_old_qichen_link_open_same_writable_store(rig,tmp_path,monkeypatch):
    from app.datasets import DatasetsApp
    from fastapi import FastAPI,Request
    r=rig;root=tmp_path/'project';(root/'config').mkdir(parents=True)
    (root/'config/business.json').write_text('{"data_dir":"runtime/not-opened"}')
    monkeypatch.setattr(r.q,'ROOT',root);monkeypatch.delattr(r.q,'authorize_operation')
    ds=DatasetsApp(r.q);stub=FastAPI()
    @stub.get('/api/probe')
    def probe():return {'source':'writable'}
    ds.business_store=SimpleNamespace(app=stub)
    client=TestClient(ds,base_url='http://127.0.0.1')
    for who in ['boss','rd','guest']:
        response=client.get('/api/library/datasets',headers=r.h[who])
        assert [d['id']for d in response.json()['datasets']]==['business','demo']
        assert response.json()['datasets'][0]['name']=='启辰智造知识库'
        client.cookies.set('p18_dataset','qichen30')
        assert client.get('/api/probe',headers=r.h[who]).json()=={'source':'writable'}
        assert client.get('/api/library/datasets',headers=r.h[who]).json()['selected']=='business'
        assert client.post('/api/library/datasets',headers=r.h[who],json={'dataset':'qichen30'}).json()['dataset']=='business'
    assert ds.qstore is None
    client.close()


def test_invitation_scope_activation_and_no_demo_shortcut(rig):
    r=rig;business_roles.install_api(r.q)
    for name,role in [('qichen_hr_head','supervisor'),('hr_employee','employee'),('hr_other_head','supervisor')]:
        with r.q.connect()as c:
            library_store.create_account(c,name,'synthetic-password-123','人力资源部普通员工')
            business_roles.assign(c,name,role,'人力资源部')
            token=library_store.login(c,name,'synthetic-password-123')
        r.h[name]={'Authorization':'Bearer '+token,'X-P18-Client':'workbench'}
    body={'username':'new_staff','department':'研发部','job':'研发'}
    for who in ['rd','head','hr_employee','hr_other_head']:
        assert r.c.post('/api/business/accounts',headers=r.h[who],json=body).status_code==403
    for role in ['boss','supervisor']:
        assert r.c.post('/api/business/accounts',headers=r.h['boss'],json={**body,'role':role}).status_code==422
    response=r.c.post('/api/business/accounts',headers=r.h['qichen_hr_head'],json=body)
    assert response.status_code==200,response.text
    code=response.json()['invitation_code']
    assert r.c.post('/api/business/accounts',headers=r.h['boss'],json=body).status_code==409
    with r.q.connect()as c:
        assert not library_store.login(c,'new_staff','synthetic-password-123')
        assert c.execute('SELECT active FROM library_accounts WHERE username=?',('new_staff',)).fetchone()[0]==0
        assert code not in repr([tuple(x)for x in c.execute('SELECT * FROM account_invitations')])
    payload={'invitation_code':code,'password':'fictional-activation-123'}
    response=r.c.post('/api/library/activate-account',headers={'X-P18-Client':'workbench'},json=payload)
    assert response.status_code==200,response.text
    assert r.c.post('/api/library/activate-account',headers={'X-P18-Client':'workbench'},json=payload).status_code==403
    with r.q.connect()as c:
        assert library_store.login(c,'new_staff',payload['password'])
        assert c.execute('SELECT is_demo FROM business_profiles WHERE username=?',('new_staff',)).fetchone()[0]==0
    (r.q.DATA/'business-demo-enabled.json').write_text('{"enabled":true}')
    with TestClient(r.q.app,base_url='http://127.0.0.1',client=('127.0.0.1',51000))as local:
        assert 'new_staff'not in [a['username']for a in local.get('/api/library/demo-accounts').json()]
        assert local.post('/api/library/demo-fill',headers={'X-P18-Client':'workbench'},json={'username':'new_staff'}).status_code==403


def test_head_ordinary_legacy_scope_but_no_confidential_or_cross_department(rig):
    r=rig;ordinary=r.create(legacy=True);secret=r.create(legacy=True,restricted=True);foreign=r.create(dept='生产制造部',legacy=True)
    for id in [ordinary,secret,foreign]:r.q.business_legacy_acl[id]={'file_sha256':'synthetic','roles':['研发'],'code':'EXAMPLE'}
    assert r.c.get('/api/documents/'+ordinary,headers=r.h['head']).status_code==200
    assert r.c.get('/api/documents/'+secret,headers=r.h['head']).status_code==404
    assert r.c.get('/api/documents/'+foreign,headers=r.h['head']).status_code==404
    assert r.action(ordinary,'head','share',username='prd').status_code==200
    assert r.c.get('/api/documents/'+ordinary,headers=r.h['prd']).status_code==200
    assert r.action(secret,'head','share',username='prd').status_code in {403,404}


def test_history_search_is_separate_and_rechecks_all_group_members(rig):
    r=rig;current=r.create();old=r.create();pending=r.create(status='submitted');trash=r.create();secret=r.create(restricted=True,owner='qa')
    r.action(old,'head','archive');r.action(trash,'head','trash')
    observed=[]
    def search(query,top_k,document_filter):
        allowed=[d['id']for d in r.q.all_docs()if document_filter(d)];observed.extend(allowed)
        return {'status':'ok','results':[{'document_id':id,'members':[{'document_id':id}]}for id in allowed]+[{'document_id':current,'members':[{'document_id':current},{'document_id':secret}]}]}
    r.q.require_semantic=lambda:SimpleNamespace(search=search)
    response=r.c.post('/api/business/history-search',headers=r.h['rd'],json={'query':'fictional'})
    assert response.status_code==200,response.text
    assert set(observed)=={current,old}
    assert {h['document_id']for h in response.json()['results']}=={current,old}
    assert any(h['historical']for h in response.json()['results'])
    assert not response.json()['eligible_for_rag']
    from app import library_api
    with r.q.connect()as c:u=library_store.session_by_digest(c,__import__('hashlib').sha256(r.h['rd']['Authorization'][7:].encode()).hexdigest())
    for id in [old,pending,trash,secret]:assert not r.q.authorize_document(r.q.get(id),u,evidence=True)


@pytest.mark.parametrize('internal', [False, True])
def test_minor_correction_real_source_atomic_switch_and_audit(rig, internal):
    r=rig;old=r.create();folder=r.q.folder_for(old);folder.mkdir(parents=True)
    from docx import Document
    doc=Document();doc.add_paragraph('Fictional typo.');doc.save(folder/'original.docx')
    old_bytes=(folder/'original.docx').read_bytes()
    original_upload=r.q.upload
    async def upload(files,mode,replace_id):
        result=await original_upload(files,mode,replace_id)
        new=result[0]['id'];path=r.q.folder_for(new);path.mkdir(parents=True)
        (path/'original.docx').write_bytes(await files[0].read());return result
    r.q.upload=upload
    url='/api/business/documents/'+old
    if internal:
        assert r.action(old,'boss','make_internal').status_code==200
    assert r.c.get(url+'/editable',headers=r.h['qa']).status_code==403
    payload={'expected':r.q.business_read(old)['version'],'reason':'Fictional spelling correction','declaration':False,'paragraphs':[{'ordinal':0,'text':'Fictional correction.'}]}
    assert r.c.post(url+'/correction',headers=r.h['rd'],json=payload).status_code==422
    response=r.c.post(url+'/correction',headers=r.h['rd'],json={**payload,'declaration':True});assert response.status_code==200,response.text
    new=response.json()['document']['id']
    assert r.q.business_read(new)['status']=='correction_pending'
    assert not r.q.business_read(new).get('company_internal')
    assert not r.q.business_read(old)['archived']
    assert Document(r.q.folder_for(new)/'original.docx').paragraphs[0].text=='Fictional correction.'
    assert (folder/'original.docx').read_bytes()==old_bytes
    assert r.c.post(url+'/correction',headers=r.h['rd'],json={**payload,'declaration':True}).status_code==409
    assert r.q.finalize_correction(new)
    assert r.q.business_read(old)['archived']and r.q.business_read(new)['status']=='published'
    assert bool(r.q.business_read(new).get('company_internal')) == internal
    assert r.c.get('/api/documents/'+new,headers=r.h['prd']).status_code == (200 if internal else 404)
    assert r.c.get('/api/documents/'+new,headers=r.h['guest']).status_code == 404
    with r.q.connect()as c:
        assert library_store.read(c,old)[1].version==library_store.read(c,new)[1].version
        assert c.execute('SELECT completed FROM business_edits WHERE document_id=?',(new,)).fetchone()[0]
        assert c.execute("SELECT COUNT(*)FROM business_events WHERE document_id=? AND action LIKE 'minor_correction%'",(new,)).fetchone()[0]==2


def test_minor_correction_conflict_and_cancel_fail_closed(rig):
    r=rig;old=r.create();folder=r.q.folder_for(old);folder.mkdir(parents=True)
    from docx import Document
    doc=Document();doc.add_paragraph('Fictional.');doc.save(folder/'original.docx')
    response=r.c.post('/api/business/documents/'+old+'/correction',headers=r.h['rd'],json={'expected':0,'reason':'typo','declaration':True,'paragraphs':[{'ordinal':0,'text':'Fixed.'}]})
    assert response.status_code==200,response.text
    new=response.json()['document']['id']
    assert r.action(old,'head','archive').status_code==200
    assert r.q.finalize_correction(new)is False
    assert r.q.business_read(new)['status']=='correction_pending'
    assert r.action(new,'qa','cancel_correction').status_code in {403,404}
    assert r.action(new,'rd','cancel_correction').status_code==200
    assert r.q.business_read(new)['status']=='withdrawn'


def test_new_guest_has_no_implicit_department_access_in_demo_policy(rig):
    r=rig;business_roles.install_api(r.q)
    response=r.c.post('/api/business/accounts',headers=r.h['boss'],json={'username':'guest_new','role':'guest','department':'财务部'})
    assert response.status_code==200,response.text
    from app.library_policy import can_view
    with r.q.connect()as c:
        identity=c.execute('SELECT identity FROM library_accounts WHERE username=?',('guest_new',)).fetchone()[0]
    assert identity=='只读访客'
    meta=LibraryMetadata('FIN','Fictional','财务部','财务部','文档','内部','V1','现行有效')
    assert not can_view(meta,identity)
    assert can_view(__import__('dataclasses').replace(meta,classification='公开'),identity)


def test_reinvite_revokes_old_code_without_resetting_active_accounts(rig):
    r=rig;business_roles.install_api(r.q)
    first=r.c.post('/api/business/accounts',headers=r.h['boss'],json={'username':'pending_staff','department':'研发部'}).json()
    route='/api/business/accounts/reinvite'
    assert r.c.post(route,headers=r.h['rd'],json={'username':'pending_staff'}).status_code==403
    second=r.c.post(route,headers=r.h['boss'],json={'username':'pending_staff'});assert second.status_code==200
    activate='/api/library/activate-account';headers={'X-P18-Client':'workbench'}
    assert r.c.post(activate,headers=headers,json={'invitation_code':first['invitation_code'],'password':'fictional-password-123'}).status_code==403
    assert r.c.post(activate,headers=headers,json={'invitation_code':second.json()['invitation_code'],'password':'fictional-password-123'}).status_code==200
    assert r.c.post(route,headers=r.h['boss'],json={'username':'pending_staff'}).status_code==409
    assert r.c.post(route,headers=r.h['boss'],json={'username':'boss'}).status_code==409


def test_uploaded_internal_document_uses_direct_department_release_and_takedown(rig):
    r=rig
    def upload(version,replaces=None):
        metadata={'name':'发布流程演示','code':'RELEASE-01','version':version,'classification':'内部'}
        if replaces:
            metadata['replaces']=replaces
        response=r.c.post('/api/business/upload',headers=r.h['rd'],
                          files={'file':('release.docx',b'test')},data={'metadata_json':json.dumps(metadata)})
        assert response.is_success, response.text
        row=response.json()
        assert row['workflow']['status']=='published'
        assert not row.get('review_reasons')
        assert row['id'] in r.scheduled
        return row['id']
    old=upload('V1')
    assert r.q.business_read(old)['status']=='published'
    assert r.c.get('/api/documents/'+old,headers=r.h['qa']).status_code==200
    assert r.c.get('/api/documents/'+old,headers=r.h['prd']).status_code==404
    new=upload('V2',old)
    assert r.q.business_read(new)['status']=='published'
    assert r.q.business_read(old)['archived'] is True
    query='/source?revision=1&index_token=old&chunk_id=old&current_only=true'
    assert r.c.get('/api/documents/'+old+query,headers=r.h['rd']).status_code==409
    assert r.action(new,'qa','take_down',note='越权用例').status_code==403
    assert r.action(new,'rd','take_down',note='撤下测试').is_success
    assert r.c.get('/api/documents/'+new,headers=r.h['qa']).status_code==404
    assert r.c.get('/api/documents/'+new+query,headers=r.h['rd']).status_code==409
    assert r.c.get('/api/documents/'+new,headers=r.h['rd']).status_code==200


def test_sensitive_content_and_supervisor_self_review_go_through_separate_gate(rig):
    r=rig
    id=r.create(owner='head',status='submitted')
    with r.q.connect() as conn:
        row=r.q.business_read(id,conn)
        row['read_jobs']=['研发']
        conn.execute('UPDATE business_documents SET body=? WHERE document_id=?',(json.dumps(row),id))
    doc=r.q.get(id)
    doc.update(publication_rules=1,characters=18,result={'blocks':[{'text':'报价金额：8000元'}]})
    r.q.save(doc)
    assert r.action(id,'head','publish').status_code==409
    assert r.action(id,'head','approve_publish').status_code==403
    response=r.action(id,'boss','approve_publish')
    assert response.is_success, response.text
    assert response.json()['classification']=='机密'
    assert r.c.get('/api/documents/'+id,headers=r.h['rd']).status_code==404


def test_optional_document_code_preserves_distinct_series_and_version_link(rig):
    r=rig
    def upload(name, version='V1', **extra):
        response=r.c.post('/api/business/upload',headers=r.h['rd'],
            files={'file':('report.docx',b'test')},
            data={'metadata_json':json.dumps(dict(name=name,version=version,**extra))})
        assert response.is_success,response.text
        return response.json()
    first=upload('测试报告')
    second=upload('另一份报告',code='  ')
    assert first['code']==second['code']==''
    assert first['id']!=second['id']
    assert r.q.business_read(first['id'])['series']!=r.q.business_read(second['id'])['series']
    assert r.q.business_read(first['id'])['status']=='published'
    newer=upload('测试报告','V2',replaces=first['id'])
    assert newer['code']==''
    assert r.q.business_read(newer['id'])['series']==r.q.business_read(first['id'])['series']
    assert r.q.business_read(newer['id'])['status']=='published'
    assert r.q.business_read(first['id'])['archived']
    numbered=upload('有编号报告',code='RD-123')
    assert r.q.business_read(numbered['id'])['status']=='published'
    next_numbered=upload('有编号报告','V2',replaces=numbered['id'])
    assert next_numbered['code']=='RD-123'


def test_parse_exception_priority_and_withdrawn_draft(rig):
    r=rig
    id=r.create(status='submitted',restricted=True)
    doc=r.q.get(id)
    doc.update(publication_rules=1,state='review',result={'blocks':[], 'issues':[{'kind':'table','message':'原表错列'}]})
    r.q.save(doc)
    rows=r.c.get('/api/business/documents',headers=r.h['head']).json()
    row=next(row for row in rows if row['id']==id)
    assert row['publication_stage']=='解析异常'
    assert row['parse_reasons']==['原表错列'] and row['review_reasons']==['标为机密']
    assert r.action(id,'head','approve_publish').status_code==409
    assert r.action(id,'rd','withdraw').is_success
    assert r.q.business_read(id)['status']=='withdrawn'
    assert r.action(id,'rd','publish').status_code==409


def test_cross_department_read_grant_never_delegates_management(rig):
    r=rig;document=r.create()
    assert r.action(document,'head','share',username='otherhead').status_code==200
    assert r.c.get('/api/documents/'+document,headers=r.h['otherhead']).status_code==200
    for action,kwargs in [('share',{'username':'prd'}),('revoke_share',{'username':'otherhead'}),('make_public',{}),('make_internal',{}),('take_down',{'note':'attempt'}),('publish',{})]:
        assert r.action(document,'otherhead',action,**kwargs).status_code==403
    assert r.c.get('/api/business/documents/'+document+'/borrowers',headers=r.h['otherhead']).status_code==404
    assert r.action(document,'head','revoke_share',username='otherhead').status_code==200
    assert r.c.get('/api/documents/'+document,headers=r.h['otherhead']).status_code==404
    secret=r.create(restricted=True)
    assert r.action(secret,'boss','share',username='head').status_code==200
    assert r.c.get('/api/documents/'+secret,headers=r.h['head']).status_code==200
    assert r.action(secret,'head','share',username='prd').status_code==403
    assert r.action(secret,'boss','share',username='prd').status_code==200
    assert r.action(secret,'boss','share',username='guest').status_code==403
    assert r.action(secret,'boss','take_down',note='isolated emergency test').status_code==200
    assert r.c.get('/api/documents/'+secret,headers=r.h['prd']).status_code==404
    assert r.q.business_read(secret)['status']=='taken_down'


def test_recent_operations_is_boss_only_bounded_and_keeps_removed_records(rig):
    r=rig
    id=r.create()
    with r.q.connect() as c:
        for i in range(10):
            c.execute('INSERT INTO business_events(document_id,at,actor,action,body) VALUES (?,?,?,?,?)',
                      (id,100+i,'head','return',json.dumps({'note':str(i),'private_extra':'not returned'})))
    for actor in ['rd','head','guest']:
        assert r.c.get('/api/business/recent-operations',headers=r.h[actor]).status_code==403
    response=r.c.get('/api/business/recent-operations',headers=r.h['boss'])
    assert response.status_code==200
    rows=response.json()
    assert len(rows)==8 and [x['note'] for x in rows]==[str(i) for i in range(9,1,-1)]
    assert rows[0]['document_name']=='虚构样例.docx'
    assert 'private_extra' not in response.text
    with r.q.connect() as c:c.execute('DELETE FROM documents WHERE id=?',(id,))
    assert r.c.get('/api/business/recent-operations',headers=r.h['boss']).json()[0]['document_name']=='已移除的资料'


def auto_submission(r, **kwargs):
    identifier=r.create(status='submitted',**kwargs)
    doc=r.q.get(identifier);doc['publication_rules']=1;r.q.save(doc)
    return identifier


def test_ordinary_auto_publication_runs_without_session_and_is_idempotent(rig):
    r=rig;identifier=auto_submission(r)
    assert r.c.get('/api/documents/'+identifier,headers=r.h['qa']).status_code==404
    r.q.on_index_complete(identifier)
    assert r.q.business_read(identifier)['status']=='published'
    assert r.c.get('/api/documents/'+identifier,headers=r.h['qa']).status_code==200
    for who in ['prd','guest']:
        assert r.c.get('/api/documents/'+identifier,headers=r.h[who]).status_code==404
    r.q.on_index_complete(identifier)
    with r.q.connect()as c:
        events=c.execute("SELECT actor,body FROM business_events WHERE document_id=? AND action='publish'",(identifier,)).fetchall()
    assert len(events)==1 and events[0]['actor']=='rd'
    assert json.loads(events[0]['body'])['automatic'] is True


@pytest.mark.parametrize('reason',['restricted','sensitive','incomplete','parse_failed','parse_review','index_failed','index_waiting','withdrawn','returned','archived','deleted','legacy'])
def test_auto_publication_keeps_ineligible_submissions_private(rig,reason):
    r=rig;identifier=auto_submission(r)
    doc=r.q.get(identifier);b=r.q.business_read(identifier)
    if reason=='restricted':b['restricted']=True
    if reason=='sensitive':doc['result']['blocks']=[{'type':'paragraph','text':'报价金额：人民币120万元。'}]
    if reason=='incomplete':doc['result']['issues']=[{'kind':'image','message':'图片内容未提取'}]
    if reason=='parse_failed':doc['state']='failed'
    if reason=='parse_review':doc['state']='review'
    if reason.startswith('index_'):r.index_states[identifier]={'status':reason[6:],'searchable':False}
    if reason in {'withdrawn','returned'}:b['status']=reason
    if reason in {'archived','deleted'}:b[reason]=True
    if reason=='legacy':doc.pop('publication_rules')
    r.q.save(doc)
    with r.q.connect()as c:c.execute('UPDATE business_documents SET body=? WHERE document_id=?',(json.dumps(b),identifier))
    r.q.on_index_complete(identifier)
    assert r.q.business_read(identifier)['status']!='published'
    if reason=='restricted':
        assert r.action(identifier,'head','approve_publish').is_success
        assert r.q.business_read(identifier)['status']=='published'


def test_auto_publish_waits_for_usable_index_then_atomically_replaces_old(rig):
    r=rig;old=r.create();new=auto_submission(r)
    b=r.q.business_read(new);b['replaces']=old
    with r.q.connect()as c:c.execute('UPDATE business_documents SET body=? WHERE document_id=?',(json.dumps(b),new))
    r.index_states[new]={'status':'failed','searchable':False}
    r.q.on_index_complete(new)
    assert not r.q.business_read(old)['archived']
    assert r.q.business_read(new)['status']=='submitted'
    r.index_states.pop(new)
    r.q.on_index_complete(new)
    assert r.q.business_read(old)['archived']
    assert r.q.business_read(new)['status']=='published'


@pytest.mark.parametrize('change',['disabled','guest','department','old_archived','old_restricted'])
def test_auto_publication_rechecks_account_and_previous_version(rig,change):
    r=rig;old=r.create();new=auto_submission(r)
    b=r.q.business_read(new);b['replaces']=old
    with r.q.connect()as c:
        c.execute('UPDATE business_documents SET body=? WHERE document_id=?',(json.dumps(b),new))
        if change=='disabled':c.execute("UPDATE library_accounts SET active=0 WHERE username='rd'")
        if change=='guest':c.execute("UPDATE business_profiles SET role='guest' WHERE username='rd'")
        if change=='department':c.execute("UPDATE business_profiles SET department='财务部' WHERE username='rd'")
        if change.startswith('old_'):
            previous=r.q.business_read(old);previous[change[4:]]=True
            c.execute('UPDATE business_documents SET body=? WHERE document_id=?',(json.dumps(previous),old))
    r.q.on_index_complete(new);r.q.on_index_complete(new)
    assert r.q.business_read(new)['status']=='submitted'
    assert r.q.business_read(new)['auto_publish_error']
    with r.q.connect()as c:
        assert c.execute("SELECT count(*) FROM business_events WHERE document_id=? AND action='auto_publish_blocked'",(new,)).fetchone()[0]==1


def test_resubmit_reuses_ready_index_and_auto_publishes(rig):
    r=rig;identifier=auto_submission(r)
    b=r.q.business_read(identifier);b['status']='returned'
    with r.q.connect()as c:c.execute('UPDATE business_documents SET body=? WHERE document_id=?',(json.dumps(b),identifier))
    assert r.action(identifier,'rd','resubmit').is_success
    assert r.q.business_read(identifier)['status']=='published'


def test_document_detail_exposes_lifecycle_summary_without_expanding_audit_access(rig):
    r=rig;identifier=r.create(status='submitted')
    assert r.action(identifier,'head','approve').status_code==200
    assert r.action(identifier,'head','publish').status_code==200
    response=r.c.get('/api/documents/'+identifier,headers=r.h['qa'])
    assert response.status_code==200
    facts=response.json()['lifecycle']
    assert facts['submitted']['actor']=='rd'
    assert facts['reviewed']['actor']=='head' and facts['published']['actor']=='head'
    assert set(facts['reviewed'])=={'actor','at'}
    assert r.c.get('/api/business/documents/'+identifier+'/audit',headers=r.h['qa']).status_code==404
    for actor in ['prd','guest']:
        assert r.c.get('/api/documents/'+identifier,headers=r.h[actor]).status_code==404
