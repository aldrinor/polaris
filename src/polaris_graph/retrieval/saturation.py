"""Multi-round saturation search — I-meta-005 Phase 4 (#988). PURE decision logic.

Phase 4 closes gap #3 (search depth): the single-pass retrieval becomes a
GAP-TARGETED SATURATION LOOP. When the Phase-3 plan-sufficiency gate returns
EXPAND, this module decides whether to fire another retrieval round for ONLY the
under-covered sub-questions, re-gate, and stop on gap-closure OR
marginal-novelty < epsilon OR round/budget exhaustion -> a PARTIAL report (not a
blind abort).

KEY DESIGN (brief §2.1 / §2.2):
- Everything here is PURE / no-network / spend-free. The live retrieval round and
  the generator are INJECTED as callables by the sweep runner, so this orchestrator
  constructs NO HTTP client and bills NO generator token. The build + smoke drive
  the loop with STUB callables (capture-only, controlled per-round evidence).
- `marginal_novelty`: the fraction of a new round's rows that are NOVEL by
  canonical URL (the EXISTING `run_diff` canonicalizer over `source_url`), with
  intra-round duplicates collapsed.
- `gap_sub_queries`: the sub-query TEXTS to fire next, covering BOTH shortfall
  modes (empty-facet AND total-shortfall). NEVER empty when a section is
  under-covered (else the loop would have no query to fire).
- `saturation_decision`: a PRIORITY LADDER over {CONTINUE, STOP_SUFFICIENT,
  STOP_NOVELTY, STOP_BUDGET}. Budget is checked BEFORE novelty.

NO `if domain ==` / NO clinical literal on this path — the loop targets the
plan's under-covered sub-queries (field-agnostic), never a domain.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

# Reuse the EXISTING canonical-URL helper from run_diff (iter-2 P2). A thin
# PUBLIC wrapper avoids importing a private name across modules while keeping a
# single source of truth for canonicalization (lowercases host, strips www.,
# DROPS tracking params utm_*/fbclid/gclid/ref/..., but PRESERVES + sorts
# identifier query params so `?abstract_id=123` vs `?abstract_id=456` stay
# DISTINCT while only tracking noise collapses).
from src.polaris_graph.audit_ir.run_diff import _normalize_url

logger = logging.getLogger("polaris_graph.saturation")

# ── saturation decisions (module-level constants; allowed per CLAUDE.md §4.1) ──
CONTINUE = "CONTINUE"
STOP_SUFFICIENT = "STOP_SUFFICIENT"
STOP_NOVELTY = "STOP_NOVELTY"
STOP_BUDGET = "STOP_BUDGET"


def canonical_source_url(url: str) -> str:
    """PUBLIC wrapper over `run_diff._normalize_url` (brief §2.1).

    Single dedup identity for the saturation novelty metric. Importing the
    private `_normalize_url` directly is undesirable across modules, so this is
    the public seam — it delegates verbatim (no reimplementation).
    """
    return _normalize_url(url or "")


def _row_source_url(row: Any) -> str:
    """Extract the row's canonical URL field (brief §2.1).

    Live rows carry `source_url` (NOT `url`), `live_retriever.py:2221`. Accepts
    dict rows (the live shape) and falls back to object attributes defensively.
    """
    if isinstance(row, dict):
        return row.get("source_url") or row.get("url") or ""
    return getattr(row, "source_url", "") or getattr(row, "url", "") or ""


def marginal_novelty(
    prev_evidence_rows: list[Any],
    new_round_rows: list[Any],
) -> float:
    """Fraction of `new_round_rows` that are NOVEL vs `prev_evidence_rows`.

    Single dedup identity = canonical URL via `canonical_source_url`
    (run_diff canonicalizer over `source_url`). A new row is NOVEL iff its
    canonical URL is not already present in `prev_evidence_rows`. Intra-round
    duplicates collapse too — two rows in the SAME new round with the same
    canonical URL count as ONE novel (brief §2.1).

    Returns `len(novel) / max(1, len(new_round_rows))`.
    """
    prev_canon: set[str] = set()
    for row in prev_evidence_rows or []:
        canon = canonical_source_url(_row_source_url(row))
        if canon:
            prev_canon.add(canon)

    seen_this_round: set[str] = set()
    novel = 0
    for row in new_round_rows or []:
        canon = canonical_source_url(_row_source_url(row))
        # A row with no usable URL cannot be deduped — count it as novel once
        # only if its (empty) canon hasn't been seen this round.
        if canon in prev_canon or canon in seen_this_round:
            continue
        seen_this_round.add(canon)
        novel += 1
    return novel / max(1, len(new_round_rows or []))


def gap_sub_queries(sufficiency_report: Any, plan: Any) -> list[str]:
    """The sub-query TEXTS to fire next for the under-covered sections (brief §2.1).

    Covers BOTH shortfall modes the Phase-3 gate fails on (`plan_sufficiency_gate
    .py:308`): `covered_count < evidence_target` OR `empty_facets`:
      - under-covered section with `empty_facets` -> the sub-query texts at those
        empty facet indices;
      - under-covered section with `covered_count < evidence_target` but NO empty
        facets (total shortfall) -> ALL the section's mapped sub-query texts (fire
        the whole section to raise total coverage).

    Deduped (order-preserving), field-agnostic, derived from the plan. NEVER
    empty when a section is under-covered — else the loop would have no query to
    fire (the exact gap Codex flagged).
    """
    sub_queries = list(getattr(plan, "sub_queries", []) or [])
    n_sub = len(sub_queries)
    per_unit = list(getattr(sufficiency_report, "per_unit", []) or [])

    out: list[str] = []
    seen: set[str] = set()

    def _add(idx: int) -> None:
        if 0 <= idx < n_sub:
            text = sub_queries[idx]
            key = " ".join(str(text or "").split()).strip().lower()
            if text and key and key not in seen:
                seen.add(key)
                out.append(text)

    for unit in per_unit:
        if getattr(unit, "sufficient", True):
            continue
        empty_facets = list(getattr(unit, "empty_facets", []) or [])
        mapped = list(getattr(unit, "sub_query_indices", []) or [])
        if empty_facets:
            # Empty-facet mode: fire ONLY the under-covered facets' texts.
            for idx in empty_facets:
                _add(idx)
        else:
            # Total-shortfall mode (covered < target, no empty facet): fire the
            # WHOLE section's mapped facets to raise total coverage.
            for idx in mapped:
                _add(idx)
    return out


def saturation_decision(
    *,
    verdict: str,
    round_index: int,
    max_rounds: int,
    novelty: float,
    eps: float,
) -> str:
    """Decide the next saturation action (brief §2.1). PRIORITY LADDER — order
    matters; budget is checked BEFORE novelty.

    Returns one of {CONTINUE, STOP_SUFFICIENT, STOP_NOVELTY, STOP_BUDGET}.

    - verdict == proceed -> STOP_SUFFICIENT (gap closed).
    - verdict == abort -> STOP_BUDGET (the Phase-3 gate returns `abort` when
      `round_index >= max_rounds`; an explicit terminal, never unhandled).
    - verdict == expand AND round_index+1 >= max_rounds -> STOP_BUDGET (rounds
      exhausted).
    - verdict == expand AND round_index >= 1 AND novelty < eps -> STOP_NOVELTY
      (the last round added < eps novel rows — the curve flattened).
    - else (expand, rounds left, novelty >= eps) -> CONTINUE.
    """
    if verdict == "proceed":
        return STOP_SUFFICIENT
    # abort is a terminal verdict (rounds/budget exhausted at the gate).
    if verdict == "abort":
        return STOP_BUDGET
    # From here: verdict == expand (or any non-proceed/non-abort -> treat as
    # expand-style; budget-bounded). Budget BEFORE novelty.
    if round_index + 1 >= max_rounds:
        return STOP_BUDGET
    if round_index >= 1 and novelty < eps:
        return STOP_NOVELTY
    return CONTINUE


# ── budget accounting (PRE-SPEND, worst-case) ────────────────────────────────

def per_query_discovery_cost(adapter_count: int) -> int:
    """Worst-case DISCOVERY calls per gap query (brief §2.2, iter-5 P1 #1).

    core Serper + core S2 (`live_retriever.py:1790`,`:1806`) = 2 calls/query,
    PLUS the need-type dispatcher which calls EACH routed adapter inside
    `for q in queries` (`domain_backends.py:660`) = `adapter_count` calls PER gap
    query. (Fetch + OpenAlex are bounded by `fetch_cap`, not multiplied per gap
    query — out of this cap's scope.)
    """
    return 2 + max(0, int(adapter_count))


@dataclass
class BudgetPreflight:
    """Result of the PRE-SPEND budget preflight for one expansion round."""

    allowed_queries: list[str]
    fired_cost: int            # worst-case discovery calls this round will spend
    truncated: bool            # True iff gap queries were truncated to fit
    exhausted: bool            # True iff remaining budget cannot fund any query


def preflight_round_budget(
    *,
    gap_queries: list[str],
    cumulative_discovery_calls: int,
    max_discovery_calls: int,
    cost_per_query: int,
) -> BudgetPreflight:
    """PRE-SPEND truncation so a round's WORST-CASE discovery spend CANNOT push
    `cumulative_discovery_calls` over `max_discovery_calls` (brief §2.2, iter-3
    P1; INVARIANT P4-14).

    `remaining = MAX - cumulative`; if `remaining <= 0` -> exhausted (no query may
    fire). Else the round may fire at most `floor(remaining / cost_per_query)` gap
    queries — TRUNCATE `gap_queries` to that many.
    """
    cost = max(1, int(cost_per_query))
    remaining = int(max_discovery_calls) - int(cumulative_discovery_calls)
    if remaining <= 0:
        return BudgetPreflight(
            allowed_queries=[], fired_cost=0, truncated=bool(gap_queries),
            exhausted=True,
        )
    max_fire = remaining // cost
    if max_fire <= 0:
        # Remaining budget cannot fund even one gap query at worst-case cost.
        return BudgetPreflight(
            allowed_queries=[], fired_cost=0, truncated=bool(gap_queries),
            exhausted=True,
        )
    allowed = list(gap_queries[:max_fire])
    return BudgetPreflight(
        allowed_queries=allowed,
        fired_cost=len(allowed) * cost,
        truncated=len(allowed) < len(gap_queries),
        exhausted=False,
    )


# ── the injectable saturation orchestrator ───────────────────────────────────

@dataclass
class RoundOutcome:
    """One saturation round's outputs from the injected `run_round_fn`.

    The orchestrator stays client-free: the runner supplies a closure that does
    the actual retrieval -> select -> [V30/upload inject] -> gate; the smoke
    supplies a capture-only stub with controlled per-round evidence.
    """

    # Cumulative RETRIEVED corpus rows (for the novelty metric; `source_url`).
    cumulative_retrieved_rows: list[Any]
    # The BILLED generator-visible set Phase 3 certifies (post-select+V30+upload).
    evidence_for_gen: list[Any]
    # The PlanSufficiencyReport for THIS round's billed set.
    sufficiency_report: Any
    # The RAW rows THIS round RETRIEVED (the novelty DENOMINATOR) -- INCLUDES
    # canonical-URL duplicates already present in the corpus, so the novelty
    # fraction can fall below 1.0 as later rounds re-fetch the same sources.
    # NOT the deduped additions: handing the deduped set here makes novelty
    # degenerate (always 1.0 unless a round adds exactly zero rows), so the
    # `novelty < eps` flatten stop would never fire below 1.0. Round 0 = all of
    # round 0 (no prior corpus, so every row is novel).
    new_round_rows: list[Any] = field(default_factory=list)
    # The cumulative RETRIEVED corpus snapshot taken BEFORE this round (the
    # novelty BASELINE a round's raw rows are compared against). Round 0 =
    # empty (no prior corpus). Carried explicitly so the loop never has to
    # reconstruct "prior corpus" by object-identity subtraction (which breaks
    # once `new_round_rows` holds raw rows not all present in the corpus).
    prev_corpus_rows: list[Any] = field(default_factory=list)


@dataclass
class SaturationResult:
    """Terminal state of the saturation loop."""

    decision: str                 # STOP_SUFFICIENT | STOP_NOVELTY | STOP_BUDGET
    rounds_fired: int             # number of EXPANSION rounds fired (round 0 excl.)
    final_round: RoundOutcome
    cumulative_discovery_calls: int
    novelty_trajectory: list[float] = field(default_factory=list)
    truncated_any_round: bool = False


def run_saturation_loop(
    *,
    round0: RoundOutcome,
    run_round_fn: Callable[[list[str]], RoundOutcome],
    max_rounds: int,
    novelty_eps: float,
    max_discovery_calls: int,
    cost_per_query: int,
    plan: Any,
    log: Optional[Callable[[str], None]] = None,
) -> SaturationResult:
    """Drive the multi-round saturation loop (brief §2.2). PURE — constructs NO
    HTTP client; the live retrieval round is the INJECTED `run_round_fn`.

    Args:
        round0: the already-executed round-0 outcome (today's single-pass
            retrieval -> select -> [V30/upload] -> gate). Round 0 is the
            un-truncatable baseline; its spend is NOT charged against the
            expansion-round budget (which starts at 0).
        run_round_fn: `(gap_queries) -> RoundOutcome`. The runner's closure fires
            a GAP-ONLY retrieval round (anchor-suppressed), merges with global
            evidence_id renumber, re-selects, re-injects V30/upload, re-gates.
        max_rounds: `PG_SATURATION_MAX_ROUNDS` — bounds total rounds (incl. 0).
        novelty_eps: `PG_SATURATION_NOVELTY_EPS` — epsilon for the flatten stop.
        max_discovery_calls: `PG_SATURATION_MAX_RETRIEVAL_CALLS` — the cumulative
            EXPANSION-round discovery-call cap (round 0 excluded).
        cost_per_query: worst-case `per_query_discovery_cost(adapter_count)`.
        plan: the pinned `ResearchPlan` (for `gap_sub_queries`).
        log: optional line logger.

    Returns SaturationResult with the terminal decision + the final round.
    """
    _log = log or (lambda _m: None)
    round_index = 0
    current = round0
    cumulative_calls = 0            # EXPANSION-round discovery spend only.
    novelty_trajectory: list[float] = []
    truncated_any = False

    while True:
        verdict = str(getattr(current.sufficiency_report, "verdict", "abort"))
        # Novelty of THE ROUND JUST RUN vs the cumulative corpus BEFORE it. For
        # round 0 there is no prior corpus, so novelty is definitionally 1.0 and
        # the round>=1 guard in `saturation_decision` ignores it anyway. For
        # expansion rounds the baseline is the round's OWN `prev_corpus_rows`
        # snapshot (the corpus as it stood BEFORE the round) and the denominator
        # is the RAW retrieved `new_round_rows` (incl. duplicates) -- so a round
        # that re-fetches mostly-seen sources reads a LOW novelty fraction and
        # the `< eps` flatten stop can actually fire. Reconstructing the prior
        # corpus by `cumulative - new_round_rows` would be wrong now that
        # `new_round_rows` holds raw rows not all present in the corpus.
        if round_index == 0:
            novelty = 1.0
        else:
            novelty = marginal_novelty(
                current.prev_corpus_rows, current.new_round_rows
            )
        novelty_trajectory.append(novelty)

        decision = saturation_decision(
            verdict=verdict,
            round_index=round_index,
            max_rounds=max_rounds,
            novelty=novelty,
            eps=novelty_eps,
        )
        _log(
            f"[saturation]  round={round_index} verdict={verdict} "
            f"novelty={novelty:.3f} -> {decision}"
        )

        if decision != CONTINUE:
            return SaturationResult(
                decision=decision,
                rounds_fired=round_index,
                final_round=current,
                cumulative_discovery_calls=cumulative_calls,
                novelty_trajectory=novelty_trajectory,
                truncated_any_round=truncated_any,
            )

        # CONTINUE -> fire round N+1, GAP-ONLY. Compute the gap queries from the
        # CURRENT round's sufficiency report, then PRE-SPEND budget-truncate.
        gaps = gap_sub_queries(current.sufficiency_report, plan)
        if not gaps:
            # Defensive: a non-proceed verdict with no gap query to fire would
            # spin the loop. Treat as budget-terminal (nothing actionable left).
            _log(
                "[saturation]  no gap sub-queries for under-covered "
                "section(s); terminating as STOP_BUDGET"
            )
            return SaturationResult(
                decision=STOP_BUDGET,
                rounds_fired=round_index,
                final_round=current,
                cumulative_discovery_calls=cumulative_calls,
                novelty_trajectory=novelty_trajectory,
                truncated_any_round=truncated_any,
            )

        preflight = preflight_round_budget(
            gap_queries=gaps,
            cumulative_discovery_calls=cumulative_calls,
            max_discovery_calls=max_discovery_calls,
            cost_per_query=cost_per_query,
        )
        truncated_any = truncated_any or preflight.truncated
        if preflight.exhausted:
            _log(
                "[saturation]  retrieval budget exhausted "
                f"(cumulative={cumulative_calls}/{max_discovery_calls}); "
                "STOP_BUDGET before firing"
            )
            return SaturationResult(
                decision=STOP_BUDGET,
                rounds_fired=round_index,
                final_round=current,
                cumulative_discovery_calls=cumulative_calls,
                novelty_trajectory=novelty_trajectory,
                truncated_any_round=truncated_any,
            )

        # Charge the WORST-CASE spend PRE-SPEND so the cumulative counter can
        # NEVER exceed MAX (INVARIANT P4-14), then fire the round.
        cumulative_calls += preflight.fired_cost
        _log(
            f"[saturation]  firing round {round_index + 1} with "
            f"{len(preflight.allowed_queries)} gap queries "
            f"(worst-case +{preflight.fired_cost} calls; "
            f"cumulative={cumulative_calls}/{max_discovery_calls})"
        )
        current = run_round_fn(preflight.allowed_queries)
        round_index += 1
