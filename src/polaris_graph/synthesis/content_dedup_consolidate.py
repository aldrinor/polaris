"""I-deepfix-001 (#1344) W9 — content-dedup CONSOLIDATE-KEEP-ALL (body-syndication baskets).

The W9 winner is dedup=ContentDeduplicator. Its native ``deduplicate()`` returns
``unique_items`` — a DROP that sheds corroborators, which VIOLATES §-1.3 (the pipeline
is WEIGHT-and-CONSOLIDATE, never FILTER-and-DROP). So W9 is wired here in the ONLY
§-1.3-legal form: ContentDeduplicator's body-MinHash CLUSTERS are used to GROUP
near-identical-body sources into a corroboration BASKET, and EVERY row is kept.
Nothing is dropped; nothing is merged.

WHAT IT ADDS over the existing finding_dedup same-work consolidation (#7, which keys
on DOI / folded title): finding_dedup catches the SAME work cited under the same
identity. It MISSES different-title near-identical-BODY syndication — the same report
republished at two URLs with different titles and no shared DOI. That is exactly what
ContentDeduplicator's body-MinHash catches. Here it is surfaced as a keep-all
corroboration WEIGHT, never a drop.

FAITHFULNESS POSTURE (the load-bearing safety argument — VERIFY it):
  * KEEP-ALL: every input row is returned, unchanged except for additive annotation
    keys. No row is removed; the output list has the SAME length as the input.
  * MERGE-NOTHING: unlike finding_dedup this NEVER collapses two findings into one
    representative. It only ATTACHES "these N rows share a near-identical body" to
    each member. So it cannot over-merge two distinct clinical findings — the
    clinical-lethal over-merge risk finding_dedup's conservative key guards against is
    not in play here, because no claim is ever dropped, rewritten, or merged.
  * NEAR-IDENTICAL ONLY: grouping fires only at the EXACT/NEAR_DUPLICATE tier
    (MinHash similarity >= ``PG_W9_BODY_SIM``, default 0.85). The loose SIMILAR tier
    (0.70-0.85) is DELIBERATELY excluded (we pin ``similar_threshold`` up to the
    near-dup floor) so merely-topical sources are NOT grouped — only true syndication.
  * GROUNDING-UNTOUCHED: the annotation is metadata. It never changes which rows
    ground prose, never feeds or relaxes strict_verify / NLI / 4-role / span-grounding.
    A corroboration count is a disclosure WEIGHT, not a gate.

Pure leaf: no network, no model, no LLM. Reuses ``src.utils.content_deduplicator``
(MinHash/SimHash, pure python, bounded O(n^2) over the corpus). Env kill-switch
(LAW VI). DEFAULT ON. ROW-level byte-identical when no two rows share a near-identical
body (no multi-member cluster => no row gains an annotation key); the stage still emits
a zeroed telemetry dict + one canary log line as the observability signal (it does NOT
claim an empty/absent result object).
"""
from __future__ import annotations

import logging
import os
from typing import Any

from src.utils.content_deduplicator import (
    ContentDeduplicator,
    DeduplicationConfig,
)

logger = logging.getLogger("polaris_graph.content_dedup_consolidate")

_ENV_FLAG = "PG_CONTENT_DEDUP_CONSOLIDATE"
_OFF_VALUES = frozenset({"0", "false", "no", "off", "disabled", ""})

# MinHash similarity floor for "near-identical body" (LAW VI). The SIMILAR tier is
# pinned UP to this floor so only EXACT + NEAR_DUPLICATE group — never merely-topical.
_ENV_SIM = "PG_W9_BODY_SIM"
_DEFAULT_SIM = 0.85

# A body shorter than this is too small to call "syndication" reliably (MinHash on a
# tiny snippet is noisy). Such rows stay SINGLETONS (kept, never annotated, never
# dropped). LAW VI.
_ENV_MIN_BODY_CHARS = "PG_W9_MIN_BODY_CHARS"
_DEFAULT_MIN_BODY_CHARS = 200


def consolidate_enabled() -> bool:
    """Kill-switch. DEFAULT ON. Set ``PG_CONTENT_DEDUP_CONSOLIDATE`` to a falsey value
    to disable — rows are then returned unannotated (byte-identical)."""
    return os.getenv(_ENV_FLAG, "1").strip().lower() not in _OFF_VALUES


def _sim() -> float:
    raw = os.getenv(_ENV_SIM, "").strip()
    if not raw:
        return _DEFAULT_SIM
    try:
        return min(max(float(raw), 0.0), 1.0)
    except ValueError:
        return _DEFAULT_SIM


def _min_body_chars() -> int:
    try:
        return max(0, int(os.getenv(_ENV_MIN_BODY_CHARS, str(_DEFAULT_MIN_BODY_CHARS))))
    except (TypeError, ValueError):
        return _DEFAULT_MIN_BODY_CHARS


def _dedup_text(row: dict[str, Any]) -> str:
    """The body text W9 compares: direct_quote, then statement, then title. NOT the
    empty 'content' key (which is absent on Gate-B rows — comparing it would fold every
    source into ONE cluster, the false-green the workflow draft hit)."""
    return str(
        row.get("direct_quote")
        or row.get("statement")
        or row.get("title")
        or row.get("source_title")
        or ""
    ).strip()


class _UnionFind:
    def __init__(self, n: int) -> None:
        self._parent = list(range(n))

    def find(self, x: int) -> int:
        root = x
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[x] != root:  # path compression
            self._parent[x], x = root, self._parent[x]
        return root

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[max(ra, rb)] = min(ra, rb)


def consolidate_body_syndication(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Annotate near-identical-body sources into KEEP-ALL corroboration baskets.

    Returns ``(rows, telemetry)``. ``rows`` is the SAME list object, with each member
    of a multi-row body-syndication basket gaining three additive keys:
    ``body_syndication_cluster_id`` (stable, derived from the basket's smallest
    evidence_id), ``body_syndication_count`` (basket size >= 2), and
    ``body_syndication_ev_ids`` (the sorted basket of evidence_ids). Singletons and
    short-body rows are untouched. The list NEVER shrinks and no two rows are merged.

    ``telemetry`` reports ``rows_in`` / ``eligible`` / ``baskets`` / ``rows_grouped`` /
    ``rows_dropped`` (always 0) so the stage is OBSERVABLE in the run artifacts.
    """
    n_total = len(rows)
    telemetry: dict[str, Any] = {
        "rows_in": n_total,
        "eligible": 0,
        "baskets": 0,
        "rows_grouped": 0,
        "rows_dropped": 0,
        "enabled": consolidate_enabled(),
    }
    if not consolidate_enabled() or n_total < 2:
        return rows, telemetry

    min_chars = _min_body_chars()
    # Eligible rows: a non-trivial body. Build the items the deduplicator scores, and a
    # back-map item_index -> original row index. Short/empty-body rows stay singletons.
    items: list[dict[str, Any]] = []
    positions: list[int] = []
    for idx, row in enumerate(rows):
        text = _dedup_text(row)
        if len(text) >= min_chars:
            items.append({"_w9_text": text})
            positions.append(idx)
    telemetry["eligible"] = len(items)
    if len(items) < 2:
        logger.info(
            "[content_dedup_consolidate] W9: %d rows, %d eligible (>=%d chars) -> "
            "0 baskets, 0 dropped (KEEP-ALL)",
            n_total, len(items), min_chars,
        )
        return rows, telemetry

    # Pin similar_threshold UP to the near-dup floor so ONLY exact + near-identical
    # bodies are flagged duplicates (the loose SIMILAR tier never fires) — no topical
    # over-grouping, and no row is prematurely claimed by a loose match.
    sim = _sim()
    cfg = DeduplicationConfig(
        exact_match_threshold=1.0,
        near_duplicate_threshold=sim,
        similar_threshold=sim,
    )
    try:
        result = ContentDeduplicator(cfg).deduplicate(items, content_key="_w9_text")
    except Exception as exc:  # noqa: BLE001 — a dedup bug must NEVER drop/merge a row
        logger.warning(
            "[content_dedup_consolidate] W9 dedup errored (%s) — returning rows "
            "UNANNOTATED (no drop, no merge on a bug).", str(exc)[:160],
        )
        return rows, telemetry

    # Union the near-identical edges over the ELIGIBLE-item index space, then translate
    # the multi-member components back to ORIGINAL row indices. Every edge here is
    # EXACT/NEAR (>= sim) by construction of cfg, so no SIMILAR-tier edge sneaks in.
    uf = _UnionFind(len(items))
    for dup in result.duplicates:
        uf.union(dup.original_index, dup.duplicate_index)
    groups: dict[int, list[int]] = {}
    for item_idx in range(len(items)):
        groups.setdefault(uf.find(item_idx), []).append(item_idx)

    baskets = 0
    rows_grouped = 0
    for members in groups.values():
        if len(members) < 2:
            continue
        orig_idx = [positions[m] for m in members]
        ev_ids = sorted(str(rows[o].get("evidence_id", "")) for o in orig_idx)
        cluster_id = "bsyn_" + (next((e for e in ev_ids if e), str(orig_idx[0])))
        for o in orig_idx:
            rows[o]["body_syndication_cluster_id"] = cluster_id
            rows[o]["body_syndication_count"] = len(orig_idx)
            rows[o]["body_syndication_ev_ids"] = ev_ids
        baskets += 1
        rows_grouped += len(orig_idx)

    telemetry["baskets"] = baskets
    telemetry["rows_grouped"] = rows_grouped
    # Firing canary: present on every Gate-B run that reaches this stage; its counts
    # make W9 OBSERVABLE (vs. the prior build-deferred ABSENCE). KEEP-ALL invariant
    # asserted in the message: 0 dropped, list length unchanged.
    logger.info(
        "[content_dedup_consolidate] W9: %d rows (%d eligible) -> %d body-syndication "
        "basket(s), %d rows grouped, 0 dropped (KEEP-ALL, sim>=%.2f)",
        n_total, len(items), baskets, rows_grouped, sim,
    )
    return rows, telemetry
