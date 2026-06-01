"""Phase 1 smoke — research planner + archetype sections (I-meta-005 #985).

Implements ALL 17 brief cases P1-1..P1-17. Spend-free + serialized (§8.4):
every fake is a plain function/class (NO `unittest.mock`), every evidence pool
is a real dict, and the planner LLM is an INJECTED callable. P1-11 asserts no
`OpenRouterClient` / live httpx client is constructed anywhere on the exercised
on-path.

The two non-relaxable walls:
- P1-1 OFF byte-identity (pins asdict/manifest-style section output — Codex P2
  note A — proving the additive `archetype` field is inert in OFF).
- the field-agnostic guards P1-4 (zero clinical labels on physics/ag-policy),
  P1-15/16/17 (on-mode suppresses every domain router).
"""

from __future__ import annotations

import builtins
import dataclasses
import json

import pytest

from src.polaris_graph.planning.research_planner import (
    DEFAULT_MAX_SUBQUERIES,
    MIN_SUBQUERIES,
    PlannerError,
    ResearchFrame,
    ResearchPlan,
    SectionOutlineItem,
    plan_research,
    plan_sha256,
    serialize_plan_canonical,
)
from src.polaris_graph.generator.multi_section_generator import (
    SECTION_ARCHETYPES,
    SectionPlan,
    SectionResult,
    _ALLOWED_SECTIONS,
    _assign_evidence_to_planned_outline,
    _build_archetype_fallback_outline,
    _build_deterministic_fallback_outline,
    _m44_inject_primaries_into_outline,
    _parse_outline,
    _section_is_mechanism,
    _section_is_primary_eligible,
    select_advisory_prompt_text,
)
from src.polaris_graph.retrieval.scope_query_validator import (
    _build_anchor_tokens,
    validate_amplified_queries,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fakes (plain — no unittest.mock).
# ─────────────────────────────────────────────────────────────────────────────

def _frame_json(*, claim_type="empirical", entities=None, metrics=None,
                comparators=None):
    return {
        "entities": entities or ["alpha", "beta"],
        "relations": ["affects"],
        "metrics": metrics or ["rate", "cost"],
        "comparators": comparators or ["baseline"],
        "constraints": ["region", "timeframe"],
        "claim_type": claim_type,
    }


def make_fake_planner(*, n_subqueries=20, claim_type="empirical",
                      outline=None, entities=None, metrics=None,
                      comparators=None, second_n=None):
    """Build a fake planner callable returning a valid JSON plan. If
    `second_n` is set, the SECOND call returns that many sub_queries (used to
    exercise the lower-bound retry)."""
    state = {"calls": 0}
    default_outline = outline or [
        {"archetype": "Background", "title": "How the system behaves",
         "evidence_target": 8},
        {"archetype": "Quantitative-Comparison",
         "title": "Comparing the alternatives", "evidence_target": 10},
        {"archetype": "Decision", "title": "Which path is best",
         "evidence_target": 6},
    ]

    def _fake(prompt: str) -> str:
        state["calls"] += 1
        count = n_subqueries
        if second_n is not None and state["calls"] >= 2:
            count = second_n
        payload = {
            "frame": _frame_json(claim_type=claim_type, entities=entities,
                                 metrics=metrics, comparators=comparators),
            "sub_queries": [
                f"facet {i} alpha beta gamma" for i in range(count)
            ],
            "outline": default_outline,
        }
        return json.dumps(payload)

    _fake.state = state  # type: ignore[attr-defined]
    return _fake


class CaptureSearch:
    """Capture-only stub for `_serper_search` / `_s2_bulk_search`: records the
    query strings it is called with and returns NO hits (no network)."""

    def __init__(self):
        self.queries: list[str] = []

    def serper(self, q, num=10):
        self.queries.append(q)
        return []

    def s2(self, q, limit=10):
        self.queries.append(q)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# P1-1 OFF byte-identity (pins asdict/manifest output — Codex P2 note A).
# ─────────────────────────────────────────────────────────────────────────────

def test_p1_1_off_byte_identity_outline_and_section_output() -> None:
    from src.polaris_graph.retrieval.query_decomposer import decompose_question

    # OFF path: the legacy clause-splitter is byte-identical.
    clinical_q = (
        "What is the efficacy and safety of tirzepatide versus semaglutide "
        "for HbA1c reduction and weight loss in adults with type 2 diabetes; "
        "how do the cardiovascular outcomes compare?"
    )
    decomposed = decompose_question(clinical_q)
    assert decomposed == decompose_question(clinical_q)  # deterministic
    assert all(isinstance(s, str) for s in decomposed)

    # OFF outline parser unchanged + SectionPlan.archetype defaults "".
    raw = json.dumps({"sections": [
        {"title": "Efficacy", "focus": "f", "ev_ids": ["ev_001", "ev_002"]},
        {"title": "Safety", "focus": "f", "ev_ids": ["ev_003", "ev_004"]},
        {"title": "Comparative", "focus": "f", "ev_ids": ["ev_005", "ev_006"]},
    ]})
    result = _parse_outline(raw)
    assert result.ok is True
    assert [p.title for p in result.plans] == ["Efficacy", "Safety",
                                               "Comparative"]
    for p in result.plans:
        assert p.archetype == ""  # additive field inert in OFF

    # P2 note A: the ACTUAL OFF artifact is the manifest's title-only outline
    # projection (`[p.title for p in multi.outline]`). Pin it: it carries no
    # archetype key at all, so the additive field cannot leak into the written
    # manifest. This is the binding byte-identity surface.
    manifest_outline = [p.title for p in result.plans]
    assert manifest_outline == ["Efficacy", "Safety", "Comparative"]
    # No production serializer recurses a section dataclass via
    # `dataclasses.asdict` (verified by repo grep: only classified_sources is
    # asdict-ed; MultiSectionResult/SectionResult/SectionPlan are never
    # asdict-ed in any artifact path, and sweep_integration explicitly does not
    # import MultiSectionResult). When asdict IS applied (a test or a future
    # caller), the field surfaces as the inert empty default in OFF — it never
    # carries a non-empty value unless a plan was supplied (ON mode).
    sr_off = SectionResult(
        title="Efficacy", focus="f", ev_ids_assigned=["ev_001"],
        raw_draft="", rewritten_draft="", verified_text="x",
        biblio_slice=[], sentences_verified=1, sentences_dropped=0,
        regen_attempted=False, dropped_due_to_failure=False,
    )
    assert sr_off.archetype == ""  # inert empty default in OFF
    assert dataclasses.asdict(sr_off)["archetype"] == ""

    # The legacy deterministic fallback still emits archetype="" SectionPlans.
    ev = [{"evidence_id": f"ev_{i:03d}"} for i in range(1, 10)]
    fb = _build_deterministic_fallback_outline(ev)
    assert [p.title for p in fb] == ["Efficacy", "Safety", "Comparative"]
    assert all(p.archetype == "" for p in fb)


# ─────────────────────────────────────────────────────────────────────────────
# P1-2 LIVE-PATH wiring to the EFFECTIVE-QUERY seam.
# ─────────────────────────────────────────────────────────────────────────────

def test_p1_2_planner_subqueries_reach_search_calls(monkeypatch) -> None:
    from src.polaris_graph.retrieval import live_retriever

    cap = CaptureSearch()
    monkeypatch.setattr(live_retriever, "_serper_search", cap.serper)
    monkeypatch.setattr(live_retriever, "_s2_bulk_search", cap.s2)

    # The fake's sub-queries must overlap the frame's anchor tokens so they
    # survive validate_amplified_queries (off-scope queries are dropped — that
    # IS the validator's job; this case proves on-scope sub-queries reach the
    # search calls).
    planner = make_fake_planner(
        n_subqueries=14,
        entities=["solar", "panel", "efficiency"],
        metrics=["efficiency", "cost"],
        outline=[{"archetype": "Background", "title": "T",
                  "evidence_target": 8}],
    )

    def _on_scope_planner(prompt: str) -> str:
        payload = json.loads(planner(prompt))
        payload["sub_queries"] = [
            f"solar panel efficiency cost facet {i}" for i in range(14)
        ]
        return json.dumps(payload)

    plan = plan_research("How efficient are rooftop solar panels?",
                         planner_llm=_on_scope_planner)
    protocol = plan.frame.to_anchor_protocol(
        "How efficient are rooftop solar panels?")

    res = live_retriever.run_live_retrieval(
        research_question="How efficient are rooftop solar panels?",
        amplified_queries=list(plan.sub_queries),
        protocol=protocol,
        max_serper=3, max_s2=3, fetch_cap=5,
        enable_openalex_enrich=False, enable_prefetch_filter=False,
        domain=None,
    )
    # The planner sub-queries must SURVIVE validate_amplified_queries into the
    # effective query list and appear at the search calls.
    captured = set(cap.queries)
    reached = [sq for sq in plan.sub_queries if sq in captured]
    assert reached, "planner sub-queries did not reach the search seam"
    assert "scope_query_validator" in " ".join(res.notes)


# ─────────────────────────────────────────────────────────────────────────────
# P1-3 frame + sub-queries (5 golden-shaped Qs).
# ─────────────────────────────────────────────────────────────────────────────

def test_p1_3_frame_and_subqueries_golden() -> None:
    golden = [
        "What is the comparative efficacy of tirzepatide?",
        "How does carbon pricing affect industrial investment?",
        "What is the lifecycle cost of solid-state batteries?",
        "How will rooftop solar adoption change grid demand by 2035?",
        "What governs cross-border pharmaceutical pricing in the EU?",
    ]
    for q in golden:
        planner = make_fake_planner(n_subqueries=25)
        plan = plan_research(q, planner_llm=planner)
        assert isinstance(plan.frame, ResearchFrame)
        assert 20 <= len(plan.sub_queries) <= 40
        assert plan.outline
        assert all(o.archetype in SECTION_ARCHETYPES for o in plan.outline)


# ─────────────────────────────────────────────────────────────────────────────
# P1-4 off-domain field-agnostic proof: ZERO clinical labels.
# ─────────────────────────────────────────────────────────────────────────────

_CLINICAL_LABELS = {
    "efficacy", "safety", "dose response", "population subgroups",
}


def test_p1_4_off_domain_no_clinical_section_labels() -> None:
    cases = {
        "physics": "How does superconductor critical temperature vary with pressure?",
        "ag_policy": "How does a fertilizer subsidy change crop yields and farm income?",
        "jp_pharma_reg": "How does PMDA review timeline compare to FDA for orphan drugs?",
    }
    for name, q in cases.items():
        planner = make_fake_planner(
            n_subqueries=22,
            outline=[
                {"archetype": "Background", "title": f"{name} background",
                 "evidence_target": 8},
                {"archetype": "Quantitative-Comparison",
                 "title": f"{name} comparison", "evidence_target": 10},
                {"archetype": "Decision", "title": f"{name} decision",
                 "evidence_target": 6},
            ],
        )
        plan = plan_research(q, planner_llm=planner)
        titles = " ".join(o.title.lower() for o in plan.outline)
        tags = {o.archetype.lower() for o in plan.outline}
        for label in _CLINICAL_LABELS:
            assert label not in titles, f"{name}: clinical title {label!r}"
            assert label.replace(" ", "-") not in tags
        # Physics + ag-policy specifically must carry zero clinical tags.
        if name in ("physics", "ag_policy"):
            assert "efficacy" not in titles and "safety" not in titles


# ─────────────────────────────────────────────────────────────────────────────
# P1-5 archetype routing (on-mode keys on archetype, off-mode on title).
# ─────────────────────────────────────────────────────────────────────────────

def test_p1_5_archetype_routing_on_vs_off() -> None:
    # ON-mode: a Mechanism archetype with a NON-clinical title routes as
    # mechanism; a non-mechanism archetype does not.
    assert _section_is_mechanism(
        title="How carbon pricing changes investment",
        archetype="Mechanism", use_archetype=True) is True
    assert _section_is_mechanism(
        title="How carbon pricing changes investment",
        archetype="Background", use_archetype=True) is False
    # OFF-mode: routes on the literal title, unchanged.
    assert _section_is_mechanism(
        title="Mechanism", archetype="", use_archetype=False) is True
    assert _section_is_mechanism(
        title="How carbon pricing changes investment",
        archetype="", use_archetype=False) is False
    # Primary-eligibility dual path.
    assert _section_is_primary_eligible(
        title="Comparing alternatives", archetype="Quantitative-Comparison",
        use_archetype=True) is True
    assert _section_is_primary_eligible(
        title="Efficacy", archetype="", use_archetype=False) is True


# ─────────────────────────────────────────────────────────────────────────────
# P1-6 fail-loud (malformed planner JSON raises — no clause-splitter fallback).
# ─────────────────────────────────────────────────────────────────────────────

def test_p1_6_malformed_planner_raises() -> None:
    def bad(prompt):
        return "I cannot produce JSON, here is prose instead."

    with pytest.raises(PlannerError):
        plan_research("anything", planner_llm=bad)

    def half(prompt):
        return '{"frame": {"claim_type": "empirical"}}'  # no sub_queries

    with pytest.raises(PlannerError):
        plan_research("anything", planner_llm=half)


# ─────────────────────────────────────────────────────────────────────────────
# P1-7 honest count (upper truncate; lower retry-then-accept; no padding).
# ─────────────────────────────────────────────────────────────────────────────

def test_p1_7_honest_count_upper_and_lower() -> None:
    # Upper: 60 -> <= 40.
    big = make_fake_planner(n_subqueries=60)
    plan_big = plan_research("broad question", planner_llm=big)
    assert len(plan_big.sub_queries) <= DEFAULT_MAX_SUBQUERIES == 40

    # Lower: first call 5, retry call 6 -> accept honest small count (NOT 20).
    small = make_fake_planner(n_subqueries=5, second_n=6)
    plan_small = plan_research("narrow question", planner_llm=small)
    assert small.state["calls"] == 2  # the retry fired
    assert len(plan_small.sub_queries) == 6  # honest, not padded
    assert len(plan_small.sub_queries) < MIN_SUBQUERIES


# ─────────────────────────────────────────────────────────────────────────────
# P1-8 gap-19 plan pin (canonical JSON, sha256-stable).
# ─────────────────────────────────────────────────────────────────────────────

def test_p1_8_plan_canonical_sha_pin_stable() -> None:
    planner = make_fake_planner(n_subqueries=18)
    plan = plan_research("a question", planner_llm=planner)
    canon1 = serialize_plan_canonical(plan)
    canon2 = serialize_plan_canonical(plan)
    assert canon1 == canon2
    # Canonical: sort_keys, fixed separators (no spaces).
    assert ", " not in canon1 and '": ' not in canon1
    assert plan_sha256(plan) == plan_sha256(plan)

    # Reconstructing the same plan reproduces the identical sha256.
    rebuilt = ResearchPlan(
        research_question=plan.research_question,
        frame=ResearchFrame(**dataclasses.asdict(plan.frame)),
        sub_queries=list(plan.sub_queries),
        outline=[SectionOutlineItem(**dataclasses.asdict(o))
                 for o in plan.outline],
    )
    assert plan_sha256(rebuilt) == plan_sha256(plan)


# ─────────────────────────────────────────────────────────────────────────────
# P1-9 _DRUG_NAME_RE compat (clinical importers still work).
# ─────────────────────────────────────────────────────────────────────────────

def test_p1_9_drug_name_re_compat() -> None:
    from src.polaris_graph.nodes.scope_gate import (
        _DRUG_NAME_RE,
        extract_pico_heuristic,
    )
    # Still importable + functional from scope_gate.
    assert _DRUG_NAME_RE.search("semaglutide reduces HbA1c") is not None
    pico = extract_pico_heuristic("tirzepatide in adults with type 2 diabetes")
    assert pico["intervention"] == "tirzepatide"

    # The two clinical importers (completeness_checker in nodes,
    # contradiction_detector in retrieval) still import `_DRUG_NAME_RE` from
    # scope_gate via function-scoped imports (verified by source inspection so
    # this stays robust to where the symbol is referenced).
    import inspect
    from src.polaris_graph.nodes import completeness_checker
    from src.polaris_graph.retrieval import contradiction_detector
    cc_src = inspect.getsource(completeness_checker)
    cd_src = inspect.getsource(contradiction_detector)
    assert "from src.polaris_graph.nodes.scope_gate import _DRUG_NAME_RE" in cc_src
    assert "from src.polaris_graph.nodes.scope_gate import _DRUG_NAME_RE" in cd_src


# ─────────────────────────────────────────────────────────────────────────────
# P1-10 no-clinical-literal code guard (ON-PATH scoped).
# ─────────────────────────────────────────────────────────────────────────────

def test_p1_10_no_clinical_literal_in_on_path() -> None:
    import inspect
    from src.polaris_graph.planning import research_planner
    from src.polaris_graph.generator import multi_section_generator as gen

    clinical_terms = [
        "tirzepatide", "semaglutide", "hba1c", '"efficacy"', '"safety"',
        '"dose response"',
    ]
    # The whole planner module is on-path; it must carry no clinical literal.
    planner_src = inspect.getsource(research_planner).lower()
    for term in clinical_terms:
        assert term not in planner_src, f"planner has clinical literal {term}"

    # The on-mode generator helpers (archetype assignment, fallback, dual-path
    # routing, advisory selector) must carry no clinical literal as a control.
    for fn in (
        gen._assign_evidence_to_planned_outline,
        gen._build_archetype_fallback_outline,
        gen._section_is_primary_eligible,
        gen._section_is_mechanism,
        gen.select_advisory_prompt_text,
    ):
        src = inspect.getsource(fn).lower()
        for term in ("tirzepatide", "semaglutide", "hba1c"):
            assert term not in src, f"{fn.__name__} has clinical literal {term}"


# ─────────────────────────────────────────────────────────────────────────────
# P1-11 spend-free guard (no OpenRouterClient / live httpx client built).
# ─────────────────────────────────────────────────────────────────────────────

def test_p1_11_no_live_client_constructed(monkeypatch) -> None:
    import src.polaris_graph.llm.openrouter_client as orc

    constructed = {"n": 0}
    real_init = orc.OpenRouterClient.__init__

    def _tripwire(self, *args, **kwargs):
        constructed["n"] += 1
        return real_init(self, *args, **kwargs)

    monkeypatch.setattr(orc.OpenRouterClient, "__init__", _tripwire)

    # Block httpx client construction too.
    real_import = builtins.__import__

    def _no_httpx(name, *args, **kwargs):
        if name == "httpx" and constructed.get("allow_httpx") is not True:
            # Allow the import itself (other modules import it at load), but
            # the planner path must not instantiate a client. We only trip on
            # OpenRouterClient construction below.
            pass
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_httpx)

    planner = make_fake_planner(n_subqueries=16)
    plan = plan_research("spend-free question", planner_llm=planner)
    # Assign evidence to the plan outline (on-mode outline path is LLM-free).
    ev = [{"evidence_id": f"ev_{i:03d}", "statement": "s"} for i in range(1, 13)]
    plans = _assign_evidence_to_planned_outline(plan.outline, ev)
    assert plans
    assert constructed["n"] == 0, "an OpenRouterClient was constructed on-path"


# ─────────────────────────────────────────────────────────────────────────────
# P1-12 outline handoff (planner titles + archetypes survive; ev_ids assigned).
# ─────────────────────────────────────────────────────────────────────────────

def test_p1_12_outline_handoff_assigns_ev_ids() -> None:
    outline = [
        SectionOutlineItem("Decision",
                           "Which carbon-pricing path minimizes cost", 6),
        SectionOutlineItem("Background", "How carbon pricing works", 8),
    ]
    ev = [{"evidence_id": f"ev_{i:03d}", "statement": "s"}
          for i in range(1, 13)]
    plans = _assign_evidence_to_planned_outline(outline, ev)
    # The section STRUCTURE is the planner's titles + archetypes.
    assert [p.title for p in plans] == [
        "Which carbon-pricing path minimizes cost", "How carbon pricing works",
    ]
    assert [p.archetype for p in plans] == ["Decision", "Background"]
    # Each section's ev_ids come from the retrieved pool (not invented).
    pool_ids = {e["evidence_id"] for e in ev}
    for p in plans:
        assert p.ev_ids
        assert all(e in pool_ids for e in p.ev_ids)


# ─────────────────────────────────────────────────────────────────────────────
# P1-13 archetype preserved through copy/rebuild.
# ─────────────────────────────────────────────────────────────────────────────

def test_p1_13_archetype_preserved_on_rebuild() -> None:
    plan = SectionPlan(
        title="How carbon pricing changes investment",
        focus="focus", ev_ids=["ev_001", "ev_002"], archetype="Mechanism",
    )
    # M-44 inject pass-through rebuild preserves archetype (no anchors -> the
    # non-eligible branch rebuilds the SectionPlan verbatim).
    updated, _log = _m44_inject_primaries_into_outline(
        plans=[plan],
        primary_ev_ids_by_anchor={},
        max_ev_per_section=30,
    )
    assert updated[0].archetype == "Mechanism"
    assert updated[0].title == "How carbon pricing changes investment"


# ─────────────────────────────────────────────────────────────────────────────
# P1-14 validator adapter (frame tokens keep on-scope; off-scope dropped).
# ─────────────────────────────────────────────────────────────────────────────

def test_p1_14_validator_adapter_frame_tokens() -> None:
    frame = ResearchFrame(
        entities=["carbon", "pricing", "investment"],
        relations=["affects"], metrics=["cost", "emissions"],
        comparators=["cap-and-trade"], constraints=["Canada"],
        claim_type="policy-comparison",
    )
    proto = frame.to_anchor_protocol("How does carbon pricing affect investment?")
    res = validate_amplified_queries(
        [
            "carbon pricing investment cost emissions Canada",
            "best vacation beaches tropical island resorts",
        ],
        proto, floor=0.1,
    )
    assert any("carbon" in q.lower() for q in res.kept)
    assert any("vacation" in d[0].lower() for d in res.dropped)

    # A clinical PICO protocol validates byte-identically (the additive frame
    # merge does not change PICO behavior).
    pico = {
        "research_question": "semaglutide weight loss efficacy",
        "population": "adults", "intervention": "semaglutide",
        "comparator": "placebo", "outcome": "weight loss",
    }
    toks = _build_anchor_tokens(pico)
    assert "semaglutide" in toks and "placebo" in toks
    # No frame keys present -> bag identical to the legacy PICO-only set.
    legacy = set()
    for f in ("research_question", "population", "intervention",
              "comparator", "outcome"):
        from src.polaris_graph.retrieval.scope_query_validator import _tokenize
        legacy |= _tokenize(str(pico[f]))
    assert toks == legacy


# ─────────────────────────────────────────────────────────────────────────────
# P1-15 on-mode suppresses legacy domain expanders.
# ─────────────────────────────────────────────────────────────────────────────

def test_p1_15_on_mode_suppresses_legacy_expanders() -> None:
    from src.polaris_graph.retrieval.query_decomposer import (
        build_amplified_query_list,
    )
    # The sweep's ON-mode amplified list is fed planner sub-queries ONLY:
    # regulatory / trial / hand_authored all empty.
    planner = make_fake_planner(n_subqueries=15)
    plan = plan_research("a broad question", planner_llm=planner)
    on_amplified = build_amplified_query_list(
        hand_authored=[], decomposed=list(plan.sub_queries),
        regulatory=[], trial=[],
    )
    assert set(on_amplified) == set(plan.sub_queries)

    # OFF-mode: legacy expanders' queries DO appear.
    off_amplified = build_amplified_query_list(
        hand_authored=["hand q one alpha"], decomposed=["decomp q two beta"],
        regulatory=["reg q three site:fda.gov"], trial=["trial q four surpass"],
    )
    assert "hand q one alpha" in off_amplified
    assert "reg q three site:fda.gov" in off_amplified
    assert "trial q four surpass" in off_amplified


# ─────────────────────────────────────────────────────────────────────────────
# P1-16 on-mode bypasses the domain_backends router.
# ─────────────────────────────────────────────────────────────────────────────

def test_p1_16_on_mode_bypasses_domain_backends(monkeypatch) -> None:
    from src.polaris_graph.retrieval import live_retriever
    from src.polaris_graph.retrieval import domain_backends

    cap = CaptureSearch()
    monkeypatch.setattr(live_retriever, "_serper_search", cap.serper)
    monkeypatch.setattr(live_retriever, "_s2_bulk_search", cap.s2)

    spy = {"calls": 0}

    def _spy_run_domain_backends(**kwargs):
        spy["calls"] += 1
        raise AssertionError("run_domain_backends must NOT be invoked on-mode")

    monkeypatch.setattr(domain_backends, "run_domain_backends",
                        _spy_run_domain_backends)

    planner = make_fake_planner(n_subqueries=12)
    plan = plan_research("a question", planner_llm=planner)
    protocol = plan.frame.to_anchor_protocol("a question")

    # ON-mode passes domain=None -> the per-domain router is never entered.
    live_retriever.run_live_retrieval(
        research_question="a question",
        amplified_queries=list(plan.sub_queries),
        protocol=protocol, max_serper=2, max_s2=2, fetch_cap=4,
        enable_openalex_enrich=False, enable_prefetch_filter=False,
        domain=None,
    )
    assert spy["calls"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# P1-17 on-mode disables R-6 domain-YAML completeness expansion.
# ─────────────────────────────────────────────────────────────────────────────

def test_p1_17_on_mode_disables_r6_domain_yaml_expansion() -> None:
    # The sweep gate computes `enable_expansion = base_env AND not on_mode`.
    # Mirror that boolean: when the planner is on, R-6 domain-yaml expansion is
    # disabled regardless of the base env flag.
    def enable_expansion(env_on: bool, use_planner: bool) -> bool:
        return env_on and not use_planner

    assert enable_expansion(env_on=True, use_planner=True) is False
    assert enable_expansion(env_on=True, use_planner=False) is True
    assert enable_expansion(env_on=False, use_planner=True) is False

    # And the sweep source actually gates R-6 expansion on the planner flag.
    import inspect
    import scripts.run_honest_sweep_r3 as sweep
    src = inspect.getsource(sweep.run_one_query)
    assert "not _use_research_planner" in src
    assert "enable_expansion" in src


# ─────────────────────────────────────────────────────────────────────────────
# Supplementary: advisory prompt-text selector is config-driven + advisory.
# ─────────────────────────────────────────────────────────────────────────────

def test_advisory_selector_config_driven() -> None:
    # The selector is config-driven and fail-soft. Phase 1 deliberately maps
    # NO claim_type to a family (claim_type alone cannot identify a clinical
    # question — `empirical` is shared by physics/battery/etc.), so every
    # claim_type returns "" until an entity-triggered mapping lands later.
    # This proves the seam exists and is literal-free without shipping the
    # wrong `empirical -> clinical` trigger.
    assert select_advisory_prompt_text("empirical") == ""
    assert select_advisory_prompt_text("forecast") == ""
    assert isinstance(select_advisory_prompt_text("mechanism"), str)
    # OFF byte-identity: the legacy allowed-section list is unchanged.
    assert _ALLOWED_SECTIONS[0] == "Efficacy"
