"""I-deepfix-001 D5 (#1344) — the credibility/tier SILENT-DEGRADE gap.

§-1.3: source credibility / tier is a WEIGHT (T1-T7), NEVER a hard gate — so a GLM-tiering
failure must NOT abort the run; the deterministic rules-floor tiers every source. THE BUG
the diced map surfaced: on a mirror blank-200 / trickle storm the GLM tiering degrades to
the rules-floor for EVERY source (``llm_success == 0``), but the post-exec status could
FALSELY read as "tiered via GLM" — a §-1.3 "completes-not-claims" violation. The fix makes
``classify_sources_llm_tiering`` carry an HONEST machine-readable status
(``tiering_mode`` + counts) so a 100%-rules-floor batch is reported as
``rules_floor_degraded``, NEVER as ``tiered_via_glm``, with a LOUD warning — and STILL drops
zero sources (it is a weight).

These tests are OFFLINE + spend-free: the LLM call is dependency-injected, so no network,
no model, no judge. NO ``unittest.mock`` (CLAUDE.md §9.4) — the injected callers are plain
functions. Faithfulness-NEUTRAL: nothing here touches strict_verify / NLI / D8 / provenance.
"""
from __future__ import annotations

import logging

from src.polaris_graph.retrieval.credibility_llm_tiering import (
    _VALID_TIERING_MODES,
    TieringBatchResult,
    _resolve_tiering_mode,
    classify_sources_llm_tiering,
)
from src.polaris_graph.retrieval.tier_classifier import (
    ClassificationSignals,
    TierLevel,
)


# ─────────────────────────────────────────────────────────────────────────────
# Injected LLM callers (offline, deterministic)
# ─────────────────────────────────────────────────────────────────────────────

def _all_error_call_llm(prompt: str) -> str:
    """Every GLM tiering call RAISES — the blank-200 / trickle-storm failure mode.
    ``llm_tier_one`` absorbs the exception and degrades the source to the rules-floor."""
    raise RuntimeError("simulated blank-200 / judge_error — GLM tiering unavailable")


def _all_ok_call_llm(prompt: str) -> str:
    """Every call returns a valid in-scheme tier — GLM tiered every source."""
    return '{"tier": "T1", "rationale": "peer-reviewed primary study venue"}'


def _good_for_marked_call_llm(prompt: str) -> str:
    """Valid tier when the prompt carries a 'good' source URL; raises otherwise — a
    deterministic MIX so the batch lands on ``partial``."""
    if "good-source" in prompt:
        return '{"tier": "T2", "rationale": "systematic review venue"}'
    raise RuntimeError("simulated judge_error for the bad source")


def _signals(n: int, *, prefix: str = "src") -> list[ClassificationSignals]:
    """N non-retracted sources with real URLs the rules-floor can classify (retracted
    sources are intentionally never positively GLM-tiered, so they are excluded here)."""
    return [
        ClassificationSignals(
            url=f"https://{prefix}-{i}.example.com/article",
            title=f"Source {i}",
            fetched_content_length=5000,
        )
        for i in range(n)
    ]


# ─────────────────────────────────────────────────────────────────────────────
# THE D5 BUG: all-error GLM -> rules_floor_degraded, 0 dropped, NOT tiered_via_glm
# ─────────────────────────────────────────────────────────────────────────────

def test_all_error_reports_rules_floor_degraded_zero_dropped(monkeypatch, caplog):
    """Inject an all-error ``call_llm``: every GLM tiering call fails. The batch MUST report
    ``tiering_mode == rules_floor_degraded`` (NOT ``tiered_via_glm``), drop ZERO sources,
    keep every source at a rules-floor tier, and emit a LOUD (WARNING) disclosure."""
    # Disable the consecutive-fallback circuit-breaker so EVERY source is attempted and the
    # counts are deterministic (with N=5 < default breaker 8 it would not trip anyway).
    monkeypatch.setenv("PG_TIER_LLM_DEGRADE_AFTER", "0")
    monkeypatch.setenv("PG_TIER_LLM_BATCH_WALL_SECONDS", "0")  # no wall — attempt all

    signals = _signals(5)
    status_out: dict = {}

    with caplog.at_level(logging.WARNING, logger="src.polaris_graph.retrieval.credibility_llm_tiering"):
        out = classify_sources_llm_tiering(
            signals, call_llm=_all_error_call_llm, status_out=status_out,
        )

    # The result CARRIES an honest machine-readable status.
    assert isinstance(out, TieringBatchResult)
    assert out.tiering_status is not None
    mode = out.tiering_status["tiering_mode"]

    # The core §-1.3 fix: 100%-rules-floor is reported HONESTLY as rules_floor_degraded ...
    assert mode == "rules_floor_degraded"
    # ... and NEVER as the false-positive "tiered_via_glm".
    assert mode != "tiered_via_glm"

    # ZERO sources dropped — tier is a WEIGHT (len preserved 1:1 with the input).
    assert len(out) == len(signals)

    # Every source carries a real rules-floor tier (a valid TierLevel) and NONE came from
    # the GLM path (no result is tagged with the 'llm_tiering' matched-rule).
    for res in out:
        assert isinstance(res.tier, TierLevel)
        assert "llm_tiering" not in res.matched_rules

    # Honest counts: GLM tiered nothing; every source is on the rules-floor.
    assert out.tiering_status["llm_success_count"] == 0
    assert out.tiering_status["total"] == len(signals)
    assert out.tiering_status["rules_floor_count"] == len(signals)
    # The all-error caller raises -> llm_tier_one absorbs it -> FALLBACK (not ERROR).
    assert out.tiering_status["fallback_count"] == len(signals)
    assert out.tiering_status["error_count"] == 0

    # The optional explicit status channel is populated identically.
    assert status_out == out.tiering_status

    # A LOUD warning was emitted (DISCLOSED, never silent) naming the degrade mode.
    degraded_warnings = [
        r for r in caplog.records
        if r.levelno >= logging.WARNING and "rules_floor_degraded" in r.getMessage()
    ]
    assert degraded_warnings, "expected a LOUD WARNING disclosing the rules_floor_degraded degrade"


# ─────────────────────────────────────────────────────────────────────────────
# Healthy + partial paths: the honest status discriminates
# ─────────────────────────────────────────────────────────────────────────────

def test_all_success_reports_tiered_via_glm(monkeypatch):
    """When every GLM call returns a valid tier, the mode is ``tiered_via_glm`` and every
    result is a GLM result — the honest positive case the degraded case must be distinct from."""
    monkeypatch.setenv("PG_TIER_LLM_DEGRADE_AFTER", "0")
    monkeypatch.setenv("PG_TIER_LLM_BATCH_WALL_SECONDS", "0")

    signals = _signals(4)
    out = classify_sources_llm_tiering(signals, call_llm=_all_ok_call_llm)

    assert out.tiering_status["tiering_mode"] == "tiered_via_glm"
    assert out.tiering_status["llm_success_count"] == len(signals)
    assert out.tiering_status["rules_floor_count"] == 0
    assert len(out) == len(signals)
    for res in out:
        assert res.matched_rules == ["llm_tiering"]
        assert res.tier == TierLevel.T1


def test_mixed_reports_partial(monkeypatch):
    """A deterministic MIX (some GLM successes, some fallbacks) lands on ``partial`` — never
    over-claimed as ``tiered_via_glm``, never falsely ``rules_floor_degraded``."""
    monkeypatch.setenv("PG_TIER_LLM_DEGRADE_AFTER", "0")  # attempt all (no circuit-break)
    monkeypatch.setenv("PG_TIER_LLM_BATCH_WALL_SECONDS", "0")

    good = _signals(2, prefix="good-source")
    bad = _signals(2, prefix="bad-source")
    signals = [good[0], bad[0], good[1], bad[1]]

    out = classify_sources_llm_tiering(signals, call_llm=_good_for_marked_call_llm)

    assert out.tiering_status["tiering_mode"] == "partial"
    assert out.tiering_status["llm_success_count"] == 2
    assert out.tiering_status["rules_floor_count"] == 2
    assert out.tiering_status["total"] == 4
    assert len(out) == len(signals)


def test_empty_corpus_is_vacuous_not_degraded():
    """An empty corpus tiers nothing — it must NOT raise the ``rules_floor_degraded`` alarm
    (the corpus-zero floor is a separate adequacy gate). Vacuous => not degraded."""
    out = classify_sources_llm_tiering([])
    assert isinstance(out, TieringBatchResult)
    assert len(out) == 0
    assert out.tiering_status["tiering_mode"] != "rules_floor_degraded"
    assert out.tiering_status["total"] == 0
    assert out.tiering_status["rules_floor_count"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# The mode resolver itself (pure)
# ─────────────────────────────────────────────────────────────────────────────

def test_resolve_tiering_mode_boundaries():
    """Pure-function teeth: the exact boundary that the §-1.3 false-positive lived on."""
    assert _resolve_tiering_mode(0, 200) == "rules_floor_degraded"   # the bug case
    assert _resolve_tiering_mode(200, 200) == "tiered_via_glm"
    assert _resolve_tiering_mode(1, 200) == "partial"
    assert _resolve_tiering_mode(199, 200) == "partial"
    assert _resolve_tiering_mode(0, 0) == "tiered_via_glm"           # vacuous empty
    # Every resolved mode is a member of the published contract set (no off-scheme label).
    for _success, _total in ((0, 200), (200, 200), (1, 200), (0, 0)):
        assert _resolve_tiering_mode(_success, _total) in _VALID_TIERING_MODES
