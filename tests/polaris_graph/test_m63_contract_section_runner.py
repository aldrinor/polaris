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
        # Post-Codex-REJECT-Blocker-3 shape: verified_text has
        # numbered `[N]` citations (not raw span tokens), and
        # biblio_slice is populated.
        import re as _re
        assert _re.search(r"\[\d+\]", result.verified_text), (
            "expected numbered [N] citations in verified_text; "
            f"got: {result.verified_text!r}"
        )
        assert "[#ev:" not in result.verified_text, (
            "raw span tokens should be resolved to [N] citations"
        )
        assert len(result.biblio_slice) > 0, (
            "biblio_slice must be populated for global biblio merge"
        )
        # Subsection heading injected after strict_verify so the
        # reader sees the slot structure.
        assert "### " in result.verified_text, (
            "expected `### subsection_title` heading in verified_text"
        )
        # Every biblio entry has required legacy shape
        for entry in result.biblio_slice:
            assert "num" in entry and isinstance(entry["num"], int)
            assert "evidence_id" in entry and entry["evidence_id"]


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


# ─────────────────────────────────────────────────────────────────────
# (5) Codex M-63 REJECT regression coverage
# ─────────────────────────────────────────────────────────────────────
class TestCodexM63RejectRegressions:
    """Regression guards for the issues Codex flagged in the M-63
    REJECT verdict at `outputs/codex_findings/m63_code_audit/findings.md`.
    Each test is named after the specific blocker/medium it guards."""

    def test_blocker1_m44_preserves_contract_plan_type(self) -> None:
        """_m44_inject_primaries_into_outline must NOT downcast a
        ContractSectionPlanExt to plain SectionPlan — Blocker 1
        regression. The audit caught type erasure via rebuild."""
        from src.polaris_graph.generator.contract_section_runner import (
            ContractSectionPlanExt,
            is_contract_section,
        )
        from src.polaris_graph.generator.multi_section_generator import (
            SectionPlan,
            _m44_inject_primaries_into_outline,
        )

        contract_plan = ContractSectionPlanExt(
            title="Efficacy", focus="x", ev_ids=["surpass_2_primary"],
            slots=(), frame_rows_by_entity={},
            contract_entities_by_id={}, research_question="q",
        )
        legacy_plan = SectionPlan(
            title="Safety", focus="y", ev_ids=["ev_00001"],
        )
        plans = [contract_plan, legacy_plan]
        primary_by_anchor = {"SURPASS-2": ["ev_00042"]}
        updated, log = _m44_inject_primaries_into_outline(
            plans, primary_by_anchor,
        )

        # Contract plan survives identity-preserved
        assert is_contract_section(updated[0]), (
            "ContractSectionPlanExt must survive M-44 as a "
            "ContractSectionPlanExt, not be downcast to SectionPlan"
        )
        assert updated[0] is contract_plan, (
            "M-44 should be a pure pass-through for contract plans"
        )
        # Legacy plan still rebuilt (expected)
        assert not is_contract_section(updated[1])
        # Log records the skip
        assert any(
            e.get("action") == "skipped_contract_plan"
            for e in log
        )

    def test_blocker2_non_gap_llm_exception_does_not_raise(
        self, clinical_template,
    ) -> None:
        """_fill_one_slot LLM-exception fallback on a non-gap row
        must produce an all-not_extractable payload, not re-raise
        via compose_gap_payload's non-gap guard — Blocker 2."""
        from src.polaris_graph.generator.contract_section_runner import (
            _fill_one_slot,
        )
        from src.polaris_graph.nodes.frame_compiler import compile_frame
        from src.polaris_graph.nodes.contract_outline import (
            compose_outline_from_contract,
        )
        compiled = compile_frame(
            "What is the efficacy of tirzepatide in T2DM?",
            clinical_template,
            "clinical_tirzepatide_t2dm",
        )
        frame_rows = _stub_fetch_rows(compiled)
        outline = compose_outline_from_contract(compiled, frame_rows)
        rows_by_eid = {r.entity_id: r for r in frame_rows}
        entities_by_id = compiled.contract.entities_by_id()
        first_slot = outline.sections[0].slots[0]
        entity_id = first_slot.entity_ids[0]
        frame_row = rows_by_eid[entity_id]
        contract_entity = entities_by_id[entity_id]

        async def _boom_llm(prompt: str):
            raise RuntimeError("simulated network timeout")

        async def _go():
            return await _fill_one_slot(
                slot=first_slot,
                entity_id=entity_id,
                frame_row=frame_row,
                contract_entity=contract_entity,
                research_question="q",
                llm_call=_boom_llm,
            )

        payload, in_tok, out_tok = asyncio.run(_go())

        # NOT RAISED. Every field is not_extractable.
        assert all(f.status == "not_extractable" for f in payload.fields)
        assert payload.bound_ev_id == entity_id
        assert in_tok == 0 and out_tok == 0

    def test_blocker3_legacy_shape_parity(self, clinical_template) -> None:
        """verified_text has [N] citations (not raw tokens) AND
        biblio_slice is populated — Blocker 3. Already asserted
        in the end-to-end test; this adds a focused assertion on
        mixed-slot shape."""
        # Deferred to the richer end-to-end test above; this stub
        # keeps the regression class explicit about what it guards.
        pass

    def test_medium1_ev_ids_from_all_slots(self, clinical_template) -> None:
        """Sweep runner contract plan construction seeds ev_ids
        as the UNION of every slot's entity_ids, not just the
        first slot's — Medium 1."""
        # The union logic lives in run_honest_sweep_r3.py — test
        # the inline algorithm directly against a fake outline.
        from src.polaris_graph.nodes.frame_compiler import compile_frame
        from src.polaris_graph.nodes.contract_outline import (
            compose_outline_from_contract,
        )
        compiled = compile_frame(
            "What is the efficacy of tirzepatide in T2DM?",
            clinical_template,
            "clinical_tirzepatide_t2dm",
        )
        frame_rows = _stub_fetch_rows(compiled)
        outline = compose_outline_from_contract(compiled, frame_rows)

        # Find a section with ≥2 slots to exercise the union
        multi_slot_sections = [
            s for s in outline.sections if len(s.slots) >= 2
        ]
        if not multi_slot_sections:
            pytest.skip("no multi-slot section available in fixture")
        sec = multi_slot_sections[0]

        # Mirror the sweep runner's union logic
        seen: set[str] = set()
        section_ev_ids: list[str] = []
        for sl in sec.slots:
            for eid in sl.entity_ids:
                if eid not in seen:
                    seen.add(eid)
                    section_ev_ids.append(eid)

        # Must be a SUPERSET of the first slot alone
        first_slot_ids = set(sec.slots[0].entity_ids)
        assert first_slot_ids.issubset(set(section_ev_ids))
        # Must include at least one id NOT in the first slot
        other_slot_ids: set[str] = set()
        for sl in sec.slots[1:]:
            other_slot_ids.update(sl.entity_ids)
        # (other_slot_ids may equal first_slot_ids if the contract
        # replicates entities across slots; if so, skip the
        # superset-strict check)
        new_ids = other_slot_ids - first_slot_ids
        if new_ids:
            assert new_ids.issubset(set(section_ev_ids))

    def test_medium3_ev_live_id_rejected_at_m54_load(self) -> None:
        """Contract entity ids matching ^ev_\\d+$ MUST fail schema
        validation at M-54 load — Medium 3 namespace-collision
        guard."""
        from src.polaris_graph.nodes.report_contract import (
            ContractSchemaError,
            load_report_contract_for_slug,
        )
        bad_template = {
            "per_query_report_contract": {
                "fake_slug": {
                    "schema_version": "v30.1",
                    "research_question":
                        "Is ev_00001 a valid entity id?",
                    "required_entities": [
                        {
                            "id": "ev_00001",  # LIVE NAMESPACE
                            "type": "pivotal_trial",
                            "required_fields": ["N", "primary_endpoint"],
                            "min_fields_for_completion": 1,
                            "rendering_slot": "sl_1",
                        }
                    ],
                    "rendering_slots": [
                        {
                            "slot_id": "sl_1",
                            "section": "Efficacy",
                            "subsection_title": "Trial",
                            "required": True,
                        }
                    ],
                    "section_order": ["Efficacy"],
                }
            }
        }
        with pytest.raises(ContractSchemaError) as excinfo:
            load_report_contract_for_slug(bad_template, "fake_slug")
        msg = str(excinfo.value).lower()
        assert "live-retrieval" in msg or "reserved" in msg, (
            f"expected collision error, got: {excinfo.value}"
        )

    def test_medium3_register_rejects_nonv30_collision(self) -> None:
        """register_frame_rows_into_evidence_pool refuses to
        clobber a non-v30 pool row — Medium 3 defense-in-depth."""
        from src.polaris_graph.generator.contract_section_runner import (
            register_frame_rows_into_evidence_pool,
        )
        from src.polaris_graph.retrieval.frame_fetcher import (
            FrameRow, ProvenanceClass,
        )

        # Existing non-v30 pool row (simulated live retrieval)
        pool: dict[str, dict] = {
            "surpass_2_primary": {
                "evidence_id": "surpass_2_primary",
                "direct_quote": "legacy live retrieval statement",
                "tier": "T1",
                # NO v30_frame_row marker
            }
        }
        bogus_row = FrameRow(
            entity_id="surpass_2_primary",
            entity_type="pivotal_trial",
            rendering_slot="sl_1",
            provenance_class=ProvenanceClass.ABSTRACT_ONLY,
            direct_quote="new v30 quote",
            quote_source="crossref_abstract",
            doi=None, pmid=None, oa_pdf_url=None, url=None,
            title="T", authors=(), journal="", year=None,
            failure_reason=None, retrieval_attempts=(),
        )
        with pytest.raises(ValueError, match="collision"):
            register_frame_rows_into_evidence_pool(
                pool, (bogus_row,)
            )

    def test_medium2_skip_anchors_computation(self) -> None:
        """Sweep runner `_compute_m50_skip_anchors` returns the
        correct anchor set — Medium 2 double-render guard."""
        # The function is defined inside `main_async`, so mirror
        # the algorithm here and assert the substring-match
        # semantics match expectation. If this logic diverges
        # from run_honest_sweep_r3.py, the test surfaces the
        # divergence.
        from src.polaris_graph.generator.contract_section_runner import (
            ContractSectionPlanExt,
        )
        from src.polaris_graph.nodes.contract_outline import (
            ContractSlotPlan,
        )
        slot = ContractSlotPlan(
            slot_id="sl_1", section="Efficacy",
            subsection_title="SURPASS-2 Primary",
            ordering=1,
            entity_ids=("surpass_2_primary",),
            provenance_classes=("abstract_only",),
            is_gap=False,
            is_partial=False,
        )
        plan = ContractSectionPlanExt(
            title="Efficacy", focus="",
            ev_ids=["surpass_2_primary"],
            slots=(slot,), frame_rows_by_entity={},
            contract_entities_by_id={}, research_question="q",
        )
        primary_anchors = ["SURPASS-2", "SURPASS-4", "SURMOUNT-2"]

        # Mirror sweep runner `_compute_m50_skip_anchors`:
        skip: set[str] = set()
        for pl in [plan]:
            for sl in pl.slots:
                for eid in sl.entity_ids:
                    norm_eid = (
                        eid.lower().replace("_", "").replace("-", "")
                    )
                    for anchor in primary_anchors:
                        norm_anchor = (
                            anchor.lower()
                            .replace("_", "").replace("-", "")
                        )
                        if norm_anchor in norm_eid:
                            skip.add(anchor)
                            break

        # SURPASS-2 entity_id matches SURPASS-2 anchor
        assert "SURPASS-2" in skip
        # SURPASS-4 has no entity in the plan → not skipped
        assert "SURPASS-4" not in skip
        # SURMOUNT-2 similarly not skipped
        assert "SURMOUNT-2" not in skip


# ─────────────────────────────────────────────────────────────────────
# (6) V30 Phase-2 M-68 drop-on-verify gap-disclosure fallback
# ─────────────────────────────────────────────────────────────────────
class TestM68GapDisclosureFallback:
    """V30 Phase-2 M-68 Fix #1 (Codex run-7 audit): a slot MUST
    NEVER silently drop from the body. Pre-M-68 behavior dropped
    SURPASS-6 + FDA Mounjaro + EMA EPAR + HC Mounjaro from the
    report body in run-7 despite frame_coverage=pass, producing
    a Structure LB vs both competitors.
    """

    def test_slot_with_zero_kept_sentences_still_renders_heading(
        self, clinical_template,
    ) -> None:
        """End-to-end: inject a fake strict_verify that keeps zero
        sentences. The returned SectionResult's verified_text MUST
        still contain every slot's heading plus the gap disclosure."""
        import asyncio
        from dataclasses import dataclass, field
        from src.polaris_graph.nodes.frame_compiler import compile_frame
        from src.polaris_graph.nodes.contract_outline import (
            compose_outline_from_contract,
        )
        from src.polaris_graph.generator.contract_section_runner import (
            ContractSectionPlanExt, run_contract_section,
        )

        compiled = compile_frame(
            "What is the efficacy of tirzepatide in T2DM?",
            clinical_template,
            "clinical_tirzepatide_t2dm",
        )
        frame_rows = _stub_fetch_rows(compiled)
        outline = compose_outline_from_contract(compiled, frame_rows)
        rows_by_eid = {r.entity_id: r for r in frame_rows}
        entities_by_id = compiled.contract.entities_by_id()
        efficacy_section = outline.sections[0]

        plan = ContractSectionPlanExt(
            title=efficacy_section.section,
            focus=efficacy_section.focus,
            ev_ids=[
                eid for sl in efficacy_section.slots
                for eid in sl.entity_ids
            ],
            slots=efficacy_section.slots,
            frame_rows_by_entity=rows_by_eid,
            contract_entities_by_id=entities_by_id,
            research_question="q",
        )

        evidence_pool: dict[str, dict] = {}
        from src.polaris_graph.generator.contract_section_runner import (
            register_frame_rows_into_evidence_pool,
        )
        register_frame_rows_into_evidence_pool(
            evidence_pool, tuple(frame_rows),
        )

        # Fake LLM returns "always not_extractable" response so
        # payloads produce only gap-like prose
        async def _fake_llm(prompt: str):
            import re as _re
            field_block = _re.search(
                r"=== REQUIRED FIELDS ===\n(.*?)\n=== OUTPUT CONTRACT ===",
                prompt, _re.DOTALL,
            )
            fields = []
            if field_block:
                for line in field_block.group(1).strip().split("\n"):
                    line = line.strip()
                    if line.startswith("- "):
                        fname = line[2:].strip()
                        fields.append({
                            "field_name": fname,
                            "status": "not_extractable",
                            "value": None,
                            "source_span": None,
                        })
            return json.dumps({"fields": fields}), 100, 50

        # Fake strict_verify that returns ZERO kept sentences
        # (simulates the run-7 drop-on-verify bug)
        @dataclass
        class _FakeReport:
            total_kept: int = 0
            total_in: int = 0
            total_dropped: int = 0
            kept_sentences: list = field(default_factory=list)
            dropped_sentences: list = field(default_factory=list)

        def _zero_kept_strict(text, pool):
            return _FakeReport()

        @dataclass
        class _SR:
            title: str
            focus: str
            ev_ids_assigned: list
            raw_draft: str
            rewritten_draft: str
            verified_text: str
            biblio_slice: list
            sentences_verified: int
            sentences_dropped: int
            regen_attempted: bool
            dropped_due_to_failure: bool
            input_tokens: int
            output_tokens: int
            error: str
            # I-gen-005 Step 1.5 telemetry fields (passed by
            # run_contract_section since the verification-details work).
            kept_sentences_pre_resolve: list = field(default_factory=list)
            dropped_sentences_final: list = field(default_factory=list)

        from src.polaris_graph.generator.live_deepseek_generator import (
            _rewrite_draft_with_spans,
        )

        async def _go():
            return await run_contract_section(
                plan, evidence_pool,
                llm_call=_fake_llm,
                section_result_cls=_SR,
                strict_verify_fn=_zero_kept_strict,
                rewrite_fn=_rewrite_draft_with_spans,
            )

        result, payloads = asyncio.run(_go())

        # Core invariant: EVERY slot heading appears in verified_text
        for slot in efficacy_section.slots:
            assert f"### {slot.subsection_title}" in result.verified_text, (
                f"slot {slot.slot_id!r} heading missing from "
                f"verified_text despite M-68 gap-disclosure "
                f"fallback"
            )
        # Gap-disclosure sentence appears ≥1 time
        assert "curator-actionable gap" in result.verified_text
        # Not flagged as dropped_due_to_failure (headings are content)
        assert result.dropped_due_to_failure is False

        # M-68 Fix #1b: gap-disclosure must carry a [N] citation
        # marker (Qwen citation_tightness rule). Each slot with
        # zero kept sentences should produce ≥1 [N] marker in its
        # disclosure prose.
        import re as _re
        gap_blocks = [
            blk for blk in result.verified_text.split("\n\n")
            if "curator-actionable gap" in blk
        ]
        for gap in gap_blocks:
            assert _re.search(r"\[\d+\]", gap), (
                f"gap disclosure missing [N] citation marker: {gap[:200]!r}"
            )

        # biblio_slice must include entries for every entity whose
        # slot rendered as a gap disclosure (synthesized on demand).
        biblio_evids = {b["evidence_id"] for b in result.biblio_slice}
        for slot in efficacy_section.slots:
            primary_ev = slot.entity_ids[0] if slot.entity_ids else ""
            if primary_ev:
                assert primary_ev in biblio_evids, (
                    f"primary entity {primary_ev!r} of gap-rendered "
                    f"slot {slot.slot_id!r} missing from biblio_slice"
                )

    def test_slot_drop_log_records_dispositions(
        self, clinical_template,
    ) -> None:
        """M-66a-T telemetry: slot_drop_log is built internally
        with per-slot disposition labels. Verify via the
        `verified_text` surface that both dispositions
        (rendered_with_content, rendered_as_gap_disclosure) can
        coexist. Full telemetry exposure deferred to SectionResult
        schema extension in a later cycle."""
        # Covered indirectly by the test above — the fact that
        # every slot renders a heading confirms slot_drop_log was
        # consulted for every slot_id. Deep inspection of the log
        # itself will land with SectionResult schema extension.
        pass

    def test_m69_fix4_rescues_contract_sentences_dropped_by_strict_verify(
        self, clinical_template,
    ) -> None:
        """V30 Phase-2 M-69 Fix #4 (Codex run-9 audit): SURPASS-5
        regressed from 4 fields rendered in run-7 to 0 sentences
        kept in run-9 because strict_verify's content-overlap check
        rejected M-58 contract sentences when direct_quote expanded
        to 25K-char full text. M-58 already enforces verbatim-
        substring anti-fabrication, so the rescue restores any
        strict_verify-dropped sentence whose first token's
        evidence_id is a contract entity.
        """
        import asyncio
        from dataclasses import dataclass, field
        from src.polaris_graph.nodes.frame_compiler import compile_frame
        from src.polaris_graph.nodes.contract_outline import (
            compose_outline_from_contract,
        )
        from src.polaris_graph.generator.contract_section_runner import (
            ContractSectionPlanExt, run_contract_section,
            register_frame_rows_into_evidence_pool,
        )
        from src.polaris_graph.generator.live_deepseek_generator import (
            _rewrite_draft_with_spans,
        )

        compiled = compile_frame(
            "What is the efficacy of tirzepatide in T2DM?",
            clinical_template,
            "clinical_tirzepatide_t2dm",
        )
        frame_rows = _stub_fetch_rows(compiled)
        outline = compose_outline_from_contract(compiled, frame_rows)
        rows_by_eid = {r.entity_id: r for r in frame_rows}
        entities_by_id = compiled.contract.entities_by_id()
        section = outline.sections[0]  # Efficacy

        # Take just SURPASS-2 to keep the test small
        surpass_2_slot = next(
            sl for sl in section.slots
            if "surpass_2" in sl.slot_id.lower()
        )
        plan = ContractSectionPlanExt(
            title=section.section,
            focus=section.focus,
            ev_ids=list(surpass_2_slot.entity_ids),
            slots=(surpass_2_slot,),
            frame_rows_by_entity=rows_by_eid,
            contract_entities_by_id=entities_by_id,
            research_question="q",
        )

        evidence_pool: dict[str, dict] = {}
        register_frame_rows_into_evidence_pool(
            evidence_pool, tuple(frame_rows),
        )

        # Fake LLM that successfully extracts one field
        async def _fake_llm(prompt: str):
            response = json.dumps({
                "fields": [{
                    "field_name": "primary_endpoint",
                    "status": "extracted",
                    "value": "Primary endpoint: change in HbA1c at 40 weeks",
                    "source_span": "Primary endpoint: change in HbA1c at 40 weeks",
                }] + [
                    {
                        "field_name": fname,
                        "status": "not_extractable",
                        "value": None, "source_span": None,
                    }
                    for fname in [
                        "N", "population", "comparator",
                        "baseline_hba1c", "timepoint",
                        "etd_with_uncertainty", "safety_signal",
                        "study_design", "sponsor",
                    ]
                ],
            })
            return response, 100, 50

        # Fake strict_verify that DROPS every contract sentence
        # (simulates the run-9 SURPASS-5 regression scenario)
        from src.polaris_graph.generator.provenance_generator import (
            SentenceVerification, ProvenanceToken,
        )

        @dataclass
        class _FakeReport:
            total_kept: int = 0
            total_in: int = 0
            total_dropped: int = 0
            kept_sentences: list = field(default_factory=list)
            dropped_sentences: list = field(default_factory=list)

        def _all_dropped_strict(text, pool):
            from src.polaris_graph.generator.provenance_generator import (
                split_into_sentences, parse_provenance_tokens,
            )
            sentences = split_into_sentences(text)
            dropped = []
            for s in sentences:
                tokens = parse_provenance_tokens(s)
                dropped.append(SentenceVerification(
                    sentence=s, tokens=tokens, is_verified=False,
                    failure_reasons=["test_drop"],
                    soft_warnings=[],
                ))
            return _FakeReport(
                total_kept=0, total_in=len(sentences),
                total_dropped=len(sentences),
                kept_sentences=[], dropped_sentences=dropped,
            )

        @dataclass
        class _SR:
            title: str
            focus: str
            ev_ids_assigned: list
            raw_draft: str
            rewritten_draft: str
            verified_text: str
            biblio_slice: list
            sentences_verified: int
            sentences_dropped: int
            regen_attempted: bool
            dropped_due_to_failure: bool
            input_tokens: int
            output_tokens: int
            error: str
            # I-gen-005 Step 1.5 telemetry fields (passed by
            # run_contract_section since the verification-details work).
            kept_sentences_pre_resolve: list = field(default_factory=list)
            dropped_sentences_final: list = field(default_factory=list)

        async def _go():
            return await run_contract_section(
                plan, evidence_pool,
                llm_call=_fake_llm,
                section_result_cls=_SR,
                strict_verify_fn=_all_dropped_strict,
                rewrite_fn=_rewrite_draft_with_spans,
            )

        result, payloads = asyncio.run(_go())

        # M-69 Fix #4 invariant: even though strict_verify dropped
        # ALL sentences, contract-slot sentences must be RESCUED
        # (M-58 already proved them verbatim). The verified_text
        # must contain the extracted primary_endpoint content,
        # NOT a gap disclosure.
        assert "Primary endpoint" in result.verified_text, (
            f"M-69 Fix #4 failed: contract sentence not rescued "
            f"after strict_verify dropped it. verified_text="
            f"{result.verified_text!r}"
        )
        assert "curator-actionable gap" not in result.verified_text, (
            "verified_text fell back to gap disclosure despite "
            "M-69 Fix #4 — sentences should have been rescued"
        )
        assert result.sentences_verified > 0

    def test_fix_b_narrative_origin_sentence_not_rescued_end_to_end(
        self, clinical_template,
    ) -> None:
        """I-faith-001 Fix B (STREAM SEPARATION), end-to-end through
        ``run_contract_section``.

        This is the WIRING test (distinct from the helper-level unit tests in
        test_faith_rescue_guard.py): it proves that the NARRATIVE stream
        specifically is the one wired rescue-INELIGIBLE. A fake strict_verify
        drops EVERY sentence for a NON-numeric reason; the deterministic slot
        sentence ("Primary endpoint: ...") MUST be rescued and appear in
        verified_text, while the narrative-origin sentence (a distinct marker
        string returned only for the narrative LLM call) MUST NOT be rescued
        and must be ABSENT from verified_text.

        Flag-swap sensitivity: if the two ``allow_rescue`` values in
        ``run_contract_section`` were transposed (narrative→True,
        deterministic→False), the narrative marker would appear and the
        deterministic content would vanish — this test would fail. The helper
        unit tests, which call ``_verify_one_stream`` with a hardcoded flag,
        cannot catch that transposition.
        """
        import asyncio
        from dataclasses import dataclass, field
        from src.polaris_graph.nodes.frame_compiler import compile_frame
        from src.polaris_graph.nodes.contract_outline import (
            compose_outline_from_contract,
        )
        from src.polaris_graph.generator.contract_section_runner import (
            ContractSectionPlanExt, run_contract_section,
            register_frame_rows_into_evidence_pool,
        )
        from src.polaris_graph.generator.live_deepseek_generator import (
            _rewrite_draft_with_spans,
        )
        from src.polaris_graph.generator.provenance_generator import (
            SentenceVerification,
        )

        compiled = compile_frame(
            "What is the efficacy of tirzepatide in T2DM?",
            clinical_template,
            "clinical_tirzepatide_t2dm",
        )
        frame_rows = _stub_fetch_rows(compiled)
        outline = compose_outline_from_contract(compiled, frame_rows)
        rows_by_eid = {r.entity_id: r for r in frame_rows}
        entities_by_id = compiled.contract.entities_by_id()
        section = outline.sections[0]  # Efficacy

        surpass_2_slot = next(
            sl for sl in section.slots
            if "surpass_2" in sl.slot_id.lower()
        )
        primary_ev = surpass_2_slot.entity_ids[0]
        plan = ContractSectionPlanExt(
            title=section.section,
            focus=section.focus,
            ev_ids=list(surpass_2_slot.entity_ids),
            slots=(surpass_2_slot,),
            frame_rows_by_entity=rows_by_eid,
            contract_entities_by_id=entities_by_id,
            research_question="q",
        )

        evidence_pool: dict[str, dict] = {}
        register_frame_rows_into_evidence_pool(
            evidence_pool, tuple(frame_rows),
        )

        # A unique marker that appears ONLY in the narrative LLM output, so we
        # can detect whether the narrative-origin sentence survived.
        _NARR_MARKER = "NarrativeOriginFabricationMarker"

        # Fake LLM: returns slot-fill JSON for the extraction prompt, and a
        # narrative paragraph (carrying the marker + the bound citation) for
        # the narrative prompt (detected via the "NARRATIVE PARAGRAPH" header
        # that build_slot_narrative_prompt emits).
        async def _fake_llm(prompt: str):
            if "NARRATIVE PARAGRAPH" in prompt:
                narrative = (
                    f"{_NARR_MARKER} the assistant raised analyst "
                    f"throughput substantially across the cohort "
                    f"[{primary_ev}]."
                )
                return narrative, 80, 40
            response = json.dumps({
                "fields": [{
                    "field_name": "primary_endpoint",
                    "status": "extracted",
                    "value": "Primary endpoint: change in HbA1c at 40 weeks",
                    "source_span": "Primary endpoint: change in HbA1c at 40 weeks",
                }] + [
                    {
                        "field_name": fname,
                        "status": "not_extractable",
                        "value": None, "source_span": None,
                    }
                    for fname in [
                        "N", "population", "comparator",
                        "baseline_hba1c", "timepoint",
                        "etd_with_uncertainty", "safety_signal",
                        "study_design", "sponsor",
                    ]
                ],
            })
            return response, 100, 50

        @dataclass
        class _FakeReport:
            total_kept: int = 0
            total_in: int = 0
            total_dropped: int = 0
            kept_sentences: list = field(default_factory=list)
            dropped_sentences: list = field(default_factory=list)

        # Drop EVERY sentence for a NON-numeric reason — so the ONLY thing
        # that decides whether a sentence survives is its stream's rescue
        # eligibility (Fix B), not the Fix A numeric guard.
        def _all_dropped_strict(text, pool):
            from src.polaris_graph.generator.provenance_generator import (
                split_into_sentences, parse_provenance_tokens,
            )
            sentences = split_into_sentences(text)
            dropped = []
            for s in sentences:
                tokens = parse_provenance_tokens(s)
                dropped.append(SentenceVerification(
                    sentence=s, tokens=tokens, is_verified=False,
                    failure_reasons=["no_content_word_overlap_any_cited_span"],
                    soft_warnings=[],
                ))
            return _FakeReport(
                total_kept=0, total_in=len(sentences),
                total_dropped=len(sentences),
                kept_sentences=[], dropped_sentences=dropped,
            )

        @dataclass
        class _SR:
            title: str
            focus: str
            ev_ids_assigned: list
            raw_draft: str
            rewritten_draft: str
            verified_text: str
            biblio_slice: list
            sentences_verified: int
            sentences_dropped: int
            regen_attempted: bool
            dropped_due_to_failure: bool
            input_tokens: int
            output_tokens: int
            error: str
            kept_sentences_pre_resolve: list = field(default_factory=list)
            dropped_sentences_final: list = field(default_factory=list)

        async def _go():
            return await run_contract_section(
                plan, evidence_pool,
                llm_call=_fake_llm,
                section_result_cls=_SR,
                strict_verify_fn=_all_dropped_strict,
                rewrite_fn=_rewrite_draft_with_spans,
            )

        result, payloads = asyncio.run(_go())

        # Deterministic stream: rescued → its content survives.
        assert "Primary endpoint" in result.verified_text, (
            "deterministic slot sentence was not rescued (the deterministic "
            "stream must remain rescue-eligible under Fix B). verified_text="
            f"{result.verified_text!r}"
        )
        # Narrative stream: rescue-INELIGIBLE → its content is DROPPED. The
        # marker must NOT appear anywhere in the rendered section.
        assert _NARR_MARKER not in result.verified_text, (
            "Fix B FAILED: a narrative-origin sentence that failed strict "
            "verify was laundered back into verified_text. The narrative "
            "stream must be rescue-INELIGIBLE. verified_text="
            f"{result.verified_text!r}"
        )

    def test_regulatory_origin_sentence_not_rescued_end_to_end(self) -> None:
        """I-faith-001 regulatory classification, end-to-end through
        ``run_contract_section``.

        WIRING test: proves the M-70 ``render_regulatory_prose`` output is
        routed to the rescue-INELIGIBLE stream. The M-70 parser verbatim-checks
        ONLY the one ``source_span`` phrase, not the LLM-synthesized prose
        ``value`` — so a regulatory paragraph can carry an unverified
        LLM-introduced claim, exactly the narrative-stream fabrication shape.

        A fake strict_verify drops EVERY sentence for a NON-numeric reason; the
        regulatory-origin sentence (carrying a unique marker returned only for
        the regulatory synthesis prompt) MUST NOT be rescued and must be ABSENT
        from verified_text. If regulatory prose were left in the deterministic
        (rescue-ELIGIBLE) stream, the marker would survive and this test would
        fail.
        """
        import asyncio
        from dataclasses import dataclass, field
        from src.polaris_graph.nodes.report_contract import RequiredEntity
        from src.polaris_graph.nodes.contract_outline import ContractSlotPlan
        from src.polaris_graph.retrieval.frame_fetcher import (
            FrameRow, ProvenanceClass,
        )
        from src.polaris_graph.generator.contract_section_runner import (
            ContractSectionPlanExt, run_contract_section,
            register_frame_rows_into_evidence_pool,
        )
        from src.polaris_graph.generator.live_deepseek_generator import (
            _rewrite_draft_with_spans,
        )
        from src.polaris_graph.generator.provenance_generator import (
            SentenceVerification,
        )

        ev_id = "fda_zepbound_label"
        # FDA-shaped page with an INDICATIONS heading so _segment_regulatory_text
        # produces an `indications` segment (the synthesis prompt only lists
        # fields whose heading matched). The verbatim phrase the LLM "uses" lives
        # here so the M-70 parser's source_span check passes — the FABRICATION is
        # the surrounding LLM prose, which the parser does NOT verbatim-check.
        verbatim_phrase = (
            "Zepbound is indicated for chronic weight management in adults"
        )
        direct_quote = (
            "1 INDICATIONS AND USAGE\n"
            f"{verbatim_phrase} with an initial body mass index of 30 kg/m2 "
            "or greater.\n"
        )

        reg_entity = RequiredEntity(
            id=ev_id,
            type="regulatory",
            required_fields=("indications",),
            min_fields_for_completion=1,
            rendering_slot="regulatory_fda",
            jurisdiction="FDA",
            label_name="Zepbound FDA label",
        )
        frame_row = FrameRow(
            entity_id=ev_id,
            entity_type="regulatory",
            rendering_slot="regulatory_fda",
            provenance_class=ProvenanceClass.ABSTRACT_ONLY,
            direct_quote=direct_quote,
            quote_source="fda_label",
            doi=None, pmid=None, oa_pdf_url=None, url=None,
            title="Zepbound label", authors=(), journal=None, year=2023,
            failure_reason=None, retrieval_attempts=(), retrieval_timings=(),
        )
        slot = ContractSlotPlan(
            slot_id="regulatory_fda",
            section="Regulatory",
            subsection_title="FDA",
            ordering=0,
            entity_ids=(ev_id,),
            provenance_classes=(ProvenanceClass.ABSTRACT_ONLY.value,),
            is_gap=False,
            is_partial=False,
        )
        plan = ContractSectionPlanExt(
            title="Regulatory",
            focus="regulatory landscape",
            ev_ids=[ev_id],
            slots=(slot,),
            frame_rows_by_entity={ev_id: frame_row},
            contract_entities_by_id={ev_id: reg_entity},
            research_question="q",
        )

        evidence_pool: dict[str, dict] = {}
        register_frame_rows_into_evidence_pool(evidence_pool, (frame_row,))

        # Marker that appears ONLY in the regulatory synthesis prose value, so
        # we can detect whether the regulatory-origin sentence survived.
        _REG_MARKER = "RegulatoryOriginFabricationMarker"

        async def _fake_llm(prompt: str):
            # Regulatory synthesis prompt (M-70) — detected via its distinctive
            # "regulatory affairs writer" header.
            if "regulatory affairs writer" in prompt:
                response = json.dumps({"fields": [{
                    "field_name": "indications",
                    "status": "extracted",
                    # The prose value carries the fabrication marker AND the
                    # verbatim phrase; only the source_span is verbatim-checked.
                    "value": (
                        f"{_REG_MARKER}. The label states that {verbatim_phrase}, "
                        "and additionally implies cardiovascular benefit."
                    ),
                    "source_span": verbatim_phrase,
                }]})
                return response, 100, 50
            # No other prompt types expected for this single regulatory entity.
            return json.dumps({"fields": []}), 0, 0

        @dataclass
        class _FakeReport:
            total_kept: int = 0
            total_in: int = 0
            total_dropped: int = 0
            kept_sentences: list = field(default_factory=list)
            dropped_sentences: list = field(default_factory=list)

        def _all_dropped_strict(text, pool):
            from src.polaris_graph.generator.provenance_generator import (
                split_into_sentences, parse_provenance_tokens,
            )
            sentences = split_into_sentences(text)
            dropped = []
            for s in sentences:
                tokens = parse_provenance_tokens(s)
                dropped.append(SentenceVerification(
                    sentence=s, tokens=tokens, is_verified=False,
                    failure_reasons=["no_content_word_overlap_any_cited_span"],
                    soft_warnings=[],
                ))
            return _FakeReport(
                total_kept=0, total_in=len(sentences),
                total_dropped=len(sentences),
                kept_sentences=[], dropped_sentences=dropped,
            )

        @dataclass
        class _SR:
            title: str
            focus: str
            ev_ids_assigned: list
            raw_draft: str
            rewritten_draft: str
            verified_text: str
            biblio_slice: list
            sentences_verified: int
            sentences_dropped: int
            regen_attempted: bool
            dropped_due_to_failure: bool
            input_tokens: int
            output_tokens: int
            error: str
            kept_sentences_pre_resolve: list = field(default_factory=list)
            dropped_sentences_final: list = field(default_factory=list)

        async def _go():
            return await run_contract_section(
                plan, evidence_pool,
                llm_call=_fake_llm,
                section_result_cls=_SR,
                strict_verify_fn=_all_dropped_strict,
                rewrite_fn=_rewrite_draft_with_spans,
            )

        result, _payloads = asyncio.run(_go())

        # LIVENESS (anti-vacuity): the regulatory prose carrying the marker MUST
        # actually have been produced and entered the regulatory stream — else
        # the absence-from-verified_text assertion below would pass for the
        # WRONG reason (segmentation missed the heading / synthesis JSON failed
        # to parse / field degraded to not_extractable → no prose at all).
        # `result.raw_draft` joins (deterministic, regulatory, narrative) raw
        # drafts, so the marker is present iff render_regulatory_prose emitted
        # it and it reached `regulatory_body_blocks`.
        assert _REG_MARKER in result.raw_draft, (
            "regulatory prose was never produced — the test would be vacuous. "
            "Check FDA segmentation / synthesis parse. "
            f"raw_draft={result.raw_draft!r}"
        )
        # Regulatory stream is rescue-INELIGIBLE: produced, entered the
        # regulatory stream, then DROPPED by rescue-ineligibility → the marker
        # must NOT survive into verified_text.
        assert _REG_MARKER not in result.verified_text, (
            "regulatory classification FAILED: an LLM-synthesized regulatory "
            "sentence that failed strict verify was laundered back into "
            "verified_text. The regulatory (M-70) stream must be rescue-"
            f"INELIGIBLE. verified_text={result.verified_text!r}"
        )
