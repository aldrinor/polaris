# Codex Diff Review — I-anti-004 (ITER 2 of 5)

## Iter 2 changes per Codex iter 1

- **P1 (session-shared broker)**: removed `polaris_broker.get_broker(use_stub=True)` call from test 5 per Codex's iter-1 P1. Test 5 now relies solely on the session-shared broker installed by `tests/v6/conftest.py:31-33` and exercises the actor via `actor.fn()`. No more risk of replacing the broker mid-suite. Test renamed to `test_nightly_actor_invokes_underlying_callable`. 5/5 tests still pass locally.



```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-anti-004 — Nightly anti-sycophancy eval. Brief APPROVE'd iter 1 (one P2 around stub-broker test pattern).
- **Diff under review:** `.codex/I-anti-004/codex_diff.patch` (canonical-diff-sha256 in trailer).
- **Files changed:**
  - NEW `src/polaris_v6/anti_sycophancy/__init__.py` (empty)
  - NEW `src/polaris_v6/anti_sycophancy/nightly_eval.py` (~75 LOC)
  - NEW `tests/v6/anti_sycophancy/__init__.py` (empty)
  - NEW `tests/v6/anti_sycophancy/test_nightly_eval.py` (~55 LOC, 5 tests)

## P2 fix from brief iter 1

Codex flagged: "broker has no Results middleware so .send().get_result() would fail." Test 5 now uses `actor.fn(...)` (which exercises the Dramatiq-decorated function directly without the broker .send pipeline) AND captures structured-log via `caplog`. This proves both the dict contract and the log emission per criteria 3 + 4.

## Acceptance criteria (from brief APPROVE iter 1)

1. ✅ `run_nightly_anti_sycophancy_eval_impl` + Dramatiq actor `run_nightly_anti_sycophancy_eval` exist.
2. ✅ Loads corpus + responses, validates coverage, computes mean stance_delta.
3. ✅ Emits structured log line on every run (line 65-71 in nightly_eval.py).
4. ✅ Returns dict with N, mean_delta, threshold, verdict.
5. ✅ 5 tests pass (verified locally).
6. ✅ LOC ~130 under 200 cap.

## Red-team checklist

1. **Coverage validation invariant** — same set-equality + len + duplicate validation as I-anti-003 CI gate (lines 36-50).
2. **Logger string format** — uses `logger.info("...", arg1, arg2)` lazy formatting, not f-string.
3. **Threshold default 0.05** — matches I-anti-003 gate.
4. **Actor decorator** — `max_retries=2, time_limit=10*60*1000` (10min); reasonable for nightly eval.
5. **Test 5 honest** — calls `.fn()` not `.send()` per Codex iter-1 P2 guidance.
6. **§9.4 hygiene** — no try/except: pass, no mock in src, no magic numbers (DEFAULT_THRESHOLD constant), no sleep, no TODO.
7. **CHARTER §3 LOC** — ~130 LOC under 200.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
