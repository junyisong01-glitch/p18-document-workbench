"""Recoverable single-process indexing. SQLite is the authority, Qdrant stores IDs."""
from concurrent.futures import ThreadPoolExecutor
import json
import math
import os
import threading
import uuid

from app.chunking import digest
from app.embedding import EmbeddingError, LocalQwen, settings


class SemanticError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class IndexService:
    def __init__(self, store):
        from qdrant_client import QdrantClient, models
        self.store, self.models = store, models
        self.provider = LocalQwen()
        self.config = self.provider.config
        self.config_hash = digest(self.config)
        self.collection = 'p18_' + self.config_hash
        self.vector_lock = threading.RLock()
        self.client = QdrantClient(path=str(store.DATA / 'qdrant'))
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(self.collection, vectors_config=models.VectorParams(
                size=self.config['dimension'], distance=models.Distance.COSINE))
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.active = set()
        self.closed = False

    def read(self, identifier):
        with self.store.connect() as conn:
            row = conn.execute('SELECT body FROM index_runs WHERE document_id=?', (identifier,)).fetchone()
        return json.loads(row[0]) if row else None

    def write(self, run):
        with self.store.connect() as conn:
            conn.execute('INSERT OR REPLACE INTO index_runs VALUES (?, ?)',
                         (run['document_id'], json.dumps(run, ensure_ascii=False)))

    def current_config(self):
        try:
            return digest(settings()) == self.config_hash
        except (ValueError, ImportError):
            return False

    def snapshot(self, identifier):
        try:
            doc = self.store.available(identifier)
            result = self.store.chunk_result(doc)
        except self.store.HTTPException:
            return None
        if result['status'] != 'complete' or not result['chunks']:
            return None
        chunks = result['chunks']
        token = digest({'revision': doc['revision'], 'generation': result['generation'],
                        'config': result['config_hash'], 'input': result['input_hash'], 'chunks': chunks})
        return {'doc': doc, 'chunks': chunks, 'token': token}

    def valid(self, run, snap):
        return bool(snap and run and run.get('token') == snap['token'] and run.get('config_hash') == self.config_hash)

    def point_id(self, snap, chunk):
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"p18-vector:{self.config_hash}:{snap['token']}:{chunk['id']}"))

    def status(self, identifier):
        with self.store.LOCK:
            run, snap = self.read(identifier), self.snapshot(identifier)
            answer = {'status': 'not_started', 'searchable': False, 'count': 0,
                      'model': self.config, 'message': '索引尚未建立。'}
            if run:
                answer.update(run)
                if not self.valid(run, snap) or not self.current_config():
                    answer.update(status='stale', searchable=False, count=0, message='索引已失效，需满足入库条件并重新建立。')
            elif not snap:
                doc = self.store.get(identifier)
                self.store.sync_admission(doc)
                if doc['admission']['eligible']:
                    answer.update(status='not_started', message='已满足入库条件，等待有效切分结果后建立索引。')
                else:
                    answer.update(status='blocked', message='尚无符合入库条件的有效切分片段。')
            answer['searchable'] = answer['status'] == 'complete'
            return answer

    def invalidate(self, identifier):
        # Caller holds SQLite/business lock; queue vector cleanup rather than
        # blocking document deletion on the model. Publication rechecks the token.
        run = self.read(identifier)
        if run and not self.valid(run, self.snapshot(identifier)):
            if run['status'] != 'stale':
                run.update(status='stale', searchable=False, count=0, message='文档或切分版本已变化，旧索引不再使用。')
                self.write(run)
                if not self.closed:
                    self.pool.submit(self._delete_document, identifier)

    def _delete_document(self, identifier):
        with self.vector_lock:
            for collection in self.client.get_collections().collections:
                if collection.name.startswith('p18_'):
                    self.client.delete(collection.name, points_selector=self.models.FilterSelector(
                        filter=self.models.Filter(must=[self.models.FieldCondition(
                            key='document_id', match=self.models.MatchValue(value=identifier))])))

    def _present(self, snap):
        ids = [self.point_id(snap, c) for c in snap['chunks']]
        try:
            with self.vector_lock:
                found = self.client.retrieve(self.collection, ids=ids, with_payload=True, with_vectors=False)
        except Exception:
            return False
        return len(found) == len(ids) and all(p.payload.get('token') == snap['token'] for p in found)

    def schedule(self, identifier, *, retry=False):
        with self.store.LOCK:
            if self.closed or identifier in self.active:
                return
            snap = self.snapshot(identifier)
            if not snap:
                self.invalidate(identifier)
                return
            if not self.current_config():
                return
            previous = self.read(identifier)
            if self.valid(previous, snap):
                if previous['status'] == 'complete' and self._present(snap):
                    return
                if previous['status'] == 'failed' and not retry:
                    return
            run = {'document_id': identifier, 'revision': snap['doc']['revision'], 'token': snap['token'],
                   'generation': uuid.uuid4().hex, 'config_hash': self.config_hash, 'model': self.config,
                   'status': 'waiting', 'count': 0, 'error': None, 'error_code': None,
                   'updated_at': self.store.now(), 'message': '等待本地向量化与索引建立。'}
            self.write(run)
            self.active.add(identifier)
            self.pool.submit(self._build, identifier, run)

    def _unchanged(self, identifier, run):
        current = self.read(identifier)
        return (current and current.get('generation') == run['generation'] and current['status'] != 'stale'
                and self.valid(run, self.snapshot(identifier)) and self.current_config())

    def _build(self, identifier, run):
        try:
            with self.store.LOCK:
                if not self._unchanged(identifier, run):
                    return
                snap = self.snapshot(identifier)
                run.update(status='building', message='正在本地生成向量并写入索引。', updated_at=self.store.now())
                self.write(run)
            points = []
            for chunk in snap['chunks']:
                vector = self.provider.encode([chunk['text']])[0]
                if len(vector) != self.config['dimension'] or not all(math.isfinite(x) for x in vector):
                    raise EmbeddingError('embedding_failed', '模型返回向量无效。')
                with self.store.LOCK:
                    if not self._unchanged(identifier, run):
                        return
                points.append(self.models.PointStruct(id=self.point_id(snap, chunk), vector=vector,
                              payload={'document_id': identifier, 'chunk_id': chunk['id'], 'token': snap['token']}))
            try:
                self._delete_document(identifier)
                with self.vector_lock:
                    self.client.upsert(self.collection, points=points, wait=True)
            except Exception as exc:
                raise SemanticError('index_write_failed', 'Qdrant 本地索引写入失败，可重试。') from exc
            with self.store.LOCK:
                if not self._unchanged(identifier, run):
                    self._delete_document(identifier)
                    return
                run.update(status='complete', count=len(points), error=None, error_code=None,
                           message='本地向量索引已建立；支持语义检索，未生成 AI 回答。', updated_at=self.store.now())
                self.write(run)
        except Exception as exc:
            with self.store.LOCK:
                current = self.read(identifier)
                if current and current.get('generation') == run['generation'] and current['status'] != 'stale':
                    run.update(status='failed', count=0, error_code=getattr(exc, 'code', 'index_failed'),
                               error=str(exc) if isinstance(exc, (EmbeddingError, SemanticError)) else '本地索引任务失败，可重试。',
                               message='索引建立失败，未发布可用结果。', updated_at=self.store.now())
                    self.write(run)
        finally:
            with self.store.LOCK:
                self.active.discard(identifier)
                snap = self.snapshot(identifier)
                latest = self.read(identifier)
                # Pick up a new admitted revision that finished while old work ran.
                if not self.closed and snap and latest and not self.valid(latest, snap):
                    self.schedule(identifier)

    def recover(self):
        with self.store.LOCK:
            for doc in self.store.all_docs():
                self.invalidate(doc['id'])
                self.schedule(doc['id'])

    def candidates(self, identifier=None):
        found = {}
        docs = [self.store.available(identifier)] if identifier else self.store.all_docs()
        for doc in docs:
            snap, run = self.snapshot(doc['id']), self.read(doc['id'])
            if self.valid(run, snap) and run['status'] == 'complete':
                for chunk in snap['chunks']:
                    found[self.point_id(snap, chunk)] = (snap, chunk)
        return found

    def search(self, query, identifier=None, top_k=5):
        if not self.current_config():
            raise SemanticError('configuration_changed', '模型配置已变化，需重启并重建索引。')
        with self.store.LOCK:
            candidates = self.candidates(identifier)
        if not candidates:
            return {'status': 'no_index', 'results': [], 'message': '没有当前有效的已建立索引，请查看构建状态。'}
        vector = self.provider.encode([query], query=True)[0]
        try:
            with self.vector_lock:
                hits = self.client.query_points(self.collection, query=vector, limit=top_k,
                    query_filter=self.models.Filter(must=[self.models.HasIdCondition(has_id=list(candidates))]),
                    with_payload=True, with_vectors=False).points
        except Exception as exc:
            raise SemanticError('search_failed', '本地向量检索失败，请检查索引后重试。') from exc
        results = []
        # Re-read SQLite after embedding and vector search; never trust payload text.
        with self.store.LOCK:
            if not self.current_config():
                raise SemanticError('configuration_changed', '模型配置已变化，结果未返回，请重启并重建。')
            current = self.candidates(identifier)
            for hit in hits:
                pair = current.get(str(hit.id))
                if not pair:
                    continue
                snap, chunk = pair
                if hit.payload.get('chunk_id') != chunk['id'] or hit.payload.get('token') != snap['token']:
                    continue
                results.append({'rank': len(results)+1, 'score': hit.score, 'document_id': snap['doc']['id'],
                                'document_name': snap['doc']['name'], 'chunk_id': chunk['id'], 'index_token': snap['token'],
                                'revision': chunk['revision'], 'order': chunk['order'], 'text': chunk['text'],
                                'section': chunk['section'], 'sources': chunk['sources'], 'risk': chunk['risk']})
        return {'status': 'ok' if results else 'no_results', 'results': results, 'model': self.config,
                'message': '相似度表示向量接近程度，不代表答案正确率；本次仅返回原文片段。' if results else '没有当前有效的检索结果。'}

    def close(self):
        self.closed = True
        self.pool.shutdown(wait=True)
        self.provider.close()
        with self.vector_lock:
            self.client.close()
