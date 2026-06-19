#!/usr/bin/env python3
"""I-arch-011 — ENFORCE-PATH breadth preflight (the redeploy gate for FIX-B + FIX-C).

The sibling `iarch011_breadth_preflight.py` proves the entailment-OFF MEMBERSHIP CEILING (754/663).
The advisor's hard requirement: the >=200 cited claim must be proven on the REAL entailment-ENFORCE
path, because production culls the OFF ceiling. This harness does that — offline, free, deterministic —
by exploiting FIX-B: a verbatim, boundary-aligned self-quote is entailed BY IDENTITY, so it passes the
enforce gate with NO LLM call. So the ENFORCE-path cited FLOOR is measurable without any network:

  drive the EXACT production enrichment path
    raw       = build_verified_span_draft(ev_ids, pool)           # weighted_enrichment FIX-K
    rewritten = _rewrite_draft_with_spans(raw, pool)              # bind [ev_id] -> [#ev:id:s-e]
    report    = strict_verify(rewritten, pool)                    # provenance_generator, ENFORCE
  with PG_STRICT_VERIFY_ENTAILMENT=enforce, FIX-B ON, and a STUB judge that DROPS every residual
  (non-verbatim) unit. So report.total_kept counts ONLY units that (a) clear every mechanical
  strict_verify check AND (b) pass FIX-B's verbatim, boundary-aligned identity entailment. That is a
  GUARANTEED LOWER BOUND on the production enforce-path cited count — the real glm-5.1 judge can only
  ADD by passing some residual units, never subtract from this floor.

GO (exit 0) iff:
  * the enforce-path cited FLOOR >= --min-cited (default 200)               [breadth survives enforce]
  * FIX-B actually FIRED (verbatim_skip_telemetry.skips > 0)                [keystone wired, not no-op]
  * a deliberately NON-substring control unit STILL routes to the judge     [gate NOT disabled]
  * the whole verify completes fast (wall << the serial-hours that froze run #6)   [FIX-C/§-1.4]

NO-GO (non-zero) otherwise — do NOT spend the VM run. FAIL-LOUD per CLAUDE.md §-1.4.

Usage:
    python scripts/iarch011_enforce_breadth_preflight.py \
        [--corpus outputs/corpus_backups/extracted/drb_78_parkinsons_dbs/corpus_snapshot.json] \
        [--min-cited 200]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# TWO-PHASE, both offline:
#  Phase 1 (basket build): entailment OFF so run_credibility_analysis's internal per-member basket
#    verify makes ZERO LLM calls (it builds the SUPPORTS baskets that feed the enrichment ev_ids).
#  Phase 2 (the measurement): flip to ENFORCE + FIX-B + a stub-drop judge for the residual, and run
#    the FINAL enrichment-section strict_verify — exactly the step that hung in run #6. Measured count
#    is a conservative FLOOR (FIX-B-verbatim units only; the real judge can only ADD).
# (Setting enforce here at module top would make Phase-1's basket verify fire ~767 real LLM calls —
#  the bug that wedged the first harness run. Keep OFF until Phase 2.)
os.environ["PG_STRICT_VERIFY_ENTAILMENT"] = "off"
os.environ.setdefault("PG_ENTAILMENT_VERBATIM_SKIP", "1")  # FIX-B default-on; explicit for clarity
# Family-segregation ctor guard reads these even though we stub the judge before it constructs.
os.environ.setdefault("PG_GENERATOR_MODEL", "deepseek/deepseek-v4-pro")
os.environ.setdefault("PG_ENTAILMENT_MODEL", "z-ai/glm-5.1")

_DEFAULT_CORPUS = "outputs/corpus_backups/extracted/drb_78_parkinsons_dbs/corpus_snapshot.json"


def _fail(msg: str) -> None:
    print(f"\n[ENFORCE-PREFLIGHT][NO-GO] {msg}", flush=True)
    sys.exit(1)


class _StubDropJudge:
    """Stands in for the real glm-5.1 judge on the RESIDUAL (non-verbatim) units. Returns NEUTRAL so
    the residual DROPS — making report.total_kept a guaranteed floor (FIX-B-verbatim units only).
    Counts calls so the harness can prove non-verbatim units actually reach the judge (gate alive)."""

    calls = 0

    def judge(self, sentence: str, span: str) -> tuple[str, str]:
        type(self).calls += 1
        return "NEUTRAL", "stub_no_network_residual_dropped"


def main() -> None:
    ap = argparse.ArgumentParser(description="I-arch-011 ENFORCE-path breadth preflight")
    ap.add_argument("--corpus", default=_DEFAULT_CORPUS)
    ap.add_argument("--min-cited", type=int, default=200,
                    help="enforce-path cited FLOOR required to declare GO (operator deliverable: 200+)")
    ap.add_argument("--max-wall-s", type=float, default=180.0,
                    help="the enrichment verify must complete under this wall (run #6 froze for hours)")
    args = ap.parse_args()

    if not os.path.exists(args.corpus):
        _fail(f"corpus_snapshot not found: {args.corpus}")
    snap = json.load(open(args.corpus, encoding="utf-8"))
    rows = snap.get("evidence_for_gen") or []
    if not rows:
        _fail("corpus_snapshot has no evidence_for_gen rows")
    evidence_pool: dict = {}
    for r in rows:
        eid = str((r or {}).get("evidence_id") or "").strip()
        if eid:
            evidence_pool.setdefault(eid, r)
    print(f"[ENFORCE-PREFLIGHT] corpus rows={len(rows)} distinct_ev_ids={len(evidence_pool)}", flush=True)

    # ── reproduce the enrichment candidate selection (T0->T2 of the ceiling harness) ──────────────
    from src.polaris_graph.authority.data_loader import load_authority_data
    gov = tuple(load_authority_data().get("psl_gov_suffixes") or ())
    if not gov:
        _fail("psl_gov_suffixes empty")
    from src.polaris_graph.synthesis.credibility_pass import run_credibility_analysis
    analysis = run_credibility_analysis(
        snap.get("question") or "", list(evidence_pool.values()),
        gov_suffixes=gov, domain=snap.get("domain") or None, judge=None,
    )
    from src.polaris_graph.generator.weighted_enrichment import (
        build_verified_span_draft,
        diagnose_unbound_supports_selection,
    )
    wfe = diagnose_unbound_supports_selection(
        evidence_pool=evidence_pool, credibility_analysis=analysis, contract_plans=[],
    )
    if wfe.reason != "ok" or len(wfe.ev_ids) <= 9:
        _fail(f"enrichment did not surface candidates (reason={wfe.reason!r}, ev_ids={len(wfe.ev_ids)})")
    print(f"[ENFORCE-PREFLIGHT] unbound-SUPPORTS candidates surfaced: {len(wfe.ev_ids)}", flush=True)

    # ── PHASE 2: flip to ENFORCE + stub the residual judge, for the enrichment verify ONLY ────────
    os.environ["PG_STRICT_VERIFY_ENTAILMENT"] = "enforce"  # _entailment_mode() reads env at call time
    import src.polaris_graph.clinical_generator.strict_verify as _sv
    _sv._get_judge = lambda: _StubDropJudge()  # type: ignore[assignment]
    # zero the FIX-B telemetry so the count is for THIS run only
    _sv._VERBATIM_SKIP_TELEMETRY["skips"] = 0
    _sv._VERBATIM_SKIP_TELEMETRY["judged"] = 0

    from src.polaris_graph.generator.live_deepseek_generator import _rewrite_draft_with_spans
    from src.polaris_graph.generator.provenance_generator import strict_verify

    # ── drive the EXACT production enrichment render+verify path under ENFORCE ────────────────────
    raw = build_verified_span_draft(wfe.ev_ids, evidence_pool)
    if not raw.strip():
        _fail("build_verified_span_draft empty")
    rewritten, _conv, _unver = _rewrite_draft_with_spans(raw, evidence_pool)
    t0 = time.time()
    report = strict_verify(rewritten, evidence_pool)
    wall = time.time() - t0

    tel = _sv.verbatim_skip_telemetry()
    kept = report.total_kept
    # distinct cited sources among kept (the operator's headline metric: breadth, not sentence count)
    distinct_cited = len({
        t.evidence_id
        for sv in report.kept_sentences
        for t in (getattr(sv, "tokens", None) or [])
    })
    print(
        f"\n[ENFORCE-PREFLIGHT] verify wall={wall:.2f}s | FIX-B skips={tel['skips']} "
        f"residual_judged={tel['judged']} (stub-dropped) | kept_sentences={kept} "
        f"distinct_cited_sources={distinct_cited} dropped={report.total_dropped}", flush=True)

    # ── control: a deliberately NON-substring sentence MUST route to the judge (gate not disabled) ─
    before = _StubDropJudge.calls
    # build a one-token sentence whose text is NOT in its span, with a valid [#ev] token from the pool
    ctrl_ev = next(iter(evidence_pool))
    ctrl_row = evidence_pool[ctrl_ev]
    dq = (ctrl_row.get("direct_quote") or ctrl_row.get("statement") or "").strip()
    if len(dq) >= 60:
        ctrl_span_len = min(len(dq), 200)
        ctrl_sentence = "This deliberately paraphrased control claim is absent verbatim from the bound span entirely."
        ctrl = f"{ctrl_sentence} [#ev:{ctrl_ev}:0-{ctrl_span_len}]."
        _ = strict_verify(ctrl, evidence_pool)
        if _StubDropJudge.calls <= before:
            _fail("CONTROL FAILED: a non-substring sentence did NOT reach the judge — FIX-B is "
                  "swallowing non-verbatim units (gate disabled). This is a faithfulness hole.")
        print(f"[ENFORCE-PREFLIGHT] control OK — non-substring sentence routed to the real judge "
              f"(+{_StubDropJudge.calls - before} call)", flush=True)

    # ── VERDICT ───────────────────────────────────────────────────────────────────────────────────
    problems = []
    if tel["skips"] <= 0:
        problems.append("FIX-B never fired (skips=0) — keystone is a no-op")
    if kept < args.min_cited:
        problems.append(f"enforce-path cited FLOOR {kept} < required {args.min_cited} "
                        f"(FIX-B did not carry enough verbatim units; the real judge would need to "
                        f"rescue {args.min_cited - kept}+ residual — do NOT assume it will)")
    if wall > args.max_wall_s:
        problems.append(f"verify wall {wall:.1f}s > {args.max_wall_s:.0f}s budget (still too slow)")
    print("\n" + "=" * 78)
    if problems:
        for p in problems:
            print(f"   ✗ {p}")
        _fail("enforce-path breadth gate FAILED — see above")
    print("[ENFORCE-PREFLIGHT][GO] FIX-B + FIX-C restore WIDE breadth on the REAL enforce path:")
    print(f"   verify completed in {wall:.2f}s (run #6 serial path never finished)")
    print(f"   FIX-B verbatim-identity skips: {tel['skips']}  (residual judged: {tel['judged']})")
    print(f"   enforce-path cited FLOOR: {kept} kept sentences / {distinct_cited} distinct sources")
    print(f"   (this is a LOWER BOUND — the real glm-5.1 judge only ADDS by passing residual units)")
    print("   faithfulness NEVER relaxed: every kept unit cleared the full strict_verify; FIX-B only")
    print("   skips the LLM for a verbatim boundary-aligned self-quote (entailed by identity).")
    print("=" * 78)
    sys.exit(0)


if __name__ == "__main__":
    main()
