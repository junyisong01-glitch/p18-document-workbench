"""Single-process native-permission concurrency. No network and synthetic fixtures only."""
from contextlib import contextmanager
from types import SimpleNamespace
import threading
import time
import pytest
from app import egress_gate, main, egress
from app.rag import RagError
from test_rag import rig
from test_external_permission import grant_rig


def wait_for(predicate):
    end=time.monotonic()+3
    while not predicate():
        assert time.monotonic()<end,'thread did not reach expected phase'
        time.sleep(.001)


def bind(r, monkeypatch):
    g=egress_gate.EgressGate();monkeypatch.setattr(egress_gate,'GATE',g)
    monkeypatch.setattr(main,'LOCK',r.store.LOCK);monkeypatch.setattr(main,'DATA',r.store.DATA)
    monkeypatch.setattr(main,'available',r.store.available)
    grant_rig(r);r.provider.reply={'status':'answered','answer':'虚构结论。[S1]','citations':['S1']}
    def revoke():
        d=r.docs['a'];return main.change_external_permission('a',SimpleNamespace(revision=d['revision'],fingerprint=egress.fingerprint(d),classification=None,checks={}),True)
    return g,revoke


def test_concurrent_first_use_same_gate():
    values=[];start=threading.Barrier(21)
    def worker():start.wait(3);values.append(egress_gate.gate())
    ts=[threading.Thread(target=worker)for _ in range(20)]
    for t in ts:t.start()
    start.wait(3)
    for t in ts:t.join(3);assert not t.is_alive()
    assert len({id(x)for x in values})==1


def test_writer_preference_and_concurrent_sends():
    g=egress_gate.EgressGate();release=threading.Event();entered=threading.Barrier(3);order=[]
    def send():
        with g.sending():entered.wait(3);assert release.wait(3)
    ts=[threading.Thread(target=send)for _ in range(2)]
    for t in ts:t.start()
    entered.wait(3);assert g.snapshot()['readers']==2
    def change():
        with g.changing():order.append('change')
    writer=threading.Thread(target=change);writer.start();wait_for(lambda:g.snapshot()['writer_waiting']==1)
    def later():
        with g.sending():order.append('later')
    late=threading.Thread(target=later);late.start();assert order==[]
    release.set()
    for t in [*ts,writer,late]:t.join(3);assert not t.is_alive()
    assert order==['change','later'] and g.snapshot()=={'readers':0,'writer':False,'writer_waiting':0}


@pytest.mark.parametrize('method',['sending','changing'])
def test_exception_releases_gate(method):
    g=egress_gate.EgressGate()
    with pytest.raises(ValueError):
        with getattr(g,method)():raise ValueError('fixture')
    assert g.snapshot()=={'readers':0,'writer':False,'writer_waiting':0}
    with g.changing():pass
    with g.sending():pass


def test_native_revoke_waits_for_inflight_answer(rig,monkeypatch):
    g,revoke=bind(rig,monkeypatch);p=rig.rag.prepare('虚构问题')
    started=threading.Event();release=threading.Event();errors=[];completed=threading.Event()
    def hook():started.set();assert release.wait(3)
    rig.provider.hook=hook
    def answer():
        try:rig.rag.answer(p['ticket'],True)
        except RagError as e:errors.append(e.code) # A completed revoke may also block publication.
    sender=threading.Thread(target=answer);sender.start();assert started.wait(3)
    def changing():revoke();completed.set()
    changer=threading.Thread(target=changing);changer.start();wait_for(lambda:g.snapshot()['writer_waiting']==1)
    assert not completed.is_set()
    # Other reads do not wait for the whole external call.
    with rig.store.LOCK:assert rig.store.available('a')['state']=='ready'
    release.set()
    for t in [sender,changer]:t.join(3);assert not t.is_alive()
    assert completed.is_set() and len(rig.provider.requests)==1 and set(errors)<={'evidence_stale'}
    assert not egress.allowed(rig.store.DATA,rig.docs['a'])


def test_revoke_in_pre_dispatch_gap_blocks_provider(rig,monkeypatch):
    g,revoke=bind(rig,monkeypatch);p=rig.rag.prepare('虚构问题')
    class GapGate:
        @contextmanager
        def sending(self):
            revoke() # Exactly after the old final check, before dispatch gate acquisition.
            with g.sending():yield
        def changing(self):return g.changing()
    monkeypatch.setattr(egress_gate,'gate',lambda:GapGate())
    with pytest.raises(RagError)as e:rig.rag.answer(p['ticket'],True)
    assert e.value.code=='evidence_stale' and not rig.provider.requests
    assert g.snapshot()['readers']==0


def test_provider_failure_does_not_block_future_revocation(rig,monkeypatch):
    g,revoke=bind(rig,monkeypatch);p=rig.rag.prepare('虚构问题')
    def fail():raise RuntimeError('synthetic transport failure')
    rig.provider.hook=fail
    with pytest.raises(RuntimeError):rig.rag.answer(p['ticket'],True)
    assert not revoke()['allowed'] and g.snapshot()['readers']==0
