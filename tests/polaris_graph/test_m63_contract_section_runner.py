"""V30 Phase-2 M-63 contract section runner tests.

Exercises the new `_run_contract_section` dispatch path without
running the full multi_section_generator or hitting the network.
The LLM call is injected via the `llm_call` parameter; strict_verify
and the citation rewriter are real (same pipeline used in live
sweeps).

All tests pure — no network, no real LLM.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml


# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def clinical_template() -> dict:
    with Path("config/scope_templates/clinical.yaml").open(
        "r", encoding="utf-8",
    ) as f:
        return yaml.safe_load(f)


def _stub_fetch_rows(compiled):
    from src.polaris_graph.retrieval.frame_fetcher import (
        FrameRow, ProvenanceClass,
    )
    return tuple(
        FrameRow(
            entity_id=b.entity_id,
            entity_type=b.entity_type,
            rendering_slot=b.rendering_slot,
            provenance_class=ProvenanceClass.ABSTRACT_ONLY,
            direct_quote=(
                "SURPASS-2 enrolled N=1879 patients. Primary "
                "endpoint: change in HbA1c at 40 weeks. ETD "
                "-0.47% (95% CI -0.59 to -0.35)."
            ),
            quote_source="crossref_abstract",
            doi="10.1056/NEJMoa2107519" if "surpass_2" in b.entity_id
                else "10.1/stub",
            pmid=None,
            oa_pdf_url=None,
            url=None,
            title=f"Title {b.entity_id}",
            authors=("Smith J",),
            journal="Lancet",
            year=2021,
            failure_reason=None,
            retrieval_attempts=(),
            retrieval_timings=(),
        )
        for b in compiled.evidence_bindings
    )


# ─────────────────────────────────────────────────────────────────────
# (1) register_frame_rows_into_evidence_pool
# ─────────────────────────────────────────────────────────────────────
class TestRegisterFrameRows:
    def test_registers_by_entity_id(self) -> None:
        from src.polaris_graph.generator.contract_section_runner import (
            register_frame_rows_into_evidence_pool,
        )
        from src.polaris_graph.retrieval.frame_fetcher import (
            FrameRow, ProvenanceClass,
        )
        pool: dict[str, dict[str, Any]] = {}
        rows = (
            FrameRow(
                entity_id="surpass_2_primary",
                entity_type="pivotal_trial",
                rendering_slot="efficacy_surpass_2",
                provenance_class=ProvenanceClass.ABSTRACT_ONLY,
                direct_quote="content",
                quote_source="crossref_abstract",
                doi="10.1/x", pmid=None, oa_pdf_url=None, url=None,
                title="T", authors=(), journal=None, year=None,
                failure_reason=None, retrieval_attempts=(),
                retrieval_timings=(),
            ),
        )
        register_frame_rows_into_evidence_pool(pool, rows)
        assert "surpass_2_primary" in pool
        entry = pool["surpass_2_primary"]
        assert entry["evidence_id"] == "surpass_2_primary"
        assert entry["direct_quote"] == "content"
        assert entry["v30_frame_row"] is True


# ─────────────────────────────────────────────────────────────────────
# (2) _fill_one_slot
# ─────────────────────────────────────────────────────────────────────
class TestFillOneSlot:
    @pytest.mark.asyncio
    async def test_gap_row_skips_llm(self) -> None:
        from src.polaris_graph.generator.contract_section_runner import (
            _fill_one_slot,
        )
        from src.polaris_graph.nodes.contract_outline import (
            ContractSlotPlan,
        )
        from src.polaris_graph.nodes.report_contract import (
            RequiredEntity,
        )
        from src.polaris_graph.retrieval.frame_fetcher import (
            FrameRow, ProvenanceClass,
        )
        slot = ContractSlotPlan(
            slot_id="s1", section="Efficacy",
            subsection_title="SURPASS-CVOT",
            ordering=1, entity_ids=("e_cvot",),
            provenance_classes=("frame_gap_unrecoverable",),
            is_gap=True, is_partial=False,
        )
        row = FrameRow(
            entity_id="e_cvot",
            entity_type="pivotal_trial",
            rendering_slot="s1",
            provenance_class=ProvenanceClass.FRAME_GAP_UNRECOVERABLE,
            direct_quote="",
            quote_source="none",
            doi=None, pmid=None, oa_pdf_url=None, url=None,
            title=None, authors=(), journal=None, year=None,
            failure_reason="paywall",
            retrieval_attempts=(), retrieval_timings=(),
        )
        entity = RequiredEntity(
            id="e_cvot",
            type="pivotal_trial",
            required_fields=("N", "primary_endpoint"),
            min_fields_for_completion=1,
            rendering_slot="s1",
            doi=None,
        )
        calls = []
        async def _should_not_be_called(prompt: str):
            calls.append(prompt)
            return "{}", 0, 0
        payload, in_tok, out_tok = await _fill_one_slot(
            slot, "e_cvot", row, entity, "q",
            _should_not_be_called,
        )
        # Gap path: LLM never called
        assert calls == []
        assert in_tok == 0 and out_tok == 0
        # All fields gap_unrecoverable
        assert all(
            f.status == "gap_unrecoverable" for f in payload.fields
        )

    @pytest.mark.asyncio
    async def test_non_gap_calls_llm_and_parses(self) -> None:
        from src.polaris_graph.generator.contract_section_runner import (
            _fill_one_slot,
        )
        from src.polaris_graph.nodes.contract_outline import (
            ContractSlotPlan,
        )
        from src.polaris_graph.nodes.report_contract import (
            RequiredEntity,
        )
        from src.polaris_graph.retrieval.frame_fetcher import (
            FrameRow, ProvenanceClass,
        )
        slot = ContractSlotPlan(
            slot_id="efficacy_surpass_2", section="Efficacy",
            subsection_title="SURPASS-2",
            ordering=2, entity_ids=("surpass_2_primary",),
            provenance_classes=("abstract_only",),
            is_gap=False, is_partial=False,
        )
        row = FrameRow(
            entity_id="surpass_2_primary",
            entity_type="pivotal_trial",
            rendering_slot="efficacy_surpass_2",
            provenance_class=ProvenanceClass.ABSTRACT_ONLY,
            direct_quote="SURPASS-2 enrolled N=1879 patients.",
            quote_source="crossref_abstract",
            doi="10.1056/NEJMoa2107519", pmid=None, oa_pdf_url=None, url=None,
            title="SURPASS-2", authors=("Frias JP",),
            journal="NEJM", year=2021,
            failure_reason=None,
            retrieval_attempts=(), retrieval_timings=(),
        )
        entity = RequiredEntity(
            id="surpass_2_primary",
            type="pivotal_trial",
            required_fields=("N", "primary_endpoint"),
            min_fields_for_completion=1,
            rendering_slot="efficacy_surpass_2",
        )
        async def _fake_llm(prompt: str):
            # Simulate LLM returning valid slot-fill JSON
            response = json.dumps({
                "fields": [
                    {"field_name": "N", "status": "extracted",
                     "value": "N=1879", "source_span": "N=1879"},
                    {"field_name": "primary_endpoint",
                     "status": "not_extractable",
                     "value": None, "source_span": None},
                ]
            })
            return response, 250, 100
        payload, in_tok, out_tok = await _fill_one_slot(
            slot, "surpass_2_primary", row, entity, "q",
            _fake_llm,
        )
        assert in_tok == 250
        assert out_tok == 100
        assert payload.completion_count() == 1


# ─────────────────────────────────────────────────────────────────────
# (3) run_contract_section end-to-end
# ─────────────────────────────────────────────────────────────────────
class TestRunContractSection:
    @pytest.mark.asyncio
    async def test_end_to_end_single_slot_single_entity(
        self, clinical_template: dict,
    ) -> None:
        """Compile + fetch + build ContractSectionPlanExt + run
        section → verify strict_verify returns kept sentences."""
        from src.polaris_graph.generator.contract_section_runner import (
            ContractSectionPlanExt,
            register_frame_rows_into_evidence_pool,
            run_contract_section,
        )
        from src.polaris_graph.generator.live_deepseek_generator import (
            _rewrite_draft_with_spans,
        )
        from src.polaris_graph.generator.provenance_generator import (
            strict_verify,
        )
        from src.polaris_graph.nodes.contract_outline import (
            compose_outline_from_contract,
        )
        from src.polaris_graph.nodes.frame_compiler import compile_frame

        # Stub SectionResult duck-typed class matching the real
        # shape (dataclass fields consumed by run_contract_section)
        class _SR:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)

        cf = compile_frame(
            "tirzepatide evidence", clinical_template,
            "clinical_tirzepatide_t2dm",
        )
        rows = _stub_fetch_rows(cf)
        outline = compose_outline_from_contract(cf, rows)

        # Build one ContractSectionPlanExt for the Efficacy section
        section = next(s for s in outline.sections if s.section == "Efficacy")
        plan = ContractSectionPlanExt(
            title=section.section,
            focus=section.focus,
            ev_ids=[eid for s in section.slots for eid in s.entity_ids],
            slots=section.slots,
            frame_rows_by_entity={r.entity_id: r for r in rows},
            contract_entities_by_id=cf.contract.entities_by_id(),
            research_question="tirzepatide evidence",
        )

        evidence_pool: dict[str, dict[str, Any]] = {}
        register_frame_rows_into_evidence_pool(evidence_pool, rows)
        assert "surpass_2_primary" in evidence_pool

        async def _fake_llm(prompt: str):
            """Contract-aware fake LLM: reads the REQUIRED FIELDS
            list from the prompt and emits one extracted field
            (N) plus not_extractable for the rest. This mirrors
            a realistic LLM that couldn't extract every field
            from a 3-sentence abstract."""
            # Extract required fields from the prompt
            m = re.search(
                r"=== REQUIRED FIELDS ===\n.*?\n((?:  - \w+\n)+)",
                prompt, re.DOTALL,
            )
            if not m:
                return json.dumps({"fields": []}), 500, 200
            required_fields = [
                line.strip("- ").strip()
                for line in m.group(1).strip().splitlines()
                if line.strip().startswith("-")
            ]
            fields = []
            for fname in required_fields:
                if fname == "N":
                    fields.append({
                        "field_name": "N",
                        "status": "extracted",
                        "value": "N=1879",
                        "source_span": "N=1879",
                    })
                else:
                    fields.append({
                        "field_name": fname,
                        "status": "not_extractable",
                        "value": None,
                        "source_span": None,
                    })
            response = json.dumps({"fields": fields})
            return response, 500, 200

        result, payloads = await run_contract_section(
            plan, evidence_pool,
            llm_call=_fake_llm,
            section_result_cls=_SR,
            strict_verify_fn=strict_verify,
            rewrite_fn=_rewrite_draft_with_spans,
        )
        assert result.title == "Efficacy"
        # Payload per entity — efficacy section has 8 SURPASS trials
        assert len(payloads) == 8
        # Every payload cites its bound_ev_id
        for p in payloads:
            assert p.bound_ev_id == p.entity_id
        # Some sentences MUST pass strict_verify (at least the
        # extracted-field sentences for SURPASS-2)
        assert result.sentences_verified > 0
        # Verified text contains `[#ev:...:start-end]` span tokens
        # (or the pre-verified form with raw entity ids)
        assert any(
            tag in result.verified_text
            for tag in ["[#ev:", "[surpass_"]
        )


# ─────────────────────────────────────────────────────────────────────
# (4) Dispatch helper
# ─────────────────────────────────────────────────────────────────────
class TestDispatch:
    def test_is_contract_section_detects_ext(self) -> None:
        from src.polaris_graph.generator.contract_section_runner import (
            ContractSectionPlanExt,
            is_contract_section,
        )
        from src.polaris_graph.generator.multi_section_generator import (
            SectionPlan,
        )
        legacy = SectionPlan(title="Efficacy", focus="x", ev_ids=[])
        assert is_contract_section(legacy) is False

        ext = ContractSectionPlanExt(
            title="Efficacy", focus="x", ev_ids=[],
            slots=(), frame_rows_by_entity={},
            contract_entities_by_id={}, research_question="q",
        )
        assert is_contract_section(ext) is True
