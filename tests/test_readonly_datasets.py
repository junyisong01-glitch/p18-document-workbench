"""Generated public fixtures; no real documents, credentials, models or live servers."""
import hashlib,json,sqlite3
import pytest
from qdrant_client import QdrantClient,models
from app.read_only_index import ReadOnlyVectors
from app.datasets import DatasetBody,ROLES
from app.library_policy import IDENTITIES

def test_read_only_snapshot_is_native_search_and_never_written(tmp_path):
    data=tmp_path/'library';client=QdrantClient(path=str(data/'qdrant'))
    client.create_collection('synthetic',vectors_config=models.VectorParams(size=2,distance=models.Distance.COSINE))
    client.upsert('synthetic',points=[models.PointStruct(id=1,vector=[1.0,0.0],payload={'synthetic':True}),models.PointStruct(id=2,vector=[0.0,1.0],payload={'synthetic':True})])
    native=client.query_points('synthetic',query=[1.0,0.0],limit=2).points;client.close()
    before={p.relative_to(data):hashlib.sha256(p.read_bytes()).hexdigest() for p in data.rglob('*') if p.is_file()}
    reader=ReadOnlyVectors(data,'synthetic')
    try:
        actual=reader.query_points('synthetic',query=[1.0,0.0],limit=2).points
        assert [p.id for p in actual]==[p.id for p in native]
        assert [p.score for p in actual]==pytest.approx([p.score for p in native])
        with pytest.raises(PermissionError):reader.collection.storage.persist(None)
        with pytest.raises(PermissionError):reader.collection.storage.delete(1)
        with pytest.raises(sqlite3.OperationalError):reader.collection.storage.storage.execute('DELETE FROM points')
    finally:reader.close()
    assert before=={p.relative_to(data):hashlib.sha256(p.read_bytes()).hexdigest() for p in data.rglob('*') if p.is_file()}

def test_dataset_field_is_not_role_or_path_authority():
    assert DatasetBody(dataset='demo').dataset=='demo'
    for data in [{'dataset':'../../data'},{'dataset':'qichen30','identity':'admin'}]:
        with pytest.raises(ValueError):DatasetBody(**data)

def test_four_roles_are_authenticated_department_identities():
    for identity in ['启辰研发岗位','启辰测试岗位','启辰运维岗位','启辰生产岗位']:
        assert identity in IDENTITIES and identity in ROLES
    assert IDENTITIES['启辰测试岗位']=='研发部' and IDENTITIES['启辰运维岗位']=='研发部'
