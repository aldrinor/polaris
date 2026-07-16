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

@pytest.fixture(autouse=True)
def _pg_gate_off_by_default(monkeypatch):
    """Default the deterministic-promotion switch OFF for every test here.

    ``PG_GATE`` is the master gate flag; another module's e2e harness threads it
    into the PROCESS env (scripts/run_gate_e2e), which — depending on collection
    order — could leak into these unit tests. Pinning it OFF keeps the OFF-path
    stub tests deterministic; the promotion tests re-enable it explicitly via
    their own ``monkeypatch.setenv``."""
    monkeypatch.delenv("PG_GATE", raising=False)


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
# (a′) THE BUG FIX (drb_72): when the LLM compiler DROPS the source scope (the
# real-run failure — no journal / no source_types / "English" misfiled as OUTPUT
# language), the deterministic source-scope promoter (PG_GATE ON) restores
# journal-only + high-quality + English SOURCE-language as EXPLICIT HARD scope
# terms — the LLM must not be able to drop or downgrade them.
# ---------------------------------------------------------------------------

class _DroppingCompilerClient:
    """Reproduces the proven task-72 bug: the contract compiler returns a
    contract with NO source scope and mis-files English as the OUTPUT language.
    Deterministic promotion must repair it (no-invention: only span-backed)."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def generate(self, prompt, system="", max_tokens=4096, temperature=0.0, **_):
        self.calls.append(system[:40])
        if system.startswith("You are the POLARIS Research Contract"):
            return _Resp(json.dumps({"contract": {
                "objective": [{
                    "term_id": "objective.question",
                    "dimension": "objective.question",
                    "value": "AI restructuring of the labor market",
                    "origin": "inferred", "force": "open",
                }],
                # the bug: "English-language sources" misread as OUTPUT language.
                "deliverable": [{
                    "term_id": "deliverable.output_language",
                    "dimension": "deliverable.output_language",
                    "value": "English", "origin": "inferred", "force": "open",
                }],
                "assumptions": [{
                    "assumption_id": "a1",
                    "statement": "assumed output language English",
                    "affected_term_ids": ["deliverable.output_language"],
                    "origin": "inferred",
                }],
            }}))
        return _Resp(json.dumps({"plan": {
            "threads": [{"thread_id": "t1", "question": "AI labor market",
                         "mandatory": True}],
            "query_intents": [{"intent_id": "qi1", "thread_id": "t1",
                               "concepts": ["AI labor market"], "mandatory": True}],
        }}))


def test_task72_deterministic_source_scope_survives_a_dropping_compiler(monkeypatch):
    """THE INVERSION (rebuilt): the LLM compiler DROPS the source scope (real-run
    failure); the deterministic-authoritative monotonic merge reinstates
    journal-only + English SOURCE-language as EXPLICIT HARD scope.

    Quality: the CLAUSE LEDGER (Phase B — the generality gap) adds a deterministic
    quality parser, so the VERBATIM "high-quality" phrase under the enclosing
    "only" scope now yields a HARD, SPAN-BACKED ``source_quality=high`` term. This
    is NOT the old promoter's INVENTED quality (which fabricated ``high`` from a
    bare "journal"/"peer" facet with no quality text): here the phrase
    "high-quality" is literally in the prompt and hardness is inherited from the
    real "only" restriction scope — span-verified, never fabricated."""
    from src.polaris_graph.instruction.constraint_extractor import Constraints
    from src.polaris_graph.planning.retrieval_projection import from_artifact

    monkeypatch.setenv("PG_GATE", "1")  # the deterministic authority is gated ON
    # the rule-reader result the S0 adapter reconciles (task-72 ground truth).
    rr = Constraints(source_types=["journal_article", "high_quality"],
                     languages=["en"])
    client = _DroppingCompilerClient()
    result = asyncio.run(run_research_planning_gate(
        TASK_72_PROMPT, mode="autonomous", client=client, rule_reader=rr,
    ))
    contract = result.contract
    by_dim = {t.dimension: t for t in contract.scope}

    # journal source_type is present AS A HARD term (the bug: it was dropped). Its
    # canonical value is the ontology facet_id (peer_reviewed_journal), the alias
    # the rule-reader "journal_article" reconciles onto (RECON-2 §3).
    src = by_dim["scope.source_types"]
    assert src.value == "peer_reviewed_journal"
    assert src.force == FORCE_HARD, "journal-only must be a hard SOURCE term"
    assert src.origin == ORIGIN_EXPLICIT
    assert src.spans and src.spans[0].matches_prompt(TASK_72_PROMPT)
    # generic-IR: it is a source/kind IN constraint.
    assert src.subject == "source" and src.attribute == "kind"
    assert src.operator == "IN"

    # QUALITY (ledger): "high-quality" is a real prompt phrase under the "only"
    # restriction scope, so the clause-ledger quality parser authors a HARD,
    # SPAN-BACKED source_quality=high term. This is lossless preservation of a
    # stated constraint, NOT the old promoter's invented quality: the term MUST
    # carry a verbatim span (the no-invention guarantee — a hard term always has a
    # real anchor).
    qual = by_dim.get("scope.source_quality")
    assert qual is not None, "the 'high-quality' phrase must yield a quality term"
    assert qual.value == "high"
    assert qual.force == FORCE_HARD, "high-quality under 'only' is a hard rule"
    assert qual.origin == ORIGIN_EXPLICIT
    assert qual.spans and qual.spans[0].matches_prompt(TASK_72_PROMPT), (
        "a hard quality term must be anchored to the verbatim 'high-quality' span"
    )

    # English is a hard SOURCE language — NOT the deliverable output_language —
    # inheriting the enclosing hard 'only ... journal articles' clause.
    lang = by_dim["scope.source_languages"]
    assert lang.value == "en"
    assert lang.force == FORCE_HARD, "English is a hard SOURCE-language rule"
    assert lang.origin == ORIGIN_EXPLICIT
    assert lang.spans and lang.spans[0].matches_prompt(TASK_72_PROMPT)

    # the 'journal' signal is present in the pinned contract JSON.
    dumped = json.dumps(contract.to_dict(), ensure_ascii=False)
    assert "journal" in dumped.lower()
    assert "scope.source_types" in dumped

    # not degraded, and the contract validates clean (no invented hard terms).
    assert contract.compiler_degraded is False
    assert validate_contract(contract, TASK_72_PROMPT) == []
    assert result.enforcement_state == "pinned_executable"

    # the retrieval projection routes scholarly backends + hard-gates the menu.
    proj = from_artifact(result.artifact)
    scope = proj.to_scope_terms()
    assert "peer_reviewed_journal" in scope["hard"]
    assert "en" in scope["languages"]
    assert "primary_literature" in proj.evidence_needs, "GO-FIND-journals routing"


def test_task72_promotion_is_noop_when_pg_gate_off(monkeypatch):
    # With PG_GATE OFF the deterministic authority is inert: a dropping compiler
    # yields NO source scope (byte-identical to the pre-inversion path). Guards the
    # default-OFF guardrail.
    from src.polaris_graph.instruction.constraint_extractor import Constraints

    monkeypatch.delenv("PG_GATE", raising=False)
    rr = Constraints(source_types=["journal_article", "high_quality"],
                     languages=["en"])
    client = _DroppingCompilerClient()
    result = asyncio.run(run_research_planning_gate(
        TASK_72_PROMPT, mode="autonomous", client=client, rule_reader=rr,
    ))
    dims = {t.dimension for t in result.contract.scope}
    assert "scope.source_types" not in dims
    assert "scope.source_quality" not in dims
    assert "scope.source_languages" not in dims


# ---------------------------------------------------------------------------
# CLAUSE LEDGER — end-to-end losslessness through the whole gate (Phase B)
# ---------------------------------------------------------------------------

class _EmptyContractClient:
    """The worst case: the LLM drops EVERYTHING (returns a bare objective). The
    deterministic clause ledger + merge must reinstate every stated constraint."""

    async def generate(self, prompt, system="", max_tokens=4096, temperature=0.0, **_):
        if system.startswith("You are the POLARIS Research Contract"):
            return _Resp(json.dumps({"contract": {"objective": [{
                "term_id": "objective.question",
                "dimension": "objective.question",
                "value": "x", "origin": "inferred", "force": "open",
            }]}, "clause_coverage": []}))
        return _Resp(json.dumps({"plan": {"threads": [], "query_intents": [],
                                          "budget": {}}}))


_LEDGER_PROMPT = (
    "Analyze the market. Only use news and company press releases from 2024 "
    "onward. Do not cite blogs. Use only high-quality sources."
)


def test_ledger_reinstates_every_constraint_when_llm_drops_them(monkeypatch):
    """The recon's exact generality gap: a bare quality adjective, a coordinated
    unknown-kind set, an unknown-kind exclusion, and a date bound the champion
    extractor misses — all survive the LLM dropping them, deterministically."""
    monkeypatch.setenv("PG_GATE", "1")
    result = asyncio.run(run_research_planning_gate(
        _LEDGER_PROMPT, mode="autonomous", client=_EmptyContractClient(),
    ))
    scope = {t.dimension: t for t in result.contract.scope}

    # (a) quality: "high-quality" under "only" → hard, span-backed.
    q = scope["scope.source_quality"]
    assert q.value == "high" and q.force == FORCE_HARD
    assert q.spans[0].matches_prompt(_LEDGER_PROMPT)

    # (b) date: "from 2024 onward" under "only" → GTE, hard.
    d = scope["scope.date"]
    assert d.value == "2024-01-01" and d.force == FORCE_HARD
    assert d.operator == "GTE"

    # (c) coordination: news + company press releases as a hard IN set.
    kinds = {t.value for t in result.contract.scope if t.dimension == "scope.source_types"}
    assert {"news", "company press releases"} <= kinds
    for t in result.contract.scope:
        if t.dimension == "scope.source_types":
            assert t.force == FORCE_HARD and t.operator == "IN"

    # (d) exclusion: "blogs" (unknown kind) preserved as NOT_IN — never positive.
    excl = [t for t in result.contract.all_terms()
            if t.dimension == "content.exclusion"]
    assert any(t.value == "blogs" and t.operator == "NOT_IN" for t in excl)

    # the ledger is persisted; every deontic clause is dispositioned.
    assert result.artifact.clause_ledger, "the ledger must be persisted on the artifact"
    deontic = [c for c in result.artifact.clause_ledger if c.get("deontic")]
    assert len(deontic) >= 3


def test_ledger_preserves_unnormalizable_clause_as_opaque_blocked(monkeypatch):
    """A deontic clause NO deterministic parser can normalize becomes a first-class
    OPAQUE hard term → enforcement_state blocked_unsupported. Never silence."""
    monkeypatch.setenv("PG_GATE", "1")
    prompt = (
        "Summarize telecom trends. You must consult industry white papers "
        "issued by regional network operators."
    )
    result = asyncio.run(run_research_planning_gate(
        prompt, mode="autonomous", client=_EmptyContractClient(),
    ))
    opaque = [t for t in result.contract.all_terms() if t.is_opaque()]
    assert opaque, "an un-normalizable obligation must be preserved as opaque"
    t = opaque[0]
    assert t.origin == ORIGIN_EXPLICIT and t.force == FORCE_HARD
    assert t.spans[0].matches_prompt(prompt)
    # the honest enforcement state: a hard opaque term is blocked, never claimed.
    assert result.enforcement_state == "blocked_unsupported"
    # the contract still validates (opaque is a first-class, valid status).
    assert validate_contract(result.contract, prompt) == []


def test_ledger_is_inert_when_pg_gate_off(monkeypatch):
    """OFF guardrail: with PG_GATE OFF the ledger never runs — no clause_ledger on
    the artifact, no ledger-derived scope terms, empty enforcement state (the
    artifact is byte-identical to the pre-ledger champion path)."""
    monkeypatch.delenv("PG_GATE", raising=False)
    result = asyncio.run(run_research_planning_gate(
        _LEDGER_PROMPT, mode="autonomous", client=_EmptyContractClient(),
    ))
    assert result.artifact.clause_ledger == []
    assert "clause_ledger" not in result.artifact.to_dict()
    assert result.enforcement_state == ""
    assert result.contract.scope == [], "no ledger candidates authored when OFF"


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


# ---------------------------------------------------------------------------
# I-gate-089 / FX-01: the reasoning-first compile budget must be adequate
# (the drb_72 live-probe truncation: glm-5.2 hit finish_reason='length' at 8192).
# ---------------------------------------------------------------------------

class _RecordingClient:
    """Stub that records the max_tokens / reasoning_max_tokens the gate passes,
    and returns valid canned JSON so the compile succeeds (no fallback)."""

    def __init__(self, contract_json: dict, plan_json: dict) -> None:
        self._contract = json.dumps(contract_json)
        self._plan = json.dumps(plan_json)
        self.calls: list[dict] = []

    async def generate(
        self, prompt, system="", max_tokens=4096, temperature=0.0,
        reasoning_max_tokens=None, **_,
    ):
        self.calls.append(
            {"max_tokens": max_tokens, "reasoning_max_tokens": reasoning_max_tokens}
        )
        if system.startswith("You are the POLARIS Research Contract"):
            return _Resp(self._contract)
        return _Resp(self._plan)


def test_compile_budget_is_adequate_for_reasoning_first_model():
    """The compile/plan calls must request a budget large enough that a
    reasoning-first model (glm-5.2: reasoning prelude + content) does not
    truncate at finish_reason='length' — the exact drb_72 probe crash. The
    old 8192 was inadequate; assert the caller budget is at least the champion
    reasoning-first floor AND that the reasoning pool leaves real content room."""
    from src.polaris_graph.planning import research_planning_gate as rpg

    client = _RecordingClient(_task72_contract_json(), _task72_plan_json())
    result = asyncio.run(run_research_planning_gate(
        TASK_72_PROMPT, mode="autonomous", client=client,
    ))

    # The canned JSON is valid, so the compile SUCCEEDED — no conservative fallback,
    # no truncation-driven degrade. (The probe crash forced the fallback.)
    assert result.contract.compiler_degraded is False
    assert result.needs_input is False

    # At least one contract-compile call and one plan-compile call were made.
    assert len(client.calls) >= 2

    # The champion's reasoning-first floor (openrouter_client
    # PG_REASONING_FIRST_MIN_MAX_TOKENS default) is 32768; the compile budget must
    # be at least that so glm-5.2's ~5k reasoning tokens + content fit without
    # finish_reason='length'. The old inadequate cap was 8192.
    _MIN_ADEQUATE = 32768
    for call in client.calls:
        assert call["max_tokens"] >= _MIN_ADEQUATE, call
        # The reasoning pool must be BOUNDED and leave a real content slice
        # (content headroom = max_tokens - pool). It must never consume the
        # whole budget (that is the starvation the probe hit).
        pool = call["reasoning_max_tokens"]
        assert pool is not None, call
        assert 0 < pool <= call["max_tokens"] // 2, call
        content_headroom = call["max_tokens"] - pool
        assert content_headroom >= _MIN_ADEQUATE // 2, call

    # Sanity: the module constants themselves are the adequate values.
    assert rpg._CONTRACT_MAX_TOKENS >= _MIN_ADEQUATE
    assert rpg._PLAN_MAX_TOKENS >= _MIN_ADEQUATE


# ---------------------------------------------------------------------------
# FX-02 (drb_72 live probe): the contract compiler is an LLM — it copies the
# verbatim quote correctly but DRIFTS on character offsets, so an otherwise
# valid full-strength contract tripped 8 fatal `span_quote_mismatch` errors and
# fell to the compiler_degraded=True conservative fallback (coverage=0). The
# compiler now re-anchors each span from its quote before validating, so the
# quote (which the model gets right) is authoritative and the offset (which it
# gets wrong) is re-derived. No-invention is preserved: a quote NOT present in
# the prompt is never re-anchored and still fails validation.
# ---------------------------------------------------------------------------

def _drifted_span(prompt: str, phrase: str, drift: int) -> dict:
    """A span whose quote is verbatim-correct but whose offsets are shifted by
    ``drift`` — exactly the LLM failure mode observed on the drb_72 live probe."""
    idx = prompt.find(phrase)
    assert idx != -1, f"phrase {phrase!r} not in prompt"
    return {"start": idx + drift, "end": idx + len(phrase) + drift, "quote": phrase}


def _task72_contract_json_with_drifted_offsets() -> dict:
    """The task-72 contract as the live LLM actually emits it: correct quotes,
    WRONG offsets (drift of a few chars each). Pre-fix this produced 8 fatal
    span_quote_mismatch errors and forced the degraded fallback."""
    return {
        "contract": {
            "objective": [{
                "term_id": "objective.question",
                "dimension": "objective.question",
                "value": "restructuring impact of AI on the labor market",
                "origin": "explicit", "force": "open",
                "spans": [_drifted_span(TASK_72_PROMPT, "literature review", -2)],
            }],
            "scope": [
                {
                    "term_id": "scope.language",
                    "dimension": "scope.source_languages",
                    "value": "en", "origin": "explicit", "force": "hard",
                    "spans": [_drifted_span(TASK_72_PROMPT, "English-language", 3)],
                },
                {
                    "term_id": "scope.source_types",
                    "dimension": "scope.source_types",
                    "value": "journal_article", "origin": "explicit", "force": "hard",
                    "spans": [_drifted_span(TASK_72_PROMPT, "journal articles", -4)],
                },
            ],
            "deliverable": [{
                "term_id": "deliverable.kind",
                "dimension": "deliverable.kind",
                "value": "literature_review", "origin": "explicit", "force": "hard",
                "spans": [_drifted_span(TASK_72_PROMPT, "literature review", -2)],
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
            ],
            "assumptions": [
                {"assumption_id": "a1", "statement": "decomposed labor-market impact",
                 "affected_term_ids": ["cov1", "cov2"], "origin": "inferred"},
            ],
        },
        "clause_coverage": [],
    }


def test_offset_drift_is_reanchored_not_degraded_on_task72():
    """FX-02: a contract with correct quotes but drifted offsets must compile
    FULL-STRENGTH (compiler_degraded=False, coverage>0) — the offsets are
    re-derived from the quotes rather than tripping span_quote_mismatch and
    forcing the conservative fallback (the drb_72 probe's half-strength path)."""
    client = _StubClient(
        _task72_contract_json_with_drifted_offsets(), _task72_plan_json()
    )
    result = asyncio.run(run_research_planning_gate(
        TASK_72_PROMPT, mode="autonomous", client=client,
    ))
    contract = result.contract

    # THE core acceptance: full-strength, not the degraded fallback.
    assert result.state == "auto_pinned"
    assert contract.compiler_degraded is False
    assert len(contract.coverage) > 0
    assert result.needs_input is False

    # The re-anchored spans now quote-match, so the contract is error-free and
    # the journal-only + English hard terms survived as EXPLICIT (no-invention:
    # still origin=explicit, still force=hard, still a verbatim span).
    assert validate_contract(contract, TASK_72_PROMPT) == []
    by_dim = {t.dimension: t for t in contract.all_terms()}
    lang = by_dim["scope.source_languages"]
    src = by_dim["scope.source_types"]
    assert lang.origin == ORIGIN_EXPLICIT and lang.force == FORCE_HARD
    assert src.origin == ORIGIN_EXPLICIT and src.force == FORCE_HARD
    assert lang.spans[0].matches_prompt(TASK_72_PROMPT)
    assert src.spans[0].matches_prompt(TASK_72_PROMPT)
    # at least one explicit hard term (journal-only) is present.
    explicit_hard = [
        t for t in contract.hard_terms() if t.origin == ORIGIN_EXPLICIT
    ]
    assert explicit_hard


def test_reanchor_never_invents_support_for_a_fabricated_quote():
    """No-invention guard: re-anchoring corrects offsets ONLY when the quote is
    genuinely in the prompt. A quote absent from the prompt is left untouched and
    still fails validation, so a hard term can never be fabricated by drift."""
    from src.polaris_graph.planning.planning_gate_schema import (
        reanchor_contract_spans,
    )

    contract = contract_from_dict({
        "scope": [{
            "term_id": "scope.fake",
            "dimension": "scope.source_types",
            "value": "peer_reviewed_only",
            "origin": "explicit", "force": "hard",
            # a quote the user NEVER wrote — pure fabrication.
            "spans": [{"start": 0, "end": 18, "quote": "peer-reviewed only"}],
        }],
    })
    reanchor_contract_spans(contract, TASK_72_PROMPT)
    # the fabricated quote is not in the prompt, so it is NOT re-anchored and the
    # span still mismatches -> the hard term is rejected (no invention).
    codes = {e.code for e in validate_contract(contract, TASK_72_PROMPT)}
    assert "span_quote_mismatch" in codes


def test_reanchor_unit_corrects_offsets_from_quote():
    """Unit: reanchor_contract_spans re-derives offsets from the verbatim quote."""
    from src.polaris_graph.planning.planning_gate_schema import (
        reanchor_contract_spans,
    )

    contract = contract_from_dict({
        "scope": [{
            "term_id": "scope.lang", "dimension": "scope.source_languages",
            "value": "en", "origin": "explicit", "force": "hard",
            "spans": [_drifted_span(TASK_72_PROMPT, "English-language", 5)],
        }],
    })
    # pre-reanchor the offset is wrong.
    assert not contract.scope[0].spans[0].matches_prompt(TASK_72_PROMPT)
    reanchor_contract_spans(contract, TASK_72_PROMPT)
    sp = contract.scope[0].spans[0]
    assert sp.matches_prompt(TASK_72_PROMPT)
    assert TASK_72_PROMPT[sp.start:sp.end] == "English-language"


# ---------------------------------------------------------------------------
# BUG B (drb_72 unregistered-slug crash): the e2e harness must resolve task 72
# to the REGISTERED lineage slug so run_gate_b's forced official-question bind
# does not fail-loud-raise on the bare 'drb_72' slug.
# ---------------------------------------------------------------------------

def test_e2e_harness_resolves_task72_to_registered_official_slug():
    from scripts.dr_benchmark.gate0_lineage import (
        DRB_SLUGS_WITHOUT_CANONICAL_GOLD,
        SLUG_TO_IDX,
        assert_drb_slug_registered,
    )
    from scripts.run_gate_e2e import _query_dict_for_task, _registered_slug_for_task

    # The bare 'drb_72' was UNREGISTERED (the ValueError the probe hit).
    assert "drb_72" not in SLUG_TO_IDX
    assert "drb_72" not in DRB_SLUGS_WITHOUT_CANONICAL_GOLD

    # The harness now resolves task 72 to its registered slug -> canonical DRB-II idx 56
    # (the id<->idx offset: task 72 -> idx 56, NOT 72 — the official GenAI-labor question).
    slug = _registered_slug_for_task("72")
    assert slug == "drb_72_ai_labor"
    assert SLUG_TO_IDX[slug] == 56

    # The lineage guard (mirrored by run_gate_b's fail-loud check) now PASSES for this slug —
    # so run_gate_b_query no longer raises the "UNREGISTERED in gate0_lineage" ValueError.
    assert_drb_slug_registered(slug)  # must NOT raise

    # The query dict the sweep consumes carries the registered slug (+ the verbatim prompt).
    task = {"id": "72", "prompt": TASK_72_PROMPT, "language": "en"}
    q = _query_dict_for_task(task)
    assert q["slug"] == "drb_72_ai_labor"
    assert q["question"] == TASK_72_PROMPT


# ===========================================================================
# INVERSION REBUILD (Phase B) — generic IR, span-loss fix, monotonic merge,
# lossless fallback, honest enum handling, bare-quote spans, validators.
# ===========================================================================

from src.polaris_graph.planning.planning_gate_schema import (  # noqa: E402
    NORM_OPAQUE,
    OP_GTE,
    OP_IN,
    OP_NOT_IN,
    PromptSpan as _SchemaSpan,
    validate_monotonicity,
)
from src.polaris_graph.planning.candidate_adapter import (  # noqa: E402
    candidate_term_id,
    reconcile_candidates,
)
from src.polaris_graph.instruction.constraint_extractor import Constraints  # noqa: E402


# --- (1) generic IR: additive fields round-trip; legacy term is byte-identical ---

def test_generic_ir_fields_are_additive_and_optional():
    # A term with none of the generic-IR fields serializes to the LEGACY shape
    # (no new keys) — the byte-identity guardrail for the OFF path.
    legacy = ContractTerm(term_id="t", dimension="scope.source_types", value="x",
                          origin=ORIGIN_EXPLICIT, force=FORCE_PREFER,
                          spans=[PromptSpan(0, 1, "x")])
    d = legacy.to_dict()
    for k in ("subject", "attribute", "operator", "value_set", "boolean_group",
              "stage_owner", "capability_id", "normalization_status"):
        assert k not in d, f"legacy term must not emit generic-IR key {k!r}"

    # A term WITH generic-IR fields round-trips them.
    rich = ContractTerm(term_id="t2", dimension="scope.source_types", value="news_media",
                       origin=ORIGIN_EXPLICIT, force=FORCE_HARD, spans=[PromptSpan(0, 1, "x")],
                       subject="source", attribute="kind", operator=OP_IN,
                       value_set=["news_media"], stage_owner="eligibility",
                       normalization_status="exact")
    back = ContractTerm.from_dict(rich.to_dict())
    assert back.subject == "source" and back.attribute == "kind"
    assert back.operator == OP_IN and back.value_set == ["news_media"]
    assert back.stage_owner == "eligibility" and back.normalization_status == "exact"


# --- (2) generic registry: date→GTE, exclusion→NOT_IN, unknown kind→opaque ---

def test_registry_maps_date_exclusion_and_opaque_kind_generically():
    p = ("Write a report. Only use news articles and company press releases from "
         "2024 onward. No blogs.")
    cands = reconcile_candidates(p, rule_reader=Constraints(
        source_types=["news"], exclusions=["blogs"]))
    by = {(c.dimension, str(c.value)): c for c in cands}

    # date is a GTE recency term with an ISO value.
    date = next(c for c in cands if c.dimension == "date.recency")
    assert date.operator == OP_GTE
    assert str(date.value).startswith("2024")

    # exclusion is a NOT_IN term, hard.
    exc = next(c for c in cands if c.dimension == "content.exclusion")
    assert exc.operator == OP_NOT_IN and exc.force == FORCE_HARD

    # a kind not in the ontology ("news" bare token) stays a FIRST-CLASS OPAQUE
    # value — never dropped.
    opaque = [c for c in cands if c.normalization_status == NORM_OPAQUE]
    assert opaque, "an unmapped kind must be preserved as opaque, never dropped"


# --- (3) span-loss fix: journal-only regex + rule-reader source-type carry spans ---

def test_span_loss_fixed_journal_only_and_rule_reader_source_type():
    p = "Write a review. Only cite peer-reviewed journal articles."
    # intake journal-only regex now carries a real span (was spans=[]).
    cands = reconcile_candidates(p)
    st = [c for c in cands if c.dimension == "source.types"]
    assert st, "expected a source-type candidate"
    assert any(c.spans for c in st), "journal-only must now carry a verbatim span"
    for c in st:
        for s in c.spans:
            assert p[s.start:s.end] == s.quote

    # rule-reader canonical token 'journal_article' recovers a span via its
    # surface form 'journal article' in the prompt.
    cands2 = reconcile_candidates(p, rule_reader=Constraints(source_types=["journal_article"]))
    st2 = [c for c in cands2 if c.dimension == "source.types"]
    assert any(c.spans for c in st2)


# --- (4) monotonic merge: LLM cannot drop a deterministic explicit candidate ---

def test_monotonicity_validator_flags_a_dropped_candidate():
    # a contract missing a deterministic candidate id fails monotonicity.
    contract = contract_from_dict({"objective": [], "scope": []})
    errs = validate_monotonicity(contract, {"det.source.kind.peer_reviewed_journal"})
    assert any(e.code == "candidate_dropped" for e in errs)

    # once the term is present, it passes.
    contract2 = contract_from_dict({"scope": [{
        "term_id": "det.source.kind.peer_reviewed_journal",
        "dimension": "scope.source_types", "value": "peer_reviewed_journal",
        "origin": "explicit", "force": "hard",
        "spans": [{"start": 0, "end": 1, "quote": "x"}],
    }]})
    assert validate_monotonicity(
        contract2, {"det.source.kind.peer_reviewed_journal"}) == []


# --- (5) bare-quote spans + honest bad-enum surfacing ---

def test_promptspan_accepts_a_bare_quote_string():
    # the model may emit a bare quote string; offsets are placeholders (-1) until
    # re-anchored. This deletes the "span must be an object" failure class.
    sp = _SchemaSpan.from_dict("journal articles")
    assert sp.quote == "journal articles"
    assert sp.start == -1 and sp.end == -1
    # after re-anchoring against a prompt that contains it, it matches.
    from src.polaris_graph.planning.planning_gate_schema import _reanchor_span
    prompt = "please cite journal articles only"
    fixed = _reanchor_span(sp, prompt)
    assert prompt[fixed.start:fixed.end] == "journal articles"


def test_bad_force_enum_is_surfaced_not_silently_downgraded():
    # an out-of-vocab force is NO LONGER silently coerced to open; it is surfaced.
    t = ContractTerm.from_dict({"term_id": "t", "dimension": "scope.x",
                               "value": "v", "origin": "explicit", "force": "definitely"})
    assert t.force == "definitely"  # kept verbatim, not silently defaulted
    contract = ResearchContract(scope=[t])
    errs = validate_contract(contract, "")
    assert any(e.code == "bad_force" for e in errs)


def test_mandatory_synonym_maps_to_hard_never_open():
    # 'mandatory' really means hard — it must never silently become open.
    t = ContractTerm.from_dict({"term_id": "t", "dimension": "scope.x", "value": "v",
                               "origin": "explicit", "force": "mandatory",
                               "spans": [{"start": 0, "end": 1, "quote": "v"}]})
    assert t.force == FORCE_HARD


# --- (6) lossless fallback (PG_GATE ON): every explicit constraint survives ---

def test_lossless_fallback_preserves_deterministic_constraints(monkeypatch):
    monkeypatch.setenv("PG_GATE", "1")

    class _BadClient:
        async def generate(self, prompt, system="", **_):
            return _Resp("not json {{{")

    rr = Constraints(source_types=["journal_article"], languages=["en"])
    result = asyncio.run(run_research_planning_gate(
        TASK_72_PROMPT, mode="autonomous", client=_BadClient(), rule_reader=rr,
    ))
    # degraded (LLM failed) BUT the deterministic source scope SURVIVED.
    assert result.contract.compiler_degraded is True
    dims = {t.dimension: t for t in result.contract.scope}
    assert "scope.source_types" in dims, "explicit source scope must survive the fallback"
    assert dims["scope.source_types"].force == FORCE_HARD
    assert result.enforcement_state == "degraded_lossless"
    assert validate_contract(result.contract, TASK_72_PROMPT) == []


def test_lossless_fallback_no_category_leakage(monkeypatch):
    # a deliverable/format candidate must NOT leak into scope in the fallback.
    monkeypatch.setenv("PG_GATE", "1")

    class _BadClient:
        async def generate(self, prompt, system="", **_):
            return _Resp("nope")

    rr = Constraints(format="literature_review", tone="academic")
    result = asyncio.run(run_research_planning_gate(
        "Write a lit review, keep it academic.", mode="autonomous",
        client=_BadClient(), rule_reader=rr,
    ))
    scope_dims = {t.dimension for t in result.contract.scope}
    assert not any(d.startswith("deliverable") or d.startswith("rhetoric")
                  for d in scope_dims), "deliverable/rhetoric must not leak into scope"
