"""Phase C — the control-path test (P0-A: contract IS wired to retrieval).

This test pins the BEHAVIORAL BAR the gate rebuild had to clear. It FAILED on the
pre-Phase-C branch (the seam shipped an empty-contract champion adapter) and now
PASSES: Phase C switched ``run_honest_sweep_r3.py:run_one_query``'s FS retrieval
seam to build its projection from the pinned ``PlanningGateArtifact`` via
``retrieval_projection.from_artifact`` (merged additively with the champion
plan's sub-queries for breadth, so the CONTRACT drives scope).

It asserts, against the REAL retrieval seam (no network, no LLM), two things:

1. ARTIFACT IDENTITY REACHES RETRIEVAL. When ``PG_GATE=1``, the projection the FS
   retrieval seam consults is compiled from the pinned ``PlanningGateArtifact``
   via ``retrieval_projection.from_artifact(gate_artifact)`` — it carries the
   artifact's pinned ``contract_sha256``. The pre-Phase-C seam called
   ``retrieval_projection.from_champion_plan(_research_plan, ...)``, which built a
   ``_ChampionPlanProjection`` over an EMPTY ``ResearchContract()`` (its hash
   never reached retrieval — a shadow artifact). That adapter is now only the
   artifact-missing fallback and is NOT wired at the seam.

2. TWO CONTRACTS → TWO ELIGIBLE SOURCE SETS. Two DIFFERENT contracts over the
   SAME candidate/corpus fixture — one allowing all sources, one hard-limiting to
   journal articles from 2024 onward — produce DIFFERENT eligible/citable source
   sets, because each is projected through ``from_artifact`` and its hard-scope
   terms reach the eligibility predicate. The gate gates.

Everything is OFFLINE and deterministic: no ``run_one_query`` drive, no network,
no LLM. We bind to the real seam two ways — (a) a source-level trace of the
gate-on FS seam in ``run_honest_sweep_r3.py`` proving it wires ``from_artifact``
and NOT ``from_champion_plan``, and (b) the real projection functions
(``from_artifact_with_champion_breadth`` / ``from_champion_plan``) over real
schema fixtures, proving the behavioral consequence.
"""

from __future__ import annotations

import pathlib

from src.polaris_graph.planning import retrieval_projection as rp
from src.polaris_graph.planning.planning_gate_schema import (
    PlanningGateArtifact,
    ResearchExecutionPlan,
    contract_from_dict,
    plan_from_dict,
)

# The live gate-on FS retrieval seam. The test traces THIS exact block so the
# behavioral bar is anchored to the real control path, not a paraphrase.
_SWEEP_PATH = (
    pathlib.Path(__file__).resolve().parents[2]
    / "scripts"
    / "run_honest_sweep_r3.py"
)
_SEAM_START_MARK = "S2 (planning gate, PG_GATE default-OFF): thread the RETRIEVAL"
_SEAM_END_MARK = "retrieval_plan=_gate_retrieval_plan,"


# ---------------------------------------------------------------------------
# Fixtures: same prompt, same candidate corpus, two DIFFERENT contracts.
# ---------------------------------------------------------------------------

PROMPT = (
    "Write a review of AI's impact on the labor market. Only cite journal "
    "articles published from 2024 onward."
)


def _span(phrase: str) -> dict:
    i = PROMPT.find(phrase)
    # Fall back to a benign span when the phrase is synthetic — the span shape
    # only needs to be structurally valid for these projection-level fixtures.
    if i == -1:
        return {"start": 0, "end": 1, "quote": PROMPT[:1]}
    return {"start": i, "end": i + len(phrase), "quote": phrase}


def _term(term_id: str, dimension: str, value, *, force: str = "hard",
          origin: str = "explicit", quote: str = "") -> dict:
    return {
        "term_id": term_id,
        "dimension": dimension,
        "value": value,
        "origin": origin,
        "force": force,
        "spans": [_span(quote)] if quote else [],
    }


def _plan() -> ResearchExecutionPlan:
    return plan_from_dict({
        "query_intents": [
            {"intent_id": "qi1", "thread_id": "t1", "purpose": "discovery",
             "concepts": ["AI labor market impact"], "mandatory": True},
        ],
        "budget": {"mandatory_lane_count": 1, "overflow_policy": "expand"},
    })


def _permissive_contract():
    """Allows all sources: no hard scope constraint at all."""
    return contract_from_dict({
        "objective": [_term("obj", "objective.question",
                            "AI impact on the labor market", force="open",
                            origin="explicit", quote="labor market")],
        "scope": [],
    })


def _restrictive_contract():
    """Hard-limits to journal articles from 2024 onward."""
    return contract_from_dict({
        "objective": [_term("obj", "objective.question",
                            "AI impact on the labor market", force="open",
                            origin="explicit", quote="labor market")],
        "scope": [
            _term("scope.source_types", "scope.source_types", "journal article",
                  quote="journal articles"),
            _term("scope.date", "scope.date", "2024", quote="2024 onward"),
        ],
    })


def _pinned_artifact(contract) -> PlanningGateArtifact:
    """A pinned artifact with real hashes (mirrors run_research_planning_gate)."""
    return PlanningGateArtifact(
        run_id="drb_control_path",
        mode="autonomous",
        state="pinned",
        original_prompt=PROMPT,
        contract=contract,
        plan=_plan(),
    ).recompute_hashes()


# ---------------------------------------------------------------------------
# A domain-neutral candidate corpus + an eligibility predicate that reads ONLY
# the projection's hard scope terms. This is a stand-in for the post-fetch
# "citable eligibility" verdict Phase C builds; here it lets us compare the
# eligible SET under two projections without a live fetch.
# ---------------------------------------------------------------------------

# (source_id, kind, year) — a mixed corpus: journals + non-journals, old + new.
CANDIDATE_CORPUS = [
    ("s_journal_2025", "journal article", 2025),
    ("s_journal_2019", "journal article", 2019),
    ("s_news_2025", "news article", 2025),
    ("s_blog_2024", "blog post", 2024),
    ("s_preprint_2024", "preprint", 2024),
]


def _eligible_source_ids(projection) -> frozenset[str]:
    """The citable set a projection admits from CANDIDATE_CORPUS.

    Eligibility is derived SOLELY from the projection's HARD scope terms (the
    only authority the seam is supposed to carry). A source is eligible unless a
    hard term excludes it:

      * a hard source-kind term (e.g. "journal article") admits only sources
        whose kind matches that term (substring, case-insensitive);
      * a hard 4-digit-year term (e.g. "2024") admits only sources at/after it.

    With NO hard terms (the permissive contract, AND the empty-contract champion
    adapter) every source is eligible. This is the domain-neutral shape of "does
    changing the contract change the citable menu".
    """
    hard = [str(t).strip() for t in projection.to_scope_terms()["hard"] if str(t).strip()]
    kind_terms = [t.lower() for t in hard if not t.strip().isdigit()]
    year_terms = [int(t) for t in hard if t.strip().isdigit() and len(t.strip()) == 4]
    min_year = max(year_terms) if year_terms else None

    eligible: set[str] = set()
    for sid, kind, year in CANDIDATE_CORPUS:
        if kind_terms and not any(kt in kind.lower() for kt in kind_terms):
            continue
        if min_year is not None and year < min_year:
            continue
        eligible.add(sid)
    return frozenset(eligible)


# ---------------------------------------------------------------------------
# Assertion 1 — the pinned contract_hash reaches the retrieval seam.
# ---------------------------------------------------------------------------

def test_pinned_contract_reaches_retrieval_via_from_artifact():
    """The projection consulted by the gate-on FS seam is
    ``from_artifact(gate_artifact)`` (carrying the pinned ``contract_sha256``),
    NOT ``from_champion_plan`` (an empty ``ResearchContract()``).

    PASSES after Phase C: ``run_honest_sweep_r3.py:run_one_query`` builds the FS
    projection from the pinned artifact (via
    ``from_artifact_with_champion_breadth``) so the pinned contract hash reaches
    retrieval; the champion adapter (empty contract) is only the artifact-missing
    fallback and is NOT wired at the seam.
    """
    artifact = _pinned_artifact(_restrictive_contract())
    pinned_hash = artifact.contract_sha256
    assert pinned_hash, "sanity: the pinned artifact must have a real contract hash"

    # (a) SOURCE-LEVEL TRACE of the REAL seam. The gate-on FS retrieval block
    #     builds its projection from the pinned ARTIFACT (from_artifact), NOT
    #     from the champion plan (from_champion_plan → empty ResearchContract()).
    src = _SWEEP_PATH.read_text(encoding="utf-8")
    i = src.index(_SEAM_START_MARK)
    j = src.index(_SEAM_END_MARK, i)
    seam = src[i:j]
    assert "from_artifact" in seam, (
        "the gate-on FS retrieval seam must build its projection from the pinned "
        "artifact via retrieval_projection.from_artifact (P0-A: the pinned "
        "contract_hash must reach retrieval)."
    )
    assert "from_champion_plan" not in seam, (
        "the gate-on FS retrieval seam must NOT wire from_champion_plan (empty "
        "contract) — that ships a shadow artifact whose scope never gates."
    )

    # (b) BEHAVIORAL: the projection the seam ACTUALLY builds (from_artifact,
    #     merged with champion breadth) carries the pinned contract hash; the
    #     champion adapter it REPLACED does not.
    from src.polaris_graph.planning.planning_gate_schema import sha256_of

    class _ChampionPlanStub:
        sub_queries = ["AI labor market impact"]
        frame = None

    # The real seam projection: from_artifact + champion breadth. Its contract is
    # the pinned contract (breadth is additive query text; it never touches scope).
    shipped = rp.from_artifact_with_champion_breadth(artifact, _ChampionPlanStub())
    assert shipped.contract.to_dict() == artifact.contract.to_dict()
    shipped_hash = sha256_of(shipped.contract.to_dict())
    assert shipped_hash == pinned_hash, (
        "the projection shipped by the seam must carry the PINNED contract (hash "
        f"{pinned_hash[:12]}), not an empty one (hash {shipped_hash[:12]}). The "
        "gate artifact must reach retrieval."
    )
    # And the champion breadth is preserved (the champion sub-query survives,
    # scope-anchored) — breadth kept, contract drives scope.
    amplified = shipped.to_amplified_queries(base_question=PROMPT)
    assert any("AI labor market impact" in a for a in amplified)

    # The REPLACED champion adapter (the pre-Phase-C fallback) carries an EMPTY
    # contract — this is exactly why the seam no longer wires it.
    fallback = rp.from_champion_plan(_ChampionPlanStub())
    fallback_hash = sha256_of(fallback.contract.to_dict())
    assert fallback_hash != pinned_hash, (
        "sanity: the champion adapter drops the contract (empty ResearchContract) "
        "— the seam correctly no longer ships it."
    )


# ---------------------------------------------------------------------------
# Assertion 2 — two contracts → two eligible source sets.
# ---------------------------------------------------------------------------

def test_two_contracts_produce_different_eligible_source_sets():
    """Two DIFFERENT contracts over the SAME candidate corpus yield DIFFERENT
    eligible/citable source sets.

    PASSES after Phase C: the seam projects each contract through
    ``from_artifact`` (the projection source it now wires — see the source-trace
    in :func:`test_pinned_contract_reaches_retrieval_via_from_artifact`), whose
    hard-scope set carries the CONTRACT's terms. The restrictive contract's hard
    ``journal article`` + ``2024`` limit reaches retrieval and gates the citable
    menu; the permissive one does not.
    """
    permissive_art = _pinned_artifact(_permissive_contract())
    restrictive_art = _pinned_artifact(_restrictive_contract())

    # Champion breadth is threaded ADDITIVELY (spec item 1) — model the exact
    # projection the seam ships: from_artifact + champion sub-queries. The champion
    # breadth is query TEXT only; it never touches the hard scope the eligibility
    # predicate reads, so the two contracts still diverge.
    class _ChampionPlanStub:
        sub_queries = ["AI labor market impact"]
        frame = None

    seam_permissive = rp.from_artifact_with_champion_breadth(
        permissive_art, _ChampionPlanStub())
    seam_restrictive = rp.from_artifact_with_champion_breadth(
        restrictive_art, _ChampionPlanStub())

    eligible_permissive = _eligible_source_ids(seam_permissive)
    eligible_restrictive = _eligible_source_ids(seam_restrictive)

    assert eligible_permissive != eligible_restrictive, (
        "the SAME corpus must yield DIFFERENT eligible sets under two different "
        f"contracts. permissive={sorted(eligible_permissive)} "
        f"restrictive={sorted(eligible_restrictive)}. The hard journal+2024 limit "
        "must reach retrieval and gate the citable menu."
    )

    # The exact eligible sets: the restrictive contract admits ONLY the 2024+
    # journal; the permissive one admits the whole corpus. (Champion breadth does
    # not change eligibility — it is additive discovery query text.)
    assert eligible_permissive == frozenset(sid for sid, _, _ in CANDIDATE_CORPUS)
    assert eligible_restrictive == frozenset({"s_journal_2025"})
