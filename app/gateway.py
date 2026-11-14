"""Server-side gateway from a P18 session to an AnythingLLM workspace.

P18 keeps what AnythingLLM cannot do: who the user is, which documents that
identity may see, and an audit trail. AnythingLLM keeps what P18 should not
rebuild: parsing, chunking, embedding and answer generation.

Trust boundary: the gateway refuses to forward a question when no workspace the
identity may read exists, and it drops every cited source that P18 cannot map to
a visible document. AnythingLLM workspace scope is coarse; the per-source check
is what makes the answer auditable.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app import library_api

BASE = os.environ.get('P18_ANYTHINGLLM_BASE', 'http://127.0.0.1:3001')
KEY = os.environ.get('P18_ANYTHINGLLM_KEY', '')
BUCKETS = ('公开', '内部', '机密', '未分类')
TIMEOUT = float(os.environ.get('P18_ANYTHINGLLM_TIMEOUT', '180'))


class AskBody(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    question: str = Field(min_length=1, max_length=2000)
    mode: str = Field(default='query', pattern='^(query|chat)$')


class AnythingLLMError(RuntimeError):
    pass


def _call(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        BASE.rstrip('/') + path, data=data, method=method,
        headers={'Authorization': f'Bearer {KEY}', 'Accept': 'application/json',
                 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.loads(response.read() or b'{}')
    except urllib.error.HTTPError as exc:
        raise AnythingLLMError(f'{exc.code}: {exc.read()[:200]!r}') from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise AnythingLLMError(str(exc)) from exc


def workspaces():
    """name -> slug for every workspace the gateway may route to."""
    listed = _call('GET', '/api/v1/workspaces')
    return {item['name']: item['slug'] for item in listed.get('workspaces') or []}


def visible_documents(store, user):
    """{document name: document} for everything this identity may read."""
    allowed = {}
    for doc in store.all_docs():
        if doc.get('state') in {'deleted', 'deleting', 'delete_failed', 'superseded'}:
            continue
        if library_api.visible(store, doc):
            allowed[doc['name']] = doc
    return allowed


def buckets_for(store, user):
    """Classification buckets containing at least one visible document."""
    names = set(visible_documents(store, user))
    found = set()
    for name in names:
        doc = next((d for d in store.all_docs() if d['name'] == name), None)
        row = library_api.metadata(store, doc['id']) if doc else None
        found.add(row[1].classification if row else '未分类')
    return [bucket for bucket in BUCKETS if bucket in found]


def answer(store, user, question, mode='query'):
    mapping = workspaces()
    targets = [mapping[name] for name in buckets_for(store, user) if name in mapping]
    if not targets:
        raise HTTPException(409, '当前身份没有可用的知识库分区')
    texts, sources = [], []
    for slug in targets:
        result = _call('POST', f'/api/v1/workspace/{slug}/chat',
                       {'message': question, 'mode': mode})
        if result.get('error'):
            raise HTTPException(502, f'AnythingLLM: {result["error"]}')
        texts.append(result.get('textResponse') or '')
        sources.extend(result.get('sources') or [])
    allowed = visible_documents(store, user)
    kept, dropped = [], 0
    for source in sources:
        title = source.get('title') or ''
        if title in allowed:
            kept.append({'title': title, 'score': source.get('score'),
                         'document_id': allowed[title]['id']})
        else:
            dropped += 1
    return {'answer': '\n\n'.join(text for text in texts if text).strip(),
            'sources': kept, 'dropped_sources': dropped,
            'workspaces': list(targets)}


def audit(data_dir, record):
    path = Path(data_dir) / 'gateway-audit.jsonl'
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + '\n')


def install(app, store):
    router = APIRouter()

    @router.post('/api/gateway/ask')
    def ask(body: AskBody):
        user = library_api.principal.get()
        if user is None:
            raise HTTPException(401, '请先登录')
        started = time.time()
        try:
            result = answer(store, user, body.question, body.mode)
        except AnythingLLMError as exc:
            audit(store.DATA, {'at': started, 'identity': user['identity'],
                               'question_length': len(body.question), 'status': 'error'})
            raise HTTPException(502, '检索服务不可用') from exc
        audit(store.DATA, {'at': started, 'identity': user['identity'],
                           'question_length': len(body.question), 'status': 'ok',
                           'workspaces': result['workspaces'],
                           'sources': len(result['sources']),
                           'dropped_sources': result['dropped_sources']})
        return result

    app.include_router(router)
