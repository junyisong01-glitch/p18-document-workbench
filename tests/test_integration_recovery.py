"""INT-002: no network, runtime library or implicit authorization."""
import time
from copy import deepcopy
import pytest
from app import main
from app.rag import RagError
from test_rag import rig
from test_rag_selection import select
from test_workbench import client, upload, wait


@pytest.mark.parametrize('boundary',['idle','restart'])
def test_expired_session_recovery_requires_new_draft_and_consent(rig,boundary):
    rig.grant(['b'])
    first=rig.rag.draft('虚构负责人？');p=select(rig,first)
    rig.provider.reply={'status':'answered','answer':'虚构负责人。[S1]','citations':['S1']}
    old=rig.rag.answer(p['ticket'],True);original=deepcopy(old)
    if boundary=='idle':rig.rag.sessions[old['session_id']]['at']=time.monotonic()-1801
    else:rig.rag.sessions.clear();rig.rag.drafts.clear();rig.rag.tickets.clear()
    with pytest.raises(RagError) as error:rig.rag.draft('虚构负责人？',old['session_id'])
    assert error.value.code=='session_expired'
    # Browser retains its old answer; recovery starts server-owned evidence from scratch.
    d=rig.rag.draft('虚构负责人？');assert d['session_id']!=old['session_id'] and d['history']==[]
    fresh=select(rig,d)
    with pytest.raises(RagError):rig.rag.answer(p['ticket'],True)
    with pytest.raises(RagError):rig.rag.answer(fresh['ticket'],False)
    assert len(rig.provider.requests)==1 and old==original
    new=rig.rag.answer(fresh['ticket'],True)
    assert new['turn_id']!=old['turn_id'] and len(rig.provider.requests)==2


def test_expired_selection_and_revoked_history_never_reuse_previous_content(rig):
    rig.grant(['b']);d=rig.rag.draft('虚构问题？');p=select(rig,d)
    rig.rag.tickets[p['ticket']]['at']=time.monotonic()-181
    with pytest.raises(RagError) as error:rig.rag.answer(p['ticket'],True)
    assert error.value.code=='ticket_expired' and not rig.provider.requests
    rig.rag.drafts[d['draft_id']]['at']=time.monotonic()-181
    with pytest.raises(RagError) as error:select(rig,d)
    assert error.value.code=='draft_expired'
    d=rig.rag.draft('虚构问题？',d['session_id']);p=select(rig,d)
    rig.provider.reply={'status':'answered','answer':'虚构负责人。[S1]','citations':['S1']}
    rig.rag.answer(p['ticket'],True);rig.grant([])
    with pytest.raises(RagError) as error:rig.rag.draft('另一完整问题？',d['session_id'])
    assert error.value.code=='history_invalid'
    recovered=rig.rag.draft('另一完整问题？')
    assert recovered['history']==[] and not recovered['default_candidate_ids']
    assert all(not c['selectable'] for c in recovered['candidates'])
    assert len(rig.provider.requests)==1


@pytest.mark.parametrize('status,searchable',[('complete',True),('building',False),('failed',False),('stale',False),('disabled',False)])
def test_public_build_and_chunk_status_use_actual_index(client,monkeypatch,status,searchable):
    d=wait(client,upload(client)['id'])
    actual={'status':status,'searchable':searchable,'message':'实际索引状态：'+status}
    monkeypatch.setattr(main,'index_status',lambda identifier:actual)
    view=main.public(main.get(d['id']),True)
    assert view['build']['searchable']==searchable
    assert view['build']['message']==view['index']['message']
    assert view['build']['reason']=='index_'+status
    # Old persisted text is normalized on read, without overwriting the saved run.
    with main.LOCK:
        main.schedule_chunks(main.get(d['id']))
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        run=main.load_chunk_run(d['id'])
        if run and run['status']=='complete':break
        time.sleep(.01)
    assert run['status']=='complete'
    with main.connect() as conn:
        run['message']='旧版：尚未向量化或创建索引，当前不可检索。'
        main.write_chunk_run(conn,run)
    chunks=main.chunk_result(main.get(d['id']),index=actual)
    assert chunks['searchable']==searchable and '旧版' not in chunks['message']
    assert '旧版' in main.load_chunk_run(d['id'])['message']


def test_index_snapshot_does_not_reenter_index_status(client,monkeypatch):
    from app.semantic import IndexService
    d=wait(client,upload(client)['id'])
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        run=main.load_chunk_run(d['id'])
        if run and run['status']=='complete':break
        time.sleep(.01)
    assert run['status']=='complete'
    service=IndexService.__new__(IndexService)
    service.store=main;service.config={};service.config_hash='fixture'
    snap=service.snapshot(d['id'])
    service.read=lambda identifier:dict(status='complete',token=snap['token'],config_hash='fixture',message='索引已建立')
    service.current_config=lambda:True
    service.close=lambda:None
    monkeypatch.setattr(main,'INDEX_SERVICE',service)
    assert main.public(main.get(d['id']),True)['chunking']['searchable'] is True
    assert client.get('/api/documents/'+d['id']+'/chunks').json()['searchable'] is True
