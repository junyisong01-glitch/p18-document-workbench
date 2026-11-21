"""Isolated demo, writable business copy and historical read-only source.

Authentication remains in the original library; The historical Qichen source stays read-only; business writes target a separate runtime copy.
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
        from app.llm import RoutedClient
        import os
        super().__init__(store, client=RoutedClient(source_library='qichen') if os.environ.get('LLM_PROVIDER')=='ollama' else DisabledClient())
        self.source_library='qichen'
        self.logger = logger

    def external_allowed(self, doc):
        return self.configuration().get('provider')=='ollama' and self.can_read(doc)

    def audit_request(self, action, ticket=None, code=None):
        self.logger(action=action, code=code)


class DatasetBody(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    dataset: Literal['demo', 'qichen30', 'business']


class DatasetsApp:
    def __init__(self, central):
        self.central = central
        self.qstore = None
        self.business_store = None
        self.lock = threading.RLock()
        self.config_path = central.ROOT/'config/qichen-libraries.json'
        self.log_lock = threading.RLock()
        business_config = central.ROOT/'config/business.json'
        self.single_library = business_config.is_file() and json.loads(business_config.read_text()).get('demo_offline') is True
        central.DEMO_LIBRARY_OFFLINE = self.single_library

        @central.app.get('/api/library/datasets')
        def datasets(request: Request):
            u=library_api.principal.get()or{}
            writable=(central.ROOT/'config/business.json').is_file()
            selected=request.cookies.get('p18_dataset','demo')
            if self.single_library:
                return {'selected':'business','datasets':[{'id':'business','name':'启辰智造知识库','read_only':False}]}
            if writable and selected=='qichen30':selected='business'
            items=[{'id':'demo','name':'演示资料库','read_only':False}]
            if writable and u.get('role'):items.insert(0,{'id':'business','name':'启辰智造知识库','read_only':False})
            elif not writable and self.config().get('enabled',True):items.insert(0,{'id':'qichen30','name':'启辰智造知识库','read_only':True})
            return {'selected':selected,'datasets':items}

        @central.app.post('/api/library/datasets')
        def select_dataset(body: DatasetBody):
            u=library_api.principal.get()
            if self.single_library and body.dataset=='demo':raise HTTPException(404,'演示资料库已下线')
            if body.dataset=='qichen30'and(central.ROOT/'config/business.json').is_file():body.dataset='business'
            if body.dataset=='qichen30' and u and u.get('role') and u['role']!='boss':raise HTTPException(403,'历史验收库仅保留维护入口，请使用业务库')
            if body.dataset=='business' and (not u or not u.get('role')):raise HTTPException(403,'尚未分配业务角色')
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
            from app.llm import provider_name
            if provider_name()=='ollama':allowed.add('/api/rag/answer')
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
        if self.single_library and path.rstrip('/') in {'/demo','/static/demo.html'}:
            return await JSONResponse({'detail':'演示资料库已下线'},status_code=404)(scope,receive,send)
        headers=dict(scope.get('headers',[]));cookies=SimpleCookie()
        try:cookies.load(headers.get(b'cookie',b'').decode())
        except Exception:pass
        selected=cookies['p18_dataset'].value if 'p18_dataset' in cookies else 'demo'
        if selected not in {'demo','qichen30','business'}:
            return await JSONResponse({'detail':'未知知识库，请重新选择'},status_code=400)(scope,receive,send)
        if selected=='qichen30'and(self.central.ROOT/'config/business.json').is_file():
            selected='business'
            scope=dict(scope);scope['headers']=[(k,v.replace(b'p18_dataset=qichen30',b'p18_dataset=business'))if k==b'cookie'else(k,v)for k,v in scope.get('headers',[])]
        central_paths={'/api/business/accounts/reinvite','/api/library/activate-account','/api/business/accounts','/api/library/demo-fill','/api/business/people','/api/library/demo-login','/api/library/demo-accounts','/api/rag/credentials','/api/library/login','/api/library/logout','/api/library/demo-session','/api/library/datasets'}
        if self.single_library:
            selected='business'
            central_paths.discard('/api/rag/credentials')
        if selected=='business' and path.startswith('/api/') and path not in central_paths:
            cfg_path=self.central.ROOT/'config/business.json'
            if not cfg_path.is_file():return await JSONResponse({'detail':'业务库尚未配置'},status_code=503)(scope,receive,send)
            auth=headers.get(b'authorization',b'').decode()
            credential=auth[7:] if auth.startswith('Bearer ') else (cookies['p18_session'].value if 'p18_session' in cookies else '')
            with self.central.connect()as conn:user=library_store.resolve_session(conn,credential) if credential else None
            if not user:return await JSONResponse({'detail':'请先正常登录'},status_code=401)(scope,receive,send)
            if not user.get('role'):return await JSONResponse({'detail':'尚未分配业务角色'},status_code=403)(scope,receive,send)
            with self.lock:
                if self.business_store is None:
                    from app.business import create_store
                    self.business_store=create_store(self.central,json.loads(cfg_path.read_text()))
            return await self.business_store.app(scope,receive,send)
        if selected=='qichen30' and path.startswith('/api/') and path not in central_paths:
            if not self.config().get('enabled',True):
                return await JSONResponse({'detail':'当前源码检出未连接已授权的启辰数据源'},status_code=503)(scope,receive,send)
            # Check trusted session BEFORE opening the source or performing any query.
            auth=headers.get(b'authorization',b'').decode()
            credential=auth[7:] if auth.startswith('Bearer ') else (cookies['p18_session'].value if 'p18_session' in cookies else '')
            with self.central.connect() as conn:user=library_store.resolve_session(conn,credential) if credential else None
            if not user:return await JSONResponse({'detail':'请先正常登录'},status_code=401)(scope,receive,send)
            if user.get('role') and user['role']!='boss':return await JSONResponse({'detail':'历史验收库仅限维护访问'},status_code=403)(scope,receive,send)
            with self.lock:
                if self.qstore is None:self.qstore=self.create_store()
            return await self.qstore.app(scope,receive,send)
        return await self.central.app(scope,receive,send)


def install(central):
    if (central.ROOT/'config/business.json').is_file():
        from app.business_roles import install_api
        install_api(central)
    return DatasetsApp(central)
