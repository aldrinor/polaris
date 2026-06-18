"""I-arch-007 ITEM 2 (#1264) — BREADTH: weighted unbound-SUPPORTS enrichment selection.

THE PROBLEM (the 485-in / ~13-cited collapse): the V30 contract render universe is the
5 required contract entities + a handful of LLM-planner enrichment picks. On a FULLY
SUCCESSFUL credibility pass that weighted + basketed hundreds of sources, the ~437 sources
that are NOT bound to a contract ``v30_entity_id`` are never *offered* to any section — a
purely STRUCTURAL funnel (it fires even when nothing times out). This module surfaces those
unbound-but-span-verified SUPPORTS sources into ONE extra legacy (field-agnostic) section so
they flow through the UNCHANGED ``_run_section`` -> ``strict_verify`` path.

§-1.3 DNA — WEIGHT-AND-CONSOLIDATE, never FILTER-AND-CAP:
  * WEIGHT + RELEVANCE-GATE, DON'T CAP: candidates are ORDERED by relevance-to-question THEN
    basket ``weight_mass`` (priority of consideration). There is NO cap / target / top-N — the
    FULL surviving list is offered. The ONE filter applied here is the EXISTING relevance GATE
    (``PG_RELEVANCE_FLOOR``, default 0.30): a member whose source row scores BELOW the floor is
    excluded. This is §-1.3's single relevance-axis carve-out — "off-topic is genuinely useless
    at any weight" (evidence_selector.py:2018-2024) — applied CONSISTENTLY to what the breadth
    section actively SURFACES, per the operator's no-off-topic-verified-but-peripheral requirement
    (#1264). It reuses the SAME floor + the SAME ``parse_relevance_floor`` fail-loud validation the
    retrieval gate uses; it is NOT a new arbitrary number, and it is NOT a breadth throttle.
  * CONSOLIDATE, DON'T DROP: the members come straight from the already-computed claim baskets
    (``ClaimBasket.supporting_members``) — the consolidated multi-source groups.
  * BASKET FAITHFULNESS: a member is offered ONLY if its OWN isolated ``span_verdict`` is
    ``"SUPPORTS"`` (computed by the credibility pass at credibility_pass.py:442-457). It is then
    re-verified against its own span by the section's UNCHANGED ``strict_verify``. Breadth
    EMERGES from how many survive that gate — it is never forced.

RECONCILIATION WITH RETRIEVAL P0-A6 (evidence_selector.py:2036-2065): the retrieval POOL still
WEIGHTS-not-FILTERS — under the default redesign a below-floor row is KEPT and down-weighted in the
pool, never hard-dropped (P0-A6 is UNTOUCHED). This relevance gate governs ONLY what the breadth
ENRICHMENT section actively SURFACES into the report; it is the operator's no-off-topic requirement
(#1264) applied at the surfacing boundary, not a re-introduction of the retrieval filter P0-A6 removed.

FAITHFULNESS-NEUTRALITY: this module only READS already-computed state and builds a candidate
``SectionPlan``. It moves NO strict_verify / NLI / 4-role D8 / span-grounding / section-floor /
sentinel threshold. The master flag defaults OFF (=> empty selection => byte-identical) and a
degraded pass (``credibility_analysis is None``) also yields an empty selection (byte-identical).
"""

from __future__ import annotations

import os
from typing import Any, NamedTuple

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


def breadth_enrichment_enabled() -> bool:
    """True iff the default-OFF master flag is explicitly enabled (LAW VI)."""
    return os.environ.get(_ENV_BREADTH_ENRICHMENT, "").strip().lower() in (
        "1", "true", "on", "yes",
    )


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


# I-arch-007 #1264 CHOKE-FIX (observability): the enrichment had FIVE independent silent-empty
# exits (credibility None / no baskets / no SUPPORTS members at all / every SUPPORTS member already
# bound or pool-absent / every remaining member below the relevance floor) and the call site logged
# ONLY the success branch. That is why the operator saw "zero appended weighted-enrichment section
# log lines in ALL reports" and could not tell WHICH gate killed it. Each reason below is a stable
# machine-readable token the call site logs LOUDLY so a no-op is never silent again.
_REASON_OK = "ok"
_REASON_CREDIBILITY_NONE = "credibility_analysis_none"  # degrade / flag-off path
_REASON_NO_BASKETS = "no_baskets"
_REASON_NO_SUPPORTS_MEMBERS = "no_supports_members"  # baskets exist but no SUPPORTS member at all
_REASON_ALL_BOUND_OR_ABSENT = "all_supports_bound_or_pool_absent"
_REASON_ALL_BELOW_FLOOR = "all_candidates_below_relevance_floor"


class UnboundSupportsSelection(NamedTuple):
    """The selection result + a diagnostic breakdown of WHY it is what it is.

    ``ev_ids`` is the FULL ordered surviving list (no cap). The counters make every empty-exit
    auditable: the call site logs ``reason`` LOUDLY so a degraded credibility pass or an
    all-below-floor pool can never silently no-op the breadth fix again. ALL counters are pure
    READS — nothing here touches a faithfulness gate.
    """
    ev_ids: list[str]
    reason: str
    baskets_seen: int
    supports_members_seen: int
    excluded_bound: int
    excluded_pool_absent: int
    excluded_below_floor: int


def diagnose_unbound_supports_selection(
    *,
    evidence_pool: Any,
    credibility_analysis: Any,
    contract_plans: Any,
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
    # its topicality score for the relevance gate + relevance-first ordering.
    best_weight: dict[str, float] = {}
    relevance_by_eid: dict[str, float | None] = {}
    supports_members_seen = 0
    excluded_bound = 0
    excluded_pool_absent = 0
    excluded_below_floor = 0
    for basket in baskets:
        try:
            weight = float(getattr(basket, "weight_mass", 0.0) or 0.0)
        except (TypeError, ValueError):
            weight = 0.0
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
            # RELEVANCE GATE (operator #1264): exclude a member whose source row is PRESENT-and-
            # below-floor. A missing/unparseable score FALLS BACK to keep (pool membership already
            # implies the retrieval floor passed) — never a SILENT exclusion. NOT finding_dedup's
            # ``or 0.0`` coercion, which would wrongly map missing->0.0->below-floor->excluded.
            relevance = _row_relevance(pool.get(eid))
            if relevance is not None and relevance < relevance_floor:
                excluded_below_floor += 1
                continue  # PRESENT-and-genuinely-off-topic => not surfaced
            if eid not in best_weight or weight > best_weight[eid]:
                best_weight[eid] = weight
            # First-seen relevance is deterministic across baskets (same row); keep it stable.
            relevance_by_eid.setdefault(eid, relevance)

    # ORDER: relevance-to-question DESC, then weight_mass DESC (priority of consideration), then
    # evidence_id for a deterministic tiebreak. A missing relevance uses a CONSTANT sentinel so a
    # pool of all-missing-relevance rows reproduces today's pure weight-desc order (the sentinel
    # ties on the relevance key, leaving the weight tiebreak in control). FULL list — no cap/top-N.
    ev_ids = [
        eid
        for eid, _ in sorted(
            best_weight.items(),
            key=lambda kv: (
                -_relevance_sort_key(relevance_by_eid.get(kv[0])),
                -kv[1],
                kv[0],
            ),
        )
    ]

    if ev_ids:
        reason = _REASON_OK
    elif supports_members_seen == 0:
        reason = _REASON_NO_SUPPORTS_MEMBERS
    elif excluded_below_floor > 0 and (excluded_bound + excluded_pool_absent) == 0:
        # Every survivor was relevance-gated out — distinct from "all already bound" so a uniformly
        # below-floor pool (e.g. a relevance-scale mismatch) is visible in the log, not silent.
        reason = _REASON_ALL_BELOW_FLOOR
    else:
        reason = _REASON_ALL_BOUND_OR_ABSENT
    return UnboundSupportsSelection(
        ev_ids=ev_ids,
        reason=reason,
        baskets_seen=len(baskets),
        supports_members_seen=supports_members_seen,
        excluded_bound=excluded_bound,
        excluded_pool_absent=excluded_pool_absent,
        excluded_below_floor=excluded_below_floor,
    )


def select_unbound_supports_by_weight(
    *,
    evidence_pool: Any,
    credibility_analysis: Any,
    contract_plans: Any,
) -> list[str]:
    """Ordered evidence_ids of unbound, isolated-verified, ON-TOPIC SUPPORTS basket members.

    Returns the FULL surviving list — NO cap, NO target, NO top-N. Ordering is
    relevance-to-question FIRST, then basket ``weight_mass`` (priority of consideration), then
    ``evidence_id`` (deterministic tiebreak). A member is included iff:
      * its own ``span_verdict == "SUPPORTS"`` (isolated per-member verification), AND
      * its ``evidence_id`` is NOT already bound to a contract section, AND
      * its ``evidence_id`` resolves in ``evidence_pool`` (so the section can cite a real span), AND
      * its source row passes the EXISTING relevance GATE — i.e. the row's ``selection_relevance``
        (the topicality score the retrieval gate stamps at evidence_selector.py:2128, read by
        finding_dedup at finding_dedup.py:212) is ``>= PG_RELEVANCE_FLOOR``. A row with NO usable
        relevance score FALLS BACK to today's behavior and is KEPT: pool membership already implies
        the retrieval relevance floor passed once, so a missing/unparseable sidecar must never
        SILENTLY EXCLUDE a member — only a row that is PRESENT-and-genuinely-below-floor is dropped.

    The floor + its fail-loud (0.0, 1.0] validation come from the SAME ``parse_relevance_floor`` the
    retrieval gate uses (no new constant). A garbage ``PG_RELEVANCE_FLOOR`` raises ``ValueError``.

    ``credibility_analysis is None`` (master flag OFF or always-release degrade) => ``[]`` =>
    byte-identical legacy render. Thin wrapper over ``diagnose_unbound_supports_selection`` so the
    list contract (and every existing test) is unchanged; the call site uses the diagnostic form to
    log WHY an empty selection happened.
    """
    return diagnose_unbound_supports_selection(
        evidence_pool=evidence_pool,
        credibility_analysis=credibility_analysis,
        contract_plans=contract_plans,
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


def is_enrichment_section(section: Any) -> bool:
    """True iff ``section`` is THIS module's weighted-enrichment section.

    Matches on the exact ``_ENRICHMENT_TITLE`` so the deterministic render is
    scoped to the one section this module builds — every contract / body section
    is byte-identical. Robust to a duck-typed plan (missing ``title`` => False).
    """
    return str(getattr(section, "title", "") or "") == _ENRICHMENT_TITLE


def _is_web_chrome(text: str) -> bool:
    """True iff ``text`` carries a sentence-form web-chrome / cookie-consent marker."""
    low = text.lower()
    return any(marker in low for marker in _WEB_CHROME_MARKERS)


def _make_junk_screen() -> Any:
    """Combined junk screen: the production boilerplate helper OR the K chrome list.

    ``is_boilerplate_or_nonassertional`` catches error-pages / non-assertional
    units; ``_is_web_chrome`` catches sentence-form consent/nav text it misses.
    Both are allowlist input-hygiene, never a verdict. Import-fails fall back to the
    chrome screen alone (never fail-open to nothing — the screen is load-bearing for
    self-quotes per the advisor's hard requirement).
    """
    try:
        from src.tools.access_bypass import (  # noqa: PLC0415
            is_boilerplate_or_nonassertional as _boiler,
        )
    except Exception:  # pragma: no cover - access_bypass import is stable in-tree
        return _is_web_chrome

    def _screen(text: str) -> bool:
        return bool(_boiler(text)) or _is_web_chrome(text)

    return _screen


def _emit_unit(unit: str, eid: str) -> str:
    """Render one verbatim unit with its ``[ev_id]`` marker INSIDE the sentence.

    Strips trailing terminal punctuation then appends ``[eid].`` so the marker
    survives strict_verify's re-split (see ``_TERMINAL_PUNCT``).
    """
    core = unit.rstrip()
    while core and core[-1] in _TERMINAL_PUNCT:
        core = core[:-1].rstrip()
    return f"{core} [{eid}]."


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

    units: list[str] = []
    for raw_unit in split_into_sentences(direct_quote) or []:
        unit = (raw_unit or "").strip()
        if len(unit) < _MIN_UNIT_CHARS:
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


def build_verified_span_draft(ev_ids: Any, evidence_pool: Any) -> str:
    """Deterministic verbatim-span draft for the enrichment section (FIX K).

    For each ev_id (in the caller's relevance/weight order), emit up to
    ``spans_per_source()`` of that source's own verbatim sentence-units, each with
    its legacy ``[ev_id]`` marker placed INSIDE the sentence, so
    ``_rewrite_draft_with_spans`` binds each unit to its best in-quote span and
    ``strict_verify`` validates it. A source whose quote is boilerplate/chrome /
    pool-absent / has no substantive unit contributes nothing. Returns the joined
    draft ("" => caller renders the existing gap stub, never a silent success). NO
    LLM, NO faithfulness-gate touch.
    """
    pool = evidence_pool or {}
    is_junk = _make_junk_screen()
    budget = spans_per_source()
    parts: list[str] = []
    for ev_id in (ev_ids or []):
        eid = str(ev_id or "")
        if not eid:
            continue
        ev = pool.get(eid)
        if not isinstance(ev, dict):
            continue
        direct_quote = (ev.get("direct_quote") or ev.get("statement") or "").strip()
        if not direct_quote or is_junk(direct_quote):
            continue
        units = _substantive_units(direct_quote, is_junk=is_junk)
        for unit in units[:budget]:
            parts.append(_emit_unit(unit, eid))
    return " ".join(parts)
