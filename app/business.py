"""Business lifecycle over a separate writable copy; original E2 remains sealed.

Visibility is always checked from SQLite, including every RRF/dedup member.
Technical readiness never grants publication. No model or egress authorization.
"""
from pathlib import Path
import json,time,uuid,threading,importlib.util,sys
from dataclasses import asdict
from fastapi import HTTPException,UploadFile,File,Form,Request
from pydantic import BaseModel,ConfigDict,Field
from app import library_api,library_store
from app.library_policy import LibraryMetadata,can_view
from app.business_roles import DEPARTMENTS

class Action(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    action:str
    expected:int=Field(ge=0)
    note:str=Field(default='',max_length=2000)
    username:str=Field(default='',max_length=100)
    expires_at:int|None=None
    confirm:str=''

def initialize(store):
    with store.connect() as c:
        c.execute('CREATE TABLE IF NOT EXISTS business_documents (document_id TEXT PRIMARY KEY, body TEXT NOT NULL)')
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS business_one_pending ON business_documents(json_extract(body,'$.series')) WHERE json_extract(body,'$.status') IN ('submitted','approved','returned') AND json_extract(body,'$.deleted')=0")
        c.execute('CREATE TABLE IF NOT EXISTS business_events (id INTEGER PRIMARY KEY, document_id TEXT NOT NULL, at REAL NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL, body TEXT NOT NULL)')
        c.execute('CREATE TABLE IF NOT EXISTS business_grants (document_id TEXT NOT NULL, username TEXT NOT NULL, expires REAL, PRIMARY KEY(document_id,username))')

def install(store,central,legacy_acl):
    initialize(store)
    def user():
        u=library_api.principal.get()
        if not u or not u.get('username') or u.get('role') not in {'boss','supervisor','employee','guest'}:raise HTTPException(403,'此账号尚未配置业务角色')
        with central.connect() as c:current=library_store.session_by_digest(c,u['session_digest'])
        if not current or any(current.get(k)!=u.get(k) for k in ['role','department','job']):raise HTTPException(401,'身份已变化，请重新登录')
        return current
    def read(identifier,c=None):
        if c is None:
            with store.connect() as conn:return read(identifier,conn)
        row=c.execute('SELECT body FROM business_documents WHERE document_id=?',(identifier,)).fetchone()
        return json.loads(row[0]) if row else None
    def write(identifier,b,u,action,note=''):
        b['version']+=1
        with store.connect() as c:
            c.execute('INSERT OR REPLACE INTO business_documents VALUES (?,?)',(identifier,json.dumps(b,ensure_ascii=False)))
            c.execute('INSERT INTO business_events(document_id,at,actor,action,body) VALUES (?,?,?,?,?)',(identifier,time.time(),u['username'],action,json.dumps({'version':b['version'],'note':note},ensure_ascii=False)))
    def manager(u,b):return u['role']=='boss' or (u['role']=='supervisor' and u['department']==b['department'])
    def visible(doc,u,*,evidence=False):
        if not u or 'role' not in u:return False
        with central.connect() as c:
            current=library_store.session_by_digest(c,u['session_digest'])
        if not current:return False
        u=current;b=read(doc['id'])
        if not b or b.get('purged'):return False
        if b.get('deleted'):
            return not evidence and manager(u,b)
        if evidence and (b['status']!='published' or b['archived']):return False
        if u['role']=='boss':return True
        if b['status'] not in {'published','legacy_archived'}:
            return not evidence and ((u['username']==b['owner'] and u['department']==b['department']) or (manager(u,b) and u['username']!=b['owner']))
        with store.connect() as c:
            grant=c.execute('SELECT expires FROM business_grants WHERE document_id=? AND username=?',(doc['id'],u['username'])).fetchone()
        if grant and (grant[0] is None or grant[0]>time.time()):return True
        if b.get('company_public'):return True
        if u['role']=='guest':return False
        if b.get('legacy'):
            rule=legacy_acl.get(doc['id'])
            if not rule or doc.get('sha256')!=rule['file_sha256']:return False
            if u['role']=='supervisor'and u['department']==b['department']and not b.get('restricted'):return True
            if rule['roles'] is not None:
                return u.get('job') in rule['roles'] and not(rule['code']=='EXT-13' and u.get('job')=='运维')
            with store.connect() as c:row=library_store.read(c,doc['id'])
            parent={'研发部':'研发部员工','生产制造部':'生产制造部员工','财务部':'财务部普通员工','人力资源部':'人力资源部普通员工','行政安全部':'行政安全部员工'}.get(u['department'],'')
            return bool(row and can_view(row[1],parent))
        if u['role']=='supervisor'and u['department']==b['department']and not b.get('restricted'):return True
        if b.get('read_jobs')is not None:return u.get('job')in b['read_jobs']or(u['username']==b['owner']and u['department']==b['department'])
        if b.get('restricted'):return u['username']==b['owner'] and u['department']==b['department']
        return u['department']==b['department']
    store.authorize_document=visible
    def operation(u,method,path):
        user()
        if method in {'GET','HEAD','OPTIONS'}:return
        if path.startswith('/api/business/'):return
        # Preserve only local retrieval/RAG preparation, no external endpoint.
        if method=='POST' and path in {'/api/search','/api/rag/drafts','/api/rag/selection'}:return
        if method=='POST' and path=='/api/rag/answer':
            from app.llm import provider_name
            if provider_name()=='ollama':return
        if method=='POST' and path.startswith('/api/documents/') and path.endswith('/review'):
            identifier=path.split('/')[3];b=read(identifier)
            if b and manager(u,b) and b['status']in {'submitted','correction_pending'}:return
        raise HTTPException(403,'业务库仅允许受控提交与审批接口；禁止直接修改、删除或外发')
    store.authorize_operation=operation
    old_schedule=store.schedule_chunks
    def schedule(doc,retry_failed=False):
        b=read(doc['id'])
        if b and b['status'] in {'approved','published','legacy_archived','correction_pending'}:return old_schedule(doc,retry_failed)
    store.schedule_chunks=schedule
    old_public=store.public
    def public(doc,detailed=False):
        result=old_public(doc,detailed);b=read(doc['id'])
        result['workflow']=b
        result['technical_index_ready']=bool(original_index_status(doc['id']).get('searchable'))
        result['technical_state']=doc['state']
        result['technical_error']=doc.get('error')
        result['external_permission'].update(allowed=False,can_review=False,notice='业务资料未获外发授权，仅供本地使用')
        if not b or b['status']!='published' or b.get('deleted') or b['archived']:
            result['index']['searchable']=False;result['build']['searchable']=False
        return result
    store.public=public
    # Existing library_record derives statuses via index_status; publication gate applies there too.
    original_index_status=store.index_status
    def index_status(identifier):
        result=original_index_status(identifier);b=read(identifier)
        if not b or b['status']!='published' or b.get('deleted') or b['archived']:result=dict(result,searchable=False)
        return result
    store.index_status=index_status
    store.business_raw_index_status=original_index_status
    store.business_read=read
    store.business_legacy_acl=legacy_acl
    def decorate(doc,result):
        b=read(doc['id'])
        if not b:return
        result['workflow']=b
        result['technical_index_ready']=bool(original_index_status(doc['id']).get('searchable'))
        result['technical_state']=doc['state']
        result['technical_error']=doc.get('error')
        if b['archived']:result['lifecycle']='已废止'
        if b.get('deleted'):result['status']='回收站'
        elif b['archived']:result['status']='历史归档'
        elif b['status']!='published':result['status']={'submitted':'待业务审核','approved':'审批通过待发布','returned':'已退回','correction_pending':'勘误处理中（免业务审批）'}.get(b['status'],b['status'])
    store.decorate_library_record=decorate
    def assert_write(u,b):
        if not manager(u,b):raise HTTPException(403,'仅老板或本部门主管可操作')
    def summary(doc):
        row=library_api.library_record(store,doc)
        row['workflow']=read(doc['id'])
        return row

    @store.app.get('/api/business/documents')
    def listing():
        u=user();out=[]
        for doc in store.all_docs():
            if doc['state'] in {'deleted','deleting','delete_failed'}:continue
            if visible(doc,u):out.append(summary(doc))
        return out

    @store.app.post('/api/business/upload')
    async def upload(file:UploadFile=File(...),metadata_json:str=Form(...)):
        u=user()
        if u['role']=='guest':raise HTTPException(403,'访客不能上传')
        try:
            m=json.loads(metadata_json)
            if not isinstance(m,dict) or set(m)-{'name','code','version','department','classification','replaces'}:raise ValueError()
            if m.get('replaces')is not None and (not isinstance(m['replaces'],str) or str(uuid.UUID(m['replaces']))!=m['replaces']):raise ValueError()
            dept=m.get('department') if u['role']=='boss' else u['department']
            if dept not in DEPARTMENTS or (u['role']!='boss' and m.get('department',dept)!=dept):raise ValueError()
            for key in ['name','code','version']:
                if not isinstance(m.get(key),str)or not m[key].strip()or len(m[key])>200:raise ValueError()
            classification=m.get('classification','内部')
            if classification not in {'内部','机密'}:raise ValueError()
        except (ValueError,TypeError):raise HTTPException(422,'提交字段无效；部门由身份决定，公开须另行批准')from None
        previous=None
        with store.LOCK:
            if m.get('replaces'):
                previous=read(m['replaces'])
                if not previous or previous['department']!=dept or not visible(store.get(m['replaces']),u) or previous['status']not in {'published','returned'} or previous.get('deleted')or previous['archived']:raise HTTPException(409,'不能替换此文档版本')
                with store.connect()as c:old_meta=library_store.read(c,m['replaces'])[1]
                if m['code']!=old_meta.code or m['version']==old_meta.version:raise HTTPException(409,'新版本须保留文档编号并使用不同版本号')
                if old_meta.classification=='机密'and classification!='机密':raise HTTPException(422,'新版本不得降低原机密级别；扩大读取须另行明确批准')
                if previous['owner']!=u['username'] and not manager(u,previous):raise HTTPException(403,'仅上传者或主管可提交新版本')
                with store.connect()as c:
                    for r in c.execute('SELECT body FROM business_documents'):
                        v=json.loads(r[0])
                        if v['series']==previous['series'] and not(v.get('owner')==previous['owner'] and v['version']==previous['version'] and v['status']=='returned') and not v.get('deleted') and v['status']in {'submitted','approved','returned','correction_pending'}:raise HTTPException(409,'已有未发布的新版本')
            else:
                with store.connect()as c:
                    if any(json.loads(r[0]).get('code')==m['code'] for r in c.execute('SELECT body FROM library_metadata')):raise HTTPException(409,'文档编号已存在，请使用上传新版本或联系主管')
        # Native parser/storage, never client-supplied text/chunks or vector data.
        response=(await store.upload(files=[file],mode='keep' if previous else 'ask',replace_id=''))[0]
        if response['status']!='accepted':raise HTTPException(409,response['message'])
        identifier=response['id'];doc=store.get(identifier)
        with store.LOCK:
            meta=LibraryMetadata(code=m['code'],name=m['name'],folder=dept,department=dept,doc_type='业务资料',classification=classification,version=m['version'],lifecycle='现行有效',viewers=(u['identity'],)if classification=='机密'else())
            b=dict(version=0,owner=u['username'],department=dept,series=previous['series']if previous else str(uuid.uuid4()),replaces=(previous.get('replaces') if previous and previous['status']=='returned' else m.get('replaces')),revises=m.get('replaces'),status='submitted',archived=False,deleted=False,company_public=False,restricted=classification=='机密',legacy=False,approved_by=None,approved_fingerprint=None)
            if previous:
                b['restricted']=b['restricted']or previous.get('restricted',False)
                inherited=previous.get('read_jobs')
                if inherited is None and previous.get('legacy'):
                    rule=legacy_acl.get(m['replaces'],{})
                    inherited=rule.get('roles')
                    if inherited is not None and rule.get('code')=='EXT-13':inherited=[job for job in inherited if job!='运维']
                if inherited is not None:b['read_jobs']=list(inherited)
            try:
                with store.connect()as c:
                    library_store.write(c,identifier,meta,0)
                    if previous:
                        latest=read(m['replaces'],c)
                        if not latest or latest['version']!=previous['version']:raise ValueError('Previous version changed')
                        if previous['status']=='returned':
                            previous.update(status='withdrawn',archived=True,version=previous['version']+1)
                            c.execute('UPDATE business_documents SET body=? WHERE document_id=?',(json.dumps(previous,ensure_ascii=False),m['replaces']))
                    b['version']=1
                    c.execute('INSERT INTO business_documents VALUES (?,?)',(identifier,json.dumps(b,ensure_ascii=False)))
                    c.execute('INSERT INTO business_events(document_id,at,actor,action,body)VALUES(?,?,?,?,?)',(identifier,time.time(),u['username'],'submitted',json.dumps({'version':1,'revises':m.get('replaces')})))
            except Exception:
                store.delete(identifier)
                raise HTTPException(409,'提交冲突，未发布本次文件，请检查是否已有待审版本')from None
        return summary(doc)

    @store.app.post('/api/business/documents/{identifier}/action')
    def action(identifier:str,body:Action):
        u=user()
        with store.LOCK:
            doc=store.get(identifier);b=read(identifier)
            if not b or not(visible(doc,u) or (body.action=='purge' and u['role']=='boss' and b.get('deleted'))):raise HTTPException(404,'文档不可访问')
            if b['version']!=body.expected:raise HTTPException(409,'文档状态已变化，请刷新')
            a=body.action
            if a in {'approve','return','publish'}:
                assert_write(u,b)
                if b.get('deleted')or b['archived']:raise HTTPException(409,'归档或回收站文件不能发布')
            if a=='cancel_correction':
                if not b.get('correction')or b['status']!='correction_pending'or b['owner']!=u['username']:raise HTTPException(403,'仅本人可取消未生效勘误')
                b.update(status='withdrawn',archived=True);write(identifier,b,u,'cancel_correction')
                return summary(doc)
            if a=='retry_parse':
                if b['owner']!=u['username'] or doc['state']!='failed' or b.get('deleted'):raise HTTPException(403,'仅上传者可重试本人解析失败资料')
                b.update(status='correction_pending'if b.get('correction')else'submitted',approved_by=None,approved_fingerprint=None)
                write(identifier,b,u,'retry_parse')
                store.retry(identifier)
                return summary(store.get(identifier))
            if a=='return':
                if b['status']!='submitted' or not body.note.strip():raise HTTPException(409,'退回须提供原因且处于待审状态')
                b.update(status='returned',approved_by=None,approved_fingerprint=None)
            elif a=='resubmit':
                if b['owner']!=u['username'] or b['status']!='returned':raise HTTPException(403,'仅本人可重新提交被退回资料')
                b.update(status='submitted')
            elif a=='approve':
                if b['status']!='submitted' or doc['state']!='ready':raise HTTPException(409,'请先完成解析及必要的内容复核')
                b.update(status='approved',approved_by=u['username'],approved_fingerprint=store.fingerprint(doc))
            elif a=='publish':
                if b['status']!='approved' or b['approved_fingerprint']!=store.fingerprint(doc)or not original_index_status(identifier).get('searchable'):raise HTTPException(409,'审批或索引未就绪，尚未发布')
                if b.get('replaces'):
                    old=read(b['replaces'])
                    if not old or old['status']!='published'or old['archived']or old.get('deleted'):raise HTTPException(409,'上一版本已变化')
                    old['archived']=True
                    # Publish both pointers in one SQLite transaction; retain all source artifacts.
                    with store.connect()as c:
                        c.execute('UPDATE business_documents SET body=? WHERE document_id=?',(json.dumps(dict(old,version=old['version']+1),ensure_ascii=False),b['replaces']))
                        b.update(status='published');b['version']+=1
                        c.execute('UPDATE business_documents SET body=? WHERE document_id=?',(json.dumps(b,ensure_ascii=False),identifier))
                        c.execute('INSERT INTO business_events(document_id,at,actor,action,body)VALUES(?,?,?,?,?)',(identifier,time.time(),u['username'],'publish_version',json.dumps({'previous':b['replaces']})))
                    return summary(doc)
                b.update(status='published')
            elif a in {'archive','trash','restore'}:
                assert_write(u,b)
                if a=='archive':b['archived']=True
                elif a=='trash':b['deleted']=True
                else:b['deleted']=False
            elif a in {'share','revoke_share'}:
                assert_write(u,b)
                if a=='share'and(b['status']!='published'or b['archived']or b['deleted']):raise HTTPException(409,'仅可借阅当前已发布资料')
                if b.get('restricted'):
                    if u['role']!='boss':raise HTTPException(403,'受限资料共享需老板明确授权')
                with central.connect()as c:target=c.execute('SELECT active FROM library_accounts WHERE username=?',(body.username,)).fetchone()
                if not target or not target[0]:raise HTTPException(422,'目标账号不可用')
                if a=='share' and body.expires_at is not None and body.expires_at<=time.time():raise HTTPException(422,'授权已过期')
                with store.connect()as c:
                    if a=='share':c.execute('INSERT OR REPLACE INTO business_grants VALUES (?,?,?)',(identifier,body.username,body.expires_at))
                    else:c.execute('DELETE FROM business_grants WHERE document_id=? AND username=?',(identifier,body.username))
                    b['version']+=1
                    c.execute('UPDATE business_documents SET body=? WHERE document_id=?',(json.dumps(b,ensure_ascii=False),identifier))
                    c.execute('INSERT INTO business_events(document_id,at,actor,action,body)VALUES(?,?,?,?,?)',(identifier,time.time(),u['username'],a,json.dumps({'username':body.username,'expires_at':body.expires_at,'version':b['version']},ensure_ascii=False)))
                return summary(doc)
            elif a in {'make_public','revoke_public'}:
                if u['role']!='boss':raise HTTPException(403,'仅老板可批准全公司公开')
                b['company_public']=a=='make_public'
            elif a=='purge':
                if u['role']!='boss' or not b.get('deleted') or body.confirm!=identifier:raise HTTPException(403,'彻底删除仅限老板，并须先软删除及确认文件ID')
                # Durable tombstone first: any failure remains inaccessible and retryable.
                b['purged']=True;write(identifier,b,u,'purge_started')
                store.delete(identifier)
                if store.INDEX_SERVICE:
                    if not store.INDEX_SERVICE.vector_lock.acquire(blocking=False):raise HTTPException(409,'索引忙，已阻止读取；请稍后继续清理')
                    try:store.INDEX_SERVICE._delete_document(identifier)
                    finally:store.INDEX_SERVICE.vector_lock.release()
                with store.connect()as c:
                    for table in ['chunks','chunk_runs','index_runs','library_metadata','business_grants']:c.execute('DELETE FROM '+table+' WHERE document_id=?',(identifier,))
                write(identifier,b,u,'purged')
                return {'purged':True}
            else:raise HTTPException(422,'未知操作')
            write(identifier,b,u,a,body.note)
            if a=='approve':store.schedule_chunks(doc)
            return summary(doc)

    @store.app.get('/api/business/documents/{identifier}/audit')
    def audit(identifier:str):
        u=user();b=read(identifier)
        if not b or not(manager(u,b)or b['owner']==u['username']):raise HTTPException(404,'不可查看审计')
        with store.connect()as c:return [dict(r)for r in c.execute('SELECT at,actor,action,body FROM business_events WHERE document_id=? ORDER BY id',(identifier,))]
    from app.enterprise_documents import install_updates
    install_updates(store,central,user,read,manager,write,summary,visible)
    return store

def create_store(central,cfg):
    """Only an explicitly provisioned runtime child can be opened for writes."""
    data=(central.ROOT/Path(cfg['data_dir'])).resolve();runtime=(central.ROOT/'runtime').resolve()
    if not data.is_relative_to(runtime)or data==central.DATA.resolve()or not(data/'business-seed.json').is_file():raise RuntimeError('业务库必须是独立、已核验的runtime副本')
    spec=importlib.util.spec_from_file_location('app._business_store',central.ROOT/'app/main.py')
    q=importlib.util.module_from_spec(spec);sys.modules[spec.name]=q;spec.loader.exec_module(q)
    q.DATA,q.DB=data,data/'workbench.sqlite3';q.AUTH_STORE=central
    q.initialize()
    seed=json.loads((data/'business-seed.json').read_text());legacy_acl=seed['acl']
    initialize(q)
    with q.connect()as c:
        for doc in q.all_docs():
            row=library_store.read(c,doc['id'])
            if not row:continue
            meta=row[1]
            b=dict(version=0,owner='legacy_import',department=meta.department,series=meta.code,status='published'if meta.lifecycle=='现行有效'else'legacy_archived',archived=meta.lifecycle!='现行有效',deleted=False,company_public=meta.classification=='公开',restricted=meta.classification=='机密',legacy=True,approved_by=None,approved_fingerprint=None,replaces=None)
            c.execute('INSERT OR IGNORE INTO business_documents VALUES (?,?)',(doc['id'],json.dumps(b,ensure_ascii=False)))
    from app.semantic import IndexService
    class SharedModelIndex(IndexService):
        def close(self):
            self.closed=True;self.pool.shutdown(wait=True)
            with self.vector_lock:self.client.close()
    q.INDEX_SERVICE=SharedModelIndex(q)
    shared=central.require_semantic().provider
    if q.INDEX_SERVICE.config!=shared.config:raise RuntimeError('业务与基线模型配置不同，停止打开业务库')
    q.INDEX_SERVICE.provider=shared
    install(q,central,legacy_acl)
    # Business RAG remains local-only irrespective of personal credentials.
    from app.datasets import LocalRag
    services={}
    def current_rag():
        u=library_api.principal.get()
        if not u:raise HTTPException(401,'请登录')
        with central.connect()as c:
            if not library_store.session_by_digest(c,u['session_digest']):raise HTTPException(401,'会话已失效')
        if u['session_digest']not in services:
            if len(services)>64:services.clear()
            services[u['session_digest']]=LocalRag(q,lambda **v:None)
        return services[u['session_digest']]
    q.current_rag=current_rag
    for doc in q.all_docs():
        if doc['state']in q.STATES:
            doc.update(state='failed',quality='failed',error='上次业务处理被中断，请重新提交新版本；未发布。');q.save(doc)
        b=q.business_read(doc['id'])
        if b and b['status']in {'approved','correction_pending'} and doc['state']=='ready':q.schedule_chunks(doc,retry_failed=True)
    q.INDEX_SERVICE.recover()
    if not hasattr(central,'BUSINESS_CHILDREN'):central.BUSINESS_CHILDREN=[]
    central.BUSINESS_CHILDREN.append(q)
    return q
