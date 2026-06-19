#!/usr/bin/env python3
"""I-arch-011 (#1268) — BEHAVIORAL breadth preflight (the §-1.4 replay gate for F2a).

Proves, on the BANKED drb_78 corpus_snapshot (794 generator-visible rows) and WITHOUT
any LLM / VM spend, that the F2a guard fix actually restores the 794->9 breadth collapse.
FAILS LOUD (non-zero exit) if any tier does not fire — "committed + green != wired"
(CLAUDE.md §-1.4); the acceptance is the EFFECT APPEARING in the real selection, not a
diff approval.

Why this is LLM-free and faithful (the exact run condition):
  * The Gate-B run sets PG_CREDIBILITY_LLM_JUDGE=off -> the credibility judge arrives None,
    so ``run_credibility_analysis`` runs PRIORS-ONLY (ZERO scoring LLM calls).
  * The Gate-B slate does NOT set PG_VERIFICATION_MODE (it stays "off"), so the per-member
    basket verify (``verify_sentence_provenance``) makes ZERO entailment LLM calls.
  Both judges therefore dormant -> the whole basket->enrichment back-half is DETERMINISTIC.

The tiers:
  T0 GUARD   — ``_credibility_guard_decision(judge=None, gov_suffixes=<real>, always_release=True)``
               returns "run" (the F2a fix). Pre-fix it returned "degrade" -> basket never built
               -> the 794->9 collapse. This is the one-line behavioral assertion of the fix.
  T1 BASKET  — the REAL ``run_credibility_analysis(judge=None)`` on the 794 banked rows COMPLETES
               (settles B12-COMPLETION's "hundreds of calls then fail" fear — false on the
               priors-only path) and CONSOLIDATES (>= 1 basket carries > 1 supporting member).
  T2 SURFACE — ``diagnose_unbound_supports_selection`` returns reason=="ok" and an unbound-SUPPORTS
               candidate list FAR larger than 9 (pre-F2a this returned reason="credibility_analysis_none",
               len 0). This is the breadth the enrichment section OFFERS.
  T3 RENDER  — ``build_verified_span_draft`` emits a non-empty deterministic verbatim-span draft and the
               number of DISTINCT sources that contribute a citable unit (the rendered-count upper bound
               before the unchanged strict_verify gate at section render).

Faithfulness is NEVER relaxed: every surfaced source is re-verified against its own span by the
UNCHANGED strict_verify at render; this harness only proves the candidates are OFFERED (pre-fix
they were structurally withheld). It does not move any verify gate.

Usage:
    python scripts/iarch011_breadth_preflight.py \
        [--corpus outputs/corpus_backups/extracted/drb_78_parkinsons_dbs/corpus_snapshot.json] \
        [--min-ev-ids 50]

Exit 0 == GO (breadth restored). Non-zero == NO-GO (do NOT spend the VM run).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

# Repo root on sys.path so ``src.*`` imports resolve when run as ``python scripts/...``.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# MEMBERSHIP-CEILING measurement (entailment OFF in THIS harness only — NOT in production).
# F2a-alone ships the basket verify under entailment-ENFORCE (the PG_STRICT_VERIFY_ENTAILMENT
# default; F2b was reverted). Running 767 real entailment LLM calls locally would be slow + costly,
# so this harness sets entailment OFF to measure the MECHANICAL membership CEILING fast and free:
# it proves the guard runs, the basket BUILDS, and the breadth enrichment SURFACES candidates.
# The entailment-enforced run will CULL this ceiling down (a member whose span does not entail the
# claim is dropped) — so T2/T3 here are an UPPER BOUND; the real entailment-enforced cited count is
# proven on the VM (16-way bounded-parallel under the 3000s wall). This is HONEST, not a relaxation:
# production keeps enforce; only this offline ceiling probe disables it.
os.environ["PG_STRICT_VERIFY_ENTAILMENT"] = "off"

_DEFAULT_CORPUS = (
    "outputs/corpus_backups/extracted/drb_78_parkinsons_dbs/corpus_snapshot.json"
)
_EV_MARKER_RE = re.compile(r"\[([^\[\]]+)\]")


def _fail(msg: str) -> None:
    print(f"\n[PREFLIGHT][NO-GO] {msg}", flush=True)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="I-arch-011 breadth preflight (F2a)")
    ap.add_argument("--corpus", default=_DEFAULT_CORPUS)
    ap.add_argument(
        "--min-ev-ids", type=int, default=50,
        help="minimum unbound-SUPPORTS candidates required to declare GO (>9 is the literal "
             "collapse threshold; 50 is a conservative breadth bar)",
    )
    args = ap.parse_args()

    if not os.path.exists(args.corpus):
        _fail(f"corpus_snapshot not found: {args.corpus}")

    print(f"[PREFLIGHT] loading {args.corpus}", flush=True)
    snap = json.load(open(args.corpus, encoding="utf-8"))
    rows = snap.get("evidence_for_gen") or []
    question = snap.get("question") or ""
    domain = snap.get("domain") or None
    if not rows:
        _fail("corpus_snapshot has no evidence_for_gen rows")
    # Mirror production: evidence_pool = {evidence_id: row}; pass its values to the pass.
    evidence_pool = {}
    for r in rows:
        eid = str((r or {}).get("evidence_id") or "").strip()
        if eid:
            evidence_pool.setdefault(eid, r)
    pool_rows = list(evidence_pool.values())
    print(
        f"[PREFLIGHT] rows={len(rows)} distinct_ev_ids={len(evidence_pool)} "
        f"domain={domain!r} q='{question[:70]}...'",
        flush=True,
    )

    from src.polaris_graph.authority.data_loader import load_authority_data
    gov = tuple(load_authority_data().get("psl_gov_suffixes") or ())
    if not gov:
        _fail("psl_gov_suffixes empty (authority data did not load)")
    print(f"[PREFLIGHT] psl_gov_suffixes={len(gov)}", flush=True)

    # ── T0 GUARD ─────────────────────────────────────────────────────────────────
    from src.polaris_graph.generator.multi_section_generator import (
        _credibility_guard_decision,
    )
    decision = _credibility_guard_decision(
        judge=None, gov_suffixes=gov, always_release=True,
    )
    print(f"\n[T0 GUARD] judge=None, gov_suffixes present, always_release=True -> {decision!r}")
    if decision != "run":
        _fail(
            f"F2a guard regression: expected 'run' (priors-only basket build), got {decision!r}. "
            f"Pre-F2a this was 'degrade' -> credibility_analysis=None -> 794->9 collapse."
        )
    # And the legacy fail-closed posture is preserved when always_release is OFF.
    legacy = _credibility_guard_decision(judge=None, gov_suffixes=gov, always_release=False)
    if legacy != "raise":
        _fail(f"legacy always-release-OFF posture broken: expected 'raise', got {legacy!r}")
    # gov_suffixes-missing still degrades/raises (intact, NOT collapsed into the judge case).
    govmiss = _credibility_guard_decision(judge=None, gov_suffixes=(), always_release=True)
    if govmiss != "degrade":
        _fail(f"gov_suffixes-missing branch broken: expected 'degrade', got {govmiss!r}")
    print("[T0 GUARD] PASS — judge=None now RUNS priors-only; legacy + gov-missing branches intact")

    # ── T1 BASKET ────────────────────────────────────────────────────────────────
    from src.polaris_graph.synthesis.credibility_pass import run_credibility_analysis
    print("\n[T1 BASKET] running REAL run_credibility_analysis(judge=None) on the banked rows "
          "(entailment-OFF in this harness = MEMBERSHIP CEILING; prod ships enforce) ...",
          flush=True)
    # Watchdog: the advisory basket verify previously hung on a SERIAL per-member entailment
    # network call (767 members). If F2b did not neutralize it, this never returns — so run it
    # in a worker thread and FAIL LOUD on a 120s join timeout instead of hanging the harness.
    import threading
    _result: dict = {}
    def _run():
        try:
            _result["analysis"] = run_credibility_analysis(
                question, pool_rows, gov_suffixes=gov, domain=domain, judge=None,
            )
        except Exception as exc:  # noqa: BLE001 — B12's "then fail" condition; capture + surface
            import traceback
            _result["error"] = exc
            _result["tb"] = traceback.format_exc()
    t0 = time.time()
    th = threading.Thread(target=_run, daemon=True)
    th.start()
    th.join(timeout=120)
    elapsed = time.time() - t0
    if th.is_alive():
        _fail(
            f"run_credibility_analysis(judge=None) DID NOT RETURN in {elapsed:.0f}s — the advisory "
            f"per-member entailment HANG is NOT neutralized. F2b ineffective; do NOT spend the VM run."
        )
    if "error" in _result:
        print(_result.get("tb", ""))
        _fail(f"run_credibility_analysis(judge=None) RAISED "
              f"({type(_result['error']).__name__}: {_result['error']}) — B12's 'then fail' materialized")
    analysis = _result["analysis"]
    baskets = list(getattr(analysis, "baskets", None) or [])
    member_counts = [
        len(getattr(b, "supporting_members", None) or ()) for b in baskets
    ]
    multi = sum(1 for c in member_counts if c > 1)
    max_members = max(member_counts) if member_counts else 0
    total_support = 0
    for b in baskets:
        for m in (getattr(b, "supporting_members", None) or ()):
            if str(getattr(m, "span_verdict", "")).strip().upper() == "SUPPORTS":
                total_support += 1
    print(
        f"[T1 BASKET] completed in {elapsed:.1f}s | baskets={len(baskets)} "
        f"multi_member_baskets={multi} max_members={max_members} total_SUPPORTS_members={total_support}"
    )
    if not baskets:
        _fail("run_credibility_analysis(judge=None) produced ZERO baskets — basket never built")
    if multi < 1:
        _fail(
            "consolidation did NOT fire: no basket carries >1 supporting member "
            f"(max_members={max_members}). The breadth lever needs multi-source baskets."
        )
    print("[T1 BASKET] PASS — priors-only pass COMPLETES fast and CONSOLIDATES (multi-source baskets)")

    # ── T2 SURFACE ───────────────────────────────────────────────────────────────
    from src.polaris_graph.generator.weighted_enrichment import (
        diagnose_unbound_supports_selection,
    )
    # contract_plans=[] -> excluded_bound=0 -> UPPER bound on surfaced breadth (the real run
    # excludes only the ~5 contract-bound entities, a negligible reduction). Honest approximation.
    wfe = diagnose_unbound_supports_selection(
        evidence_pool=evidence_pool, credibility_analysis=analysis, contract_plans=[],
    )
    print(
        f"\n[T2 SURFACE] reason={wfe.reason!r} ev_ids={len(wfe.ev_ids)} "
        f"baskets_seen={wfe.baskets_seen} supports_members_seen={wfe.supports_members_seen} "
        f"excluded_bound={wfe.excluded_bound} pool_absent={wfe.excluded_pool_absent} "
        f"below_floor_kept(telemetry)={wfe.excluded_below_floor}"
    )
    if wfe.reason != "ok":
        _fail(
            f"breadth enrichment would be EMPTY (reason={wfe.reason!r}). Pre-F2a this was "
            f"'credibility_analysis_none' — if still empty, F2a did not restore the basket."
        )
    if len(wfe.ev_ids) <= 9:
        _fail(
            f"unbound-SUPPORTS candidates ({len(wfe.ev_ids)}) did not climb past the collapse "
            f"threshold (9). F2a did not widen breadth."
        )
    if len(wfe.ev_ids) < args.min_ev_ids:
        _fail(
            f"unbound-SUPPORTS candidates ({len(wfe.ev_ids)}) below the breadth bar "
            f"(--min-ev-ids={args.min_ev_ids}). Investigate finding_dedup consolidation (F1) or "
            f"PG_RELEVANCE_FLOOR ordering — surgically, NEVER a cap/floor/target (§-1.3)."
        )
    print(f"[T2 SURFACE] PASS — {len(wfe.ev_ids)} unbound-SUPPORTS candidates surfaced (was 0 pre-F2a)")

    # ── T3 RENDER (upper bound, deterministic) ───────────────────────────────────
    from src.polaris_graph.generator.weighted_enrichment import build_verified_span_draft
    # FIX-K is the actual render mode (PG_BREADTH_ENRICHMENT_RENDER_VERIFIED_SPANS=1 on the slate).
    draft = build_verified_span_draft(wfe.ev_ids, evidence_pool)
    marker_ids = set(_EV_MARKER_RE.findall(draft or ""))
    contributing = {mid for mid in marker_ids if mid in evidence_pool}
    print(
        f"\n[T3 RENDER] verified-span draft len={len(draft)} chars | "
        f"distinct contributing sources (pre-strict_verify)={len(contributing)}"
    )
    if not draft.strip():
        _fail("build_verified_span_draft produced an EMPTY draft — nothing would render")
    if len(contributing) <= 9:
        _fail(
            f"only {len(contributing)} sources contribute a citable verbatim unit (<=9). The "
            f"rendered cited-source count would not climb. Investigate the junk-screen / unit split."
        )
    print(f"[T3 RENDER] PASS — {len(contributing)} sources contribute a deterministic citable unit")

    # ── VERDICT ──────────────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("[PREFLIGHT][GO] F2a (entailment-ENFORCE in prod) RESTORES the breadth CEILING on drb_78:")
    print(f"   T0 guard judge=None -> 'run' (priors-only basket build)")
    print(f"   T1 priors-only pass: {elapsed:.1f}s, {multi} multi-source baskets (max {max_members})")
    print(f"   T2 unbound-SUPPORTS CEILING: {len(wfe.ev_ids)}  (collapse was 9)")
    print(f"   T3 deterministic render CEILING: {len(contributing)} distinct sources")
    print("   NOTE: T2/T3 are the entailment-OFF MEMBERSHIP CEILING (this harness only). Production")
    print("   ships entailment-ENFORCE (16-way bounded, 3000s wall); the enforced run CULLS this")
    print("   ceiling to the real cited count — proven on the VM, not here. Faithfulness NEVER relaxed:")
    print("   every cited corroborator is entailment-verified by the basket verify under enforce.")
    print("=" * 72)
    sys.exit(0)


if __name__ == "__main__":
    main()
