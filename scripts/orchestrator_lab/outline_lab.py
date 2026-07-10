"""S4 OUTLINE offline hamster harness (Design 5 §8).

Runs the S4 orchestrator's DETERMINISTIC segments ALONE on a banked bank-file (LAW II: real
fetched rows only; the fixture under tests/fixtures/ is a hand-built branch-coverage miniature,
labelled as such — NOT a live corpus). Two OFFLINE modes, both pure (no LLM, no network),
seconds per iteration so a defect can be read line-by-line, root-caused, patched, re-run:

  digest     — build the basket-digest menu + the ORCH-2 requirements block, print the menu and
               a coverage table (every pool row -> basket OR singleton). Proves the 100%-of-pool
               honesty invariant on the bank.
  apply-dry  — apply a RECORDED reviser op list through parse + apply, print the op verdicts,
               the recompose (RE-OPEN) set, the kept-byte-identical set, and deferred/rejected
               ops. This is where apply-logic bugs are hunted (Design 5 §8 mode `apply-dry`).

The LIVE ``plan`` mode makes ONE real GLM outline call and belongs to the VM hamster (the running
generator, box2) — it is NOT runnable offline (no model creds) and refuses loudly rather than
faking a call (LAW II). It drives the full S4 outline path on a banked cp3 bank: basket-digest +
ORCH-2 requirements block -> live outline -> required-title conform/reorder -> deterministic
basket_ids backfill -> orphan check -> cp4 write+load (verdict-leak guarded). ``revise`` (the live
reviser leg) still belongs to the compose stage and this offline-first harness refuses it.

Bank file shape (JSON): {evidence:[{evidence_id,title,statement,tier},...],
clusters:[{representative_index,member_indices,corroboration_count,member_hosts},...],
plans:[{title,focus,ev_ids,basket_ids}], section_results:{title:{...}},
reviser_output:{ops:[...],gap_queries:[...],revision_needed:bool}, deliverable:{...}, scope:{...}}.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.polaris_graph.generator.outline_digest import (  # noqa: E402
    build_outline_digest,
    build_requirements_block,
)
from src.polaris_graph.generator.outline_revise import (  # noqa: E402
    apply_revision_ops,
    build_section_outcomes,
    find_orphan_baskets,
    parse_revision_ops,
    plan_signature,
)


def _load_bank(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _clusters(bank: dict) -> list[SimpleNamespace]:
    return [SimpleNamespace(**c) for c in bank.get("clusters", [])]


def _mode_digest(bank: dict) -> int:
    evidence = bank.get("evidence", [])
    menu = build_outline_digest(evidence, _clusters(bank))
    print("=== BASKET-DIGEST MENU ===")
    print(menu.render())
    print(f"\n[menu] total_chars={menu.total_chars} degraded={menu.degraded} "
          f"baskets={len(menu.basket_lines)} singletons={len(menu.singleton_lines)}")

    block = build_requirements_block(bank.get("deliverable"), bank.get("scope"))
    print("\n=== ORCH-2 REQUIREMENTS BLOCK ===")
    print(block if block else "(empty — no deliverable/scope asks => byte-identical no-append)")

    print("\n=== COVERAGE TABLE (100%-of-pool honesty) ===")
    covered = menu.covered_ev_ids()
    for row in evidence:
        ev_id = str(row.get("evidence_id", ""))
        where = menu.ev_id_to_basket.get(ev_id, "singleton")
        print(f"  {ev_id:<10} -> {where}")
    pool = {str(r.get('evidence_id', '')) for r in evidence if r.get('evidence_id')}
    missing = pool - covered
    print(f"\n[coverage] pool={len(pool)} covered={len(covered & pool)} missing={sorted(missing)}")
    return 0 if not missing else 1


def _mode_apply_dry(bank: dict) -> int:
    plans = bank.get("plans", [])
    reviser_output = bank.get("reviser_output")
    if reviser_output is None:
        print("[apply-dry] bank has no `reviser_output` to replay — nothing to apply.")
        return 1
    allowed = {str(e) for p in plans for e in (p.get("ev_ids") or [])}
    for p in plans:
        allowed |= {str(e) for e in (p.get("ev_ids") or [])}
    # allow ev_ids referenced by the reviser that live in the pool but not yet on a plan
    allowed |= {str(e) for e in bank.get("pool_ev_ids", [])}
    titles = [str(p.get("title", "")) for p in plans]

    outcomes = build_section_outcomes(
        plans, bank.get("section_results", {}),
        basket_members=bank.get("basket_members", {}),
        basket_corroboration=bank.get("basket_corroboration", {}),
    )
    orphans = find_orphan_baskets(plans, bank.get("basket_corroboration", {}))
    print("=== SECTION OUTCOME DIGESTS (the section checklist) ===")
    for oc in outcomes:
        print(f"  {oc.title!r}: verified={oc.verified_sentence_count} kept={oc.kept_fraction} "
              f"dropped={oc.dropped} unused={oc.unused_ev_ids} uncovered={oc.uncovered_baskets} "
              f"undersupplied={oc.undersupplied}")
    print(f"[orphan_baskets] {orphans}")

    sigs_before = {str(p.get('title', '')): plan_signature(p) for p in plans}
    parsed = parse_revision_ops(reviser_output, allowed_ev_ids=allowed, plan_titles=titles)
    applied = apply_revision_ops(plans, parsed, outcomes=outcomes)

    print("\n=== APPLY RESULT ===")
    print(f"[parse] accepted={len(parsed.ops)} rejected={len(parsed.rejected)} "
          f"parse_failed={parsed.parse_failed} revision_needed={parsed.revision_needed}")
    for rej in parsed.rejected:
        print(f"   REJECT {rej.get('reason_code')}: {rej.get('op')}")
    print(f"[apply] changed={applied.changed} recompose={applied.recompose_titles} "
          f"kept={applied.kept_titles} deferred={len(applied.deferred_ops)}")
    print("\n[keep byte-identity] (kept sections must hash-equal wave-1):")
    for title in applied.kept_titles:
        after = next((plan_signature(p) for p in applied.new_plans
                      if str(p.get('title', '')) == title), None)
        same = "OK" if sigs_before.get(title) == after else "MISMATCH"
        print(f"   {title!r}: {same}")
    print("\n=== FINAL PLANS ===")
    for p in applied.new_plans:
        print(f"  {p.get('title')!r} ev_ids={p.get('ev_ids')} archetype={p.get('archetype')}")
    return 0


def _plan_to_dict(p) -> dict:
    """SectionPlan -> plain DATA dict for the cp4 payload (no verdict keys, ever)."""
    return {
        "title": str(getattr(p, "title", "")),
        "focus": str(getattr(p, "focus", "")),
        "ev_ids": list(getattr(p, "ev_ids", []) or []),
        "basket_ids": list(getattr(p, "basket_ids", []) or []),
        "archetype": str(getattr(p, "archetype", "")),
        "undersupplied": bool(getattr(p, "undersupplied", False)),
    }


def _mode_plan(bank: dict, *, model: str, run_dir: Path) -> int:
    """LIVE S4 outline (ONE real GLM call, box2 VM hamster). Drives the full path and writes cp4.

    Proves the ITER-2 acceptance on a banked cp3 bank: (a) final_plans headings == required aspects
    in exact order; (b) basket_ids non-empty where members intersect + orphan list shrinks to only
    genuine orphans; (c) degraded=False; (d) cp4 verdict-leak guard passes on write AND load."""
    # The whole point of `plan` is to exercise the basket-digest path — arm the flag loudly.
    if os.getenv("PG_OUTLINE_BASKET_DIGEST", "0").strip().lower() not in ("1", "true", "yes", "on"):
        os.environ["PG_OUTLINE_BASKET_DIGEST"] = "1"
        print("[plan] armed PG_OUTLINE_BASKET_DIGEST=1 (the basket-digest outline path under test)")

    from src.polaris_graph.generator.multi_section_generator import _call_outline  # noqa: E402
    from src.polaris_graph.generator.outline_checkpoint import (  # noqa: E402
        build_cp4_payload,
        load_cp4_outline_snapshot,
        write_cp4_outline_snapshot,
    )
    from src.polaris_graph.generator.outline_revise import find_orphan_baskets  # noqa: E402

    evidence = bank.get("evidence", [])
    clusters = _clusters(bank)
    deliverable = bank.get("deliverable")
    scope = bank.get("scope")
    question = str(bank.get("question", ""))
    domain = str(bank.get("domain", ""))
    required = [str(t).strip() for t in ((deliverable or {}).get("required_sections", []) or [])]

    # Rebuild the digest ONCE (deterministic, identical to _call_outline's own build) to derive the
    # basket corroboration/member maps used by the orphan check + the coverage cross-read.
    menu = build_outline_digest(evidence, clusters)
    basket_members = {bid: list(members) for bid, members in menu.basket_member_ev_ids.items()}
    basket_corroboration = {bid: len(members) for bid, members in menu.basket_member_ev_ids.items()}

    print(f"[plan] LIVE outline call: model={model} pool={len(evidence)} "
          f"baskets={len(menu.basket_lines)} singletons={len(menu.singleton_lines)} "
          f"required={required}")

    parse_result, retry_attempted, in_tok, out_tok = asyncio.run(_call_outline(
        question, evidence, model, 0.2, 2500,
        domain=domain, finding_clusters=clusters,
        deliverable_spec=deliverable, scope_spec=scope,
    ))
    plans = parse_result.plans
    stats = parse_result.digest_stats

    # (a) headings == required aspects, exact order
    headings = [str(p.title) for p in plans]
    order_ok = (headings == required) if required else None
    print("\n=== (a) FINAL PLAN HEADINGS ===")
    for p in plans:
        print(f"  {p.title!r} ev_ids={len(p.ev_ids)} basket_ids={len(p.basket_ids)} "
              f"undersupplied={p.undersupplied}")
    print(f"[a] headings == required (exact order): {order_ok}  (retry_attempted={retry_attempted})")

    # (b) basket_ids non-empty where members intersect + orphan list shrinks
    # baseline: plans WITHOUT the backfill (all multi-member baskets look orphaned)
    baseline_plans = [{"title": p.title, "ev_ids": p.ev_ids, "basket_ids": []} for p in plans]
    baseline_orphans = find_orphan_baskets(baseline_plans, basket_corroboration)
    final_orphans = find_orphan_baskets(plans, basket_corroboration)
    with_baskets = [p.title for p in plans if p.basket_ids]
    print("\n=== (b) BASKET_IDS BACKFILL + ORPHAN SHRINK ===")
    print(f"[b] sections carrying basket_ids: {with_baskets}")
    print(f"[b] orphan baskets BEFORE backfill: {len(baseline_orphans)}  "
          f"AFTER backfill: {len(final_orphans)}  (shrunk by {len(baseline_orphans) - len(final_orphans)})")
    # each surviving orphan is DISCLOSED in the revision audit as a reassign candidate
    revision_audit = {
        "rounds": 0,
        "orphan_baskets_after_plan": list(final_orphans),
        "orphan_reassign_candidates": [
            {"basket_id": bid, "members": basket_members.get(bid, []),
             "disposition": "reassign_candidate"}
            for bid in final_orphans
        ],
        "note": ("orphans routed to sections by the compose-stage reviser / "
                 "route_orphan_baskets_to_section_plans; each is disclosed here, never dropped"),
    }

    # (c) degraded flag from the digest telemetry
    print("\n=== (c) DIGEST TELEMETRY (digest_stats) ===")
    print(json.dumps(stats, indent=1))
    degraded_ok = (stats.get("digest_degraded") is False)
    print(f"[c] degraded == False: {degraded_ok}")

    # (d) cp4 write + load (verdict-leak guarded on BOTH)
    payload = build_cp4_payload(
        question_sha=hashlib.sha256(question.encode("utf-8")).hexdigest(),
        upstream=[{"stage": "basket", "sha": str(bank.get("cp3_sha", ""))}],
        run_config_sha="",
        flag_slate={"PG_OUTLINE_BASKET_DIGEST": "1"},
        adjustments_applied=[],
        final_plans=[_plan_to_dict(p) for p in plans],
        revision_audit=revision_audit,
        digest_stats=stats,
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    written = write_cp4_outline_snapshot(run_dir, payload)
    reloaded = load_cp4_outline_snapshot(run_dir) if written else None
    load_ok = bool(reloaded) and reloaded.get("payload", {}).get("final_plans") is not None
    print("\n=== (d) cp4 CHECKPOINT (verdict-leak guarded) ===")
    print(f"[d] wrote: {written}  reloaded_ok: {load_ok}")

    ok = bool(load_ok) and (order_ok in (True, None)) and degraded_ok
    print(f"\n[plan] ACCEPTANCE (a,c,d) ok={ok}  in_tok={in_tok} out_tok={out_tok}")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="S4 outline offline hamster harness")
    parser.add_argument("--bank", required=True, help="bank JSON file (fixture or exported run)")
    parser.add_argument("--mode", required=True,
                        choices=["digest", "apply-dry", "plan", "revise"])
    parser.add_argument("--model", default=os.getenv("PG_S4_OUTLINE_MODEL",
                        os.getenv("PG_GENERATOR_MODEL", "z-ai/glm-5.2")),
                        help="outline model for `plan` mode (default GLM-5.2)")
    parser.add_argument("--run-dir", default="outputs/s4_plan_lab",
                        help="cp4 checkpoint output dir for `plan` mode")
    args = parser.parse_args(argv)

    if args.mode == "revise":
        print("[revise] LIVE reviser leg — belongs to the compose stage (VM hamster). "
              "This offline-first harness refuses to fake a model call (LAW II). Use "
              "`digest` / `apply-dry` offline, or `plan` for the live outline call.")
        return 2

    bank = _load_bank(Path(args.bank))
    if args.mode == "digest":
        return _mode_digest(bank)
    if args.mode == "plan":
        return _mode_plan(bank, model=args.model, run_dir=Path(args.run_dir))
    return _mode_apply_dry(bank)


if __name__ == "__main__":
    raise SystemExit(main())
