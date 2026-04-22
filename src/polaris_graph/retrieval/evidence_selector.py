"""
Evidence selector — BUG-M-201 fix (deep-dive R6).

Pre-fix, `run_one_query` passed `retrieval.evidence_rows[:PG_LIVE_MAX_EV_TO_GEN]`
to the generator — raw retrieval order with no tier awareness. Gates
reasoned over the full pool; generation reasoned over a smaller,
order-biased subset. Real artifacts showed 20 corpus sources but
only 4 evidence rows surviving to generation.

Post-fix, `select_evidence_for_generation()` produces a deterministic,
tier-balanced, relevance-ranked subset. The result is emitted to
`manifest.json.evidence_selection` so downstream consumers can see
exactly what the generator saw.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# Tier priority for within-pool ranking. Lower tier number = higher priority.
_TIER_PRIORITY: dict[str, int] = {
    "T1": 1, "T2": 2, "T3": 3, "T4": 4,
    "T5": 5, "T6": 6, "T7": 7, "UNKNOWN": 8,
}

_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were",
    "of", "in", "on", "at", "to", "for", "with", "by", "from", "as",
    "that", "this", "these", "those", "it", "its", "be", "been",
    "what", "which", "who", "how", "why", "when", "where",
})


def _content_tokens(text: str) -> set[str]:
    """Lowercase content-word tokens, stopword-filtered, 3+ chars."""
    toks = re.findall(r"[A-Za-z][A-Za-z\-]{2,}", text.lower())
    return {t for t in toks if t not in _STOPWORDS}


@dataclass
class EvidenceSelection:
    """Result of select_evidence_for_generation."""
    selected_rows: list[dict[str, Any]]
    full_counts: dict[str, int]        # tier -> count in FULL pool
    selected_counts: dict[str, int]    # tier -> count in SELECTED subset
    dropped_count: int
    selection_strategy: str            # stable identifier for telemetry
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_total": (
                sum(self.full_counts.values())
            ),
            "evidence_selected": len(self.selected_rows),
            "selection_strategy": self.selection_strategy,
            "full_tier_counts": dict(self.full_counts),
            "selected_tier_counts": dict(self.selected_counts),
            "dropped_count": self.dropped_count,
            "notes": list(self.notes),
        }


def _row_tier(row: dict[str, Any], url_to_tier: dict[str, str]) -> str:
    """Resolve tier for an evidence row via URL join to classified sources.
    Falls back to row's own `tier` field, then UNKNOWN."""
    url = row.get("source_url") or row.get("url") or ""
    if url in url_to_tier:
        return url_to_tier[url]
    tier = row.get("tier") or "UNKNOWN"
    return str(tier)


# M-41d (2026-04-21): jurisdictional-diversity floor for T3 regulatory
# selection. V24 had 0 Health Canada entries in its bibliography
# despite 7 HC rows in the corpus (M-37 shipped the tier fix and the
# prompt rule, but the evidence selector tier-quota gave T3 only 12
# slots that all went to FDA/EMA/NICE since they scored higher on
# lexical relevance than a Canadian monograph). M-41d adds a floor:
# within the T3 quota, reserve one slot for each present jurisdiction
# whose evidence appears in the pool.
#
# Jurisdiction detection is by URL host suffix. A row maps to exactly
# one jurisdiction or None. No drug-specific tokens; the host list
# mirrors the regulatory_anchors template schema across domains.
_M41D_JURISDICTION_HOSTS: list[tuple[str, tuple[str, ...]]] = [
    # M-41d pass-2 (Codex audit medium #3): removed bare "europa.eu"
    # from EMA — it was too broad (collapsed any EU-domain source
    # into EMA). Kept "ema.europa.eu" which is the specific EMA
    # documents host.
    ("FDA",  ("fda.gov",)),
    ("EMA",  ("ema.europa.eu",)),
    ("NICE", ("nice.org.uk",)),
    ("MHRA", ("mhra.gov.uk",)),
    ("HC",   ("canada.ca", "hres.ca", "hc-sc.gc.ca", "cda-amc.ca")),
    ("TGA",  ("tga.gov.au",)),
    ("PMDA", ("pmda.go.jp",)),
    ("WHO",  ("who.int",)),
    ("NMPA", ("nmpa.gov.cn",)),
]


def _row_jurisdiction(row: dict[str, Any]) -> str | None:
    """Return the regulatory jurisdiction code a row belongs to, or
    None if the URL is not from a recognized regulatory host.

    M-41d pass-2 (Codex audit medium #3): uses proper host-suffix
    matching instead of substring `in`. Pre-pass-2 `h in url` would
    classify `https://not-fda.gov.example/path` as FDA because the
    literal string `fda.gov` appears in the path. Now we extract the
    actual host component from the URL and require it to either
    equal one of the listed hosts or end with `.{host}` (proper
    subdomain). Plain substring-in-path no longer matches.
    """
    url = (row.get("source_url") or row.get("url") or "").lower()
    if not url:
        return None
    # Extract host: scheme://host/path → host. Be permissive about
    # missing schemes; in that case treat the first path segment as
    # host if it looks like a hostname.
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url if "://" in url else f"http://{url}")
        host = (parsed.hostname or "").lower()
    except (ValueError, AttributeError):
        return None
    if not host:
        return None
    for code, hosts in _M41D_JURISDICTION_HOSTS:
        for h in hosts:
            # Proper suffix match: host == h OR host ends with ".h".
            if host == h or host.endswith("." + h):
                return code
    return None


# M-42e (2026-04-22): named-trial primary-paper floor for T1 tier.
# V25 had SURPASS-2 NEJM cited but missed SURPASS-1 Rosenstock,
# SURPASS-3 Ludvik, SURMOUNT-1 Jastreboff as first-class biblio
# entries even though M-35 anchor queries surfaced them into the
# corpus. The tier-balanced selector gave T1 proportional slots
# allocated by relevance, letting meta-analyses and review papers
# outscore primary trials on lexical relevance.
#
# M-42e adds a T1 named-trial-primary floor: for each anchor trial
# configured in `per_query_primary_trial_anchors`, if the T1 pool
# contains a matching primary paper (title regex), reserve 1 slot
# before filling T1 by relevance. Capped at 6 (prevents displacing
# T2 meta-analysis allocation below V25 baseline).
_M42E_PRIMARY_FLOOR_CAP = 6

# Known primary-publication DOI prefixes (NEJM, Lancet, JAMA,
# Diabetes Care, Nat Med). Used alongside title regex to detect
# primary-trial rows in T1 pool.
_M42E_PRIMARY_DOI_PREFIXES = (
    "10.1056/nejm",    # NEJM
    "10.1016/s0140-6736",  # Lancet
    "10.1016/s2213-8587",  # Lancet Diabetes & Endocrinology
    "10.1001/jama",    # JAMA
    "10.2337/dc",      # Diabetes Care
    "10.1038/s41591",  # Nat Med
    "10.1016/s2468-1253",  # Lancet Gastro
    "10.1038/s41586",  # Nature
)


def _m42e_detect_primary_for_anchor(
    row: dict[str, Any],
    anchor: str,
) -> bool:
    """True if `row` appears to be the primary publication for the
    named-trial `anchor` (e.g. 'SURPASS-2', 'SURMOUNT-1').

    Detection: anchor appears in row title AND row URL/DOI matches
    a known primary-publication prefix. Both conditions required to
    prevent tagging post-hoc analyses / substudies / abstracts as
    primaries.
    """
    if not anchor:
        return False
    title = (row.get("title") or "").lower()
    url = (row.get("source_url") or row.get("url") or "").lower()
    anchor_l = anchor.lower()
    # Title must contain the anchor (possibly with colon or
    # parenthesis separator).
    if anchor_l not in title:
        return False
    # URL must look like a primary publication — DOI prefix OR
    # host suggesting peer-reviewed journal.
    if any(p in url for p in _M42E_PRIMARY_DOI_PREFIXES):
        return True
    # Fallback: nejm.org, thelancet.com, jamanetwork.com, nature.com
    primary_hosts = (
        "nejm.org", "thelancet.com", "jamanetwork.com",
        "nature.com", "diabetesjournals.org",
    )
    for h in primary_hosts:
        if h in url:
            return True
    return False


def _row_relevance(
    row: dict[str, Any],
    question_tokens: set[str],
    protocol_tokens: set[str],
) -> float:
    """Deterministic lexical relevance score in [0, 1].

    Overlap between the union of question+protocol tokens and the
    evidence's statement+direct_quote content tokens. Jaccard-ish but
    normalized by the question side so longer evidence doesn't dominate.
    """
    text = " ".join(str(row.get(k, "") or "") for k in ("statement", "direct_quote"))
    ev_toks = _content_tokens(text)
    anchors = question_tokens | protocol_tokens
    if not anchors:
        return 0.0
    overlap = ev_toks & anchors
    return len(overlap) / max(1, len(anchors))


def select_evidence_for_generation(
    *,
    research_question: str,
    protocol: dict[str, Any] | None,
    classified_sources: list[Any],
    evidence_rows: list[dict[str, Any]],
    max_rows: int,
    primary_trial_anchors: list[str] | None = None,
) -> EvidenceSelection:
    """Pick up to max_rows evidence rows, tier-balanced + relevance-ranked.

    Strategy (deterministic, stable):
      1. Join evidence rows to classified sources by URL → tier per row.
      2. Compute full_tier_counts.
      3. Score each row by lexical relevance (question+protocol anchors
         vs statement+direct_quote content words).
      4. Sort within each tier by (-relevance, original_index) for
         deterministic top-N per tier.
      5. Allocate slots proportionally to full_tier_counts but with
         floors for high-value tiers that are present (each T1-T3 tier
         present gets at least min(1, available)).
      6. Fill remaining slots globally by (tier_priority, -relevance,
         original_index).

    Args:
        research_question: the user's raw question.
        protocol: scope protocol dict (uses population/intervention/
            comparator/outcome/research_question if present).
        classified_sources: list of objects with .url and .tier (or
            dict-like with those keys). Used for URL→tier join.
        evidence_rows: full evidence row pool.
        max_rows: target selection size.

    Returns:
        EvidenceSelection with selected_rows + telemetry.
    """
    if max_rows <= 0 or not evidence_rows:
        return EvidenceSelection(
            selected_rows=[], full_counts={}, selected_counts={},
            dropped_count=0, selection_strategy="tier_balanced_v1",
            notes=["no evidence rows or max_rows <= 0"],
        )

    # Build URL → tier map from classified_sources (whatever shape).
    url_to_tier: dict[str, str] = {}
    for src in classified_sources or []:
        url = getattr(src, "url", None) or (
            src.get("url") if isinstance(src, dict) else None
        )
        tier = getattr(src, "tier", None) or (
            src.get("tier") if isinstance(src, dict) else None
        )
        if url and tier:
            url_to_tier[str(url)] = str(tier)

    # Compute relevance tokens from research question + protocol anchors.
    question_tokens = _content_tokens(research_question or "")
    protocol_tokens: set[str] = set()
    if protocol:
        for key in ("population", "intervention", "comparator",
                    "outcome", "research_question"):
            v = protocol.get(key)
            if v:
                protocol_tokens |= _content_tokens(str(v))

    # Score every row and tag with tier + original index.
    scored: list[tuple[int, float, str, dict[str, Any]]] = []
    for idx, row in enumerate(evidence_rows):
        tier = _row_tier(row, url_to_tier)
        score = _row_relevance(row, question_tokens, protocol_tokens)
        scored.append((idx, score, tier, row))

    # Full tier counts (FROM evidence_rows, the selectable universe).
    full_counts: dict[str, int] = {}
    for _, _, tier, _ in scored:
        full_counts[tier] = full_counts.get(tier, 0) + 1

    # Early exit: if total <= max_rows, keep everything (but still emit
    # telemetry so the manifest is consistent).
    if len(scored) <= max_rows:
        selected_counts = dict(full_counts)
        return EvidenceSelection(
            selected_rows=list(evidence_rows),
            full_counts=full_counts,
            selected_counts=selected_counts,
            dropped_count=0,
            selection_strategy="tier_balanced_v1_all",
            notes=[f"pool_size<=max_rows ({len(scored)}/{max_rows})"],
        )

    # Floors: reserve at least 1 slot for each present T1, T2, T3
    # (high-value tiers) if pool has any.
    present_hv = [t for t in ("T1", "T2", "T3") if full_counts.get(t, 0) > 0]

    # Proportional allocation.
    quotas: dict[str, int] = {}
    allocated = 0
    # First pass: proportional (round down).
    for tier, n in full_counts.items():
        share = int(round(max_rows * n / len(scored)))
        quotas[tier] = share
        allocated += share

    # Enforce floors for high-value tiers present.
    for tier in present_hv:
        if quotas.get(tier, 0) < 1:
            delta = 1 - quotas.get(tier, 0)
            quotas[tier] = quotas.get(tier, 0) + delta
            allocated += delta

    # Cap: can't give a tier more than it has.
    for tier in list(quotas.keys()):
        quotas[tier] = min(quotas[tier], full_counts[tier])

    # Rebalance: while allocated != max_rows, adjust.
    allocated = sum(quotas.values())
    # If over-allocated: deduct from lowest-priority tiers first.
    # BUG-N-302 fix (pass 2 remediation): if max_rows is smaller than
    # the number of present high-value floors, the old code refused
    # to deduct below floors and overshot max_rows. Now we prefer
    # floors but WILL violate them if necessary to hit max_rows.
    while allocated > max_rows:
        lowest = max(
            (t for t, q in quotas.items() if q > 0),
            key=lambda t: (_TIER_PRIORITY.get(t, 9), t),
        )
        # Prefer deducting from non-floor tiers first.
        if lowest in present_hv and quotas[lowest] <= 1:
            # try next-lowest among non-floored
            candidates = [
                t for t, q in quotas.items() if q > 0
                and not (t in present_hv and q <= 1)
            ]
            if candidates:
                lowest = max(candidates, key=lambda t: (_TIER_PRIORITY.get(t, 9), t))
            # else: fall through and deduct the floor anyway —
            # honoring max_rows is a hard contract; the floor is a soft
            # preference. Only way this happens is max_rows < floor count.
        quotas[lowest] -= 1
        allocated -= 1
    # If under-allocated: add to highest-priority tiers with remaining capacity.
    while allocated < max_rows:
        candidates = [
            t for t, q in quotas.items()
            if q < full_counts.get(t, 0)
        ]
        if not candidates:
            break
        best = min(candidates, key=lambda t: (_TIER_PRIORITY.get(t, 9), t))
        quotas[best] += 1
        allocated += 1

    # Now pick within each tier by (-score, original_idx).
    by_tier: dict[str, list[tuple[int, float, str, dict[str, Any]]]] = {}
    for item in scored:
        by_tier.setdefault(item[2], []).append(item)
    for tier in by_tier:
        by_tier[tier].sort(key=lambda x: (-x[1], x[0]))

    # M-42e (2026-04-22): T1 named-trial primary floor. Compute
    # anchor-matched primary rows once so we can reserve their
    # slots before the T1 pick-by-relevance pass. Capped at
    # `_M42E_PRIMARY_FLOOR_CAP` to avoid displacing T2 allocation.
    m42e_primary_ids: set[int] = set()
    if primary_trial_anchors and quotas.get("T1", 0) > 0:
        t1_items_for_m42e = by_tier.get("T1", [])
        for anchor in primary_trial_anchors:
            if len(m42e_primary_ids) >= _M42E_PRIMARY_FLOOR_CAP:
                break
            # Find the highest-scoring T1 row matching this anchor
            for item in t1_items_for_m42e:
                if id(item) in m42e_primary_ids:
                    continue
                if _m42e_detect_primary_for_anchor(item[3], anchor):
                    m42e_primary_ids.add(id(item))
                    break
        # Preservation guard: don't expand T1 usage beyond its
        # quota. The floor operates WITHIN the T1 quota — if
        # T1 quota is 8 and 6 anchor-matched primaries exist, all
        # 6 primaries + 2 top-scored rows fill the T1 quota.
        # If primary_count > T1 quota, cap reservations at quota.
        if len(m42e_primary_ids) > quotas.get("T1", 0):
            # Reduce reservations to match quota — keep highest-scored
            # primaries.
            t1_items_by_score = sorted(
                [i for i in t1_items_for_m42e if id(i) in m42e_primary_ids],
                key=lambda x: (-x[1], x[0]),
            )
            m42e_primary_ids = set(
                id(i) for i in t1_items_by_score[:quotas.get("T1", 0)]
            )

    selected: list[tuple[int, float, str, dict[str, Any]]] = []
    for tier, quota in quotas.items():
        # M-42e: for T1 tier, reserve named-trial primary slots
        # (computed above) before filling rest by relevance.
        if tier == "T1" and quota > 0 and m42e_primary_ids:
            tier_items = by_tier.get("T1", [])
            reserved_t1 = [
                i for i in tier_items if id(i) in m42e_primary_ids
            ][:quota]
            slots_left = quota - len(reserved_t1)
            # Fill remaining T1 slots by relevance (skipping reserved)
            for item in tier_items:
                if slots_left <= 0:
                    break
                if id(item) not in m42e_primary_ids:
                    reserved_t1.append(item)
                    slots_left -= 1
            selected.extend(reserved_t1)
            continue
        # M-41d: for T3 (regulatory) tier, enforce a
        # jurisdictional-diversity floor — reserve one slot per
        # present jurisdiction (FDA, EMA, NICE, HC, ...) before
        # filling the rest of the T3 quota by relevance. Prevents the
        # V24 failure mode where Health Canada evidence was in the
        # corpus but outcompeted within T3 by higher-scoring FDA/EMA.
        tier_items = by_tier.get(tier, [])
        if tier == "T3" and quota > 0 and tier_items:
            # Group T3 items by jurisdiction.
            juris_groups: dict[str | None, list[tuple[int, float, str, dict[str, Any]]]] = {}
            for item in tier_items:
                jur = _row_jurisdiction(item[3])
                juris_groups.setdefault(jur, []).append(item)
            present_juris = [j for j in juris_groups if j is not None]
            # Reserve 1 slot per present jurisdiction (capped at the
            # T3 quota — we never over-fill). Pick the top-scoring
            # row per jurisdiction as the reserved slot.
            reserved: list[tuple[int, float, str, dict[str, Any]]] = []
            reserved_ids: set[int] = set()
            slots_left = quota
            for jur in present_juris:
                if slots_left <= 0:
                    break
                for item in juris_groups[jur]:
                    if id(item) not in reserved_ids:
                        reserved.append(item)
                        reserved_ids.add(id(item))
                        slots_left -= 1
                        break
            # Fill remaining slots from the tier's global score order,
            # skipping already-reserved items.
            for item in tier_items:
                if slots_left <= 0:
                    break
                if id(item) not in reserved_ids:
                    reserved.append(item)
                    reserved_ids.add(id(item))
                    slots_left -= 1
            selected.extend(reserved)
        else:
            selected.extend(tier_items[:quota])

    # Sort final selection by (tier_priority, -score, original_idx) for
    # deterministic output order.
    selected.sort(key=lambda x: (_TIER_PRIORITY.get(x[2], 9), -x[1], x[0]))

    selected_rows = [item[3] for item in selected]
    selected_counts: dict[str, int] = {}
    for _, _, tier, _ in selected:
        selected_counts[tier] = selected_counts.get(tier, 0) + 1

    notes: list[str] = []
    if sum(selected_counts.values()) < max_rows:
        notes.append(
            f"could not fill max_rows={max_rows}; "
            f"selected {sum(selected_counts.values())}"
        )

    return EvidenceSelection(
        selected_rows=selected_rows,
        full_counts=full_counts,
        selected_counts=selected_counts,
        dropped_count=len(evidence_rows) - len(selected_rows),
        selection_strategy="tier_balanced_v1",
        notes=notes,
    )
