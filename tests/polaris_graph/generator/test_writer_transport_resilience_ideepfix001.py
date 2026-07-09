"""I-deepfix-001 B3/B4 (#1370) — offline tests for the WT-5 writer transport/throughput fixes.

Pure Python, no network / GPU / LLM. Covers:
  * the three DEFAULT-OFF flag helpers (byte-identity precondition),
  * the pure makespan-wall formula (B4 basket-scaled wall) incl. the frozen-flat invariant,
  * ``_call_writer``'s flag-gated transport-disconnect catch -> clean sentinel (B3),
  * ``_pre_pass_one_basket``'s transport-aware retry: a disconnect sentinel grants a FRESH reconnect
    window WITHOUT charging a productive attempt, and never leaks the sentinel into a draft,
  * ``abstractive_pre_pass``'s bounded K-span RECOVERY second pass (B4) and its default-OFF byte-identity,
  * the wall-scaled flag gating (OFF => flat wall).

Async coverage uses ``asyncio.run`` in sync test bodies (no pytest-asyncio dependency).
"""

from __future__ import annotations

import asyncio
import math
from types import SimpleNamespace

import httpx
import pytest

from src.polaris_graph.generator import abstractive_writer as aw


# ── DEFAULT-OFF flag helpers (byte-identity precondition) ─────────────────────────────────────────
@pytest.mark.parametrize(
    "helper, env",
    [
        (aw._wall_basket_scaled_enabled, aw._ENV_WALL_BASKET_SCALED),
        (aw._kspan_recovery_pass_enabled, aw._ENV_KSPAN_RECOVERY_PASS),
        (aw._deadline_transport_aware_enabled, aw._ENV_DEADLINE_TRANSPORT_AWARE),
    ],
)
def test_new_flags_default_off(monkeypatch, helper, env):
    monkeypatch.delenv(env, raising=False)
    assert helper() is False


@pytest.mark.parametrize("val", ["0", "", "false", "off", "no", "FALSE", "Off"])
def test_new_flags_falsy(monkeypatch, val):
    for env in (aw._ENV_WALL_BASKET_SCALED, aw._ENV_KSPAN_RECOVERY_PASS, aw._ENV_DEADLINE_TRANSPORT_AWARE):
        monkeypatch.setenv(env, val)
    assert aw._wall_basket_scaled_enabled() is False
    assert aw._kspan_recovery_pass_enabled() is False
    assert aw._deadline_transport_aware_enabled() is False


@pytest.mark.parametrize("val", ["1", "true", "on", "yes", "ON"])
def test_new_flags_truthy(monkeypatch, val):
    for env in (aw._ENV_WALL_BASKET_SCALED, aw._ENV_KSPAN_RECOVERY_PASS, aw._ENV_DEADLINE_TRANSPORT_AWARE):
        monkeypatch.setenv(env, val)
    assert aw._wall_basket_scaled_enabled() is True
    assert aw._kspan_recovery_pass_enabled() is True
    assert aw._deadline_transport_aware_enabled() is True


# ── B4 pure makespan-wall formula ────────────────────────────────────────────────────────────────
def test_makespan_wall_matches_frozen_flat_default():
    # The documented flat _DEFAULT_WALL_DEADLINE_S == makespan(23 baskets, 8 conc, 1 retry, 120s).
    assert aw._makespan_wall_seconds(23, 8, 1, 120.0) == aw._DEFAULT_WALL_DEADLINE_S == 720.0


def test_makespan_wall_scales_up_for_large_section():
    # 104 baskets @ conc 24, 1 retry, 120s -> ceil(104/24)=5 waves * 2 * 120 = 1200s (> the flat 720).
    assert aw._makespan_wall_seconds(104, 24, 1, 120.0) == 1200.0
    assert aw._makespan_wall_seconds(113, 8, 1, 120.0) == math.ceil(113 / 8) * 2 * 120.0


def test_makespan_wall_zero_baskets():
    assert aw._makespan_wall_seconds(0, 8, 1, 120.0) == 0.0
    assert aw._makespan_wall_seconds(-3, 8, 1, 120.0) == 0.0


# ── B3 _call_writer transport-disconnect catch (flag-gated) ──────────────────────────────────────
class _RaisingClient:
    """OpenRouterClient double whose ``generate`` raises a transport disconnect; ``close`` is a no-op."""

    def __init__(self, exc, *_a, **_k):
        self._exc = exc

    async def generate(self, **_kwargs):
        raise self._exc

    async def close(self):
        return None


def _install_raising_client(monkeypatch, exc):
    monkeypatch.setattr(
        "src.polaris_graph.llm.openrouter_client.OpenRouterClient",
        lambda *a, **k: _RaisingClient(exc),
    )


def _one_member():
    # A member that survives _basket_supports_members + _compose_junk_screen (clean prose, SUPPORTS).
    return SimpleNamespace(
        evidence_id="e1",
        span_verdict="SUPPORTS",
        credibility_weight=1.0,
        direct_quote="Robots reduced the employment-to-population ratio by 0.2 percentage points.",
    )


@pytest.mark.parametrize(
    "exc",
    [
        httpx.ConnectTimeout("connect timed out"),
        httpx.ConnectError("connection refused"),
        httpx.RemoteProtocolError("server disconnected without sending a response"),
        httpx.ReadError("read error"),
    ],
)
def test_call_writer_catches_transport_when_enabled(monkeypatch, exc):
    _install_raising_client(monkeypatch, exc)
    members = [_one_member()]
    # A minimal evidence_pool row so _member_global_span can resolve (any non-crash value is fine —
    # generate() raises before the span matters).
    pool = {"e1": {"direct_quote": members[0].direct_quote}}
    out = asyncio.run(aw._call_writer(
        members, pool, model="z-ai/glm-5.2", max_tokens=32, reasoning_max_tokens=0,
        temperature=0.2, catch_transport=True,
    ))
    assert out == aw._WRITER_TRANSPORT_DISCONNECT


def test_call_writer_reraises_transport_when_disabled(monkeypatch):
    # Flag OFF (catch_transport defaults False) => byte-identical legacy behavior: the exception escapes.
    _install_raising_client(monkeypatch, httpx.ConnectTimeout("connect timed out"))
    members = [_one_member()]
    pool = {"e1": {"direct_quote": members[0].direct_quote}}
    with pytest.raises(httpx.ConnectTimeout):
        asyncio.run(aw._call_writer(
            members, pool, model="z-ai/glm-5.2", max_tokens=32, reasoning_max_tokens=0,
            temperature=0.2,  # catch_transport omitted -> False
        ))


# ── B3 _pre_pass_one_basket transport-aware sentinel handling ────────────────────────────────────
def _basket_with_one_member():
    return SimpleNamespace(claim_cluster_id="ccid-1", supporting_members=[_one_member()])


def test_transport_aware_sentinel_does_not_charge_productive_attempt(monkeypatch):
    # ON: first _call_writer returns the disconnect sentinel (a transport event -> fresh window, no
    # productive attempt charged), second returns a good draft that passes -> accepted. The wrapper is
    # invoked ONLY for the good draft (never for the sentinel), and last_draft never holds the sentinel.
    monkeypatch.setenv(aw._ENV_DEADLINE_TRANSPORT_AWARE, "1")
    monkeypatch.setenv(aw._ENV_MAX_RETRIES, "1")  # productive budget = 2 attempts

    calls = {"n": 0}

    async def fake_call_writer(*_a, **_k):
        calls["n"] += 1
        if calls["n"] == 1:
            return aw._WRITER_TRANSPORT_DISCONNECT
        return "Robots reduced employment by 0.2 percentage points. [#ev:e1:0-70]"

    wrapper_calls = {"n": 0}

    def fake_wrapper(draft, basket, pool, verify_fn):
        wrapper_calls["n"] += 1
        assert draft != aw._WRITER_TRANSPORT_DISCONNECT  # the sentinel is never verified
        return True, []

    monkeypatch.setattr(aw, "_call_writer", fake_call_writer)
    monkeypatch.setattr(aw, "_draft_passes_wrapper", fake_wrapper)

    result = asyncio.run(aw._pre_pass_one_basket(
        _basket_with_one_member(), {"e1": {"direct_quote": "x"}},
        writer_verify_fn=lambda *a, **k: None,
        model="z-ai/glm-5.2", max_retries=1, max_tokens=32, reasoning_max_tokens=0,
        temperature=0.2, call_deadline_s=5.0,
    ))
    assert result == "Robots reduced employment by 0.2 percentage points. [#ev:e1:0-70]"
    assert calls["n"] == 2          # two writer calls: disconnect + good
    assert wrapper_calls["n"] == 1  # only the good draft was verified


def test_transport_aware_sentinel_budget_exhausts_to_kspan(monkeypatch):
    # ON: every _call_writer returns the sentinel -> the bounded transport budget exhausts -> the
    # function returns "" (clean K-span), NEVER the sentinel string.
    monkeypatch.setenv(aw._ENV_DEADLINE_TRANSPORT_AWARE, "1")
    monkeypatch.setenv(aw._ENV_MAX_RETRIES, "1")

    async def always_sentinel(*_a, **_k):
        return aw._WRITER_TRANSPORT_DISCONNECT

    monkeypatch.setattr(aw, "_call_writer", always_sentinel)
    monkeypatch.setattr(aw, "_draft_passes_wrapper", lambda *a, **k: (False, ["x"]))

    result = asyncio.run(aw._pre_pass_one_basket(
        _basket_with_one_member(), {"e1": {"direct_quote": "x"}},
        writer_verify_fn=lambda *a, **k: None,
        model="z-ai/glm-5.2", max_retries=1, max_tokens=32, reasoning_max_tokens=0,
        temperature=0.2, call_deadline_s=5.0,
    ))
    assert result == ""
    assert aw._WRITER_TRANSPORT_DISCONNECT not in result


# ── abstractive_pre_pass: recovery pass + default-OFF byte-identity (B4) ──────────────────────────
def _fake_ppob_factory(call_log):
    async def fake_ppob(basket, evidence_pool, *, writer_verify_fn, model, max_retries,
                        max_tokens, reasoning_max_tokens, temperature, call_deadline_s,
                        group_mode=False):
        key = basket.claim_cluster_id
        call_log[key] = call_log.get(key, 0) + 1
        if key == "slow" and call_log[key] == 1:
            # First pass: stall past the (floored 1.0s) wall so this basket is abandoned.
            await asyncio.sleep(5.0)
            return "late"
        return f"draft-{key}"

    return fake_ppob


def _two_baskets():
    return [SimpleNamespace(claim_cluster_id="fast"), SimpleNamespace(claim_cluster_id="slow")]


def test_recovery_pass_redrafts_abandoned_basket(monkeypatch):
    monkeypatch.setenv(aw._ENV_KSPAN_RECOVERY_PASS, "1")
    monkeypatch.setenv(aw._ENV_WALL_DEADLINE_S, "1")     # floored to 1.0; slow (5.0s) is abandoned
    monkeypatch.setenv(aw._ENV_CALL_DEADLINE_S, "1")     # keeps the recovery makespan wall small
    monkeypatch.delenv(aw._ENV_WALL_BASKET_SCALED, raising=False)
    monkeypatch.delenv(aw._ENV_DEADLINE_TRANSPORT_AWARE, raising=False)
    call_log: dict = {}
    monkeypatch.setattr(aw, "_pre_pass_one_basket", _fake_ppob_factory(call_log))

    out = asyncio.run(aw.abstractive_pre_pass(
        _two_baskets(), {}, writer_verify_fn=lambda *a, **k: None,
    ))
    assert out.get("fast") == "draft-fast"
    assert out.get("slow") == "draft-slow"   # recovered on the second, fresh task
    assert call_log["slow"] == 2             # original (abandoned) + one recovery call


def test_recovery_off_is_byte_identical_abandon(monkeypatch):
    # OFF (default): the abandoned slow basket is NOT recovered -> absent from out; slow is called ONCE.
    monkeypatch.delenv(aw._ENV_KSPAN_RECOVERY_PASS, raising=False)
    monkeypatch.setenv(aw._ENV_WALL_DEADLINE_S, "1")
    monkeypatch.setenv(aw._ENV_CALL_DEADLINE_S, "1")
    monkeypatch.delenv(aw._ENV_WALL_BASKET_SCALED, raising=False)
    monkeypatch.delenv(aw._ENV_DEADLINE_TRANSPORT_AWARE, raising=False)
    call_log: dict = {}
    monkeypatch.setattr(aw, "_pre_pass_one_basket", _fake_ppob_factory(call_log))

    out = asyncio.run(aw.abstractive_pre_pass(
        _two_baskets(), {}, writer_verify_fn=lambda *a, **k: None,
    ))
    assert out.get("fast") == "draft-fast"
    assert "slow" not in out
    assert call_log["slow"] == 1


def test_pre_pass_happy_path_all_fast(monkeypatch):
    # Regression: the semaphore-parametrized _one still drafts every basket on the normal fast path.
    monkeypatch.delenv(aw._ENV_KSPAN_RECOVERY_PASS, raising=False)
    monkeypatch.delenv(aw._ENV_WALL_BASKET_SCALED, raising=False)
    monkeypatch.delenv(aw._ENV_DEADLINE_TRANSPORT_AWARE, raising=False)
    call_log: dict = {}
    monkeypatch.setattr(aw, "_pre_pass_one_basket", _fake_ppob_factory(call_log))

    baskets = [SimpleNamespace(claim_cluster_id=f"b{i}") for i in range(5)]
    out = asyncio.run(aw.abstractive_pre_pass(
        baskets, {}, writer_verify_fn=lambda *a, **k: None,
    ))
    assert out == {f"b{i}": f"draft-b{i}" for i in range(5)}
