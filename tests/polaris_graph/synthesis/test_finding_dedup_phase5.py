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

import types

import pytest

from src.polaris_graph.authority.data_loader import load_authority_data
from src.polaris_graph.retrieval.evidence_selector import (
    parse_relevance_floor,
    select_evidence_for_generation,
)
from src.polaris_graph.synthesis.finding_dedup import (
    _finding_key,
    _host_of,
    dedup_by_finding,
)

_GOV = load_authority_data()["psl_gov_suffixes"]


@pytest.fixture(autouse=True)
def _legacy_off_default(monkeypatch):
    """I-arch-007 A20 (#1262): the WEIGHT-AND-CONSOLIDATE redesign is now DEFAULT ON
    (unset env ⇒ consolidate-keep-all / relevance-WEIGHT, no legacy drop). The cases
    below pin the LEGACY collapse-drop / sub-floor-drop path, which is now reached only
    by an EXPLICIT falsey master flag. Force the explicit-OFF legacy path by default so
    these legacy-behavior assertions are exercised against the path they describe. The
    redesign-ON cases ``monkeypatch.setenv(_REDESIGN_FLAG, "1")`` AFTER this fixture, so
    they override it and test the default-ON behavior — no faithfulness assertion is
    weakened, only the env the legacy cases run under is made explicit."""
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "0")


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


# ── I-arch-002 (#1246) P3.3 — CONSOLIDATE-keep-all + OFF byte-identical ───────
#
# Under PG_SWEEP_CREDIBILITY_REDESIGN, finding_dedup STOPS being a source-dropper:
# every same-claim row flows through as a basket carrying corroboration as weight
# (DNA §-1.3 Principle 2). OFF keeps the legacy collapse-to-representative drop
# byte-for-byte. delenv on the OFF test so a stray env =1 cannot flip it.

_REDESIGN_FLAG = "PG_SWEEP_CREDIBILITY_REDESIGN"


def test_p3_3_consolidate_keep_all_when_redesign_on(monkeypatch):
    # Three independent hosts asserting the SAME finding. ON: all 3 rows survive
    # (no member dropped), the representative still carries corroboration, and
    # the collapsed count is honestly 0 (nothing was dropped).
    monkeypatch.setenv(_REDESIGN_FLAG, "1")
    rows = [
        _row("ev0", "https://nejm.org/a", _WL72, authority=0.9),
        _row("ev1", "https://thelancet.com/b", _WL72, authority=0.7),
        _row("ev2", "https://nih.gov/c", _WL72, authority=0.6),
    ]
    res = dedup_by_finding(rows, gov_suffixes=_GOV)
    assert res.distinct_finding_count == 1
    assert len(res.deduped_rows) == 3              # CONSOLIDATE: no member dropped
    assert res.collapsed_row_count == 0            # nothing collapsed away
    ids = [r["evidence_id"] for r in res.deduped_rows]
    assert ids == ["ev0", "ev1", "ev2"]            # original order preserved
    # Corroboration weight still surfaced on the representative (highest authority).
    rep = next(r for r in res.deduped_rows if r["evidence_id"] == "ev0")
    assert rep["corroboration_count"] == 3
    assert rep["independent_hosts"] == ["nejm.org", "nih.gov", "thelancet.com"]
    # Caller's rows still never mutated (shallow-copy purity holds in ON mode too).
    assert "corroboration_count" not in rows[0]


def test_p3_3_off_byte_identical_collapse_drop(monkeypatch):
    # OFF (EXPLICIT falsey flag — I-arch-007 A20 made the redesign default ON, so the
    # legacy collapse-to-representative drop is now reached only by an explicit "0"):
    # the legacy collapse-drop is byte-for-byte — exactly the test_p5_2 expectation.
    monkeypatch.setenv(_REDESIGN_FLAG, "0")
    rows = [
        _row("ev0", "https://nejm.org/a", _WL72, authority=0.9),
        _row("ev1", "https://thelancet.com/b", _WL72, authority=0.7),
        _row("ev2", "https://nih.gov/c", _WL72, authority=0.6),
    ]
    res = dedup_by_finding(rows, gov_suffixes=_GOV)
    assert res.distinct_finding_count == 1
    assert len(res.deduped_rows) == 1              # legacy: collapsed to the rep
    assert res.deduped_rows[0]["evidence_id"] == "ev0"
    assert res.deduped_rows[0]["corroboration_count"] == 3
    assert res.collapsed_row_count == 2


def test_p3_3_off_preserves_safe_guards(monkeypatch):
    # The 3 safe guards survive in OFF mode unchanged: qualitative pass-through,
    # conservative-singleton (distinct endpoint), unknown-subject sentinel.
    # OFF is now an EXPLICIT falsey flag (I-arch-007 A20 made the redesign default ON).
    monkeypatch.setenv(_REDESIGN_FLAG, "0")
    # qualitative pass-through — two qualitative rows, both kept, zero findings.
    qual = dedup_by_finding(
        [
            _row("q0", "https://a.org/x", "The therapy was generally well tolerated."),
            _row("q1", "https://b.org/y", "A favorable safety profile was reported."),
        ],
        gov_suffixes=_GOV,
    )
    assert len(qual.deduped_rows) == 2
    assert qual.distinct_finding_count == 0
    # conservative-singleton — same value, DIFFERENT endpoint -> never merged.
    sep = dedup_by_finding(
        [_row("ev0", "https://a.org/x", _WL72), _row("ev1", "https://b.org/y", _WL20)],
        gov_suffixes=_GOV,
    )
    assert sep.distinct_finding_count == 2
    assert len(sep.deduped_rows) == 2


def test_p3_3_on_preserves_safe_guards(monkeypatch):
    # The same 3 safe guards survive ON: qualitative rows pass through (kept),
    # distinct-endpoint findings stay separate (conservative-singleton), and an
    # unknown subject never merges. CONSOLIDATE only stops the SAME-claim drop —
    # it never relaxes the over-merge defense.
    monkeypatch.setenv(_REDESIGN_FLAG, "1")
    qual = dedup_by_finding(
        [
            _row("q0", "https://a.org/x", "The therapy was generally well tolerated."),
            _row("q1", "https://b.org/y", "A favorable safety profile was reported."),
        ],
        gov_suffixes=_GOV,
    )
    assert len(qual.deduped_rows) == 2
    assert qual.distinct_finding_count == 0
    sep = dedup_by_finding(
        [_row("ev0", "https://a.org/x", _WL72), _row("ev1", "https://b.org/y", _WL20)],
        gov_suffixes=_GOV,
    )
    assert sep.distinct_finding_count == 2
    assert len(sep.deduped_rows) == 2             # distinct endpoints never merged
    # unknown subject -> per-claim sentinel -> never merged.
    q = "A mean reduction of 20.9% at week 72 was observed."
    unk = dedup_by_finding(
        [_row("u0", "https://a.org/x", q), _row("u1", "https://b.org/y", q)],
        gov_suffixes=_GOV,
    )
    assert len(unk.deduped_rows) == 2


# ── I-arch-002 (#1246) P3.3 — round(value,3) retirement on the redesign key ───

def _claim_stub(value):
    # Known subject so the key is the full numeric tuple (not the unknown sentinel).
    return types.SimpleNamespace(
        subject="tirzepatide",
        predicate="weight loss",
        value=value,
        unit="%",
        dose="",
        arm="",
        endpoint_phrase="week 72",
    )


def test_p3_3_finding_key_off_rounds_value():
    # OFF (default exact_value=False) keeps round(value, 3): two values that differ
    # only in the 4th decimal collapse to the SAME rounded slot (legacy behaviour).
    k_a = _finding_key(_claim_stub(14.9001), "evA", 0)
    k_b = _finding_key(_claim_stub(14.9002), "evB", 0)
    assert k_a == k_b
    assert k_a[2] == round(14.9001, 3) == 14.9     # the rounded value slot


def test_p3_3_finding_key_on_keeps_exact_value():
    # ON (exact_value=True) retires the rounding: the two near-distinct values now
    # produce DISTINCT keys, matching claim_graph._normalized_key_numeric's EXACT
    # value (the basket-clustering key the two consolidators must agree on).
    k_a = _finding_key(_claim_stub(14.9001), "evA", 0, exact_value=True)
    k_b = _finding_key(_claim_stub(14.9002), "evB", 0, exact_value=True)
    assert k_a != k_b
    assert k_a[2] == 14.9001
    assert k_b[2] == 14.9002


# ── I-deepfix-001 D1 (#1344) — QUALITATIVE corroboration baskets (§-1.3) ──────
#
# The numeric ``_finding_key`` path keys every basket on an EXTRACTED numeric
# value slot, so a QUALITATIVE (non-numeric) claim several INDEPENDENT sources
# assert earned NO corroboration basket (the D1 diced-dice blind spot:
# ``dice_d1_consolidation_qualitative_basket``). The qualitative pass forms ONE
# multi-citation basket carrying ALL members, keyed on a NON-NUMERIC normalized
# signature. CONSERVATIVE (high Jaccard + polarity guard): two DIFFERENT
# qualitative claims never merge (false-merge is worse than no-merge). KEEP-ALL:
# no source dropped. Gated on the consolidate-keep-all regime (the redesign flag)
# + the ``PG_FINDING_DEDUP_QUALITATIVE`` kill switch.

_QUAL_FLAG = "PG_FINDING_DEDUP_QUALITATIVE"

# A qualitative claim (no extractable numeric finding) several sources assert.
_QUAL_CLAIM = "The therapy was generally well tolerated across the study cohort."


def _has_numeric_finding_key(finding_key) -> bool:
    # The EXACT predicate dice_d1_consolidation_qualitative_basket uses: a key is
    # numeric iff any element is a NON-ZERO int/float (bools excluded).
    if not isinstance(finding_key, (list, tuple)):
        return False
    for el in finding_key:
        if isinstance(el, bool):
            continue
        if isinstance(el, (int, float)) and float(el) != 0.0:
            return True
    return False


def test_d1_qualitative_same_claim_forms_one_basket_all_kept(monkeypatch):
    # N independent hosts asserting the SAME qualitative claim -> ONE basket with
    # N members (ALL kept, §-1.3 keep-all), a NON-NUMERIC finding_key, and
    # corroboration over the N distinct hosts.
    monkeypatch.setenv(_REDESIGN_FLAG, "1")
    rows = [
        _row("ev0", "https://nejm.org/a", _QUAL_CLAIM, authority=0.9),
        _row("ev1", "https://thelancet.com/b", _QUAL_CLAIM, authority=0.7),
        _row("ev2", "https://nih.gov/c", _QUAL_CLAIM, authority=0.6),
    ]
    res = dedup_by_finding(rows, gov_suffixes=_GOV)
    # keep-all: every source survives (no corroborator dropped).
    assert len(res.deduped_rows) == 3
    assert res.qualitative_basket_count == 1
    qual = [
        c for c in res.clusters
        if isinstance(c.finding_key, tuple) and c.finding_key
        and c.finding_key[0] == "__qual__"
    ]
    assert len(qual) == 1
    basket = qual[0]
    # ONE basket carrying ALL 3 members (multi-citation).
    assert basket.member_indices == [0, 1, 2]
    # corroboration over the 3 distinct independent hosts.
    assert basket.corroboration_count == 3
    assert basket.member_hosts == ["nejm.org", "nih.gov", "thelancet.com"]
    # the finding_key is QUALITATIVE (non-numeric) — what the D1 dice asserts.
    assert not _has_numeric_finding_key(list(basket.finding_key))
    # the numeric distinct-finding count is unchanged (qualitative is separate).
    assert res.distinct_finding_count == 0


def test_d1_qualitative_basket_satisfies_dice_predicate(monkeypatch):
    # End-to-end against the EXACT dice predicate: >=1 corroborated (count>1)
    # basket whose finding_key is non-numeric => the D1 dice goes GREEN.
    monkeypatch.setenv(_REDESIGN_FLAG, "1")
    rows = [
        _row("ev0", "https://nejm.org/a", _QUAL_CLAIM, authority=0.9),
        _row("ev1", "https://who.int/b", _QUAL_CLAIM, authority=0.7),
    ]
    res = dedup_by_finding(rows, gov_suffixes=_GOV)
    corro = [c for c in res.clusters if int(c.corroboration_count) > 1]
    qual_corro = [
        c for c in corro if not _has_numeric_finding_key(list(c.finding_key))
    ]
    assert len(qual_corro) >= 1


def test_d1_different_qualitative_claims_not_merged(monkeypatch):
    # Two DIFFERENT qualitative claims (low shingle overlap) must NEVER merge.
    # Both stay singletons -> no basket; both rows kept.
    monkeypatch.setenv(_REDESIGN_FLAG, "1")
    rows = [
        _row("ev0", "https://a.org/x", _QUAL_CLAIM),
        _row("ev1", "https://b.org/y",
             "Mortality increased sharply among the older subgroup of patients."),
    ]
    res = dedup_by_finding(rows, gov_suffixes=_GOV)
    assert len(res.deduped_rows) == 2
    assert res.qualitative_basket_count == 0


def test_d1_polarity_guard_blocks_negation_flip(monkeypatch):
    # A negation flip ("was associated" vs "was NOT associated") shares ~0.88
    # Jaccard but asserts the OPPOSITE claim. The polarity guard blocks the merge
    # even above threshold, so a real opposing claim is never corroborated away.
    monkeypatch.setenv(_REDESIGN_FLAG, "1")
    pos = ("The combination therapy was associated with a clinically meaningful "
           "and statistically robust improvement in progression free survival "
           "among previously treated adult patients.")
    neg = pos.replace("was associated", "was not associated")
    rows = [
        _row("ev0", "https://a.org/x", pos),
        _row("ev1", "https://b.org/y", neg),
    ]
    res = dedup_by_finding(rows, gov_suffixes=_GOV)
    assert res.qualitative_basket_count == 0     # opposite polarity -> never merged
    assert len(res.deduped_rows) == 2


def test_d1_qualitative_same_host_is_not_corroboration(monkeypatch):
    # Two rows asserting the same qualitative claim but from the SAME registrable
    # domain are NOT independent corroboration: the basket's corroboration_count
    # is 1 (so the D1 dice, which requires >1, would not count it). No row dropped.
    monkeypatch.setenv(_REDESIGN_FLAG, "1")
    rows = [
        _row("ev0", "https://nih.gov/a", _QUAL_CLAIM),
        _row("ev1", "https://www.nih.gov/b", _QUAL_CLAIM),   # same domain, www + path
    ]
    res = dedup_by_finding(rows, gov_suffixes=_GOV)
    assert len(res.deduped_rows) == 2
    qual = [
        c for c in res.clusters
        if isinstance(c.finding_key, tuple) and c.finding_key
        and c.finding_key[0] == "__qual__"
    ]
    assert len(qual) == 1
    assert qual[0].corroboration_count == 1      # one registrable domain


def test_d1_qualitative_kill_switch_off_no_basket(monkeypatch):
    # LAW VI: PG_FINDING_DEDUP_QUALITATIVE=0 restores the numeric-only behavior
    # (no qualitative basket) even with the redesign regime on. No row dropped.
    monkeypatch.setenv(_REDESIGN_FLAG, "1")
    monkeypatch.setenv(_QUAL_FLAG, "0")
    rows = [
        _row("ev0", "https://nejm.org/a", _QUAL_CLAIM),
        _row("ev1", "https://nih.gov/b", _QUAL_CLAIM),
    ]
    res = dedup_by_finding(rows, gov_suffixes=_GOV)
    assert res.qualitative_basket_count == 0
    assert len(res.deduped_rows) == 2            # qualitative rows still kept


def test_d1_legacy_regime_no_qualitative_basket(monkeypatch):
    # Gated on the consolidate-keep-all regime: with the legacy (drop) regime
    # explicitly off, NO qualitative basket forms (the path is byte-inert) —
    # same-claim qualitative rows are kept exactly as the legacy did.
    monkeypatch.setenv(_REDESIGN_FLAG, "0")
    rows = [
        _row("ev0", "https://nejm.org/a", _QUAL_CLAIM),
        _row("ev1", "https://nih.gov/b", _QUAL_CLAIM),
    ]
    res = dedup_by_finding(rows, gov_suffixes=_GOV)
    assert res.qualitative_basket_count == 0
    assert len(res.deduped_rows) == 2


def test_d1_qualitative_does_not_mutate_input_rows(monkeypatch):
    # Purity holds for the qualitative path too: the caller's rows never gain
    # corroboration keys (we return shallow copies).
    monkeypatch.setenv(_REDESIGN_FLAG, "1")
    rows = [
        _row("ev0", "https://nejm.org/a", _QUAL_CLAIM),
        _row("ev1", "https://nih.gov/b", _QUAL_CLAIM),
    ]
    dedup_by_finding(rows, gov_suffixes=_GOV)
    assert "corroboration_count" not in rows[0]
    assert "finding_keys" not in rows[0]
