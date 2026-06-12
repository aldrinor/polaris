"""I-perm-024 (#1216) — extended beat-both scorer metrics (claim-by-claim only).

Proves: (1) every metric is derived from audited ClaimRows/RubricElements, never raw
text (§-1.1 structural guard); (2) Claimify dedup collapses repeated VERIFIED claims
WITHOUT hiding a bad verdict (Codex brief-gate iter-1 P2); (3) diversity_score is a
diagnostic NO decision path consumes; (4) build_scorecard is byte-identical when the
extended path is off.
"""
from __future__ import annotations

import inspect
from pathlib import Path

from src.polaris_graph.benchmark import benchmark_scorecard, claim_audit_scorer
from src.polaris_graph.benchmark.benchmark_scorecard import build_scorecard
from src.polaris_graph.benchmark.claim_audit_scorer import ClaimRow, RubricElement
from src.polaris_graph.benchmark.claim_dedup import dedup_claims
from src.polaris_graph.benchmark.extended_metrics import (
    ScoredClaim,
    citation_support_rate,
    compute_extended_metrics,
    diversity_score,
    faithfulness_precision,
    load_safety_floor_element_ids,
    required_entity_recall,
    safety_floor_recall,
)

_CID = [0]


def _verified(cid="src1", sev="S1"):
    _CID[0] += 1
    return ClaimRow(claim_id=f"v{_CID[0]}", severity=sev, verdict="VERIFIED",
                    citation_id=cid, span_quote="supporting span")


def _unsupported(cid=None, sev="S1"):
    _CID[0] += 1
    return ClaimRow(claim_id=f"u{_CID[0]}", severity=sev, verdict="UNSUPPORTED",
                    citation_id=cid, span_quote=None,
                    audit_note="no support" if cid else None)


def _fabricated(cid="src9", sev="S1"):
    _CID[0] += 1
    return ClaimRow(claim_id=f"f{_CID[0]}", severity=sev, verdict="FABRICATED",
                    citation_id=cid, span_quote="refuting span")


# ── metric correctness ────────────────────────────────────────────────────

def test_faithfulness_precision_exact():
    rows = [_verified(), _verified(), _unsupported(), _fabricated()]
    m = faithfulness_precision(rows)
    assert m["material_atoms"] == 4
    assert m["verified"] == 2
    assert m["value"] == 0.5


def test_citation_support_rate_excludes_verified_but_uncited():
    rows = [_verified(cid="src1"), _verified(cid=None), _unsupported()]
    m = citation_support_rate(rows)
    assert m["material_atoms"] == 3
    assert m["verified_and_cited"] == 1   # the cid=None VERIFIED does NOT count
    assert round(m["value"], 4) == round(1 / 3, 4)


def test_diversity_score_monoculture_low_vs_diverse_high():
    mono = diversity_score([_verified("s1"), _verified("s1"), _verified("s1")])
    assert mono["distinct_sources"] == 1 and round(mono["value"], 4) == round(1 / 3, 4)
    div = diversity_score([_verified("s1"), _verified("s2"), _verified("s3")])
    assert div["distinct_sources"] == 3 and div["value"] == 1.0
    assert "NOT a superiority signal" in mono["note"]


def test_required_entity_recall_on_rubric():
    rubric = [
        RubricElement("E1", covered=True, citation_supported=True),
        RubricElement("E2", covered=True, citation_supported=False),
        RubricElement("E3", covered=False, citation_supported=False),
    ]
    m = required_entity_recall(rubric)
    assert m["total_required"] == 3 and m["covered_supported"] == 1
    assert round(m["value"], 4) == round(1 / 3, 4)
    assert set(m["missing"]) == {"E2", "E3"}


def test_safety_floor_recall_restricted_to_tagged_subset():
    rubric = [
        RubricElement("Q76-E6", covered=True, citation_supported=True),
        RubricElement("Q76-E7", covered=False, citation_supported=False),
        RubricElement("Q76-E1", covered=True, citation_supported=True),  # not safety
    ]
    m = safety_floor_recall(rubric, {"Q76-E6", "Q76-E7"})
    assert m["total_safety_required"] == 2     # E1 excluded
    assert m["covered_supported"] == 1
    assert m["value"] == 0.5


def test_safety_floor_denominator_is_preregistered_count():
    # Codex diff-gate iter-1 P2: a tagged id absent from the supplied rubric must
    # SURFACE + count against recall, NOT shrink the denominator into a false-high.
    rubric = [RubricElement("Q76-E6", covered=True, citation_supported=True)]
    m = safety_floor_recall(rubric, {"Q76-E6", "Q76-E7"})  # E7 not in rubric
    assert m["total_safety_required"] == 2          # pre-registered count, not 1
    assert m["covered_supported"] == 1
    assert m["value"] == 0.5                          # penalised, not 1.0
    assert m["missing_from_rubric"] == ["Q76-E7"]
    assert "Q76-E7" in m["missing"]


def test_required_entity_recall_pending_when_no_rubric():
    assert required_entity_recall(None)["pending"] is True
    assert required_entity_recall(None)["value"] is None


# ── pre-registered safety registry ────────────────────────────────────────

def test_load_safety_floor_from_real_registry_q76():
    ids = load_safety_floor_element_ids("76")
    assert ids == {"Q76-E6", "Q76-E7"}


def test_load_safety_floor_q72_is_empty_non_clinical():
    assert load_safety_floor_element_ids("72") == set()


# ── Claimify dedup ────────────────────────────────────────────────────────

def test_dedup_collapses_restatements_of_one_numeric_fact():
    # true restatements = same content tokens reordered (dedup is conservative: it
    # does NOT stem, so "provides"/"providing" stay distinct — under-merge is the
    # §-1.1-safe direction; this proves the collapse on genuine restatements).
    texts = [
        "butyrate provides 70 percent of colonocyte energy needs",
        "colonocyte energy needs butyrate provides 70 percent",
        "70 percent of colonocyte energy needs butyrate provides",
    ]
    res = dedup_claims(texts)
    assert res.n_kept == 1            # all three collapse
    assert res.representatives == [0]


def test_dedup_is_conservative_on_verb_variation():
    # a 1-token paraphrase difference below the 0.80 Jaccard bar is NOT merged —
    # conservative under-merge (never hide a distinct claim) over aggressive merge.
    texts = [
        "butyrate is the primary colonocyte energy source providing 70 percent",
        "butyrate provides 70 percent of colonocyte energy as primary source",
    ]
    res = dedup_claims(texts)
    assert res.n_kept == 2


def test_dedup_does_not_over_merge_conflicting_numbers():
    texts = ["CRC risk reduced by 20 percent", "CRC risk reduced by 37 percent"]
    res = dedup_claims(texts)
    assert res.n_kept == 2            # different decimals → distinct facts


def test_dedup_blocks_entity_swap_with_matching_numbers():
    # Codex diff-gate iter-1 P1: distinct DRUGS, same 20% phrasing, Jaccard >= 0.80 —
    # must NOT merge (a mutual semaglutide<->liraglutide swap = different facts).
    texts = [
        "semaglutide significantly reduced major adverse cardiovascular events by 20 percent",
        "liraglutide significantly reduced major adverse cardiovascular events by 20 percent",
    ]
    res = dedup_claims(texts)
    assert res.n_kept == 2


def test_dedup_blocks_alphanumeric_entity_swap():
    # Codex diff-gate iter-2 P1: alphanumeric drug-class tokens (SGLT2/DPP4, IL6/TNF,
    # PCSK9/DPP4) are subjects too — isalpha() missed them. They must NOT merge.
    for a_ent, b_ent in (("SGLT2", "DPP4"), ("IL6", "TNF"), ("PCSK9", "DPP4")):
        texts = [
            f"{a_ent} inhibitors significantly reduced major adverse cardiovascular events in adults by 20 percent",
            f"{b_ent} inhibitors significantly reduced major adverse cardiovascular events in adults by 20 percent",
        ]
        res = dedup_claims(texts)
        assert res.n_kept == 2, f"{a_ent} vs {b_ent} wrongly merged"


def test_dedup_blocks_hyphenated_and_short_entity_swaps():
    # Codex diff-gate iter-3 P1: hyphenated cytokines (IL-6/TNF, IL-6/IL-10) and
    # short metal-ion symbols (Zn/Cu, Mg/Fe) are distinct entities — must NOT merge.
    pairs = [
        ("IL-6", "TNF"), ("IL-6", "IL-10"), ("Zn", "Cu"), ("Mg", "Fe"),
        ("CD4", "CD8"),
    ]
    for a_ent, b_ent in pairs:
        texts = [
            f"{a_ent} signalling was associated with the outcome in adults by 20 percent",
            f"{b_ent} signalling was associated with the outcome in adults by 20 percent",
        ]
        res = dedup_claims(texts)
        assert res.n_kept == 2, f"{a_ent} vs {b_ent} wrongly merged"


def test_dedup_blocks_sign_and_greek_entity_swaps():
    # Codex diff-gate iter-4 P1: sign suffixes and Greek variants distinguish entities
    # (CD4+/CD4-, pks+/pks-, IL-1alpha/IL-1beta) — must NOT merge.
    alpha, beta = chr(0x3B1), chr(0x3B2)
    pairs = [
        ("CD4+", "CD4-"), ("pks+", "pks-"), (f"IL-1{alpha}", f"IL-1{beta}"),
        ("HER2+", "HER2-"), ("ER+", "ER-"),
    ]
    for a_ent, b_ent in pairs:
        texts = [
            f"{a_ent} tumour cells increased the marker in adults by 20 percent",
            f"{b_ent} tumour cells increased the marker in adults by 20 percent",
        ]
        res = dedup_claims(texts)
        assert res.n_kept == 2, f"{a_ent} vs {b_ent} wrongly merged"


def test_alphanumeric_entity_swap_does_not_inflate_citation_rate():
    scored = [
        ScoredClaim(
            "SGLT2 inhibitors significantly reduced major adverse cardiovascular events in adults by 20 percent",
            _verified(cid=None)),
        ScoredClaim(
            "DPP4 inhibitors significantly reduced major adverse cardiovascular events in adults by 20 percent",
            _verified(cid="src6")),
    ]
    out = compute_extended_metrics(scored)
    assert out["dedup"]["n_verified_collapsed"] == 0
    csr = out["citation_support_rate"]
    assert csr["material_atoms"] == 2 and csr["value"] == 0.5


def test_entity_swap_does_not_inflate_citation_support_rate():
    # the metric-level consequence Codex flagged: an uncited VERIFIED drug-A claim and
    # a cited VERIFIED drug-B claim must BOTH survive → citation_support_rate = 1/2.
    scored = [
        ScoredClaim(
            "semaglutide significantly reduced major adverse cardiovascular events by 20 percent",
            _verified(cid=None)),
        ScoredClaim(
            "liraglutide significantly reduced major adverse cardiovascular events by 20 percent",
            _verified(cid="src5")),
    ]
    out = compute_extended_metrics(scored)
    assert out["dedup"]["n_verified_collapsed"] == 0   # no merge
    csr = out["citation_support_rate"]
    assert csr["material_atoms"] == 2 and csr["verified_and_cited"] == 1
    assert csr["value"] == 0.5


def test_dedup_blocks_one_sided_subgroup_modifiers():
    # Codex diff-gate iter-5 P1: a clinically-distinct SUBGROUP narrowing is a one-sided
    # subset modifier (HER2+ breast cancer vs breast cancer; CD4+ T cells vs T cells;
    # low-dose aspirin vs aspirin) — these are DIFFERENT facts and must NOT merge.
    pairs = [
        ("HER2+ breast cancer patients had a 20 percent response rate to the drug",
         "breast cancer patients had a 20 percent response rate to the drug"),
        ("CD4+ T cells increased the marker in adults by 20 percent",
         "T cells increased the marker in adults by 20 percent"),
        ("low-dose aspirin reduced events in adults by 20 percent",
         "aspirin reduced events in adults by 20 percent"),
    ]
    for a, b in pairs:
        res = dedup_claims([a, b])
        assert res.n_kept == 2, f"subset modifier wrongly merged:\n  {a}\n  {b}"


def test_dedup_still_collapses_identical_subject_reorderings():
    # the kept value: verbatim repeats + pure reorderings (IDENTICAL subjects) still merge.
    texts = [
        "butyrate provides 70 percent of colonocyte energy needs",
        "colonocyte energy needs butyrate provides 70 percent",
        "butyrate provides 70 percent of colonocyte energy needs",
    ]
    assert dedup_claims(texts).n_kept == 1


def test_dedup_is_cross_system_identical():
    texts = ["fiber raises SCFA 15%", "dietary fiber raises SCFA by 15%"]
    a = dedup_claims(texts)
    b = dedup_claims(list(texts))
    assert a.groups == b.groups


# ── verdict-aware keep (the P2 fix): a bad verdict is NEVER hidden ─────────

def test_mixed_verdict_cluster_keeps_the_bad_verdict():
    # same fact, one VERIFIED and one UNSUPPORTED → both must survive dedup.
    same = "colibactin from pks+ E. coli causes DNA double-strand breaks"
    scored = [
        ScoredClaim(same, _verified("s1")),
        ScoredClaim(same, _unsupported(cid="s1")),
    ]
    out = compute_extended_metrics(scored)
    # one text cluster collapsed, but n_verified_collapsed counts only VERIFIED dups
    assert out["dedup"]["n_verified_collapsed"] == 0
    fp = out["faithfulness_precision"]
    assert fp["material_atoms"] == 2 and fp["verified"] == 1   # UNSUPPORTED survived
    assert fp["value"] == 0.5


def test_collapsed_verified_prefers_cited_representative():
    # a VERIFIED-uncited + VERIFIED-cited restatement of one fact collapses to the
    # CITED rep (deterministic, disclosed) so citation_support_rate is not understated.
    same = "fermented foods raise microbiome diversity in adults"
    scored = [
        ScoredClaim(same, _verified(cid=None)),   # uncited, appears first
        ScoredClaim(same, _verified(cid="src7")),  # cited
    ]
    out = compute_extended_metrics(scored)
    assert out["dedup"]["n_verified_collapsed"] == 1
    csr = out["citation_support_rate"]
    assert csr["material_atoms"] == 1 and csr["verified_and_cited"] == 1  # cited kept
    assert csr["value"] == 1.0


def test_repeated_verified_does_not_inflate_precision():
    same = "fermented foods increase microbiome diversity"
    scored = [ScoredClaim(same, _verified("s1")) for _ in range(10)]
    scored += [ScoredClaim(f"hard distinct claim number {i}", _unsupported(cid=f"s{i}"))
               for i in range(5)]
    out = compute_extended_metrics(scored)
    assert out["dedup"]["n_verified_collapsed"] == 9   # 10 VERIFIED → 1
    fp = out["faithfulness_precision"]
    assert fp["material_atoms"] == 6 and fp["verified"] == 1   # 1 verified + 5 unsupp
    assert round(fp["value"], 4) == round(1 / 6, 4)


# ── §-1.1 structural: metrics are verdict-derived, never text-derived ─────

def test_metric_functions_take_only_audited_inputs_no_report_text():
    for fn in (faithfulness_precision, citation_support_rate, diversity_score):
        params = list(inspect.signature(fn).parameters)
        assert params == ["rows"], f"{fn.__name__} must take only audited rows"
    for fn in (required_entity_recall,):
        assert list(inspect.signature(fn).parameters) == ["rubric"]
    # no metric function accepts a report/body/text param anywhere
    banned = {"report", "report_text", "body", "text", "raw"}
    for fn in (faithfulness_precision, citation_support_rate, diversity_score,
               required_entity_recall, safety_floor_recall):
        assert not (set(inspect.signature(fn).parameters) & banned)


def test_metrics_unchanged_when_claim_text_differs_but_rows_identical():
    rows = [_verified("s1"), _unsupported(), _verified("s2")]
    # identical rows, but completely different (all-distinct) texts → no dedup either way
    a = compute_extended_metrics(
        [ScoredClaim(f"alpha unique sentence {i}", r) for i, r in enumerate(rows)])
    b = compute_extended_metrics(
        [ScoredClaim(f"zzz totally other words {i}", r) for i, r in enumerate(rows)])
    assert a["faithfulness_precision"] == b["faithfulness_precision"]
    assert a["citation_support_rate"] == b["citation_support_rate"]
    assert a["diversity_score"]["value"] == b["diversity_score"]["value"]


# ── diversity is a diagnostic NO decision path consumes (Codex P2) ─────────

def test_no_decision_path_consumes_diversity_score():
    # the scorecard PASS/aggregate logic must never read diversity — structural guard
    for mod in (benchmark_scorecard, claim_audit_scorer):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        assert "diversity" not in src.lower(), (
            f"{mod.__name__} must not reference diversity (it is a diagnostic only)")


# ── byte-identical when the extended path is off ──────────────────────────

def test_build_scorecard_byte_identical_when_extended_none():
    rows = {("polaris", "76"): [_verified("s1"), _unsupported()]}
    default = build_scorecard(rows)
    explicit_off = build_scorecard(rows, extended=None)
    assert default == explicit_off
    assert "extended" not in default


def test_build_scorecard_attaches_extended_when_provided():
    rows = {("polaris", "76"): [_verified("s1")]}
    card = build_scorecard(rows, extended={"polaris:76": {"ok": True}})
    assert card["extended"] == {"polaris:76": {"ok": True}}


# ── end-to-end shape ──────────────────────────────────────────────────────

def test_compute_extended_metrics_full_shape():
    scored = [ScoredClaim("a claim about butyrate", _verified("s1")),
              ScoredClaim("a distinct claim about fiber", _unsupported())]
    rubric = [RubricElement("Q76-E6", covered=True, citation_supported=True)]
    out = compute_extended_metrics(
        scored, rubric=rubric, safety_element_ids={"Q76-E6"})
    for key in ("faithfulness_precision", "citation_support_rate", "diversity_score",
                "required_entity_recall", "safety_floor_recall", "methodology_note",
                "dedup", "n_raw_claims", "n_kept_claims"):
        assert key in out
    assert out["required_entity_recall"]["value"] == 1.0
    assert out["safety_floor_recall"]["value"] == 1.0
