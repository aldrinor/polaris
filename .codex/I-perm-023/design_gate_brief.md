# Codex DESIGN gate — I-perm-023 (#1215) PR-1: diversity-aware selection (forward guard) — iter 2

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings. Same quality bar regardless of iteration count.
- Reserve P0/P1 for real execution risks; cosmetic = P3/P2.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on non-P0/P1; no iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## ITER-1 RESOLUTION — the two P1s drove a design change. Verify the new design.

### P1.1 (faithfulness proof was wrong) — CORRECTED
You were right: in the sweep path `evidence_for_gen = evidence_selection.selected_rows` is passed to
`generate_multi_section_report`, which builds `evidence_pool = {ev['evidence_id']: ev for ev in
evidence}`. So strict_verify's evidence universe is the SELECTED pool, NOT the full retrieved pool.

Corrected, honest faithfulness statement (this is now the load-bearing claim — red-team it):
> Selection cannot RELAX strict_verify / the 4-role evaluator / D8 (those re-check every generated
> sentence against the cited span, unchanged). But selection BOUNDS what evidence CAN be verified: a
> sentence can only verify against an evidence_id that is in the selected pool. Therefore a worse
> selection can only REDUCE coverage/richness (fewer rows available to ground a claim) — it can NEVER
> admit a fabrication (a sentence whose cited row was dropped fails strict_verify and is removed). The
> error direction is loss of coverage, surfaced by the §-1.1 line-by-line audit + the #1213
> Coverage-gaps disclosure — never an unsupported claim shipped.

So PR-1 is still unit-testable (the selection logic is deterministic; the coverage effect is what the
§-1.1 audit measures). Confirm this corrected statement is accurate and not itself an overclaim.

### P1.2 (greedy branch must replicate all floors) — RESOLVED BY NOT TOUCHING THE FLOORS
Your core requirement: the new path must NOT be weaker than the floor stack it replaces (T1/T2/T3 tier
floors, M-42e/M-51 primary custody, M-42c mechanism-≥3, M-41d jurisdiction, M-42d HC, with family caps
yielding to protected rows). Re-implementing that entire stack in a new OWNING branch is exactly where
a regression hides.

**New architecture (changed from iter-1):** do NOT add a new owning branch. Add the constrained-greedy
diversity step as a THIRD diversity PASS in the existing #956 region — `evidence_selector.py:1708-1738`
— immediately AFTER `_apply_domain_cap` and BEFORE the final sort (1743). This is the SAME mechanism
the codebase already uses for source diversity (`_reserve_subqueries`, `_apply_domain_cap`): same-tier
swaps on POST-FLOOR slack, honoring the exact existing `protected_ids` set
(`m42e_primary_ids | m42c_mech_ids | m51_inserted_ids | _t3_floor_protected_ids`, plus the rows the
subquery/domain passes brought in).

Why this resolves P1.2 BY CONSTRUCTION:
- Every floor (tier quotas + M-42e + M-42c + M-41d + M-42d + M-51) runs UNCHANGED, byte-for-byte. The
  greedy pass never reserves, never evicts a `protected_ids` row, never alters a quota. So it is
  structurally INCAPABLE of being weaker than the floor stack — it only reorders the non-protected
  free-fill slack (the same rows `_apply_domain_cap` is already allowed to swap).
- Family-cap precedence is inherited: `protected_ids` rows are off-limits to the swap, identical to how
  `_apply_domain_cap` already protects them.
- Fail-closed: infeasible env settings (e.g. a coverage axis with zero candidates in slack) → the pass
  makes no swap and logs, never raises, never drops below the floor.

The pass: for each diversity axis bucket NOT yet covered among selected rows (entity_id ∪
safety_category ∪ evidence_class ∪ jurisdiction), if a non-selected same-tier candidate would add a
novel bucket, swap it for the LOWEST-marginal-value non-protected selected row in that tier (deterministic:
swap target chosen by `(redundancy desc, -relevance, tier_priority, original_idx)`; total order). Bounded
iterations (env `PG_GREEDY_MAX_SWAPS`). Telemetry: `diversity_score` (DIAGNOSTIC-only, not a §-1.1
superiority signal — unique-source counts are banned as quality), per-axis covered buckets, swaps made →
`notes` + `to_dict()`.

This is SOFT coverage (best-effort swaps), consistent with #956 — NOT a hard per-class reservation
(which WOULD compete with the tier floors and is explicitly OUT of scope; hard min-1-primary-per-entity
is already provided by M-51 + M-42e). Confirm soft coverage is the right strength for a forward guard
(vs a hard reservation that risks displacing a floor).

## HARD CONSTRAINTS (operator-locked — not consultable)
1. §-1.1 faithfulness non-negotiable; strict_verify / 4-role / D8 NEVER relaxed (see corrected proof).
2. Default-OFF byte-identical: `PG_SELECT_CONSTRAINED_GREEDY` read at CALL TIME (not import — the
   I-cap-005 lesson). OFF → the new pass is never invoked → byte-identical (same kill-switch shape as
   `_subquery_reserve_config` / `_domain_cap_config`).
3. Deterministic only — no RNG/DPP; total-ordered tiebreaks (replay bit-identical).
4. LAW VI: all weights/caps/axis vocab are env knobs (`PG_GREEDY_*`), call-time read.
5. PR-1 ONLY. PR-2 (SourceEvidencePack cache + MAP de-sectioning) is a SEPARATE follow-up — behavioral,
   faithfulness proof requires a PAID §-1.1 audit (operator-gated), not a unit test. Do not fold it in.

## Forward-guard honesty (confirm I am NOT overselling)
At drb_76 scale pool=46 ≤ cap=150 → the short-pool pass-through returns BEFORE this region runs (the
#956 passes + this new pass only execute on the truncating path, `len(scored) > max_rows`). So this is a
**no-op at drb_76 scale** (matches manifest: 46/46 selected, dropped_count=0,
strategy=tier_balanced_v1_all_m46_ordered). It only diversifies once I-perm-007 grows the post-extraction
pool past the cap (the 1000-URL target). The drb_76 monoculture is finding-level + upstream-extraction
(I-perm-007 + #1213), OUT of scope. Confirm the scope fence.

## Questions for you (DESIGN ruling before I write the pass)
1. Is the "third #956-style diversity pass on post-floor slack" the right shape (vs the new owning
   branch from iter-1)? It resolves P1.2 by construction (floors untouched) and matches the existing
   `_apply_domain_cap` pattern. Any reason a new owning branch is still preferable despite the floor-
   replication risk?
2. Axis set entity ∪ safety_category ∪ evidence_class ∪ jurisdiction (you suggested jurisdiction as the
   4th). Is mechanism already adequately covered by the M-42c hard floor (so it need NOT be a 5th
   greedy axis), or should mechanism be a soft axis too?
3. Soft coverage swaps (best-effort, #956-style) vs hard per-class reservation: confirm soft is the
   right strength for a forward guard and hard reservation is correctly OUT of scope (it would compete
   with floors).
4. Test parity: I will add a test asserting the new pass NEVER evicts any `protected_ids` row and is a
   no-op when OFF / when pool ≤ cap. Is that the right parity assertion, plus a test that a monoculture
   slack gets diversified when pool > cap?

## Honest scope
PR-1 only: a deterministic, default-OFF, post-floor-slack diversity pass (forward guard, no-op until the
pool exceeds the cap). Floors untouched (parity by construction). Faithfulness profile identical to the
existing #956 passes. Unit-testable; no paid run required to land it. PR-2 deferred (paid §-1.1 audit).
