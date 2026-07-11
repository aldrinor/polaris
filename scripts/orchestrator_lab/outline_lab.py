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
    _is_chrome_interstitial,
    _is_weight_demoted,
    assert_unique_required_sections,
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
        # O4 (un-starve): the spine outline call's content ceiling (was hardcoded 2500). A CAP not a
        # target — recorded so the checkpoint proves the spine call was NOT starved this run.
        "PG_OUTLINE_MAX_TOKENS": os.getenv("PG_OUTLINE_MAX_TOKENS", "32768"),
        # O1/O2/O3/O6: two-level sub-theme full-partition arm-state. ON by default (a winner built but
        # left default-OFF is the still-broken loop root); recorded so the checkpoint proves it fired.
        "PG_OUTLINE_SUBTHEME_PARTITION": os.getenv("PG_OUTLINE_SUBTHEME_PARTITION", "1"),
        "PG_OUTLINE_REVISE_ROUNDS": os.getenv(
            "PG_OUTLINE_REVISE_ROUNDS", str(PG_OUTLINE_REVISE_ROUNDS_DEFAULT)),
        "PG_OUTLINE_REVISE_MAX_RECOMPOSE": os.getenv(
            "PG_OUTLINE_REVISE_MAX_RECOMPOSE", str(PG_OUTLINE_REVISE_MAX_RECOMPOSE_DEFAULT)),
        "model": str(model),
    }


_JUNK_GATE_PREDICATE_WARNED = False  # P3-3: warn ONCE per run when the junk-gate predicate collapses


def _row_topic_verdict(row: dict) -> str:
    """Item 3 + P2-2 (FOUR-VALUED): the cp4 per-candidate semantic topic verdict, read from the row's
    topic-judge + content-integrity stamps. FOUR values so the disclosure never overstates ignorance
    (395/686 rows this run carry ``topic_offtopic_demoted``, 445 carry ``content_relevance_label=
    demoted`` — yet every candidate read as ``unjudged`` before, starving the S5 router):

      "chrome_interstitial" — a §-1.3.1(a) content-integrity chrome NON-SOURCE (bot / cookie / 404 /
                        "Just a moment..." failed fetch). Sourced from the junk-gate class-(a) stamp
                        predicate (``is_row_content_junk``) OR the digest title-interstitial heuristic
                        (banked rows may lack the fetch-side stamp). DISCLOSURE only — DELETION stays
                        with the S5/junk gate; the router routes it to the gate, never to keep-all.
      "off_subject"   — an AFFIRMATIVE deletable off-topic stamp (the SAME fail-open predicate the
                        compose router + run-level junk gate consume; a positive-relevance verdict
                        vetoes it). This is the ONLY value the orphan-basket all-members rule treats
                        as deletable — deletion semantics UNCHANGED (§-1.3.1 judge-only, fail-open).
      "demoted_weight" — a WEIGHT-demote stamp (``topic_offtopic_demoted`` truthy, OR
                        ``content_relevance_label`` in {demoted, escalated_demoted}). DISCLOSURE only:
                        the row is KEPT and routed; the S5 router now sees it is relevance-demoted.
      "unjudged"      — no stamp / any uncertainty / import-or-predicate error (FAIL-OPEN => KEEP).

    Zero routing/deletion change — only the disclosure is richer (a chrome / demoted row no longer
    hides as ``unjudged``)."""
    global _JUNK_GATE_PREDICATE_WARNED
    r = row or {}
    _title = str(r.get("title", "") or "")
    try:
        from src.polaris_graph.generator.junk_deletion_gate import (  # noqa: PLC0415
            is_row_content_junk,
            is_row_deletable_offtopic,
        )
        # P2-2: chrome non-source (class-a) checked FIRST — a failed fetch is neither on- nor off-topic.
        if is_row_content_junk(r) or _is_chrome_interstitial(_title):
            return "chrome_interstitial"
        if is_row_deletable_offtopic(r):
            return "off_subject"
    except Exception as exc:  # noqa: BLE001 — fail-open: a judge/import error never flips a row
        # P3-3: a broken junk-gate import silently marked EVERY candidate "unjudged" with zero trace
        # (a collapsed predicate is invisible). Keep fail-open, but DISCLOSE it ONCE per run so the
        # collapse is loud (§-1.3 fail-loud-never-silent); still apply the title chrome heuristic.
        if not _JUNK_GATE_PREDICATE_WARNED:
            _JUNK_GATE_PREDICATE_WARNED = True
            print(
                f"[outline_lab] WARNING: junk-gate topic predicate unavailable ({str(exc)[:160]}) "
                "— topic verdicts fail-open (title heuristic / 'unjudged') for this run.",
                file=sys.stderr,
            )
        if _is_chrome_interstitial(_title):
            return "chrome_interstitial"
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
    # P3-2: the per-plan for-loop that re-unioned the same ev_ids was a no-op repeat of the
    # comprehension above — removed.
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
    # item 13: when the bank has a required-section structure, thread it so apply restricts ops to
    # keep/reassign and cannot break the user's exact-N-in-order contract.
    _required = [
        str(t).strip()
        for t in ((bank.get("deliverable") or {}).get("required_sections", []) or [])
        if str(t).strip()
    ]
    # fix 5 (P3): thread the ev_id -> basket map (built from the bank's basket_members) so a split
    # op's children get their basket_ids backfilled by the SAME rule the plan stage uses. Absent
    # basket_members => None => children keep basket_ids=[] (byte-identical to before).
    _bm = bank.get("basket_members", {}) or {}
    _ev2b = {str(e): str(bid) for bid, members in _bm.items() for e in (members or [])}
    applied = apply_revision_ops(
        plans, parsed, outcomes=outcomes, required_titles=_required,
        ev_id_to_basket=(_ev2b or None),
    )

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
    # fix 7 (P3): fail loud on a degenerate duplicate required title BEFORE the expensive live outline
    # call — a case-insensitive dup would silently drop one section's evidence at compose (by_title
    # last-wins). Same predicate the requirements-block builder uses; question-agnostic.
    assert_unique_required_sections(required)

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
    # O4 (un-starve, build plan OUTLINE wheel): the outline call's max_tokens was hardcoded 2500 — a
    # starved budget the reasoning prelude alone consumed, forcing the (PG_OUTLINE_MIN_MAX_TOKENS-
    # floored) content to truncate on a large pool. Read PG_OUTLINE_MAX_TOKENS (default 32768) so the
    # spine call has real headroom; max_tokens is a CAP not a target (billed by actual usage) — a
    # generous cap is free insurance (§9.1.8). The downstream floor (PG_OUTLINE_MIN_MAX_TOKENS) still
    # applies inside _call_outline, so this only ever RAISES the ceiling, never lowers it.
    _outline_max_tokens = int(os.getenv("PG_OUTLINE_MAX_TOKENS", "32768"))
    parse_result, retry_attempted, in_tok, out_tok = asyncio.run(_call_outline(
        question, evidence, model, 0.2, _outline_max_tokens,
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
    # P2-1 (fix 2): capture each section's PRE-fold anchor ev_ids BEFORE the same-work fold below, so
    # the INFORMATIVE per-section distinct-work fraction (the planner's RAW anchoring behaviour) can be
    # computed. The POST-fold fraction is ~1.0 by construction (the fold makes anchors distinct-by-
    # work), so grading acceptance on it is tautological — the pre-fold fraction is the real signal.
    pre_fold_anchor_ev_ids: list[list[str]] = []
    for _p in plans:
        pre_fold_anchor_ev_ids.append([str(x) for x in (_p.ev_ids or [])])
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

    # PUSH B: full pool accounting for the cp4 audit — every pool member is assigned to a section,
    # OR disclosed as an orphan-basket reassign candidate, OR disclosed as an unassigned singleton.
    assigned_ev_ids = {str(e) for p in plans for e in (p.ev_ids or [])}
    # item 9(a): the WORK keys already anchored by an assigned ev_id. A still-unassigned singleton
    # whose WORK is anchored via a DIFFERENT ev_id of the same paper is NOT a coverage gap — ev_882
    # is the same work as the anchored eloundou "GPTs are GPTs" and must not read as unassigned. Uses
    # the SAME alias_of that fix-3/item-2 built (now chrome-stripped + prefix-folded + false-merge
    # guarded), so the exclusion tracks the honest work identity. §-1.3: the row stays in the pool/
    # bibliography (disclosed via its canonical); it just stops double-reporting as a gap. This is
    # why the prior 136 unassigned-high-tier count was OVERSTATED.
    assigned_work_keys = {alias_of.get(e, e) for e in assigned_ev_ids}
    row_by_id = {str(r.get("evidence_id", "")): r for r in evidence}
    singleton_ev_ids = [
        str(r.get("evidence_id", "")) for r in evidence
        if str(r.get("evidence_id", "")) and str(r.get("evidence_id", "")) not in menu.ev_id_to_basket
    ]
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
        _tv = _row_topic_verdict(row_by_id[e])
        _entry = {
            "ev_id": e,
            "tier": str(row_by_id[e].get("tier", "") or ""),
            "title": str(row_by_id[e].get("title", "") or "")[:90],
            "disposition": "reassign_candidate",
            "topic_verdict": _tv,
            # P2-2: chrome non-source disclosure (§-1.3.1(a)) — the S5 router routes it to the junk
            # gate (DELETE), never to a keep-all residual section. Disclosure only; None when not chrome.
            "content_flag": ("chrome_interstitial" if _tv == "chrome_interstitial" else None),
            "same_work_aliases": [],
        }
        _seen_work[_wk] = _entry
        unassigned_high_tier.append(_entry)

    # P1 (fix 1 — dark-basket disclosure gap): find_orphan_baskets(min=2) above only flags
    # multi-WORK unassigned baskets. A SINGLE-work multi-row basket (work_corroboration==1) whose
    # rows are basket members — NOT singletons (they live in menu.ev_id_to_basket) — that reaches NO
    # section therefore falls through BOTH the orphan list AND the unassigned-singleton list, and the
    # cp4 note's "every pool member is accounted for" claim was FALSE for those rows (32 of 66 baskets
    # this run). Compute the COMPLETE unassigned-basket set by the SAME reachability rule the S5
    # router uses (route_orphan_baskets_to_section_plans, verified_compose.py — it thresholds NOTHING
    # on corroboration): a basket is unassigned iff it is on NO plan's basket_ids AND none of its
    # members is an assigned ev_id. Disclose EVERY such basket; the work_corroboration>=2 ones are
    # already in orphan_reassign_candidates (find_orphan_baskets(min=2), kept untouched for the
    # reviser uncovered-baskets checklist), so the REMAINDER go to a parallel list. §-1.3: DISCLOSURE
    # ONLY — zero plan mutation, no drop. Each entry mirrors an orphan candidate's shape.
    assigned_basket_ids = {str(b) for p in plans for b in (getattr(p, "basket_ids", []) or [])}
    _final_orphans_set = set(final_orphans)
    unassigned_single_work_baskets: list[dict] = []
    for _bid in menu.basket_member_ev_ids:
        _members = [str(m) for m in basket_members.get(_bid, [])]
        if _bid in assigned_basket_ids:
            continue                                   # covered by the basket_ids backfill
        if set(_members) & assigned_ev_ids:
            continue                                   # reachable via an assigned member ev_id
        if _bid in _final_orphans_set:
            continue                                   # already an orphan_reassign_candidate (corr>=2)
        unassigned_single_work_baskets.append({
            "basket_id": _bid,
            "members": _members,
            "work_corroboration": int(basket_corroboration.get(_bid, 0)),
            "disposition": "reassign_candidate",
            # same all-members fail-open rule as the orphan candidates: "off_subject" ONLY when EVERY
            # member is affirmatively judge-confirmed off-topic; any uncertainty => "unjudged" (KEEP).
            "topic_verdict": (
                "off_subject"
                if (_members and all(
                    _row_topic_verdict(row_by_id.get(m, {})) == "off_subject" for m in _members))
                else "unjudged"
            ),
            # chrome disclosure (§-1.3.1(a)) — DELETION stays with the S5/junk gate; None otherwise.
            "content_flag": ("chrome_interstitial" if menu.basket_chrome.get(_bid) else None),
        })

    # each surviving orphan basket + every unassigned high-tier singleton is DISCLOSED here as a
    # reassign candidate — DISCLOSURE ONLY, zero plan mutation (§-1.3 consolidate, never dropped).
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
             "disposition": "reassign_candidate",
             "topic_verdict": (
                 "off_subject"
                 if (basket_members.get(bid)
                     and all(_row_topic_verdict(row_by_id.get(m, {})) == "off_subject"
                             for m in basket_members.get(bid, [])))
                 else "unjudged"
             ),
             # P2-2: the digest already computed chrome=True for an all-interstitial basket (e.g. an
             # all-"Just a moment..." Cloudflare basket) — surface it as a distinct disclosure so the
             # S5 router routes it to the junk gate (class-a DELETE), not KEEP+route. Disclosure only;
             # deletion stays with the S5/junk gate (§-1.3.1(a)). None when the basket is not chrome.
             "content_flag": ("chrome_interstitial" if menu.basket_chrome.get(bid) else None)}
            for bid in final_orphans
        ],
        "unassigned_singletons_count": len(unassigned_singletons),
        "unassigned_high_tier": unassigned_high_tier,
        # P1 (fix 1): the COMPLETE remainder of unassigned baskets (single-work / low-corroboration)
        # not already disclosed in orphan_reassign_candidates — so EVERY unassigned basket in the pool
        # is named here + reaches the S5 router (which thresholds nothing on corroboration).
        "unassigned_single_work_baskets": unassigned_single_work_baskets,
        "unassigned_single_work_basket_count": len(unassigned_single_work_baskets),
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
            # P1 (fix 1) S5 hand-off contract: the unassigned_single_work_baskets above (every "
            # remaining unassigned basket, regardless of work_corroboration) MUST also reach "
            # route_orphan_baskets_to_section_plans — the router thresholds NOTHING on corroboration "
            # (verified_compose.py:3598), so a single-work basket is routed by the same title+focus "
            # overlap rule as a multi-work orphan (keep-all residual otherwise). Disclose "
            # routed_single_work_basket_count alongside routed_basket_count.
            "unassigned_single_work_baskets (work_corroboration<2) MUST reach "
            "route_orphan_baskets_to_section_plans in the S5 compose slate — the router thresholds "
            "nothing on corroboration; disclose routed_single_work_basket_count.",
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
                 "here. Every pool row is now accounted for (fix 1): assigned to a section, "
                 "same-work-folded (plan_work_folds), a member of a basket reachable by a section "
                 "(its basket_id is on a plan OR a member ev_id is assigned), a member of a disclosed "
                 "UNASSIGNED basket (orphan_reassign_candidates for work_corroboration>=2, "
                 "unassigned_single_work_baskets otherwise — the COMPLETE unassigned-basket set by "
                 "the S5 router's own reachability rule), or an unassigned-singleton-disclosed "
                 "(§-1.3 consolidate — none silently dropped)."),
    }
    print("\n=== (b') FULL POOL DISCLOSURE (cp4 audit-level honesty) ===")
    print(f"[b'] assigned_ev_ids={len(assigned_ev_ids)} unassigned_singletons={len(unassigned_singletons)} "
          f"unassigned_high_tier={len(unassigned_high_tier)} "
          f"orphan_reassign_candidates={len(final_orphans)} "
          f"unassigned_single_work_baskets={len(unassigned_single_work_baskets)}")
    for item in unassigned_high_tier:
        print(f"     {item['ev_id']:<10} {item['tier']:<4} {item['title']}")
    for _b in unassigned_single_work_baskets:
        print(f"     basket {_b['basket_id']:<8} rows={len(_b['members'])} "
              f"work_corr={_b['work_corroboration']} verdict={_b['topic_verdict']}"
              + (f" [{_b['content_flag']}]" if _b['content_flag'] else ""))

    # (c) degraded flag from the digest telemetry
    print("\n=== (c) DIGEST TELEMETRY (digest_stats) ===")
    print(json.dumps(stats, indent=1))
    degraded_ok = (stats.get("digest_degraded") is False)
    print(f"[c] degraded == False: {degraded_ok}")

    # (e) per-section distinct-work fractions — TWO per section (P2-1 / fix 2):
    #   PRE-fold (INFORMATIVE): of the planner's RAW anchors, how many are distinct works. This is the
    #     real anchoring-quality signal — it rises toward 1.0 as the planner stops anchoring twice on
    #     the same underlying work; it can legitimately be < 1.0 and is NOT a pass/fail bar.
    #   POST-fold (INVARIANT): after the item-14 same-work fold, each remaining anchor is a distinct
    #     work BY CONSTRUCTION, so this MUST be ~1.0. It is kept ONLY as a fail-loud sanity assertion —
    #     a post-fold value < 1.0 means dedup_plan_ev_ids_by_work / alias_of is inconsistent (a real
    #     bug), never a quality bar. The prior code graded acceptance on the post-fold value against
    #     >=0.90, which could NEVER fail (a false-green-shaped gate; min=1.000 was cited as "quality").
    # Also disclosed per section (DISCLOSURE ONLY — deletion stays with S2/S3 + the junk gate):
    #   demoted_anchors + chrome_anchors (fix 3, corpus dirt an anchor carries) and shared_anchor_count
    #   (fix 6, anchors this section shares with another section).
    print("\n=== (e) PER-SECTION DISTINCT-WORK FRACTION (pre-fold informative / post-fold invariant) ===")
    # fix 6: how many sections each POST-fold anchor ev_id appears in, for the shared-anchor count.
    _ev_section_count: dict[str, int] = {}
    for _p in plans:
        for _e in {str(x) for x in (_p.ev_ids or [])}:
            _ev_section_count[_e] = _ev_section_count.get(_e, 0) + 1

    post_fold_fracs: list[float] = []
    pre_fold_fracs: list[float] = []
    per_section_work: list[dict] = []      # POST-fold structured record for cp4 digest_stats
    pre_fold_per_section: list[dict] = []  # fix 2: the INFORMATIVE pre-fold record
    for _idx, p in enumerate(plans):
        ev = [str(x) for x in (p.ev_ids or [])]
        works = {alias_of.get(e, e) for e in ev}
        frac = (len(works) / len(ev)) if ev else 1.0          # POST-fold (~1.0 by construction)
        post_fold_fracs.append(frac)

        # fix 2: PRE-fold fraction over the planner's RAW anchors (captured before the item-14 fold).
        _pre = pre_fold_anchor_ev_ids[_idx] if _idx < len(pre_fold_anchor_ev_ids) else ev
        _pre_works = {alias_of.get(e, e) for e in _pre}
        _pre_frac = (len(_pre_works) / len(_pre)) if _pre else 1.0
        pre_fold_fracs.append(_pre_frac)

        # INDEPENDENT cross-check: anchors sharing a MULTI-member basket with another anchor in the
        # SAME section (menu.ev_id_to_basket) — corroboration via the finding-cluster path, not the
        # same-work alias path. Disclosure only.
        _bhits: dict[str, int] = {}
        for e in ev:
            _b = menu.ev_id_to_basket.get(e)
            if _b is not None:
                _bhits[_b] = _bhits.get(_b, 0) + 1
        _co_basket_anchors = sum(c for c in _bhits.values() if c >= 2)

        # fix 3: corpus-dirt disclosure per section (DISCLOSURE ONLY). demoted_anchors via the existing
        # weight-demote predicate; chrome_anchors via the four-valued topic verdict — so the S5
        # reviser/router sees WHICH sections carry demoted / chrome anchors without re-deriving stamps.
        _demoted_anchors = sum(1 for e in ev if _is_weight_demoted(row_by_id.get(e, {})))
        _chrome_anchors = sum(
            1 for e in ev if _row_topic_verdict(row_by_id.get(e, {})) == "chrome_interstitial")
        # fix 6: anchors also present in another section (legitimate cross-angle reuse — but visible).
        _shared_anchors = sum(1 for e in set(ev) if _ev_section_count.get(e, 0) >= 2)

        per_section_work.append({
            "section": str(p.title),
            "anchors": len(ev),
            "distinct_works": len(works),
            "frac": round(frac, 4),
            "pre_fold_frac": round(_pre_frac, 4),
            "distinct_baskets": len(_bhits),
            "co_basket_anchors": _co_basket_anchors,
            "demoted_anchors": _demoted_anchors,
            "chrome_anchors": _chrome_anchors,
            "shared_anchor_count": _shared_anchors,
        })
        pre_fold_per_section.append({
            "section": str(p.title),
            "anchors": len(_pre),
            "distinct_works": len(_pre_works),
            "frac": round(_pre_frac, 4),
        })
        print(f"  {p.title!r}: anchors={len(ev)} distinct_works={len(works)} "
              f"pre_fold_frac={_pre_frac:.3f} post_fold_frac={frac:.3f} "
              f"co_basket_anchors={_co_basket_anchors} demoted_anchors={_demoted_anchors} "
              f"chrome_anchors={_chrome_anchors} shared_anchors={_shared_anchors}")

    pre_fold_min_frac = min(pre_fold_fracs) if pre_fold_fracs else 1.0
    post_fold_min_frac = min(post_fold_fracs) if post_fold_fracs else 1.0
    # fix 2: the post-fold value is an INVARIANT, not a quality bar. It must be ~1.0; anything lower
    # means the same-work fold left two anchors of one work on a section (alias map broke) — fail LOUD
    # (§-1.3) rather than pass a tautological >=0.90 check.
    _POST_FOLD_EPS = 1e-9
    post_fold_invariant_ok = post_fold_min_frac >= (1.0 - _POST_FOLD_EPS)
    if not post_fold_invariant_ok:
        print(
            f"[e] INVARIANT VIOLATION: post-fold distinct-work frac {post_fold_min_frac:.4f} < 1.0 — "
            "the same-work fold (dedup_plan_ev_ids_by_work / alias_of) is INCONSISTENT; a section "
            "still carries two anchors of one work after the fold. This is a real fold/alias bug.",
            file=sys.stderr,
        )
    print(f"[e] pre-fold min distinct-work frac (INFORMATIVE) = {pre_fold_min_frac:.3f}")
    print(f"[e] post-fold min distinct-work frac (INVARIANT, must be ~1.0) = {post_fold_min_frac:.3f} "
          f"invariant_ok={post_fold_invariant_ok}")

    # persist BOTH the informative pre-fold metric and the post-fold invariant into cp4 digest_stats
    # (durable in the checkpoint, not print-only). §-1.3: disclosure, never a drop.
    if isinstance(stats, dict):
        stats["per_section_distinct_work"] = per_section_work
        stats["pre_fold_per_section_distinct_work"] = pre_fold_per_section
        stats["pre_fold_min_distinct_work_frac"] = round(pre_fold_min_frac, 4)
        stats["post_fold_min_distinct_work_frac"] = round(post_fold_min_frac, 4)
        stats["post_fold_distinct_work_invariant_ok"] = bool(post_fold_invariant_ok)
        stats["plan_work_fold_count"] = sum(
            len(_a) for _f in plan_work_folds for _a in _f.get("folded", {}).values()
        )
        stats["digest_oversized"] = bool(getattr(menu, "oversized", False))

    # item 7: undersupplied disclosure. The honesty gate below passes on any() non-empty section, so a
    # mostly-hollow outline (3 of 4 required sections undersupplied) can read as a clean green. Surface
    # the count + the per-section list on the gate line AND record it into cp4 digest_stats so the
    # hollowness is visible in the checkpoint, never silently green.
    undersupplied_sections = [str(p.title) for p in plans if p.undersupplied]
    undersupplied_count = len(undersupplied_sections)
    if isinstance(stats, dict):
        stats["undersupplied_count"] = undersupplied_count
        stats["undersupplied_sections"] = list(undersupplied_sections)

    # ── O1/O2/O3/O6 TWO-LEVEL SUB-THEME FULL-PARTITION (build plan OUTLINE wheel) ─────────────────
    # The section SPINE above (required titles pinned in order, or facet-emergent) is UNTOUCHED. This
    # layer groups EVERY digest line-id (Bxx corroboration baskets + ev_xxx singletons) into a NAMED
    # sub-theme under exactly ONE section, so composed paragraphs land in a real two-level topic tree
    # (FS-Researcher index.md analog) instead of the flat keep-all residual dump cp4 shipped before.
    # DNA: this is CONSOLIDATE grouping — ZERO drops, ZERO caps; the sub-theme COUNT per section
    # EMERGES from the evidence. The faithfulness engine is UNTOUCHED (a sub-theme is a compose
    # container, never a verdict; every sentence still re-passes strict_verify downstream). O4's
    # un-starved PG_OUTLINE_MAX_TOKENS lets the partition JSON hold EVERY line-id (the 2500 starve
    # could not). Never a faithfulness gate: a model/transport failure degrades to the deterministic
    # Cross-Cutting backstop with a LOUD disclosure (residual_fraction rises), never a fake success.
    partition = None
    _part_on = os.getenv("PG_OUTLINE_SUBTHEME_PARTITION", "1").strip().lower() in (
        "1", "true", "yes", "on")
    if _part_on:
        from src.polaris_graph.generator.outline_partition import (  # noqa: E402, PLC0415
            partition_outline_subthemes,
        )
        _sections_spine = [{"title": str(p.title), "focus": str(p.focus)} for p in plans]
        partition = asyncio.run(partition_outline_subthemes(
            sections=_sections_spine, menu=menu, model=model, question=question,
        ))
        subtheme_stats = {
            "partition_enabled": True,
            "naming_ok": partition.naming_ok,
            "route_call_count": partition.route_call_count,
            "domain_line_ids": len(partition.domain_ids),
            "assigned_line_ids": partition.assigned_count,
            "assigned_by_live_rounds": len(partition.assigned_by_model_ids),
            "residual_line_ids": len(partition.residual_ids),
            "residual_fraction": partition.residual_fraction,
            "subthemes_per_section": {
                t: len(v) for t, v in partition.section_subthemes.items()
            },
            "gap_round_fired": partition.gap_round_fired,
            "self_review_fired": partition.self_review_fired,
            "self_review_merges": partition.self_review_merges,
            "self_review_gaps": partition.self_review_gaps,
            "duplicate_id_count": partition.duplicate_id_count,
            "unknown_id_count": partition.unknown_id_count,
            "content_max_tokens": partition.content_max_tokens,
            "partition_in_tokens": partition.total_in_tokens,
            "partition_out_tokens": partition.total_out_tokens,
        }
        if isinstance(stats, dict):
            stats["subtheme_partition"] = subtheme_stats
        # O5 signal (map-honors-outline): the COMPOSE-stage section_basket_map (a different wheel/
        # worktree) reads this grounded line-id -> {section, subtheme} map as its strongest homing
        # signal, instead of a title-overlap guess. DISCLOSURE + DATA only (no verdict key).
        revision_audit["subtheme_partition"] = {
            "outline_assignment": partition.assignment,
            "residual_line_ids": list(partition.residual_ids),
            "residual_fraction": partition.residual_fraction,
            "self_review_gaps": partition.self_review_gaps,
        }
        print("\n=== (O1/O2/O3/O6) TWO-LEVEL SUB-THEME FULL-PARTITION ===")
        print(f"[part] domain_line_ids={len(partition.domain_ids)} "
              f"assigned={partition.assigned_count} "
              f"live_assigned={len(partition.assigned_by_model_ids)} "
              f"residual={len(partition.residual_ids)} "
              f"residual_fraction={partition.residual_fraction}")
        for _t in [str(p.title) for p in plans]:
            _sts = partition.section_subthemes.get(_t, [])
            print(f"  {_t!r}: {len(_sts)} sub-themes -> "
                  + "; ".join(f"{s['name']}({len(s['basket_ids'])})" for s in _sts))
        print(f"[part] naming_ok={partition.naming_ok} route_calls={partition.route_call_count} "
              f"gap_round_fired={partition.gap_round_fired} "
              f"self_review_fired={partition.self_review_fired} "
              f"merges={len(partition.self_review_merges)} gaps={partition.self_review_gaps} "
              f"dup_ids={partition.duplicate_id_count} unknown_ids={partition.unknown_id_count} "
              f"content_max_tokens={partition.content_max_tokens} "
              f"part_in_tok={partition.total_in_tokens} part_out_tok={partition.total_out_tokens}")
    else:
        print("\n[part] PG_OUTLINE_SUBTHEME_PARTITION=0 — two-level partition skipped (flat plans).")

    # (d) cp4 write + load (verdict-leak guarded on BOTH)
    # item 6: record the FULL effective S4 knob set + a sha256 of it as run_config_sha (until
    # RunConfig WP-0b lands) so the checkpoint can PROVE what produced it — the prior hardcoded
    # {"PG_OUTLINE_BASKET_DIGEST":"1"} + run_config_sha="" proved nothing about the actual run.
    flag_slate = _effective_s4_flag_slate(model)
    run_config_sha = hashlib.sha256(
        json.dumps(flag_slate, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    print(f"\n[d] effective S4 flag_slate={json.dumps(flag_slate, sort_keys=True)} "
          f"run_config_sha={run_config_sha[:12]}")
    # O1 two-level schema: attach each section's ordered sub-theme list to its plan dict. The compose
    # stage reads final_plans[*].subthemes (name/focus/basket_ids/ev_ids) to render an H3 per sub-theme
    # and compose per basket. Empty [] when the partition is OFF (byte-identical flat cp4).
    final_plans_data = [_plan_to_dict(p) for p in plans]
    if partition is not None:
        for _fp in final_plans_data:
            _fp["subthemes"] = partition.section_subthemes.get(str(_fp.get("title", "")), [])
    payload = build_cp4_payload(
        question_sha=hashlib.sha256(question.encode("utf-8")).hexdigest(),
        upstream=[{"stage": "basket", "sha": str(bank.get("cp3_sha", ""))}],
        run_config_sha=run_config_sha,
        flag_slate=flag_slate,
        adjustments_applied=[],
        final_plans=final_plans_data,
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

    ok = (
        bool(load_ok)
        and (order_ok in (True, None))
        and degraded_ok
        and be_gate_ok
        # fix 2: gate on the post-fold INVARIANT (the same-work fold must have made anchors distinct-
        # by-work), NOT the old tautological >=0.90 post-fold bar that could never fail. The pre-fold
        # fraction is disclosed as an informative metric (pre_fold_min_distinct_work_frac), never a bar.
        and post_fold_invariant_ok
    )
    _part_summary = (
        f"subthemes_total={sum(len(v) for v in partition.section_subthemes.values())} "
        f"assigned={partition.assigned_count}/{len(partition.domain_ids)} "
        f"residual_fraction={partition.residual_fraction}"
        if partition is not None else "partition=OFF"
    )
    print(f"\n[plan] ACCEPTANCE (a,c,d,b/e,post-fold-invariant) ok={ok}  "
          f"pre_fold_min_frac={pre_fold_min_frac:.3f} post_fold_invariant_ok={post_fold_invariant_ok}  "
          f"in_tok={in_tok} out_tok={out_tok}  [{_part_summary}]")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    # P3-3 / fix 8: reset the once-per-run junk-gate warning latch at every run entry. It is a
    # MODULE global, so in a long-lived process that runs main() more than once the collapsed-
    # predicate warning would otherwise fire only ONCE EVER (first run), silently swallowing the
    # collapse on every later run — the opposite of the fail-loud intent (§-1.3).
    global _JUNK_GATE_PREDICATE_WARNED
    _JUNK_GATE_PREDICATE_WARNED = False

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
