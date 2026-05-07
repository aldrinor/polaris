# Claude architect audit — I-f5-006

**Issue:** Inspector synthesis-claim badge
**Branch:** bot/I-f5-006
**Canonical-diff-sha256:** c2b18a4f19fffdb053547a408c1cd590601414a9a937605895326ff469157776
**Brief verdict:** APPROVE iter 3
**Diff verdict:** APPROVE iter 1 (0/0/0/0)

## Substrate honesty
- New schema field + 3-clause validator (synthesis with tokens forbidden / synthesis with fail forbidden / non-synthesis kept tokenless forbidden — schema gap closed).
- strict_verify gains opt-in `is_synthesis_claim` param; default False preserves existing behavior. Future Issue may wire this into the prompt template.
- Frontend optional field with defensive undefined-falsy default — no badge unless explicitly flagged.

## §9.4 N/A frontend.

## CHARTER §1 LOC cap
- 172 net. Under 200.

## Verdict
APPROVE.
