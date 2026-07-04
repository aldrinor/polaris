"""T3 (I-deepfix-001 #1344) — Source-necessity min-vertex-cover (Hopcroft-Karp), NEW module.

DeepTRACE metric VI (Source Necessity). A report that LISTS many sources but whose factual claims
are all carried by a small load-bearing subset scores badly on #6: the listed references read as
padding. This module computes the necessity of each LISTED source FAITHFULLY — as the paper does —
by building the (statement, source) factual-support bipartite graph and computing its
**minimum vertex cover via Hopcroft-Karp maximum matching + König's construction**.

WHAT IT PRODUCES (all DISCLOSURE / render-structure — the faithfulness engine is UNTOUCHED):

  * ``necessity_ratio`` = necessary_sources / listed_sources (DeepTRACE #6), where a source is
    NECESSARY iff it is the SOLE supporter of at least one relevant, supported statement — the
    sources present in EVERY minimum vertex cover. This equals the sole-supporter reading used by
    the WS-14 benchmark scorer, so the number POLARIS discloses matches the number the benchmark
    measures.
  * ``min_vertex_cover`` — the actual minimum set of sources (+ statements) covering every support
    edge, via Hopcroft-Karp + König. Exposed for audit; every source in it is load-bearing.
  * ``zero_support`` — the listed sources that support NO relevant statement (genuine padding).

§-1.3 DNA — WEIGHT-and-CONSOLIDATE, never FILTER-and-DROP:

  * Necessity is computed over the support MATRIX, never the citation-layer render. Broad honest
    facet coverage (O1/F1) makes each source load-bearing for its OWN facet, so it lands in the
    min-cover — POLARIS raises #6 STRUCTURALLY, never by excluding honest corroborators.
  * A "redundant" (corroborated) source is KEPT at full weight — corroboration is the whole point
    of consolidate. This module NEVER drops it; it only reports the necessity split.
  * The ONE render move is QUARANTINE of ZERO-factual-support entries out of the LISTED reference
    set into a typed audit ledger: kept + disclosed, NEVER removed from the corpus. A zero-support
    source supports no statement, so it can never be a sole-supporter (necessary) — quarantining it
    can only RAISE the honest necessity ratio without touching any load-bearing source.

The faithfulness engine (strict_verify / NLI / 4-role D8 / provenance / span-grounding) runs
UPSTREAM and is not imported here. This module reads only the already-verified support structure.
PURE / offline. LAW VI kill-switch. snake_case.
"""
from __future__ import annotations

import os
import re
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

_QUARANTINE_ENV = "PG_SOURCE_NECESSITY_QUARANTINE"
_OFF_VALUES = frozenset({"", "0", "false", "off", "no"})

_LEDGER_HEADER = "## Source-necessity audit ledger (listed but non-load-bearing — not dropped)"
_BIB_ENTRY_LINE_RE = re.compile(r"^\[(\d+)\]\s")


def quarantine_enabled() -> bool:
    """T3 kill-switch. Default ON; OFF => no quarantine + no disclosure (byte-identical revert)."""
    return os.environ.get(_QUARANTINE_ENV, "1").strip().lower() not in _OFF_VALUES


# ─────────────────────────────────────────────────────────────────────────────
# Hopcroft-Karp maximum bipartite matching + König minimum vertex cover
# ─────────────────────────────────────────────────────────────────────────────
def hopcroft_karp_matching(
    adjacency: Mapping[Any, Sequence[Any]],
    left_nodes: Sequence[Any],
) -> dict[Any, Any]:
    """Maximum-cardinality matching of a bipartite graph via Hopcroft-Karp.

    ``adjacency`` maps each LEFT node to the RIGHT nodes it is joined to; ``left_nodes`` is the
    (deterministically ordered) left vertex set. Returns ``match_right`` mapping each MATCHED right
    node to its left partner. PURE — O(E * sqrt(V)). Deterministic for a fixed input ordering.
    """
    match_left: dict[Any, Any] = {}
    match_right: dict[Any, Any] = {}
    inf = float("inf")

    def bfs() -> bool:
        dist: dict[Any, float] = {}
        queue: deque = deque()
        for u in left_nodes:
            if u not in match_left:
                dist[u] = 0
                queue.append(u)
            else:
                dist[u] = inf
        found = False
        while queue:
            u = queue.popleft()
            for v in adjacency.get(u, ()):  # right neighbours
                w = match_right.get(v)  # left node currently matched to v (or None)
                if w is None:
                    found = True
                elif dist.get(w, inf) == inf:
                    dist[w] = dist[u] + 1
                    queue.append(w)
        return found

    def dfs(u: Any, dist: dict[Any, float]) -> bool:
        for v in adjacency.get(u, ()):
            w = match_right.get(v)
            if w is None or (dist.get(w, float("inf")) == dist[u] + 1 and dfs(w, dist)):
                match_left[u] = v
                match_right[v] = u
                return True
        dist[u] = float("inf")
        return False

    # Hopcroft-Karp phases: recompute layered distances, then augment along shortest paths.
    while True:
        dist: dict[Any, float] = {}
        queue = deque()
        for u in left_nodes:
            if u not in match_left:
                dist[u] = 0
                queue.append(u)
            else:
                dist[u] = inf
        reached_free = False
        while queue:
            u = queue.popleft()
            for v in adjacency.get(u, ()):
                w = match_right.get(v)
                if w is None:
                    reached_free = True
                elif dist.get(w, inf) == inf:
                    dist[w] = dist[u] + 1
                    queue.append(w)
        if not reached_free:
            break
        for u in left_nodes:
            if u not in match_left:
                dfs(u, dist)
    return dict(match_right)


def min_vertex_cover(
    left_nodes: Sequence[Any],
    right_nodes: Sequence[Any],
    adjacency: Mapping[Any, Sequence[Any]],
) -> tuple[set[Any], set[Any]]:
    """Minimum vertex cover of a bipartite graph (König's theorem construction).

    Returns ``(cover_left, cover_right)``. |cover| == size of the maximum matching. Every support
    edge has an endpoint in the cover. PURE / deterministic. Used to expose the exact load-bearing
    source set; sole-supporter sources are a subset of ``cover_right`` (they are forced).
    """
    left_nodes = list(left_nodes)
    right_nodes = list(right_nodes)
    match_right = hopcroft_karp_matching(adjacency, left_nodes)
    matched_left = set(match_right.values())

    # König: start Z from unmatched LEFT nodes; alternate NOT-in-matching (L->R) and
    # in-matching (R->L) edges. Min cover = (L \ Z) ∪ (R ∩ Z).
    match_left = {v: u for u, v in match_right.items()}  # left -> right
    visited_left: set[Any] = set()
    visited_right: set[Any] = set()
    stack: list[Any] = [u for u in left_nodes if u not in matched_left]
    for u in stack:
        visited_left.add(u)
    work = deque(stack)
    while work:
        u = work.popleft()
        for v in adjacency.get(u, ()):
            # traverse only NON-matching edges L->R
            if match_left.get(u) == v:
                continue
            if v not in visited_right:
                visited_right.add(v)
                w = match_right.get(v)  # its matched left partner
                if w is not None and w not in visited_left:
                    visited_left.add(w)
                    work.append(w)
    cover_left = {u for u in left_nodes if u not in visited_left}
    cover_right = {v for v in right_nodes if v in visited_right}
    return cover_left, cover_right


# ─────────────────────────────────────────────────────────────────────────────
# Source-necessity over the LISTED-source support graph
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class SourceNecessity:
    """The necessity split over the listed-source support graph. All fields are DISCLOSURE."""

    listed_sources: int
    necessary_sources: int
    necessity_ratio: float
    necessary_ids: tuple = field(default_factory=tuple)   # sole-supporter (forced) source ids
    redundant_ids: tuple = field(default_factory=tuple)   # supporting but corroborated (kept)
    zero_support_ids: tuple = field(default_factory=tuple)  # support no statement (quarantine target)
    min_cover_size: int = 0


def compute_source_necessity(
    support_by_source: Mapping[Any, Sequence[Any]],
    listed_sources: Sequence[Any],
) -> SourceNecessity:
    """Compute DeepTRACE #6 source-necessity over the LISTED-source universe.

    ``support_by_source`` maps a source id -> the statement ids whose OWN isolated span it SUPPORTS
    (the same span-verified members counted in ``verified_support_origin_count``; never the advisory
    clustered count). ``listed_sources`` is the full listed reference set (the same universe #8
    thoroughness uses). A source absent from ``support_by_source`` (or mapped to []) supports no
    statement -> ``zero_support``. A source that is the SOLE supporter of >=1 statement is
    NECESSARY (present in every minimum vertex cover). Everything else that supports >=1 statement
    is REDUNDANT (corroborated — KEPT at full weight, never dropped).

    PURE. Never mutates inputs. Faithfulness-neutral (reads already-verified support only).
    """
    listed = [str(s) for s in listed_sources]
    listed_set = set(listed)
    n = len(listed)

    # Build statement -> supporting listed sources (bounded to the listed universe).
    supporters_by_statement: dict[Any, set[str]] = {}
    supported_listed: set[str] = set()
    for src, stmts in (support_by_source or {}).items():
        sid = str(src)
        if sid not in listed_set:
            continue
        for st in stmts or ():
            supporters_by_statement.setdefault(str(st), set()).add(sid)
            supported_listed.add(sid)

    # Sole-supporter (necessary) sources = present in EVERY minimum cover.
    necessary: set[str] = set()
    for _st, sups in supporters_by_statement.items():
        if len(sups) == 1:
            necessary.add(next(iter(sups)))

    zero_support = sorted(listed_set - supported_listed)
    redundant = sorted(supported_listed - necessary)

    # Faithful minimum vertex cover via Hopcroft-Karp + König over the support edges (audit).
    statement_ids = list(supporters_by_statement.keys())
    adjacency: dict[Any, list[str]] = {}
    for st, sups in supporters_by_statement.items():
        adjacency[("stmt", st)] = [("src", s) for s in sorted(sups)]
    left = [("stmt", st) for st in statement_ids]
    right = [("src", s) for s in sorted(supported_listed)]
    cover_left, cover_right = min_vertex_cover(left, right, adjacency)
    min_cover_size = len(cover_left) + len(cover_right)

    ratio = (len(necessary) / n) if n else 0.0
    return SourceNecessity(
        listed_sources=n,
        necessary_sources=len(necessary),
        necessity_ratio=round(ratio, 4),
        necessary_ids=tuple(sorted(necessary)),
        redundant_ids=tuple(redundant),
        zero_support_ids=tuple(zero_support),
        min_cover_size=min_cover_size,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Render transform: quarantine zero-support cited entries + disclose necessity
# ─────────────────────────────────────────────────────────────────────────────
def _necessity_disclosure_line(necessity: SourceNecessity) -> str:
    return (
        "_Source necessity (DeepTRACE metric VI, minimum-vertex-cover reading): "
        f"{necessity.necessary_sources} of {necessity.listed_sources} listed references are "
        "NECESSARY (each is the sole supporter of at least one report claim); necessity ratio "
        f"{necessity.necessity_ratio:.4f}. Non-load-bearing listed entries are moved to the audit "
        "ledger below — kept and disclosed, never dropped from the corpus (WEIGHT-and-CONSOLIDATE)._"
    )


def retype_bibliography_by_source_necessity(
    biblio_section_text: str,
    zero_support_nums: set[int],
    necessity: SourceNecessity,
) -> str:
    """Move zero-factual-support cited entry lines out of "## Bibliography" into a typed
    source-necessity audit ledger, and append the necessity disclosure. PURE string surgery.

    An entry line (``^[N] ...``) whose N is in ``zero_support_nums`` moves VERBATIM under the
    ledger header; every other line stays. Nothing is re-rendered, invented, or deleted — a
    quarantined source still ships in report.md, typed as a non-load-bearing audit row. Returns the
    input UNCHANGED when there is nothing to quarantine (byte-identical) so the caller can no-op.
    """
    if not biblio_section_text:
        return biblio_section_text
    if not zero_support_nums:
        # Still surface the necessity number when there ARE listed sources; but keep byte-identity
        # when the disclosure would be vacuous (no listed sources).
        if necessity.listed_sources <= 0:
            return biblio_section_text
    lines = biblio_section_text.split("\n")
    kept: list[str] = []
    ledger: list[str] = []
    for line in lines:
        m = _BIB_ENTRY_LINE_RE.match(line)
        if m and int(m.group(1)) in zero_support_nums:
            ledger.append(line)
        else:
            kept.append(line)
    kept_block = "\n".join(kept).rstrip()
    disclosure = _necessity_disclosure_line(necessity)
    if not ledger:
        # No quarantine, but disclose the necessity number inline (kept references only).
        return kept_block + "\n\n" + disclosure + "\n"
    ledger_block = "\n".join(ledger).strip()
    return (
        kept_block
        + "\n\n"
        + disclosure
        + "\n\n"
        + _LEDGER_HEADER
        + "\n\n"
        + "_These listed sources support no report claim under isolated span verification. They are "
        "disclosed here for audit completeness and remain in the corpus at full weight; they are not "
        "part of the load-bearing cited reference set._\n\n"
        + ledger_block
        + "\n"
    )


def zero_support_bib_nums(
    support_by_num: Mapping[int, Sequence[Any]],
    cited_nums: Sequence[int],
) -> set[int]:
    """The cited bibliography numbers that support NO statement (quarantine targets). PURE.

    ``support_by_num`` maps a bibliography number -> the statement ids it span-verified SUPPORTS.
    ``cited_nums`` is the set of numbers actually cited in the body. A cited number with an empty
    (or missing) support list is zero-support. Only CITED numbers are eligible (an uncited row is
    already handled by the T2 corpus-ledger typing)."""
    cited = {int(n) for n in cited_nums}
    out: set[int] = set()
    for n in cited:
        stmts = support_by_num.get(n)
        if not stmts:
            out.add(n)
    return out
