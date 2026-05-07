# Claude architect audit — I-f6-002

**Issue:** Edge-aware tooltip positioning
**Branch:** bot/I-f6-002
**Canonical-diff-sha256:** 79c6ca6e48e843093b80641239f07b38a670e879a0e77b69506d70f75261b844
**Brief verdict:** APPROVE iter 2
**Diff verdict:** APPROVE iter 1 (0/0/0/0)

## Substrate honesty
- Optional `side?` prop with `"top"` default; existing callers unaffected.
- Harness exercises 3 deliberately-clipping side requests; Playwright asserts viewport-bounded popups.
- Base UI default flip+shift collision avoidance is the production behavior.

## §9.4 N/A frontend.

## CHARTER §1 LOC cap
- 106 net. Under 200.

## Verdict
APPROVE.
