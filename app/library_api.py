"""Access boundary for managed libraries; legacy databases remain unchanged."""
from contextvars import ContextVar
from dataclasses import asdict
import json
import os
from fastapi import APIRouter, HTTPException, Request, Response, Query, File, UploadFile, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from app import library_store
from app.library_policy import LibraryMetadata, can_view, can_use_as_evidence

principal = ContextVar('library_principal', default=None)
DELETED_STATES = {'deleted', 'deleting', 'delete_failed', 'superseded'}


def metadata(store, identifier):
    if hasattr(store, 'metadata_overlay'):
        return store.metadata_overlay(identifier)
    with store.connect() as conn:
        return library_store.read(conn, identifier)


def visible(store, doc, *, evidence=False):
    user = principal.get()
    if hasattr(store, 'authorize_document'):
        return store.authorize_document(doc, user, evidence=evidence)
    if user is None:
        return True  # Legacy HTTP mode or trusted background worker.
    with store.connect() as conn:
        if not library_store.session_by_digest(conn, user['session_digest']):
            return False
    row = metadata(store, doc['id'])
    if row is None:
        return user['manager'] and not evidence
    return (can_use_as_evidence if evidence else can_view)(row[1], user['identity'])


def visible_ids(store, docs, *, evidence=False):
    """Visibility for a whole list with one session check and one metadata read.

    Same rules as visible(); only the query pattern changes, which removes two
    queries per document from every list request.
    """
    user = principal.get()
    if hasattr(store, 'authorize_document'):
        return {doc['id'] for doc in docs if store.authorize_document(doc, user, evidence=evidence)}
    if user is None:
        return {doc['id'] for doc in docs}
    with store.connect() as conn:
        if not library_store.session_by_digest(conn, user['session_digest']):
            return set()
        rows = {row[0]: json.loads(row[1])
                for row in conn.execute('SELECT document_id, body FROM library_metadata')}
    allowed = set()
    for doc in docs:
        meta = rows.get(doc['id'])
        if meta is None:
            if user['manager'] and not evidence:
                allowed.add(doc['id'])
            continue
        checker = can_use_as_evidence if evidence else can_view
        if checker(LibraryMetadata(**{**meta, 'viewers': tuple(meta.get('viewers') or ())}), user['identity']):
            allowed.add(doc['id'])
    return allowed



def external_allowed(store, doc):
    if getattr(store, 'READ_ONLY_LIBRARY', False):
        return False
    if principal.get() is None:
        return True
    row = metadata(store, doc['id'])
    return bool(row and row[1].classification != '机密' and visible(store, doc, evidence=True))


class LoginBody(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)


class MetadataBody(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    expected_version: int = Field(ge=0)
    code: str = Field(default='', max_length=200)
    name: str = Field(min_length=1, max_length=200)
    folder: str = Field(min_length=1, max_length=500)
    department: str = Field(min_length=1, max_length=100)
    doc_type: str = Field(min_length=1, max_length=100)
    classification: str
    version: str = Field(min_length=1, max_length=100)
    lifecycle: str
    viewers: list[str] = Field(default_factory=list, max_length=10)


class DemoBody(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    identity: str


class CatalogBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=100)


def library_record(store, doc):
    row = metadata(store, doc['id'])
    meta = row[1] if row else None
    parsed = doc.get('result') or {}
    issues = [x.get('message','需要核对') for x in parsed.get('issues',[])]
    if doc.get('error'): issues.append(doc['error'])
    if doc.get('state') in {'review','held'} and not issues: issues.append('等待人工复核')
    searchable = bool(store.index_status(doc['id']).get('searchable'))
    if not meta: status='待分类'
    elif meta.lifecycle == '已废止': status='已停用检索'
    elif doc['state'] in store.STATES: status='处理中'
    elif doc['state'] == 'failed': status='处理失败'
    elif doc['state'] in {'review','held'}: status='待复核'
    elif searchable: status='可检索'
    else: status='待建索引'
    result=dict(id=doc['id'], name=meta.name if meta else doc['name'], code=meta.code if meta else '',
        folder=meta.folder if meta else '未分类', department=meta.department if meta else '未分类',
        docType=meta.doc_type if meta else '未分类', classification=meta.classification if meta else '未分类',
        version=meta.version if meta else '', effectiveDate='已废止' if meta and meta.lifecycle=='已废止' else '',
        reviewSearchable=bool(searchable and doc['state']=='review'),
        reviewCompleted=bool(doc['state'] in {'ready','held'} and doc.get('revision') is not None and (doc.get('review_decision') or {}).get('revision')==doc.get('revision')), status=status, qcIssues=issues, viewers=list(meta.viewers) if meta else [],
        preview='\n\n'.join(x.get('text','') for x in parsed.get('blocks',[]))[:30000],
        format=doc.get('ext','').lstrip('.').upper(), createdAt=doc['created_at'], metadataVersion=row[0] if row else 0,
        lifecycle=meta.lifecycle if meta else '现行有效')

    if hasattr(store,'decorate_library_record'):store.decorate_library_record(doc,result)
    return result

def install(app, store):
    router = APIRouter()

    @app.middleware('http')
    async def access_guard(request, call_next):
        if not request.url.path.startswith('/api/'):
            return await call_next(request)
        with getattr(store, 'AUTH_STORE', store).connect() as conn:
            managed = library_store.enabled(conn)
            auth = request.headers.get('authorization', '')
            credential = auth[7:] if auth.startswith('Bearer ') else request.cookies.get('p18_session', '')
            user = library_store.resolve_session(conn, credential) if managed and credential else None
        if not managed:
            if request.url.path.startswith('/api/library'):
                return JSONResponse({'detail': '文件库权限模式尚未启用'}, status_code=409)
            if request.url.path not in {'/api/config','/api/semantic'} and os.environ.get('P18_ALLOW_LEGACY_OPEN') != '1':
                return JSONResponse({'detail':'权限模式尚未初始化，请使用正常账号初始化流程'}, status_code=503)
            return await call_next(request)
        if (request.url.path == '/api/library/login' and request.method == 'POST') or (request.url.path in {'/api/library/demo-login','/api/library/demo-fill','/api/library/activate-account'} and request.method == 'POST') or (request.url.path == '/api/library/demo-accounts' and request.method == 'GET'):
            return await call_next(request)
        if request.url.path == '/api/library/demo-session' and request.method == 'POST':
            return await call_next(request)
        if user is None:
            return JSONResponse({'detail': '请使用有效的登录会话'}, status_code=401)
        token = principal.set(user)
        try:
            path = request.url.path
            permitted_posts = {'/api/business/accounts/reinvite','/api/business/accounts','/api/business/people','/api/rag/provider','/api/rag/fallback', '/api/rag/credentials', '/api/library/datasets', '/api/search', '/api/library/logout', '/api/rag/prepare',
                               '/api/rag/drafts', '/api/rag/selection', '/api/rag/answer'}
            demo_create = user.get('demo') and request.method == 'POST' and path in {'/api/library/upload','/api/library/catalog/folders'}
            if hasattr(store,'authorize_operation'):
                try:store.authorize_operation(user,request.method,path)
                except HTTPException as exc:return JSONResponse({'detail':exc.detail},status_code=exc.status_code)
            elif request.method not in {'GET','HEAD','OPTIONS'} and path not in permitted_posts and not user['manager'] and not demo_create:
                return JSONResponse({'detail': '需要文档管理权限'}, status_code=403)
            if path.startswith('/api/documents/'):
                identifier = path.split('/')[3]
                try:
                    doc = store.get(identifier)
                except HTTPException:
                    return JSONResponse({'detail': '文档不存在或不可访问'}, status_code=404)
                if not visible(store, doc):
                    return JSONResponse({'detail': '文档不存在或不可访问'}, status_code=404)
                row = metadata(store, identifier)
                if path.endswith('/external-permission') and (not row or row[1].classification == '机密' or row[1].lifecycle != '现行有效'):
                    return JSONResponse({'detail': '该资料不允许外发'}, status_code=403)
            response = await call_next(request)
            response.headers['Cache-Control'] = 'no-store'
            return response
        finally:
            principal.reset(token)

    @router.get('/api/library/documents')
    def list_records(response: Response, limit: int | None = Query(None, ge=1, le=200), offset: int = Query(0, ge=0)):
        # Keep strict per-document index_status, never the delivery's relaxed status_many.
        with store.LOCK:
            docs=[d for d in store.all_docs() if d['state'] not in {'deleted','deleting','delete_failed','superseded'}]
            allowed=visible_ids(store,docs)
            visible_docs=[d for d in docs if d['id'] in allowed]
            page=visible_docs if limit is None else visible_docs[offset:offset+limit]
            records=[library_record(store,d) for d in page]
            # Account revocation may commit outside the data lock. Recheck before return.
            final_allowed=visible_ids(store,docs)
            records=[r for r in records if r['id'] in final_allowed]
        response.headers['X-Total-Count']=str(sum(d['id'] in final_allowed for d in docs))
        return records

    @router.get('/api/library/catalog/{kind}')
    def catalog(kind: str):
        if kind not in {'folders','types'}: raise HTTPException(404)
        attr = 'folder' if kind=='folders' else 'doc_type'
        names=set()
        with store.connect() as conn:
            if principal.get()['manager']:
                names.update(r[0] for r in conn.execute('SELECT name FROM library_catalog WHERE kind=?',(kind,)))
        if kind=='folders':
            with store.connect() as conn:
                names.update(r[0] for r in conn.execute('SELECT name FROM library_folder_creators WHERE identity=?',(principal.get()['identity'],)))
        for doc in store.all_docs():
            if doc['state'] in {'deleted','deleting','delete_failed','superseded'} or not visible(store,doc): continue
            row=metadata(store,doc['id'])
            if row:names.add(getattr(row[1],attr))
        if kind=='types':names.update(['制度','规程','报告','技术文档','名册','报表','预案','FAQ'])
        return [{'id':name,'name':name} for name in sorted(names)]

    @router.post('/api/library/catalog/{kind}')
    def create_catalog(kind: str, body: CatalogBody):
        if kind not in {'folders','types'}: raise HTTPException(404)
        name=body.name.strip()
        if not name: raise HTTPException(422,'名称不能为空')
        if name in {x['name'] for x in catalog(kind)}: raise HTTPException(409,'名称已存在')
        import sqlite3
        try:
            with store.connect() as conn:
                conn.execute('INSERT INTO library_catalog VALUES (?,?)',(kind,name))
                if kind=='folders':conn.execute('INSERT INTO library_folder_creators VALUES (?,?)',(name,principal.get()['identity']))
        except sqlite3.IntegrityError:raise HTTPException(409,'名称已存在') from None
        return {'id':name,'name':name}

    @router.post('/api/library/upload')
    async def upload_document(file: UploadFile = File(...), metadata_json: str = Form(...)):
        from pydantic import ValidationError
        try:
            body=MetadataBody.model_validate_json(metadata_json)
            values=body.model_dump(exclude={'expected_version'});values['viewers']=tuple(values['viewers'])
            meta=LibraryMetadata(**values)
            if not can_view(meta,principal.get()['identity']):raise ValueError('不能创建自己无权查看的资料')
        except (ValueError,ValidationError) as exc:raise HTTPException(422,'分类信息无效：'+str(exc)) from None
        result=(await store.upload(files=[file],mode='ask',replace_id=''))[0]
        if result['status']!='accepted':raise HTTPException(409,result['message'])
        # A failed metadata write leaves a manager-only, unsearchable unclassified upload.
        with store.LOCK,store.connect() as conn:library_store.write(conn,result['id'],meta,0)
        return library_record(store,store.get(result['id']))

    @router.post('/api/library/demo-session')
    def demo_session(body: DemoBody, request: Request):
        from app.library_policy import IDENTITIES
        from hashlib import sha256
        with store.LOCK, store.connect() as conn:
            if not library_store.demo_enabled(conn): raise HTTPException(404, '未启用演示环境')
            if body.identity not in IDENTITIES: raise HTTPException(422, '未知演示身份')
            auth=request.headers.get('authorization','')
            old=auth[7:] if auth.startswith('Bearer ') else request.cookies.get('p18_session','')
            if old:
                library_store.revoke_session(conn,old)
                store.MANAGED_RAG.pop(sha256(old.encode()).hexdigest(),None)
            credential=library_store.issue_session(conn,body.identity,manager=False)
            conn.execute('UPDATE library_sessions SET demo=1 WHERE digest=?',(sha256(credential.encode()).hexdigest(),))
        response=JSONResponse({'identity':body.identity,'manager':False,'demo':True})
        response.set_cookie('p18_session',credential,httponly=True,samesite='strict',max_age=3600,path='/')
        response.headers['Cache-Control']='no-store'
        return response

    @router.post('/api/library/login')
    def login(body: LoginBody, request: Request):
        consume=getattr(store,'consume_demo_login',lambda *a:None)
        credential=consume(request,body.username,body.password)
        if credential is None:
            with store.connect() as conn:
                credential = library_store.login(conn, body.username, body.password)
        if not credential:
            raise HTTPException(401, '账号或密码无效，连续失败后请稍后重试')
        response = JSONResponse({'authenticated': True})
        response.set_cookie('p18_session', credential, httponly=True, samesite='strict', max_age=3600, path='/')
        from app.business_roles import profile
        with store.connect()as c:business_profile=profile(c,body.username)
        response.delete_cookie('p18_demo_challenge',path='/')
        response.set_cookie('p18_dataset','business' if business_profile and (store.ROOT/'config/business.json').is_file() else 'demo',httponly=True,samesite='strict',path='/')
        response.headers['Cache-Control'] = 'no-store'
        return response

    @router.post('/api/library/logout')
    def logout(request: Request):
        auth = request.headers.get('authorization', '')
        credential = auth[7:] if auth.startswith('Bearer ') else request.cookies.get('p18_session', '')
        with store.connect() as conn:
            library_store.revoke_session(conn, credential)
        with store.LOCK:
            store.MANAGED_RAG.pop(principal.get()['session_digest'], None)
        response = JSONResponse({'authenticated': False})
        response.delete_cookie('p18_session', path='/')
        return response

    @router.get('/api/library/me')
    def me():
        user = principal.get()
        from app.enterprise_accounts import can_create_accounts
        return dict(identity=user['identity'], username=user.get('username') or '',
                    manager=user['manager'] and not getattr(store, 'READ_ONLY_LIBRARY', False),
                    **({**{key:user[key] for key in ['role','department','job']},'can_create_accounts':can_create_accounts(user)} if 'role' in user else {}),
                    **({'demo':True} if user.get('demo') else {}))

    @router.get('/api/library/documents/{identifier}/preview')
    def parsed_preview(identifier: str):
        with store.LOCK:
            doc=store.get(identifier)
            if not visible(store,doc): raise HTTPException(404,'文档不存在或不可访问')
            result=doc.get('result') or {}
            return {'revision':doc['revision'],'parser_version':result.get('parser_version'),
                    'sheets':result.get('excel_sheets',[]),'review_policy':result.get('excel_review_policy')}

    @router.get('/api/library/documents/{identifier}')
    def read_metadata(identifier: str):
        doc = store.get(identifier)
        if doc.get('state') in DELETED_STATES:
            raise HTTPException(404, '文档已删除或已被替换')
        if not visible(store, doc):
            raise HTTPException(404, '文档不存在或不可访问')
        row = metadata(store, identifier)
        return {'metadata': asdict(row[1]) if row else None, 'version': row[0] if row else 0}

    @router.put('/api/library/documents/{identifier}')
    def update_metadata(identifier: str, body: MetadataBody):
        # Management capability does not implicitly grant content access.
        doc = store.get(identifier)
        if doc.get('state') in DELETED_STATES:
            raise HTTPException(404, '文档已删除或已被替换')
        if not visible(store, doc):
            raise HTTPException(404, '文档不存在或不可访问')
        values = body.model_dump(exclude={'expected_version'})
        values['viewers'] = tuple(values['viewers'])
        try:
            meta = LibraryMetadata(**values)
            with store.LOCK, store.connect() as conn:
                version = library_store.write(conn, identifier, meta, body.expected_version)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        return {'version': version, 'metadata': asdict(meta)}

    app.include_router(router)
