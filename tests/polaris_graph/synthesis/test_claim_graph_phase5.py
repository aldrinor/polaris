"""Offline smoke for the L4 claim-graph (Phase 5 / I-cred-005-claimgraph).

Pure CPU: no network, no LLM, no spend. Fixtures live in
``tests/fixtures/credibility/claim_graph_cases.json`` (LAW VI — no live data). The
semantic NLI edge source is exercised with an INJECTED fake judge
``(claim_a, claim_b) -> (label, confidence)``; the production judge is never
constructed (no ``OPENROUTER_API_KEY``, no httpx client).

The two invariants point in OPPOSITE directions and each gets its own test:
  * CONSERVATIVE-SINGLETON / under-merge (never over-merge two distinct claims).
  * RECALL-FIRST / over-detect on contradictions (never silently drop a real one).

Serialized per CLAUDE.md §8.4 (pure-python). NO unittest.mock.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.polaris_graph.synthesis.claim_graph import (
    AtomicClaim,
    ClaimGraph,
    ContradictionEdge,
    build_claim_graph,
    build_contradiction_edges,
    claim_graph_enabled,
    cluster_equivalent_claims,
    extract_atomic_claims,
)

_FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "tests" / "fixtures" / "credibility" / "claim_graph_cases.json"
)


def _cases() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def _rows(name: str) -> list[dict]:
    return _cases()[name]["rows"]


# ── default-OFF flag (LAW II no-silent-downgrade / byte-identity precondition) ──


def test_flag_default_off(monkeypatch):
    """PG_SWEEP_CLAIM_GRAPH unset => claim_graph_enabled() is False (default-OFF)."""
    monkeypatch.delenv("PG_SWEEP_CLAIM_GRAPH", raising=False)
    assert claim_graph_enabled() is False


@pytest.mark.parametrize("off_val", ["", "0", "false", "off", "no", "  ", "FALSE", "Off"])
def test_flag_off_values(monkeypatch, off_val):
    """Every documented off-value (case/space-insensitive) keeps the layer OFF."""
    monkeypatch.setenv("PG_SWEEP_CLAIM_GRAPH", off_val)
    assert claim_graph_enabled() is False


@pytest.mark.parametrize("on_val", ["1", "true", "on", "yes", "TRUE"])
def test_flag_on_values(monkeypatch, on_val):
    """A truthy value flips the kill-switch ON."""
    monkeypatch.setenv("PG_SWEEP_CLAIM_GRAPH", on_val)
    assert claim_graph_enabled() is True


def test_module_does_not_read_flag_in_pure_functions(monkeypatch):
    """The pure library builds the graph regardless of the flag — the caller gates
    invocation. (Proves the flag is a CALLER kill-switch, not a hidden internal
    short-circuit that would make the function impure.)"""
    monkeypatch.delenv("PG_SWEEP_CLAIM_GRAPH", raising=False)
    graph = build_claim_graph(_rows("equivalent_clinical_numeric"))
    assert isinstance(graph, ClaimGraph)
    assert len(graph.claims) == 2


# ── INVARIANT 1: conservative-singleton — equivalence clustering ───────────────


def test_equivalent_claims_share_one_cluster(monkeypatch):
    """Two independent rows asserting the SAME finding cluster to ONE claim_cluster_id.

    Pins the LEGACY positional-key clustering. I-arch-007 A20 (#1262) made the redesign
    merge key (``build_merge_key``) DEFAULT ON; that spec-driven key is MORE conservative
    (a defaulted ``arm``/discriminator fails closed to a singleton), so equivalence under
    the redesign key is exercised separately in ``test_claim_graph_merge_key_arch002.py``.
    This case asserts the legacy semantics under the EXPLICIT-OFF path."""
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "0")
    graph = build_claim_graph(_rows("equivalent_clinical_numeric"))
    cids = {c.claim_cluster_id for c in graph.claims}
    assert len(cids) == 1, "equivalent claims must share one cluster id"
    assert graph.distinct_cluster_count == 1
    # the single cluster holds both member indices
    (only_cid,) = cids
    assert sorted(graph.clusters[only_cid]) == [0, 1]


def test_distinct_claims_never_over_merge():
    """CONSERVATIVE-SINGLETON: different subjects/values stay in SEPARATE clusters.

    semaglutide-14.9% vs tirzepatide-22.5% are distinct claims — over-merging them
    is the clinical-lethal failure mode this invariant forbids."""
    graph = build_claim_graph(_rows("distinct_clinical_numeric"))
    cids = {c.claim_cluster_id for c in graph.claims}
    assert len(cids) == 2, "distinct claims must NOT over-merge"
    assert graph.distinct_cluster_count == 2


def test_close_numeric_values_are_not_over_merged():
    """Codex iter-1 P1 regression: two numeric claims with the SAME subject/predicate but
    values differing in the 4th decimal (14.9001 vs 14.9002) must NOT share a cluster.
    The previous round-to-3dp collapsed them — a conservative-singleton violation."""
    from types import SimpleNamespace

    from src.polaris_graph.synthesis.claim_graph import (
        _claim_cluster_id,
        _normalized_key_numeric,
    )

    def _nc(value):
        return SimpleNamespace(subject="semaglutide", predicate="weight_loss",
                               value=value, unit="%", dose="", arm="", endpoint_phrase="")

    key_a = _normalized_key_numeric(_nc(14.9001), "e1", 0)
    key_b = _normalized_key_numeric(_nc(14.9002), "e2", 0)
    assert key_a != key_b, "distinct close values must yield distinct keys"
    assert _claim_cluster_id(key_a) != _claim_cluster_id(key_b)
    # ...but a genuinely EQUAL value still clusters (true equivalence is not broken).
    assert _normalized_key_numeric(_nc(14.9001), "e3", 0) == key_a


def test_edge_attaches_only_to_subject_matching_clusters():
    """Codex iter-1 P2 regression: a row hosting claims on TWO subjects must not leak the
    unrelated subject's cluster into a contradiction edge about the OTHER subject — the
    edge attaches by (evidence_id, subject), not by evidence_id alone."""
    from src.polaris_graph.synthesis.claim_graph import (
        AtomicClaim,
        _cluster_id_for_evidence,
        _cluster_ids_by_subject,
        _edge_cluster_pair,
        cluster_equivalent_claims,
    )

    # Row r1 hosts a claim on 'aspirin' AND on 'warfarin'; row r2 hosts 'aspirin'.
    claims = [
        AtomicClaim(evidence_id="r1", kind="numeric", subject="aspirin", predicate="rate",
                    normalized_key=("numeric", "aspirin", "rate", 10.0, "%", "", "", ""),
                    text="aspirin 10%"),
        AtomicClaim(evidence_id="r1", kind="numeric", subject="warfarin", predicate="rate",
                    normalized_key=("numeric", "warfarin", "rate", 99.0, "%", "", "", ""),
                    text="warfarin 99%"),
        AtomicClaim(evidence_id="r2", kind="numeric", subject="aspirin", predicate="rate",
                    normalized_key=("numeric", "aspirin", "rate", 50.0, "%", "", "", ""),
                    text="aspirin 50%"),
    ]
    cluster_equivalent_claims(claims)  # assigns each claim_cluster_id
    by_subject = _cluster_ids_by_subject(claims)
    by_evid = _cluster_id_for_evidence(claims)

    # A contradiction edge on subject 'aspirin' spanning r1 + r2.
    pair = _edge_cluster_pair("aspirin", ("r1", "r2"), by_subject, by_evid)
    warfarin_cid = next(c.claim_cluster_id for c in claims if c.subject == "warfarin")
    aspirin_cids = {c.claim_cluster_id for c in claims if c.subject == "aspirin"}
    assert warfarin_cid not in pair, "unrelated-subject cluster must not be pulled in"
    assert set(pair) == aspirin_cids


def test_unknown_subject_is_a_singleton(monkeypatch):
    """A claim whose subject the extractor cannot resolve (unknown sentinel) is its
    OWN singleton cluster and never collides with another unknown.

    Pins the LEGACY ``__numeric_unknown__`` sentinel-key shape. I-arch-007 A20 (#1262)
    made the redesign merge key DEFAULT ON; under that key an unknown subject ALSO
    forces a singleton (via the fail-closed UNKNOWN-discriminator dispatch — see
    ``test_20_unknown_discriminator_forces_singleton`` in the merge-key suite), but the
    key STRING differs. This case asserts the legacy sentinel under the EXPLICIT-OFF path
    — the singleton GUARANTEE itself holds in BOTH modes."""
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "0")
    rows = [
        {"evidence_id": "u1", "direct_quote": "Achieved 14.9% weight loss from baseline.",
         "source_url": "https://a.org", "tier": "T1"},
        {"evidence_id": "u2", "direct_quote": "Reported 14.9% weight loss from baseline.",
         "source_url": "https://b.org", "tier": "T1"},
    ]
    claims = extract_atomic_claims(rows)
    cluster_equivalent_claims(claims)
    # the numeric extractor resolves the 14.9% value but NOT a drug subject -> both
    # claims carry the per-claim ``__numeric_unknown__`` sentinel key -> two singletons.
    numeric = [c for c in claims if c.kind == "numeric"]
    assert len(numeric) == 2, "both rows must yield an (unknown-subject) numeric claim"
    assert all(c.subject == "unknown" for c in numeric)
    assert all(c.normalized_key[0] == "__numeric_unknown__" for c in numeric)
    assert len({c.claim_cluster_id for c in numeric}) == 2, (
        "unknown-subject claims must each be their own singleton (never collide)"
    )


def test_raw_claims_are_always_distinct_singletons():
    """Non-clinical rows are now extracted by the B9 domain-agnostic numeric
    extractor (the documented residual is fixed): each distinct GDP/emissions
    finding yields its own claim, keyed by its own subject/predicate/value ->
    never merged, never dropped (field-agnostic coverage guarantee). Two
    DIFFERENT findings stay distinct singletons (no false merge)."""
    graph = build_claim_graph(_rows("non_clinical_numeric"))
    # Each non-clinical row yields exactly one claim (numeric now, not raw).
    assert len(graph.claims) == 2, "each non-clinical row must yield exactly one claim"
    assert len({c.claim_cluster_id for c in graph.claims}) == 2, (
        "two distinct non-clinical findings stay distinct singletons"
    )


# ── field-agnostic coverage: every row yields >=1 atomic claim ─────────────────


@pytest.mark.parametrize(
    "case",
    ["equivalent_clinical_numeric", "distinct_clinical_numeric", "non_clinical_numeric",
     "numeric_contradiction", "qualitative_present_vs_absent", "no_conflict_corpus"],
)
def test_every_row_yields_at_least_one_claim(case):
    """FIELD-AGNOSTIC: no evidence row is silently dropped — every row id appears on
    at least one atomic claim (clinical, non-clinical, or raw fallback)."""
    rows = _rows(case)
    claims = extract_atomic_claims(rows)
    covered = {c.evidence_id for c in claims}
    expected = {str(r["evidence_id"]) for r in rows}
    assert expected <= covered, f"rows dropped in {case}: {expected - covered}"


def test_non_clinical_numeric_produces_claims_finding_dedup_would_miss():
    """The motivating gap is now CLOSED by B9: the domain-agnostic numeric
    extractor produces structured numeric claims on GDP/emissions rows (the
    clinical-only extractor used to return nothing -> raw singletons). Every
    non-clinical row still yields >=1 atomic claim; nothing is dropped."""
    claims = extract_atomic_claims(_rows("non_clinical_numeric"))
    assert len(claims) == 2
    # B9: these are NUMERIC claims now (the residual is fixed), not raw
    # fallbacks. Each row is still covered (field-agnostic coverage guarantee).
    assert all(c.kind == "numeric" for c in claims)
    covered = {c.evidence_id for c in claims}
    assert covered == {"e_econ_1", "e_econ_2"}


# ── INVARIANT 2: recall-first on contradictions ────────────────────────────────


def test_numeric_contradiction_emits_an_edge():
    """RECALL-FIRST: a numeric disagreement (14.9% vs 17.4%) emits a contradiction edge."""
    graph = build_claim_graph(_rows("numeric_contradiction"))
    numeric_edges = [e for e in graph.edges if e.source == "numeric"]
    assert len(numeric_edges) >= 1, "a real numeric conflict must NOT be dropped"
    edge = numeric_edges[0]
    assert set(edge.evidence_ids) == {"e_contra_1", "e_contra_2"}
    # endpoints are attached to their (two distinct) claim clusters for the P6 join
    assert len(edge.claim_cluster_ids) == 2


def test_qualitative_present_vs_absent_emits_an_edge():
    """RECALL-FIRST on the no-number lethal-miss class: a present-vs-absent
    contraindication conflict (invisible to the numeric path) emits an edge."""
    graph = build_claim_graph(_rows("qualitative_present_vs_absent"))
    qual_edges = [e for e in graph.edges if e.source == "qualitative"]
    assert len(qual_edges) >= 1, "a qualitative conflict must NEVER be silently dropped"
    assert set(qual_edges[0].evidence_ids) == {"e_qual_1", "e_qual_2"}


def test_no_conflict_corpus_emits_no_edge():
    """No fabricated conflict: an agreeing corpus yields zero contradiction edges."""
    graph = build_claim_graph(_rows("no_conflict_corpus"))
    assert graph.edges == [], "must not fabricate a conflict where none exists"


def test_semantic_edge_with_injected_fake_judge():
    """The semantic NLI edge source fires with an INJECTED fake judge — no network,
    no production judge. Proves the injectable-detector design + recall on the
    prose-only directional-contradiction class."""
    rows = [
        {"evidence_id": "s1",
         "direct_quote": "Adjuvant chemotherapy improved overall survival in the cohort.",
         "source_url": "https://nejm.org/a", "tier": "T1"},
        {"evidence_id": "s2",
         "direct_quote": "Adjuvant chemotherapy provided no overall survival benefit in the cohort.",
         "source_url": "https://thelancet.com/b", "tier": "T1"},
    ]

    def fake_judge(claim_a: str, claim_b: str):
        # deterministic: these two prose claims directly contradict
        return ("contradict", 0.95)

    graph = build_claim_graph(rows, nli_judge=fake_judge)
    sem_edges = [e for e in graph.edges if e.source == "semantic"]
    assert len(sem_edges) >= 1, "injected judge must surface the prose-only conflict"


def test_no_judge_means_no_semantic_edges_no_spend():
    """No injected judge => NO semantic edges and NO production judge is built (the
    pure library never constructs an httpx client / makes a network call)."""
    rows = [
        {"evidence_id": "s1",
         "direct_quote": "Adjuvant chemotherapy improved overall survival.",
         "source_url": "https://nejm.org/a", "tier": "T1"},
        {"evidence_id": "s2",
         "direct_quote": "Adjuvant chemotherapy provided no overall survival benefit.",
         "source_url": "https://thelancet.com/b", "tier": "T1"},
    ]
    graph = build_claim_graph(rows)  # nli_judge defaults to None
    assert [e for e in graph.edges if e.source == "semantic"] == []


def test_injected_judge_fail_open_does_not_drop_rule_edges():
    """A judge that ERRORS on every pair must not abort the build AND must not
    suppress the deterministic numeric/qualitative edges (recall-first is preserved
    on the paths this module controls)."""
    rows = _rows("numeric_contradiction")

    def exploding_judge(claim_a: str, claim_b: str):
        raise RuntimeError("simulated transient judge failure")

    graph = build_claim_graph(rows, nli_judge=exploding_judge)
    # the numeric edge still fires; the failing judge only skips its own pairs
    assert any(e.source == "numeric" for e in graph.edges)
    assert [e for e in graph.edges if e.source == "semantic"] == []


# ── determinism: claim_cluster_id is stable + reproducible ─────────────────────


def test_claim_cluster_id_is_deterministic_across_runs():
    """Same input -> same claim_cluster_id (no uuid/random/time). Required for the
    downstream P6 join on (claim_cluster_id, origin_cluster_id)."""
    rows = _rows("equivalent_clinical_numeric")
    g1 = build_claim_graph(rows)
    g2 = build_claim_graph(rows)
    ids1 = [c.claim_cluster_id for c in g1.claims]
    ids2 = [c.claim_cluster_id for c in g2.claims]
    assert ids1 == ids2
    assert all(cid.startswith("clm_") for cid in ids1)


def test_cluster_id_groups_match_member_indices():
    """The clusters mapping is internally consistent: each claim_cluster_id maps to
    exactly the member indices whose claims carry that id."""
    graph = build_claim_graph(_rows("distinct_clinical_numeric"))
    for cid, indices in graph.clusters.items():
        for idx in indices:
            assert graph.claims[idx].claim_cluster_id == cid


# ── robustness: empty / degenerate input never raises ──────────────────────────


def test_empty_rows_yield_empty_graph():
    graph = build_claim_graph([])
    assert graph.claims == []
    assert graph.clusters == {}
    assert graph.edges == []
    assert graph.raw_row_count == 0
    assert graph.distinct_cluster_count == 0


def test_blank_text_rows_are_skipped_not_crashed():
    """Rows with no text produce no claim (and no crash) — never a phantom claim."""
    rows = [
        {"evidence_id": "blank1", "direct_quote": "", "source_url": "https://a.org"},
        {"evidence_id": "blank2", "source_url": "https://b.org"},
    ]
    graph = build_claim_graph(rows)
    assert graph.claims == []


def test_edge_requires_two_distinct_endpoints():
    """build_contradiction_edges drops any 'edge' with fewer than two endpoints —
    a single-source self-quote can never raise a cross-source conflict."""
    rows = _rows("numeric_contradiction")
    claims = extract_atomic_claims(rows)
    cluster_equivalent_claims(claims)
    edges = build_contradiction_edges(rows, claims)
    for e in edges:
        assert len(e.evidence_ids) >= 2
