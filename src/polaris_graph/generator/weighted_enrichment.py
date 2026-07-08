"""I-arch-007 ITEM 2 (#1264) — BREADTH: weighted unbound-SUPPORTS enrichment selection.

THE PROBLEM (the 485-in / ~13-cited collapse): the V30 contract render universe is the
5 required contract entities + a handful of LLM-planner enrichment picks. On a FULLY
SUCCESSFUL credibility pass that weighted + basketed hundreds of sources, the ~437 sources
that are NOT bound to a contract ``v30_entity_id`` are never *offered* to any section — a
purely STRUCTURAL funnel (it fires even when nothing times out). This module surfaces those
unbound-but-span-verified SUPPORTS sources into ONE extra legacy (field-agnostic) section so
they flow through the UNCHANGED ``_run_section`` -> ``strict_verify`` path.

§-1.3 DNA — WEIGHT-AND-CONSOLIDATE, never FILTER-AND-CAP:
  * WEIGHT, DON'T FILTER (I-arch-011 B18, the keystone): candidates are ORDERED by
    relevance-to-question THEN basket ``weight_mass`` (priority of consideration). There is NO cap /
    target / top-N / FLOOR DROP — the FULL surviving list is offered. KEEP-ALL-AND-SORT-BELOW-FLOOR-
    LAST: a member whose source row scores BELOW ``PG_RELEVANCE_FLOOR`` is NOT excluded — it is KEPT
    and sorted LAST (a below-floor ORDERING demotion, never a drop), exactly the way the retrieval
    pool itself down-weights a below-floor row under the redesign (evidence_selector.py:2066-2070,
    ``kept = list(scored)``). The pre-I-arch-011 code RE-IMPOSED a hard ``selection_relevance < 0.30``
    DROP here — the SECTION-1.3-FORBIDDEN filter-and-cap anti-pattern the selector docstring
    (evidence_selector.py:1944-1953) explicitly forbids, which killed 729/746 unbound SUPPORTS so the
    enrichment appended NOTHING. That drop is REMOVED. ``below_floor_count`` is now pure TELEMETRY
    (how many kept rows sit below the floor), never an exclusion.
  * CONSOLIDATE, DON'T DROP: the members come straight from the already-computed claim baskets
    (``ClaimBasket.supporting_members``) — the consolidated multi-source groups.
  * BASKET FAITHFULNESS: a member is offered ONLY if its OWN isolated ``span_verdict`` is
    ``"SUPPORTS"`` (computed by the credibility pass at credibility_pass.py:442-457). It is then
    re-verified against its own span by the section's UNCHANGED ``strict_verify``. Breadth
    EMERGES from how many survive that gate — it is never forced.

RECONCILIATION WITH RETRIEVAL P0-A6 (evidence_selector.py:2036-2070): the retrieval POOL
WEIGHTS-not-FILTERS — under the default redesign a below-floor row is KEPT and down-weighted in the
pool, never hard-dropped (P0-A6 is UNTOUCHED). The breadth ENRICHMENT section now behaves
IDENTICALLY: a below-floor unbound SUPPORTS member is KEPT and sorted LAST, never dropped — the
relevance floor is an ORDERING weight at the surfacing boundary, not a re-introduction of the
retrieval filter P0-A6 removed. The ONLY hard gate remains the faithfulness engine (strict_verify /
NLI / 4-role / span-grounding), which is untouched.

FAITHFULNESS-NEUTRALITY: this module only READS already-computed state and builds a candidate
``SectionPlan``. It moves NO strict_verify / NLI / 4-role D8 / span-grounding / section-floor /
sentinel threshold. The master flag defaults OFF (=> empty selection => byte-identical) and a
degraded pass (``credibility_analysis is None``) also yields an empty selection (byte-identical).
"""

from __future__ import annotations

import logging
import os
import re
from collections import Counter
from typing import Any, Callable, NamedTuple

logger = logging.getLogger(__name__)

# LAW VI: env-overridable, default OFF (unset => byte-identical legacy render).
_ENV_BREADTH_ENRICHMENT = "PG_BREADTH_ENRICHMENT_ENABLED"

# A NON-contract title => ``is_contract_section()`` (an isinstance(ContractSectionPlanExt) check)
# is False => the section dispatches through ``_run_legacy_bounded`` -> field-agnostic
# ``_run_section`` -> the same three-stream strict_verify the contract sentences use.
_ENRICHMENT_TITLE = "Corroborated Weighted Findings"
_ENRICHMENT_FOCUS = (
    "Additional independently span-verified findings drawn from the weighted source corpus that "
    "were not bound to a contract entity. Each sentence must survive the same strict_verify gate as "
    "every other section; unsupported material is dropped, never padded."
)

_SUPPORTS = "SUPPORTS"

# The per-row topicality sidecar the retrieval relevance gate stamps (evidence_selector.py:2128)
# and finding_dedup reads (finding_dedup.py:212). It is THE existing relevance standard.
_RELEVANCE_FIELD = "selection_relevance"

# Constant sentinel for the relevance ORDERING key when a row carries no usable relevance score.
# Using a constant (not the parsed value, not 0.0) ensures a pool of all-missing-relevance rows
# ties on the relevance key, so the weight_mass tiebreak reproduces today's pure weight-desc order.
_MISSING_RELEVANCE_SORT_KEY = 0.0


def _row_relevance(row: Any) -> float | None:
    """The row's ``selection_relevance`` topicality score, or ``None`` when not usable.

    Returns ``None`` (=> relevance-gate FALLBACK = keep, ordering = sentinel) when the row is
    missing, has no ``selection_relevance``, or carries an unparseable value. Deliberately NOT
    ``float(row.get(field, 0.0) or 0.0)`` (finding_dedup's coercion): that maps a missing/None
    score to 0.0, which would push it below any floor and wrongly EXCLUDE a member whose pool
    membership already implies the retrieval relevance floor passed once.
    """
    if not isinstance(row, dict):
        return None
    raw = row.get(_RELEVANCE_FIELD)
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _relevance_sort_key(relevance: float | None) -> float:
    """Relevance value for the ORDERING key; the constant sentinel when relevance is unknown."""
    return _MISSING_RELEVANCE_SORT_KEY if relevance is None else relevance


# ─────────────────────────────────────────────────────────────────────────────
# I-deepfix-001 (#1344) DEFER-1 — off-topic CITE-SURFACE suppression.
#
# drb_72 cited OFF-TOPIC sources (B1 supply-chain blogs, B2 Russian cosmetics, B3
# recycling journal, B4 post-merger M&A) as numbered findings in the breadth
# "Corroborated Weighted Findings" section. The keystone (I-arch-011 B18) correctly
# forbids the lexical ``selection_relevance < floor`` DROP (it killed 729/746 real
# unbound SUPPORTS and also suppressed REAL on-topic low-cred sources). So the
# discriminator is NOT the noisy score — it is the SEMANTIC confirmed-OFF verdict
# the topic gate / W2 content-relevance judge already produced and stamped on the
# row (``topic_offtopic_demoted`` / ``content_relevance_label``). A confirmed
# "this is about cosmetics, not AI labor" verdict is, by definition, not a
# corroborator of an AI-labor claim, so withholding it from CITATION is not a
# §-1.3 hard-drop: the source STAYS in evidence_pool + the credibility disclosure
# (kept-and-disclosed). Gated default-ON; ``PG_OFFTOPIC_CITE_SUPPRESS=0`` restores
# the byte-identical legacy cite-surface.
_CONFIRMED_OFFTOPIC_LABELS = frozenset({"demoted", "escalated_demoted"})


def offtopic_cite_suppress_enabled() -> bool:
    """Kill-switch ``PG_OFFTOPIC_CITE_SUPPRESS`` (default ON). OFF => the cite
    surface is byte-identical to the legacy keep-all-and-cite behaviour."""
    return os.environ.get("PG_OFFTOPIC_CITE_SUPPRESS", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


_POSITIVE_RELEVANCE_LABELS = frozenset({"relevant", "escalated_relevant"})


def _offtopic_relevance_override_enabled() -> bool:
    """Kill-switch ``PG_OFFTOPIC_RELEVANCE_OVERRIDE`` (default ON). OFF => the
    legacy byte-identical ``_is_confirmed_offtopic`` (topic-flag wins)."""
    return os.environ.get("PG_OFFTOPIC_RELEVANCE_OVERRIDE", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


def _is_confirmed_offtopic(row: Any) -> bool:
    """True iff a SEMANTIC judge confirmed this source is OFF-topic.

    Keys ONLY on the topic-gate sidecar (``topic_offtopic_demoted is True``) OR the
    W2 content-relevance LABEL (``content_relevance_label`` in
    {``demoted``, ``escalated_demoted``}) — NEVER on the noisy lexical/embedding
    ``selection_relevance`` score (that is the §-1.3-banned keystone DROP). A
    missing/absent label is keep-neutral (NOT off-topic): an unjudged or
    judged-RELEVANT row is never suppressed.

    I-deepfix-001 (drb_72 forensic): when the TWO semantic judges DISAGREE — the
    W2 content-relevance judge affirmatively rated the source ``relevant`` /
    ``escalated_relevant`` (high weight) while the topic gate stamped
    ``topic_offtopic_demoted=True`` — the AFFIRMATIVE relevance verdict WINS and the
    source is NOT suppressed. This is the §-1.3 weight-not-filter rule: a false-positive
    off-topic flag must never bury a source the content-relevance judge judged relevant.
    (The drb_72 corpus buried the SEMINAL papers this way — GPTs-are-GPTs / World Bank /
    Humlum all carried content_relevance_label='relevant' weight=1.0 BUT
    topic_offtopic_demoted=True, so the old predicate suppressed them from the finding
    surface.) Behind ``PG_OFFTOPIC_RELEVANCE_OVERRIDE`` (default ON); OFF = byte-identical."""
    if not isinstance(row, dict):
        return False
    label = str(row.get("content_relevance_label", "") or "").strip().lower()
    if _offtopic_relevance_override_enabled() and label in _POSITIVE_RELEVANCE_LABELS:
        # judges conflict (relevant vs off-topic-demoted) -> trust the positive relevance, KEEP.
        return False
    if row.get("topic_offtopic_demoted") is True:
        return True
    return label in _CONFIRMED_OFFTOPIC_LABELS


# ─────────────────────────────────────────────────────────────────────────────
# I-deepfix-001 wave-2 — OFF-TOPIC FAIL-CLOSED QUARANTINE (Fable design).
#
# THE BUG (box2 wave-1): a RESUME reloads the corpus_snapshot post-selection and
# SKIPS the topic judge, so every reloaded row carries NO topic verdict. The
# ``_is_confirmed_offtopic`` seam keys ONLY on a POSITIVE confirmed-OFF verdict
# (``topic_offtopic_demoted`` / ``content_relevance_label`` in demoted/escalated),
# so an unjudged off-topic row (a funeral / tree-cover / face-recognition source
# leaked into an AI-labor report) sails through and anchors a numbered finding.
#
# THE FIX — §-1.3 WITHHOLD-and-disclose, NEVER a lexical DROP: the BANNED discriminator
# is the noisy lexical ``selection_relevance < floor`` (weighted_enrichment keystone:
# it killed 729/746 real sources). This fix uses ONLY the ABSENCE of a semantic verdict
# as a FAIL-CLOSED signal: a row the judge NEVER judged is WITHHELD from the finding
# surface (kept in evidence_pool + the disclosure — never a pool drop, never deleted),
# but ONLY when we can prove the judge actually ran this run (``topic_judge_ran``), and
# ONLY within a blast-radius ceiling (``PG_QUARANTINE_MAX_FRACTION``). If the judge was
# legitimately SKIPPED (a resume without PG_RESUME_RUN_TOPIC_JUDGE, or the topic gate
# off), NOTHING is unjudged-in-the-leak-sense => nothing is quarantined. The faithfulness
# engine (strict_verify / NLI / 4-role D8 / provenance / span-grounding) is UNTOUCHED —
# withholding a citation is a SURFACE-placement decision, never a grounding change.
# Gated default-OFF (LAW VI): PG_QUARANTINE_UNJUDGED_TOPIC unset => byte-identical.
_ENV_QUARANTINE_UNJUDGED = "PG_QUARANTINE_UNJUDGED_TOPIC"      # master flag, default OFF
_ENV_QUARANTINE_MAX_FRACTION = "PG_QUARANTINE_MAX_FRACTION"    # blast-radius ceiling (LAW VI)
# Run-scoped signal the orchestrator sets when the topic judge demonstrably ran this run
# (fresh OR the PG_RESUME_RUN_TOPIC_JUDGE resume path). Mirrored as a plain env name so the
# generator never imports the retrieval-side gate on the hot path; ``topic_judge_ran`` ALSO
# derives the same fact from the data (any row carrying a verdict), so the coupling holds
# even if the orchestrator never set the flag.
_ENV_TOPIC_JUDGE_RAN = "PG_TOPIC_JUDGE_RAN"
_DEFAULT_QUARANTINE_MAX_FRACTION = 0.5
_QUARANTINE_REASON = "unjudged_topic_no_verdict"


def quarantine_unjudged_topic_enabled() -> bool:
    """Master kill-switch ``PG_QUARANTINE_UNJUDGED_TOPIC`` (default OFF, LAW VI). OFF => no
    row is ever quarantined on missing-verdict => byte-identical to the legacy cite surface."""
    return os.environ.get(_ENV_QUARANTINE_UNJUDGED, "").strip().lower() in (
        "1", "true", "on", "yes", "enabled",
    )


def _quarantine_max_fraction() -> float:
    """Blast-radius ceiling in [0.0, 1.0] (default 0.5). If quarantine WOULD withhold a
    larger fraction of the surface than this, the guard trips (FAIL LOUD + disable). A
    garbage value is an operator config error => ValueError (LAW VI: fail-loud, never
    swallowed)."""
    raw = os.environ.get(_ENV_QUARANTINE_MAX_FRACTION)
    if raw is None or not str(raw).strip():
        return _DEFAULT_QUARANTINE_MAX_FRACTION
    val = float(str(raw).strip())  # ValueError on garbage: fail loud
    if not (0.0 <= val <= 1.0):
        raise ValueError(
            f"{_ENV_QUARANTINE_MAX_FRACTION} must be in [0.0, 1.0]; got {val!r}"
        )
    return val


def _topic_judge_ran_env() -> bool:
    """The explicit run-scoped signal ``PG_TOPIC_JUDGE_RAN`` the orchestrator sets once the
    topic judge has executed this run (fresh or resume). Absent => rely on the data-derived
    corroboration in ``topic_judge_ran``."""
    return os.environ.get(_ENV_TOPIC_JUDGE_RAN, "").strip().lower() in (
        "1", "true", "on", "yes", "enabled",
    )


def is_topic_unjudged(row: Any) -> bool:
    """True iff a row carries NO topic verdict at all — the topic/content-relevance judge
    never stamped it (``topic_offtopic_demoted`` absent AND ``content_relevance_label``
    empty). A row a judge stamped — either a ``topic_offtopic_demoted`` sidecar (True/False)
    OR a non-empty ``content_relevance_label`` (relevant / demoted / escalated_* /
    wall_rescue_floor) — returns False. A non-dict returns False (keep-neutral; never
    quarantined). PURE read of already-computed state; no faithfulness gate is touched and
    NO lexical ``selection_relevance`` score is consulted (that is the §-1.3-banned DROP)."""
    if not isinstance(row, dict):
        return False
    if row.get("topic_offtopic_demoted") is not None:
        return False  # a topic-gate verdict (True/False) was stamped => judged
    label = str(row.get("content_relevance_label", "") or "").strip()
    return label == ""  # no content-relevance label => the judge never saw this row


def topic_judge_ran(rows: Any = None) -> bool:
    """Run-scoped: True iff the topic/content-relevance judge demonstrably ran this run.

    OR of two POSITIVE signals (either alone is sufficient proof the judge ran; only when
    NEITHER holds do we conclude the judge was legitimately SKIPPED and stand quarantine
    down):
      (1) the explicit orchestrator env flag ``PG_TOPIC_JUDGE_RAN`` (set the moment
          ``classify_topic_relevance`` executed this run — including the resume path opened
          by ``PG_RESUME_RUN_TOPIC_JUDGE``), OR
      (2) at least one provided row carries a topic verdict (``not is_topic_unjudged`` — a
          stamp only a judge could have written).

    This is the coupling that makes the quarantine NEVER fire when the judge was skipped:
    a skipped-judge run has no env flag AND no stamped row, so this returns False."""
    if _topic_judge_ran_env():
        return True
    for row in (rows or ()):
        if isinstance(row, dict) and not is_topic_unjudged(row):
            return True
    return False


def partition_unjudged_topic_rows(
    rows: Any,
    *,
    judged_universe: Any = None,
    anchor_predicate: "Callable[[Any], bool] | None" = None,
) -> "tuple[list, list]":
    """Split ``rows`` into ``(kept, quarantined)`` on ``is_topic_unjudged``, FAIL-CLOSED.

    Quarantine fires ONLY when ALL of:
      * ``PG_QUARANTINE_UNJUDGED_TOPIC`` is ON (default OFF => ``(list(rows), [])``), AND
      * the topic judge ran this run (``topic_judge_ran`` over ``judged_universe`` or
        ``rows``) — so a legitimately-skipped judge NEVER quarantines, AND
      * the blast-radius guard passes: the withheld fraction ``<= PG_QUARANTINE_MAX_FRACTION``
        (default 0.5). If it WOULD exceed the ceiling, the guard TRIPS: ``logger.error``
        (FAIL LOUD) + disable for this call (return every row kept). A mass-withhold is the
        signature of a judge that did not actually stamp the corpus, so we refuse to nuke it.

    A marquee/required-entity anchor (via ``anchor_predicate``) is NEVER quarantined. A
    quarantined row is WITHHELD from the finding surface only — the caller keeps it in
    ``evidence_pool`` + the off-topic disclosure; nothing is deleted; the faithfulness engine
    is untouched. OFF / judge-skipped / no unjudged row => ``(list(rows), [])``."""
    row_list = list(rows or [])
    if not quarantine_unjudged_topic_enabled():
        return row_list, []
    universe = list(judged_universe) if judged_universe is not None else row_list
    if not topic_judge_ran(universe):
        # The judge was legitimately skipped this run => absence of a verdict is EXPECTED,
        # not a leak. Never quarantine (byte-identical keep-all).
        return row_list, []

    def _is_anchor(r: Any) -> bool:
        if anchor_predicate is None:
            return False
        try:
            return bool(anchor_predicate(r))
        except Exception:  # noqa: BLE001 — a broken predicate must never quarantine an anchor
            return False

    candidates = [r for r in row_list if is_topic_unjudged(r) and not _is_anchor(r)]
    if not candidates:
        return row_list, []
    max_fraction = _quarantine_max_fraction()
    fraction = (len(candidates) / len(row_list)) if row_list else 0.0
    if fraction > max_fraction:
        logger.error(
            "[weighted_enrichment] PG_QUARANTINE_UNJUDGED_TOPIC blast-radius guard TRIPPED: "
            "would withhold %d/%d rows (%.1f%%) > ceiling %.1f%% — DISABLING quarantine for "
            "this run and KEEPING ALL rows (fail-loud; a mass-withhold means the judge did not "
            "actually stamp the corpus, so refusing to nuke it).",
            len(candidates), len(row_list), 100.0 * fraction, 100.0 * max_fraction,
        )
        return row_list, []
    quarantined_ids = {id(r) for r in candidates}
    kept = [r for r in row_list if id(r) not in quarantined_ids]
    logger.info(
        "[weighted_enrichment] PG_QUARANTINE_UNJUDGED_TOPIC (%s): WITHHELD %d/%d unjudged-topic "
        "row(s) from the finding surface (kept in evidence_pool + disclosed; faithfulness engine "
        "untouched)",
        _QUARANTINE_REASON, len(candidates), len(row_list),
    )
    return kept, candidates


def breadth_enrichment_enabled() -> bool:
    """True iff the default-OFF master flag is explicitly enabled (LAW VI)."""
    return os.environ.get(_ENV_BREADTH_ENRICHMENT, "").strip().lower() in (
        "1", "true", "on", "yes",
    )


# ─────────────────────────────────────────────────────────────────────────────
# I-deepfix-001 (#1344 follow-on, M5) — PROMOTION-ELIGIBILITY PARTITION.
#
# drb_72 let near-zero-weight, single-origin, non-journal sources anchor standalone
# numbered findings exactly like a corroborated NEJM/AEA source: cognifit blog
# (weight 0.03), inboundlogistics (0.00), procom (0.01), protolabs (0.00), a wsu
# blog (0.06), an IZA working paper (0.05), a predatory 10.5555 DOI (0.00), and an
# off-topic 10.26163 DOI (0.00). Each is on-topic enough to span-verify (the body
# sentence is verbatim from the source span, so it self-entails and PASSES the
# UNCHANGED strict_verify), yet carries ~0 credibility weight and is corroborated by
# nobody. Whether a source EARNED a top-level cited claim is a SURFACE-placement
# (credibility / corroboration) decision, NOT a grounding decision — it is handled
# here at the cite surface, NEVER in the frozen faithfulness engine.
#
# §-1.3 — WEIGHT-and-CONSOLIDATE, never FILTER-and-DROP: this is a ROUTING decision,
# not a removal. A member is PROMOTED (earns a standalone cited claim) if ANY of:
#   * corroboration >= K distinct verified origins (the CONSOLIDATE leg), OR
#   * credibility weight >= W (the WEIGHT leg), OR
#   * its host is a recognized peer-reviewed journal venue (over-demotion guard).
# A single-origin AND below-W AND non-journal member is ROUTED to ``disclosed_only``:
# KEPT in evidence_pool + the credibility disclosure + a dedicated report block, but
# NOT promoted to a standalone numbered finding. Nothing is dropped; conservation holds
# (promoted UNION disclosed_only == the original ordered list). The faithfulness engine
# (strict_verify / NLI / 4-role D8 / span-grounding / provenance) is untouched — weight
# and corroboration are credibility judgments, never a faithfulness gate. The OR-with-
# corroboration leg IS the §-1.3 CONSOLIDATE principle (any source another agrees with is
# rescued). Gated default-ON; ``PG_CWF_PROMOTION_ELIGIBILITY=0`` fails OPEN to promote-all
# => the partition is byte-identical to the legacy keep-all-and-cite selection.
_ENV_PROMOTION = "PG_CWF_PROMOTION_ELIGIBILITY"                 # default ON
_ENV_PROMOTION_MIN_WEIGHT = "PG_CWF_PROMOTION_MIN_WEIGHT"       # LAW VI override (default below)
_ENV_PROMOTION_MIN_CORROBORATION = "PG_CWF_PROMOTION_MIN_CORROBORATION"
_DEFAULT_PROMOTION_MIN_WEIGHT = 0.10   # WEIGHT leg threshold (LAW VI overridable)
_DEFAULT_PROMOTION_MIN_CORROBORATION = 2  # CONSOLIDATE leg: distinct verified origins (LAW VI overridable)
_DISCLOSED_ONLY_REASON = "single_origin_low_weight_non_journal"

# I-deepfix-001 (drb_72) FIX-C — OFF-TOPIC single-origin CITE gate (M5 promotion override).
# drb_72 promoted single-origin spans whose direct quote shares ZERO topical content with the
# research question (MWCNT/graphene materials-science, an unrelated NYSE-IPO CV blurb, a
# corruption/poverty span) into standalone GenAI-labor findings. §-1.3 ROUTE-don't-DROP: such a
# member is routed to ``disclosed_only`` (KEPT in evidence_pool + the credibility disclosure), not
# deleted. FAIL-OPEN by construction — a member PROMOTES whenever ANY of: empty research_question /
# gate OFF / the quote has < 6 content words (too terse to judge topicality) / ANY question-term
# overlap > the min / corroborated (>= K verified origins). Only a corroborated-by-nobody,
# >=6-word, ZERO-overlap span is demoted. The faithfulness engine is UNTOUCHED (topicality is a
# credibility/surface judgment, never a grounding gate). Default-ON; OFF => promote-all =>
# byte-identical to the pre-FIX-C partition.
_ENV_PROMOTION_TOPICAL_GATE = "PG_CWF_PROMOTION_TOPICAL_GATE"              # default ON
_ENV_PROMOTION_MIN_TOPICAL_OVERLAP = "PG_CWF_PROMOTION_MIN_TOPICAL_OVERLAP"  # default 0.0 (LAW VI)
_DEFAULT_PROMOTION_MIN_TOPICAL_OVERLAP = 0.0  # zero-overlap only (LAW VI overridable)
_PROMOTION_TOPICAL_MIN_QUOTE_WORDS = 6  # a quote below this is too terse to judge -> keep-neutral promote


def promotion_topical_gate_enabled() -> bool:
    """Kill-switch ``PG_CWF_PROMOTION_TOPICAL_GATE`` (default ON). OFF => the off-topic demotion
    override never fires => the promotion partition is byte-identical to pre-FIX-C."""
    # I-deepfix-001 (#1369) FIX E — default-ON via the NEGATIVE idiom so an unset AND an empty-string
    # value both read ON (matching the four fix-4-corrected CWF sub-flags). Force-on in the benchmark
    # slate, so this is consistency hardening, not a live-behavior change.
    return os.environ.get(_ENV_PROMOTION_TOPICAL_GATE, "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


def _parse_promotion_min_topical_overlap(raw: Any) -> float:
    """The topical-overlap demotion threshold in [0.0, 1.0] (LAW VI). A member with quote-vs-question
    overlap <= this (and >= 6 quote words and single-origin) is routed to disclosed-only. Garbage =>
    ValueError (fail-loud, never swallowed)."""
    if raw is None or not str(raw).strip():
        value = _DEFAULT_PROMOTION_MIN_TOPICAL_OVERLAP
    else:
        try:
            value = float(str(raw).strip())
        except ValueError as e:
            raise ValueError(
                f"{_ENV_PROMOTION_MIN_TOPICAL_OVERLAP} must be a float in [0.0, 1.0]; got {raw!r}"
            ) from e
    if not (0.0 <= value <= 1.0):
        raise ValueError(
            f"{_ENV_PROMOTION_MIN_TOPICAL_OVERLAP} out of range [0.0, 1.0]: {value}"
        )
    return value


def promotion_eligibility_enabled() -> bool:
    """Kill-switch ``PG_CWF_PROMOTION_ELIGIBILITY`` (default ON). OFF => promote-all =>
    the enrichment selection is byte-identical to the legacy keep-all-and-cite list."""
    return os.environ.get(_ENV_PROMOTION, "1").strip().lower() in (
        "1", "true", "on", "yes", "enabled",
    )


def _parse_promotion_min_weight(raw: Any) -> float:
    """The WEIGHT-leg threshold W in [0.0, 1.0] (LAW VI). Garbage => ValueError (fail-loud)."""
    if raw is None or not str(raw).strip():
        value = _DEFAULT_PROMOTION_MIN_WEIGHT
    else:
        try:
            value = float(str(raw).strip())
        except ValueError as e:
            raise ValueError(
                f"{_ENV_PROMOTION_MIN_WEIGHT} must be a float in [0.0, 1.0]; got {raw!r}"
            ) from e
    if not (0.0 <= value <= 1.0):
        raise ValueError(f"{_ENV_PROMOTION_MIN_WEIGHT} out of range [0.0, 1.0]: {value}")
    return value


def _parse_promotion_min_corroboration(raw: Any) -> int:
    """The CONSOLIDATE-leg threshold K (distinct verified origins), int >= 1 (LAW VI).
    Garbage => ValueError (fail-loud)."""
    if raw is None or not str(raw).strip():
        return _DEFAULT_PROMOTION_MIN_CORROBORATION
    try:
        value = int(str(raw).strip())
    except ValueError as e:
        raise ValueError(
            f"{_ENV_PROMOTION_MIN_CORROBORATION} must be an int >= 1; got {raw!r}"
        ) from e
    if value < 1:
        raise ValueError(f"{_ENV_PROMOTION_MIN_CORROBORATION} must be >= 1: {value}")
    return value


def _host_is_known_journal(url: str) -> bool:
    """Over-demotion guard: a recognized peer-reviewed journal article is ALWAYS
    promotion-eligible regardless of weight, so a freak-low weight can never demote a
    real journal. Pure read of the EXISTING ``PEER_REVIEWED_JOURNAL_DOMAINS`` weighting
    table (a credibility classifier, not a faithfulness gate). Lazy import keeps this
    module free of any retrieval-side dependency; any error fails-CLOSED (not a journal)
    so the guard can only RESCUE, never accidentally demote."""
    if not url:
        return False
    try:
        from urllib.parse import urlparse

        from src.polaris_graph.retrieval.tier_classifier import (
            PEER_REVIEWED_JOURNAL_DOMAINS,
            _domain_matches,
        )

        host = (urlparse(url).hostname or "").lower()
        return bool(host) and _domain_matches(host, PEER_REVIEWED_JOURNAL_DOMAINS)
    except Exception:  # noqa: BLE001 — guard fails CLOSED (treat as non-journal); never raises
        return False


def contract_bound_evidence_ids(contract_plans: Any) -> set[str]:
    """The evidence_ids already inside the contract render universe (excluded from enrichment).

    Robust against duck-typed plan shapes: unions a plan's ``ev_ids`` (the SectionPlan field
    every contract plan mirrors) with every ``slot.entity_ids`` it carries. Missing attrs are
    treated as empty so a shape change can NEVER over-exclude into an empty enrichment.
    """
    bound: set[str] = set()
    for plan in contract_plans or ():
        for eid in (getattr(plan, "ev_ids", None) or ()):
            if eid:
                bound.add(str(eid))
        for slot in (getattr(plan, "slots", None) or ()):
            for eid in (getattr(slot, "entity_ids", None) or ()):
                if eid:
                    bound.add(str(eid))
    return bound


# I-arch-007 #1264 CHOKE-FIX (observability): the enrichment had several independent silent-empty
# exits (credibility None / no baskets / no SUPPORTS members at all / every SUPPORTS member already
# bound or pool-absent) and the call site logged ONLY the success branch. That is why the operator
# saw "zero appended weighted-enrichment section log lines in ALL reports" and could not tell WHICH
# gate killed it. Each reason below is a stable machine-readable token the call site logs LOUDLY so a
# no-op is never silent again.
#
# I-arch-007 #1264 had a FIFTH exit — "every remaining member below the relevance floor" — because
# the selection HARD-DROPPED below-floor rows. I-arch-011 (B18) REMOVED that drop (keep-all-sort-
# below-floor-last), so a below-floor row can NEVER cause an empty exit any more. The empty case is
# now honestly one of: degraded credibility / no baskets / no SUPPORTS member / all bound-or-pool-
# absent. The `_REASON_ALL_BELOW_FLOOR` token is therefore RETIRED (it can no longer be reached).
_REASON_OK = "ok"
_REASON_CREDIBILITY_NONE = "credibility_analysis_none"  # degrade / flag-off path
_REASON_NO_BASKETS = "no_baskets"
_REASON_NO_SUPPORTS_MEMBERS = "no_supports_members"  # baskets exist but no SUPPORTS member at all
_REASON_ALL_BOUND_OR_ABSENT = "all_supports_bound_or_pool_absent"


class UnboundSupportsSelection(NamedTuple):
    """The selection result + a diagnostic breakdown of WHY it is what it is.

    ``ev_ids`` is the FULL ordered surviving list (no cap, no floor drop). The counters make every
    empty-exit auditable: the call site logs ``reason`` LOUDLY so a degraded credibility pass can
    never silently no-op the breadth fix again. ALL counters are pure READS — nothing here touches a
    faithfulness gate.

    I-arch-011 (B18): ``excluded_below_floor`` is RETAINED as the field NAME (the call site at
    multi_section_generator.py:6794/6822 reads it) but its MEANING is now pure TELEMETRY — the count
    of KEPT rows that sit below ``PG_RELEVANCE_FLOOR`` (sorted LAST), NOT an exclusion. A below-floor
    row is never dropped any more, so this counter can never reduce ``ev_ids``.
    """
    ev_ids: list[str]
    reason: str
    baskets_seen: int
    supports_members_seen: int
    excluded_bound: int
    excluded_pool_absent: int
    # I-arch-011 (B18): kept-but-below-floor count (telemetry); NOT an exclusion. Field name held
    # stable for the out-of-lane consumer (multi_section_generator.py:6794/6822).
    excluded_below_floor: int
    # I-deepfix-001 (#1344) DEFER-1: evidence_ids of SUPPORTS members SUPPRESSED FROM
    # CITATION because a SEMANTIC judge confirmed them OFF-topic (kept in
    # evidence_pool + the credibility disclosure — never deleted, never a faithfulness
    # change). Default () keeps the legacy 7-positional constructors valid + the OFF
    # path (PG_OFFTOPIC_CITE_SUPPRESS=0 => empty) byte-identical. Pure TELEMETRY +
    # the disclosed off-topic-excluded-from-citation set the call site surfaces.
    offtopic_suppressed: tuple[str, ...] = ()
    # I-deepfix-001 (#1344 M5): PROMOTION-ELIGIBILITY partition — the members ROUTED to
    # DISCLOSED-ONLY (kept in evidence_pool + the credibility disclosure, re-surfaced in a
    # dedicated report block, but NOT promoted to a standalone numbered finding) because each is
    # single-origin (uncorroborated) AND below the credibility-weight bar AND not a recognized
    # journal venue. Each record: ``{evidence_id, source_url, source_tier, credibility_weight,
    # reason}``. Append-only LAST field (default () keeps every legacy positional constructor valid
    # AND the OFF path byte-identical). NOT a drop — a ROUTE; conservation holds (``ev_ids`` UNION
    # ``disclosed_only`` == the full ordered list); the faithfulness engine is untouched.
    disclosed_only: tuple[dict[str, Any], ...] = ()


# I-deepfix-001 WS-8 (D4) part 2: COMPOSITION-ordering recency leg. The bibliography re-rank alone did not
# stop the headline breach (Codex: the 1986 source headlined from the selection/composition path). This
# demotes an OLD source in the unbound-supports selection ORDERING so it no longer anchors a top finding —
# a WEIGHT on the sort key only, NEVER a filter (the full list is kept; nothing is dropped/capped — §-1.3).
# Journal-class only: gated on PG_DOCUMENT_TYPE_WEIGHT (the journal-class signal, same as the bib re-rank)
# AND PG_COMPOSITION_RECENCY (default-ON); OFF, non-journal-class, or unknown/absent year => factor 1.0 =>
# byte-identical ordering. Reuses the SAME env-tunable curve as the bibliography leg (PG_M2_RECENCY_*).
_COMPOSITION_RECENCY_ENV = "PG_COMPOSITION_RECENCY"
_WE_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")


def _composition_recency_enabled() -> bool:
    """Journal-class gate: the composition recency leg fires only when PG_DOCUMENT_TYPE_WEIGHT is ON (the
    journal-class run signal) AND PG_COMPOSITION_RECENCY is not disabled (default-ON)."""
    dtw = os.environ.get("PG_DOCUMENT_TYPE_WEIGHT", "").strip().lower() in ("1", "true", "on", "yes")
    comp = os.environ.get(_COMPOSITION_RECENCY_ENV, "1").strip().lower() not in ("0", "false", "no", "off")
    return dtw and comp


def _we_publication_year(entry: "dict | None") -> "int | None":
    """Publication year of an evidence-pool entry: an explicit year field, else the first plausible
    4-digit year in title/statement/direct_quote/url/doi. None when none found (=> no penalty)."""
    if not isinstance(entry, dict):
        return None
    for k in ("year", "publication_year", "pub_year"):
        v = entry.get(k)
        if v is None:
            continue
        try:
            y = int(str(v).strip()[:4])
        except (TypeError, ValueError):
            continue
        if 1500 <= y <= 2100:
            return y
    for k in ("title", "statement", "direct_quote", "url", "doi"):
        m = _WE_YEAR_RE.search(str(entry.get(k) or ""))
        if m:
            y = int(m.group(0))
            if 1500 <= y <= 2100:
                return y
    return None


def _we_recency_factor(year: "int | None", reference_year: "int | None") -> float:
    """A [floor, 1.0] ordering multiplier: 1.0 within ``grace`` years of the corpus-newest source, decaying
    linearly by ``decay`` per year older, FLOORED (an old source is DEMOTED for headline order, never
    dropped). Same env curve as the bibliography leg. Missing year / disabled => 1.0."""
    if year is None or reference_year is None or not _composition_recency_enabled():
        return 1.0
    try:
        grace = int(os.getenv("PG_M2_RECENCY_GRACE_YEARS", "5"))
        decay = float(os.getenv("PG_M2_RECENCY_DECAY_PER_YEAR", "0.02"))
        floor = float(os.getenv("PG_M2_RECENCY_FLOOR", "0.25"))
    except (TypeError, ValueError):
        grace, decay, floor = 5, 0.02, 0.25
    age = max(0, int(reference_year) - int(year) - grace)
    return max(floor, 1.0 - decay * age)


# ─────────────────────────────────────────────────────────────────────────────
# I-deepfix-001 (U9) — TOPICAL question-overlap ORDERING weight.
#
# THE BUG (drb_72 AI-labor cited logistics blogs; a PD-DBS run cited elder-abuse
# sources): query-decomposition emits off-topic sub-queries and the ONLY per-row
# relevance signal on the surfacing path is ``selection_relevance`` — a per-passage
# SEMANTIC score. A semantically-fluent but topically-foreign passage (a
# supply-chain article that reads coherently) can score a high ``selection_relevance``
# and, being the PRIMARY sort key here, WRRF-fuse to the TOP of the cited breadth
# surface — so an off-topic source LEADS the findings. The semantic score does not
# capture whether the source is ABOUT the research question's topic.
#
# THE FIX — §-1.3 WEIGHT, DON'T FILTER: add a second, TOPICAL relevance signal —
# the lexical overlap between the source text and the research-question topic terms —
# as an ORDERING multiplier on the existing relevance sort key. An off-topic source
# (near-zero question-term overlap) is DEMOTED in the order (its relevance key is
# scaled toward ``PG_TOPICAL_RELEVANCE_FLOOR``) so it no longer top-fuses, while an
# on-topic source keeps its full relevance key. This is a pure RE-ORDER over the
# SAME kept set — NOTHING is dropped, capped, or thinned; conservation holds (the
# returned ev_ids are the identical set, only re-ordered). It is the exact same class
# as the WS-8 recency ordering leg above and the ``key_findings`` sentence-relevance
# re-order weight, and it reuses the EXISTING grounding tokenizer
# (``provenance_generator._content_words``) — no new model, no new word list, no spend.
# The faithfulness engine (strict_verify / NLI / 4-role D8 / span-grounding /
# provenance) is UNTOUCHED. Default-ON, gated by ``PG_TOPICAL_RELEVANCE_WEIGHT``; an
# empty ``research_question`` (every legacy caller) or the gate OFF => factor 1.0 for
# every row => byte-identical legacy ordering.
_ENV_TOPICAL_RELEVANCE_WEIGHT = "PG_TOPICAL_RELEVANCE_WEIGHT"
_ENV_TOPICAL_RELEVANCE_FLOOR = "PG_TOPICAL_RELEVANCE_FLOOR"
# The row text fields scanned for question-term overlap (the same source-content
# fields finding_dedup / provenance read). Read-only; order-insensitive.
_TOPIC_TEXT_FIELDS = (
    "title", "statement", "claim", "direct_quote", "snippet", "summary", "text", "body",
)


def topical_relevance_weight_enabled() -> bool:
    """Kill-switch ``PG_TOPICAL_RELEVANCE_WEIGHT`` (default ON). OFF => every topical
    factor is 1.0 => the surfacing ORDER is byte-identical to the legacy ordering."""
    return os.environ.get(_ENV_TOPICAL_RELEVANCE_WEIGHT, "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


def _topical_relevance_floor() -> float:
    """The [floor, 1.0] ORDERING multiplier's lower bound for a zero-overlap (off-topic)
    row. Default 0.25 (an off-topic row keeps at most 25% of its relevance sort value, so
    it sinks below every on-topic row — a DEMOTION, never a drop). A garbage value is an
    operator config error and raises ValueError (LAW VI: fail-loud, never swallowed)."""
    raw = os.environ.get(_ENV_TOPICAL_RELEVANCE_FLOOR)
    if raw is None or not str(raw).strip():
        return 0.25
    val = float(raw)  # ValueError on garbage: fail loud
    if not (0.0 <= val <= 1.0):
        raise ValueError(
            f"{_ENV_TOPICAL_RELEVANCE_FLOOR} must be in [0.0, 1.0]; got {val!r}"
        )
    return val


def _question_topic_terms(research_question: str) -> frozenset[str]:
    """Content-word topic terms of the research question, or an empty set when the
    question is blank / has no content words (=> topical factor 1.0 => byte-identical).
    Reuses the EXISTING grounding tokenizer (alphabetic, >=3 chars, stopword-stripped);
    imported LAZILY (mirrors ``key_findings``) so this module keeps its import-time
    independence. PURE — no network, no GPU, no LLM."""
    if not research_question or not research_question.strip():
        return frozenset()
    from src.polaris_graph.generator.provenance_generator import (  # noqa: PLC0415
        _content_words,
    )
    return frozenset(_content_words(research_question))


def _topical_overlap(row: Any, question_terms: frozenset[str]) -> float:
    """Overlap coefficient of the row's source text against the question topic terms:
    ``|row_terms & question_terms| / |question_terms|`` in [0.0, 1.0]. Returns 1.0
    (keep-neutral) when there are no question terms; 0.0 when the row carries no usable
    text. A missing row (not a dict) is keep-neutral (1.0) — pool membership already
    implies the row passed the upstream retrieval relevance gate once. PURE."""
    if not question_terms:
        return 1.0
    if not isinstance(row, dict):
        return 1.0
    from src.polaris_graph.generator.provenance_generator import (  # noqa: PLC0415
        _content_words,
    )
    parts = [str(row.get(f) or "") for f in _TOPIC_TEXT_FIELDS]
    row_terms = _content_words(" ".join(p for p in parts if p))
    if not row_terms:
        return 0.0
    return len(row_terms & question_terms) / len(question_terms)


def _topical_factor(overlap: float, floor: float) -> float:
    """Map a question-topic overlap in [0.0, 1.0] to a [floor, 1.0] ORDERING multiplier:
    overlap 1.0 => 1.0 (on-topic, full weight), overlap 0.0 => ``floor`` (off-topic,
    demoted but KEPT). Linear so the demotion is monotone in topicality."""
    ov = max(0.0, min(1.0, overlap))
    return floor + (1.0 - floor) * ov


# ─────────────────────────────────────────────────────────────────────────────
# I-deepfix-001 (#1344 SPAN-TOPICALITY) — HIGH-PRECISION, fail-OPEN per-SPAN
# off-topic WITHHOLD (§-1.3 WITHHOLD-and-disclose per span; the SOURCE is NEVER
# dropped — it stays in evidence_pool + the credibility disclosure, and every other
# span it carries still cites; the frozen faithfulness engine strict_verify / NLI /
# 4-role D8 / provenance / span-grounding is UNTOUCHED).
#
# PRIOR-FIX DEFECT (Codex P1): the first cut flagged a span off-topic whenever it
# shared ZERO exact ``_content_words`` with ONLY the top-level research question. That
# over-withheld genuinely on-topic spans that phrase the topic with SYNONYMS, ACRONYMS,
# ENTITY NAMES, or lower-level terms (a "labor" question vs an on-topic span about
# "automation exposure in clerical occupations"; a "GLP-1 obesity" question vs a
# "semaglutide reduces BMI" span). If every one of a source's spans missed the exact
# question vocabulary the whole source silently vanished from citation though on-topic.
#
# PRECISION-SAFE REWRITE: a span is CONFIDENTLY foreign ONLY when it shares nothing with
# EITHER of TWO references — (1) the research-question topic terms AND (2) the source's
# OWN rich local topic (its title/metadata fields UNIONED with every SIBLING span's
# content words). A synonym/acronym/entity/lower-level on-topic span still shares
# vocabulary with the rest of its OWN coherent document, so it clears reference (2) and
# is KEPT. Only a paragraph foreign to the question AND to its own document — a Gaza-
# ceasefire sentence embedded in an AI-labor report — is WITHHELD. Every ambiguity
# fails OPEN (KEEP): empty question, a short span, a thin local reference, or ANY shared
# term on EITHER reference. This never nukes an off-topic SOURCE (its spans share the
# source's own dominant topic, so they are all KEPT — the source's fate is decided at
# the basket/source level by ``_is_confirmed_offtopic``, not here). Gated default-ON;
# ``PG_OFFTOPIC_SPAN_SUPPRESS=0`` restores the byte-identical legacy keep-all behaviour.
_ENV_OFFTOPIC_SPAN_SUPPRESS = "PG_OFFTOPIC_SPAN_SUPPRESS"                    # default ON
_ENV_OFFTOPIC_SPAN_MIN_CONTENT_WORDS = "PG_OFFTOPIC_SPAN_MIN_CONTENT_WORDS"  # LAW VI override
_ENV_OFFTOPIC_SPAN_MIN_LOCAL_TERMS = "PG_OFFTOPIC_SPAN_MIN_LOCAL_TERMS"      # LAW VI override
# A span shorter than this many content words is too terse to judge foreign confidently
# => KEEP (fail-open). A local reference (title + siblings) thinner than the min-local
# floor cannot attest the source's topic reliably => KEEP (fail-open).
_DEFAULT_OFFTOPIC_SPAN_MIN_CONTENT_WORDS = 6
_DEFAULT_OFFTOPIC_SPAN_MIN_LOCAL_TERMS = 8
# The source's TITLE / METADATA fields that describe its dominant topic. DELIBERATELY
# EXCLUDES the quote-body fields (``direct_quote`` / ``statement`` / ``text`` / ``body``
# that ``_TOPIC_TEXT_FIELDS`` carries): the spans being judged ARE the quote body, so
# folding it into the local reference would make every span trivially self-overlap and
# silently NO-OP the gate. The source's OTHER spans are the SIBLING reference, added
# separately in ``_withhold_offtopic_spans``.
_SOURCE_TOPIC_TITLE_FIELDS = (
    "source_title", "title", "page_title", "name", "section_title",
    "topic", "subject", "keywords",
)


def offtopic_span_suppress_enabled() -> bool:
    """Kill-switch ``PG_OFFTOPIC_SPAN_SUPPRESS`` (default ON). OFF => no span is ever
    withheld on topicality => byte-identical to the legacy keep-all cite behaviour."""
    return os.environ.get(_ENV_OFFTOPIC_SPAN_SUPPRESS, "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


def _env_positive_int(name: str, default: int) -> int:
    """Parse a positive-int env override (fail LOUD on garbage per LAW VI); unset => default."""
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        val = int(str(raw).strip())
    except ValueError as e:
        raise ValueError(f"{name} must be an int >= 1; got {raw!r}") from e
    if val < 1:
        raise ValueError(f"{name} must be >= 1: {val}")
    return val


def _offtopic_span_min_content_words() -> int:
    return _env_positive_int(
        _ENV_OFFTOPIC_SPAN_MIN_CONTENT_WORDS, _DEFAULT_OFFTOPIC_SPAN_MIN_CONTENT_WORDS
    )


def _offtopic_span_min_local_terms() -> int:
    return _env_positive_int(
        _ENV_OFFTOPIC_SPAN_MIN_LOCAL_TERMS, _DEFAULT_OFFTOPIC_SPAN_MIN_LOCAL_TERMS
    )


def _span_is_confidently_offtopic(
    unit_terms: "frozenset[str] | set[str]",
    question_terms: "frozenset[str] | set[str]",
    local_topic_terms: "frozenset[str] | set[str]",
    min_content_words: int,
    min_local_terms: int,
) -> bool:
    """True ONLY when a span is CONFIDENTLY foreign to BOTH the research question AND its
    OWN source's rich local topic. Every ambiguity fails OPEN (returns False => KEEP)."""
    if not question_terms:
        return False                        # no question topic => never judge => KEEP
    if len(unit_terms) < min_content_words:
        return False                        # span too terse to judge => KEEP
    if unit_terms & question_terms:
        return False                        # shares a QUESTION term => on-topic => KEEP
    if len(local_topic_terms) < min_local_terms:
        return False                        # local reference too thin to judge => KEEP
    if unit_terms & local_topic_terms:
        return False                        # coherent with its OWN document => KEEP
    # Zero overlap with the question AND with the source's own dominant topic: a genuinely
    # foreign paragraph (a Gaza-ceasefire sentence in an AI-labor report) => WITHHOLD.
    return True


def _corpus_topic_terms(pool: "dict[str, Any]") -> "dict[str, int]":
    """Map each on-topic content word to the NUMBER OF DISTINCT SOURCES that contain it
    (across every source's title/metadata fields + quote body). The per-span off-topic
    gate treats a word as shared corpus vocabulary only when it appears in a source OTHER
    than the one being judged (Codex iter-2 P1: a plain union self-overlaps because a
    source's own quote is in it, which would keep every span incl a foreign one). Counting
    distinct sources lets the gate subtract the current source's SOLE-authored words while
    retaining genuinely shared on-topic vocabulary. Computed once per pass."""
    from collections import Counter  # noqa: PLC0415
    from src.polaris_graph.generator.provenance_generator import (  # noqa: PLC0415
        _content_words,
    )
    counts: "Counter[str]" = Counter()
    for ev in (pool or {}).values():
        if not isinstance(ev, dict):
            continue
        source_terms = set(
            _content_words(
                " ".join(str(ev.get(f) or "") for f in _SOURCE_TOPIC_TITLE_FIELDS)
            )
        )
        source_terms |= set(_content_words(str(_member_quote(ev) or "")))
        for term in source_terms:
            counts[term] += 1
    return dict(counts)


def _withhold_offtopic_spans(
    units: "list[str]",
    ev: "dict[str, Any]",
    question_terms: "frozenset[str] | set[str]",
    min_content_words: int,
    min_local_terms: int,
    corpus_topic_terms: "frozenset[str] | set[str] | None" = None,
) -> "list[str]":
    """Return ``units`` with CONFIDENTLY-foreign spans withheld from CITATION (fail-open).

    Builds the source's RICH local topic reference ONCE — its title/metadata fields
    (``_SOURCE_TOPIC_TITLE_FIELDS``, which EXCLUDE the quote body) UNIONED with the
    content words of the source's OTHER spans — then keeps every span except those
    foreign to BOTH the question and that reference. No question terms / no units =>
    unchanged (byte-identical). The source is never dropped; the frozen faithfulness
    engine is never touched (this only chooses which verbatim spans of an already-
    verified source are surfaced as citations)."""
    if not question_terms or not units:
        return units
    from src.polaris_graph.generator.provenance_generator import (  # noqa: PLC0415
        _content_words,
    )
    title_terms = _content_words(
        " ".join(str((ev or {}).get(f) or "") for f in _SOURCE_TOPIC_TITLE_FIELDS)
    )
    unit_terms = [set(_content_words(u or "")) for u in units]
    # Codex-P1 (iter 2 -> iter 3) answer: a span is withheld only when it is foreign to the
    # OTHER sources' established on-topic vocabulary. `corpus_topic_terms` maps each word to
    # the number of DISTINCT sources containing it; the current source's OWN words (title +
    # every unit) are excluded unless another source ALSO uses them. This KEEPS a lower-level
    # / synonym / entity on-topic span ("clerical occupations": occupations/workers appear in
    # OTHER sources -> retained) while a truly foreign span (a Gaza-ceasefire sentence whose
    # gaza/ceasefire/hostages words appear in NO other source) is still WITHHELD. Without this
    # subtraction the source's own quote self-overlaps and the gate keeps everything.
    corpus_counts: "dict[str, int]" = dict(corpus_topic_terms or {})
    own_terms: set = set(title_terms)
    for terms in unit_terms:
        own_terms |= terms
    corpus_ref: set = {
        w for w, c in corpus_counts.items()
        if c > (1 if w in own_terms else 0)
    }
    kept: list[str] = []
    for i, unit in enumerate(units):
        # Local reference = title/metadata terms + EVERY OTHER span's terms (never this
        # span's own words, which would self-overlap and defeat the foreign test). A
        # synonym/acronym on-topic span shares vocabulary with a sibling span here.
        sibling_terms: set[str] = set()
        for j, terms in enumerate(unit_terms):
            if j != i:
                sibling_terms |= terms
        local_ref = title_terms | sibling_terms | corpus_ref
        if _span_is_confidently_offtopic(
            unit_terms[i], question_terms, local_ref, min_content_words, min_local_terms
        ):
            logger.info(
                "[weighted_enrichment] I-deepfix-001 SPAN-TOPICALITY: WITHHELD "
                "confidently-foreign span from citation (source kept in evidence_pool + "
                "disclosure; faithfulness engine untouched): %r",
                (unit or "")[:160],
            )
            continue
        kept.append(unit)
    # FAIL-OPEN SAFETY (Codex-P1 answer): the span gate must NEVER empty a source. If
    # every span was judged foreign (a pathological source of only-unrelated paragraphs),
    # KEEP the source's spans unchanged — a source's fate is decided at the basket/source
    # level (``_is_confirmed_offtopic``), never by this per-span citation gate.
    if not kept:
        return units
    return kept


def diagnose_unbound_supports_selection(
    *,
    evidence_pool: Any,
    credibility_analysis: Any,
    contract_plans: Any,
    research_question: str = "",
) -> UnboundSupportsSelection:
    """``select_unbound_supports_by_weight`` + a diagnostic breakdown (the same selection logic).

    Identical surviving list + ordering as ``select_unbound_supports_by_weight`` (which delegates
    here), PLUS the per-exit counters that make a silent no-op impossible. Faithfulness-neutral:
    this only READS already-computed state; it surfaces nothing into the report by itself.
    """
    if credibility_analysis is None:
        return UnboundSupportsSelection([], _REASON_CREDIBILITY_NONE, 0, 0, 0, 0, 0)
    baskets = getattr(credibility_analysis, "baskets", None) or []
    if not baskets:
        return UnboundSupportsSelection([], _REASON_NO_BASKETS, 0, 0, 0, 0, 0)
    bound = contract_bound_evidence_ids(contract_plans)
    pool = evidence_pool or {}

    # EXISTING relevance gate (no new constant): reuse the retrieval gate's parser so the breadth
    # surfacing applies the SAME PG_RELEVANCE_FLOOR (default 0.30) + the SAME fail-loud (0.0, 1.0]
    # validation. Lazy import (reading, not a cross-module edit) mirrors live_retriever.py:3186.
    from src.polaris_graph.retrieval.evidence_selector import parse_relevance_floor

    relevance_floor = parse_relevance_floor(os.environ.get("PG_RELEVANCE_FLOOR"))

    # Per-eid: the HIGHEST basket weight_mass it appears under (ordering only, never a filter) and
    # its topicality score for the relevance-first ordering.
    best_weight: dict[str, float] = {}
    relevance_by_eid: dict[str, float | None] = {}
    supports_members_seen = 0
    excluded_bound = 0
    excluded_pool_absent = 0
    below_floor_count = 0  # I-arch-011 (B18): KEPT-but-below-floor (telemetry); NEVER an exclusion.
    # I-deepfix-001 (#1344) DEFER-1: SEMANTIC confirmed-OFF members withheld from the
    # CITED breadth surface (kept in pool + disclosure; NOT a faithfulness change).
    suppress_offtopic = offtopic_cite_suppress_enabled()
    offtopic_suppressed: list[str] = []
    # I-deepfix-001 (#1344 M5) PROMOTION-ELIGIBILITY accumulators (most-favorable-to-promotion so
    # any demotion is conservative): per-eid the MAX member ``credibility_weight`` seen (absent =>
    # unknown => keep-neutral promote), the MAX basket ``verified_support_origin_count`` (the
    # CONSOLIDATE leg), whether ANY member's host is a recognized peer-reviewed journal venue (the
    # over-demotion guard), and a tier label for the disclosure surface. Pure READS of already-
    # computed credibility state — no faithfulness gate is touched.
    best_cred_weight: dict[str, float] = {}
    max_origin: dict[str, int] = {}
    is_journal: dict[str, bool] = {}
    best_tier: dict[str, str] = {}
    # I-deepfix-001 (drb_72) FIX-C: per-eid topical signals for the off-topic promotion override.
    # ``q_terms`` is the question's content-word topic set (empty => fail-open promote-all).
    # ``best_quote_overlap`` = MAX quote-vs-question overlap; ``quote_words`` = quote content-word
    # count. Computed ONLY when the gate is enabled (else empty => the override never fires).
    _promo_topical_gate = promotion_topical_gate_enabled()
    _promo_q_terms = _question_topic_terms(research_question) if _promo_topical_gate else frozenset()
    best_quote_overlap: dict[str, float] = {}
    quote_words: dict[str, int] = {}
    for basket in baskets:
        try:
            weight = float(getattr(basket, "weight_mass", 0.0) or 0.0)
        except (TypeError, ValueError):
            weight = 0.0
        # I-deepfix-001 (#1344 M5): the basket's distinct isolated-verified origin count (the
        # CONSOLIDATE-leg signal). Non-int / missing => 0 (conservative: no corroboration credit).
        try:
            verified_origin = int(getattr(basket, "verified_support_origin_count", 0) or 0)
        except (TypeError, ValueError):
            verified_origin = 0
        for member in (getattr(basket, "supporting_members", None) or ()):
            if str(getattr(member, "span_verdict", "")).strip().upper() != _SUPPORTS:
                continue  # CONSOLIDATE: only isolated-verified SUPPORTS members are offered
            supports_members_seen += 1
            eid = str(getattr(member, "evidence_id", "") or "")
            if not eid:
                continue
            if eid in bound:
                excluded_bound += 1
                continue
            if eid not in pool:
                excluded_pool_absent += 1
                continue
            # I-deepfix-001 (#1344) DEFER-1: a member a SEMANTIC judge confirmed OFF-topic
            # (topic-gate / W2 label) is WITHHELD FROM CITATION — not surfaced into the
            # breadth section's ev_ids, so the bibliography numberer never assigns it [N].
            # §-1.3-SAFE: it is NOT a lexical ``relevance < floor`` drop (that is the banned
            # keystone DROP); it keys ONLY on the confirmed-OFF verdict, and the source STAYS
            # in evidence_pool + the credibility disclosure (kept-and-disclosed, never deleted).
            # The faithfulness engine (strict_verify / NLI / 4-role / span-grounding) is
            # untouched. OFF (PG_OFFTOPIC_CITE_SUPPRESS=0) => no member is skipped => the
            # ev_ids list is byte-identical to the legacy keep-all-and-cite behaviour.
            if suppress_offtopic and _is_confirmed_offtopic(pool.get(eid)):
                offtopic_suppressed.append(eid)
                continue
            # I-arch-011 (B18) — WEIGHT, DON'T FILTER (§-1.3, the keystone): the pre-fix code
            # RE-IMPOSED a hard ``relevance < floor`` DROP here — the FILTER-AND-CAP anti-pattern the
            # selector docstring (evidence_selector.py:1944-1953) forbids, which killed 729/746
            # unbound SUPPORTS. KEEP-ALL-AND-SORT-BELOW-FLOOR-LAST: a below-floor row is NEVER
            # excluded; it is KEPT and demoted in the ORDER (sorted last) exactly the way the
            # retrieval pool down-weights a below-floor row (evidence_selector.py:2066-2070). A
            # missing/unparseable score is keep-neutral (sentinel 0.0), NOT below-floor — pool
            # membership already implies the retrieval floor passed once. ``below_floor_count`` is
            # pure telemetry: how many KEPT rows sit below the floor, never an exclusion. The ONLY
            # hard gate is the UNCHANGED strict_verify each surfaced sentence still must pass.
            relevance = _row_relevance(pool.get(eid))
            if relevance is not None and relevance < relevance_floor:
                below_floor_count += 1  # KEPT (sorts last), never dropped
            if eid not in best_weight or weight > best_weight[eid]:
                best_weight[eid] = weight
            # First-seen relevance is deterministic across baskets (same row); keep it stable.
            relevance_by_eid.setdefault(eid, relevance)
            # I-deepfix-001 (#1344 M5): accumulate the promotion-eligibility signals for this eid
            # (most-favorable-to-promotion). ``credibility_weight`` is the MEMBER's own credibility
            # (BasketMember.credibility_weight); None/unparseable is left unknown (=> promote-neutral).
            _mw = getattr(member, "credibility_weight", None)
            if _mw is not None:
                try:
                    _mw = float(_mw)
                except (TypeError, ValueError):
                    _mw = None
            if _mw is not None:
                _prev_w = best_cred_weight.get(eid)
                best_cred_weight[eid] = _mw if _prev_w is None else max(_prev_w, _mw)
            if verified_origin > max_origin.get(eid, 0):
                max_origin[eid] = verified_origin
            if not is_journal.get(eid, False):
                _murl = str(getattr(member, "source_url", "") or "") or str(
                    (pool.get(eid) or {}).get("source_url")
                    or (pool.get(eid) or {}).get("url")
                    or ""
                )
                if _host_is_known_journal(_murl):
                    is_journal[eid] = True
            if not best_tier.get(eid):
                _mt = str(getattr(member, "source_tier", "") or "")
                if _mt:
                    best_tier[eid] = _mt
            # I-deepfix-001 (drb_72) FIX-C: quote-vs-question topical overlap + quote content-word
            # count for the off-topic promotion override. Computed once per eid (the member quote
            # is stable across baskets); only when the gate is enabled and the question has terms.
            if _promo_topical_gate and _promo_q_terms and eid not in quote_words:
                from src.polaris_graph.generator.provenance_generator import (  # noqa: PLC0415
                    _content_words,
                )
                _qw = set(_content_words(str(_member_quote(pool.get(eid)) or "")))
                quote_words[eid] = len(_qw)
                best_quote_overlap[eid] = len(_qw & _promo_q_terms) / len(_promo_q_terms)

    # I-arch-011 (B18) ORDER, KEEP-ALL-SORT-BELOW-FLOOR-LAST:
    #   1. ``is_below_floor`` (False before True) — a PRESENT-and-below-floor row sorts AFTER every
    #      at/above-floor row AND after every missing-relevance row (a missing score is keep-neutral,
    #      NOT below-floor, so it ranks ahead of a genuine below-floor row).
    #   2. relevance-to-question DESC (within the same below-floor bucket).
    #   3. weight_mass DESC (priority of consideration).
    #   4. evidence_id (deterministic tiebreak).
    # A missing relevance uses the CONSTANT sentinel (0.0) and ``is_below_floor=False`` so a pool of
    # all-missing-relevance rows reproduces today's pure weight-desc order. FULL list — no cap/top-N,
    # no floor DROP.
    def _is_below_floor(eid: str) -> bool:
        rel = relevance_by_eid.get(eid)
        return rel is not None and rel < relevance_floor

    # WS-8 (D4) part 2: corpus-relative recency factor applied to the weight_mass ORDERING term (never to
    # relevance, never a filter). Journal-class only + byte-identical when off/unknown-year. Computed once.
    _year_by_eid = {eid: _we_publication_year(pool.get(eid)) for eid in best_weight}
    _years = [y for y in _year_by_eid.values() if y is not None]
    _ref_year = max(_years) if _years else None

    # I-deepfix-001 (U9): TOPICAL question-overlap ORDERING factor, computed once. Multiplies the
    # relevance sort key (a WEIGHT on the order, never a filter): an off-topic row (near-zero question-
    # term overlap) is DEMOTED toward the floor so it no longer top-fuses, while an on-topic row keeps
    # its full relevance key. Gate OFF or empty ``research_question`` => empty term set => factor 1.0 for
    # every row => byte-identical legacy ordering. The full kept set is preserved (nothing dropped).
    _q_terms = (
        _question_topic_terms(research_question)
        if topical_relevance_weight_enabled()
        else frozenset()
    )
    _topical_floor = _topical_relevance_floor()
    _topical_factor_by_eid = {
        eid: _topical_factor(_topical_overlap(pool.get(eid), _q_terms), _topical_floor)
        for eid in best_weight
    }

    ev_ids = [
        eid
        for eid, _ in sorted(
            best_weight.items(),
            key=lambda kv: (
                _is_below_floor(kv[0]),                       # False (0) before True (1)
                # I-deepfix-001 (U9): relevance sort key scaled by the TOPICAL question-overlap factor
                # (demotes an off-topic row within its bucket; factor 1.0 when the leg is off / no
                # question / no question terms => byte-identical). §-1.3 WEIGHT, never a drop.
                -(_relevance_sort_key(relevance_by_eid.get(kv[0]))
                  * _topical_factor_by_eid.get(kv[0], 1.0)),
                # WS-8 (D4): demote an OLD source in the weight_mass ordering (still kept — §-1.3); factor
                # 1.0 when the recency leg is off / non-journal-class / year unknown => byte-identical.
                -(kv[1] * _we_recency_factor(_year_by_eid.get(kv[0]), _ref_year)),
                kv[0],
            ),
        )
    ]

    # I-arch-011 (B18): the empty case can no longer be "all below floor" (the floor never
    # excludes). Report the TRUE reason: no SUPPORTS member at all, else everything bound/pool-absent.
    # I-deepfix-001 (#1344 M5): ``reason`` is computed from the FULL surviving list BEFORE the
    # promotion partition, so it honestly reports whether any unbound SUPPORTS member was FOUND —
    # the partition only ROUTES the found members into promoted vs disclosed-only, it never changes
    # whether members existed.
    if ev_ids:
        reason = _REASON_OK
    elif supports_members_seen == 0:
        reason = _REASON_NO_SUPPORTS_MEMBERS
    else:
        reason = _REASON_ALL_BOUND_OR_ABSENT

    # I-deepfix-001 (#1344 M5) PROMOTION-ELIGIBILITY PARTITION — route (NOT drop) near-zero,
    # single-origin, non-journal members to ``disclosed_only`` (kept + re-surfaced, never deleted).
    # §-1.3: WEIGHT-and-CONSOLIDATE — a member is PROMOTED if its weight clears W OR another source
    # corroborates it (>= K verified origins) OR it is a recognized journal venue; only a member
    # failing ALL three is routed to disclosed-only. Conservation holds: ``promoted`` UNION
    # ``disclosed_only`` == the full ``ev_ids`` above (nothing vanishes). The faithfulness engine is
    # untouched — weight/corroboration are credibility judgments, never a grounding gate.
    disclosed_only: list[dict[str, Any]] = []
    if promotion_eligibility_enabled():
        # FAIL-LOUD env parse (LAW VI): a garbage threshold is an operator config error and raises
        # ValueError, NOT swallowed by the fail-open guard below.
        min_w = _parse_promotion_min_weight(os.environ.get(_ENV_PROMOTION_MIN_WEIGHT))
        min_c = _parse_promotion_min_corroboration(os.environ.get(_ENV_PROMOTION_MIN_CORROBORATION))
        # I-deepfix-001 (drb_72) FIX-C: FAIL-LOUD topical-overlap threshold parse (LAW VI).
        min_t = _parse_promotion_min_topical_overlap(
            os.environ.get(_ENV_PROMOTION_MIN_TOPICAL_OVERLAP)
        )
        try:
            def _topical_demote(eid: str) -> bool:
                # FIX-C off-topic single-origin CITE gate: a corroborated-by-nobody, >=6-word,
                # <= min-overlap quote is routed to disclosed_only (KEPT, not dropped). FAIL-OPEN
                # on empty question / gate off / terse quote / any overlap above min / corroboration.
                return (
                    _promo_topical_gate
                    and bool(_promo_q_terms)
                    and best_quote_overlap.get(eid) is not None
                    and quote_words.get(eid, 0) >= _PROMOTION_TOPICAL_MIN_QUOTE_WORDS
                    and best_quote_overlap[eid] <= min_t
                    and max_origin.get(eid, 0) < min_c
                )

            def _promotion_eligible(eid: str) -> bool:
                if _topical_demote(eid):
                    return False                                  # FIX-C off-topic single-origin override
                w = best_cred_weight.get(eid)
                if w is None:
                    return True                                   # unknown weight => keep-neutral (promote)
                if w >= min_w:
                    return True                                   # WEIGHT leg
                if max_origin.get(eid, 0) >= min_c:
                    return True                                   # CONSOLIDATE leg (corroboration rescues)
                if is_journal.get(eid, False):
                    return True                                   # journal carve-out (over-demotion guard)
                return False

            _promoted = [e for e in ev_ids if _promotion_eligible(e)]
            disclosed_only = [
                {
                    "evidence_id": e,
                    "source_url": str(
                        (pool.get(e) or {}).get("source_url")
                        or (pool.get(e) or {}).get("url")
                        or ""
                    ),
                    "source_tier": best_tier.get(e, ""),
                    "credibility_weight": best_cred_weight.get(e),
                    "reason": (
                        "off_topic_single_origin" if _topical_demote(e)
                        else _DISCLOSED_ONLY_REASON
                    ),
                }
                for e in ev_ids
                if not _promotion_eligible(e)
            ]
            ev_ids = _promoted
            # I-deepfix-001 (drb_72) FIX-C: honest realized-effect [activation] marker — emitted once
            # per selection whenever the topical gate is enabled (demoted=0 is still a live marker).
            if _promo_topical_gate:
                logger.info(
                    "[activation] promotion_topical_gate: demoted=%d promoted=%d",
                    sum(1 for e in disclosed_only if e.get("reason") == "off_topic_single_origin"),
                    len(_promoted),
                )
        except Exception:  # noqa: BLE001 — fail-OPEN to promote-all = byte-identical legacy keep-all
            logger.warning(
                "[weighted_enrichment] M5 promotion-eligibility partition failed; FAIL-OPEN to "
                "promote-all (byte-identical legacy keep-all-and-cite). ev_ids left unchanged.",
                exc_info=True,
            )
            disclosed_only = []

    return UnboundSupportsSelection(
        ev_ids=ev_ids,
        reason=reason,
        baskets_seen=len(baskets),
        supports_members_seen=supports_members_seen,
        excluded_bound=excluded_bound,
        excluded_pool_absent=excluded_pool_absent,
        excluded_below_floor=below_floor_count,  # field name held stable; meaning = kept-below-floor
        offtopic_suppressed=tuple(offtopic_suppressed),  # I-deepfix-001 DEFER-1 (kept+disclosed)
        disclosed_only=tuple(disclosed_only),  # I-deepfix-001 M5 (routed-to-disclosed, never dropped)
    )


def select_unbound_supports_by_weight(
    *,
    evidence_pool: Any,
    credibility_analysis: Any,
    contract_plans: Any,
    research_question: str = "",
) -> list[str]:
    """Ordered evidence_ids of unbound, isolated-verified SUPPORTS basket members.

    Returns the FULL surviving list — NO cap, NO target, NO top-N, NO floor DROP. A member is
    included iff:
      * its own ``span_verdict == "SUPPORTS"`` (isolated per-member verification), AND
      * its ``evidence_id`` is NOT already bound to a contract section, AND
      * its ``evidence_id`` resolves in ``evidence_pool`` (so the section can cite a real span).

    I-arch-011 (B18) — WEIGHT, DON'T FILTER (§-1.3, the keystone): the relevance floor is now an
    ORDERING weight, NEVER an exclusion. Ordering is:
      1. at/above-floor (and missing-relevance) rows FIRST, below-floor rows LAST (a demotion, not a
         drop), THEN
      2. relevance-to-question DESC, THEN
      3. basket ``weight_mass`` (priority of consideration), THEN
      4. ``evidence_id`` (deterministic tiebreak).
    The pre-fix code RE-IMPOSED a hard ``selection_relevance < PG_RELEVANCE_FLOOR`` DROP here — the
    FILTER-AND-CAP anti-pattern the selector docstring (evidence_selector.py:1944-1953) forbids,
    which killed 729/746 unbound SUPPORTS so the enrichment appended NOTHING. That drop is REMOVED;
    a below-floor row is KEPT and sorted LAST, mirroring the retrieval pool's keep-all-down-weight
    (evidence_selector.py:2066-2070). A row with NO usable relevance score is keep-neutral (sentinel
    0.0, treated as NOT-below-floor) — pool membership already implies the retrieval floor passed.

    The floor + its fail-loud (0.0, 1.0] validation come from the SAME ``parse_relevance_floor`` the
    retrieval gate uses (no new constant). A garbage ``PG_RELEVANCE_FLOOR`` raises ``ValueError``.

    Faithfulness is UNCHANGED: every surfaced member is re-verified against its own span by the
    section's UNCHANGED ``strict_verify``; breadth comes from consolidating already-verifiable
    corroborators, never from relaxing a verify gate.

    ``credibility_analysis is None`` (master flag OFF or always-release degrade) => ``[]`` =>
    byte-identical legacy render. Thin wrapper over ``diagnose_unbound_supports_selection``; the call
    site uses the diagnostic form to log WHY an empty selection happened.
    """
    return diagnose_unbound_supports_selection(
        evidence_pool=evidence_pool,
        credibility_analysis=credibility_analysis,
        contract_plans=contract_plans,
        research_question=research_question,
    ).ev_ids


def build_weighted_enrichment_plan(ev_ids: Any, *, section_plan_cls: Any):
    """Build ONE legacy (field-agnostic) enrichment SectionPlan, or ``None`` when empty.

    ``None`` on empty ``ev_ids`` => caller appends nothing => byte-identical OFF/degrade path.
    """
    ev_ids = list(ev_ids or [])
    if not ev_ids:
        return None
    return section_plan_cls(
        title=_ENRICHMENT_TITLE,
        focus=_ENRICHMENT_FOCUS,
        ev_ids=ev_ids,
    )


# ─────────────────────────────────────────────────────────────────────────────
# I-deepfix-001 D4 (#1344) — FACET-CLUSTER THE WEIGHTED-ENRICHMENT BREADTH SURFACE.
#
# Gap: the "Corroborated Weighted Findings" section keeps ALL unbound-but-verified members (correct,
# §-1.3 keep-all) but lands them as ONE flat list of single-source one-liners — it reads as a link
# dump, not facet-organized coverage (DRB-II presentation + analysis; DR-original readability).
#
# Fix (PURE PLACEMENT — nothing dropped, faithfulness engine untouched): route each unbound member
# under the FACET/section its subject matches (reusing the report's own facet section TITLES), so it
# becomes part of that topical section. Members matching no facet stay in a residual "Additional
# corroborated findings" block (keep-all). This changes ONLY which section a member is composed under;
# every member still flows through the UNCHANGED strict_verify + section floor exactly as before.
#
# DEFAULT-OFF (LAW VI): ``enrichment_facet_route_enabled()`` False => the caller builds the single flat
# plan (byte-identical). No facet titles => also the single flat plan (no facets to route under).
_ENV_ENRICHMENT_FACET_ROUTE = "PG_ENRICHMENT_FACET_ROUTE"

# The residual bucket TITLE for members matching no facet (kept + surfaced, never dropped).
_ENRICHMENT_RESIDUAL_TITLE = "Additional Corroborated Findings"
# Prefix for a per-facet routed enrichment section title.
_ENRICHMENT_FACET_TITLE_PREFIX = "Corroborated Findings: "

# Minimal English stopword set for the facet content-word overlap. Small on purpose: a bigger list
# risks dropping a real topical token. Purely a MATCH heuristic — a miss routes a member to residual
# (kept), never drops it, so faithfulness is unaffected by the stoplist's exact contents.
_FACET_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "of", "in", "on", "for", "to", "with", "by", "at", "from",
    "as", "is", "are", "was", "were", "be", "been", "being", "this", "that", "these", "those",
    "it", "its", "their", "his", "her", "our", "your", "we", "they", "he", "she", "you", "i",
    "not", "no", "but", "if", "then", "than", "so", "such", "into", "over", "under", "about",
    "key", "findings", "analysis", "assessment", "overview", "summary", "evidence", "corroborated",
    "weighted", "additional", "section", "results", "study", "studies", "report",
})


def enrichment_facet_route_enabled() -> bool:
    """PG_ENRICHMENT_FACET_ROUTE gate (D4). DEFAULT-OFF => byte-identical single flat plan; an explicit
    1/true/on/yes turns the facet-clustered enrichment routing ON."""
    return os.environ.get(_ENV_ENRICHMENT_FACET_ROUTE, "0").strip().lower() in ("1", "true", "on", "yes")


def _facet_content_tokens(text: Any) -> set[str]:
    """Lower-cased content tokens of ``text`` (>=3 chars, not a stopword). Pure. Used to match a
    member's subject/quote text against a facet section title by token overlap."""
    out: set[str] = set()
    for tok in re.findall(r"[a-z0-9]+", str(text or "").lower()):
        if len(tok) >= 3 and tok not in _FACET_STOPWORDS:
            out.add(tok)
    return out


def route_enrichment_members_by_facet(
    ev_ids: Any,
    facet_titles: Any,
    *,
    text_of: Callable[[str], str],
    min_overlap: int = 1,
) -> "tuple[list[tuple[str, list[str]]], list[str]]":
    """Partition enrichment members into per-facet buckets by subject/topic overlap. PURE, keep-all.

    Each ev_id is routed under the FIRST facet whose title content-words overlap the member's text
    (``text_of(ev_id)`` — the member's subject / quote / title) by ``>= min_overlap`` tokens. A member
    matching NO facet lands in the residual list. Order-stable: facet buckets follow ``facet_titles``
    order; within a bucket, members follow ``ev_ids`` order; the residual follows ``ev_ids`` order.

    Returns ``(routed, residual)`` where ``routed`` is ``[(facet_title, [ev_id, ...]), ...]`` for the
    facets that received >=1 member (empty facets are omitted), and ``residual`` is the unmatched
    ev_ids. KEEP-ALL INVARIANT (asserted by the caller's test): the disjoint union of every routed
    bucket and the residual EQUALS the de-duplicated input ev_ids — no member is dropped, none appears
    twice. Nothing here touches the faithfulness engine; this is pure section placement."""
    ids: list[str] = []
    seen: set[str] = set()
    for e in (ev_ids or []):
        e = str(e or "")
        if e and e not in seen:
            seen.add(e)
            ids.append(e)
    titles = [str(t or "").strip() for t in (facet_titles or []) if str(t or "").strip()]
    if not ids or not titles:
        return ([], list(ids))
    title_tokens = [(t, _facet_content_tokens(t)) for t in titles]
    buckets: dict[str, list[str]] = {t: [] for t in titles}
    residual: list[str] = []
    for e in ids:
        member_tokens = _facet_content_tokens(text_of(e))
        placed = False
        if member_tokens:
            best_title = ""
            best_overlap = 0
            for (t, toks) in title_tokens:
                overlap = len(member_tokens & toks)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_title = t
            if best_overlap >= max(1, int(min_overlap)):
                buckets[best_title].append(e)
                placed = True
        if not placed:
            residual.append(e)
    routed = [(t, buckets[t]) for t in titles if buckets[t]]
    return (routed, residual)


def build_weighted_enrichment_plans_by_facet(
    ev_ids: Any,
    facet_titles: Any,
    *,
    section_plan_cls: Any,
    text_of: Callable[[str], str],
    min_overlap: int = 1,
) -> list:
    """Build the FACET-CLUSTERED enrichment SectionPlan LIST (D4), or ``[]`` when empty.

    Returns one SectionPlan per facet that received >=1 routed member (titled
    ``"Corroborated Findings: <facet>"``) IN ``facet_titles`` ORDER, followed by a single residual
    ``"Additional Corroborated Findings"`` plan for the members matching no facet. Every plan carries
    the SAME ``_ENRICHMENT_FOCUS`` so each still routes through the field-agnostic ``_run_section`` ->
    strict_verify path exactly as the flat plan did. KEEP-ALL: the concatenation of all returned plans'
    ``ev_ids`` equals the de-duplicated input (nothing dropped). ``[]`` on empty input => caller
    appends nothing => byte-identical to the OFF path. When NO member matches any facet, the sole
    returned plan is the residual, titled the SAME as the legacy flat section so a zero-facet corpus is
    presentation-identical to today."""
    routed, residual = route_enrichment_members_by_facet(
        ev_ids, facet_titles, text_of=text_of, min_overlap=min_overlap,
    )
    plans: list = []
    for (title, members) in routed:
        if not members:
            continue
        plans.append(section_plan_cls(
            title=f"{_ENRICHMENT_FACET_TITLE_PREFIX}{title}",
            focus=_ENRICHMENT_FOCUS,
            ev_ids=list(members),
        ))
    if residual:
        # When nothing routed to a facet, keep the legacy flat title so a zero-match corpus renders
        # identically to today's single "Corroborated Weighted Findings" section.
        residual_title = _ENRICHMENT_TITLE if not plans else _ENRICHMENT_RESIDUAL_TITLE
        plans.append(section_plan_cls(
            title=residual_title,
            focus=_ENRICHMENT_FOCUS,
            ev_ids=list(residual),
        ))
    return plans


# ---------------------------------------------------------------------------
# I-arch-008 (#1265) FIX K — DETERMINISTIC VERIFIED-SPAN RENDER for the
# enrichment section (the 590-in / 0-cited collapse).
#
# THE BUG (traced + behaviorally proven on the cQ75 corpus, state/iarch007_
# breadth_collapse_finding.md): the "Corroborated Weighted Findings" section
# selects ~590 unbound-but-span-verified SUPPORTS sources, then runs them
# through ``_run_section`` -> ``_call_section`` (the LLM), which GENERATES fresh
# prose. That prose then has to RE-EARN strict_verify/entailment from scratch and
# ~0 survives — so the breadth basket renders EMPTY ("no claim survived strict
# verification"). The sources were ALREADY isolated-span-verified (``span_verdict
# == SUPPORTS``); re-generating prose about them throws that verification away.
#
# THE FIX (faithfulness-NEUTRAL, no gate relaxation): when
# ``PG_BREADTH_ENRICHMENT_RENDER_VERIFIED_SPANS`` is ON, the enrichment section
# SKIPS the LLM and instead emits a DETERMINISTIC draft = each source's OWN
# verbatim sentence-units, each tagged with a legacy ``[ev_id]`` marker. That
# draft flows through the UNCHANGED ``_rewrite_draft_with_spans`` ->
# ``strict_verify`` path: the rewriter binds each unit to its best in-quote span
# via the SAME ``_find_best_span_for_sentence`` every section uses, and
# strict_verify validates each as that source's exact span-grounded words.
# Breadth EMERGES from how many survive the unchanged gate (measured ceiling on
# cQ75: 571 of 671 usable sources become citable, vs 7 today). NOTHING about the
# faithfulness engine moves — each rendered citation is literally the source's
# own quote against its own span.
#
# TWO build-correctness rules the behavioral harness surfaced
# (scripts/breadth_replay_harness.py — the §-1.4 acceptance gate):
#   1. PER-SENTENCE-UNIT tagging is MANDATORY. ``strict_verify`` re-splits the
#      draft into sentence units; a "whole quote + ONE trailing marker" tags only
#      the LAST unit, so every earlier unit drops with ``no_provenance_token``.
#      That naive draft verifies only 51 of 671 vs 571 for per-unit tagging — an
#      11x silent collapse (the same 590->0 symptom in microcosm). Each unit
#      therefore carries its OWN ``[ev_id]`` marker.
#   2. A JUNK SCREEN is REQUIRED. For a verbatim self-quote, strict_verify's
#      content-word/decimal checks are a tautology (idle) — they filter nothing —
#      so faithfulness rests on SPAN QUALITY. A fetch-shell / cookie-banner /
#      error-page span would otherwise self-quote straight through. We reuse the
#      SAME ``is_boilerplate_or_nonassertional`` allowlist screen strict_verify's
#      BUG-19 pregate uses, applied BOTH per source-quote and per unit, so K's
#      input hygiene is identical to the gate's.
#
# DEFAULT OFF (LAW VI) => ``render_verified_spans_enabled()`` False =>
# byte-identical legacy LLM render. ``is_enrichment_section`` matches ONLY this
# module's own ``_ENRICHMENT_TITLE`` section, so no other section is ever touched.

_ENV_RENDER_VERIFIED_SPANS = "PG_BREADTH_ENRICHMENT_RENDER_VERIFIED_SPANS"

# Per-SOURCE verbatim-unit budget (a verbosity bound + survival redundancy, NOT a
# breadth cap — the NUMBER OF SOURCES surfaced is uncapped; this only bounds how
# many of one source's own sentences are quoted, and offering a few raises the
# chance at least one clears entailment in enforce mode). Env-overridable (LAW
# VI); fail-loud on a non-int; floored at 1 so the flag can never silently zero
# the render.
_ENV_SPANS_PER_SOURCE = "PG_BREADTH_ENRICHMENT_SPANS_PER_SOURCE"
_DEFAULT_SPANS_PER_SOURCE = 3

# A sentence-unit must clear this length AND carry a real word to be a citable
# claim (drops bare fragments / lone numbers / headers). Allowlist-side only: the
# unchanged strict_verify gate still independently judges every surviving unit.
_MIN_UNIT_CHARS = 40

# I-beatboth-011 #4 (#1289) — RENDER-SAFETY char bound on a single emitted unit.
# A clean claim sentence is at most a few hundred chars; a unit longer than this is
# NOT a sentence — it is a fetch-shell / raw-extraction blob (the drb_72 defect was a
# ~75K-char raw academic-equation dump that carried a literal NUL byte and self-quoted
# straight into report.md, making it binary-corrupt). This is an allowlist-side
# RENDER bound on a single SURFACED unit, NOT a breadth cap (the number of SOURCES
# surfaced is uncapped) and NOT a faithfulness gate (strict_verify is untouched). A
# real long-but-legitimate quote is split into sentence units upstream by
# ``split_into_sentences``; a single unit exceeding this bound is structurally a blob,
# never a clinical sentence. Env-overridable (LAW VI); fail-loud on a non-int; floored
# at ``_MIN_UNIT_CHARS`` so the bound can never silently zero the render.
_ENV_MAX_UNIT_CHARS = "PG_BREADTH_ENRICHMENT_MAX_UNIT_CHARS"
_DEFAULT_MAX_UNIT_CHARS = 600

# C0 control bytes (and DEL) that MUST NEVER reach the rendered report — a literal NUL
# (\x00) at byte offset 220201 made drb_72 report.md binary-corrupt and unshowable.
# We strip every C0 control char EXCEPT \n and \t (which are legitimate whitespace in
# a multi-line quote). 0x7F (DEL) is included. This is byte-hygiene on the emitted
# render text, never a verdict and never a content drop.
_C0_CONTROL_KEEP = {"\n", "\t"}

# CAPTCHA / Cloudflare / security-interstitial stubs that fetch as a grammatical-looking
# SENTENCE (so ``is_boilerplate_or_nonassertional`` does NOT catch them) and would
# otherwise self-quote into the report. Allowlist input-hygiene, NEVER a verdict, NEVER a
# quality/length drop of real content.
#
# I-beatboth-011 #7 P1 (#1289): the bare trigger phrase "just a moment" is NOT enough to
# drop a member — real substantive prose can carry it ("Just a moment — the data show
# wages rose 5% in 2023"). Dropping such prose would violate §-1.3 keep-all. A drop now
# requires the trigger AND a STRONG WAF / security co-token (BYTE-IDENTICAL predicate
# shared with ``finding_dedup._is_captcha_stub`` so consolidation and render agree). The
# co-tokens are high-precision multi-word / branded anchors a real clinical sentence (any
# language) never contains.
_CAPTCHA_STUB_TRIGGER = "just a moment"
_WAF_CO_TOKENS = (
    "performing security verification",   # Cloudflare / generic WAF
    "checking your browser",              # Cloudflare "checking your browser before accessing"
    "cloudflare",                         # Cloudflare attribution / interstitial brand
    "ray id",                             # Cloudflare error footer "Ray ID: ..."
    "cf-ray",                             # Cloudflare response-header / footer token
    "enable javascript and cookies",      # Cloudflare retry prompt
    "ddos protection",                    # Cloudflare attribution stub
    "attention required",                 # Cloudflare 1020 / block interstitial title
    "verifying you are human",            # hCaptcha / Cloudflare Turnstile
    "needs to review the security of your connection",  # Cloudflare interstitial body
)

# Web-chrome / cookie-consent / nav markers that read as a grammatical SENTENCE.
# These slip past ``is_boilerplate_or_nonassertional`` + ``strip_web_boilerplate``
# (which catch error-pages + line-level chrome, not sentence-form consent text) —
# and on a verbatim self-quote strict_verify's content/decimal checks are IDLE, so
# without this screen a "Enable basic functions like page navigation." span would
# self-quote straight into a clinical report. Same allowlist-only, whole-unit
# input-hygiene pattern as the strict_verify BUG-19 pregate: multi-word, anchored
# to chrome-specific phrasing so a real clinical sentence (any language) is never
# touched, and NEVER a verdict — only what the breadth section actively SURFACES.
_WEB_CHROME_MARKERS = (
    "enable basic functions",
    "page navigation",
    "access to secure areas",
    "secure areas of the website",
    "website cannot function",
    "without these cookies",
    "accept all cookies",
    "cookie settings",
    "cookie policy",
    "privacy policy",
    "terms of service",
    "all rights reserved",
    "page not found",
    "404 error",
    "are you a robot",
    "enable javascript",
    "request access to",
    "sign in to continue",
    "subscribe to read",
    "log in to view",
    # I-beatboth-011 §3.4 idx68 (#1289): social-media / repository / masthead chrome that leaked into
    # cited spans in banked v3 (Scribd, Facebook, YouTube, journal masthead). HIGH-PRECISION multi-word
    # anchors ONLY (never bare "share"/"download"/"subscribers", which appear in real prose) — P1-4:
    # allowlist input-hygiene, NOT a length/quality drop of real content.
    "download free for 30 days",          # Scribd
    "report this document",               # Scribd
    "is this content inappropriate",      # Scribd
    "like comment share",                 # Facebook
    "subscribers subscribed",             # YouTube channel chrome
    "share save download",                # YouTube action bar
    "tap to unmute",                      # YouTube player chrome
    "skip navigation",                    # YouTube / generic nav
    "cite this paper as",                 # journal masthead citation widget
    # I-beatboth-011 b1 (#1289): publisher login-nav + image-URL masthead chrome that self-quoted into the
    # answer BODY/Key-Findings in banked v3 (drb_72 report.md carried the literal Wiley masthead+login-nav
    # run ".../logo-header-1690978619437.png) ## Change Password Old Password New Password Too Short.[13]").
    # HIGH-PRECISION multi-word anchors ONLY (never bare "password"/"image"/"logo"/"favicon", which appear
    # in real prose) — allowlist input-hygiene, NOT a length/quality drop of real content.
    "change password old password new password",  # Wiley/publisher login-nav run
    "/pb-assets/",                                 # publisher asset path segment (slash-anchored)
    "![image",                                     # markdown image leader "![Image N: ...]" (structure-anchored)
)

# Structure-anchored web-chrome asset URLs that a bare substring marker cannot express
# precisely — I-beatboth-011 b1 (#1289). Each REQUIRES a file extension / digit-stamp so a
# real-prose mention ("the favicon was redesigned", "a logo-header CSS class") is NEVER matched
# (the §-1.3 no-real-claim-dropped invariant). favicon coverage was missing entirely; logo-header
# was a bare substring (over-screen risk) — both are now extension/path-anchored here.
_WEB_CHROME_RE = re.compile(
    r"favicon[\w.\-]*\.(?:ico|png|svg|gif|jpe?g)\b"   # favicon.<ext> asset file
    r"|\blogo-header[-\w]*\.png\b",                   # masthead image URL logo-header-<stamp>.png
    re.IGNORECASE,
)

# Trailing sentence-terminal punctuation stripped before the ``[ev_id]`` marker is
# appended, so the marker sits INSIDE the sentence unit (``...trial [ev_id].``) and
# survives strict_verify's re-split. A marker appended AFTER the period
# (``...trial. [ev_id]``) is peeled onto its own fragment -> the content sentence
# goes tokenless -> dropped ``no_provenance_token`` (the silent-collapse the harness
# caught: it suppressed otherwise-citable sources).
_TERMINAL_PUNCT = ".!?"

# Legacy ``[ev_id]`` marker form — exactly what ``_call_section``'s LLM emits and
# what ``_rewrite_draft_with_spans`` (_EV_MARKER_RE) consumes. We emit this (not a
# pre-baked ``[#ev:id:s-e]`` token) so K's spans are computed by the SAME
# production span-finder as every other section — no parallel offset math.


def render_verified_spans_enabled() -> bool:
    """True iff the default-OFF verified-span render flag is explicitly enabled (LAW VI)."""
    return os.environ.get(_ENV_RENDER_VERIFIED_SPANS, "").strip().lower() in (
        "1", "true", "on", "yes", "enabled",
    )


def spans_per_source() -> int:
    """Per-source verbatim-unit budget from ``PG_BREADTH_ENRICHMENT_SPANS_PER_SOURCE``.

    Default ``_DEFAULT_SPANS_PER_SOURCE``. Fail-loud on a non-integer (LAW II — no
    silent fallback to a guessed value); floored at 1 so the render can never be
    silently zeroed by a ``0`` / negative value.
    """
    raw = os.environ.get(_ENV_SPANS_PER_SOURCE)
    if raw is None or not raw.strip():
        return _DEFAULT_SPANS_PER_SOURCE
    try:
        val = int(raw.strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{_ENV_SPANS_PER_SOURCE}={raw!r} is not an integer "
            f"(per-source verbatim-unit budget)"
        ) from exc
    return max(1, val)


def max_unit_chars() -> int:
    """Render-safety char bound on a single emitted unit (I-beatboth-011 #4).

    Default ``_DEFAULT_MAX_UNIT_CHARS``. Fail-loud on a non-integer (LAW II — no
    silent fallback to a guessed value); floored at ``_MIN_UNIT_CHARS`` so the bound
    can never silently zero the render. A unit longer than this is structurally a
    fetch-shell / raw-extraction blob, never a clinical sentence.
    """
    raw = os.environ.get(_ENV_MAX_UNIT_CHARS)
    if raw is None or not raw.strip():
        return _DEFAULT_MAX_UNIT_CHARS
    try:
        val = int(raw.strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{_ENV_MAX_UNIT_CHARS}={raw!r} is not an integer "
            f"(per-unit render char bound)"
        ) from exc
    return max(_MIN_UNIT_CHARS, val)


def _strip_control_bytes(text: str) -> str:
    """Strip C0 control bytes (and DEL 0x7F) EXCEPT \\n and \\t from render text.

    The drb_72 defect leaked a literal NUL byte (``\\x00``) into report.md, making it
    binary-corrupt and unshowable. This removes every ``ord(ch) < 32`` control char
    plus ``0x7F`` while KEEPING newline/tab (legitimate whitespace in a multi-line
    quote). Byte-hygiene on the emitted render text, never a verdict, never a content
    drop of a real claim — only non-printable control bytes are removed.
    """
    if not text:
        return text
    return "".join(
        ch
        for ch in text
        if ch in _C0_CONTROL_KEEP or (ord(ch) >= 32 and ord(ch) != 0x7F)
    )


def _is_captcha_stub(text: str) -> bool:
    """True iff ``text`` is a CAPTCHA / security-interstitial stub (allowlist-only).

    I-beatboth-011 #7 P1 (#1289): the bare trigger phrase ("just a moment") is NOT
    sufficient — a genuinely substantive sentence can contain it. A drop requires the
    trigger AND a strong WAF / security co-token (BYTE-IDENTICAL predicate shared with
    ``finding_dedup._is_captcha_stub``). §-1.3 keep-all: real prose carrying a bare
    "just a moment" with no security co-token is never dropped.
    """
    low = text.lower()
    return (_CAPTCHA_STUB_TRIGGER in low) and any(tok in low for tok in _WAF_CO_TOKENS)


def is_enrichment_section(section: Any) -> bool:
    """True iff ``section`` is one of THIS module's weighted-enrichment section plans.

    Scopes the FIX-K deterministic verified-span render to the sections this module builds — every
    contract / body section stays byte-identical.

    I-deepfix-001 D4 (#1344, Fable P1): when ``PG_ENRICHMENT_FACET_ROUTE`` is ON the enrichment payload
    is split into per-facet plans (title ``"Corroborated Findings: <facet>"``) plus a residual plan
    (``"Additional Corroborated Findings"``), NOT the single flat ``_ENRICHMENT_TITLE`` section. Every
    such plan carries the SAME ``_ENRICHMENT_FOCUS`` (``build_weighted_enrichment_plans_by_facet``), so
    matching on the shared ``focus`` recognizes flat, facet, AND residual plans — otherwise the paid
    Gate-B slate (which force-ONs BOTH facet-route and the verified-span render) would drop every
    facet-titled plan back to the distill+LLM 590-in/0-cited collapse path FIX-K exists to bypass. The
    title checks are kept as a defensive fallback for a plan built without the focus string.
    Robust to a duck-typed plan (missing attrs => False)."""
    focus = str(getattr(section, "focus", "") or "")
    if focus and focus == _ENRICHMENT_FOCUS:
        return True
    title = str(getattr(section, "title", "") or "")
    if title in (_ENRICHMENT_TITLE, _ENRICHMENT_RESIDUAL_TITLE):
        return True
    return bool(title.startswith(_ENRICHMENT_FACET_TITLE_PREFIX))


def _is_web_chrome(text: str) -> bool:
    """True iff ``text`` carries a sentence-form web-chrome / cookie-consent marker."""
    low = text.lower()
    if any(marker in low for marker in _WEB_CHROME_MARKERS):
        return True
    return bool(_WEB_CHROME_RE.search(text))


# ─────────────────────────────────────────────────────────────────────────────
# I-wire-012 (#1326) — THE ONE shared render-side chrome+truncation predicate.
#
# The render/compose surfaces (Corroborated Weighted Findings, the verified-compose
# section body, the per-claim corroboration header, Key-Findings / Abstract /
# Conclusion / depth) each grew their OWN parallel chrome screen
# (``_make_junk_screen`` here, ``verified_compose._compose_junk_screen``,
# ``run_honest_sweep_r3._span_is_render_chrome`` / ``_claim_header_is_unrenderable``,
# the ``key_findings`` filter). Parallel screens DRIFT — a chrome shape patched in
# one leaks through the others. This module is the chrome hub (verified_compose
# already delegates to ``_make_junk_screen``), so the ONE predicate lives here and
# every screen DELEGATES to it: no composer can emit an unscreened claim.
#
# FAITHFULNESS (FROZEN engine): this is render/compose INPUT hygiene only — it
# SUPPRESSES a page-furniture/truncated unit, it NEVER promotes one and NEVER
# touches a strict_verify / NLI / 4-role / span-grounding VERDICT. Page furniture is
# not a corroborating source, so suppressing it STRENGTHENS faithfulness (§-1.3).
#
# PRECISION OVER RECALL (the codebase law: "over-strip deletes a real finding, worse
# than a leak"). Every NEW category is high-precision allowlist/structure-anchored so
# a real clinical/economics/policy finding (any language) is never dropped; the
# canary below is the leak backstop. The "non-English-out-of-scope" category was
# DELIBERATELY NOT built: a language-only drop deletes real non-English sources (a
# §-1.3 multilingual-preservation regression), and any genuine non-English chrome
# already fires one of the structural categories below — so a separate language gate
# would only add over-strip risk for no recall.
_RENDER_CHROME_SCREEN_ENV = "PG_RENDER_CHROME_SCREEN"

# Page-furniture / masthead / journal / fetch-framing / nav SPANS that render as a
# grammatical-looking fragment (so the whole-line boilerplate screen misses them).
# Consolidated from run_honest_sweep_r3._RENDER_CHROME_SPAN_RE — the SINGLE source of
# truth now (the runner delegates to this predicate).
_SHARED_RENDER_CHROME_RE = re.compile(
    r"\bVolume\s+\d+\s*,?\s*(?:Number|No\.?|Issue)\s+\d+\b"
    r"|\bPages?\s+\d+\s*[-‐-―]\s*\d+\b"
    r"|\bCITATIONS\b\s+\d+\s+\bREADS\b\s+\d+"
    r"|\bMarkdown Content\s*:|\bURL Source\s*:|\bPublished Time\s*:"
    r"|\bNumber of Pages\s*:|\bCite this paper as\b"
    r"|#main-content|Twitter-intent|twitter\.com/intent"
    r"|same series\s*[-‐-―]\s*working paper"
    r"|\blisted\s+topics?\s+include\b",
    re.IGNORECASE,
)
# I-deepfix-001 (drb_72) FIX-A — ISSNe/ISSNp boundary + over-fire.
#
# The legacy bare rule ``\bISSN\b\s*:?\s*\d`` (a) MISSED "ISSNe"/"ISSNp" (the ``\b`` after the
# second N fails when a lowercase letter follows) AND (b) OVER-FIRED on a substantive finding that
# merely cites an ISSN in passing ("A 2021 study (ISSN 2049-3630) found 14% of jobs at risk." is a
# real finding, NEVER masthead chrome). §-1.3 precision-over-recall: a bare ISSN serial ALONE is
# NOT chrome — a masthead recital reciting a publication identity IS. So the token is now CO-SIGNAL
# gated: an ISSN/ISSNe/ISSNp serial that co-occurs (within a bounded window, order-independent) with
# a masthead recital word (publication / section / volume / issue / journal) is journal-masthead
# chrome; a bare ISSN mention inside substantive prose is left as a finding. Default-ON
# (``PG_CWF_ISSN_CHROME``); OFF restores the byte-identical legacy bare rule (``_LEGACY_BARE_ISSN_RE``)
# so a kill-switch run is unchanged. SUPPRESS-ONLY — never promotes a unit, never touches a
# faithfulness verdict.
_ENV_ISSN_CHROME = "PG_CWF_ISSN_CHROME"  # default ON
_LEGACY_BARE_ISSN_RE = re.compile(r"\bISSN\b\s*:?\s*\d", re.IGNORECASE)
_ISSN_MASTHEAD_COSIGNAL_RE = re.compile(
    r"\bISSN[a-z]?\b\s*:?\s*\d[\d-]*.{0,80}?\b(?:publication|section|volume|issue|journal)\b"
    r"|\b(?:publication|section|volume|issue|journal)\b.{0,80}?\bISSN[a-z]?\b\s*:?\s*\d",
    re.IGNORECASE,
)
_ISSN_CHROME_ACTIVATION_LOGGED = False  # emit the [activation] marker once per process on first fire


def issn_chrome_gate_enabled() -> bool:
    """Kill-switch ``PG_CWF_ISSN_CHROME`` (default ON). ON => the ISSNe/ISSNp-aware CO-SIGNAL rule
    (masthead recital only); OFF => the byte-identical legacy bare ``\\bISSN\\b\\s*:?\\s*\\d`` rule."""
    # I-deepfix-001 (#1369) FIX 4 — default-ON semantics: UNSET and EMPTY-STRING
    # are both ON; disabled ONLY by an explicit OFF token. The prior truthy-only
    # membership test made an empty-string env value DISABLE the gate (the
    # opposite of the intended default-ON), matching the other fix-6 gates now.
    return os.environ.get(_ENV_ISSN_CHROME, "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


def _is_issn_masthead_chrome(text: str) -> bool:
    """FIX-A: ISSN masthead-recital chrome. Default-ON co-signal rule (ISSNe/ISSNp-aware, over-fire
    safe); OFF => legacy bare ISSN. Emits the ``[activation]`` marker once per process on first fire."""
    global _ISSN_CHROME_ACTIVATION_LOGGED
    if issn_chrome_gate_enabled():
        if _ISSN_MASTHEAD_COSIGNAL_RE.search(text):
            if not _ISSN_CHROME_ACTIVATION_LOGGED:
                _ISSN_CHROME_ACTIVATION_LOGGED = True
                logger.info("[activation] issn_masthead_chrome: fired=1 (co-signal gate ON)")
            return True
        return False
    return bool(_LEGACY_BARE_ISSN_RE.search(text))


# I-deepfix-001 (drb_72) FIX-B — chart alt-text enumeration ("The chart has 1 X axis … 1 Y axis …").
# A screen-reader alt-text describing a figure's axes rendered as a standalone finding. Requires the
# "the chart has" + "x axis" + "y axis" CO-OCCURRENCE (bounded window) so a real finding that merely
# names an axis ("Employment on the y-axis rose as automation on the x-axis increased.") never matches.
# Default-ON (``PG_CWF_CHART_ALT_CHROME``); OFF => the rule is skipped (byte-identical). SUPPRESS-ONLY.
_ENV_CHART_ALT_CHROME = "PG_CWF_CHART_ALT_CHROME"  # default ON
_CHART_ALT_TEXT_RE = re.compile(
    r"\bthe chart has\b.{0,80}?\bx[\s-]?axis\b.{0,120}?\by[\s-]?axis\b",
    re.IGNORECASE,
)
_CHART_ALT_ACTIVATION_LOGGED = False  # emit the [activation] marker once per process on first fire


def chart_alt_chrome_gate_enabled() -> bool:
    """Kill-switch ``PG_CWF_CHART_ALT_CHROME`` (default ON). OFF => the chart-alt-text rule is
    skipped => the predicate is byte-identical to pre-FIX-B."""
    # I-deepfix-001 (#1369) FIX 4 — default-ON semantics: UNSET and EMPTY-STRING
    # are both ON; disabled ONLY by an explicit OFF token (see issn_chrome_gate).
    return os.environ.get(_ENV_CHART_ALT_CHROME, "1").strip().lower() not in (
        "0", "false", "no", "off",
    )
# Claim-header chrome: CC-license / keywords-list / login-wall / share-button furniture
# (consolidated from run_honest_sweep_r3._CLAIM_HEADER_CHROME_RE). "Close-Share" and CC-license
# are explicitly in the I-wire-012 category list. PRECISION: this predicate can DROP composer text,
# so the bare ``\bkeywords\b`` of the header-only version is TIGHTENED to the ``Keywords:`` list
# LABEL — a real sentence ("the keywords were extracted from ...") is never matched.
_SHARED_CLAIM_HEADER_CHROME_RE = re.compile(
    r"creative commons|licensed under a |\bkeywords\s*:|premium access|must have premium|"
    r"share icon|close\s*-\s*share|all rights reserved",
    re.IGNORECASE,
)
# Numbered table-of-contents entry, SECTION-NAME-anchored only ("1 Introduction", "3 Methods").
# PRECISION: the loose decimal "N.N Capitalized" form (kept header-only in run_honest_sweep, where
# an over-match merely swaps to subject+predicate) is DELIBERATELY EXCLUDED here — it would drop a
# real magnitude claim ("$3.2 Billion") from a composer. Only the unambiguous section-name ToC shape
# (which a real finding sentence never IS) screens droppable text.
_SHARED_TOC_RE = re.compile(
    r"^\s*\d+\s+(?:Introduction|Background|Materials?|Methods?|Results?|Discussion|"
    r"References|Conclusion|Abstract)\s*$",
    re.IGNORECASE,
)
# A WHOLE-UNIT scraped document label standing alone as a "claim" ("Abstract",
# "AI Summary", "Author summary", "Graphical abstract"). Whole-unit anchored
# (``fullmatch``-style ``^...$``) so it NEVER catches POLARIS's own ``## Abstract``
# section header (that carries the ``## `` prefix + body) or a real sentence that
# merely contains the word "abstract".
_DOC_LABEL_RE = re.compile(
    r"^(?:abstract|ai\s+summary|ai\s+overview|graphical\s+abstract|author\s+summary|"
    r"plain\s+language\s+summary|highlights|table\s+of\s+contents)\s*[:.]?\s*$",
    re.IGNORECASE,
)
# An ORCID identifier in a "claim" => an author/affiliation masthead list, never a
# finding (a real clinical/economics sentence never carries a 0000-0000-0000-0000
# ORCID id). High precision by construction.
_ORCID_RE = re.compile(r"\b\d{4}-\d{4}-\d{4}-\d{3}[\dxX]\b")
# A bare DOI / identifier row standing alone as a "claim" (no assertional prose).
_DOI_ONLY_RE = re.compile(
    r"^\s*(?:doi\s*:?\s*|https?://(?:dx\.)?doi\.org/)?10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\s*$",
    re.IGNORECASE,
)
# Trailing ``[N]`` / ``[#ev:...]`` citation markers (stripped before the sentence-form
# completeness test so "…claim.[12]" is judged on the "." not the marker).
_SHARED_TRAILING_CITE_RE = re.compile(r"(?:\s*\[(?:\d+|#ev:[^\]]*)\])+\s*$")

# ─────────────────────────────────────────────────────────────────────────────
# I-wire-013 (#1327) iter-3a — CONTAINMENT forensic chrome rules (the UNBLINDING).
#
# The legacy chrome categories above are WHOLE-UNIT junk classifiers (anchored ^…$ / standalone-
# label / bare-DOI shapes): they return False the moment a unit ALSO carries real prose, so glued
# page-furniture survived ("…over the recent past.[1] 1 Introduction 1.1 Research background 1.2
# Resea.[14]", a masthead glued mid-Abstract, a "## Dennis Zami …" author header glued onto a
# section title). These rules — ported from the independent detector
# scripts/iwire013_sec11_forensic_audit.py (which catches 55 chrome / 20 truncation on the banked
# render where the production predicate reported ~0) — flag a unit that CONTAINS chrome, not only a
# unit that IS chrome.
#
# PRECISION OVER RECALL (drop-path law — "over-strip deletes a real finding, worse than a leak"):
# the detector's loose bare ``\d+ TitleCase`` ToC token and any-run non-Latin rule were tightened
# for this DROP path (they over-flagged real economics prose with year/figure number pairs and an
# English finding quoting a short CJK term). The kept rules are structure-anchored and validated to
# flag ZERO of a clean-finding probe set while catching the real glued chrome (≈47/55 of the banked
# render; the residual are detector false-positives we deliberately KEEP, or niche chrome the canary
# backstops). Every numeric threshold is a named constant (LAW VI / §9.4).

# A glued/inline markdown header INSIDE a unit body (a SECOND "## …" header welded onto the title /
# into prose) — NOT a clean leading header (the caller passes a header's TITLE, post-``#`` strip).
_INLINE_HEADER_RE = re.compile(r"(?:^|[^\n#])#{1,6}\s+[A-Za-z]")
# Author-with-superscript-affiliation list: "Kanbach1,2 · Louisa Heiduk1 · …" (middot separators).
_AFFIL_MIDDOT_RE = re.compile(r"[A-Za-z]{2,}\d{1,2}(?:,\d)?\s*[·•]")
# A run of non-Latin script (Arabic / CJK) — the report is English-only, so a PREDOMINANTLY
# non-Latin unit is a foreign-page scrape. A SHORT inline foreign term inside English prose is NOT
# flagged (§-1.3 multilingual preservation): the run must be long AND outweigh the Latin letters.
_NONLATIN_CHAR_RE = re.compile(r"[؀-ۿݐ-ݿ一-鿿぀-ヿ가-힯]")
_NONLATIN_RUN_RE = re.compile(r"[؀-ۿݐ-ݿ一-鿿぀-ヿ가-힯]{4,}")
_MIN_NONLATIN_RUN_CHARS = 4  # a shorter run is an inline foreign term, kept
# A DOTTED section-number token glued into a unit ("1.1 Research", "5.2 AI"); the TitleCase word is
# excluded when it is a magnitude/measure unit so a real "3.2 Million / 4.5 Billion" pair never
# reads as a two-token ToC. A unit needs ``_MIN_DOTTED_TOC_HITS`` dotted tokens to flag as glued ToC.
_DOTTED_SECTION_TOKEN_RE = re.compile(r"(?:^|\s)\d+\.\d+(?:\.\d+){0,2}\s+([A-Z][a-z]+)")
_MIN_DOTTED_TOC_HITS = 2
_MAGNITUDE_UNIT_WORDS = frozenset({
    "million", "billion", "trillion", "thousand", "hundred", "percent", "percentage",
    "times", "average", "points", "point",
})
# A STANDALONE numbered-heading LINE/unit: a unit that OPENS with a dotted section number + a
# TitleCase word ("3.3 Recommender Systems", "1.1 Research background to the study"). Anchored at the
# unit start so a mid-sentence "see section 3.3 for details" never matches; the opener word is
# magnitude-excluded so "3.2 Billion outcomes …" never matches.
_STANDALONE_DOTTED_HEADING_RE = re.compile(r"^\s*\d+\.\d+(?:\.\d+){0,2}\s+([A-Z][a-z][\w]*)")
# A STANDALONE numbered SECTION-NAME heading ("1 Introduction", "3 Methods") — anchored at the unit
# start with a closed section-name vocabulary so a prose "Figure 1 Results" / "Table 2 Methods"
# (which does NOT open with a bare number) is never matched.
_STANDALONE_SECTION_NAME_RE = re.compile(
    r"^\s*\d+(?:\.\d+){0,3}\s+(?:Introduction|Background|Materials?|Methods?|Methodology|"
    r"Results?|Discussion|References?|Conclusion|Abstract|Literature|Overview)\b",
    re.IGNORECASE,
)
# Journal / submission MASTHEAD furniture welded into a unit ("44 Pages Posted: 9 Jan 2018",
# "Vol: 30 Issue: 1", "Date Issued April 2020", "Policy Research Working Paper 11057").
_MASTHEAD_CHROME_RE = re.compile(
    r"\bpages?\s+posted\s*:|\bposted\s*:\s*\d|\blast revised\s*:|\bdate issued\b|"
    r"\bworking paper\s+\d{2,}|\bvol\.?\s*:?\s*\d+\s*(?:,|issue|no\.?)|"
    r"there are \d+ versions of this paper|\bpolicy research working paper\b|"
    r"cite this paper as|number of pages",
    re.IGNORECASE,
)
# Author / submission-metadata block ("Received: 31 May 2023 / Accepted: …", "Published online").
_SUBMISSION_META_RE = re.compile(
    r"received:\s*\d|accepted:\s*\d|published online|\brevised:\s*\d", re.IGNORECASE,
)
# Browser / UI / nav / social-share junk welded into a unit.
_NAV_CHROME_RE = re.compile(
    r"share\s+facebook|facebook\s+twitter|twitter\s+linkedin|download associated records|"
    r"clear your browser cache|refresh the page or clear|accessing this content requir|"
    r"this content is only available as a pdf|i need some assistance|most recent answer|"
    r"requires a membership|please log into",
    re.IGNORECASE,
)
# Open-access / license / copyright furniture.
_LICENSE_CHROME_RE = re.compile(
    r"creative commons|creativecommons\.org/licenses|open access article distributed under|"
    r"this is an open access article|©\s*\d{4}\s+the\b|©\s*the author|copyright\s+©",
    re.IGNORECASE,
)
# HARD bibliographic / portal markers (a LONE URL is NOT chrome; these are unambiguous).
_BIBLIO_CHROME_RE = re.compile(
    r"\bdoi:\s*10\.\d|crossref reports the following articles citing|"
    r"volume title publisher|name:\s*\S+\.txt\b|file type:\s*text/",
    re.IGNORECASE,
)  # I-deepfix-001 (drb_72) FIX-A: the bare ISSN alternative moved to the gated ``_is_issn_masthead_chrome``
#    (ISSNe/ISSNp-aware + over-fire-safe); it is invoked in ``_contains_forensic_chrome`` below.
_URL_RE = re.compile(r"https?://", re.IGNORECASE)
_DOI_URL_RE = re.compile(r"https?://(?:dx\.)?doi\.org/", re.IGNORECASE)
_MIN_URLS_FOR_CHROME = 3       # >=3 bare URLs in one unit => a link list / portal blob
_MIN_DOI_URLS_FOR_CHROME = 2   # >=2 doi.org URLs => a reference blob
# A statistics / regression TABLE welded into a unit: a dense run of parenthesised std-errors
# "(0.018) (0.016) (0.011)" or starred coefficients "0.034* 0.030* 0.027**". A real finding cites
# one coefficient, never a 3+/2+ run.
_STATS_TABLE_RE = re.compile(
    r"(?:\(\s*[-−]?\d+\.\d+\s*\)\s*){3,}|(?:\d+\.\d+\s*\*{1,3}\s*){3,}"
)

# I-deepfix-002 (#1363) FIX-1 — cookie/consent banner, DOI-registry error page, mixed-script
# masthead. drb_72 smoke leaked these into cited claims (cookie-wall [10][23][24], DOI-Not-Found
# error page [25], Russian journal masthead [5][11]); they self-entail strict_verify (text == its
# own span) so the faithfulness engine cannot catch them — they are page furniture / dead-fetch
# shells, never a corroborating source. SUPPRESS-only (FLAG-not-drop); engine UNCHANGED.
_COOKIE_CONSENT_RE = re.compile(
    r"utiliz\w*\s+technologies\s+such\s+as\s+cookies"
    r"|we\s+use\s+cookies\s+to\s+enhance\s+your\s+browsing"
    r"|we\s+value\s+your\s+privacy"
    r"|analytics,?\s+personali[sz]ation,?\s+and\s+targeted\s+advertising"
    r"|necessary\s+cookies\s+are\s+required"
    r"|the\s+technical\s+storage\s+or\s+access\s+(?:is|that\s+is)\s+(?:strictly\s+necessary|used\s+exclusively)"
    r"|opens\s+(?:in\s+a\s+new\s+window|an\s+external\s+website)"
    r"|store\s+and/or\s+access\s+information\s+on\s+your\s+device"
    r"|error\s*[-–—]\s*cookies\s+turned\s+off"
    r"|cookieabsent"
    r"|press\s+alt\+1\s+for\s+screen-reader\s+mode"
    r"|strictly\s+necessary\s+for\s+the\s+legitimate\s+purpose"
    r"|accept\s+all\s+cookies", re.IGNORECASE)
_DOI_ERROR_RE = re.compile(
    r"DOI\s+Not\s+Found"
    r"|this\s+DOI\s+cannot\s+be\s+found\s+in\s+the\s+DOI\s+System"
    r"|report\s+this\s+error\s+to\s+the\s+responsible\s+DOI\s+Registration\s+Agency"
    r"|the\s+DOI\s+has\s+not\s+been\s+activated\s+yet"
    r"|search\s+again\s+from\s+DOI\.ORG", re.IGNORECASE)
# A 4+ char non-Latin run (Cyrillic U+0400–052F added — the legacy _NONLATIN_CHAR_RE omitted it)
# AND a Vol/Issue/№/Том token = a foreign-language journal masthead, not English prose quoting a
# short foreign term.
_NONLATIN_MASTHEAD_RUN_RE = re.compile(r"[Ѐ-ԯ؀-ۿ一-鿿぀-ヿ가-힣]{4,}")
_MASTHEAD_VOL_TOKEN_RE = re.compile(r"\b(?:Vol\.?|Volume|Issue|No\.)\b|№|Том\b", re.IGNORECASE)


def _is_foreign_journal_masthead(text: str) -> bool:
    return bool(_NONLATIN_MASTHEAD_RUN_RE.search(text) and _MASTHEAD_VOL_TOKEN_RE.search(text))


# ─────────────────────────────────────────────────────────────────────────────
# I-deepfix-001 (#1344) DEFER-4 — residual WHOLE-UNIT page-furniture the FIX-1 (cookie/DOI/foreign-
# masthead/byline) and legacy categories miss. drb_72 smoke leaked these as cited claims:
#   A14 publisher PAYWALL call-to-action ("Get full access to this article / View all access and
#       purchase options for this article." [20]) — the legacy chrome_furniture_screen._PAYWALL_RE
#       covers Member-only/Feature-Story but not this Sage/Atypon access-wall string.
#   A15 working-paper COVER masthead + author-opinion DISCLAIMER ("DISCUSSION PAPER SERIES IZA DP
#       No. 14409 ... Any opinions expressed in this paper are those of the author(s) ..." [19]).
#   A16 PDF FOOTNOTE / citation-apparatus run ("See OECD (2020), Table 3.3. 14Tate and Yang (2016)
#       analyze ... 7 Post-merger restructuring." [19]).
#
# PRECISION + OVER-STRIP SAFETY (operator-locked drop-path law "over-strip deletes a real finding,
# worse than a leak"): each rule fires ONLY on a unit that is DOMINANTLY page furniture — a paywall
# CTA, a series-cover masthead, a footnote/reference run with NO finding clause. A real economics /
# labor finding never carries these anchors. Units that are a REAL finding welded to a SMALL artifact
# (A17 "…eliminated.1 1 This number assumes…", A18 "Box 3.1 … In collaboration with Indeed …",
# A19 "(See Exhibit 1.)", E1 truncated "…not only access to.") are DELIBERATELY NOT matched here —
# dropping their whole unit would delete the real finding inside, so they are left to the render-seam
# REPAIR / truncation legs. A20 ("eloundou_gpts_are_gpts") is a SUPPORT sub-bullet source-locator
# (keep-only surface), not a claim unit, so it is out of this predicate's lane too. FLAG-not-drop:
# the source row stays in evidence_pool + the credibility disclosure; the faithfulness engine
# (strict_verify / NLI / 4-role / span-grounding) is UNCHANGED.

# A14 — publisher paywall / "get full access" CTA furniture. Multi-word, access-wall-specific.
_PAYWALL_ACCESS_RE = re.compile(
    r"\bget\s+full\s+access\s+to\s+this\s+article\b"
    r"|\bview\s+all\s+access\s+and\s+purchase\s+options\b"
    r"|\bpurchase\s+options\s+for\s+this\s+article\b",
    re.IGNORECASE,
)
# A15 — working-paper / discussion-paper COVER masthead + author-opinion DISCLAIMER. Both phrases are
# series-cover boilerplate a real finding never contains (the working-paper-NUMBER masthead form
# "Policy Research Working Paper 11057" is already covered by _MASTHEAD_CHROME_RE; this adds the
# "DISCUSSION PAPER SERIES" series header and the "Any opinions expressed in this paper are those of
# the author(s)" disclaimer that the IZA cover carries).
_WORKING_PAPER_COVER_RE = re.compile(
    r"\bdiscussion\s+paper\s+series\b"
    r"|\bany\s+opinions?\s+expressed\s+in\s+this\s+paper\s+are\s+those\s+of\s+the\b",
    re.IGNORECASE,
)
# A16 — PDF footnote / citation-apparatus run: a 1-2 digit footnote number GLUED directly to a
# Capitalized surname ("14Tate and Yang (2016)") or a "See <REF> (year), Table N" cross-reference
# opener. A real sentence writes "Tate and Yang (2016)" (space, no glue) and never opens "See OECD
# (2020), Table 3.3.". The glue rule's ``[A-Z][a-z]{2,}`` excludes all-caps tokens (so "4IR", "23
# OECD") and lowercase (so "165million") — only a footnote-digit welded to a Mixed-case surname.
_FOOTNOTE_GLUE_RE = re.compile(
    r"\b\d{1,2}[A-Z][a-z]{2,}\s+(?:and|et\s+al\.?|\(\d{4}\))"
    r"|\bSee\s+[A-Z][A-Za-z]+(?:\s+(?:and|&)\s+[A-Z][A-Za-z]+)?\s*\(\d{4}\)\s*,?\s+Table\s+\d",
)


def _is_residual_chrome_furniture(text: str) -> bool:
    """I-deepfix-001 (#1344) DEFER-4: True iff ``text`` is a residual furniture-DOMINATED unit
    (publisher paywall CTA, working-paper cover masthead/disclaimer, PDF footnote/citation run).
    High-precision whole-unit screen; a real finding welded to a small artifact is NOT matched."""
    return bool(
        _PAYWALL_ACCESS_RE.search(text)
        or _WORKING_PAPER_COVER_RE.search(text)
        or _FOOTNOTE_GLUE_RE.search(text)
    )


# ─────────────────────────────────────────────────────────────────────────────
# I-deepfix-001 (#1344) chrome_canary_unblind — three chrome CLASSES the containment predicate was
# BLIND to (the canary passed 0/226 while the report was saturated with chrome). Each rule is a
# high-precision CONTAINMENT signal (fires even when the class is welded INTO otherwise-real prose),
# structure/dual-signal-anchored so it can NEVER flag clean clinical prose:
#   (a) AUTHOR-AFFILIATION / EMAIL block — an email address CO-OCCURRING with an institution keyword
#       (a corresponding-author byline: "…, Department of Cardiology, Harvard University. Email:
#       jsmith@harvard.edu"). A real clinical/research finding never carries a raw email address, and
#       the email+institution DUAL signal never co-occurs in substantive prose (precision-first per
#       §-1.3: recall is secondary, over-strip is worse). The email alone is NOT enough (a finding
#       could conceivably quote one); both signals are required.
#   (b) TABLE-OF-CONTENTS DOT-LEADERS — a run of 4+ leader dots (a normal ellipsis is exactly 3)
#       followed by a page number ("Introduction ......... 12"). Consecutive-dot runs with a trailing
#       page number are ToC furniture; a decimal table ("0.034 0.030") has digits BETWEEN the dots so
#       it never matches.
#   (c) COOKIE / CONSENT banner — the "By clicking/continuing … you accept/agree/consent" consent-CTA
#       phrasing the legacy ``_COOKIE_CONSENT_RE`` alternation missed. Bounded gap (no ``.``/newline)
#       between the two anchors keeps it from spanning unrelated sentences.
# FLAG-not-drop / detector-only: a flagged unit is withheld from the rendered rollup and KEPT in
# evidence; the faithfulness engine (strict_verify / NLI / 4-role / provenance / span-grounding) is
# UNCHANGED. Gated by the caller under ``render_chrome_screen_enabled()`` (default ON).
_AFFIL_EMAIL_ADDRESS_RE = re.compile(
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"
)
_AFFIL_INSTITUTION_KEYWORD_RE = re.compile(
    r"\b(?:Universit(?:y|ies|[àáäé]|e)|Universidad|Universit[àé]|Department|Departamento|"
    r"Institut(?:e|o|ion)?|College|Hospital|Clinic|Laborator(?:y|ies)|Faculty|Facultad|"
    r"Escuela|Polytechnic|Academy|Ministry)\b",
    re.IGNORECASE,
)
_TOC_DOTLEADER_RE = re.compile(r"(?:\.[ \t]*){4,}\d{1,4}\b")
_COOKIE_BY_CLICKING_RE = re.compile(
    r"\bby\s+(?:clicking|continuing|using|browsing)\b[^.\n]{0,80}?"
    r"\byou\s+(?:accept|agree|consent)\b",
    re.IGNORECASE,
)


def _contains_missed_chrome_class(text: str) -> bool:
    """I-deepfix-001 (#1344) chrome_canary_unblind: True iff ``text`` CONTAINS one of the three
    high-precision chrome classes the legacy containment predicate was blind to — an author-
    affiliation/email byline, a ToC dot-leader run, or a "By clicking … you accept" consent banner.
    Detector-only (FLAG-not-drop); the faithfulness engine is UNCHANGED."""
    if _AFFIL_EMAIL_ADDRESS_RE.search(text) and _AFFIL_INSTITUTION_KEYWORD_RE.search(text):
        return True
    if _TOC_DOTLEADER_RE.search(text):
        return True
    return bool(_COOKIE_BY_CLICKING_RE.search(text))


# ─────────────────────────────────────────────────────────────────────────────
# I-wire-016 (#1338) gap-fill — precision-safe furniture rules the legacy categories miss (the OSS
# survey confirmed no fetch-time HTML extractor fits the render seam; extend the deterministic
# predicate). Codex iter-1/2/3 removed every rule whose surface form overlaps a real finding (biblio
# date+page, bibliometric stats, "Name<digit>, <digit>" superscript), leaving the unambiguous
# affiliation-glued / title+affiliation / author-attribution-phrase rules. VALIDATED precision-first:
# ZERO of the 398 curated-clean real-content units are flagged; every Codex adversarial real-finding
# case is KEPT. Under-removal is the safe direction (recall secondary per §-1.3); the chrome-as-claim
# canary backstops the rarer residual classes. FLAG-not-drop: a flagged unit is withheld from the
# rendered rollup, KEPT in evidence; the faithfulness engine (strict_verify / NLI / 4-role / span) is UNCHANGED.
#
# gap 1 — a digit GLUED to an institution keyword ANCHORED to its affiliation preposition (Department
# OF, Laboratory OF/FOR/AT, Institute OF/FOR, …) so an adjective ("2Laboratory-confirmed cases",
# "1Institutional review boards") never matches (Codex iter-1 P1). Real prose spells "a/one/the department";
# only an author-block superscript glues a digit directly to "Department of"/"Institute of"/etc.
_AFFIL_GLUED_RE = re.compile(
    r"\b\d{1,2}(?:Department\s+(?:of|for)\b|Departamento\s+de\b|Faculty\s+of\b|School\s+of\b|"
    r"Institute\s+(?:of|for)\b|University\s+of\b|Universidad\s+de\b|Facultad\s+de\b|Escuela\s+de\b|"
    r"Laborator(?:y|ies)\s+(?:of|for|at)\b|Centre\s+for\b|Center\s+for\b)",
)
# gap 4 — title+affiliation composite: a dash + digit + institution ("A Survey of … - 1 Department of …").
_TITLE_AFFIL_RE = re.compile(
    r"[-–—]\s*\d{1,2}\s+(?:Department\s+of|Institute\s+(?:of|for)|Faculty\s+of|School\s+of|"
    r"University\s+of|Laborator(?:y|ies)\s+(?:of|for|at)|Centre\s+for|Center\s+for)\b",
)
# gap 1 — author-attribution MASTHEAD block: the authorship phrase ("X is listed as an author",
# "… are among the listed authors") AND a co-occurring article-portal MASTHEAD signal (the
# "article has received N accesses/citations/altmetric" engagement-stats furniture). Codex iter-4 P1:
# the phrase ALONE flags a real research-integrity finding ("X is listed as an author on the retracted
# paper"); requiring BOTH the phrase AND the portal-stats co-signal anchors it to the masthead block
# ("Gazdag is listed as an author. The article has received 3258 accesses, 16 citations…") — a real
# integrity/COI finding never co-reports portal engagement stats. Both signals required (precision-first).
_AUTHOR_ATTRIB_PHRASE_RE = re.compile(
    r"\bis listed as an?\s+(?:author|co-author)\b|\bare among the listed authors\b|"
    r"\blisted as (?:the\s+)?(?:author|co-author)s?\b",
    re.IGNORECASE,
)
_MASTHEAD_PORTAL_STATS_RE = re.compile(
    # Codex iter-5 P1: the co-signal must be a TRUE portal-only metric (a number directly followed by
    # "accesses" or "altmetric") — masthead engagement counts a research finding never reports. Bare
    # "N citations" and unconstrained "article has received" are REMOVED: a real integrity/bibliometrics
    # finding legitimately says "received 18 citations before correction", so they are not portal-unique.
    r"\b\d[\d,]*\s+(?:accesses|altmetric)\b",
    re.IGNORECASE,
)
# DROPPED (Codex iter-1/2/3, not precision-safe — surface form overlaps real findings):
#  - gap 2 biblio date+page ("…, July 12, p. 36" vs "The July 12, p. 36 article reported…").
#  - gap 3 bibliometric stats ("3,258 accesses, 16 citations, 7 altmetric" vs real bibliometrics findings;
#    "vascular accesses"). The author-attribution phrase above catches the masthead blocks these appeared in.
#  - gap 1 "Name<digit>, <digit>" author-superscript (titlecase mouse-gene notation "Smad1, 5 and Smad2, 3").
# These rare residual classes are left to the chrome-as-claim canary (enforce, floor 0.05) per §-1.3
# (precision over recall — never risk dropping a real finding).


def _contains_iwire016_gap_furniture(s: str) -> bool:
    """I-wire-016 #1338: precision-safe gap-class furniture rules (validated 0 content false-positives;
    Codex iter-1/2/3 removed every rule whose surface form overlaps a real finding). Catches the
    affiliation/author-attribution masthead blocks; rarer stats/biblio/superscript classes are left to
    the chrome-as-claim canary. FLAG-not-drop: withheld from rollup, kept in evidence; faithfulness UNCHANGED."""
    if _AFFIL_GLUED_RE.search(s) or _TITLE_AFFIL_RE.search(s):
        return True
    # author-attribution masthead: the authorship phrase AND a portal-stats co-signal (both required —
    # Codex iter-4 P1: the phrase alone flags a real integrity/COI finding).
    return bool(_AUTHOR_ATTRIB_PHRASE_RE.search(s) and _MASTHEAD_PORTAL_STATS_RE.search(s))


# ─────────────────────────────────────────────────────────────────────────────
# I-deepfix-001 (#1344) drb72_apparatus_unblind — three chrome CLASSES that leaked into cited
# CLAIMS (and into the Abstract + Conclusion sandwich) of the drb_72 report because no enumerated
# rule covered them and chrome self-entails strict_verify (text == its own span) so the faithfulness
# engine is structurally blind to furniture. All are high-precision CONTAINMENT / structure signals,
# dual-signal / structure-anchored so they can NEVER flag a real economics / labor / clinical finding
# (precision-first per §-1.3: fail-OPEN on ambiguity — over-strip is worse than a leak). FLAG-not-drop
# / detector-only: a flagged unit is WITHHELD from the rendered rollup and from the abstract/conclusion
# harvest, KEPT in evidence + the credibility disclosure; the faithfulness engine (strict_verify / NLI /
# 4-role / provenance / span-grounding) is UNCHANGED. Gated by the caller under
# ``render_chrome_screen_enabled()`` (default ON).
#
#   (1) CITATION-COUNTER / CITEDBY-PATH API blob — a scraped citation-metrics API response
#       ("… includes the values 54719037, 1074, and 1837 … references path …"). The furniture
#       markers are an API field/path token (``citedby`` / ``references path`` / a crossref-openalex
#       API host). ``citedby`` and the API host are furniture on their own (a real finding never
#       writes them). ``references path`` is dual-signal-guarded — it must co-occur with a BARE 5+
#       digit integer (an unformatted entity/citation id like ``54719037``; a real finding writes a
#       grouped number ``54,719,037`` or ``$54 million``, never a bare 8-digit id) within the clause.
#   (2) VERSION-HEADER cover block — the SSRN / working-paper cover version furniture
#       ("This version: March 18, 2026  First version: August 16, 2025  Please click here for the
#       latest version."). ``This/First version:`` is dual-signal-guarded (must be followed by a
#       month name or a digit — a DATE, not the prose "in this version, we …"); the "please click …
#       for the latest version" CTA is unambiguous furniture on its own.
#   (3) FIGURE-CAPTION / AXIS apparatus — CAPTION/AXIS-ONLY (Codex #1344 P1 tighten). The prior
#       rule matched "Figure A2 replicates … Figure 12" / "for each quintile is as follows" ANYWHERE,
#       so a hit ate real result prose and dropped its citation unit. The rule now matches ONLY a span
#       whose WHOLE sentence is pure figure/axis furniture: a bare figure-to-figure caption cross-
#       reference ("Figure A2 replicates the prior analysis in Figure 12.") or a table axis lead-in
#       that ENDS at the descriptor colon with no data row ("… for each quintile is as follows:"). It
#       is anchored ^…$ over a SINGLE sentence (``[^.]*`` never crosses a period), so a welded methods
#       sentence that merely describes what a figure does is NOT eaten. A KEEP guard adds a second
#       fail-open safety: if the span ALSO carries a result verb/qualifier (shows/finds/reports/remains/
#       increase/decrease/negative/positive/significant/…) OR a numeric RESULT (a decimal, a percent, a
#       p-value, a dollar/grouped magnitude — a bare figure id like "A2"/"12"/"[22]" is NOT a result
#       number), the span is real finding prose and is KEPT. A real finding that merely CITES a figure
#       ("As shown in Figure 12, employment rose across each quintile") carries neither anchor.
_CITEDBY_API_RE = re.compile(
    r"\bcitedby\b"
    r"|\b(?:api\.crossref\.org|api\.openalex\.org)\b",
    re.IGNORECASE,
)
_REFERENCES_PATH_RE = re.compile(r"\breferences[\s\-]?path\b", re.IGNORECASE)
_BARE_ENTITY_ID_RE = re.compile(r"(?<![\d.])\d{5,}(?![\d.])")
_VERSION_HEADER_RE = re.compile(
    r"\b(?:this|first|current|previous|earlier)\s+version\s*:\s*"
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?|\d)"
    r"|\bplease\s+click\s+here\s+for\s+the\s+(?:latest|most\s+recent)\s+version\b",
    re.IGNORECASE,
)
# CAPTION/AXIS-ONLY figure apparatus (Codex #1344 P1 tighten): anchored ^…$ over a SINGLE
# sentence so ONLY a pure caption/axis stub matches; ``[^.]*`` never crosses a sentence period,
# so a welded methods sentence is structurally excluded.
_FIGURE_APPARATUS_RE = re.compile(
    # a bare figure-to-figure caption cross-reference stub (the whole sentence is the cross-ref)
    # I-deepfix-001 c-fix (iter3): the second Figure ref must be effectively sentence-final —
    # only whitespace / period / trailing cite may follow it. This fails OPEN on any substantive
    # trailing result prose ("...and confirms the relationship is robust..."), which is real
    # finding text, not caption furniture.
    r"^\W*Figure\s+[A-Z]?\d+\s+replicates\b[^.]*?\bFigure\s+[A-Z]?\d+\b\s*\.?\s*(?:\[\d+\])?\s*$"
    # a table axis lead-in that ENDS at the descriptor colon (no data row follows)
    r"|^\W*[^.]*?\bfor\s+each\s+quintile\s+is\s+as\s+follows\s*:\s*(?:\[\d+\])?\s*$",
    re.IGNORECASE,
)
# KEEP guard (fail-open, §-1.3): a result verb/qualifier marks real finding prose — never furniture.
_FIGURE_RESULT_VERB_RE = re.compile(
    r"\b(?:shows?|showed|finds?|found|reports?|reported|reveal(?:s|ed)?|remains?|remained|"
    # I-deepfix-001 c-fix (iter3): result verbs Codex flagged as missing — a welded result
    # sentence using any of these is KEPT (fail-open), never dropped as furniture.
    r"confirms?|confirmed|demonstrat\w+|indicat\w+|establish\w+|suggest\w+|imply|implies|implied|"
    r"robust|consistent|"
    r"increas(?:e|es|ed|ing)|decreas(?:e|es|ed|ing)|rose|rise[sn]?|risen|fell|fall(?:s|en|ing)?|"
    r"declin\w+|grew|grow(?:s|ing)?|widen\w+|narrow\w+|"
    r"negative|positive|significant(?:ly)?|associat\w+|correlat\w+|"
    r"higher|lower|greater|elevat\w+|reduc\w+|gradient|elasticity|coefficient)\b",
    re.IGNORECASE,
)
# KEEP guard (fail-open, §-1.3): a numeric RESULT (decimal / percent / p-value / grouped or dollar
# magnitude). A bare figure/table id ("A2", "12", "[22]") is NOT a result number.
_FIGURE_RESULT_NUMBER_RE = re.compile(
    r"\d\.\d"                                         # a decimal value (4.2, 0.05)
    r"|\d\s?%|\bpercent\b|\bpercentage\s+points?\b"   # a percentage
    r"|\bp\s?[<>=]\s?0?\.\d"                          # a p-value
    r"|\$\s?\d"                                       # a dollar amount
    r"|\d{1,3}(?:,\d{3})+",                           # a grouped thousands magnitude
    re.IGNORECASE,
)


def _figure_apparatus_is_pure_furniture(text: str) -> bool:
    """I-deepfix-001 (#1344): True iff ``text`` is a CAPTION/AXIS-ONLY figure-apparatus stub with no
    real result content. Fail-open (§-1.3): a span that ALSO carries a result verb/qualifier or a
    numeric result is real finding prose and is KEPT (returns False), never withheld — this is the
    Codex-#1344-P1 tighten that stops the rule eating result prose and dropping its citation unit."""
    if not _FIGURE_APPARATUS_RE.search(text):
        return False
    if _FIGURE_RESULT_VERB_RE.search(text) or _FIGURE_RESULT_NUMBER_RE.search(text):
        return False  # KEEP: a real finding welded with a figure/axis reference
    return True


def _contains_drb72_apparatus_chrome(text: str) -> bool:
    """I-deepfix-001 (#1344): True iff ``text`` CONTAINS one of the three drb_72 apparatus chrome
    classes the enumerated denylist was blind to — a citation-counter/citedby-path API blob, an
    SSRN/working-paper version-header cover block, or a CAPTION/AXIS-ONLY figure-apparatus stub.
    High-precision / dual-signal-anchored (never flags a real finding). Detector-only
    (FLAG-not-drop); the faithfulness engine is UNCHANGED."""
    if _CITEDBY_API_RE.search(text):
        return True
    if _REFERENCES_PATH_RE.search(text) and _BARE_ENTITY_ID_RE.search(text):
        return True
    if _VERSION_HEADER_RE.search(text):
        return True
    return _figure_apparatus_is_pure_furniture(text)


def _dotted_toc_hits(text: str) -> int:
    """Count dotted section-number tokens whose TitleCase word is NOT a magnitude unit (so a
    "3.2 Million / 4.5 Billion" magnitude pair contributes ZERO ToC hits)."""
    return sum(
        1 for word in _DOTTED_SECTION_TOKEN_RE.findall(text)
        if word.lower() not in _MAGNITUDE_UNIT_WORDS
    )


def _is_predominantly_nonlatin(text: str) -> bool:
    """True iff ``text`` carries a long non-Latin run AND its non-Latin characters outnumber its
    Latin letters — a foreign-page scrape, not an English finding quoting a short foreign term."""
    if not _NONLATIN_RUN_RE.search(text):
        return False
    nonlatin = len(_NONLATIN_CHAR_RE.findall(text))
    latin = len(re.findall(r"[A-Za-z]", text))
    return nonlatin >= _MIN_NONLATIN_RUN_CHARS and nonlatin >= latin


# ─────────────────────────────────────────────────────────────────────────────
# A1+A2 (I-wire Wave-A) — the render-seam chrome classes the drb_72 audit found the containment
# predicate STILL blind to. At iter-3b the set is TWO high-precision / structure-anchored rules: a
# title-page / monograph MASTHEAD and a BIBLIOGRAPHY-fragment. (A pure TABLE/FIGURE CAPTION-stub rule
# was tried and REMOVED — a present-tense captioned finding could not be separated from a bare
# caption without over-stripping; see the note where the class used to live below.) Each rule is
# FLAG-not-drop (a flagged unit is withheld from the rendered rollup and KEPT in evidence_pool +
# the disclosure); the faithfulness engine (strict_verify / NLI / 4-role / provenance) is UNCHANGED.
#
# (1) TITLE-PAGE / MONOGRAPH MASTHEAD — an ALL-CAPS "<MONTH> <YEAR> <DOC-TYPE>" cover header
#     ("JUNE 2011 RESEARCH", "MARCH 2020 WORKING PAPER"). It fires ONLY on a PURE all-caps line: the
#     trailing guard ``(?![^\n]*[a-z])`` requires NO lowercase letter anywhere after the doc type, so
#     any running-prose sentence — which ALWAYS carries a lowercase letter, whether the continuation
#     is lowercase ("… RESEARCH: employment rose …") OR title-case ("… RESEARCH: Employment rose …")
#     — can NEVER match. ``(?m)^`` + an optional bounded leading ALL-CAPS institute/series run
#     ("CENTRE FOR ECONOMIC POLICY JUNE 2011 …") anchor the genuine cover-header form. A masthead that
#     carries "No. 8452" is LEAKED (its "o" trips the guard): the safe direction, since over-strip of
#     a real finding is worse than a leaked masthead (§-1.3 drop-path law).
_TITLE_PAGE_MASTHEAD_RE = re.compile(
    r"(?m)^\W{0,4}"
    r"(?:[A-Z][A-Z&.'/-]*\s+){0,6}"
    r"\b(?:JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)"
    r"\s+(?:19|20)\d{2}\s+"
    r"(?:RESEARCH|REPORT|WORKING\s+PAPER|DISCUSSION\s+PAPER|WHITE\s+PAPER|POLICY\s+BRIEF|"
    r"BRIEFING|BULLETIN|MONOGRAPH|PREPRINT)\b"
    # Codex P1 (Wave-A iter-3b): fire ONLY on a pure ALL-CAPS masthead line. A real sentence ALWAYS
    # carries a lowercase letter somewhere after the doc type — whether the continuation is lowercase
    # ("JUNE 2011 RESEARCH: employment rose …") OR title-case ("… RESEARCH: Employment rose …") — so
    # requiring NO lowercase letter to end-of-line rejects every running-prose sentence. A masthead
    # that legitimately carries "No. 8452" is LEAKED (its "o" trips the guard), which is the safe
    # direction: over-strip of a real finding is worse than a leaked masthead (§-1.3 drop-path law).
    r"(?![^\n]*[a-z])"
)
# (2) BIBLIOGRAPHY fragment — a reference-list locator a real finding sentence never contains: a
#     "pp. 45-67" page range, a "Retrieved from http…" / "Accessed <date>" retrieval line, or an
#     "In: <Editor> (Ed(s).)" book-chapter opener. DELIBERATELY OMITTED: a bare "12(3): 45-67"
#     volume(issue):pages locator — it collides with real clinical prose ("in arm 2 (3): 45-60
#     patients responded"), and over-strip of a real finding is worse than a leak (§-1.3). An
#     author-block-glued-to-"Abstract" byline is ALSO deliberately not screened here: it cannot be
#     separated from real academic/clinical prose ("Patients at Massachusetts General Hospital showed
#     improved Abstract Reasoning scores") without over-stripping — genuine title pages carry an
#     ORCID / email / superscript-affiliation signal already caught by ``_contains_missed_chrome_class``
#     and ``_contains_iwire016_gap_furniture``.
_BIBLIOGRAPHY_FRAGMENT_RE = re.compile(
    r"\bpp\.\s*\d+\s*[-–—]\s*\d+\b"
    r"|\bRetrieved\s+from\s+https?://"
    r"|\bAccessed\s+(?:on\s+)?\d{1,2}\s+[A-Za-z]+\s+\d{4}\b"
    r"|\bIn:\s+[A-Z][A-Za-z.\s,&]+?\(Eds?\.\)",
    re.IGNORECASE,
)
# (3) PURE TABLE / FIGURE CAPTION stub — REMOVED at Wave-A iter-3b (Codex P1). A caption-opening unit
#     carries a real PRESENT-TENSE finding whose verb no finite whitelist can enumerate and which has
#     no -ed/-ing morphology ("Table 1. Patients receive standard care after randomization.[1]",
#     "Figure 2: The low-dose arms lack measurable benefit.[1]"), so any caption-stub screen
#     over-withholds real findings. Per §-1.3 (over-strip is worse than a leak) the table/figure
#     caption class is DEFERRED — it cannot be separated from real captioned findings without a real
#     clause parser. Masthead + bibliography-fragment (high-precision, structure-anchored) remain.


def _contains_missed_titlepage_biblio_caption(text: str) -> bool:
    """A1+A2 (I-wire Wave-A): True iff ``text`` CONTAINS a still-missing render-seam chrome class — an
    ALL-CAPS title-page/monograph masthead OR an unambiguous bibliography-fragment locator. (The
    table/figure caption class was removed at iter-3b — it could not be separated from real captioned
    findings without over-stripping.) High-precision / detector-only (FLAG-not-drop); the faithfulness
    engine is UNCHANGED."""
    if _TITLE_PAGE_MASTHEAD_RE.search(text):
        return True
    return bool(_BIBLIOGRAPHY_FRAGMENT_RE.search(text))


# ─────────────────────────────────────────────────────────────────────────────
# I-deepfix-001 P1_chrome_gate (#1344) — the SEVEN box1 render-seam chrome CLASSES the containment
# predicate was empirically proven blind to (all 8 shipped box1 chrome strings returned False; all
# three nets that route through ``_contains_forensic_chrome`` — the render-seam sanitize pass, the
# chrome canary, and the verified-compose K-span junk screen — failed together). Each rule is a
# high-precision, label/structure-anchored CONTAINMENT signal (fires even when the class is welded
# INTO otherwise-real prose) that can NEVER flag a real economics / labor / clinical finding
# (precision-first per §-1.3: over-strip of a real finding is worse than a leaked furniture unit).
# FLAG-not-drop / suppress-only: a flagged unit is WITHHELD from the rendered rollup and KEPT in
# evidence_pool + the disclosure; the faithfulness engine (strict_verify / NLI / 4-role / provenance
# / span-grounding) is UNCHANGED. Gated by the caller under ``render_chrome_screen_enabled()``.
# Frontier basis: trafilatura 2.1 / jusText stopword-density boilerplate SIGNALS ported as a
# text-level predicate (the tools need raw HTML the render seam no longer has).
#
#   (1) PUBLISHER PAYWALL / PURCHASE CTA — "Add to cart", "Purchase this article", "Subscribe for
#       unlimited", "Rent this article", "printable version". Distinct from the legacy
#       ``_PAYWALL_ACCESS_RE`` (Sage/Atypon "get full access to this article") — this covers the
#       cart/subscription CTA form. Multi-word, CTA-specific; a finding never carries these.
#   (2) MULTILINGUAL LICENSE / REPOSITORY furniture — German repository boilerplate
#       ("Standard-Nutzungsbedingungen", "EconStor", "Die Dokumente auf …", "zu eigenen
#       wissenschaftlichen Zwecken"). Distinctive repository tokens a real English finding never
#       contains. ("Terms of Use" alone is deliberately NOT screened — too generic.)
#   (3) GLUED AUTHOR-STATS-TABLE — either a Stata summary-table header run ("Variable Obs Mean
#       Std. Dev. Min Max") OR >=2 glued "Surname<digit>" author-superscript tokens
#       ("Kanbach1 Heiduk2 Kraus3"). The surname-digit rule is the RISKY one (a clinical
#       "Group1 … Group2" could collide), so it is GUARDED by ``_stopword_density`` < the floor:
#       a pure author list has near-zero stopwords while real prose does not.
#   (4) ASTERISKED-AUTHOR STREET + ZIP affiliation block — a US "City, ST 02142" postal block
#       (unambiguous), or a corresponding-author marker co-occurring with a street address. A real
#       finding never carries a full postal address.
#   (5) EXEC / PROMO BIO — a job-title ("Chief Executive Officer", "CEO", "Founder", "Managing
#       Director") WELDED to a promo predicate ("visionary", "thought leader", "award-winning",
#       "driving digital transformation"). DUAL-signal: a real finding that merely names a CEO
#       ("the CEO announced layoffs") carries no promo predicate and is KEPT.
#   (6) STITCHED METADATA-RECITAL citation — a reference recital ("… journal article, volume 42,
#       article 7, authored by …"). The "journal article" + "volume N" + ("article N" | "authored
#       by") co-occurrence is a stitched biblio recital a finding never writes.
#   (7) SHORT NAV / TOPIC-LIST item — the RISKY short-nav rule, guarded on FOUR ANDed conditions:
#       word-count <= 6 AND ends with a bare ordinal ("Labor Market Trends 3.2") AND no finite verb
#       AND ``_stopword_density`` < the floor. All four together isolate a scraped ToC/nav entry
#       from a real short sentence (which carries a verb and stopwords).
_PAYWALL_CTA_BOX1_RE = re.compile(
    r"\badd\s+to\s+cart\b"
    r"|\bpurchase\s+(?:this\s+)?(?:article|pdf|access|subscription)\b"
    r"|\brent\s+(?:this\s+)?article\b"
    r"|\bbuy\s+(?:now|this\s+article|the\s+pdf)\b"
    r"|\bsubscribe\s+(?:for|to\s+get)\s+(?:unlimited|full|instant)\b"
    r"|\bstart\s+your\s+free\s+trial\b"
    r"|\bprintable\s+version\b",
    re.IGNORECASE,
)
_REPO_LICENSE_FURNITURE_RE = re.compile(
    r"\bStandard-?Nutzungsbedingungen\b"
    r"|\bNutzungsbedingungen\b"
    r"|\bEconStor\b"
    r"|\bLeibniz[- ]Informationszentrum\b"
    r"|\bzu\s+eigenen\s+wissenschaftlichen\s+Zwecken\b"
    r"|\bDie\s+Dokumente\s+auf\b",
    re.IGNORECASE,
)
_STATS_SUMMARY_HEADER_RE = re.compile(
    r"\bObs\.?\s+Mean\b"
    r"|\bMean\s+Std\.?\s*Dev\.?\b"
    r"|\bVariable\s+Obs\b"
    r"|\bStd\.?\s*Dev\.?\s+Min\s+Max\b",
    re.IGNORECASE,
)
# A glued author-superscript token: a name-like stem (>=3 letters, any case, so an OCR-mangled
# "bALACHANDER2" byline surname counts while "Q1" does not) welded — OR joined by ONE space — to a
# 1-2 digit affiliation superscript that is NOT part of a decimal / percent / longer number
# (``(?![\w.%])``). The finite finding-label allowlist (Group / Stage / Type / ...) is DROPPED: it was
# open-ended and could never enumerate every real TWO-CATEGORY label ("High School1 Low College2",
# "Blue Collar1 White Collar2" — School / College / Collar are not authorable in any finite list), so
# it still over-stripped real labor / economic findings (Codex blocker). Instead rule 3b is anchored to
# the STRONGER author-LIST structure a real finding never carries: >=3 such surname-digit pairs, OR
# exactly 2 pairs PLUS an author/affiliation CO-SIGNAL in the same unit (see ``_AUTHOR_COSIGNAL_RE``).
# Two bare category-labels (exactly 2 pairs, no co-signal) therefore NEVER trip it, while a genuine
# glued byline (5 welded names, or a spaced "Surname 2, Surname 1, First Last 2" OCR list, or 2 names +
# an affiliation) still fires. Precision-first per §-1.3: over-stripping a real finding is the harm.
_SURNAME_DIGIT_PAIR_RE = re.compile(r"\b([A-Za-z]{3,})[ ]?(\d{1,2})(?![\w.%])")
# An author/affiliation co-signal that upgrades EXACTLY 2 surname-digit pairs to an author byline: an
# affiliation keyword (University / Institute / College / Department as a WHOLE word — "\bCollege\b"
# never matches the welded "College2" in a labelled finding), an "et al." marker, or an email address.
# A finite, high-precision set; still ANDed under the stopword-density guard so real prose that merely
# names an institution ("Researchers at Stanford University found Group1 and Group2 differed" — density
# above the floor) is NOT upgraded. Precision-first per §-1.3.
#
# The superscript author ASTERISK is deliberately NOT an author co-signal at ALL — not even the
# ">=2 starred pairs" form the iter-1 fix used. A "*" welded to a "Surname<digit>" token is byte-
# identical whether it is an author corresponding-author marker ("Jane Smith1* John Doe2*") OR a
# statistical / footnote SIGNIFICANCE STAR on a category label ("High School1* Low College2*
# earnings differed" — TWO starred category labels, no independent author signal). The iter-1
# ">=2 starred pairs" heuristic could not tell these apart and over-stripped the real two-category /
# table finding (Codex iter-2 P1 blocker). So the asterisk path now requires an INDEPENDENT author
# signal (``_AUTHOR_COSIGNAL_RE``): the exactly-2-pair upgrade fires ONLY on an affiliation keyword /
# "et al." / email. Precision-first per §-1.3: a genuine bare-stars-only two-author byline that
# carries no affiliation/email/et-al ("Jane Smith1* John Doe2*") is now an ACCEPTED LEAK (leaked page
# furniture is far lower harm than deleting a real clinical / labor / economic finding); the >=3-pair
# path still catches any real glued author LIST, and 2 names + a real affiliation still fires.
_AUTHOR_COSIGNAL_RE = re.compile(
    r"\b(?:University|Institute|College|Department)\b"
    r"|\bet\s+al\b"
    r"|[\w.+-]+@[\w-]+\.[A-Za-z]{2,}",
    re.IGNORECASE,
)


def _surname_digit_pair_count(text: str) -> int:
    """Count "Surname<digit>" author-superscript pairs (welded ``Kanbach1`` or single-space ``Archbold
    2``), with NO finding-label allowlist — the pair COUNT plus an author/affiliation co-signal (not a
    per-word allowlist) is what separates a genuine glued byline from a real two-category finding. See
    ``_SURNAME_DIGIT_PAIR_RE`` and the rule-3b call site for the >=3 / 2+co-signal structure."""
    return len(_SURNAME_DIGIT_PAIR_RE.findall(text))
# A US "City, ST 02142" postal block. On its OWN this over-strips a real finding that merely cites a
# place (Codex P1 iter 1); it is chrome ONLY with an affiliation CO-SIGNAL (a street address or a
# corresponding-author marker), so rule 4 ANDs it below.
_US_CITY_STATE_ZIP_RE = re.compile(r"\b[A-Z][A-Za-z.\-]+,\s+[A-Z]{2}\s+\d{5}(?:-\d{4})?\b")
_CORRESP_AUTHOR_RE = re.compile(
    r"\*\s*correspond|\bcorrespond(?:ing|ence)\s+(?:author|to)\b", re.IGNORECASE
)
_STREET_ADDRESS_RE = re.compile(
    r"\b\d{1,5}\s+(?:[A-Z][a-z]+\s+){1,4}"
    r"(?:Street|St\.|Avenue|Ave\.?|Road|Rd\.?|Drive|Dr\.?|Boulevard|Blvd\.?|Lane|Ln\.?|"
    r"Way|Square|Sq\.?|Court|Ct\.?)\b"
)
_EXEC_TITLE_RE = re.compile(
    r"\bchief\s+\w+\s+officer\b|\bC[EFOT]O\b|\b(?:co-)?founder\b|\bmanaging\s+director\b|"
    r"\bpresident\s+and\s+ceo\b|\bvice\s+president\b|\bexecutive\s+director\b|\bpartner\s+at\b",
    re.IGNORECASE,
)
_PROMO_PREDICATE_RE = re.compile(
    r"\bvisionary\b|\bthought\s+leader(?:ship)?\b|\bpassionate\s+about\b|\baward[- ]winning\b|"
    r"\bworld[- ]class\b|\bleading\s+expert\b|\bdriving\s+(?:digital\s+)?transformation\b|"
    r"\brenowned\b|\bseasoned\s+(?:leader|executive|professional)\b|\btrusted\s+advisor\b|"
    r"\bproven\s+track\s+record\b|\bindustry\s+veteran\b",
    re.IGNORECASE,
)
_METADATA_RECITAL_RE = re.compile(
    r"\bjournal\s+article\b[^.]{0,80}\bvolume\s+\d+\b[^.]{0,60}\b(?:article\s+\d+|authored\s+by)\b"
    r"|\bvolume\s+\d+\b[^.]{0,30}\bissue\s+\d+\b[^.]{0,30}\bauthored\s+by\b",
    re.IGNORECASE,
)
# Rule 7 helpers: a trailing bare ordinal (a standalone 1-3 digit / dotted section number at the
# very end, e.g. "3.2" / "5"; a trailing "0.42%" carries a % so it never matches), and the small
# finite-verb / copula lexicon whose ABSENCE (with the other three guards) marks a nav/topic stub.
_TRAILING_CITE_STRIP_RE = re.compile(r"(?:\s*\[\d+\])+\s*$")
_ENDS_WITH_BARE_ORDINAL_RE = re.compile(r"(?:^|\s)\d{1,3}(?:\.\d{1,2})?\s*$")
_CHROME_STOPWORD_DENSITY_FLOOR = 0.10
_NAV_ITEM_MAX_WORDS = 6
_CHROME_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "at", "for", "with", "by",
    "from", "as", "is", "are", "was", "were", "be", "been", "being", "am", "that", "this",
    "these", "those", "it", "its", "their", "his", "her", "they", "we", "our", "you", "your",
    "which", "who", "whom", "whose", "than", "then", "into", "over", "under", "about", "between",
    "among", "per", "via", "not", "no", "nor", "so", "if", "while", "during", "after", "before",
    "above", "below", "up", "down", "out", "off", "how", "when", "where", "what", "why", "all",
    "each", "more", "most", "some", "such", "also", "may", "can", "will", "would", "should",
    "could", "has", "have", "had", "do", "does", "did", "versus", "vs", "both", "either",
})
def _stopword_density(text: str) -> float:
    """The fraction of ALPHABETIC tokens in ``text`` that are common English stopwords (PURE). A
    scraped author list / ToC-nav stub has near-zero stopword density; real running prose does not.
    The precision guard for the risky surname-digit (rule 3b) and short-nav (rule 7) chrome rules."""
    words = re.findall(r"[A-Za-z]+", text.lower())
    if not words:
        return 0.0
    return sum(1 for w in words if w in _CHROME_STOPWORDS) / len(words)


def _is_titlecase_heading(text: str) -> bool:
    """True iff EVERY content word (>=3 letters and not a stopword) starts uppercase — the Title-Case
    shape of a scraped ToC / nav / section heading ("Labor Market Trends 3.2"). This REPLACES the old
    finite-verb-absence heuristic (Codex P1 iter 1: a small verb lexicon mislabels real short claims
    whose verb is outside it — "doubled", "worsened", "adopted", "differed" — as nav stubs). A real
    short sentence carries at least one LOWERCASE content word (its verb / object), so it is not
    Title-Case and is kept. Requires >=2 content words so a one-word label is not a "heading"."""
    content_words = [
        w for w in re.findall(r"[A-Za-z]+", text)
        if len(w) >= 3 and w.lower() not in _CHROME_STOPWORDS
    ]
    if len(content_words) < 2:
        return False
    return all(w[0].isupper() for w in content_words)


def _is_short_nav_topic_item(text: str) -> bool:
    """Rule 7 (the risky short-nav rule): True iff ``text`` is a scraped ToC / nav / topic-list stub
    under ALL FOUR guards — <= 6 words AND ends with a bare ordinal AND stopword-density below the
    floor AND Title-Case heading shape (every content word capitalized). Any one guard failing keeps
    a real short sentence (precision-first per §-1.3)."""
    core = _TRAILING_CITE_STRIP_RE.sub("", text.strip()).strip()
    words = core.split()
    if not (1 <= len(words) <= _NAV_ITEM_MAX_WORDS):
        return False
    if not _ENDS_WITH_BARE_ORDINAL_RE.search(core):
        return False
    if _stopword_density(core) >= _CHROME_STOPWORD_DENSITY_FLOOR:
        return False
    return _is_titlecase_heading(core)


def _contains_p1_box1_chrome(text: str) -> bool:
    """I-deepfix-001 P1_chrome_gate (#1344): True iff ``text`` CONTAINS one of the seven box1
    render-seam chrome CLASSES the containment predicate was blind to (paywall/purchase CTA;
    multilingual license/repository furniture; glued author-stats-table; asterisked-author
    street+ZIP affiliation; exec/promo bio; stitched metadata-recital citation; short nav/topic-list
    stub). High-precision / label-anchored; detector-only (FLAG-not-drop); the faithfulness engine
    is UNCHANGED."""
    s = text
    # (1) publisher paywall / purchase CTA
    if _PAYWALL_CTA_BOX1_RE.search(s):
        return True
    # (2) multilingual license / repository furniture
    if _REPO_LICENSE_FURNITURE_RE.search(s):
        return True
    # (3a) Stata summary-table header run
    if _STATS_SUMMARY_HEADER_RE.search(s):
        return True
    # (3b) glued author byline, anchored to author-LIST STRUCTURE (NOT a per-word label allowlist —
    #      that was open-ended and still over-stripped real TWO-CATEGORY findings like "High School1
    #      Low College2 earnings differed" / "Blue Collar1 White Collar2 wages diverged", Codex
    #      blocker). Fire ONLY on >=3 surname-digit pairs, OR exactly 2 pairs PLUS an INDEPENDENT
    #      author/affiliation co-signal in the SAME unit — all still under the stopword-density guard.
    #      The co-signal is an affiliation keyword (University|Institute|College|Department) / "et al."
    #      / email ONLY. The superscript author asterisk is NOT a co-signal (not even ">=2 starred
    #      pairs"): two starred CATEGORY labels ("High School1* Low College2* earnings differed") are
    #      byte-identical to a two-author starred byline, so the iter-1 starred-pair heuristic
    #      over-stripped that real finding (Codex iter-2 P1 blocker). A genuine bare-stars-only byline
    #      ("Jane Smith1* John Doe2*", no affiliation/email/et-al) is now an ACCEPTED LEAK — leaked
    #      furniture is far lower harm than deleting a real finding (§-1.3 precision-first).
    _pairs = _surname_digit_pair_count(s)
    _cosignal = bool(_AUTHOR_COSIGNAL_RE.search(s))
    if (
        (_pairs >= 3 or (_pairs == 2 and _cosignal))
        and _stopword_density(s) < _CHROME_STOPWORD_DENSITY_FLOOR
    ):
        return True
    # (4) asterisked-author street + ZIP affiliation block. A City,ST ZIP is chrome ONLY with an
    #     affiliation CO-SIGNAL (a street address or a corresponding-author marker); a bare City,ST
    #     ZIP in a real finding ("... in Cambridge, MA 02142 ...") is KEPT — Codex P1 iter 1.
    if _US_CITY_STATE_ZIP_RE.search(s) and (
        _STREET_ADDRESS_RE.search(s) or _CORRESP_AUTHOR_RE.search(s)
    ):
        return True
    if _CORRESP_AUTHOR_RE.search(s) and _STREET_ADDRESS_RE.search(s):
        return True
    # (5) exec / promo bio (dual-signal: job title WELDED to a promo predicate)
    if _EXEC_TITLE_RE.search(s) and _PROMO_PREDICATE_RE.search(s):
        return True
    # (6) stitched metadata-recital citation
    if _METADATA_RECITAL_RE.search(s):
        return True
    # (7) short nav / topic-list stub (four-guarded)
    return _is_short_nav_topic_item(s)


# ─────────────────────────────────────────────────────────────────────────────
# Box C QUALITY fix (workflow wioabua6u) — the render-seam chrome CLASSES the containment
# predicate above was STILL PROVEN BLIND to on the live Box A/C breadth section. Each rule is
# high-precision + STRUCTURE-ANCHORED to furniture a real finding never carries (constraint 2,
# precision-first): an author affiliation-byline / a date WELDED onto a section header, website
# nav-menu glyph furniture, a file-asset size inventory, a bibliographic recital, an IMF/ToC
# trailing-page heading, a heading glued to prose, a pipeline repetition marker, and a
# predominantly non-English (Vietnamese Latin-extended) heading. FLAG-not-drop / detector-only: a
# flagged UNIT is withheld from the rendered rollup, the SOURCE stays in evidence_pool + its
# credibility disclosure; the faithfulness engine (strict_verify / NLI / 4-role D8 / provenance /
# span-grounding) is UNCHANGED. Gated by the caller under render_chrome_screen_enabled() (default ON).

# author affiliation-byline furniture (bio line / masthead author block).
_BOXC_AFFIL_BYLINE_RE = re.compile(
    r"\bis\s+(?:a\s+)?(?:Non-?Resident\s+)?Senior\s+Fellow\b"
    r"|\bAuthors?\s+and\s+[Cc]ontributors\b"
    r"|\bAbout\s+(?:CSIS|Brookings|the\s+Author)\b"
    r"|\bEDITORS\b[\s\S]{0,80}?\bAUTHORS\b"
)
# a calendar date WELDED directly onto a section header word (author-date + "Abstract"/etc.).
_BOXC_DATE_WELDED_HEADER_RE = re.compile(
    r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}\s+"
    r"(?:Abstract|Introduction|Conclusion|Executive\s+Summary)\b"
)
# website nav-menu furniture -- glyphs / bracketed nav labels a real finding never carries, plus a
# markdown nav-link run ("](https://...) * [").
# Correction 6 (Codex+Fable gate): written with EXPLICIT \uXXXX unicode escapes so the SOURCE stays
# pure-ASCII and no file-encoding / mojibake ambiguity can silently break a glyph class. NON-raw
# string: \uXXXX expands to the literal char in the compiled pattern; \\ escapes the regex
# metacharacters. Glyphs: \u2794 = heavy rightwards arrow, \u2261 = triple-bar, \u2718 = ballot-X,
# \u00fc = u-umlaut, \u00b7 = middle-dot, \u2022 = bullet. Same classes as before.
_BOXC_NAV_MENU_RE = re.compile(
    "\u2794"                                             # heavy round-tipped rightwards arrow
    "|\u2261\\s*Menu"                                    # triple-bar [ws]* Menu
    "|\u2718"                                             # heavy ballot X
    "|\\[Zur(?:\u00fc|ue)ck\\]"                          # [Zurueck] with u-umlaut or ue
    "|\\[Startseite"                                     # [Startseite
    "|\\]\\(https?://[^)]+\\)\\s*[*\u00b7\u2022]\\s*\\["  # ](url) [ws]* {* mid-dot bullet} [ws]* [
)
# file-asset-metadata inventory — >=2 size tokens WELDED to a file-asset noun ("paper PDF of 6 MB",
# "text file of 213.59 KB", "study brief PDF of 1.08 MB"): a download-widget size inventory.
# Correction 1 (Codex+Fable gate): the prior ">=2 BARE size tokens" trigger over-dropped real
# quantitative claims that merely carry two data sizes — "grew from 570 GB in 2020 to 45 TB by 2023
# [7]" / "Each A100 card provides 80 GB ... consumer cards offer 24 GB [12]". Anchor the token to a
# preceding FILE-ASSET noun (PDF / file / download / attachment / document / text file / brief) so a
# bare data-magnitude claim is KEPT and only a file-download size inventory is flagged (precision-
# first, constraint 2). Still requires >=2 such WELDED matches (one incidental file size is fine).
_BOXC_FILE_SIZE_TOKEN_RE = re.compile(
    r"(?:PDF|file|download|attachment|document|text\s+file|brief)"
    r"\s+(?:of\s+)?\d+(?:\.\d+)?\s?(?:MB|KB|GB|TB)\b",
    re.IGNORECASE,
)
_BOXC_MIN_FILE_SIZE_TOKENS = 2
# bibliographic-recital-as-prose ("published volume 13, article 569", "with an ISSN date of").
_BOXC_BIBLIO_RECITAL_RE = re.compile(
    r"published\s+volume\s+\d+\s*,\s*article\s+\d+"
    r"|with\s+an\s+ISSN\s+date\s+of",
    re.IGNORECASE,
)
# IMF/ToC trailing-page heading — a Title-Case heading run ending in a bare page number with NO
# verb. The shape admits ONLY Capitalized words + a small connective allowlist + a trailing 1-3
# digit page number, so any lowercase content word (a real sentence's verb/object) breaks the match.
_BOXC_TOC_PAGE_RE = re.compile(
    r"^(?:(?:[A-Z][\w’'.&/-]*|and|of|the|for|to|in|on|at|a|an|with|from|by|[-–—&])[:,]?\s+)+"
    r"\d{1,3}$"
)
# heading-glued-to-prose — an ALL-CAPS multiword run of 5+ words embedded anywhere, and a leading
# standalone policy-brief heading token followed by unrelated prose.
_BOXC_ALLCAPS_RUN_RE = re.compile(r"\b(?:[A-Z][A-Z0-9]*[A-Z]\s+){4,}[A-Z][A-Z0-9]*[A-Z]\b")
_BOXC_HEADING_OPENER_RE = re.compile(
    r"^\s*(?:Elevator\s+pitch|Key\s+findings|One[- ]page\s+summary|Executive\s+summary)\b\s+[A-Z]"
)
# a pipeline-internal "(also mirrored)" duplicate/repetition annotation (never in a real finding).
_BOXC_REPETITION_MARKER_RE = re.compile(r"\(also\s+mirrored\)", re.IGNORECASE)
# predominantly non-English heading in an English-contract run — a run of Vietnamese Latin-extended
# tone-marked characters (Latin Extended Additional U+1E00–U+1EFF + the Vietnamese-specific
# precomposed letters Ă/ă/Đ/đ/Ơ/ơ/Ư/ư) a real English finding never carries at this density.
_BOXC_VIET_DIACRITIC_RE = re.compile(
    r"[Ḁ-ỿĂăĐđƠơƯư]"
)
_BOXC_MIN_VIET_DIACRITIC_CHARS = 3
# Correction 2 (Codex+Fable gate): any alphabetic (unicode) character, for the DENSITY denominator.
_BOXC_ALPHA_RE = re.compile(r"[^\W\d_]", re.UNICODE)
# tone-marked chars must be at least this SHARE of the alphabetic characters for the density leg to
# fire (a predominantly-Vietnamese heading; an English sentence naming a Vietnamese entity is well
# below it and is KEPT). ~18% chosen so the leaked full-Vietnamese title (~0.22) drops while the two
# entity-naming English claims (~0.06-0.07) are preserved.
_BOXC_VIET_DENSITY = 0.18
# OR the mostly-UPPERCASE heading shape: uppercase-dominant AND carrying the >=floor tone-mark run.
_BOXC_UPPER_HEADING_RATIO = 0.6


def _is_boxc_toc_trailing_page(text: str) -> bool:
    """True iff ``text`` is an IMF/ToC trailing-page heading — a multi-word Title-Case heading run
    ending in a bare 1-3 digit page number with no finite verb. High-precision: the shape admits only
    Capitalized words + a small connective allowlist, so any lowercase content word keeps a real
    sentence; requires >=4 tokens and >=2 Capitalized content words so a short "Table 3" stub is out
    of this rule's lane."""
    core = _TRAILING_CITE_STRIP_RE.sub("", text.strip()).strip()
    if not _BOXC_TOC_PAGE_RE.match(core):
        return False
    tokens = core.split()
    if len(tokens) < 4:
        return False
    caps = [t for t in tokens[:-1] if t[:1].isupper() and len(re.sub(r"[^A-Za-z]", "", t)) >= 2]
    return len(caps) >= 2


def _is_boxc_non_english(text: str) -> bool:
    """True iff ``text`` is a predominantly non-English (Vietnamese) heading in an English-contract run
    (e.g. "CACH MANG CONG NGHIEP 4.0 TAI VIET NAM ...").

    Correction 2 (Codex+Fable gate): the prior ABSOLUTE ``count >= 3`` over-dropped real English claims
    that merely NAME one or two Vietnamese entities — "Vietnam Ministry of Labour (Bo Lao dong ...)
    projects 3 million displaced workers by 2030 [9]", "Prime Minister Pham Minh Chinh and Nguyen Thi
    Hong announced the strategy in 2024 [2]". This uses a DENSITY test instead: the tone-marked chars
    must be at least ``_BOXC_VIET_DENSITY`` of the ALPHABETIC characters (a SHARE, not an absolute
    count), OR the text must be the mostly-UPPERCASE heading shape carrying the tone-mark run. A
    one-or-two-proper-noun English sentence stays below both bars and is KEPT (§-1.3 multilingual
    preservation); the full-Vietnamese heading crosses either bar and is DROPPED. A small floor
    (``_BOXC_MIN_VIET_DIACRITIC_CHARS``) still gates out incidental 1-2 accented characters."""
    diac = len(_BOXC_VIET_DIACRITIC_RE.findall(text))
    if diac < _BOXC_MIN_VIET_DIACRITIC_CHARS:
        return False
    alpha = _BOXC_ALPHA_RE.findall(text)
    if not alpha:
        return False
    # DENSITY leg: tone-marked chars as a SHARE of alphabetic chars.
    if diac / len(alpha) >= _BOXC_VIET_DENSITY:
        return True
    # OR the mostly-UPPERCASE heading shape (uppercase-dominant AND >=floor tone marks, already true).
    upper = sum(1 for c in alpha if c.isupper())
    return (upper / len(alpha)) >= _BOXC_UPPER_HEADING_RATIO


# Correction 3 (Codex+Fable gate): the affiliation-byline class must flag ONLY a PURE masthead (names +
# affiliations, no attributed result). A real finding that MENTIONS an author's affiliation in passing —
# "Landry Signé, who is a Senior Fellow at Brookings, projects that AI will shift 30 percent of tasks
# [4]." — carries BOTH a bracketed [N] citation AND a finite finding/report verb, so it is KEPT.
_BOXC_BRACKET_CITE_RE = re.compile(r"\[\d{1,3}\]")
_BOXC_FINDING_VERB_RE = re.compile(
    r"\b(?:project(?:s|ed|ing)?|estimat(?:e|es|ed|ing)|forecast(?:s|ed|ing)?|predict(?:s|ed|ing)?|"
    r"find(?:s)?|found|report(?:s|ed|ing)?|show(?:s|ed|ing|n)?|suggest(?:s|ed|ing)?|"
    r"indicat(?:e|es|ed|ing)|warn(?:s|ed|ing)?|conclud(?:e|es|ed|ing)|reduc(?:e|es|ed|ing)|"
    r"increas(?:e|es|ed|ing)|shift(?:s|ed|ing)?|displac(?:e|es|ed|ing)|rais(?:e|es|ed|ing)|"
    r"grow(?:s|ing)?|grew|reach(?:es|ed|ing)?|account(?:s|ed|ing)?\s+for|will\s+\w+)\b",
    re.IGNORECASE,
)


def _has_attributed_cited_finding(text: str) -> bool:
    """True iff ``text`` carries BOTH a bracketed [N] citation AND a finite finding/report verb — a real
    attributed finding that merely names an author affiliation in passing (KEEP). The pure masthead
    byline class (names + affiliations, NO [N] citation, NO finding verb) has neither and stays FLAGGED.
    Precision-first (constraint 2): the guard only ever RELAXES a drop; it never adds one."""
    return bool(_BOXC_BRACKET_CITE_RE.search(text) and _BOXC_FINDING_VERB_RE.search(text))


def _contains_boxc_render_chrome(text: str) -> bool:
    """Box C QUALITY fix (workflow wioabua6u): True iff ``text`` CONTAINS one of the render-seam
    chrome CLASSES the containment predicate was still proven blind to on the live Box A/C breadth
    section (author/date-welded byline · nav-menu glyph furniture · file-asset size inventory ·
    bibliographic recital · ToC trailing-page heading · heading-glued-to-prose · repetition marker ·
    predominantly non-English heading). High-precision / structure-anchored; detector-only
    (FLAG-not-drop); the faithfulness engine is UNCHANGED."""
    s = text
    # date-welded section header always flags; the affiliation byline flags ONLY when the unit has NO
    # surviving attributed cited finding (correction 3 — keep "…Senior Fellow…, projects … [4]").
    if _BOXC_DATE_WELDED_HEADER_RE.search(s):
        return True
    if _BOXC_AFFIL_BYLINE_RE.search(s) and not _has_attributed_cited_finding(s):
        return True
    if _BOXC_NAV_MENU_RE.search(s):
        return True
    if len(_BOXC_FILE_SIZE_TOKEN_RE.findall(s)) >= _BOXC_MIN_FILE_SIZE_TOKENS:
        return True
    if _BOXC_BIBLIO_RECITAL_RE.search(s):
        return True
    if _is_boxc_toc_trailing_page(s):
        return True
    if _BOXC_ALLCAPS_RUN_RE.search(s) or _BOXC_HEADING_OPENER_RE.search(s):
        return True
    if _BOXC_REPETITION_MARKER_RE.search(s):
        return True
    return _is_boxc_non_english(s)


# I-deepfix-001 (#1344) FF1-CHROME v2: the FOUR NEW page-furniture vocabularies the enumerated
# containment denylist never enumerated (recurrence of the I-wire-013 blind-predicate class on
# unlisted surface vocabularies) — service/dead-fetch interstitial · OpenAlex/entity-portal record
# scaffold · "Name - Honorific" bare byline directory stub · "Publication date:"/bare NN:N masthead.
# High-precision / structure-anchored / cited-finding-guarded. Detector-only (FLAG-not-drop); the
# faithfulness engine (strict_verify / NLI / D8 / provenance / span-grounding) is UNCHANGED.
# v2 (Codex+Fable build-gate precision fix): the v1 RULE 1 used an UNANCHORED `_SERVICE_OFFLINE_RE.search`
# whose narrow `_has_attributed_cited_finding` guard (needs a [N] citation AND a finding VERB — the
# copula "is" is not one) could NOT rescue a substantive cited finding that merely CONTAINS an outage
# phrase, so real claims like "Public employment service is unavailable in 37 percent of rural districts
# [7]." were over-dropped (the P1). v2 WHOLE-UNIT anchors RULE 1 (^…$ over the cite-stripped core) and
# adds the same KEEP guard to RULE 4 (the P2 bare-NN:N collision), so a real cited finding is NEVER
# dropped — precision-first per the operator-locked drop-path law (§-1.3).
_SERVICE_OFFLINE_RE = re.compile(
    r"^(?:this\s+)?(?:journal|site|website|server|service|page|content|portal|database|repository|domain)"
    r"\s+is\s+(?:currently\s+|temporarily\s+)?(?:offline|unavailable|down|under\s+maintenance|not\s+available)\s*[.!?]*$"
    r"|^service\s+(?:temporarily\s+)?unavailable\s*[.!?]*$"
    r"|^this\s+site\s+can[’']?t\s+be\s+reached\s*[.!?]*$",
    re.IGNORECASE,
)
_PORTAL_RECORD_SCAFFOLD_RE = re.compile(
    r"DetailsLocations"
    r"|Year\s*:\s*(?:19|20)\d{2}\s+Type\s*:\s*\w+\s+Abstract\s*:"
    r"|Type\s*:\s*article\s+Abstract\s*:"
    r"|Cited\s+by\s+\d+\s+Related\s+works",
    re.IGNORECASE,
)
_BYLINE_HONORIFIC_RE = re.compile(
    r"^[A-Z][A-Za-z.'’-]+(?:\s+[A-Z][A-Za-z.'’-]+){0,3}\s+[-–—]\s+"
    r"(?:Mr|Mrs|Ms|Mx|Miss|Dr|Prof|Professor|Sir|Dame|Rev)\.?$"
)
_PUB_DATE_MASTHEAD_RE = re.compile(
    r"(?<!the\s)\bPublication\s+date\b\s*:?\s*"
    r"(?:(?:19|20)\d{2}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(?:19|20)\d{2})",
    re.IGNORECASE,
)
_MASTHEAD_COSIGNAL_RE = re.compile(
    r"(?<!\d)\d{1,3}\s*:\s*\d{1,3}(?!\d)|Document Version|Published in|\bDOI\s*10\.|\bISSN[a-z]?\b",
    re.IGNORECASE,
)


def _contains_portal_masthead_status_chrome(text: str) -> bool:
    """True iff ``text`` is one of the four NEW page-furniture vocabularies (FF1-CHROME) the
    enumerated containment denylist never enumerated: (1) a service/dead-fetch interstitial
    ("This journal is currently offline.") — WHOLE-UNIT anchored AND cited-finding-guarded; (2) an
    OpenAlex/entity-portal record scaffold ("…DetailsLocations Year: NNNN Type: article Abstract: …");
    (3) a bare "Name - Honorific" byline/directory stub; (4) a "Publication date: <Month YYYY>"
    masthead paired with a bare "NN:N" volume:issue (or DOI/ISSN/Document-Version) co-signal AND
    cited-finding-guarded. High-precision / structure-anchored — detector-only (FLAG-not-drop); it
    never strips a substantive finding. Precision-first per the operator-locked drop-path law (§-1.3).
    Reuses ``_TRAILING_CITE_STRIP_RE`` and the ``_has_attributed_cited_finding`` KEEP guard so a real
    cited finding is never dropped."""
    s = text
    # The cite-stripped, whitespace-trimmed unit — the whole-unit anchor surface for RULEs 1 and 3.
    core = _TRAILING_CITE_STRIP_RE.sub("", text.strip()).strip()
    # RULE 1 — service/dead-fetch interstitial. WHOLE-UNIT anchored (Codex+Fable P1 over-strip fix): the
    # interstitial must BE the entire unit (after stripping a trailing [N] + terminal punctuation), so a
    # substantive cited finding that merely CONTAINS an outage phrase ("Public employment service is
    # unavailable in 37 percent of rural districts [7].") is NEVER dropped. The narrow
    # `_has_attributed_cited_finding` guard is kept as a second KEEP layer (it only ever relaxes a drop).
    if _SERVICE_OFFLINE_RE.search(core) and not _has_attributed_cited_finding(s):
        return True
    # RULE 2 — OpenAlex/entity-portal record scaffold (glued UI-button token / Year:/Type:/Abstract:
    # field-ladder); no guard needed (no author writes these text-extraction artifacts).
    if _PORTAL_RECORD_SCAFFOLD_RE.search(s):
        return True
    # RULE 3 — bare "Name - Honorific" byline/directory stub; whole-unit ^…$ anchored with the
    # honorific as the TERMINAL token (keeps "Ms. Parikh testified that … [9]").
    if _BYLINE_HONORIFIC_RE.match(core):
        return True
    # RULE 4 — masthead "Publication date: <Month YYYY>" + a bare volume:issue / DOI / ISSN /
    # Document-Version co-signal (dual-signal). The (?<!the\s) lookbehind + required co-signal + the
    # `_has_attributed_cited_finding` KEEP guard (Codex+Fable P2 fix) keep a real cited claim that
    # recites a publication date ("Publication date: March 2021 the study found a 2:1 response ratio [5].").
    if (
        _PUB_DATE_MASTHEAD_RE.search(s)
        and _MASTHEAD_COSIGNAL_RE.search(s)
        and not _has_attributed_cited_finding(s)
    ):
        return True
    return False


def _contains_forensic_chrome(text: str) -> bool:
    """True iff ``text`` CONTAINS page-furniture chrome (not only IS chrome). The CONTAINMENT
    unblinding ported from scripts/iwire013_sec11_forensic_audit.py, tightened for this drop path
    (see the module comment above). High-precision / structure-anchored; never flags a clean
    finding. Gated by the caller under ``render_chrome_screen_enabled()``."""
    s = text
    low = s.lower()
    # browser/UI · license · author/submission metadata · bibliographic/portal · masthead
    if _NAV_CHROME_RE.search(s) or _LICENSE_CHROME_RE.search(s) or _BIBLIO_CHROME_RE.search(s):
        return True
    # I-deepfix-001 (drb_72) FIX-A: ISSNe/ISSNp-aware, over-fire-safe ISSN masthead recital
    # (default-ON co-signal gate; OFF => byte-identical legacy bare ISSN).
    if _is_issn_masthead_chrome(s):
        return True
    # I-deepfix-002 (#1363) FIX-1: cookie/consent banner · DOI-registry error page · foreign masthead
    if _COOKIE_CONSENT_RE.search(s) or _DOI_ERROR_RE.search(s) or _is_foreign_journal_masthead(s):
        return True
    # I-deepfix-001 (#1344) DEFER-4: residual furniture-dominated units — publisher paywall CTA ·
    # working-paper cover masthead/disclaimer · PDF footnote/citation-apparatus run.
    if _is_residual_chrome_furniture(s):
        return True
    # I-deepfix-001 (#1344) chrome_canary_unblind: author-affiliation/email byline · ToC dot-leaders ·
    # "By clicking … you accept" consent banner (the three classes the canary was blind to).
    if _contains_missed_chrome_class(s):
        return True
    if _SUBMISSION_META_RE.search(s) or _MASTHEAD_CHROME_RE.search(s) or _STATS_TABLE_RE.search(s):
        return True
    if _ORCID_RE.search(s) or "orcid" in low or _AFFIL_MIDDOT_RE.search(s):
        return True
    if len(_URL_RE.findall(s)) >= _MIN_URLS_FOR_CHROME:
        return True
    if len(_DOI_URL_RE.findall(s)) >= _MIN_DOI_URLS_FOR_CHROME:
        return True
    # glued markdown header / ToC fragment
    if _INLINE_HEADER_RE.search(s) or _dotted_toc_hits(s) >= _MIN_DOTTED_TOC_HITS:
        return True
    if _STANDALONE_SECTION_NAME_RE.search(s):
        return True
    standalone_dotted = _STANDALONE_DOTTED_HEADING_RE.match(s)
    if standalone_dotted and standalone_dotted.group(1).lower() not in _MAGNITUDE_UNIT_WORDS:
        return True
    # I-wire-016 #1338 gap-fill (affiliation-glued / title+affiliation / author-attribution-phrase) —
    # the precision-safe masthead classes that leaked past the legacy categories.
    if _contains_iwire016_gap_furniture(s):
        return True
    # I-deepfix-001 #1344 drb72_apparatus_unblind: citation-counter/citedby-path API blob ·
    # SSRN/working-paper version-header cover · CAPTION/AXIS-ONLY figure apparatus (the classes that
    # leaked into cited claims + the Abstract/Conclusion sandwich; figure rule tightened per Codex P1).
    if _contains_drb72_apparatus_chrome(s):
        return True
    # A1+A2 (I-wire Wave-A): title-page/monograph masthead · author-block→Abstract byline ·
    # bibliography-fragment locator · pure table/figure caption stub (the classes the drb_72 audit
    # found the containment predicate STILL blind to). High-precision / fail-open on real prose.
    if _contains_missed_titlepage_biblio_caption(s):
        return True
    # I-deepfix-001 P1_chrome_gate (#1344): the SEVEN box1 render-seam chrome classes the containment
    # predicate was proven blind to (paywall/purchase CTA · multilingual license/repository furniture ·
    # glued author-stats-table · asterisked-author street+ZIP affiliation · exec/promo bio · stitched
    # metadata-recital citation · short nav/topic-list stub). High-precision / label-anchored.
    if _contains_p1_box1_chrome(s):
        return True
    # Box C QUALITY fix (workflow wioabua6u): the render-seam chrome classes proven STILL blind on
    # the live Box A/C breadth section — author/date-welded byline · nav-menu glyphs · file-asset
    # size inventory · bibliographic recital · ToC trailing-page heading · heading-glued-to-prose ·
    # repetition marker · predominantly non-English (Vietnamese) heading. High-precision / anchored.
    if _contains_boxc_render_chrome(s):
        return True
    # I-deepfix-001 #1344 FF1-CHROME v2: the four NEW furniture vocabularies the enumerated denylist
    # never enumerated — service/dead-fetch interstitial · OpenAlex/entity-portal record scaffold ·
    # "Name - Honorific" bare byline stub · "Publication date:"/bare NN:N masthead. WHOLE-UNIT anchored /
    # cited-finding-guarded (precision-first §-1.3); detector-only (FLAG-not-drop).
    if _contains_portal_masthead_status_chrome(s):
        return True
    # I-deepfix-001 (drb_72) FIX-B: figure alt-text axis enumeration ("The chart has 1 X axis … Y axis …").
    if chart_alt_chrome_gate_enabled() and _CHART_ALT_TEXT_RE.search(s):
        global _CHART_ALT_ACTIVATION_LOGGED
        if not _CHART_ALT_ACTIVATION_LOGGED:
            _CHART_ALT_ACTIVATION_LOGGED = True
            logger.info("[activation] chart_alt_chrome: fired=1 (chart-alt-text gate ON)")
        return True
    # foreign-page scrape (predominantly non-Latin)
    return _is_predominantly_nonlatin(s)


def render_chrome_screen_enabled() -> bool:
    """Default ON (LAW VI kill-switch ``PG_RENDER_CHROME_SCREEN=0``). When OFF, the NEW
    I-wire-012 chrome categories are skipped and the predicate is byte-identical to the
    legacy base junk screen (boilerplate + sentence-form web-chrome + CAPTCHA)."""
    return os.environ.get(_RENDER_CHROME_SCREEN_ENV, "1").strip().lower() in (
        "1", "true", "on", "yes", "enabled",
    )


def _base_junk(text: str) -> bool:
    """The PRE-I-wire-012 junk screen, byte-equivalent to the old ``_make_junk_screen``
    closure: production boilerplate OR sentence-form web-chrome OR CAPTCHA stub OR a
    unit that reduces to "" under ``strip_web_boilerplate``. Import-safe (access_bypass
    import failure falls back to the chrome + CAPTCHA screens, never fail-open to nothing)."""
    try:
        from src.tools.access_bypass import (  # noqa: PLC0415
            is_boilerplate_or_nonassertional as _boiler,
            strip_web_boilerplate as _strip_boiler,
        )
    except Exception:  # pragma: no cover - access_bypass import is stable in-tree
        return _is_web_chrome(text) or _is_captcha_stub(text)
    try:
        if bool(_boiler(text)) or _is_web_chrome(text) or _is_captcha_stub(text):
            return True
        return not (_strip_boiler(text) or "").strip()
    except Exception:  # pragma: no cover - boiler helpers are pure in-tree
        return _is_web_chrome(text) or _is_captcha_stub(text)


# I-deepfix-001 (#1369) FIX 4 — chrome TYPES the existing screens structurally cannot match (Fable,
# code-verified on box-2 report): (a) GENERATED document-navigation NARRATION ("...on page 46, presents
# Figure 4.1 on page 61, includes Figure 6.1 as a schematic") — span-grounded so strict_verify passes it,
# but it is document-structure furniture, not a research finding; (b) an author MASTHEAD carrying NO
# ORCID/ISSN (so _ORCID_RE + the ISSN masthead rule both miss it: "Alexandra Shajek 1. Institut für ...,
# GmbH, Berlin, Germany 2."). Default-ON kill-switch PG_RENDER_CHROME_NARRATION. Precision-first: the
# narration rule needs >=2 distinct structure references so a real claim mentioning ONE figure is safe.
_STRUCTURE_REF_RE = re.compile(
    r"\b(?:on\s+)?page\s+\d+\b|\bFig(?:ure|\.)?\s*\d+(?:\.\d+)?\b|\bTable\s+\d+(?:\.\d+)?\b"
    r"|\bas\s+a\s+schematic\b|\bchapter\s+\d+\b|\bsection\s+\d+(?:\.\d+)?\b",
    re.I,
)
_MASTHEAD_NO_ORCID_RE = re.compile(
    r"\b\d\s*\.?\s*(?:Institut|Institute|Universit|GmbH|Department|Laborator|Faculty|Ministry|Centre|Center)\b"
    r".{0,90}?\b(?:Germany|Deutschland|USA|United\s+States|France|Italy|Spain|Netherlands|Austria|"
    r"Switzerland|Sweden|Norway|Denmark|Finland|Belgium|Poland|Portugal|Greece|China|Japan|Korea|India|"
    r"Canada|Australia|Kingdom)\b",
    re.I,
)


def _render_chrome_narration_enabled() -> bool:
    """Kill-switch ``PG_RENDER_CHROME_NARRATION`` (default ON). Only an explicit 0/false/off/no
    disables; an EMPTY string stays ON."""
    return os.environ.get("PG_RENDER_CHROME_NARRATION", "1").strip().lower() not in ("0", "false", "off", "no")


# I-deepfix-001 (#1369) iter2/iter3 (Codex + Fable P1, WEIGHT-NOT-FILTER / no-drop): a REAL finding that
# merely cites figure/table LOCATIONS is NOT chrome. TWO keep-signals, both computed on the residual after
# stripping the structure references, so "Figure 4.1"'s "4.1" / "page 61"'s "61" never read as findings:
#   (a) a finding metric survives — a %, "percent/pp", a decimal, OR a plain/comma integer of >=2 digits
#       ("job losses of 1,200 and 900 workers"); OR
#   (b) SUBSTANTIVE content dominates — the structure references are a MINORITY of the text (< 45% of chars),
#       so a qualitative finding ("Table 2 and Table 3 show automation displaces routine work") is KEPT.
# Only text that is BOTH metric-free AND dominated by document-navigation refs ("...page 46, presents
# Figure 4.1 on page 61, includes Figure 6.1 as a schematic") is flagged as chrome. Err toward KEEP (§-1.3).
_FINDING_METRIC_RE = re.compile(
    r"\d+(?:\.\d+)?\s*%|\bpercent(?:age\s+points?)?\b|\bpp\b|\d{1,3}(?:,\d{3})+|\d+\.\d+|\b\d{2,}\b"
)
# Document-DESCRIPTION verb that DIRECTLY GOVERNS a structure noun — the writer narrating a document's own
# apparatus ("presents Figure 4.1", "includes Figure 6.1", "reproduces Table 2 as a schematic"). Codex iter-3
# P1: the verb ALONE is not enough — "present/illustrate/depict/include" are REAL finding verbs when they
# govern CONTENT ("present evidence that automation displaces work", "illustrate that ...", "depict a shift").
# So we require the description verb to be IMMEDIATELY followed by a structure noun (Figure/Table/Chart/...),
# OR the standalone "as a schematic" tail. This catches the box-2 navigation chrome without touching a real
# qualitative finding that merely uses "present/illustrate/depict".
# STRONG navigation signal: a description verb DIRECTLY governing a structure noun ("presents Figure 4.1").
# Each occurrence counts fully toward the narration chain.
_NAV_VERB_STRUCTURE_RE = re.compile(
    r"\b(?:outlines?|presents?|depicts?|illustrates?|includes?|reproduces?|shows?|contains?|summariz\w+)\s+"
    r"(?:the\s+|a\s+|an\s+)?(?:Fig(?:ure|\.)?|Table|Chart|Schematic|Diagram|Panel|Exhibit|Appendix|Chapter)\b",
    re.I,
)
# WEAK navigation signal: a bare "see Figure/Table/page" locator or an "as a schematic" tail. Codex iter-4 +
# Fable iter-5 P1 (no-drop): a REAL finding routinely carries such parentheticals — "(see Table 2) and
# manufacturing (see Figure 3)". So ALL of these together count AT MOST ONCE toward the chain.
_NAV_LOCATOR_RE = re.compile(
    r"\bas\s+a\s+schematic\b|\bsee\s+(?:figure|table|page)\b",
    re.I,
)


def _is_generated_narration_or_masthead(text: str) -> bool:
    """True iff ``text`` is generated document-navigation narration or an ORCID/ISSN-less author-
    affiliation masthead. NARRATION = >=2 structure refs AND no finding metric AND (a document-DESCRIPTION
    verb like outlines/presents/includes OR the structure refs DOMINATE the text). Weight-not-filter /
    no-drop (Codex+Fable P1): a real finding citing a table/figure location — quantitative ('3.2% ... Table 4
    on page 12.', 'job losses of 1,200 and 900 workers') OR qualitative ('Table 2 and Table 3 show automation
    displaces routine work') — is CONTENT and is NEVER dropped (it has a metric, or an outcome verb rather
    than a description verb, or low structure-share). PURE."""
    # Masthead: an affiliation block carrying a finding metric is a numbered-list FINDING, not a masthead.
    if _MASTHEAD_NO_ORCID_RE.search(text) and not _FINDING_METRIC_RE.search(text):
        return True
    refs = _STRUCTURE_REF_RE.findall(text)
    if len(refs) >= 2:
        residual = _STRUCTURE_REF_RE.sub(" ", text)
        if _FINDING_METRIC_RE.search(residual):
            return False  # a real finding metric survives the structure refs -> content, keep it
        ref_chars = sum(len(m) for m in refs)
        structure_dominates = ref_chars / (len(text.strip()) or 1) >= 0.45
        # Codex iter-3/4 + Fable iter-5 P1 (no-drop): pure document narration walks the reader through
        # MULTIPLE exhibits ("presents Figure 4.1 ... includes Figure 6.1 as a schematic"); a REAL finding
        # cites locations in passing ("...(see Table 2) and manufacturing (see Figure 3)", "present evidence
        # that ..."). So the chain = (every strong description-verb-governs-structure phrase) + (all the weak
        # bare "see X"/"as a schematic" locators counted AT MOST ONCE combined). Flag only when the chain
        # reaches 2 OR the structure refs outright dominate. A real finding never chains 2+ STRONG nav clauses.
        nav_chain = len(_NAV_VERB_STRUCTURE_RE.findall(text)) + min(1, len(_NAV_LOCATOR_RE.findall(text)))
        if nav_chain >= 2 or structure_dominates:
            return True   # metric-free + (multi-clause document-navigation OR structure-dominated) -> chrome
        return False      # metric-free finding with <=1 locator phrase and low structure-share -> keep it
    return False


def _is_new_chrome_category(text: str) -> bool:
    """The NEW I-wire-012 chrome categories (default-ON, high-precision) PLUS the I-wire-013 (#1327)
    CONTAINMENT forensic rules (a unit that CONTAINS glued page-furniture, not only IS junk)."""
    if _SHARED_RENDER_CHROME_RE.search(text):
        return True
    # I-deepfix-001 (#1369) FIX 4: generated page/figure narration + ORCID-less masthead (default-ON).
    if _render_chrome_narration_enabled() and _is_generated_narration_or_masthead(text):
        return True
    if _SHARED_CLAIM_HEADER_CHROME_RE.search(text):
        return True
    if _SHARED_TOC_RE.search(text):
        return True
    if _ORCID_RE.search(text):
        return True
    stripped = text.strip()
    if _DOC_LABEL_RE.match(stripped):
        return True
    if _DOI_ONLY_RE.match(stripped):
        return True
    # I-wire-014 (#1334): the benchmarked whole-unit-collapse furniture screen — a unit DOMINATED
    # by page furniture (journal metrics/cite/permissions/JEL/Associated-Records/member-only/
    # feature-story/cookie-geo/back-matter label runs) with no real clause surviving. Whole-unit
    # decision only (never an inline partial strip), so a real claim with a welded fragment is
    # preserved (validated content_preserved_rate = 1.0 on chrome_gold_augmented).
    try:
        from src.polaris_graph.generator.chrome_furniture_screen import (  # noqa: PLC0415
            is_furniture_dominant,
        )
        if is_furniture_dominant(text):
            return True
    except Exception:  # pragma: no cover - chrome_furniture_screen is stable in-tree
        pass
    # I-wire-013 (#1327): CONTAINMENT unblinding — glued ToC / masthead / author / license /
    # bibliographic / nav / stats-table / foreign-scrape welded into otherwise-real prose.
    return _contains_forensic_chrome(text)


def _is_unrenderable_sentence_form(text: str) -> bool:
    """``require_sentence_form`` extras for a unit that MUST be a standalone complete
    claim (a bullet / a lifted body sentence): a mid-word START cut (a lowercase opener
    is a span sliced mid-token — a real body sentence opens capital/quote/digit) or an
    INCOMPLETE sentence (no sentence-terminal punctuation after stripping a trailing
    ``[N]`` marker). NOT applied to verified-compose / enrichment clauses (which a
    composer may legitimately lowercase / leave mid-clause) — only to bullet/header
    surfaces, so a lowercased verbatim clause is never over-dropped."""
    core = text.strip()
    if not core:
        return True
    first = core[:1]
    if first.islower():
        return True
    no_cite = _SHARED_TRAILING_CITE_RE.sub("", core).rstrip()
    if no_cite and no_cite[-1] not in ".!?\"')]":
        return True
    return False


# I-deepfix-001 P0 (box2 chrome infestation): furniture-chrome vocabulary the I-wire-013 containment
# port never enumerated (BLS wage-in-table, PDF object dict, tel:/mailto, >=2 inline md-links, scraped
# masthead byline). SUPPRESS-ONLY, faithfulness-neutral. Kill-switch PG_SOURCE_FURNITURE_CHROME (default ON).
_FURN_WAGE_RE = re.compile(r"\$\s?[\d,]+(?:\.\d+)?\s*(?:per\s+(?:year|hour)|/\s*(?:year|hour|hr))", re.IGNORECASE)
_FURN_PDF_OBJ_RE = re.compile(r"(?:%PDF|\bendobj\b|\bendstream\b|\bxref\b|/ID\s*\[<|\bIndex\[\d+\s+\d+\]|\b\d+\s+\d+\s+obj\b|/(?:Root|Prev|Length|BBox)\b)")
_FURN_CONTACT_RE = re.compile(r"\b(?:tel:|mailto:)\S", re.IGNORECASE)
_FURN_MDLINK_RE = re.compile(r"\]\(\s*https?://")
_FURN_TBWIDGET_RE = re.compile(r"#TB_inline|&inlineId=|&width=\d+", re.IGNORECASE)
# Codex P1: the author-byline rule was DROPPED — "[David Autor](url) is a professor at MIT who finds that
# one more robot ... reduces wages by 0.42%" matched it and suppressed a REAL finding. Box2's actual masthead
# byline chrome is always glued to a wage table (caught by _FURN_WAGE_RE) so no coverage is lost. Over-drop-safe.

# I-deepfix-001 wave-2 (#1370): the furniture-chrome vocabulary the box2 §-1.1 line-by-line read exposed the
# wave-1 set still missed — a dashboard chart-legend dump (a RUN of >=3 bare "+NN%" tokens, no sentence
# structure), a bare international CONTACT phone number, a nav CTA ("view details" / "Learn more about the"),
# a document-TITLE recital ("The document is titled ..."), and CC-license / publisher boilerplate. SUPPRESS-ONLY,
# faithfulness-neutral. Each pattern was verified NON-matching against the box2 MUST-KEEP real findings (the
# Acemoglu robot -0.42% wage stat, the Eloundou 1.8% exposure stat, the GDP 1.5%/3%/3.7% projection, the SMEs
# 83% stat, the Accenture 26.08% stat) — a genuine finding's percents are ALWAYS separated by prose words, so
# the consecutive-"%"-run signature never fires on them (over-drop-safe, the Codex-P1 byline lesson applied).
_FURN_CHARTDUMP_RE = re.compile(r"(?:[+\-]?\d+(?:\.\d+)?\s?%\s+){2,}[+\-]?\d+(?:\.\d+)?\s?%")
_FURN_PHONE_RE = re.compile(r"\+\d{1,3}[\s\-]\d{2,4}[\s\-]\d{2,4}(?:[\s\-]\d{2,4})?")
# Fable gate (wave-2): "learn more about the" / "read more" substring-match REAL synthesis prose
# ("workers learn more about the mechanism of task substitution") — DROPPED (byline-trap). Only the
# unambiguous nav CTAs remain; neither ever appears inside a genuine finding.
_FURN_NAVCTA_RE = re.compile(r"\bview details\b|\bclick here\b", re.IGNORECASE)
# Fable gate (wave-2): the bare "is titled" leg substring-matched a REAL cited finding ("the study,
# which is titled 'Generative AI at Work,' found +14%"). Tightened to the RECITAL form only — a doc-noun
# IMMEDIATELY followed by "(is )titled" ("The document is titled …", "A work titled …") — so a mid-prose
# ", which is titled" (comma breaks the doc-noun adjacency) is never matched. Over-drop-safe.
_FURN_DOCTITLE_RE = re.compile(
    r"\b(?:a|an|the)\s+(?:document|work|study|report|book|guide|paper|article|publication|chapter)\s+(?:is\s+)?titled\b",
    re.IGNORECASE,
)
_FURN_PUBLISHER_RE = re.compile(
    r"books in this series are published|some rights are reserved|users can reuse,\s*share,?\s*adapt|authors alliance",
    re.IGNORECASE,
)
# Codex gate (wave-2) P1: a unit carrying a genuine finding SIGNAL — a decimal, a percentage, or a
# finding VERB — must NEVER be dropped by the SOFT furniture legs (doc-title recital, >=2 md-links),
# because a real finding legitimately mentions a title ("A study titled X FOUND +14%") or carries a
# linked author + linked paper. Only a pure recital / link-farm with NO finding is chrome. The HARD
# legs (PDF-object dict, chart-legend dump, publisher boilerplate, contact-phone) are unambiguous and
# fire regardless. Over-drop-safe (verified vs the box2 MUST-KEEP findings + the Codex adversarial cases).
_FINDING_SIGNAL_RE = re.compile(
    r"\d\.\d|\b\d+(?:\.\d+)?\s?%|\b(?:found|finds|estimat\w+|report\w+|show\w+|showed|conclud\w+|"
    r"observ\w+|demonstrat\w+|reveal\w+|reduc\w+|increas\w+|associated with|correlat\w+|"
    r"percentage points?)\b",
    re.IGNORECASE,
)
# Codex gate (wave-2) P1: the phone leg fires ONLY with a contact CONTEXT word, so a signed statistical
# estimate ("+0.123 (0.045)") — digits/dots/parens/spaces, no contact context — is never dropped.
_FURN_CONTACT_CTX_RE = re.compile(
    r"\b(?:phone|telephone|fax|hotline|dial|call\s*back)\b",
    re.IGNORECASE,
)


def _source_furniture_chrome_enabled() -> bool:
    return os.getenv("PG_SOURCE_FURNITURE_CHROME", "1").strip().lower() not in ("0", "false", "off", "no")


def _contains_source_furniture_chrome(text: str) -> bool:
    """True iff ``text`` carries page/source FURNITURE chrome the enumerated categories miss: a PDF
    object-dictionary recital, a tel:/mailto: contact line, a wage figure inside a nav/pipe table or a
    table-widget id (BLS OOH), >=2 inline markdown links (nav link-furniture), or a scraped author
    masthead byline glued to a profile link. SUPPRESS-ONLY, faithfulness-neutral."""
    if not _source_furniture_chrome_enabled():
        return False
    s = str(text or "")
    if not s.strip():
        return False
    if _FURN_PDF_OBJ_RE.search(s):
        return True
    if _FURN_CONTACT_RE.search(s):
        return True
    if _FURN_WAGE_RE.search(s) and ("|" in s or _FURN_TBWIDGET_RE.search(s)):
        return True
    # I-deepfix-001 wave-2 (#1370): the box2 §-1.1 furniture classes wave-1 missed.
    # HARD legs (unambiguous furniture — fire regardless of finding-signal):
    if _FURN_CHARTDUMP_RE.search(s):  # a run of >=3 whitespace-separated bare %-tokens (chart legend)
        return True
    if _FURN_PUBLISHER_RE.search(s):  # CC-license / publisher boilerplate
        return True
    if _FURN_NAVCTA_RE.search(s):  # "view details" / "click here" (never inside a finding)
        return True
    # SOFT legs (Codex P1/P1-cont: guarded — a unit with a real finding SIGNAL is never dropped here.
    # Phone is under the guard AND format-tight AND context-gated so a signed statistic like
    # "Recruitment increased employment by +0.123 (0.045)" is triple-safe from a false drop):
    if not _FINDING_SIGNAL_RE.search(s):
        if _FURN_PHONE_RE.search(s) and _FURN_CONTACT_CTX_RE.search(s):  # a contact phone, not a statistic
            return True
        if _FURN_DOCTITLE_RE.search(s):  # a pure doc-title RECITAL ("The document is titled …")
            return True
        if len(_FURN_MDLINK_RE.findall(s)) >= 2:  # a link-farm / nav block, not a linked finding
            return True
    return False


def is_render_chrome_or_unrenderable(
    text: str,
    *,
    require_sentence_form: bool = False,
    known_words: "set[str] | frozenset[str] | None" = None,
) -> bool:
    """THE ONE shared render-side chrome+truncation predicate (I-wire-012 #1326; I-wire-013 #1327).

    True iff ``text`` is page-furniture chrome, a CAPTCHA/boilerplate stub, a numbered
    ToC / CC-license / masthead / login-wall fragment, a standalone scraped doc label
    ("Abstract"/"AI Summary"), an author-ORCID/affiliation list, a bare DOI row, glued
    page-furniture welded INTO real prose (I-wire-013 CONTAINMENT), or a mid-word/cut-span
    TRUNCATION. With ``require_sentence_form=True`` it ALSO rejects a mid-word-START fragment
    and an incomplete sentence (bullet/header surfaces only).

    ``known_words`` (I-wire-013 #1327): when a caller supplies the run's corpus-vocabulary
    allowlist, the truncation leg ALSO catches a CORPUS-GROUNDED span cut at a ``[N]`` boundary
    (a non-inflectional prefix/suffix of a longer corpus word — "… 1.2 Resea.[14]"). It defaults
    to ``None`` so every existing caller (including the canary) is unchanged: no corpus → the
    boundary-cut leg is skipped → no new false positive.

    SUPPRESS-ONLY: never promotes a unit, never alters a faithfulness VERDICT. The base
    screen (boilerplate/web-chrome/CAPTCHA) ALWAYS runs (preserving the pre-I-wire-012
    behaviour of every existing consumer); the NEW categories + truncation are gated on
    ``render_chrome_screen_enabled()`` (default ON) so a ``PG_RENDER_CHROME_SCREEN=0``
    run is byte-identical to the legacy base screen."""
    if not text or not str(text).strip():
        return True  # an empty unit is non-assertional by definition
    s = str(text)
    if _base_junk(s):
        return True
    if not render_chrome_screen_enabled():
        return False  # NEW categories OFF -> byte-identical to the legacy base screen
    if _is_new_chrome_category(s):
        return True
    # I-deepfix-001 P0 (box2 chrome infestation): the missing-vocabulary furniture classes. SUPPRESS-ONLY,
    # faithfulness-neutral; inside the render_chrome_screen_enabled() gate so PG_RENDER_CHROME_SCREEN=0 stays
    # byte-identical. Auto-fixes _screen_render_chrome_prose + _compose_junk_screen + the render seam at once.
    if _contains_source_furniture_chrome(s):
        return True
    try:
        from src.polaris_graph.generator.key_findings import (  # noqa: PLC0415
            is_truncated_fragment,
        )
        # When a corpus allowlist is supplied, treat the unit as eligible at BOTH boundaries so the
        # corpus-grounded span-cut leg fires on a cut at the unit's leading/trailing ``[N]`` edge
        # (the chokepoint splits the report into per-citation units before calling this). With no
        # corpus (known_words=None) the boundary flags are inert and only the marker leg runs.
        _eligible = known_words is not None
        if is_truncated_fragment(
            s,
            known_words,
            ends_before_marker=_eligible,
            starts_after_marker=_eligible,
        ):
            return True
    except Exception:  # pragma: no cover - key_findings is stable in-tree
        pass
    if require_sentence_form and _is_unrenderable_sentence_form(s):
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# I-wire-012 (#1326) — FAIL-LOUD chrome-as-claim CANARY on the SHIPPED report.
#
# A render-integrity tripwire: it measures what FRACTION of the report's CLAIM bullets
# are chrome (page furniture that rendered as a finding) and, in ``enforce`` mode above
# a floor, REFUSES to ship — so a chrome regression can NOT ship as
# ``released_with_disclosed_gaps``. It NEVER promotes a unit and NEVER touches a
# faithfulness verdict. Modes (LAW VI, default-safe):
#   off     — explicit opt-out: no telemetry, no enforce.
#   warn    — emit telemetry to the manifest; never fails the run.
#   enforce — DEFAULT (I-wire-013 #1327): emit telemetry AND fail the run (status flip) when rate > floor.
_RENDER_CANARY_MODE_ENV = "PG_RENDER_CHROME_CANARY"
_RENDER_CANARY_FLOOR_ENV = "PG_RENDER_CHROME_CANARY_FLOOR"
_DEFAULT_RENDER_CANARY_FLOOR = 0.05
_RENDER_CANARY_MODES = ("off", "warn", "enforce")
_DEFAULT_RENDER_CANARY_MODE = "enforce"

# A TOP-LEVEL report bullet (no leading indent) = a claim surface (Key-Findings, the
# per-claim corroboration header, a finding bullet). Indented ``  - SUPPORT:`` /
# ``  - GROUNDED-BUT-WEAK`` sub-bullets (source URLs, not claims) and numbered
# bibliography lines ("1. Title") are deliberately EXCLUDED so the rate measures
# chrome-as-CLAIM, not chrome-as-source-locator.
_TOP_LEVEL_BULLET_RE = re.compile(r"^-\s+(.*\S)\s*$")
_BOLD_MARKER_RE = re.compile(r"\*\*")


def render_chrome_canary_mode() -> str:
    """Canary mode from ``PG_RENDER_CHROME_CANARY`` (off|warn|enforce); default ``enforce``
    (I-wire-013 #1327 — the tripwire enforces by default, not telemetry-only). Fail-loud on an
    UNRECOGNIZED value (LAW II — no silent guessed fallback), mirroring ``render_chrome_canary_floor``.
    ``off`` is the explicit opt-out (telemetry suppressed by the caller; verdict never trips)."""
    raw = os.environ.get(_RENDER_CANARY_MODE_ENV)
    if raw is None or not raw.strip():
        return _DEFAULT_RENDER_CANARY_MODE
    mode = raw.strip().lower()
    if mode not in _RENDER_CANARY_MODES:
        raise ValueError(
            f"{_RENDER_CANARY_MODE_ENV}={raw!r} is not a valid chrome-canary mode "
            f"(expected one of {_RENDER_CANARY_MODES})"
        )
    return mode


def render_chrome_canary_floor() -> float:
    """Chrome-as-claim rate floor from ``PG_RENDER_CHROME_CANARY_FLOOR`` (default 0.05).
    Fail-loud on a non-float (LAW II — no silent guessed fallback); clamped to [0, 1]."""
    raw = os.environ.get(_RENDER_CANARY_FLOOR_ENV)
    if raw is None or not raw.strip():
        return _DEFAULT_RENDER_CANARY_FLOOR
    try:
        val = float(raw.strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{_RENDER_CANARY_FLOOR_ENV}={raw!r} is not a float (chrome-as-claim rate floor)"
        ) from exc
    return min(1.0, max(0.0, val))


def _report_claim_bullets(report_text: str) -> list[str]:
    """The report's TOP-LEVEL claim bullets, bold markers stripped (PURE)."""
    out: list[str] = []
    for line in (report_text or "").split("\n"):
        m = _TOP_LEVEL_BULLET_RE.match(line)
        if not m:
            continue
        out.append(_BOLD_MARKER_RE.sub("", m.group(1)).strip())
    return out


# I-deepfix-001 WS-7 (D3): the chrome canary was BLIND to prose — it scored only top-level claim BULLETS
# (_report_claim_bullets), so an in-prose chrome leak (a leading bare section-header word, an in-text
# "(1, 2)" ref marker, a truncated "(2017)" subject) shipped without tripping the canary (drb_72: 0/33
# bullets flagged while prose leaked). This adds the report's claim-bearing PROSE units to the canary
# DENOMINATOR, screened with the SAME shared predicate, so a prose leak now trips the canary fail-closed.
# MEASUREMENT ONLY — the canary computes a rate/verdict; it NEVER drops or edits a rendered unit (that is
# the render seam's job). Default-ON PG_RENDER_CHROME_CANARY_PROSE; OFF => bullets-only => byte-identical.
_RENDER_CANARY_PROSE_ENV = "PG_RENDER_CHROME_CANARY_PROSE"
_PROSE_UNIT_MIN_CHARS = 40


def _render_canary_prose_enabled() -> bool:
    return os.environ.get(_RENDER_CANARY_PROSE_ENV, "1").strip().lower() not in ("0", "false", "no", "off")


def _report_prose_units(report_text: str) -> list[str]:
    """The report's claim-bearing PROSE units (substantial non-bullet, non-header paragraph lines),
    EXCLUDING scaffolding sections (Bibliography / Methods / disclosures / Source corroboration / the H1
    question echo) whose legitimate DOIs/URLs are not chrome. PURE. These are the units the chrome canary
    was blind to (it scored only top-level bullets)."""
    out: list[str] = []
    in_scaffold = False
    for line in (report_text or "").split("\n"):
        s = line.strip()
        if not s:
            continue
        hdr = _SECTION_HEADER_RE.match(line)
        if hdr:
            title = hdr.group(2).strip().lower()
            in_scaffold = any(title.startswith(t) for t in _SCAFFOLDING_SECTION_TITLES)
            continue
        if in_scaffold:
            continue
        if _TOP_LEVEL_BULLET_RE.match(line) or _LEADING_BULLET_RE.match(line):
            continue  # bullets are already scored by _report_claim_bullets
        if len(s) >= _PROSE_UNIT_MIN_CHARS:
            out.append(_BOLD_MARKER_RE.sub("", s).strip())
    return out


def evaluate_render_chrome_canary(report_text: str) -> dict[str, Any]:
    """Compute the chrome-as-claim rate over the SHIPPED report's claim bullets AND prose units, and the
    canary verdict. PURE (no I/O). ``verdict='fail'`` ONLY in ``enforce`` mode when the rate exceeds the
    floor and there is at least one claim unit — so the caller can flip the run status. In ``warn``/``off``
    the verdict is always ``pass`` (telemetry only). Each chrome unit is screened with the SAME shared
    predicate every composer uses (chrome + truncation), so the canary and the screens can never disagree.
    WS-7 (D3): prose units are added to the denominator (default-ON PG_RENDER_CHROME_CANARY_PROSE) so an
    in-prose chrome leak trips the canary — MEASUREMENT ONLY, no rendered unit is dropped or edited."""
    bullets = _report_claim_bullets(report_text)
    units = list(bullets)
    prose_units = 0
    if _render_canary_prose_enabled():
        prose = _report_prose_units(report_text)
        prose_units = len(prose)
        units = units + prose
    chrome = [b for b in units if is_render_chrome_or_unrenderable(b)]
    total = len(units)
    n_chrome = len(chrome)
    rate = (n_chrome / total) if total else 0.0
    floor = render_chrome_canary_floor()
    mode = render_chrome_canary_mode()
    tripped = bool(total and mode == "enforce" and rate > floor)
    return {
        "mode": mode,
        "floor": floor,
        # WS-7 (D3): denominator now = bullets + prose units. total_claim_bullets kept for back-compat
        # consumers (= total scored units); total_claim_units + prose_units_scored are the explicit names.
        "total_claim_bullets": total,
        "total_claim_units": total,
        "prose_units_scored": prose_units,
        "chrome_claim_bullets": n_chrome,
        "chrome_as_claim_rate": round(rate, 4),
        "verdict": "fail" if tripped else "pass",
        "examples": [b[:120] for b in chrome[:5]],
    }


# ─────────────────────────────────────────────────────────────────────────────
# I-wire-013 (#1327) iter-3a — RENDER-SEAM CHOKEPOINT.
#
# ONE sanitization pass over EVERY claim-bearing unit of the FINAL assembled report (Abstract,
# Key-Findings bullets, every ``###`` section body INCLUDING multi_section_generator output, the
# Corroborated Weighted Findings citation-split blob, the Conclusion), dropping/repairing chrome +
# truncated units with the now-unblinded predicate. This is the single seam that screens the
# currently-unscreened multi_section_generator output (0 screen calls today). It runs AFTER every
# composer + the header-sanity screen and BEFORE the chrome canary, so the canary reads the cleaned
# artifact and a residual leak still trips it fail-closed.
#
# FAITHFULNESS (FROZEN engine): RENDER hygiene only — it SUPPRESSES a page-furniture / truncated
# unit, NEVER promotes one and NEVER touches a strict_verify / NLI / 4-role / span-grounding verdict.
# Page furniture is not a corroborating source, so suppressing it STRENGTHENS faithfulness.
#
# OVER-STRIP SAFE (the drop-path law "over-strip deletes a real finding, worse than a leak"):
#   * Per-``[N]``-unit granularity — a flagged citation unit is dropped WITH its own trailing marker
#     (marker-paired, so a kept finding never loses its citation and a dropped chrome unit never
#     orphans a marker). The 4005-char Corroborated-Weighted-Findings blob keeps every real finding;
#     only its chrome sub-units drop.
#   * Scaffolding sections (Bibliography / Methods / disclosures / Reliability / Source corroboration
#     / the H1 question echo) are EXCLUDED — their legitimate DOIs/URLs are not chrome.
#   * A unit carrying SUBSTANTIAL real prose plus a glued inline ``#`` header is REPAIRED (cut at the
#     header, prefix kept) — the remainder is dropped only when it independently re-tests as chrome,
#     so a real "Limitations: … most extreme.## Analytical synthesis …" paragraph is never lost.

# LAW VI: env-overridable, default ON (kill-switch ``PG_RENDER_SEAM_SANITIZE=0`` => no-op pass-through).
_RENDER_SEAM_SANITIZE_ENV = "PG_RENDER_SEAM_SANITIZE"
# I-deepfix-001 (drb_72) FIX-D: drop a bullet that carries NO claim text — only the list marker and/or
# orphan citation markers ("- ", "- [12]"). Such a bullet renders as an empty dash or a bare "[12]".
# Default-ON (``PG_CWF_EMPTY_BULLET_DROP``); OFF => byte-identical pass-through. SUPPRESS-ONLY: the
# cited evidence is untouched (it still appears wherever a real claim carries it).
_ENV_EMPTY_BULLET_DROP = "PG_CWF_EMPTY_BULLET_DROP"  # default ON
_EMPTY_BULLET_RE = re.compile(r"^\s*[-*]\s*(?:\[[^\]]+\]\s*)*$")


def empty_bullet_drop_enabled() -> bool:
    """Kill-switch ``PG_CWF_EMPTY_BULLET_DROP`` (default ON). OFF => an empty / marker-only bullet is
    left byte-identical (no drop)."""
    # I-deepfix-001 (#1369) FIX 4 — default-ON semantics: UNSET and EMPTY-STRING
    # are both ON; disabled ONLY by an explicit OFF token (see issn_chrome_gate).
    return os.environ.get(_ENV_EMPTY_BULLET_DROP, "1").strip().lower() not in (
        "0", "false", "no", "off",
    )
# LAW VI: the corpus known-word floor (a word must occur >= this many times across the run's fetched
# source text to count as "known" for the truncation allowlist). Mirrors the detector default.
_RENDER_SEAM_KNOWN_WORD_FLOOR_ENV = "PG_RENDER_SEAM_KNOWN_WORD_FLOOR"
_DEFAULT_KNOWN_WORD_FLOOR = 5
# A unit needs at least this many real-prose characters before a glued inline header in it is
# REPAIRED (prefix kept) rather than the whole unit dropped — below it the unit is treated as junk.
_MIN_REPAIR_PREFIX_CHARS = 40
# Section headers that are pipeline SCAFFOLDING, not carried-up source prose (no body units are
# screened under them; their legitimate DOIs/URLs must not be chrome-flagged). Matched against the
# header TITLE's leading text. Mirrors the detector's _SCAFFOLDING_TITLES.
_SCAFFOLDING_SECTION_TITLES = (
    "reliability header", "methods", "capability disclosures", "contradiction disclosures",
    "bibliography", "source corroboration", "evidence-support disclosure", "research report:",
)
_KNOWN_WORD_FIELDS = ("direct_quote", "statement", "title")
_SECTION_HEADER_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
# I-wire-017 (#1339) FIX C1: the shallowest header LEVEL (``###`` = 3) that may be dropped when its
# sanitized body collapses to no claim-bearing prose. Top-level (``#``/``##``) report-structure
# headers are never dropped (a top-level empty section is left for the operator to see), only the
# per-claim ``###``-and-deeper content sections that the render seam emptied out.
_MIN_DROPPABLE_EMPTY_HEADER_LEVEL = 3
_LEADING_BULLET_RE = re.compile(r"^\s*-\s+")
# I-wire-013 (#1327) iter-3b D-P1-1: split on BOTH the numeric ``[N]`` marker AND the provenance
# ``[#ev:<id>:<start>-<end>]`` token (single capture group, inner alternation — keeps the
# text/marker pairing in ``_sanitize_report_line`` intact) so the render seam covers per-citation
# units on provenance-cited reports too, not just numeric-cited ones. ``[^\]]*`` captures the whole
# ``[#ev:...]`` body up to its closing bracket. Reports with only ``[N]`` are byte-identical (the
# numeric alternative is unchanged).
_CITATION_SPLIT_RE = re.compile(r"(\[\d+\]|\[#ev:[^\]]*\])")
_INLINE_HEADER_SPLIT_RE = re.compile(r"#{1,6}\s+[A-Za-z]")

# I-deepfix-001 B6(a) (#1350): the per-claim "Source corroboration" section is a SCAFFOLDING title
# (byte-preserved above), so its worst chrome — a page-furniture scrape promoted to a basket HEADER
# bullet ("- **<masthead/ToC/affiliation>** — N verified independent source(s)") — never reaches the
# full containment predicate. This default-ON branch screens the corroboration section's HEADER
# bullets (only) through ``is_render_chrome_or_unrenderable``; a chrome header has its CLAIM TEXT
# replaced by a neutral placeholder while the verified-source COUNT is preserved verbatim. LAW VI
# kill-switch ``PG_CORROBORATION_SANITIZE=0`` => the section stays byte-preserved (pre-B6 behaviour).
#
# §-1.3 CONSOLIDATE-don't-DROP (the dominant HARD RULE, outranks the spec's literal "screen each
# sub-bullet"): the ``- SUPPORT:`` / ``- GROUNDED-BUT-WEAK:`` / ``- CONTRADICTED:`` sub-bullets carry
# a SOURCE locator (url / evidence_id / tier / weight) — NOT a claim — so they are KEEP-ONLY here;
# screening them risks the chrome predicate's "bare DOI/URL row" leg dropping a corroborating source,
# which is a faithfulness violation. A divergence from the seam spec's literal wording, documented in
# the deepfix honest-gaps. Faithfulness-NEUTRAL: this only suppresses a chrome CLAIM string; it never
# drops a source, count, or verdict.
_CORROBORATION_SANITIZE_ENV = "PG_CORROBORATION_SANITIZE"
# The corroboration section's title prefix (lower-cased), matched to scope the branch to ONLY that
# section (Bibliography / Methods / Reliability stay truly byte-preserved).
_CORROBORATION_SECTION_PREFIX = "source corroboration"
# A corroboration HEADER bullet: a TOP-LEVEL ``- **<claim>** — <count> verified ...`` line. The claim
# text is the ``**bold**`` span; the ``— N verified independent source(s)`` suffix is the count. We
# screen only the claim span and preserve the suffix verbatim. A sub-bullet (``  - SUPPORT: ...``) is
# INDENTED, so the no-leading-whitespace anchor here never matches it (sub-bullets are KEEP-ONLY).
_CORROBORATION_HEADER_RE = re.compile(r"^-\s+\*\*(?P<claim>.+?)\*\*(?P<suffix>\s*[—-].*)?$")
# The neutral placeholder a chrome basket header collapses to — the COUNT suffix still carries the
# corroboration; only the unrenderable page-furniture claim string is withheld.
_CORROBORATION_CHROME_PLACEHOLDER = "(claim text withheld — source page-furniture, not a finding)"

# ─────────────────────────────────────────────────────────────────────────────
# I-deepfix-001 H1 (#1344) — SOURCE-INTERNAL inline reference-marker STRIP (REPAIR-first).
#
# THE GAP: a fetched source's OWN in-text citation apparatus ("... productivity rose (1, 2).",
# "... as shown (1; 3; 5).") is lifted verbatim into a verified span and rendered as a claim,
# leaving a bare "(1, 2)" numeral group in the body that is NOT one of the report's OWN ``[N]``
# provenance markers — it points at the SOURCE'S bibliography, not ours (dangling mis-attribution).
# This REPAIRS the sentence in place (removes only the leaked marker; the claim text survives) at
# the single render chokepoint, over every claim unit. High-precision: only a parenthetical whose
# WHOLE content is >=2 short integers separated by comma/semicolon is stripped, so a real
# parenthetical ("(1, 2, or 3 doses were compared)") is never touched (it has non-numeric words) and
# a solitary "(3)" is left alone (too ambiguous). The report's OWN citations use SQUARE brackets
# ``[N]`` / ``[#ev:...]`` and are never matched by this parenthesis rule. Faithfulness-NEUTRAL:
# render text only — no source, count, provenance token, or verdict is touched. LAW VI kill-switch
# ``PG_RENDER_SEAM_REF_STRIP=0`` => byte-identical (no strip).
_RENDER_SEAM_REF_STRIP_ENV = "PG_RENDER_SEAM_REF_STRIP"
# A leaked source-internal in-text citation: a parenthetical containing ONLY a comma/semicolon-
# separated run of >=2 integers (1-3 digits each), optional surrounding spaces. Matches "(1, 2)",
# "(1,2,3)", "(1; 2)", "( 10, 11 )". Does NOT match "(3)" (single), "(2020)" (4-digit year),
# "(1, 2 arms)" (has a word), or the report's square-bracket ``[N]`` markers.
_SOURCE_INTERNAL_REF_RE = re.compile(r"\(\s*\d{1,3}(?:\s*[,;]\s*\d{1,3})+\s*\)")
# A dangling space before sentence-final punctuation left by a stripped marker ("rose  .") is closed.
_PRE_PUNCT_SPACE_RE = re.compile(r"\s+([.!?,;:])")
_MULTISPACE_RE = re.compile(r"[ \t]{2,}")

# ─────────────────────────────────────────────────────────────────────────────
# I-deepfix-001 H2 (#1344) — SPLIT the glued "Corroborated Weighted Findings" enrichment blob.
#
# THE GAP: the enrichment section body is composed by ``build_verified_span_draft`` (one verbatim
# span-unit per source-work, each already carrying ONLY its OWN work's ``[ev_id]`` markers) but
# ``_rewrite_draft_with_spans`` re-joins every unit with a SPACE, so the whole section renders as ONE
# thousands-of-character paragraph — many unrelated source findings concatenated, unreadable, and the
# reader cannot tell which ``[N]`` binds which finding. This splits that glued paragraph into ONE
# bullet per finding (sentence) at the render seam. Each finding keeps its OWN trailing ``[N]`` marker
# (the sentence splitter preserves ``.[N]``), so NO citation is re-attributed — the composer already
# guaranteed each unit carries only its own work's markers. Faithfulness-NEUTRAL: pure render reflow —
# no text, marker, source, or verdict is added/removed/re-bound. LAW VI kill-switch
# ``PG_CWF_SPLIT_FINDINGS=0`` => byte-identical (the glued paragraph is left as one line).
_CWF_SPLIT_FINDINGS_ENV = "PG_CWF_SPLIT_FINDINGS"
# The enrichment section TITLES (lower-cased prefixes) whose glued body is split into per-finding
# bullets. Mirrors ``_ENRICHMENT_TITLE`` / ``_ENRICHMENT_RESIDUAL_TITLE``.
_ENRICHMENT_SECTION_PREFIXES = (
    _ENRICHMENT_TITLE.lower(),
    _ENRICHMENT_RESIDUAL_TITLE.lower(),
)


def render_seam_ref_strip_enabled() -> bool:
    """True iff the default-ON H1 source-internal ref-marker strip is active (LAW VI kill-switch
    ``PG_RENDER_SEAM_REF_STRIP=0`` => no strip)."""
    return os.environ.get(_RENDER_SEAM_REF_STRIP_ENV, "1").strip().lower() in (
        "1", "true", "on", "yes", "enabled",
    )


def cwf_split_findings_enabled() -> bool:
    """True iff the default-ON H2 CWF blob-split is active (LAW VI kill-switch
    ``PG_CWF_SPLIT_FINDINGS=0`` => the glued enrichment paragraph is left as one line)."""
    return os.environ.get(_CWF_SPLIT_FINDINGS_ENV, "1").strip().lower() in (
        "1", "true", "on", "yes", "enabled",
    )


def strip_source_internal_refs(text: str) -> str:
    """H1 REPAIR: remove leaked source-internal in-text citation markers (bare "(1, 2)" numeral
    groups) from ``text`` and close the whitespace they leave, keeping the claim prose intact. PURE;
    faithfulness-neutral (the report's OWN ``[N]`` / ``[#ev:...]`` square-bracket markers are never
    matched). Returns ``text`` unchanged when the kill-switch is OFF or no marker is present."""
    if not text or not render_seam_ref_strip_enabled():
        return text
    if not _SOURCE_INTERNAL_REF_RE.search(text):
        return text
    # Preserve the line's ORIGINAL leading indentation (a nested markdown bullet that happens to
    # carry a leaked ref must not be de-indented into a top-level bullet).
    lead = text[: len(text) - len(text.lstrip())]
    out = _SOURCE_INTERNAL_REF_RE.sub("", text)
    out = _PRE_PUNCT_SPACE_RE.sub(r"\1", out)
    out = _MULTISPACE_RE.sub(" ", out)
    return lead + out.strip()


def _is_enrichment_section_title(title: str) -> bool:
    """True iff a header title names the flat/residual "Corroborated Weighted Findings" enrichment
    section whose glued body H2 splits into per-finding bullets. PURE."""
    low = title.strip().lower().lstrip("# ").strip()
    return any(low.startswith(p) for p in _ENRICHMENT_SECTION_PREFIXES)


def _split_enrichment_blob_line(
    line: str, known_words: "set[str] | frozenset[str] | None"
) -> "tuple[list[str], int]":
    """H2: split ONE glued enrichment body line (a space-joined run of ``sentence.[N]`` findings)
    into one Markdown bullet per finding, sanitizing each finding through the SAME per-line screen
    (``_sanitize_report_line``) so a chrome/truncated finding still drops. Returns
    ``(bullet_lines, dropped)``. A line that is a header, blank, already a bullet, or splits to a
    single sentence is returned as ``([sanitized_line], dropped)`` (no spurious bulletisation).
    PURE except the lazy sentence-splitter import; faithfulness-neutral."""
    stripped = line.strip()
    # Only split real glued prose. A blank / heading / existing bullet / short single clause is
    # sanitized-in-place, never bulletised (over-split is worse than a leak for a real single line).
    if not stripped or stripped.startswith(("#", "-", "*", "|", ">")):
        clean, dropped = _sanitize_report_line(line, known_words)
        # I-deepfix-001 (drb_72) FIX-D: a bullet whose remainder — after removing the leading list
        # marker AND every citation marker — is empty carries NO claim ("- ", "- [12]"); drop it.
        if empty_bullet_drop_enabled() and clean.lstrip().startswith(("-", "*")):
            _residual = re.sub(r"^[-*]\s*", "", clean.strip())
            _residual = re.sub(r"\[[^\]]+\]", "", _residual)
            if not _residual.strip():
                return ([], dropped)
        return ([clean] if clean.strip() or not dropped else []), dropped
    try:
        from src.polaris_graph.generator.provenance_generator import (  # noqa: PLC0415
            split_into_sentences,
        )
        sentences = split_into_sentences(stripped)
    except Exception:  # pragma: no cover - provenance_generator is stable in-tree
        clean, dropped = _sanitize_report_line(line, known_words)
        return ([clean] if clean.strip() or not dropped else []), dropped
    if len(sentences) <= 1:
        clean, dropped = _sanitize_report_line(line, known_words)
        return ([clean] if clean.strip() or not dropped else []), dropped
    bullets: list[str] = []
    dropped = 0
    for sent in sentences:
        clean, drop = _sanitize_report_line(sent, known_words)
        dropped += drop
        clean = clean.strip()
        if clean:
            bullets.append(f"- {clean}")
    return bullets, dropped


def render_seam_sanitize_enabled() -> bool:
    """True iff the default-ON render-seam chokepoint is active (LAW VI kill-switch
    ``PG_RENDER_SEAM_SANITIZE=0`` => byte-identical pass-through)."""
    return os.environ.get(_RENDER_SEAM_SANITIZE_ENV, "1").strip().lower() in (
        "1", "true", "on", "yes", "enabled",
    )


def corroboration_sanitize_enabled() -> bool:
    """True iff the default-ON B6(a) corroboration-header chrome screen is active (LAW VI kill-switch
    ``PG_CORROBORATION_SANITIZE=0`` => the corroboration section stays byte-preserved)."""
    return os.environ.get(_CORROBORATION_SANITIZE_ENV, "1").strip().lower() in (
        "1", "true", "on", "yes", "enabled",
    )


def _is_corroboration_section_title(title: str) -> bool:
    """True iff a header title names the per-claim Source-corroboration rollup (B6(a) scope)."""
    return title.strip().lower().lstrip("# ").strip().startswith(_CORROBORATION_SECTION_PREFIX)


def _sanitize_corroboration_header(
    line: str, known_words: "set[str] | frozenset[str] | None"
) -> "tuple[str, int]":
    """B6(a): screen ONE corroboration HEADER bullet. A top-level ``- **<claim>** — N verified ...``
    whose CLAIM span is chrome (page furniture promoted to a basket header) has the claim string
    replaced by a neutral placeholder, preserving the verified-source COUNT suffix verbatim. Returns
    ``(clean_line, suppressed)`` where ``suppressed`` is 1 iff a chrome claim was withheld. A
    sub-bullet (indented) or a non-matching line is returned unchanged with 0. PURE; faithfulness-
    neutral (no source / count / verdict ever dropped)."""
    m = _CORROBORATION_HEADER_RE.match(line)
    if not m:
        return line, 0  # sub-bullet / blank / prose — KEEP-ONLY, untouched
    claim = m.group("claim").strip()
    suffix = m.group("suffix") or ""
    if claim and is_render_chrome_or_unrenderable(claim, known_words=known_words):
        return f"- **{_CORROBORATION_CHROME_PLACEHOLDER}**{suffix}", 1
    return line, 0


def _known_word_floor() -> int:
    """The corpus known-word frequency floor (LAW VI). Fail-soft on a non-int / non-positive value
    to the detector default (the allowlist must never be silently emptied)."""
    raw = os.environ.get(_RENDER_SEAM_KNOWN_WORD_FLOOR_ENV, "").strip()
    if not raw:
        return _DEFAULT_KNOWN_WORD_FLOOR
    try:
        return max(1, int(raw))
    except ValueError:
        return _DEFAULT_KNOWN_WORD_FLOOR


def build_known_words_from_evidence(evidence_rows: Any, floor: int | None = None) -> set[str]:
    """The corpus-vocabulary allowlist (the truncation false-positive guard) built from the run's OWN
    fetched source text — every lowercase token occurring >= ``floor`` times across the evidence
    rows' ``direct_quote`` / ``statement`` / ``title`` fields. So a word the corpus genuinely uses
    ("labor", "Acemoglu", "computerisation") never false-flags as a span cut, while an absent
    fragment ("Resea", "hodology") does. Accepts a list of row dicts OR a ``{evidence_id: row}`` map
    (the in-memory ``ev_pool`` shape). PURE; returns an empty set when no source text is available
    (=> the caller's truncation leg is simply skipped, never a wrong drop)."""
    if floor is None:
        floor = _known_word_floor()
    if isinstance(evidence_rows, dict):
        rows: Any = evidence_rows.values()
    else:
        rows = evidence_rows or ()
    freq: Counter[str] = Counter()
    for row in rows:
        if not isinstance(row, dict):
            continue
        for field in _KNOWN_WORD_FIELDS:
            value = row.get(field)
            if isinstance(value, str) and value:
                for word in _BOUNDARY_VOCAB_RE.findall(value):
                    freq[word.lower()] += 1
    return {word for word, count in freq.items() if count >= floor}


# An alphabetic vocabulary token (mirrors the detector's _WORD_RE / key_findings._BOUNDARY_WORD_RE).
_BOUNDARY_VOCAB_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*[A-Za-z]|[A-Za-z]")


def _unit_core_for_screen(text: str) -> str:
    """The screen-test text of a unit: leading ``- `` bullet marker and ``**bold**`` markers
    removed so the predicate judges the prose, not the markdown wrapper. PURE."""
    core = _LEADING_BULLET_RE.sub("", text.strip())
    return _BOLD_MARKER_RE.sub("", core).strip()


def _repair_glued_inline_header(text: str, known_words: "set[str] | frozenset[str] | None") -> "str | None":
    """If ``text`` is substantial real prose with a glued inline ``#`` header welded mid-unit, return
    the kept prefix (the header + remainder dropped) — but ONLY when the remainder independently
    re-tests as chrome, so a real paragraph is never over-stripped. Returns ``None`` when no
    repair applies (the caller then drops the whole unit)."""
    m = _INLINE_HEADER_SPLIT_RE.search(text)
    if not m or m.start() < _MIN_REPAIR_PREFIX_CHARS:
        return None
    prefix = text[:m.start()].rstrip()
    remainder = text[m.start():]
    prefix_core = _unit_core_for_screen(prefix)
    # Keep the prefix only if it is itself clean prose AND the excised remainder is independently
    # chrome (over-strip guard: never drop a remainder that re-tests clean).
    if not prefix_core or is_render_chrome_or_unrenderable(prefix_core, known_words=known_words):
        return None
    if not is_render_chrome_or_unrenderable(_unit_core_for_screen(remainder), known_words=known_words):
        return None
    return prefix


def _sanitize_report_line(line: str, known_words: "set[str] | frozenset[str] | None") -> "tuple[str, int]":
    """Sanitize ONE claim-section body line: split it into per-``[N]`` citation units, drop each unit
    (with its own trailing marker) that is chrome or a corpus-grounded truncation cut, and repair a
    unit that is real prose with a glued inline header. Returns ``(clean_line, dropped_count)``. A
    marker-less unit that is the whole short line is dropped iff it is chrome (a standalone ToC /
    masthead line). PURE."""
    parts = _CITATION_SPLIT_RE.split(line)
    segments: list[tuple[str, str]] = []
    i = 0
    while i < len(parts):
        seg_text = parts[i]
        seg_marker = parts[i + 1] if i + 1 < len(parts) else ""
        segments.append((seg_text, seg_marker))
        i += 2
    kept: list[str] = []
    dropped = 0
    # I-wire-017 (#1339) FIX B: when a prose segment is dropped as chrome, the SAME claim's trailing
    # continuation citation markers ("prose[6][7][5]" splits into a prose seg + two marker-only segs)
    # would otherwise survive orphaned. Track the drop and suppress the contiguous marker-only run
    # that immediately follows it. A marker-only run after a KEPT segment stays (it belongs to that
    # kept claim). Withhold-only — the dropped markers' evidence is untouched.
    suppress_trailing_markers = False
    for seg_text, seg_marker in segments:
        if not seg_text.strip() and not seg_marker:
            continue
        # A marker-only continuation segment (no prose, just "[N]") inherits the fate of the prose
        # segment it continues: dropped if that prose segment was dropped, kept otherwise.
        if not seg_text.strip():
            if suppress_trailing_markers:
                dropped += 1
                continue
            kept.append(seg_text + seg_marker)
            continue
        core = _unit_core_for_screen(seg_text)
        if core and is_render_chrome_or_unrenderable(core, known_words=known_words):
            repaired = _repair_glued_inline_header(seg_text, known_words)
            if repaired is not None:
                # Real-prose prefix kept WITH its citation marker (the kept finding stays cited);
                # only the glued-header remainder is excised. The prose survives, so its trailing
                # continuation markers are NOT orphaned — keep them.
                kept.append(repaired + seg_marker)
                dropped += 1
                suppress_trailing_markers = False
                continue
            dropped += 1
            suppress_trailing_markers = True  # orphan this dropped claim's continuation markers
            continue  # whole chrome unit + its marker dropped
        kept.append(seg_text + seg_marker)
        suppress_trailing_markers = False
    # I-deepfix-001 H1 (#1344): REPAIR-first strip of leaked source-internal in-text ref markers
    # ("(1, 2)") on the kept prose. No-op (byte-identical) when the kill-switch is OFF or the line
    # carries no such marker; never touches the report's OWN ``[N]`` / ``[#ev:...]`` square-bracket
    # markers (they are seg_marker parts, and the rule matches PARENTHESES only). Faithfulness-neutral.
    return strip_source_internal_refs("".join(kept)), dropped


def _is_scaffolding_section_title(title: str) -> bool:
    """True iff a header title names a pipeline SCAFFOLDING section (excluded from sanitization)."""
    low = title.strip().lower().lstrip("# ").strip()
    return any(low.startswith(s) for s in _SCAFFOLDING_SECTION_TITLES)


def _line_has_claim_prose(line: str) -> bool:
    """True iff ``line`` carries claim-bearing prose (not just blanks or bare ``[N]`` /
    ``[#ev:...]`` citation markers). Strips leading bullet / ``**bold**`` markers and ALL citation
    markers, then checks any real alphabetic content remains. I-wire-017 (#1339) FIX C1 helper: used
    to decide whether a sanitized section body has collapsed to orphaned markers only. PURE."""
    text_only = "".join(_CITATION_SPLIT_RE.split(line)[::2])  # even indices = non-marker text
    return bool(_unit_core_for_screen(text_only).strip())


def _immediate_parent_is_scaffolding(level: int, header_stack: "list[tuple[int, bool]]") -> bool:
    """True iff the NEAREST strictly-shallower open header (the immediate markdown parent) is a
    scaffolding header — e.g. ``### references`` whose parent is ``## Bibliography``. A non-scaffolding
    header at an intermediate depth BREAKS the chain (it becomes the new parent), so a content section
    under a non-scaffolding parent is NOT protected even if a far ancestor is the report's scaffolding
    ``# Research Report:`` title. ``header_stack`` holds ``(level, is_scaffolding)`` for the open
    ancestor headers, shallowest-first. PURE."""
    for anc_level, anc_scaffolding in reversed(header_stack):
        if anc_level < level:
            return anc_scaffolding
    return False


def _drop_empty_claim_sections(lines: "list[str]") -> "tuple[list[str], int]":
    """I-wire-017 (#1339) FIX C1 post-pass: drop a non-scaffolding ``###``-or-deeper section header
    whose body — after the line-level sanitization already ran — has NO claim-bearing prose left
    (only blank lines / bare orphaned citation markers). Such a section renders as a dangling header
    over "[6][7][5]"; withholding the empty header is suppress-only (the evidence is untouched).

    A SCAFFOLDING header — by its own title OR by having a scaffolding IMMEDIATE parent
    (``### references`` under ``## Bibliography``) — is always preserved. Any top-level (``#``/``##``)
    header is also preserved (a top-level empty section is left for the operator). Returns
    ``(kept_lines, headers_dropped)``. PURE."""
    kept: list[str] = []
    headers_dropped = 0
    # Open ancestor headers as (level, is_scaffolding), shallowest-first; a header at depth d closes
    # every open ancestor at depth >= d before it is pushed.
    header_stack: list[tuple[int, bool]] = []
    i = 0
    n = len(lines)
    while i < n:
        header = _SECTION_HEADER_RE.match(lines[i])
        if not header:
            kept.append(lines[i])
            i += 1
            continue
        level = len(header.group(1))
        title = header.group(2)
        parent_scaffolding = _immediate_parent_is_scaffolding(level, header_stack)
        header_stack = [hs for hs in header_stack if hs[0] < level]
        own_scaffolding = _is_scaffolding_section_title(title)
        header_stack.append((level, own_scaffolding))
        if (
            level < _MIN_DROPPABLE_EMPTY_HEADER_LEVEL
            or own_scaffolding
            or parent_scaffolding
        ):
            kept.append(lines[i])
            i += 1
            continue
        # Collect this section's body up to (not including) the next header of ANY level.
        body_start = i + 1
        j = body_start
        while j < n and not _SECTION_HEADER_RE.match(lines[j]):
            j += 1
        body = lines[body_start:j]
        if any(_line_has_claim_prose(b) for b in body):
            kept.extend(lines[i:j])  # real content survives -> keep header + body verbatim
        else:
            headers_dropped += 1  # empty content section -> drop header + its marker-only body
        i = j
    return kept, headers_dropped


def sanitize_rendered_report(
    report_md: str, known_words: "set[str] | frozenset[str] | None" = None
) -> "tuple[str, int]":
    """THE render-seam chokepoint (I-wire-013 #1327). Run ONE sanitization pass over every
    claim-bearing unit of the assembled ``report_md``, dropping/repairing chrome + truncated units
    with the unblinded ``is_render_chrome_or_unrenderable`` predicate. Returns
    ``(clean_report_md, units_removed)``.

    Scaffolding sections (Bibliography / Methods / disclosures / Reliability / Source corroboration /
    the H1 question echo) are byte-preserved. A glued-chrome HEADER line ("## Dennis Zami …" welded
    onto a title) is dropped; a clean section header is preserved. Default-ON kill-switch
    ``PG_RENDER_SEAM_SANITIZE``; faithfulness-neutral (suppress-only). PURE."""
    if not report_md or not render_seam_sanitize_enabled():
        return report_md, 0
    out_lines: list[str] = []
    removed = 0
    in_scaffolding = False
    # I-deepfix-001 B6(a): tracked SEPARATELY from in_scaffolding. The corroboration section is
    # scaffolding (byte-preserved DOIs/URLs) EXCEPT its per-claim HEADER bullets, which carry a
    # claim string that can be page-furniture chrome. When in_corroboration is set and the B6(a)
    # screen is enabled, header bullets are screened; sub-bullets stay byte-preserved (KEEP-ONLY).
    in_corroboration = False
    corroboration_screen = corroboration_sanitize_enabled()
    # I-deepfix-001 H2 (#1344): tracked separately — inside the flat/residual "Corroborated Weighted
    # Findings" enrichment section, split the glued single-paragraph body into one bullet per finding.
    in_enrichment = False
    cwf_split = cwf_split_findings_enabled()
    for line in report_md.split("\n"):
        header = _SECTION_HEADER_RE.match(line)
        if header:
            title = header.group(2)
            in_scaffolding = _is_scaffolding_section_title(title)
            in_corroboration = _is_corroboration_section_title(title)
            in_enrichment = _is_enrichment_section_title(title)
            # Screen a glued-chrome header by its TITLE (post-``#`` strip), but never a clean /
            # scaffolding header — dropping a real header would orphan its body. Gated by
            # ``render_chrome_screen_enabled()`` so this header path honours the same
            # ``PG_RENDER_CHROME_SCREEN=0`` kill-switch as ``is_render_chrome_or_unrenderable``
            # (Codex P1 iter 1: the direct ``_contains_forensic_chrome`` call otherwise bypassed it).
            if (
                not in_scaffolding
                and render_chrome_screen_enabled()
                and _contains_forensic_chrome(title)
            ):
                removed += 1
                continue
            out_lines.append(line)
            continue
        if in_corroboration and corroboration_screen and line.strip():
            # B6(a): inside the corroboration rollup, screen ONLY the per-claim HEADER bullet's
            # claim string (sub-bullets / blanks pass through untouched via the (line, 0) branch).
            clean_line, suppressed = _sanitize_corroboration_header(line, known_words)
            removed += suppressed
            out_lines.append(clean_line)
            continue
        if in_scaffolding or not line.strip():
            out_lines.append(line)
            continue
        if in_enrichment and cwf_split:
            # H2: de-blob the enrichment section — split the glued ``sentence.[N] sentence.[N] ...``
            # paragraph into one bullet per finding, each sanitized through the SAME per-line screen
            # and keeping ONLY its own trailing ``[N]`` marker. Faithfulness-neutral render reflow.
            bullet_lines, dropped = _split_enrichment_blob_line(line, known_words)
            removed += dropped
            out_lines.extend(bullet_lines)
            continue
        clean_line, dropped = _sanitize_report_line(line, known_words)
        removed += dropped
        if clean_line.strip() or not dropped:
            out_lines.append(clean_line)
        # else: the line reduced entirely to chrome -> drop the now-empty line.
    # I-deepfix-001 (drb_72) FIX-D belt: after the line-level pass, drop any surviving bullet that is
    # ONLY a list marker and/or orphan citation markers ("- ", "- [12]") — it carries no claim. A real
    # bibliography line ("1. Title") never matches (it is not a ``-``/``*`` bullet). SUPPRESS-ONLY.
    _empty_bullet_drop = empty_bullet_drop_enabled()
    if _empty_bullet_drop:
        _kept: list[str] = []
        _emptied = 0
        for _l in out_lines:
            if _EMPTY_BULLET_RE.match(_l):
                _emptied += 1
                continue
            _kept.append(_l)
        if _emptied:
            out_lines = _kept
            removed += _emptied
        logger.info("[activation] empty_bullet_drop: dropped=%d", _emptied)
    # I-wire-017 (#1339) FIX C1: after the line-level pass, drop any non-scaffolding ###-or-deeper
    # section whose body collapsed to no claim-bearing prose (blank / bare-marker only).
    out_lines, empty_headers_dropped = _drop_empty_claim_sections(out_lines)
    removed += empty_headers_dropped
    return "\n".join(out_lines), removed


def _make_junk_screen() -> Any:
    """Return THE shared render-side chrome+truncation predicate (I-wire-012 #1326).

    Historically this returned a bespoke closure (boilerplate + web-chrome + CAPTCHA).
    It now returns ``is_render_chrome_or_unrenderable`` so every consumer of this hub
    (``verified_compose._compose_junk_screen``, this module's own
    ``_substantive_units`` / ``build_verified_span_draft``) screens through the ONE
    predicate. The base screen still ALWAYS runs (so flag-OFF is byte-identical for
    these consumers); the new chrome categories are added when
    ``PG_RENDER_CHROME_SCREEN`` is ON (default)."""
    return is_render_chrome_or_unrenderable


def _emit_unit(unit: str, eids: Any) -> str:
    """Render one verbatim unit with its ``[ev_id]`` marker(s) INSIDE the sentence.

    Strips trailing terminal punctuation then appends ``[eid]`` for each evidence_id
    (I-beatboth-011 #7 multi-citation: a same-work group emits ALL its grounding
    co-citation markers on the one unit) followed by ``.`` so every marker sits INSIDE
    the sentence unit and survives strict_verify's re-split (see ``_TERMINAL_PUNCT``).
    Accepts a single id (str) or an ordered list of ids; the order is preserved
    (representative first) and is deterministic.
    """
    if isinstance(eids, str):
        ids = [eids]
    else:
        ids = [str(e) for e in (eids or []) if str(e)]
    core = unit.rstrip()
    while core and core[-1] in _TERMINAL_PUNCT:
        core = core[:-1].rstrip()
    marker_str = "".join(f" [{eid}]" for eid in ids)
    return f"{core}{marker_str}."


def _substantive_units(direct_quote: str, *, is_junk: Any) -> list[str]:
    """The source's verbatim sentence-units that are citable claims, longest-first.

    Splits with the SAME ``split_into_sentences`` strict_verify re-splits with, so
    each emitted unit is one gate unit. Keeps a unit only if it clears
    ``_MIN_UNIT_CHARS``, carries a real letter, is NOT boilerplate/chrome per the
    shared ``is_junk`` screen, and carries no ``[...]`` (which would be mis-read as a
    marker). Ordered longest-first so the per-source budget keeps the most
    content-bearing sentences (most likely the real finding).
    """
    from src.polaris_graph.generator.provenance_generator import (  # noqa: PLC0415
        split_into_sentences,
    )

    max_chars = max_unit_chars()
    units: list[str] = []
    for raw_unit in split_into_sentences(direct_quote) or []:
        # I-beatboth-011 #4 (#1289): strip C0 control bytes (incl. a literal NUL) from
        # the unit BEFORE any length/screen check so a control byte can never reach the
        # render and the bound measures clean printable chars.
        unit = _strip_control_bytes(raw_unit or "").strip()
        if len(unit) < _MIN_UNIT_CHARS:
            continue
        # I-beatboth-011 #4 (#1289): a unit longer than the render bound is structurally
        # a fetch-shell / raw-extraction blob (the 75K equation dump), never a clinical
        # sentence — DROP it. NOT a breadth cap (source count uncapped); NOT a verify
        # gate (strict_verify untouched). A real long quote is sentence-split upstream.
        if len(unit) > max_chars:
            continue
        if not any(ch.isalpha() for ch in unit):
            continue
        # `[...]`-shaped substrings inside a quote would be mis-read as markers
        # by _rewrite_draft_with_spans; a unit carrying one is skipped (rare; keeps
        # the marker contract unambiguous rather than risk a false token bind).
        if "[" in unit and "]" in unit:
            continue
        if is_junk(unit):
            continue
        units.append(unit)
    units.sort(key=len, reverse=True)
    return units


# I-beatboth-011 #7 (#1289) — SAME-WORK CONSOLIDATION identity (§-1.3 CONSOLIDATE-
# DON'T-DROP). Two unbound SUPPORTS members are the SAME WORK when they share a
# normalized DOI, else a folded title PLUS a corroborating discriminator. KEEP ALL
# their URLs as corroborating locators of the ONE work, but COUNT/PRESENT them as ONE
# source (multi-URL corroboration), never N independent sources. Identity ladder
# mirrors the existing ``_m51_canonical_identity`` convention (evidence_selector.py:
# 2781): DOI first, else title(+discriminator), else (fallback) the evidence_id itself
# so a member with neither stays its own distinct unit (never wrongly merged).
#
# I-beatboth-011 #4 (#1289) — P1 OVER-MERGE FIX (§-1.3: NEVER merge distinct works;
# under-merge is safe, over-merge corrupts breadth/attribution). The no-DOI branch
# MUST NOT merge on folded TITLE ALONE — two genuinely DIFFERENT works can share a
# normalized title and would be wrongly collapsed, losing distinct corroborators. So
# the no-DOI key requires the folded title PLUS the FIRST PRESENT corroborating
# discriminator the records share, in this fixed priority order: publication YEAR →
# first-author SURNAME → VENUE/journal → URL HOST. A priority-ordered composite (NOT
# pairwise OR / union-find, which is non-transitive and over-merges through chains) is
# a plain equality key, biased to UNDER-merge. Title-with-no-discriminator stays its
# own ev-id singleton (distinct). This key computation is the SHARED canonical contract
# with ``synthesis/finding_dedup.py`` and is duplicated BYTE-FOR-BYTE there (the
# no-new-source-file rule forbids a shared module).
_DOI_PREFIX_RE = re.compile(r"^\s*(?:doi\s*:?\s*|https?://(?:dx\.)?doi\.org/)", re.IGNORECASE)
_TITLE_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")
_WHITESPACE_RUN_RE = re.compile(r"\s+")
# Publication-year validity bounds (SHARED with the selector's _row_year convention
# at evidence_selector.py:769-770 and finding_dedup._row_year). Outside => absent.
_MIN_YEAR = 1900
_MAX_YEAR = 2100


def _normalize_doi(raw: Any) -> str:
    """Normalized DOI for same-work grouping ('' when absent/unusable).

    SHARED contract with ``finding_dedup._normalize_doi``: strip a leading
    ``doi:`` / ``https://doi.org/`` / ``http://dx.doi.org/`` prefix, lowercase,
    ``rstrip("/")``; a USABLE DOI starts with the ``10.`` registrant prefix.
    """
    doi = str(raw or "").strip()
    if not doi:
        return ""
    doi = _DOI_PREFIX_RE.sub("", doi).strip().lower().rstrip("/")
    # A usable DOI starts with the ``10.`` registrant prefix; anything else is noise.
    return doi if doi.startswith("10.") else ""


def _normalize_title(raw: Any) -> str:
    """Normalized title key for same-work grouping ('' when too short to be safe).

    SHARED with ``finding_dedup._fold_title``: lowercase, collapse non-alphanumeric
    runs to a single space, strip; require >= 12 chars (a tiny/generic title is an
    over-merge risk).
    """
    title = str(raw or "").strip().lower()
    title = _TITLE_NORMALIZE_RE.sub(" ", title).strip()
    # Guard against an over-merge on a tiny/generic title: require real substance.
    return title if len(title) >= 12 else ""


def _record_title(ev: dict[str, Any]) -> str:
    """The record's title across the schema aliases (``source_title`` is canonical;
    ``title`` / ``page_title`` / ``name`` are the validator-mapped variants).

    SHARED precedence with ``finding_dedup._row_title`` so the two consolidators
    fold the SAME title field.
    """
    for key in ("source_title", "title", "page_title", "name"):
        value = ev.get(key)
        if value:
            return str(value)
    return ""


def _record_year(ev: dict[str, Any]) -> str:
    """Publication year as a discriminator token ('' when absent/invalid).

    Reads ``ev['year']`` else ``ev['metadata']['year']`` and validates [1900, 2100]
    — the SHARED convention with the selector's ``_row_year`` (evidence_selector.py:
    793-809) and ``finding_dedup._row_year``.
    """
    val = ev.get("year")
    if val is None:
        meta = ev.get("metadata")
        if isinstance(meta, dict):
            val = meta.get("year")
    if val is None:
        return ""
    try:
        year = int(val)
    except (TypeError, ValueError):
        return ""
    return str(year) if _MIN_YEAR <= year <= _MAX_YEAR else ""


def _first_author_surname(ev: dict[str, Any]) -> str:
    """First-author surname (folded) as a discriminator token ('' when absent).

    Records carry ``authors`` (a list, family-name-first, e.g. ``["Autor D", ...]``)
    or a singular ``author`` string. The surname is the FIRST whitespace token of the
    first author, lowercased + non-alphanumerics stripped. SHARED with
    ``finding_dedup._first_author_surname``.
    """
    raw = ev.get("authors")
    first = ""
    if isinstance(raw, (list, tuple)):
        for entry in raw:
            if entry and str(entry).strip():
                first = str(entry).strip()
                break
    elif raw:
        first = str(raw).strip()
    if not first:
        single = ev.get("author")
        if single and str(single).strip():
            first = str(single).strip()
    if not first:
        return ""
    surname = first.split()[0] if first.split() else ""
    surname = _TITLE_NORMALIZE_RE.sub("", surname.lower())
    return surname


def _record_venue(ev: dict[str, Any]) -> str:
    """Venue/journal (folded) as a discriminator token ('' when absent).

    Reads ``venue`` else ``journal``, lowercased with non-alphanumeric runs
    collapsed to a single space and trimmed. SHARED with ``finding_dedup._row_venue``.
    """
    raw = ev.get("venue") or ev.get("journal") or ""
    text = str(raw).strip().lower()
    if not text:
        return ""
    text = _TITLE_NORMALIZE_RE.sub(" ", text)
    return _WHITESPACE_RUN_RE.sub(" ", text).strip()


def _record_host(ev: dict[str, Any]) -> str:
    """URL host (no leading ``www.``) as the WEAKEST discriminator token.

    Same-work fetches usually span DIFFERENT hosts, so host merges almost nothing —
    it is last in the priority order purely as a safety net. SHARED with
    ``finding_dedup._row_host`` (which delegates to ``_host_of``); the host reduction
    here is inlined (no urllib import already present) but produces the SAME token.
    """
    from urllib.parse import urlparse  # noqa: PLC0415

    url = str(ev.get("source_url", "") or ev.get("url", "") or "")
    if not url:
        return ""
    host = (urlparse(url).hostname or "").lower().strip()
    if host.startswith("www."):
        host = host[4:]
    return host


def _title_discriminator(ev: dict[str, Any]) -> str:
    """The STRICT corroborating discriminator for the no-DOI title branch.

    I-beatboth-011 #4 P2 hardening (#1289): the no-DOI key MUST be strong enough that
    two DISTINCT works sharing a title cannot merge on a single weak signal. A single
    weak signal alone (year-only or host-only) is NOT enough. The token requires the
    folded title PLUS either:
      * a STRONG discriminator (first-author surname and/or venue) — every present
        STRONG/year signal is folded in (year → author → venue, fixed order), so a
        differing year OR differing author OR differing venue yields a DIFFERENT token
        and the two works do NOT merge; OR
      * two INDEPENDENT WEAK signals (year AND host) when no strong signal is present.

    HOST IS ENABLING-ONLY, NEVER BLOCKING. Same-work members are the same work fetched
    at DIFFERENT URLs, so they (almost) always differ on host (the ``_record_host``
    safety-net premise + §-1.3). Host therefore appears ONLY as the SECOND weak signal
    alongside year, and NEVER in the strong-path token — otherwise every legitimate
    same-work merge (which spans different hosts) would be blocked.

    Returns '' when neither a strong signal nor (year AND host) is present, so the record
    stays a title-only singleton and is never merged on title alone. SHARED contract with
    ``finding_dedup._title_discriminator`` (byte-identical key string).
    """
    year = _record_year(ev)
    surname = _first_author_surname(ev)
    venue = _record_venue(ev)
    host = _record_host(ev)
    if surname or venue:
        parts: list[str] = []
        if year:
            parts.append("y:" + year)
        if surname:
            parts.append("a:" + surname)
        if venue:
            parts.append("v:" + venue)
        return "|".join(parts)
    if year and host:
        return "y:" + year + "|h:" + host
    return ""


def _work_identity(eid: str, ev: dict[str, Any]) -> str:
    """Same-work group key for one member: DOI, else title(+discriminator), else its
    own ev_id.

    I-beatboth-011 #4 (#1289): the no-DOI branch NEVER merges on folded title ALONE
    (two different works can share a title). It requires the folded title AND the
    FIRST present discriminator (year → first-author surname → venue → host).
    Title-with-no-discriminator falls through to the evidence_id (never a constant),
    so a member with neither a DOI nor (usable title + discriminator) stays its OWN
    distinct unit — consolidation can only MERGE genuine same-work duplicates, never
    collapse unrelated works. Matches ``finding_dedup._same_work_key``.
    """
    doi = _normalize_doi(ev.get("doi"))
    if doi:
        return f"doi:{doi}"
    title = _normalize_title(_record_title(ev))
    if title:
        discriminator = _title_discriminator(ev)
        if discriminator:
            return f"title:{title}|{discriminator}"
    return f"ev:{eid}"


def _member_quote(ev: dict[str, Any]) -> str:
    """The member's render-safe direct quote (control bytes stripped)."""
    raw = (ev.get("direct_quote") or ev.get("statement") or "")
    return _strip_control_bytes(str(raw)).strip()


def build_verified_span_draft(
    ev_ids: Any, evidence_pool: Any, *, research_question: str = ""
) -> str:
    """Deterministic verbatim-span draft for the enrichment section (FIX K).

    Emits, in the caller's relevance/weight order, up to ``spans_per_source()`` of each
    WORK's own verbatim sentence-units, each with its legacy ``[ev_id]`` marker placed
    INSIDE the sentence, so ``_rewrite_draft_with_spans`` binds each unit to its best
    in-quote span and ``strict_verify`` validates it.

    I-beatboth-011 #4 (#1289) — RENDER SAFETY: every emitted span is control-byte
    sanitized (NO NUL / C0 bytes ever reach the report) and a unit exceeding the render
    char bound (a 75K raw-extraction blob) is dropped. A CAPTCHA / Cloudflare security
    stub member is dropped by the junk screen.

    I-beatboth-011 #7 (#1289) — SAME-WORK CONSOLIDATION (§-1.3 CONSOLIDATE-DON'T-DROP):
    members that are the SAME WORK (same normalized DOI, else title) are grouped into
    ONE multi-citation unit-set — counted/presented as ONE source — instead of N. ALL
    the work's URLs are KEPT as corroborating locators: a corroborator's ``[ev_id]``
    marker is attached to a unit ONLY when that corroborator's OWN quote actually
    contains the emitted unit, so every emitted marker is span-grounded by construction
    (this NEVER changes which members verify — the representative would verify alone;
    corroborators only ADD already-grounding co-citations). A truncated-intro duplicate
    of the representative contributes its URL as a corroborator, not a separate source.

    A source whose quote is boilerplate/chrome/CAPTCHA, pool-absent, or has no
    substantive unit contributes nothing. Returns the joined draft ("" => caller renders
    the existing gap stub, never a silent success). NO LLM, NO faithfulness-gate touch.
    """
    pool = evidence_pool or {}
    is_junk = _make_junk_screen()
    budget = spans_per_source()
    # I-deepfix-001 (#1344 SPAN-TOPICALITY): precision-safe per-span off-topic WITHHOLD
    # inputs (empty question OR flag OFF => empty term set => no span ever withheld =>
    # byte-identical). §-1.3 WITHHOLD-and-disclose per span; the source stays in the pool.
    span_question_terms = (
        _question_topic_terms(research_question)
        if offtopic_span_suppress_enabled()
        else frozenset()
    )
    span_min_content_words = _offtopic_span_min_content_words()
    span_min_local_terms = _offtopic_span_min_local_terms()
    # Corpus-wide on-topic vocabulary, computed ONCE (Codex-P1 iter-2 answer): the per-span
    # off-topic gate KEEPS any span sharing vocabulary with the whole corpus, so lower-level /
    # synonym / acronym on-topic spans are retained; only spans foreign to the ENTIRE corpus
    # are withheld. Empty when the gate is disabled (byte-identical no-op).
    span_corpus_terms = _corpus_topic_terms(pool) if span_question_terms else set()

    # Group ev_ids into same-work buckets, PRESERVING the caller's relevance/weight
    # order: a work's bucket is keyed by its FIRST-seen member, so the highest-ordered
    # member of each work is the representative and the bucket order is the work order.
    work_order: list[str] = []
    work_members: dict[str, list[str]] = {}
    for ev_id in (ev_ids or []):
        eid = str(ev_id or "")
        if not eid:
            continue
        ev = pool.get(eid)
        if not isinstance(ev, dict):
            continue
        direct_quote = _member_quote(ev)
        # Drop CAPTCHA stubs / boilerplate at the WHOLE-member level up front.
        if not direct_quote or is_junk(direct_quote):
            continue
        key = _work_identity(eid, ev)
        if key not in work_members:
            work_members[key] = []
            work_order.append(key)
        work_members[key].append(eid)

    parts: list[str] = []
    for key in work_order:
        member_eids = work_members[key]
        representative = member_eids[0]
        rep_ev = pool.get(representative)
        if not isinstance(rep_ev, dict):
            continue
        rep_quote = _member_quote(rep_ev)
        units = _substantive_units(rep_quote, is_junk=is_junk)
        # I-deepfix-001 (#1344 SPAN-TOPICALITY): WITHHOLD confidently-foreign spans of an
        # otherwise-on-topic source from citation (fail-open; source never dropped).
        units = _withhold_offtopic_spans(
            units, rep_ev, span_question_terms,
            span_min_content_words, span_min_local_terms,
            corpus_topic_terms=span_corpus_terms,
        )
        if not units:
            continue
        # Pre-compute each corroborator's sanitized quote ONCE for the contains-check.
        corroborator_quotes = [
            (m, _member_quote(pool[m]))
            for m in member_eids[1:]
            if isinstance(pool.get(m), dict)
        ]
        for unit in units[:budget]:
            # The representative ALWAYS grounds (its own quote contains the unit). Attach
            # a corroborator marker ONLY when that corroborator's own quote also contains
            # the unit — so every emitted marker is span-grounded and no member's verify
            # status changes. ALL same-work members retain their URL as a co-locator;
            # those whose fetch differs simply do not add a (would-fail) marker.
            markers = [representative]
            for m_eid, m_quote in corroborator_quotes:
                if unit in m_quote and m_eid not in markers:
                    markers.append(m_eid)
            parts.append(_emit_unit(unit, markers))
    return " ".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# I-deepfix-001 WS-3 (#1344) — NUMBERED "Evidence base" breadth surface.
#
# THE LEAK (drb_72 "12 of 88 cited"): the FULL ordered unbound-SUPPORTS surface from
# ``select_unbound_supports_by_weight`` is already UNCAPPED (weighted_enrichment.py:295,469,573),
# but nothing RENDERS it as a numbered reference block, so most span-verified sources never
# receive a ``[N]`` citation. This surfaces EVERY source that carries a surviving isolated-
# ``SUPPORTS`` span into ONE numbered "Evidence base" section: one numbered entry per distinct
# WORK (same-work CONSOLIDATION, §-1.3 — never N entries for one work), each entry = that work's
# OWN verbatim span unit(s) tagged with its ``[ev_id]`` marker(s) so the downstream bibliography
# numberer assigns each a real ``[N]``.
#
# §-1.3 — WEIGHT-and-CONSOLIDATE, never FILTER-and-CAP: this is SURFACING breadth (keep-all), NOT a
# cap / floor / thinner. The input ``ev_ids`` is already the uncapped ordered surface; this ONLY
# renders it. Faithfulness is UNTOUCHED — each emitted unit is a verbatim span carrying a legacy
# ``[ev_id]`` marker that flows through the UNCHANGED ``_rewrite_draft_with_spans`` -> ``strict_verify``
# exactly like every other section; a unit that cannot ground is dropped by that gate, never padded.
# The SAME render-safety screens as ``build_verified_span_draft`` apply (control-byte strip, junk
# screen, per-unit char bound, same-work consolidation). Default-ON;
# ``PG_BREADTH_EVIDENCE_BASE_SECTION=0`` => returns "" => no section => byte-identical legacy output.
_ENV_EVIDENCE_BASE_SECTION = "PG_BREADTH_EVIDENCE_BASE_SECTION"
_EVIDENCE_BASE_TITLE = "Evidence base"


def evidence_base_section_enabled() -> bool:
    """Kill-switch ``PG_BREADTH_EVIDENCE_BASE_SECTION`` (default ON). OFF => the numbered
    Evidence base section is not rendered (``build_evidence_base_section`` returns "") =>
    byte-identical legacy output."""
    return os.environ.get(_ENV_EVIDENCE_BASE_SECTION, "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


def build_evidence_base_section(
    ev_ids: Any,
    evidence_pool: Any,
    *,
    start_index: int = 1,
    research_question: str = "",
) -> str:
    """Render the FULL ordered unbound-SUPPORTS surface as ONE numbered "Evidence base" markdown
    section so EVERY source with a surviving span gets a ``[N]`` citation.

    ``ev_ids`` is the ordered surface from ``select_unbound_supports_by_weight`` (already uncapped —
    NO cap / floor / thinner is applied here). Members are CONSOLIDATED into same-work buckets
    (§-1.3 keep-all-count-once): one numbered entry per distinct work, in the caller's
    relevance/weight order, each carrying its verbatim span unit(s) + the ``[ev_id]`` marker(s) the
    downstream span-binder + ``strict_verify`` re-check.

    Returns "" when the flag is OFF, ``ev_ids`` is empty, or no surfaced source yields a substantive
    verbatim unit (caller renders nothing — byte-identical). NO LLM; NO faithfulness-gate touch.
    """
    if not evidence_base_section_enabled():
        return ""
    ev_ids = list(ev_ids or [])
    if not ev_ids:
        return ""
    pool = evidence_pool or {}
    is_junk = _make_junk_screen()
    budget = spans_per_source()
    # I-deepfix-001 (#1344 SPAN-TOPICALITY): precision-safe per-span off-topic WITHHOLD
    # inputs (empty question OR flag OFF => empty term set => no span ever withheld).
    span_question_terms = (
        _question_topic_terms(research_question)
        if offtopic_span_suppress_enabled()
        else frozenset()
    )
    span_min_content_words = _offtopic_span_min_content_words()
    span_min_local_terms = _offtopic_span_min_local_terms()
    # Corpus-wide on-topic vocabulary, computed ONCE (Codex-P1 iter-2 answer): the per-span
    # off-topic gate KEEPS any span sharing vocabulary with the whole corpus, so lower-level /
    # synonym / acronym on-topic spans are retained; only spans foreign to the ENTIRE corpus
    # are withheld. Empty when the gate is disabled (byte-identical no-op).
    span_corpus_terms = _corpus_topic_terms(pool) if span_question_terms else set()

    # Same-work grouping, PRESERVING the caller's relevance/weight order (mirrors
    # ``build_verified_span_draft``: a work's bucket is keyed by its FIRST-seen member so the
    # highest-ordered member of each work is the representative and bucket order is work order).
    work_order: list[str] = []
    work_members: dict[str, list[str]] = {}
    for ev_id in ev_ids:
        eid = str(ev_id or "")
        if not eid:
            continue
        ev = pool.get(eid)
        if not isinstance(ev, dict):
            continue
        direct_quote = _member_quote(ev)
        if not direct_quote or is_junk(direct_quote):
            continue
        key = _work_identity(eid, ev)
        if key not in work_members:
            work_members[key] = []
            work_order.append(key)
        work_members[key].append(eid)

    lines: list[str] = []
    number = start_index
    for key in work_order:
        member_eids = work_members[key]
        representative = member_eids[0]
        rep_ev = pool.get(representative)
        if not isinstance(rep_ev, dict):
            continue
        rep_quote = _member_quote(rep_ev)
        units = _substantive_units(rep_quote, is_junk=is_junk)
        # I-deepfix-001 (#1344 SPAN-TOPICALITY): WITHHOLD confidently-foreign spans of an
        # otherwise-on-topic source from the numbered breadth surface (fail-open).
        units = _withhold_offtopic_spans(
            units, rep_ev, span_question_terms,
            span_min_content_words, span_min_local_terms,
            corpus_topic_terms=span_corpus_terms,
        )
        if not units:
            continue
        # Pre-compute each corroborator's sanitized quote ONCE for the contains-check (same-work URLs
        # co-cite ONLY when their own fetch actually contains the emitted unit — span-grounded markers).
        corroborator_quotes = [
            (m, _member_quote(pool[m]))
            for m in member_eids[1:]
            if isinstance(pool.get(m), dict)
        ]
        emitted: list[str] = []
        for unit in units[:budget]:
            markers = [representative]
            for m_eid, m_quote in corroborator_quotes:
                if unit in m_quote and m_eid not in markers:
                    markers.append(m_eid)
            emitted.append(_emit_unit(unit, markers))
        if not emitted:
            continue
        lines.append(f"{number}. {' '.join(emitted)}")
        number += 1

    if not lines:
        return ""
    return f"## {_EVIDENCE_BASE_TITLE}\n\n" + "\n".join(lines)
