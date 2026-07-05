"""R1_deepener_enable — offline RED->GREEN proof for the citation-snowball deepener UNLOCK + AUTO-TRIGGER.

Proves the FOUR properties the operator-authorized (AskUserQuestion 2026-07-04) unlock must have, WITHOUT
any network / Semantic Scholar / heavy model / GPU (a FAKE deepener is injected; the tier-mix predicate is
pure; the preflight runs offline=True):

  (a) the deepener FLAG is now HONORED — the slate setdefaults PG_SWEEP_EVIDENCE_DEEPENER ON when unset,
      an operator =0 SURVIVES (LAW VI, NOT force-flipped), the flag is OUT of the force-EXACT / REQUIRED-OFF
      / required-truthy kill structures (so force-EXACT can't override the setdefault and the preflight does
      not raise on "1") — this is what makes it a REAL fix, not a bare-setdefault FAKE;
  (b) the unlock is STORM/F2-SCOPED — STORM core / STORM ingest / agentic / legacy-decompose / IterResearch /
      research-planner (F2) STILL raise fail-closed when armed on the clean slate (purity intact for them);
  (c) a discovered paper enters the run_live_retrieval(seed_urls=...) → fetch → tier → strict_verify pass as
      a BARE URL (the adapter attaches no tier / evidence row / trust flag — nothing auto-trusted) and a
      thin/abstract-only deepened paper is DROPPED fail-closed by the SAME is_content_starved chokepoint;
  (d) the auto-trigger FIRES on a REVIEW-HEAVY / PRIMARY-STARVED corpus — the exact task72 pathology
      (corpus_adequacy='proceed', total_uncovered==0, but T1+T2 = 14/182) the value-based borderline gate
      misses — and does NOT fire on a primary-rich corpus.

§-1.3 WEIGHT-and-CONSOLIDATE: the predicate only WIDENS retrieval (decides WHETHER to snowball); it
never filters, demotes, caps, or auto-trusts a source. All thresholds are env-tunable (LAW VI). The FROZEN
faithfulness engine (fetch->classify_source_tier->is_content_starved->strict_verify) is NEVER touched.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import pytest

from scripts.dr_benchmark.run_gate_b import (
    _BENCHMARK_FORCE_EXACT_FLAGS,
    _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS,
    _BENCHMARK_PREFLIGHT_REQUIRED_OFF_FLAGS,
    apply_full_capability_benchmark_slate,
    preflight_full_capability,
)
from src.polaris_graph.retrieval.deepener_sweep_adapter import (
    discovered_urls,
    is_review_heavy_or_primary_starved,
    should_trigger_deepener,
)


@pytest.fixture(autouse=True)
def _isolate_env():
    """Snapshot os.environ before each test and restore it after, so the full-capability slate / a forced
    loser flag never leaks into a sibling test. Compatible with monkeypatch (monkeypatch undoes first at
    teardown, then this fixture restores the pristine snapshot)."""
    snap = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(snap)


# --- shared clean-winners-only slate for the (a)/(b) preflight proofs ------------------------------
# Reproduces the production env JUST BEFORE preflight_full_capability(offline=True): the full-capability
# slate + the programmatic forces run_gate_b_query applies + the COMPLETE required / required-off contract,
# so a negative test isolates exactly the loser under test. Mirrors the proven helper in
# tests/dr_benchmark/test_purity_preflight_gates.py::_apply_clean_winners_only_slate (kept local so this
# test is a SELF-CONTAINED proof of all four properties). offline=True skips ONLY the W4/W5 GPU host probes.
def _clean_winners_only_slate() -> None:
    for _k in (
        "PG_STORM_ENABLED_IN_BENCHMARK", "PG_STORM_INGEST_WEB_RESULTS", "PG_STORM_ENABLED",
        "PG_STORM_OUTLINE_SECTIONS", "PG_STORM_MIN_EFFECTIVE_QUERIES",
        "PG_AGENTIC_SEARCH_IN_BENCHMARK", "PG_SWEEP_EVIDENCE_DEEPENER", "PG_SWEEP_QUERY_DECOMPOSE",
        "PG_QGEN_ITERRESEARCH", "PG_USE_RESEARCH_PLANNER",
    ):
        os.environ.pop(_k, None)
    apply_full_capability_benchmark_slate()
    for _name, _value in {
        "PG_AGENTIC_SEARCH_IN_BENCHMARK": "0",      # loser, force-off (mirrors run_gate_b_query)
        "PG_DEPTH_ANNOTATION_IN_BENCHMARK": "1",
        "PG_NLI_IN_BENCHMARK": "1",
        "PG_USE_SAFETY_REFUSAL": "1",
        "PG_SWEEP_NLI_CONFLICT": "1",
        "PG_BENCHMARK_STRICT_GATES": "1",
        "PG_SWEEP_TABLE_CELL_VERIFY": "1",
        "PG_SECTION_DISTILL": "1",
        "PG_RELEVANCE_SCORER": "semantic_v2",
        "PG_TRAFILATURA_SUBPROCESS": "1",
        "PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY": "1",
    }.items():
        os.environ[_name] = _value
    for _flag in _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS:
        os.environ[_flag] = "1"
    for _flag in _BENCHMARK_PREFLIGHT_REQUIRED_OFF_FLAGS:
        os.environ[_flag] = "0"
    os.environ["PG_STRICT_VERIFY_ENTAILMENT"] = "enforce"


# --- minimal CorpusSource stand-in (title + tier are all the predicate reads) ---------------------
@dataclass
class _Src:
    url: str = ""
    tier: str = ""
    title: str = ""


# --- (i) auto-trigger predicate: the task72 blocked-reference / primary-starved corpus -------------
def test_autotrigger_fires_on_task72_primary_starved_corpus():
    # Real Box-B drb_72 tier mix: 182 sources, T1=12, T2=2 (T1+T2=14, 7.7%), rest T3/T4/T6.
    tier_counts = {"T1": 12, "T2": 2, "T3": 14, "T4": 60, "T6": 94}
    assert sum(tier_counts.values()) == 182
    assert is_review_heavy_or_primary_starved(
        classified_sources=[], tier_counts=tier_counts
    ) is True


def test_autotrigger_does_not_fire_on_primary_rich_corpus():
    # Primary-rich: 100 sources, 55 T1 primaries + 20 T2 reviews => T1+T2 = 75% (not starved), and the
    # T1 fraction (0.55) is above the review-primary ceiling => review-heavy leg is False too.
    tier_counts = {"T1": 55, "T2": 20, "T3": 10, "T6": 15}
    assert is_review_heavy_or_primary_starved(
        classified_sources=[], tier_counts=tier_counts
    ) is False


def test_autotrigger_review_detected_by_title_even_when_mistiered():
    # A systematic review that landed OFF T2 (e.g. mis-tiered T6, like the blocked sciencedirect review)
    # is still counted via its TITLE, so a review-with-thin-primaries corpus still triggers.
    srcs = [
        _Src(url="https://x", tier="T6", title="A Systematic Review and Meta-Analysis of AI Labor"),
    ]
    tier_counts = {"T1": 1, "T6": 30}  # 31 total, T1 frac 0.032 -> thin primaries
    assert is_review_heavy_or_primary_starved(
        classified_sources=srcs, tier_counts=tier_counts
    ) is True


def test_autotrigger_env_tunable_primary_starved_frac(monkeypatch):
    # LAW VI: the starved-fraction threshold is an env knob. At a 0.05 floor, task72's 0.077 no longer
    # trips the primary-starved leg; with T1 high enough the review-heavy leg is also off -> no trigger.
    tier_counts = {"T1": 12, "T2": 2, "T6": 168}  # 182 total, T1+T2 frac 0.077, T1 frac 0.066
    monkeypatch.setenv("PG_DEEPENER_PRIMARY_STARVED_FRAC", "0.05")
    monkeypatch.setenv("PG_DEEPENER_REVIEW_PRIMARY_CEIL", "0.05")  # T1 frac 0.066 > 0.05 -> review leg off
    assert is_review_heavy_or_primary_starved(
        classified_sources=[], tier_counts=tier_counts
    ) is False
    # Default thresholds -> fires.
    monkeypatch.delenv("PG_DEEPENER_PRIMARY_STARVED_FRAC", raising=False)
    monkeypatch.delenv("PG_DEEPENER_REVIEW_PRIMARY_CEIL", raising=False)
    assert is_review_heavy_or_primary_starved(
        classified_sources=[], tier_counts=tier_counts
    ) is True


def test_autotrigger_empty_corpus_is_false():
    assert is_review_heavy_or_primary_starved(classified_sources=None, tier_counts=None) is False
    assert is_review_heavy_or_primary_starved(classified_sources=[], tier_counts={}) is False


# --- (i-b) the auto-trigger OR's into should_trigger_deepener and catches the task72 MISS -----------
def test_should_trigger_catches_proceed_covered_when_review_heavy():
    # The value-based borderline gate alone says NO (proceed + fully covered) — the task72 miss.
    assert should_trigger_deepener(
        flag_on=True, has_s2_key=True, has_seed_evidence=True,
        adequacy_decision="proceed", total_uncovered=0,
    ) is False
    # With the review-heavy / primary-starved auto-trigger, the SAME corpus now deepens.
    assert should_trigger_deepener(
        flag_on=True, has_s2_key=True, has_seed_evidence=True,
        adequacy_decision="proceed", total_uncovered=0, corpus_review_heavy=True,
    ) is True


def test_should_trigger_hard_preconditions_still_bind_with_autotrigger():
    # corpus_review_heavy NEVER bypasses the flag / seed-evidence preconditions (still return False).
    for missing in ("flag_on", "has_seed_evidence"):
        kw = dict(flag_on=True, has_s2_key=True, has_seed_evidence=True,
                  adequacy_decision="proceed", total_uncovered=0, corpus_review_heavy=True)
        kw[missing] = False
        assert should_trigger_deepener(**kw) is False
    # The KEY precondition is FAIL-LOUD (wiring-gap iter-4, Codex REVISE): flag-on + key-absent RAISES
    # naming SEMANTIC_SCHOLAR_API_KEY (the recall lever would be dark), even with corpus_review_heavy=True —
    # corpus_review_heavy still never bypasses the key precondition, but now it fails loud instead of False.
    with pytest.raises(RuntimeError, match="SEMANTIC_SCHOLAR_API_KEY"):
        should_trigger_deepener(
            flag_on=True, has_s2_key=False, has_seed_evidence=True,
            adequacy_decision="proceed", total_uncovered=0, corpus_review_heavy=True,
        )


def test_should_trigger_default_autotrigger_is_backward_compatible():
    # Default corpus_review_heavy=False => byte-identical to the pre-R1 borderline behaviour.
    assert should_trigger_deepener(
        flag_on=True, has_s2_key=True, has_seed_evidence=True,
        adequacy_decision="proceed", total_uncovered=0,
    ) is False
    assert should_trigger_deepener(
        flag_on=True, has_s2_key=True, has_seed_evidence=True,
        adequacy_decision="expand", total_uncovered=0,
    ) is True


# --- (ii) discovered URLs enter the pass as BARE urls — the adapter admits nothing itself ----------
def test_discovered_urls_are_bare_and_not_auto_trusted():
    # The deepener output carries rich metadata; the adapter extracts ONLY the url string. No tier,
    # no evidence row, no "trusted"/"verified" flag crosses the boundary — the sweep must fetch+tier+
    # verify each url. This is what proves "route into the pass, NOT auto-trusted" at the adapter seam.
    deepener_out = {
        "deepened_papers": [
            {"url": "https://primary-rct-1", "title": "RCT", "tier": "T1", "verified": True,
             "abstract": "trust me", "citationCount": 999},
            {"url": "https://primary-rct-2", "title": "Cohort", "tier": "T1"},
        ]
    }
    urls = discovered_urls(deepener_out, cap=20)
    assert urls == ["https://primary-rct-1", "https://primary-rct-2"]
    assert all(isinstance(u, str) for u in urls)  # bare strings — no tier/verified flag survives


# --- (iii) nothing admitted without the frozen gate: thin deepened content DROPPED by the chokepoint
def test_thin_deepened_paper_dropped_by_same_chokepoint():
    from src.polaris_graph.retrieval.live_retriever import is_content_starved

    # A deepened paper that fetches to an abstract-only stub is DROPPED (cannot earn a tier on metadata).
    assert is_content_starved("Short abstract only of a deepened primary study.") is True
    # Substantive fetched full text survives the starvation gate, then earns its tier from
    # classify_source_tier over the FETCHED content — never from the deepener's say-so.
    assert is_content_starved("Substantive primary RCT full text with real prose. " * 30) is False


# --- (a) the deepener FLAG is HONORED — setdefault-ON, operator=0 survives, out of the kill structures
def test_a_deepener_setdefault_on_when_unset():
    # The slate setdefaults the recall lever ON when the operator env carries no value.
    os.environ.pop("PG_SWEEP_EVIDENCE_DEEPENER", None)
    apply_full_capability_benchmark_slate()
    assert os.environ["PG_SWEEP_EVIDENCE_DEEPENER"] == "1"


def test_a_deepener_operator_override_zero_survives():
    # LAW VI: an explicit operator PG_SWEEP_EVIDENCE_DEEPENER=0 is RESPECTED (setdefault, NOT force-flipped
    # to "1"). This is the exact behaviour the old I-cap-005 P1-1 required-truthy note forbade and R1
    # deliberately restores — the deepener SPENDS, so the operator may legitimately run it dark.
    os.environ["PG_SWEEP_EVIDENCE_DEEPENER"] = "0"
    apply_full_capability_benchmark_slate()
    assert os.environ["PG_SWEEP_EVIDENCE_DEEPENER"] == "0"


def test_a_deepener_out_of_all_kill_structures():
    # A force-EXACT entry would flip the value to "0" PAST the setdefault (the "bare setdefault is a FAKE
    # fix" the task warns about); a REQUIRED-OFF entry would RAISE the preflight on "1"; a required-truthy
    # entry would forbid an operator =0. The deepener must be out of ALL THREE for the unlock to be real.
    assert "PG_SWEEP_EVIDENCE_DEEPENER" not in _BENCHMARK_FORCE_EXACT_FLAGS
    assert "PG_SWEEP_EVIDENCE_DEEPENER" not in _BENCHMARK_PREFLIGHT_REQUIRED_OFF_FLAGS
    assert "PG_SWEEP_EVIDENCE_DEEPENER" not in _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS


def test_a_preflight_does_not_raise_with_deepener_on():
    # End-to-end: on the clean winners-only slate the deepener resolves ON and the offline preflight
    # PASSES — "1" is now a VALID value, not a re-armed-loser dropped-pin.
    _clean_winners_only_slate()
    assert os.environ["PG_SWEEP_EVIDENCE_DEEPENER"] == "1"
    preflight_full_capability(offline=True)  # must NOT raise


# --- (b) the unlock is STORM/F2-SCOPED — every OTHER killed loser STILL raises fail-closed when armed --
_OTHER_LOSERS_STILL_KILLED: tuple[str, ...] = (
    "PG_STORM_ENABLED_IN_BENCHMARK",   # STORM (L6) core — the loser the operator saw fire
    "PG_STORM_INGEST_WEB_RESULTS",     # STORM seed-URL ingest lane
    "PG_AGENTIC_SEARCH_IN_BENCHMARK",  # agentic URL-discovery (STORM's twin)
    "PG_SWEEP_QUERY_DECOMPOSE",        # legacy q1d decompose
    "PG_QGEN_ITERRESEARCH",            # IterResearch driver (superseded by FS-Researcher)
    "PG_USE_RESEARCH_PLANNER",         # F2 (L12) legacy facet planner
)


@pytest.mark.parametrize("loser_env", _OTHER_LOSERS_STILL_KILLED, ids=list(_OTHER_LOSERS_STILL_KILLED))
def test_b_other_losers_still_raise_when_armed(loser_env):
    # Arm exactly ONE other loser on top of the clean (deepener-ON) slate; the preflight must FAIL CLOSED
    # naming it. Proves the operator-authorized unlock is deepener-scoped: STORM/F2/etc. stay killed AND
    # the deepener being ON does NOT itself trip the gate (the only raise is the armed loser).
    _clean_winners_only_slate()
    assert os.environ["PG_SWEEP_EVIDENCE_DEEPENER"] == "1"  # unlocked lever ON, and yet...
    os.environ[loser_env] = "1"
    with pytest.raises(RuntimeError) as exc:
        preflight_full_capability(offline=True)
    assert loser_env.lower() in str(exc.value).lower(), (
        f"the NO-LOSER gate raised but did not name the armed loser {loser_env!r}: {str(exc.value)[:200]}"
    )


# --- wiring-gap iter-5 (Codex REVISE P1): the run_one_query deepener FLAG PARSER -------------------
# The evidence-deepener gate in scripts/run_honest_sweep_r3.run_one_query parses PG_SWEEP_EVIDENCE_DEEPENER
# into the `flag_on` it feeds should_trigger_deepener(). Iter-4 shipped the fail-loud raise at that
# chokepoint, but the flag was parsed inline with `.strip() in ("1", "true", "True")` — which does NOT accept
# the case-insensitive on/yes the rest of the codebase honours (_TRUE_TOKENS). So PG_SWEEP_EVIDENCE_DEEPENER=on
# (or =yes) + an absent SEMANTIC_SCHOLAR_API_KEY parsed flag_on=False and the chokepoint NEVER raised — the
# recall lever stayed silently DARK on a paid run instead of failing loud (LAW II). Iter-5 normalises the
# parse to the canonical _env_flag helper. These regressions are keyless (SEMANTIC_SCHOLAR_API_KEY unset) and
# spend-free (no LLM, no net) and lock BOTH the parse convention AND the composed run_one_query-gate behaviour.
def test_deepener_flag_parser_honours_on_yes_case_insensitively(monkeypatch):
    from scripts.run_honest_sweep_r3 import _env_flag
    # Values the OLD `.strip() in ("1", "true", "True")` parser WRONGLY rejected (on/yes and any casing), plus
    # the ones it accepted — all must parse truthy through the canonical PG-truthy convention now.
    for raw in ("on", "yes", "ON", "Yes", "On", "YES", "1", "true", "TRUE", "  on  "):
        monkeypatch.setenv("PG_SWEEP_EVIDENCE_DEEPENER", raw)
        assert _env_flag("PG_SWEEP_EVIDENCE_DEEPENER", default=False) is True, raw
    for raw in ("0", "false", "no", "off", ""):
        monkeypatch.setenv("PG_SWEEP_EVIDENCE_DEEPENER", raw)
        assert _env_flag("PG_SWEEP_EVIDENCE_DEEPENER", default=False) is False, raw
    monkeypatch.delenv("PG_SWEEP_EVIDENCE_DEEPENER", raising=False)
    assert _env_flag("PG_SWEEP_EVIDENCE_DEEPENER", default=False) is False   # unset -> off (byte-identical)


def test_run_one_query_deepener_gate_raises_on_yes_flag_with_absent_key(monkeypatch):
    # Reproduce the run_one_query deepener gate EXACTLY: flag_on via the same _env_flag call the fixed line
    # 10493 uses; has_s2_key via the same bool(os.getenv(...).strip()) expression line 10494 uses; then the
    # should_trigger_deepener() chokepoint. Keyless: SEMANTIC_SCHOLAR_API_KEY absent. Proves =on and =yes now
    # reach the FAIL-LOUD raise naming SEMANTIC_SCHOLAR_API_KEY (before the fix they parsed flag_on=False ->
    # silent no-raise -> dark recall lever on a paid run).
    from scripts.run_honest_sweep_r3 import _env_flag
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    for raw in ("on", "yes"):
        monkeypatch.setenv("PG_SWEEP_EVIDENCE_DEEPENER", raw)
        flag_on = _env_flag("PG_SWEEP_EVIDENCE_DEEPENER", default=False)         # == run_one_query line 10493
        has_s2_key = bool(os.getenv("SEMANTIC_SCHOLAR_API_KEY", "").strip())     # == run_one_query line 10494
        assert flag_on is True and has_s2_key is False
        with pytest.raises(RuntimeError, match="SEMANTIC_SCHOLAR_API_KEY"):
            should_trigger_deepener(
                flag_on=flag_on, has_s2_key=has_s2_key, has_seed_evidence=True,
                adequacy_decision="proceed", total_uncovered=0, corpus_review_heavy=True,
            )
    # Flag OFF/unset + absent key must NOT raise (nothing enabled -> a missing key is not an error).
    monkeypatch.delenv("PG_SWEEP_EVIDENCE_DEEPENER", raising=False)
    flag_off = _env_flag("PG_SWEEP_EVIDENCE_DEEPENER", default=False)
    assert flag_off is False
    assert should_trigger_deepener(
        flag_on=flag_off, has_s2_key=False, has_seed_evidence=True,
        adequacy_decision="expand", total_uncovered=2,
    ) is False


def test_run_one_query_deepener_flag_uses_convention_not_legacy_parse():
    # Fail-before / pass-after GUARD on the exact call site Codex flagged (run_honest_sweep_r3.py:10493). The
    # 2400-line async run_one_query cannot be unit-driven keyless/spend-free, so lock the parse at the source:
    # the legacy `.strip() in ("1", "true", "True")` (which rejects on/yes) must be GONE from run_one_query,
    # replaced by the canonical _env_flag(...) parse for PG_SWEEP_EVIDENCE_DEEPENER.
    import inspect
    from scripts.run_honest_sweep_r3 import run_one_query
    src = inspect.getsource(run_one_query)
    assert 'PG_SWEEP_EVIDENCE_DEEPENER", "0").strip() in ("1", "true", "True")' not in src   # legacy parse gone
    assert '_env_flag("PG_SWEEP_EVIDENCE_DEEPENER"' in src                                    # convention in
