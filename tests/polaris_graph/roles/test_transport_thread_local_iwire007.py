"""I-wire-007 (#1321) change #2: each claim worker uses its OWN thread-local OpenRouter client.

The I-arch-007 #1264 shared-cascade — one slow SHARED socket froze ALL roles — must NOT recur at the
higher concurrency the AIMD controller rides to. `OpenRouterRoleTransport` already makes the
`httpx.Client` THREAD-LOCAL (`self._tls = threading.local()`, lazy per-thread rebuild via the
factory). This test LOCKS that contract so a future refactor cannot silently reintroduce a shared
mutable client across the worker pool:

  (1) two distinct threads each get a DISTINCT client object (no sharing across the pool);
  (2) force-closing one thread's client (the total-deadline force-close) does NOT close another
      thread's client — the cascade-abort the #1264 fix prevents.

SPEND-FREE / NO NETWORK: the injected client AND the rebuild factory both use a MockTransport, so no
socket / no LLM / no spend in any pytest path.
"""

from __future__ import annotations

import threading

import httpx

from src.polaris_graph.roles.openrouter_role_transport import OpenRouterRoleTransport


def _mock_client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "VERIFIED"}}]})

    return httpx.Client(transport=httpx.MockTransport(handler))


def _make_transport() -> OpenRouterRoleTransport:
    return OpenRouterRoleTransport(_mock_client(), http_client_factory=_mock_client)


def test_each_thread_gets_a_distinct_client():
    """Two worker threads must resolve to TWO different client objects (no shared client in the pool)."""
    transport = _make_transport()
    clients: dict[str, object] = {}
    barrier = threading.Barrier(2)

    def _grab(tag: str):
        barrier.wait()  # ensure both threads are live before either resolves its client.
        clients[tag] = transport._http_client

    t1 = threading.Thread(target=_grab, args=("a",))
    t2 = threading.Thread(target=_grab, args=("b",))
    t1.start()
    t2.start()
    t1.join(timeout=5.0)
    t2.join(timeout=5.0)

    assert "a" in clients and "b" in clients, "both worker threads resolved a client"
    assert clients["a"] is not clients["b"], (
        "each worker thread must get its OWN thread-local client — a shared client across the pool is "
        "the I-arch-007 #1264 cascade the thread-local design prevents."
    )


def test_force_close_on_one_thread_does_not_close_another_threads_client():
    """The total-deadline force-close on worker A must NOT tear down worker B's in-flight client."""
    transport = _make_transport()
    a_client: list[httpx.Client] = []
    b_client: list[httpx.Client] = []
    a_ready = threading.Event()
    b_ready = threading.Event()
    proceed = threading.Event()

    def _worker_a():
        a_client.append(transport._http_client)
        a_ready.set()
        proceed.wait(timeout=5.0)
        a_client[0].close()  # the force-close (_post_with_total_deadline :479 client.close()).

    def _worker_b():
        b_client.append(transport._http_client)
        b_ready.set()
        proceed.wait(timeout=5.0)

    ta = threading.Thread(target=_worker_a)
    tb = threading.Thread(target=_worker_b)
    ta.start()
    tb.start()
    assert a_ready.wait(timeout=5.0) and b_ready.wait(timeout=5.0)
    proceed.set()
    ta.join(timeout=5.0)
    tb.join(timeout=5.0)

    assert a_client[0] is not b_client[0], "the two threads held distinct clients"
    assert a_client[0].is_closed is True, "worker A force-closed ITS client"
    assert b_client[0].is_closed is False, (
        "worker B's client must stay OPEN — a force-close on one worker can NEVER cascade to a "
        "sibling's in-flight client (the I-arch-007 #1264 fix this test locks)."
    )


def test_constructing_thread_uses_the_injected_client():
    """The constructing thread (tests + the single-threaded path) uses the INJECTED client verbatim."""
    injected = _mock_client()
    transport = OpenRouterRoleTransport(injected, http_client_factory=_mock_client)
    assert transport._http_client is injected, "the constructing thread reuses the injected client"
