"""Egress gate: sends (readers) and grant/revoke (writer) are exclusive."""
import threading
import time

from app.egress_gate import EgressGate


def test_writer_waits_for_inflight_send():
    gate = EgressGate()
    started, released, change_done = threading.Event(), threading.Event(), threading.Event()

    def send():
        with gate.sending():
            started.set()
            released.wait(2)

    def revoke():
        with gate.changing():
            change_done.set()

    sender = threading.Thread(target=send)
    sender.start()
    assert started.wait(2)
    changer = threading.Thread(target=revoke)
    changer.start()
    time.sleep(0.1)
    assert not change_done.is_set(), '撤销不得在发送结束前完成'
    released.set()
    sender.join(2)
    changer.join(2)
    assert change_done.is_set()


def test_pending_writer_blocks_new_sends():
    gate = EgressGate()
    holder_started, holder_release = threading.Event(), threading.Event()
    writer_started = threading.Event()
    send_entered = threading.Event()

    def holder():
        with gate.sending():
            holder_started.set()
            holder_release.wait(2)

    def writer():
        with gate.changing():
            writer_started.set()

    def late_send():
        with gate.sending():
            send_entered.set()

    first = threading.Thread(target=holder)
    first.start()
    assert holder_started.wait(2)
    changer = threading.Thread(target=writer)
    changer.start()
    time.sleep(0.1)
    late = threading.Thread(target=late_send)
    late.start()
    time.sleep(0.1)
    assert not send_entered.is_set(), '有撤销在等时，新的发送必须排队'
    holder_release.set()
    first.join(2)
    changer.join(2)
    late.join(2)
    assert writer_started.is_set() and send_entered.is_set()


def test_sends_run_concurrently_and_snapshot_reports_state():
    gate = EgressGate()
    barrier = threading.Barrier(3)

    def send():
        with gate.sending():
            barrier.wait(2)

    threads = [threading.Thread(target=send) for _ in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait(2)
    assert gate.snapshot()['readers'] == 2
    for thread in threads:
        thread.join(2)
    assert gate.snapshot() == {'readers': 0, 'writer': False, 'writer_waiting': 0}
