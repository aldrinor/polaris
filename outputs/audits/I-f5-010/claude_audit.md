# Claude architect audit — I-f5-010

**Issue:** F5 adversarial — paywalled / multi-span bad / T1-vs-T1 conflict
**Branch:** bot/I-f5-010
**Canonical-diff-sha256:** 36aa1036cb541050930edab69b58a5116c2a3da38b08e2b0f0abf33313a7991b
**Brief verdict:** APPROVE iter 1
**Diff verdict:** APPROVE iter 1 (0/0/0/0)

## Substrate honesty
- Paywalled badge driven by existing `Source.full_text_available: false`; no new schema.
- T1-conflict caption is HEURISTIC — explicit "may conflict — review" tooltip + "heuristic, not semantic detection" framing. Not silent overclaim.
- Negative test asserts conflict caption ABSENT for single-T1 sentence (regression guard).

## §9.4 N/A frontend.

## CHARTER §1 LOC cap
- 140 net. Under 200.

## Verdict
APPROVE.
