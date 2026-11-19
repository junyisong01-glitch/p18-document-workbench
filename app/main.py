"""Single-machine document workbench with optional offline semantic indexing."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
import uuid
from typing import Annotated, Literal

import pymupdf as fitz
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.parser import soffice_path
from app.admission import categories, requirements, confirmed, sync_admission
from app.chunking import configuration, digest, fingerprint, prepare

ROOT = Path(__file__).resolve().parent.parent
from app.llm import load_env
load_env(ROOT / '.env')
DATA = Path(os.environ.get("P18_DATA_DIR", ROOT / "runtime"))
DB = DATA / "workbench.sqlite3"
LOCK = threading.RLock()
POOL = ThreadPoolExecutor(max_workers=2)
ACTIVE = {}
CHUNK_ACTIVE = {}
INDEX_SERVICE = None
SEMANTIC_ERROR = None
RAG_SERVICE = None
MANAGED_RAG = {}
MAX_FILE = 20_000_000
MAX_BATCH = 100_000_000
STATES = {"queued", "converting", "parsing"}


def now():
    return datetime.now(timezone.utc).isoformat()


def connect():
    conn = sqlite3.connect(DB, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


def initialize():
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "files").mkdir(exist_ok=True)
    with connect() as conn:
        if os.environ.get('P18_SQLITE_WAL','0') == '1':
            conn.execute('PRAGMA journal_mode=WAL')
        from app.library_store import initialize as initialize_library
        initialize_library(conn)
        conn.execute("CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, body TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, document_id TEXT, action TEXT, at TEXT, revision INTEGER)")
        if "payload" not in {r[1] for r in conn.execute("PRAGMA table_info(events)")}:
            conn.execute("ALTER TABLE events ADD COLUMN payload TEXT")
        conn.execute("CREATE TABLE IF NOT EXISTS index_runs (document_id TEXT PRIMARY KEY, body TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS chunk_runs (document_id TEXT PRIMARY KEY, body TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS chunks (document_id TEXT NOT NULL, sequence INTEGER NOT NULL, id TEXT NOT NULL, body TEXT NOT NULL, PRIMARY KEY(document_id, sequence))")


def save(doc):
    sync_admission(doc)
    doc["updated_at"] = now()
    with connect() as conn:
        conn.execute("INSERT OR REPLACE INTO documents VALUES (?, ?)", (doc["id"], json.dumps(doc, ensure_ascii=False)))
        row = conn.execute("SELECT body FROM chunk_runs WHERE document_id=?", (doc['id'],)).fetchone()
        if row and (not doc['admission']['eligible'] or json.loads(row[0])['revision'] != doc['revision']):
            conn.execute("DELETE FROM chunks WHERE document_id=?", (doc['id'],))
            conn.execute("DELETE FROM chunk_runs WHERE document_id=?", (doc['id'],))

    if INDEX_SERVICE is not None:
        INDEX_SERVICE.invalidate(doc['id'])


def get(identifier):
    with connect() as conn:
        row = conn.execute("SELECT body FROM documents WHERE id = ?", (identifier,)).fetchone()
    if not row:
        raise HTTPException(404, "文档不存在或已删除。")
    return json.loads(row[0])


def all_docs():
    with connect() as conn:
        return [json.loads(r[0]) for r in conn.execute("SELECT body FROM documents")]


def event(doc, action, payload=None):
    with connect() as conn:
        conn.execute("INSERT INTO events (document_id, action, at, revision, payload) VALUES (?, ?, ?, ?, ?)",
                     (doc["id"], action, now(), doc["revision"], json.dumps(payload, ensure_ascii=False) if payload is not None else None))


def folder_for(identifier):
    # Only opaque UUIDs ever form storage paths; user filenames are metadata.
    try:
        if str(uuid.UUID(identifier)) != identifier:
            raise ValueError()
    except ValueError:
        raise HTTPException(404, "文档不存在。")
    return DATA / "files" / identifier


def public(doc, detailed=False):
    sync_admission(doc)
    result = dict(doc)
    result['review_pending'] = doc['state'] == 'review'
    decision = doc.get('review_decision') or {}
    result['review_completed'] = (doc['state'] in {'ready', 'held'} and decision.get('revision') == doc['revision'])
    index = index_status(doc['id'])
    if doc['admission']['eligible']:
        result['build'] = dict(result['build'], status={'not_started':'waiting','disabled':'waiting','unavailable':'failed'}.get(index['status'],index['status']),
            reason='index_'+index['status'], message=index['message'], searchable=bool(index.get('searchable')))
    result['index'] = index if detailed else {key: index.get(key) for key in
        ('status', 'searchable', 'count', 'message', 'error', 'error_code', 'updated_at', 'token', 'generation')}
    from app.egress import status as permission_status
    result['external_permission'] = permission_status(DATA, doc)
    if detailed:
        result['review_requirements'] = requirements(doc)
        result['chunking'] = chunk_result(doc, include_chunks=False, index=index)
    if not detailed:
        result.pop("result", None)
    return result


def on_index_complete(identifier):
    """Both index publication and already-complete recovery recheck this guard."""
    with LOCK:
        doc = get(identifier)
        if not doc.get('replaces') or doc.get('state') != 'ready':
            return True
        return activate_replacement(doc)


def activate_replacement(doc):
    target = doc.get("replaces")
    if not target:
        return
    if doc.get('state') != 'ready':
        return
    if os.environ.get('P18_SEMANTIC_ENABLED') == '1':
        if INDEX_SERVICE is None or not INDEX_SERVICE.replacement_usable(doc['id']):
            return False  # Parsed/reviewed is not a usable replacement.
    try:
        old = get(target)
    except HTTPException:
        return
    if old["state"] not in {"deleted", "delete_failed", "deleting", "superseded"}:
        old["state"] = "superseded"
        old["superseded_by"] = doc["id"]
        save(old)
    if old.get('state') == 'superseded' and old.get('superseded_by') == doc['id']:
        # A previous attempt may have saved the old state before audit failed.
        with connect() as conn:
            audited = conn.execute("SELECT 1 FROM events WHERE document_id=? AND action='replacement_prepared' LIMIT 1", (old['id'],)).fetchone()
        if not audited:
            event(old, "replacement_prepared")
    return True


def kill_process(proc):
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def parser_python(ext):
    """Optional DOCX worker only; the main/embedding interpreter stays unchanged."""
    path=os.environ.get('P18_DOCX_PYTHON','')
    if ext != '.docx' or os.environ.get('P18_PARSER','legacy') != 'docling' or not path:
        return sys.executable
    candidate=Path(path)
    if not candidate.is_absolute() or not candidate.is_file() or not os.access(candidate,os.X_OK):
        raise ValueError('Docling 独立解析环境不可用，请检查配置或切回 legacy。')
    return str(candidate)


def run_job(identifier, revision):
    proc = None
    try:
        with LOCK:
            doc = get(identifier)
            if doc["state"] != "queued" or doc["revision"] != revision:
                return
            doc["state"] = "converting" if doc["ext"] == ".doc" else "parsing"
            save(doc)
            folder = folder_for(identifier)
            (folder / "result.json").unlink(missing_ok=True)
            proc = subprocess.Popen([parser_python(doc["ext"]), "-m", "app.parse_worker", str(folder), doc["ext"]],
                                    cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    start_new_session=True)
            ACTIVE[identifier] = proc
        try:
            proc.wait(timeout=180)
        except subprocess.TimeoutExpired:
            kill_process(proc)
            proc.wait()
            raise ValueError("处理超过 180 秒，已停止任务；请拆分文件或重试。")
        with LOCK:
            doc = get(identifier)
            if doc["state"] in {"deleted", "deleting", "delete_failed"} or doc["revision"] != revision:
                return
            result_file = folder / "result.json"
            if proc.returncode or not result_file.exists():
                raise ValueError("文档处理进程中断，请重试或更换文件。")
            result = json.loads(result_file.read_text())
            doc["result"] = result
            doc["issues_count"] = len(result["issues"]) + len(result.get("preview_warnings", []))
            doc["characters"] = result["characters"]
            if result.get("error"):
                doc.update(state="failed", quality="failed", error=result["error"])
            elif result["issues"] or result.get("preview_warnings"):
                doc.update(state="review", quality="review", error=None)
            else:
                doc.update(state="ready", quality="clear", error=None)
                activate_replacement(doc)
            save(doc)
            event(doc, "extraction_finished")
            schedule_chunks(doc)
    except Exception as exc:
        with LOCK:
            try:
                doc = get(identifier)
                if doc["state"] not in {"deleted", "deleting", "delete_failed"} and doc["revision"] == revision:
                    doc.update(state="failed", quality="failed", error=str(exc) if isinstance(exc, ValueError) else "处理失败，请重试。")
                    save(doc)
            except HTTPException:
                pass
    finally:
        with LOCK:
            if ACTIVE.get(identifier) is proc:
                ACTIVE.pop(identifier, None)


def load_chunk_run(identifier):
    with connect() as conn:
        row = conn.execute("SELECT body FROM chunk_runs WHERE document_id=?", (identifier,)).fetchone()
    return json.loads(row[0]) if row else None


def write_chunk_run(conn, run):
    conn.execute("INSERT OR REPLACE INTO chunk_runs VALUES (?, ?)",
                 (run['document_id'], json.dumps(run, ensure_ascii=False)))


def chunk_result(doc, include_chunks=True, index=None):
    # Recalculate rather than trusting stale caller-supplied admission flags.
    sync_admission(doc)
    run = load_chunk_run(doc['id'])
    answer = {'status': 'not_started', 'count': 0, 'chunks': [], 'searchable': False,
              'message': '尚未切分。', 'warnings': []}
    if not doc['admission']['eligible']:
        answer.update(status='blocked', message='尚未通过入库条件，不提供正式切分结果。')
        return answer
    try:
        settings = configuration()
        answer['current_config'] = settings
    except ValueError as exc:
        answer.update(status='failed', message=str(exc))
        return answer
    if not run:
        return answer
    stale = (run['revision'] != doc['revision'] or run.get('config_hash') != digest(settings)
             or run.get('input_hash') != fingerprint(doc))
    answer.update({key: value for key, value in run.items() if key != 'normalized'})
    if stale:
        answer.update(status='stale', count=0, message='解析结果或切分配置已变化，请重新生成；旧片段不再提供使用。')
    elif include_chunks and run['status'] == 'complete':
        with connect() as conn:
            answer['chunks'] = [json.loads(row[0]) for row in conn.execute(
                "SELECT body FROM chunks WHERE document_id=? ORDER BY sequence", (doc['id'],))]
    if not stale and run['status'] == 'complete':
        # IndexService.snapshot calls this function: never resolve the index here.
        answer.update(searchable=bool(index and index.get('searchable')),
                      message='本地切分已完成；'+(index['message'] if index else '可检索性由当前向量索引状态决定。'))
    return answer


def schedule_chunks(doc, retry_failed=False):
    # Called under LOCK at parsing/review completion and startup, not from GET.
    sync_admission(doc)
    if not doc['admission']['eligible']:
        return
    try:
        settings = configuration()
        error = None
    except ValueError as exc:
        settings = {};error = str(exc)
    previous = load_chunk_run(doc['id'])
    config_hash, input_hash = digest(settings), fingerprint(doc)
    same = previous and previous.get('config_hash') == config_hash and previous.get('input_hash') == input_hash
    if same and (previous['status'] == 'complete' or (previous['status'] == 'failed' and not retry_failed)):
        return
    if doc['id'] in CHUNK_ACTIVE:
        if same:
            return
        # Old worker's publication guard will reject it. A subsequent request can
        # regenerate, or it will queue the new version after discarding its output.
        return
    run = {'document_id': doc['id'], 'revision': doc['revision'], 'config': settings,
           'config_hash': config_hash, 'input_hash': input_hash,
           'generation': uuid.uuid4().hex, 'status': 'failed' if error else 'queued',
           'count': 0, 'updated_at': now(), 'warnings': [],
           'message': error or '已加入本地切分队列。', 'error': error}
    with connect() as conn:
        conn.execute("DELETE FROM chunks WHERE document_id=?", (doc['id'],))
        write_chunk_run(conn, run)
    if error:
        return
    CHUNK_ACTIVE[doc['id']] = run['generation']
    POOL.submit(run_chunk_job, doc['id'], run['generation'])


def run_chunk_job(identifier, generation):
    try:
        with LOCK:
            doc = get(identifier)
            run = load_chunk_run(identifier)
            sync_admission(doc)
            if not run or run['generation'] != generation or not doc['admission']['eligible']:
                return
            run.update(status='processing', updated_at=now(), message='正在本地整理与切分。')
            with connect() as conn:write_chunk_run(conn, run)
        normalized, chunks = prepare(doc, run['config'])
        with LOCK:
            latest = get(identifier)
            sync_admission(latest)
            current_run = load_chunk_run(identifier)
            if (not latest['admission']['eligible'] or latest['revision'] != run['revision']
                or fingerprint(latest) != run['input_hash'] or configuration() != run['config']
                or not current_run or current_run['generation'] != generation):
                return
            run.update(status='complete', count=len(chunks), normalized=normalized,
                       warnings=normalized['warnings'], updated_at=now(), error=None,
                       message='本地切分完成；可检索性由当前向量索引状态决定。')
            with connect() as conn:
                conn.execute("DELETE FROM chunks WHERE document_id=?", (identifier,))
                conn.executemany("INSERT INTO chunks VALUES (?, ?, ?, ?)",
                    [(identifier, c['order'], c['id'], json.dumps(c, ensure_ascii=False)) for c in chunks])
                write_chunk_run(conn, run)
            save(latest)
            if INDEX_SERVICE is not None:
                INDEX_SERVICE.schedule(identifier)
    except Exception as exc:
        with LOCK:
            run = load_chunk_run(identifier)
            if run and run['generation'] == generation:
                run.update(status='failed', count=0, updated_at=now(),
                           error=str(exc) if isinstance(exc, ValueError) else '本地切分或保存失败，请重试。',
                           message='本地切分失败，未生成可用片段。')
                with connect() as conn:
                    conn.execute("DELETE FROM chunks WHERE document_id=?", (identifier,))
                    write_chunk_run(conn, run)
    finally:
        with LOCK:
            if CHUNK_ACTIVE.get(identifier) == generation:
                CHUNK_ACTIVE.pop(identifier, None)
            # Invalidate interrupted/stale runs, then pick up an admitted new
            # revision if parsing/review completed while this worker was running.
            try:
                latest = get(identifier)
                run = load_chunk_run(identifier)
                if run and run['generation'] == generation and run['status'] in {'queued', 'processing'}:
                    run.update(status='failed', message='结果已过期或任务中断，请重新生成。', error='stale_result', count=0)
                    with connect() as conn:write_chunk_run(conn, run)
                if latest.get('admission', {}).get('eligible') and (not run or run['revision'] != latest['revision']):
                    schedule_chunks(latest)
            except HTTPException:
                pass


@asynccontextmanager
async def lifespan(app):
    global INDEX_SERVICE, SEMANTIC_ERROR, RAG_SERVICE
    from app.llm import startup_check
    app.state.llm_health=startup_check()
    if app.state.llm_health.get('notice'):
        import logging
        logging.getLogger(__name__).warning(app.state.llm_health['notice'])
    initialize()
    MANAGED_RAG.clear()
    from app.rag import RagService
    RAG_SERVICE = RagService(sys.modules[__name__])
    SEMANTIC_ERROR = None
    if os.environ.get('P18_SEMANTIC_ENABLED') == '1':
        try:
            from app.semantic import IndexService
            INDEX_SERVICE = IndexService(sys.modules[__name__])
        except Exception:
            SEMANTIC_ERROR = '本地索引初始化失败，请检查可选依赖、模型配置及Qdrant目录占用。'
            INDEX_SERVICE = None
    with LOCK:
        for doc in all_docs():
            previous_state = doc["state"]
            if doc["state"] in STATES:
                doc.update(state="failed", quality="failed", error="上次处理因服务停止而中断，请重试。")
                save(doc)
            elif doc["state"] == "deleting":
                doc.update(state="delete_failed", error="上次删除中断，请重试删除。")
                save(doc)
            # Old generic confirmations did not attest to category-specific
            # checks. Keep history, but require one explicit review before use.
            if doc['state'] == 'ready' and categories(doc) and not confirmed(doc):
                doc.update(state='review', quality='review')
                event(doc, 'admission_review_required')
            if 'admission' not in doc or doc['state'] != previous_state:
                save(doc)
        for doc in all_docs():
            if doc.get('admission', {}).get('eligible'):
                schedule_chunks(doc)
    if INDEX_SERVICE is not None:
        INDEX_SERVICE.recover()
    yield
    # Finish bounded local preparation before a test/app changes its database.
    while CHUNK_ACTIVE:
        import asyncio
        await asyncio.sleep(.02)
    for child in getattr(sys.modules[__name__],'BUSINESS_CHILDREN',[]):
        child.POOL.shutdown(wait=True)
        if child.INDEX_SERVICE and not child.INDEX_SERVICE.closed:child.INDEX_SERVICE.close()
    if INDEX_SERVICE is not None:
        INDEX_SERVICE.close()
        INDEX_SERVICE = None
    with LOCK:
        for proc in list(ACTIVE.values()):
            kill_process(proc)


app = FastAPI(title="P18 文档工作台", lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])


@app.middleware("http")
async def local_guard(request: Request, call_next):
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        # No CORS permission: foreign origins cannot send this custom header.
        if request.headers.get("X-P18-Client") != "workbench":
            return JSONResponse({"detail": "请从本机工作台操作。"}, status_code=403)
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            return JSONResponse({"detail": "不允许跨站操作。"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; frame-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'self'"
    return response


def index_status(identifier):
    if INDEX_SERVICE is None:
        return {'status': 'unavailable' if SEMANTIC_ERROR else 'disabled', 'searchable': False,
                'message': SEMANTIC_ERROR or '本地语义后端未启用；安装可选依赖并设置 P18_SEMANTIC_ENABLED=1。'}
    return INDEX_SERVICE.status(identifier)


def require_semantic():
    if INDEX_SERVICE is None:
        raise HTTPException(503, {'code': 'model_unavailable', 'message': SEMANTIC_ERROR or '本地语义后端未启用。'})
    return INDEX_SERVICE


class SearchBody(BaseModel):
    mode: Literal["vector", "hybrid", "hybrid_dedup"] | None = None
    query: str = Field(min_length=1, max_length=2000)
    document_id: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=50, strict=True)


@app.get('/api/semantic')
def semantic_health():
    from app.local_setup import check_local_runtime
    service = INDEX_SERVICE
    return {'setup': check_local_runtime(), 'enabled': service is not None, 'error': SEMANTIC_ERROR or (service.provider.last_error if service else None),
            'model': service.config if service else None,
            'metrics': service.provider.metrics if service else {},
            'model_loaded': bool(service and service.provider.process and service.provider.process.is_alive()),
            'scope': 'local', 'external_inference': False, 'retrieval_mode': os.environ.get('P18_SEARCH_MODE', 'vector')}


@app.get('/api/documents/{identifier}/index')
def document_index(identifier: str):
    with LOCK:
        available(identifier)
        return index_status(identifier)


@app.post('/api/documents/{identifier}/index')
async def build_index(identifier: str, request: Request):
    body = await request.json()
    service = require_semantic()
    with LOCK:
        doc = available(identifier)
        if not isinstance(body, dict) or body.get('revision') != doc['revision'] or not service.snapshot(identifier):
            raise HTTPException(409, '当前解析版本无效或尚无通过审核的有效切分结果。')
        if not service.current_config():
            raise HTTPException(409, '模型配置已变化，请重启后重建索引。')
        service.schedule(identifier, retry=True)
        return service.status(identifier)


@app.post('/api/search')
def semantic_search(body: SearchBody):
    from app.embedding import EmbeddingError
    from app.semantic import SemanticError
    if not body.query.strip():
        raise HTTPException(422, '问题不能为空。')
    service = require_semantic()
    try:
        top_k = body.top_k if body.top_k is not None else int(os.environ.get('P18_SEARCH_TOP_K', '5'))
        if not 1 <= top_k <= 50:
            raise ValueError()
    except ValueError:
        raise HTTPException(503, 'P18_SEARCH_TOP_K 必须为1–50。')
    try:
        if library_api.principal.get() is not None:
            visible = library_api.visible_ids(sys.modules[__name__], all_docs(), evidence=True)
            if body.document_id and body.document_id not in visible:
                raise HTTPException(404, '文档不存在或不可访问')
            result = service.search(body.query.strip(), body.document_id, top_k, mode=body.mode,
                                    document_filter=lambda d: d['id'] in visible)
            fresh = library_api.visible_ids(sys.modules[__name__], all_docs(), evidence=True)
            result['results'] = [h for h in result.get('results', [])
                if all(m.get('document_id') in fresh for m in h.get('members', [h]))]
            return result
        return service.search(body.query.strip(), body.document_id, top_k, mode=body.mode)
    except (EmbeddingError, SemanticError) as exc:
        raise HTTPException(503, {'code': exc.code, 'message': str(exc)}) from exc


class ExternalPermissionBody(BaseModel):
    model_config = {"extra":"forbid", "strict":True}
    revision: int = Field(ge=1)
    fingerprint: str = Field(min_length=64,max_length=64)
    classification: Literal['fictional','public_verified'] | None = None
    checks: dict[str,bool] = Field(default_factory=dict)


@app.post('/api/documents/{identifier}/external-permission')
def grant_external_permission(identifier: str, body: ExternalPermissionBody):
    return change_external_permission(identifier,body,False)


@app.post('/api/documents/{identifier}/external-permission/revoke')
def revoke_external_permission(identifier: str, body: ExternalPermissionBody):
    return change_external_permission(identifier,body,True)


def change_external_permission(identifier, body, revoke):
    from app.egress import update, audit, CHECKS
    from app.egress_gate import gate
    # Gate first, then data lock: never wait for network completion holding LOCK.
    with gate().changing(), LOCK:
        doc=available(identifier)
        try:return update(DATA,doc,body.revision,body.fingerprint,body.classification,body.checks,revoke)
        except ValueError as exc:
            code=str(exc)
            audit(DATA,'permission_blocked',{'document_id':identifier,'revision':body.revision,'code':code,
                'classification':body.classification,'checks':{k:body.checks.get(k) for k in CHECKS}})
            raise HTTPException(409,{'code':code,'message':'授权条件未满足或文档版本已变化，请重新核对当前文档及全部三项确认。'}) from None


class RagPrepareBody(BaseModel):
    model_config = {"extra": "forbid"}
    question: str = Field(min_length=1, max_length=2000)
    session_id: str | None = Field(default=None, max_length=100)


class RagDraftBody(RagPrepareBody):
    turn_id: str | None = Field(default=None, min_length=1, max_length=100)


class RagSelectionBody(BaseModel):
    model_config = {"extra": "forbid", "strict": True}
    draft_id: str = Field(min_length=1, max_length=100)
    selection_version: int = Field(ge=0)
    candidate_ids: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(max_length=80)


class RagAnswerBody(BaseModel):
    model_config = {"extra": "forbid"}
    ticket: str = Field(min_length=1, max_length=100)
    consent: bool = Field(strict=True)


def current_rag():
    user = library_api.principal.get()
    if user is None:
        return RAG_SERVICE
    from app.rag import RagService, SessionDeepSeekClient
    from app.llm import RoutedClient
    from app.library_store import session_by_digest
    with LOCK, connect() as conn:
        for key in list(MANAGED_RAG):
            if not session_by_digest(conn, key):
                MANAGED_RAG.pop(key, None)
        if not session_by_digest(conn, user['session_digest']):
            raise HTTPException(401, '登录会话已失效')
        key = user['session_digest']
        if key not in MANAGED_RAG:
            if len(MANAGED_RAG) >= 64:
                raise HTTPException(503, '问答会话过多，请稍后重试')
            MANAGED_RAG[key] = RagService(sys.modules[__name__], client=(RoutedClient(session=True) if 'LLM_PROVIDER' in os.environ else SessionDeepSeekClient()))
        return MANAGED_RAG[key]


def rag_call(method, *args):
    from app.rag import RagError
    from app.embedding import EmbeddingError
    from app.semantic import SemanticError
    try:
        return getattr(current_rag(), method)(*args)
    except (RagError, EmbeddingError, SemanticError) as error:
        raise HTTPException(409, {'code':error.code,'message':str(error),**({'details':error.details} if getattr(error,'details',None) is not None else {})})


def require_private_credential_transport(request):
    local = request.url.hostname in {'localhost','127.0.0.1','::1'} and request.client and request.client.host in {'127.0.0.1','::1'}
    if request.url.scheme != 'https' and not local:
        raise HTTPException(400, '密钥配置仅允许HTTPS或本机回环连接。')
    if library_api.principal.get() is None:
        raise HTTPException(401, '请先正常登录。')


@app.get('/api/rag/credentials')
def credential_status(request: Request):
    require_private_credential_transport(request)
    service=current_rag()
    cfg=service.configuration()
    from app.rag import model_endpoint
    return {'configured':bool(service.client.configured),'scope':'login_session',
            'persistent':False,'provider':service.client.label,'endpoint':model_endpoint(cfg['base_url']),
            'notice':'仅本次登录有效；不回传密钥。配置不等于文档获准外发。'}


@app.put('/api/rag/credentials')
async def configure_credentials(request: Request):
    require_private_credential_transport(request)
    raw=b''
    async for part in request.stream():
        raw+=part
        if len(raw)>2048:
            raise HTTPException(422,'密钥请求过大；请求内容不会回显。')
    try:
        if len(raw)>2048:raise ValueError()
        body=json.loads(raw)
        import re
        if not isinstance(body,dict) or set(body)!={'api_key'} or not isinstance(body['api_key'],str):raise ValueError()
        value=body['api_key'].strip()
        if not re.fullmatch(r'[A-Za-z0-9_-]{16,256}',value):raise ValueError()
    except (ValueError,TypeError,UnicodeError):
        raise HTTPException(422,'密钥格式不正确；请求内容不会回显。') from None
    service=current_rag()
    with service.lock:
        if any(s.get('busy') for s in service.sessions.values()):
            raise HTTPException(409,'问答请求正在进行，请结束后再更改密钥配置。')
        service.client.set_key(value)
        service.tickets.clear()
    return {'configured':True,'scope':'login_session','persistent':False,'verified':False}


@app.delete('/api/rag/credentials')
def clear_credentials(request: Request):
    require_private_credential_transport(request)
    service=current_rag()
    with service.lock:
        if any(s.get('busy') for s in service.sessions.values()):
            raise HTTPException(409,'问答请求正在进行，请结束后再更改密钥配置。')
        service.client.set_key(None)
        service.tickets.clear()
    return {'configured':False,'scope':'login_session','persistent':False}


@app.post('/api/rag/fallback')
async def confirm_llm_fallback(request: Request):
    require_private_credential_transport(request)
    body=await request.json()
    if not isinstance(body,dict) or set(body)!={'confirm_external_fallback'} or body['confirm_external_fallback'] is not True:
        raise HTTPException(422,'必须明确确认切换到外部DeepSeek。')
    service=current_rag()
    from app.llm import RoutedClient
    if not isinstance(service.client,RoutedClient):raise HTTPException(409,'当前路由不支持故障降级。')
    with service.lock:
        if any(s.get('busy') for s in service.sessions.values()):raise HTTPException(409,'请等待当前回答结束。')
        try:service.client.confirm_fallback()
        except Exception as e:raise HTTPException(409,{'code':getattr(e,'code','fallback_error'),'message':str(e)})
        service.tickets.clear();service.drafts.clear();service.sessions.clear();service.receipts.clear()
    return {'confirmed':True,'provider':'deepseek','notice':'旧确认已失效；请重新检索、选择获准证据并人工确认本轮外发。'}


class RagProviderBody(BaseModel):
    model_config = {"extra":"forbid", "strict":True}
    provider: Literal['ollama','deepseek']
    confirm_external: bool = False


@app.post('/api/rag/provider')
def select_llm_provider(body: RagProviderBody, request: Request):
    require_private_credential_transport(request)
    service=current_rag()
    from app.llm import RoutedClient
    from app.rag import RagError
    if not isinstance(service.client,RoutedClient):raise HTTPException(409,'当前部署不支持会话模型切换。')
    if service.source_library!='demo' and body.provider=='deepseek':raise HTTPException(403,'启辰库禁止使用外部模型。')
    if body.provider=='deepseek' and body.confirm_external is not True:raise HTTPException(422,'必须明确确认选择外部DeepSeek。')
    with service.lock:
        if any(s.get('busy') for s in service.sessions.values()):raise HTTPException(409,'请等待当前回答结束后再切换模型。')
        try:service.client.select_provider(body.provider,body.confirm_external)
        except RagError as error:raise HTTPException(409,{'code':error.code,'message':str(error)})from None
        service.tickets.clear();service.drafts.clear();service.sessions.clear();service.receipts.clear()
    return {'provider':body.provider,'scope':'login_session','notice':'仅更改本次登录的模型路由，未发送资料；旧证据和确认已失效，请重新检索核对。'}


@app.get('/api/rag')
def rag_health():
    return current_rag().status()


@app.post('/api/rag/prepare')
def rag_prepare(body: RagPrepareBody):
    # 兼容端点：自动选证据并签发票据，绕过人工勾选。登录态下禁用，
    # 只保留给无会话的本地脚本与回归测试。
    if library_api.principal.get() is not None:
        raise HTTPException(404, '该接口仅用于本地兼容模式，请改用 /api/rag/drafts')
    return rag_call('prepare', body.question, body.session_id)


@app.post('/api/rag/drafts')
def rag_draft(body: RagDraftBody):
    return rag_call('draft', body.question, body.session_id, body.turn_id)


@app.post('/api/rag/selection')
def rag_selection(body: RagSelectionBody):
    return rag_call('selection', body.draft_id, body.selection_version, body.candidate_ids)


@app.post('/api/rag/answer')
def rag_answer(body: RagAnswerBody):
    return rag_call('answer', body.ticket, body.consent)


@app.get("/api/config")
def config():
    return {"max_file": MAX_FILE, "max_batch": MAX_BATCH, "max_files": 20, "max_pages": 200,
            "workers": 2, "conversion": bool(soffice_path()), "indexing": INDEX_SERVICE is not None, "scope": "local",
            "workbench_version": "semantic-ui-v1", "data_directory": str(DATA.resolve())}


@app.get("/api/documents")
def documents():
    with LOCK:
        return sorted([public(d) for d in all_docs() if d["state"] not in {"deleted", "superseded"} and library_api.visible(sys.modules[__name__], d)],
                      key=lambda d: d["created_at"], reverse=True)


@app.get("/api/documents/{identifier}")
def detail(identifier: str):
    with LOCK:
        doc = get(identifier)
        if doc["state"] in {"deleted", "deleting", "delete_failed", "superseded"}:
            raise HTTPException(404, "文档不可用。")
        with connect() as conn:
            events = [dict(row) for row in conn.execute("SELECT action, at, revision, payload FROM events WHERE document_id=? ORDER BY id", (identifier,))]
        for item in events:
            item["payload"] = json.loads(item["payload"]) if item["payload"] else None
        return {**public(doc, True), "events": events}


@app.post("/api/documents")
async def upload(files: list[UploadFile] = File(...), mode: str = Form("ask"), replace_id: str = Form("")):
    if mode not in {"ask", "keep", "replace"}:
        raise HTTPException(400, "无效的同名处理方式。")
    if not 1 <= len(files) <= 20:
        raise HTTPException(400, "一次请选择 1–20 个文件。")
    if mode == "replace" and len(files) != 1:
        raise HTTPException(400, "替换操作一次只处理一个文件。")
    loaded, total = [], 0
    for f in files:
        name = (f.filename or "未命名").replace("\\", "/").split("/")[-1][:200]
        content = await f.read(MAX_FILE + 1)
        total += len(content)
        loaded.append((name, content))
        await f.close()
    if total > MAX_BATCH:
        raise HTTPException(400, "单批文件总大小超过 100 MB，请分批上传。")
    responses = []
    with LOCK:
        for name, content in loaded:
            ext = Path(name).suffix.lower()
            if len(content) > MAX_FILE or not content or ext not in {".docx", ".doc", ".pdf", ".xlsx"}:
                responses.append({"name": name, "status": "rejected", "message": "文件为空、超过 20 MB，或不属于 PDF / DOCX / DOC / XLSX。"})
                continue
            digest = hashlib.sha256(content).hexdigest()
            existing = [d for d in all_docs() if d["state"] not in {"deleted", "deleting", "delete_failed", "superseded"}]
            if library_api.principal.get() is not None:
                visible_existing = library_api.visible_ids(sys.modules[__name__], existing)
                existing = [d for d in existing if d['id'] in visible_existing]
            duplicate = next((d for d in existing if d["sha256"] == digest), None)
            if duplicate:
                responses.append({"name": name, "status": "duplicate", "id": duplicate["id"], "message": "相同内容已存在，未重复上传。"})
                continue
            matches = [d for d in existing if d["name"] == name]
            if matches and mode == "ask":
                responses.append({"name": name, "status": "conflict", "candidates": [{"id": d["id"], "name": d["name"], "created_at": d["created_at"]} for d in matches], "message": "同名文件内容不同，请选择另存或替换。"})
                continue
            if mode == "replace":
                target = next((d for d in matches if d["id"] == replace_id), None)
                if not target or target["state"] in STATES:
                    responses.append({"name": name, "status": "rejected", "message": "替换目标不存在或正在处理，请刷新后重试。"})
                    continue
                if any(d.get("replaces") == replace_id and d["state"] in STATES | {"review", "held", "ready"} for d in existing):
                    responses.append({"name": name, "status": "rejected", "message": "该文档已有待处理的替换，请先处理或删除该替换文件。"})
                    continue
            identifier = str(uuid.uuid4())
            folder = folder_for(identifier)
            folder.mkdir()
            (folder / ("original" + ext)).write_bytes(content)
            doc = {"id": identifier, "name": name, "ext": ext, "size": len(content), "sha256": digest,
                   "state": "queued", "quality": "pending", "issues_count": 0, "characters": 0,
                   "created_at": now(), "revision": 1, "replaces": replace_id if mode == "replace" else None,
                   "reviewed_at": None, "error": None}
            save(doc)
            event(doc, "uploaded")
            POOL.submit(run_job, identifier, 1)
            responses.append({"name": name, "status": "accepted", "id": identifier})
    return responses


@app.post("/api/documents/{identifier}/review")
async def review(identifier: str, request: Request):
    body = await request.json()
    with LOCK:
        doc = get(identifier)
        if doc["state"] not in {"review", "held"} or body.get("revision") != doc["revision"]:
            raise HTTPException(409, "解析结果已变化或无需复核，请刷新后操作。")
        action = body.get("action")
        if action not in {"accept", "hold"}:
            raise HTTPException(400, "请选择确认使用或暂不入库。")
        reviewer = body.get('reviewer')
        note = body.get('note', '')
        if not isinstance(reviewer, str) or not reviewer.strip() or len(reviewer.strip()) > 80:
            raise HTTPException(400, "请填写审核人姓名或工号（1–80 字符，人工填写，未验证身份）。")
        if not isinstance(note, str) or len(note.strip()) > 2000:
            raise HTTPException(400, "审核备注不能超过 2000 字符。")
        reviewer, note = reviewer.strip(), note.strip()
        checks = body.get('checks', {})
        if not isinstance(checks, dict):
            raise HTTPException(400, "复核确认格式不正确。")
        if action == 'accept':
            if 'unusable' in categories(doc):
                raise HTTPException(409, "文件没有可用内容，不能确认入库，请更换文件或重新解析。")
            if any(checks.get(r['key']) is not True for r in requirements(doc)):
                raise HTTPException(400, "请逐项核对并确认；已知错误或无法判断的内容应暂不入库。")
        outcome = 'accepted' if action == 'accept' else body.get('outcome', 'uncertain')
        if outcome not in {'accepted', 'incorrect', 'uncertain'} or (action == 'hold' and outcome == 'accepted'):
            raise HTTPException(400, "请选择确认有误或无法判断。")
        doc['review_decision'] = {'revision': doc['revision'], 'outcome': outcome,
                                  'checks': {r['key']: checks.get(r['key']) is True for r in requirements(doc)}, 'at': now(),
                                  'reviewer': reviewer, 'identity_source': 'manual', 'note': note}
        doc.update(state="ready" if action == "accept" else "held", reviewed_at=now())
        if action == "accept":
            activate_replacement(doc)
        save(doc)
        event(doc, "review_" + action, {**doc['review_decision'], 'document_name': doc['name'],
              'requirements': requirements(doc), 'issues': (doc.get('result') or {}).get('issues', []),
              'preview_warnings': (doc.get('result') or {}).get('preview_warnings', [])})
        schedule_chunks(doc)
        return public(doc, True)


@app.get("/api/documents/{identifier}/chunks")
def chunks_view(identifier: str):
    with LOCK:
        return chunk_result(available(identifier), index=index_status(identifier))


@app.post("/api/documents/{identifier}/chunks")
async def regenerate_chunks(identifier: str, request: Request):
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(400, '请提供当前解析版本。')
    with LOCK:
        doc = available(identifier)
        sync_admission(doc)
        if body.get('revision') != doc['revision'] or not doc['admission']['eligible']:
            raise HTTPException(409, '当前版本尚未通过入库条件，或解析版本已变化。')
        schedule_chunks(doc, retry_failed=True)
        return chunk_result(doc, index=index_status(identifier))


@app.post("/api/documents/{identifier}/retry")
def retry(identifier: str):
    with LOCK:
        doc = get(identifier)
        if doc["state"] in STATES or identifier in ACTIVE:
            return {"message": "任务已经在队列中或处理中。"}
        if doc["state"] != "failed":
            raise HTTPException(409, "只有处理失败的文档可以重试。")
        doc.update(state="queued", quality="pending", error=None, reviewed_at=None, review_decision=None, result=None,
                   revision=doc["revision"] + 1, characters=0, issues_count=0)
        save(doc)
        event(doc, "retry")
        POOL.submit(run_job, identifier, doc["revision"])
        return public(doc)


@app.post("/api/documents/{identifier}/reparse")
async def reparse(identifier: str, request: Request):
    body = await request.json()
    with LOCK:
        doc = available(identifier)
        if not isinstance(body, dict) or body.get('revision') != doc['revision']:
            raise HTTPException(409, '解析版本已变化，请刷新后重试。')
        if doc['state'] in STATES or identifier in ACTIVE:
            raise HTTPException(409, '文档仍在处理中。')
        archive = folder_for(identifier) / 'history'
        archive.mkdir(exist_ok=True)
        (archive / f"revision-{doc['revision']}.json").write_text(json.dumps(doc, ensure_ascii=False), encoding='utf-8')
        event(doc, 'reparse_requested', {'previous_revision': doc['revision']})
        doc.update(state='queued', quality='pending', error=None, reviewed_at=None,
                   review_decision=None, result=None, revision=doc['revision']+1,
                   characters=0, issues_count=0)
        save(doc)
        POOL.submit(run_job, identifier, doc['revision'])
        return public(doc)


@app.delete("/api/documents/{identifier}")
def delete(identifier: str):
    with LOCK:
        doc = get(identifier)
        # Include superseded artifacts: they are not a user-visible version store.
        targets = [doc]
        all_records = all_docs()
        pending = {identifier}
        while pending:
            children = [d for d in all_records if d.get("superseded_by") in pending and d not in targets]
            targets.extend(children)
            pending = {d["id"] for d in children}
        for target in targets:
            target["state"] = "deleting"
            save(target)
            proc = ACTIVE.get(target["id"])
            if proc:
                kill_process(proc)
                proc.wait(timeout=10)
            try:
                folder = folder_for(target["id"])
                if folder.exists():
                    shutil.rmtree(folder)
                # Keep only a minimal tombstone; no filename, content or source hash.
                tombstone = {"id": target["id"], "state": "deleted", "revision": target["revision"], "deleted_at": now()}
                save(tombstone)
                event(tombstone, "deleted")
            except OSError:
                target.update(state="delete_failed", error="文件清理未完成，已禁止使用；请重试删除。")
                save(target)
                raise HTTPException(500, target["error"])
    return {"deleted": True}


def available(identifier):
    doc = get(identifier)
    if doc["state"] in {"deleted", "deleting", "delete_failed", "superseded"}:
        raise HTTPException(404, "文档不可用。")
    return doc


def source_guard(doc, revision=None, index_token=None, chunk_id=None):
    """Optional guards keep legacy previews compatible; new QA supplies all three."""
    if all(x is None for x in (revision, index_token, chunk_id)):
        return None
    if revision is not None and index_token is None and chunk_id is None:
        if doc['revision'] != revision:
            raise HTTPException(409, {"code": "source_stale", "message": "来源解析版本已改变。"})
        return None
    if any(x is None for x in (revision, index_token, chunk_id)):
        raise HTTPException(409, {"code": "source_stale", "message": "来源标识不完整，请重新检索。"})
    service = require_semantic()
    snap, run = service.snapshot(doc['id']), service.read(doc['id'])
    if (doc['revision'] != revision or not service.valid(run, snap)
            or run.get('status') != 'complete' or not service.current_config()
            or snap['token'] != index_token):
        raise HTTPException(409, {"code": "source_stale", "message": "来源版本或索引已失效，请重新检索。"})
    chunk = next((c for c in snap['chunks'] if c['id'] == chunk_id), None)
    if chunk is None:
        raise HTTPException(409, {"code": "source_stale", "message": "来源片段已失效，请重新检索。"})
    return chunk


@app.get("/api/documents/{identifier}/source")
def source_read(identifier: str, revision: int, index_token: str, chunk_id: str):
    with LOCK:
        doc = available(identifier)
        chunk = source_guard(doc, revision, index_token, chunk_id)
        return {"source": chunk, "document": public(doc, detailed=True)}


@app.get("/api/documents/{identifier}/source/highlight")
def source_highlight(identifier: str, revision: int, index_token: str, chunk_id: str):
    """Read-only exact text geometry, with the same current-source guard as preview."""
    from app.qa_highlight import locate
    with LOCK:
        doc = available(identifier)
        chunk = source_guard(doc, revision, index_token, chunk_id)
        relative = (doc.get("result") or {}).get("preview", {}).get("original")
        if not relative:
            return {"status": "unavailable", "pages": [], "message": "暂无可靠预览位置；以下为真实提取片段。"}
        return locate(folder_for(identifier) / relative, doc["ext"], chunk)


@app.get("/api/documents/{identifier}/file/{variant}")
def file_download(identifier: str, variant: str, revision: int | None = None, index_token: str | None = None, chunk_id: str | None = None):
    with LOCK:
        doc = available(identifier)
        source_guard(doc, revision, index_token, chunk_id)
        if variant == "original":
            relative = "original" + doc["ext"]
            name = doc["name"]
        elif variant == "converted" and (doc.get("result") or {}).get("converted"):
            relative = doc["result"]["converted"]
            name = Path(doc["name"]).stem + "-转换副本.docx"
        else:
            raise HTTPException(404, "该文件副本尚未生成。")
        return FileResponse(folder_for(identifier) / relative, filename=name, media_type="application/octet-stream")


@app.get("/api/documents/{identifier}/preview/{variant}/meta")
def preview_meta(identifier: str, variant: str, revision: int | None = None, index_token: str | None = None, chunk_id: str | None = None):
    with LOCK:
        doc = available(identifier)
        source_guard(doc, revision, index_token, chunk_id)
        relative = (doc.get("result") or {}).get("preview", {}).get(variant)
        if not relative:
            raise HTTPException(404, "预览尚未生成，可下载原文件查看。")
        with fitz.open(folder_for(identifier) / relative) as pdf:
            return {"pages": len(pdf), "converted_preview": doc["ext"] != ".pdf"}


@app.get("/api/documents/{identifier}/preview/{variant}/{page}")
def preview_page(identifier: str, variant: str, page: int, zoom: float = Query(1, ge=1, le=3), revision: int | None = None, index_token: str | None = None, chunk_id: str | None = None):
    with LOCK:
        doc = available(identifier)
        source_guard(doc, revision, index_token, chunk_id)
        relative = (doc.get("result") or {}).get("preview", {}).get(variant)
        if not relative:
            raise HTTPException(404, "预览尚未生成。")
        with fitz.open(folder_for(identifier) / relative) as pdf:
            if not 1 <= page <= len(pdf):
                raise HTTPException(404, "页码不存在。")
            target = pdf[page - 1]
            scale = min(2 * zoom, 4200 / max(target.rect.width, target.rect.height))
            png = target.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False).tobytes("png")
        return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"})


@app.get("/library/")
def library_page():
    return FileResponse(ROOT/'web/app/index.html')


@app.get('/demo')
def demo_page():
    from app import library_store
    with connect() as conn:
        if not library_store.demo_enabled(conn): raise HTTPException(404, '未启用演示环境')
    return FileResponse(ROOT / 'web' / 'demo.html')


@app.get("/login")
@app.get("/documents")
@app.get("/search")
@app.get("/qa")
@app.get("/identity")
@app.get("/")
def index():
    return FileResponse(ROOT/'web/app/index.html')


app.mount('/assets', StaticFiles(directory=ROOT/'web/app/assets',check_dir=False),name='unified-assets')
app.mount("/library/assets", StaticFiles(directory=ROOT / "web" / "library" / "assets", check_dir=False), name="library-assets")
app.mount("/static", StaticFiles(directory=ROOT / "web"), name="static")


from app import library_api
library_api.install(app, sys.modules[__name__])
