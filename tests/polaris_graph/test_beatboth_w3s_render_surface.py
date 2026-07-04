"""I-deepfix-001 beat-both W3-S render-surface fixes — FAIL-LOUD behavioral tests.

Each test proves the fix EFFECT in the REAL rendered/accounted output (RED->GREEN via the LAW-VI
kill-switch), not a flag tautology. All offline ($0), no network / model.

  S1 — the per-claim corroboration COUNT is bound to the authoritative verified-support count;
       a 0-verified basket renders "single-source, not independently corroborated", never a
       "0 verified independent source(s)" count bullet.
  S2 — a required entity is credited COVERED when the report's CITED evidence matches its canonical
       id (doi/pmid/url_pattern); it flips from a disclosed GAP to VERIFIED, raising coverage.
  S3 — a SECOND, REPORT-SCOPED reliability header counts corroboration over ONLY the cited baskets
       and renders as the headline above the pool-level counts.
  S4 — a single-source-of-truth contradiction ledger enumerates ALL N detected contradictions
       (== manifest.contradictions_found) with a per-item disposition.
  S6 — the displayed corroboration weight is derived from the single authority_score source of
       truth, so a source shows one weight (0.60), never a divergent credibility_weight (0.08).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]


def _load_run_module():
    """Load scripts/run_honest_sweep_r3.py as an importable module (it is a script, not a package
    member). Cached in sys.modules so the ~seconds import cost is paid once."""
    if "rhs_w3s" in sys.modules:
        return sys.modules["rhs_w3s"]
    path = _REPO / "scripts" / "run_honest_sweep_r3.py"
    spec = importlib.util.spec_from_file_location("rhs_w3s", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["rhs_w3s"] = mod
    spec.loader.exec_module(mod)
    return mod


RHS = _load_run_module()


# ─────────────────────────────────────────────────────────────────────────────
# Shared basket/bibliography fixtures for the corroboration-block render (S1 + S6).
# ─────────────────────────────────────────────────────────────────────────────
def _member(eid, url, tier, cred_w, auth, mtier="ENTAILMENT_VERIFIED", origin=None):
    return {
        "evidence_id": eid,
        "source_url": url,
        "source_tier": tier,
        "origin_cluster_id": origin or f"oc_{eid}",
        "credibility_weight": cred_w,
        "authority_score": auth,
        "span_verdict": "SUPPORTS",
        "member_tier": mtier,
        "direct_quote": "Automation raised measured labor productivity in the surveyed firms.",
    }


def _bibliography_with_basket(basket, member_eids):
    """A bibliography whose rows expose each member's evidence_id (so _is_biblio_present is True),
    with the basket projected onto the first row (the render iterates row['baskets'])."""
    rows = []
    for i, eid in enumerate(member_eids, start=1):
        row = {"num": i, "evidence_id": eid, "url": f"http://src/{eid}"}
        if i == 1:
            row["baskets"] = [basket]
        rows.append(row)
    return rows


def _uncorroborated_basket():
    """A basket the authoritative CONSOLIDATE leg ruled unverified (verified_support_origin_count=0
    / basket_verdict='unverified') — the S1 over-claim case."""
    return {
        "claim_cluster_id": "c_uncorr",
        "claim_text": "Automation raised measured labor productivity across surveyed firms.",
        "subject": "Automation",
        "predicate": "raised measured labor productivity",
        "verified_support_origin_count": 0,
        "basket_verdict": "unverified",
        "supporting_members": [_member("e1", "http://src/e1", "T4", 0.30, 0.30)],
    }


def _multi_source_basket():
    """A genuinely multi-source basket (2 distinct verified origins) — the count>=2 / S6 case.
    authority_score (0.60) diverges from credibility_weight (0.08) to prove the S6 source-of-truth."""
    return {
        "claim_cluster_id": "c_multi",
        "claim_text": "Automation raised measured labor productivity across surveyed firms.",
        "subject": "Automation",
        "predicate": "raised measured labor productivity",
        "verified_support_origin_count": 2,
        "basket_verdict": "full",
        "supporting_members": [
            _member("e1", "http://src/e1", "T1", 0.08, 0.60, origin="oc_a"),
            _member("e2", "http://src/e2", "T1", 0.08, 0.60, origin="oc_b"),
        ],
    }


# ── S1 ────────────────────────────────────────────────────────────────────────
def test_s1_zero_verified_renders_uncorroborated_label(monkeypatch):
    """RED (S1 OFF) -> the legacy '0 verified independent source(s)' count bullet.
    GREEN (S1 ON, default) -> 'single-source, not independently corroborated' and NO '0 verified
    independent source(s)'. The authoritative count is the binding one (WS-6), the label is honest."""
    biblio = _bibliography_with_basket(_uncorroborated_basket(), ["e1"])

    # RED: kill-switch OFF reproduces the misleading count bullet.
    monkeypatch.setenv("PG_S1_UNCORROBORATED_LABEL", "0")
    off = RHS._basket_corroboration_block(biblio)
    assert "0 verified independent source(s)" in off, (
        "RED baseline missing: with S1 OFF the block should print the legacy "
        "'0 verified independent source(s)' bullet"
    )
    assert "single-source, not independently corroborated" not in off

    # GREEN: default-ON binds the honest uncorroborated label and drops the count bullet.
    monkeypatch.setenv("PG_S1_UNCORROBORATED_LABEL", "1")
    on = RHS._basket_corroboration_block(biblio)
    assert "single-source, not independently corroborated" in on, (
        "S1 EFFECT missing: a 0-verified basket must render the honest uncorroborated label"
    )
    assert "0 verified independent source(s)" not in on, (
        "S1 regression: the misleading '0 verified independent source(s)' bullet must be gone"
    )


def test_s1_multi_source_still_prints_count():
    """S1 must NOT touch a genuinely corroborated basket — count>=2 still prints the count."""
    biblio = _bibliography_with_basket(_multi_source_basket(), ["e1", "e2"])
    block = RHS._basket_corroboration_block(biblio)
    assert "2 verified independent source(s)" in block, (
        "S1 must leave a real 2-source basket's count intact"
    )
    assert "single-source, not independently corroborated" not in block


def test_s1_suffix_helper_pure():
    assert RHS.corroboration_count_suffix(0, enabled=True).endswith(
        "single-source, not independently corroborated"
    )
    assert RHS.corroboration_count_suffix(0, enabled=False) == " — 0 verified independent source(s)"
    assert RHS.corroboration_count_suffix(3, enabled=True) == " — 3 verified independent source(s)"


# ── S6 ────────────────────────────────────────────────────────────────────────
def test_s6_weight_from_authority_score_single_source(monkeypatch):
    """RED (S6 OFF) -> the divergent credibility_weight (0.08) renders next to the T1 tier.
    GREEN (S6 ON, default) -> the single authority_score (0.60) renders, so tier + weight agree."""
    biblio = _bibliography_with_basket(_multi_source_basket(), ["e1", "e2"])

    monkeypatch.setenv("PG_S6_AUTHORITY_SINGLE_SOURCE", "0")
    off = RHS._basket_corroboration_block(biblio)
    assert "weight 0.08" in off and "weight 0.60" not in off, (
        "RED baseline missing: with S6 OFF the block should print the credibility_weight 0.08"
    )

    monkeypatch.setenv("PG_S6_AUTHORITY_SINGLE_SOURCE", "1")
    on = RHS._basket_corroboration_block(biblio)
    assert "weight 0.60" in on, (
        "S6 EFFECT missing: the displayed weight must come from the authority_score source of truth"
    )
    assert "weight 0.08" not in on, (
        "S6 regression: a T1 tier label must not sit on the divergent 0.08 credibility_weight"
    )


def test_s6_helper_falls_back_ONLY_when_authority_absent():
    """Codex diff-gate P1 (#1344): authority_score is the single source of truth. Fallback to
    credibility_weight happens ONLY when authority_score is ABSENT (missing / non-numeric) — a PRESENT
    0.0 is a real low-authority weight that must render as '0.00', NOT be overridden by the divergent
    credibility_weight (which re-opens the two-surface divergence S6 exists to close)."""
    # PRESENT authority_score 0.0 -> the single-source-of-truth value, NOT the credibility_weight.
    assert RHS.member_display_weight(
        {"authority_score": 0.0, "credibility_weight": 0.15}, enabled=True
    ) == "0.00"
    # ABSENT (missing key) -> falls back to credibility_weight (byte-identical to legacy).
    assert RHS.member_display_weight(
        {"credibility_weight": 0.15}, enabled=True
    ) == "0.15"
    # ABSENT (None) -> falls back to credibility_weight.
    assert RHS.member_display_weight(
        {"authority_score": None, "credibility_weight": 0.15}, enabled=True
    ) == "0.15"
    # PRESENT positive authority_score -> the single source of truth.
    assert RHS.member_display_weight(
        {"authority_score": 0.72, "credibility_weight": 0.10}, enabled=True
    ) == "0.72"
    # Neither present -> 'n/a' (never a guessed number).
    assert RHS.member_display_weight({}, enabled=True) == "n/a"


# ── S3 ────────────────────────────────────────────────────────────────────────
def _basket_obj(ccid, vcount, refuters=()):  # minimal duck-typed basket
    return {
        "claim_cluster_id": ccid,
        "verified_support_origin_count": vcount,
        "refuter_cluster_ids": tuple(refuters),
    }


def test_s3_report_scoped_counts_restrict_to_cited():
    from src.polaris_graph.generator.multi_section_generator import (
        build_report_scoped_reliability_header,
    )
    baskets = [
        _basket_obj("A", 3),   # cited, multi-source
        _basket_obj("B", 1),   # cited, single-origin
        _basket_obj("C", 4),   # NOT cited -> excluded
        _basket_obj("D", 1),   # NOT cited -> excluded
    ]
    scoped = build_report_scoped_reliability_header(baskets, {"A", "B"})
    assert scoped is not None
    assert scoped["claims_total"] == 2, "report-scoped must count ONLY the cited baskets"
    assert scoped["claims_multi_source_corroborated"] == 1
    assert scoped["claims_single_origin"] == 1
    # Empty cited set -> None (=> caller renders pool-only, byte-identical).
    assert build_report_scoped_reliability_header(baskets, set()) is None


def test_s3_render_shows_report_scoped_headline():
    pool = {
        "claims_total": 286,
        "claims_with_verified_support": 286,
        "claims_multi_source_corroborated": 2,
        "claims_single_origin": 284,
        "claims_contested": 0,
    }
    scoped = {
        "claims_total": 12,
        "claims_with_verified_support": 12,
        "claims_multi_source_corroborated": 0,
        "claims_single_origin": 12,
        "claims_contested": 0,
    }
    # RED: without report_scoped, no report-scoped headline.
    off = RHS.render_reliability_header_md(pool, None)
    assert "Report-scoped" not in off
    # GREEN: with report_scoped, the cited-claims headline renders above the pool counts.
    on = RHS.render_reliability_header_md(pool, scoped)
    assert "Report-scoped (the claims actually cited in this report)" in on
    assert "Cited: multi-source corroborated (>= 2 verified origins): 0" in on
    assert "Pool-level counts" in on and "Multi-source corroborated (>= 2 verified origins): 2" in on
    # The report-scoped headline appears BEFORE the pool-level block.
    assert on.index("Report-scoped") < on.index("Pool-level counts")


# ── S4 ────────────────────────────────────────────────────────────────────────
class _Contradiction:
    def __init__(self, subject, predicate):
        self.subject = subject
        self.predicate = predicate


def test_s4_ledger_enumerates_all_n_with_disposition():
    from src.polaris_graph.retrieval.contradiction_detector import (
        POSSIBLE_METRIC_MISMATCH_MARKER,
    )
    contradictions = [
        _Contradiction("exposure", "share of jobs affected"),                       # disclosed
        _Contradiction("wage", f"change {POSSIBLE_METRIC_MISMATCH_MARKER}"),         # withheld
        {"subject": "adoption", "predicate": "firm uptake rate"},                    # disclosed (dict)
    ]
    rows = RHS.s4_contradiction_disposition_rows(contradictions)
    # SINGLE source of truth: exactly one row per detected record (== manifest.contradictions_found).
    assert len(rows) == len(contradictions) == 3
    dispositions = [r["disposition"] for r in rows]
    assert dispositions[0] == RHS.S4_DISPOSITION_DISCLOSED
    assert dispositions[1] == RHS.S4_DISPOSITION_WITHHELD
    assert dispositions[2] == RHS.S4_DISPOSITION_DISCLOSED

    md = RHS.render_s4_contradiction_disposition_ledger(contradictions)
    # The rendered headline count must equal len(contradictions) (== the manifest count).
    manifest_count = len(contradictions)
    assert f"matches `manifest.contradictions_found`): {manifest_count}." in md
    # Every record is enumerated (all 3 subjects appear).
    for subj in ("exposure", "wage", "adoption"):
        assert subj in md
    # Empty -> byte-identical omission.
    assert RHS.render_s4_contradiction_disposition_ledger([]) == ""


# ── S2 ────────────────────────────────────────────────────────────────────────
def test_s2_citation_credits_required_entity_from_cited_evidence():
    from src.polaris_graph.generator.required_entity_ledger import (
        build_ledger,
        citation_covered_entity_ids,
    )
    required = [
        {"id": "acemoglu2020", "severity": "high", "doi": "10.1086/705716"},
        {"id": "eloundou2024", "severity": "high", "url_pattern": "science.org/doi/10.1126/science.adj0998"},
        {"id": "never_cited", "severity": "medium", "doi": "10.9999/absent"},
    ]
    # The report's CITED evidence (bibliography rows): one carries the doi in its URL (doi.org
    # locator), one matches the url_pattern. 'never_cited' appears nowhere.
    cited_records = [
        {"evidence_id": "e1", "url": "https://doi.org/10.1086/705716", "source_url": "https://doi.org/10.1086/705716"},
        {"evidence_id": "e2", "url": "https://www.science.org/doi/10.1126/science.adj0998"},
        {"evidence_id": "e3", "url": "https://example.com/unrelated"},
    ]
    covered = citation_covered_entity_ids(required, cited_records)
    assert covered == {"acemoglu2020", "eloundou2024"}, (
        "S2 must credit entities whose canonical id matches the cited evidence, and only those"
    )

    # RED: without the citation credit the two cited entities are disclosed as GAPS (0/3 covered).
    red = build_ledger(required, covered_entity_ids=set())
    assert red.coverage_fraction() == pytest.approx(0.0)
    red_gaps = {s.entity_id for s in red.gap_slots()}
    assert {"acemoglu2020", "eloundou2024"} <= red_gaps

    # GREEN: unioning the citation credit flips them to VERIFIED (2/3), raising coverage.
    green = build_ledger(required, covered_entity_ids=set(), extra_covered_ids=covered)
    assert green.coverage_fraction() == pytest.approx(2 / 3)
    green_verified = {s.entity_id for s in green.verified_slots()}
    assert {"acemoglu2020", "eloundou2024"} == green_verified
    # The genuinely-uncited entity is STILL an honest disclosed gap (no over-claim).
    assert {s.entity_id for s in green.gap_slots()} == {"never_cited"}


def test_s2_cited_bibliography_records_excludes_uncited_corpus_ledger_rows():
    """Codex diff-gate P1 (#1344): the S2 credit must be fed ONLY the bibliography rows the report BODY
    actually cites — an UNCITED corpus-ledger row whose URL matches a required entity's DOI must be
    EXCLUDED, so that entity stays an honest disclosed gap instead of being falsely marked covered.

    RED (the flagged bug): feeding EVERY bibliography row would credit the uncited row's DOI and suppress
    the gap. GREEN (the fix): ``s2_cited_bibliography_records`` keeps only rows whose ``num`` is cited in
    the body, so the uncited corpus-ledger row is dropped before the credit runs."""
    from src.polaris_graph.generator.required_entity_ledger import citation_covered_entity_ids

    required = [{"id": "gapped_entity", "severity": "high", "doi": "10.9999/uncited-only"}]
    # The body cites [1] only; [2] is a retrieved-but-uncited corpus-ledger row (appears only as its
    # own bibliography entry line, never as a body citation).
    report_body = (
        "## Key findings\n\nAI raised productivity [1].\n\n"
        "## Bibliography\n"
        "[1] Some cited source — https://example.org/cited (tier T2)\n"
        "[2] Uncited corpus-ledger row — https://doi.org/10.9999/uncited-only (tier T4)\n"
    )
    bibliography = [
        {"num": 1, "evidence_id": "e1", "url": "https://example.org/cited"},
        {"num": 2, "evidence_id": "e2", "url": "https://doi.org/10.9999/uncited-only"},
    ]

    # RED baseline: the WHOLE bibliography would credit the gapped entity via the uncited row.
    all_rows_credit = citation_covered_entity_ids(required, bibliography)
    assert all_rows_credit == {"gapped_entity"}, "confirms the over-credit path the fix must block"

    # GREEN: the cited-only filter drops the uncited row, so NO credit -> the entity stays a gap.
    cited_only = RHS.s2_cited_bibliography_records(bibliography, report_body)
    assert [r["num"] for r in cited_only] == [1], "only the body-cited row [1] survives"
    assert citation_covered_entity_ids(required, cited_only) == set(), (
        "the uncited corpus-ledger row must NOT credit the required entity (no gap suppression)"
    )

    # Fail-safe: an empty/unreadable body credits nothing (under-credit, never suppresses a gap).
    assert RHS.s2_cited_bibliography_records(bibliography, "") == []
