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

import logging
import math
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any


_LOGGER = logging.getLogger(__name__)


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


# ── I-arch-004 F24 (#1255): generator-facing evidence cap default ────────────
# THE BUG: every direct entry point (run_honest_sweep_r3, run_honest_on_prerebuild_corpus,
# run_live_honest_cycle) read ``int(os.getenv("PG_LIVE_MAX_EV_TO_GEN", "20"))`` — a hardcoded
# default of 20. The Gate-B cert slate overrides it to 1500, so the starvation is LATENT on the
# certification path; but a DIRECT / bypass / flags-OFF caller silently capped the generator at
# 20 evidence rows regardless of how large the corpus was. A 20-evidence generation off a
# multi-hundred-source corpus is a starved generation (CLAUDE.md §-1.3: a silent thinner).
#
# THE FIX (§-1.3 WEIGHT-AND-CONSOLIDATE, not a bigger silent cap): when the env is UNSET, default
# to the FULL pool — i.e. NO cap (the selector already keeps everything when ``pool_size <=
# max_rows``, see the ``len(scored) <= max_rows`` keep-all branch). When the env IS set, honor it
# (LAW VI) but emit a LOUD WARNING whenever the cap actually BINDS (cap < pool_size) so a direct
# caller is never SILENTLY truncated. Truncation is always observable; it is never silent.
_MAX_EV_TO_GEN_ENV = "PG_LIVE_MAX_EV_TO_GEN"


def resolve_max_ev_to_gen(pool_size: int) -> int:
    """Resolve the generator-facing evidence cap for a corpus of ``pool_size`` rows.

    Returns the effective ``max_rows`` to hand the tier-balanced selector:

    * Env UNSET  -> ``pool_size`` (full-corpus floor; the selector keeps every row, NO silent
      20-cap). A non-positive/empty corpus returns 0 (the selector's own
      ``max_rows <= 0`` short-circuit handles it).
    * Env SET    -> the parsed integer (LAW VI operator override). If that cap is smaller than the
      corpus (it BINDS), log a LOUD WARNING naming the drop count, so a direct caller can SEE the
      truncation. A non-binding or absurd (<=0) value still defers to the selector's own guards.

    This is a CAPABILITY FLOOR, not a thinner: the default path delivers the full pool; any
    reduction is operator-chosen AND announced.
    """
    safe_pool = max(0, int(pool_size))
    raw = os.getenv(_MAX_EV_TO_GEN_ENV)
    if raw is None or not str(raw).strip():
        # Full-corpus floor: feed every available row to the selector (keep-all).
        return safe_pool
    try:
        cap = int(str(raw).strip())
    except (ValueError, TypeError):
        _LOGGER.warning(
            "[evidence_selector] F24: %s=%r is not an integer — defaulting to the "
            "full-corpus floor (%d rows, no cap) rather than a silent starve.",
            _MAX_EV_TO_GEN_ENV, raw, safe_pool,
        )
        return safe_pool
    if 0 < cap < safe_pool:
        _LOGGER.warning(
            "[evidence_selector] F24: %s=%d BINDS on a %d-row corpus — the generator will see "
            "only %d of %d rows (%d dropped). This is an operator-set cap, NOT a silent default; "
            "unset %s to feed the full corpus.",
            _MAX_EV_TO_GEN_ENV, cap, safe_pool, cap, safe_pool, safe_pool - cap,
            _MAX_EV_TO_GEN_ENV,
        )
    return cap


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


# ── I-perm-011 (#1205): max-over-subqueries relevance (default OFF) ──────────
# `_row_relevance` normalizes overlap by the WHOLE question+protocol token set.
# That denominator scales with question LENGTH: a ~73-content-token multi-part
# research question makes the 0.30 floor demand >=22 exact-word matches, so an
# excellent on-topic top-tier paper whose domain vocabulary (Fusobacterium,
# butyrate, tumorigenesis) doesn't lexically overlap the question's exact words
# (predominant, mitigate, retard) is dropped (drb_76: 597->53; 74 on-topic T1
# shed). The run already decomposes the question into focused sub-queries
# (q1d + STORM). Scoring each row against the BEST-MATCHING sub-query (each with
# a SMALL denominator) lets a row matching ONE facet clear the floor instead of
# being diluted by the other ~60 paragraph tokens.
#
# This is MONOTONIC-UP: it returns max(whole_question_score, best_subquery_score)
# so a row NEVER scores lower than today. Flag-ON therefore keeps a SUPERSET of
# flag-OFF rows — it can only OPEN the throttle, never tighten it.
#
# Flag `PG_SELECT_SUBQUERY_FLOOR` (default OFF). OFF, or no sub-query token sets,
# => the score equals `_row_relevance` exactly (byte-identical selection).


def _subquery_floor_enabled() -> bool:
    """Kill-switch `PG_SELECT_SUBQUERY_FLOOR` (default OFF). OFF => the
    whole-question `_row_relevance` score is used unchanged (byte-identical).

    B1 (b1b10 redesign): the semantic scorer (`PG_RELEVANCE_SCORER=semantic_v2`)
    implies the sub-query floor for the LEXICAL FALLBACK path — it is MONOTONIC-UP
    (max over per-sub-query scores, each with a small denominator) so it can only
    OPEN the floor, never tighten it, mitigating the long-question denominator if
    the embedder is unavailable and selection degrades to the lexical scorer. Safe
    because: (a) the semantic path itself takes the per-sub-query max in cosine
    space, so this only affects the lexical fallback; (b) when semantic_v2 is OFF
    the env still governs => byte-identical default behavior."""
    raw = os.environ.get("PG_SELECT_SUBQUERY_FLOOR", "0").strip().lower()
    if raw not in ("0", "false", "no", "off", ""):
        return True
    return _semantic_scorer_enabled()


def _subquery_token_sets(sub_queries: list[str] | None) -> list[set[str]]:
    """Per-sub-query content-token sets, dropping empties. Returns [] when the
    feature is disabled OR no usable sub-queries are supplied — the empty list
    makes `_row_relevance_facet` fall back to the whole-question score."""
    if not sub_queries or not _subquery_floor_enabled():
        return []
    sets: list[set[str]] = []
    for sq in sub_queries:
        toks = _content_tokens(str(sq or ""))
        if toks:
            sets.append(toks)
    return sets


def _row_relevance_facet(
    row: dict[str, Any],
    question_tokens: set[str],
    protocol_tokens: set[str],
    subquery_token_sets: list[set[str]],
) -> float:
    """Relevance score that takes the MAX of the whole-question score and the
    best per-sub-query score. `subquery_token_sets` empty => identical to
    `_row_relevance` (the only caller-visible difference is the max-up lift when
    the flag is on AND sub-queries are present). Result clamped to [0, 1]."""
    base = _row_relevance(row, question_tokens, protocol_tokens)
    if not subquery_token_sets:
        return base
    text = " ".join(
        str(row.get(k, "") or "") for k in ("statement", "direct_quote")
    )
    ev_toks = _content_tokens(text)
    best = base
    for subq_toks in subquery_token_sets:
        denom = len(subq_toks)
        if denom <= 0:
            continue
        score = len(ev_toks & subq_toks) / denom
        if score > best:
            best = score
    return min(1.0, best)


# ── B1 (b1b10 redesign, 2026-06-14): SEMANTIC relevance scorer ───────────────
# THE BUG (claude_plan.md B1 / DUAL_AGREED_PLAN.md): `_row_relevance` =
# len(overlap)/max(1,len(anchors)) — lexical word-overlap divided by QUESTION
# LENGTH. The denominator scales with question length, so a ~73-token multi-part
# research question makes a 0.30 floor demand >=22 exact-word matches; an on-topic
# T1 paper whose domain vocab (Fusobacterium, butyrate) doesn't lexically match
# the question's words (predominant, mitigate) is dropped (the live 236/589 loss;
# the code comment at `_row_relevance` documents the same drb_76 collapse). No
# single float is safe on that scorer — the SCORER is wrong.
#
# THE FIX: embedding-cosine relevance (synonym/paraphrase aware) reusing the
# ALREADY-LOADED embedder from `prefetch_offtopic_filter` (no new model cost).
# Relevance stays a FILTER (topical, orthogonal axis); credibility/authority/
# retrieval_weight stay the WEIGHT in the sort. This is the relevance HALF of
# §-1.3 (the one axis "weight don't filter" does NOT govern — off-topic is
# useless at any weight); the faithfulness engine is untouched.
#
# GATING: `PG_RELEVANCE_SCORER` (default "lexical"). Only "semantic_v2" activates
# the embedding scorer AND the restored relevance filter. Unset / any other value
# => byte-identical lexical behavior (the `_row_relevance_facet` path).


def _relevance_scorer_mode() -> str:
    """Read `PG_RELEVANCE_SCORER` (default "lexical"). "semantic_v2" => the
    embedding-cosine scorer + restored relevance filter; anything else (incl.
    unset) => the legacy lexical `_row_relevance_facet` scorer, byte-identical."""
    return os.environ.get("PG_RELEVANCE_SCORER", "lexical").strip().lower()


def _semantic_scorer_enabled() -> bool:
    """True iff `PG_RELEVANCE_SCORER == semantic_v2`. Default OFF => byte-identical
    lexical selection (no embedder load, no filter change)."""
    return _relevance_scorer_mode() == "semantic_v2"


def _relevance_drop_ledger_enabled() -> bool:
    """Kill-switch `PG_RELEVANCE_DROP_LEDGER` (default ON under semantic_v2). When
    ON, every below-floor relevance drop is logged with its cosine score + url so
    the operator can audit the filter. Telemetry-only — never changes the keep
    set. Default-ON is harmless when the semantic scorer is OFF (no drops are made
    by the semantic filter on the legacy path)."""
    raw = os.environ.get("PG_RELEVANCE_DROP_LEDGER", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


# Module-level cache: `prefetch_offtopic_filter._load_embedder()` constructs a
# fresh `EmbeddingService` per call (it does NOT use the singleton), so cache the
# handle here to reuse the already-resident MiniLM weights across rows / sections.
# Sentinel `False` = "tried and failed to load" (distinct from `None` = "not yet
# tried") so the loud-fallback path fires exactly once, not on every section.
_SEMANTIC_EMBEDDER_CACHE: Any = None


def _get_semantic_embedder() -> Any:
    """Return the cached embedder (reusing `prefetch_offtopic_filter`'s loader so
    we share the same MiniLM weights / model cost). Returns the embedder, or None
    if it could not be loaded — the caller MUST handle None with a LOUD fallback
    to the lexical scorer (LAW II: no silent degrade)."""
    global _SEMANTIC_EMBEDDER_CACHE
    if _SEMANTIC_EMBEDDER_CACHE is None:
        try:
            from src.polaris_graph.retrieval.prefetch_offtopic_filter import (
                _load_embedder,
            )
            loaded = _load_embedder()
        except Exception as exc:  # import-path failure
            _LOGGER.warning(
                "[select] semantic relevance: embedder import failed (%s) — "
                "the caller will fall back LOUDLY to the lexical scorer.",
                str(exc)[:200],
            )
            loaded = None
        # False sentinel = "load attempted, unavailable" so we don't retry per row.
        _SEMANTIC_EMBEDDER_CACHE = loaded if loaded is not None else False
    return _SEMANTIC_EMBEDDER_CACHE if _SEMANTIC_EMBEDDER_CACHE else None


def _row_embed_text(row: dict[str, Any]) -> str:
    """The text embedded for a row's relevance — statement + direct_quote, the
    SAME fields the lexical scorer reads (`_row_relevance`), so the two scorers
    rank the same content surface."""
    return " ".join(
        str(row.get(k, "") or "") for k in ("statement", "direct_quote")
    )


def _semantic_relevance_scores(
    research_question: str,
    sub_queries: list[str] | None,
    evidence_rows: list[dict[str, Any]],
) -> dict[int, float] | None:
    """Batch embedding-cosine relevance for every row.

    Returns ``{row_index -> max cosine over {research_question} ∪ {sub_queries}}``
    clamped to [0, 1], or ``None`` if the embedder is unavailable / scoring fails
    (the caller then falls back LOUDLY to the lexical scorer — never a silent
    keep-all, LAW II).

    The MAX over the question AND each sub-query is the cosine-space analogue of
    `_row_relevance_facet`'s max-over-subqueries: a row matching ONE focused facet
    clears the floor instead of being diluted. Because the score is cosine (not a
    fraction over the whole-question token set), the long-question denominator that
    buried on-topic papers is gone at the root — but we still take the per-subquery
    max so a multi-facet question routes each row to its best-matching facet. All
    anchors are embedded in the SAME cosine space (no scale-mixing — the silent bug
    `_row_relevance_facet` would have if base became cosine while subquery stayed
    lexical).
    """
    embedder = _get_semantic_embedder()
    if embedder is None:
        return None
    anchors: list[str] = []
    q = (research_question or "").strip()
    if q:
        anchors.append(q)
    for sq in sub_queries or []:
        s = str(sq or "").strip()
        if s:
            anchors.append(s)
    if not anchors:
        # No usable anchor text — cannot score semantically; fall back loudly.
        _LOGGER.warning(
            "[select] semantic relevance: empty research_question AND no "
            "sub-queries — falling back to the lexical scorer."
        )
        return None
    row_texts = [_row_embed_text(row) for row in evidence_rows]
    try:
        from src.polaris_graph.retrieval.prefetch_offtopic_filter import (
            _similarity_scores,
        )
        # One embed pass per anchor over ALL row texts (batched inside
        # `_similarity_scores`); take the per-row MAX across anchors. Rows are
        # embedded once per anchor (anchors are few: 1 question + a handful of
        # sub-queries), NEVER once per row.
        per_anchor: list[list[float]] = [
            _similarity_scores(embedder, anchor, row_texts) for anchor in anchors
        ]
    except Exception as exc:
        _LOGGER.warning(
            "[select] semantic relevance scoring failed (%s) — falling back to "
            "the lexical scorer.",
            str(exc)[:200],
        )
        return None
    scores: dict[int, float] = {}
    for i in range(len(evidence_rows)):
        best = 0.0
        for sims in per_anchor:
            if i < len(sims):
                v = sims[i]
                if v > best:
                    best = v
        # Clamp to [0, 1]: cosine can be negative (off-topic); a negative score is
        # floored to 0.0 so it reads as "no relevance" and a row with no embeddable
        # text (empty statement+quote) scores 0.0 rather than being laundered up.
        scores[i] = min(1.0, max(0.0, float(best)))
    return scores


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


# ── I-perm-003 (#1197): corpus-size-scaled evidence-selection budget ─────────
# The generator-facing cap is a FIXED `max_rows` (PG_LIVE_MAX_EV_TO_GEN, default
# 20 — #1070/#1078). At 1000-URL retrieval the fixed cap truncates the pool to a
# constant slice regardless of how much best-ranked evidence the corpus actually
# holds. This PREVENTATIVE knob scales the selection budget WITH the pool size so
# a larger corpus feeds proportionally more BEST-ranked rows (the existing
# tier-balanced + relevance/recency truncation already picks best-ranked, never
# first-N — this only raises the budget it operates under).
#
# HONEST SCOPE: on the beatboth8 corpus the selector drops 0 sources (the ~90%
# loss is UPSTREAM extraction, owned by I-perm-007), so this changes nothing
# there. It is a forward guard for when the upstream pool is genuinely large.
#
# DEFAULT OFF. When `PG_SWEEP_SELECTION_SCALE` is unset/0/false/no/off the helper
# returns `base_max_rows` UNCHANGED and `select_evidence_for_generation` is
# byte-identical to the prior behaviour (no reassignment, no telemetry).
#
# FLOOR semantics: effective = max(base_max_rows, ceil(pool_size * frac)),
# optionally clamped to a ceiling. The `max(...)` guarantees scaling NEVER drops
# the budget below the operator/code cap (a small pool with a low frac keeps the
# existing cap — never a regression).
_SELECTION_SCALE_FRAC_DEFAULT = 0.30
# 0 = no ceiling (scale unbounded with the pool). A positive value clamps the
# scaled budget so an enormous pool can't blow past an operator-set ceiling.
_SELECTION_SCALE_CEILING_DEFAULT = 0


def _selection_scale_enabled() -> bool:
    """Flag `PG_SWEEP_SELECTION_SCALE` (default OFF). ON only on explicit
    truthy ('1'/'true'/'yes'/'on'). OFF → byte-identical prior selection AND
    no scaling telemetry. Inverse default of `_env_flag_on` ON-by-default."""
    raw = os.environ.get("PG_SWEEP_SELECTION_SCALE", "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _selection_scale_frac() -> float:
    """Budget-per-pool-row fraction `PG_SWEEP_SELECTION_SCALE_FRAC`
    (default 0.30). Non-positive / unparseable → default (FAIL SOFT to a sane
    positive fraction; a 0 frac would make scaling a no-op via the floor)."""
    raw = os.environ.get("PG_SWEEP_SELECTION_SCALE_FRAC", "").strip()
    if not raw:
        return _SELECTION_SCALE_FRAC_DEFAULT
    try:
        frac = float(raw)
    except (ValueError, TypeError):
        return _SELECTION_SCALE_FRAC_DEFAULT
    # Reject non-finite (inf/nan): a positive `inf` parses but would OverflowError in
    # `math.ceil(pool_size * frac)` (Codex iter-1 P2). FAIL SOFT to the sane default.
    return frac if (frac > 0 and math.isfinite(frac)) else _SELECTION_SCALE_FRAC_DEFAULT


def _selection_scale_ceiling() -> int:
    """Optional absolute ceiling `PG_SWEEP_SELECTION_SCALE_CEILING`
    (default 0 = no ceiling). Clamps the scaled budget so an enormous pool can't
    overshoot an operator cap. Values <= 0 / unparseable → no ceiling."""
    raw = os.environ.get("PG_SWEEP_SELECTION_SCALE_CEILING", "").strip()
    if not raw:
        return _SELECTION_SCALE_CEILING_DEFAULT
    try:
        ceiling = int(raw)
    except (ValueError, TypeError):
        return _SELECTION_SCALE_CEILING_DEFAULT
    return ceiling if ceiling > 0 else _SELECTION_SCALE_CEILING_DEFAULT


def _scaled_max_rows(pool_size: int, base_max_rows: int) -> tuple[int, str | None]:
    """Corpus-size-scaled selection budget (I-perm-003, default OFF).

    Returns ``(effective_max_rows, note)``. When the flag is OFF, returns
    ``(base_max_rows, None)`` — the caller MUST treat that as a byte-identical
    no-op (no telemetry note appended). When ON, returns the FLOOR-guarded scaled
    budget ``max(base_max_rows, ceil(pool_size * frac))`` (optionally clamped to a
    ceiling) plus a single telemetry string for the selection notes.
    """
    if not _selection_scale_enabled():
        return base_max_rows, None
    frac = _selection_scale_frac()
    ceiling = _selection_scale_ceiling()
    scaled = math.ceil(pool_size * frac)
    effective = max(base_max_rows, scaled)
    clamped = False
    if ceiling > 0 and effective > ceiling:
        # Never below the base cap even when the ceiling is < base (floor wins).
        effective = max(base_max_rows, ceiling)
        clamped = True
    note = (
        f"selection_scale pool={pool_size} frac={frac} "
        f"base_max_rows={base_max_rows} scaled={scaled} "
        f"effective={effective} ceiling={ceiling or 'none'}"
        f"{' clamped' if clamped else ''}"
    )
    return effective, note


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


# ── I-perm-023 (#1215): diversity-aware selection (constrained-greedy) ────────
# A default-OFF forward guard that diversifies the SELECTED set on the coverage
# axes the existing floor stack does NOT already cover. Entity custody is owned by
# the M-42e/M-51 anchor-primary floors, mechanism by the M-42c floor, the 1-per
# present-jurisdiction reservation by M-41d — so this pass adds SAFETY-CATEGORY +
# EVIDENCE-CLASS coverage (plus jurisdiction diversity BEYOND the M-41d 1-per floor)
# via the SAME post-floor same-tier swap mechanism as the #956 passes. It NEVER
# touches a floor / quota / protected row, so floor parity is guaranteed BY
# CONSTRUCTION. Swaps are COVERAGE-MONOTONE: a swap fires only when the incoming row
# adds a NOVEL bucket AND the evicted row's every bucket stays covered by another
# selected row, so distinct coverage can only INCREASE, never drop an axis.
# Faithfulness (Codex design-gate iter-2): selection only changes the generator's
# candidate menu; the effective generator evidence_pool starts from selected_rows
# (and may add sanctioned prepends + M-52 live pulls), and strict_verify / the
# 4-role evaluator / D8 re-check every sentence against the cited span unchanged —
# so a swap can at worst trade one verifiable row for another, NEVER admit
# unsupported prose. No-op at drb_76 scale (pool<=cap returns via the short-pool
# branch before this region runs).

# Safety-category taxonomy (FDA/DailyMed SPL labeling sections). Keyword -> category,
# preference-only (a miss costs diversity, never faithfulness). Versioned constant.
_GREEDY_SAFETY_CATEGORIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("boxed_warning", ("boxed warning", "black box warning", "black-box warning")),
    ("contraindication", ("contraindication", "contraindicated")),
    ("warning_precaution", ("warnings and precautions", "warning", "precaution")),
    ("adverse_reaction", ("adverse reaction", "adverse event", "adverse effect",
                          "side effect")),
    ("drug_interaction", ("drug interaction", "drug-drug interaction")),
    ("pregnancy_lactation", ("pregnancy", "lactation", "breastfeeding", "teratogen")),
    ("hepatic_renal", ("hepatotoxicity", "hepatic impairment", "renal impairment",
                       "nephrotox")),
    ("hypoglycemia", ("hypoglycemia", "hypoglycaemia")),
    ("overdose", ("overdose", "overdosage")),
)

# Evidence-class taxonomy. Keyword -> class, preference-only. Versioned constant.
_GREEDY_EVIDENCE_CLASSES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("meta_analysis", ("meta-analysis", "meta analysis", "systematic review",
                       "cochrane")),
    ("rct", ("randomized", "randomised", "double-blind", "placebo-controlled",
             "phase 3 trial", "phase iii")),
    ("guideline", ("guideline", "consensus statement", "recommendation",
                   "position statement")),
    ("real_world", ("real-world", "observational", "registry", "cohort study",
                    "case-control", "post-marketing")),
    ("regulatory", ("prescribing information", "package insert",
                    "summary of product characteristics", "smpc")),
)

_GREEDY_MAX_SWAPS_DEFAULT = 24
_GREEDY_AXES_DEFAULT = ("safety", "class", "jurisdiction")
_GREEDY_VALID_AXES = frozenset(_GREEDY_AXES_DEFAULT)


def _greedy_match_category(
    row: dict[str, Any], taxonomy: tuple[tuple[str, tuple[str, ...]], ...],
) -> str | None:
    """First taxonomy category whose keyword appears in the row's title/statement/
    quote (case-insensitive substring), in taxonomy order. None if no match."""
    combined = " ".join((
        _row_title_text(row),
        str(row.get("statement") or ""),
        str(row.get("direct_quote") or ""),
    )).lower()
    for category, tokens in taxonomy:
        if any(tok in combined for tok in tokens):
            return category
    return None


def _greedy_active_axes() -> tuple[str, ...]:
    """Call-time active axis set (env override PG_GREEDY_AXES, default safety/class/
    jurisdiction). Unknown axis names are ignored; empty/invalid -> the default."""
    raw = os.environ.get("PG_GREEDY_AXES", "").strip()
    if not raw:
        return _GREEDY_AXES_DEFAULT
    axes = tuple(a for a in (x.strip() for x in raw.split(",")) if a in _GREEDY_VALID_AXES)
    return axes or _GREEDY_AXES_DEFAULT


def _row_coverage_buckets(
    row: dict[str, Any], axes: tuple[str, ...],
) -> frozenset[tuple[str, str]]:
    """The (axis, value) coverage buckets a row belongs to across the ACTIVE axes.
    safety_category / evidence_class are keyword-derived; jurisdiction reuses the
    existing M-41d host predicate. A row with no axis value contributes nothing."""
    out: set[tuple[str, str]] = set()
    if "safety" in axes:
        s = _greedy_match_category(row, _GREEDY_SAFETY_CATEGORIES)
        if s:
            out.add(("safety", s))
    if "class" in axes:
        c = _greedy_match_category(row, _GREEDY_EVIDENCE_CLASSES)
        if c:
            out.add(("class", c))
    if "jurisdiction" in axes:
        j = _row_jurisdiction(row)
        if j:
            out.add(("jurisdiction", j))
    return frozenset(out)


def _constrained_greedy_config() -> tuple[bool, int]:
    """Call-time config for the I-perm-023 diversity pass. DEFAULT OFF (NOT
    `_env_flag_on`, which defaults ON — Codex design-gate iter-2 P2.3) -> when unset
    the pass never runs and selected/notes/to_dict stay byte-identical. Returns
    (enabled, max_swaps)."""
    raw = os.environ.get("PG_SELECT_CONSTRAINED_GREEDY", "0").strip().lower()
    enabled = raw in ("1", "true", "yes", "on")
    raw_n = os.environ.get("PG_GREEDY_MAX_SWAPS", "").strip()
    try:
        n = int(raw_n) if raw_n else _GREEDY_MAX_SWAPS_DEFAULT
    except (ValueError, TypeError):
        n = _GREEDY_MAX_SWAPS_DEFAULT
    return enabled, max(0, n)


def _apply_domain_cap(
    selected: list[tuple[int, float, str, dict[str, Any]]],
    scored: list[tuple[int, float, str, dict[str, Any]]],
    protected_ids: set[int],
    cap: int,
    rec_enabled: bool,
    rec_eps: float,
) -> tuple[int, set[int]]:
    """Soft per-domain cap via same-tier swaps. An over-cap domain's NON-protected
    slack rows (worst-priority first) are replaced by the best same-tier pool row
    of an under-cap domain. YIELDS (stops) when no valid same-tier replacement
    exists — never leaves a slot empty, drops a tier below quota, or evicts a
    protected/reserved row. Returns (rows_moved, brought_in_ids) — the brought-in
    ids let the caller protect them from a later pass (Codex design-gate iter-2
    P2.2: the I-perm-023 greedy pass must not undo this domain-diversity pass)."""
    moved = 0
    brought_in: set[int] = set()
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
                brought_in.add(id(best))
                selected_ids.discard(id(old))
                selected_ids.add(id(best))
                domain_count[dom] -= 1
                domain_count[_row_domain(best[3])] = domain_count.get(_row_domain(best[3]), 0) + 1
                moved += 1
                swapped = True
                break
            if not swapped:
                break  # yield: no same-tier under-cap replacement available
    return moved, brought_in


def _apply_coverage_diversification(
    selected: list[tuple[int, float, str, dict[str, Any]]],
    scored: list[tuple[int, float, str, dict[str, Any]]],
    protected_ids: set[int],
    max_swaps: int,
    axes: tuple[str, ...],
    rec_enabled: bool,
    rec_eps: float,
    domain_cap: int | None = None,
) -> tuple[int, dict[str, Any]]:
    """I-perm-023 (#1215) constrained-greedy diversity pass. COVERAGE-MONOTONE
    same-tier swaps on post-floor slack: a swap fires only when a non-selected
    same-tier candidate adds a NOVEL coverage bucket AND the evicted (non-protected)
    selected row's every bucket remains covered by another selected row — so the
    pass can only INCREASE distinct coverage, never drop an axis or touch a floor.
    When ``domain_cap`` is set (the active #956 per-domain soft cap) a swap is ALSO
    rejected if it would raise the candidate's source domain ABOVE that cap (Codex
    diff-gate iter-1 P1: the greedy pass must not regress the domain-diversity pass
    by pulling an at-cap domain back over the cap). Deterministic (total-ordered
    tie-breaks); bounded by max_swaps. Returns (swaps, telemetry)."""
    selected_ids = {id(it) for it in selected}
    pool_by_tier: dict[str, list] = defaultdict(list)
    for it in scored:
        if id(it) not in selected_ids:
            pool_by_tier[it[2]].append(it)
    # live (axis, value) -> count of selected rows covering it
    bucket_count: Counter = Counter()
    for it in selected:
        for b in _row_coverage_buckets(it[3], axes):
            bucket_count[b] += 1
    # live per-domain count (only consulted when domain_cap is enforced)
    domain_count: Counter = Counter(_row_domain(it[3]) for it in selected)
    brought_in: set[int] = set()
    swaps = 0
    while swaps < max_swaps:
        best = None  # (sort_key, cand, evict_pos, tier, cand_buckets)
        for tier, pool in pool_by_tier.items():
            for cand in pool:
                if id(cand) in brought_in:
                    continue
                cb = _row_coverage_buckets(cand[3], axes)
                novel = sum(1 for b in cb if bucket_count.get(b, 0) == 0)
                if novel == 0:
                    continue
                # same-tier, non-protected, not-brought-in, REDUNDANT evictable:
                # every bucket it holds is covered by >=2 selected rows, so removing
                # it keeps each of those buckets covered (>=1) -> coverage-monotone.
                evictables = [
                    i for i, it in enumerate(selected)
                    if it[2] == tier
                    and id(it) not in protected_ids
                    and id(it) not in brought_in
                    and all(bucket_count.get(b, 0) >= 2
                            for b in _row_coverage_buckets(it[3], axes))
                ]
                # Codex diff-gate iter-1 P1: respect the #956 domain cap. Admitting
                # `cand` raises its domain by 1 UNLESS the evicted row is the SAME
                # domain (net-zero). If cand's domain is already at/over the cap, the
                # ONLY domain-feasible swap evicts a same-domain row.
                if domain_cap is not None:
                    cand_dom = _row_domain(cand[3])
                    if domain_count.get(cand_dom, 0) >= domain_cap:
                        evictables = [
                            i for i in evictables
                            if _row_domain(selected[i][3]) == cand_dom
                        ]
                if not evictables:
                    continue
                # worst evictable (Codex design-gate iter-2 P2.4): highest
                # redundancy, then lowest relevance, then highest original idx.
                evict_pos = max(evictables, key=lambda i: (
                    sum(bucket_count.get(b, 0) - 1
                        for b in _row_coverage_buckets(selected[i][3], axes)),
                    -selected[i][1],
                    selected[i][0],
                ))
                # candidate preference: most novel buckets, then best priority,
                # then original index (total order, deterministic).
                key = (-novel, _priority_sort_key(cand, rec_enabled, rec_eps), cand[0])
                if best is None or key < best[0]:
                    best = (key, cand, evict_pos, tier, cb)
        if best is None:
            break
        _, cand, evict_pos, tier, cb = best
        old = selected[evict_pos]
        for b in _row_coverage_buckets(old[3], axes):
            bucket_count[b] -= 1
        domain_count[_row_domain(old[3])] -= 1
        selected[evict_pos] = cand
        for b in cb:
            bucket_count[b] += 1
        domain_count[_row_domain(cand[3])] = domain_count.get(_row_domain(cand[3]), 0) + 1
        selected_ids.discard(id(old))
        selected_ids.add(id(cand))
        brought_in.add(id(cand))
        pool_by_tier[tier] = [p for p in pool_by_tier[tier] if id(p) != id(cand)]
        swaps += 1
    # telemetry — DIAGNOSTIC only (distinct-bucket counts are NOT a §-1.1 quality /
    # superiority signal; unique-source counts are banned as quality).
    per_axis: dict[str, int] = {}
    for (axis, _val), c in bucket_count.items():
        if c > 0:
            per_axis[axis] = per_axis.get(axis, 0) + 1
    distinct_buckets = sum(1 for c in bucket_count.values() if c > 0)
    diversity_score = round(distinct_buckets / len(selected), 4) if selected else 0.0
    return swaps, {
        "swaps": swaps,
        "distinct_buckets": distinct_buckets,
        "per_axis_buckets": per_axis,
        "diversity_score": diversity_score,
        "axes": list(axes),
    }


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


# ── I-pipe-003 (#1228): honest relevance-floor drop telemetry + anchor preserve ─
# Forensic (dual Claude+Codex 2026-06-12): PG_RELEVANCE_FLOOR=0.30 cut 236 of 589
# rows (589 -> 353) but the operator-facing `[select] ... dropped=0` hid it. Root
# cause: `_relevance_floor_selection` ALREADY reports the real drop in
# `dropped_count` (len(scored) - len(kept)), but the downstream capped-finding-dedup
# pass in run_honest_sweep_r3.py REASSIGNS the EvidenceSelection to a SECOND
# `relevance_floor=None` call whose short-pool path legitimately returns
# `dropped_count=0` — laundering the floor cut out of the surfaced telemetry. The
# operator-facing line fix is cross-file (run_honest_sweep_r3.py:4723); the in-file
# fix here EMITS the real floor-cut count at the moment the cut happens, which
# survives the downstream reassignment.
#
# PG_RELEVANCE_HONEST_DROP (default ON): log the ACTUAL number of rows cut by the
#   floor (never 0 when cuts occurred). `=0` reverts to the prior no-log behavior.
#   Telemetry-only — does NOT change `dropped_count`, `notes`, or which rows are
#   kept, so flag value never alters the selection itself.
# PG_RELEVANCE_PRESERVE_ANCHORS (default OFF): when on, never cut a marquee /
#   required-entity row even if it scores below the floor. This EXTENDS the existing
#   `primary_trial_anchors` floor-exemption (line ~1342) to the DISTINCT marquee
#   marker set (`is_marquee` / `required_entity` / `anchor_seed` / `is_anchor` /
#   `entity_anchor` / `marquee` flags, or a `required_entity`/`anchor` seed_source /
#   query_origin — mirrors multi_section_generator._breadth_row_is_marquee, I-pipe-006
#   #1231). OFF => byte-identical keep set. Faithfulness-safe: this can only ADD an
#   already-fetched row to the candidate pool — strict_verify / NLI / 4-role still
#   gate every emitted sentence; no unverified claim is fabricated to fill a gap.


def _relevance_honest_drop_enabled() -> bool:
    """Kill-switch `PG_RELEVANCE_HONEST_DROP` (default ON). When ON, the
    relevance-floor selection logs the ACTUAL number of rows cut by the floor.
    `=0`/`false`/`off`/`no` reverts to the prior no-log behavior. Telemetry-only:
    NEVER changes which rows are kept or the returned `dropped_count`."""
    raw = os.environ.get("PG_RELEVANCE_HONEST_DROP", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _relevance_preserve_anchors_enabled() -> bool:
    """Kill-switch `PG_RELEVANCE_PRESERVE_ANCHORS` (default OFF). When ON, a
    marquee / required-entity row is floor-EXEMPT (kept even below the floor),
    extending the existing primary-anchor exemption to the distinct marquee marker
    set. OFF => byte-identical keep set (the prior behavior)."""
    raw = os.environ.get("PG_RELEVANCE_PRESERVE_ANCHORS", "0").strip().lower()
    return raw not in ("0", "false", "no", "off", "")


def _row_is_marquee_anchor(row: dict[str, Any]) -> bool:
    """True iff an evidence row was contributed by the required-entity / anchor
    lane and therefore is a marquee primary source that must not be floor-cut.

    Detection uses ONLY existing evidence-row fields (no schema invention) and
    mirrors `multi_section_generator._breadth_row_is_marquee` (I-pipe-006 #1231):
    a truthy `is_marquee` / `required_entity` / `anchor_seed` / `is_anchor` /
    `entity_anchor` / `marquee` flag, OR a `required_entity`/`anchor` substring in
    `seed_source` / `query_origin` / `seed_query_origin`. This is a DISTINCT marker
    set from `primary_trial_anchors` (which `_m42e_detect_primary_for_anchor` matches
    by RCT name/title) — a required-entity row can score below floor AND fail the
    primary-anchor name match, so without this exemption it would be silently cut."""
    if not isinstance(row, dict):
        return False
    for flag in ("is_marquee", "required_entity", "anchor_seed", "is_anchor",
                 "entity_anchor", "marquee"):
        if row.get(flag):
            return True
    seed_source = str(row.get("seed_source") or "").lower()
    if "required_entity" in seed_source or "anchor" in seed_source:
        return True
    for origin_key in ("query_origin", "seed_query_origin"):
        origin = str(row.get(origin_key) or "").lower()
        if "required_entity" in origin or "anchor" in origin:
            return True
    return False


# ── I-scope-001 (#1244): low-cred domain denylist (gate 1, pure, no LLM) ───────
# Grounded diagnosis (do not re-derive): the drb_72 breadth run cited 76 distinct
# sources, 0 fabrication, but ~9 were contamination — 3 of them low-credibility
# domains (facebook.com, scribd.com, en.wikipedia.org) that the tier system
# mis-tiered and the relevance floor passed on shared generic words. The tier
# system rates CREDIBILITY but cannot demote a junk-host article that happens to
# share content words with the topic. This gate drops candidate rows whose source
# netloc matches an operator-supplied denylist. It is DEFAULT-OFF: the env var
# `PG_SCOPE_DENYLIST_DOMAINS` is empty by default, so `_scope_denylist_domains()`
# returns () and `_apply_scope_denylist` is a byte-identical no-op (returns the
# input list unchanged). Suggested-but-NOT-hardcoded-on default list (operator
# pastes it into the env when desired):
#   facebook.com,scribd.com,en.wikipedia.org,blogspot,wordpress,reddit,quora,medium.com
# Deliberately does NOT denylist .gov / .edu / nber / doi.org (credibility is not
# journal-only; gov + working-papers + institutes are kept). Marquee /
# required-entity anchors are EXEMPT (never dropped). Faithfulness-safe: selection
# can only SUBTRACT a candidate before generation; strict_verify / NLI / 4-role /
# provenance are unchanged, and subtraction cannot fabricate.


def _scope_denylist_domains() -> tuple[str, ...]:
    """Parse `PG_SCOPE_DENYLIST_DOMAINS` (comma-separated, default empty = OFF).
    Each entry is lowercased + stripped; blank entries dropped. Empty env =>
    `()` => the denylist gate is a byte-identical no-op."""
    raw = os.environ.get("PG_SCOPE_DENYLIST_DOMAINS", "").strip()
    if not raw:
        return ()
    return tuple(
        entry.strip().lower()
        for entry in raw.split(",")
        if entry.strip()
    )


def _row_netloc(row: dict[str, Any]) -> str:
    """Lowercased hostname for an evidence row's source URL. Reuses the
    urlparse pattern already used elsewhere in this module (lines ~197/751)."""
    url = (row.get("source_url") or row.get("url") or "").strip().lower()
    if not url:
        return ""
    from urllib.parse import urlparse
    try:
        host = urlparse(
            url if "://" in url else f"http://{url}"
        ).hostname or ""
    except Exception:
        host = ""
    return host.lower()


def _netloc_matches_denylist(netloc: str, denylist: tuple[str, ...]) -> bool:
    """True iff a netloc matches a denylist entry.

    Dotted entries (e.g. `facebook.com`, `en.wikipedia.org`) match on EXACT
    netloc OR a `.`+entry suffix (so `m.facebook.com` matches but
    `facebook.com.evil.org` does NOT). Bare-token entries (e.g. `blogspot`,
    `reddit`) match on substring-in-netloc (catches `foo.blogspot.com`)."""
    if not netloc or not denylist:
        return False
    for entry in denylist:
        if "." in entry:
            if netloc == entry or netloc.endswith("." + entry):
                return True
        else:
            if entry in netloc:
                return True
    return False


def _apply_scope_denylist(
    scored: list[tuple[int, float, str, dict[str, Any]]],
    primary_trial_anchors: list[str] | None,
) -> tuple[list[tuple[int, float, str, dict[str, Any]]], int, list[str]]:
    """Drop scored rows whose netloc matches `PG_SCOPE_DENYLIST_DOMAINS`.

    EXEMPT: marquee / required-entity anchors AND named-trial primary anchors
    (the same exemption set as the relevance floor). Returns
    `(kept_scored, n_dropped, dropped_netlocs)`. When the env var is empty the
    denylist is `()` and the input is returned UNCHANGED (byte-identical no-op).
    Pure — does not mutate the caller's rows."""
    denylist = _scope_denylist_domains()
    if not denylist:
        return scored, 0, []
    anchors = list(primary_trial_anchors or [])

    def _is_exempt(row: dict[str, Any]) -> bool:
        if _row_is_marquee_anchor(row):
            return True
        return any(_m42e_detect_primary_for_anchor(row, a) for a in anchors)

    # I-arch-002 (#1246) P-W2scope: under the master redesign flag the denylist becomes
    # a credibility-CLASS WEIGHT, not a DROP (DNA §-1.3 — social/junk hosts STAY at low
    # weight; they sometimes report a real journal). The matched row is KEPT, stamped
    # `scope_denylist_demoted` + a low credibility class, and surfaced per-citation.
    # OFF => the exact prior `continue`-drop => byte-identical.
    _cred_redesign = _credibility_redesign_enabled()
    kept: list[tuple[int, float, str, dict[str, Any]]] = []
    dropped_netlocs: list[str] = []
    for item in scored:
        row = item[3]
        netloc = _row_netloc(row)
        if _netloc_matches_denylist(netloc, denylist) and not _is_exempt(row):
            if _cred_redesign:
                demoted = dict(row)
                demoted["scope_denylist_demoted"] = True
                demoted["credibility_class"] = "low_denylist"
                kept.append((item[0], item[1], item[2], demoted))
                continue
            dropped_netlocs.append(netloc)
            continue
        kept.append(item)
    return kept, len(dropped_netlocs), dropped_netlocs


# ── I-scope-001 (#1244): arXiv -> journal version preference (gate 3, pure) ────
# Grounded diagnosis: 2 of the 9 drb_72 contaminants were arXiv/preprint twins of
# a paper that ALSO appears as a published journal/DOI row — the citation should
# prefer the published version. This gate, when ON (`PG_SCOPE_PREFER_JOURNAL`,
# default OFF), groups rows by NORMALIZED title and, for any title that appears as
# BOTH an arxiv.org row AND a non-arxiv journal/DOI row, drops the arXiv twin(s)
# and keeps the journal row. An arXiv row with NO journal twin is NEVER dropped
# (two arXiv versions with no journal twin both survive). Default OFF => no-op.
# Faithfulness-safe (subtract-only, see gate-1 note).


def _prefer_journal_enabled() -> bool:
    """Kill-switch `PG_SCOPE_PREFER_JOURNAL` (default OFF). When ON, an arXiv
    twin of a journal/DOI row is dropped in favor of the published version."""
    raw = os.environ.get("PG_SCOPE_PREFER_JOURNAL", "0").strip().lower()
    return raw not in ("0", "false", "no", "off", "")


def _normalize_title_for_twin(title: str) -> str:
    """Normalize a title for arXiv<->journal twin matching: lowercase,
    collapse all non-alphanumeric runs to single spaces, strip. Empty in =>
    empty out (an untitled row can never twin-match)."""
    if not title:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def _row_is_arxiv(row: dict[str, Any]) -> bool:
    """True iff the row's source host is arxiv.org (preprint host)."""
    return "arxiv.org" in _row_netloc(row)


def _row_has_journal_doi(row: dict[str, Any]) -> bool:
    """True iff the row looks like a published journal/DOI version (non-arXiv):
    a non-arxiv host AND a DOI marker (doi field, or `doi.org`/`/10.` in URL).
    Conservative — a row that is neither arXiv nor a clear DOI/journal row is
    treated as NEITHER twin side, so it is never used to evict an arXiv row."""
    if _row_is_arxiv(row):
        return False
    if row.get("doi"):
        return True
    url = (row.get("source_url") or row.get("url") or "").lower()
    return "doi.org" in url or "/10." in url


def prefer_journal_over_arxiv(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int, list[str]]:
    """Drop arXiv rows that have a journal/DOI twin (same normalized title).

    Returns `(kept_rows, n_dropped, dropped_titles)`. Pure — does not mutate
    rows; preserves input order of the kept rows. Never drops an arXiv row
    whose normalized title has no non-arXiv journal/DOI twin in the pool."""
    # Build the set of normalized titles that have a journal/DOI representative.
    journal_titles: set[str] = set()
    for row in rows:
        if _row_has_journal_doi(row):
            norm = _normalize_title_for_twin(_row_title_text(row))
            if norm:
                journal_titles.add(norm)
    if not journal_titles:
        return list(rows), 0, []
    # I-arch-002 (#1246) P-W2scope: under the master redesign flag the arXiv twin is
    # CONSOLIDATED as a VERSION of the same source (CONSOLIDATE-don't-DROP, DNA §-1.3),
    # not dropped — the preprint + journal both stay (journal is the preferred rep).
    # OFF => the exact prior twin-drop => byte-identical.
    _cred_redesign = _credibility_redesign_enabled()
    kept: list[dict[str, Any]] = []
    dropped_titles: list[str] = []
    for row in rows:
        if _row_is_arxiv(row):
            norm = _normalize_title_for_twin(_row_title_text(row))
            if norm and norm in journal_titles:
                if _cred_redesign:
                    twin = dict(row)
                    twin["arxiv_journal_twin"] = True
                    twin["preferred_version"] = "journal"
                    kept.append(twin)
                    continue
                dropped_titles.append(_row_title_text(row) or "(no title)")
                continue
        kept.append(row)
    return kept, len(dropped_titles), dropped_titles


def _credibility_redesign_enabled() -> bool:
    """I-arch-002 (#1246): master switch for the WEIGHT-AND-CONSOLIDATE redesign
    (CLAUDE.md §-1.3). Default OFF — when unset, every redesign branch below stays
    on the legacy DROP/CAP path, so selection is byte-identical. Read from
    ``PG_SWEEP_CREDIBILITY_REDESIGN`` (the single master flag that governs the whole
    migration; the selection boundary previously had ZERO flag influence)."""
    return os.environ.get("PG_SWEEP_CREDIBILITY_REDESIGN", "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _relevance_floor_selection(
    *,
    scored: list[tuple[int, float, str, dict[str, Any]]],
    relevance_floor: float,
    full_counts: dict[str, int],
    primary_trial_anchors: list[str] | None,
    semantic_mode: bool = False,
    semantic_requested: bool = False,
    semantic_fell_back: bool = False,
) -> EvidenceSelection:
    """I-meta-005 Phase 5 (#989): relevance-floor selection (no max_rows cap).

    Keep EVERY row whose lexical relevance >= ``relevance_floor``, PLUS any row
    matching a primary trial anchor (floor-EXEMPT — a relevant primary RCT must
    never be dropped on a low lexical score). Ranked by ``relevance x authority``
    (authority = the row's ``authority_score`` sidecar, default 1.0). Each kept
    row is stamped with the additive ``selection_relevance`` float so
    ``finding_dedup`` picks representatives on the IDENTICAL score (no recompute
    drift). Pure; returns SHALLOW COPIES (never mutates the caller's rows).

    B1 (b1b10 redesign): when ``semantic_mode`` (the score in each tuple is the
    embedding-cosine relevance, PG_RELEVANCE_SCORER=semantic_v2), the keep set is
    the RESTORED relevance FILTER (``score >= floor OR floor-exempt``) — reversing
    the credibility-redesign keep-all over-correction that had let off-topic noise
    through. Relevance FILTERS; credibility/authority/retrieval_weight WEIGHT the
    sort (orthogonal axes). ``semantic_requested`` / ``semantic_fell_back`` are
    telemetry only. When ``semantic_mode`` is False every branch is byte-identical
    to the prior behavior (the lexical keep-all under PG_SWEEP_CREDIBILITY_REDESIGN,
    or the lexical floor filter otherwise).
    """
    # I-scope-001 (#1244) gate 1: low-cred domain denylist. Default-OFF — when
    # `PG_SCOPE_DENYLIST_DOMAINS` is empty, `_apply_scope_denylist` returns
    # `scored` UNCHANGED (byte-identical), so the keep/sort below is exactly the
    # prior behavior. Marquee / required-entity / primary-anchor rows are EXEMPT.
    scored, _denylist_dropped, _denylist_netlocs = _apply_scope_denylist(
        scored, primary_trial_anchors
    )
    if _denylist_dropped:
        _LOGGER.info(
            "[scope] denylist dropped %d low-cred source(s): %s",
            _denylist_dropped,
            "; ".join(sorted(set(_denylist_netlocs))),
        )

    anchors = list(primary_trial_anchors or [])

    def _is_anchor(row: dict[str, Any]) -> bool:
        return any(_m42e_detect_primary_for_anchor(row, a) for a in anchors)

    def _authority(row: dict[str, Any]) -> float:
        # Default 1.0 ONLY when authority_score is absent/None — an EXPLICIT 0.0
        # (genuinely zero-authority row) must rank as 0.0, not be laundered to 1.0
        # by a falsy `or` (Codex diff-gate P2).
        a = row.get("authority_score")
        return 1.0 if a is None else float(a)

    # F15 (GH #1245 / D11, §-1.3 WEIGHT-not-FILTER): honor the per-row
    # `retrieval_weight` set by live_retriever's DOWN-WEIGHT path (content-starved
    # / landing-page sources kept in the pool at a low weight rather than hard-
    # dropped). It multiplies the ranking score so a down-weighted source sorts
    # LAST while still being present — the source flows to composition carrying
    # its weight (§-1.3), never silently filtered. Default 1.0 ONLY when absent/
    # None (a real full-text row), so a normal row is byte-identical. ON-path
    # only: a down-weighted row only exists when the redesign flag is set.
    def _retrieval_weight(row: dict[str, Any]) -> float:
        w = row.get("retrieval_weight")
        return 1.0 if w is None else float(w)

    # I-pipe-003 (#1228): PG_RELEVANCE_PRESERVE_ANCHORS (default OFF). When ON, a
    # below-floor marquee / required-entity row is also floor-EXEMPT. OFF =>
    # `_preserve_marquee` is False => predicate is byte-identical to the prior
    # `item[1] >= relevance_floor or _is_anchor(item[3])`.
    _preserve_marquee = _relevance_preserve_anchors_enabled()

    def _floor_exempt(row: dict[str, Any]) -> bool:
        if _is_anchor(row):
            return True
        if _preserve_marquee and _row_is_marquee_anchor(row):
            return True
        return False

    # I-arch-002 (#1246) P-W1 — WEIGHT, don't FILTER (DNA §-1.3). Under the master
    # redesign flag the relevance "floor" stopped HARD-DROPPING below-floor rows:
    # every scored row was KEPT carrying its LEXICAL relevance score. That keep-all
    # was right for CREDIBILITY (a low-tier source may carry a real finding) but
    # WRONG for topical RELEVANCE — it let off-topic noise into the pot because the
    # lexical scorer was the only filter and it was broken (the long-question
    # denominator buried on-topic T1 papers, so keep-all was the lesser evil).
    #
    # B1 (b1b10 redesign): with a SEMANTIC scorer (`semantic_mode`), relevance is a
    # trustworthy filter again, so RESTORE it — keep rows whose cosine relevance
    # >= floor OR floor-exempt. This is the relevance/credibility axis split: the
    # SEMANTIC score FILTERS here; credibility/authority/retrieval_weight still only
    # WEIGHT the sort below. Off-topic is genuinely useless at any weight (the one
    # axis §-1.3 "weight don't filter" does not govern). The faithfulness engine is
    # untouched.
    #
    # B1 fallback (Codex diff-gate P0): whenever the operator REQUESTED the semantic
    # scorer (`semantic_requested`), the filter MUST be restored — even when the
    # embedder was unavailable and we degraded to the lexical score
    # (`semantic_requested and not semantic_mode`). Otherwise, under
    # PG_SWEEP_CREDIBILITY_REDESIGN, an embedder-unavailable run would silently fall
    # into the keep-all branch (`_redesign_on and ...`), violating the hard
    # constraint "embedder-unavailable must LOUDLY fall back to the lexical FILTER,
    # never a silent keep-all". So keep-all is preserved ONLY when semantic was NOT
    # requested at all (the true legacy path) => byte-identical default.
    _redesign_on = _credibility_redesign_enabled()
    _restore_filter = semantic_mode or semantic_requested
    if _redesign_on and not _restore_filter:
        kept = list(scored)
    else:
        kept = [
            item for item in scored
            if item[1] >= relevance_floor or _floor_exempt(item[3])
        ]
    # B1: drop ledger — log every below-floor relevance drop (score + url) so the
    # operator can audit the semantic filter. Only emits in semantic_mode (the
    # legacy lexical-floor path already has its own honest-drop log below) and only
    # when PG_RELEVANCE_DROP_LEDGER is ON. Telemetry only — does not change `kept`.
    if semantic_mode and _relevance_drop_ledger_enabled():
        for item in scored:
            if item[1] < relevance_floor and not _floor_exempt(item[3]):
                _row = item[3]
                _url = (
                    _row.get("source_url") or _row.get("url") or "<no-url>"
                )
                _LOGGER.info(
                    "[select] relevance_drop_ledger: cosine=%.4f < floor=%.4f "
                    "DROP url=%s tier=%s",
                    item[1], relevance_floor, _url, item[2],
                )
    # F15: under the redesign, multiply the ranking score by the per-row
    # retrieval weight so a DOWN-WEIGHTED (content-starved / landing-page) source
    # sorts LAST while still being kept. OFF path is byte-identical (the prior
    # sort key); a normal row's weight is 1.0 so ranking is unchanged for it.
    if _redesign_on:
        kept.sort(
            key=lambda s: (
                -(s[1] * _authority(s[3]) * _retrieval_weight(s[3])),
                _TIER_PRIORITY.get(s[2], 9),
                s[0],
            )
        )
    else:
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
    # I-pipe-003 (#1228): rows kept ONLY because the preserve-anchors flag exempted
    # a below-floor marquee row (i.e. not already a primary anchor). 0 when the flag
    # is OFF — so the note below is byte-identical in the default (OFF) case.
    marquee_exempt = sum(
        1 for item in kept
        if (_preserve_marquee
            and item[1] < relevance_floor
            and not _is_anchor(item[3])
            and _row_is_marquee_anchor(item[3]))
    )
    dropped_count = len(scored) - len(kept)
    # I-pipe-003 (#1228): emit the ACTUAL floor-cut count (PG_RELEVANCE_HONEST_DROP,
    # default ON). This is the count the operator-facing telemetry was hiding as
    # `dropped=0` (the downstream capped-finding-dedup reassignment laundered the
    # floor object's honest `dropped_count` out of the surfaced line). Telemetry-only
    # — `dropped_count` / `notes` / kept rows are unchanged by this flag.
    if _relevance_honest_drop_enabled():
        _LOGGER.info(
            "[select] relevance_floor=%s honest_drop: cut %d of %d rows "
            "(kept %d; anchor_floor_exempt=%d; marquee_floor_exempt=%d)",
            relevance_floor, dropped_count, len(scored), len(kept),
            anchor_exempt, marquee_exempt,
        )
    note = (
        f"relevance_floor={relevance_floor}: kept {len(kept)}/{len(scored)} "
        f"rows (>= floor OR primary anchor); no max_rows cap; ranked "
        f"relevance x authority_score; anchor_floor_exempt={anchor_exempt}"
    )
    # Only widen the note string when the preserve-anchors flag is ON, so the
    # default (OFF) note is byte-identical to the prior behavior.
    if _preserve_marquee:
        note += f"; marquee_floor_exempt={marquee_exempt}"
    # B1: surface the semantic-scorer state in telemetry. Strategy id flips to
    # `relevance_floor_semantic_v1` ONLY when the semantic score actually drove the
    # filter (the falsifiable manifest check). A requested-but-fell-back run keeps
    # the legacy strategy id and discloses the LOUD degrade in the note. When the
    # scorer is OFF (the default), strategy + note are byte-identical to the prior
    # behavior.
    strategy = "relevance_floor_v1"
    if semantic_mode:
        strategy = "relevance_floor_semantic_v1"
        note += "; relevance_scorer=semantic_v2 (embedding-cosine FILTER)"
    elif semantic_requested and semantic_fell_back:
        note += (
            "; relevance_scorer=semantic_v2 REQUESTED but embedder unavailable "
            "— LOUD fallback to lexical scorer (filtered on lexical score)"
        )
    return EvidenceSelection(
        selected_rows=selected_rows,
        full_counts=full_counts,
        selected_counts=selected_counts,
        dropped_count=dropped_count,
        selection_strategy=strategy,
        notes=[note],
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
    sub_queries: list[str] | None = None,
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

    # I-perm-011 (#1205): per-sub-query token sets for the max-over-subqueries
    # floor (default OFF). CONFINED TO THE RELEVANCE-FLOOR PATH (`relevance_floor
    # is not None`): the lift is MONOTONIC-UP, so on the keep-everything-above-floor
    # path it only OPENS the floor (keeps a SUPERSET) — a true "can only open, never
    # tighten" guarantee. On the tier-balanced TRUNCATING path it must NOT apply:
    # lifting a row's score there reorders the top-N and could DISPLACE a
    # previously-kept row (a tighten). So for the tier-balanced path the sets stay
    # empty and `_row_relevance_facet` == `_row_relevance` exactly (byte-identical
    # regardless of the flag). `_subquery_token_sets` also returns [] when the flag
    # is OFF or no usable sub-queries are supplied.
    _subq_token_sets = (
        _subquery_token_sets(sub_queries) if relevance_floor is not None else []
    )

    # B1 (b1b10 redesign): SEMANTIC relevance scorer (PG_RELEVANCE_SCORER=
    # semantic_v2, default OFF). CONFINED to the relevance-floor path (the same
    # `relevance_floor is not None` guard as the sub-query floor) so the legacy
    # tier-balanced TRUNCATING path stays byte-identical (lifting a row's score
    # there could displace a kept row). When ON, every row's `score` is the
    # embedding-cosine relevance (max over the question + sub-queries) instead of
    # the lexical-overlap-÷-question-length fraction. Embedder unavailable / scoring
    # failure => `_semantic_scores` is None => LOUD fallback to the lexical scorer
    # (LAW II: no silent degrade). The restored relevance FILTER on this score lives
    # in `_relevance_floor_selection`; credibility/authority/retrieval_weight keep
    # their WEIGHT role in the sort there.
    _semantic_scores: dict[int, float] | None = None
    _semantic_fell_back = False
    if relevance_floor is not None and _semantic_scorer_enabled():
        _semantic_scores = _semantic_relevance_scores(
            research_question, sub_queries, evidence_rows,
        )
        if _semantic_scores is None:
            _semantic_fell_back = True
            _LOGGER.warning(
                "[select] PG_RELEVANCE_SCORER=semantic_v2 requested but the "
                "embedder/scoring was unavailable — FELL BACK to the lexical "
                "scorer for this selection (relevance still filtered, on the "
                "lexical score). This is a LOUD degrade, not a silent keep-all."
            )

    # Score every row and tag with tier + original index.
    scored: list[tuple[int, float, str, dict[str, Any]]] = []
    for idx, row in enumerate(evidence_rows):
        tier = _row_tier(row, url_to_tier)
        if _semantic_scores is not None:
            score = _semantic_scores.get(idx, 0.0)
        else:
            score = _row_relevance_facet(
                row, question_tokens, protocol_tokens, _subq_token_sets,
            )
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
            semantic_mode=(_semantic_scores is not None),
            semantic_requested=_semantic_scorer_enabled(),
            semantic_fell_back=_semantic_fell_back,
        )

    # I-perm-003 (#1197): corpus-size-scaled budget (default OFF). Fixed-cap
    # (tier-balanced max_rows) path only — the relevance-floor mode above already
    # returns without a cap. When the flag is OFF, `_scaled_max_rows` returns the
    # passed `max_rows` UNCHANGED and `_selection_scale_note` is None, so every
    # branch below (short-pool + truncation) is byte-identical to the prior path
    # and NO telemetry is appended. When ON, the floor-guarded scaled budget
    # raises `max_rows` so a large pool feeds more BEST-ranked rows.
    max_rows, _selection_scale_note = _scaled_max_rows(len(scored), max_rows)

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
        _short = _m46_short_pool_ordered_selection(
            evidence_rows=evidence_rows,
            scored=scored,
            full_counts=full_counts,
            max_rows=max_rows,
            primary_trial_anchors=primary_trial_anchors,
        )
        # I-perm-003: surface the scaling note (ON-mode only; None when OFF →
        # byte-identical). The scaled budget can flip a pool that USED to
        # truncate into this keep-everything short-pool branch.
        if _selection_scale_note is not None:
            _short.notes.append(_selection_scale_note)
        return _short

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
        _dom_moved, _dom_brought = _apply_domain_cap(
            selected, scored, protected_ids, _dom_cap, _rec_enabled, _rec_eps,
        )
        if _dom_moved:
            _diversity_notes.append(
                f"domain_soft_cap cap={_dom_cap} moved={_dom_moved}"
            )
        # Codex design-gate iter-2 P2.2: protect rows the domain pass brought in so
        # the I-perm-023 greedy pass below cannot undo the domain-diversity pass.
        protected_ids |= _dom_brought
    # I-perm-023 (#1215): constrained-greedy coverage diversification. Runs LAST in
    # the #956 region (after the floor stack + subquery + domain passes), on
    # post-floor slack only, honoring every protected/floor/brought-in id. DEFAULT
    # OFF (PG_SELECT_CONSTRAINED_GREEDY read at call time) -> byte-identical when
    # unset; also a no-op when pool<=cap (the short-pool branch returned earlier).
    _greedy_enabled, _greedy_max_swaps = _constrained_greedy_config()
    if _greedy_enabled and _greedy_max_swaps > 0:
        _greedy_axes = _greedy_active_axes()
        # pass the ACTIVE #956 domain cap so the greedy pass cannot pull an at-cap
        # domain back over it (Codex diff-gate iter-1 P1). None when the domain cap
        # is disabled.
        _greedy_dom_cap = (
            max(1, math.ceil(_dom_frac * max_rows)) if _dom_enabled else None
        )
        _greedy_swaps, _greedy_telem = _apply_coverage_diversification(
            selected, scored, protected_ids, _greedy_max_swaps, _greedy_axes,
            _rec_enabled, _rec_eps, domain_cap=_greedy_dom_cap,
        )
        if _greedy_swaps:
            _diversity_notes.append(
                f"constrained_greedy swaps={_greedy_swaps} "
                f"distinct_buckets={_greedy_telem['distinct_buckets']} "
                f"diversity_score={_greedy_telem['diversity_score']} "
                f"axes={','.join(_greedy_axes)} (DIAGNOSTIC)"
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
    # I-perm-003 (#1197): corpus-size-scaled budget telemetry (ON-mode only;
    # None when the flag is OFF → byte-identical, no note).
    if _selection_scale_note is not None:
        notes.append(_selection_scale_note)
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
