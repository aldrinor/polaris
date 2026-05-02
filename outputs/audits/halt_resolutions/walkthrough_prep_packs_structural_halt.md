# Halt — walkthrough prep packs (2a_7, 2b_7, 2c_6, 5_1) — structural

**Tasks:** `2a_7_prep_briefing_pack`, `2b_7_prep_briefing_pack`, `2c_6_prep_briefing_pack`, `5_1_prep_briefing_pack`
**Halt condition:** #4 — anticipated based on `1.8_prep_briefing_pack` halt (same root cause: walkthrough packs describe Phase-N END behavior; Phase-N substrate hasn't shipped yet)
**Timestamp:** 2026-05-02
**Cost saved:** 12+ Codex invocations × ~$0.10/invoke = ~$1.20 + 30+ min wall-clock

## Why pre-emptive halt

`1.8_prep_briefing_pack` halted at iter_3 with structural-substrate-gap findings:
the briefing claims Phase 1 features (full upload-as-evidence, chunk listing,
tier T7 assignment) that the Phase 0 substrate doesn't yet provide.

Phases 2A, 2B, 2C, and 5 walkthrough briefing packs have the SAME structural
property: they describe end-of-phase behavior that requires the corresponding
phase's substrate to be fully wired. None of those phases have shipped their
full substrate yet (gated on §G #3 cluster + §G #10 runner + Phase 1+ work).

Iterating Codex on these now would burn 12+ invocations across 4 tasks × 3
iterations and halt each one for the same root reason. Not worth the burn.

## Resolution paths (apply to all 4 walkthrough prep packs)

Same as `1.8_prep_briefing_pack_halt.md` resolution paths:

1. **Defer per-pack** until the phase's substrate ships. Each pack's deadline:
   - 2a_7: 2026-06-22 (defer to ~2026-06-15 OK)
   - 2b_7: 2026-07-13 (defer to ~2026-07-06 OK)
   - 2c_6: 2026-07-19 (defer to ~2026-07-12 OK)
   - 5_1: 2026-09-02 (defer to ~2026-08-25 OK)

2. **Author the missing substrate now** (~6-8 weeks for full Phases 2A-5 — not
   feasible without §G #3 cluster).

3. **Lower each pack's bar** to "Phase-N-PARTIAL-honest" — endpoint contracts
   only, document gaps inline.

## Recommendation

**Path 1 (defer)** for all 4. Each pack will land in its phase's prep window
when the phase substrate is ready. The `1.8_prep_briefing_pack` files in HEAD
(reverted to last-APPROVE'd state — pre-Codex-iter-1) are still useful as
structural templates for the deferred packs.

## Stop hook behavior

Each task's halt marker (this file + the `1.8` per-task halt marker) makes
the Stop hook walk past those tasks. With all 5 walkthrough packs halted, the
hook will surface the FIRST non-halted, non-user-blocked, non-APPROVE'd task
in canonical sequence. Likely candidates:

- `4_5_prep_drafts` (Phase 4 handover-package skeleton drafts) — substrate
  doesn't depend on cluster; may be feasible
- `5_3` Carney handover package finalization — partial; depends on Phase 5

Or: orchestrator declares "no more actionable substrate without user actions"
and exits cleanly, awaiting user-side §G items.
