# PR #913 — Step 3i V4 Pro prompt tighten

Codex design review (this session) APPROVE'd the tightened wording with 2 P2 refinements:
1. Design-context numbers carve-out (dose, arms, N, phase, duration)
2. Multi-value sentence per-claim rule + balancing RIGHT narrative example

Both applied in the final wording.

Real-data targets:
- efficacy.s005 (responder rates) — atom_NNN expected
- safety.s000/s001 (per-row safety) — OMIT expected (catalog gap addressed in Step 3k)
- merged efficacy.s001-004 (treatment differences) — OMIT expected
- efficacy.s009 (trial design) — narrative-allowed (Step 3j handles detector)

Verification: 102/102 tests pass. Imports clean. Ready for merge.
