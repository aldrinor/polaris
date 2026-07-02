"""I-deepfix-001 (#1344) consolidation_keystone — offline RED->GREEN tests.

Two source changes are exercised, both grouping/weight-only (the FROZEN faithfulness engine
strict_verify / NLI / 4-role D8 / provenance / span-grounding is never imported or called here):

  1. credibility_pass._regroup_graph_by_finding_dedup now unions QUALITATIVE claim atoms when
     finding_dedup emits a ``("__qual__", ...)`` cluster. Pre-fix the numeric-only index resolved
     a qualitative cluster to ZERO members -> never merged -> 0 corroboration.

  2. finding_dedup._build_qualitative_groups skips a furniture-DOMINANT row (cookie/byline/ToC)
     so page boilerplate never seeds a FALSE N-source corroboration basket. The row is still KEPT
     (keep-all); it is only excluded from clustering.

All offline: no GPU, no network, no paid LLM. ``dedup_by_finding`` is monkeypatched so the test
does not depend on the real dice.
"""
from __future__ import annotations

import dataclasses

import src.polaris_graph.synthesis.finding_dedup as finding_dedup_mod
from src.polaris_graph.synthesis.credibility_pass import (
    BASKET_VERDICT_CONTESTED,
    _assemble_baskets,
    _regroup_graph_by_finding_dedup,
)
from src.polaris_graph.synthesis.finding_dedup import _build_qualitative_groups


# ---- minimal graph-shaped stubs (only the fields the function reads) --------------------

class _Claim:
    def __init__(self, kind: str, evidence_id: str, claim_cluster_id: str) -> None:
        self.kind = kind
        self.evidence_id = evidence_id
        self.claim_cluster_id = claim_cluster_id


@dataclasses.dataclass
class _Edge:
    claim_cluster_ids: tuple
    kind: str = "refutes"


@dataclasses.dataclass
class _Graph:
    claims: list
    edges: list
    clusters: dict
    distinct_cluster_count: int


class _FakeCluster:
    def __init__(self, finding_key: tuple, member_indices: list) -> None:
        self.finding_key = finding_key
        self.member_indices = member_indices


class _FakeDedup:
    def __init__(self, clusters: list) -> None:
        self.clusters = clusters


def _make_qual_graph():
    claims = [
        _Claim(kind="qualitative", evidence_id="e1", claim_cluster_id="clm_a"),
        _Claim(kind="qualitative", evidence_id="e2", claim_cluster_id="clm_b"),
    ]
    graph = _Graph(
        claims=claims,
        edges=[_Edge(claim_cluster_ids=("clm_a", "clm_b"))],
        clusters={"clm_a": [0], "clm_b": [1]},
        distinct_cluster_count=2,
    )
    annotated = [{"evidence_id": "e1"}, {"evidence_id": "e2"}]
    return graph, annotated, claims


def test_qualitative_cluster_merges_distinct_origins(monkeypatch):
    """A ``__qual__`` finding_dedup cluster over two rows now MERGES the two qualitative
    claim atoms into one basket (RED pre-fix: numeric-only map -> 0 members -> no merge)."""
    graph, annotated, claims = _make_qual_graph()
    monkeypatch.setattr(
        finding_dedup_mod,
        "dedup_by_finding",
        lambda *a, **k: _FakeDedup([_FakeCluster(("__qual__", "e1", "tok"), [0, 1])]),
    )
    result = _regroup_graph_by_finding_dedup(
        graph, annotated, gov_suffixes=(), domain=None
    )
    # Merged into ONE cluster.
    assert result.distinct_cluster_count == 1
    assert set(result.clusters.keys()) == {"clm_a"}
    assert sorted(result.clusters["clm_a"]) == [0, 1]
    # Both claims now carry the merged representative id.
    assert claims[0].claim_cluster_id == "clm_a"
    assert claims[1].claim_cluster_id == "clm_a"


def _basket_verdict_by_cluster(graph, annotated):
    """Assemble baskets on a (regrouped) graph and return {cluster_id: basket_verdict}.

    Members have no span text, so every isolated per-member verify returns UNSUPPORTED
    (no paid LLM, no verify_fn call) — the ONLY thing that can flip the verdict to
    ``contested`` here is a refuter reference, which is exactly what P1#1 fixes.
    """
    baskets = _assemble_baskets(
        graph, [], annotated, {}, verify_fn=lambda *_a, **_k: None,
    )
    return {b.claim_cluster_id: b.basket_verdict for b in baskets}


def test_contested_qualitative_basket_stays_contested(monkeypatch):
    """The refuter edge is remapped onto the merged basket id AND the DOWNSTREAM basket
    still renders ``contested`` — the self-loop refuter the merge creates is never dropped.

    RED pre-fix: ``_assemble_baskets`` recorded a refuter only for OTHER cluster ids
    (``other != cid``), so the single-id self-loop edge recorded NO refuter and the basket
    fell through to ``unverified``/``full``/``partial`` — silently hiding the contradiction
    (hard-constraint-3 violation)."""
    graph, annotated, _claims = _make_qual_graph()
    monkeypatch.setattr(
        finding_dedup_mod,
        "dedup_by_finding",
        lambda *a, **k: _FakeDedup([_FakeCluster(("__qual__", "e1", "tok"), [0, 1])]),
    )
    result = _regroup_graph_by_finding_dedup(
        graph, annotated, gov_suffixes=(), domain=None
    )
    assert len(result.edges) == 1
    assert result.edges[0].claim_cluster_ids == ("clm_a",)
    # KEYSTONE: assert the downstream ClaimBasket verdict, not just the edge tuple.
    verdicts = _basket_verdict_by_cluster(result, annotated)
    assert verdicts == {"clm_a": BASKET_VERDICT_CONTESTED}


def test_contested_numeric_basket_stays_contested_after_merge(monkeypatch):
    """BOTH-merges guard (P1#1 must hold for numeric too): a numeric refuter edge between two
    clusters that MERGE collapses to a self-loop, and its downstream basket still renders
    ``contested`` (RED pre-fix: same single-id self-loop drop as the qualitative case)."""
    claims = [
        _Claim(kind="numeric", evidence_id="e1", claim_cluster_id="clm_a"),
        _Claim(kind="numeric", evidence_id="e2", claim_cluster_id="clm_b"),
    ]
    graph = _Graph(
        claims=claims,
        edges=[_Edge(claim_cluster_ids=("clm_a", "clm_b"))],
        clusters={"clm_a": [0], "clm_b": [1]},
        distinct_cluster_count=2,
    )
    annotated = [{"evidence_id": "e1"}, {"evidence_id": "e2"}]
    monkeypatch.setattr(
        finding_dedup_mod,
        "dedup_by_finding",
        lambda *a, **k: _FakeDedup([_FakeCluster(("hba1c", "1.2"), [0, 1])]),
    )
    result = _regroup_graph_by_finding_dedup(
        graph, annotated, gov_suffixes=(), domain=None
    )
    assert result.distinct_cluster_count == 1
    assert result.edges[0].claim_cluster_ids == ("clm_a",)
    verdicts = _basket_verdict_by_cluster(result, annotated)
    assert verdicts == {"clm_a": BASKET_VERDICT_CONTESTED}


def test_numeric_cluster_still_merges(monkeypatch):
    """Regression guard: the numeric path is unchanged — a numeric cluster still merges."""
    claims = [
        _Claim(kind="numeric", evidence_id="e1", claim_cluster_id="clm_a"),
        _Claim(kind="numeric", evidence_id="e2", claim_cluster_id="clm_b"),
    ]
    graph = _Graph(
        claims=claims,
        edges=[],
        clusters={"clm_a": [0], "clm_b": [1]},
        distinct_cluster_count=2,
    )
    annotated = [{"evidence_id": "e1"}, {"evidence_id": "e2"}]
    monkeypatch.setattr(
        finding_dedup_mod,
        "dedup_by_finding",
        lambda *a, **k: _FakeDedup([_FakeCluster(("hba1c", "1.2"), [0, 1])]),
    )
    result = _regroup_graph_by_finding_dedup(
        graph, annotated, gov_suffixes=(), domain=None
    )
    assert result.distinct_cluster_count == 1


# ---- P1#1: MERGE-ONLY seed — an existing multi-member cluster never gets SPLIT ------------

def _cid_by_claim_index(result) -> dict:
    """Map each claim index -> the cluster id it belongs to in the regrouped graph."""
    out: dict[int, str] = {}
    for cid, members in (getattr(result, "clusters", None) or {}).items():
        for m in members:
            out[int(m)] = cid
    return out


def test_partial_finding_merge_keeps_existing_cluster_atomic_and_contested(monkeypatch):
    """P1#1 (MERGE-ONLY seed, FAITHFULNESS-CRITICAL): an existing 2-member cluster [i, j] carrying a
    refuter edge must move ATOMICALLY when a finding-dedup group pulls only i into a lower-index merge.

    Setup: claim 0 sits in its OWN lower-index cluster ``clm_low``; claims 1 (=i) and 2 (=j) are BOTH
    members of the existing cluster ``clm_x``; a refuter edge contradicts the whole ``clm_x`` basket
    against ``clm_other`` (claim 3). finding_dedup groups rows 0+1 (so ONLY i is pulled into the
    lower-index merge).

    RED pre-fix: the union-find started from singletons, so i was relabeled into ``clm_low`` while j
    kept ``clm_x``; the edge remap rewrote the refuter onto ``clm_low`` and the residual ``clm_x`` basket
    (holding j) SILENTLY lost its contested state — i and j SPLIT across two baskets.
    GREEN: seeding the union-find from ``clm_x``'s members moves i AND j together; the basket holding
    both stays ``contested`` (the refuter edge is not lost)."""
    claims = [
        _Claim(kind="numeric", evidence_id="e0", claim_cluster_id="clm_low"),
        _Claim(kind="numeric", evidence_id="e1", claim_cluster_id="clm_x"),   # member i
        _Claim(kind="numeric", evidence_id="e2", claim_cluster_id="clm_x"),   # member j
        _Claim(kind="numeric", evidence_id="e3", claim_cluster_id="clm_other"),
    ]
    graph = _Graph(
        claims=claims,
        edges=[_Edge(claim_cluster_ids=("clm_x", "clm_other"))],
        clusters={"clm_low": [0], "clm_x": [1, 2], "clm_other": [3]},
        distinct_cluster_count=3,
    )
    annotated = [
        {"evidence_id": "e0"}, {"evidence_id": "e1"},
        {"evidence_id": "e2"}, {"evidence_id": "e3"},
    ]
    # finding_dedup pulls rows 0 (e0) + 1 (e1=member i) together -> only i joins the lower-index merge.
    monkeypatch.setattr(
        finding_dedup_mod,
        "dedup_by_finding",
        lambda *a, **k: _FakeDedup([_FakeCluster(("hba1c", "1.2"), [0, 1])]),
    )
    result = _regroup_graph_by_finding_dedup(
        graph, annotated, gov_suffixes=(), domain=None
    )
    cid_by_idx = _cid_by_claim_index(result)
    # MERGE-ONLY: i (claim 1) and j (claim 2) must remain in the SAME basket — never split.
    assert cid_by_idx[1] == cid_by_idx[2], (
        "existing cluster [i, j] was SPLIT by a partial finding-dedup merge (MERGE-ONLY violated)"
    )
    # The basket holding BOTH i and j still renders contested (refuter edge preserved, not misrouted).
    merged_cid = cid_by_idx[1]
    verdicts = _basket_verdict_by_cluster(result, annotated)
    assert verdicts[merged_cid] == BASKET_VERDICT_CONTESTED


# ---- P1#2: qual representative disambiguation — a multi-atom row is NOT merged -------------

def test_multi_atom_qual_row_not_merged(monkeypatch):
    """P1#2 (qual representative disambiguation, FAITHFULNESS-CRITICAL): a row mapping to MORE THAN ONE
    qualitative atom must NOT be unioned (we cannot know which atom made the row match the group).

    Setup: eid ``e1`` carries TWO qualitative atoms (claims 0, 1); eid ``e2`` carries ONE (claim 2). A
    ``__qual__`` finding cluster groups row 0 (e1, ambiguous) + row 1 (e2, unambiguous).

    RED pre-fix: the code appended ``qual_indices[0]`` for the 2-atom row, FALSE-MERGING claim 0 with
    claim 2 (distinct-eid assertions) and inflating verified_support_origin_count -> clusters collapse
    3 -> 2. GREEN: the ambiguous 2-atom row is SKIPPED, so no cross-eid merge happens (clusters stay 3);
    undercount-safe."""
    claims = [
        _Claim(kind="qualitative", evidence_id="e1", claim_cluster_id="clm_a"),   # e1 atom #1
        _Claim(kind="qualitative", evidence_id="e1", claim_cluster_id="clm_a2"),  # e1 atom #2
        _Claim(kind="qualitative", evidence_id="e2", claim_cluster_id="clm_b"),   # e2 atom (single)
    ]
    graph = _Graph(
        claims=claims,
        edges=[],
        clusters={"clm_a": [0], "clm_a2": [1], "clm_b": [2]},
        distinct_cluster_count=3,
    )
    annotated = [{"evidence_id": "e1"}, {"evidence_id": "e2"}]  # row 0 -> e1 (2 atoms), row 1 -> e2
    monkeypatch.setattr(
        finding_dedup_mod,
        "dedup_by_finding",
        lambda *a, **k: _FakeDedup([_FakeCluster(("__qual__", "e1", "tok"), [0, 1])]),
    )
    result = _regroup_graph_by_finding_dedup(
        graph, annotated, gov_suffixes=(), domain=None
    )
    # No false cross-eid merge: the ambiguous multi-atom row was skipped -> all three clusters remain.
    assert result.distinct_cluster_count == 3
    cid_by_idx = _cid_by_claim_index(result)
    # claim 0 (an e1 atom) and claim 2 (e2) must stay in SEPARATE clusters.
    assert cid_by_idx[0] != cid_by_idx[2], (
        "a 2-atom row was false-merged with a different-eid claim (verified_support_origin_count inflated)"
    )


# ---- finding_dedup furniture-guard --------------------------------------------------------

# A cookie-consent body long enough to shingle but furniture-DOMINANT (post-strip residue empty).
_FURNITURE_BODY = (
    "In order to better serve you and keep this site secure, please complete this challenge."
)
_REAL_CLAIM_BODY = (
    "Metformin reduced fasting plasma glucose in adult patients with type two diabetes."
)


def test_furniture_rows_excluded_from_qualitative_clustering():
    """Two identical furniture-dominant rows do NOT form a qualitative basket (RED pre-fix:
    they clustered into a FALSE 2-source corroboration over page boilerplate)."""
    rows = [
        {"evidence_id": "e1", "statement": _FURNITURE_BODY},
        {"evidence_id": "e2", "statement": _FURNITURE_BODY},
    ]
    groups = _build_qualitative_groups(
        rows, [False, False], set(), threshold=0.5
    )
    assert groups == {}


def test_real_qualitative_claims_still_cluster():
    """Control (keep-all / no over-strip): two identical REAL qualitative claims still form
    a basket — the furniture guard only excludes furniture-dominant residue."""
    rows = [
        {"evidence_id": "e1", "statement": _REAL_CLAIM_BODY},
        {"evidence_id": "e2", "statement": _REAL_CLAIM_BODY},
    ]
    groups = _build_qualitative_groups(
        rows, [False, False], set(), threshold=0.5
    )
    assert len(groups) == 1
    (members,) = list(groups.values())
    assert sorted(members) == [0, 1]
