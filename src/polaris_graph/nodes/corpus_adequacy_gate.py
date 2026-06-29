"""
Corpus-adequacy gate — HONEST-REBUILD R-6 Gap-1.

Decides whether the retrieved+classified corpus is strong enough for
synthesis. Prevents the silent failure mode where the pipeline ships a
150-word report with a "13/13 rule checks pass" badge even though the
corpus had 3 T1 sources and a 400-word report is misleadingly brief.

DECISION SPACE:
    PROCEED: corpus meets domain thresholds; synthesize normally
    EXPAND:  corpus short of thresholds but close; run a second
             retrieval round with broader queries (caller decides)
    ABORT:   corpus is too thin for confident synthesis; caller should
             either abort, ask the user to approve a short report, or
             widen retrieval significantly

DOES NOT MAKE NETWORK CALLS. Pure function — tier counts + thresholds.
"""
from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

logger = logging.getLogger("polaris_graph.corpus_adequacy_gate")


AdequacyDecision = Literal["proceed", "expand", "abort"]


# ── BUG-20 (I-arch-011): exclude content-less stubs from the grounded count ────
# THE BUG: the adequacy gate counted EVERY retrieved row toward `evidence_rows`
# (the grounded-content threshold), including rows the fetch/tier layer flagged as
# content-less stubs — a fetch that failed, a landing page with no body, or a
# content-starved span. Counting 91 such stubs as valid sources produced a
# FALSE adequacy PASS (decision=proceed) on a corpus with no real grounded content.
#
# THE FIX: when the caller passes the actual `evidence_rows`, count toward the
# grounded `evidence_rows` finding ONLY rows that are NOT degraded. A row is
# degraded iff any of these flags is truthy on the row dict. `fetch_degraded` is
# the semantic boolean the tier/authority layer sets; the concrete per-row flags
# the fetch layer already writes (live_retriever.py) are read as the union so the
# fix fires on the REAL production rows, not only on an aspirational future flag.
#
# We exclude ONLY content-less stubs (the flags below). A merely down-weighted but
# GROUNDED row (`down_weighted` / low `relevance_weight`) is NOT excluded — per the
# WEIGHT-AND-CONSOLIDATE DNA (§-1.3) a low-weight grounded source is still a real
# source; dropping it would be a banned breadth cap. This change only STOPS a
# false PASS; it never relaxes a real gate and adds no cap/floor.
_DEGRADED_ROW_FLAGS: tuple[str, ...] = (
    "fetch_degraded",
    "content_starved",
    "fetch_failed",
    "landing_page",
)


def _row_is_content_less_stub(row: Any) -> bool:
    """True iff ``row`` is a content-less stub per any degraded flag.

    Reads the union of the tier/authority `fetch_degraded` boolean and the
    concrete fetch-layer flags (`content_starved` / `fetch_failed` /
    `landing_page`). A non-dict row is treated as not-a-stub (defensive — the
    caller filters rows elsewhere); only truthy flags exclude a row.
    """
    if not isinstance(row, dict):
        return False
    return any(bool(row.get(flag)) for flag in _DEGRADED_ROW_FLAGS)


def count_grounded_rows(evidence_rows: list[Any]) -> int:
    """Count evidence rows that carry real grounded content (BUG-20).

    Excludes content-less stubs (see ``_row_is_content_less_stub``). Used by
    :func:`assess_corpus_adequacy` for the `evidence_rows` grounded threshold so
    a stub-padded corpus cannot false-PASS adequacy.
    """
    return sum(1 for r in evidence_rows if not _row_is_content_less_stub(r))


# ── I-deepfix-001 B7 (#1351): on-topic adequacy predicate ──────────────────────
# THE BUG (§-1.1 BANNED pattern-presence signal): assess_corpus_adequacy was a
# PURE tier-count gate with ZERO relevance dimension — fresh2 reported
# decision=proceed over a pool the 9-lens forensic flagged ~12/27 off-topic
# (incl. an Anubis bot-wall tiered T1). A contaminated pool false-PASSED.
#
# THE FIX (gate-honesty only; faithfulness engine UNTOUCHED — strict_verify /
# NLI / 4-role / D8 / provenance never read this): when the caller passes the
# ACTUAL evidence_rows, a row counts toward the grounded / tier denominators ONLY
# if it is on-topic — its topical-relevance WEIGHT (the per-row `relevance_weight`
# the B4 retrieval-relevance scorer writes at live_retriever.py ~L5108) is at or
# above a DISCLOSED floor (PG_ADEQUACY_RELEVANCE_FLOOR, default 0.30, §-1.3
# disclosed weight-floor — never a silent source DROP; the row still flows to
# composition and the faithfulness engine).
#
# FAIL-OPEN (the wave-1 P0 class): a row with NO explicit `relevance_weight` key
# (every OFF-path / legacy / seed row, and any pre-B4 row) is treated as ON-TOPIC.
# Only a row carrying an EXPLICIT weight BELOW the floor is demoted from the
# denominator. This preserves "byte-identical when the B4 weight is absent" and
# can never collapse a legacy run's grounded count to a false ABORT.
_ENV_RELEVANCE_FLOOR = "PG_ADEQUACY_RELEVANCE_FLOOR"
_DEFAULT_RELEVANCE_FLOOR = 0.30


def _adequacy_relevance_floor() -> float:
    """Disclosed on-topic weight floor (LAW VI). Clamp to [0, 1]; a misconfigured
    value outside that range falls back to the default."""
    raw = os.getenv(_ENV_RELEVANCE_FLOOR, "").strip()
    if not raw:
        return _DEFAULT_RELEVANCE_FLOOR
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return _DEFAULT_RELEVANCE_FLOOR
    return min(max(val, 0.0), 1.0)


def _row_is_on_topic(row: Any, floor: float) -> bool:
    """True iff ``row`` is on-topic for the adequacy denominators (B7).

    FAIL-OPEN: a non-dict row, or a row with NO explicit ``relevance_weight``
    key, counts as ON-TOPIC (missing weight is never treated as off-topic — that
    would nuke every legacy/OFF-path run). Only an explicit numeric weight BELOW
    ``floor`` makes a row off-topic. A non-numeric weight also fails open.
    """
    if not isinstance(row, dict):
        return True
    if "relevance_weight" not in row:
        return True
    try:
        w = float(row.get("relevance_weight"))
    except (TypeError, ValueError):
        return True
    return w >= floor


def count_on_topic_grounded_rows(evidence_rows: list[Any], floor: float) -> int:
    """Grounded rows (BUG-20 stub filter) that are ALSO on-topic (B7).

    A row counts iff it is NOT a content-less stub AND it is on-topic at ``floor``.
    """
    return sum(
        1 for r in evidence_rows
        if not _row_is_content_less_stub(r) and _row_is_on_topic(r, floor)
    )


def _on_topic_tier_counts(
    evidence_rows: list[Any], floor: float, raw_tier_counts: dict[str, int],
) -> dict[str, int]:
    """Re-tally tier_counts over ON-TOPIC rows only (B7).

    Each evidence row's tier is read from ``row['tier']`` (the surface the
    classifier back-fills). A row with no usable tier is bucketed UNKNOWN so the
    total still reflects every on-topic row. FAIL-OPEN: if NO row carries a tier
    key at all, the on-topic re-tally is empty and the caller falls back to the
    raw classifier ``tier_counts`` (so an evidence_rows pool that simply lacks the
    tier key never zeroes the gate).
    """
    counts: dict[str, int] = {}
    saw_tier = False
    for r in evidence_rows:
        if not isinstance(r, dict):
            continue
        if _row_is_content_less_stub(r) or not _row_is_on_topic(r, floor):
            continue
        tier = r.get("tier")
        if tier:
            saw_tier = True
            key = str(tier)
        else:
            key = "UNKNOWN"
        counts[key] = counts.get(key, 0) + 1
    # FAIL-OPEN: no per-row tier signal at all → keep the classifier tier_counts.
    if not saw_tier:
        return dict(raw_tier_counts)
    return counts


@dataclass
class AdequacyThresholds:
    """Per-domain thresholds for corpus adequacy.

    Loaded from the scope template's `corpus_adequacy` block. Callers
    can also provide overrides.
    """
    min_total_sources: int = 8
    min_t1_count: int = 2            # at least 2 peer-reviewed primary
    min_t1_plus_t2: int = 3          # or 3 combined T1+T2+T3
    min_t1_plus_t2_plus_t3: int = 3
    min_t3_plus_t4_plus_t6: int = 0  # GH#405: emerging-policy quality floor
    min_evidence_rows: int = 5       # after content-starved filter
    max_t5_plus_t6_fraction: float = 0.70   # too much industry/commentary = abort
    max_t7_fraction: float = 0.50           # too many stubs = abort
    # Fraction-of-threshold below which we ABORT instead of EXPAND
    abort_if_below_fraction: float = 0.5


@dataclass
class AdequacyFinding:
    name: str
    ok: bool
    observed: float
    threshold: float
    severity: str   # "ok" | "warn" | "critical"


@dataclass
class CorpusAdequacyReport:
    decision: AdequacyDecision
    findings: list[AdequacyFinding] = field(default_factory=list)
    total_sources: int = 0
    tier_counts: dict[str, int] = field(default_factory=dict)
    evidence_rows: int = 0
    notes: list[str] = field(default_factory=list)
    thresholds: dict[str, Any] = field(default_factory=dict)
    # I-deepfix-001 B7 (#1351): disclose BOTH the raw-pool and the on-topic
    # denominators so Methods cannot read "8/8 grounded" over a contaminated
    # pool. Populated ONLY when real evidence_rows are supplied; defaults keep
    # the legacy report shape byte-identical when they are not.
    on_topic_evidence_rows: int = 0          # grounded AND on-topic at the floor
    raw_grounded_evidence_rows: int = 0      # grounded (stub-filtered) regardless of topic
    on_topic_relevance_floor: float = 0.0    # the disclosed floor used (0.0 = gate inert)
    on_topic_tier_counts: dict[str, int] = field(default_factory=dict)


_DEFAULT_DOMAIN_THRESHOLDS: dict[str, AdequacyThresholds] = {
    "clinical": AdequacyThresholds(
        min_total_sources=10, min_t1_count=3,
        min_t1_plus_t2=5, min_t1_plus_t2_plus_t3=6,
        min_evidence_rows=6,
        max_t5_plus_t6_fraction=0.50,
        max_t7_fraction=0.40,
    ),
    "policy": AdequacyThresholds(
        # GH#405: emerging-policy topics (housing 2026, etc.) lack T1
        # by definition. Relaxed from clinical-shaped thresholds; the
        # real quality signal is min_t3_plus_t4_plus_t6 (regulatory +
        # think-tank + advocacy density).
        min_total_sources=8, min_t1_count=0,
        min_t1_plus_t2=0, min_t1_plus_t2_plus_t3=0,
        min_t3_plus_t4_plus_t6=5,
        min_evidence_rows=5,
        max_t5_plus_t6_fraction=0.60,
        max_t7_fraction=0.40,
    ),
    "tech": AdequacyThresholds(
        min_total_sources=6, min_t1_count=1,
        min_t1_plus_t2=2, min_t1_plus_t2_plus_t3=2,
        min_evidence_rows=4,
        max_t5_plus_t6_fraction=0.60,
        max_t7_fraction=0.50,
    ),
    "due_diligence": AdequacyThresholds(
        min_total_sources=8, min_t1_count=1,
        min_t1_plus_t2=2, min_t1_plus_t2_plus_t3=3,
        min_evidence_rows=5,
        max_t5_plus_t6_fraction=0.70,
        max_t7_fraction=0.40,
    ),
    # GH#405: emerging-policy domains. T1 peer-reviewed clinical trials
    # do not exist for these topics by definition; the real quality
    # signal is min_t3_plus_t4_plus_t6 (gov + think-tank + advocacy).
    "ai_sovereignty": AdequacyThresholds(
        min_total_sources=8, min_t1_count=0,
        min_t1_plus_t2=0, min_t1_plus_t2_plus_t3=0,
        min_t3_plus_t4_plus_t6=4,
        min_evidence_rows=5,
        max_t5_plus_t6_fraction=0.80,
        max_t7_fraction=0.40,
    ),
    "canada_us": AdequacyThresholds(
        min_total_sources=8, min_t1_count=0,
        min_t1_plus_t2=0, min_t1_plus_t2_plus_t3=0,
        min_t3_plus_t4_plus_t6=4,
        min_evidence_rows=5,
        max_t5_plus_t6_fraction=0.80,
        max_t7_fraction=0.40,
    ),
    "workforce": AdequacyThresholds(
        # Workforce evidence base is dominated by T4 think-tank reports
        # (StatsCan, OECD, McKinsey); gov-stats agencies surface as T4
        # rather than T3 in the current tier classifier (follow-up
        # GH#406 calibration risk).
        min_total_sources=6, min_t1_count=0,
        min_t1_plus_t2=0, min_t1_plus_t2_plus_t3=0,
        min_t3_plus_t4_plus_t6=4,
        min_evidence_rows=5,
        max_t5_plus_t6_fraction=0.85,
        max_t7_fraction=0.40,
    ),
}


def _get_thresholds(
    domain: str,
    protocol: dict[str, Any] | None = None,
    override: AdequacyThresholds | None = None,
) -> AdequacyThresholds:
    """Resolve adequacy thresholds with override > protocol > default."""
    if override is not None:
        return override
    # Protocol may carry a corpus_adequacy block
    if protocol:
        ca = protocol.get("corpus_adequacy") or {}
        if ca:
            base = _DEFAULT_DOMAIN_THRESHOLDS.get(domain, AdequacyThresholds())
            # Merge: take protocol values where present
            return AdequacyThresholds(
                min_total_sources=int(ca.get("min_total_sources", base.min_total_sources)),
                min_t1_count=int(ca.get("min_t1_count", base.min_t1_count)),
                min_t1_plus_t2=int(ca.get("min_t1_plus_t2", base.min_t1_plus_t2)),
                min_t1_plus_t2_plus_t3=int(ca.get("min_t1_plus_t2_plus_t3", base.min_t1_plus_t2_plus_t3)),
                min_t3_plus_t4_plus_t6=int(ca.get("min_t3_plus_t4_plus_t6", base.min_t3_plus_t4_plus_t6)),
                min_evidence_rows=int(ca.get("min_evidence_rows", base.min_evidence_rows)),
                max_t5_plus_t6_fraction=float(ca.get("max_t5_plus_t6_fraction", base.max_t5_plus_t6_fraction)),
                max_t7_fraction=float(ca.get("max_t7_fraction", base.max_t7_fraction)),
                abort_if_below_fraction=float(ca.get("abort_if_below_fraction", base.abort_if_below_fraction)),
            )
    return _DEFAULT_DOMAIN_THRESHOLDS.get(domain, AdequacyThresholds())


def assess_corpus_adequacy(
    *,
    tier_counts: dict[str, int],
    evidence_row_count: int,
    domain: str,
    protocol: dict[str, Any] | None = None,
    override: AdequacyThresholds | None = None,
    evidence_rows: list[Any] | None = None,
) -> CorpusAdequacyReport:
    """Return an AdequacyReport for the retrieved corpus.

    Args:
        tier_counts: dict mapping "T1"/"T2"/.../"T7"/"UNKNOWN" -> count.
        evidence_row_count: number of evidence rows AFTER content-starved
            filtering (Fix-D). Used for the grounded `evidence_rows` threshold
            ONLY when ``evidence_rows`` is not supplied (back-compat path).
        domain: clinical / policy / tech / due_diligence.
        protocol: dict form of protocol.json (may carry adequacy overrides).
        override: explicit AdequacyThresholds, wins over all else.
        evidence_rows: BUG-20 (I-arch-011) — the ACTUAL evidence row dicts. When
            supplied, the grounded `evidence_rows` finding counts only rows that
            are NOT content-less stubs (excludes `fetch_degraded` /
            `content_starved` / `fetch_failed` / `landing_page` rows) so a
            stub-padded corpus cannot false-PASS adequacy. When None, behaviour is
            byte-identical to the prior callers (uses ``evidence_row_count``).
            WIRING NOTE: the run-script wiring pass should pass
            ``evidence_rows=retrieval.evidence_rows`` at each call site.
    """
    thr = _get_thresholds(domain, protocol, override)

    # BUG-20: when the real rows are available, the grounded evidence count
    # EXCLUDES content-less stubs. Falls back to evidence_row_count otherwise.
    # I-deepfix-001 B7 (#1351): when real rows are available, the grounded count
    # ALSO excludes OFF-topic rows (explicit relevance_weight below the disclosed
    # floor) — gate denominators must reflect on-topic grounded content, not raw
    # tier presence (the §-1.1 BANNED pattern-presence signal). Fail-open: a row
    # without an explicit weight counts as on-topic (see ``_row_is_on_topic``).
    _floor = _adequacy_relevance_floor()
    raw_grounded = 0
    on_topic_grounded = 0
    # `tier_counts` is the CLASSIFIER tier histogram (the legacy gate input). When
    # real rows are supplied we re-tally tier_counts over ON-TOPIC rows so the
    # tier thresholds are computed over on-topic content too; otherwise the gate
    # is byte-identical to the prior callers.
    on_topic_tier_counts: dict[str, int] = {}
    if evidence_rows is not None:
        raw_grounded = count_grounded_rows(evidence_rows)
        on_topic_grounded = count_on_topic_grounded_rows(evidence_rows, _floor)
        grounded_evidence_rows = on_topic_grounded
        on_topic_tier_counts = _on_topic_tier_counts(
            evidence_rows, _floor, tier_counts,
        )
        gate_tier_counts = on_topic_tier_counts
    else:
        grounded_evidence_rows = evidence_row_count
        raw_grounded = evidence_row_count
        on_topic_grounded = evidence_row_count
        gate_tier_counts = dict(tier_counts)

    total = sum(gate_tier_counts.values())
    t1 = gate_tier_counts.get("T1", 0)
    t2 = gate_tier_counts.get("T2", 0)
    t3 = gate_tier_counts.get("T3", 0)
    t4 = gate_tier_counts.get("T4", 0)
    t5 = gate_tier_counts.get("T5", 0)
    t6 = gate_tier_counts.get("T6", 0)
    t7 = gate_tier_counts.get("T7", 0)

    findings: list[AdequacyFinding] = []

    def _record(name: str, observed: float, threshold: float,
                direction: str, critical_at: float | None = None) -> None:
        if direction == "min":
            ok = observed >= threshold
            # below 50% of threshold = critical
            if critical_at is None:
                critical_at = threshold * thr.abort_if_below_fraction
            severity = ("ok" if ok else
                        "critical" if observed <= critical_at else
                        "warn")
        else:  # "max"
            ok = observed <= threshold
            # 1.5x over = critical
            if critical_at is None:
                critical_at = threshold * 1.5
            severity = ("ok" if ok else
                        "critical" if observed >= critical_at else
                        "warn")
        findings.append(AdequacyFinding(
            name=name, ok=ok, observed=observed,
            threshold=threshold, severity=severity,
        ))

    _record("total_sources", total, thr.min_total_sources, "min")
    _record("t1_count", t1, thr.min_t1_count, "min")
    _record("t1_plus_t2", t1 + t2, thr.min_t1_plus_t2, "min")
    _record("t1_plus_t2_plus_t3", t1 + t2 + t3,
            thr.min_t1_plus_t2_plus_t3, "min")
    # GH#405: real quality signal for emerging-policy domains.
    _record("t3_plus_t4_plus_t6", t3 + t4 + t6,
            thr.min_t3_plus_t4_plus_t6, "min")
    # BUG-20: grounded count (stubs excluded when real rows were supplied).
    _record("evidence_rows", grounded_evidence_rows,
            thr.min_evidence_rows, "min")

    low_quality_fraction = (t5 + t6) / max(total, 1)
    _record("low_quality_fraction",
            low_quality_fraction, thr.max_t5_plus_t6_fraction, "max")

    t7_fraction = t7 / max(total, 1)
    _record("t7_fraction", t7_fraction, thr.max_t7_fraction, "max")

    critical_count = sum(1 for f in findings if f.severity == "critical")
    warn_count = sum(1 for f in findings if f.severity == "warn")

    if critical_count > 0:
        decision: AdequacyDecision = "abort"
    elif warn_count > 0:
        decision = "expand"
    else:
        decision = "proceed"

    notes: list[str] = []
    if decision == "abort":
        failing = [f.name for f in findings if f.severity == "critical"]
        notes.append(
            f"Corpus fails {len(failing)} critical threshold(s): {failing}. "
            f"Refusing to synthesize a confident report; caller should "
            f"expand retrieval substantially or ABORT."
        )
    elif decision == "expand":
        warning = [f.name for f in findings if f.severity == "warn"]
        notes.append(
            f"Corpus below nominal on {len(warning)} threshold(s): {warning}. "
            f"Synthesis possible but caller is encouraged to trigger a "
            f"second retrieval round before proceeding."
        )

    # I-deepfix-001 B7 (#1351): disclose the on-topic vs raw denominators so the
    # gate honesty is auditable (and the §-1.1 contaminated-pool false-PASS is
    # visible). Only when real rows were supplied AND off-topic rows were demoted.
    if evidence_rows is not None and on_topic_grounded < raw_grounded:
        notes.append(
            f"Adequacy computed over ON-TOPIC grounded rows "
            f"({on_topic_grounded}) — {raw_grounded - on_topic_grounded} "
            f"grounded row(s) demoted from the denominator as off-topic "
            f"(relevance_weight < {_floor:.2f}); raw grounded pool="
            f"{raw_grounded}. Demoted rows are KEPT in the corpus (§-1.3), "
            f"only excluded from the sufficiency count."
        )

    # I-deepfix-001 W01-fx06 (#1344): the DECISION above (proceed/expand/abort) and
    # all on-topic disclosure ride on `gate_tier_counts` / `on_topic_*` — that is
    # UNCHANGED (methods-honesty preserved byte-for-byte). But the REPORTED
    # `total_sources` / `tier_counts` are restored to the CLASSIFIER population (the
    # passed-in `tier_counts` arg = corpus_approval `dist` counts), exactly as
    # pre-7000627a. RATIONALE: the FX-06 self-consistency tripwire in the spine
    # (run_honest_sweep_r3.py ~9341) compares `adequacy.total_sources` /
    # `adequacy.tier_counts` against the approval `dist` population. When B7 re-tallied
    # the REPORTED counts over ON-TOPIC evidence_rows, the two populations diverged BY
    # CONSTRUCTION whenever ANY row was demoted off-topic (e.g. 833 classified vs 639
    # on-topic), firing error_corpus_population_mismatch on EVERY normal run before a
    # single generator token. Reporting the classifier population restores FX-06
    # equality by construction while the on-topic gate honesty lives entirely in the
    # dedicated on_topic_* fields. The decision is byte-identical (it never reads these
    # two reported fields — they are artifact/approval-population fields only).
    reported_tier_counts = dict(tier_counts)
    reported_total_sources = sum(reported_tier_counts.values())
    return CorpusAdequacyReport(
        decision=decision,
        findings=findings,
        total_sources=reported_total_sources,
        # REPORTED population = the classifier histogram (the population the approval
        # gate `dist` and the report consume). The on-topic counts the DECISION used
        # are surfaced separately via on_topic_tier_counts / on_topic_evidence_rows.
        tier_counts=reported_tier_counts,
        evidence_rows=grounded_evidence_rows,
        notes=notes,
        thresholds=asdict(thr),
        on_topic_evidence_rows=on_topic_grounded,
        raw_grounded_evidence_rows=raw_grounded,
        on_topic_relevance_floor=(_floor if evidence_rows is not None else 0.0),
        on_topic_tier_counts=dict(on_topic_tier_counts),
    )
