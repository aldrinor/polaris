"""S3 — Outline FEED + gap-scope fix. BANKED-replay + unit tests (no live fetch).

Covers the four S3 acceptance obligations (consolidated design §6, build seq S3):

  1. THE BUG FIX — ``_tool_search_more_evidence`` now threads the gate's
     ``research_frame`` + ``protocol`` into ``run_live_retrieval`` (was dropped ->
     unscoped). Proven at the UNIT level by capturing the kwargs of a stubbed
     ``run_live_retrieval`` (NO network).
  2. FEED — required coverage obligations pre-loaded as PENDING gaps (NOT
     headings); term ledger built; explicit locks preserved.
  3. update_outline REJECTS dropping an explicit lock / the last owner of a
     binding term.
  4. refine_outline_from_seed replays BANKED corpora for the four named DRB tasks
     (30/61/76/90) — real refinement runs, locks + term-mappings preserved, and
     the gap-search call carries scope. OFF path byte-identical.

Everything is OFFLINE: the outline-agent decide/execute LLM calls and
``run_live_retrieval`` are stubbed; only pure data flows are exercised. No live
fetch, no ~35-min compose, no RACE/FACT scoring (per the guardrails).
"""

from __future__ import annotations

import asyncio
import os

import pytest

from src.polaris_graph.planning.planning_gate_schema import (
    FORCE_HARD,
    FORCE_PREFER,
    ORIGIN_EXPLICIT,
    ORIGIN_INFERRED,
    ContractTerm,
    CoverageBinding,
    CoverageRequirement,
    PromptSpan,
    QueryIntent,
    ResearchContract,
    ResearchExecutionPlan,
    SectionRequirement,
)
from src.polaris_graph.planning.retrieval_projection import from_contract_and_plan
import src.polaris_graph.outline.outline_gate_feed as F
import src.polaris_graph.outline.outline_agent as OA


# ---------------------------------------------------------------------------
# Banked corpora for the four named DRB tasks (30/61/76/90).
#
# These are small BANKED evidence pools shaped exactly like the champion cp2 fold-
# in rows (evidence_id / statement / title / tier / source_url), one per task. No
# corpus keyed to those task ids ships in the repo, so they are constructed here
# as deterministic fixtures — the point of the replay is that *real banked rows*
# (not a live fetch) flow through ``refine_outline_from_seed`` and the seed +
# ledger survive. Each pool is intentionally multi-theme so the seed outline has
# something to organize.
# ---------------------------------------------------------------------------

def _row(i: int, title: str, statement: str, tier: int = 1) -> dict:
    return {
        "evidence_id": f"ev_{i}",
        "title": title,
        "statement": statement,
        "tier": tier,
        "source_url": f"https://example.org/{i}",
        "provenance_class": "primary",
    }


BANKED_CORPORA: dict[int, dict] = {
    30: {  # Global South cooperation / civilizational exchange (zh prompt)
        "prompt": "全球南方合作如何推动文明交流互鉴？非西方现代化、后殖民主义、东方学、全球史。",
        "evidence": [
            _row(0, "Non-Western modernization theory", "Non-Western modernization reframes development away from a single Western path."),
            _row(1, "Postcolonial critique of development", "Postcolonial scholarship critiques residual colonial hierarchies in aid."),
            _row(2, "Orientalism and knowledge production", "Orientalism shaped how the Global North represents Southern societies."),
            _row(3, "Global history methodology", "Global history de-centers the nation-state as the unit of civilizational exchange."),
            _row(4, "South-South cooperation mechanisms", "South-South cooperation builds horizontal knowledge and trade linkages."),
        ],
        "required_coverage": ["non-Western modernization", "postcolonialism", "Orientalism", "global history"],
    },
    61: {  # Chub mackerel price dynamics, Pacific Rim markets
        "prompt": "Research on the price dynamics of chub mackerel in major aquatic markets of Pacific Rim countries.",
        "evidence": [
            _row(0, "Chub mackerel landings 2010-2020", "Chub mackerel landings fluctuated with El Nino cycles across the Pacific."),
            _row(1, "Tokyo wholesale market prices", "Tokyo wholesale prices for chub mackerel rose 30% over the decade."),
            _row(2, "Chinese import demand", "Chinese import demand shifted seasonal price peaks earlier."),
            _row(3, "Fuel cost pass-through", "Rising fuel costs were partially passed through to dock prices."),
            _row(4, "Quota policy effects", "Catch quotas tightened supply and lifted average prices."),
        ],
        "required_coverage": ["price trends", "supply and landings", "market demand"],
    },
    76: {  # Gut microbiota / intestinal function (en prompt)
        "prompt": "The significance of the gut microbiota in maintaining normal intestinal function.",
        "evidence": [
            _row(0, "Microbiota and barrier function", "The gut microbiota reinforces the intestinal epithelial barrier."),
            _row(1, "Short-chain fatty acids", "Microbial SCFAs fuel colonocytes and modulate inflammation."),
            _row(2, "Dysbiosis and disease", "Dysbiosis is associated with IBD and metabolic disorders."),
            _row(3, "Immune training", "Commensals train mucosal immunity from early life."),
            _row(4, "Diet and composition", "Diet is a primary determinant of microbiota composition."),
        ],
        "required_coverage": ["barrier function", "immune modulation", "dysbiosis"],
    },
    90: {  # Liability allocation, autonomous vehicles (en prompt)
        "prompt": "Analyze liability allocation in accidents involving vehicles with advanced driver assistance.",
        "evidence": [
            _row(0, "Product liability framework", "Product liability may attach to the ADAS manufacturer for defects."),
            _row(1, "Driver duty of care", "The human driver retains a duty of supervision under Level 2 systems."),
            _row(2, "Regulatory approaches", "Jurisdictions diverge on strict vs fault-based liability for AVs."),
            _row(3, "Data and black-box evidence", "Event data recorders shift the evidentiary burden in AV crashes."),
            _row(4, "Insurance models", "No-fault insurance pools are proposed to absorb AV accident risk."),
        ],
        "required_coverage": ["product liability", "driver duty", "regulatory approaches"],
    },
}


def _make_contract_and_plan(task: int, *, hard_journal: bool = True):
    """Build a pinned-style contract + plan for a banked task.

    Scope: journal-only + English (both HARD, explicit). Coverage: the task's
    ``required_coverage`` topics as required obligations. One explicit locked
    section ("Introduction") owning the first required topic, so the ledger has a
    lock + a binding-term owner to protect.
    """
    data = BANKED_CORPORA[task]
    scope = []
    if hard_journal:
        scope = [
            ContractTerm(
                term_id="sc.src", dimension="scope.source_types",
                value="peer-reviewed journal articles",
                origin=ORIGIN_EXPLICIT, force=FORCE_HARD,
                spans=[PromptSpan(0, 5, "x")],
            ),
            ContractTerm(
                term_id="sc.lang", dimension="scope.source_languages",
                value="en", origin=ORIGIN_EXPLICIT, force=FORCE_HARD,
            ),
        ]
    coverage = []
    for i, topic in enumerate(data["required_coverage"]):
        coverage.append(CoverageRequirement(
            requirement_id=f"rq.{i}", kind="topic",
            statement=ContractTerm(
                term_id=f"t.cov{i}", dimension="content.coverage", value=topic,
                origin=ORIGIN_EXPLICIT, force=FORCE_HARD,
            ),
            required=True,
        ))
    sections = [SectionRequirement(
        section_id="s.intro",
        title=ContractTerm(
            term_id="t.intro", dimension="deliverable.section", value="Introduction",
            origin=ORIGIN_EXPLICIT, force=FORCE_HARD,
        ),
        order=0, exact_title_lock=True, coverage_requirement_ids=["rq.0"],
    )]
    contract = ResearchContract(scope=scope, coverage=coverage, sections=sections)
    contract.contract_sha256 = "banked-" + str(task)
    plan = ResearchExecutionPlan(
        query_intents=[QueryIntent(
            intent_id="q1", thread_id="th1",
            concepts=data["prompt"].split()[:3], required_terms=["key"],
            mandatory=True,
        )],
        coverage_matrix=[CoverageBinding(
            contract_term_id="t.cov0", requirement_id="rq.0",
            section_ids=["s.intro"], owning_stages=["outline"],
        )],
    )
    return contract, plan


# a minimal stand-in for OutlineParseResult with the fields the loop reads.
class _FakeParseResult:
    def __init__(self, plans):
        self.plans = plans
        self.digest_stats = {}
        self.quantified_models = {}
        self.calc_claims = {}


def _seed_plans(task: int):
    """A tiny seed outline (SectionPlan list) for a task — includes the locked
    'Introduction' so the loop starts from a structure the ledger will protect."""
    from src.polaris_graph.generator.multi_section_generator import SectionPlan
    ev = BANKED_CORPORA[task]["evidence"]
    return [
        SectionPlan(title="Introduction", focus="scope", ev_ids=[ev[0]["evidence_id"]]),
        SectionPlan(title="Analysis", focus="core", ev_ids=[r["evidence_id"] for r in ev[1:3]]),
        SectionPlan(title="Discussion", focus="synthesis", ev_ids=[r["evidence_id"] for r in ev[3:]]),
    ]


# ===========================================================================
# 1. FEED-helper unit tests
# ===========================================================================

@pytest.mark.parametrize("task", [30, 61, 76, 90])
def test_coverage_seeds_are_obligations_not_headings(task):
    contract, _ = _make_contract_and_plan(task)
    seeds = F.coverage_gap_seeds(contract)
    # every REQUIRED coverage topic is present as an aspect...
    aspects = {s["aspect"] for s in seeds}
    for topic in BANKED_CORPORA[task]["required_coverage"]:
        assert topic in aspects, f"required topic {topic!r} missing from seeds"
    # ...and only the one EXPLICITLY bound to a locked section keeps a section
    # home; every other required topic stays unassigned (NOT a heading — the
    # round-1 coverage-to-heading bug must not recur).
    homed = [s for s in seeds if s["section"]]
    assert len(homed) == 1 and homed[0]["section"] == "Introduction"
    unassigned = [s for s in seeds if not s["section"]]
    assert len(unassigned) == len(BANKED_CORPORA[task]["required_coverage"]) - 1


def test_optional_coverage_not_seeded():
    contract = ResearchContract(coverage=[
        CoverageRequirement(
            requirement_id="rq.opt", kind="topic",
            statement=ContractTerm(term_id="t", dimension="content.coverage", value="an optional aside"),
            required=False,
        ),
    ])
    assert F.coverage_gap_seeds(contract) == []


def test_term_ledger_locks_and_binding_owners():
    contract, plan = _make_contract_and_plan(76)
    led = F.build_term_ledger(contract, coverage_matrix=plan.coverage_matrix)
    assert led["locked_titles"] == ["Introduction"]
    assert led["binding_term_owners"] == {"t.cov0": ["Introduction"]}
    # only HARD terms are binding
    assert "sc.src" in led["binding_term_ids"]
    assert "t.cov0" in led["binding_term_ids"]


def test_inferred_terms_are_not_binding():
    contract = ResearchContract(scope=[
        ContractTerm(term_id="soft.geo", dimension="scope.geographies", value="US",
                     origin=ORIGIN_INFERRED, force=FORCE_PREFER),
    ])
    led = F.build_term_ledger(contract)
    assert led["binding_term_ids"] == []
    assert led["binding_term_owners"] == {}


def test_gate_scope_routes_journals_and_protocol():
    contract, plan = _make_contract_and_plan(61)
    proj = from_contract_and_plan(contract, plan, original_prompt=BANKED_CORPORA[61]["prompt"])
    frame, protocol = F.gate_scope_for_gap_search(proj, base_question="mackerel prices")
    assert frame is not None
    assert "primary_literature" in list(getattr(frame, "evidence_needs", []))  # GO FIND journals
    assert protocol is not None and "research_question" in protocol


def test_gate_scope_failopen_on_none():
    assert F.gate_scope_for_gap_search(None) == (None, None)


def test_validate_revision_drop_lock_and_last_owner():
    contract, plan = _make_contract_and_plan(90)
    led = F.build_term_ledger(contract, coverage_matrix=plan.coverage_matrix)
    # dropping 'Introduction' violates BOTH the title lock and the last-owner rule
    v = F.validate_revision_against_ledger(
        led, titles_before=["Introduction", "Body"], titles_after=["Body"])
    assert any("explicit_title_lock_dropped" in x for x in v)
    assert any("last_owner_of_binding_term_dropped" in x for x in v)
    # a benign add is allowed
    assert F.validate_revision_against_ledger(
        led, titles_before=["Introduction", "Body"],
        titles_after=["Introduction", "Body", "New"]) == []


def test_validate_revision_empty_ledger_is_noop():
    assert F.validate_revision_against_ledger({}, titles_before=["A"], titles_after=[]) == []
    assert F.validate_revision_against_ledger(None, titles_before=["A"], titles_after=[]) == []


# ===========================================================================
# 2. THE BUG FIX — gap search now carries scope (unit-level, no network)
# ===========================================================================

class _StubResp:
    content = "scoped gap query"


class _StubClient:
    def __init__(self, *a, **k):
        pass

    async def generate(self, **kwargs):
        return _StubResp()

    async def close(self):
        pass


class _StubLiveResult:
    def __init__(self):
        self.evidence_rows = []      # empty => fold-in short-circuits (no network)
        self.candidates_total = 0


def _run(coro):
    # Py3.11: no implicit current event loop in a fresh thread. Own the loop.
    return asyncio.new_event_loop().run_until_complete(coro)


def test_gap_search_threads_scope_when_workspace_has_gate(monkeypatch):
    """With a gate research_frame + protocol on the workspace, the gap-search
    ``run_live_retrieval`` call MUST receive them. Captures the kwargs of a stub."""
    contract, plan = _make_contract_and_plan(76)
    proj = from_contract_and_plan(contract, plan, original_prompt=BANKED_CORPORA[76]["prompt"])
    frame, protocol = F.gate_scope_for_gap_search(proj, base_question="gut microbiota")
    assert frame is not None

    ws = OA.OutlineWorkspace(
        research_question="gut microbiota intestinal function",
        ev_store={},
        gate_research_frame=frame,
        gate_gap_protocol=protocol,
    )

    captured = {}

    def _fake_run_live_retrieval(**kwargs):
        captured.update(kwargs)
        return _StubLiveResult()

    # stub the LLM query-derive client and the retrieval entry point
    monkeypatch.setattr(
        "src.polaris_graph.llm.openrouter_client.OpenRouterClient", _StubClient,
    )
    monkeypatch.setattr(
        "src.polaris_graph.retrieval.live_retriever.run_live_retrieval",
        _fake_run_live_retrieval,
    )

    res = _run(OA._tool_search_more_evidence(
        ws, "stub-model", section="Analysis", aspect="dysbiosis mechanisms",
    ))
    assert "research_frame" in captured, "gap search dropped research_frame (BUG)"
    assert captured["research_frame"] is frame
    assert captured.get("protocol") is protocol
    assert res.tool_name == "search_more_evidence"


def test_gap_search_offpath_carries_no_scope(monkeypatch):
    """A workspace with NO gate scope (every champion caller) passes
    research_frame=None / protocol=None — byte-identical to the champion."""
    ws = OA.OutlineWorkspace(research_question="anything", ev_store={})
    captured = {}

    def _fake_run_live_retrieval(**kwargs):
        captured.update(kwargs)
        return _StubLiveResult()

    monkeypatch.setattr(
        "src.polaris_graph.llm.openrouter_client.OpenRouterClient", _StubClient,
    )
    monkeypatch.setattr(
        "src.polaris_graph.retrieval.live_retriever.run_live_retrieval",
        _fake_run_live_retrieval,
    )
    _run(OA._tool_search_more_evidence(ws, "stub-model", aspect="some aspect"))
    assert captured.get("research_frame") is None
    assert captured.get("protocol") is None


# ===========================================================================
# 3. update_outline ledger guard
# ===========================================================================

def test_update_outline_refuses_dropping_a_lock(monkeypatch):
    from src.polaris_graph.generator.multi_section_generator import SectionPlan
    contract, plan = _make_contract_and_plan(30)
    led = F.build_term_ledger(contract, coverage_matrix=plan.coverage_matrix)
    ws = OA.OutlineWorkspace(
        research_question="q",
        ev_store={"ev_0": BANKED_CORPORA[30]["evidence"][0]},
        outline_draft=[
            SectionPlan(title="Introduction", focus="", ev_ids=["ev_0"]),
            SectionPlan(title="Body", focus="", ev_ids=[]),
        ],
        term_ledger=led,
    )
    # a merge op that would collapse 'Introduction' into 'Body' -> drops the lock
    ops = [{"op": "merge", "titles": ["Introduction", "Body"], "new_title": "Combined"}]
    res = _run(OA._tool_update_outline(ws, ops=ops))
    assert res.success is False
    assert res.error == "contract_term_ledger_violation"
    # the outline was NOT mutated (Introduction survives)
    assert any(p.title == "Introduction" for p in ws.outline_draft)


def test_update_outline_allows_benign_reassign(monkeypatch):
    from src.polaris_graph.generator.multi_section_generator import SectionPlan
    contract, plan = _make_contract_and_plan(30)
    led = F.build_term_ledger(contract, coverage_matrix=plan.coverage_matrix)
    ws = OA.OutlineWorkspace(
        research_question="q",
        ev_store={"ev_0": BANKED_CORPORA[30]["evidence"][0],
                  "ev_1": BANKED_CORPORA[30]["evidence"][1]},
        outline_draft=[
            SectionPlan(title="Introduction", focus="", ev_ids=["ev_0"]),
            SectionPlan(title="Body", focus="", ev_ids=["ev_1"]),
        ],
        term_ledger=led,
    )
    ops = [{"op": "reassign", "title": "Body", "add_ev_ids": ["ev_0"]}]
    res = _run(OA._tool_update_outline(ws, ops=ops))
    # reassign keeps both titles -> no ledger violation; op applies (or is a
    # benign no-op) but is NEVER rejected for a ledger reason.
    assert res.error != "contract_term_ledger_violation"
    assert any(p.title == "Introduction" for p in ws.outline_draft)


# ===========================================================================
# 4. BANKED replay through refine_outline_from_seed (no live fetch)
# ===========================================================================

def _stub_agent_loop(monkeypatch, *, do_illegal_merge=False):
    """Replace OutlineAgent.run with a deterministic in-memory refinement that
    exercises the real update_outline seam (so the ledger guard actually fires)
    but issues NO LLM / network calls."""
    async def _fake_run(self):
        ws = self.workspace
        ws.turn = 2
        # a real refinement: reassign evidence between two existing sections via
        # the REAL _tool_update_outline (so the ledger guard is exercised).
        titles = [p.title for p in ws.outline_draft]
        if len(titles) >= 2 and ws.ev_store:
            some_ev = next(iter(ws.ev_store))
            await OA._tool_update_outline(
                ws, ops=[{"op": "reassign", "title": titles[-1], "add_ev_ids": [some_ev]}],
            )
        if do_illegal_merge and len(titles) >= 2:
            # attempt to drop the locked first section — the guard must refuse.
            await OA._tool_update_outline(
                ws, ops=[{"op": "merge", "titles": titles[:2], "new_title": "X"}],
            )
        ws.disclose("stub agentic loop: real refinement applied")
        return ws
    monkeypatch.setattr(OA.OutlineAgent, "run", _fake_run)


@pytest.mark.parametrize("task", [30, 61, 76, 90])
def test_banked_replay_refines_and_preserves_locks(task, monkeypatch):
    monkeypatch.setenv("PG_OUTLINE_AGENT", "1")
    monkeypatch.setenv("PG_OUTLINE_SECTION_FLOOR", "0")   # isolate the FEED behavior
    monkeypatch.setenv("PG_OUTLINE_THEME_FLOOR", "0")
    _stub_agent_loop(monkeypatch, do_illegal_merge=True)

    contract, plan = _make_contract_and_plan(task)
    seed = _FakeParseResult(_seed_plans(task))
    evidence = list(BANKED_CORPORA[task]["evidence"])

    parse_result, retried, in_tok, out_tok = _run(OA.refine_outline_from_seed(
        research_question=BANKED_CORPORA[task]["prompt"],
        evidence=evidence,
        seed_parse_result=seed,
        contract=contract,
        retrieval_projection=from_contract_and_plan(contract, plan),
        coverage_matrix=plan.coverage_matrix,
    ))

    # (a) real refinement ran (the loop executed, telemetry present)
    stats = parse_result.digest_stats.get("outline_agent", {})
    assert stats.get("turns", 0) >= 1
    assert stats.get("degraded_to_seed") in (False, None)

    # (b) the explicit lock survived — 'Introduction' is still present, and the
    #     illegal merge that tried to drop it was refused by the ledger guard.
    titles = [p.title for p in parse_result.plans]
    assert "Introduction" in titles, f"explicit lock lost for task {task}: {titles}"

    # (c) the required-coverage obligations were pre-loaded as PENDING gaps (as
    #     obligations, not headings): the ledger of the gap search carries them.
    #     We read them back from the disclosures the FEED emitted.
    discl = " ".join(stats.get("disclosures", []))
    assert "required-coverage obligation" in discl

    # (d) a ledger-violation refusal was disclosed (the illegal merge was blocked)
    assert "REFUSED" in discl or "ledger" in discl.lower()


def test_banked_replay_gap_search_carries_scope(monkeypatch):
    """End-to-end through refine_outline_from_seed: the workspace the loop runs on
    carries the gate scope, so any gap search it fires is scoped. Verified by
    capturing the workspace the (stubbed) agent received."""
    monkeypatch.setenv("PG_OUTLINE_AGENT", "1")
    seen = {}

    async def _capture_run(self):
        seen["frame"] = self.workspace.gate_research_frame
        seen["protocol"] = self.workspace.gate_gap_protocol
        seen["contract_hash"] = self.workspace.contract_hash
        self.workspace.turn = 1
        return self.workspace

    monkeypatch.setattr(OA.OutlineAgent, "run", _capture_run)

    contract, plan = _make_contract_and_plan(90)
    seed = _FakeParseResult(_seed_plans(90))
    _run(OA.refine_outline_from_seed(
        research_question=BANKED_CORPORA[90]["prompt"],
        evidence=list(BANKED_CORPORA[90]["evidence"]),
        seed_parse_result=seed,
        contract=contract,
        retrieval_projection=from_contract_and_plan(contract, plan),
        coverage_matrix=plan.coverage_matrix,
    ))
    assert seen["frame"] is not None, "gate scope never reached the workspace"
    assert "primary_literature" in list(getattr(seen["frame"], "evidence_needs", []))
    assert seen["protocol"] is not None
    assert seen["contract_hash"] == "banked-90"


# ===========================================================================
# 5. OFF / no-gate path byte-identical
# ===========================================================================

def test_no_gate_workspace_fields_are_inert(monkeypatch):
    """With no gate objects, refine_outline_from_seed leaves the workspace gate
    fields at their inert defaults (byte-identical to champion)."""
    monkeypatch.setenv("PG_OUTLINE_AGENT", "1")
    seen = {}

    async def _capture_run(self):
        seen["frame"] = self.workspace.gate_research_frame
        seen["protocol"] = self.workspace.gate_gap_protocol
        seen["ledger"] = dict(self.workspace.term_ledger)
        seen["hash"] = self.workspace.contract_hash
        seen["gaps"] = self.workspace.gap_ledger.pending_count
        self.workspace.turn = 1
        return self.workspace

    monkeypatch.setattr(OA.OutlineAgent, "run", _capture_run)
    seed = _FakeParseResult(_seed_plans(76))
    _run(OA.refine_outline_from_seed(
        research_question=BANKED_CORPORA[76]["prompt"],
        evidence=list(BANKED_CORPORA[76]["evidence"]),
        seed_parse_result=seed,
        # no contract / projection / matrix
    ))
    assert seen["frame"] is None
    assert seen["protocol"] is None
    assert seen["ledger"] == {}
    assert seen["hash"] == ""
    assert seen["gaps"] == 0


def test_off_path_import_only_no_gate_kwargs():
    """run_outline_agent_or_legacy keeps its full champion signature: the new
    gate kwargs are all None-default and keyword-only, so every existing caller
    is unaffected."""
    import inspect
    sig = inspect.signature(OA.run_outline_agent_or_legacy)
    for name in ("gate_contract", "gate_projection", "gate_coverage_matrix", "seed_outline"):
        assert name in sig.parameters
        assert sig.parameters[name].default is None
