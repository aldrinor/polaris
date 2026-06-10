"""I-transport-001 (#1191) — bounded-retry transport resilience (faithfulness-safe).

HERMETIC / OFFLINE: every test monkeypatches the httpx client (generation + NLI judge) or injects an
``httpx.MockTransport`` (4-role seam). NO socket is opened, NO live LLM is called, and NO ambient
``OPENROUTER_*`` / ``FIRECRAWL_*`` / ``SEMANTIC_SCHOLAR_*`` / ``SERPER_*`` keys leak into a probe — the
relevant env is set to a fixed test value or deleted per test.

Covers, for the three LLM transport seams (generation, 4-role verifier seam, NLI entailment judge):
  (a) ONE transient ``httpx.RemoteProtocolError`` (mid-stream incomplete-chunked-read) then success
      -> the verdict/response is returned (the fault was retried, not propagated).
  (b) ONE structurally-empty ``{"choices": []}`` HTTP 200 then success -> the verdict is returned.
  (c) ALL attempts fault -> the TERMINAL stays fail-CLOSED:
        - generation: re-raises after ``MAX_RETRIES`` (the caller maps this to ``status=error``);
        - seam: ``BlankVerdictError`` propagates (release HELD) after the effort ladder exhausts;
        - judge: returns the EXACT ``("ENTAILED", "judge_error: ...")`` sentinel, which the
          consumer (``strict_verify`` enforce mode) DROPS — fail-closed, not fail-open.

NON-GOAL: no faithfulness-gate relaxation, no NEUTRAL-sentinel flip. The judge sentinel staying
``ENTAILED`` + ``judge_error:`` prefix is the load-bearing contract both consumers fail-closed on.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from datetime import datetime, timezone

from src.polaris_graph.clinical_retrieval.evidence_pool import (
    AdequacyVerdict,
    EvidencePool,
    Source,
    SourceTier,
)
from src.polaris_graph.llm import entailment_judge, openrouter_client
from src.polaris_graph.roles import openrouter_role_transport as ort
from src.polaris_graph.roles.openrouter_role_transport import (
    BlankVerdictError,
    OpenRouterRoleTransport,
)
from src.polaris_graph.roles.role_transport import RoleRequest

# --------------------------------------------------------------------------------------------- env


@pytest.fixture(autouse=True)
def _hermetic_env(monkeypatch):
    """Fix the OpenRouter key to a test value and DELETE every ambient backend key so no probe can
    reach a live endpoint even if a stub is missed. Keep retries fast (no real sleep)."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-hermetic")
    monkeypatch.setenv("PG_GENERATOR_MODEL", "deepseek/deepseek-v4-pro")
    monkeypatch.setenv("PG_ENTAILMENT_MODEL", "google/gemma-4-31b-it")
    # Zero backoffs so the bounded retries do not actually sleep in the suite.
    monkeypatch.setenv("PG_ENTAILMENT_RETRY_BACKOFF_S", "0")
    for _k in (
        "OPENROUTER_BASE_URL",
        "FIRECRAWL_API_KEY",
        "SEMANTIC_SCHOLAR_API_KEY",
        "SERPER_API_KEY",
        "PG_PROVIDER_BLANK_RETRIES",
    ):
        monkeypatch.delenv(_k, raising=False)
    yield


@pytest.fixture(autouse=True)
def _reset_run_cost():
    openrouter_client.reset_run_cost()
    yield
    openrouter_client.reset_run_cost()


# ===================================================================== SEAM 1 — GENERATION (_call_impl)


_GEN_REQUEST = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")


def _empty_choices_response() -> httpx.Response:
    """A structurally-empty HTTP 200 ({"choices": []}, no error key) — the drb_72-class empty 200."""
    return httpx.Response(
        200, json={"choices": [], "model": "deepseek/deepseek-v4-pro"}, request=_GEN_REQUEST,
    )


def _ok_generation_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": "the answer"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.0001},
            "model": "deepseek/deepseek-v4-pro",
        },
        request=_GEN_REQUEST,
    )


def _make_generation_client(monkeypatch, post_side_effects):
    """Build an OpenRouterClient whose ``_client.post`` returns/raises the queued side effects in
    order. ``response_format=json_object`` + ``reasoning_enabled=False`` forces the NON-STREAM path,
    which posts via ``self._client.post`` (a single mockable coroutine)."""
    client = openrouter_client.OpenRouterClient(api_key="test-key-hermetic")
    calls = {"n": 0}

    async def _fake_post(*args, **kwargs):
        i = calls["n"]
        calls["n"] += 1
        effect = post_side_effects[min(i, len(post_side_effects) - 1)]
        if isinstance(effect, Exception):
            raise effect
        return effect

    monkeypatch.setattr(client._client, "post", _fake_post)
    # No real backoff sleeps.
    monkeypatch.setattr(openrouter_client.asyncio, "sleep", _noop_async_sleep)
    return client, calls


async def _noop_async_sleep(*_a, **_k):
    return None


def _run_generation(client):
    return asyncio.run(
        client._call_impl(
            messages=[{"role": "user", "content": "q"}],
            call_type="section",
            reasoning_enabled=False,
            response_format={"type": "json_object"},
        )
    )


def test_generation_remote_protocol_error_then_success(monkeypatch):
    """(a) ONE mid-stream httpx.RemoteProtocolError then a valid 200 -> the response is returned
    (Site 1: RemoteProtocolError is now in the retry tuple at openrouter_client.py:1975)."""
    client, calls = _make_generation_client(
        monkeypatch,
        [httpx.RemoteProtocolError("peer closed connection mid-stream"), _ok_generation_response()],
    )
    resp = _run_generation(client)
    assert resp.content == "the answer"
    assert calls["n"] == 2  # one failed attempt + one success


def test_generation_empty_choices_then_success(monkeypatch):
    """(b) ONE empty {"choices": []} 200 then a valid 200 -> the response is returned
    (Site 2: empty-choices now raises a RETRYABLE RuntimeError INSIDE the loop)."""
    client, calls = _make_generation_client(
        monkeypatch,
        [_empty_choices_response(), _ok_generation_response()],
    )
    resp = _run_generation(client)
    assert resp.content == "the answer"
    assert calls["n"] == 2


def test_generation_all_remote_protocol_error_fails_closed(monkeypatch):
    """(c) EVERY attempt raises RemoteProtocolError -> after MAX_RETRIES the error re-raises
    (the caller maps an exception to status=error — fail-closed). Asserts MAX_RETRIES+1 attempts."""
    client, calls = _make_generation_client(
        monkeypatch,
        [httpx.RemoteProtocolError("persistent mid-stream disconnect")],
    )
    with pytest.raises(httpx.RemoteProtocolError):
        _run_generation(client)
    assert calls["n"] == openrouter_client.MAX_RETRIES + 1


def test_generation_all_empty_choices_fails_closed(monkeypatch):
    """(c) EVERY attempt returns an empty 200 -> the retryable RuntimeError re-raises after
    MAX_RETRIES (status=error). No empty completion is ever consumed as content."""
    client, calls = _make_generation_client(monkeypatch, [_empty_choices_response()])
    with pytest.raises(RuntimeError):
        _run_generation(client)
    assert calls["n"] == openrouter_client.MAX_RETRIES + 1


# ===================================================================== SEAM 2 — 4-ROLE VERIFIER SEAM


def _judge_request() -> RoleRequest:
    """A JUDGE role request — the Judge is an effort-reasoning role, so complete() uses the effort
    ladder (multi-attempt) which is exactly the provider-exclusion/step-down failover Site 3 reuses."""
    return RoleRequest(role="judge", model_slug="qwen/qwen3.6-35b-a3b", prompt="decide", params={})


def _seam_transport(handler) -> OpenRouterRoleTransport:
    return OpenRouterRoleTransport(httpx.Client(transport=httpx.MockTransport(handler)))


def _seam_ok_payload() -> dict:
    return {
        "model": "qwen/qwen3.6-35b-a3b",
        "provider": "DeepInfra",
        "choices": [{"message": {"role": "assistant", "content": "VERIFIED"}}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 5},
    }


def _seam_empty_payload() -> dict:
    # The drb_75 shape: a structurally-empty HTTP 200, model=None, choices=[].
    return {"model": None, "provider": "DeepInfra", "choices": []}


@pytest.fixture(autouse=True)
def _pin_effort_ladder(monkeypatch):
    """Pin the effort ladder to a deterministic 3-entry tuple so the seam attempt count is stable
    regardless of ambient PG_FOUR_ROLE_EFFORT_LADDER (the module value is read at import)."""
    monkeypatch.setattr(ort, "_VERIFIER_EFFORT_LADDER", ("xhigh", "low", None))
    yield


def test_seam_remote_protocol_error_then_success(monkeypatch):
    """(a) The seam already retries transport faults via PG_ROLE_TRANSPORT_RETRIES (:828-849); this
    is a REGRESSION GUARD that a transient RemoteProtocolError on the POST is retried, not a new
    Site-3 behavior. ONE RemoteProtocolError then a valid 200 -> the verdict is returned."""
    monkeypatch.setenv("PG_ROLE_TRANSPORT_RETRIES", "2")
    state = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["n"] += 1
        if state["n"] == 1:
            raise httpx.RemoteProtocolError("peer closed mid-stream")
        return httpx.Response(200, json=_seam_ok_payload())

    resp = _seam_transport(handler).complete(_judge_request())
    assert resp.raw_text == "VERIFIED"
    assert state["n"] == 2


def test_seam_empty_choices_then_success(monkeypatch):
    """(b) Site 3 (FIXES drb_75): ONE structurally-empty {"choices": []} 200 then a valid 200 ->
    the empty 200 now raises a RECOVERABLE BlankVerdictError routed into the effort-ladder +
    provider-exclusion failover, which advances to the next attempt and returns the verdict.

    Also asserts the drb_75 MECHANISM: the blanking provider ("DeepInfra" -> slug "deepinfra") is
    added to body['provider']['ignore'] BEFORE the retry, so OpenRouter advances to the next healthy
    provider (it does NOT auto-advance off an empty 200)."""
    state = {"n": 0, "bodies": []}

    def handler(request: httpx.Request) -> httpx.Response:
        state["n"] += 1
        state["bodies"].append(json.loads(request.content.decode("utf-8")))
        if state["n"] == 1:
            return httpx.Response(200, json=_seam_empty_payload())
        return httpx.Response(200, json=_seam_ok_payload())

    resp = _seam_transport(handler).complete(_judge_request())
    assert resp.raw_text == "VERIFIED"
    assert state["n"] == 2  # the empty 200 was retried (not HELD immediately)
    # The blanking provider was excluded on the RETRY request (provider-exclusion failover, :960-964).
    retry_provider_block = state["bodies"][1].get("provider", {})
    assert "deepinfra" in retry_provider_block.get("ignore", [])


def test_seam_all_empty_choices_held_after_ladder(monkeypatch):
    """(c) EVERY attempt returns an empty 200 -> BlankVerdictError propagates (release HELD) only
    AFTER the full effort ladder exhausts. No fake verdict is ever synthesized."""
    state = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["n"] += 1
        return httpx.Response(200, json=_seam_empty_payload())

    with pytest.raises(BlankVerdictError):
        _seam_transport(handler).complete(_judge_request())
    # One attempt per ladder entry (the pinned 3-entry ladder) — HELD only on exhaustion.
    assert state["n"] == len(ort._VERIFIER_EFFORT_LADDER)


# ===================================================================== SEAM 3 — NLI ENTAILMENT JUDGE


@pytest.fixture(autouse=True)
def _reset_judge_singleton():
    entailment_judge._JUDGE_SINGLETON = None
    yield
    entailment_judge._JUDGE_SINGLETON = None


class _FakeJudgeClient:
    """A stub httpx.Client for the NLI judge: returns/raises queued side effects per .post()."""

    def __init__(self, side_effects):
        self._side_effects = side_effects
        self.n = 0

    def post(self, *args, **kwargs):
        i = self.n
        self.n += 1
        effect = self._side_effects[min(i, len(self._side_effects) - 1)]
        if isinstance(effect, Exception):
            raise effect
        return effect


def _single_span_pool(full_text: str) -> EvidencePool:
    """A minimal one-source EvidencePool (pattern from test_strict_verify_entailment.py) whose
    full_text is the cited span, so a `[#ev:src-1:0-<len>]` token validates and checks (a)-(e) pass,
    letting verify_sentence reach the entailment judge."""
    src = Source(
        url="https://www.urncst.org/article",
        domain="urncst.org",
        tier=SourceTier.T1,
        title="Source",
        snippet="snippet text",
        full_text=full_text,
        full_text_available=True,
        source_id="src-1",
    )
    return EvidencePool(
        decision_id="dec-transport-001",
        sources=[src],
        adequacy=AdequacyVerdict(
            is_adequate=True,
            sources_per_tier={SourceTier.T1: 0, SourceTier.T2: 0, SourceTier.T3: 0},
            min_required_per_tier={SourceTier.T1: 0, SourceTier.T2: 0, SourceTier.T3: 0},
        ),
        retrieval_started_at_utc=datetime.now(timezone.utc),
        retrieval_finished_at_utc=datetime.now(timezone.utc),
        latency_ms=0,
        cost_usd=0.0,
    )


_JUDGE_REQUEST = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")


def _judge_http_response(payload: dict) -> httpx.Response:
    return httpx.Response(200, json=payload, request=_JUDGE_REQUEST)


def _judge_ok_payload(verdict: str = "ENTAILED") -> dict:
    return {
        "choices": [{"message": {"content": json.dumps({"verdict": verdict, "reason": "ok"})}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.0001},
    }


def _make_judge(monkeypatch, side_effects) -> entailment_judge._EntailmentJudge:
    monkeypatch.setattr(entailment_judge.time, "sleep", lambda *_a, **_k: None)
    judge = entailment_judge._EntailmentJudge()
    judge._client = _FakeJudgeClient(side_effects)
    return judge


def test_judge_remote_protocol_error_then_success(monkeypatch):
    """(a) Site 4: ONE httpx.RemoteProtocolError on the judge POST then a valid 200 -> the real
    verdict is returned (the transient fault was retried, NOT collapsed to the judge_error sentinel)."""
    monkeypatch.setenv("PG_ENTAILMENT_RETRIES", "2")
    judge = _make_judge(
        monkeypatch,
        [httpx.RemoteProtocolError("mid-stream disconnect"), _judge_http_response(_judge_ok_payload())],
    )
    verdict, reason = judge.judge("a sentence", "a span")
    assert verdict == "ENTAILED"
    assert not reason.startswith("judge_error:")
    assert judge._client.n == 2


def test_judge_empty_choices_then_success(monkeypatch):
    """(b) Site 4: ONE empty {"choices": []} 200 then a valid 200 -> the verdict is returned
    (the empty 200 raises inside the loop and is retried)."""
    monkeypatch.setenv("PG_ENTAILMENT_RETRIES", "2")
    judge = _make_judge(
        monkeypatch,
        [_judge_http_response({"choices": []}), _judge_http_response(_judge_ok_payload())],
    )
    verdict, reason = judge.judge("a sentence", "a span")
    assert verdict == "ENTAILED"
    assert not reason.startswith("judge_error:")
    assert judge._client.n == 2


def test_judge_all_fault_returns_failclosed_sentinel_consumer_drops(monkeypatch):
    """(c) Site 4: EVERY attempt raises -> the EXACT ('ENTAILED', 'judge_error: ...') sentinel is
    returned after PG_ENTAILMENT_RETRIES, and the consumer (strict_verify enforce) DROPS it.

    This is the load-bearing faithfulness property: the sentinel stays ENTAILED+prefix so BOTH
    consumers fail CLOSED (NOT a NEUTRAL flip, which would bypass provenance detection)."""
    monkeypatch.setenv("PG_ENTAILMENT_RETRIES", "2")
    judge = _make_judge(monkeypatch, [httpx.RemoteProtocolError("persistent disconnect")])
    verdict, reason = judge.judge("a sentence", "a span")

    # The sentinel contract: ENTAILED verdict + judge_error: prefix (do NOT flip to NEUTRAL).
    assert verdict == "ENTAILED"
    assert reason.startswith("judge_error:")
    # PG_ENTAILMENT_RETRIES=2 => 3 total attempts before the sentinel.
    assert judge._client.n == 3

    # The consumer fails CLOSED on this sentinel. Drive the REAL strict_verify enforce-mode path
    # end-to-end through verify_sentence (the only place that calls _get_judge().judge): a sentence
    # whose mechanical checks (a)-(e) PASS but the entailment judge returns the judge_error sentinel
    # must be DROPPED (returns not-verified, reason=entailment_judge_error_fail_closed). This proves
    # the retry-then-exhaust path remains fail-CLOSED, not fail-open.
    from src.polaris_graph.clinical_generator import strict_verify as sv

    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    monkeypatch.setattr(sv, "_get_judge", lambda: judge)
    judge._client = _FakeJudgeClient([httpx.RemoteProtocolError("persistent disconnect")])

    full_text = "metformin reduced HbA1c in adults with type 2 diabetes mellitus"
    pool = _single_span_pool(full_text)
    # The sentence shares >=2 content words with the span and carries a valid provenance token, so
    # checks (a)-(e) pass and control reaches the entailment judge (which returns the sentinel).
    sentence = (
        f"metformin reduced HbA1c in type 2 diabetes [#ev:src-1:0-{len(full_text)}]."
    )
    ok, detail = sv.verify_sentence(sentence, pool)
    assert ok is False
    assert detail == "entailment_judge_error_fail_closed"


def test_judge_budget_exceeded_propagates_not_retried(monkeypatch):
    """Site 4 invariant: BudgetExceededError must propagate IMMEDIATELY (first/outside the retry) —
    a cap breach is never masked as a transient judge error nor retried."""
    monkeypatch.setenv("PG_ENTAILMENT_RETRIES", "2")
    monkeypatch.setattr(openrouter_client, "PG_MAX_COST_PER_RUN", 0.0001)
    # A valid 200 whose cost (0.001) breaches the 0.0001 cap on the FIRST attempt.
    payload = {
        "choices": [{"message": {"content": json.dumps({"verdict": "ENTAILED", "reason": "ok"})}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "cost": 0.001},
    }
    judge = _make_judge(monkeypatch, [_judge_http_response(payload)])
    # NOTE: the cap breach must abort on the FIRST POST, before any retry.
    with pytest.raises(openrouter_client.BudgetExceededError):
        judge.judge("a sentence", "a span")
    # Exactly ONE POST — the breach aborts before any retry.
    assert judge._client.n == 1


# ============================================================ SITE 5 — DISCOVERY BREADTH PROBE (drb_78)


def test_breadth_probe_transient_s2_500_then_recovers(monkeypatch):
    """(b for Site 5; FIXES drb_78): a transient S2 HTTP-500 (which _s2_bulk_search SWALLOWS to an
    empty list) yields 0 S2 URLs on attempt 1 -> union below the 100 floor -> the bounded retry
    re-issues BOTH backends; on attempt 2 S2 recovers and the union crosses the floor. Proves the
    PG_BREADTH_PROBE_RETRIES path (the production discovery functions are faked — NO network)."""
    import src.polaris_graph.retrieval.live_retriever as lr
    import scripts.dr_benchmark.super_heavy_preflight as m

    monkeypatch.setenv("PG_BREADTH_PROBE_RETRIES", "2")
    monkeypatch.setenv("PG_BREADTH_PROBE_RETRY_BACKOFF_S", "0")
    monkeypatch.setenv("PG_SWEEP_MAX_SERPER", "100")
    monkeypatch.setenv("PG_SWEEP_MAX_S2", "100")

    s2_calls = {"n": 0}

    def _fake_serper(query, num=10, api_calls=None):
        return [{"url": f"https://serper/{i}"} for i in range(60)]

    def _fake_s2(query, limit=20):
        s2_calls["n"] += 1
        if s2_calls["n"] == 1:
            return []  # transient S2 HTTP-500 -> swallowed to [] (live_retriever.py:410-421)
        return [{"url": f"https://s2/{i}"} for i in range(90)]

    monkeypatch.setattr(lr, "_serper_search", _fake_serper)
    monkeypatch.setattr(lr, "_s2_bulk_search", _fake_s2)

    n = m._default_breadth_probe()
    # Attempt 1: 60 serper + 0 S2 = 60 (< 100 floor) -> retry. Attempt 2: +90 unique S2 = 150.
    assert n == 150
    assert s2_calls["n"] == 2  # S2 was re-issued after the transient blip


def test_breadth_probe_persistent_s2_failure_stays_below_floor(monkeypatch):
    """(c for Site 5): a PERSISTENT S2 failure (always []) means the union never crosses the floor
    even after all retries -> the probe returns the genuinely-low count, so the caller's
    _PREFLIGHT_MIN_BREADTH floor check still fails CLOSED (GateError). The retry never widens the
    floor; it only recovers a transient blip."""
    import src.polaris_graph.retrieval.live_retriever as lr
    import scripts.dr_benchmark.super_heavy_preflight as m

    monkeypatch.setenv("PG_BREADTH_PROBE_RETRIES", "2")
    monkeypatch.setenv("PG_BREADTH_PROBE_RETRY_BACKOFF_S", "0")
    monkeypatch.setenv("PG_SWEEP_MAX_SERPER", "100")
    monkeypatch.setenv("PG_SWEEP_MAX_S2", "100")

    serper_calls = {"n": 0}

    def _fake_serper(query, num=10, api_calls=None):
        serper_calls["n"] += 1
        return [{"url": f"https://serper/{i}"} for i in range(30)]  # only 30 < 100 floor

    def _fake_s2_dead(query, limit=20):
        return []  # persistent S2 outage

    monkeypatch.setattr(lr, "_serper_search", _fake_serper)
    monkeypatch.setattr(lr, "_s2_bulk_search", _fake_s2_dead)

    n = m._default_breadth_probe()
    # Union stays at 30 (< 100 floor) on every attempt -> probe returns the honest low count.
    assert n == 30
    # All attempts were exhausted (1 + PG_BREADTH_PROBE_RETRIES) because the floor was never met.
    assert serper_calls["n"] == 3
    assert n < m._PREFLIGHT_MIN_BREADTH  # the caller's floor check will fail CLOSED on this
