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

import os
import re
from collections import Counter
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
    # its topicality score for the relevance-first ordering.
    best_weight: dict[str, float] = {}
    relevance_by_eid: dict[str, float | None] = {}
    supports_members_seen = 0
    excluded_bound = 0
    excluded_pool_absent = 0
    below_floor_count = 0  # I-arch-011 (B18): KEPT-but-below-floor (telemetry); NEVER an exclusion.
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

    ev_ids = [
        eid
        for eid, _ in sorted(
            best_weight.items(),
            key=lambda kv: (
                _is_below_floor(kv[0]),                       # False (0) before True (1)
                -_relevance_sort_key(relevance_by_eid.get(kv[0])),
                -kv[1],
                kv[0],
            ),
        )
    ]

    # I-arch-011 (B18): the empty case can no longer be "all below floor" (the floor never
    # excludes). Report the TRUE reason: no SUPPORTS member at all, else everything bound/pool-absent.
    if ev_ids:
        reason = _REASON_OK
    elif supports_members_seen == 0:
        reason = _REASON_NO_SUPPORTS_MEMBERS
    else:
        reason = _REASON_ALL_BOUND_OR_ABSENT
    return UnboundSupportsSelection(
        ev_ids=ev_ids,
        reason=reason,
        baskets_seen=len(baskets),
        supports_members_seen=supports_members_seen,
        excluded_bound=excluded_bound,
        excluded_pool_absent=excluded_pool_absent,
        excluded_below_floor=below_floor_count,  # field name held stable; meaning = kept-below-floor
    )


def select_unbound_supports_by_weight(
    *,
    evidence_pool: Any,
    credibility_analysis: Any,
    contract_plans: Any,
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
    """True iff ``section`` is THIS module's weighted-enrichment section.

    Matches on the exact ``_ENRICHMENT_TITLE`` so the deterministic render is
    scoped to the one section this module builds — every contract / body section
    is byte-identical. Robust to a duck-typed plan (missing ``title`` => False).
    """
    return str(getattr(section, "title", "") or "") == _ENRICHMENT_TITLE


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
    r"|\bISSN\b\s*:?\s*\d"
    r"|\bCITATIONS\b\s+\d+\s+\bREADS\b\s+\d+"
    r"|\bMarkdown Content\s*:|\bURL Source\s*:|\bPublished Time\s*:"
    r"|\bNumber of Pages\s*:|\bCite this paper as\b"
    r"|#main-content|Twitter-intent|twitter\.com/intent"
    r"|same series\s*[-‐-―]\s*working paper"
    r"|\blisted\s+topics?\s+include\b",
    re.IGNORECASE,
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
    r"\bdoi:\s*10\.\d|\bissn\b\s*:?\s*\d|crossref reports the following articles citing|"
    r"volume title publisher|name:\s*\S+\.txt\b|file type:\s*text/",
    re.IGNORECASE,
)
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


def _is_new_chrome_category(text: str) -> bool:
    """The NEW I-wire-012 chrome categories (default-ON, high-precision) PLUS the I-wire-013 (#1327)
    CONTAINMENT forensic rules (a unit that CONTAINS glued page-furniture, not only IS junk)."""
    if _SHARED_RENDER_CHROME_RE.search(text):
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


def evaluate_render_chrome_canary(report_text: str) -> dict[str, Any]:
    """Compute the chrome-as-claim rate over the SHIPPED report's claim bullets and the
    canary verdict. PURE (no I/O). ``verdict='fail'`` ONLY in ``enforce`` mode when the
    rate exceeds the floor and there is at least one claim bullet — so the caller can
    flip the run status. In ``warn``/``off`` the verdict is always ``pass`` (telemetry
    only). Each chrome bullet is screened with the SAME shared predicate every composer
    uses (chrome + truncation), so the canary and the screens can never disagree."""
    bullets = _report_claim_bullets(report_text)
    chrome = [b for b in bullets if is_render_chrome_or_unrenderable(b)]
    total = len(bullets)
    n_chrome = len(chrome)
    rate = (n_chrome / total) if total else 0.0
    floor = render_chrome_canary_floor()
    mode = render_chrome_canary_mode()
    tripped = bool(total and mode == "enforce" and rate > floor)
    return {
        "mode": mode,
        "floor": floor,
        "total_claim_bullets": total,
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
_LEADING_BULLET_RE = re.compile(r"^\s*-\s+")
# I-wire-013 (#1327) iter-3b D-P1-1: split on BOTH the numeric ``[N]`` marker AND the provenance
# ``[#ev:<id>:<start>-<end>]`` token (single capture group, inner alternation — keeps the
# text/marker pairing in ``_sanitize_report_line`` intact) so the render seam covers per-citation
# units on provenance-cited reports too, not just numeric-cited ones. ``[^\]]*`` captures the whole
# ``[#ev:...]`` body up to its closing bracket. Reports with only ``[N]`` are byte-identical (the
# numeric alternative is unchanged).
_CITATION_SPLIT_RE = re.compile(r"(\[\d+\]|\[#ev:[^\]]*\])")
_INLINE_HEADER_SPLIT_RE = re.compile(r"#{1,6}\s+[A-Za-z]")


def render_seam_sanitize_enabled() -> bool:
    """True iff the default-ON render-seam chokepoint is active (LAW VI kill-switch
    ``PG_RENDER_SEAM_SANITIZE=0`` => byte-identical pass-through)."""
    return os.environ.get(_RENDER_SEAM_SANITIZE_ENV, "1").strip().lower() in (
        "1", "true", "on", "yes", "enabled",
    )


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
    for seg_text, seg_marker in segments:
        if not seg_text.strip() and not seg_marker:
            continue
        core = _unit_core_for_screen(seg_text)
        if core and is_render_chrome_or_unrenderable(core, known_words=known_words):
            repaired = _repair_glued_inline_header(seg_text, known_words)
            if repaired is not None:
                # Real-prose prefix kept WITH its citation marker (the kept finding stays cited);
                # only the glued-header remainder is excised.
                kept.append(repaired + seg_marker)
                dropped += 1
                continue
            dropped += 1
            continue  # whole chrome unit + its marker dropped
        kept.append(seg_text + seg_marker)
    return "".join(kept), dropped


def _is_scaffolding_section_title(title: str) -> bool:
    """True iff a header title names a pipeline SCAFFOLDING section (excluded from sanitization)."""
    low = title.strip().lower().lstrip("# ").strip()
    return any(low.startswith(s) for s in _SCAFFOLDING_SECTION_TITLES)


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
    for line in report_md.split("\n"):
        header = _SECTION_HEADER_RE.match(line)
        if header:
            title = header.group(2)
            in_scaffolding = _is_scaffolding_section_title(title)
            # Screen a glued-chrome header by its TITLE (post-``#`` strip), but never a clean /
            # scaffolding header — dropping a real header would orphan its body.
            if not in_scaffolding and _contains_forensic_chrome(title):
                removed += 1
                continue
            out_lines.append(line)
            continue
        if in_scaffolding or not line.strip():
            out_lines.append(line)
            continue
        clean_line, dropped = _sanitize_report_line(line, known_words)
        removed += dropped
        if clean_line.strip() or not dropped:
            out_lines.append(clean_line)
        # else: the line reduced entirely to chrome -> drop the now-empty line.
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


def build_verified_span_draft(ev_ids: Any, evidence_pool: Any) -> str:
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
