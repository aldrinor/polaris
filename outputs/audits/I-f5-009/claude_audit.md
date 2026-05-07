# Claude architect audit — I-f5-009

**Issue:** F5 functional — every assertion gated-and-clickable
**Branch:** bot/I-f5-009
**Canonical-diff-sha256:** d1bb66c945e91770d7201d192a7aac5d6918b5035e13d4a1d4ec0b3ae6d0011b
**Brief verdict:** APPROVE iter 1
**Diff verdict:** APPROVE iter 1 (0/0/0/0)

## Substrate honesty
- Schema field `assertion_surface` defaults to "prose"; future generator emission of non-prose surfaces is the substrate target.
- Frontend coerces undefined → "prose" defensively (Codex iter-1 P2 fix).
- Demo exercises all 5 non-prose surfaces with dedicated rows.

## §9.4 N/A frontend.

## CHARTER §1 LOC cap
- 161 net. Under 200.

## Verdict
APPROVE.
