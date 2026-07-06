"""FF-4IR-CONFIG — the drb_72 workforce contract is re-authored for the OFFICIAL question.

Root cause (I-deepfix-001 forensic, 4IR-validity-abort): the ``drb_72_ai_labor``
``per_query_report_contract`` in ``config/scope_templates/workforce.yaml`` was authored
from the OLD launch-stub program prompt ("... a key driver of the Fourth Industrial
Revolution ... only cites high-quality, English-language journal articles"). The runtime
question is FORCED to the OFFICIAL DeepResearch-Bench idx-56 prompt (generative AI on the
labor market; positive/negative effects, challenges, opportunities; pre-June-2023) via
``PG_BENCHMARK_OFFICIAL_QUESTION`` (run_gate_b.py). The stale contract still carried an
off-question ``fourth_industrial_revolution_framing`` entity + ``theory_4ir_framing``
rendering slot; the V30 render emitted that slot's "Fourth Industrial Revolution framing"
subsection header unconditionally, injecting the forbidden reformulation phrase into
report.md and tripping ``abort_run_validity_gate`` at the source.

This is a STALE-CONFIG fix — the run-validity gate is CORRECT and stays untouched. We delete
the off-question 4IR entity + slot (and its off-question amplified retrieval query) so the
contract stops naming the reformulation, WHILE RETAINING every on-question anchor entity
(§-1.3 WIDEN-only: no on-question source is dropped for a number).

Pure config assertions — NO network, NO LLM, NO spend.
"""
from __future__ import annotations

from src.polaris_graph.nodes.scope_gate import _SCOPE_TEMPLATES_DIR, load_scope_template
from src.polaris_graph.roles.native_gate_b_inputs import load_required_entities

_SLUG = "drb_72_ai_labor"

# The on-question anchor entities a faithful review of the OFFICIAL idx-56 question MUST
# carry. All are AI / generative-AI labor-market economics papers; NONE is dropped by this
# fix (the fix only removes the off-question Fourth-Industrial-Revolution framing entity).
_EXPECTED_ON_QUESTION_ENTITY_IDS = {
    "acemoglu_restrepo_automation_tasks",
    "autor_why_still_jobs",
    "acemoglu_restrepo_robots_jobs",
    "frey_osborne_computerisation",
    "brynjolfsson_genai_at_work",
    "eloundou_gpts_are_gpts",
}


def _contract() -> dict:
    template = load_scope_template("workforce")
    return template["per_query_report_contract"][_SLUG]


def test_contract_has_no_fourth_industrial_revolution_entity_or_slot():
    """The off-question 4IR entity + its rendering slot are gone (RED before the fix)."""
    contract = _contract()
    entity_ids = {e["id"] for e in contract["required_entities"]}
    assert "fourth_industrial_revolution_framing" not in entity_ids, entity_ids

    slot_names = set(contract["rendering_slots"].keys())
    assert "theory_4ir_framing" not in slot_names, slot_names

    # No surviving entity carries the 4IR coverage requirement or rendering slot.
    for e in contract["required_entities"]:
        reqs = " ".join(e.get("coverage_content_requirements", [])).lower()
        assert "fourth industrial revolution" not in reqs, e["id"]
        assert e.get("rendering_slot") != "theory_4ir_framing", e["id"]


def test_workforce_yaml_text_names_no_fourth_industrial_revolution():
    """The contract config no longer NAMES the forbidden reformulation (RED before the fix).

    Guards the exact phrase the run-validity gate treats as an off-question tell, plus the
    slug/anchor spellings, so a future re-injection is caught at config-parse time.
    """
    text = (_SCOPE_TEMPLATES_DIR / "workforce.yaml").read_text(encoding="utf-8")
    lowered = text.lower()
    assert "fourth industrial revolution" not in lowered, "workforce.yaml still names 4IR"
    assert "fourth_industrial_revolution" not in lowered
    assert "theory_4ir_framing" not in lowered
    assert "4ir-framing" not in lowered


def test_official_question_anchor_entities_are_retained():
    """§-1.3 WIDEN-only coverage guard: every on-question anchor survives and NO extra
    off-question entity remains (exactly the six generative-AI / automation labor papers)."""
    entities = load_required_entities(load_scope_template("workforce"), _SLUG)
    entity_ids = {e["id"] for e in entities}
    assert entity_ids == _EXPECTED_ON_QUESTION_ENTITY_IDS, entity_ids
    # The two generative-AI papers (the core of the OFFICIAL question) are explicitly present.
    assert "brynjolfsson_genai_at_work" in entity_ids
    assert "eloundou_gpts_are_gpts" in entity_ids
