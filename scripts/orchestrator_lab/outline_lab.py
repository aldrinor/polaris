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

The LIVE ``plan`` / ``revise`` modes each make one real LLM call and belong to the VM hamster
(the running generator) — they are NOT runnable offline and this harness refuses them loudly
rather than faking a call.

Bank file shape (JSON): {evidence:[{evidence_id,title,statement,tier},...],
clusters:[{representative_index,member_indices,corroboration_count,member_hosts},...],
plans:[{title,focus,ev_ids,basket_ids}], section_results:{title:{...}},
reviser_output:{ops:[...],gap_queries:[...],revision_needed:bool}, deliverable:{...}, scope:{...}}.
"""

from __future__ import annotations

import argparse
import json
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="S4 outline offline hamster harness")
    parser.add_argument("--bank", required=True, help="bank JSON file (fixture or exported run)")
    parser.add_argument("--mode", required=True,
                        choices=["digest", "apply-dry", "plan", "revise"])
    args = parser.parse_args(argv)

    if args.mode in ("plan", "revise"):
        print(f"[{args.mode}] LIVE LLM mode — requires the running generator (VM hamster). "
              "This offline harness refuses to fake a model call (LAW II). Use `digest` / "
              "`apply-dry` offline.")
        return 2

    bank = _load_bank(Path(args.bank))
    if args.mode == "digest":
        return _mode_digest(bank)
    return _mode_apply_dry(bank)


if __name__ == "__main__":
    raise SystemExit(main())
