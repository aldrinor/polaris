# Codex round 2 — M-PROD-4 v2 (1 P0 + 6 P1 closed)

## Pre-flight
- Branch: `polaris`
- Commit: `1c182fd`

## R1 closures (all 7 blockers)

**P0 [scope fictional]:** rewrote both docs to match reality
- 3 clinical templates (not 5 domains)
- M-INT-4/5 telemetry-only (not enforcing) in v1.0
- Code-backed refusal matrix with file:line refs

**P1 #1 [12 vs 13 count]:** consistently 13 throughout
**P1 #2 [migration order wrong]:** smoke (step 3) before gate (step 4)
**P1 #3 [M-LIVE-2 input wrong]:** documents actual phase_g auto-discovery
**P1 #4 [SOC2 21/21 stale]:** updated to 28/28 (3 occurrences)
**P1 #5 [pricing $TBD stale]:** full table from canonical source
**P1 #6 [refusal matrix lies]:** honest "what v1.0 actually enforces" with code refs

## Acceptance bar
1. Factual correctness — every LOCKED claim maps to verdict brief
2. Substrate count = 13 throughout
3. Refusal matrix backed by actual code
4. Migration guide commands run cleanly when followed in order
5. Pricing/compliance posture matches canonical sources

## Severity rubric
**APPROVE iff zero P0 + zero P1.**

## Reviewer instructions
- Find ALL P0/P1 defects. If zero, write "no P0/P1 found"
  explicitly.
- Do NOT re-raise R1 findings already addressed.
- Run the migration guide end-to-end again; it should now work
  in the documented order.

## Anti-nits (do NOT flag)
- Prose/tone preferences
- R1 findings already addressed
- Stylistic suggestions for "more docs"

## Round metadata
Round 2 of 5 hard cap.
