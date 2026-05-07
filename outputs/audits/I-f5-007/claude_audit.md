# Claude architect audit — I-f5-007

**Issue:** Inspector retracted + stale (>2y) badges
**Branch:** bot/I-f5-007
**Canonical-diff-sha256:** fa65f6f8e87681e5a2568f05bfeac19c36927fc93d55440be53bc50d0162f753
**Brief verdict:** APPROVE iter 2
**Diff verdict:** APPROVE iter 2 (iter 1 sandbox-blocked the dev-server attempt; iter 2 static review clean)

## Substrate honesty
- New backend field `Source.retracted: bool = False` — schema surface for future CrossRef/Retraction Watch wiring. Today's populator: always False.
- Frontend isStale is computed from `publication_date` (730-day threshold) — pure derivation, no backend dependency.
- Demo fixture uses runtime-fresh date for normal sources to avoid stale-fixture trap.

## §9.4 N/A frontend.

## CHARTER §1 LOC cap
- 157 net. Under 200.

## Verdict
APPROVE.
