"""Explicitly submitted questions, scoped to their author and department supervisor.

No automatic question logging or approximate cross-question merging. Management
receives counts only. A linked document is reauthorized on every read.
"""
import re
import time
import unicodedata
import uuid

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

from app.business_roles import DEPARTMENTS


class GapCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    question: str = Field(min_length=1, max_length=1000)


class GapUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    expected: int = Field(ge=0)
    status: Literal['open', 'in_progress', 'resolved']
    note: str = Field(default='', max_length=1000)
    document_id: str | None = None


def normalize(question):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', question)).strip()


def install(store, user, read, visible):
    with store.connect() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS knowledge_gaps (
          id TEXT PRIMARY KEY, department TEXT NOT NULL, question TEXT NOT NULL,
          normalized TEXT NOT NULL, status TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
          document_id TEXT, version INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL,
          updated REAL NOT NULL, UNIQUE(department, normalized))''')
        c.execute('''CREATE TABLE IF NOT EXISTS knowledge_gap_reporters (
          gap_id TEXT NOT NULL, username TEXT NOT NULL, created REAL NOT NULL,
          PRIMARY KEY(gap_id, username))''')
        c.execute('''CREATE TABLE IF NOT EXISTS knowledge_gap_events (
          id INTEGER PRIMARY KEY, gap_id TEXT NOT NULL, actor TEXT NOT NULL,
          at REAL NOT NULL, action TEXT NOT NULL, version INTEGER NOT NULL)''')

    def author():
        u = user()
        if u['role'] not in {'employee', 'supervisor'} or u['department'] not in DEPARTMENTS:
            raise HTTPException(403, '仅内部员工可记录本部门问题')
        return u

    def output(row, u, c):
        result = dict(row)
        result.pop('normalized', None)
        result['reporter_count'] = c.execute(
            'SELECT COUNT(*) FROM knowledge_gap_reporters WHERE gap_id=?', (row['id'],)).fetchone()[0]
        result['document'] = None
        identifier = result.pop('document_id')
        if identifier:
            b = read(identifier, c)
            if b and not b.get('deleted') and not b.get('archived') and b['status'] == 'published':
                doc = store.get(identifier)
                if visible(doc, u, evidence=True):
                    result['document'] = {'id': identifier, 'name': doc['name']}
        return result

    @store.app.post('/api/business/gaps')
    def create(body: GapCreate):
        u = author()
        question = normalize(body.question)
        if not question:
            raise HTTPException(422, '请填写需要补充的问题')
        now = time.time()
        with store.LOCK, store.connect() as c:
            existing = c.execute('SELECT * FROM knowledge_gaps WHERE department=? AND normalized=?',
                                 (u['department'], question)).fetchone()
            identifier = existing['id'] if existing else str(uuid.uuid4())
            if not existing:
                c.execute('''INSERT INTO knowledge_gaps
                  (id,department,question,normalized,status,created,updated) VALUES (?,?,?,?,?,?,?)''',
                          (identifier, u['department'], body.question.strip(), question, 'open', now, now))
            inserted = c.execute('INSERT OR IGNORE INTO knowledge_gap_reporters VALUES (?,?,?)',
                                 (identifier, u['username'], now)).rowcount
            if inserted:
                c.execute('UPDATE knowledge_gaps SET updated=? WHERE id=?', (now, identifier))
                c.execute('INSERT INTO knowledge_gap_events(gap_id,actor,at,action,version) VALUES (?,?,?,?,?)',
                          (identifier, u['username'], now, 'record', existing['version'] if existing else 0))
            row = c.execute('SELECT * FROM knowledge_gaps WHERE id=?', (identifier,)).fetchone()
            return output(row, u, c)

    @store.app.get('/api/business/gaps')
    def listing():
        u = author()
        with store.connect() as c:
            if u['role'] == 'supervisor':
                rows = c.execute('SELECT * FROM knowledge_gaps WHERE department=? ORDER BY updated DESC',
                                 (u['department'],)).fetchall()
            else:
                rows = c.execute('''SELECT g.* FROM knowledge_gaps g JOIN knowledge_gap_reporters r ON r.gap_id=g.id
                  WHERE g.department=? AND r.username=? ORDER BY g.updated DESC''',
                                 (u['department'], u['username'])).fetchall()
            return [output(row, u, c) for row in rows]

    @store.app.get('/api/business/gaps/summary')
    def summary():
        u = user()
        if u['role'] not in {'boss', 'supervisor'}:
            raise HTTPException(403, '仅管理角色可查看汇总')
        with store.connect() as c:
            rows = c.execute('''SELECT department,status,COUNT(*) AS total FROM knowledge_gaps
              WHERE (?='boss' OR department=?) GROUP BY department,status''',
                             (u['role'], u['department'])).fetchall()
            return [dict(row) for row in rows]

    @store.app.put('/api/business/gaps/{identifier}')
    def update(identifier: str, body: GapUpdate):
        u = author()
        if u['role'] != 'supervisor':
            raise HTTPException(403, '仅归属部门主管可处理问题')
        with store.LOCK, store.connect() as c:
            row = c.execute('SELECT * FROM knowledge_gaps WHERE id=? AND department=?',
                            (identifier, u['department'])).fetchone()
            if not row:
                raise HTTPException(404, '问题不存在或不可访问')
            if row['version'] != body.expected:
                raise HTTPException(409, '问题已更新，请刷新后重试')
            if body.status == 'resolved' and not body.document_id:
                raise HTTPException(422, '请关联已发布的补充资料')
            if body.document_id:
                b = read(body.document_id, c)
                if (not b or b['status'] != 'published' or b.get('archived') or b.get('deleted')
                        or not visible(store.get(body.document_id), u, evidence=True)
                        or not store.business_raw_index_status(body.document_id).get('searchable')):
                    raise HTTPException(404, '补充资料不可访问或尚未发布')
            now = time.time()
            c.execute('''UPDATE knowledge_gaps SET status=?,note=?,document_id=?,version=version+1,updated=?
                         WHERE id=?''', (body.status, body.note.strip(), body.document_id, now, identifier))
            c.execute('INSERT INTO knowledge_gap_events(gap_id,actor,at,action,version) VALUES (?,?,?,?,?)',
                      (identifier, u['username'], now, body.status, body.expected + 1))
            return output(c.execute('SELECT * FROM knowledge_gaps WHERE id=?', (identifier,)).fetchone(), u, c)
