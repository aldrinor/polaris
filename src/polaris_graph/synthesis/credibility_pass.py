"""I-cred-012 (#1162) — credibility-analysis pass ORCHESTRATOR (the activation chain).

Pure orchestrator that runs the committed P4→P3→P2→P5→P6 redesign chain over the generator's EFFECTIVE
evidence pool and returns the disclosure inputs (``credibility_by_evidence``, ``origin_by_evidence``,
``claims``, ``edges``, ``weight_mass``). The sweep runner calls it under the master slate
``PG_SWEEP_CREDIBILITY_REDESIGN``; OFF ⇒ not invoked ⇒ byte-identical. ADVISORY only: ``strict_verify`` +
the 4-role D8 release policy stay the ONLY binding gates — nothing here keeps/drops a sentence or flips
release.

FAIL-LOUD vs LABEL (I-arch-005 B12, operator-locked 2026-06-14 "VERIFY = LABEL, NEVER HOLD"):
a row missing ``evidence_id``, a P4 independence-annotation gap, or a wired-module crash still ABORT the
pass (``CredibilityPassError``) — those are real, unrecoverable integrity holes. But the two INFRA
conditions that used to abort the WHOLE report no longer hold it (I-arch-005 B12-P1, operator-locked
2026-06-14 "nothing shall hold the report"):
  * a PER-SOURCE P2 ``judge_error`` — ``score_source_credibility`` isolates it to ONE row and falls back
    to that source's DETERMINISTIC priors (a real weight, never fabricated);
  * a MISSING production credibility judge (``judge=None``) — an infra/config condition, NOT a
    faithfulness finding: the chain runs priors-only and every source carries its real deterministic
    authority weight.
In both cases the affected sources are LABELED ``credibility_unscored`` (a disclosed gap, surfaced LOUD
per LAW II — never a silent downgrade) and the rest keep scoring; the report SHIPS with the gap rather
than HELD. The genuine cited-evidence coverage gap (a CITED evidence_id with NO credibility row at all)
stays fail-loud — that is a real provenance hole, caught downstream by ``apply_disclosure_to_svs``'s
coverage assertion. The credibility WEIGHT math is untouched; only the abort-the-basket reaction on
those two infra conditions became a per-source label (the pass is ADVISORY — the binding gates are
``strict_verify`` + the 4-role D8 release policy).

Order (locked): P4 copied-annotated rows (fail-loud on missing eid) → P3 supersession → P2 score
(LABEL credibility_unscored on judge_error / judge=None, never abort) → POST-P3 credibility =
P2 × P3 multiplier (certainty carried) → P5 claim graph
→ P6 weight-mass over the POST-P3 judgments. P10 dissent + the M-52 effective-pool hoist + the P8
render-site wrapper are the per-hook sub-issues; this module is the chain core they consume.
"""
from __future__ import annotations

import dataclasses
import os
from dataclasses import dataclass, field
from typing import Any, Callable

from src.polaris_graph.authority.credibility_skill import score_source_credibility
from src.polaris_graph.authority.supersession import supersession_adjustment
from src.polaris_graph.synthesis.claim_graph import build_claim_graph
from src.polaris_graph.synthesis.independence_collapse import collapse_independent_origins
from src.polaris_graph.synthesis.weight_mass import aggregate_weight_mass

_MASTER_FLAG = "PG_SWEEP_CREDIBILITY_REDESIGN"
_OFF_VALUES = frozenset({"", "0", "false", "off", "no"})

# I-arch-008 HOP-A KEYSTONE (#1265): the basket consolidator re-clusters claims from scratch via
# ``claim_graph.build_claim_graph`` whose FAIL-CLOSED ``build_merge_key`` singletons every clinical
# numeric whose dose/comparator/effect_measure/endpoint is blank (the documented A13 residual). That
# fragments 787 sources -> ~1781 mostly-singleton clusters (only 1 multi-member), so
# ``verified_support_origin_count`` stays <=1 everywhere and the rendered header reads "Multi-source
# corroborated (>=2 verified origins): 0". MEANWHILE ``finding_dedup.dedup_by_finding`` ALREADY groups
# the SAME rows by numeric finding (787 -> ~99 clusters WITH member_indices + member_hosts), and that
# grouping is on the LIVE run path (run_honest_sweep_r3.py:8079) — but it is thrown away for the basket
# path. When this flag is ON the basket consolidator CONSUMES finding_dedup's already-computed cluster
# grouping: it MERGES claim_graph's existing claim partition (never rebuilds members from rows, never
# splits, never drops) so same-finding members land in ONE basket, then runs the EXISTING isolated
# per-member verify UNCHANGED. Multi-source baskets EMERGE because the members are already grouped — NOT
# because any member newly passes the gate (the set that passes ``_verify_member_in_isolation`` is
# byte-identical: same claim.text, same span, same verify_fn). DEFAULT OFF => the legacy claim_graph
# grouping runs byte-identical (§-1.3 WEIGHT-AND-CONSOLIDATE, never FILTER-AND-CAP).
_ENV_BASKET_CONSUME_FINDING_DEDUP = "PG_BASKET_CONSUME_FINDING_DEDUP"


def basket_consume_finding_dedup_enabled() -> bool:
    """True iff the HOP-A keystone (consume finding_dedup grouping for baskets) is explicitly enabled.

    DEFAULT OFF (unset / 0 / off / false / no) => the legacy claim_graph cluster grouping is used
    verbatim => the assembled baskets, the rendered header, and the disclosure JSON are byte-identical
    to the pre-change tree. ON => ``_regroup_graph_by_finding_dedup`` merges the claim partition using
    finding_dedup membership before ``_assemble_baskets`` (grouping + origin-counting ONLY — the
    per-member verify and strict_verify are NEVER touched)."""
    return os.environ.get(_ENV_BASKET_CONSUME_FINDING_DEDUP, "").strip().lower() not in _OFF_VALUES

# I-arch-007 ITEM 1b (#1264): bounded parallelism for the per-member isolated-verify loop in
# ``_assemble_baskets``. The advisory pass verifies EVERY basket member against its OWN single span via
# the production entailment judge — a SERIAL O(N) loop over hundreds of members at up to 150 s/call is the
# wedge that hung Q72/Q76/Q90 (the credibility-pass death). Parallelizing the INDEPENDENT per-member
# verifies with a BOUNDED pool + deterministic post-step reassembly changes WALL-CLOCK only — never which
# verdict any member gets (``_verify_member_in_isolation`` is pure per-member: each member's claim vs its
# OWN single span) and never a binding gate (the pass is ADVISORY; ``basket_verdict`` is a pure LABEL).
# LAW VI: env-overridable, no magic number. DEFAULT 1 = the byte-identical SERIAL path — the parallelism
# stays INERT until explicitly enabled, which honors the HARD ordering constraint that 1b's parallel
# verifies (they share the singleton entailment-judge client) must NOT run concurrently before ITEM 2a
# makes that client thread-safe/thread-local (CONSOLIDATED_FIX_PLAN ITEM 1b "HARD ORDERING CONSTRAINT").
_ENV_PASS_MAX_INFLIGHT = "PG_CREDIBILITY_PASS_MAX_INFLIGHT"
_DEFAULT_PASS_MAX_INFLIGHT = 1


def _pass_max_inflight() -> int:
    """The bounded per-member verify concurrency (LAW VI). 1 (default) ⇒ the serial path is taken
    verbatim — byte-identical to the pre-1b loop. A bad/empty value falls back to the serial default
    (fail-safe, never an unbounded pool)."""
    try:
        value = int(
            os.environ.get(_ENV_PASS_MAX_INFLIGHT, _DEFAULT_PASS_MAX_INFLIGHT)
            or _DEFAULT_PASS_MAX_INFLIGHT
        )
    except (TypeError, ValueError):
        return _DEFAULT_PASS_MAX_INFLIGHT
    return value if value >= 1 else _DEFAULT_PASS_MAX_INFLIGHT


def credibility_redesign_enabled() -> bool:
    """The master activation slate. OFF ⇒ the runner never calls the pass ⇒ byte-identical.

    P0-A20 (I-arch-007, 602->22 funnel): the WEIGHT-AND-CONSOLIDATE redesign (CLAUDE.md §-1.3)
    is now the COHERENT DEFAULT — UNSET evaluates ON, matching the run-path mirror
    ``run_honest_sweep_r3._cred_redesign_on`` (which already defaults ``"on"``). Pre-fix this
    helper (and the other four library mirrors) defaulted to the EMPTY string, which IS a member
    of ``_OFF_VALUES`` -> unset evaluated OFF -> the library stayed on the legacy filter-and-cap /
    source-DROP path while the orchestrator believed the redesign was on. That split IS the funnel.
    An EXPLICIT ``PG_SWEEP_CREDIBILITY_REDESIGN=0`` (or off/false/no) still returns False -> the
    legacy path is preserved byte-for-byte for the regression/escape-hatch case."""
    return os.environ.get(_MASTER_FLAG, "on").strip().lower() not in _OFF_VALUES


class CredibilityPassError(RuntimeError):
    """Activated pass cannot complete faithfully — fail-loud, never a silent false-green advisory."""


@dataclass
class EvidenceCredibility:
    evidence_id: str
    credibility_weight: float       # POST-P3: P2 weight × supersession multiplier, clamped [0,1]
    reliability_score: float
    relevance_score: float
    origin_cluster_id: str
    is_canonical_origin: bool
    certainty_downgrade: bool       # carried explicitly from P3 (supersession), not folded into the number
    soft_warning: str | None
    # I-arch-005 B12 (#1257): True iff THIS source's credibility judge errored (the priors-only
    # fallback weight was used). A DISCLOSED LABEL — the source is still scored (priors), the rest
    # of the corpus keeps its LLM judgments, and the WHOLE report no longer aborts on one judge
    # error. Defaulted False so every legacy construction + the flag-OFF path is byte-identical.
    credibility_unscored: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# I-arch-002 [8] / Wave-3 design §5/§6 — the per-claim ClaimBasket.
#
# A basket is one claim_cluster_id's whole group of supporting sources. Principle
# 2 (CONSOLIDATE, don't DROP): ``supporting_members`` keeps ALL sources, never a
# representative. Principle 3 (BASKET FAITHFULNESS): the verdict is decided against
# the WHOLE basket, but ``verified_support_origin_count`` is computed by ISOLATED
# per-member verification — each member verified against its OWN single span, never
# a multi-citation union (design §0/§5 FIX-3: a union that passes while a member
# fails alone must count that member UNVERIFIED). ``basket_verdict`` is a LABEL only
# (design §6): it may downgrade / drop / label, but NEVER resurrect a
# strict_verify-dropped sentence.
#
# These are ADVISORY side-outputs assembled under the master flag. strict_verify +
# the 4-role D8 release policy stay the ONLY binding gates — nothing here keeps or
# drops a sentence or flips release.
# ─────────────────────────────────────────────────────────────────────────────

# basket_verdict labels (design §5 — NAMED constants, no inline magic strings).
BASKET_VERDICT_FULL = "full"            # every supporting member independently verified on its own span
BASKET_VERDICT_PARTIAL = "partial"      # some but not all members verified
BASKET_VERDICT_CONTESTED = "contested"  # >=1 refuter edge references this cluster (user judges)
BASKET_VERDICT_UNVERIFIED = "unverified"  # no member verified alone


@dataclass
class BasketMember:
    """One source backing a claim basket, carrying its OWN isolated span verdict.

    ``span_verdict`` is the result of verifying this member ALONE against its own
    span (SUPPORTS / UNSUPPORTED). It is never a union verdict — that is the whole
    anti-laundering property (design §5 FIX-3). A member with no verified span is
    kept (Principle 2: never dropped) and shown as UNSUPPORTED.
    """

    evidence_id: str
    source_url: str
    source_tier: str
    origin_cluster_id: str
    credibility_weight: float | None
    authority_score: float
    span: tuple                     # (start, end) of the member's own verified span
    direct_quote: str               # the span text the member was verified against
    # "SUPPORTS" | "UNSUPPORTED" — the BINARY result of isolated per-member
    # verification. Design §5's enum also lists CONTEXT, but that is a RENDER-layer
    # (P5.x) distinction (a span shown as background, not support); isolated
    # strict_verify is pass/fail, so this assembly emits only the two binary values.
    span_verdict: str


@dataclass
class ClaimBasket:
    """A per-claim basket — the group of sources carrying the SAME claim (design §5).

    ``supporting_members`` keeps ALL sources (never dropped). ``refuter_cluster_ids``
    REFERENCE the contradicting clusters (not duplicated). ``total_clustered_origin_count``
    is ADVISORY (the clustered, not-verified origin count from weight_mass) and is
    NEVER rendered as support strength. ``verified_support_origin_count`` —
    the ONLY strengthening count — is the number of DISTINCT origin clusters whose
    member passed ISOLATED per-member verification on its own span. ``basket_verdict``
    is a LABEL derived from those counts + refuter references; it can never upgrade a
    dropped sentence.
    """

    claim_cluster_id: str
    claim_text: str
    subject: str
    predicate: str
    supporting_members: list                 # list[BasketMember] — ALL sources, never dropped
    refuter_cluster_ids: tuple               # REFERENCE only (design §5)
    weight_mass: float                       # authority-only, copy-uninflatable (from weight_mass.py)
    total_clustered_origin_count: int        # ADVISORY ONLY — never rendered as support strength
    verified_support_origin_count: int       # isolated-verified distinct origins (the only strengthening count)
    basket_verdict: str                      # full | partial | contested | unverified (LABEL only)


@dataclass
class CredibilityAnalysis:
    credibility_by_evidence: dict   # evidence_id -> EvidenceCredibility
    origin_by_evidence: dict        # evidence_id -> origin_cluster_id
    claims: list                    # AtomicClaim[] (Phase-5)
    edges: list                     # ContradictionEdge[] (Phase-5)
    weight_mass: list               # ClaimWeightMass[] (Phase-6)
    # I-arch-002 [8] — per-claim baskets + the sentence->claim_cluster_id binding.
    # Defaulted so the empty-rows early-return (and any legacy caller) still builds.
    baskets: list = field(default_factory=list)             # ClaimBasket[]
    cluster_id_by_evidence: dict = field(default_factory=dict)  # evidence_id -> claim_cluster_id[] (binding)


def _require_evidence_id(row: dict, index: int) -> str:
    eid = str((row or {}).get("evidence_id") or "").strip()
    if not eid:
        raise CredibilityPassError(
            f"abort_credibility_pass_error: evidence row {index} has no evidence_id (cannot disclose a "
            f"claim whose source can't be identified)"
        )
    return eid


def _clamp01(value: float) -> float:
    return 0.0 if value < 0.0 else 1.0 if value > 1.0 else value


# ── I-arch-002 [8] — ClaimBasket assembly + isolated per-member verification ───


def _row_span_text(row: dict) -> str:
    """The member's own span text (the same field strict_verify reads). Mirrors
    ``provenance_generator``'s ``direct_quote or statement`` resolution so the
    isolated verification runs against the SAME bytes strict_verify would."""
    return str((row or {}).get("direct_quote") or (row or {}).get("statement") or "")


def _verify_member_in_isolation(
    claim_text: str,
    member_row: dict,
    *,
    verify_fn: Callable,
) -> str:
    """Verify ONE member against ITS OWN single span — never a union (design §5 FIX-3).

    Builds a single-provenance-token sentence (``<claim_text> [#ev:<eid>:0-<len>]``)
    so ``verify_sentence_provenance`` has EXACTLY ONE token. The per-token union loop
    inside the verifier (which aggregates decimals/text across MULTIPLE tokens) is the
    laundering path; one token means no union, so a member whose own span lacks the
    claim's number/content fails ALONE — even if a multi-citation union would pass.

    Returns ``"SUPPORTS"`` iff the isolated sentence is verified, else ``"UNSUPPORTED"``.
    The verifier is INJECTED (production ``verify_sentence_provenance`` by default; a
    deterministic fake in tests) and is NEVER re-run as a gate — this is advisory.
    """
    eid = str((member_row or {}).get("evidence_id") or "")
    span = _row_span_text(member_row)
    if not eid or not span:
        return "UNSUPPORTED"
    # Defensive single-token guarantee (the anti-laundering invariant, design §5
    # FIX-3): strip ANY stray provenance / calc token already in the claim text so
    # the appended one is the ONLY token. With exactly one token the verifier's
    # per-token union loop cannot aggregate this member's span with any other — a
    # member whose own span lacks the claim fails ALONE.
    from src.polaris_graph.generator.provenance_generator import (  # noqa: PLC0415
        _CALC_TOKEN_RE,
        _PROVENANCE_TOKEN_RE,
    )
    safe_text = _PROVENANCE_TOKEN_RE.sub(" ", str(claim_text or ""))
    safe_text = _CALC_TOKEN_RE.sub(" ", safe_text).strip()
    # ONE token spanning the member's whole own span.
    sentence = f"{safe_text} [#ev:{eid}:0-{len(span)}]"
    pool = {eid: dict(member_row)}
    try:
        result = verify_fn(sentence, pool)
    except Exception:
        # Advisory path: a verifier failure on one member is conservatively UNSUPPORTED
        # (never resurrects the member, never aborts the basket) — fail-closed for the
        # strengthening count, which can only ever UNDERCOUNT, never inflate.
        return "UNSUPPORTED"
    return "SUPPORTS" if bool(getattr(result, "is_verified", False)) else "UNSUPPORTED"


def _run_member_verifies(
    tasks: list[tuple[str, dict]],
    *,
    verify_fn: Callable,
    max_inflight: int,
) -> list[str]:
    """Run the per-member isolated verifies for ``tasks`` and return their verdicts IN ORDER.

    ``tasks`` is the FLAT, deterministically-ordered list of ``(claim_text, member_row)`` pairs
    (built in the ORIGINAL ``sorted(clusters)`` → member order). The returned verdict list is
    index-aligned with ``tasks`` (``results[i]`` is the verdict for ``tasks[i]``), so the caller
    reassembles baskets in EXACTLY the serial order — the parallel path is verdict-identical to the
    serial path, only faster.

    ``max_inflight == 1`` (the default) takes the SERIAL path verbatim — byte-identical to the
    pre-1b inline loop. For ``max_inflight >= 2`` a BOUNDED ``ThreadPoolExecutor`` caps concurrency at
    exactly ``max_inflight``; each worker runs inside a COPIED ``contextvars.copy_context()`` so:
      * the run-scoped JUDGE TELEMETRY ContextVar (FX-09, a MUTABLE dict) is the SAME object in the
        copy, so the judge's in-place ``calls/judge_error`` ticks land in the parent's counter (mirrors
        ``provenance_generator._verify_in_context``);
      * the run-scoped COST ContextVar (a float — rebinds don't propagate across a copy) is isolated to
        zero in the worker and its per-task delta is re-added to the parent counter + the budget
        re-checked (mirrors ``credibility_skill.score_source_credibility``), so the parallel advisory
        verifies never silently lose the run's cost accounting (Codex P2).
    A worker exception PROPAGATES out (fail-loud) exactly as the serial loop's ``verify_fn`` would —
    the existing ``_verify_member_in_isolation`` already maps a verifier failure to ``UNSUPPORTED``
    internally, so only a programming/budget defect ever escapes here.

    This is ADVISORY — ``_verify_member_in_isolation`` is never re-run as a gate, and parallelism
    changes WALL-CLOCK only, never any verdict.
    """
    n = len(tasks)
    if max_inflight <= 1 or n <= 1:
        # SERIAL fast path (default / single task): byte-identical to the pre-1b inline loop.
        return [
            _verify_member_in_isolation(claim_text, member_row, verify_fn=verify_fn)
            for claim_text, member_row in tasks
        ]

    import concurrent.futures  # noqa: PLC0415 (lazy: zero cost on the serial default path)
    import contextvars  # noqa: PLC0415
    from src.polaris_graph.llm.openrouter_client import (  # noqa: PLC0415
        _add_run_cost,
        check_run_budget,
        current_run_cost,
        reset_run_cost,
    )

    def _verify_one(
        idx: int, claim_text: str, member_row: dict, ctx: contextvars.Context
    ) -> tuple[int, str, float]:
        def _run() -> tuple[str, float]:
            reset_run_cost()  # isolate THIS member's spend in the copied context (parent re-adds a clean delta)
            verdict = _verify_member_in_isolation(claim_text, member_row, verify_fn=verify_fn)
            return verdict, current_run_cost()
        verdict, delta = ctx.run(_run)
        return idx, verdict, delta

    results: list[str | None] = [None] * n
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=max_inflight)
    try:
        futures = [
            pool.submit(_verify_one, i, claim_text, member_row, contextvars.copy_context())
            for i, (claim_text, member_row) in enumerate(tasks)
        ]
        for future in concurrent.futures.as_completed(futures):
            idx, verdict, delta = future.result()  # re-raises BudgetExceededError / worker exc (fail closed)
            results[idx] = verdict
            _add_run_cost(delta)   # thread the per-member spend into the single run counter (no lost ticks)
            check_run_budget(0)    # raises BudgetExceededError -> bounded overspend (~max_inflight in flight)
    except BaseException:
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    else:
        pool.shutdown(wait=True)
    for i, verdict in enumerate(results):
        if verdict is None:
            raise CredibilityPassError(
                f"abort_credibility_pass_error: basket member index {i} produced no verdict from the "
                f"compute pool (fail-closed — a dropped future must never silently undercount)."
            )
    return [v for v in results if v is not None]


def _regroup_graph_by_finding_dedup(
    graph: Any,
    annotated: list[dict],
    *,
    gov_suffixes: tuple,
    domain: str | None,
) -> Any:
    """HOP-A KEYSTONE (#1265): MERGE claim_graph's existing claim partition using
    ``finding_dedup``'s already-computed cluster grouping, so same-finding members land in
    ONE basket. Returns a NEW graph-shaped view (same ``claims`` objects, MERGED ``clusters``,
    REMAPPED ``edges``); the input ``graph`` is never mutated.

    FAITHFULNESS — grouping + relabel ONLY (the HARD constraint):
      * The ``claims`` list (and every ``AtomicClaim.text`` / span the isolated verify reads) is
        UNCHANGED — passed through by reference. So the set of members that pass
        ``_verify_member_in_isolation`` downstream is byte-identical to the legacy grouping: same
        claim text, same span, same verify_fn. No member newly passes any gate.
      * Clusters are MERGED, never split and never dropped: the rebuilt partition covers EXACTLY the
        same claim indices as the input (a partition refinement in reverse — union only). A
        qualitative / raw / non-clinical claim that finding_dedup does not cluster keeps its OWN
        legacy singleton id (finding_dedup only groups finding-bearing rows; everything else is left
        exactly as claim_graph clustered it).
      * ``verified_support_origin_count`` rises ONLY because distinct ALREADY-verified origins now
        share a basket — never because acceptance was relaxed.
      * EDGES are remapped to the merged ids so a CONTESTED basket (a refuter edge references it)
        still renders CONTESTED — relabeling cluster ids without remapping edges would SILENTLY hide
        a contradiction (clinical-lethal). Each edge's ``claim_cluster_ids`` is rewritten through the
        same old->new map.

    ``finding_dedup`` is on the LIVE run path already (run_honest_sweep_r3.py:8079); this consumes its
    PURE grouping (no network, no LLM) with the SAME ``gov_suffixes`` + ``domain`` the rest of the
    pass uses. Deferred import (mirrors the lazy ``verify_sentence_provenance`` import) — finding_dedup
    imports credibility_pass inside its own function, so a function-local import here avoids the cycle.
    """
    from src.polaris_graph.synthesis.finding_dedup import dedup_by_finding  # noqa: PLC0415

    claims = list(getattr(graph, "claims", None) or [])
    if not claims:
        return graph

    # claim_graph emits AT MOST ONE numeric AtomicClaim per evidence_id (extract_numeric_claims emits
    # <=1/row); finding_dedup groups by the SAME numeric finding. Map evidence_id -> the NUMERIC claim
    # index so a finding cluster's member rows resolve to the right atom to union. Non-numeric
    # (qualitative/raw) claims are intentionally NOT in this map — they keep their legacy singleton id.
    numeric_claim_idx_by_eid: dict[str, int] = {}
    for ci, claim in enumerate(claims):
        if str(getattr(claim, "kind", "") or "") != "numeric":
            continue
        eid = str(getattr(claim, "evidence_id", "") or "")
        # First numeric atom per eid wins (deterministic; <=1 expected in practice).
        numeric_claim_idx_by_eid.setdefault(eid, ci)

    # finding_dedup member_indices are ROW indices into ``annotated`` -> resolve to evidence_id.
    eid_by_row_index = {
        i: str((row or {}).get("evidence_id") or "")
        for i, row in enumerate(annotated or [])
    }

    dedup = dedup_by_finding(annotated, gov_suffixes=gov_suffixes, domain=domain)

    # ── Union-Find over claim indices: union the numeric atoms that finding_dedup grouped together.
    parent = list(range(len(claims)))

    def _find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def _union(a: int, b: int) -> None:
        ra, rb = _find(a), _find(b)
        if ra != rb:
            # Deterministic representative: the lower claim index, so the rebuilt id is stable
            # across runs (claims are in a deterministic extraction order).
            parent[max(ra, rb)] = min(ra, rb)

    for fcluster in (getattr(dedup, "clusters", None) or []):
        member_claim_indices: list[int] = []
        for row_index in (getattr(fcluster, "member_indices", None) or []):
            eid = eid_by_row_index.get(int(row_index), "")
            ci = numeric_claim_idx_by_eid.get(eid)
            if ci is not None:
                member_claim_indices.append(ci)
        # Union all members of this finding cluster into one component (merge-only).
        for ci in member_claim_indices[1:]:
            _union(member_claim_indices[0], ci)

    # ── Relabel: every claim in a merged component takes the EXISTING claim_cluster_id of its
    #    component representative (a real ``clm_*`` id already on a member — never a new scheme, so
    #    the downstream join key format is unchanged). Components that were never unioned keep their
    #    own id verbatim (byte-identical for unmerged claims). old_id -> new_id for the edge remap.
    rep_id_by_root: dict[int, str] = {}
    for idx in range(len(claims)):
        root = _find(idx)
        if root not in rep_id_by_root:
            rep_id_by_root[root] = str(getattr(claims[root], "claim_cluster_id", "") or "")

    old_to_new: dict[str, str] = {}
    new_clusters: dict[str, list[int]] = {}
    for idx, claim in enumerate(claims):
        old_id = str(getattr(claim, "claim_cluster_id", "") or "")
        new_id = rep_id_by_root[_find(idx)]
        if old_id and old_id != new_id:
            old_to_new[old_id] = new_id
        # Relabel the claim in place is UNSAFE (shared object); we only rebuild the clusters dict and
        # the cluster_id_by_evidence binding from new_id, and _assemble_baskets reads members from the
        # clusters dict + the binding — never re-reads claim.claim_cluster_id for the basket id. But to
        # keep the basket's claim_cluster_id and the binding consistent we DO set it (these AtomicClaim
        # objects are this pass's own, freshly built by build_claim_graph this call — not the caller's).
        claim.claim_cluster_id = new_id
        new_clusters.setdefault(new_id, []).append(idx)

    if not old_to_new:
        # No merge happened (e.g. finding_dedup found nothing to group) -> the legacy grouping stands.
        return graph

    # ── Remap edges so a refuter reference still lands on the MERGED cluster id (never hide a
    #    contradiction). claim_cluster_ids that were not relabeled pass through unchanged.
    new_edges: list = []
    for edge in (getattr(graph, "edges", None) or []):
        ids = tuple(sorted({
            old_to_new.get(str(c), str(c))
            for c in (getattr(edge, "claim_cluster_ids", ()) or ())
            if str(c)
        }))
        new_edges.append(dataclasses.replace(edge, claim_cluster_ids=ids))

    return dataclasses.replace(
        graph,
        claims=claims,
        clusters=new_clusters,
        edges=new_edges,
        distinct_cluster_count=len(new_clusters),  # keep the count consistent with the merged partition
    )


def _assemble_baskets(
    graph: Any,
    weight_mass: list,
    annotated: list[dict],
    credibility_by_evidence: dict,
    *,
    verify_fn: Callable,
    max_inflight: int = _DEFAULT_PASS_MAX_INFLIGHT,
) -> list:
    """Assemble one ClaimBasket per claim cluster (design §5/§6).

    Principle 2: ALL members of a cluster are kept (``supporting_members`` is the full
    group, never a representative). Principle 3: ``verified_support_origin_count`` is the
    count of DISTINCT origin clusters whose member passed ISOLATED per-member verification
    (NOT the raw passing-member count, and NOT ``weight_mass.independent_origin_count`` —
    that is the clustered, not-verified count, surfaced ONLY as the ADVISORY
    ``total_clustered_origin_count``). ``basket_verdict`` is a pure LABEL.

    I-arch-007 ITEM 1b (#1264): the per-member isolated verifies (the expensive entailment-judge
    calls) are gathered into a FLAT, deterministically-ordered task list, dispatched through a BOUNDED
    pool (``max_inflight``), and reassembled in the ORIGINAL ``sorted(clusters)`` → member order. The
    verdict each member receives is unchanged from the serial path — only wall-clock differs.
    """
    row_by_eid = {str(r.get("evidence_id", "")): r for r in (annotated or [])}
    wm_by_cluster = {
        str(getattr(w, "claim_cluster_id", "") or ""): w for w in (weight_mass or [])
    }

    # Refuter references (design §5): for each cluster, the OTHER cluster ids it is
    # joined to by a ContradictionEdge. REFERENCE only — never duplicated into the basket.
    refuters_by_cluster: dict[str, set] = {}
    for edge in (getattr(graph, "edges", None) or []):
        ids = [str(c) for c in (getattr(edge, "claim_cluster_ids", ()) or ()) if str(c)]
        for cid in ids:
            for other in ids:
                if other != cid:
                    refuters_by_cluster.setdefault(cid, set()).add(other)

    clusters = getattr(graph, "clusters", None) or {}
    claims = getattr(graph, "claims", None) or []

    # ── ITEM 1b step 1: build the per-member verify task list in the ORIGINAL deterministic order ──
    # (sorted(clusters) → member order). Each entry is (claim_text, member_row); empty clusters are
    # skipped exactly as the serial loop does, so the index alignment is identical to a serial pass.
    sorted_cluster_ids = [cid for cid in sorted(clusters) if [claims[i] for i in clusters[cid]]]
    verify_tasks: list[tuple[str, dict]] = []
    for cluster_id in sorted_cluster_ids:
        for claim in [claims[i] for i in clusters[cluster_id]]:
            eid = str(getattr(claim, "evidence_id", "") or "")
            row = row_by_eid.get(eid, {})
            verify_tasks.append((str(getattr(claim, "text", "") or ""), row))

    # ── ITEM 1b step 2: run the verifies (serial when max_inflight<=1; bounded-parallel otherwise) ──
    # Verdicts come back index-aligned with verify_tasks, so the reassembly below consumes them in the
    # SAME order the serial loop computed them — verdict-identical, only faster.
    verdicts = _run_member_verifies(
        verify_tasks, verify_fn=verify_fn, max_inflight=max_inflight,
    )
    _verdict_cursor = 0

    baskets: list[ClaimBasket] = []
    for cluster_id in sorted_cluster_ids:
        member_indices = clusters[cluster_id]
        member_claims = [claims[i] for i in member_indices]
        head = member_claims[0]
        cwm = wm_by_cluster.get(cluster_id)

        members: list[BasketMember] = []
        verified_origin_ids: set[str] = set()
        verified_any = False
        all_verified = True
        for claim in member_claims:
            eid = str(getattr(claim, "evidence_id", "") or "")
            row = row_by_eid.get(eid, {})
            ec = credibility_by_evidence.get(eid)
            origin_id = str(getattr(ec, "origin_cluster_id", "") or "") if ec else ""
            if not origin_id:
                # an unmapped member is its own independent origin (mirrors weight_mass)
                origin_id = f"origin::{eid}"
            span = _row_span_text(row)
            # ISOLATED per-member verification (design §5 FIX-3): the claim's TEXT against
            # THIS member's own single span — never a union of basket spans. The verdict was
            # precomputed (serial or bounded-parallel) and is consumed here in the ORIGINAL order.
            verdict = verdicts[_verdict_cursor]
            _verdict_cursor += 1
            if verdict == "SUPPORTS":
                verified_any = True
                verified_origin_ids.add(origin_id)
            else:
                all_verified = False
            members.append(BasketMember(
                evidence_id=eid,
                source_url=str(getattr(claim, "source_url", "") or row.get("source_url", "")),
                source_tier=str(getattr(claim, "source_tier", "") or row.get("tier", "")),
                origin_cluster_id=origin_id,
                credibility_weight=(getattr(ec, "credibility_weight", None) if ec else None),
                authority_score=_clamp01(float(row.get("authority_score", 0.0) or 0.0)),
                span=(0, len(span)),
                direct_quote=span,
                span_verdict=verdict,
            ))

        refuter_ids = tuple(sorted(refuters_by_cluster.get(cluster_id, set())))
        # verified count = DISTINCT verified origin clusters (the only strengthening count).
        verified_support_origin_count = len(verified_origin_ids)
        # advisory clustered count (NOT verified) — sourced from weight_mass, never reused
        # as the strengthening count.
        total_clustered_origin_count = int(
            getattr(cwm, "independent_origin_count", 0) or 0
        ) if cwm is not None else 0

        # basket_verdict is a pure LABEL (design §6): derived from verified counts +
        # refuter references. It NEVER feeds is_verified / strict_verify — a downstream
        # consumer reads it for display, it can never resurrect a dropped sentence.
        if refuter_ids:
            basket_verdict = BASKET_VERDICT_CONTESTED
        elif not verified_any:
            basket_verdict = BASKET_VERDICT_UNVERIFIED
        elif all_verified:
            basket_verdict = BASKET_VERDICT_FULL
        else:
            basket_verdict = BASKET_VERDICT_PARTIAL

        baskets.append(ClaimBasket(
            claim_cluster_id=cluster_id,
            claim_text=str(getattr(head, "text", "") or ""),
            subject=str(getattr(head, "subject", "") or ""),
            predicate=str(getattr(head, "predicate", "") or ""),
            supporting_members=members,
            refuter_cluster_ids=refuter_ids,
            weight_mass=float(getattr(cwm, "weight_mass", 0.0) or 0.0) if cwm is not None else 0.0,
            total_clustered_origin_count=total_clustered_origin_count,
            verified_support_origin_count=verified_support_origin_count,
            basket_verdict=basket_verdict,
        ))
    return baskets


def run_credibility_analysis(
    research_question: str,
    rows: list[dict],
    *,
    gov_suffixes: tuple,
    domain: str | None = None,
    judge: Callable | None = None,
    now_year: int | None = None,
    max_inflight: int | None = None,
) -> CredibilityAnalysis:
    """Run the P4→P3→P2→P5→P6 chain over the EFFECTIVE evidence pool.

    Fail-loud on a MISSING evidence_id, a P4 independence-annotation gap, or a wired-module crash (real
    integrity holes). The two INFRA conditions that used to abort the WHOLE report no longer hold it
    (I-arch-005 B12-P1, operator-locked 2026-06-14 "nothing shall hold the report"): a PER-SOURCE P2
    ``judge_error`` and a MISSING production judge (``judge=None``) each LABEL the affected sources
    ``credibility_unscored`` (priors-only weight — a real, honest deterministic weight, never fabricated)
    and the rest keep scoring, so the report ships with the disclosed gap. ``rows`` MUST already be the
    generator's effective pool (post-M-52, post-dissent); ``gov_suffixes`` is the PSL gov-suffix tuple the
    rest of the pipeline uses (dependency-injected, no global). ``judge`` is the production credibility
    judge (injected); None ⇒ the whole pool ships priors-only + LABELED ``credibility_unscored`` (a
    disclosed gap surfaced LOUD per LAW II), NOT a silent false-green and NOT a hold.

    ``max_inflight`` (I-arch-007 ITEM 1b, #1264) bounds the per-member isolated-verify concurrency in
    ``_assemble_baskets`` (LAW VI). ``None`` (the default) reads the ``PG_CREDIBILITY_PASS_MAX_INFLIGHT``
    env knob, which itself defaults to 1 = the byte-identical SERIAL path. The bound changes WALL-CLOCK
    only — the per-member verdicts and the resulting baskets are identical to the serial pass.
    """
    if max_inflight is None:
        max_inflight = _pass_max_inflight()
    if not rows:
        return CredibilityAnalysis({}, {}, [], [], [])
    if judge is None:
        # I-arch-005 B12-P1 (#1257, operator-locked 2026-06-14 "VERIFY = LABEL, NEVER HOLD"): a missing
        # production credibility judge is an INFRA/config condition (the pass is ADVISORY — strict_verify
        # + the 4-role D8 release policy stay the ONLY binding gates), NOT a faithfulness finding. It must
        # NOT abort the whole report. The chain runs priors-only (every source carries its real
        # deterministic authority weight, never fabricated) and LABELS every source credibility_unscored —
        # a disclosed gap. LOUD log (LAW II: no silent downgrade) so the operator sees it.
        import logging as _logging  # noqa: PLC0415
        _logging.getLogger(__name__).warning(
            "[credibility-pass] no production credibility judge wired (judge=None); running priors-only "
            "and LABELING all %d source(s) credibility_unscored (disclosed gap) — the report ships with "
            "the gap, never aborts (operator-locked 'nothing shall hold the report').",
            len(rows),
        )
    from src.polaris_graph.llm.openrouter_client import BudgetExceededError
    try:
        return _run_chain(
            research_question, rows,
            gov_suffixes=gov_suffixes, domain=domain, judge=judge, now_year=now_year,
            max_inflight=max_inflight,
        )
    except (CredibilityPassError, BudgetExceededError):
        # CredibilityPassError = fail-loud abort; BudgetExceededError (Codex #012a P1-2) must reach the
        # sweep's budget-abort path cleanly, NOT be masked as a generic credibility-pass error.
        raise
    except Exception as exc:  # ANY OTHER wired-module failure → fail-loud abort, never a silent false-green
        raise CredibilityPassError(
            f"abort_credibility_pass_error: a wired credibility module failed "
            f"({type(exc).__name__}): {exc}"
        ) from exc


def _run_chain(
    research_question: str,
    rows: list[dict],
    *,
    gov_suffixes: tuple,
    domain: str | None,
    judge: Callable | None,
    now_year: int | None,
    max_inflight: int = _DEFAULT_PASS_MAX_INFLIGHT,
) -> CredibilityAnalysis:
    """The P4→P3→P2→P5→P6 chain body; wrapped by run_credibility_analysis for the fail-loud posture."""
    # ── P4: independent-origin collapse → per-row assignment, on COPIED rows (never mutate the caller) ──
    collapse = collapse_independent_origins(rows, gov_suffixes=gov_suffixes)
    if len(collapse.assignments) != len(rows):
        raise CredibilityPassError(
            "abort_independence_annotation_gap: P4 returned "
            f"{len(collapse.assignments)} assignments for {len(rows)} rows"
        )
    annotated: list[dict] = []
    origin_by_evidence: dict = {}
    for i, row in enumerate(rows):
        eid = _require_evidence_id(row, i)
        assignment = collapse.assignments[i]
        new_row = dict(row)  # COPY
        new_row["origin_cluster_id"] = assignment.origin_cluster_id
        new_row["is_canonical_origin"] = assignment.is_canonical_origin
        annotated.append(new_row)
        origin_by_evidence[eid] = assignment.origin_cluster_id

    # ── P3: supersession multiplier per source ──
    supers_by_evidence = {
        _require_evidence_id(row, i): supersession_adjustment(row, now_year=now_year)
        for i, row in enumerate(annotated)
    }

    # ── P2: credibility judgments — judge_error / judge=None LABEL the source, never abort ──
    # I-arch-005 B12 (#1257, operator-locked 2026-06-14 "VERIFY = LABEL, NEVER HOLD"): the pass
    # is ADVISORY (its own docstring). The two INFRA conditions must NOT abort the WHOLE report —
    # each LABELS the affected source(s) ``credibility_unscored`` (a disclosed gap) and KEEPS the
    # rest scoring with real weights:
    #   * a PER-SOURCE judge_error — ``score_source_credibility`` already isolates the error to ONE
    #     row and falls back to that source's DETERMINISTIC priors (a real, honest weight, never
    #     fabricated), flagging it ``judge_error=True``;
    #   * judge=None (no production judge wired) — ``score_source_credibility(judge=None)`` returns
    #     priors-only for EVERY row but with ``judge_error=False`` (it is not a per-source error, it
    #     is a global infra condition). So the ``errored_ids`` set is EMPTY in that case; we OR in
    #     ``judge_missing`` below so EVERY source is correctly labeled ``credibility_unscored`` (NOT a
    #     silent priors-only false-green — that EXACT trap is why the explicit OR exists).
    # The credibility WEIGHT math is unchanged — a labeled row simply carries its priors-only weight +
    # the disclosed label. (The genuine provenance hole — a CITED evidence_id with NO credibility row
    # at all — is still fail-loud, caught downstream by ``apply_disclosure_to_svs``'s coverage
    # assertion; that is a real coverage gap, NOT a recoverable infra condition.)
    judge_missing = judge is None
    judgments = score_source_credibility(research_question, annotated, domain=domain, judge=judge)
    errored_ids = {j.evidence_id for j in judgments if getattr(j, "judge_error", False)}
    if errored_ids:
        example = sorted(errored_ids)[:5]
        # LOUD log (LAW II: no silent downgrade) — the run still ships, but the operator sees it.
        import logging as _logging  # noqa: PLC0415
        _logging.getLogger(__name__).warning(
            "[credibility-pass] credibility judge errored for %d/%d source(s) (e.g. %s); "
            "LABELING them credibility_unscored (priors-only weight) and continuing to score the "
            "rest — the report ships with the disclosed gap (never aborts the basket).",
            len(errored_ids), len(judgments), example,
        )

    # ── POST-P3 credibility = P2 weight × supersession multiplier (certainty carried, not folded away) ──
    credibility_by_evidence: dict = {}
    for row, judgment in zip(annotated, judgments):
        eid = judgment.evidence_id
        supersession = supers_by_evidence.get(eid)
        multiplier = supersession.multiplier if supersession else 1.0
        credibility_by_evidence[eid] = EvidenceCredibility(
            evidence_id=eid,
            credibility_weight=_clamp01(judgment.credibility_weight * multiplier),
            reliability_score=judgment.reliability_score,
            relevance_score=judgment.relevance_score,
            origin_cluster_id=origin_by_evidence.get(eid, ""),
            is_canonical_origin=bool(row.get("is_canonical_origin")),
            certainty_downgrade=bool(supersession.certainty_downgrade) if supersession else False,
            soft_warning=(supersession.soft_warning if supersession else None),
            # OR in ``judge_missing``: with judge=None EVERY source is priors-only with
            # judge_error=False, so ``errored_ids`` is empty — without the OR every source would ship
            # credibility_unscored=False (a silent priors-only false-green, the EXACT trap B12-P1 fixes).
            credibility_unscored=(eid in errored_ids) or judge_missing,
        )

    # POST-P3 judgments for downstream — P6 disclosure must use the post-P3 credibility, not raw P2.
    adjusted_judgments = [
        dataclasses.replace(j, credibility_weight=credibility_by_evidence[j.evidence_id].credibility_weight)
        for j in judgments
    ]

    # ── P5: claim graph (atomic claims + contradiction edges) ──
    graph = build_claim_graph(annotated, domain=domain)

    # ── I-arch-008 HOP-A KEYSTONE (#1265): consume finding_dedup's already-computed grouping ──
    # DEFAULT OFF => byte-identical (the legacy claim_graph fragmentation stands). ON => MERGE the
    # claim partition using finding_dedup membership so same-finding members share ONE basket, BEFORE
    # weight-mass aggregation so the mass keys agree with the merged ids. Grouping + relabel + edge
    # remap ONLY — the claims/spans the isolated verify reads are untouched, so no member newly passes.
    if basket_consume_finding_dedup_enabled():
        graph = _regroup_graph_by_finding_dedup(
            graph, annotated, gov_suffixes=gov_suffixes, domain=domain,
        )

    # ── P6: origin-cluster weight-mass (mass = authority(canonical) ONLY; credibility disclosed) ──
    weight_mass = aggregate_weight_mass(graph.claims, annotated, adjusted_judgments)

    # ── I-arch-002 [8] — assemble per-claim baskets with ISOLATED per-member verification.
    # The verifier is the PRODUCTION single-sentence callable, lazy-imported here so this
    # module's import graph stays decoupled from the big provenance module (mirrors the
    # local imports at run_credibility_analysis / apply_disclosure_to_svs). It is used
    # ADVISORY only — strict_verify itself is never re-run as a gate.
    from src.polaris_graph.generator.provenance_generator import (  # noqa: PLC0415
        verify_sentence_provenance,
    )
    # I-arch-011 (#1268): the per-member basket verify runs under entailment-ENFORCE (the
    # PG_STRICT_VERIFY_ENTAILMENT default). It MUST stay enforce: ``span_verdict==SUPPORTS`` is
    # consumed at render WITHOUT re-verification — both as inline corroborator citations
    # (provenance_generator.py B6/B8 ``_verified_corroborators_for_tokens``) and as the breadth
    # enrichment section — so an entailment-OFF advisory verdict would ship un-entailed corroborator
    # citations (the rejected F2b; Codex P0-1). The serial-entailment HANG is avoided NOT by
    # disabling the judge but by the architecture's bounded parallelism + wall: ``max_inflight``
    # (PG_CREDIBILITY_PASS_MAX_INFLIGHT, slate=16) runs the verify 16-way over a PER-THREAD judge
    # client (I-arch-007 ITEM 2a, entailment_judge.py threading.local — deadlock-safe), and the
    # caller's PG_CREDIBILITY_PASS_WALL_S=3000 wall bounds the whole pass. Faithfulness STRENGTHENED.
    baskets = _assemble_baskets(
        graph, weight_mass, annotated, credibility_by_evidence,
        verify_fn=verify_sentence_provenance,
        max_inflight=max_inflight,
    )

    # ── sentence -> claim_cluster_id binding (design §6): evidence_id -> the cluster
    #    id(s) its atomic claim(s) belong to. The resolve sites today carry only cited
    #    tokens (each an evidence_id), so this lets the render layer (P5.x) map a cited
    #    token to the basket whose verified count it should surface. Reference data only.
    cluster_id_by_evidence: dict[str, list[str]] = {}
    for claim in (graph.claims or []):
        eid = str(getattr(claim, "evidence_id", "") or "")
        ccid = str(getattr(claim, "claim_cluster_id", "") or "")
        if not eid or not ccid:
            continue
        bucket = cluster_id_by_evidence.setdefault(eid, [])
        if ccid not in bucket:
            bucket.append(ccid)

    return CredibilityAnalysis(
        credibility_by_evidence=credibility_by_evidence,
        origin_by_evidence=origin_by_evidence,
        claims=graph.claims,
        edges=graph.edges,
        weight_mass=weight_mass,
        baskets=baskets,
        cluster_id_by_evidence=cluster_id_by_evidence,
    )


# ─────────────────────────────────────────────────────────────────────────────
# I-cred-008b (#1162) — the SHARED per-claim disclosure populate+carrier+coverage
# helper, called at ALL FOUR cited-prose resolve sites (legacy _run_section,
# fact-dedup re-resolve, V30 contract runner, quantified-analysis). ONE copy of
# this faithfulness-critical logic so it cannot drift across the four sites.
# ─────────────────────────────────────────────────────────────────────────────

def _cited_evidence_ids_for_coverage(sv: Any) -> list[str]:
    """The cited evidence_ids on a RESOLVER-EMITTED SentenceVerification (its tokens)."""
    out: list[str] = []
    for token in (getattr(sv, "tokens", None) or []):
        eid = str(getattr(token, "evidence_id", "") or "")
        if eid:
            out.append(eid)
    return out


def apply_disclosure_to_svs(svs: list, analysis: "CredibilityAnalysis") -> list:
    """Populate the four advisory disclosure fields on each resolver-emitted SV, then carry the
    P3 certainty downgrade — ONE shared implementation for all four cited-prose resolve sites.

    Steps (ADVISORY only — never re-runs strict_verify, never flips ``is_verified``):
      1. COVERAGE ASSERTION (fail-LOUD): every cited token's evidence_id on these SVs MUST have
         credibility + origin coverage in ``analysis`` (both maps are co-built per-row in
         ``_run_chain``). A cited token with none ⇒ ``CredibilityPassError(abort_credibility_coverage_gap)``.
         Scoped to RESOLVER-EMITTED cited SVs (the SVs handed to ``resolve_provenance_to_citations``),
         NOT every ``[N]`` marker in deterministic tables/timelines — those never become SVs at the
         resolve sites, so they are excluded for free (Codex I-cred-012 iter-5 P2-3).
      2. POPULATE: the EvidenceCredibility→float adaptation
         (``{eid: ec.credibility_weight}``) feeds ``populate_disclosure`` (which expects FLOAT weights,
         not the EvidenceCredibility object), populating span_verdict / credibility_weight /
         independent_origin_count / certainty_label.
      3. P3 CERTAINTY CARRIER (Codex I-cred-012 iter-5 P2): ``populate_disclosure`` derives certainty
         from credibility/origins ONLY; it does NOT see the P3 supersession downgrade. So for each
         populated SV whose cited evidence carries ``certainty_downgrade=True``, cap its certainty_label
         (never above "moderate") and surface the source's ``soft_warning`` on the SV's ``soft_warnings``.

    Inputs are NOT mutated; ``populate_disclosure`` returns NEW SVs via ``dataclasses.replace``.
    """
    from src.polaris_graph.synthesis.disclosure_population import populate_disclosure

    cred_by_ev = analysis.credibility_by_evidence or {}
    origin_by_ev = analysis.origin_by_evidence or {}

    # ── Step 1: coverage assertion (fail-loud BEFORE populate) ──
    for sv in (svs or []):
        for eid in _cited_evidence_ids_for_coverage(sv):
            if eid not in cred_by_ev or eid not in origin_by_ev:
                raise CredibilityPassError(
                    "abort_credibility_coverage_gap: a cited evidence_id "
                    f"({eid!r}) emitted by the resolver has no credibility/origin coverage "
                    "in the credibility analysis; refusing to disclose a claim whose source "
                    "the activated pass never scored (fail-loud, never a false-green advisory)"
                )

    # ── Step 2: EvidenceCredibility → FLOAT adaptation, then populate ──
    cred_floats = {
        eid: ec.credibility_weight for eid, ec in cred_by_ev.items()
    }
    # I-arch-002 [10] / design §5 FIX-4 (Reading A) — Codex Slice-B P1: thread the
    # per-claim baskets + the evidence_id->claim_cluster_id binding (both built by
    # _run_chain on this CredibilityAnalysis) into populate_disclosure so the
    # OVERWRITE of independent_origin_count -> verified_support_origin_count actually
    # reaches the operator-visible claim_disclosure.json emit
    # (run_honest_sweep_r3.py:353 / quantified_analysis.py:539 both read this field
    # off kept_sentences_pre_resolve). Pre-fix apply_disclosure_to_svs omitted these,
    # so the clustered (not-verified) count still leaked to the JSON. OFF byte-identity
    # is structural: this whole function only runs when credibility_analysis is not
    # None (itself gated on PG_SWEEP_CREDIBILITY_REDESIGN at every call site); when the
    # flag is OFF baskets is empty / the binding is empty, so populate_disclosure's
    # _surfaced_verified_count returns None and the legacy clustered count is preserved.
    populated = populate_disclosure(
        svs, cred_floats, origin_by_ev,
        baskets=getattr(analysis, "baskets", None),
        cluster_id_by_evidence=getattr(analysis, "cluster_id_by_evidence", None),
    )

    # ── Step 3: P3 certainty carrier (downgrade + soft_warning surface) ──
    out: list = []
    for sv in populated:
        downgrade = False
        warnings: list[str] = []
        for eid in _cited_evidence_ids_for_coverage(sv):
            ec = cred_by_ev.get(eid)
            if ec is None:
                continue
            if bool(getattr(ec, "certainty_downgrade", False)):
                downgrade = True
                warn = getattr(ec, "soft_warning", None)
                if warn:
                    warnings.append(str(warn))
        if not downgrade:
            out.append(sv)
            continue
        # Cap certainty at "moderate" (never "high") when any cited source was P3-downgraded.
        new_label = sv.certainty_label
        if new_label == "high":
            new_label = "moderate"
        existing_warnings = list(getattr(sv, "soft_warnings", None) or [])
        for w in warnings:
            if w not in existing_warnings:
                existing_warnings.append(w)
        out.append(dataclasses.replace(
            sv,
            certainty_label=new_label,
            soft_warnings=existing_warnings,
        ))
    return out
