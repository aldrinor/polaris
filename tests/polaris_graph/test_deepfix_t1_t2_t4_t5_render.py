"""I-deepfix-001 (#1344) — behavioural RED->GREEN tests for the CORE render fixes T1/T2/T4/T5.

Each test proves the EFFECT in real composed/rendered output (not a flag tautology):

  T1  the per-claim Layer-2 corroboration surface renders EVERY distinct-origin verified source as
      the report's own numbered ``[N]`` citation on the claim (DeepTRACE #8 thoroughness attribution).
  T2  the rendered bibliography is TYPED — cited references stay under "## Bibliography"; retrieved-
      but-uncited corpus rows move to a typed corpus-ledger audit appendix (no source dropped).
  T4  a literal_span whose offset does not slice back to its raw literal is REJECTED fail-closed
      (DeepTRACE #7 citation-accuracy; faithfulness-strengthening).
  T5  the reliability/audit MACHINERY renders as a trailing typed APPENDIX, not a body PREPEND, so
      the scored body opens on a real claim (DeepTRACE #3 relevant-statement denominator).

All offline ($0): pure functions + a faked spec_llm. No network, no model, no GPU.
"""
from __future__ import annotations

import pytest

from scripts.run_honest_sweep_r3 import (
    _CORPUS_LEDGER_HEADER,
    _basket_corroboration_block,
    cited_reference_numbers,
    compose_report_with_reliability,
    render_reliability_header_md,
    split_bibliography_section_by_citation,
)
from src.polaris_graph.synthesis import tradeoff_modeler
from src.polaris_graph.synthesis.tradeoff_modeler import (
    build_quantified_spec,
    literal_span_is_faithful,
)


# ─────────────────────────────────────────────────────────────────────────────
# T1 — full basket rendered as numbered multi-citation on the claim
# ─────────────────────────────────────────────────────────────────────────────
def _three_source_bibliography() -> list[dict]:
    """A 3-source corroborated basket attached to a numbered bibliography (nums 1/2/3)."""
    members = [
        {
            "member_tier": "ENTAILMENT_VERIFIED", "evidence_id": f"ev{i}",
            "source_url": f"https://example.org/src{i}", "source_tier": f"T{i}",
            "credibility_weight": 0.9 - 0.1 * i, "origin_cluster_id": f"oc{i}",
            "span_verdict": "SUPPORTS",
        }
        for i in (1, 2, 3)
    ]
    basket = {
        "claim_cluster_id": "clm_labor_productivity",
        "claim_text": "Generative AI assistants raise measured worker productivity in support tasks.",
        "subject": "Generative AI assistants",
        "predicate": "raise measured worker productivity",
        "supporting_members": members,
        "verified_support_origin_count": 3,
        "basket_verdict": "corroborated",
        "refuter_cluster_ids": [],
    }
    return [
        {"evidence_id": "ev1", "num": 1, "url": "https://example.org/src1",
         "statement": "Source one", "baskets": [basket]},
        {"evidence_id": "ev2", "num": 2, "url": "https://example.org/src2",
         "statement": "Source two", "baskets": []},
        {"evidence_id": "ev3", "num": 3, "url": "https://example.org/src3",
         "statement": "Source three", "baskets": []},
    ]


def test_t1_layer2_renders_all_distinct_origin_citations(monkeypatch):
    """T1 GREEN: with the Layer-2 cite gate ON, the corroboration header carries [1][2][3] and each
    SUPPORT bullet carries its own [N] — the whole 3-source basket is attributed to the claim."""
    monkeypatch.setenv("PG_CORROBORATION_LAYER2_CITE", "1")
    out = _basket_corroboration_block(_three_source_bibliography())
    assert out, "expected a rendered corroboration block for a 3-source basket"
    assert "3 verified independent source(s)" in out
    # Header carries the full multi-citation of the claim.
    assert "[1][2][3]" in out, f"header must cite the whole basket; got:\n{out}"
    # Each SUPPORT bullet is bound to its numbered reference (marker after the locator, so the
    # legacy ``SUPPORT: <url>`` prefix is preserved).
    assert "https://example.org/src1 [1]" in out
    assert "https://example.org/src2 [2]" in out
    assert "https://example.org/src3 [3]" in out


def test_t6_policy_collapses_same_origin_mirror_on_the_claim(monkeypatch):
    """T6 PRODUCTION WIRING (#1344): the corroboration render consumes the citation-layer POLICY
    (``split_basket_citation_layers(supports_members=...)``), so two verified SUPPORTS members sharing
    ONE origin_cluster_id but sitting at DIFFERENT bibliography numbers are collapsed to ONE citation
    on the claim. This is the genuine rendered EFFECT that proves the policy is not dead code: the prior
    local num-set derivation double-cited the mirror ([1][2]); the policy origin-dedup cites it once
    ([1]). A revert of the wiring re-introduces [2], failing this test. Distinct origins are unaffected
    (see test_t1_layer2_renders_all_distinct_origin_citations)."""
    monkeypatch.setenv("PG_CORROBORATION_LAYER2_CITE", "1")
    monkeypatch.setenv("PG_CITATION_TWO_LAYER_POLICY", "1")
    members = [
        {"member_tier": "ENTAILMENT_VERIFIED", "evidence_id": "evA", "source_url": "https://a.org/x",
         "source_tier": "T1", "credibility_weight": 0.9, "origin_cluster_id": "oc_same",
         "span_verdict": "SUPPORTS"},
        # SAME origin_cluster_id as evA (a mirror of one paper), but a DIFFERENT bibliography number.
        {"member_tier": "ENTAILMENT_VERIFIED", "evidence_id": "evA_mirror",
         "source_url": "https://mirror.org/x", "source_tier": "T3", "credibility_weight": 0.5,
         "origin_cluster_id": "oc_same", "span_verdict": "SUPPORTS"},
    ]
    basket = {
        "claim_cluster_id": "clm_mirror",
        "claim_text": "Generative AI assistants raise measured worker productivity in support tasks.",
        "subject": "Generative AI assistants",
        "predicate": "raise measured worker productivity",
        "supporting_members": members,
        "verified_support_origin_count": 1,
        "basket_verdict": "corroborated",
        "refuter_cluster_ids": [],
    }
    biblio = [
        {"evidence_id": "evA", "num": 1, "url": "https://a.org/x", "statement": "S1", "baskets": [basket]},
        {"evidence_id": "evA_mirror", "num": 2, "url": "https://mirror.org/x", "statement": "S2",
         "baskets": []},
    ]
    out = _basket_corroboration_block(biblio)
    assert out
    # The same-origin mirror is collapsed: the claim is cited ONCE ([1]), never [1][2], and [2] never
    # renders as a corroboration citation (the mirror still lives in the numbered Bibliography).
    assert "[1]" in out
    assert "[1][2]" not in out, f"same-origin mirror must not double-cite the claim; got:\n{out}"
    assert "[2]" not in out, f"the same-origin mirror's [2] must not render as corroboration; got:\n{out}"


def test_t1_layer2_off_is_bare_urls_no_markers(monkeypatch):
    """T1 RED (pre-fix behaviour): with the gate OFF the corroboration bullets carry NO [N] markers,
    so a multi-source basket earns no statement-citation attribution (the defect T1 closes)."""
    monkeypatch.setenv("PG_CORROBORATION_LAYER2_CITE", "0")
    out = _basket_corroboration_block(_three_source_bibliography())
    assert out
    assert "[1][2][3]" not in out
    assert "SUPPORT [1]:" not in out
    assert "SUPPORT:" in out  # legacy bare bullet


# ─────────────────────────────────────────────────────────────────────────────
# T2 — cited references vs typed corpus-ledger audit appendix
# ─────────────────────────────────────────────────────────────────────────────
_BIBLIO_BLOCK = (
    "\n\n## Bibliography\n"
    "[1] Acemoglu & Restrepo — https://doi.org/10.1086/705716 (tier T1)\n"
    "[2] Eloundou et al. — https://doi.org/10.1126/science.adj0998 (tier T1)\n"
    "[3] A retrieved-but-uncited corpus row — https://example.org/x (tier T4)\n"
)


def test_t2_cited_reference_numbers_excludes_entry_lines():
    """T2: the cited set is body citations only — a [N] that is a bibliography ENTRY line
    (``^[N] ...``) is NOT counted as a citation of that source."""
    report = (
        "## Key findings\n\nProductivity rose [1] and exposure was measured [2].\n"
        + _BIBLIO_BLOCK
    )
    cited = cited_reference_numbers(report)
    assert cited == {1, 2}, cited  # [3] appears only as its own entry line => uncited


def test_t2_split_moves_uncited_to_ledger_keeps_all():
    """T2 GREEN: the uncited entry [3] moves under the typed corpus-ledger appendix; cited [1][2]
    stay under Bibliography; every entry survives exactly once (no source dropped)."""
    retyped = split_bibliography_section_by_citation(_BIBLIO_BLOCK, {1, 2})
    assert _CORPUS_LEDGER_HEADER in retyped
    # Cited entries remain under the reference list (before the ledger header).
    ref_part, _, ledger_part = retyped.partition(_CORPUS_LEDGER_HEADER)
    assert "[1] Acemoglu" in ref_part and "[2] Eloundou" in ref_part
    assert "[3] A retrieved-but-uncited" in ledger_part
    assert "[3] A retrieved-but-uncited" not in ref_part
    # No source dropped: all three entries still present exactly once overall.
    for n in (1, 2, 3):
        assert retyped.count(f"[{n}] ") == 1


def test_t2_all_cited_is_byte_identical():
    """T2: when every entry is cited there is no ledger and the block is byte-identical."""
    assert split_bibliography_section_by_citation(_BIBLIO_BLOCK, {1, 2, 3}) == _BIBLIO_BLOCK


# ─────────────────────────────────────────────────────────────────────────────
# T4 — literal_span faithfulness invariant (fail-closed)
# ─────────────────────────────────────────────────────────────────────────────
def test_t4_literal_span_is_faithful_helper():
    """T4: the load-bearing invariant — a span must slice back to exactly its literal."""
    ev = "Brynjolfsson et al. reported a 14 percent gain"
    good_start = ev.index("14")
    assert literal_span_is_faithful(ev, "14", good_start, good_start + 2) is True
    # The F2 defect: an offset landing inside the surname 'Brynjolfsson'.
    assert literal_span_is_faithful(ev, "14", 40, 43) is False
    # Out-of-range / inverted offsets are unfaithful, not a crash.
    assert literal_span_is_faithful(ev, "14", -1, 2) is False
    assert literal_span_is_faithful(ev, "14", 5, 3) is False
    assert literal_span_is_faithful(ev, "14", 0, 9999) is False


def _minimal_spec():
    return {
        "model_id": "m1",
        "title": "t",
        "inputs": [
            {"name": "x", "datapoint_ref": {
                "ev_id": "ev1", "value": 14, "unit": "", "label": "", "context": ""}}
        ],
        "outputs": [{"name": "y", "formula": "x"}],
    }


def test_t4_frame_drift_span_is_rejected_fail_closed(monkeypatch):
    """T4 RED->GREEN integration: when span derivation returns a drifted offset (does not slice back
    to the literal), build_quantified_spec REJECTS fail-closed with ``literal_span_frame_drift``
    instead of emitting a citation whose span points at unrelated text."""
    monkeypatch.setenv("PG_LITERAL_SPAN_ENFORCE", "1")
    # Force a drifted span: literal "14" but offsets [0,3] slice ev_text to 'Bry...' (mid-surname).
    monkeypatch.setattr(
        tradeoff_modeler, "_locate_unique_literal", lambda text, val: ("14", 0, 3)
    )
    reasons: list[str] = []
    spec = build_quantified_spec(
        "q",
        [{"evidence_id": "ev1", "value": "14", "unit": "", "label": "", "context": ""}],
        {"ev1": {"direct_quote": "Brynjolfsson reported 14 percent"}},
        spec_llm=lambda *_: _minimal_spec(),
        on_reject=reasons.append,
    )
    assert spec is None
    assert any(r.startswith("literal_span_frame_drift") for r in reasons), reasons


def test_t4_enforce_off_does_not_reject_on_drift(monkeypatch):
    """T4: the kill-switch OFF path does not raise the frame-drift rejection (pre-fix behaviour)."""
    monkeypatch.setenv("PG_LITERAL_SPAN_ENFORCE", "0")
    monkeypatch.setattr(
        tradeoff_modeler, "_locate_unique_literal", lambda text, val: ("14", 0, 3)
    )
    reasons: list[str] = []
    build_quantified_spec(
        "q",
        [{"evidence_id": "ev1", "value": "14", "unit": "", "label": "", "context": ""}],
        {"ev1": {"direct_quote": "Brynjolfsson reported 14 percent"}},
        spec_llm=lambda *_: _minimal_spec(),
        on_reject=reasons.append,
    )
    assert not any(r.startswith("literal_span_frame_drift") for r in reasons), reasons


# ─────────────────────────────────────────────────────────────────────────────
# T5 — reliability/audit machinery -> trailing typed appendix
# ─────────────────────────────────────────────────────────────────────────────
_RELIABILITY = render_reliability_header_md(
    {"claims_total": 10, "claims_with_verified_support": 8,
     "claims_multi_source_corroborated": 2, "claims_single_origin": 6}
)
_BODY = "# Research report: does AI raise productivity?\n\nGenerative AI raises productivity [1].\n"


def test_t5_machinery_is_trailing_appendix_by_default(monkeypatch):
    """T5 GREEN: the scored body comes first (opens on the report title/claim); the reliability
    machinery renders AFTER it, under a typed appendix boundary."""
    monkeypatch.setenv("PG_AUDIT_MACHINERY_APPENDIX", "1")
    out = compose_report_with_reliability(_BODY, _RELIABILITY)
    assert out.startswith("# Research report:"), "body must open the report"
    boundary = "## Appendix: audit, disclosure, and weighting (not scored as report claims)"
    assert boundary in out
    # Ordering: the body claim precedes the appendix boundary precedes the reliability counts.
    assert out.index("raises productivity [1]") < out.index(boundary)
    assert out.index(boundary) < out.index("Reliability header")
    # Nothing dropped — the counts still ship.
    assert "Evidence-pool claim clusters (total): 10" in out


def test_t5_off_is_legacy_prepend(monkeypatch):
    """T5 RED (pre-fix): with the gate OFF the machinery is PREPENDED — the report opens on the
    reliability counts, exactly the #3 relevant-statement pollution T5 removes."""
    monkeypatch.setenv("PG_AUDIT_MACHINERY_APPENDIX", "0")
    out = compose_report_with_reliability(_BODY, _RELIABILITY)
    assert out.lstrip().startswith("## Reliability header")
    assert out.index("Reliability header") < out.index("raises productivity [1]")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
