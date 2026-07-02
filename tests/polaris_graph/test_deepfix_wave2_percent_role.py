"""I-deepfix-001 (Wave-2) — numeric PERCENT-ROLE re-check in strict_verify.

A printed percent ("15%", "15 percent") is a PERCENT claim: it must be grounded
by a cited span that carries that SAME value AS A PERCENT — not merely as a bare
digit that coincidentally equals the value (a page number "p. 15", a year "2015",
a plain count "15"). The pre-fix bare-number checks pass "rose 15%" against a span
containing "... p. 15" because "15" is in the number union; that is a role
confusion that can ship a wrong percentage. The fix adds a STRICTLY ADDITIVE,
faithfulness-TIGHTENING gate (env PG_PROVENANCE_PERCENT_ROLE_MATCH, default-ON)
in BOTH the production ``provenance_generator`` verifier / corroborator filter and
the clinical ``strict_verify`` — it only ADDS a drop, never rescues/relaxes an
existing check.

Each fix has a FORCED-POSITIVE (inject the exact bad case; assert it drops) and a
NEGATIVE-CONTROL (a legitimate matching-percent case; assert it is NOT touched).
The kill-switch-off tests reproduce the pre-fix LEAK, proving default-off is
byte-identical to the legacy behavior. These are offline LOGIC tests (no
GPU/network/LLM); a fresh render validates the wiring later.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.generator.provenance_generator import (
    _percent_role_match_enabled,
    _percents_in,
    corroborator_span_grounds_sentence,
    verify_sentence_provenance,
)


# ── the percent-role extractor (shared helper) ───────────────────────────────

def test_percents_in_extracts_percent_role_not_bare_digits():
    # "%" and "percent" both count; a bare digit / year / page number does NOT.
    text = "revenue rose 14% during 2015 reported on p. 15 and up 9 percent later"
    assert _percents_in(text) == {"14", "9"}
    # a probability like 0.15 is not a printed percent
    assert _percents_in("odds were 0.15 overall") == set()
    # representation-agnostic: "15 percent" reads the SAME as "15%"
    assert _percents_in("grew 15 percent") == _percents_in("grew 15%") == {"15"}


def test_flag_default_on_and_off(monkeypatch):
    monkeypatch.delenv("PG_PROVENANCE_PERCENT_ROLE_MATCH", raising=False)
    assert _percent_role_match_enabled() is True
    monkeypatch.setenv("PG_PROVENANCE_PERCENT_ROLE_MATCH", "0")
    assert _percent_role_match_enabled() is False


# ── verify_sentence_provenance: the numeric percent-role gate ─────────────────
#
# The span carries a DIFFERENT percent ("14%") plus the bare digit 15 twice
# ("in 2015", "p. 15"). The legacy bare-number integer check passes "15%" because
# "15" is in the span's number union; the percent-role gate catches that "15" is
# never present AS A PERCENT.

_SPAN = "Revenue rose 14% during the fiscal period reported in 2015 on p. 15."
_POOL = {"evA": {"direct_quote": _SPAN, "statement": "revenue note"}}
_END = len(_SPAN)


def test_forced_positive_wrong_percent_drops():
    """FORCED-POSITIVE: 'rose 15%' cited to a span with '14%' + bare '15' DROPS."""
    sentence = f"Revenue rose 15% [#ev:evA:0-{_END}]."
    v = verify_sentence_provenance(sentence, _POOL)
    assert v.is_verified is False, v.failure_reasons
    assert any(
        str(r).startswith("percent_not_in_cited_span") for r in v.failure_reasons
    ), v.failure_reasons
    # the specific missing percent value is reported
    assert any("15" in str(r) for r in v.failure_reasons
               if str(r).startswith("percent_not_in_cited_span")), v.failure_reasons


def test_negative_control_matching_percent_kept():
    """NEGATIVE-CONTROL: 'rose 14%' cited to the SAME span is KEPT (14% is present
    AS A PERCENT). The legitimate percent claim is never touched by the gate."""
    sentence = f"Revenue rose 14% [#ev:evA:0-{_END}]."
    v = verify_sentence_provenance(sentence, _POOL)
    assert v.is_verified is True, v.failure_reasons
    assert not any(
        str(r).startswith("percent_not_in_cited_span") for r in v.failure_reasons
    ), v.failure_reasons


def test_kill_switch_off_reproduces_legacy_leak(monkeypatch):
    """PG_PROVENANCE_PERCENT_ROLE_MATCH=0 => the SAME forced-positive input PASSES
    (byte-identical to the pre-fix behavior). This documents the leak the default-on
    gate closes and proves the OFF path is a no-op."""
    monkeypatch.setenv("PG_PROVENANCE_PERCENT_ROLE_MATCH", "0")
    sentence = f"Revenue rose 15% [#ev:evA:0-{_END}]."
    v = verify_sentence_provenance(sentence, _POOL)
    assert v.is_verified is True, (
        "with the gate OFF the legacy bare-number check passes '15%' on a 'p. 15' "
        f"digit — the leak. failure_reasons={v.failure_reasons}"
    )


# ── corroborator_span_grounds_sentence: the same gate on the numeric path ─────
#
# The claim shares exactly ONE content word ("revenue") with the corroborator span
# (below the >=2 lexical floor), so grounding falls to the NUMERIC path. The span
# carries a different percent ("14%") plus the bare digit 15 ("page 15"): the
# legacy integer-subset path grounds it on "15"; the percent-role gate detaches it.

_CORROB_SPAN = "Revenue climbed 14% as shown on page 15 of the annual filing."


def test_corroborator_forced_positive_wrong_percent_detaches():
    """FORCED-POSITIVE: a numeric-only corroborator whose span lacks the claim's
    printed percent (15%) is DETACHED (returns False)."""
    claim = "Revenue rose 15% this year"
    assert corroborator_span_grounds_sentence(claim, _CORROB_SPAN) is False


def test_corroborator_negative_control_matching_percent_grounds():
    """NEGATIVE-CONTROL: the corroborator carries the claim's percent (14%) AS A
    PERCENT, so it still grounds (returns True) — genuine multi-citation preserved."""
    claim = "Revenue rose 14% this year"
    assert corroborator_span_grounds_sentence(claim, _CORROB_SPAN) is True


def test_corroborator_kill_switch_off_reproduces_leak(monkeypatch):
    """With the gate OFF the wrong-percent corroborator is grounded on the bare
    '15' (page number) — the mis-attribution leak; default-off is byte-identical."""
    monkeypatch.setenv("PG_PROVENANCE_PERCENT_ROLE_MATCH", "0")
    claim = "Revenue rose 15% this year"
    assert corroborator_span_grounds_sentence(claim, _CORROB_SPAN) is True


# ── clinical strict_verify parity ────────────────────────────────────────────

from datetime import datetime, timezone  # noqa: E402

from src.polaris_graph.clinical_generator.strict_verify import (  # noqa: E402
    verify_sentence,
)
from src.polaris_graph.clinical_retrieval.evidence_pool import (  # noqa: E402
    AdequacyVerdict,
    EvidencePool,
    Source,
    SourceTier,
)


def _clinical_pool(full_text: str) -> EvidencePool:
    src = Source(
        url="https://www.cochrane.org/CD001",
        domain="cochrane.org",
        tier=SourceTier.T1,
        title="Source",
        snippet="snippet",
        full_text=full_text,
        full_text_available=True,
        source_id="src-1",
    )
    return EvidencePool(
        decision_id="dec-1",
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


_CLIN_TEXT = (
    "The trial reported an event rate of 14% in the treatment arm during 2015, "
    "as detailed on page 15 of the supplement."
)


def test_clinical_forced_positive_wrong_percent_drops():
    """FORCED-POSITIVE (clinical): sentence claims '15%' but the span only carries
    '14%' AS A PERCENT (plus bare '15' on 'page 15'); it DROPS with the new reason."""
    pool = _clinical_pool(_CLIN_TEXT)
    passed, reason = verify_sentence(
        f"The treatment arm showed an event rate of 15% [#ev:src-1:0-{len(_CLIN_TEXT)}].",
        pool,
    )
    assert passed is False
    assert reason == "percent_not_in_cited_span"


def test_clinical_negative_control_matching_percent_kept():
    """NEGATIVE-CONTROL (clinical): the matching-percent claim (14%) is KEPT."""
    pool = _clinical_pool(_CLIN_TEXT)
    passed, reason = verify_sentence(
        f"The treatment arm showed an event rate of 14% [#ev:src-1:0-{len(_CLIN_TEXT)}].",
        pool,
    )
    assert passed is True, f"expected pass, got reason={reason}"


def test_clinical_kill_switch_off_reproduces_leak(monkeypatch):
    """With the gate OFF the clinical verifier passes '15%' on the bare 'page 15'
    digit (legacy leak); default-off is byte-identical."""
    monkeypatch.setenv("PG_PROVENANCE_PERCENT_ROLE_MATCH", "0")
    pool = _clinical_pool(_CLIN_TEXT)
    passed, reason = verify_sentence(
        f"The treatment arm showed an event rate of 15% [#ev:src-1:0-{len(_CLIN_TEXT)}].",
        pool,
    )
    assert passed is True, f"expected legacy pass with gate off, got reason={reason}"
