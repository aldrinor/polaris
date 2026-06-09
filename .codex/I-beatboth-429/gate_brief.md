HARD ITERATION CAP: 5 per document. This is iter 2 of 5.

ITER-2 CHANGELOG (addressing your iter-1 P1 "bound Retry-After before sleeping + update test"):
- The retry delay now clamps BOTH the `Retry-After` header value AND the exponential backoff to `PG_ROLE_HTTP_BACKOFF_CAP_SECONDS`: `if delay is None: delay = backoff_base * 2**attempt` then unconditionally `delay = min(backoff_cap, delay)`. A hostile/misconfigured `Retry-After: 7200` can never make the judge sleep past the cap.
- Test updated: `test_retry_after_header_is_honored_within_cap` raises the cap above 7 to prove the header IS read+preferred (slept==[7.0]); NEW `test_retry_after_is_clamped_to_cap` proves a 7200s Retry-After clamps to the 0.05 cap (slept==[0.05]). Full file: 9 passed.

- Front-load ALL real findings in iter 1. No drip-feeding.
- Reserve P0/P1 for real execution/faithfulness risks; classify non-blockers as P2/P3.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
- Output: a final line `verdict: APPROVE` or `verdict: REQUEST_CHANGES`, plus a short blockers list.

# Diff review — I-beatboth-429 (#1173): 4-role role transport HTTP 429/503 backoff-retry

## Context
The beat-both 5-question run generated real reports (drb_72 75-verified, drb_75 74-verified sentences) but EVERY question's 4-role seam HELD release on `RoleTransportError: OpenRouter 'judge' returned HTTP 429`. Root cause: `openrouter_role_transport.py` retried ONLY `httpx.TransportError`; a non-200 status (incl 429 rate-limit) raised immediately with no retry. The judge makes one call per claim (~178 for drb_72) → a burst trips OpenRouter's rate limit.

## The change (RESILIENCE ONLY — must be FAIL-CLOSED)
Add bounded exponential-backoff retry on retryable HTTP statuses (default 429, 503) honoring `Retry-After`, env-driven (PG_ROLE_HTTP_RETRY_MAX / _STATUS / _BACKOFF_BASE_SECONDS / _CAP_SECONDS), before the existing non-200 raise. Unit test (8 cases) passes: 429-then-200 → succeeds; always-429 → RoleTransportError after bounded retries (fail-closed).

## VERIFY (be adversarial — this is the FAITHFULNESS-CRITICAL 4-role transport)
1. FAIL-CLOSED preserved: after retries are exhausted (or a non-retryable non-200), the call STILL raises `RoleTransportError` → release HELD. A 429 can NEVER produce a fake/empty/silent verdict or a silent release. Confirm no path swallows the error or returns a default verdict.
2. The verdict-parsing, blank-verdict recovery, budget-cap accounting, and provider-exclusion logic are UNCHANGED (only the HTTP-status retry was added).
3. Backoff is BOUNDED (cannot hang forever) and env-driven (LAW VI, named constants, no magic numbers). Retry-After parsing is safe on a missing/non-numeric header.
4. No new faithfulness weakening anywhere; the 4-role gate's authority is intact.
5. The test genuinely exercises both the success-after-retry and the fail-closed-after-exhaustion paths (not a tautology).

----- BEGIN UNIFIED DIFF UNDER REVIEW -----

