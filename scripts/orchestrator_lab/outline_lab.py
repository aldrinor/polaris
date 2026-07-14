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
same_work_groups:[{member_evidence_ids,canonical_index,same_work_id},...] (PUSH A, OPTIONAL — the
exact cp3 payload shape; absent => the digest is byte-identical to the pre-PUSH-A menu),
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
    PG_OUTLINE_DIGEST_MAX_CHARS_DEFAULT,
    _build_alias_map,
    build_outline_digest,
    build_requirements_block,
    dedup_plan_ev_ids_by_work,
)
from src.polaris_graph.generator.outline_revise import (  # noqa: E402
    PG_OUTLINE_REVISE_MAX_RECOMPOSE_DEFAULT,
    PG_OUTLINE_REVISE_ROUNDS_DEFAULT,
    apply_revision_ops,
    build_section_outcomes,
    find_orphan_baskets,
    parse_revision_ops,
    plan_signature,
)

# PUSH B: the tiers a still-unassigned singleton is disclosed BY NAME for (a T1-T3 credible source
# on no section plan is a reassign candidate the compose-stage router should pick up).
_HIGH_TIERS = {"T1", "T2", "T3"}


def _effective_s4_flag_slate(model: str) -> dict[str, str]:
    """Item 6: capture the FULL effective S4 knob set for the cp4 checkpoint. Until RunConfig (WP-0b)
    lands, these env reads ARE the run config — the checkpoint MUST record what produced it or it
    cannot prove its own provenance (the whole point of the checkpoint pivot). Values are EFFECTIVE
    (env override OR the same default the reader uses; the two token knobs mirror
    ``multi_section_generator``'s ``os.getenv(name, "16384"/"6144")`` readers).

    Item 7 (honest reporting): ``PG_OUTLINE_REVISE`` and ``PG_EXTRACT_DELIVERABLE_SPEC`` are read
    NOWHERE in the worktree (grep-verified) — they are NO-OPS, so they are deliberately NOT recorded
    here; listing them would falsely imply they were validated/active this run."""
    return {
        "PG_OUTLINE_BASKET_DIGEST": os.getenv("PG_OUTLINE_BASKET_DIGEST", "0"),
        # Item 3a: coverage-routing arm-state — the cp4 checkpoint MUST record whether the compose
        # wheel routes orphan baskets + unassigned high-tier singletons to sections
        # (PG_ROUTE_ALL_BASKETS, default-OFF; the S5-compose run slate arms it). Operator law:
        # "a winner built but left default-OFF is the still-broken loop root" — so the checkpoint
        # proves whether it was armed rather than leaving it invisible.
        "PG_ROUTE_ALL_BASKETS": os.getenv("PG_ROUTE_ALL_BASKETS", "0"),
        "PG_OUTLINE_DIGEST_MAX_CHARS": os.getenv(
            "PG_OUTLINE_DIGEST_MAX_CHARS", str(PG_OUTLINE_DIGEST_MAX_CHARS_DEFAULT)),
        "PG_OUTLINE_MIN_MAX_TOKENS": os.getenv("PG_OUTLINE_MIN_MAX_TOKENS", "16384"),
        "PG_OUTLINE_REASONING_MAX_TOKENS": os.getenv("PG_OUTLINE_REASONING_MAX_TOKENS", "6144"),
        "PG_OUTLINE_REVISE_ROUNDS": os.getenv(
            "PG_OUTLINE_REVISE_ROUNDS", str(PG_OUTLINE_REVISE_ROUNDS_DEFAULT)),
        "PG_OUTLINE_REVISE_MAX_RECOMPOSE": os.getenv(
            "PG_OUTLINE_REVISE_MAX_RECOMPOSE", str(PG_OUTLINE_REVISE_MAX_RECOMPOSE_DEFAULT)),
        "model": str(model),
    }


def _row_topic_verdict(row: dict) -> str:
    """Item 3 (THREE-VALUED): the cp4 per-candidate semantic topic verdict, read from the row's
    topic-judge stamps. THREE values so the disclosure never overstates ignorance (395/686 rows this
    run carry ``topic_offtopic_demoted``, 445 carry ``content_relevance_label=demoted`` — yet every
    candidate read as ``unjudged`` before, starving the S5 router):

      "off_subject"   — an AFFIRMATIVE deletable off-topic stamp (the SAME fail-open predicate the
                        compose router + run-level junk gate consume; a positive-relevance verdict
                        vetoes it). This is the ONLY value the orphan-basket all-members rule treats
                        as deletable — deletion semantics UNCHANGED (§-1.3.1 judge-only, fail-open).
      "demoted_weight" — a WEIGHT-demote stamp (``topic_offtopic_demoted`` truthy, OR
                        ``content_relevance_label`` in {demoted, escalated_demoted}). DISCLOSURE only:
                        the row is KEPT and routed; the S5 router now sees it is relevance-demoted.
      "unjudged"      — no stamp / any uncertainty / import-or-predicate error (FAIL-OPEN => KEEP).

    Zero routing/deletion change — only the disclosure is richer (a demoted row no longer hides as
    ``unjudged``)."""
    r = row or {}
    try:
        from src.polaris_graph.generator.junk_deletion_gate import (  # noqa: PLC0415
            is_row_deletable_offtopic,
        )
        if is_row_deletable_offtopic(r):
            return "off_subject"
    except Exception:  # noqa: BLE001 — fail-open: a judge/import error never flips a row off-topic
        pass
    if r.get("topic_offtopic_demoted") or str(
        r.get("content_relevance_label", "") or ""
    ).strip().lower() in ("demoted", "escalated_demoted"):
        return "demoted_weight"
    return "unjudged"


def _load_bank(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _clusters(bank: dict) -> list[SimpleNamespace]:
    return [SimpleNamespace(**c) for c in bank.get("clusters", [])]


def _mode_digest(bank: dict) -> int:
    evidence = bank.get("evidence", [])
    # PUSH A: feed the cp3 same_work_groups so the menu reports WORK-level corroboration and folds
    # same-work singleton copies. Absent in the bank => None => byte-identical menu.
    menu = build_outline_digest(
        evidence, _clusters(bank), same_work_groups=bank.get("same_work_groups")
    )
    print("=== BASKET-DIGEST MENU ===")
    print(menu.render())
    print(f"\n[menu] total_chars={menu.total_chars} degraded={menu.degraded} "
          f"baskets={len(menu.basket_lines)} singletons={len(menu.singleton_lines)} "
          f"singleton_folds={sum(len(v) for v in menu.singleton_alias_ev_ids.values())}")

    block = build_requirements_block(bank.get("deliverable"), bank.get("scope"))
    print("\n=== ORCH-2 REQUIREMENTS BLOCK ===")
    print(block if block else "(empty — no deliverable/scope asks => byte-identical no-append)")

    print("\n=== COVERAGE TABLE (100%-of-pool honesty) ===")
    covered = menu.covered_ev_ids()
    # PUSH A: map each folded alias back to the canonical singleton line it joined, so the table
    # still lists 100% of the pool (folded aliases are covered, never dropped).
    alias_to_canonical = {
        a: canonical
        for canonical, aliases in menu.singleton_alias_ev_ids.items()
        for a in aliases
    }
    for row in evidence:
        ev_id = str(row.get("evidence_id", ""))
        if ev_id in menu.ev_id_to_basket:
            where = menu.ev_id_to_basket[ev_id]
        elif ev_id in alias_to_canonical:
            where = f"singleton(=same-work of {alias_to_canonical[ev_id]})"
        else:
            where = "singleton"
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
    # allow ev_ids referenced by the reviser that live in the pool but not yet on a plan. PUSH A
    # part (3): pool_ev_ids carries EVERY member incl. every same-work alias, so a planner/reviser
    # reference to a folded alias is never rejected as unknown.
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
<<<<<<< Updated upstream
<<<<<<< Updated upstream
    # item 13: when the bank has a required-section structure, thread it so apply restricts ops to
    # keep/reassign and cannot break the user's exact-N-in-order contract.
    _required = [
        str(t).strip()
        for t in ((bank.get("deliverable") or {}).get("required_sections", []) or [])
        if str(t).strip()
    ]
    applied = apply_revision_ops(plans, parsed, outcomes=outcomes, required_titles=_required)
=======
=======
>>>>>>> Stashed changes
    # Fable item 6: thread the digest ev_id->basket map so apply RE-BACKFILLS basket_ids on the
    # recomposed sections (a reassign that homes an orphan basket's members must clear it from the
    # orphan list — the compose router is ev-overlap-keyed, find_orphan_baskets is basket_id-keyed;
    # the re-backfill makes them agree). Built from the bank's basket_members (bid -> member ev_ids).
    ev_id_to_basket = {
        str(ev): str(bid)
        for bid, members in (bank.get("basket_members", {}) or {}).items()
        for ev in (members or [])
    }
    applied = apply_revision_ops(
        plans, parsed, outcomes=outcomes, ev_id_to_basket=ev_id_to_basket,
    )
<<<<<<< Updated upstream
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes

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
        print(f"  {p.get('title')!r} ev_ids={p.get('ev_ids')} "
              f"basket_ids={p.get('basket_ids')} archetype={p.get('archetype')}")
    # Fable item 6: orphan check RE-RUN after apply — a reassign that homed an orphan basket's
    # members must now show that basket cleared (the re-backfilled basket_ids reconcile the two
    # orphan definitions). Uses the same work-level corroboration map the digest reports.
    orphans_after = find_orphan_baskets(applied.new_plans, bank.get("basket_corroboration", {}))
    print(f"[orphan_baskets AFTER apply] {orphans_after}  (before apply: {orphans})")
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
    genuine orphans; (c) degraded=False; (d) cp4 verdict-leak guard passes on write AND load; plus
    PUSH A (e) per-section distinct-work fraction and PUSH B full unassigned-singleton disclosure."""
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
    same_work_groups = bank.get("same_work_groups")  # PUSH A: cp3 payload shape (may be None)
    required = [str(t).strip() for t in ((deliverable or {}).get("required_sections", []) or [])]

    # Rebuild the digest ONCE (deterministic, identical to _call_outline's own build) to derive the
    # basket corroboration/member maps used by the orphan check + the coverage cross-read. PUSH A:
    # same_work_groups threaded so basket corroboration is WORK-level (matches what the model saw).
    # item 4a: prioritize_tier1 matches the live _call_outline build (T1 singletons lead). Sorting is
    # display-only, so the basket/singleton MAPS derived below are unchanged — the flag only keeps the
    # cross-read faithful to what the planner actually read.
    menu = build_outline_digest(
        evidence, clusters, same_work_groups=same_work_groups, prioritize_tier1=True,
    )
    basket_members = {bid: list(members) for bid, members in menu.basket_member_ev_ids.items()}
    basket_corroboration = dict(menu.basket_work_corroboration)

    print(f"[plan] LIVE outline call: model={model} pool={len(evidence)} "
          f"baskets={len(menu.basket_lines)} singletons={len(menu.singleton_lines)} "
          f"singleton_folds={sum(len(v) for v in menu.singleton_alias_ev_ids.values())} "
          f"required={required}")

    # PUSH A: feed the same_work_groups INTO the live outline call so the PLANNER reads work-level
    # corroboration + folded singletons (the model's actual input, not just the cross-read rebuild).
    # W0 un-starve (docs/fsr_build_plan.md "AGENTIC OUTLINER LOOP" section): the LIVE outline
    # call was hardcoded to max_tokens=2500 (the \_call_outline floor bumps it to 16384, but that
    # is still ~8x under the model's real completion budget). PG_OUTLINE_MAX_TOKENS (default
    # 131072) + PG_OUTLINE_REASONING_MAX_TOKENS (default 32768, set in multi_section_generator.py)
    # give the planner real room; unset env keeps this byte-identical to the old 16384 floor path
    # ONLY if PG_OUTLINE_MAX_TOKENS is explicitly lowered — the new default is intentionally raised
    # per §9.1.8 (reasoning + generation tokens ALWAYS MAX, never starve).
    _outline_lab_max_tokens = int(os.getenv("PG_OUTLINE_MAX_TOKENS", "131072"))
    parse_result, retry_attempted, in_tok, out_tok = asyncio.run(_call_outline(
        question, evidence, model, 0.2, _outline_lab_max_tokens,
        domain=domain, finding_clusters=clusters,
        deliverable_spec=deliverable, scope_spec=scope,
        same_work_groups=same_work_groups,
    ))
    plans = parse_result.plans
    stats = parse_result.digest_stats

    # item 14: fold each plan's anchor ev_ids to ONE per underlying WORK (a section anchoring twice
    # on the same source is not twice-corroborated — that is what dragged distinct_work_frac below
    # the 0.90 PUSH-A bar). Deterministic, DISCLOSED — the folded same-work aliases are recorded in
    # the cp4 audit (`plan_work_folds`) and the aliases stay in the pool/bibliography (§-1.3
    # consolidate, never a silent drop). Fixes the metric honestly instead of excluding it.
    # item 2: pass the pool so the alias map ALSO folds TITLE-identical works the cp3 URL/DOI groups
    # missed (>=12 such groups measured on cp4 — e.g. eloundou "GPTs are GPTs" + its GovAI mirror).
    # This folds them out of the per-section anchors below AND lifts the distinct-work fraction
    # honestly (consolidate the same-work anchors; never hide the metric). §-1.3: folded + disclosed
    # in plan_work_folds, the aliases stay in the pool/bibliography — never a silent drop.
    alias_of = _build_alias_map(same_work_groups, evidence)
    plan_work_folds: list[dict] = []
    folded_alias_ev_ids: set[str] = set()
    for _p in plans:
        _canon, _folded = dedup_plan_ev_ids_by_work(_p.ev_ids or [], alias_of)
        if _folded:
            plan_work_folds.append({"section": str(_p.title), "folded": _folded})
            for _aliases in _folded.values():
                folded_alias_ev_ids.update(_aliases)
        _p.ev_ids = _canon

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

    # PUSH B (Fable items 1/2/10): FULL pool accounting for the cp4 audit. Every pool row lands in
    # exactly one honest bucket — (i) an ev_id individually assigned to a section, (ii) a member of a
    # basket assigned to a section, (iii) a member of a surviving ORPHAN basket (work-corroboration
    # >=2, unassigned), (iv) a member of an unassigned SINGLE-WORK basket (work-corroboration <2,
    # unassigned — previously UNDISCLOSED: finding 1), (v) an unassigned singleton row, or (vi) a
    # folded same-work alias. The ACCEPTANCE gate below asserts that as set-equality (§-1.3 none
    # dropped) — the machine check that would have caught finding 1 instead of a false prose claim.
    assigned_ev_ids = {str(e) for p in plans for e in (p.ev_ids or [])}
<<<<<<< Updated upstream
<<<<<<< Updated upstream
    # item 9(a): the WORK keys already anchored by an assigned ev_id. A still-unassigned singleton
    # whose WORK is anchored via a DIFFERENT ev_id of the same paper is NOT a coverage gap — ev_882
    # is the same work as the anchored eloundou "GPTs are GPTs" and must not read as unassigned. Uses
    # the SAME alias_of that fix-3/item-2 built (now chrome-stripped + prefix-folded + false-merge
    # guarded), so the exclusion tracks the honest work identity. §-1.3: the row stays in the pool/
    # bibliography (disclosed via its canonical); it just stops double-reporting as a gap. This is
    # why the prior 136 unassigned-high-tier count was OVERSTATED.
    assigned_work_keys = {alias_of.get(e, e) for e in assigned_ev_ids}
=======
    assigned_basket_ids = {str(b) for p in plans for b in (p.basket_ids or [])}
>>>>>>> Stashed changes
=======
    assigned_basket_ids = {str(b) for p in plans for b in (p.basket_ids or [])}
>>>>>>> Stashed changes
    row_by_id = {str(r.get("evidence_id", "")): r for r in evidence}

    def _basket_member_union(bids) -> set[str]:
        out: set[str] = set()
        for bid in bids:
            out |= {str(m) for m in basket_members.get(bid, [])}
        return out

    # (iv) unassigned baskets whose WORK-level corroboration is <2 — find_orphan_baskets requires
    # corroboration>=2, so it never lists them; their members are basket members (not singletons)
    # and their basket is unassigned (not in final_orphans) => ZERO disclosure before this fix.
    final_orphans_set = set(final_orphans)
    unassigned_low_corr_baskets = sorted(
        bid for bid in basket_members
        if bid not in assigned_basket_ids and bid not in final_orphans_set
    )

    singleton_ev_ids = [
        str(r.get("evidence_id", "")) for r in evidence
        if str(r.get("evidence_id", "")) and str(r.get("evidence_id", "")) not in menu.ev_id_to_basket
    ]
<<<<<<< Updated upstream
<<<<<<< Updated upstream
    # item 14 + item 9(a): exclude a singleton that is (i) an assigned ev_id, (ii) a same-work alias
    # folded OUT of a plan's anchors (accounted for by its canonical, disclosed in plan_work_folds),
    # or (iii) a copy whose WORK is already anchored by an assigned ev_id. All three keep the pool
    # accounting honest and stop the unassigned count from being overstated (§-1.3: never a drop).
    unassigned_singletons = [
        e for e in singleton_ev_ids
        if e not in assigned_ev_ids
        and e not in folded_alias_ev_ids
        and alias_of.get(e, e) not in assigned_work_keys
    ]
    # item 9(b): collapse same-work unassigned candidates to ONE line carrying the aliases (ev_085 +
    # ev_1110 are the same UK-employment PDF listed twice today). §-1.3 consolidate: aliased +
    # disclosed, never dropped. The FIRST candidate seen per work is canonical (deterministic: pool
    # order). ``topic_verdict`` reads the row's SEMANTIC topic-judge stamp via the fail-open predicate
    # (§-1.3.1): "off_subject" ONLY on an affirmative OFF_SUBJECT stamp (positive relevance vetoes);
    # any uncertainty/missing => "unjudged" (KEEP). The compose router consumes the SAME predicate.
    unassigned_high_tier: list[dict] = []
    _seen_work: dict[str, dict] = {}
    for e in unassigned_singletons:
        if str(row_by_id[e].get("tier", "") or "").upper() not in _HIGH_TIERS:
            continue
        _wk = alias_of.get(e, e)
        if _wk in _seen_work:
            _seen_work[_wk]["same_work_aliases"].append(e)
            continue
        _entry = {
            "ev_id": e,
            "tier": str(row_by_id[e].get("tier", "") or ""),
            "title": str(row_by_id[e].get("title", "") or "")[:90],
            "disposition": "reassign_candidate",
            "topic_verdict": _row_topic_verdict(row_by_id[e]),
            "same_work_aliases": [],
        }
        _seen_work[_wk] = _entry
        unassigned_high_tier.append(_entry)
=======
    unassigned_singletons = [e for e in singleton_ev_ids if e not in assigned_ev_ids]
>>>>>>> Stashed changes
=======
    unassigned_singletons = [e for e in singleton_ev_ids if e not in assigned_ev_ids]
>>>>>>> Stashed changes

    # (Fable item 1) the high-tier disclosure scan now covers unassigned SINGLETONS **and** the
    # member rows of BOTH orphan and single-work unassigned baskets — a T1 row buried inside an
    # unassigned basket (e.g. inside B57) was previously never named. Each row is disclosed with the
    # basket it lives in (None => a true singleton). (Fable item 10) disposition is 'unassigned',
    # NOT a blanket reassign candidate: the real list includes plainly off-topic rows (cosmetic
    # triclosan/Homosalate, EMF SCHEER, ICSID arbitration, Dr. Seuss, GVP), so any actual
    # reassignment MUST first pass the §-1.3.1 topic-judge (fail-open). Disclosure only; zero plan
    # mutation.
    member_basket_of: dict[str, str] = {}
    for bid in list(final_orphans) + unassigned_low_corr_baskets:
        for m in basket_members.get(bid, []):
            member_basket_of.setdefault(str(m), bid)
    unassigned_high_tier = []
    _seen_high_tier: set[str] = set()
    for e in list(unassigned_singletons) + list(member_basket_of.keys()):
        if e in _seen_high_tier or e in assigned_ev_ids:
            continue
        _seen_high_tier.add(e)
        row = row_by_id.get(e)
        if row is None:
            continue
        if str(row.get("tier", "") or "").upper() in _HIGH_TIERS:
            unassigned_high_tier.append({
                "ev_id": e,
                "tier": str(row.get("tier", "") or ""),
                "title": str(row.get("title", "") or "")[:90],
                "basket_id": member_basket_of.get(e),   # None => a true unassigned singleton
                "disposition": "unassigned",             # §-1.3.1 topic-judge REQUIRED before reassign
            })

    # each surviving orphan basket, each single-work unassigned basket, and every unassigned
    # high-tier row is DISCLOSED here — DISCLOSURE ONLY, zero plan mutation (§-1.3 consolidate).
    revision_audit = {
        "rounds": 0,
        # S4 collapse fix 1(b): every content-word-overlap title re-map is DISCLOSED here (§-1.3) so
        # the cp4 audit shows which required titles were mapped from a paraphrased emitted heading.
        "title_conformed": list(getattr(parse_result, "title_conformed", []) or []),
        "orphan_baskets_after_plan": list(final_orphans),
        "orphan_reassign_candidates": [
            # item 3b: per-candidate topic verdict, read from the members' topic-judge stamps via the
            # fail-open predicate. An orphan basket is "off_subject" ONLY when EVERY member is
            # confirmed OFF_SUBJECT (all-members rule => the router deletes it before residual
            # routing, §-1.3.1 disclosed); if ANY member is not confirmed off-topic => "unjudged"
            # (fail-open => KEEP + route). Empty-members => "unjudged".
            {"basket_id": bid, "members": basket_members.get(bid, []),
<<<<<<< Updated upstream
<<<<<<< Updated upstream
             "disposition": "reassign_candidate",
             "topic_verdict": (
                 "off_subject"
                 if (basket_members.get(bid)
                     and all(_row_topic_verdict(row_by_id.get(m, {})) == "off_subject"
                             for m in basket_members.get(bid, [])))
                 else "unjudged"
             )}
=======
             "disposition": "unassigned"}   # item 10: topic-judge gated, not auto-reassign
>>>>>>> Stashed changes
=======
             "disposition": "unassigned"}   # item 10: topic-judge gated, not auto-reassign
>>>>>>> Stashed changes
            for bid in final_orphans
        ],
        # Fable item 1: single-work unassigned baskets (work-corroboration <2) — DISCLOSED so no
        # pool row is silently unaccounted (they are neither singletons nor orphans).
        "unassigned_single_work_baskets": [
            {"basket_id": bid, "members": basket_members.get(bid, [])}
            for bid in unassigned_low_corr_baskets
        ],
        "unassigned_singletons_count": len(unassigned_singletons),
        "unassigned_high_tier": unassigned_high_tier,
<<<<<<< Updated upstream
<<<<<<< Updated upstream
        # item 14: same-work anchor folds per section (canonical kept, aliases disclosed) — §-1.3
        # consolidate; the folded aliases remain in the pool/bibliography, never dropped.
        "plan_work_folds": plan_work_folds,
        # item 7 (operator rule 2026-07-05 — "a winner built but left default-OFF is the still-broken
        # loop root"): the cp4 checkpoint NAMES the compose-stage (S5) acceptance criteria so the S5
        # run slate ARMS the flags rather than leaving them invisibly OFF. The S4 flag_slate above
        # already RECORDS PG_ROUTE_ALL_BASKETS + PG_OUTLINE_REVISE_ROUNDS; the ARMING (=1) belongs to
        # the S5 compose lab run config (a different section/branch), and these are its gates:
        "s5_acceptance": [
            "PG_ROUTE_ALL_BASKETS=1 in the S5 compose run slate — the orphan-basket + unassigned "
            "high-tier singleton router MUST FIRE; disclose routed_basket_count + routed_singleton_"
            "count (router-fired + routed-counts-disclosed is a NAMED S5 acceptance item).",
            "PG_OUTLINE_REVISE_ROUNDS=1 exercised LIVE at the compose stage (rounds=0 here in plan "
            "mode is correct) — its firing is an explicit S5 acceptance criterion; do not let the "
            "revise loop fall silently between section loops.",
        ],
        "note": ("orphan baskets AND unassigned high-tier singletons are routed to section plans at "
                 "COMPOSE via PG_ROUTE_ALL_BASKETS (verified_compose.py "
                 "route_orphan_baskets_to_section_plans, default-OFF). Item 3b/3c (§-1.3.1): the "
                 "compose call site computes the JUDGE-CONFIRMED off-topic ev_id set from the pool "
                 "via the SAME fail-open predicate that stamps `topic_verdict` above "
                 "(is_row_deletable_offtopic — affirmative OFF_SUBJECT only, positive relevance "
                 "vetoes) and hands it to the router with the unassigned high-tier singleton "
                 "candidates; the router's BASKET leg routes each orphan basket and its SINGLETON "
                 "leg routes each candidate by the same title+focus overlap rule (keep-all residual "
                 "otherwise), DELETING only judge-CONFIRMED off-topic items before routing "
                 "(disclosed) — uncertainty => KEEP, so no zero-overlap off-topic junk lands in the "
                 "keep-all residual section. This cp4 audit is DISCLOSURE ONLY — zero plan mutation "
                 "here. Every pool member is accounted for: assigned to a section, same-work-folded "
                 "(plan_work_folds), orphan-basket-disclosed, or unassigned-singleton-disclosed "
                 "(§-1.3 consolidate — none silently dropped)."),
=======
=======
>>>>>>> Stashed changes
        "note": ("orphan baskets, single-work unassigned baskets, and unassigned singletons are ALL "
                 "DISCLOSED here (§-1.3 consolidate — none dropped); this cp4 audit is DISCLOSURE "
                 "ONLY, zero plan mutation. Any actual reassignment at COMPOSE "
                 "(verified_compose.py route_orphan_baskets_to_section_plans, PG_ROUTE_ALL_BASKETS, "
                 "default-OFF) MUST first pass the §-1.3.1 topic-judge (FAIL-OPEN) — the unassigned "
                 "list includes plainly off-topic rows that must NOT be pulled into a section as-is. "
                 "The S2 off-topic leak + S3 title-like-claim gap are escalated cross-section in "
                 "docs/s4_outline_upstream_escalations.md."),
<<<<<<< Updated upstream
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
    }

    # (Fable item 2) machine ACCOUNTING identity: assigned ev_ids + members of assigned baskets +
    # orphan-basket members + single-work-basket members + unassigned singletons + folded aliases
    # must equal the pool EXACTLY (set equality, not counts). This is the binding check that would
    # have caught finding 1 (single-work baskets silently unaccounted) instead of shipping a false
    # 'every pool member is accounted for' prose claim.
    folded_aliases: set[str] = set()
    for canonical, aliases in menu.singleton_alias_ev_ids.items():
        folded_aliases.add(str(canonical))
        folded_aliases.update(str(a) for a in aliases)
    accounted = (
        assigned_ev_ids
        | _basket_member_union(assigned_basket_ids)   # non-referenced members of ASSIGNED baskets
        | _basket_member_union(final_orphans)
        | _basket_member_union(unassigned_low_corr_baskets)
        | set(unassigned_singletons)
        | folded_aliases
    )
    pool_ev_ids = {str(r.get("evidence_id", "")) for r in evidence if str(r.get("evidence_id", ""))}
    unaccounted = sorted(pool_ev_ids - accounted)
    accounting_ok = not unaccounted

    print("\n=== (b') FULL POOL DISCLOSURE (cp4 audit-level honesty) ===")
    print(f"[b'] assigned_ev_ids={len(assigned_ev_ids)} "
          f"unassigned_singletons={len(unassigned_singletons)} "
          f"orphan_baskets={len(final_orphans)} "
          f"unassigned_single_work_baskets={len(unassigned_low_corr_baskets)} "
          f"unassigned_high_tier={len(unassigned_high_tier)}")
    for item in unassigned_high_tier:
        print(f"     {item['ev_id']:<10} {item['tier']:<4} "
              f"basket={item['basket_id'] or '-':<6} {item['title']}")
    print(f"[b'] ACCOUNTING set-equality (pool==accounted): {accounting_ok}  "
          f"pool={len(pool_ev_ids)} accounted={len(accounted & pool_ev_ids)} "
          f"unaccounted={unaccounted[:8]}")

    # (c) degraded flag from the digest telemetry
    print("\n=== (c) DIGEST TELEMETRY (digest_stats) ===")
    print(json.dumps(stats, indent=1))
    degraded_ok = (stats.get("digest_degraded") is False)
    print(f"[c] degraded == False: {degraded_ok}")

    # PUSH A (e): per-section distinct-work fraction — of a section's anchor ev_ids, how many are
    # DISTINCT works (rows sharing a same_work_id count once). Rises toward 1.0 as the planner reads
    # the work-level digest and stops anchoring twice on the same underlying work. (``alias_of`` was
    # already built above for the item-14 anchor fold — reuse it; do not rebuild. After that fold the
    # per-section fraction is ~1.0 because each remaining anchor is a distinct work, which is the
    # honest fix — the bar is met by consolidating same-work anchors, not by hiding the metric.)
    print("\n=== (e) PER-SECTION DISTINCT-WORK FRACTION (PUSH A) ===")
    section_fracs = []
    for p in plans:
        ev = [str(x) for x in (p.ev_ids or [])]
        works = {alias_of.get(e, e) for e in ev}
        frac = (len(works) / len(ev)) if ev else 1.0
        section_fracs.append(frac)
        print(f"  {p.title!r}: anchors={len(ev)} distinct_works={len(works)} frac={frac:.3f}")
    min_frac = min(section_fracs) if section_fracs else 1.0
    frac_ok = min_frac >= 0.90
    print(f"[e] all sections distinct-work fraction >= 0.90: {frac_ok} (min={min_frac:.3f})")

    # item 7: undersupplied disclosure. The honesty gate below passes on any() non-empty section, so a
    # mostly-hollow outline (3 of 4 required sections undersupplied) can read as a clean green. Surface
    # the count + the per-section list on the gate line AND record it into cp4 digest_stats so the
    # hollowness is visible in the checkpoint, never silently green.
    undersupplied_sections = [str(p.title) for p in plans if p.undersupplied]
    undersupplied_count = len(undersupplied_sections)
    if isinstance(stats, dict):
        stats["undersupplied_count"] = undersupplied_count
        stats["undersupplied_sections"] = list(undersupplied_sections)

    # (d) cp4 write + load (verdict-leak guarded on BOTH)
<<<<<<< Updated upstream
<<<<<<< Updated upstream
    # item 6: record the FULL effective S4 knob set + a sha256 of it as run_config_sha (until
    # RunConfig WP-0b lands) so the checkpoint can PROVE what produced it — the prior hardcoded
    # {"PG_OUTLINE_BASKET_DIGEST":"1"} + run_config_sha="" proved nothing about the actual run.
    flag_slate = _effective_s4_flag_slate(model)
    run_config_sha = hashlib.sha256(
        json.dumps(flag_slate, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    print(f"\n[d] effective S4 flag_slate={json.dumps(flag_slate, sort_keys=True)} "
          f"run_config_sha={run_config_sha[:12]}")
=======
=======
>>>>>>> Stashed changes
    # Fable item 8: pin EVERY env knob this run's behavior (and the downstream compose promise in the
    # note) actually reads — not just PG_OUTLINE_BASKET_DIGEST — and thread a REAL run_config sha
    # (was hardcoded ''), so the cp4 envelope is reproducible. Effective env value per knob; unset =>
    # "" (the code default applied). The sha is over the sorted slate so it is order-independent.
    _env_knobs = (
        "PG_OUTLINE_BASKET_DIGEST",
        "PG_OUTLINE_DIGEST_MAX_CHARS",
        "PG_OUTLINE_MIN_MAX_TOKENS",
        "PG_OUTLINE_REASONING_MAX_TOKENS",
        "PG_ROUTE_ALL_BASKETS",
    )
    flag_slate = {k: os.getenv(k, "") for k in _env_knobs}
    run_config_sha = hashlib.sha256(
        json.dumps(flag_slate, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
<<<<<<< Updated upstream
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
    payload = build_cp4_payload(
        question_sha=hashlib.sha256(question.encode("utf-8")).hexdigest(),
        upstream=[{"stage": "basket", "sha": str(bank.get("cp3_sha", ""))}],
        run_config_sha=run_config_sha,
        flag_slate=flag_slate,
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

    # P2 HONESTY GATE (b/e): a passing (a)/(c)/(d) signal on a HOLLOW outline (every final plan
    # empty while the bank carries evidence) is a false green — the exact failure that shipped a
    # collapsed outline as "ok". FAIL when the final plans carry ZERO ev_ids while the bank is
    # non-empty; and on a real (non-fixture) bank additionally require >=1 required section that is
    # NOT undersupplied (at least one required heading must actually be evidence-backed).
    ev_total = sum(len(p.ev_ids) for p in plans)
    bank_nonempty = len(evidence) > 0
    hollow_collapse = (ev_total == 0 and bank_nonempty)
    required_supplied_ok = (any(not p.undersupplied for p in plans) if required else True)
    be_gate_ok = (not hollow_collapse) and required_supplied_ok
    print("\n=== (b/e) HONESTY GATE (no hollow collapse) ===")
    print(f"[b/e] ev_id_total={ev_total} bank_nonempty={bank_nonempty} "
          f"hollow_collapse={hollow_collapse} required_supplied_ok={required_supplied_ok} "
          f"undersupplied_count={undersupplied_count} undersupplied_sections={undersupplied_sections} "
          f">>> be_gate_ok={be_gate_ok}")

    # (Fable item 2) the accounting identity is now a BINDING acceptance term — a single unaccounted
    # pool row fails the run rather than shipping a false 'every pool member is accounted for' claim.
    ok = (
        bool(load_ok)
        and (order_ok in (True, None))
        and degraded_ok
        and be_gate_ok
        and accounting_ok
    )
    print(f"\n[plan] ACCEPTANCE (a,c,d,b/e,acct) ok={ok}  distinct_work_frac_ok={frac_ok}  "
          f"accounting_ok={accounting_ok}  in_tok={in_tok} out_tok={out_tok}")
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
