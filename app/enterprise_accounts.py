"""Invitation-only provisioning; HR may create ordinary identities, never elevate."""
import hashlib,json,secrets,time,re
from fastapi import HTTPException
from pydantic import BaseModel,ConfigDict,Field
from typing import Literal
from app import library_store

def can_create_accounts(u):
    return bool(u and(u.get('role')=='boss'or(u.get('username')=='qichen_hr_head'and u.get('role')=='supervisor'and u.get('department')=='人力资源部')))

class NewAccount(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    username:str=Field(min_length=3,max_length=64)
    department:str
    role:Literal['employee','guest']='employee'
    job:Literal['','研发','测试','运维','生产']=''

class Activate(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    invitation_code:str=Field(min_length=32,max_length=128)
    password:str=Field(min_length=12,max_length=1024)

class Reinvite(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    username:str=Field(min_length=3,max_length=64)

def install_accounts(central):
    from app.business_roles import DEPARTMENTS,assign
    from app.library_api import principal
    with central.connect()as c:
        c.execute('CREATE TABLE IF NOT EXISTS account_invitations (digest TEXT PRIMARY KEY,username TEXT NOT NULL,created_by TEXT NOT NULL,expires REAL NOT NULL,used REAL)')
    def actor():
        u=principal.get()
        if not can_create_accounts(u):raise HTTPException(403,'仅老板或人事主管可邀请建号')
        with central.connect()as c:current=library_store.session_by_digest(c,u['session_digest'])
        if not can_create_accounts(current):raise HTTPException(401,'身份已变化，请重新登录')
        return current
    @central.app.post('/api/business/accounts')
    def create(body:NewAccount):
        u=actor()
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{2,63}',body.username)or body.department not in DEPARTMENTS:raise HTTPException(422,'账号须以字母开头，部门须为现有部门')
        if body.job and not(body.department=='研发部'and body.job in {'研发','测试','运维'}or body.department=='生产制造部'and body.job=='生产'):raise HTTPException(422,'专业岗位与部门不匹配')
        identity={'研发部':'研发部员工','生产制造部':'生产制造部员工','财务部':'财务部普通员工','人力资源部':'人力资源部普通员工','行政安全部':'行政安全部员工'}[body.department]
        if body.role=='guest':identity='只读访客'
        code=secrets.token_urlsafe(32)
        with central.LOCK,central.connect()as c:
            if c.execute('SELECT 1 FROM library_accounts WHERE username=?',(body.username,)).fetchone():raise HTTPException(409,'账号已存在，未覆盖')
            library_store.create_account(c,body.username,secrets.token_urlsafe(40),identity,manager=False)
            assign(c,body.username,body.role,body.department,body.job,u['username'])
            c.execute('UPDATE business_profiles SET is_demo=0 WHERE username=?',(body.username,))
            c.execute('UPDATE library_accounts SET active=0 WHERE username=?',(body.username,))
            c.execute('INSERT INTO account_invitations VALUES (?,?,?,?,NULL)',(hashlib.sha256(code.encode()).hexdigest(),body.username,u['username'],time.time()+86400))
            c.execute('INSERT INTO business_role_audit(at,actor,action,body)VALUES(?,?,?,?)',(time.time(),u['username'],'invite_account',json.dumps({'username':body.username,'department':body.department,'role':body.role})))
        return {'username':body.username,'invitation_code':code,'expires_in':86400,'notice':'邀请仅显示一次。请通过可信方式交给本人，在登录页激活并设置自己的密码。未激活不可登录，不加入免密演示卡片。'}
    @central.app.post('/api/business/accounts/reinvite')
    def reinvite(body:Reinvite):
        u=actor();code=secrets.token_urlsafe(32)
        with central.LOCK,central.connect()as c:
            row=c.execute('SELECT a.active,p.role FROM library_accounts a JOIN business_profiles p ON p.username=a.username WHERE a.username=?',(body.username,)).fetchone()
            if not row or row[0]or row[1]not in {'employee','guest'}or not c.execute('SELECT 1 FROM account_invitations WHERE username=?',(body.username,)).fetchone():raise HTTPException(409,'仅可重发本入口创建且尚未激活的员工/访客邀请，不重置在用账号')
            c.execute('UPDATE account_invitations SET used=?WHERE username=?AND used IS NULL',(time.time(),body.username))
            c.execute('INSERT INTO account_invitations VALUES (?,?,?,?,NULL)',(hashlib.sha256(code.encode()).hexdigest(),body.username,u['username'],time.time()+86400))
            c.execute('INSERT INTO business_role_audit(at,actor,action,body)VALUES(?,?,?,?)',(time.time(),u['username'],'reinvite_account',json.dumps({'username':body.username})))
        return {'username':body.username,'invitation_code':code,'expires_in':86400,'notice':'已重发24小时一次性邀请，旧邀请立即作废；账号原部门和职责未改动。'}
    @central.app.post('/api/library/activate-account')
    def activate(body:Activate):
        with central.LOCK,central.connect()as c:
            row=c.execute('SELECT username,expires,used FROM account_invitations WHERE digest=?',(hashlib.sha256(body.invitation_code.encode()).hexdigest(),)).fetchone()
            if not row or row[1]<=time.time()or row[2]is not None:raise HTTPException(403,'邀请无效、已使用或已过期')
            # Same password hashing as native accounts; no plaintext persistence.
            import hashlib as h
            salt=secrets.token_hex(16);digest=h.scrypt(body.password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
            c.execute('UPDATE library_accounts SET salt=?,password=?,active=1 WHERE username=?',(salt,digest,row[0]))
            c.execute('DELETE FROM library_sessions WHERE username=?',(row[0],))
            c.execute('UPDATE account_invitations SET used=?WHERE digest=?',(time.time(),hashlib.sha256(body.invitation_code.encode()).hexdigest()))
            c.execute('INSERT INTO business_role_audit(at,actor,action,body)VALUES(?,?,?,?)',(time.time(),row[0],'activate_account','{}'))
        return {'activated':True,'notice':'账号已激活，请用自己的账号和密码正常登录。'}
