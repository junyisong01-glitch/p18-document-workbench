"""Reader/writer gate that makes revocation and dispatch mutually exclusive.

Sends are readers: they may run concurrently with each other. Grant/revoke is
the writer. A writer waits for in-flight sends to finish and blocks new ones
from starting, so after a revocation call returns there is no send still using
the old grant.

This is deliberately coarse: the alternative (check, then send outside any
lock) leaves a window where a revoked document is still transmitted. Holding
the reader for the whole model call is acceptable because revocation is a rare,
human-driven action and the caller is told it may take up to one model timeout.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager

class EgressGate:
    def __init__(self):
        self._condition = threading.Condition()
        self._readers = 0
        self._writer = False
        self._writer_waiting = 0

    @contextmanager
    def sending(self):
        with self._condition:
            # Writer preference: a pending revocation must not be starved.
            while self._writer or self._writer_waiting:
                self._condition.wait()
            self._readers += 1
        try:
            yield
        finally:
            with self._condition:
                self._readers -= 1
                if not self._readers:
                    self._condition.notify_all()

    @contextmanager
    def changing(self):
        with self._condition:
            self._writer_waiting += 1
            while self._writer or self._readers:
                self._condition.wait()
            self._writer_waiting -= 1
            self._writer = True
        try:
            yield
        finally:
            with self._condition:
                self._writer = False
                self._condition.notify_all()

    def snapshot(self):
        with self._condition:
            return {'readers': self._readers, 'writer': self._writer,
                    'writer_waiting': self._writer_waiting}


# Adapted from the supplied P18 delivery app/egress_gate.py (2d5504d).
# Scope: one Python process, native external-permission routes only.
# Account/ACL/source mutations and external operator tools are not covered.
GATE = EgressGate()  # Eager module initialization: one gate even on concurrent first use.


def gate():
    return GATE
