"""Phase 4a (L3, §6c-4) — independence-collapse by content near-duplication.

Credibility-weighted sourcing redesign, plan
``docs/credibility_weighted_sourcing_redesign_plan_2026_06_07.md`` Phase 4a.

WHAT THIS DOES
==============
Given a list of generator-visible evidence rows, cluster the near-DUPLICATE
content copies (syndication / press-release rehash / verbatim republication)
into ``origin clusters`` so a later weighted tally (L5, Phase 6) counts each
independent ORIGIN exactly once and cannot be inflated by copies.

The collapse is layered on the existing host-collapse primitive
(``authority.corroboration``: ``count_independent_hosts`` /
``registrable_domain``). Two rows join the same origin cluster when EITHER

  1. they share a registrable domain (eTLD+1 host-collapse — the existing
     primitive; subdomains of one institution are the same origin), OR
  2. their text content is a near-duplicate: TF-IDF cosine >= the configured
     similarity threshold (default ``DEFAULT_SIMILARITY_THRESHOLD`` = 0.85),

EXCEPT a curated acceptable-mirror allowlist (arXiv / SSRN / PMC by default)
is NOT collapsed on content alone across DIFFERENT registrable domains — a
legitimate mirror of the same paper on two scholarly hosts stays two
independent origins rather than being falsely flagged a copy (the
echo-collapse false-positive bound, plan §6 RISKS).

CANONICAL-ORIGIN INVARIANT (the load-bearing safety property)
=============================================================
Each cluster designates exactly ONE **canonical origin**. When ANY member
carries a parseable publication date, the canonical is the EARLIEST-dated
member and ``authority_score`` is NOT consulted — a DATED cluster keeps
STRICT copy-invariance (adding a same/later/undated copy of ANY authority
leaves the canonical + cluster_mass unchanged). When EVERY member is undated
there is no date to identify the seed, so the canonical is the LOWEST-
``authority_score`` member (conservative-min, Codex #1161): a higher-authority
copy can NEVER become canonical or inflate cluster_mass, and the worst a copy
can do is LOWER the mass (monotonic non-increase) — never inflate.

Therefore: adding a copied row to an existing cluster — **even a copy whose
own ``authority_score`` is HIGHER than the cluster's canonical origin** —
does NOT change the cluster set nor its canonical origin nor inflate its
mass. A high-authority verbatim republisher is still derivative; only its own
*independent* content
would form a new cluster. This is exactly what lets the L5 weighted tally
(``cluster_mass = authority_score(canonical_origin)``, copies contribute
zero) be uninflatable by copies. The invariant is proven by
``test_independence_collapse.py``.

OUTPUT (per the Phase-4a emitted contract)
==========================================
``collapse_independent_origins`` returns an :class:`IndependenceCollapseResult`
carrying, for every input row (by index):
  - a stable ``origin_cluster_id`` (deterministic, derived from the canonical
    member so it is stable under copy-additions),
  - the canonical-origin row index for that cluster,
  - an ``is_canonical_origin`` / ``is_derivative_copy`` flag,
and an ``independent_origin_count`` = number of distinct origin clusters.

PURITY / SAFETY
===============
Pure: constructs no client, opens no network, loads no model, calls no LLM,
mutates none of the caller's rows (membership/flags are emitted in a fresh
structure). snake_case, explicit imports, no host/TLD literals in code (the
PSL ``gov_suffixes`` and the mirror allowlist are passed in by the caller).

DEFAULT-OFF: this module is inert library code. Nothing in the production
pipeline imports or invokes it; it acts ONLY when a flagged caller calls
``collapse_independent_origins``. It touches NO faithfulness gate
(strict_verify / 4-role / two-family / corpus_approval are untouched) and
NEVER drops a source — it only annotates duplicated corroboration.
"""
from __future__ import annotations

import datetime
import math
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from src.polaris_graph.authority.corroboration import registrable_domain

# ── Module constants (LAW VI — named, not magic numbers) ────────────────────
# Cosine-similarity threshold at/above which two texts are a content copy.
DEFAULT_SIMILARITY_THRESHOLD: float = 0.85
# Curated acceptable-mirror domains: legitimate cross-host mirrors of the same
# scholarly artefact that must NOT be over-collapsed on content alone (plan §6
# echo-collapse false-positive bound). Passed-in overrides win; this is only
# the documented default.
#
# IMPORTANT: these are compared against each row's REGISTRABLE DOMAIN (the
# eTLD+1 produced by ``corroboration.registrable_domain``), so they MUST be
# written in eTLD+1 form. PMC lives at ``ncbi.nlm.nih.gov``, whose eTLD+1
# (without a multi-level PSL suffix match) collapses to ``nih.gov`` — so the
# allowlist entry for PMC is ``nih.gov`` (the registrable-domain key actually
# seen at comparison time), NOT the full ``ncbi.nlm.nih.gov`` host. Writing the
# full host here would silently never match and re-open the false-positive.
DEFAULT_ACCEPTABLE_MIRROR_DOMAINS: tuple[str, ...] = (
    "arxiv.org",   # arXiv preprint mirror
    "ssrn.com",    # SSRN working-paper mirror
    "nih.gov",     # PMC (ncbi.nlm.nih.gov) eTLD+1 -> nih.gov
)
# Row keys consulted for the row's text, in priority order. First non-empty
# wins. Mirrors finding_dedup's row-shape expectations.
_TEXT_KEYS: tuple[str, ...] = ("direct_quote", "statement", "text", "snippet")
# Row keys consulted for an explicit publication-order signal, in priority
# order. First parseable value wins; absence falls back to corpus order.
_ORDER_KEYS: tuple[str, ...] = (
    "published_date",
    "publication_date",
    "published",
    "date",
)
# A token is a maximal run of word characters; lowercased. Pure-stdlib
# tokeniser — no model, no network.
_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)


@dataclass
class OriginCluster:
    """One cluster of rows that share a single independent origin."""

    origin_cluster_id: str
    canonical_index: int            # input row index of the canonical origin
    member_indices: list[int]       # all input row indices in the cluster
    copy_indices: list[int]         # derivative-copy members (canonical excluded)
    member_hosts: list[str]         # sorted unique registrable-domains present


@dataclass
class RowOriginAssignment:
    """Per-row origin assignment (emitted contract — one per input row)."""

    row_index: int
    origin_cluster_id: str
    canonical_index: int
    is_canonical_origin: bool
    is_derivative_copy: bool


@dataclass
class IndependenceCollapseResult:
    """Result of :func:`collapse_independent_origins`."""

    clusters: list[OriginCluster]
    assignments: list[RowOriginAssignment]  # ordered by input row index
    raw_row_count: int
    independent_origin_count: int            # == number of distinct clusters
    similarity_threshold: float = field(default=DEFAULT_SIMILARITY_THRESHOLD)


# ── Pure helpers ────────────────────────────────────────────────────────────


def _host_of(url: str) -> str:
    """Bare hostname (lowercased, ``www.`` stripped) from a URL; ``""`` if none.

    ``registrable_domain`` expects a HOST, not a full URL, so this reduction
    must run first (mirrors ``finding_dedup._host_of``).
    """
    if not url:
        return ""
    host = (urlparse(url).hostname or "").lower().strip()
    if host.startswith("www."):
        host = host[4:]
    return host


def _row_text(row: dict[str, Any]) -> str:
    """First non-empty text field of a row (priority order ``_TEXT_KEYS``)."""
    for key in _TEXT_KEYS:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _row_domain(row: dict[str, Any], gov_suffixes: tuple[str, ...]) -> str:
    """Registrable domain (eTLD+1) for a row's ``source_url``; ``""`` if none."""
    return registrable_domain(_host_of(str(row.get("source_url", ""))), gov_suffixes)


def _parse_order_date(value: Any) -> tuple[int, int, int] | None:
    """Parse a publication-order value to a sortable ``(year, month, day)``, or ``None``
    when it is not CONFIDENTLY parseable (then the row is treated as undated and sorts
    last). Only UNAMBIGUOUS year-first formats are accepted — ISO ``YYYY-MM-DD`` /
    ``YYYY/MM/DD`` / ``YYYY-MM`` / ``YYYY``, or an int/float year. Ambiguous or malformed
    values (e.g. ``01/01/2099`` day-first, or free text) are REJECTED so they cannot
    lexically outrank a real ISO date and steal the canonical origin (Codex iter-2 P1).
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        year = int(value)
        return (year, 1, 1) if 1000 <= year <= 9999 else None
    if not isinstance(value, str):
        return None
    match = re.match(r"^(\d{4})(?:[-/](\d{1,2})(?:[-/](\d{1,2}))?)?$", value.strip())
    if not match:
        return None
    year = int(match.group(1))
    month = int(match.group(2) or 1)
    day = int(match.group(3) or 1)
    try:
        # REAL calendar validation — an ISO-shaped but non-calendar date (e.g. 2024-02-31,
        # Feb has no 31st; or 2024-13-01) raises and is treated as undated, so it cannot
        # outrank a genuine date and steal the canonical origin (Codex iter-3 P1).
        datetime.date(year, month, day)
    except ValueError:
        return None
    return (year, month, day)


def _order_key(row: dict[str, Any], row_index: int) -> tuple:
    """Deterministic canonical-selection order key (canonical = ``min`` over members).

    A DATED row sorts before any undated row; among dated rows the earliest CALENDAR date
    wins and ``authority_score`` is NEVER consulted (so a higher-authority but later-dated
    copy can never steal the canonical origin). Same-date ties break on the STABLE
    evidence_id, then the input index. Codex iter-1/2/3 fixes: dated-beats-undated;
    malformed/non-ISO and non-calendar dates are treated as undated.

    When EVERY member of a cluster is undated there is no date to identify the seed
    positionally, so the canonical is the LOWEST-``authority_score`` member: a higher-
    authority copy can then never become the canonical origin and inflate ``cluster_mass``
    (the load-bearing copy-invariance invariant — Codex iter-4 P1). The evidence_id breaks
    authority ties (NOT the input index), so a prepended copy cannot win on position. A
    later-added LOWER-authority copy may relabel the cluster to itself, but that only ever
    LOWERS the mass — monotonically non-increasing under additions, never inflatable.

    Returns a 5-tuple ``(has_no_date, (y, m, d), auth_rank, evidence_id, row_index)``; the
    ``auth_rank`` slot is a constant ``0.0`` for DATED rows (date decides) and the real
    authority for undated rows (lowest wins).
    """
    eid = str(row.get("evidence_id", "") or "")
    for key in _ORDER_KEYS:
        parsed = _parse_order_date(row.get(key))
        if parsed is not None:
            return (0, parsed, 0.0, eid, row_index)
    authority = row.get("authority_score")
    auth_rank = float(authority) if isinstance(authority, (int, float)) else 0.0
    return (1, (9999, 12, 31), auth_rank, eid, row_index)


def _tokenize(text: str) -> list[str]:
    """Lowercased word-character tokens. Pure stdlib; deterministic."""
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _term_frequencies(tokens: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for tok in tokens:
        counts[tok] = counts.get(tok, 0) + 1
    return counts


def _tfidf_cosine_matrix(texts: list[str]) -> list[list[float]]:
    """Pairwise TF-IDF cosine similarity over ``texts`` (pure Python).

    TF = raw term count per document. IDF = ``ln((1 + N) / (1 + df)) + 1``
    (the smoothed, always-positive scikit-learn convention) so a single-doc
    corpus still yields well-defined, non-degenerate vectors. Vectors are
    L2-normalised; cosine of two normalised vectors is their dot product.
    An empty document has a zero vector and cosine 0 with everything.
    """
    n = len(texts)
    token_lists = [_tokenize(t) for t in texts]
    # Document frequency per term.
    doc_freq: dict[str, int] = {}
    for tokens in token_lists:
        for term in set(tokens):
            doc_freq[term] = doc_freq.get(term, 0) + 1
    idf: dict[str, float] = {
        term: math.log((1 + n) / (1 + df)) + 1.0 for term, df in doc_freq.items()
    }
    # Build L2-normalised TF-IDF vectors as sparse dicts.
    vectors: list[dict[str, float]] = []
    for tokens in token_lists:
        tf = _term_frequencies(tokens)
        vec = {term: count * idf[term] for term, count in tf.items()}
        norm = math.sqrt(sum(w * w for w in vec.values()))
        if norm > 0.0:
            vec = {term: w / norm for term, w in vec.items()}
        vectors.append(vec)
    # Pairwise cosine = dot product of normalised vectors.
    matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        matrix[i][i] = 1.0 if vectors[i] else 0.0
        for j in range(i + 1, n):
            a, b = vectors[i], vectors[j]
            # Iterate the smaller dict for the dot product.
            if len(a) > len(b):
                a, b = b, a
            dot = sum(weight * b.get(term, 0.0) for term, weight in a.items())
            sim = 0.0 if dot < 0.0 else (1.0 if dot > 1.0 else dot)
            matrix[i][j] = sim
            matrix[j][i] = sim
    return matrix


class _UnionFind:
    """Minimal disjoint-set for transitive content-copy clustering."""

    def __init__(self, n: int) -> None:
        self._parent = list(range(n))

    def find(self, x: int) -> int:
        root = x
        while self._parent[root] != root:
            root = self._parent[root]
        # Path compression.
        while self._parent[x] != root:
            self._parent[x], x = root, self._parent[x]
        return root

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            # Attach the higher-index root under the lower so the canonical
            # (lowest order-key) tends to stay near the root; canonical choice
            # below is explicit regardless, this only keeps roots stable.
            lo, hi = (ra, rb) if ra < rb else (rb, ra)
            self._parent[hi] = lo


# ── Public API ──────────────────────────────────────────────────────────────


def collapse_independent_origins(
    rows: list[dict[str, Any]],
    *,
    gov_suffixes: tuple[str, ...],
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    acceptable_mirror_domains: tuple[str, ...] = DEFAULT_ACCEPTABLE_MIRROR_DOMAINS,
) -> IndependenceCollapseResult:
    """Cluster rows into independent origins; flag derivative copies.

    Args:
        rows: generator-visible evidence rows. Each may carry ``evidence_id``,
            ``source_url``, text (``direct_quote``/``statement``/``text``/
            ``snippet``), an optional publication-order key
            (``published_date``/``publication_date``/``published``/``date``),
            and an optional ``authority_score`` (NOT used for clustering or
            canonical choice — only carried through by the caller).
        gov_suffixes: PSL multi-level gov-suffix tuple from
            ``authority.data_loader.load_authority_data()["psl_gov_suffixes"]``
            — passed in so this module hardcodes NO host/TLD literals.
        similarity_threshold: TF-IDF cosine at/above which two texts are a
            content copy (LAW VI — caller-configurable; default 0.85).
        acceptable_mirror_domains: registrable domains whose cross-host
            content near-duplicates are legitimate mirrors and are NOT
            collapsed on content alone (false-positive bound).

    Returns:
        :class:`IndependenceCollapseResult` with one
        :class:`RowOriginAssignment` per input row (ordered by row index),
        the :class:`OriginCluster` list, and the ``independent_origin_count``.
    """
    rows = list(rows or [])
    n = len(rows)
    threshold = float(similarity_threshold)
    mirror_set = {d.lower() for d in acceptable_mirror_domains}

    if n == 0:
        return IndependenceCollapseResult(
            clusters=[],
            assignments=[],
            raw_row_count=0,
            independent_origin_count=0,
            similarity_threshold=threshold,
        )

    domains = [_row_domain(rows[i], gov_suffixes) for i in range(n)]
    texts = [_row_text(rows[i]) for i in range(n)]
    sim = _tfidf_cosine_matrix(texts)

    uf = _UnionFind(n)
    for i in range(n):
        for j in range(i + 1, n):
            same_domain = bool(domains[i]) and domains[i] == domains[j]
            if same_domain:
                # Same registrable origin (host-collapse primitive): one origin.
                uf.union(i, j)
                continue
            # Cross-domain: collapse only on content near-duplication. A curated
            # acceptable-mirror host (arXiv/SSRN/PMC) only ever collapses with its
            # OWN registrable domain (the same_domain branch above), NEVER via
            # cross-domain content. Otherwise a non-mirror blog that copies the
            # content of TWO different mirror hosts would TRANSITIVELY bridge them
            # into one union-find cluster (Codex iter-1 P2). Skipping any
            # cross-domain union that touches a mirror keeps legitimate mirrors
            # independent on content alone; the rare non-mirror copy of mirror
            # content simply stays its own origin — a safe under-collapse, never a
            # mirror false-merge.
            either_mirror = domains[i] in mirror_set or domains[j] in mirror_set
            if either_mirror:
                continue
            if texts[i] and texts[j] and sim[i][j] >= threshold:
                uf.union(i, j)

    # Group members by union-find root.
    members_by_root: dict[int, list[int]] = {}
    for i in range(n):
        members_by_root.setdefault(uf.find(i), []).append(i)

    clusters: list[OriginCluster] = []
    canonical_of: dict[int, int] = {}      # member index -> canonical index
    cluster_id_of: dict[int, str] = {}     # member index -> origin_cluster_id

    for member_indices in members_by_root.values():
        member_indices = sorted(member_indices)
        # Canonical = earliest-dated origin (authority not consulted), or for an all-undated
        # cluster the LOWEST-authority member (conservative-min, no inflation — Codex #1161).
        canonical_index = min(
            member_indices, key=lambda idx: _order_key(rows[idx], idx)
        )
        # Stable, copy-immune id: derived from the canonical row's EVIDENCE IDENTITY, NOT its
        # input position — so a copy added BEFORE the canonical (prepended) does not shift the
        # index and change the id (Codex iter-2 P2). A missing evidence_id is a FAIL-LOUD data
        # error (Codex #1161), never a position-relative fallback.
        canonical_eid = str(rows[canonical_index].get("evidence_id", "") or "").strip()
        if not canonical_eid:
            raise ValueError(
                "independence_collapse: canonical row is missing 'evidence_id'; a stable "
                "origin_cluster_id requires every evidence row to carry evidence_id "
                "(Codex #1161 — a positional fallback id is not copy-stable)."
            )
        origin_cluster_id = f"origin::{canonical_eid}"
        copy_indices = [i for i in member_indices if i != canonical_index]
        member_hosts = sorted({domains[i] for i in member_indices} - {""})
        clusters.append(
            OriginCluster(
                origin_cluster_id=origin_cluster_id,
                canonical_index=canonical_index,
                member_indices=member_indices,
                copy_indices=copy_indices,
                member_hosts=member_hosts,
            )
        )
        for i in member_indices:
            canonical_of[i] = canonical_index
            cluster_id_of[i] = origin_cluster_id

    clusters.sort(key=lambda c: c.canonical_index)

    assignments = [
        RowOriginAssignment(
            row_index=i,
            origin_cluster_id=cluster_id_of[i],
            canonical_index=canonical_of[i],
            is_canonical_origin=(canonical_of[i] == i),
            is_derivative_copy=(canonical_of[i] != i),
        )
        for i in range(n)
    ]

    return IndependenceCollapseResult(
        clusters=clusters,
        assignments=assignments,
        raw_row_count=n,
        independent_origin_count=len(clusters),
        similarity_threshold=threshold,
    )
