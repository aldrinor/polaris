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

import os
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
    # M-42d (2026-04-22): added `hpfb-dgpsa.ca` — Health Products and
    # Food Branch / Drug and Health Product Portal host. Existing
    # *.canada.ca hosts already catch recalls-rappels.canada.ca,
    # health-products.canada.ca, pdf.hres.ca via suffix match.
    ("HC",   ("canada.ca", "hres.ca", "hc-sc.gc.ca", "cda-amc.ca",
              "hpfb-dgpsa.ca")),
    ("TGA",  ("tga.gov.au",)),
    ("PMDA", ("pmda.go.jp",)),
    ("WHO",  ("who.int",)),
    ("NMPA", ("nmpa.gov.cn",)),
]


# M-42d (2026-04-22): Health Canada quota expansion. V25 baseline had
# 1 HC entry in the bibliography (M-41d reserved 1 slot per present
# jurisdiction). V26 aims for >=2 HC entries covering >=2 distinct
# topics (e.g. monograph + recall/advisory). The expansion is a
# quota-bounded 2nd reservation that ONLY fires after every present
# jurisdiction has its 1st reservation, so FDA/EMA/NICE/MHRA each
# keep their baseline 1 slot regardless of HC's 2nd. Relevance-fill
# still runs afterwards so FDA/EMA/NICE can exceed 1 slot naturally.
#
# Env override `PG_M41D_HC_QUOTA` (default 2). Setting to 1 restores
# exact M-41d behavior (no HC expansion).
_M42D_HC_QUOTA_DEFAULT = 2
_M42D_HC_JURISDICTION_CODE = "HC"


def _m42d_hc_quota() -> int:
    """Return the Health Canada quota (1..N) for the T3 selector floor.

    M-42d (2026-04-22): configurable via `PG_M41D_HC_QUOTA` env var.
    Defaults to 2. Values <1 clamp to 1 (legacy M-41d behavior).
    Invalid strings fall back to default.
    """
    raw = os.environ.get("PG_M41D_HC_QUOTA", "")
    if not raw:
        return _M42D_HC_QUOTA_DEFAULT
    try:
        v = int(raw)
    except (ValueError, TypeError):
        return _M42D_HC_QUOTA_DEFAULT
    return max(1, v)


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

# M-42e pass-2 (Codex audit blocker fix): reject titles that
# explicitly indicate a non-primary analysis type even when the
# URL is on a primary-publication host/DOI. Pre-pass-2 a title
# like "Post hoc analysis of SURPASS-2: subgroup results" on NEJM
# would be classified as primary; this fixes that.
_M42E_NON_PRIMARY_TITLE_PATTERNS = (
    "post hoc",
    "post-hoc",
    "posthoc",
    "subgroup analysis",
    "subgroup analyses",
    "subgroup results",
    "secondary analysis",
    "secondary analyses",
    "exploratory analysis",
    "exploratory analyses",
    "pooled analysis",
    "pooled analyses",
    "network meta-analysis",
    "meta-analysis",      # rarely a primary; safer to reject
    "systematic review",
    "substudy",
    "sub-study",
    "sub study",
    "pre-planned analysis",
    "pre-specified analysis",
    "pre-specified secondary",
    "commentary",
    "editorial",
    "perspective",
    # Pass-3 (Codex audit medium #1): narrow modeling/PK analysis
    # markers. These are supportive analyses that may be published on
    # primary hosts but are not the primary trial publication. We
    # avoid the generic bare "analysis" because "Primary analysis of
    # SURPASS-2" IS the primary result and must not be rejected.
    "pharmacokinetic analysis",
    "population pharmacokinetic",
    "modeling analysis",
    "model-based analysis",
    "exposure-response analysis",
    "pk analysis",
    "pd analysis",
    "pkpd analysis",
)


# M-42c (2026-04-22): mechanism-evidence detection for the
# mechanism-section selector floor. Token patterns mirror the M-40
# outline trigger vocabulary. A row is "mechanism-flagged" when any
# of these appear in title OR statement OR direct_quote.
_M42C_MECHANISM_TOKENS = (
    "mechanism",
    "pharmacokinetic",
    "pharmacodynamic",
    "receptor",
    "half-life",
    "half life",
    "bioavailability",
    "metabolism",
    "agonist",
    "antagonist",
    "binding",
    "signaling",
    "signalling",  # British spelling
    "pathway",
    "kinetic",
    "clamp",       # glucose clamp / euglycemic clamp
    "isotope",     # tracer / isotope labeling
    "affinity",    # receptor affinity
    "biomarker",
    "glucagon",    # incretin mechanism
    "insulin secretion",
    "insulin sensitivity",
)


def _m42c_row_is_mechanism_rich(row: dict[str, Any]) -> bool:
    """True if the row contains mechanism-of-action vocabulary in
    title, statement, or direct_quote. Case-insensitive substring
    match against `_M42C_MECHANISM_TOKENS`."""
    fields = [
        str(row.get("title") or ""),
        str(row.get("statement") or ""),
        str(row.get("direct_quote") or ""),
    ]
    combined = " ".join(fields).lower()
    return any(tok in combined for tok in _M42C_MECHANISM_TOKENS)


# M-42c floor: number of T1/T2 slots to reserve for mechanism rows
# when the corpus contains enough mechanism-flagged content. The
# floor fires only when the pool has >=4 mechanism rows (matches the
# M-40 outline-trigger threshold). Slots are taken from T1 first,
# then T2; the floor does NOT expand those tier quotas.
_M42C_MECHANISM_FLOOR_MIN_POOL_ROWS = 4
_M42C_MECHANISM_FLOOR_SLOTS = 3  # reserve 3 slots across T1+T2


def _m42e_detect_primary_for_anchor(
    row: dict[str, Any],
    anchor: str,
) -> bool:
    """True if `row` appears to be the primary publication for the
    named-trial `anchor` (e.g. 'SURPASS-2', 'SURMOUNT-1').

    Detection (M-42e pass-2):
      1. Anchor appears in row title (required).
      2. Row URL/DOI matches a known primary-publication prefix OR
         sits on a primary-publication host.
      3. Row title does NOT match any non-primary-analysis pattern
         (post hoc, subgroup, secondary, exploratory, pooled,
         meta-analysis, substudy, etc.). Even on a primary host, a
         title declaring itself as a post hoc or subgroup analysis
         is NOT the primary publication; usually it's a follow-up
         analysis published in the same or a companion journal.

    All three conditions required to prevent tagging analyses as
    primaries.
    """
    if not anchor:
        return False
    title = (row.get("title") or "").lower()
    url = (row.get("source_url") or row.get("url") or "").lower()
    anchor_l = anchor.lower()
    # (1) Title must contain the anchor (possibly with colon or
    # parenthesis separator).
    if anchor_l not in title:
        return False
    # (3) Title must NOT contain a non-primary-analysis marker.
    for pat in _M42E_NON_PRIMARY_TITLE_PATTERNS:
        if pat in title:
            return False
    # (2) URL must look like a primary publication — DOI prefix OR
    # host suggesting peer-reviewed journal.
    if any(p in url for p in _M42E_PRIMARY_DOI_PREFIXES):
        return True
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
    #
    # IMPORTANT trade-off (Codex audit medium #3): the floor
    # operates WITHIN T1 quota; it does not expand T1 and does not
    # directly push T2 below its quota. When T1 quota is small (e.g.
    # 5) and 6+ primaries match, all T1 slots become primaries with
    # no T1 review slot remaining. This is accepted behavior —
    # trading T1 review diversity for named-trial primary coverage —
    # but future readers should know the mechanism.
    # M-42c (2026-04-22): mechanism-rich T1+T2 floor. When the pool
    # has >=4 mechanism-flagged rows, reserve up to 3 T1+T2 slots
    # for mechanism content so the M-40 Mechanism section has an
    # evidence pool deep enough for the M-42c conditional prompt
    # target (20-35 sentences when >=8 mech ev_ids flow through).
    # Floor operates WITHIN existing T1+T2 quotas — does NOT expand
    # them. When no mechanism content present, no-op (backwards
    # compatible).
    m42c_mech_ids: set[int] = set()
    m42c_mech_pool_rows = [s for s in scored
                            if _m42c_row_is_mechanism_rich(s[3])]
    m42c_mech_fires = (
        len(m42c_mech_pool_rows) >= _M42C_MECHANISM_FLOOR_MIN_POOL_ROWS
    )
    if m42c_mech_fires:
        # Mechanism rows ordered by (tier_priority, -score) — prefer
        # T1 mechanism evidence over T2.
        mech_ranked = sorted(
            m42c_mech_pool_rows,
            key=lambda s: (_TIER_PRIORITY.get(s[2], 9), -s[1], s[0]),
        )
        # Only count rows in tiers T1 or T2 — the mechanism floor
        # doesn't touch T3/T4 quotas.
        slots_left = _M42C_MECHANISM_FLOOR_SLOTS
        for item in mech_ranked:
            if slots_left <= 0:
                break
            if item[2] not in ("T1", "T2"):
                continue
            # Only reserve if the tier has quota slots available.
            if quotas.get(item[2], 0) <= 0:
                continue
            m42c_mech_ids.add(id(item))
            slots_left -= 1

    m42e_primary_ids: set[int] = set()
    m42e_matched_anchors: list[str] = []  # M-42e pass-2: telemetry
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
                    m42e_matched_anchors.append(anchor)  # pass-2 telemetry
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
    # M-42d: telemetry notes populated inside the T3 block (HC expansion).
    # Collected here and flushed to `notes` after the main tier loop.
    _m42d_pending_notes: list[str] = []
    for tier, quota in quotas.items():
        # M-42e + M-42c: for T1 tier, reserve named-trial primary
        # slots (M-42e) AND mechanism-evidence slots (M-42c) before
        # filling rest by relevance. Both floors are computed above;
        # a row can satisfy both (e.g. a SURPASS-2 primary paper
        # that also has mechanism content — counted once).
        if tier == "T1" and quota > 0 and (m42e_primary_ids or m42c_mech_ids):
            tier_items = by_tier.get("T1", [])
            # Priority order: M-42e primary floor, then M-42c mech
            # floor, then fill by relevance. Reserved IDs are union
            # of both; deduped so a row satisfies at most one slot.
            reserved_t1: list[tuple[int, float, str, dict[str, Any]]] = []
            reserved_t1_ids: set[int] = set()
            # Pass 1: M-42e primaries
            for item in tier_items:
                if len(reserved_t1) >= quota:
                    break
                if id(item) in m42e_primary_ids and id(item) not in reserved_t1_ids:
                    reserved_t1.append(item)
                    reserved_t1_ids.add(id(item))
            # Pass 2: M-42c mechanism T1 rows
            for item in tier_items:
                if len(reserved_t1) >= quota:
                    break
                if id(item) in m42c_mech_ids and id(item) not in reserved_t1_ids:
                    reserved_t1.append(item)
                    reserved_t1_ids.add(id(item))
            # Pass 3: fill remaining T1 slots by relevance
            for item in tier_items:
                if len(reserved_t1) >= quota:
                    break
                if id(item) not in reserved_t1_ids:
                    reserved_t1.append(item)
                    reserved_t1_ids.add(id(item))
            selected.extend(reserved_t1)
            continue
        # M-42c: for T2 tier with mechanism floor, reserve mech T2
        # rows before filling rest by relevance.
        if tier == "T2" and quota > 0 and m42c_mech_ids:
            tier_items = by_tier.get("T2", [])
            reserved_t2: list[tuple[int, float, str, dict[str, Any]]] = []
            reserved_t2_ids: set[int] = set()
            # Pass 1: M-42c mechanism T2 rows
            for item in tier_items:
                if len(reserved_t2) >= quota:
                    break
                if id(item) in m42c_mech_ids and id(item) not in reserved_t2_ids:
                    reserved_t2.append(item)
                    reserved_t2_ids.add(id(item))
            # Pass 2: fill remaining T2 by relevance
            for item in tier_items:
                if len(reserved_t2) >= quota:
                    break
                if id(item) not in reserved_t2_ids:
                    reserved_t2.append(item)
                    reserved_t2_ids.add(id(item))
            selected.extend(reserved_t2)
            continue
        # M-41d: for T3 (regulatory) tier, enforce a
        # jurisdictional-diversity floor — reserve one slot per
        # present jurisdiction (FDA, EMA, NICE, HC, ...) before
        # filling the rest of the T3 quota by relevance. Prevents the
        # V24 failure mode where Health Canada evidence was in the
        # corpus but outcompeted within T3 by higher-scoring FDA/EMA.
        #
        # M-42d (2026-04-22): after the per-jurisdiction first-slot
        # pass, HC gets up to `_m42d_hc_quota()` additional reserved
        # slots (default 2 total). Preservation guard: HC's 2nd..Nth
        # slots only fire AFTER every present jurisdiction already has
        # its 1st, so FDA/EMA/NICE/MHRA are never displaced. The
        # relevance fill that follows still lets high-scoring
        # FDA/EMA/NICE rows beyond 1 slot be selected naturally.
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
            # M-42d: HC quota expansion. After every present
            # jurisdiction has its 1st slot, reserve up to
            # (hc_quota - 1) additional HC rows from the quota that
            # remains. This NEVER displaces FDA/EMA/NICE's 1st slots
            # because those are already allocated above.
            hc_quota = _m42d_hc_quota()
            m42d_hc_extras = 0
            if (
                hc_quota > 1
                and _M42D_HC_JURISDICTION_CODE in juris_groups
                and slots_left > 0
            ):
                hc_rows = juris_groups[_M42D_HC_JURISDICTION_CODE]
                # Rows are already in tier_items' original order (by
                # score then index). Skip the one already reserved.
                extras_remaining = hc_quota - 1
                for item in hc_rows:
                    if slots_left <= 0 or extras_remaining <= 0:
                        break
                    if id(item) not in reserved_ids:
                        reserved.append(item)
                        reserved_ids.add(id(item))
                        slots_left -= 1
                        extras_remaining -= 1
                        m42d_hc_extras += 1
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
            # Record telemetry for the HC expansion pass. Only emit
            # when the expansion actually added rows so audits can
            # distinguish "fired and added" vs "did not fire".
            #
            # M-42d pass-2 (Codex audit MEDIUM): `reserved` now reports
            # actual slots taken by the HC floor (1 from the 1-per-juris
            # pass + m42d_hc_extras) instead of the desired target
            # bounded by pool. When `hc_quota` exceeds available slots,
            # this prevents overstated telemetry.
            if m42d_hc_extras > 0:
                m42d_hc_reserved = 1 + m42d_hc_extras
                m42d_telemetry_note = (
                    f"m42d_hc_quota_expand hc_pool="
                    f"{len(juris_groups.get(_M42D_HC_JURISDICTION_CODE, []))} "
                    f"reserved={m42d_hc_reserved} "
                    f"extras_added={m42d_hc_extras} "
                    f"quota={hc_quota}"
                )
                _m42d_pending_notes.append(m42d_telemetry_note)
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
    # M-42e pass-2: surface the primary-floor telemetry so sweep
    # audits can see which anchors reserved slots and whether the
    # cap truncated reservations.
    # Pass-3 (Codex medium #2): split matched / reserved counts.
    # When matched > T1 quota, quota-trim reduces actual reservations
    # below matches. Report both so audits see the true state.
    if m42e_matched_anchors:
        cap = _M42E_PRIMARY_FLOOR_CAP
        actual_reserved = len(m42e_primary_ids)
        notes.append(
            f"m42e_primary_floor matched={len(m42e_matched_anchors)} "
            f"reserved={actual_reserved} cap={cap} "
            f"anchors={m42e_matched_anchors[:10]}"
        )
    # M-42c: mechanism-floor telemetry so sweep audits see when the
    # floor fires and how many slots were reserved.
    if m42c_mech_fires:
        notes.append(
            f"m42c_mechanism_floor pool_mech_rows={len(m42c_mech_pool_rows)} "
            f"reserved={len(m42c_mech_ids)} slots="
            f"{_M42C_MECHANISM_FLOOR_SLOTS}"
        )
    # M-42d: flush HC quota expansion telemetry collected inside the T3
    # block. Empty list = expansion did not fire (legacy behavior).
    notes.extend(_m42d_pending_notes)
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
