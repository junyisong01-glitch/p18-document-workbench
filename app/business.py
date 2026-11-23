"""Business lifecycle over a separate writable copy; original E2 remains sealed.

Visibility is always checked from SQLite, including every RRF/dedup member.
Ordinary checked submissions publish after indexing; risk still requires review.
"""
from pathlib import Path
import json,time,uuid,threading,importlib.util,sys,re,unicodedata
from dataclasses import asdict, replace
from fastapi import HTTPException,UploadFile,File,Form,Request
from pydantic import BaseModel,ConfigDict,Field
from app import library_api,library_store
from app.library_policy import LibraryMetadata,can_view
from app.business_roles import DEPARTMENTS
from app.business_review import review_reasons, technical_ready

class Action(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    action:str
    expected:int=Field(ge=0)
    note:str=Field(default='',max_length=2000)
    username:str=Field(default='',max_length=100)
    expires_at:int|None=None
    confirm:str=''

class UploadMatch(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    name:str=Field(min_length=1,max_length=200)
    code:str=Field(default='',max_length=200)
    department:str=Field(max_length=100)

def match_title(value):
    value=unicodedata.normalize('NFKC',value).casefold().strip()
    value=re.sub(r'^(?:ext[-–]\d+|qc(?:[-–][a-z]+)+[-–]\d+)[ _\u3000]+','',value)
    value=re.sub(r'\.(docx?|xlsx?|pdf|txt|md|csv|jpe?g|png)$','',value)
    value=re.sub(r'[_\s-]*v\d+(?:\.\d+)*(?:版)?$','',value)
    return re.sub(r'[\s_—–-]+','',value)

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
    def owner(u,b):
        return (u['role']!='guest' and u['username']==b['owner']
                and (u['role']=='boss' or u['department']==b['department']))
    def reviewer(u,b):
        return manager(u,b) and (u['role']=='boss' or not owner(u,b))
    def prepare_index(doc,b):
        return (doc.get('publication_rules') == 1 and b['status']=='submitted'
                and not b.get('deleted') and not b['archived'] and technical_ready(doc))
    def visible(doc,u,*,evidence=False):
        if not u or 'role' not in u:return False
        with central.connect() as c:
            current=library_store.session_by_digest(c,u['session_digest'])
        if not current:return False
        u=current;b=read(doc['id'])
        if not b or b.get('purged'):return False
        if b.get('deleted'):
            return not evidence and (manager(u,b) or owner(u,b) and b['status']=='withdrawn')
        if evidence and (b['status']!='published' or b['archived']):return False
        if u['role']=='boss':return True
        if b['status'] not in {'published','legacy_archived'}:
            return not evidence and ((u['username']==b['owner'] and u['department']==b['department']) or (manager(u,b) and u['username']!=b['owner']))
        with store.connect() as c:
            grant=c.execute('SELECT expires FROM business_grants WHERE document_id=? AND username=?',(doc['id'],u['username'])).fetchone()
        if b.get('company_public'):return True  # Existing public records remain explicitly external-public.
        if u['role']=='guest':return False
        if grant and (grant[0] is None or grant[0]>time.time()):return True
        if b.get('company_internal') and not b.get('restricted'):return True
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
        if getattr(central,'DEMO_LIBRARY_OFFLINE',False) and (path=='/api/rag/provider' and method=='POST'
            or path=='/api/rag/credentials' and method in {'PUT','DELETE'}
            or path=='/api/rag/external-settings' and method=='PUT'):return
        if method=='POST' and path=='/api/rag/answer':
            from app.llm import provider_name
            if getattr(central,'DEMO_LIBRARY_OFFLINE',False) or provider_name()=='ollama':return
        if method=='POST' and path.startswith('/api/documents/') and path.endswith('/review'):
            identifier=path.split('/')[3];b=read(identifier)
            if b and manager(u,b) and b['status']in {'submitted','correction_pending','approved'}:return
        raise HTTPException(403,'业务库仅允许受控提交与审批接口；禁止直接修改、删除或外发')
    store.authorize_operation=operation
    old_schedule=store.schedule_chunks
    def schedule(doc,retry_failed=False):
        b=read(doc['id'])
        if b and (b['status'] in {'approved','published','legacy_archived','correction_pending'} or prepare_index(doc,b)):
            result=old_schedule(doc,retry_failed)
            # A resubmission can reuse an already-complete index without a worker.
            if prepare_index(doc,b) and original_index_status(doc['id']).get('searchable'):
                store.on_index_complete(doc['id'])
            return result
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
        if b['status'] in {'submitted','correction_pending','approved'} and not b.get('deleted') and not b['archived']:
            reasons=review_reasons(doc,b) if doc.get('publication_rules')==1 else []
            result['review_reasons']=reasons
            if doc['state'] in {'review','held','failed'} and not technical_ready(doc):
                result['publication_stage']='解析异常'
                issues=(doc.get('result') or {}).get('issues',[])
                result['parse_reasons']=[item['message'] for item in issues[:4]]
            elif not technical_ready(doc):
                result['publication_stage']='解析处理中'
            elif b['status']=='approved':
                result['publication_stage']='待发布'
            elif reasons or b['status']=='submitted' and doc.get('publication_rules')!=1:
                result['publication_stage']='内容待审'
            elif b['status']=='submitted':
                result['publication_stage']='自动发布中'
            else:
                result['publication_stage']='勘误处理中'
            index=original_index_status(doc['id'])
            if index.get('status')=='failed':
                result['index_error']=index.get('message') or '索引失败，请重试。'
        if b['archived']:result['lifecycle']='已废止'
        if b.get('deleted'):result['status']='回收站'
        elif b['archived']:result['status']='历史归档'
        elif b['status']=='published' and doc.get('publication_rules')==1 and technical_ready(doc):
            if result['technical_index_ready']:
                result['status']='可检索'
        elif b['status']!='published':result['status']=result.get('publication_stage') or {'submitted':'待业务审核','approved':'审批通过待发布','returned':'已退回','correction_pending':'勘误处理中','taken_down':'已下架','withdrawn':'已撤回'}.get(b['status'],b['status'])
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
            if not isinstance(m,dict) or set(m)-{'name','code','version','department','classification','replaces','replaces_expected'}:raise ValueError()
            if 'replaces_expected' in m and (type(m['replaces_expected']) is not int or m['replaces_expected']<0 or not m.get('replaces')):raise ValueError()
            if m.get('replaces')is not None and (not isinstance(m['replaces'],str) or str(uuid.UUID(m['replaces']))!=m['replaces']):raise ValueError()
            dept=m.get('department') if u['role']=='boss' else u['department']
            if dept not in DEPARTMENTS or (u['role']!='boss' and m.get('department',dept)!=dept):raise ValueError()
            m.setdefault('code', '')
            if not isinstance(m['code'],str) or len(m['code'])>200:raise ValueError()
            m['code']=m['code'].strip()
            for key in ['name','version']:
                if not isinstance(m.get(key),str)or not m[key].strip()or len(m[key])>200:raise ValueError()
            classification=m.get('classification','内部')
            if classification not in {'内部','机密'}:raise ValueError()
        except (ValueError,TypeError):raise HTTPException(422,'提交字段无效；部门由身份决定，公开须另行批准')from None
        previous=None
        replacing_failed=False
        with store.LOCK:
            if m.get('replaces'):
                previous=read(m['replaces'])
                replacing_failed=bool(previous and previous['status'] in {'submitted','approved'} and store.get(m['replaces'])['state']=='failed')
                if not previous or previous['department']!=dept or not visible(store.get(m['replaces']),u) or (previous['status']not in {'published','returned','withdrawn','taken_down'} and not replacing_failed) or previous.get('deleted')or previous['archived']:raise HTTPException(409,'不能替换此文档版本')
                if 'replaces_expected' in m and m['replaces_expected']!=previous['version']:raise HTTPException(409,'原资料已变化，请重新检查匹配结果')
                with store.connect()as c:old_meta=library_store.read(c,m['replaces'])[1]
                if not m['code']:m['code']=old_meta.code
                if m['code']!=old_meta.code or (m['version']==old_meta.version and previous['status']!='withdrawn' and not replacing_failed):raise HTTPException(409,'新版本须保留文档编号并使用不同版本号')
                if old_meta.classification=='机密'and classification!='机密':raise HTTPException(422,'新版本不得降低原机密级别；扩大读取须另行明确批准')
                if previous['owner']!=u['username'] and not manager(u,previous):raise HTTPException(403,'仅上传者或主管可提交新版本')
                with store.connect()as c:
                    for r in c.execute('SELECT body FROM business_documents'):
                        v=json.loads(r[0])
                        if v['series']==previous['series'] and not(v==previous and (previous['status']=='returned' or replacing_failed)) and not v.get('deleted') and v['status']in {'submitted','approved','returned','correction_pending'}:raise HTTPException(409,'已有未发布的新版本')
            else:
                with store.connect()as c:
                    if m['code'] and any(json.loads(r[0]).get('code')==m['code'] for r in c.execute('SELECT body FROM library_metadata')):raise HTTPException(409,'文档编号已存在，请使用上传新版本或联系主管')
        # Native parser/storage, never client-supplied text/chunks or vector data.
        response=(await store.upload(files=[file],mode='keep' if previous else 'ask',replace_id=''))[0]
        if response['status']!='accepted':raise HTTPException(409,response['message'])
        identifier=response['id']
        with store.LOCK:
            doc=store.get(identifier)
            meta=LibraryMetadata(code=m['code'],name=m['name'],folder=dept,department=dept,doc_type='业务资料',classification=classification,version=m['version'],lifecycle='现行有效',viewers=(u['identity'],)if classification=='机密'else())
            b=dict(version=0,owner=u['username'],department=dept,series=previous['series']if previous else str(uuid.uuid4()),replaces=(previous.get('replaces') if previous and (previous['status'] in {'returned','withdrawn'} or replacing_failed) else m.get('replaces')),revises=m.get('replaces'),status='submitted',archived=False,deleted=False,company_public=False,restricted=classification=='机密',legacy=False,approved_by=None,approved_fingerprint=None)
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
                    if not previous and meta.code and any(json.loads(row[0]).get('code')==meta.code
                                            for row in c.execute('SELECT body FROM library_metadata')):
                        raise ValueError('Document code already exists')
                    library_store.write(c,identifier,meta,0)
                    if previous:
                        latest=read(m['replaces'],c)
                        if not latest or latest['version']!=previous['version']:raise ValueError('Previous version changed')
                        if previous['status'] in {'returned','withdrawn'} or replacing_failed:
                            previous.update(status='withdrawn',archived=True,version=previous['version']+1)
                            c.execute('UPDATE business_documents SET body=? WHERE document_id=?',(json.dumps(previous,ensure_ascii=False),m['replaces']))
                            c.execute('INSERT INTO business_events(document_id,at,actor,action,body)VALUES(?,?,?,?,?)',(m['replaces'],time.time(),u['username'],'replaced_submission',json.dumps({'version':previous['version'],'new_document':identifier})))
                    b['version']=1
                    c.execute('INSERT INTO business_documents VALUES (?,?)',(identifier,json.dumps(b,ensure_ascii=False)))
                    c.execute('INSERT INTO business_events(document_id,at,actor,action,body)VALUES(?,?,?,?,?)',(identifier,time.time(),u['username'],'submitted',json.dumps({'version':1,'revises':m.get('replaces')})))
            except Exception:
                store.delete(identifier)
                raise HTTPException(409,'提交冲突，未发布本次文件，请检查是否已有待审版本')from None
            doc['publication_rules']=1
            store.save(doc)
            store.schedule_chunks(doc)
        return summary(doc)

    def publish(doc,b,u,*,reviewed=False,automatic=False):
        identifier=doc['id']
        if not technical_ready(doc) or not original_index_status(identifier).get('searchable'):
            raise HTTPException(409,'解析或索引尚未就绪')
        with store.connect()as c:
            if b.get('replaces'):
                old=read(b['replaces'],c)
                if not old or old['status'] not in {'published','taken_down'} or old['archived'] or old.get('deleted'):
                    raise HTTPException(409,'上一版本已变化')
                if old.get('restricted') and not b.get('restricted'):
                    raise HTTPException(409,'原资料的查看限制已变化，请按最新限制重新上传')
                if b.get('correction'):
                    edit=c.execute('SELECT previous_version FROM business_edits WHERE document_id=?',(identifier,)).fetchone()
                    if not edit or old['version']!=edit[0]:
                        raise HTTPException(409,'原生效版本或授权已变化，请重新提交勘误')
                    c.execute('UPDATE business_edits SET completed=? WHERE document_id=?',(time.time(),identifier))
                old.update(archived=True,version=old['version']+1)
                c.execute('UPDATE business_documents SET body=? WHERE document_id=?',
                          (json.dumps(old,ensure_ascii=False),b['replaces']))
            reasons=review_reasons(doc,b) if reviewed and doc.get('publication_rules')==1 else []
            if reasons:
                b['restricted']=True
                b.pop('read_jobs',None)
                meta_row=library_store.read(c,identifier)
                library_store.write(c,identifier,replace(meta_row[1],classification='机密'),meta_row[0])
            b.pop('auto_publish_error',None)
            b.update(status='published',published_by=u['username'],version=b['version']+1)
            c.execute('UPDATE business_documents SET body=? WHERE document_id=?',
                      (json.dumps(b,ensure_ascii=False),identifier))
            event='publish_version' if b.get('replaces') else 'publish'
            c.execute('INSERT INTO business_events(document_id,at,actor,action,body)VALUES(?,?,?,?,?)',
                      (identifier,time.time(),u['username'],event,json.dumps({
                          'previous':b.get('replaces'),'version':b['version'],'reviewed':reviewed,'automatic':automatic,
                          'note':'检查通过，已自动发布' if automatic else '',
                          'approved_by':b.get('approved_by'),'review_reasons':reasons},ensure_ascii=False)))
        return None if automatic else summary(doc)

    old_complete=getattr(store,'on_index_complete',lambda identifier:True)
    def auto_publish(identifier):
        result=old_complete(identifier)
        with store.LOCK:
            doc=store.get(identifier);b=read(identifier)
            if not b or not prepare_index(doc,b) or review_reasons(doc,b):return result
            if not original_index_status(identifier).get('searchable'):return False
            # Background publication uses current account authority, never a saved session.
            with central.connect()as c:
                row=c.execute('SELECT a.username,p.role,p.department FROM library_accounts a JOIN business_profiles p ON p.username=a.username WHERE a.username=? AND a.active=1',(b['owner'],)).fetchone()
            u=dict(row) if row else None
            try:
                if not u or not owner(u,b):
                    raise HTTPException(409,'上传者的账号或部门已变化，请联系本部门主管处理')
                publish(doc,b,u,automatic=True)
            except HTTPException as exc:
                if b.get('auto_publish_error')!=exc.detail:
                    b['auto_publish_error']=exc.detail
                    write(identifier,b,{'username':b['owner']},'auto_publish_blocked',exc.detail)
            return result
    store.on_index_complete=auto_publish

    @store.app.post('/api/business/documents/{identifier}/action')
    def action(identifier:str,body:Action):
        u=user()
        with store.LOCK:
            doc=store.get(identifier);b=read(identifier)
            if not b or not(visible(doc,u) or (body.action=='purge' and u['role']=='boss' and b.get('deleted'))):raise HTTPException(404,'文档不可访问')
            if b['version']!=body.expected:raise HTTPException(409,'文档状态已变化，请刷新')
            a=body.action
            if a in {'approve','return','publish','approve_publish','withdraw','take_down','retry_index'}:
                if b.get('deleted')or b['archived']:raise HTTPException(409,'归档或回收站文件不能发布')
            if a=='withdraw':
                if not owner(u,b) or b['status'] not in {'submitted','approved','returned'}:
                    raise HTTPException(403,'仅上传者可撤回本人未发布的提交')
                b.update(status='withdrawn',approved_by=None,approved_fingerprint=None)
            elif a=='take_down':
                own_regular=(owner(u,b) and b.get('published_by')==u['username']
                             and not b['restricted'] and not b['company_public'] and not b.get('company_internal'))
                if not (manager(u,b) or own_regular):
                    raise HTTPException(403,'无权下架此文档')
                if b['status']!='published':
                    raise HTTPException(409,'仅可下架现行文档')
                if not body.note.strip():
                    raise HTTPException(422,'请填写下架原因')
                b.update(status='taken_down',company_public=False,company_internal=False)
            elif a=='retry_index':
                if not (owner(u,b) or manager(u,b)):
                    raise HTTPException(403,'无权重试索引')
                if b['status'] not in {'submitted','approved','correction_pending'} or not technical_ready(doc):
                    raise HTTPException(409,'当前资料不能重试索引')
                if original_index_status(identifier).get('status')!='failed':
                    raise HTTPException(409,'当前索引未处于失败状态')
                chunk_run=store.load_chunk_run(identifier)
                if chunk_run and chunk_run['status']=='complete' and store.INDEX_SERVICE is not None:
                    store.INDEX_SERVICE.schedule(identifier,retry=True)
                else:
                    store.schedule_chunks(doc,retry_failed=True)
                return summary(doc)
            elif a=='cancel_correction':
                if not b.get('correction')or b['status']!='correction_pending'or b['owner']!=u['username']:raise HTTPException(403,'仅本人可取消未生效勘误')
                b.update(status='withdrawn',archived=True);write(identifier,b,u,'cancel_correction')
                return summary(doc)
            elif a=='retry_parse':
                if not (owner(u,b) or manager(u,b)) or b['status'] not in {'submitted','correction_pending','approved'} or doc['state']!='failed' or b.get('deleted') or b['archived']:raise HTTPException(403,'仅上传者或归属主管可重试当前解析失败资料')
                b.update(status='correction_pending'if b.get('correction')else'submitted',approved_by=None,approved_fingerprint=None)
                write(identifier,b,u,'retry_parse')
                store.retry(identifier)
                return summary(store.get(identifier))
            elif a=='return':
                assert_write(u,b)
                if b['status'] not in {'submitted','correction_pending'} or not body.note.strip():raise HTTPException(409,'退回须提供原因且处于待审状态')
                b.update(status='returned',approved_by=None,approved_fingerprint=None)
            elif a=='resubmit':
                if b['owner']!=u['username'] or b['status']!='returned':raise HTTPException(403,'仅本人可重新提交被退回资料')
                b.update(status='correction_pending' if b.get('correction') else 'submitted')
            elif a in {'approve','approve_publish'}:
                assert_write(u,b)
                if b['status'] not in {'submitted','correction_pending'} or not technical_ready(doc):
                    raise HTTPException(409,'请先完成解析及必要的技术复核')
                reasons=review_reasons(doc,b) if doc.get('publication_rules')==1 else []
                if reasons and not reviewer(u,b):
                    raise HTTPException(403,'主管本人提交的高风险资料须由管理层负责人审核')
                if b['status']=='correction_pending' and not reasons:
                    raise HTTPException(409,'常规勘误会自动生效')
                if a=='approve_publish' and not reasons:
                    raise HTTPException(409,'此文档可走普通发布流程')
                b.update(approved_by=u['username'],approved_fingerprint=store.fingerprint(doc))
                if a=='approve_publish':
                    return publish(doc,b,u,reviewed=True)
                b['status']='approved'
            elif a=='publish':
                if not (owner(u,b) or manager(u,b)):
                    raise HTTPException(403,'仅上传者或本部门主管可发布')
                if b['status']=='approved':
                    assert_write(u,b)
                    if b['approved_fingerprint']!=store.fingerprint(doc):
                        raise HTTPException(409,'审批对应的文件已变化')
                    if doc.get('publication_rules')==1 and review_reasons(doc,b) and not reviewer(u,b):
                        raise HTTPException(403,'主管本人提交的高风险资料须由管理层负责人发布')
                    return publish(doc,b,u,reviewed=True)
                if not prepare_index(doc,b) or review_reasons(doc,b):
                    raise HTTPException(409,'资料尚未完成所需审核或解析检查')
                return publish(doc,b,u)
            elif a in {'archive','trash','restore'}:
                if not (a in {'trash','restore'} and owner(u,b) and b['status']=='withdrawn'):assert_write(u,b)
                if a=='archive':b['archived']=True
                elif a=='trash':b['deleted']=True
                else:b['deleted']=False
            elif a in {'share','revoke_share'}:
                assert_write(u,b)
                if a=='share'and(b['status']!='published'or b['archived']or b['deleted']):raise HTTPException(409,'仅可借阅当前已发布资料')
                if b.get('restricted'):
                    if u['role']!='boss':raise HTTPException(403,'受限资料共享需老板明确授权')
                with central.connect()as c:target=c.execute('SELECT a.active,p.role FROM library_accounts a LEFT JOIN business_profiles p ON p.username=a.username WHERE a.username=?',(body.username,)).fetchone()
                if not target or not target[0]:raise HTTPException(422,'目标账号不可用')
                if a=='share' and target[1] not in {'employee','supervisor','boss'}:raise HTTPException(403,'仅可向内部成员授权借阅；访客只能查看对外公开资料')
                if a=='share' and body.expires_at is not None and body.expires_at<=time.time():raise HTTPException(422,'授权已过期')
                with store.connect()as c:
                    if a=='share':c.execute('INSERT OR REPLACE INTO business_grants VALUES (?,?,?)',(identifier,body.username,body.expires_at))
                    else:c.execute('DELETE FROM business_grants WHERE document_id=? AND username=?',(identifier,body.username))
                    b['version']+=1
                    c.execute('UPDATE business_documents SET body=? WHERE document_id=?',(json.dumps(b,ensure_ascii=False),identifier))
                    c.execute('INSERT INTO business_events(document_id,at,actor,action,body)VALUES(?,?,?,?,?)',(identifier,time.time(),u['username'],a,json.dumps({'username':body.username,'expires_at':body.expires_at,'version':b['version']},ensure_ascii=False)))
                return summary(doc)
            elif a in {'make_public','revoke_public','make_internal','revoke_internal'}:
                if u['role']!='boss':raise HTTPException(403,'仅管理层负责人可调整公司级可见范围')
                if a in {'make_public','make_internal'} and (b['status']!='published' or b['archived'] or b.get('deleted')
                                         or b.get('restricted')):
                    raise HTTPException(409,'只有现行且符合公开条件的资料可以公开')
                if a=='make_public':b.update(company_public=True,company_internal=False)
                elif a=='make_internal':b.update(company_internal=True,company_public=False)
                elif a=='revoke_public':b['company_public']=False
                else:b['company_internal']=False
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
            if a in {'approve','resubmit'}:store.schedule_chunks(doc)
            return summary(doc)

    @store.app.get('/api/business/recent-operations')
    def recent_operations():
        u=user()
        if u['role']!='boss':raise HTTPException(403,'仅管理层负责人可查看全公司操作记录')
        with store.connect() as c:
            rows=c.execute('SELECT e.id,e.document_id,e.at,e.actor,e.action,e.body,d.body AS document_body FROM business_events e LEFT JOIN documents d ON d.id=e.document_id ORDER BY e.at DESC,e.id DESC LIMIT 8').fetchall()
        result=[]
        for row in rows:
            details=json.loads(row['body'])
            document=json.loads(row['document_body']) if row['document_body'] else {}
            result.append(dict(id=row['id'],at=row['at'],actor=row['actor'],action=row['action'],
                               document_name=document.get('name') or '已移除的资料',
                               note=str(details.get('note') or details.get('reason') or '')[:500],
                               recipient=str(details.get('username') or '')))
        return result

    @store.app.get('/api/business/documents/{identifier}/audit')
    def audit(identifier:str):
        u=user();b=read(identifier)
        if not b or not(manager(u,b)or b['owner']==u['username']):raise HTTPException(404,'不可查看审计')
        with store.connect()as c:return [dict(r)for r in c.execute('SELECT at,actor,action,body FROM business_events WHERE document_id=? ORDER BY id',(identifier,))]

    @store.app.post('/api/business/upload-match')
    def upload_match(body:UploadMatch):
        u=user()
        if u['role']=='guest':raise HTTPException(403,'访客不能上传')
        dept=body.department if u['role']=='boss' else u['department']
        if dept not in DEPARTMENTS or dept!=body.department:raise HTTPException(422,'部门与当前身份不符')
        matches=[]
        for doc in store.all_docs():
            b=read(doc['id'])
            if not b or b['department']!=dept or b['deleted'] or b['archived'] or not (owner(u,b) or manager(u,b)) or not visible(doc,u):continue
            with store.connect()as c:record=library_store.read(c,doc['id'])
            if not record:continue
            meta=record[1]
            same_code=bool(body.code.strip() and body.code.strip()==meta.code)
            if not same_code and match_title(body.name)!=match_title(meta.name):continue
            can_replace=b['status'] in {'published','returned','withdrawn','taken_down'} or b['status'] in {'submitted','approved'} and doc['state']=='failed'
            matches.append({'id':doc['id'],'name':meta.name,'code':meta.code,'version':meta.version,
              'department':dept,'classification':'机密' if b['restricted'] else meta.classification,
              'expected':b['version'],'status':b['status'],'failed':doc['state']=='failed',
              'can_replace':can_replace,'reason':'编号相同' if same_code else '名称相同或仅版本后缀不同'})
        return matches

    @store.app.get('/api/business/documents/{identifier}/borrowers')
    def borrowers(identifier:str):
        u=user();b=read(identifier)
        if not b or not manager(u,b) or not visible(store.get(identifier),u):raise HTTPException(404,'不可管理此资料借阅')
        if b['restricted'] and u['role']!='boss':raise HTTPException(403,'机密资料借阅由管理层负责人管理')
        if b['status']!='published' or b['archived'] or b['deleted']:raise HTTPException(409,'仅管理当前已发布资料的借阅')
        with store.connect()as c:grants={r[0]:r[1] for r in c.execute('SELECT username,expires FROM business_grants WHERE document_id=?',(identifier,)) if r[1] is None or r[1]>time.time()}
        with central.connect()as c:
            return [dict(username=r[0],role=r[1],department=r[2],job=r[3],granted=r[0] in grants,expires_at=grants.get(r[0])) for r in c.execute("SELECT p.username,p.role,p.department,p.job FROM business_profiles p JOIN library_accounts a ON a.username=p.username WHERE a.active=1 AND p.role IN ('employee','supervisor','boss') ORDER BY p.department,p.username")]
    from app.knowledge_gaps import install as install_gaps
    install_gaps(store,user,read,visible)
    from app.qa_feedback import install as install_feedback
    install_feedback(store,user,visible)
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
    single_library=cfg.get('demo_offline') is True
    q.INDEX_SERVICE=IndexService(q) if single_library else SharedModelIndex(q)
    if not single_library:
        shared=central.require_semantic().provider
        if q.INDEX_SERVICE.config!=shared.config:raise RuntimeError('业务与基线模型配置不同，停止打开业务库')
        q.INDEX_SERVICE.provider=shared
    install(q,central,legacy_acl)
    # Business RAG remains local-only irrespective of personal credentials.
    from app.datasets import LocalRag
    services={}
    if single_library:
        from app.external_model import QuestionOnlyRag, install_admin
        install_admin(q,central)
    def current_rag():
        u=library_api.principal.get()
        if not u:raise HTTPException(401,'请登录')
        with central.connect()as c:
            if not library_store.session_by_digest(c,u['session_digest']):raise HTTPException(401,'会话已失效')
        if u['session_digest']not in services:
            if len(services)>64:services.clear()
            services[u['session_digest']]=(QuestionOnlyRag(q,central) if single_library else LocalRag(q,lambda **v:None))
        return services[u['session_digest']]
    q.current_rag=current_rag
    for doc in q.all_docs():
        if doc['state']in q.STATES:
            doc.update(state='failed',quality='failed',error='上次业务处理被中断，请重新提交新版本；未发布。');q.save(doc)
        b=q.business_read(doc['id'])
        if (b and technical_ready(doc)
                and (b['status'] in {'approved','correction_pending'}
                     or b['status']=='submitted' and doc.get('publication_rules')==1)):
            q.schedule_chunks(doc,retry_failed=True)
    q.INDEX_SERVICE.recover()
    if not hasattr(central,'BUSINESS_CHILDREN'):central.BUSINESS_CHILDREN=[]
    central.BUSINESS_CHILDREN.append(q)
    return q
