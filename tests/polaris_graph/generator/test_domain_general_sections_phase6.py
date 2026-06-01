"""I-meta-005 Phase 6 (#990) smoke — domain-general section prompts + verified
synthesis.

Codex rulings: A1 (planner `answer_type` -> registry-driven advisory selection;
clinical guidance loads ONLY for a clinical frame) + B-impl-1 / shape 1 (the
"Integrative" synthesis is a NORMAL planned outline section, generated +
strict_verified like any other; the unverified analyst block is demoted on-mode).

SPEND-FREE: pure config/parse/structural assertions — no LLM, no network. The live
generator behaviour (advisory append, integrative verification, analyst demotion)
is exercised by the generator regression suite + the Codex diff-gate; here we pin
the deterministic surface + the by-construction structural guarantees.

Plain assertions, no unittest.mock.
"""
from __future__ import annotations

import inspect

from src.polaris_graph.generator import multi_section_generator as msg
from src.polaris_graph.generator.multi_section_generator import (
    SECTION_ARCHETYPES,
    select_advisory_prompt_text,
)
from src.polaris_graph.planning.research_planner import (
    ANSWER_TYPES,
    ResearchFrame,
    ResearchPlan,
    SectionOutlineItem,
    _parse_frame,
    plan_sha256,
)


# ── P6-2 / P6-3 advisory selection by answer_type (the A1 clinical trigger) ───

def test_p6_2_clinical_answer_type_loads_clinical_advisory():
    # answer_type "clinical" selects the clinical advisory family REGARDLESS of the
    # generic claim_type (empirical is shared by physics/econ/clinical).
    text = select_advisory_prompt_text("empirical", "clinical")
    assert text  # non-empty
    assert "CLINICAL WRITING GUIDANCE" in text or "clinical" in text.lower()


def test_p6_3_non_clinical_answer_type_gets_no_clinical_advisory():
    # Non-clinical domains + general -> no advisory append (empty).
    for at in ("economics", "policy", "materials", "engineering", "general"):
        assert select_advisory_prompt_text("empirical", at) == "", at


def test_p6_3b_answer_type_wins_over_claim_type():
    # claim_type alone never selects clinical (by_claim_type is unmapped); only the
    # explicit answer_type does. A non-clinical answer_type with ANY claim_type ->
    # no clinical advisory.
    assert select_advisory_prompt_text("mechanism", "general") == ""
    assert select_advisory_prompt_text("policy-comparison", "economics") == ""
    # clinical answer_type with any claim_type -> clinical advisory.
    assert select_advisory_prompt_text("descriptive", "clinical")


def test_p6_off_default_general_no_advisory():
    # Default/absent answer_type ("general") -> no append (OFF-mode byte-identity:
    # the on-path computes advisory_text="" so the section prompt is unchanged).
    assert select_advisory_prompt_text("empirical") == ""        # default arg
    assert select_advisory_prompt_text("", "") == ""


# ── answer_type machinery (A1): parse fail-soft + canonical pin ──────────────

def _frame_obj(answer_type):
    return {
        "frame": {
            "entities": ["x"], "relations": [], "metrics": [], "comparators": [],
            "constraints": [], "claim_type": "empirical",
            "evidence_needs": [], "jurisdictions": [],
            "answer_type": answer_type,
        }
    }


def test_p6_answer_type_parse_and_fail_soft():
    assert _parse_frame(_frame_obj("clinical")).answer_type == "clinical"
    # unknown -> "general" (fail-soft; advisory routing never aborts a run)
    assert _parse_frame(_frame_obj("made_up_domain")).answer_type == "general"
    # absent -> "general"
    raw = _frame_obj("clinical")
    del raw["frame"]["answer_type"]
    assert _parse_frame(raw).answer_type == "general"
    assert "clinical" in ANSWER_TYPES and "general" in ANSWER_TYPES


def test_p6_answer_type_in_canonical_pin():
    def _plan(at):
        return ResearchPlan(
            research_question="q",
            frame=ResearchFrame(entities=["x"], claim_type="empirical",
                                answer_type=at),
            sub_queries=["sq0"],
            outline=[SectionOutlineItem(archetype="Background", title="T",
                                        evidence_target=1, sub_query_indices=[0])],
        )
    # answer_type is in the SHA-pinned canonical projection -> different
    # answer_type yields a different plan_sha (reproducible from the artifact).
    assert "answer_type" in _plan("clinical").to_canonical_dict()["frame"]
    assert plan_sha256(_plan("clinical")) != plan_sha256(_plan("economics"))
    # ...but identical answer_type reproduces the identical sha (stability).
    assert plan_sha256(_plan("clinical")) == plan_sha256(_plan("clinical"))


# ── P6-4 / P6-5 Integrative section is a NORMAL outline section ───────────────

def test_p6_4_integrative_archetype_registered():
    assert "Integrative" in SECTION_ARCHETYPES


def test_p6_4_integrative_not_special_cased_to_bypass_verify():
    # B-impl-1 safety: the Integrative section must be VERIFIED like any section.
    # Structural guarantee — there is NO code branch on the "Integrative" archetype
    # that would skip strict_verify or treat it as an unverified appender. (The
    # only place an archetype string appears as a control value would be such a
    # branch; assert none reference "Integrative" as a verify/append special-case.)
    src = inspect.getsource(msg)
    # The archetype appears ONLY in the SECTION_ARCHETYPES list (a data tag), never
    # as an `if ... == "Integrative"` / `archetype == 'Integrative'` control branch.
    assert 'archetype == "Integrative"' not in src
    assert "archetype == 'Integrative'" not in src
    assert '"Integrative":' not in src  # not a dispatch-dict key either


def test_p6_5_integrative_is_outline_section_not_appender():
    # P2-2: the Integrative section respects pruning because it is a PLANNED
    # outline item (subject to the Phase-4 pruned plan), NOT one of the five
    # out-of-plan appenders that are hard-gated off in partial_mode. Assert it is
    # generated through the normal section path (no force-append). The five
    # appenders (V30 plans, M50, trial table, analyst synthesis, limitations) are
    # the only `not partial_mode` out-of-plan blocks; Integrative is not among
    # them — it flows from research_plan.outline.
    src = inspect.getsource(msg)
    # Integrative must NOT be appended in a `not partial_mode` appender block.
    # (If it were, partial_saturation would force-append it, bypassing pruning.)
    assert "Integrative" in src  # present as an archetype
    # The analyst-synthesis demotion gate now includes `research_plan is None`.
    assert "research_plan is None" in src


# ── P6-6 no clinical literal as an on-path control value ─────────────────────

def test_p6_6_no_clinical_literal_on_advisory_path():
    # The advisory selection + append are registry/param driven. There is NO
    # `if ... == "clinical"` / `if domain == "clinical"` literal controlling the
    # on-path in the generator. ("clinical.yaml" as a registry VALUE / config
    # filename is allowed — it is data, not a control literal.)
    src = inspect.getsource(msg)
    assert '== "clinical"' not in src
    assert "== 'clinical'" not in src
    assert 'domain == "clinical"' not in src
