"""I-deepfix-001 (KEYSTONE de-storm) — round-robin BURST-SPREAD of the per-claim judge START host.

Behavioral, hermetic (fake httpx clients, NO socket). Proves the transport-only de-storm fix:

  * (A) DISTRIBUTION — spread ON spreads the START host round-robin across the mirror chain (each
        host ~ inflight/len), instead of hammering host[0] with the whole 20-way credibility-pass
        burst (the account-QPS 429 storm that blew the pass wall -> credibility_analysis=None).
  * (A-neg) OFF byte-identity — PG_JUDGE_BURST_SPREAD=0 => every call STARTS on the chain LEAD +
        the ring walks lead->next (byte-identical to the pre-fix single-host pin).
  * (B) WRAPAROUND — a faulted call walks the FULL ring from wherever it started (modulo wrap),
        then STOPS after every distinct host is tried.
  * (C) FAIL-CLOSED, NEVER FAKE-PASS — an exhausted / all-faulted member returns the fail-closed
        sentinel (entailment: ('ENTAILED','judge_error:...') that consumers DROP; credibility: ""
        that upstream maps to an advisory judge_error). A timed-out member is NEVER stamped SUPPORTS.
        The parsed verdict is IDENTICAL spread ON vs OFF — the fix changes WHICH host answers, never
        the verdict.
  * (D) the SIBLING credibility_judge_caller repeats (A)-(C).

The distribution/wraparound assertions are DETERMINISTIC: the process-global round-robin counter is
reset to a known state via judge_burst_spread._reset_burst_start before each such test.
"""
import json
import threading
from collections import Counter

import httpx
import pytest

from src.polaris_graph.authority import credibility_judge_caller
from src.polaris_graph.llm import entailment_judge, openrouter_client
from src.polaris_graph.llm import judge_burst_spread as jbs

_CHAIN = ["h0", "h1", "h2", "h3"]  # a controlled 4-host mirror chain (monkeypatched in)


# ─────────────────────────── shared env + fakes ───────────────────────────


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    entailment_judge._JUDGE_SINGLETON = None
    openrouter_client.reset_run_cost()
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("PG_GENERATOR_MODEL", "deepseek/deepseek-v4-pro")  # glm != deepseek -> family ok
    monkeypatch.setenv("PG_ENTAILMENT_MODEL", "z-ai/glm-5.2")
    monkeypatch.setenv("PG_CREDIBILITY_JUDGE_MODEL", "z-ai/glm-5.2")
    monkeypatch.setenv("PG_OPENROUTER_PROVIDER_ROUTING", "1")
    monkeypatch.setenv("PG_JUDGE_PROVIDER_ROTATE", "1")  # rotation ON so the chain is derived
    monkeypatch.setenv("PG_ENTAILMENT_RETRY_BACKOFF_S", "0")
    monkeypatch.delenv("PG_ROLE_ALLOW_FALLBACKS", raising=False)
    monkeypatch.delenv("PG_JUDGE_UNHEALTHY_PROVIDERS", raising=False)
    # No-op the sleeps so the hermetic suite is fast (assertions never look at a sleep duration).
    monkeypatch.setattr(entailment_judge.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(credibility_judge_caller.time, "sleep", lambda *_a, **_k: None)
    # Controlled 4-host chain for BOTH judge modules (removes YAML coupling; assertions are exact).
    monkeypatch.setattr(entailment_judge, "_mirror_provider_chain", lambda: list(_CHAIN))
    monkeypatch.setattr(credibility_judge_caller, "_mirror_provider_chain", lambda: list(_CHAIN))
    yield
    entailment_judge._JUDGE_SINGLETON = None
    openrouter_client.reset_run_cost()


class _FakeResp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(f"HTTP {self.status_code}", request=None, response=None)

    def json(self):
        return self._payload


def _entailed_200():
    return _FakeResp(200, {
        "choices": [{"message": {"content": json.dumps({"verdict": "ENTAILED", "reason": "ok"})}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.0},
    })


def _verdict_200(verdict):
    return _FakeResp(200, {
        "choices": [{"message": {"content": json.dumps({"verdict": verdict, "reason": "r"})}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.0},
    })


def _blank_200():
    return _FakeResp(200, {"choices": [{"message": {"content": ""}}], "usage": {}})


class _RecordingJudgeClient:
    """Injected entailment client: records the provider ``order`` sent each POST; returns a scripted
    response per attempt (the LAST script entry repeats)."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.sent_orders = []
        self._i = 0

    def post(self, endpoint, headers=None, json=None):  # noqa: A002 — httpx kwarg name
        prov = (json or {}).get("provider") or {}
        self.sent_orders.append(list(prov.get("order") or []))
        resp = self._responses[min(self._i, len(self._responses) - 1)]
        self._i += 1
        return resp

    def close(self):
        pass


def _fresh_judge():
    return entailment_judge._EntailmentJudge()


# ═══════════════════════════ mode resolver (pure) ═══════════════════════════


def test_mode_default_is_spread(monkeypatch):
    monkeypatch.delenv("PG_JUDGE_BURST_SPREAD", raising=False)
    assert jbs.burst_spread_mode() == "spread"


@pytest.mark.parametrize("val", ["0", "false", "no", "off", "OFF", "False"])
def test_mode_off_variants(monkeypatch, val):
    monkeypatch.setenv("PG_JUDGE_BURST_SPREAD", val)
    assert jbs.burst_spread_mode() == "off"


def test_mode_lb(monkeypatch):
    monkeypatch.setenv("PG_JUDGE_BURST_SPREAD", "lb")
    assert jbs.burst_spread_mode() == "lb"


@pytest.mark.parametrize("val", ["1", "on", "spread", "true", "xyz"])
def test_mode_truthy_or_unknown_is_spread(monkeypatch, val):
    monkeypatch.setenv("PG_JUDGE_BURST_SPREAD", val)
    assert jbs.burst_spread_mode() == "spread"


# ═══════════════════════ (A) start-index distribution ═══════════════════════


def test_next_start_index_round_robin_single_thread():
    jbs._reset_burst_start(0)
    seq = [jbs.next_burst_start_index(4) for _ in range(20)]
    assert seq[:8] == [0, 1, 2, 3, 0, 1, 2, 3]  # strict round-robin from the reset
    assert Counter(seq) == {0: 5, 1: 5, 2: 5, 3: 5}  # each host is the START exactly 5/20


def test_next_start_index_thread_safe_balanced():
    # 40 concurrent draws must be DISTINCT consecutive integers (lock -> no lost increment), so their
    # residues mod 4 are perfectly balanced (10 each). A lost increment would collide -> imbalance.
    jbs._reset_burst_start(0)
    out = []
    lock = threading.Lock()
    barrier = threading.Barrier(40)

    def _draw():
        barrier.wait()
        v = jbs.next_burst_start_index(4)
        with lock:
            out.append(v)

    threads = [threading.Thread(target=_draw) for _ in range(40)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(out) == 40
    assert Counter(out) == {0: 10, 1: 10, 2: 10, 3: 10}


def test_next_start_index_singleton_chain_returns_zero():
    jbs._reset_burst_start(7)
    assert jbs.next_burst_start_index(1) == 0
    assert jbs.next_burst_start_index(0) == 0


def test_entailment_spread_on_distributes_start_hosts(monkeypatch):
    """POSITIVE (the KEYSTONE de-storm): with spread ON, 20 sequential judge() calls START on the 4
    chain hosts round-robin (each exactly 5) instead of all POSTing host[0] — no single-host storm."""
    monkeypatch.setenv("PG_JUDGE_BURST_SPREAD", "1")
    jbs._reset_burst_start(0)
    judge = _fresh_judge()
    client = _RecordingJudgeClient([_entailed_200()])  # every POST succeeds immediately (no rotation)
    judge._client = client
    for _ in range(20):
        verdict, _r = judge.judge("a sentence", "a span that entails it")
        assert verdict == "ENTAILED"
    starts = [tuple(o) for o in client.sent_orders]
    assert Counter(starts) == {("h0",): 5, ("h1",): 5, ("h2",): 5, ("h3",): 5}


def test_entailment_spread_off_all_start_lead(monkeypatch):
    """NEGATIVE CONTROL (byte-identical OFF): PG_JUDGE_BURST_SPREAD=0 => every call STARTS on the
    chain LEAD (h0), identical to the pre-fix single-host pin. The counter offset is irrelevant OFF."""
    monkeypatch.setenv("PG_JUDGE_BURST_SPREAD", "0")
    jbs._reset_burst_start(2)  # a non-zero offset must NOT leak into the OFF path
    judge = _fresh_judge()
    client = _RecordingJudgeClient([_entailed_200()])
    judge._client = client
    for _ in range(20):
        judge.judge("a sentence", "a span that entails it")
    assert all(o == ["h0"] for o in client.sent_orders), client.sent_orders


# ═══════════════════════ (B) wraparound / exhaustion ═══════════════════════


def test_entailment_spread_wraparound_walks_full_ring(monkeypatch):
    """POSITIVE: a member that STARTS mid-chain (index 2) and faults walks the FULL ring with
    wraparound (h2 -> h3 -> h0 -> h1) and recovers the REAL verdict from a healthy host."""
    monkeypatch.setenv("PG_JUDGE_BURST_SPREAD", "1")
    monkeypatch.setenv("PG_ENTAILMENT_RETRIES", "3")  # 3 rotations reach all 4 hosts
    jbs._reset_burst_start(2)  # force START host index 2
    judge = _fresh_judge()
    client = _RecordingJudgeClient([_blank_200(), _blank_200(), _blank_200(), _entailed_200()])
    judge._client = client
    verdict, _r = judge.judge("a sentence", "a span")
    assert verdict == "ENTAILED", verdict
    assert client.sent_orders == [["h2"], ["h3"], ["h0"], ["h1"]], client.sent_orders


def test_entailment_spread_exhaustion_stops_and_fails_closed(monkeypatch):
    """NEGATIVE CONTROL against fake-pass: an all-fault member walks every DISTINCT host once, the
    ring STOPS (no 5th distinct host), and the judge returns the FAIL-CLOSED sentinel — it is NEVER
    stamped a passing verdict. This is the hard faithfulness constraint."""
    monkeypatch.setenv("PG_JUDGE_BURST_SPREAD", "1")
    monkeypatch.setenv("PG_ENTAILMENT_RETRIES", "5")
    jbs._reset_burst_start(0)
    judge = _fresh_judge()
    client = _RecordingJudgeClient([_blank_200()])  # every attempt blanks
    judge._client = client
    verdict, reason = judge.judge("a sentence", "a span")
    # Fail-closed sentinel: ENTAILED + 'judge_error:' prefix -> both consumers DROP the claim.
    assert verdict == "ENTAILED", verdict
    assert reason.startswith("judge_error:"), reason
    distinct = {tuple(o) for o in client.sent_orders}
    assert distinct == {("h0",), ("h1",), ("h2",), ("h3",)}, client.sent_orders  # walked all 4
    # Ring stopped: no host outside the 4-host chain was ever tried.
    assert all(o[0] in _CHAIN for o in client.sent_orders), client.sent_orders


# ═══════════════════════ (C) verdict-invariance ON vs OFF ═══════════════════════


@pytest.mark.parametrize("verdict", ["ENTAILED", "NEUTRAL", "CONTRADICTED"])
def test_entailment_verdict_identical_spread_on_vs_off(monkeypatch, verdict):
    """The parsed verdict is IDENTICAL spread ON vs OFF for the same served body — the de-storm
    changes WHICH host answers, never the verdict (transport-only)."""
    def _run(mode):
        monkeypatch.setenv("PG_JUDGE_BURST_SPREAD", mode)
        jbs._reset_burst_start(1)
        judge = _fresh_judge()
        judge._client = _RecordingJudgeClient([_verdict_200(verdict)])
        return judge.judge("s", "span")

    assert _run("1") == _run("0")


# ═══════════════════════ (A/B) entailment 'lb' mode ═══════════════════════


def test_entailment_lb_mode_drops_order_and_load_balances(monkeypatch):
    """'lb' (documented D8 cure): drop the single-host `order`, send allow_fallbacks=True +
    require_parameters=True so OpenRouter load-balances the burst. Rotation is a no-op (no order)."""
    monkeypatch.setenv("PG_JUDGE_BURST_SPREAD", "lb")
    judge = _fresh_judge()
    client = _RecordingJudgeClient([_blank_200(), _entailed_200()])
    judge._client = client
    seen = {}
    _orig_post = client.post

    def _spy(endpoint, headers=None, json=None):  # noqa: A002
        seen["provider"] = dict((json or {}).get("provider") or {})
        return _orig_post(endpoint, headers=headers, json=json)

    client.post = _spy
    judge.judge("s", "span")
    assert "order" not in seen["provider"], seen["provider"]
    assert seen["provider"].get("allow_fallbacks") is True
    assert seen["provider"].get("require_parameters") is True
    # No `order` was ever pinned across attempts (rotation no-op under lb).
    assert all(o == [] for o in client.sent_orders), client.sent_orders


# ═══════════════════════ (D) credibility_judge_caller sibling ═══════════════════════


def _cred_recording_client(posts, script):
    """httpx.Client factory: records each POST's provider ``order`` into ``posts`` and returns/raises
    per ``script`` (list of ("ok", body) | ("blank", body) | ("raise",); last entry repeats)."""

    class _Resp:
        def __init__(self, body):
            self._b = body

        def raise_for_status(self):
            return None

        def json(self):
            return self._b

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def close(self):
            pass

        def post(self, url, headers=None, json=None):  # noqa: A002
            prov = (json or {}).get("provider") or {}
            posts.append(list(prov.get("order") or []))
            step = script[min(len(posts) - 1, len(script) - 1)]
            if step[0] == "raise":
                raise RuntimeError("transport fault")
            return _Resp(step[1])

    return _Client


def _cred_ok_body():
    return {"choices": [{"message": {"content": '{"reliability_score": 0.7}'},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 8, "completion_tokens": 4, "cost": 0.001}}


def _cred_blank_body():
    return {"choices": [{"message": {"content": ""}, "finish_reason": "stop"}], "usage": {}}


def test_credibility_spread_on_distributes_start_hosts(monkeypatch):
    monkeypatch.setenv("PG_JUDGE_BURST_SPREAD", "1")
    jbs._reset_burst_start(0)
    posts = []
    monkeypatch.setattr(httpx, "Client", _cred_recording_client(posts, [("ok", _cred_ok_body())]))
    caller = credibility_judge_caller.make_openrouter_credibility_caller()
    for _ in range(20):
        assert caller("hi") == '{"reliability_score": 0.7}'
    starts = [tuple(o) for o in posts]
    assert Counter(starts) == {("h0",): 5, ("h1",): 5, ("h2",): 5, ("h3",): 5}


def test_credibility_spread_off_all_start_lead(monkeypatch):
    monkeypatch.setenv("PG_JUDGE_BURST_SPREAD", "0")
    jbs._reset_burst_start(3)  # offset must not leak into the OFF path
    posts = []
    monkeypatch.setattr(httpx, "Client", _cred_recording_client(posts, [("ok", _cred_ok_body())]))
    caller = credibility_judge_caller.make_openrouter_credibility_caller()
    for _ in range(20):
        caller("hi")
    assert all(o == ["h0"] for o in posts), posts


def test_credibility_spread_wraparound_walks_full_ring(monkeypatch):
    monkeypatch.setenv("PG_JUDGE_BURST_SPREAD", "1")
    monkeypatch.setenv("PG_CREDIBILITY_JUDGE_RETRIES", "3")
    jbs._reset_burst_start(1)  # force START host index 1
    posts = []
    script = [("raise",), ("raise",), ("raise",), ("ok", _cred_ok_body())]
    monkeypatch.setattr(httpx, "Client", _cred_recording_client(posts, script))
    caller = credibility_judge_caller.make_openrouter_credibility_caller()
    assert caller("hi") == '{"reliability_score": 0.7}'
    assert posts == [["h1"], ["h2"], ["h3"], ["h0"]], posts


def test_credibility_exhaustion_degrades_advisory_never_fabricates(monkeypatch):
    """NEVER-FABRICATE: an all-blank member exhausts and returns EMPTY content (upstream maps it to
    an advisory judge_error) — it is NEVER stamped a reliability score. The credibility analog of the
    entailment fail-closed sentinel."""
    monkeypatch.setenv("PG_JUDGE_BURST_SPREAD", "1")
    monkeypatch.setenv("PG_CREDIBILITY_JUDGE_RETRIES", "3")
    jbs._reset_burst_start(0)
    posts = []
    monkeypatch.setattr(httpx, "Client", _cred_recording_client(posts, [("blank", _cred_blank_body())]))
    caller = credibility_judge_caller.make_openrouter_credibility_caller()
    result = caller("hi")
    assert (result or "").strip() == "", result  # empty -> advisory, not a fabricated score
    distinct = {tuple(o) for o in posts}
    assert distinct == {("h0",), ("h1",), ("h2",), ("h3",)}, posts  # walked all 4 then stopped


def test_credibility_body_identical_spread_on_vs_off(monkeypatch):
    """The returned body is IDENTICAL spread ON vs OFF for the same served response (transport-only)."""
    def _run(mode):
        monkeypatch.setenv("PG_JUDGE_BURST_SPREAD", mode)
        jbs._reset_burst_start(2)
        posts = []
        monkeypatch.setattr(httpx, "Client", _cred_recording_client(posts, [("ok", _cred_ok_body())]))
        return credibility_judge_caller.make_openrouter_credibility_caller()("hi")

    assert _run("1") == _run("0") == '{"reliability_score": 0.7}'
