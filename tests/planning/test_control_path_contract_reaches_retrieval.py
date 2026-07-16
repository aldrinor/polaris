"""Phase A — the FAILING control-path test (P0-A: contract not wired to retrieval).

This test documents the BEHAVIORAL BAR the gate rebuild must clear. It is
EXPECTED TO FAIL on the current branch and is therefore marked ``xfail`` with
``reason='P0-A: contract not wired to retrieval; fixed in Phase C'`` so the
suite stays green while the assertion body remains real.

It asserts, against the REAL retrieval seam (no network, no LLM), two things:

1. ARTIFACT IDENTITY REACHES RETRIEVAL. When ``PG_GATE=1``, the projection that
   the FS retrieval seam in ``scripts/run_honest_sweep_r3.py:run_one_query``
   consults must be compiled from the pinned ``PlanningGateArtifact`` via
   ``retrieval_projection.from_artifact(gate_artifact)`` — i.e. it must carry the
   artifact's pinned ``contract_sha256``. Today the seam calls
   ``retrieval_projection.from_champion_plan(_research_plan, ...)``, which builds
   a ``_ChampionPlanProjection`` over an EMPTY ``ResearchContract()`` (see
   ``retrieval_projection.py:_ChampionPlanProjection.__init__`` →
   ``contract=ResearchContract()``). The pinned contract's hash therefore NEVER
   reaches retrieval — it is a shadow artifact (sol P0, verdict P0-A).

2. TWO CONTRACTS → TWO ELIGIBLE SOURCE SETS. Two DIFFERENT contracts over the
   SAME candidate/corpus fixture — one allowing all sources, one hard-limiting to
   journal articles from 2024 onward — must produce DIFFERENT eligible/citable
   source sets. Today the seam projects BOTH contracts through the empty-contract
   champion adapter, whose hard-scope predicate set is ``[]`` for BOTH, so the
   eligible set is IDENTICAL (the whole corpus) regardless of the contract. The
   gate does not gate.

The negative half of each assertion (that ``from_artifact`` DOES carry the hash
and DOES diverge) is exercised inline so the test also pins the FIX target: the
same real functions, once the seam is switched to ``from_artifact`` in Phase C,
make these assertions pass with no test edit.

Everything is OFFLINE and deterministic: no ``run_one_query`` drive, no network,
no LLM. We bind to the real seam two ways — (a) a source-level trace of the
gate-on FS seam in ``run_honest_sweep_r3.py`` proving it wires
``from_champion_plan`` and NOT ``from_artifact``, and (b) the real projection
functions (``from_artifact`` / ``from_champion_plan``) over real schema fixtures,
proving the behavioral consequence.
"""

from __future__ import annotations

import pathlib

import pytest

from src.polaris_graph.planning import retrieval_projection as rp
from src.polaris_graph.planning.planning_gate_schema import (
    PlanningGateArtifact,
    ResearchExecutionPlan,
    contract_from_dict,
    plan_from_dict,
)

_XFAIL_REASON = "P0-A: contract not wired to retrieval; fixed in Phase C"

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

@pytest.mark.xfail(reason=_XFAIL_REASON, strict=True)
def test_pinned_contract_reaches_retrieval_via_from_artifact():
    """The projection consulted by the gate-on FS seam must be
    ``from_artifact(gate_artifact)`` (carrying the pinned ``contract_sha256``),
    NOT ``from_champion_plan`` (an empty ``ResearchContract()``).

    FAILS today because ``run_honest_sweep_r3.py:run_one_query`` wires
    ``from_champion_plan`` at the FS seam and never passes the artifact.
    """
    artifact = _pinned_artifact(_restrictive_contract())
    pinned_hash = artifact.contract_sha256
    assert pinned_hash, "sanity: the pinned artifact must have a real contract hash"

    # (a) SOURCE-LEVEL TRACE of the REAL seam. The gate-on FS retrieval block
    #     must build its projection from the pinned ARTIFACT (from_artifact), not
    #     from the champion plan (from_champion_plan → empty ResearchContract()).
    src = _SWEEP_PATH.read_text(encoding="utf-8")
    i = src.index(_SEAM_START_MARK)
    j = src.index(_SEAM_END_MARK, i)
    seam = src[i:j]
    assert "from_artifact" in seam, (
        "the gate-on FS retrieval seam does NOT build its projection from the "
        "pinned artifact via retrieval_projection.from_artifact — it currently "
        "calls from_champion_plan, shipping an empty ResearchContract() (P0-A: "
        "the pinned contract_hash never reaches retrieval)."
    )
    assert "from_champion_plan" not in seam, (
        "the gate-on FS retrieval seam still wires from_champion_plan (empty "
        "contract). The pinned contract is a shadow artifact."
    )

    # (b) BEHAVIORAL: the projection the seam SHOULD build carries the pinned
    #     hash; the one it ACTUALLY builds does not.
    projection_that_should_ship = rp.from_artifact(artifact)
    assert projection_that_should_ship.contract.to_dict() == artifact.contract.to_dict()
    from src.polaris_graph.planning.planning_gate_schema import sha256_of
    assert sha256_of(projection_that_should_ship.contract.to_dict()) == pinned_hash

    # The champion-plan adapter that the seam ACTUALLY uses drops the contract.
    class _ChampionPlanStub:
        sub_queries = ["AI labor market impact"]
        frame = None

    shipped = rp.from_champion_plan(_ChampionPlanStub())
    shipped_hash = sha256_of(shipped.contract.to_dict())
    assert shipped_hash == pinned_hash, (
        "the projection actually shipped by the seam carries an EMPTY contract "
        f"(hash {shipped_hash[:12]}), NOT the pinned contract (hash "
        f"{pinned_hash[:12]}). The gate artifact never reaches retrieval."
    )


# ---------------------------------------------------------------------------
# Assertion 2 — two contracts → two eligible source sets.
# ---------------------------------------------------------------------------

@pytest.mark.xfail(reason=_XFAIL_REASON, strict=True)
def test_two_contracts_produce_different_eligible_source_sets():
    """Two DIFFERENT contracts over the SAME candidate corpus must yield
    DIFFERENT eligible/citable source sets.

    FAILS today because the seam projects BOTH contracts through the
    empty-contract champion adapter (``from_champion_plan``), whose hard-scope
    set is ``[]`` for BOTH — so the eligible set is the WHOLE corpus in both
    cases. Changing the contract does not change the citable menu.
    """
    permissive_art = _pinned_artifact(_permissive_contract())
    restrictive_art = _pinned_artifact(_restrictive_contract())

    # The projections the seam ACTUALLY ships today: both via the champion
    # adapter (the seam ignores the artifact entirely). We model the seam's
    # own behavior — an empty contract for BOTH — to prove the divergence the
    # gate promises does NOT occur on the wired path.
    class _ChampionPlanStub:
        sub_queries = ["AI labor market impact"]
        frame = None

    seam_permissive = rp.from_champion_plan(_ChampionPlanStub())
    seam_restrictive = rp.from_champion_plan(_ChampionPlanStub())

    eligible_permissive = _eligible_source_ids(seam_permissive)
    eligible_restrictive = _eligible_source_ids(seam_restrictive)

    assert eligible_permissive != eligible_restrictive, (
        "the SAME corpus yields the SAME eligible set under BOTH contracts "
        f"({sorted(eligible_permissive)}) because the wired seam ships an empty "
        "contract for both (from_champion_plan). The hard journal+2024 limit "
        "never reaches retrieval — the gate does not gate the citable menu."
    )

    # The FIX target (from_artifact), pinned inline so this passes untouched once
    # Phase C switches the seam: the restrictive contract admits ONLY the 2024+
    # journal, the permissive one admits the whole corpus.
    fixed_permissive = _eligible_source_ids(rp.from_artifact(permissive_art))
    fixed_restrictive = _eligible_source_ids(rp.from_artifact(restrictive_art))
    assert fixed_permissive == frozenset(sid for sid, _, _ in CANDIDATE_CORPUS)
    assert fixed_restrictive == frozenset({"s_journal_2025"})
