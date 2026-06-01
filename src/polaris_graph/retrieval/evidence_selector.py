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

import math
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any


# Tier priority for within-pool ranking. Lower tier number = higher priority.
_TIER_PRIORITY: dict[str, int] = {
    "T1": 1, "T2": 2, "T3": 3, "T4": 4,
    "T5": 5, "T6": 6, "T7": 7, "UNKNOWN": 8,
}

# I-meta-005 Phase 5 (#989): default relevance floor for `PG_RELEVANCE_FLOOR`.
_DEFAULT_RELEVANCE_FLOOR = 0.30


def parse_relevance_floor(
    raw: str | None, *, default: float = _DEFAULT_RELEVANCE_FLOOR,
) -> float:
    """Parse + validate ``PG_RELEVANCE_FLOOR`` (I-meta-005 Phase 5 #989).

    Range is (0.0, 1.0]. Empty/None -> ``default``. An unparseable float OR an
    out-of-range value raises ``ValueError`` (FAIL LOUD) — a missing/garbage floor
    must never silently send an unbounded, unfiltered pool to the generator.
    """
    if raw is None or not str(raw).strip():
        value = default
    else:
        try:
            value = float(str(raw).strip())
        except ValueError as exc:
            raise ValueError(
                "PG_RELEVANCE_FLOOR must be a float in (0.0, 1.0]; got "
                f"{raw!r}"
            ) from exc
    if not (0.0 < value <= 1.0):
        raise ValueError(
            f"PG_RELEVANCE_FLOOR out of range (0.0, 1.0]: {value}"
        )
    return value

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


def _row_title_text(row: dict[str, Any]) -> str:
    """M-48 pass-2 (2026-04-22, Codex blocker fix): shared accessor for
    a row's title/title-like text.

    Live evidence rows from `run_live_retrieval` populate `statement`
    with `cand.title[:300]` — NOT `title`. Pre-pass-2 accessors only
    read `row["title"]`, silently returning `""` for every live row.
    This broke M-42e primary detection AND M-48 population-scope
    labeling AND the preflight coverage check on real sweep data
    (tests passed only because fixtures used `title`).

    Precedence: explicit `title` > `statement` (live-retriever form) >
    `source_title` (alternative schema seen in some retrievers) > "".
    Returns a plain string (never None)."""
    for key in ("title", "statement", "source_title"):
        v = row.get(key)
        if isinstance(v, str) and v:
            return v
    return ""


def _m42c_row_is_mechanism_rich(row: dict[str, Any]) -> bool:
    """True if the row contains mechanism-of-action vocabulary in
    title, statement, or direct_quote. Case-insensitive substring
    match against `_M42C_MECHANISM_TOKENS`."""
    fields = [
        _row_title_text(row),
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
    # M-48 pass-2 (Codex blocker fix): live retriever populates
    # `statement` not `title`. Use shared accessor.
    title = _row_title_text(row).lower()
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


# ── #955 (S2, 2026-05-30): within-tier-band recency tiebreaker ──────────────
# Semantic Scholar `year` is fetched (live_retriever.py) and lands on the row
# (row["year"] or row["metadata"]["year"]) but the selector never used it, so a
# 2014 review and a 2025 pivotal RCT in the same tier competed only on
# tier + lexical relevance. This adds recency as a SOFT tiebreaker: relevance
# stays primary (banded into widths of epsilon); within the SAME tier AND SAME
# relevance band, a higher year sorts first. It NEVER crosses tiers, floor
# priority classes, or higher relevance bands (band is monotonic in score), and
# it NEVER hard-drops a row (only reorders within a band).
#
# Codex brief-gate APPROVE (#955) P2 note, documented here as required: because
# same-tier/same-band rows are treated as near-ties, recency CAN change WHICH
# same-band row fills a tier quota slot — a same-band OLDER row may lose its
# slot to a same-band NEWER one. It can never cost a MORE-relevant (higher-band)
# row its slot. That is the intended "soft floor, never hard-drop the more
# relevant" semantics. Default epsilon 0.05 per Codex ruling (0.0 = exact-tie
# only, too weak for the 2014-vs-2025 near-tie case).
_RECENCY_MIN_YEAR = 1900
_RECENCY_MAX_YEAR = 2100
_RECENCY_EPSILON_DEFAULT = 0.05


def _recency_enabled() -> bool:
    """Kill-switch `PG_SELECT_RECENCY_TIEBREAK` (default ON). OFF →
    byte-identical prior ordering AND no recency telemetry."""
    raw = os.environ.get("PG_SELECT_RECENCY_TIEBREAK", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _recency_epsilon() -> float:
    """Relevance band width `PG_SELECT_RECENCY_EPSILON` (default 0.05).
    epsilon <= 0 → exact-score-tie mode (band = raw score)."""
    raw = os.environ.get("PG_SELECT_RECENCY_EPSILON", "").strip()
    if not raw:
        return _RECENCY_EPSILON_DEFAULT
    try:
        return float(raw)
    except (ValueError, TypeError):
        return _RECENCY_EPSILON_DEFAULT


def _row_year(row: dict[str, Any]) -> int | None:
    """Publication year from `row['year']` or `row['metadata']['year']`.
    Returns None if absent / non-numeric / outside [1900, 2100]. No network."""
    val = row.get("year")
    if val is None:
        meta = row.get("metadata")
        if isinstance(meta, dict):
            val = meta.get("year")
    if val is None:
        return None
    try:
        year = int(val)
    except (ValueError, TypeError):
        return None
    if year < _RECENCY_MIN_YEAR or year > _RECENCY_MAX_YEAR:
        return None
    return year


def _relevance_band(score: float, epsilon: float) -> float:
    """Bucket a relevance score into a band. Higher score → higher band.
    epsilon <= 0 → exact score (only exact ties share a band)."""
    if epsilon <= 0:
        return score
    return math.floor(score / epsilon)


def _year_sort_value(row: dict[str, Any]) -> int:
    """Ascending-sort value for 'newer first': negated year; a missing year
    maps below any real year so undated rows sort LAST within a band (but are
    never excluded)."""
    year = _row_year(row)
    return -(year if year is not None else _RECENCY_MIN_YEAR - 1)


def _relevance_recency_key(
    item: tuple[int, float, str, dict[str, Any]],
    enabled: bool,
    epsilon: float,
) -> tuple:
    """Sort fragment ranking by relevance then (soft) recency, or by raw
    relevance when disabled. Callers append the original index for full
    determinism. Disabled → `(-score,)`, byte-identical to the prior key."""
    _idx, score, _tier, row = item
    if not enabled:
        return (-score,)
    # Within a relevance band, newer year first; then EXACT score as the
    # sub-tiebreaker. Because the band is monotonic in score and exact score
    # breaks within-band ties, an all-undated corpus reproduces the prior
    # pure-(-score) order EXACTLY — recency only reorders DATED same-band rows.
    return (-_relevance_band(score, epsilon), _year_sort_value(row), -score)


def _recency_telemetry_note(
    scored: list[tuple[int, float, str, dict[str, Any]]],
    epsilon: float,
) -> str:
    """Note emitted ONLY when the recency tiebreaker is enabled."""
    dated = sum(1 for s in scored if _row_year(s[3]) is not None)
    return (
        f"recency_tiebreak enabled epsilon={epsilon} "
        f"dated={dated}/{len(scored)}"
    )


# ── #956 (S2, 2026-05-30): source-diversity passes ──────────────────────────
# Tier quota != topical diversity: 20 T1 RCTs all on ONE sub-topic satisfy the
# T1 quota while starving the other sub-topics, tanking per-sub-topic coverage.
# Two SOFT post-selection passes operate ONLY on post-floor slack and ALWAYS
# preserve tier minimums (Codex brief-gate P2). Because the selected set sits
# exactly at the tier quotas, every quota-preserving swap is SAME-TIER: a
# diversity swap replaces a same-tier NON-reserved relevance-fill row with a
# same-tier pool row, so no tier ever drops below quota and no floor-reserved
# (M-42e/M-51/M-42c/M-42d) or sub-query-reserved row is ever evicted. Both
# passes run on the truncating main path only (short-pool keeps every row, so
# diversity is already maximal there). Codex rulings: k=1, cap_frac=0.5,
# reservation BEFORE domain cap.
_SUBQUERY_K_DEFAULT = 1
_DOMAIN_CAP_FRAC_DEFAULT = 0.5


def _env_flag_on(name: str) -> bool:
    return os.environ.get(name, "1").strip().lower() not in ("0", "false", "no", "off")


def _subquery_reserve_config() -> tuple[bool, int]:
    enabled = _env_flag_on("PG_SELECT_SUBQUERY_RESERVE")
    raw = os.environ.get("PG_SELECT_SUBQUERY_K", "").strip()
    try:
        k = int(raw) if raw else _SUBQUERY_K_DEFAULT
    except (ValueError, TypeError):
        k = _SUBQUERY_K_DEFAULT
    return enabled, max(1, k)


def _domain_cap_config() -> tuple[bool, float]:
    enabled = _env_flag_on("PG_SELECT_DOMAIN_CAP")
    raw = os.environ.get("PG_SELECT_DOMAIN_CAP_FRAC", "").strip()
    try:
        frac = float(raw) if raw else _DOMAIN_CAP_FRAC_DEFAULT
    except (ValueError, TypeError):
        frac = _DOMAIN_CAP_FRAC_DEFAULT
    return enabled, frac


def _row_query_origin(row: dict[str, Any]) -> str:
    """The sub-query that surfaced the row (`query_origin`), or `_unlabeled`."""
    return str(row.get("query_origin") or "") or "_unlabeled"


def _row_domain(row: dict[str, Any]) -> str:
    """Registrable-ish domain (last two host labels) for the per-domain cap."""
    url = (row.get("source_url") or row.get("url") or "").lower()
    if not url:
        return ""
    try:
        from urllib.parse import urlparse
        host = (urlparse(url if "://" in url else f"http://{url}").hostname or "").lower()
    except (ValueError, AttributeError):
        return ""
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def _priority_sort_key(
    item: tuple[int, float, str, dict[str, Any]],
    rec_enabled: bool,
    rec_eps: float,
) -> tuple:
    """Within-tier priority for diversity swap decisions — same ordering the
    selector uses (banded relevance + #955 recency, then original index).
    Ascending = best first; max(...) of this key = worst (lowest priority)."""
    return (*_relevance_recency_key(item, rec_enabled, rec_eps), item[0])


def _reserve_subqueries(
    selected: list[tuple[int, float, str, dict[str, Any]]],
    scored: list[tuple[int, float, str, dict[str, Any]]],
    protected_ids: set[int],
    k: int,
    rec_enabled: bool,
    rec_eps: float,
) -> tuple[int, set[int]]:
    """Same-tier swap so each sub-query origin present in a tier's pool reaches
    >= k selected rows in that tier, evicting only NON-protected slack rows whose
    origin is OVER-represented (count > k). Returns (swaps, brought_in_ids)."""
    selected_ids = {id(it) for it in selected}
    pool_by_tier: dict[str, list] = defaultdict(list)
    for it in scored:
        if id(it) not in selected_ids:
            pool_by_tier[it[2]].append(it)
    brought_in: set[int] = set()
    swaps = 0
    for tier in {it[2] for it in selected}:
        sel_pos = [i for i, it in enumerate(selected) if it[2] == tier]
        origin_count = Counter(_row_query_origin(selected[i][3]) for i in sel_pos)
        cand_by_origin: dict[str, list] = defaultdict(list)
        for it in pool_by_tier.get(tier, []):
            cand_by_origin[_row_query_origin(it[3])].append(it)
        missing = sorted(
            [o for o in cand_by_origin if origin_count.get(o, 0) < k],
            key=lambda o: (-max(c[1] for c in cand_by_origin[o]), o),
        )
        for origin in missing:
            cands = sorted(
                cand_by_origin[origin],
                key=lambda c: _priority_sort_key(c, rec_enabled, rec_eps),
            )
            ci = 0
            while origin_count.get(origin, 0) < k and ci < len(cands):
                evictable = [
                    i for i in sel_pos
                    if id(selected[i]) not in protected_ids
                    and id(selected[i]) not in brought_in
                    and origin_count[_row_query_origin(selected[i][3])] > k
                    and _row_query_origin(selected[i][3]) != origin
                ]
                if not evictable:
                    break
                evict_i = max(
                    evictable,
                    key=lambda i: _priority_sort_key(selected[i], rec_enabled, rec_eps),
                )
                bring = cands[ci]
                ci += 1
                old_origin = _row_query_origin(selected[evict_i][3])
                selected[evict_i] = bring
                brought_in.add(id(bring))
                origin_count[old_origin] -= 1
                origin_count[origin] = origin_count.get(origin, 0) + 1
                swaps += 1
    return swaps, brought_in


def _apply_domain_cap(
    selected: list[tuple[int, float, str, dict[str, Any]]],
    scored: list[tuple[int, float, str, dict[str, Any]]],
    protected_ids: set[int],
    cap: int,
    rec_enabled: bool,
    rec_eps: float,
) -> int:
    """Soft per-domain cap via same-tier swaps. An over-cap domain's NON-protected
    slack rows (worst-priority first) are replaced by the best same-tier pool row
    of an under-cap domain. YIELDS (stops) when no valid same-tier replacement
    exists — never leaves a slot empty, drops a tier below quota, or evicts a
    protected/reserved row. Returns the number of rows moved."""
    moved = 0
    selected_ids = {id(it) for it in selected}
    domain_count = Counter(_row_domain(it[3]) for it in selected)
    over = [d for d, c in domain_count.items() if d and c > cap]
    for dom in over:
        while domain_count[dom] > cap:
            evict_positions = sorted(
                [i for i, it in enumerate(selected)
                 if _row_domain(it[3]) == dom and id(it) not in protected_ids],
                key=lambda i: _priority_sort_key(selected[i], rec_enabled, rec_eps),
                reverse=True,  # worst-priority first
            )
            swapped = False
            for ei in evict_positions:
                tier = selected[ei][2]
                repls = [
                    it for it in scored
                    if id(it) not in selected_ids
                    and it[2] == tier
                    and _row_domain(it[3]) != dom
                    and domain_count.get(_row_domain(it[3]), 0) < cap
                ]
                if not repls:
                    continue
                best = min(repls, key=lambda it: _priority_sort_key(it, rec_enabled, rec_eps))
                old = selected[ei]
                selected[ei] = best
                selected_ids.discard(id(old))
                selected_ids.add(id(best))
                domain_count[dom] -= 1
                domain_count[_row_domain(best[3])] = domain_count.get(_row_domain(best[3]), 0) + 1
                moved += 1
                swapped = True
                break
            if not swapped:
                break  # yield: no same-tier under-cap replacement available
    return moved


def _m46_short_pool_ordered_selection(
    *,
    evidence_rows: list[dict[str, Any]],
    scored: list[tuple[int, float, str, dict[str, Any]]],
    full_counts: dict[str, int],
    max_rows: int,
    primary_trial_anchors: list[str] | None,
) -> EvidenceSelection:
    """M-46 (2026-04-22): compute floor detection + deterministic
    priority ordering + telemetry for the short-pool case
    (pool_size <= max_rows).

    Pre-M-46: the early-exit branch returned evidence_rows as-is with
    a single `pool_size<=max_rows` note and no floor telemetry. When
    floors were configured, the reservations silently did not fire.

    Post-M-46: all rows are kept (no truncation), but ordering is
    [M-42e primaries → M-42c mechanism → M-42d HC → rest by tier
    priority then -relevance then index]. Notes include the same
    floor-telemetry entries seen on truncating runs so downstream
    audits see consistent signals regardless of pool size.

    The function is self-contained and does NOT share state with the
    main branch; it re-detects primaries / mechanism / HC using the
    same module-level predicates (`_m42e_detect_primary_for_anchor`,
    `_m42c_row_is_mechanism_rich`, `_row_jurisdiction`).
    """
    notes: list[str] = [
        f"pool_size<=max_rows ({len(scored)}/{max_rows})",
        "m46_short_pool_ordered_selection",
    ]

    # --- M-42e primary detection ---
    m42e_ids: set[int] = set()
    m42e_anchors: list[str] = []
    if primary_trial_anchors:
        # Prefer T1 primaries; fall back to any-tier if no T1 match
        # (matches M-42e spirit — the primary paper is the priority).
        t1_scored = [s for s in scored if s[2] == "T1"]
        for anchor in primary_trial_anchors:
            if len(m42e_ids) >= _M42E_PRIMARY_FLOOR_CAP:
                break
            matched = False
            for item in t1_scored:
                if id(item) in m42e_ids:
                    continue
                if _m42e_detect_primary_for_anchor(item[3], anchor):
                    m42e_ids.add(id(item))
                    m42e_anchors.append(anchor)
                    matched = True
                    break
            # No fallback to other tiers — same contract as main branch.
            del matched  # quiet linters
    if m42e_anchors:
        notes.append(
            f"m42e_primary_floor matched={len(m42e_anchors)} "
            f"reserved={len(m42e_ids)} cap={_M42E_PRIMARY_FLOOR_CAP} "
            f"anchors={m42e_anchors[:10]}"
        )

    # --- M-51 primary custody (short-pool path) ---
    # V29 cycle 1. Short-pool path keeps ALL rows so no truncation
    # trim is needed. But we still want to scan the full `scored`
    # pool for anchor-matched primaries that M-42e (T1-only) may
    # have missed (non-T1 primaries, or rows with tie-breaking
    # mis-rankings). Any match is prioritized to class 0 in
    # `_priority_class` via `m51_extra_ids`.
    m51_extra_ids: set[int] = set()
    m51_sp_matched_anchors: list[str] = []
    if primary_trial_anchors:
        def _m51_canonical_identity_sp(row: dict[str, Any]) -> tuple:
            evid = row.get("evidence_id")
            if isinstance(evid, str) and evid:
                return ("ev", evid)
            url = (row.get("source_url") or row.get("url") or "").lower()
            title = _row_title_text(row).lower()[:200]
            dq = (row.get("direct_quote") or "")[:200]
            return ("key", url, title, dq)
        already_canon = {
            _m51_canonical_identity_sp(item[3]) for item in scored
            if id(item) in m42e_ids
        }
        seen_anchors_sp: set[str] = set()
        for anchor in primary_trial_anchors:
            if anchor in seen_anchors_sp:
                continue
            seen_anchors_sp.add(anchor)
            # Already covered by M-42e for this anchor?
            if anchor in m42e_anchors:
                continue
            # Scan full scored pool (includes non-T1) for this anchor
            for scored_item in scored:
                if id(scored_item) in m42e_ids:
                    continue
                if id(scored_item) in m51_extra_ids:
                    continue
                if _m42e_detect_primary_for_anchor(scored_item[3], anchor):
                    m51_extra_ids.add(id(scored_item))
                    m51_sp_matched_anchors.append(anchor)
                    break
    if m51_sp_matched_anchors:
        notes.append(
            f"m51_anchor_primary_custody matched="
            f"{len(m51_sp_matched_anchors)} "
            f"inserted={len(m51_sp_matched_anchors)} "
            f"cap={len({a for a in primary_trial_anchors})} "
            f"anchors={m51_sp_matched_anchors[:12]}"
        )

    # --- M-42c mechanism detection ---
    mech_pool = [s for s in scored if _m42c_row_is_mechanism_rich(s[3])]
    m42c_ids: set[int] = set()
    if len(mech_pool) >= _M42C_MECHANISM_FLOOR_MIN_POOL_ROWS:
        mech_ranked = sorted(
            mech_pool,
            key=lambda s: (_TIER_PRIORITY.get(s[2], 9), -s[1], s[0]),
        )
        slots_left = _M42C_MECHANISM_FLOOR_SLOTS
        for item in mech_ranked:
            if slots_left <= 0:
                break
            if item[2] not in ("T1", "T2"):
                continue
            if id(item) in m42e_ids:
                # Primary-trial slot already reserved — don't double-count.
                continue
            m42c_ids.add(id(item))
            slots_left -= 1
        notes.append(
            f"m42c_mechanism_floor pool_mech_rows={len(mech_pool)} "
            f"reserved={len(m42c_ids)} "
            f"slots={_M42C_MECHANISM_FLOOR_SLOTS}"
        )

    # --- M-42d HC quota expansion detection ---
    hc_rows = [s for s in scored
               if s[2] == "T3"
               and _row_jurisdiction(s[3]) == _M42D_HC_JURISDICTION_CODE]
    hc_quota = _m42d_hc_quota()
    m42d_hc_ids: set[int] = set()
    m42d_hc_extras = 0
    if hc_rows and hc_quota > 1:
        # In short-pool mode, reserve up to `hc_quota` HC rows
        # (bounded by pool) — first one mirrors the 1-per-juris pass
        # in the main branch, extras are the M-42d expansion.
        hc_sorted = sorted(hc_rows, key=lambda s: (-s[1], s[0]))
        target = min(hc_quota, len(hc_sorted))
        for item in hc_sorted[:target]:
            m42d_hc_ids.add(id(item))
        m42d_hc_extras = max(0, len(m42d_hc_ids) - 1)
        if m42d_hc_extras > 0:
            notes.append(
                f"m42d_hc_quota_expand hc_pool={len(hc_rows)} "
                f"reserved={len(m42d_hc_ids)} "
                f"extras_added={m42d_hc_extras} quota={hc_quota}"
            )

    # --- Deterministic priority ordering ---
    # Priority class: 0 = M-42e primary OR M-51 anchor-primary extra,
    # 1 = M-42c mechanism, 2 = M-42d HC, 3 = rest. Within same class:
    # by tier priority, then -score, then index.
    def _priority_class(item: tuple[int, float, str, dict[str, Any]]) -> int:
        iid = id(item)
        if iid in m42e_ids or iid in m51_extra_ids:
            return 0
        if iid in m42c_ids:
            return 1
        if iid in m42d_hc_ids:
            return 2
        return 3

    # #955: recency is a SOFT tiebreaker AFTER priority-class + tier (both stay
    # ahead, per Codex P2) and after the banded relevance — recency only orders
    # within the same class/tier/relevance-band.
    _rec_enabled = _recency_enabled()
    _rec_eps = _recency_epsilon()
    ordered = sorted(
        scored,
        key=lambda item: (
            _priority_class(item),
            _TIER_PRIORITY.get(item[2], 9),
            *_relevance_recency_key(item, _rec_enabled, _rec_eps),
            item[0],
        ),
    )
    if _rec_enabled:
        notes.append(_recency_telemetry_note(scored, _rec_eps))
    selected_rows = [item[3] for item in ordered]
    selected_counts = dict(full_counts)

    return EvidenceSelection(
        selected_rows=selected_rows,
        full_counts=full_counts,
        selected_counts=selected_counts,
        dropped_count=0,
        selection_strategy="tier_balanced_v1_all_m46_ordered",
        notes=notes,
    )


def _relevance_floor_selection(
    *,
    scored: list[tuple[int, float, str, dict[str, Any]]],
    relevance_floor: float,
    full_counts: dict[str, int],
    primary_trial_anchors: list[str] | None,
) -> EvidenceSelection:
    """I-meta-005 Phase 5 (#989): relevance-floor selection (no max_rows cap).

    Keep EVERY row whose lexical relevance >= ``relevance_floor``, PLUS any row
    matching a primary trial anchor (floor-EXEMPT — a relevant primary RCT must
    never be dropped on a low lexical score). Ranked by ``relevance x authority``
    (authority = the row's ``authority_score`` sidecar, default 1.0). Each kept
    row is stamped with the additive ``selection_relevance`` float so
    ``finding_dedup`` picks representatives on the IDENTICAL score (no recompute
    drift). Pure; returns SHALLOW COPIES (never mutates the caller's rows).
    """
    anchors = list(primary_trial_anchors or [])

    def _is_anchor(row: dict[str, Any]) -> bool:
        return any(_m42e_detect_primary_for_anchor(row, a) for a in anchors)

    def _authority(row: dict[str, Any]) -> float:
        # Default 1.0 ONLY when authority_score is absent/None — an EXPLICIT 0.0
        # (genuinely zero-authority row) must rank as 0.0, not be laundered to 1.0
        # by a falsy `or` (Codex diff-gate P2).
        a = row.get("authority_score")
        return 1.0 if a is None else float(a)

    kept = [
        item for item in scored
        if item[1] >= relevance_floor or _is_anchor(item[3])
    ]
    kept.sort(
        key=lambda s: (
            -(s[1] * _authority(s[3])),
            _TIER_PRIORITY.get(s[2], 9),
            s[0],
        )
    )
    selected_rows: list[dict[str, Any]] = []
    selected_counts: dict[str, int] = {}
    for idx, score, tier, row in kept:
        new_row = dict(row)
        new_row["selection_relevance"] = float(score)
        selected_rows.append(new_row)
        selected_counts[tier] = selected_counts.get(tier, 0) + 1
    anchor_exempt = sum(
        1 for item in kept
        if item[1] < relevance_floor and _is_anchor(item[3])
    )
    return EvidenceSelection(
        selected_rows=selected_rows,
        full_counts=full_counts,
        selected_counts=selected_counts,
        dropped_count=len(scored) - len(kept),
        selection_strategy="relevance_floor_v1",
        notes=[
            f"relevance_floor={relevance_floor}: kept {len(kept)}/{len(scored)} "
            f"rows (>= floor OR primary anchor); no max_rows cap; ranked "
            f"relevance x authority_score; anchor_floor_exempt={anchor_exempt}",
        ],
    )


def select_evidence_for_generation(
    *,
    research_question: str,
    protocol: dict[str, Any] | None,
    classified_sources: list[Any],
    evidence_rows: list[dict[str, Any]],
    max_rows: int,
    primary_trial_anchors: list[str] | None = None,
    relevance_floor: float | None = None,
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
    # I-meta-005 Phase 5 (#989) — Codex diff-gate P2: in relevance-floor mode the
    # `max_rows` cap is REPLACED by the floor, so a legacy `max_rows <= 0` must NOT
    # empty the ON-mode pool. The empty-corpus guard still applies in both modes.
    if (max_rows <= 0 and relevance_floor is None) or not evidence_rows:
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

    # I-meta-005 Phase 5 (#989): relevance-floor mode (PG_USE_FINDING_DEDUP). Keep
    # EVERY row at/above the relevance floor (no max_rows cap), ranked
    # relevance x authority. ON-mode only; `relevance_floor is None` on the legacy
    # path -> the tier-balanced max_rows selection below is byte-identical (and
    # adds NO new row key).
    if relevance_floor is not None:
        return _relevance_floor_selection(
            scored=scored,
            relevance_floor=relevance_floor,
            full_counts=full_counts,
            primary_trial_anchors=primary_trial_anchors,
        )

    # M-46 (2026-04-22): when total <= max_rows, still keep everything,
    # BUT compute floor-detection + deterministic priority ordering
    # + telemetry so downstream consumers see the same reservation
    # signals they would see on a truncating run.
    #
    # Pre-M-46 behavior: early-exit branch returned evidence_rows as-is
    # with a single `pool_size<=max_rows` note and no floor telemetry.
    # M-42e primaries, M-42c mechanism rows, and M-42d HC rows were
    # silently not prioritized when pool was small.
    #
    # Post-M-46 behavior: selected list ordered as [M-42e primaries →
    # M-42c mechanism → M-42d HC → rest by (tier priority, -relevance,
    # index)]. All original rows are kept; only ordering changes.
    # Notes include the m42e_primary_floor / m42c_mechanism_floor /
    # m42d_hc_quota_expand entries seen on truncating runs.
    if len(scored) <= max_rows:
        return _m46_short_pool_ordered_selection(
            evidence_rows=evidence_rows,
            scored=scored,
            full_counts=full_counts,
            max_rows=max_rows,
            primary_trial_anchors=primary_trial_anchors,
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
    # #955: within-tier ranking gains a SOFT recency tiebreaker. Relevance
    # (banded) stays primary; within a band, higher year first. Floors below
    # still reserve their matched rows — recency only reorders same-band
    # candidates (Codex P2: floor reservation priority is evaluated before
    # recency). Kill-switch OFF → identical (-score, idx) ordering.
    _rec_enabled = _recency_enabled()
    _rec_eps = _recency_epsilon()
    for tier in by_tier:
        by_tier[tier].sort(
            key=lambda x: (*_relevance_recency_key(x, _rec_enabled, _rec_eps), x[0])
        )

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
    # #956: ids of T3 jurisdiction/HC floor-reserved rows, so the diversity
    # passes never evict a regulatory-floor row (the m42e/m42c/m51 floors are
    # already tracked by their own id sets).
    _t3_floor_protected_ids: set[int] = set()
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
            # #956: at this point reserved_ids holds ONLY the jurisdiction +
            # HC floor slots (the relevance-fill below is NOT a floor). Capture
            # them so the diversity passes treat them as protected.
            _t3_floor_protected_ids |= set(reserved_ids)
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

    # ─── M-51 (2026-04-23): V29 Strategy β cycle 1 — anchor-matched
    # primary hard-reservation post-process. Per Codex V29 plan pass-1
    # review (CONDITIONAL-no-blockers) at
    # `outputs/codex_findings/v29_fix_plan_review_pass1/findings.md`.
    #
    # Prior mechanism gap (verified by V28 cross-review):
    # `outputs/audits/v28/cross_review.md` shows SURPASS-4 Del Prato
    # Lancet + SURPASS-CVOT Nicholls were present in V28's
    # `live_corpus_dump.json` but absent from the final bibliography.
    # The existing M-42e floor only scans `by_tier.get("T1", [])`
    # within the T1 quota slice; when T1 quota is tight and
    # non-primary T1 rows outrank primaries by relevance, primaries
    # are still dropped. This is the dominant root cause driving 4
    # of 7 V28 LOSE_BOTH dimensions.
    #
    # M-51 post-process: for each unique anchor, scan the FULL `scored`
    # pool (not just T1); insert any anchor-matched primary not
    # already in `selected` at position 0 (highest priority). Cap at
    # min(|unique_anchors|, max_rows). Trim non-M-51 tail rows to
    # keep len(selected) <= max_rows.
    #
    # Codex review revisions woven in:
    #   - Canonical identity (not Python `id()`): evidence_id if
    #     present, else (source_url, title, direct_quote[:200]).
    #   - Derived cap min(|unique_anchors|, max_rows), not literal 11.
    #   - Trim protects M-51-inserted rows; pops lowest-priority
    #     non-M-51 tail rows when overflow.
    #   - No-anchors path is a no-op (byte-identical to pre-M-51).

    def _m51_canonical_identity(row: dict[str, Any]) -> tuple:
        """Stable identity for M-51 duplicate detection. Prefers
        `evidence_id` when present; falls back to normalized
        (source_url, title, direct_quote[:200]) tuple."""
        evid = row.get("evidence_id")
        if isinstance(evid, str) and evid:
            return ("ev", evid)
        url = (row.get("source_url") or row.get("url") or "").lower()
        title = _row_title_text(row).lower()[:200]
        dq = (row.get("direct_quote") or "")[:200]
        return ("key", url, title, dq)

    m51_inserted_ids: set[int] = set()  # ids of (tuple) items in `selected`
    m51_matched_anchors: list[str] = []
    if primary_trial_anchors:
        selected_canon = {
            _m51_canonical_identity(item[3]) for item in selected
        }
        unique_anchors = []
        seen_anchors: set[str] = set()
        for a in primary_trial_anchors:
            if a in seen_anchors:
                continue
            seen_anchors.add(a)
            unique_anchors.append(a)
        m51_cap = min(len(unique_anchors), max_rows)
        for anchor in unique_anchors:
            if len(m51_matched_anchors) >= m51_cap:
                break
            # Scan full scored pool for first anchor-matched primary
            # not already in selected.
            for scored_item in scored:
                canon = _m51_canonical_identity(scored_item[3])
                if canon in selected_canon:
                    continue
                if _m42e_detect_primary_for_anchor(scored_item[3], anchor):
                    selected.insert(0, scored_item)
                    selected_canon.add(canon)
                    m51_inserted_ids.add(id(scored_item))
                    m51_matched_anchors.append(anchor)
                    break
        # Trim non-reserved tail if M-51 overflowed max_rows. Pop
        # lowest-priority non-M-51-inserted rows from END of list.
        # Sort by (tier_priority, -score, idx) so the tail IS the
        # lowest priority after the main tier loop's sort runs
        # below — but here we haven't sorted yet. Pop items with
        # the lowest tier priority first (T7 before T1).
        if len(selected) > max_rows:
            # Build eviction candidates: indices of non-M-51 items
            # sorted by (reverse tier priority, +score, reverse idx).
            # We want to evict lowest-tier, lowest-score first.
            eviction_order = sorted(
                [
                    i for i, item in enumerate(selected)
                    if id(item) not in m51_inserted_ids
                ],
                key=lambda i: (
                    -_TIER_PRIORITY.get(selected[i][2], 9),  # lowest tier first
                    selected[i][1],                           # lowest score first
                    -selected[i][0],                          # highest idx first
                ),
            )
            to_evict = len(selected) - max_rows
            evict_ids = set(eviction_order[:to_evict])
            # Rebuild selected in original order, skipping evicted.
            selected = [item for i, item in enumerate(selected)
                        if i not in evict_ids]

    # ── #956 (S2): source-diversity passes (main truncating path only) ──────
    # Operate on post-floor slack via SAME-TIER swaps: reservation first, then
    # the per-domain soft cap. protected_ids = every floor-reserved row
    # (M-42e primary, M-42c mechanism, M-51 anchor custody, T3 jurisdiction/HC).
    # Both kill-switchable; OFF → no swaps, no telemetry (byte-identical).
    _diversity_notes: list[str] = []
    protected_ids = (
        set(m42e_primary_ids) | set(m42c_mech_ids)
        | set(m51_inserted_ids) | set(_t3_floor_protected_ids)
    )
    _subq_enabled, _subq_k = _subquery_reserve_config()
    if _subq_enabled:
        _subq_swaps, _subq_brought = _reserve_subqueries(
            selected, scored, protected_ids, _subq_k, _rec_enabled, _rec_eps,
        )
        if _subq_swaps:
            _diversity_notes.append(
                f"subquery_reservation k={_subq_k} swaps={_subq_swaps}"
            )
        # Don't let the domain cap undo a sub-query reservation.
        protected_ids |= _subq_brought
    _dom_enabled, _dom_frac = _domain_cap_config()
    if _dom_enabled:
        _dom_cap = max(1, math.ceil(_dom_frac * max_rows))
        _dom_moved = _apply_domain_cap(
            selected, scored, protected_ids, _dom_cap, _rec_enabled, _rec_eps,
        )
        if _dom_moved:
            _diversity_notes.append(
                f"domain_soft_cap cap={_dom_cap} moved={_dom_moved}"
            )

    # Sort final selection by (tier_priority, relevance/recency, original_idx)
    # for deterministic output order. #955: recency is a soft tiebreaker after
    # tier + banded relevance; kill-switch OFF → identical (tier, -score, idx).
    selected.sort(
        key=lambda x: (
            _TIER_PRIORITY.get(x[2], 9),
            *_relevance_recency_key(x, _rec_enabled, _rec_eps),
            x[0],
        )
    )

    selected_rows = [item[3] for item in selected]
    selected_counts: dict[str, int] = {}
    for _, _, tier, _ in selected:
        selected_counts[tier] = selected_counts.get(tier, 0) + 1

    notes: list[str] = []
    # #956: source-diversity telemetry (empty unless a pass fired).
    notes.extend(_diversity_notes)
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
    # M-51 (2026-04-23): anchor-custody telemetry for V29 diagnosis.
    if m51_matched_anchors:
        m51_cap_final = min(
            len({a for a in primary_trial_anchors or []}), max_rows,
        )
        notes.append(
            f"m51_anchor_primary_custody matched="
            f"{len(m51_matched_anchors)} "
            f"inserted={len(m51_matched_anchors)} "
            f"cap={m51_cap_final} "
            f"anchors={m51_matched_anchors[:12]}"
        )
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
