"""Tests for the Research Planning Gate compiler + schema (S1).

Offline + deterministic. The LLM is a fixture stub (an injected ``client`` with
an async ``generate`` returning canned JSON), so NOTHING here hits the network.
These assert the S1 acceptance criteria from the consolidated design §8 / the
build task:

  (a) on the task-72 prompt the compiled contract carries journal-only + English
      as EXPLICIT hard terms with quote-verified spans, a literature_review
      deliverable, and coverage requirements;
  (b) an unspecified-recency prompt yields recency force=open (NEVER hard);
  (c) autonomous mode NEVER returns needs_input (no blocking, no input channel);
  (d) a hard term with origin=inferred is REJECTED by the deterministic validator.

Plus schema-level invariants (span quote-equality, hashing reproducibility,
fail-soft parsing) and the conservative fallback.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from src.polaris_graph.planning.planning_gate_schema import (
    FORCE_HARD,
    FORCE_OPEN,
    FORCE_PREFER,
    ORIGIN_EXPLICIT,
    ORIGIN_INFERRED,
    ContractTerm,
    PromptSpan,
    ResearchContract,
    contract_from_dict,
    plan_from_dict,
    sha256_of,
    validate_contract,
    validate_plan,
)
from src.polaris_graph.planning.research_planning_gate import (
    run_research_planning_gate,
)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

TASK_72_PROMPT = (
    "Please write a literature review on the restructuring impact of "
    "Artificial Intelligence (AI) on the labor market. Ensure the review only "
    "cites high-quality, English-language journal articles."
)

# unspecified recency: nothing in the text names a date window
NO_RECENCY_PROMPT = (
    "Summarize the main mechanisms by which gut microbiota influence host "
    "metabolism, and how diet modulates them."
)


def _span_for(prompt: str, phrase: str) -> dict:
    idx = prompt.find(phrase)
    assert idx != -1, f"phrase {phrase!r} not in prompt"
    return {"start": idx, "end": idx + len(phrase), "quote": phrase}


# ---------------------------------------------------------------------------
# Stub LLM client (injected; canned JSON; async generate -> .content)
# ---------------------------------------------------------------------------

class _Resp:
    def __init__(self, content: str) -> None:
        self.content = content


class _StubClient:
    """Returns canned JSON keyed by which system prompt is being used.

    The gate calls the contract compiler first (its system prompt starts with
    'You are the POLARIS Research Contract Compiler') then the plan compiler.
    """

    def __init__(self, contract_json: dict, plan_json: dict) -> None:
        self._contract = json.dumps(contract_json)
        self._plan = json.dumps(plan_json)
        self.calls: list[str] = []

    async def generate(self, prompt, system="", max_tokens=4096, temperature=0.0, **_):
        self.calls.append(system[:40])
        if system.startswith("You are the POLARIS Research Contract"):
            return _Resp(self._contract)
        return _Resp(self._plan)


def _task72_contract_json() -> dict:
    return {
        "contract": {
            "objective": [{
                "term_id": "objective.question",
                "dimension": "objective.question",
                "value": "restructuring impact of AI on the labor market",
                "origin": "explicit", "force": "open",
                "spans": [_span_for(TASK_72_PROMPT, "literature review")],
            }],
            "scope": [
                {
                    "term_id": "scope.language",
                    "dimension": "scope.source_languages",
                    "value": "en", "origin": "explicit", "force": "hard",
                    "spans": [_span_for(TASK_72_PROMPT, "English-language")],
                },
                {
                    "term_id": "scope.source_types",
                    "dimension": "scope.source_types",
                    "value": "journal_article", "origin": "explicit", "force": "hard",
                    "spans": [_span_for(TASK_72_PROMPT, "journal articles")],
                },
            ],
            "deliverable": [{
                "term_id": "deliverable.kind",
                "dimension": "deliverable.kind",
                "value": "literature_review", "origin": "explicit", "force": "hard",
                "spans": [_span_for(TASK_72_PROMPT, "literature review")],
            }],
            "coverage": [
                {"requirement_id": "cov1", "kind": "topic",
                 "statement": {"term_id": "cov1", "dimension": "content.coverage",
                               "value": "AI restructuring of labor market",
                               "origin": "inferred", "force": "open"}},
                {"requirement_id": "cov2", "kind": "topic",
                 "statement": {"term_id": "cov2", "dimension": "content.coverage",
                               "value": "employment effects", "origin": "inferred",
                               "force": "open"}},
                {"requirement_id": "cov3", "kind": "topic",
                 "statement": {"term_id": "cov3", "dimension": "content.coverage",
                               "value": "skill demand shifts", "origin": "inferred",
                               "force": "open"}},
                {"requirement_id": "cov4", "kind": "topic",
                 "statement": {"term_id": "cov4", "dimension": "content.coverage",
                               "value": "wage / inequality effects", "origin": "inferred",
                               "force": "open"}},
            ],
            "assumptions": [
                {"assumption_id": "a1", "statement": "decomposed labor-market impact into 4 topics",
                 "affected_term_ids": ["cov1", "cov2", "cov3", "cov4"], "origin": "inferred"},
            ],
        },
        "clause_coverage": [],
    }


def _task72_plan_json() -> dict:
    return {
        "plan": {
            "threads": [
                {"thread_id": f"t{i}", "question": f"q{i}", "mandatory": True,
                 "coverage_requirement_ids": [f"cov{i}"]}
                for i in range(1, 5)
            ],
            "query_intents": [
                {"intent_id": f"qi{i}", "thread_id": f"t{i}", "purpose": "discovery",
                 "source_type": "journal_article", "language": "en", "mandatory": True}
                for i in range(1, 5)
            ],
            "coverage_matrix": [
                {"contract_term_id": "scope.language", "owning_stages": ["retrieval"],
                 "query_intent_ids": ["qi1", "qi2", "qi3", "qi4"]},
                {"contract_term_id": "scope.source_types", "owning_stages": ["retrieval"],
                 "query_intent_ids": ["qi1", "qi2", "qi3", "qi4"]},
                {"contract_term_id": "deliverable.kind", "owning_stages": ["render"]},
            ],
            "budget": {"mandatory_lane_count": 4, "overflow_policy": "expand"},
            "stop_conditions": ["every mandatory thread has journal evidence"],
        }
    }


# ---------------------------------------------------------------------------
# (a) task-72: explicit hard journal-only + English with verified spans
# ---------------------------------------------------------------------------

def test_task72_journal_and_english_are_explicit_hard_with_spans():
    client = _StubClient(_task72_contract_json(), _task72_plan_json())
    result = asyncio.run(run_research_planning_gate(
        TASK_72_PROMPT, mode="autonomous", client=client,
    ))
    contract = result.contract

    by_dim = {t.dimension: t for t in contract.all_terms()}
    lang = by_dim["scope.source_languages"]
    assert lang.value == "en"
    assert lang.origin == ORIGIN_EXPLICIT
    assert lang.force == FORCE_HARD, "English-language is an explicit hard scope rule"
    assert lang.spans and lang.spans[0].matches_prompt(TASK_72_PROMPT)

    src = by_dim["scope.source_types"]
    assert src.value == "journal_article"
    assert src.origin == ORIGIN_EXPLICIT
    assert src.force == FORCE_HARD, "journal-only is an explicit hard scope rule"
    assert src.spans and src.spans[0].matches_prompt(TASK_72_PROMPT)

    deliv = by_dim["deliverable.kind"]
    assert deliv.value == "literature_review"

    # 4 coverage requirements present.
    assert len(contract.coverage) == 4

    # no validator errors on this contract.
    assert validate_contract(contract, TASK_72_PROMPT) == []

    # the plan's mandatory query intents carry the journal/English lanes.
    intents = result.plan.mandatory_query_intents()
    assert len(intents) == 4
    assert all(qi.source_type == "journal_article" for qi in intents)
    assert all(qi.language == "en" for qi in intents)


# ---------------------------------------------------------------------------
# (b) unspecified recency -> force=open, never hard
# ---------------------------------------------------------------------------

def test_unspecified_recency_is_open_never_hard():
    # The compiler represents an unspecified date as open/null (never a fabricated
    # cutoff). We model that: a date term with origin=inferred, force=open.
    contract_json = {
        "contract": {
            "objective": [{"term_id": "obj", "dimension": "objective.question",
                           "value": "gut microbiota + metabolism", "origin": "inferred",
                           "force": "open"}],
            "scope": [{
                "term_id": "scope.date",
                "dimension": "scope.date",
                "value": None, "origin": "inferred", "force": "open",
                "rationale": "no date window stated; left open with a soft freshness preference",
            }],
            "assumptions": [{"assumption_id": "a1",
                             "statement": "no recency stated; open date, prefer fresher",
                             "affected_term_ids": ["scope.date"], "origin": "inferred"},
                            {"assumption_id": "a2",
                             "statement": "objective inferred from the request paraphrase",
                             "affected_term_ids": ["obj"], "origin": "inferred"}],
        }
    }
    plan_json = {"plan": {"threads": [], "query_intents": [], "coverage_matrix": [],
                          "budget": {}, "stop_conditions": []}}
    client = _StubClient(contract_json, plan_json)
    result = asyncio.run(run_research_planning_gate(
        NO_RECENCY_PROMPT, mode="autonomous", client=client,
    ))
    date_term = next(t for t in result.contract.all_terms() if t.dimension == "scope.date")
    assert date_term.force == FORCE_OPEN
    assert date_term.force != FORCE_HARD
    assert date_term.value is None
    assert validate_contract(result.contract, NO_RECENCY_PROMPT) == []


def test_autonomous_downgrades_a_slipped_through_inferred_hard_date():
    # Adversarial: the model tries to make an inferred recency HARD. Autonomous
    # disclosure must downgrade it to preference (never a fabricated hard cutoff).
    contract_json = {
        "contract": {
            "objective": [{"term_id": "obj", "dimension": "objective.question",
                           "value": "x", "origin": "inferred", "force": "open"}],
            "scope": [{"term_id": "scope.date", "dimension": "scope.date",
                       "value": "2019..2025", "origin": "inferred", "force": "hard"}],
        }
    }
    plan_json = {"plan": {}}
    client = _StubClient(contract_json, plan_json)
    result = asyncio.run(run_research_planning_gate(
        NO_RECENCY_PROMPT, mode="autonomous", client=client,
    ))
    date_term = next(t for t in result.contract.all_terms() if t.dimension == "scope.date")
    assert date_term.force == FORCE_PREFER, "inferred hard date must be downgraded"
    # and the contract is clean after disclosure
    assert validate_contract(result.contract, NO_RECENCY_PROMPT) == []


# ---------------------------------------------------------------------------
# (c) autonomous mode NEVER returns needs_input
# ---------------------------------------------------------------------------

def test_autonomous_never_returns_needs_input_even_with_material_ambiguity():
    # A contract loaded with a material, cannot-proceed-open ambiguity would make
    # interactive mode block. Autonomous must NOT.
    contract_json = {
        "contract": {
            "objective": [{"term_id": "obj", "dimension": "objective.question",
                           "value": "ADAS liability", "origin": "explicit", "force": "open",
                           "spans": [{"start": 0, "end": 4, "quote": NO_RECENCY_PROMPT[:4]}]}],
            "ambiguities": [{
                "ambiguity_id": "amb1", "text": "Which jurisdiction governs?",
                "affected_term_ids": ["scope.jurisdiction"],
                "plausible_interpretations": ["US", "EU"],
                "material": True, "can_proceed_open": False,
                "decision_impact": ["retrieval", "outline"],
            }],
        }
    }
    plan_json = {"plan": {}}
    client = _StubClient(contract_json, plan_json)
    result = asyncio.run(run_research_planning_gate(
        NO_RECENCY_PROMPT, mode="autonomous", client=client,
    ))
    assert result.needs_input is False
    assert result.state == "auto_pinned"
    assert result.questions == []
    assert result.artifact.state != "needs_input"


def test_interactive_mode_does_ask_material_questions():
    # The dual proof: the SAME material ambiguity DOES block in interactive mode
    # (so the autonomous-never-blocks property is meaningful, not vacuous).
    contract_json = {
        "contract": {
            "objective": [{"term_id": "obj", "dimension": "objective.question",
                           "value": "ADAS liability", "origin": "inferred", "force": "open"}],
            "ambiguities": [{
                "ambiguity_id": "amb1", "text": "Which jurisdiction governs?",
                "affected_term_ids": ["scope.jurisdiction"],
                "plausible_interpretations": ["US", "EU"],
                "material": True, "can_proceed_open": False,
                "decision_impact": ["retrieval"],
            }],
        }
    }
    client = _StubClient(contract_json, {"plan": {}})
    result = asyncio.run(run_research_planning_gate(
        NO_RECENCY_PROMPT, mode="interactive", client=client,
    ))
    assert result.needs_input is True
    assert result.state == "needs_input"
    assert len(result.questions) == 1
    assert len(result.questions) <= 3


def test_interactive_caps_questions_at_three():
    ambs = [{
        "ambiguity_id": f"amb{i}", "text": f"question {i}?",
        "affected_term_ids": [f"term{i}"], "plausible_interpretations": ["a", "b"],
        "material": True, "can_proceed_open": False, "decision_impact": ["retrieval"],
    } for i in range(6)]
    contract_json = {"contract": {
        "objective": [{"term_id": "obj", "dimension": "objective.question",
                       "value": "x", "origin": "inferred", "force": "open"}],
        "ambiguities": ambs,
    }}
    client = _StubClient(contract_json, {"plan": {}})
    result = asyncio.run(run_research_planning_gate(
        NO_RECENCY_PROMPT, mode="interactive", client=client,
    ))
    assert len(result.questions) == 3


# ---------------------------------------------------------------------------
# (d) a hard term with origin=inferred is REJECTED by the validator
# ---------------------------------------------------------------------------

def test_inferred_hard_term_is_rejected_by_validator():
    contract = contract_from_dict({
        "scope": [{"term_id": "s1", "dimension": "scope.source_types",
                   "value": "journal_article", "origin": "inferred", "force": "hard"}],
    })
    errors = validate_contract(contract, "some prompt with no journal phrase")
    codes = {e.code for e in errors}
    assert "hard_not_explicit" in codes


def test_explicit_term_without_span_is_rejected():
    contract = contract_from_dict({
        "scope": [{"term_id": "s1", "dimension": "scope.source_types",
                   "value": "journal_article", "origin": "explicit", "force": "hard"}],
    })
    codes = {e.code for e in validate_contract(contract, "prompt")}
    assert "explicit_without_span" in codes


def test_explicit_span_quote_mismatch_is_rejected():
    contract = contract_from_dict({
        "scope": [{"term_id": "s1", "dimension": "scope.source_types",
                   "value": "journal_article", "origin": "explicit", "force": "hard",
                   "spans": [{"start": 0, "end": 5, "quote": "WRONG"}]}],
    })
    codes = {e.code for e in validate_contract(contract, "hello world")}
    assert "span_quote_mismatch" in codes


def test_inferred_value_without_assumption_is_flagged():
    contract = contract_from_dict({
        "scope": [{"term_id": "s1", "dimension": "scope.date", "value": "2020",
                   "origin": "inferred", "force": "open"}],
    })
    codes = {e.code for e in validate_contract(contract, "prompt")}
    assert "inferred_not_disclosed" in codes


# ---------------------------------------------------------------------------
# Schema invariants + hashing + fallback
# ---------------------------------------------------------------------------

def test_promptspan_quote_equality_invariant():
    p = "abcdef"
    good = PromptSpan(1, 3, "bc")
    bad = PromptSpan(1, 3, "zz")
    assert good.matches_prompt(p)
    assert not bad.matches_prompt(p)


def test_hashing_is_reproducible_and_deterministic():
    c = contract_from_dict({"objective": [{"term_id": "o", "dimension": "objective.question",
                                           "value": "q", "origin": "inferred", "force": "open"}]})
    assert sha256_of(c.to_dict()) == sha256_of(c.to_dict())
    c2 = contract_from_dict(c.to_dict())
    assert sha256_of(c.to_dict()) == sha256_of(c2.to_dict())


def test_artifact_recompute_hashes_populates_all_three():
    client = _StubClient(_task72_contract_json(), _task72_plan_json())
    result = asyncio.run(run_research_planning_gate(
        TASK_72_PROMPT, mode="autonomous", client=client,
    ))
    art = result.artifact
    assert art.contract_sha256 and len(art.contract_sha256) == 64
    assert art.plan_sha256 and len(art.plan_sha256) == 64
    assert art.artifact_sha256 and len(art.artifact_sha256) == 64
    assert art.contract_sha256 != art.plan_sha256


def test_fail_soft_parsing_tolerates_missing_and_unknown_keys():
    # scalar instead of list, unknown key, missing groups
    c = contract_from_dict({
        "objective": {"question": "the raw q"},   # grouped-object shape
        "scope": [],
        "totally_unknown_key": 123,
        "coverage": ["a bare string topic"],
    })
    assert any(t.value == "the raw q" for t in c.objective)
    assert len(c.coverage) == 1
    # never raised


def test_conservative_fallback_when_llm_output_unusable():
    class _BadClient:
        async def generate(self, prompt, system="", **_):
            return _Resp("not json at all {{{")

    result = asyncio.run(run_research_planning_gate(
        TASK_72_PROMPT, mode="autonomous", client=_BadClient(),
    ))
    # degraded, but never crashed and never blocked
    assert result.contract.compiler_degraded is True
    assert result.needs_input is False
    # the raw prompt survives as the objective (span-verified, open)
    obj = [t for t in result.contract.objective if t.value]
    assert obj and obj[0].value == TASK_72_PROMPT.strip()
    assert obj[0].force == FORCE_OPEN
    assert validate_contract(result.contract, TASK_72_PROMPT) == []


def test_off_path_raises_without_client_or_live_flag(monkeypatch):
    monkeypatch.delenv("PG_PLANNING_GATE_LIVE", raising=False)
    with pytest.raises(RuntimeError):
        asyncio.run(run_research_planning_gate(
            TASK_72_PROMPT, mode="autonomous", client=None,
        ))


def test_mode_must_be_explicit():
    client = _StubClient(_task72_contract_json(), _task72_plan_json())
    with pytest.raises(ValueError):
        asyncio.run(run_research_planning_gate(
            TASK_72_PROMPT, mode="magic", client=client,
        ))


def test_plan_validator_flags_uncovered_required_requirement():
    contract = contract_from_dict({
        "coverage": [{"requirement_id": "cov1", "kind": "topic", "required": True,
                      "statement": {"term_id": "cov1", "dimension": "content.coverage",
                                    "value": "x", "origin": "inferred", "force": "open"}}],
    })
    # plan with no mandatory intent for cov1
    plan = plan_from_dict({"threads": [], "query_intents": [], "coverage_matrix": []})
    codes = {e.code for e in validate_plan(plan, contract)}
    assert "requirement_without_intent" in codes


def test_plan_validator_flags_truncatable_mandatory_lane():
    contract = ResearchContract()
    plan = plan_from_dict({
        "query_intents": [{"intent_id": "qi1", "thread_id": "t1", "mandatory": True},
                          {"intent_id": "qi2", "thread_id": "t2", "mandatory": True}],
        "budget": {"mandatory_lane_count": 2, "max_queries": 1, "overflow_policy": "expand"},
    })
    codes = {e.code for e in validate_plan(plan, contract)}
    assert "mandatory_lane_truncatable" in codes
