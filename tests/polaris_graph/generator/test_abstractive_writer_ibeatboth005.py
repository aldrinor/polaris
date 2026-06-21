"""I-beatboth-005 (#1282) — unit tests for the FAITHFUL ABSTRACTIVE WRITER module.

Deterministic, no-network unit coverage of ``abstractive_writer`` — the writer-specific verify
WRAPPER (the four P1 closures), the fail-closed activation guard, the sync writer_fn dict lookup,
the model resolution, the default-OFF flag, and the P1-3 numeric-completeness helpers. The
behavioral end-to-end proof (compose loop + section tail, FAIL LOUD) lives in
``scripts/iarch_beatboth005_abstractive_writer_replay_harness.py`` per §-1.4.

A tiny in-test FAKE verifier stands in for ``verify_sentence_provenance`` ONLY where we are unit-
testing the WRAPPER's behavior on a returned ``SentenceVerification`` (P1-1 judge_error demotion,
P1-2 kwarg pinning) — using the real ``SentenceVerification`` dataclass so ``dataclasses.replace``
is exercised exactly as in production. The P1-3 helpers + the activation guard call the REAL engine
helpers / mode resolver.
"""

from __future__ import annotations

import pytest

from src.polaris_graph.generator import abstractive_writer as aw
from src.polaris_graph.generator.provenance_generator import (
    ProvenanceToken,
    SentenceVerification,
)


# ── default-OFF flag (byte-identity precondition) ────────────────────────────────────────────────
def test_writer_disabled_by_default(monkeypatch):
    monkeypatch.delenv(aw._ENV_ENABLE, raising=False)
    assert aw._abstractive_writer_enabled() is False


@pytest.mark.parametrize("val", ["0", "", "false", "off", "no", "FALSE", "Off"])
def test_writer_disabled_for_falsy_values(monkeypatch, val):
    monkeypatch.setenv(aw._ENV_ENABLE, val)
    assert aw._abstractive_writer_enabled() is False


@pytest.mark.parametrize("val", ["1", "true", "on", "yes", "ON"])
def test_writer_enabled_for_truthy_values(monkeypatch, val):
    monkeypatch.setenv(aw._ENV_ENABLE, val)
    assert aw._abstractive_writer_enabled() is True


# ── model resolution (LAW VI + §9.1.8 lock conformance) ──────────────────────────────────────────
def test_model_explicit_override_wins(monkeypatch):
    monkeypatch.setenv(aw._ENV_MODEL, "vendor/some-model")
    monkeypatch.setenv("PG_GENERATOR_MODEL", "vendor/generator")
    assert aw._resolve_model() == "vendor/some-model"


def test_model_falls_back_to_generator_role(monkeypatch):
    monkeypatch.delenv(aw._ENV_MODEL, raising=False)
    monkeypatch.setenv("PG_GENERATOR_MODEL", "z-ai/glm-5.2")
    assert aw._resolve_model() == "z-ai/glm-5.2"


def test_model_default_is_operator_glm52(monkeypatch):
    monkeypatch.delenv(aw._ENV_MODEL, raising=False)
    monkeypatch.delenv("PG_GENERATOR_MODEL", raising=False)
    assert aw._resolve_model() == "z-ai/glm-5.2"


# ── _basket_key (stable canonical id) ────────────────────────────────────────────────────────────
def test_basket_key_uses_claim_cluster_id():
    class _B:
        claim_cluster_id = "ccid-7"
    assert aw._basket_key(_B()) == "ccid-7"


def test_basket_key_empty_when_missing():
    assert aw._basket_key(object()) == ""


# ── sync writer_fn — pure dict lookup (P1-4 adapter) ─────────────────────────────────────────────
def test_writer_fn_returns_precomputed_draft():
    class _B:
        claim_cluster_id = "k1"
    fn = aw.make_abstractive_writer_fn({"k1": "drafted prose"})
    assert fn(_B(), {}) == "drafted prose"


def test_writer_fn_missing_key_returns_empty_string():
    class _B:
        claim_cluster_id = "absent"
    fn = aw.make_abstractive_writer_fn({"k1": "drafted prose"})
    assert fn(_B(), {}) == ""  # -> the loop treats a writer-empty basket as a K-span fallback


# ── P1-3 numeric-completeness helpers reuse the ENGINE'S definition ──────────────────────────────
def test_substantive_span_numerics_decimals_and_percent_ints():
    span = "Response was 13.0 percent in arm A and 27 percent in arm B over 104 weeks."
    nums = aw._substantive_span_numerics(span)
    assert "13.0" in nums          # decimal — substantive
    assert "27" in nums            # percent-expressed integer — substantive
    assert "104" not in nums       # bare structural integer (weeks marker) — NOT substantive


def test_substantive_span_numerics_excludes_study_markers():
    # bare integers with no percent are study/structural markers the engine itself exempts.
    span = "In STEP 1, the cohort of 240 patients was followed for 68 weeks."
    nums = aw._substantive_span_numerics(span)
    assert nums == set()


def test_numeral_appears_verbatim_exact_match():
    assert aw._numeral_appears_verbatim("13.0", "the rate reached 13.0 percent") is True
    # "13" must NOT match "13.0" (a dropped decimal is a real numeric change).
    assert aw._numeral_appears_verbatim("13.0", "the rate reached 13 percent") is False


def test_cited_span_text_for_slices_the_token_subspan():
    quote = "ABCDE faithful claim text here."
    pool = {"ev_x": {"evidence_id": "ev_x", "direct_quote": quote}}
    tok = ProvenanceToken(evidence_id="ev_x", start=0, end=5, raw="[#ev:ev_x:0-5]")
    assert aw._cited_span_text_for([tok], pool) == "ABCDE"


def test_cited_span_text_for_out_of_bounds_is_empty():
    pool = {"ev_x": {"evidence_id": "ev_x", "direct_quote": "short"}}
    tok = ProvenanceToken(evidence_id="ev_x", start=0, end=999, raw="[#ev:ev_x:0-999]")
    assert aw._cited_span_text_for([tok], pool) == ""


# ── P1-1 / P1-2 wrapper behavior (real SentenceVerification + dataclasses.replace) ───────────────
def _sv(*, is_verified=True, judge_error=False, sentence="", tokens=None, reasons=None):
    return SentenceVerification(
        sentence=sentence, tokens=tokens or [], is_verified=is_verified,
        failure_reasons=list(reasons or []), judge_error=judge_error,
    )


def test_wrapper_pins_local_window_fallback_false():
    """P1-2: the wrapper must pass allow_local_window_fallback=False to the base verifier."""
    seen = {}

    def _base(sentence, pool, *args, **kwargs):
        seen["alwf"] = kwargs.get("allow_local_window_fallback")
        return _sv(is_verified=True, sentence=sentence)

    wrapped = aw.make_writer_verify_fn(_base)
    wrapped("a claim [#ev:ev_x:0-5]", {"ev_x": {"evidence_id": "ev_x", "direct_quote": "ABCDE"}})
    assert seen["alwf"] is False


def test_wrapper_flips_advisory_judge_error_to_unverified():
    """P1-1: an advisory-kept transport judge_error (is_verified=True, judge_error=True) is FLIPPED."""
    def _base(sentence, pool, *args, **kwargs):
        return _sv(is_verified=True, judge_error=True, sentence=sentence)

    wrapped = aw.make_writer_verify_fn(_base)
    res = wrapped("a claim [#ev:ev_x:0-5]", {"ev_x": {"evidence_id": "ev_x", "direct_quote": "ABCDE"}})
    assert res.is_verified is False
    assert "writer_judge_error_fail_closed" in res.failure_reasons


def test_wrapper_keeps_clean_verified_sentence():
    """A clean, complete, judge_error-free verified sentence passes the wrapper unchanged."""
    quote = "growth rose 5.4 percent overall"
    pool = {"ev_x": {"evidence_id": "ev_x", "direct_quote": quote}}
    tok = ProvenanceToken(evidence_id="ev_x", start=0, end=len(quote), raw=f"[#ev:ev_x:0-{len(quote)}]")

    def _base(sentence, p, *args, **kwargs):
        return _sv(is_verified=True, judge_error=False, sentence=sentence, tokens=[tok])

    wrapped = aw.make_writer_verify_fn(_base)
    res = wrapped(f"growth rose 5.4 percent overall [#ev:ev_x:0-{len(quote)}]", pool)
    assert res.is_verified is True
    assert res.failure_reasons == []


def test_wrapper_completeness_drops_missing_span_numeric():
    """P1-3: a verified sentence that DROPS a substantive span numeric is FAILED (writer_numeric_dropped)."""
    span = "response was 13.0 percent and 27.0 percent"
    pool = {"ev_x": {"evidence_id": "ev_x", "direct_quote": span}}
    sentence = f"response was 13.0 percent [#ev:ev_x:0-{len(span)}]"  # token covers the whole span; 27.0 dropped

    def _base(s, p, *args, **kwargs):
        return _sv(is_verified=True, judge_error=False, sentence=s)

    wrapped = aw.make_writer_verify_fn(_base)
    res = wrapped(sentence, pool)
    assert res.is_verified is False
    assert "writer_numeric_dropped" in res.failure_reasons


def test_wrapper_completeness_passes_when_all_numerics_present():
    span = "response was 13.0 percent and 27.0 percent"
    pool = {"ev_x": {"evidence_id": "ev_x", "direct_quote": span}}
    sentence = f"response was 13.0 percent and 27.0 percent overall [#ev:ev_x:0-{len(span)}]"

    def _base(s, p, *args, **kwargs):
        return _sv(is_verified=True, judge_error=False, sentence=s)

    wrapped = aw.make_writer_verify_fn(_base)
    res = wrapped(sentence, pool)
    assert res.is_verified is True


def test_wrapper_does_not_run_completeness_on_already_failed_sentence():
    """An already-failed sentence is not escalated by the completeness guard (no double-jeopardy)."""
    def _base(s, p, *args, **kwargs):
        return _sv(is_verified=False, reasons=["numeric_mismatch"], sentence=s)

    wrapped = aw.make_writer_verify_fn(_base)
    res = wrapped("anything [#ev:ev_x:0-5]", {"ev_x": {"evidence_id": "ev_x", "direct_quote": "ABCDE"}})
    assert res.is_verified is False
    assert "writer_numeric_dropped" not in res.failure_reasons


# ── fail-closed activation guard (§3.6 / §5.5) ───────────────────────────────────────────────────
def test_activation_guard_passes_under_enforce(monkeypatch):
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    aw.assert_activation_preconditions()  # must not raise


@pytest.mark.parametrize("mode", ["off", "warn"])
def test_activation_guard_raises_off_enforce(monkeypatch, mode):
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", mode)
    with pytest.raises(RuntimeError, match="abort_abstractive_writer_unsafe_activation"):
        aw.assert_activation_preconditions()
