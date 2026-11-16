"""Two isolated data sources behind the existing local workbench.

Authentication remains in the original library; Qichen business storage is read-only.
The dataset cookie chooses a store, never an identity or an authorization grant.
"""
from pathlib import Path
from dataclasses import replace
import importlib.util, sys, json, sqlite3, threading, time
from http.cookies import SimpleCookie
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from typing import Literal
from app import library_api, library_store
from app.library_policy import can_view
from app.read_only_index import ReadOnlyIndex
from app.rag import RagService

ROLES = {'启辰研发岗位':'研发','启辰测试岗位':'测试','启辰运维岗位':'运维','启辰生产岗位':'生产',
         '研发部员工':'研发','生产制造部员工':'生产'}


class DisabledClient:
    configured = False
    label = '启辰本地证据（禁止外发）'


class LocalRag(RagService):
    def __init__(self, store, logger):
        super().__init__(store, client=DisabledClient())
        self.logger = logger

    def external_allowed(self, doc):
        return False

    def audit_request(self, action, ticket=None, code=None):
        self.logger(action=action, code=code)


class DatasetBody(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    dataset: Literal['demo', 'qichen30']


class DatasetsApp:
    def __init__(self, central):
        self.central = central
        self.qstore = None
        self.lock = threading.RLock()
        self.config_path = central.ROOT/'config/qichen-libraries.json'
        self.log_lock = threading.RLock()

        @central.app.get('/api/library/datasets')
        def datasets(request: Request):
            return {'selected':request.cookies.get('p18_dataset','demo'),
                    'datasets':[{'id':'demo','name':'演示资料库（6份）','read_only':False},
                                *([{'id':'qichen30','name':'启辰智造（30份·只读）','read_only':True}] if self.config().get('enabled',True) else [])]}

        @central.app.post('/api/library/datasets')
        def select_dataset(body: DatasetBody):
            # Original middleware already authenticates and enforces local CSRF headers.
            response=JSONResponse({'dataset':body.dataset,'reload_required':True})
            response.set_cookie('p18_dataset',body.dataset,httponly=True,samesite='strict',path='/')
            response.headers['Cache-Control']='no-store'
            return response

    def log(self, **record):
        user=library_api.principal.get()
        item=dict(at=time.time(),dataset='qichen30',identity=user['identity'] if user else None,**record)
        with self.log_lock:
            with (self.central.DATA/'qichen-access.jsonl').open('a') as stream:
                stream.write(json.dumps(item,ensure_ascii=False)+'\n')

    def config(self):
        # Fresh authorization reads: changing ACL takes effect in existing sessions.
        return json.loads(self.config_path.read_text())

    def user_valid(self, user):
        if not user:return False
        with self.central.connect() as conn:
            return library_store.session_by_digest(conn,user['session_digest']) is not None

    def create_store(self):
        cfg=self.config();data=Path(cfg['data_dir']).resolve()
        if data==self.central.DATA.resolve() or not(data/'workbench.sqlite3').is_file():
            raise RuntimeError('启辰只读数据源路径无效')
        name='app._qichen_store'
        spec=importlib.util.spec_from_file_location(name,self.central.ROOT/'app/main.py')
        q=importlib.util.module_from_spec(spec);sys.modules[name]=q;spec.loader.exec_module(q)
        q.DATA,q.DB=data,data/'workbench.sqlite3'
        q.AUTH_STORE,q.READ_ONLY_LIBRARY=self.central,True
        def connect():
            conn=sqlite3.connect(q.DB.as_uri()+'?mode=ro',uri=True,timeout=15)
            conn.row_factory=sqlite3.Row;conn.execute('PRAGMA query_only=ON');return conn
        q.connect=connect
        def metadata_overlay(identifier):
            with connect() as conn:row=library_store.read(conn,identifier)
            policy=self.config()['acl'].get(identifier)
            if not row or not policy:return None
            # Preserve conservative classification. Actual EXT read grants are explicit ACL below.
            return row
        q.metadata_overlay=metadata_overlay
        def authorize(doc,user,*,evidence=False):
            if not self.user_valid(user):return False
            rule=self.config()['acl'].get(doc['id'])
            if not rule or doc.get('sha256')!=rule['file_sha256']:return False
            row=metadata_overlay(doc['id'])
            if not row or (evidence and row[1].lifecycle!='现行有效'):return False
            role=ROLES.get(user['identity'])
            if rule['roles'] is not None:
                # The unresolved EXT-13 OPS conflict is denied independently of config edits.
                return bool(role and role in rule['roles'] and not(rule['code']=='EXT-13' and role=='运维'))
            # Existing fifteen retain their original department/confidentiality policy.
            parent={'研发':'研发部员工','测试':'研发部员工','运维':'研发部员工','生产':'生产制造部员工'}.get(role,user['identity'])
            return can_view(row[1],parent)
        q.authorize_document=authorize
        q.INDEX_SERVICE=ReadOnlyIndex(q,self.central.require_semantic().provider)
        raw_public=q.public
        def public(doc,detailed=False):
            value=raw_public(doc,detailed)
            value['external_permission']=dict(value['external_permission'],allowed=False,can_review=False,
                notice='启辰只读库未获外发授权；仅可本地查看。')
            return value
        q.public=public
        sessions={}
        def current_rag():
            user=library_api.principal.get()
            if not self.user_valid(user):raise HTTPException(401,'登录会话已失效')
            with self.lock:
                for key in list(sessions):
                    with self.central.connect() as conn:
                        if not library_store.session_by_digest(conn,key):sessions.pop(key,None)
                key=user['session_digest']
                if key not in sessions:
                    if len(sessions)>=64:raise HTTPException(503,'本地会话过多')
                    sessions[key]=LocalRag(q,self.log)
                return sessions[key]
        q.current_rag=current_rag
        @q.app.middleware('http')
        async def readonly_guard(request,call_next):
            allowed={'/api/search','/api/rag/drafts','/api/rag/selection'}
            if request.method not in {'GET','HEAD','OPTIONS'} and request.url.path not in allowed:
                self.log(action='readonly_or_egress_denied',path=request.url.path)
                return JSONResponse({'detail':'启辰库仅限本地只读；禁止修改资料、授予外发许可或调用模型。'},status_code=403,
                                    headers={'Cache-Control':'no-store'})
            response=await call_next(request)
            if response.status_code>=400:self.log(action='request_denied',path=request.url.path,status=response.status_code)
            return response
        # Never run q.lifespan: it would initialize/recover persistent indexes.
        return q

    async def __call__(self,scope,receive,send):
        if scope['type']!='http':
            return await self.central.app(scope,receive,send)
        path=scope['path']
        headers=dict(scope.get('headers',[]));cookies=SimpleCookie()
        try:cookies.load(headers.get(b'cookie',b'').decode())
        except Exception:pass
        selected=cookies['p18_dataset'].value if 'p18_dataset' in cookies else 'demo'
        if selected not in {'demo','qichen30'}:
            return await JSONResponse({'detail':'未知知识库，请重新选择'},status_code=400)(scope,receive,send)
        central_paths={'/api/rag/credentials','/api/library/login','/api/library/logout','/api/library/demo-session','/api/library/datasets'}
        if selected=='qichen30' and path.startswith('/api/') and path not in central_paths:
            if not self.config().get('enabled',True):
                return await JSONResponse({'detail':'当前源码检出未连接已授权的启辰数据源'},status_code=503)(scope,receive,send)
            # Check trusted session BEFORE opening the source or performing any query.
            auth=headers.get(b'authorization',b'').decode()
            credential=auth[7:] if auth.startswith('Bearer ') else (cookies['p18_session'].value if 'p18_session' in cookies else '')
            with self.central.connect() as conn:user=library_store.resolve_session(conn,credential) if credential else None
            if not user:return await JSONResponse({'detail':'请先正常登录'},status_code=401)(scope,receive,send)
            with self.lock:
                if self.qstore is None:self.qstore=self.create_store()
            return await self.qstore.app(scope,receive,send)
        return await self.central.app(scope,receive,send)


def install(central):
    return DatasetsApp(central)
