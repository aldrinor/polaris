# Claude architect audit — I-f12-003

## Issue scope

Claim-level diff algorithm. Acceptance: diff sample fixtures.

## What landed

`src/polaris_v6/compare/claim_diff.py` — `compute_claim_diff(left, right)` returns `ClaimDiffReport` with per-section best-Jaccard pairing of shipped sentences classified on a 2-axis matrix (text-overlap × evidence-id-overlap). Provenance markers stripped from sentence_text before tokenization (P1 fix on iter-1 diff review). Same-run-id rejected. Drop-reasoned sentences filtered before pairing (P1 fix on iter-2 brief review).

`tests/v6/compare/test_claim_diff.py` — 9 tests covering matrix cells + only_left + counts aggregation + drop filter + same-run guard + provenance-stripping.

## Architectural alignment

- **Plan F12 (compare runs):** complements pool-level `differ.py`. Frontend integration is downstream (I-f12-004+).
- **CLAUDE.md §9.4 hygiene:** clean.
- **CHARTER §3 LOC:** 209 net (slight overage on a tight spec; the +9 lines are the iter-1 P1 fix for provenance-stripping + its dedicated test).

## Verdict

Ready to merge. 9/9 pass. Codex brief APPROVE iter 3 (matrix complete + drop_reason filter + LOC trim); Codex diff APPROVE iter 2 (provenance-stripping P1 fixed iter-1).
