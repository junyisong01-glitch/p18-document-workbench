"""Scoped organization roles; absent profiles retain legacy behavior."""
import json,time
from app import library_store
DEPARTMENTS=('研发部','生产制造部','财务部','人力资源部','行政安全部')
ROLES=('boss','supervisor','employee','guest')
def initialize(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS business_profiles (username TEXT PRIMARY KEY, role TEXT NOT NULL CHECK(role IN ('boss','supervisor','employee','guest')), department TEXT NOT NULL, job TEXT NOT NULL DEFAULT '')")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS business_single_boss ON business_profiles(role) WHERE role='boss'")
    if 'is_demo'not in {r[1]for r in conn.execute('PRAGMA table_info(business_profiles)')}:
        conn.execute('ALTER TABLE business_profiles ADD COLUMN is_demo INTEGER NOT NULL DEFAULT 0')
        demo_names=('demo_manager','qichen_rd','qichen_qa','qichen_ops','qichen_prd','qichen_fin','qichen_hr','qichen_adm','qichen_rd_head','qichen_prd_head','qichen_fin_head','qichen_hr_head','qichen_adm_head','qichen_guest')
        conn.execute('UPDATE business_profiles SET is_demo=1 WHERE username IN ('+','.join('?'for _ in demo_names)+')',demo_names)
    conn.execute('CREATE TABLE IF NOT EXISTS business_role_audit (id INTEGER PRIMARY KEY, at REAL NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL, body TEXT NOT NULL)')
def profile(conn,username):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='business_profiles'").fetchone():return None
    row=conn.execute('SELECT role,department,job FROM business_profiles WHERE username=?',(username,)).fetchone()
    return dict(role=row[0],department=row[1],job=row[2]) if row else None
def assign(conn,username,role,department,job='',actor='local_provisioning'):
    if role not in ROLES or (role not in {'boss','guest'} and department not in DEPARTMENTS):raise ValueError('角色或部门无效')
    if not conn.execute('SELECT 1 FROM library_accounts WHERE username=? AND active=1',(username,)).fetchone():raise ValueError('账号不存在或停用')
    conn.execute('INSERT INTO business_profiles(username,role,department,job) VALUES (?,?,?,?) ON CONFLICT(username) DO UPDATE SET role=excluded.role,department=excluded.department,job=excluded.job',(username,role,department,job))
    conn.execute('DELETE FROM library_sessions WHERE username=?',(username,))
    conn.execute('INSERT INTO business_role_audit(at,actor,action,body) VALUES (?,?,?,?)',(time.time(),actor,'assign',json.dumps(dict(username=username,role=role,department=department,job=job),ensure_ascii=False)))

def install_api(central):
    with central.connect()as c:initialize(c)
    from app.enterprise_accounts import install_accounts
    install_accounts(central)
    from fastapi import Request,HTTPException
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel,ConfigDict
    from app.library_api import principal
    class ProfileBody(BaseModel):
        model_config=ConfigDict(extra='forbid',strict=True)
        username:str
        role:str
        department:str
    def local_demo(request):
        from pathlib import Path
        cfg=central.DATA/'business-demo-enabled.json'
        return (request.url.hostname in {'127.0.0.1','localhost','::1'} and request.client and request.client.host in {'127.0.0.1','::1'} and cfg.is_file() and json.loads(cfg.read_text()).get('enabled')is True)
    # Short-lived demonstration password: never reads an account's real password.
    import secrets,hashlib,hmac
    challenges={}
    def consume_demo(request,username,password):
        if not password.startswith('p18-demo-'):return None
        if not local_demo(request):return False
        nonce=request.cookies.get('p18_demo_challenge','')
        with central.LOCK:
            item=challenges.pop(hashlib.sha256(nonce.encode()).hexdigest(),None)
            if not item or item['expires']<time.time() or item['username']!=username or not hmac.compare_digest(item['digest'],hashlib.sha256(password.encode()).hexdigest()):return False
            with central.connect()as c:
                current=profile(c,username)
                row=c.execute('SELECT identity,manager,active FROM library_accounts WHERE username=?',(username,)).fetchone()
                if not row or not row[2] or current!=item['profile']:return False
                token=library_store.issue_session(c,row[0],manager=bool(row[1]))
                c.execute('UPDATE library_sessions SET username=?WHERE digest=?',(username,hashlib.sha256(token.encode()).hexdigest()))
                return token
    central.consume_demo_login=consume_demo
    @central.app.post('/api/library/demo-fill')
    async def demo_fill(request:Request):
        if not local_demo(request):raise HTTPException(404,'未启用本机演示填入')
        try:
            body=await request.json()
            if not isinstance(body,dict)or set(body)!={'username'}or not isinstance(body['username'],str):raise ValueError()
        except(ValueError,TypeError):raise HTTPException(422,'只接受指定演示账号')from None
        with central.LOCK,central.connect()as c:
            p=profile(c,body['username']);row=c.execute('SELECT active FROM library_accounts WHERE username=?',(body['username'],)).fetchone()
            if not p or not row or not row[0]or not c.execute('SELECT is_demo FROM business_profiles WHERE username=?',(body['username'],)).fetchone()[0]:raise HTTPException(403,'演示账号不可用')
            now=time.time()
            for k in list(challenges):
                if challenges[k]['expires']<now:challenges.pop(k,None)
            if len(challenges)>=128:raise HTTPException(429,'演示填入过于频繁，请稍后再试')
            old=request.cookies.get('p18_demo_challenge','')
            if old:challenges.pop(hashlib.sha256(old.encode()).hexdigest(),None)
            nonce=secrets.token_urlsafe(32);password='p18-demo-'+secrets.token_urlsafe(24)
            challenges[hashlib.sha256(nonce.encode()).hexdigest()]={'username':body['username'],'profile':p,'digest':hashlib.sha256(password.encode()).hexdigest(),'expires':now+120}
        response=JSONResponse({'username':body['username'],'password':password,'expires_in':120})
        response.set_cookie('p18_demo_challenge',nonce,httponly=True,samesite='strict',max_age=120,path='/');response.headers['Cache-Control']='no-store';return response
    @central.app.get('/api/library/demo-accounts')
    def demo_accounts(request:Request):
        if not local_demo(request):return []
        with central.connect()as c:
            return [dict(username=r[0],role=r[1],department=r[2],job=r[3],password_required=r[1]=='boss')for r in c.execute('SELECT p.username,p.role,p.department,p.job FROM business_profiles p JOIN library_accounts a ON a.username=p.username WHERE a.active=1 AND p.is_demo=1 ORDER BY p.department,p.username')]
    @central.app.post('/api/library/demo-login')
    async def demo_login(request:Request):
        if not local_demo(request):raise HTTPException(404,'未启用本机演示快捷登录')
        try:
            body=await request.json()
            if not isinstance(body,dict)or set(body)!={'username'}or not isinstance(body['username'],str):raise ValueError()
        except(ValueError,TypeError):raise HTTPException(422,'只接受指定演示账号')from None
        import hashlib
        with central.LOCK,central.connect()as c:
            p=profile(c,body['username']);row=c.execute('SELECT identity,manager,active FROM library_accounts WHERE username=?',(body['username'],)).fetchone()
            if not row or not row[2]or not p or not c.execute('SELECT is_demo FROM business_profiles WHERE username=?',(body['username'],)).fetchone()[0]or p['role']=='boss':raise HTTPException(403,'该身份须正常密码登录')
            previous=request.cookies.get('p18_session','')
            if previous:library_store.revoke_session(c,previous);central.MANAGED_RAG.pop(hashlib.sha256(previous.encode()).hexdigest(),None)
            token=library_store.issue_session(c,row[0],manager=bool(row[1]));c.execute('UPDATE library_sessions SET username=? WHERE digest=?',(body['username'],hashlib.sha256(token.encode()).hexdigest()))
        response=JSONResponse({'authenticated':True});response.set_cookie('p18_session',token,httponly=True,samesite='strict',max_age=3600,path='/');response.set_cookie('p18_dataset','business',httponly=True,samesite='strict',path='/');response.headers['Cache-Control']='no-store';return response
    @central.app.get('/api/business/people')
    def people():
        u=principal.get()
        if not u or u.get('role')!='boss':raise HTTPException(403,'仅老板可查看人员管理')
        with central.connect()as c:return [dict(username=r[0],role=r[1],department=r[2],job=r[3])for r in c.execute('SELECT username,role,department,job FROM business_profiles')]
    @central.app.put('/api/business/people')
    def change_person(body:ProfileBody):
        u=principal.get()
        if not u or u.get('role')!='boss' or body.role=='boss':raise HTTPException(403,'仅老板可任免主管；本入口不增加第二个老板')
        with central.LOCK,central.connect()as c:
            old=profile(c,body.username)
            if not old or old['role']=='boss':raise HTTPException(403,'不可通过此入口修改老板')
            try:assign(c,body.username,body.role,body.department,old['job'] if body.department==old['department'] else '',u['username'])
            except ValueError as e:raise HTTPException(422,str(e))from None
        return {'updated':True}
