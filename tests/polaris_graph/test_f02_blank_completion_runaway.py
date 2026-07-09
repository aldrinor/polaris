"""I-arch-004 F02 (#1255) — generator empty-completion reasoning-runaway + silent skip.

PROVES the three F02 harness behaviors that fix the drb_72 death (a blank HTTP 200 logged
``status=ok`` then silently skipped after consuming ~473s of wall-clock):

  (a) HARNESS RAISE — a degenerate blank stream (content empty + usage NULL + finish_reason
      None) RAISES ``BlankCompletionError`` (a ``RuntimeError``) — it is NEVER returned as a
      ``status=ok`` LLMResponse. After ``MAX_RETRIES`` it re-raises (fail-CLOSED). One
      harness-level guard covers BOTH generate and judge call_types.
  (b) RETRY ROTATION — the retry does NOT reuse the blanking provider: the served provider is
      mapped to its routing slug and added to ``body['provider']['ignore']`` BEFORE the re-POST
      (the generator is pinned ``allow_fallbacks=false`` so OpenRouter will not auto-advance off
      an empty 200; a same-provider retry would re-stall).
  (c) NARROWNESS (no faithfulness/recovery regression) — the gate fires ONLY on the exact
      degenerate CONJUNCTION. A blank-content response that carries a usage block (the
      ``</think>``-recoverable misroute / truncation shape) does NOT trip the BlankCompletionError
      guard, so the existing recovery + FX-01 paths are untouched.
  (d) CONTRACT-SLOT REASONING CAP — the V30 ``_m63_llm_call`` lowers the reasoning sub-budget for
      its terse extraction / <=3-sentence narrative calls (``PG_CONTRACT_SLOT_REASONING_MAX_TOKENS``)
      and bounds them with a stall timeout — it does NOT starve the content budget.

HERMETIC / OFFLINE: every test monkeypatches ``client._client.post`` (the non-stream seam, forced
via ``response_format=json_object`` + ``reasoning_enabled=False``) or inspects request bodies. NO
socket is opened, NO live LLM is called. This is a RELIABILITY/COST fix — NO faithfulness gate is
relaxed (the terminal raise stays fail-CLOSED; the contract-slot CONTENT budget stays ample).
"""

from __future__ import annotations

import asyncio
import copy

import httpx
import pytest

from src.polaris_graph.llm import openrouter_client
from src.polaris_graph.llm.openrouter_client import BlankCompletionError

_GEN_REQUEST = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")


# --------------------------------------------------------------------------------------------- env
@pytest.fixture(autouse=True)
def _hermetic_env(monkeypatch):
    """Fix the OpenRouter key + generator model; zero the backoff sleeps so retries don't sleep."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-hermetic")
    # The blanking-provider rotation maps the served display name -> routing slug; keep that
    # deterministic regardless of any ambient provider-routing config fixture.
    yield


async def _noop_async_sleep(*_a, **_k):
    return None


# --------------------------------------------------------------------------------------------- payloads
def _blank_degenerate_response(provider: str = "DeepInfra") -> httpx.Response:
    """The drb_72 degenerate signature on the non-stream seam: a 200 whose single choice has EMPTY
    content, NO ``usage`` block (null usage), and NO ``finish_reason``. Carries a ``provider`` so the
    rotation has an identity to exclude."""
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": ""}}],  # no finish_reason, content blank
            "model": "deepseek/deepseek-v4-pro",
            "provider": provider,
            # NOTE: NO "usage" key -> data.get("usage") is falsy -> usage_was_null is True.
        },
        request=_GEN_REQUEST,
    )


def _ok_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": "the answer"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.0001},
            "model": "deepseek/deepseek-v4-pro",
            "provider": "Novita",
        },
        request=_GEN_REQUEST,
    )


def _blank_but_has_usage_response() -> httpx.Response:
    """A blank-CONTENT 200 that DOES carry a usage block + a finish_reason — the
    ``</think>``-recoverable misroute / truncation shape. Must NOT trip BlankCompletionError (the
    gate is the degenerate CONJUNCTION only); the EXISTING empty-content+empty-reasoning FIX-H2
    guard (ValueError) owns this both-empty case instead."""
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": ""}, "finish_reason": "length"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 0, "cost": 0.0001},
            "model": "deepseek/deepseek-v4-pro",
            "provider": "DeepInfra",
        },
        request=_GEN_REQUEST,
    )


def _make_client(monkeypatch, post_side_effects):
    """OpenRouterClient whose ``_client.post`` returns/raises queued side effects in order, and
    records each request body for the rotation assertion. ``response_format=json_object`` +
    ``reasoning_enabled=False`` forces the NON-STREAM path (a single mockable ``post`` coroutine)."""
    client = openrouter_client.OpenRouterClient(api_key="test-key-hermetic")
    state = {"n": 0, "bodies": []}

    async def _fake_post(*args, **kwargs):
        i = state["n"]
        state["n"] += 1
        # DEEP-COPY the body sent on THIS attempt — `_call_impl` mutates the SAME
        # body['provider']['ignore'] list in place across attempts, so a shallow capture would show
        # every snapshot with the final mutated state. The rotation assertion reads body[1].
        state["bodies"].append(copy.deepcopy(kwargs.get("json")))
        effect = post_side_effects[min(i, len(post_side_effects) - 1)]
        if isinstance(effect, Exception):
            raise effect
        return effect

    monkeypatch.setattr(client._client, "post", _fake_post)
    monkeypatch.setattr(openrouter_client.asyncio, "sleep", _noop_async_sleep)
    return client, state


def _run(client, **overrides):
    kwargs = dict(
        messages=[{"role": "user", "content": "q"}],
        call_type="contract_slot",
        reasoning_enabled=False,
        response_format={"type": "json_object"},
    )
    kwargs.update(overrides)
    return asyncio.run(client._call_impl(**kwargs))


# --------------------------------------------------------------------------------------------- (a) RAISE
def test_blank_degenerate_stream_raises_not_status_ok(monkeypatch):
    """(a) EVERY attempt returns the degenerate blank 200 -> after MAX_RETRIES the
    BlankCompletionError re-raises (fail-CLOSED). The blank is NEVER returned as a status=ok
    LLMResponse, and BlankCompletionError IS a RuntimeError (caught by generic transport handlers)."""
    client, state = _make_client(monkeypatch, [_blank_degenerate_response()])
    with pytest.raises(BlankCompletionError):
        _run(client)
    assert issubclass(BlankCompletionError, RuntimeError)
    # MAX_RETRIES+1 attempts were made (each blank retried until the cap), then re-raised.
    assert state["n"] == openrouter_client.MAX_RETRIES + 1


def test_blank_degenerate_then_success_recovers(monkeypatch):
    """(a)+(b) ONE degenerate blank 200 then a valid 200 -> the call RECOVERS (the response is
    returned), proving the blank was RETRIED in-loop, not consumed as content."""
    client, state = _make_client(monkeypatch, [_blank_degenerate_response(), _ok_response()])
    resp = _run(client)
    assert resp.content == "the answer"
    assert state["n"] == 2  # one blank attempt + one success


# --------------------------------------------------------------------------------------------- (b) ROTATION
def test_retry_excludes_the_blanking_provider(monkeypatch):
    """(b) The retry MUST NOT reuse the blanking provider: the served provider ('WandB') is mapped to
    its routing slug ('wandb') and added to body['provider']['ignore'] BEFORE the re-POST. (The
    generator is allow_fallbacks=false; OpenRouter does not auto-advance off a blank 200, so without
    this the retry re-stalls on the same provider.)

    'Phala' is chosen because it IS in the generator's glm-5.2 `order` chain
    [friendli, novita, z-ai, phala] but NOT in its base `ignore`, so the assertion proves the ROTATION
    added it (absent on attempt 1, present on the retry) — not a pre-existing config exclusion. (Codex+
    Fable gate-fix P1-1: the generator `order`/`ignore` pins are RESTORED as the byte-identical default;
    the prior 'WandB' probe was in the base `ignore`, so it no longer distinguishes rotation from the
    config deny-list.)"""
    client, state = _make_client(
        monkeypatch, [_blank_degenerate_response(provider="Phala"), _ok_response()]
    )
    resp = _run(client)
    assert resp.content == "the answer"
    assert state["n"] == 2
    # The first request did NOT exclude phala; the RETRY request excludes the blanking provider.
    first_ignore = (state["bodies"][0].get("provider", {}) or {}).get("ignore", [])
    retry_ignore = (state["bodies"][1].get("provider", {}) or {}).get("ignore", [])
    assert "phala" not in first_ignore
    assert "phala" in retry_ignore


# --------------------------------------------------------------------------------------------- (a) STREAM PATH
def test_blank_degenerate_STREAM_raises(monkeypatch):
    """(a) The PRIMARY drb_72 path is STREAMING. ``_accumulate_sse`` always synthesizes a
    ``{"finish_reason": None}``-only usage dict even when the stream dies blank, so the guard must
    test for the ABSENCE of real token-count keys (not dict-emptiness). A streaming blank-death
    (content='' + usage carrying NO token counts + finish_reason None) RAISES BlankCompletionError —
    proving the gate fires on the streaming seam, not only the non-stream seam."""
    client = openrouter_client.OpenRouterClient(api_key="test-key-hermetic")
    monkeypatch.setattr(openrouter_client.asyncio, "sleep", _noop_async_sleep)
    state = {"n": 0}

    async def _fake_read_stream(body, timeout):
        state["n"] += 1
        # (content, reasoning, usage, served) — the blank-death shape: only the synthetic
        # finish_reason key, NO prompt/completion/total tokens, finish_reason None.
        return "", "", {"finish_reason": None}, {"provider": "WandB"}

    monkeypatch.setattr(client, "_read_stream", _fake_read_stream)
    with pytest.raises(BlankCompletionError):
        asyncio.run(
            client._call_impl(
                messages=[{"role": "user", "content": "q"}],
                call_type="contract_slot",
                reasoning_enabled=False,
            )
        )
    # MAX_RETRIES+1 streaming attempts, then fail-CLOSED (never status=ok).
    assert state["n"] == openrouter_client.MAX_RETRIES + 1


# ----------------------------------------------- (b) REAL SSE-PATH rotation (NON-Path-B, real _accumulate_sse)
class _FakeStreamResponse:
    """Minimal async-context-manager fake of an httpx streaming response that drives the REAL
    ``_accumulate_sse`` — so the test exercises the actual served-provider capture gate (NOT a
    monkeypatched _read_stream). ``aiter_lines`` replays the queued SSE lines."""

    def __init__(self, lines):
        self._lines = lines
        self.headers = {"content-type": "text/event-stream"}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def raise_for_status(self):
        return None

    async def aiter_lines(self):
        for ln in self._lines:
            yield ln


def _sse_blank_death_lines(provider: str) -> list[str]:
    """SSE chunks for a degenerate blank-death stream: a chunk carrying ONLY the served `provider`
    (no content delta, no usage, no finish_reason) then a clean [DONE]. _accumulate_sse will return
    content='' + a usage dict with NO token keys + served={'provider': provider}."""
    return [
        f'data: {{"provider": "{provider}", "choices": [{{"delta": {{}}}}]}}',
        "data: [DONE]",
    ]


def _sse_ok_lines() -> list[str]:
    """SSE chunks for a healthy completion: a content delta + a usage chunk + [DONE]."""
    return [
        'data: {"provider": "Novita", "choices": [{"delta": {"content": "the answer"}, '
        '"finish_reason": "stop"}]}',
        'data: {"usage": {"prompt_tokens": 10, "completion_tokens": 5}}',
        "data: [DONE]",
    ]


def test_REAL_sse_path_rotation_excludes_blanking_provider(monkeypatch):
    """(b) REAL streaming-seam regression (Codex diff-gate P1): in a NORMAL (non-Path-B) run, the
    served-provider capture must be available so the rotation excludes the blanking provider. Drives
    the REAL ``_accumulate_sse`` (the served-provider capture is now UNCONDITIONAL, not Path-B-gated)
    by mocking only ``self._client.stream``. Proves the FIRST attempt blanks on 'Phala' and the RETRY
    request carries 'phala' in body['provider']['ignore'] — then recovers. ('Phala' is in the restored
    glm-5.2 `order` chain but not the base `ignore`; see the P1-1 note on the non-stream sibling test.)"""
    client = openrouter_client.OpenRouterClient(api_key="test-key-hermetic")
    monkeypatch.setattr(openrouter_client.asyncio, "sleep", _noop_async_sleep)
    # Confirm Path-B is INACTIVE for this run (the gate the P1 was about).
    assert not openrouter_client._pathb_capture.is_active()
    state = {"n": 0, "bodies": []}

    def _fake_stream(method, url, **kwargs):
        i = state["n"]
        state["n"] += 1
        state["bodies"].append(copy.deepcopy(kwargs.get("json")))
        lines = _sse_blank_death_lines("Phala") if i == 0 else _sse_ok_lines()
        return _FakeStreamResponse(lines)

    monkeypatch.setattr(client._client, "stream", _fake_stream)
    resp = asyncio.run(
        client._call_impl(
            messages=[{"role": "user", "content": "q"}],
            call_type="contract_slot",
            reasoning_enabled=False,
        )
    )
    assert resp.content == "the answer"
    assert state["n"] == 2
    # The blanking provider 'Phala' -> slug 'phala' was NOT excluded on attempt 1, but IS on retry —
    # proving the rotation works on the REAL streaming path in a non-Path-B run.
    first_ignore = (state["bodies"][0].get("provider", {}) or {}).get("ignore", [])
    retry_ignore = (state["bodies"][1].get("provider", {}) or {}).get("ignore", [])
    assert "phala" not in first_ignore
    assert "phala" in retry_ignore


def _sse_blank_death_no_provider() -> list[str]:
    """SSE chunks for the WORST drb_72 case: a fully-dead stream that emits NO `provider` field at
    all (just an empty delta then [DONE]). _accumulate_sse returns served={} — so the rotation has
    NO served identity and MUST fall back to the request order[0]."""
    return ['data: {"choices": [{"delta": {}}]}', "data: [DONE]"]


def test_REAL_sse_path_rotation_falls_back_to_order_when_provider_unknown(monkeypatch):
    """(b) The order[0] fallback (Codex diff-gate P1): a fully-dead stream that reports NO provider
    field leaves served={}, so unconditional-capture alone CANNOT rotate. The fallback must exclude
    the pinned current provider = order[0]. Without it the retry re-POSTs the same stalled provider
    (allow_fallbacks=false) — the exact drb_72 runaway."""
    monkeypatch.setenv("OPENROUTER_PROVIDER_ORDER", "wandb,siliconflow,baidu")
    monkeypatch.setenv("OPENROUTER_ALLOW_FALLBACKS", "false")
    client = openrouter_client.OpenRouterClient(api_key="test-key-hermetic")
    monkeypatch.setattr(openrouter_client.asyncio, "sleep", _noop_async_sleep)
    assert not openrouter_client._pathb_capture.is_active()
    state = {"n": 0, "bodies": []}

    def _fake_stream(method, url, **kwargs):
        i = state["n"]
        state["n"] += 1
        state["bodies"].append(copy.deepcopy(kwargs.get("json")))
        lines = _sse_blank_death_no_provider() if i == 0 else _sse_ok_lines()
        return _FakeStreamResponse(lines)

    monkeypatch.setattr(client._client, "stream", _fake_stream)
    resp = asyncio.run(
        client._call_impl(
            messages=[{"role": "user", "content": "q"}],
            call_type="contract_slot",
            reasoning_enabled=False,
        )
    )
    assert resp.content == "the answer"
    assert state["n"] == 2
    # No served provider was reported, so the rotation fell back to order[0]=wandb on the retry.
    first_ignore = (state["bodies"][0].get("provider", {}) or {}).get("ignore", [])
    retry_ignore = (state["bodies"][1].get("provider", {}) or {}).get("ignore", [])
    assert "wandb" not in first_ignore
    assert "wandb" in retry_ignore


# --------------------------------------------------------------------------------------------- (c) NARROWNESS
def test_blank_with_usage_does_not_trip_degenerate_guard(monkeypatch):
    """(c) A blank-CONTENT response that DOES carry a usage block + finish_reason is NOT the
    degenerate signature -> it must NOT raise BlankCompletionError. (The both-empty case is owned by
    the existing FIX-H2 ValueError instead — proving the new gate is the narrow CONJUNCTION and does
    not shadow the recovery/truncation paths.)"""
    client, _state = _make_client(monkeypatch, [_blank_but_has_usage_response()])
    with pytest.raises(Exception) as exc_info:
        _run(client)
    # It is NOT the degenerate-blank guard (usage was present) — it is the FIX-H2 both-empty
    # ValueError (content empty AND reasoning empty), which is a distinct fail-closed terminal.
    assert not isinstance(exc_info.value, BlankCompletionError)
    assert isinstance(exc_info.value, ValueError)


# --------------------------------------------------------------------------------------------- (d) CONTRACT-SLOT CAP
def test_contract_slot_reasoning_cap_is_lowered_and_content_not_starved():
    """(d) The V30 contract-slot call lowers the reasoning sub-budget (so the terse extraction /
    <=3-sentence narrative does not burn a deep-reasoning runaway) while keeping the CONTENT budget
    ample. Asserts the module constants are the lowered reasoning value + a stall timeout well under
    the section wall, and that the content floor stays generous (no §9.1.8 content starvation)."""
    from src.polaris_graph.generator import multi_section_generator as msg

    # Reasoning sub-budget is the LOWERED value (terse calls don't need deep reasoning) ...
    assert msg.PG_CONTRACT_SLOT_REASONING_MAX_TOKENS <= 4096
    assert msg.PG_CONTRACT_SLOT_REASONING_MAX_TOKENS > 0
    # ... while the CONTENT budget floor stays ample (serves §9.1.8 "never starve content").
    assert msg.PG_CONTRACT_SLOT_MIN_MAX_TOKENS >= msg.PG_CONTRACT_SLOT_REASONING_MAX_TOKENS
    # ... and the per-call stall timeout is WELL UNDER the section WALL-CLOCK backstop BUT
    # comfortably ABOVE the observed legitimate contract-slot duration (the drb_72 slot ran ~473s; a
    # 25K-char FDA-label regulatory echo runs 400-545s on the slow band). A too-tight stall timeout
    # would false-time-out a legitimate clinical regulatory slot → not_extractable → missing
    # FDA-label content (a §-1.1 completeness regression). 600s floor guards against re-tightening it.
    #
    # I-arch-005 B24 (#1257): the upper bound is the section WALL-CLOCK (_section_wallclock_seconds,
    # default 1800s), NOT the main GENERATOR_TIMEOUT_SECONDS. The contract-slot call passes its OWN
    # explicit timeout (PG_CONTRACT_SLOT_STALL_TIMEOUT_S) to client.generate(); openrouter_client
    # _call_impl resolves `actual_timeout = timeout or default`, so an explicit timeout always wins and
    # GENERATOR_TIMEOUT_SECONDS (the *unset-caller* default, now right-sized to 600s for non-slate
    # callers) NEVER bounds this call. The runtime invariant that actually matters is therefore
    # slot_stall < section_wall: both inner per-call timeouts sit under the outer section backstop.
    from src.polaris_graph.generator.multi_section_generator import _section_wallclock_seconds
    assert 600 <= msg.PG_CONTRACT_SLOT_STALL_TIMEOUT_S < _section_wallclock_seconds()


def test_contract_slot_reasoning_cap_reaches_the_request_body(monkeypatch):
    """(d) The lowered reasoning budget actually REACHES the OpenRouter body: a reasoning-first
    model with reasoning_enabled=False + reasoning_max_tokens set lands the cap in
    body['reasoning']['max_tokens'] (openrouter_client branch 3). Proves the knob is wired, not a
    dead constant."""
    from src.polaris_graph.generator import multi_section_generator as msg

    client, state = _make_client(monkeypatch, [_ok_response()])
    # Mirror the _m63_llm_call shape: reasoning-OFF + an explicit tight reasoning_max_tokens.
    _run(
        client,
        reasoning_max_tokens=msg.PG_CONTRACT_SLOT_REASONING_MAX_TOKENS,
    )
    body = state["bodies"][0]
    assert body["reasoning"]["max_tokens"] == msg.PG_CONTRACT_SLOT_REASONING_MAX_TOKENS
    # The CONTENT budget (overall max_tokens) is NOT clamped down to the reasoning value — it stays
    # at the reasoning-first floor (ample content headroom), proving content is not starved.
    assert body["max_tokens"] >= msg.PG_CONTRACT_SLOT_MIN_MAX_TOKENS
