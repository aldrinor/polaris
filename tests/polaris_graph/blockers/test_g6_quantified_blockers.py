"""I-pipe-012 (#1237) blocker tests — quantified_analysis typed-status + bounded retry.

Blocker: with many numbers present, ``run_quantified_section`` returned a bare
``None`` at several distinct death points (spec_provider raised / returned a
non-dict / build_quantified_spec rejected / execution failed / no verified
sentences), collapsing "no numbers to model" (a clean Writer DECLINE) and "the
differentiator silently broke" (a transport/parse fault) into the same signal. A
post-run audit could not tell them apart without scraping the free-text log.

Fix (kill-switch default-ON ``PG_QUANTIFIED_TYPED_STATUS=1``; ``=0`` reverts to the
pre-fix bare-``None`` shape): stamp a discrete ``telem["quantified_status"]`` in
{ok, declined_no_spec, empty_transport, parse_error} at every return point, plus a
BOUNDED retry (``PG_QUANTIFIED_SPEC_RETRIES``, default 1) on the TRANSIENT raised
path only (a non-dict return is a decline, never retried).

FAITHFULNESS: untouched. These tests exercise telemetry + spec-acquisition retry
ONLY — strict_verify / Regime C / NLI / 4-role / provenance are never relaxed. The
``ok`` case still requires ≥1 sentence to survive Regime C verification.

SPEND-FREE: every ``spec_provider`` is a fake async closure; the deterministic
render + sandbox path runs with no network. Plain assertions, no unittest.mock.

Coverage:
  flag-OFF identity        — PG_QUANTIFIED_TYPED_STATUS=0 -> no quantified_status key,
                             single spec_provider call (no retry), firing_status intact
  parseable -> ok          — a valid spec that fires stamps quantified_status=ok + payload
  unparseable -> parse_err — spec_provider RAISES -> quantified_status=parse_error (NOT None-silent),
                             AND the bounded retry actually re-invoked the provider
  no-spec -> declined      — spec_provider returns None -> quantified_status=declined_no_spec
  validation reject -> err — a bad dict failing build_quantified_spec -> parse_error
  retry honors decline     — a non-dict return is NOT retried (single call)
"""
from __future__ import annotations

import asyncio
import os

import src.polaris_graph.generator.quantified_analysis as qa
from src.polaris_graph.generator.quantified_analysis import (
    QUANTIFIED_STATUS_DECLINED_NO_SPEC,
    QUANTIFIED_STATUS_OK,
    QUANTIFIED_STATUS_PARSE_ERROR,
    _call_spec_provider_with_retry,
    _stamp_status,
    run_quantified_section,
)
from src.polaris_graph.tools.evidence_extractor import extract_numbers_from_evidence


# ── env helpers (no mock; explicit set/restore so flag state is deterministic) ──
class _env:
    """Context manager: set env vars for the body, restore exactly on exit, and
    REBIND the module-level flag constants that are read at import time so the test
    exercises the intended on/off behavior (the constants snapshot os.environ at
    import; tests must reload them, not just the env)."""

    def __init__(self, **kv: str):
        self._kv = kv
        self._saved: dict[str, str | None] = {}
        self._saved_flag = qa._TYPED_STATUS_ENABLED
        self._saved_retries = qa._SPEC_PROVIDER_RETRIES

    def __enter__(self):
        for k, v in self._kv.items():
            self._saved[k] = os.environ.get(k)
            os.environ[k] = v
        qa._TYPED_STATUS_ENABLED = os.environ.get(
            "PG_QUANTIFIED_TYPED_STATUS", "1"
        ).strip().lower() not in ("0", "false", "no", "off")
        qa._SPEC_PROVIDER_RETRIES = max(
            0, int(os.environ.get("PG_QUANTIFIED_SPEC_RETRIES", "1"))
        )
        return self

    def __exit__(self, *exc):
        for k, old in self._saved.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old
        qa._TYPED_STATUS_ENABLED = self._saved_flag
        qa._SPEC_PROVIDER_RETRIES = self._saved_retries
        return False


# ── shared fixtures ─────────────────────────────────────────────────────────
def _firing_rows():
    return {
        "ev_1": {
            "statement": "The total program cost was $2.0 billion in fiscal 2024.",
            "direct_quote": "The total program cost was $2.0 billion in fiscal 2024.",
            "source_url": "https://example.org/x", "tier": "T1",
        },
    }


def _ok_spec_provider():
    """A spec_provider that produces a spec which VALIDATES, EXECUTES, and lands ≥1
    Regime-C-verified sentence (mirrors test_p7_sweep_orchestrator_end_to_end)."""
    async def spec_provider(_q, sourced):
        dp = next(d for d in sourced if abs(float(d["value"]) - 2_000_000_000.0) < 1)
        return {
            "model_id": "tco", "title": "TCO",
            "inputs": [
                {"name": "cost", "datapoint_ref": {
                    "ev_id": dp["evidence_id"], "label": dp["label"],
                    "context": dp["context"], "value": dp["value"],
                    "unit": dp["unit"]}},
                {"name": "years", "base": 3.0, "unit": "years",
                 "sweep": [1.0, 5.0, 1.0], "modeled": True},
            ],
            "outputs": [{"name": "tco", "unit": "USD", "display_kind": "currency",
                         "formula": "cost * years"}],
            "sensitivity": [{"input": "years", "output": "tco"}],
        }
    return spec_provider


def _run(spec_provider, rows):
    return asyncio.run(run_quantified_section("q", rows, spec_provider=spec_provider))


# ── flag-OFF identity ───────────────────────────────────────────────────────
def test_flag_off_no_status_key_and_single_call():
    """PG_QUANTIFIED_TYPED_STATUS=0 => byte-identical pre-fix shape: NO
    quantified_status key, and exactly ONE spec_provider call (no retry) even on a
    raised fault. firing_status / firing_error preserved exactly."""
    rows = {"ev_1": {"statement": "x", "direct_quote": "x"}}
    calls = {"n": 0}

    async def raising_provider(_q, _s):
        calls["n"] += 1
        raise RuntimeError("simulated 404 on generator route")

    with _env(PG_QUANTIFIED_TYPED_STATUS="0"):
        section, telem = _run(raising_provider, rows)

    assert section is None
    assert "quantified_status" not in telem            # additive key suppressed
    assert telem["firing_status"] == "spec_provider_error"   # legacy signal intact
    assert "simulated 404" in telem.get("firing_error", "")
    assert calls["n"] == 1                              # NO retry when flag OFF


def test_flag_off_decline_identical():
    """Flag-OFF: a Writer decline (None) keeps the exact legacy firing_status and
    grows no new key."""
    rows = {"ev_1": {"statement": "Qualitative only.", "direct_quote": "Qualitative only."}}

    async def decline(_q, _s):
        return None

    with _env(PG_QUANTIFIED_TYPED_STATUS="0"):
        section, telem = _run(decline, rows)

    assert section is None
    assert telem["spec_produced"] is False
    assert telem["firing_status"] == "no_spec_returned"
    assert "quantified_status" not in telem


# ── parseable -> ok + payload ───────────────────────────────────────────────
def test_parseable_returns_ok_with_payload():
    rows = _firing_rows()
    # sanity: the extractor really produced the $2.0B datapoint we model
    dps = extract_numbers_from_evidence(rows)
    assert any(abs(float(d["value"]) - 2_000_000_000.0) < 1 for d in dps)

    with _env(PG_QUANTIFIED_TYPED_STATUS="1"):
        section, telem = _run(_ok_spec_provider(), rows)

    assert telem["quantified_status"] == QUANTIFIED_STATUS_OK
    # legacy "fired" path still holds (typed status ADDS, never replaces)
    assert telem["firing_status"] == "fired"
    # payload: a verified section + the kept-sentence count (>=1 survived Regime C)
    assert section is not None and "Quantified Trade-off" in section
    assert telem["verified_sentences"] >= 1


# ── unparseable (raised) -> parse_error, NOT silent None ────────────────────
def test_raised_provider_returns_parse_error_not_silent():
    rows = {"ev_1": {"statement": "x", "direct_quote": "x"}}

    async def raising_provider(_q, _s):
        raise ValueError("malformed JSON from generator route")

    with _env(PG_QUANTIFIED_TYPED_STATUS="1", PG_QUANTIFIED_SPEC_RETRIES="1"):
        section, telem = _run(raising_provider, rows)

    assert section is None                              # still fail-closed (no fabrication)
    assert telem["quantified_status"] == QUANTIFIED_STATUS_PARSE_ERROR
    assert telem["firing_status"] == "spec_provider_error"
    assert "malformed JSON" in telem.get("firing_error", "")


def test_bounded_retry_reinvokes_on_transient_raise():
    """The bounded retry actually RE-INVOKES the provider on a raised fault: with 2
    retries a provider that raises twice then succeeds must land ``ok``; total
    attempts == 1 + retries when it never recovers."""
    rows = _firing_rows()
    calls = {"n": 0}
    ok = _ok_spec_provider()

    async def flaky(_q, sourced):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise ConnectionError("transient transport blip")
        return await ok(_q, sourced)

    with _env(PG_QUANTIFIED_TYPED_STATUS="1", PG_QUANTIFIED_SPEC_RETRIES="2"):
        section, telem = _run(flaky, rows)

    assert calls["n"] == 3                              # 2 failures + 1 success
    assert telem["quantified_status"] == QUANTIFIED_STATUS_OK
    assert section is not None


def test_retry_exhausts_then_parse_error():
    rows = {"ev_1": {"statement": "x", "direct_quote": "x"}}
    calls = {"n": 0}

    async def always_raises(_q, _s):
        calls["n"] += 1
        raise TimeoutError("provider down")

    with _env(PG_QUANTIFIED_TYPED_STATUS="1", PG_QUANTIFIED_SPEC_RETRIES="2"):
        section, telem = _run(always_raises, rows)

    assert calls["n"] == 3                              # 1 + 2 retries, all attempted
    assert section is None
    assert telem["quantified_status"] == QUANTIFIED_STATUS_PARSE_ERROR


# ── no-spec (decline) -> declined_no_spec ───────────────────────────────────
def test_decline_returns_declined_no_spec_and_not_retried():
    """A non-dict (None) return is a Writer DECLINE: typed status is
    declined_no_spec AND it is NOT retried (re-billing a decline is waste)."""
    rows = {"ev_1": {"statement": "Qualitative finding, no usable numbers.",
                     "direct_quote": "Qualitative finding, no usable numbers."}}
    calls = {"n": 0}

    async def decline(_q, _s):
        calls["n"] += 1
        return None

    with _env(PG_QUANTIFIED_TYPED_STATUS="1", PG_QUANTIFIED_SPEC_RETRIES="3"):
        section, telem = _run(decline, rows)

    assert section is None
    assert telem["spec_produced"] is False
    assert telem["quantified_status"] == QUANTIFIED_STATUS_DECLINED_NO_SPEC
    assert telem["firing_status"] == "no_spec_returned"
    assert calls["n"] == 1                              # decline NOT retried


# ── validation-rejected dict -> parse_error ─────────────────────────────────
def test_bad_dict_validation_rejected_is_parse_error():
    """A dict that fails build_quantified_spec hard validation is a malformed
    payload -> parse_error family (not a clean decline, not silent None)."""
    rows = _firing_rows()

    async def bad_dict(_q, _s):
        # well-formed JSON object but invalid model (model_id with spaces, no inputs)
        return {"model_id": "has spaces", "title": "t", "inputs": [], "outputs": []}

    with _env(PG_QUANTIFIED_TYPED_STATUS="1"):
        section, telem = _run(bad_dict, rows)

    assert section is None
    assert telem["firing_status"] == "spec_validation_rejected"
    assert telem["quantified_status"] == QUANTIFIED_STATUS_PARSE_ERROR


# ── pure-helper unit coverage (stamp + retry) ───────────────────────────────
def test_stamp_status_respects_kill_switch():
    with _env(PG_QUANTIFIED_TYPED_STATUS="0"):
        t: dict = {}
        _stamp_status(t, QUANTIFIED_STATUS_OK)
        assert "quantified_status" not in t            # OFF => no key
    with _env(PG_QUANTIFIED_TYPED_STATUS="1"):
        t = {}
        _stamp_status(t, QUANTIFIED_STATUS_OK)
        assert t["quantified_status"] == QUANTIFIED_STATUS_OK


def test_retry_helper_returns_value_and_exc():
    async def good(_q, _s):
        return {"ok": True}

    async def bad(_q, _s):
        raise RuntimeError("boom")

    with _env(PG_QUANTIFIED_TYPED_STATUS="1", PG_QUANTIFIED_SPEC_RETRIES="1"):
        val, exc = asyncio.run(_call_spec_provider_with_retry(good, "q", []))
        assert val == {"ok": True} and exc is None
        val2, exc2 = asyncio.run(_call_spec_provider_with_retry(bad, "q", []))
        assert val2 is None and isinstance(exc2, RuntimeError)
