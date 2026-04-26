V30 joint analysis cross-review — xhigh reasoning.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

The user pushed back that prior wishlist work was self-mirroring. We
ran two parallel research streams and produced three synthesis docs:

  1. Real-user research (35 + 32 primary sources) at
     `outputs/codex_findings/v30_real_user_wishlist/SYNTHESIS.md`

  2. Joint commercialization plan (Phase A-D, ETAs, decisions) at
     `outputs/codex_findings/v30_phase2_to_production_plan/JOINT_PLAN.md`
     — pivoted to AUDIT-LANE-ONLY (no preview lane) + Evidence Inspector
     5-view UI per user mandate "best of the best quality" +
     "biggest impact / differentiation UI"

  3. Joint user-wishlist analysis at
     `outputs/codex_findings/v30_user_wishlist_plan/JOINT_ANALYSIS.md`
     — reconciles your earlier `findings.md` (the per-wish deep dive)
     with Claude's framing AND the real-user research AND the
     audit-only + Evidence Inspector pivot

You've reviewed (1) and (2) implicitly because you produced (1)'s
findings.md and the source for (2). You have NOT reviewed (3) —
the JOINT_ANALYSIS.md is Claude's synthesis pass-1.

## Your job

Review `outputs/codex_findings/v30_user_wishlist_plan/JOINT_ANALYSIS.md`
critically. Per autoloop V2 protocol: green / disagree / partial.

## Specific things I want your honest take on

1. **The 7-wish triage** — ship-now vs ship-later vs trap. Claude split
   them as:

   - SHIP NOW (Phase B bounded): #4 chart/table, #2 10-50 docs upload,
     #1 Workspace Brief
   - SHIP LATER (Phase C): #3 visible memory, #6 citation-bound deck
   - TRAP defer/never: #5 infographic, #7 video/audio

   Are any of these miscategorized? Specifically:
   - Should slide deck (#6) move earlier (Phase B beta)?
   - Is the Workspace Brief (#1 bounded) actually feasible in Phase B
     given that V30 today is contract-anchored single-question, not
     multi-document corpus synthesis?
   - Is bounded upload (#2 at 10-50 docs) underestimated at 15-25 days
     when persistent workspace Chroma + parser pipeline + provenance UI
     all need product-hardening?

2. **Composition architecture** — Claude bought your "one composition
   core, multiple renderers" recommendation wholesale. Does that still
   hold given the audit-lane-only + Evidence Inspector pivot? Or does
   it shift in some way (e.g., Evidence Inspector becomes the canonical
   renderer, all other renderers feed BACK into inspector views)?

3. **Snowball + upload architecture** — 6-layer stack (ingestion /
   corpus-store / index / memory / retrieval / governance). Is the
   layering correct, or does it conflate concerns? Specifically: should
   the memory layer be split into "session memory" and "workspace
   memory" given the audit-grade requirement that memory be USER-VISIBLE
   and DELETABLE?

4. **The "1-click magic" UX call** — Claude said "1 click to start
   yes; 1 click to trust no" and that the Evidence Inspector is what
   makes trust visible. Does that hold under the audit-only single-lane
   pivot? Or does cutting the Preview lane create a different UX
   problem (e.g., user clicks once, then waits 2h25m with nothing to
   look at)?

5. **PRD bundle scope sanity** — 52-86 eng days = 5-9 weeks for a
   small team. Realistic? Or is Claude underestimating because
   Evidence Inspector + bounded upload + Workspace Brief + chart/table
   are all doing significant new product work simultaneously?

6. **What did Claude miss** — same question as last time. Things you
   see that aren't in the JOINT_ANALYSIS.md.

7. **Specific risks Claude undercounts** — particularly around:
   - PHI creep once uploads ship (you flagged this)
   - Editorial QA throughput for templates becoming Phase C bottleneck
   - The single-lane 2h25m UX gap (no progressive output)

## What you should output

Write to `outputs/codex_findings/v30_joint_analysis_review/findings.md`:

```markdown
# Codex review of V30 joint user-wishlist analysis

## Verdict
GREEN / PARTIAL / DISAGREE

## Per-wish triage assessment
For each of the 7 wishes:
- Claude's call (ship-now / ship-later / trap)
- Codex's call
- Agreement / disagreement / nuance
- If disagreement: specific reasoning + recommended fix

## Composition architecture
Does it hold under audit-only + Evidence Inspector pivot?

## Snowball + upload
Layering correctness; memory split call

## 1-click UX
Does the audit-only single-lane create a 2h25m blank-stare problem?
What replaces the Preview lane as the time-to-first-value mechanism?

## PRD bundle scope
Realistic ETA or underestimated?

## What Claude missed
Specific gaps Claude didn't address.

## Risks Claude undercounts
Concrete probability+impact assessment.

## Recommended fixes to JOINT_ANALYSIS.md
Specific edits if any.
```

Be direct. Under 600 lines. Full xhigh budget. Disagreements welcome —
that's the point of cross-review.
