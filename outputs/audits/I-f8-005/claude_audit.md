# Claude architect audit — I-f8-005

**Issue:** Guideline-vs-trial evidence-type tag
**Branch:** bot/I-f8-005
**Canonical-diff-sha256:** 01abb5399460a952a17a2632ae47023b837c92960355b68905951dc6de157bd1
**Brief verdict:** APPROVE iter 1
**Diff verdict:** APPROVE iter 1 (0/0/0/0)

## Substrate honesty
- 7-value Literal evidence_type on ContradictionSide; defaults "unspecified" → no badge.
- Demo sec_x:29 exercises trial-vs-guideline case; Playwright asserts both tags.

## §9.4 N/A frontend.

## CHARTER §1 LOC cap
- 130 net. Under 200.

## Verdict
APPROVE.
