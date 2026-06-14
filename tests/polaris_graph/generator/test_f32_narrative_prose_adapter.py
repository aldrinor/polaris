"""I-arch-004 F32 (#1255): the V30 per-entity NARRATIVE paragraph call must
NOT reuse the JSON-only contract-slot LLM wrapper.

BUG (pre-fix): ``run_contract_section`` used a single injected ``llm_call`` for
BOTH the JSON slot-fill / regulatory-synthesis calls AND the free-form narrative
paragraph call (``build_slot_narrative_prompt`` -> contract_section_runner.py).
In the production path that single adapter (``_m63_llm_call``) wraps every call
with a JSON-only system message ("You are a JSON-only extraction assistant ...
Do not include prose ... or any text outside the JSON object."). The narrative
prompt explicitly asks for "plain prose, ONE paragraph", so the model received
DIRECTLY CONFLICTING instructions (system: JSON only, no prose; user: prose
paragraph) — the narrative was generated under JSON-mode constraints.

FIX: a separate prose adapter (``_m63_narrative_llm_call``) with its own PROSE
system message (``PG_NARRATIVE_PROSE_SYSTEM_MESSAGE``) + explicit non-JSON
response mode is threaded into ``run_contract_section`` via the new optional
``narrative_llm_call`` param and used for the narrative call ONLY. The JSON
slot-fill + regulatory-synthesis calls KEEP ``llm_call``.

These tests prove:
  (1) ROUTING (behavioral) — the narrative prompt is dispatched through
      ``narrative_llm_call`` while JSON-extraction prompts go through
      ``llm_call``; with no ``narrative_llm_call`` threaded it falls back to
      ``llm_call`` (byte-identical for legacy callers).
  (2) PROSE-NESS (real adapter, source + constant) — the production narrative
      adapter passes ``system=PG_NARRATIVE_PROSE_SYSTEM_MESSAGE`` +
      ``response_format=None``, and that prose system message is NOT the
      JSON-only extraction string. This assertion FAILS on pre-fix code (the
      prose constant did not exist; the JSON-only string was the sole system
      message for the narrative call).

Pure — no network, no real LLM. Reuses the end-to-end scaffolding the existing
``test_m63_contract_section_runner`` module already exercises.
"""
from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import yaml

# The marker ``build_slot_narrative_prompt`` injects into the narrative prompt
# (see slot_fill.py). Stable header used by the existing wiring tests to detect
# the narrative call.
_NARRATIVE_PROMPT_MARKER = "NARRATIVE PARAGRAPH"


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


@dataclass
class _SR:
    title: str = ""
    focus: str = ""
    ev_ids_assigned: list = field(default_factory=list)
    raw_draft: str = ""
    rewritten_draft: str = ""
    verified_text: str = ""
    biblio_slice: list = field(default_factory=list)
    sentences_verified: int = 0
    sentences_dropped: int = 0
    regen_attempted: bool = False
    dropped_due_to_failure: bool = False
    input_tokens: int = 0
    output_tokens: int = 0
    error: str = ""
    kept_sentences_pre_resolve: list = field(default_factory=list)
    dropped_sentences_final: list = field(default_factory=list)
    slot_strict_verify: list = field(default_factory=list)


def _build_efficacy_plan(clinical_template: dict):
    """Compile -> fetch -> one ContractSectionPlanExt (Efficacy)."""
    from src.polaris_graph.generator.contract_section_runner import (
        ContractSectionPlanExt,
        register_frame_rows_into_evidence_pool,
    )
    from src.polaris_graph.nodes.contract_outline import (
        compose_outline_from_contract,
    )
    from src.polaris_graph.nodes.frame_compiler import compile_frame

    compiled = compile_frame(
        "What is the efficacy of tirzepatide in T2DM?",
        clinical_template,
        "clinical_tirzepatide_t2dm",
    )
    rows = _stub_fetch_rows(compiled)
    outline = compose_outline_from_contract(compiled, rows)
    section = next(s for s in outline.sections if s.section == "Efficacy")
    # Single slot keeps the test cheap (one narrative call).
    surpass_2_slot = next(
        sl for sl in section.slots if "surpass_2" in sl.slot_id.lower()
    )
    plan = ContractSectionPlanExt(
        title=section.section,
        focus=section.focus,
        ev_ids=list(surpass_2_slot.entity_ids),
        slots=(surpass_2_slot,),
        frame_rows_by_entity={r.entity_id: r for r in rows},
        contract_entities_by_id=compiled.contract.entities_by_id(),
        research_question="tirzepatide efficacy",
    )
    evidence_pool: dict[str, dict[str, Any]] = {}
    register_frame_rows_into_evidence_pool(evidence_pool, rows)
    return plan, evidence_pool, surpass_2_slot.entity_ids[0]


def _slot_fill_json(prompt: str, primary_ev: str) -> str:
    """One extracted field + not_extractable for the rest (mirrors a realistic
    abstract-only extraction)."""
    return json.dumps({
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
                "N", "population", "comparator", "baseline_hba1c",
                "timepoint", "etd_with_uncertainty", "safety_signal",
                "study_design", "sponsor",
            ]
        ],
    })


# ─────────────────────────────────────────────────────────────────────
# (1) ROUTING — narrative prompt -> narrative_llm_call; JSON -> llm_call
# ─────────────────────────────────────────────────────────────────────
class TestNarrativeCallRouting:
    def test_narrative_routed_to_narrative_adapter_json_to_llm_call(
        self, clinical_template: dict,
    ) -> None:
        from src.polaris_graph.generator.contract_section_runner import (
            run_contract_section,
        )
        from src.polaris_graph.generator.live_deepseek_generator import (
            _rewrite_draft_with_spans,
        )
        from src.polaris_graph.generator.provenance_generator import (
            strict_verify,
        )

        plan, evidence_pool, primary_ev = _build_efficacy_plan(
            clinical_template,
        )

        json_prompts: list[str] = []
        narrative_prompts: list[str] = []

        async def _json_call(prompt: str):
            json_prompts.append(prompt)
            return _slot_fill_json(prompt, primary_ev), 100, 50

        async def _narrative_call(prompt: str):
            narrative_prompts.append(prompt)
            # A grounded prose paragraph restating the extracted field.
            return (
                "In this trial the primary endpoint was the change in HbA1c "
                f"at 40 weeks [{primary_ev}]."
            ), 80, 40

        async def _go():
            return await run_contract_section(
                plan, evidence_pool,
                llm_call=_json_call,
                narrative_llm_call=_narrative_call,
                section_result_cls=_SR,
                strict_verify_fn=strict_verify,
                rewrite_fn=_rewrite_draft_with_spans,
            )

        asyncio.run(_go())

        # The narrative prompt MUST go to the prose adapter.
        assert narrative_prompts, (
            "narrative_llm_call was never invoked — the narrative paragraph "
            "call was not routed to the prose adapter."
        )
        assert all(
            _NARRATIVE_PROMPT_MARKER in p for p in narrative_prompts
        ), (
            "narrative_llm_call received a NON-narrative prompt: "
            f"{narrative_prompts!r}"
        )
        # The JSON adapter MUST NOT receive any narrative prompt.
        assert json_prompts, "llm_call (JSON adapter) was never invoked."
        assert all(
            _NARRATIVE_PROMPT_MARKER not in p for p in json_prompts
        ), (
            "JSON llm_call received a narrative prompt — the narrative call "
            "must be routed to narrative_llm_call, not the JSON adapter."
        )

    def test_falls_back_to_llm_call_when_no_narrative_adapter(
        self, clinical_template: dict,
    ) -> None:
        """No ``narrative_llm_call`` threaded => narrative falls back to
        ``llm_call`` (byte-identical for legacy callers / existing tests)."""
        from src.polaris_graph.generator.contract_section_runner import (
            run_contract_section,
        )
        from src.polaris_graph.generator.live_deepseek_generator import (
            _rewrite_draft_with_spans,
        )
        from src.polaris_graph.generator.provenance_generator import (
            strict_verify,
        )

        plan, evidence_pool, primary_ev = _build_efficacy_plan(
            clinical_template,
        )

        saw_narrative_on_llm_call: list[bool] = []

        async def _only_call(prompt: str):
            if _NARRATIVE_PROMPT_MARKER in prompt:
                saw_narrative_on_llm_call.append(True)
                return (
                    "In this trial the primary endpoint was the change in "
                    f"HbA1c at 40 weeks [{primary_ev}]."
                ), 80, 40
            return _slot_fill_json(prompt, primary_ev), 100, 50

        async def _go():
            return await run_contract_section(
                plan, evidence_pool,
                llm_call=_only_call,
                # narrative_llm_call intentionally omitted (defaults to None)
                section_result_cls=_SR,
                strict_verify_fn=strict_verify,
                rewrite_fn=_rewrite_draft_with_spans,
            )

        asyncio.run(_go())
        assert saw_narrative_on_llm_call, (
            "fallback broken: with no narrative_llm_call threaded, the "
            "narrative call must fall back to llm_call."
        )


# ─────────────────────────────────────────────────────────────────────
# (2) PROSE-NESS — the REAL production narrative adapter uses a prose
#     system message + non-JSON response mode (NOT the JSON-only string).
# ─────────────────────────────────────────────────────────────────────
class TestNarrativeAdapterIsProse:
    def test_prose_system_message_is_not_json_only(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            PG_NARRATIVE_PROSE_SYSTEM_MESSAGE,
        )

        msg = PG_NARRATIVE_PROSE_SYSTEM_MESSAGE.lower()
        # The discriminating assertion: the narrative system message is PROSE,
        # NOT the JSON-only extraction string. Pre-fix the narrative call used
        # the "JSON-only extraction assistant ... any text outside the JSON
        # object" system message — these substrings MUST be absent now.
        assert "json-only" not in msg, (
            "narrative system message still carries the JSON-only directive"
        )
        assert "json object" not in msg, (
            "narrative system message still tells the model to emit a JSON "
            "object — the narrative is prose"
        )
        assert "json schema" not in msg, (
            "narrative system message still tells the model to emit a JSON "
            "schema — the narrative is prose"
        )
        # And it positively instructs prose output.
        assert "prose" in msg, (
            "narrative system message does not instruct prose output"
        )

    def test_production_narrative_adapter_wires_prose_system_and_non_json(
        self,
    ) -> None:
        """Source-level wiring proof (repo-sanctioned idiom — see
        test_disclosure_failloud_wiring_icred008b.py using inspect.getsource):
        the production narrative adapter passes the prose system message + an
        explicit non-JSON response mode, and the contract-section caller threads
        it as ``narrative_llm_call``."""
        from src.polaris_graph.generator import multi_section_generator as msg_mod

        src = inspect.getsource(msg_mod.generate_multi_section_report)

        # A distinct narrative adapter exists.
        assert "_m63_narrative_llm_call" in src, (
            "production narrative adapter _m63_narrative_llm_call is missing"
        )
        # It uses the PROSE system message constant (NOT the JSON-only inline
        # string used by _m63_llm_call).
        assert "system=PG_NARRATIVE_PROSE_SYSTEM_MESSAGE" in src, (
            "narrative adapter does not pass the prose system message"
        )
        # Explicit non-JSON response mode on the narrative call.
        assert "response_format=None" in src, (
            "narrative adapter does not set an explicit non-JSON response mode"
        )
        # The caller threads the prose adapter into run_contract_section.
        assert "narrative_llm_call=_m63_narrative_llm_call" in src, (
            "run_contract_section caller does not thread narrative_llm_call"
        )

    def test_run_contract_section_accepts_narrative_llm_call_param(self) -> None:
        """The seam exists: ``run_contract_section`` exposes an optional
        ``narrative_llm_call`` keyword (defaulting to None => fallback)."""
        from src.polaris_graph.generator.contract_section_runner import (
            run_contract_section,
        )

        params = inspect.signature(run_contract_section).parameters
        assert "narrative_llm_call" in params, (
            "run_contract_section is missing the narrative_llm_call param"
        )
        assert params["narrative_llm_call"].default is None, (
            "narrative_llm_call must default to None for byte-identical "
            "legacy-caller behaviour"
        )
