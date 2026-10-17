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
DATA = Path(os.environ.get("P18_DATA_DIR", ROOT / "runtime"))
DB = DATA / "workbench.sqlite3"
LOCK = threading.RLock()
POOL = ThreadPoolExecutor(max_workers=2)
ACTIVE = {}
CHUNK_ACTIVE = {}
INDEX_SERVICE = None
SEMANTIC_ERROR = None
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
    if detailed:
        result['chunking'] = chunk_result(doc, include_chunks=False)
        result['index'] = index_status(doc['id'])
    if not detailed:
        result.pop("result", None)
    return result


def activate_replacement(doc):
    target = doc.get("replaces")
    if not target:
        return
    try:
        old = get(target)
    except HTTPException:
        return
    if old["state"] not in {"deleted", "delete_failed", "deleting", "superseded"}:
        old["state"] = "superseded"
        old["superseded_by"] = doc["id"]
        save(old)
        event(old, "replacement_prepared")


def kill_process(proc):
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


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
            proc = subprocess.Popen([sys.executable, "-m", "app.parse_worker", str(folder), doc["ext"]],
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


def chunk_result(doc, include_chunks=True):
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
                       message='本地切分完成；尚未向量化或创建索引，当前不可检索。')
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
    global INDEX_SERVICE, SEMANTIC_ERROR
    initialize()
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
    query: str = Field(min_length=1, max_length=2000)
    document_id: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=50, strict=True)


@app.get('/api/semantic')
def semantic_health():
    service = INDEX_SERVICE
    return {'enabled': service is not None, 'error': SEMANTIC_ERROR or (service.provider.last_error if service else None),
            'model': service.config if service else None,
            'metrics': service.provider.metrics if service else {},
            'model_loaded': bool(service and service.provider.process and service.provider.process.is_alive()),
            'scope': 'local', 'external_inference': False}


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
        return service.search(body.query.strip(), body.document_id, top_k)
    except (EmbeddingError, SemanticError) as exc:
        raise HTTPException(503, {'code': exc.code, 'message': str(exc)}) from exc


@app.get("/api/config")
def config():
    return {"max_file": MAX_FILE, "max_batch": MAX_BATCH, "max_files": 20, "max_pages": 200,
            "workers": 2, "conversion": bool(soffice_path()), "indexing": INDEX_SERVICE is not None, "scope": "local"}


@app.get("/api/documents")
def documents():
    with LOCK:
        return sorted([public(d) for d in all_docs() if d["state"] not in {"deleted", "superseded"}],
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
            if len(content) > MAX_FILE or not content or ext not in {".docx", ".doc", ".pdf"}:
                responses.append({"name": name, "status": "rejected", "message": "文件为空、超过 20 MB，或不属于 PDF / DOCX / DOC。"})
                continue
            digest = hashlib.sha256(content).hexdigest()
            existing = [d for d in all_docs() if d["state"] not in {"deleted", "deleting", "delete_failed", "superseded"}]
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
                if any(d.get("replaces") == replace_id and d["state"] in STATES | {"review", "held"} for d in existing):
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
        return chunk_result(available(identifier))


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
        return chunk_result(doc)


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


@app.get("/api/documents/{identifier}/file/{variant}")
def file_download(identifier: str, variant: str):
    with LOCK:
        doc = available(identifier)
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
def preview_meta(identifier: str, variant: str):
    with LOCK:
        doc = available(identifier)
        relative = (doc.get("result") or {}).get("preview", {}).get(variant)
        if not relative:
            raise HTTPException(404, "预览尚未生成，可下载原文件查看。")
        with fitz.open(folder_for(identifier) / relative) as pdf:
            return {"pages": len(pdf), "converted_preview": doc["ext"] != ".pdf"}


@app.get("/api/documents/{identifier}/preview/{variant}/{page}")
def preview_page(identifier: str, variant: str, page: int, zoom: float = Query(1, ge=1, le=3)):
    with LOCK:
        doc = available(identifier)
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


@app.get("/")
def index():
    return FileResponse(ROOT / "web" / "index.html")


@app.get("/style.css")
def stylesheet():
    return FileResponse(ROOT / "web" / "style.css", media_type="text/css")


@app.get("/app.js")
def javascript():
    return FileResponse(ROOT / "web" / "app.js", media_type="text/javascript")


app.mount("/static", StaticFiles(directory=ROOT / "web"), name="static")
