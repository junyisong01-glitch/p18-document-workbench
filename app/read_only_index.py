"""Read the existing Qdrant snapshot with SQLite mode=ro; native Qdrant search.

No upsert, re-encoding, persistence migration, collection creation or copied index.
LocalCollection.load_vectors is the installed client's ordinary load path.
"""
from pathlib import Path
import json, sqlite3, threading
from qdrant_client import models
from qdrant_client.local.local_collection import LocalCollection
from qdrant_client.local.persistence import CollectionPersistence
from app.semantic import IndexService
from app.chunking import digest


class ReadOnlyPersistence(CollectionPersistence):
    def __init__(self, location):
        self.location = Path(location) / 'storage.sqlite'
        self.storage = sqlite3.connect(self.location.as_uri()+'?mode=ro', uri=True, check_same_thread=False)
        self.storage.execute('PRAGMA query_only=ON')

    def persist(self, point):
        raise PermissionError('只读知识库不允许写入向量')

    def delete(self, point_id):
        raise PermissionError('只读知识库不允许删除向量')


class ReadOnlyVectors:
    def __init__(self, data, collection):
        self.name = collection
        params = json.loads((data/'qdrant/meta.json').read_text())['collections'][collection]
        self.collection = LocalCollection(models.CreateCollection(**params))
        self.collection.storage = ReadOnlyPersistence(data/'qdrant/collection'/collection)
        self.collection.load_vectors()

    def query_points(self, collection, **kwargs):
        if collection != self.name:
            raise ValueError('未知集合')
        return self.collection.query_points(**kwargs)

    def close(self):
        self.collection.close()


class ReadOnlyIndex(IndexService):
    def __init__(self, store, provider):
        self.store, self.models = store, models
        self.provider = provider  # Same loaded local embedding process as six-doc library.
        self.config = provider.config
        self.config_hash = digest(self.config)
        self.collection = 'p18_' + self.config_hash
        self.vector_lock = threading.RLock()
        self.client = ReadOnlyVectors(store.DATA, self.collection)

    def write(self, *args, **kwargs):
        raise PermissionError('只读知识库不允许写入索引')

    schedule = invalidate = recover = _delete_document = write

    def close(self):
        self.client.close()  # Does not close the shared embedding provider.
