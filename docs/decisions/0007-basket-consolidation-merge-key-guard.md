# 0007. Consolidate into corroboration baskets; guard the merge key against false-merge

Status: accepted

Date: 2026-06-15

## Context

Moving from single-span faithfulness to basket faithfulness (ADR 0006, principle 3) must STRENGTHEN the gate, not weaken it. The forbidden regression is "a claim is supported if ANY one basket member loosely supports it" — an OR that lowers the bar.

The Wave-3 consolidation stress test (`pipeline_redesign_master_plan.md` §6; `docs/consolidation_design_wave3.md`) surfaced a subtler danger. `strict_verify` runs per member and never cross-compares members. So span-grounding CANNOT catch a false-merge: if two distinct claims are wrongly fused into one basket, each still grounds its own span and passes — while fabricating a corroboration COUNT that was never real. A false-merge is a fabrication the faithfulness engine is structurally blind to.

## Decision

Basket verification is an AND over independent grounding: every basket member is still independently span-grounded; the basket only ADDS corroboration metadata. Never accept the ANY-member OR.

Because the faithfulness engine cannot see a false-merge, the ONLY place to stop it is the consolidation merge key. Every discriminating merge-key slot that can be empty must be sentinel-guarded so it can never wildcard-merge two distinct claims.

## Consequences

- The merge key, not the faithfulness gate, is the sole defense against inflated corroboration counts. It must be designed and reviewed as a safety-critical component, not a convenience.
- An empty or missing key slot is a hazard: without a sentinel, it matches everything and silently fuses unrelated claims. Guard every such slot.
- This is why the corroboration count is trustworthy downstream: it can only go up when genuinely independent members ground the same claim, never when a loose match or a blank field merges them.
- The insight generalizes: when a per-item check cannot see a cross-item error, move the defense to the step that creates the grouping.
