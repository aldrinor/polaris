"""Offline unit tests for Phase 4a independence-collapse.

Module under test: ``src/polaris_graph/synthesis/independence_collapse.py``.

THE LOAD-BEARING INVARIANT (plan Phase 4a / Phase 6 copy-invariance):
adding a copied row to an existing cluster — even one whose own
``authority_score`` is HIGHER than the cluster's canonical origin — does NOT
change the cluster SET nor its CANONICAL ORIGIN. So a later weighted tally
over canonical origins (``cluster_mass = authority_score(canonical_origin)``)
cannot be inflated by copies. Proven by
``test_added_high_authority_copy_does_not_change_cluster_set_or_canonical``
and ``test_canonical_never_chosen_by_authority``.

All fixtures are inline literals (LAW VI — no live data, no network, no model).
"""
from __future__ import annotations

from typing import Any

from src.polaris_graph.synthesis.independence_collapse import (
    DEFAULT_ACCEPTABLE_MIRROR_DOMAINS,
    DEFAULT_SIMILARITY_THRESHOLD,
    collapse_independent_origins,
)

# The PSL gov-suffix tuple is passed in by the caller in production; for these
# offline tests a small fixture tuple suffices (no host literals live in the
# module under test). Covers the multi-level suffix path used by
# registrable_domain.
_GOV_SUFFIXES: tuple[str, ...] = ("go.jp", "gc.ca", "gov.uk")

# A press-release body and a near-verbatim syndication of it (>0.85 cosine).
_PRESS_RELEASE = (
    "The agency announced that quarterly emissions fell by twelve percent "
    "following the new industrial regulation introduced last spring across "
    "all twenty member regions of the federation."
)
_SYNDICATED_COPY = (
    "The agency announced that quarterly emissions fell by twelve percent "
    "following the new industrial regulation introduced last spring across "
    "all twenty member regions of the federation, officials said."
)
# A genuinely different finding (independent reporting) — low cosine to above.
_INDEPENDENT_FINDING = (
    "A separate university study measured rainfall totals over the alpine "
    "watershed and reported a record snowpack deficit for the third "
    "consecutive winter season."
)


def _row(
    evidence_id: str,
    url: str,
    text: str,
    *,
    authority_score: float | None = None,
    **extra: Any,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "evidence_id": evidence_id,
        "source_url": url,
        "direct_quote": text,
    }
    if authority_score is not None:
        row["authority_score"] = authority_score
    row.update(extra)
    return row


def _collapse(rows: list[dict[str, Any]], **kw: Any):
    return collapse_independent_origins(rows, gov_suffixes=_GOV_SUFFIXES, **kw)


# ── Basic shape / edge cases ────────────────────────────────────────────────


def test_empty_input_returns_empty_result() -> None:
    result = _collapse([])
    assert result.raw_row_count == 0
    assert result.independent_origin_count == 0
    assert result.clusters == []
    assert result.assignments == []


def test_single_row_is_its_own_canonical_origin() -> None:
    result = _collapse([_row("e0", "https://newsone.com/a", _PRESS_RELEASE)])
    assert result.independent_origin_count == 1
    assert len(result.assignments) == 1
    a = result.assignments[0]
    assert a.is_canonical_origin is True
    assert a.is_derivative_copy is False
    assert a.canonical_index == 0


def test_every_input_row_has_exactly_one_assignment() -> None:
    rows = [
        _row("e0", "https://a.com/x", _PRESS_RELEASE),
        _row("e1", "https://b.com/y", _INDEPENDENT_FINDING),
        _row("e2", "https://c.com/z", _SYNDICATED_COPY),
    ]
    result = _collapse(rows)
    assert [a.row_index for a in result.assignments] == [0, 1, 2]
    # Partition check: canonical + copy flags are mutually exclusive & total.
    for a in result.assignments:
        assert a.is_canonical_origin != a.is_derivative_copy


# ── Host-collapse primitive (layered on corroboration.registrable_domain) ───


def test_same_registrable_domain_collapses_to_one_origin() -> None:
    """Two different texts on subdomains of one institution = one origin."""
    rows = [
        _row("e0", "https://news.example.com/a", _PRESS_RELEASE),
        _row("e1", "https://www.example.com/b", _INDEPENDENT_FINDING),
    ]
    result = _collapse(rows)
    assert result.independent_origin_count == 1
    cluster = result.clusters[0]
    assert sorted(cluster.member_indices) == [0, 1]
    assert cluster.member_hosts == ["example.com"]


def test_distinct_domains_distinct_content_stay_independent() -> None:
    rows = [
        _row("e0", "https://a.com/x", _PRESS_RELEASE),
        _row("e1", "https://b.com/y", _INDEPENDENT_FINDING),
    ]
    result = _collapse(rows)
    assert result.independent_origin_count == 2


# ── Content-copy collapse (TF-IDF cosine >= threshold) ──────────────────────


def test_near_verbatim_copy_across_domains_collapses() -> None:
    rows = [
        _row("e0", "https://origin-wire.com/release", _PRESS_RELEASE),
        _row("e1", "https://reprint-daily.com/story", _SYNDICATED_COPY),
    ]
    result = _collapse(rows)
    assert result.independent_origin_count == 1
    cluster = result.clusters[0]
    assert sorted(cluster.member_indices) == [0, 1]
    assert cluster.canonical_index == 0  # earliest by corpus order
    assert cluster.copy_indices == [1]


def test_many_copies_of_one_release_collapse_to_one_origin() -> None:
    """N near-verbatim copies of one press release -> independent_origin==1."""
    rows = [_row("e0", "https://origin-wire.com/release", _PRESS_RELEASE)]
    for i in range(1, 50):
        rows.append(
            _row(f"e{i}", f"https://reprint{i}.com/story", _SYNDICATED_COPY)
        )
    result = _collapse(rows)
    assert result.raw_row_count == 50
    assert result.independent_origin_count == 1
    assert result.clusters[0].canonical_index == 0
    assert len(result.clusters[0].copy_indices) == 49


def test_two_distinct_findings_with_copies_yield_two_origins() -> None:
    rows = [
        _row("e0", "https://wire-a.com/r", _PRESS_RELEASE),
        _row("e1", "https://reprint-a.com/r", _SYNDICATED_COPY),   # copy of e0
        _row("e2", "https://univ-b.edu/study", _INDEPENDENT_FINDING),
    ]
    result = _collapse(rows)
    assert result.independent_origin_count == 2


# ── Acceptable-mirror allowlist (false-positive bound) ──────────────────────


def test_acceptable_mirror_hosts_not_collapsed_on_content_alone() -> None:
    """Same paper text on two scholarly mirror hosts stays TWO origins."""
    paper_text = (
        "We present a transformer variant whose attention cost scales "
        "linearly with sequence length while preserving downstream accuracy "
        "on the standard long-range benchmark suite."
    )
    rows = [
        _row("e0", "https://arxiv.org/abs/2401.00001", paper_text),
        _row("e1", "https://ncbi.nlm.nih.gov/pmc/articles/PMC1", paper_text),
    ]
    result = _collapse(rows)
    # Both are acceptable-mirror domains -> NOT collapsed on content.
    assert result.independent_origin_count == 2


def test_mirror_allowlist_still_collapses_same_domain_copies() -> None:
    """The allowlist suppresses CROSS-host content-collapse only; two copies
    on the SAME mirror host are still one origin (host-collapse primitive)."""
    paper_text = (
        "We present a transformer variant whose attention cost scales "
        "linearly with sequence length while preserving downstream accuracy."
    )
    rows = [
        _row("e0", "https://arxiv.org/abs/2401.00001", paper_text),
        _row("e1", "https://arxiv.org/abs/2401.00001v2", paper_text),
    ]
    result = _collapse(rows)
    assert result.independent_origin_count == 1


def test_mirror_host_not_collapsed_with_cross_domain_copy() -> None:
    """A mirror host (arXiv) only collapses within its OWN registrable domain,
    NEVER via cross-domain content — so a non-mirror blog copying an arXiv
    abstract stays a SEPARATE origin. This keeps mirrors immune to being
    transitively bridged through a content copy (Codex iter-1 P2); the rare
    blog-copy-of-a-paper is a safe under-collapse, never a mirror false-merge."""
    paper_text = (
        "We present a transformer variant whose attention cost scales "
        "linearly with sequence length while preserving downstream accuracy "
        "on the standard long-range benchmark suite of nine tasks."
    )
    rows = [
        _row("e0", "https://arxiv.org/abs/2401.00001", paper_text),
        _row("e1", "https://random-blog.com/repost", paper_text),
    ]
    result = _collapse(rows)
    assert result.independent_origin_count == 2


def test_blog_copying_two_mirrors_does_not_merge_the_mirrors() -> None:
    """Codex iter-1 P2 regression: a non-mirror blog whose content matches BOTH
    arXiv and PMC must NOT transitively bridge the two mirror hosts into one
    origin. arXiv, PMC, and the blog stay THREE independent origins."""
    paper_text = (
        "We present a transformer variant whose attention cost scales "
        "linearly with sequence length while preserving downstream accuracy "
        "on the standard long-range benchmark suite of nine tasks."
    )
    rows = [
        _row("arxiv", "https://arxiv.org/abs/2401.00001", paper_text),
        _row("pmc", "https://ncbi.nlm.nih.gov/pmc/articles/PMC1", paper_text),
        _row("blog", "https://random-blog.com/repost", paper_text),
    ]
    result = _collapse(rows)
    assert result.independent_origin_count == 3


# ── THE INVARIANT: copies cannot change the cluster set or canonical ────────


def test_added_high_authority_copy_does_not_change_cluster_set_or_canonical() -> None:
    """Load-bearing copy-invariance proof.

    Baseline: one canonical origin (low authority) + one copy.
    Then add ANOTHER copy whose own authority_score is far HIGHER than the
    canonical's. The cluster set and the canonical origin MUST be unchanged,
    so a weight tally over canonical origins cannot be inflated by the copy.
    """
    base = [
        _row("origin", "https://wire.com/release", _PRESS_RELEASE,
             authority_score=0.20),
        _row("copy1", "https://reprint1.com/s", _SYNDICATED_COPY,
             authority_score=0.30),
    ]
    base_result = _collapse(base)
    assert base_result.independent_origin_count == 1
    base_cluster = base_result.clusters[0]
    base_canonical_eid = base[base_cluster.canonical_index]["evidence_id"]
    assert base_canonical_eid == "origin"

    # Add a HIGHER-authority verbatim republisher.
    with_high_authority_copy = base + [
        _row("copy2_high_auth", "https://bigsite.com/s", _SYNDICATED_COPY,
             authority_score=0.99),
    ]
    result = _collapse(with_high_authority_copy)

    # Still exactly ONE independent origin.
    assert result.independent_origin_count == 1
    cluster = result.clusters[0]
    # Canonical origin is STILL the original low-authority seed.
    assert with_high_authority_copy[cluster.canonical_index]["evidence_id"] == "origin"
    # The high-authority copier is flagged derivative, not canonical.
    high = next(
        a for a in result.assignments
        if with_high_authority_copy[a.row_index]["evidence_id"] == "copy2_high_auth"
    )
    assert high.is_derivative_copy is True
    assert high.is_canonical_origin is False
    # The stable origin_cluster_id is UNCHANGED by the copy addition.
    assert cluster.origin_cluster_id == base_cluster.origin_cluster_id


def test_canonical_never_chosen_by_authority() -> None:
    """Even if a derivative copy has the single highest authority in the
    cluster, the canonical is the earliest/seed member, never the highest
    authority. Authority is not consulted for the canonical choice."""
    rows = [
        _row("seed", "https://origin.com/r", _PRESS_RELEASE,
             authority_score=0.10),                    # earliest, low authority
        _row("loud_copy", "https://loud.com/r", _SYNDICATED_COPY,
             authority_score=1.00),                    # later, top authority
    ]
    result = _collapse(rows)
    assert result.independent_origin_count == 1
    cluster = result.clusters[0]
    assert rows[cluster.canonical_index]["evidence_id"] == "seed"
    assert cluster.copy_indices == [1]


def test_undated_prepended_higher_authority_copy_cannot_steal_canonical() -> None:
    """Codex iter-4 P1 regression: when EVERY member is undated, the canonical is the
    LOWEST-authority member (not the first by input index), so an undated higher-authority
    copy PREPENDED before the seed cannot become canonical or inflate cluster_mass, and the
    origin_cluster_id stays stable."""
    seed = _row("seed", "https://origin.com/r", _PRESS_RELEASE, authority_score=0.10)
    base_id = _collapse([seed]).clusters[0].origin_cluster_id
    high_copy = _row("loud", "https://loud.com/r", _SYNDICATED_COPY, authority_score=0.99)
    rows = [high_copy, seed]  # PREPEND the undated higher-authority copy before the seed
    result = _collapse(rows)
    assert result.independent_origin_count == 1
    cluster = result.clusters[0]
    # Canonical is the lowest-authority seed, NOT the prepended high-authority copy.
    assert rows[cluster.canonical_index]["evidence_id"] == "seed"
    assert cluster.origin_cluster_id == base_id
    loud = next(a for a in result.assignments if rows[a.row_index]["evidence_id"] == "loud")
    assert loud.is_derivative_copy is True


def test_undated_high_authority_copy_cannot_outrank_dated_canonical() -> None:
    """Codex iter-1 P1 regression: a DATED canonical origin + an UNDATED copy
    whose own authority is far higher. The undated copy must NOT become the
    canonical (an undated row can never outrank a dated origin), so the cluster
    mass over the canonical is uninflatable."""
    base = [
        _row("dated_origin", "https://wire.com/release", _PRESS_RELEASE,
             authority_score=0.15, published_date="2024-02-01"),
    ]
    assert _collapse(base).clusters[0].canonical_index == 0

    rows = base + [
        _row("undated_high_auth", "https://bigsite.com/s", _SYNDICATED_COPY,
             authority_score=0.99),
    ]
    result = _collapse(rows)
    assert result.independent_origin_count == 1
    cluster = result.clusters[0]
    # Canonical is STILL the dated origin, never the undated high-authority copy.
    assert rows[cluster.canonical_index]["evidence_id"] == "dated_origin"
    undated = next(
        a for a in result.assignments
        if rows[a.row_index]["evidence_id"] == "undated_high_auth"
    )
    assert undated.is_derivative_copy is True


def test_origin_cluster_id_stable_under_prepended_copy() -> None:
    """Codex iter-2 P2 regression: origin_cluster_id derives from the canonical row's
    EVIDENCE IDENTITY, not its input position — so a copy added BEFORE the canonical
    (prepended) does not change the cluster id even though the canonical's index shifts."""
    origin = _row("origin", "https://wire.com/release", _PRESS_RELEASE,
                  published_date="2024-02-01")
    base_id = _collapse([origin]).clusters[0].origin_cluster_id
    assert base_id == "origin::origin"

    copy = _row("copycat", "https://aggregator.com/x", _SYNDICATED_COPY)
    rows = [copy, origin]  # PREPEND the derivative copy before the canonical origin
    result = _collapse(rows)
    assert result.independent_origin_count == 1
    cluster = result.clusters[0]
    # Canonical is still the dated origin (its index is now 1), and the id is unchanged.
    assert rows[cluster.canonical_index]["evidence_id"] == "origin"
    assert cluster.origin_cluster_id == base_id


def test_malformed_non_iso_date_copy_cannot_become_canonical() -> None:
    """Codex iter-2 P1 regression: a derivative copy whose published_date is malformed /
    non-ISO (day-first '01/01/2099') is treated as UNDATED — it can NOT lexically outrank
    the canonical's real ISO date and steal canonical."""
    origin = _row("origin", "https://wire.com/release", _PRESS_RELEASE,
                  published_date="2024-01-01")
    copy = _row("copycat", "https://aggregator.com/x", _SYNDICATED_COPY,
                published_date="01/01/2099")  # day-first, NOT ISO -> treated as undated
    rows = [origin, copy]
    result = _collapse(rows)
    assert result.independent_origin_count == 1
    cluster = result.clusters[0]
    assert rows[cluster.canonical_index]["evidence_id"] == "origin"
    copy_assignment = next(
        a for a in result.assignments if rows[a.row_index]["evidence_id"] == "copycat"
    )
    assert copy_assignment.is_derivative_copy is True


def test_invalid_calendar_date_copy_cannot_become_canonical() -> None:
    """Codex iter-3 P1 regression: an ISO-SHAPED but non-calendar date (2024-02-31 — Feb has
    no 31st) is treated as UNDATED via real datetime validation, so it cannot outrank a real
    2024-03-01 origin and steal canonical (it would have, since (2024,2,31) < (2024,3,1))."""
    origin = _row("origin", "https://wire.com/release", _PRESS_RELEASE,
                  published_date="2024-03-01")
    copy = _row("copycat", "https://aggregator.com/x", _SYNDICATED_COPY,
                published_date="2024-02-31")  # Feb 31 — not a real date -> treated as undated
    rows = [origin, copy]
    result = _collapse(rows)
    assert result.independent_origin_count == 1
    cluster = result.clusters[0]
    assert rows[cluster.canonical_index]["evidence_id"] == "origin"


def test_canonical_uses_explicit_publication_order_when_present() -> None:
    """When a publication-date key is present, the EARLIEST date is canonical
    even if it appears later in corpus order — still order-based, never
    authority-based."""
    rows = [
        # Later date, appears first in corpus order, higher authority.
        _row("later_pub", "https://a.com/r", _PRESS_RELEASE,
             authority_score=0.90, published_date="2025-06-01"),
        # Earlier date, appears second, lower authority -> should be canonical.
        _row("earlier_pub", "https://b.com/r", _SYNDICATED_COPY,
             authority_score=0.10, published_date="2025-01-15"),
    ]
    result = _collapse(rows)
    assert result.independent_origin_count == 1
    cluster = result.clusters[0]
    assert rows[cluster.canonical_index]["evidence_id"] == "earlier_pub"


def test_copy_addition_is_order_independent_for_canonical() -> None:
    """Re-ordering the copies in the input does not change which row is
    canonical (the seed) nor the cluster set."""
    seed = _row("seed", "https://origin.com/r", _PRESS_RELEASE,
                authority_score=0.10, published_date="2024-01-01")
    copy_a = _row("ca", "https://a.com/r", _SYNDICATED_COPY,
                  authority_score=0.95, published_date="2024-05-01")
    copy_b = _row("cb", "https://b.com/r", _SYNDICATED_COPY,
                  authority_score=0.99, published_date="2024-09-01")
    r1 = _collapse([seed, copy_a, copy_b])
    r2 = _collapse([copy_b, seed, copy_a])
    assert r1.independent_origin_count == r2.independent_origin_count == 1
    assert r1.clusters[0].member_hosts == r2.clusters[0].member_hosts
    # Canonical is the seed in both orderings.
    assert (
        [seed, copy_a, copy_b][r1.clusters[0].canonical_index]["evidence_id"]
        == "seed"
    )
    assert (
        [copy_b, seed, copy_a][r2.clusters[0].canonical_index]["evidence_id"]
        == "seed"
    )


# ── Emitted-contract groupability (Phase 6 can group by origin_cluster_id) ──


def test_origin_cluster_id_is_stable_and_groupable() -> None:
    """Every row carries a stable origin_cluster_id; grouping assignments by
    it reproduces the cluster membership (what Phase 6's weight-mass needs)."""
    rows = [
        _row("e0", "https://wire.com/r", _PRESS_RELEASE),
        _row("e1", "https://reprint.com/r", _SYNDICATED_COPY),     # copy of e0
        _row("e2", "https://univ.edu/study", _INDEPENDENT_FINDING),
    ]
    result = _collapse(rows)
    grouped: dict[str, list[int]] = {}
    for a in result.assignments:
        grouped.setdefault(a.origin_cluster_id, []).append(a.row_index)
    # Exactly one id per cluster; membership matches the cluster objects.
    assert len(grouped) == result.independent_origin_count
    for cluster in result.clusters:
        assert sorted(grouped[cluster.origin_cluster_id]) == sorted(
            cluster.member_indices
        )
    # Each cluster has exactly one canonical row.
    for cluster in result.clusters:
        canonicals = [
            a for a in result.assignments
            if a.origin_cluster_id == cluster.origin_cluster_id
            and a.is_canonical_origin
        ]
        assert len(canonicals) == 1
        assert canonicals[0].row_index == cluster.canonical_index


# ── Configurable threshold (LAW VI) ─────────────────────────────────────────


def test_threshold_is_caller_configurable() -> None:
    """Raising the threshold above the pair's cosine prevents collapse;
    proves the 0.85 default is config, not a hardcoded magic gate."""
    rows = [
        _row("e0", "https://a.com/r", _PRESS_RELEASE),
        _row("e1", "https://b.com/r", _SYNDICATED_COPY),
    ]
    collapsed = _collapse(rows, similarity_threshold=0.85)
    assert collapsed.independent_origin_count == 1
    # An impossibly high threshold disables content-collapse entirely.
    not_collapsed = _collapse(rows, similarity_threshold=1.0001)
    assert not_collapsed.independent_origin_count == 2
    assert not_collapsed.similarity_threshold == 1.0001


def test_result_reports_default_threshold() -> None:
    result = _collapse([_row("e0", "https://a.com/r", _PRESS_RELEASE)])
    assert result.similarity_threshold == DEFAULT_SIMILARITY_THRESHOLD


def test_default_mirror_allowlist_contains_curated_registrable_domains() -> None:
    # Entries are in eTLD+1 form (the space the comparison uses): PMC's
    # ncbi.nlm.nih.gov collapses to nih.gov, so the entry is nih.gov.
    assert "arxiv.org" in DEFAULT_ACCEPTABLE_MIRROR_DOMAINS
    assert "ssrn.com" in DEFAULT_ACCEPTABLE_MIRROR_DOMAINS
    assert "nih.gov" in DEFAULT_ACCEPTABLE_MIRROR_DOMAINS


# ── Purity: caller rows are never mutated ───────────────────────────────────


def test_input_rows_are_not_mutated() -> None:
    rows = [
        _row("e0", "https://a.com/r", _PRESS_RELEASE, authority_score=0.2),
        _row("e1", "https://b.com/r", _SYNDICATED_COPY, authority_score=0.9),
    ]
    snapshot = [dict(r) for r in rows]
    _collapse(rows)
    assert rows == snapshot  # no origin_cluster_id/flags written onto inputs


def test_empty_text_rows_do_not_falsely_collapse() -> None:
    """Two rows with no text and different domains must NOT collapse (a zero
    vector has cosine 0 with everything — never a false copy)."""
    rows = [
        _row("e0", "https://a.com/r", ""),
        _row("e1", "https://b.com/r", ""),
    ]
    result = _collapse(rows)
    assert result.independent_origin_count == 2
