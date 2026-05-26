# PR #912 — I-gen-005 Step 3h Claude architect review

Real-V4-Pro smoke (PG_ATOM_REFUSAL_MODE=log_only) caught 3 bugs that
unit tests + Codex theory review missed:
1. Splitter `;` inside parens (CI bounds) — false refusals
2. Unicode minus mismatch — false soft mismatches
3. Smoke print U+2192 — Windows cp1252 crash

All 3 fixed + regression-tested. 120/120 pass.

Operator re-run after merge should show refusal_rate < 30%
(predicted; not yet verified).

Codex iter-1: APPROVE. Ready to merge.
