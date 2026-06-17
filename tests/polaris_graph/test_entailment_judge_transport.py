"""I-arch-007 ITEM 2a — entailment-judge transport self-heal + thread-safety (faithfulness-NEUTRAL).

HERMETIC / OFFLINE: every test injects a stub `httpx.Client` (the same `judge._client = <stub>`
contract the I-bug-100 cost tests + the I-transport-001 retry tests use) or hits an in-process stub
HTTP server. NO real provider socket is opened and NO live LLM is called; the OpenRouter key is set to
a fixed test value so the family-segregation ctor check passes hermetically.

The load-bearing property is **verdict-INVARIANCE** (this file is the BINDING NLI gate's own code):
  - the SAME judge input -> the SAME `(verdict, reason)` before and after the redesign, across
    ENTAILED / NEUTRAL / CONTRADICTED / bad-verdict / empty-content; the fail-closed sentinel string
    `('ENTAILED', 'judge_error: ...')` is asserted byte-for-byte.
  - SELF-HEAL (MODE C / Q78): a closed/poisoned client on attempt 1 -> attempt 2 rebuilds + succeeds,
    so the Q78 over-drop disappears while a genuinely-unsupported claim still fails closed.
  - THREAD-SAFETY: N concurrent judge calls where one trips the force-close path -> no sibling sees a
    closed client and there is no `[X509]`/closed-client cascade.
  - PAYLOAD-vs-TRANSPORT asymmetry: a parse fault retries WITHOUT a client rebuild; a transport poison
    retries WITH a rebuild.

NON-GOAL: no faithfulness-gate relaxation. The verdict logic, the verdict-validation
(`verdict not in {ENTAILED,NEUTRAL,CONTRADICTED}`), and the terminal fail-closed
`('ENTAILED','judge_error: ...')` sentinel are byte-unchanged — only the transport recovers/fails-fast
instead of permanently bricking.
"""

from __future__ import annotations

import json
import threading

import httpx
import pytest

from src.polaris_graph.llm import entailment_judge, openrouter_client


# --------------------------------------------------------------------------------------------- env


@pytest.fixture(autouse=True)
def _hermetic_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-hermetic")
    monkeypatch.setenv("PG_GENERATOR_MODEL", "deepseek/deepseek-v4-pro")
    monkeypatch.setenv("PG_ENTAILMENT_MODEL", "google/gemma-4-31b-it")
    # No real backoff sleeps in the suite.
    monkeypatch.setenv("PG_ENTAILMENT_RETRY_BACKOFF_S", "0")
    monkeypatch.setenv("PG_ENTAILMENT_RETRIES", "2")
    for _k in ("OPENROUTER_BASE_URL", "PG_ENTAILMENT_TRANSPORT_POISON_MARKERS"):
        monkeypatch.delenv(_k, raising=False)
    yield


@pytest.fixture(autouse=True)
def _reset_run_cost():
    openrouter_client.reset_run_cost()
    yield
    openrouter_client.reset_run_cost()


@pytest.fixture(autouse=True)
def _reset_judge_singleton():
    entailment_judge._JUDGE_SINGLETON = None
    yield
    entailment_judge._JUDGE_SINGLETON = None


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    monkeypatch.setattr(entailment_judge.time, "sleep", lambda *_a, **_k: None)
    yield


# --------------------------------------------------------------------------------- stub transport


_JUDGE_REQUEST = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")


def _http_response(payload: dict) -> httpx.Response:
    return httpx.Response(200, json=payload, request=_JUDGE_REQUEST)


def _ok_payload(verdict: str = "ENTAILED", reason: str = "ok") -> dict:
    return {
        "choices": [{"message": {"content": json.dumps({"verdict": verdict, "reason": reason})}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.0001},
    }


class _StubClient:
    """A stub httpx client mimicking the real `is_closed` BOOL surface.

    - Returns/raises queued side effects per `.post()`.
    - `close()` flips `is_closed` to a real `True` (so the production `is_closed is True` heal path
      fires only on a genuinely closed client, never on a MagicMock child / attr-less fake).
    - Tracks how many times it was constructed-by-the-builder via the shared `build_log`.
    """

    def __init__(self, side_effects, *, build_log=None, client_id=0):
        self._side_effects = list(side_effects)
        self.n = 0
        self.is_closed = False
        self.client_id = client_id
        if build_log is not None:
            build_log.append(client_id)

    def post(self, *args, **kwargs):
        if self.is_closed:
            # Mimic httpx's real message so the production poison-matcher recognises it.
            raise RuntimeError("Cannot send a request, as the client has been closed.")
        i = self.n
        self.n += 1
        effect = self._side_effects[min(i, len(self._side_effects) - 1)]
        if isinstance(effect, Exception):
            raise effect
        return effect

    def close(self):
        self.is_closed = True


def _make_judge(monkeypatch, build_specs):
    """Build a real `_EntailmentJudge` whose per-thread client comes from a SEQUENCE of stub specs.

    `build_specs` is a list; the i-th `_build_client()` invocation pops `build_specs[i]` (a list of
    side effects for that client). This exercises the rebuild-on-poison path: attempt-1 client is
    spec[0]; after a rebuild, the thread's next read builds spec[1]. The build_log records every
    builder invocation (one entry per real client construction)."""
    judge = entailment_judge._EntailmentJudge.__new__(entailment_judge._EntailmentJudge)
    judge._model = "google/gemma-4-31b-it"
    judge._endpoint = "https://openrouter.ai/api/v1/chat/completions"
    judge._api_key = "test-key-hermetic"
    judge._tls = threading.local()
    build_log: list[int] = []
    state = {"i": 0}

    def _fake_build():
        i = state["i"]
        state["i"] += 1
        spec = build_specs[min(i, len(build_specs) - 1)]
        return _StubClient(spec, build_log=build_log, client_id=i)

    monkeypatch.setattr(judge, "_build_client", _fake_build)
    return judge, build_log


# =============================================================== verdict-INVARIANCE (the headline)


@pytest.mark.parametrize(
    "verdict_in",
    ["ENTAILED", "NEUTRAL", "CONTRADICTED"],
)
def test_verdict_invariance_valid_verdicts(monkeypatch, verdict_in):
    """The SAME judge input -> the SAME (verdict, reason) for every valid verdict. Transport
    redesign must not perturb the verdict logic at all."""
    judge, _ = _make_judge(monkeypatch, [[_http_response(_ok_payload(verdict_in, "because"))]])
    verdict, reason = judge.judge("a sentence", "a span")
    assert verdict == verdict_in
    assert reason == "because"


def test_verdict_invariance_bad_verdict_failclosed_sentinel(monkeypatch):
    """A garbled verdict that NEVER becomes valid -> retries exhaust -> the EXACT fail-closed
    sentinel. Byte-assert the contract: verdict=='ENTAILED', reason starts 'judge_error:'."""
    judge, _ = _make_judge(monkeypatch, [[_http_response(_ok_payload("MAYBE", "x"))]])
    verdict, reason = judge.judge("a sentence", "a span")
    assert verdict == "ENTAILED"
    assert reason.startswith("judge_error:")
    # The bad_verdict detail is preserved across retries into the terminal sentinel.
    assert "bad_verdict='MAYBE'" in reason


def test_verdict_invariance_empty_content_failclosed_sentinel(monkeypatch):
    """An empty {"choices": []} 200 on every attempt -> the EXACT fail-closed sentinel (a parse
    fault, NOT a transport poison)."""
    judge, _ = _make_judge(monkeypatch, [[_http_response({"choices": []})]])
    verdict, reason = judge.judge("a sentence", "a span")
    assert verdict == "ENTAILED"
    assert reason.startswith("judge_error:")


def test_failclosed_sentinel_is_byte_exact(monkeypatch):
    """The terminal sentinel string shape is part of the binding contract (both consumers key on
    the 'judge_error:' prefix + the ENTAILED verdict). Assert it verbatim."""
    judge, _ = _make_judge(
        monkeypatch, [[httpx.RemoteProtocolError("persistent mid-stream disconnect")]]
    )
    verdict, reason = judge.judge("a sentence", "a span")
    assert verdict == "ENTAILED"
    assert reason == "judge_error: RemoteProtocolError"


# ============================================================ SELF-HEAL (MODE C — the Q78 killer)


def test_self_heal_closed_client_on_attempt1_rebuilds_and_succeeds(monkeypatch):
    """A 'client has been closed' on attempt 1 -> the GENERIC branch rebuilds THIS thread's client
    before the retry -> attempt 2 (a fresh client) succeeds. The Q78 over-drop (a real ENTAILED
    spuriously dropped to the judge_error sentinel) disappears."""
    closed_err = RuntimeError("Cannot send a request, as the client has been closed.")
    judge, build_log = _make_judge(
        monkeypatch,
        [
            [closed_err],                         # client #0: poisoned -> raises closed
            [_http_response(_ok_payload("ENTAILED", "supported"))],  # client #1: healthy
        ],
    )
    verdict, reason = judge.judge("a sentence", "a span")
    assert verdict == "ENTAILED"
    assert not reason.startswith("judge_error:")
    # The builder ran twice: the original client + ONE rebuild on the poison path.
    assert build_log == [0, 1]


def test_self_heal_does_not_resurrect_genuinely_unsupported_claim(monkeypatch):
    """Self-heal recovers a CLOSED transport, NEVER a real verdict: a client that heals and then
    returns a NEUTRAL (genuinely-unsupported) verdict still yields NEUTRAL — the claim still drops
    downstream. Faithfulness is STRENGTHENED (fewer FALSE drops), never relaxed."""
    closed_err = RuntimeError("Cannot send a request, as the client has been closed.")
    judge, build_log = _make_judge(
        monkeypatch,
        [
            [closed_err],
            [_http_response(_ok_payload("NEUTRAL", "specificity inflation"))],
        ],
    )
    verdict, reason = judge.judge("a sentence", "a span")
    assert verdict == "NEUTRAL"   # NOT spuriously ENTAILED — the healed transport returns the real call
    assert reason == "specificity inflation"
    assert build_log == [0, 1]


def test_x509_poison_rebuilds_before_retry(monkeypatch):
    """An SSL/X509/PEM TLS-state fault is recognised as transport poison -> rebuild before retry."""
    import ssl

    x509_err = ssl.SSLError("[X509] PEM lib (_ssl.c:4166)")
    judge, build_log = _make_judge(
        monkeypatch,
        [
            [x509_err],
            [_http_response(_ok_payload("ENTAILED", "ok"))],
        ],
    )
    verdict, _ = judge.judge("a sentence", "a span")
    assert verdict == "ENTAILED"
    assert build_log == [0, 1]   # rebuilt once on the X509 poison


def test_parse_fault_retries_WITHOUT_rebuild(monkeypatch):
    """PAYLOAD-vs-TRANSPORT asymmetry: a malformed-JSON content (a parse fault) is RETRIED but does
    NOT rebuild the client — the original client is reused. This is the operational definition of
    'NOT a parse fault' in the self-heal predicate."""
    bad_json = {"choices": [{"message": {"content": "this is not json {{{"}}]}
    # All attempts return the same un-parseable content; no transport poison anywhere.
    judge, build_log = _make_judge(monkeypatch, [[_http_response(bad_json)]])
    verdict, reason = judge.judge("a sentence", "a span")
    assert verdict == "ENTAILED"
    assert reason.startswith("judge_error:")
    # Builder ran exactly ONCE (the original client). No rebuild on a pure parse fault.
    assert build_log == [0]


def test_predicate_payload_vs_transport_asymmetry():
    """Unit-level proof of the predicate: a closed/X509 fault is poison; a parse/bad-verdict fault
    is not."""
    import ssl

    assert entailment_judge._is_transport_poison(
        RuntimeError("Cannot send a request, as the client has been closed.")
    ) is True
    assert entailment_judge._is_transport_poison(ssl.SSLError("[X509] PEM lib")) is True
    # Payload faults -> NOT poison.
    assert entailment_judge._is_transport_poison(json.JSONDecodeError("x", "y", 0)) is False
    assert entailment_judge._is_transport_poison(KeyError("choices")) is False
    # Reason-string variant (the _RetryableJudgeError path loses the type).
    assert entailment_judge._is_transport_poison_reason("bad_verdict='MAYBE'") is False
    assert entailment_judge._is_transport_poison_reason(
        "client has been closed mid-call"
    ) is True


# ======================================================================== THREAD-SAFETY (no cascade)


def test_thread_local_client_each_worker_isolated(monkeypatch):
    """Each thread reads its OWN client from the thread-local store, so a sibling can never see
    another thread's client object. Hold a live reference to every worker's client (CPython recycles
    an object's id() once it is GC'd, so identity must be proven against retained objects, not raw
    ids of dead ones) and assert all six are distinct objects AND a single worker reads the SAME
    object twice (intra-thread stability)."""
    judge, _ = _make_judge(monkeypatch, [[_http_response(_ok_payload("ENTAILED", "ok"))]])
    clients: dict[int, object] = {}
    lock = threading.Lock()
    barrier = threading.Barrier(6)

    def _worker(idx):
        barrier.wait()  # keep all six threads (and their clients) alive simultaneously
        first = judge._client   # property read builds this thread's own client
        second = judge._client  # a second read returns the SAME thread-local client
        assert first is second
        barrier.wait()          # hold the references until every thread has built
        with lock:
            clients[idx] = first

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # Six retained, simultaneously-live client objects -> all DISTINCT (thread-local isolation).
    distinct = {id(c) for c in clients.values()}
    assert len(distinct) == len(clients) == 6


def test_concurrent_force_close_no_sibling_cascade(monkeypatch):
    """N concurrent judge calls; one worker trips the force-close path (its own client closes), and
    NO sibling thread ever observes a closed client / X509 cascade. Each worker's verdict is the
    correct ENTAILED — the force-close is isolated to the tripping thread."""
    # Per build: the FIRST client a thread builds raises 'closed' once (forcing a rebuild), the
    # rebuilt client succeeds. Each thread independently walks build #0 (closed) -> build #1 (ok),
    # but because the store is thread-local, no thread's close() touches another's client.
    closed_err = RuntimeError("Cannot send a request, as the client has been closed.")
    judge, _ = _make_judge(
        monkeypatch,
        [
            [closed_err],
            [_http_response(_ok_payload("ENTAILED", "ok"))],
        ],
    )

    results: dict[int, tuple[str, str]] = {}
    errors: list[BaseException] = []
    lock = threading.Lock()
    barrier = threading.Barrier(6)

    def _worker(idx):
        try:
            barrier.wait()  # maximise concurrency on the shared singleton judge
            v, r = judge.judge("a sentence", "a span")
            with lock:
                results[idx] = (v, r)
        except BaseException as exc:  # noqa: BLE001 — record any leaked failure for the assert
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"a sibling cascade leaked: {errors}"
    assert len(results) == 6
    for v, r in results.values():
        # Every worker self-healed its OWN closed client and returned the real verdict — no sibling
        # ever inherited a closed client (which would have produced the judge_error sentinel).
        assert v == "ENTAILED"
        assert not r.startswith("judge_error:")


def test_client_setter_and_getter_roundtrip_per_thread(monkeypatch):
    """The `judge._client = <stub>` test-injection contract is preserved: a write on a thread is
    read back on the SAME thread, and the defensive heal does NOT fire for an attr-less / MagicMock
    stub (the `is_closed is True` guard)."""
    from unittest.mock import MagicMock

    judge, _ = _make_judge(monkeypatch, [[_http_response(_ok_payload())]])
    # Inject a MagicMock (its .is_closed is a truthy CHILD mock, NOT `is True`).
    mock = MagicMock()
    judge._client = mock
    assert judge._client is mock  # getter returned the injected stub, no spurious rebuild

    # Inject an attr-less fake (getattr default False) — also no rebuild.
    class _NoIsClosed:
        pass

    fake = _NoIsClosed()
    judge._client = fake
    assert judge._client is fake
