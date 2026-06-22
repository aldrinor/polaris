#!/usr/bin/env python3
"""beatboth011 (#1289) defect #8 — contract-slot binding / false-gap REGRESSION HARNESS.

FAIL-LOUD offline harness (no network, no LLM, no faithfulness-engine call).

It exercises the REAL ``_basket_fallback_corroborators_for_slot`` join in
``src/polaris_graph/generator/contract_section_runner.py`` to PROVE the three
faithfulness invariants that govern whether an existing basket member may be
re-bound to a contract slot that would otherwise render a disclosed gap:

  (a) a slot with no direct finding BUT >=2 VERIFIED basket members that
      co-cluster with the slot's bound entity -> those members are RETURNED as
      bind candidates (no false gap).
  (b) a slot with NO co-clustered verified member -> the join returns [] so the
      gap disclosure REMAINS (no fabricated binding).
  (c) an UNVERIFIED member (absent from the basket SUPPORTS index, or a
      content-less / sub-floor span) is NEVER returned -> never bound.

WHY THIS HARNESS EXISTS (the drb_72 finding — recorded, NOT papered over):
  The §-1.1 audit of outputs/p6_postfix_resume/workforce/drb_72_ai_labor/report.md
  flagged ``acemoglu_restrepo_robots_jobs`` as a FALSE GAP. Investigation of the
  REAL run data showed:
    * the contract entity's DOI fetch (10.1086/705716) returned a
      ``metadata_only`` SHELL (direct_quote == "", 0 chars) -> the slot's only
      bound entity is content-less, so it produced no AtomicClaim and is ABSENT
      from cluster_id_by_evidence;
    * the successfully-fetched copies of the same paper (ev_228 NBER w23285,
      ev_224 MIT) entered via GENERAL retrieval, were NEVER bound to the contract
      entity, were NEVER clustered, and are absent from all 314 basket members
      (0 hits in reasoning_trace.jsonl) -> they were NEVER entailment-verified.
  Therefore the basket-fallback CORRECTLY returns [] for this slot: there is no
  VERIFIED corroborator reachable. Binding ev_228/ev_224 would require a
  query_origin / title match — a CROSS-CLAIM relaxation the file's own docstring
  (lines 386-397) and CLAUDE.md §-1.3 / §-1.1 forbid (the same query_origin tag
  is carried by off-claim sources e.g. ev_247 "did robots swing the 2016
  election", ev_244 "Robots Create Jobs"; strict_verify checks span-grounding,
  NOT slot/claim identity, so it would NOT backstop a wrong binding).

  The user-visible false gap is REAL, but its fix is UPSTREAM (retrieval ->
  contract-entity binding -> clustering: bind/cluster the fetched copy to the
  contract entity so it gets VERIFIED), NOT a re-route of unverified pool members
  in this file. This harness guards the in-file invariants so a future change
  cannot silently start binding unverified members.

Exit 0 iff every invariant holds; exit 1 (loud) on any regression.
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _load_join():
    from src.polaris_graph.generator.contract_section_runner import (
        _basket_fallback_corroborators_for_slot,
        _MIN_VERIFIABLE_SPAN_CHARS,
    )
    return _basket_fallback_corroborators_for_slot, _MIN_VERIFIABLE_SPAN_CHARS


def _pool_row(eid: str, quote: str) -> dict:
    return {"evidence_id": eid, "direct_quote": quote, "title": eid, "url": ""}


def main() -> int:
    failures: list[str] = []
    try:
        join, min_span = _load_join()
    except Exception:  # pragma: no cover - import wiring failure is itself a fail
        traceback.print_exc()
        print("HARNESS FAIL: could not import the real join function", file=sys.stderr)
        return 1

    good_span = "x" * (min_span + 20)   # a real verifiable span (>= floor)
    short_span = "x" * (min_span - 1)   # sub-floor -> not verifiable

    # The slot's bound entity (a real, clustered entity that DID produce a claim).
    slot_bound_eid = "slot_primary"
    slot_cluster = "clm_robots_jobs"

    # ── case (a): slot bound entity co-clusters with 2 VERIFIED basket members ─
    # cluster_id_by_evidence maps the slot's bound entity to EXACTLY ONE cluster
    # (anti-cross-claim: a multi-cluster source is excluded). The basket SUPPORTS
    # index lists the two independently span-verified corroborators for that
    # cluster, both carrying real verifiable prose in the pool.
    cluster_idx = {slot_bound_eid: [slot_cluster]}
    supports_idx = {slot_cluster: ["ev_corro_a", "ev_corro_b"]}
    pool = {
        "ev_corro_a": _pool_row("ev_corro_a", good_span),
        "ev_corro_b": _pool_row("ev_corro_b", good_span),
    }
    got_a = join(
        slot_entity_ids=[slot_bound_eid],
        cluster_id_by_evidence=cluster_idx,
        basket_supports_by_cluster=supports_idx,
        evidence_pool=pool,
        already_bound={slot_bound_eid},
    )
    if sorted(got_a) != ["ev_corro_a", "ev_corro_b"]:
        failures.append(
            f"(a) expected 2 verified co-clustered members to bind, got {got_a!r}"
        )

    # ── case (b): NO co-clustered verified member -> gap MUST remain ───────────
    # The slot's bound entity is a content-less SHELL: it produced no claim, so it
    # is ABSENT from cluster_id_by_evidence (the exact drb_72 shape). The join
    # walks slot-entity -> cluster and finds nothing -> returns []. The disclosed
    # gap therefore stays. (Also covers a slot whose entity maps to a cluster that
    # simply has no SUPPORTS members.)
    got_b_shell = join(
        slot_entity_ids=["shell_entity_no_cluster"],
        cluster_id_by_evidence={},                 # shell never clustered
        basket_supports_by_cluster=supports_idx,   # baskets exist, just not reachable
        evidence_pool=pool,
        already_bound={"shell_entity_no_cluster"},
    )
    if got_b_shell != []:
        failures.append(
            f"(b) shell-bound slot must yield NO binding (gap remains), got {got_b_shell!r}"
        )
    got_b_empty = join(
        slot_entity_ids=[slot_bound_eid],
        cluster_id_by_evidence=cluster_idx,
        basket_supports_by_cluster={slot_cluster: []},  # cluster has no SUPPORTS
        evidence_pool=pool,
        already_bound={slot_bound_eid},
    )
    if got_b_empty != []:
        failures.append(
            f"(b) cluster with no SUPPORTS member must yield no binding, got {got_b_empty!r}"
        )

    # ── case (c): UNVERIFIED member is NEVER bound ────────────────────────────
    # c1: a member absent from the basket SUPPORTS index (never entailment-
    #     verified) — this is the literal ev_228/ev_224 drb_72 situation — must
    #     NOT be returned even though it sits in the pool with a real quote.
    pool_c1 = dict(pool)
    pool_c1["ev_unverified"] = _pool_row("ev_unverified", good_span)
    got_c1 = join(
        slot_entity_ids=[slot_bound_eid],
        cluster_id_by_evidence=cluster_idx,
        basket_supports_by_cluster=supports_idx,  # ev_unverified NOT in here
        evidence_pool=pool_c1,
        already_bound={slot_bound_eid},
    )
    if "ev_unverified" in got_c1:
        failures.append(
            f"(c1) a pool member NOT in the SUPPORTS index was bound: {got_c1!r}"
        )

    # c2: a SUPPORTS-listed member whose pool span is sub-floor (content-less /
    #     metadata-only shell corroborator) must NOT be returned — it cannot
    #     rescue the slot because it carries no verifiable prose.
    supports_c2 = {slot_cluster: ["ev_corro_a", "ev_shellish"]}
    pool_c2 = {
        "ev_corro_a": _pool_row("ev_corro_a", good_span),
        "ev_shellish": _pool_row("ev_shellish", short_span),  # sub-floor span
    }
    got_c2 = join(
        slot_entity_ids=[slot_bound_eid],
        cluster_id_by_evidence=cluster_idx,
        basket_supports_by_cluster=supports_c2,
        evidence_pool=pool_c2,
        already_bound={slot_bound_eid},
    )
    if "ev_shellish" in got_c2:
        failures.append(
            f"(c2) a sub-floor (content-less) member was bound: {got_c2!r}"
        )
    if "ev_corro_a" not in got_c2:
        failures.append(
            f"(c2) the genuine verified member should still bind, got {got_c2!r}"
        )

    # c3: anti-cross-claim — a slot whose bound entity maps to MORE THAN ONE
    #     cluster is ambiguous and must yield NO corroborators (mirrors
    #     verified_corroborators_for_tokens; prevents attributing one source to
    #     one claim when it spans many).
    got_c3 = join(
        slot_entity_ids=[slot_bound_eid],
        cluster_id_by_evidence={slot_bound_eid: [slot_cluster, "clm_other"]},
        basket_supports_by_cluster=supports_idx,
        evidence_pool=pool,
        already_bound={slot_bound_eid},
    )
    if got_c3 != []:
        failures.append(
            f"(c3) multi-cluster (ambiguous) bound entity must yield no binding, got {got_c3!r}"
        )

    if failures:
        print("HARNESS FAIL — faithfulness/binding invariant regressed:", file=sys.stderr)
        for f in failures:
            print("  - " + f, file=sys.stderr)
        return 1

    print(
        "HARNESS PASS: (a) 2 verified co-clustered members bind; "
        "(b) no-match -> gap remains; (c) unverified/sub-floor/ambiguous never bind. "
        "NOTE: drb_72 acemoglu_restrepo_robots_jobs is case (b/c) — ev_228/ev_224 are "
        "NOT verified basket members, so the gap CORRECTLY remains; the fix is upstream "
        "(retrieval->contract-binding->clustering), not in this file."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
