"""I-arch-007 (#1264) — role-transport POST HARD total-deadline (preflight DEATH-lane residual).

The preflight flagged a residual thread-level trickle-hang: the 4-role/D8 role-transport POST
(``openrouter_role_transport.py`` ~:1056) was bounded ONLY by an httpx read-GAP that a trickled
keep-alive socket resets indefinitely, and the #1226 watchdog explicitly does NOT interrupt an
in-flight POST. This ports the proven HANG-J3 ``_post_with_total_deadline`` pattern
(entailment_judge.py:115-137): a HARD per-call wall that force-closes the hung client so the orphaned
worker thread unblocks, with a bounded rebuild-and-retry that fails CLOSED on exhaustion.

These are TRANSPORT-only assertions; no faithfulness gate is touched (exhaustion -> the UNCHANGED
fail-closed ``RoleTransportError`` the 4-role seam already consumes; never a fabricated verdict).
"""

from __future__ import annotations

import concurrent.futures
import threading
import time

import httpx
import pytest

from src.polaris_graph.roles.openrouter_role_transport import (
    OpenRouterRoleTransport,
    _default_role_http_client,
    _post_with_total_deadline,
    _role_transport_total_s,
)


class _BlockingClient:
    """A client whose POST blocks (simulating a trickle-hung socket) until close() is called."""

    def __init__(self) -> None:
        self.closed = False
        self.post_calls = 0
        self._unblock = threading.Event()

    def post(self, url, *, json=None, headers=None, timeout=None):
        self.post_calls += 1
        # Block as a trickle-hung read would; only close() (the force-close) releases it.
        self._unblock.wait(timeout=30)
        raise AssertionError("post should have been force-closed before returning")

    def close(self):
        self.closed = True
        self._unblock.set()


class _FastClient:
    def __init__(self, resp) -> None:
        self._resp = resp
        self.closed = False

    def post(self, url, *, json=None, headers=None, timeout=None):
        return self._resp

    def close(self):
        self.closed = True


def test_total_deadline_force_closes_a_trickle_hung_post():
    """A hung POST is FORCE-CLOSED at the deadline and TimeoutError raised — it can NOT hang."""
    client = _BlockingClient()
    started = time.monotonic()
    with pytest.raises(concurrent.futures.TimeoutError):
        _post_with_total_deadline(
            client, "https://openrouter/x", json_body={}, headers={}, timeout=900, total_s=0.5,
        )
    elapsed = time.monotonic() - started
    assert client.closed is True            # the hung socket was force-closed -> worker unblocks + exits
    assert elapsed < 5.0                    # returned promptly at the deadline; did NOT hang


def test_healthy_post_is_byte_identical_never_closed():
    """A HEALTHY (fast) POST returns its response unchanged and is NEVER force-closed."""
    sentinel = object()
    client = _FastClient(sentinel)
    out = _post_with_total_deadline(
        client, "https://openrouter/x", json_body={"a": 1}, headers={"h": "v"}, timeout=900, total_s=900,
    )
    assert out is sentinel
    assert client.closed is False           # healthy path is byte-identical: no force-close


def test_init_wires_a_rebuild_factory():
    """__init__ stores a rebuild factory so a trickle-hang degrades to a FRESH client, not a dead one."""
    transport = OpenRouterRoleTransport(_FastClient(object()))
    assert callable(transport._http_client_factory)
    built = _default_role_http_client()
    try:
        assert isinstance(built, httpx.Client)
    finally:
        built.close()


def test_positional_construction_still_works():
    """Every existing positional caller (run_gate_b.py:157, diagnostics) is byte-identical."""
    transport = OpenRouterRoleTransport(_FastClient(object()))
    assert transport._http_client is not None


def test_total_s_env_override_and_generous_default(monkeypatch):
    monkeypatch.setenv("PG_ROLE_TRANSPORT_TOTAL_S", "123")
    assert _role_transport_total_s() == 123.0
    monkeypatch.delenv("PG_ROLE_TRANSPORT_TOTAL_S", raising=False)
    assert _role_transport_total_s() == 900.0   # generous default — above any healthy 4-role call


def test_force_close_is_thread_isolated_no_sibling_cascade():
    """Codex P1: the 4-role seam shares ONE transport across concurrent claim workers, so a
    total-deadline force-close on one worker must NEVER close a sibling/main thread's client.

    The client is thread-local: the constructing thread uses the injected client; a NEW worker thread
    builds its OWN from the factory. Closing the worker's client must leave the main client untouched."""
    main_client = _FastClient(object())
    worker_clients = []

    def _factory():
        c = _FastClient(object())
        worker_clients.append(c)
        return c

    transport = OpenRouterRoleTransport(main_client, http_client_factory=_factory)
    assert transport._http_client is main_client  # constructing thread uses the INJECTED client

    seen = {}

    def _worker():
        c = transport._http_client            # a worker thread builds its OWN client
        seen["worker_client"] = c
        c.close()                             # simulate the force-close on THIS worker's client

    t = threading.Thread(target=_worker)
    t.start()
    t.join()

    assert seen["worker_client"] is not main_client          # the worker got its own client
    assert seen["worker_client"] in worker_clients           # built from the factory
    assert main_client.closed is False                       # sibling/main client NOT torn down (no cascade)
