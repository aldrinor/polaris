"""I-cred-008b (#1162) — multi-site disclosure wiring smoke (offline, no network).

Proves the populated per-claim disclosure rides through the resolve sites into
``SectionResult.kept_sentences_pre_resolve``, at BOTH:
  * the V30 CONTRACT runner (run_contract_section, site 3/4) — the iter-4 P1-1 multi-site requirement,
  * the FACT-DEDUP re-resolve (site 2/4) — reproduces the edited code path,
and that with ``credibility_analysis=None`` the SVs are byte-identical (no populate).

The LLM is injected (fake); strict_verify + the citation rewriter are REAL (same as live sweeps).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

from src.polaris_graph.synthesis.credibility_pass import (
    CredibilityAnalysis,
    EvidenceCredibility,
    apply_disclosure_to_svs,
)


@pytest.fixture(scope="module")
def clinical_template() -> dict:
    with Path("config/scope_templates/clinical.yaml").open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _stub_fetch_rows(compiled):
    from src.polaris_graph.retrieval.frame_fetcher import FrameRow, ProvenanceClass
    return tuple(
        FrameRow(
            entity_id=b.entity_id,
            entity_type=b.entity_type,
            rendering_slot=b.rendering_slot,
            provenance_class=ProvenanceClass.ABSTRACT_ONLY,
            direct_quote=(
                "SURPASS-2 enrolled N=1879 patients. Primary endpoint: change in "
                "HbA1c at 40 weeks. ETD -0.47% (95% CI -0.59 to -0.35)."
            ),
            quote_source="crossref_abstract",
            doi="10.1056/NEJMoa2107519" if "surpass_2" in b.entity_id else "10.1/stub",
            pmid=None, oa_pdf_url=None, url=None,
            title=f"Title {b.entity_id}", authors=("Smith J",), journal="Lancet",
            year=2021, failure_reason=None, retrieval_attempts=(), retrieval_timings=(),
        )
        for b in compiled.evidence_bindings
    )


def _analysis_covering(evidence_pool: dict, *, downgrade_ids=()) -> CredibilityAnalysis:
    """Build a CredibilityAnalysis covering EVERY evidence_id in the pool (no coverage gap)."""
    cred: dict[str, EvidenceCredibility] = {}
    origin: dict[str, str] = {}
    for i, eid in enumerate(evidence_pool):
        origin[eid] = f"origin_{i}"
        cred[eid] = EvidenceCredibility(
            evidence_id=eid,
            credibility_weight=0.85,
            reliability_score=0.85,
            relevance_score=0.85,
            origin_cluster_id=f"origin_{i}",
            is_canonical_origin=True,
            certainty_downgrade=(eid in downgrade_ids),
            soft_warning=("superseded by a newer source" if eid in downgrade_ids else None),
        )
    return CredibilityAnalysis(
        credibility_by_evidence=cred, origin_by_evidence=origin,
        claims=[], edges=[], weight_mass=[],
    )


async def _fake_llm(prompt: str):
    m = re.search(r"=== REQUIRED FIELDS ===\n.*?\n((?:  - \w+\n)+)", prompt, re.DOTALL)
    if not m:
        return json.dumps({"fields": []}), 500, 200
    required = [
        line.strip("- ").strip()
        for line in m.group(1).strip().splitlines()
        if line.strip().startswith("-")
    ]
    fields = []
    for fname in required:
        if fname == "N":
            fields.append({"field_name": "N", "status": "extracted",
                           "value": "N=1879", "source_span": "N=1879"})
        else:
            fields.append({"field_name": fname, "status": "not_extractable",
                           "value": None, "source_span": None})
    return json.dumps({"fields": fields}), 500, 200


def _build_contract_inputs(clinical_template):
    from src.polaris_graph.generator.contract_section_runner import (
        ContractSectionPlanExt,
        register_frame_rows_into_evidence_pool,
    )
    from src.polaris_graph.nodes.contract_outline import compose_outline_from_contract
    from src.polaris_graph.nodes.frame_compiler import compile_frame

    cf = compile_frame("tirzepatide evidence", clinical_template, "clinical_tirzepatide_t2dm")
    rows = _stub_fetch_rows(cf)
    outline = compose_outline_from_contract(cf, rows)
    section = next(s for s in outline.sections if s.section == "Efficacy")
    plan = ContractSectionPlanExt(
        title=section.section, focus=section.focus,
        ev_ids=[eid for s in section.slots for eid in s.entity_ids],
        slots=section.slots,
        frame_rows_by_entity={r.entity_id: r for r in rows},
        contract_entities_by_id=cf.contract.entities_by_id(),
        research_question="tirzepatide evidence",
    )
    evidence_pool: dict[str, dict[str, Any]] = {}
    register_frame_rows_into_evidence_pool(evidence_pool, rows)
    return plan, evidence_pool


class _SR:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


# ── (b1) contract site: kept SVs carry the disclosure ────────────────────────
@pytest.mark.asyncio
async def test_contract_site_populates_disclosure(clinical_template):
    from src.polaris_graph.generator.contract_section_runner import run_contract_section
    from src.polaris_graph.generator.live_deepseek_generator import _rewrite_draft_with_spans
    from src.polaris_graph.generator.provenance_generator import strict_verify

    plan, evidence_pool = _build_contract_inputs(clinical_template)
    analysis = _analysis_covering(evidence_pool)

    result, _payloads = await run_contract_section(
        plan, evidence_pool,
        llm_call=_fake_llm, section_result_cls=_SR,
        strict_verify_fn=strict_verify, rewrite_fn=_rewrite_draft_with_spans,
        credibility_analysis=analysis,
    )
    kept = result.kept_sentences_pre_resolve
    assert kept, "contract section produced kept SVs"
    # Every kept SV carries the populated disclosure (span_verdict + a certainty bucket).
    for sv in kept:
        assert sv.span_verdict in ("SUPPORTS", "UNSUPPORTED")
        assert sv.certainty_label in ("high", "moderate", "low")
    assert any(sv.credibility_weight is not None for sv in kept), (
        "at least one kept SV must carry a credibility_weight (cited evidence is covered)"
    )


# ── (a) flag-OFF byte-identical at the contract site ─────────────────────────
@pytest.mark.asyncio
async def test_contract_site_flag_off_byte_identical(clinical_template):
    from src.polaris_graph.generator.contract_section_runner import run_contract_section
    from src.polaris_graph.generator.live_deepseek_generator import _rewrite_draft_with_spans
    from src.polaris_graph.generator.provenance_generator import strict_verify

    plan, evidence_pool = _build_contract_inputs(clinical_template)

    result_off, _ = await run_contract_section(
        plan, evidence_pool,
        llm_call=_fake_llm, section_result_cls=_SR,
        strict_verify_fn=strict_verify, rewrite_fn=_rewrite_draft_with_spans,
        credibility_analysis=None,
    )
    # OFF: SVs carry NONE of the disclosure fields (inert defaults), and verified_text is unchanged
    # vs a separate OFF run (determinism check).
    for sv in result_off.kept_sentences_pre_resolve:
        assert sv.span_verdict == ""
        assert sv.credibility_weight is None
        assert sv.independent_origin_count is None
        assert sv.certainty_label == ""

    plan2, pool2 = _build_contract_inputs(clinical_template)
    result_off2, _ = await run_contract_section(
        plan2, pool2,
        llm_call=_fake_llm, section_result_cls=_SR,
        strict_verify_fn=strict_verify, rewrite_fn=_rewrite_draft_with_spans,
        credibility_analysis=None,
    )
    assert result_off.verified_text == result_off2.verified_text


# ── (b2) fact-dedup re-resolve site: reproduce the edited code path ──────────
def test_fact_dedup_site_populates_disclosure():
    """Reproduce the fact-dedup re-resolve block: build final_svs, apply the helper, resolve.

    Mirrors multi_section_generator.py site 2/4 exactly: post-dedup SVs are populated BEFORE the
    local `_resolve(...)` ALIAS, then assigned to kept_sentences_pre_resolve. We assert the populated
    SVs survive resolution (verified_text renders) AND carry the disclosure.
    """
    from src.polaris_graph.generator.provenance_generator import (
        SentenceVerification,
        resolve_provenance_to_citations as _resolve,
        strict_verify,
    )

    quote = "Tirzepatide reduced HbA1c by 2.07 percent at 40 weeks in SURPASS-2."
    evidence_pool = {
        "ev1": {
            "evidence_id": "ev1",
            "direct_quote": quote,  # strict_verify reads direct_quote (or statement), NOT text
            "source_url": "https://example.org/surpass2",
            "tier": "T1",
        },
    }
    # A real kept SV (post-dedup "rewrite") with a valid provenance token over the evidence span.
    sentence = f"Tirzepatide reduced HbA1c by 2.07 percent at 40 weeks in SURPASS-2.[#ev:ev1:0-{len(quote)}]"
    report = strict_verify(sentence, evidence_pool)
    final_svs = list(report.kept_sentences)
    assert final_svs, "the rewrite sentence must pass strict_verify to be a kept post-dedup SV"

    analysis = _analysis_covering(evidence_pool)
    # ── the exact edited site-2 sequence ──
    final_svs = apply_disclosure_to_svs(final_svs, analysis)
    new_text, _new_biblio = _resolve(final_svs, evidence_pool)
    kept_sentences_pre_resolve = list(final_svs)  # the SectionResult assignment

    assert new_text, "resolve produced text"
    assert kept_sentences_pre_resolve[0].span_verdict == "SUPPORTS"
    assert kept_sentences_pre_resolve[0].credibility_weight is not None
    assert kept_sentences_pre_resolve[0].certainty_label in ("high", "moderate", "low")

    # flag-OFF parity: the SAME SVs without the helper carry no disclosure.
    report_off = strict_verify(sentence, evidence_pool)
    off_svs = list(report_off.kept_sentences)
    assert off_svs[0].span_verdict == "" and off_svs[0].credibility_weight is None


# ── (e at a resolve site) coverage gap fires fail-loud at the contract site ──
@pytest.mark.asyncio
async def test_contract_site_coverage_gap_fires(clinical_template):
    from src.polaris_graph.generator.contract_section_runner import run_contract_section
    from src.polaris_graph.generator.live_deepseek_generator import _rewrite_draft_with_spans
    from src.polaris_graph.generator.provenance_generator import strict_verify
    from src.polaris_graph.synthesis.credibility_pass import CredibilityPassError

    plan, evidence_pool = _build_contract_inputs(clinical_template)
    # An analysis covering a DIFFERENT, irrelevant evidence_id => every cited token is uncovered.
    empty_analysis = CredibilityAnalysis(
        credibility_by_evidence={
            "unrelated_ev": EvidenceCredibility(
                evidence_id="unrelated_ev", credibility_weight=0.5,
                reliability_score=0.5, relevance_score=0.5,
                origin_cluster_id="oX", is_canonical_origin=True,
                certainty_downgrade=False, soft_warning=None,
            )
        },
        origin_by_evidence={"unrelated_ev": "oX"},
        claims=[], edges=[], weight_mass=[],
    )
    with pytest.raises(CredibilityPassError, match="abort_credibility_coverage_gap"):
        await run_contract_section(
            plan, evidence_pool,
            llm_call=_fake_llm, section_result_cls=_SR,
            strict_verify_fn=strict_verify, rewrite_fn=_rewrite_draft_with_spans,
            credibility_analysis=empty_analysis,
        )


# ── (d at a resolve site) certainty carrier rides through the contract site ──
@pytest.mark.asyncio
async def test_contract_site_certainty_carrier(clinical_template):
    from src.polaris_graph.generator.contract_section_runner import run_contract_section
    from src.polaris_graph.generator.live_deepseek_generator import _rewrite_draft_with_spans
    from src.polaris_graph.generator.provenance_generator import strict_verify

    plan, evidence_pool = _build_contract_inputs(clinical_template)
    # Downgrade every cited source: every kept SV's certainty must be capped (never "high")
    # and carry the soft_warning.
    analysis = _analysis_covering(evidence_pool, downgrade_ids=tuple(evidence_pool.keys()))

    result, _ = await run_contract_section(
        plan, evidence_pool,
        llm_call=_fake_llm, section_result_cls=_SR,
        strict_verify_fn=strict_verify, rewrite_fn=_rewrite_draft_with_spans,
        credibility_analysis=analysis,
    )
    kept = result.kept_sentences_pre_resolve
    assert kept
    for sv in kept:
        assert sv.certainty_label != "high", "P3 downgrade must cap certainty below high"
        assert "superseded by a newer source" in (sv.soft_warnings or [])
