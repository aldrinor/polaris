"""I-meta-005 Phase 5 (#989) smoke — finding-dedup + relevance-floor corpus.

Cases P5-1..P5-9 (+ P5-3b) from the Codex-APPROVED brief
`.codex/I-meta-005-phase-5/brief.md` §5. SPEND-FREE: pure CPU clustering +
selection; no network, no LLM. Plain-class fixtures — NO unittest.mock.

The sweep-level cases (P5-10 gate-before-dedup ordering, P5-11 floor fail-loud)
live with the sweep wiring; this module pins the pure `finding_dedup` +
`evidence_selector` relevance-floor behaviour.

Serialized per CLAUDE.md §8.4 (pure-python).
"""
from __future__ import annotations

import pytest

from src.polaris_graph.authority.data_loader import load_authority_data
from src.polaris_graph.retrieval.evidence_selector import (
    parse_relevance_floor,
    select_evidence_for_generation,
)
from src.polaris_graph.synthesis.finding_dedup import (
    _host_of,
    dedup_by_finding,
)

_GOV = load_authority_data()["psl_gov_suffixes"]


def _row(eid, url, quote, *, authority=0.5, tier="T1"):
    """A live-shaped evidence row carrying the fields the dedup + selector read.

    NOTE: `selection_relevance` is deliberately NOT set here — it is a sidecar the
    SELECTOR stamps in relevance-floor mode; the dedup representative pick falls
    back to `authority_score` when it is absent.
    """
    return {
        "evidence_id": eid,
        "source_url": url,
        "url": url,
        "direct_quote": quote,
        "statement": quote,
        "tier": tier,
        "authority_score": authority,
    }


# Clinical quotes VERIFIED to extract via contradiction_detector.
_WL72 = "Tirzepatide produced a mean weight loss of 20.9% at week 72."
_WL72_B = "Tirzepatide achieved a mean weight loss of 20.9% at week 72."
_WL20 = "Tirzepatide produced a mean weight loss of 20.9% at week 20."


# ── P5-2 collapse rehashes from independent hosts ────────────────────────────

def test_p5_2_collapse_rehashes_three_independent_hosts():
    rows = [
        _row("ev0", "https://nejm.org/a", _WL72, authority=0.9),
        _row("ev1", "https://thelancet.com/b", _WL72, authority=0.7),
        _row("ev2", "https://nih.gov/c", _WL72, authority=0.6),
    ]
    res = dedup_by_finding(rows, gov_suffixes=_GOV)
    assert res.distinct_finding_count == 1
    assert len(res.deduped_rows) == 1
    rep = res.deduped_rows[0]
    assert rep["evidence_id"] == "ev0"            # highest authority -> rep
    assert rep["corroboration_count"] == 3        # 3 independent registrable domains
    assert rep["independent_hosts"] == ["nejm.org", "nih.gov", "thelancet.com"]
    assert res.collapsed_row_count == 2


# ── P5-3 NO unique-claim loss (clinical-lethal) ──────────────────────────────

def test_p5_3_different_endpoint_stays_separate():
    rows = [
        _row("ev0", "https://a.org/x", _WL72),
        _row("ev1", "https://b.org/y", _WL20),   # same value, DIFFERENT endpoint
    ]
    res = dedup_by_finding(rows, gov_suffixes=_GOV)
    assert res.distinct_finding_count == 2
    assert len(res.deduped_rows) == 2             # both findings survive


def test_p5_3_unknown_subject_never_merges():
    # A quote whose numeric subject the extractor cannot resolve must never merge
    # with another unknown-subject row, even with identical numbers.
    q = "A mean reduction of 20.9% at week 72 was observed."
    rows = [
        _row("ev0", "https://a.org/x", q),
        _row("ev1", "https://b.org/y", q),
    ]
    res = dedup_by_finding(rows, gov_suffixes=_GOV)
    # Either no numeric finding extracts (qualitative singletons) OR the unknown
    # subject forces per-claim singletons. Both keep BOTH rows -> never merged.
    assert len(res.deduped_rows) == 2


# ── P5-3b multi-claim row retention (defensive / future-proof) ───────────────

def test_p5_3b_multi_claim_row_retained_via_helper():
    # The clinical extractor currently emits <=1 claim/row, so we validate the
    # retention rule at the dedup level: a row that is the representative of its
    # OWN finding is always kept even when it shares another finding with a
    # higher-authority row. Two rows, one shared finding: the lower-authority row
    # is collapsed; the higher-authority rep survives carrying the finding.
    rows = [
        _row("ev_hi", "https://a.org/x", _WL72, authority=0.9),
        _row("ev_lo", "https://b.org/y", _WL72_B, authority=0.4),
    ]
    res = dedup_by_finding(rows, gov_suffixes=_GOV)
    assert res.distinct_finding_count == 1
    ids = [r["evidence_id"] for r in res.deduped_rows]
    assert ids == ["ev_hi"]                       # higher-authority rep kept
    assert res.deduped_rows[0]["corroboration_count"] == 2


# ── P5-6 / P5-7 corroboration counts INDEPENDENT hosts ───────────────────────

def test_p5_6_single_host_corroboration_one():
    rows = [_row("ev0", "https://nejm.org/a", _WL72)]
    res = dedup_by_finding(rows, gov_suffixes=_GOV)
    assert res.deduped_rows[0]["corroboration_count"] == 1


def test_p5_7_same_domain_paths_corroboration_one():
    rows = [
        _row("ev0", "https://nih.gov/a", _WL72),
        _row("ev1", "https://nih.gov/b", _WL72),
        _row("ev2", "https://www.nih.gov/c", _WL72),   # www. + different path
    ]
    res = dedup_by_finding(rows, gov_suffixes=_GOV)
    assert len(res.deduped_rows) == 1
    assert res.deduped_rows[0]["corroboration_count"] == 1   # one registrable domain


def test_p5_7b_host_of_strips_www_and_path():
    assert _host_of("https://www.NIH.gov/abc?x=1") == "nih.gov"
    assert _host_of("https://nih.gov/abc") == "nih.gov"
    assert _host_of("") == ""
    assert _host_of("not a url") == ""


# ── P5-8 field-agnostic SAFE: non-clinical numeric -> safe singleton ─────────

def test_p5_8_non_clinical_numeric_is_safe_singleton():
    # DOCUMENTED RESIDUAL 2: the clinical extractor returns nothing for these, so
    # they are kept as SAFE singletons (never falsely merged, never dropped, no
    # corroboration). This pins the SAFE behaviour, not domain-general clustering
    # (deferred to the follow-up extractor issue).
    rows = [
        _row("ev0", "https://a.org/x", "The intervention increased GDP by 3.2% in 2024."),
        _row("ev1", "https://b.org/y", "The intervention increased GDP by 3.2% in 2024."),
    ]
    res = dedup_by_finding(rows, gov_suffixes=_GOV)
    assert len(res.deduped_rows) == 2             # both kept; never falsely merged
    # no corroboration attached (no finding extracted)
    assert "corroboration_count" not in res.deduped_rows[0]


# ── P5-9 qualitative rows never merged/dropped ───────────────────────────────

def test_p5_9_qualitative_rows_kept_as_singletons():
    rows = [
        _row("ev0", "https://a.org/x", "The therapy was generally well tolerated."),
        _row("ev1", "https://b.org/y", "A favorable safety profile was reported."),
    ]
    res = dedup_by_finding(rows, gov_suffixes=_GOV)
    assert len(res.deduped_rows) == 2
    assert res.distinct_finding_count == 0


def test_p5_purity_does_not_mutate_input_rows():
    rows = [
        _row("ev0", "https://nejm.org/a", _WL72, authority=0.9),
        _row("ev1", "https://nih.gov/b", _WL72, authority=0.6),
    ]
    dedup_by_finding(rows, gov_suffixes=_GOV)
    # Caller's rows must NOT gain corroboration keys (we return shallow copies).
    assert "corroboration_count" not in rows[0]
    assert "independent_hosts" not in rows[0]


# ── P5-1 / P5-4 / P5-5 evidence_selector relevance-floor mode ────────────────

def _sel_rows(n_relevant, n_irrelevant, *, authorities=None):
    rows = []
    for i in range(n_relevant):
        auth = authorities[i] if authorities else 0.5
        rows.append(_row(
            f"ev{i}", f"https://h{i}.org/x",
            "tirzepatide weight loss type 2 diabetes trial", authority=auth,
        ))
    for i in range(n_irrelevant):
        rows.append(_row(
            f"ir{i}", f"https://z{i}.org/x",
            "unrelated cooking recipe content here", authority=0.5,
        ))
    return rows


def test_p5_1_off_mode_byte_identical_no_new_key():
    q = "tirzepatide weight loss in type 2 diabetes"
    rows = _sel_rows(30, 5)
    off = select_evidence_for_generation(
        research_question=q, protocol=None, classified_sources=[],
        evidence_rows=rows, max_rows=20,
    )
    assert off.selection_strategy == "tier_balanced_v1"
    assert len(off.selected_rows) == 20                    # the legacy 20-cap
    # OFF must NOT add the selection_relevance key (strict byte-identity).
    assert all("selection_relevance" not in r for r in off.selected_rows)


def test_p5_4_floor_mode_no_cap_drops_sub_floor():
    q = "tirzepatide weight loss in type 2 diabetes"
    rows = _sel_rows(30, 5)
    on = select_evidence_for_generation(
        research_question=q, protocol=None, classified_sources=[],
        evidence_rows=rows, max_rows=20, relevance_floor=0.30,
    )
    assert on.selection_strategy == "relevance_floor_v1"
    assert len(on.selected_rows) == 30                     # no 20-cap; sub-floor dropped
    assert all("selection_relevance" in r for r in on.selected_rows)


def test_p5_5_relevance_times_authority_ranking():
    q = "tirzepatide weight loss in type 2 diabetes"
    # equal-relevance rows -> authority breaks the tie (relevance*authority desc)
    auths = [0.50 + i * 0.01 for i in range(10)]
    rows = _sel_rows(10, 0, authorities=auths)
    on = select_evidence_for_generation(
        research_question=q, protocol=None, classified_sources=[],
        evidence_rows=rows, max_rows=20, relevance_floor=0.30,
    )
    top_auth = [r["authority_score"] for r in on.selected_rows[:3]]
    assert top_auth == sorted(top_auth, reverse=True)      # highest authority first
    assert top_auth[0] == max(auths)


# ── P5-11 PG_RELEVANCE_FLOOR fail-loud (the sweep's gate before sending a pool) ──

def test_p5_11_relevance_floor_default_and_valid():
    assert parse_relevance_floor(None) == pytest.approx(0.30)   # default
    assert parse_relevance_floor("") == pytest.approx(0.30)     # blank -> default
    assert parse_relevance_floor("0.5") == pytest.approx(0.5)
    assert parse_relevance_floor("1.0") == pytest.approx(1.0)   # inclusive upper


def test_p5_11_relevance_floor_fails_loud_on_invalid():
    with pytest.raises(ValueError):
        parse_relevance_floor("not_a_number")
    with pytest.raises(ValueError):
        parse_relevance_floor("0.0")          # exclusive lower bound
    with pytest.raises(ValueError):
        parse_relevance_floor("-0.1")
    with pytest.raises(ValueError):
        parse_relevance_floor("1.5")          # above range


# ── diff-gate P2 fixes ───────────────────────────────────────────────────────

def test_p5_explicit_zero_authority_ranks_below_positive():
    # Codex diff-gate P2: an EXPLICIT authority_score=0.0 must NOT be laundered to
    # 1.0 by `or`. A zero-authority row ranks BELOW an equal-relevance positive row.
    q = "tirzepatide weight loss in type 2 diabetes"
    rows = [
        _row("zero", "https://a.org/x",
             "tirzepatide weight loss type 2 diabetes trial", authority=0.0),
        _row("pos", "https://b.org/y",
             "tirzepatide weight loss type 2 diabetes trial", authority=0.6),
    ]
    on = select_evidence_for_generation(
        research_question=q, protocol=None, classified_sources=[],
        evidence_rows=rows, max_rows=20, relevance_floor=0.30,
    )
    ids = [r["evidence_id"] for r in on.selected_rows]
    assert ids == ["pos", "zero"]            # positive authority ranks first


def test_p5_floor_mode_ignores_zero_max_rows():
    # Codex diff-gate P2: in floor mode the max_rows cap is replaced by the floor,
    # so max_rows=0 (a legacy PG_LIVE_MAX_EV_TO_GEN=0) must NOT empty the pool.
    q = "tirzepatide weight loss in type 2 diabetes"
    rows = _sel_rows(5, 0)
    on = select_evidence_for_generation(
        research_question=q, protocol=None, classified_sources=[],
        evidence_rows=rows, max_rows=0, relevance_floor=0.30,
    )
    assert len(on.selected_rows) == 5        # floor kept all above-floor rows
    # OFF-mode with max_rows=0 still short-circuits to empty (unchanged).
    off = select_evidence_for_generation(
        research_question=q, protocol=None, classified_sources=[],
        evidence_rows=rows, max_rows=0,
    )
    assert off.selected_rows == []
