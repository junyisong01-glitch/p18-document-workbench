"""Opt-in feedback. Server-owned turn snapshots; no automatic persistent chats."""
from copy import deepcopy
import json
import secrets
import time
import uuid
from typing import Literal
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field


class FeedbackCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    context_id: str = Field(min_length=1, max_length=100)
    category: Literal['missing', 'answer', 'citation']
    note: str = Field(default='', max_length=1000)


class FeedbackUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    expected: int = Field(ge=0)
    status: Literal['open', 'investigating', 'resolved', 'closed']
    cause: Literal['unknown', 'retrieval', 'answer', 'citation', 'missing', 'permission', 'question', 'other']
    note: str = Field(default='', max_length=2000)


def install(store, user, visible):
    with store.connect() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS qa_feedback (
          id TEXT PRIMARY KEY, owner TEXT NOT NULL, department TEXT NOT NULL,
          context_id TEXT NOT NULL, category TEXT NOT NULL, note TEXT NOT NULL,
          snapshot TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
          cause TEXT NOT NULL DEFAULT 'unknown', handling_note TEXT NOT NULL DEFAULT '',
          version INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL, updated REAL NOT NULL,
          UNIQUE(owner, context_id))''')
        c.execute('''CREATE TABLE IF NOT EXISTS qa_feedback_events (
          id INTEGER PRIMARY KEY, feedback_id TEXT NOT NULL, actor TEXT NOT NULL,
          at REAL NOT NULL, status TEXT NOT NULL, cause TEXT NOT NULL, note TEXT NOT NULL)''')

    def internal():
        u = user()
        if u['role'] == 'guest':
            raise HTTPException(403, '仅内部账号可提交和查看反馈')
        return u

    def permitted(snapshot, u):
        for source in snapshot['sources']:
            try:
                doc = store.get(source['document_id'])
                if doc['revision'] != source['revision'] or not visible(doc, u, evidence=True):
                    return False
            except HTTPException:
                return False
        return True

    def capture(service, method, result, context):
        u = user()
        if u['role'] == 'guest':
            return
        if method == 'draft':
            if (result.get('status') != 'drafted' or result.get('default_candidate_ids')
                    or any(c.get('selectable') for c in result.get('candidates', []))):
                return
            snapshot = dict(question=result['question'], answer='没找到可靠依据',
                            answer_status='insufficient_evidence', citations=[], sources=[],
                            request_id=result.get('request_id'), provider='本地检索')
        elif method == 'answer' and result.get('status') == 'answered' and context:
            sources = context.get('provenance', context.get('evidence', [])) + context.get('historical', []) + result.get('citations', [])
            if 'external' in context:
                sources += context['external'].get('evidence', [])
            refs = {(m['document_id'], m['revision']) for s in sources for m in [s, *s.get('members', [])]}
            snapshot = dict(question=context['question'], answer=result['answer'],
                            answer_status=result['answer_status'], citations=deepcopy(result.get('citations', [])),
                            sources=[dict(document_id=d, revision=r) for d, r in refs],
                            request_id=context.get('audit_id'), provider=result.get('provider', ''))
        else:
            return
        # Retained in this login's RAG service for 30 minutes, persisted only on explicit POST.
        with service.lock:
            now = time.monotonic()
            receipts = {k:v for k,v in getattr(service, 'feedback_contexts', {}).items() if now-v['at'] < 1800}
            while len(receipts) >= 64:
                receipts.pop(next(iter(receipts)))
            token = secrets.token_urlsafe(24)
            receipts[token] = dict(at=now, owner=u['username'], snapshot=snapshot)
            service.feedback_contexts = receipts
            result['feedback_context_id'] = token
    store.capture_qa_feedback = capture

    def output(row, u):
        snapshot = json.loads(row['snapshot'])
        allowed = permitted(snapshot, u)
        result = {k:row[k] for k in ['id', 'category', 'status', 'version', 'created', 'updated']}
        result.update(context_available=allowed,
                      question=snapshot['question'] if allowed else '关联资料已变更或当前无权查看',
                      note=row['note'] if allowed else '',
                      snapshot={k:v for k,v in snapshot.items() if k != 'sources'} if allowed else None)
        # Handling notes are maintenance-only: never relay arbitrary admin text to reporters.
        if u['role'] == 'boss':
            result.update(owner=row['owner'], department=row['department'], cause=row['cause'],
                          handling_note=row['handling_note'] if allowed else '')
        return result

    @store.app.post('/api/business/feedback')
    def create(body: FeedbackCreate):
        u = internal()
        service = store.current_rag()
        with service.lock:
            context = getattr(service, 'feedback_contexts', {}).get(body.context_id)
            if not context or context['owner'] != u['username'] or time.monotonic()-context['at'] >= 1800:
                raise HTTPException(409, '本轮反馈上下文已过期，请重新提问后反馈')
            snapshot = deepcopy(context['snapshot'])
        with store.LOCK, store.connect() as c:
            if not permitted(snapshot, u):
                raise HTTPException(409, '引用资料已变更或当前不可查看，请重新提问后反馈')
            existing = c.execute('SELECT * FROM qa_feedback WHERE owner=? AND context_id=?',
                                 (u['username'], body.context_id)).fetchone()
            if existing:
                return output(existing, u)
            identifier, now = str(uuid.uuid4()), time.time()
            c.execute('''INSERT INTO qa_feedback
              (id,owner,department,context_id,category,note,snapshot,created,updated)
              VALUES (?,?,?,?,?,?,?,?,?)''', (identifier,u['username'],u['department'],body.context_id,
              body.category,body.note.strip(),json.dumps(snapshot,ensure_ascii=False),now,now))
            return output(c.execute('SELECT * FROM qa_feedback WHERE id=?',(identifier,)).fetchone(),u)

    @store.app.get('/api/business/feedback')
    def listing():
        u = internal()
        with store.LOCK, store.connect() as c:
            rows = c.execute("SELECT * FROM qa_feedback WHERE (?='boss' OR owner=?) ORDER BY created DESC",
                             (u['role'],u['username'])).fetchall()
            return [output(row,u) for row in rows]

    @store.app.put('/api/business/feedback/{identifier}')
    def update(identifier: str, body: FeedbackUpdate):
        u = internal()
        if u['role'] != 'boss':
            raise HTTPException(403, '仅维护管理账号可处理反馈')
        if body.status in {'resolved','closed'} and (body.cause == 'unknown' or not body.note.strip()):
            raise HTTPException(422, '请记录排查原因和处理说明后再结束反馈')
        with store.LOCK, store.connect() as c:
            row = c.execute('SELECT * FROM qa_feedback WHERE id=?',(identifier,)).fetchone()
            if not row:
                raise HTTPException(404, '反馈不存在或不可访问')
            if row['version'] != body.expected:
                raise HTTPException(409, '反馈已更新，请刷新后重试')
            now = time.time()
            c.execute('''UPDATE qa_feedback SET status=?,cause=?,handling_note=?,version=version+1,updated=?
              WHERE id=?''',(body.status,body.cause,body.note.strip(),now,identifier))
            c.execute('INSERT INTO qa_feedback_events(feedback_id,actor,at,status,cause,note) VALUES (?,?,?,?,?,?)',
                      (identifier,u['username'],now,body.status,body.cause,body.note.strip()))
            return output(c.execute('SELECT * FROM qa_feedback WHERE id=?',(identifier,)).fetchone(),u)
