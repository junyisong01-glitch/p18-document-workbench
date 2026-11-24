"""Department-routed requests; approval atomically creates an ordinary read grant.

No hidden-document discovery: applicants submit a question and purpose, and the
responsible department selects a document. Every result read rechecks access.
"""
import json
import time
import uuid
from typing import Literal
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from app.business_roles import DEPARTMENTS


class CreateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    question: str = Field(min_length=1, max_length=2000)
    purpose: str = Field(min_length=1, max_length=1000)
    department: str


class Decision(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    expected: int = Field(ge=0)
    action: Literal['approve', 'reject', 'cancel', 'needs_content', 'resolve']
    document_id: str | None = None
    document_version: int | None = Field(default=None, ge=0)
    days: int = Field(default=7, ge=1, le=30)
    note: str = Field(default='', max_length=1000)


def install(store, central, user, read, visible, manager):
    with store.connect() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS access_requests (
          id TEXT PRIMARY KEY, owner TEXT NOT NULL, owner_department TEXT NOT NULL,
          department TEXT NOT NULL, question TEXT NOT NULL, purpose TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending', version INTEGER NOT NULL DEFAULT 0,
          document_id TEXT, expires REAL, actor TEXT, created REAL NOT NULL, updated REAL NOT NULL)''')
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS access_request_pending ON access_requests(owner,department,question) WHERE status='pending'")
        c.execute('''CREATE TABLE IF NOT EXISTS access_request_events (
          id INTEGER PRIMARY KEY, request_id TEXT NOT NULL, actor TEXT NOT NULL,
          action TEXT NOT NULL, at REAL NOT NULL, version INTEGER NOT NULL)''')

    # Additive, repeatable migration preserves existing requests and audit entries.
    with store.connect() as c:
        columns = {r[1] for r in c.execute('PRAGMA table_info(access_requests)')}
        for name in ('review_note', 'gap_note', 'gap_actor'):
            if name not in columns:
                c.execute(f'ALTER TABLE access_requests ADD COLUMN {name} TEXT')
        event_columns = {r[1] for r in c.execute('PRAGMA table_info(access_request_events)')}
        if 'note' not in event_columns:
            c.execute('ALTER TABLE access_request_events ADD COLUMN note TEXT')
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS access_request_open ON access_requests(owner,department,question) WHERE status IN ('pending','needs_content')")

    def internal():
        u = user()
        if u['role'] not in {'employee', 'supervisor', 'boss'}:
            raise HTTPException(403, '仅内部成员可申请资料支持')
        return u

    def reviewer(u, row):
        return u['username'] != row['owner'] and (u['role'] == 'boss' or
            u['role'] == 'supervisor' and u['department'] == row['department'])

    def output(row, u):
        result = {k:row[k] for k in ('id','owner','owner_department','department','question','purpose','status','version','created','updated','review_note','gap_note','gap_actor')}
        result.update(can_review=reviewer(u,row), document=None, access_available=False, expires_at=row['expires'])
        # Requests route to a role, not to an assigned individual. The stored
        # actor is the historical decision maker, even after later role changes.
        result['reviewer_scope'] = f"{row['department']}主管或管理层" if row['status'] in {'pending','needs_content'} else None
        result['handled_by'] = row['actor'] if row['status'] not in {'pending','needs_content'} else None
        # Do not retain a revoked file's title/identifier in applicant notifications.
        if row['status'] in {'approved','resolved'} and row['document_id']:
            try:
                doc = store.get(row['document_id'])
                if visible(doc, u, evidence=True):
                    result['document'] = {'id':doc['id'], 'name':doc['name']}
                    result['access_available'] = True
            except HTTPException:
                pass
        return result

    @store.app.get('/api/business/access-requests')
    def listing():
        u = internal()
        with store.LOCK, store.connect() as c:
            rows = c.execute('''SELECT * FROM access_requests WHERE owner=? OR ?='boss'
              OR (?='supervisor' AND department=?) ORDER BY updated DESC''',
              (u['username'],u['role'],u['role'],u['department'])).fetchall()
            return [output(r,u) for r in rows]

    @store.app.post('/api/business/access-requests')
    def create(body: CreateRequest):
        u = internal()
        question = ' '.join(body.question.split())
        purpose = body.purpose.strip()
        if not question or not purpose or body.department not in DEPARTMENTS:
            raise HTTPException(422, '请填写问题、用途并选择相关部门')
        now = time.time()
        with store.LOCK, store.connect() as c:
            existing = c.execute("SELECT * FROM access_requests WHERE owner=? AND department=? AND question=? AND status IN ('pending','needs_content')",
                                 (u['username'],body.department,question)).fetchone()
            if existing:
                return output(existing,u)
            identifier = str(uuid.uuid4())
            c.execute('''INSERT INTO access_requests
              (id,owner,owner_department,department,question,purpose,created,updated) VALUES (?,?,?,?,?,?,?,?)''',
              (identifier,u['username'],u['department'],body.department,question,purpose,now,now))
            c.execute('INSERT INTO access_request_events(request_id,actor,action,at,version) VALUES (?,?,?,?,0)',
                      (identifier,u['username'],'create',now))
            return output(c.execute('SELECT * FROM access_requests WHERE id=?',(identifier,)).fetchone(),u)

    @store.app.get('/api/business/access-requests/{identifier}/recommendations')
    def recommendations(identifier: str):
        from app.embedding import EmbeddingError
        from app.semantic import SemanticError
        u = internal()
        with store.LOCK, store.connect() as c:
            row = c.execute('SELECT * FROM access_requests WHERE id=?',(identifier,)).fetchone()
            if not row or not reviewer(u,row):
                raise HTTPException(404,'申请不存在或不可处理')
            if row['status'] not in {'pending','needs_content'}:
                raise HTTPException(409,'申请已处理，请刷新')
            question, purpose, department = row['question'], row['purpose'], row['department']

        def eligible(doc):
            b = read(doc['id'])
            return bool(b and b['department']==department and manager(u,b)
                and not (b.get('restricted') and u['role']!='boss')
                and visible(doc,u,evidence=True)
                and store.business_raw_index_status(doc['id']).get('searchable'))

        # Search only the reviewer's readable, grantable department documents.
        # No elevated principal or hidden-document discovery is used.
        try:
            result = store.require_semantic().search(question, top_k=20, mode='hybrid', document_filter=eligible)
        except (EmbeddingError, SemanticError) as exc:
            raise HTTPException(503,'相关资料检索暂不可用，请稍后重试或手动核对文件') from exc
        with store.LOCK, store.connect() as c:
            u = internal()
            current = c.execute('SELECT * FROM access_requests WHERE id=?',(identifier,)).fetchone()
            if not current or not reviewer(u,current):
                raise HTTPException(404,'申请不存在或不可处理')
            if current['status'] not in {'pending','needs_content'}:
                raise HTTPException(409,'申请已处理，请刷新')
            found = []
            seen = set()
            for hit in result.get('results',[]):
                doc_id = hit.get('document_id')
                if not doc_id or doc_id in seen:
                    continue
                try:
                    doc = store.get(doc_id)
                except HTTPException:
                    continue
                if not eligible(doc):
                    continue
                b = read(doc_id,c)
                found.append({'id':doc_id,'name':doc['name'],'document_version':b['version'],
                              'excerpt':str(hit.get('text',''))[:900],'section':str(hit.get('section',''))[:160]})
                seen.add(doc_id)
                if len(found)==5:
                    break
        from app.access_recommendations import classify, arrange
        quotes, checked = classify(question, purpose, found)
        # Model work happens outside the lock. Recheck identity, request and document
        # versions afterwards so revoked access or changed text cannot leak via reasons.
        with store.LOCK, store.connect() as c:
            u = internal()
            current = c.execute('SELECT * FROM access_requests WHERE id=?',(identifier,)).fetchone()
            if not current or not reviewer(u,current):
                raise HTTPException(404,'申请不存在或不可处理')
            if current['status'] not in {'pending','needs_content'}:
                raise HTTPException(409,'申请已处理，请刷新')
            fresh = []
            for item in found:
                try:
                    doc = store.get(item['id'])
                except HTTPException:
                    continue
                b = read(item['id'],c)
                if b and b['version'] == item['document_version'] and eligible(doc):
                    fresh.append(item)
            return {'items':arrange(fresh, quotes),'review_available':checked,
                    'notice':('推荐仅辅助核对，仍需结合用途选择文件。' if checked else
                    '暂未完成依据核对，以下仅为相关候选，可展开原文人工选择。') if fresh else
                    '在你可授权的本部门资料中未检索到相关候选。请人工核对，必要时补充资料；这不代表整个知识库没有相关内容。'}

    @store.app.post('/api/business/access-requests/{identifier}/decision')
    def decide(identifier: str, body: Decision):
        u = internal()
        with store.LOCK, store.connect() as c:
            row = c.execute('SELECT * FROM access_requests WHERE id=?',(identifier,)).fetchone()
            if not row or not (row['owner']==u['username'] or reviewer(u,row)):
                raise HTTPException(404, '申请不存在或不可处理')
            if body.action=='cancel':
                if row['owner']!=u['username']:
                    raise HTTPException(403,'仅申请人可撤回申请')
            elif not reviewer(u,row):
                raise HTTPException(403,'请由资料所属部门的其他主管或管理层处理')
            if row['status'] not in {'pending','needs_content'} or row['version']!=body.expected:
                raise HTTPException(409,'申请已处理或发生变化，请刷新')
            if body.action == 'resolve' and row['status'] != 'needs_content':
                raise HTTPException(409, '仅待补充申请可完成补充')
            if body.action == 'approve' and row['status'] == 'needs_content':
                raise HTTPException(409, '请使用完成补充操作并说明补充结果')
            note = body.note.strip()
            if body.action in {'needs_content','resolve','reject'} and not note:
                raise HTTPException(422, '请填写供申请人查看的处理说明')
            if body.action=='cancel' and note:
                raise HTTPException(422, '撤回操作不接受处理说明')
            if body.action not in {'approve','resolve'} and (body.document_id is not None or body.document_version is not None):
                raise HTTPException(422,'此操作不接受文件参数')
            document_id = None
            expires = None
            if body.action in {'approve','resolve'}:
                with central.connect() as accounts:
                    person = accounts.execute('''SELECT a.active,p.role,p.department FROM library_accounts a
                      JOIN business_profiles p ON p.username=a.username WHERE a.username=?''',(row['owner'],)).fetchone()
                if not person or not person['active'] or person['role'] not in {'employee','supervisor','boss'} or person['department']!=row['owner_department']:
                    raise HTTPException(409,'申请人身份已变化，请重新提交申请')
                b = read(body.document_id,c) if body.document_id else None
                if (not b or b['department']!=row['department'] or not manager(u,b)
                        or b.get('restricted') and u['role']!='boss'):
                    raise HTTPException(404,'所选资料不可用于此申请')
                doc = store.get(body.document_id)
                if (b['status']!='published' or b.get('archived') or b.get('deleted') or b.get('purged')
                        or not visible(doc,u,evidence=True) or not store.business_raw_index_status(body.document_id).get('searchable')):
                    raise HTTPException(409,'请选择当前已发布且可检索的资料')
                if body.document_version is None or body.document_version!=b['version']:
                    raise HTTPException(409,'资料已变化，请刷新后重新选择')
                document_id = body.document_id
                expires = now = time.time()
                expires += body.days*86400
                existing = c.execute('SELECT expires FROM business_grants WHERE document_id=? AND username=?',
                                     (document_id,row['owner'])).fetchone()
                # An approval must never shorten an existing permanent or longer grant.
                if existing and (existing['expires'] is None or existing['expires']>expires):
                    expires = existing['expires']
                c.execute('INSERT OR REPLACE INTO business_grants VALUES (?,?,?)',(document_id,row['owner'],expires))
                b['version']+=1
                c.execute('UPDATE business_documents SET body=? WHERE document_id=?',(json.dumps(b,ensure_ascii=False),document_id))
                c.execute('INSERT INTO business_events(document_id,at,actor,action,body) VALUES (?,?,?,?,?)',
                          (document_id,now,u['username'],'share',json.dumps({'username':row['owner'],'expires_at':expires,'version':b['version'],'request_id':identifier},ensure_ascii=False)))
            status = {'approve':'approved','reject':'rejected','cancel':'cancelled','needs_content':'needs_content','resolve':'resolved'}[body.action]
            now = time.time()
            c.execute('''UPDATE access_requests SET status=?,version=version+1,document_id=?,expires=?,actor=?,updated=? WHERE id=?''',
                      (status,document_id,expires,u['username'],now,identifier))
            c.execute('UPDATE access_requests SET review_note=? WHERE id=?', (note or None,identifier))
            if body.action == 'needs_content':
                c.execute('UPDATE access_requests SET gap_note=?,gap_actor=? WHERE id=?', (note,u['username'],identifier))
            c.execute('INSERT INTO access_request_events(request_id,actor,action,at,version,note) VALUES (?,?,?,?,?,?)',
                      (identifier,u['username'],body.action,now,row['version']+1,note or None))
            # Finish the transaction before projecting access (visible reads a new connection).
        with store.connect() as c:
            return output(c.execute('SELECT * FROM access_requests WHERE id=?',(identifier,)).fetchone(),u)
