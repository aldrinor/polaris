"""I-cred-008b (#1162) — the SHARED disclosure populate+carrier+coverage helper.

Offline, deterministic, no network. Exercises ``apply_disclosure_to_svs`` directly:
  (c) the EvidenceCredibility -> FLOAT credibility_weight adaptation,
  (d) the P3 certainty downgrade CARRIER (cap certainty + surface soft_warning),
  (e) ``abort_credibility_coverage_gap`` fires on an uncovered cited token (fail-loud),
plus the no-mutation / no-verifier-touch posture the four resolve sites depend on.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.polaris_graph.generator.provenance_generator import SentenceVerification
from src.polaris_graph.synthesis.credibility_pass import (
    CredibilityAnalysis,
    CredibilityPassError,
    EvidenceCredibility,
    apply_disclosure_to_svs,
)


def _sv(sentence, eids, is_verified=True):
    return SentenceVerification(
        sentence=sentence,
        tokens=[SimpleNamespace(evidence_id=e, start=0, end=1) for e in eids],
        is_verified=is_verified,
    )


def _ec(eid, weight, *, downgrade=False, soft_warning=None, origin="o1"):
    return EvidenceCredibility(
        evidence_id=eid,
        credibility_weight=weight,
        reliability_score=weight,
        relevance_score=weight,
        origin_cluster_id=origin,
        is_canonical_origin=True,
        certainty_downgrade=downgrade,
        soft_warning=soft_warning,
    )


def _analysis(ecs, origins):
    return CredibilityAnalysis(
        credibility_by_evidence={ec.evidence_id: ec for ec in ecs},
        origin_by_evidence=dict(origins),
        claims=[],
        edges=[],
        weight_mass=[],
    )


# ── (c) EvidenceCredibility -> FLOAT adaptation ──────────────────────────────
def test_evidence_credibility_to_float_adaptation():
    """The helper must feed populate_disclosure the FLOAT .credibility_weight, not the object.

    Two cited sources at 0.9 / 0.3; MIN over cited = 0.3 proves the float (not the object) reached
    populate_disclosure (an EvidenceCredibility object would have raised or produced None).
    """
    analysis = _analysis(
        [_ec("e0", 0.9, origin="o1"), _ec("e1", 0.3, origin="o2")],
        {"e0": "o1", "e1": "o2"},
    )
    out = apply_disclosure_to_svs([_sv("The rate was 5 percent.", ["e0", "e1"])], analysis)
    assert out[0].span_verdict == "SUPPORTS"
    assert abs(out[0].credibility_weight - 0.3) < 1e-9  # MIN over the FLOAT weights
    assert out[0].independent_origin_count == 2  # two distinct origin clusters


# ── (d) P3 certainty downgrade CARRIER ───────────────────────────────────────
def test_certainty_carrier_caps_and_surfaces_warning():
    """populate_disclosure would compute 'high' (two origins, cred 0.9); the P3 downgrade caps it."""
    analysis = _analysis(
        [
            _ec("e0", 0.9, origin="o1", downgrade=True, soft_warning="superseded by 2026 guideline"),
            _ec("e1", 0.9, origin="o2"),
        ],
        {"e0": "o1", "e1": "o2"},
    )
    out = apply_disclosure_to_svs([_sv("s", ["e0", "e1"])], analysis)
    # Without the carrier this would be 'high'; the P3 downgrade caps it at 'moderate'.
    assert out[0].certainty_label == "moderate"
    assert "superseded by 2026 guideline" in out[0].soft_warnings


def test_certainty_carrier_noop_when_no_downgrade():
    """No cited source downgraded => certainty + soft_warnings unchanged from populate_disclosure."""
    analysis = _analysis(
        [_ec("e0", 0.9, origin="o1"), _ec("e1", 0.9, origin="o2")],
        {"e0": "o1", "e1": "o2"},
    )
    out = apply_disclosure_to_svs([_sv("s", ["e0", "e1"])], analysis)
    assert out[0].certainty_label == "high"
    assert out[0].soft_warnings == []


# ── (e) coverage-gap fail-loud ───────────────────────────────────────────────
def test_coverage_gap_raises_on_uncovered_cited_token():
    """A cited token whose evidence_id is absent from the analysis must FAIL LOUD."""
    analysis = _analysis([_ec("e0", 0.8, origin="o1")], {"e0": "o1"})
    with pytest.raises(CredibilityPassError, match="abort_credibility_coverage_gap"):
        apply_disclosure_to_svs([_sv("s", ["e0", "e_missing"])], analysis)


def test_coverage_gap_raises_when_origin_missing_even_if_cred_present():
    """Coverage requires BOTH credibility AND origin coverage (both maps co-built per row)."""
    analysis = CredibilityAnalysis(
        credibility_by_evidence={"e0": _ec("e0", 0.8, origin="o1")},
        origin_by_evidence={},  # origin coverage missing
        claims=[], edges=[], weight_mass=[],
    )
    with pytest.raises(CredibilityPassError, match="abort_credibility_coverage_gap"):
        apply_disclosure_to_svs([_sv("s", ["e0"])], analysis)


# ── posture: pure + never touches verifier fields ────────────────────────────
def test_helper_is_pure_and_advisory():
    analysis = _analysis([_ec("e0", 0.8, origin="o1")], {"e0": "o1"})
    sv = _sv("s", ["e0"], is_verified=True)
    out = apply_disclosure_to_svs([sv], analysis)
    # input untouched
    assert sv.span_verdict == "" and sv.credibility_weight is None
    assert sv.certainty_label == "" and sv.soft_warnings == []
    # output keeps verifier fields
    assert out[0].is_verified is True
    assert out[0].sentence == sv.sentence and out[0].tokens == sv.tokens


def test_unverified_sentence_gets_unsupported_verdict_low_certainty():
    analysis = _analysis([_ec("e0", 0.9, origin="o1")], {"e0": "o1"})
    out = apply_disclosure_to_svs([_sv("s", ["e0"], is_verified=False)], analysis)
    assert out[0].span_verdict == "UNSUPPORTED"
    assert out[0].certainty_label == "low"


# ── site 4 (quantified): the surfaced telem["claim_disclosure"] rows ─────────
def test_quantified_site_surfaces_disclosure_in_telemetry():
    """run_quantified_section (site 4, no SectionResult) must surface disclosure rows in telem.

    Offline: a deterministic spec_provider + REAL execute/verify. credibility_analysis covers the two
    cited inputs (ev_017, ev_021) so there is no coverage gap; telem['claim_disclosure'] carries the
    per-claim disclosure the runner merges into claim_disclosure.json.
    """
    import asyncio

    from src.polaris_graph.generator.quantified_analysis import run_quantified_section

    evidence_pool = {
        "ev_017": {
            "evidence_id": "ev_017",
            "direct_quote": "The program cost was $1.548 billion in fiscal 2024.",
            "source_url": "https://example.org/a", "tier": "T1",
        },
        "ev_021": {
            "evidence_id": "ev_021",
            "direct_quote": "Annual maintenance is $120 million per year.",
            "source_url": "https://example.org/b", "tier": "T1",
        },
    }

    def _spec(_q, _sourced):
        # Bind each datapoint_ref to the EXACT extracted sourced number (label/context/value),
        # so build_quantified_spec's unique-literal match succeeds. We pick the 1.548e9 / 1.2e8 rows.
        capex = next(d for d in _sourced if d.get("value") == "1548000000.0")
        opex = next(d for d in _sourced if d.get("value") == "120000000.0")
        return {
            "model_id": "tco", "title": "Total cost of ownership",
            "inputs": [
                {"name": "capex", "datapoint_ref": {
                    "ev_id": capex["evidence_id"], "label": capex["label"],
                    "context": capex["context"], "value": capex["value"], "unit": "USD"}},
                {"name": "opex", "datapoint_ref": {
                    "ev_id": opex["evidence_id"], "label": opex["label"],
                    "context": opex["context"], "value": opex["value"], "unit": "USD"}},
                {"name": "years", "base": 5.0, "unit": "years",
                 "sweep": [1.0, 10.0, 1.0], "modeled": True},
            ],
            "outputs": [{"name": "tco", "unit": "USD", "display_kind": "currency",
                         "formula": "capex + opex * years"}],
            "sensitivity": [{"input": "years", "output": "tco"}],
        }

    async def _spec_provider(_q, _s):
        return _spec(_q, _s)

    analysis = _analysis(
        [_ec("ev_017", 0.8, origin="o1"), _ec("ev_021", 0.6, origin="o2")],
        {"ev_017": "o1", "ev_021": "o2"},
    )

    # ON: telem carries the disclosure rows.
    section_md, telem = asyncio.run(run_quantified_section(
        "q", evidence_pool, spec_provider=_spec_provider, credibility_analysis=analysis,
    ))
    assert section_md is not None
    rows = telem.get("claim_disclosure")
    assert rows, "quantified telemetry must surface claim_disclosure rows when analysis present"
    for r in rows:
        assert r["span_verdict"] in ("SUPPORTS", "UNSUPPORTED")
        assert "credibility_weight" in r and "certainty_label" in r

    # OFF (analysis None): no claim_disclosure key (byte-identical telemetry).
    section_md_off, telem_off = asyncio.run(run_quantified_section(
        "q", evidence_pool, spec_provider=_spec_provider, credibility_analysis=None,
    ))
    assert section_md_off is not None
    assert "claim_disclosure" not in telem_off
