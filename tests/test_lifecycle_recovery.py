"""Lifecycle faults use synthetic records/vectors; no model or enterprise data."""
import json,threading,uuid
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from app import main
from app.semantic import IndexService
from test_workbench import client,upload,wait,pdf_bytes


def test_parsed_replacement_does_not_retire_old_before_index(client,monkeypatch):
    first=upload(client);wait(client,first['id'])
    monkeypatch.setenv('P18_SEMANTIC_ENABLED','1')
    service=SimpleNamespace(status=lambda identifier:{'status':'waiting','message':'synthetic test index pending','searchable':False},invalidate=lambda identifier:None,schedule=lambda *a,**k:None,close=lambda:None)
    service.replacement_usable=lambda identifier:service.status(identifier).get('searchable',False)
    monkeypatch.setattr(main,'INDEX_SERVICE',service)
    second=upload(client,data=pdf_bytes('New synthetic content'),mode='replace',replace_id=first['id']);new=wait(client,second['id'])
    assert new['state']=='ready' and main.get(first['id'])['state']=='ready'
    assert upload(client,data=pdf_bytes('Another synthetic replacement'),mode='replace',replace_id=first['id'])['status']=='rejected'
    # Failed index, unavailable backend and stale snapshot all preserve the old file.
    for status in ['failed','stale','waiting']:
        service.status=lambda identifier:{'status':status,'searchable':False}
        main.on_index_complete(new['id']);assert main.get(first['id'])['state']=='ready'
    monkeypatch.setattr(main,'INDEX_SERVICE',None);main.on_index_complete(new['id']);assert main.get(first['id'])['state']=='ready'
    monkeypatch.setattr(main,'INDEX_SERVICE',service);service.status=lambda identifier:{'searchable':True}
    main.on_index_complete(new['id']);old=main.get(first['id']);assert old['state']=='superseded' and old['superseded_by']==new['id']
    main.on_index_complete(new['id']);assert main.get(first['id'])==old


def test_reviewed_file_still_waits_for_valid_index(client,monkeypatch):
    d=upload(client);wait(client,d['id']);old=main.get(d['id'])
    new={**old,'id':'synthetic-review','replaces':old['id'],'state':'review'};main.save(new)
    monkeypatch.setenv('P18_SEMANTIC_ENABLED','1');monkeypatch.setattr(main,'INDEX_SERVICE',SimpleNamespace(replacement_usable=lambda identifier:True,status=lambda identifier:{'searchable':True},invalidate=lambda i:None,close=lambda:None))
    main.on_index_complete(new['id']);assert main.get(old['id'])['state']=='ready'


@pytest.fixture
def vector_service(tmp_path):
    from qdrant_client import QdrantClient,models
    svc=IndexService.__new__(IndexService);svc.models=models;svc.client=QdrantClient(path=str(tmp_path/'synthetic-qdrant'));svc.vector_lock=threading.RLock();svc.store=SimpleNamespace(LOCK=threading.RLock());svc.closed=False
    expected={'document_id':'a','status':'stale','generation':'old-run','token':'old-token'};svc.read=lambda i:dict(expected);svc.snapshot=lambda i:None;svc.valid=lambda run,snap:False
    svc.client.create_collection('p18_test',vectors_config=models.VectorParams(size=2,distance=models.Distance.COSINE))
    points=[]
    for doc,token in [('a','old-token'),('a','new-token'),('b','old-token')]:points.append(models.PointStruct(id=str(uuid.uuid4()),vector=[1.,0.],payload={'document_id':doc,'token':token}))
    svc.client.upsert('p18_test',points=points,wait=True)
    yield svc,expected
    svc.client.close()


def test_stale_cleanup_only_deletes_matching_document_and_token(vector_service):
    s,e=vector_service;assert s._cleanup_stale('a',dict(e))
    rows=s.client.scroll('p18_test',with_payload=True)[0];assert {(p.payload['document_id'],p.payload['token'])for p in rows}=={('a','new-token'),('b','old-token')}


def test_new_generation_blocks_delayed_cleanup(vector_service):
    s,e=vector_service;old=dict(e);e.update(status='complete',generation='new-run',token='new-token')
    assert not s._cleanup_stale('a',old);assert s.client.count('p18_test').count==3


def test_cleanup_retries_once_and_can_resume_after_failure(vector_service,monkeypatch):
    s,e=vector_service;original=s.client.delete;calls=[]
    def fail_once(*a,**k):
        calls.append(1)
        if len(calls)==1:raise RuntimeError('synthetic disk issue')
        return original(*a,**k)
    monkeypatch.setattr(s.client,'delete',fail_once);assert s._cleanup_stale('a',dict(e))and len(calls)==2
    monkeypatch.setattr(s.client,'delete',Mock(side_effect=RuntimeError('persistent synthetic fault')))
    assert not s._cleanup_stale('a',dict(e));assert s.client.delete.call_count==2 and e['status']=='stale'
    monkeypatch.setattr(s.client,'delete',original);assert s._cleanup_stale('a',dict(e))


def test_recovery_queues_durable_stale_run_and_complete_replacement(vector_service):
    s,e=vector_service;s.store.all_docs=lambda:[{'id':'a'}];queue=[];s.pool=SimpleNamespace(submit=lambda *args:queue.append(args));s.invalidate=lambda i:None;s.schedule=lambda i:None
    s.recover();assert queue[0][1:]==('a',e)


def test_completed_index_recovery_calls_activation_without_reencoding(vector_service):
    s,e=vector_service;s.active=set();s.config_hash='cfg';s.config={};s.snapshot=lambda i:{'token':'new-token'};s.current_config=lambda:True;s.valid=lambda a,b:True;e['status']='complete';s._present=lambda snap:True;s.store.on_index_complete=Mock();s.pool=SimpleNamespace(submit=lambda *a:pytest.fail('must not reencode'))
    s.schedule('a');s.store.on_index_complete.assert_called_once_with('a')


def test_activation_bookkeeping_failure_keeps_completed_index(vector_service):
    s,e=vector_service;e['status']='complete';s.store.on_index_complete=Mock(side_effect=RuntimeError('synthetic audit failure'));writes=[];s.write=lambda run:writes.append(dict(run))
    s._replacement_ready('a');assert writes[-1]['status']=='complete' and writes[-1]['replacement_pending']


def test_audit_failure_after_retirement_can_be_repaired_idempotently(client,monkeypatch):
    first=upload(client);wait(client,first['id']);old=main.get(first['id']);new={**old,'id':'audit-replacement','replaces':old['id']};main.save(new)
    monkeypatch.setenv('P18_SEMANTIC_ENABLED','1');monkeypatch.setattr(main,'INDEX_SERVICE',SimpleNamespace(replacement_usable=lambda i:True,status=lambda i:{'searchable':True},invalidate=lambda i:None,close=lambda:None))
    original=main.event;monkeypatch.setattr(main,'event',Mock(side_effect=RuntimeError('synthetic audit disk issue')))
    with pytest.raises(RuntimeError):main.on_index_complete(new['id'])
    assert main.get(old['id'])['state']=='superseded'
    monkeypatch.setattr(main,'event',original);main.on_index_complete(new['id']);main.on_index_complete(new['id'])
    with main.connect()as c:assert c.execute("select count(*) from events where document_id=? and action='replacement_prepared'",(old['id'],)).fetchone()[0]==1


def test_cleanup_waiting_for_vector_does_not_block_admission_recheck(vector_service):
    s,e=vector_service;started=threading.Event()
    def cleanup():
        started.set();s._cleanup_stale('a',dict(e))
    with s.vector_lock:
        worker=threading.Thread(target=cleanup);worker.start();assert started.wait(1)
        acquired=s.store.LOCK.acquire(timeout=1)
        if acquired:s.store.LOCK.release()
    worker.join(2);assert acquired and not worker.is_alive()


def test_cleanup_never_holds_vector_waiting_for_business_lock(vector_service):
    s,e=vector_service
    with s.store.LOCK:
        worker=threading.Thread(target=s._cleanup_stale,args=('a',dict(e)));worker.start();worker.join(2)
        assert not worker.is_alive()
        assert s.vector_lock.acquire(timeout=1);s.vector_lock.release()


def test_complete_status_without_actual_points_is_not_a_usable_replacement(vector_service):
    s,e=vector_service;e['status']='complete';s.snapshot=lambda i:{'token':'new-token'};s.valid=lambda a,b:True;s.current_config=lambda:True;s._present=lambda snap:False
    assert not s.replacement_usable('a')
    s._present=lambda snap:True;assert s.replacement_usable('a')


def test_replacement_defers_instead_of_waiting_on_busy_vector_lock(vector_service):
    s,e=vector_service;e['status']='complete';s.snapshot=lambda i:{'token':'new-token'};s.valid=lambda a,b:True;s.current_config=lambda:True;s._present=lambda snap:True
    started=threading.Event();release=threading.Event()
    def busy():
        with s.vector_lock:started.set();release.wait(2)
    worker=threading.Thread(target=busy);worker.start();assert started.wait(1)
    try:assert not s.replacement_usable('a')
    finally:release.set();worker.join(2)
    s.store.on_index_complete=lambda identifier:False;writes=[];s.write=lambda run:writes.append(dict(run));s._replacement_ready('a');assert writes[-1]['replacement_pending'] and writes[-1]['status']=='complete'
