"""B5/B7 (DUAL_AGREED_PLAN, operator-locked 2026-06-14) — VERIFY = LABEL, NEVER HOLD.

Proves the four lane fixes WITHOUT relaxing any faithfulness gate:

1. PG_ALWAYS_RELEASE default is now ON; the OFF switch is an EXPLICIT off token (byte-identical
   legacy regression). A typo/unrecognized value resolves to the default ON (never silently holds).
2. strict_verify drop DISPOSITION classifier: un-provenanced -> hard drop; provenanced-but-failed
   -> support-failed DISCLOSED (count only, never the raw sentence text). The disclosure builder
   surfaces counts + reasons, NEVER the hallucinated sentence text.
3. FABRICATED narrowing is coupled to redaction (tested in test_iperm001_release.py).
4. Side-judge fail-soft labels (conflict/credibility) tested at the runner integration layer; here
   we lock the pure release-policy + classifier units.
"""

from __future__ import annotations

import pytest

from src.polaris_graph.generator.provenance_generator import (
    DROP_DISPOSITION_SUPPORT_FAILED,
    DROP_DISPOSITION_UNPROVENANCED,
    SentenceVerification,
    build_drop_disclosure,
    classify_drop_disposition,
)
from src.polaris_graph.roles.release_policy import always_release_enabled


# ── Fix #1: PG_ALWAYS_RELEASE default ON ─────────────────────────────────────


def test_always_release_default_is_on(monkeypatch):
    """Unset -> ON (the new production default: nothing shall hold the report)."""
    monkeypatch.delenv("PG_ALWAYS_RELEASE", raising=False)
    assert always_release_enabled() is True


@pytest.mark.parametrize("token", ["0", "false", "no", "off", "FALSE", "  Off  "])
def test_explicit_off_token_disables(monkeypatch, token):
    """The OFF switch is retained for the byte-identical legacy regression."""
    monkeypatch.setenv("PG_ALWAYS_RELEASE", token)
    assert always_release_enabled() is False


@pytest.mark.parametrize("token", ["1", "true", "yes", "on", "garbage", "maybe", "", "   "])
def test_on_or_unrecognized_resolves_to_on(monkeypatch, token):
    """ON tokens AND unrecognized typos AND EMPTY/whitespace resolve to ON — a default-ON flag must
    never SILENTLY withhold a report on an unset/empty/stray value (Codex diff-gate P1: empty string
    is NOT an off-token; only the explicit '0'/'false'/'no'/'off' tokens hold). Legacy callers pass
    '0' or always_release=False, never an empty string."""
    monkeypatch.setenv("PG_ALWAYS_RELEASE", token)
    assert always_release_enabled() is True


# ── Fix #2: strict_verify drop disposition + disclosure ──────────────────────


def _sv(reasons):
    return SentenceVerification(
        sentence="x", tokens=[], is_verified=False, failure_reasons=list(reasons),
    )


@pytest.mark.parametrize("reason", ["no_provenance_token", "empty_or_contentless_sentence"])
def test_unprovenanced_reasons_are_hard_drop(reason):
    assert classify_drop_disposition(_sv([reason])) == DROP_DISPOSITION_UNPROVENANCED


@pytest.mark.parametrize(
    "reason",
    [
        "numeric_mismatch",
        "overlap_too_low",
        "entailment_failed",
        "invalid_token",
        "span_out_of_range",
        "entailment_judge_error_fail_closed",
        "calc_mixed_with_ev_token",
    ],
)
def test_support_failed_reasons_are_disclosed_not_hard_dropped(reason):
    """A provenanced-but-failed sentence is the 'unsupported/contradicted by source' class — it must
    be DISCLOSED (so it is never SILENTLY deleted), distinct from a hygiene un-provenanced drop."""
    assert classify_drop_disposition(_sv([reason])) == DROP_DISPOSITION_SUPPORT_FAILED


def test_mixed_reasons_route_to_support_failed():
    """ANY support-grounding failure alongside an un-provenanced reason -> the stricter disclosed
    bucket (a real claim that failed verification is never demoted to a silent hygiene drop)."""
    assert (
        classify_drop_disposition(_sv(["no_provenance_token", "numeric_mismatch"]))
        == DROP_DISPOSITION_SUPPORT_FAILED
    )


def test_no_failure_reasons_fail_safe_to_support_failed():
    """A dropped sentence with NO reasons fails SAFE to the disclosed bucket — never silently nothing."""
    assert classify_drop_disposition(_sv([])) == DROP_DISPOSITION_SUPPORT_FAILED


def test_build_drop_disclosure_counts_and_never_leaks_text():
    """The disclosure carries COUNTS + reason tallies — NEVER the raw dropped sentence text (a
    generator-hallucinated / unsupported sentence must not ship as prose under any label)."""
    dropped = [
        SentenceVerification(
            sentence="Mortality fell 117% (hallucinated).",
            tokens=[], is_verified=False, failure_reasons=["numeric_mismatch"],
        ),
        SentenceVerification(
            sentence="The drug is contraindicated [#ev:e1:0-9].",
            tokens=[], is_verified=False, failure_reasons=["entailment_failed"],
        ),
        SentenceVerification(
            sentence="[#ev:e2:0-3]",
            tokens=[], is_verified=False, failure_reasons=["no_provenance_token"],
        ),
    ]
    out = build_drop_disclosure(dropped)
    assert out["support_failed_count"] == 2
    assert out["unprovenanced_count"] == 1
    # Reasons are SPLIT by disposition (Codex diff-gate P2): the support-failed reason tally
    # matches the support-failed count and never conflates the un-provenanced hygiene reason.
    assert out["support_failed_reason_counts"] == {
        "numeric_mismatch": 1, "entailment_failed": 1,
    }
    assert out["unprovenanced_reason_counts"] == {"no_provenance_token": 1}
    # CRITICAL: the disclosure is a dict of counts only — no sentence text anywhere in it.
    blob = repr(out)
    assert "hallucinated" not in blob
    assert "contraindicated" not in blob


def test_build_drop_disclosure_empty_when_no_drops():
    out = build_drop_disclosure([])
    assert out["support_failed_count"] == 0
    assert out["unprovenanced_count"] == 0
    assert out["support_failed_reason_counts"] == {}
    assert out["unprovenanced_reason_counts"] == {}
