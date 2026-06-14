# Codex DIFF gate — I-arch-004 A1 (#1248): section-generation crash isolation

HARD ITERATION CAP: 5 per document. This is iter 4 of 5.

## ITER-3 RESOLUTION (your 1 P1 fixed — please verify)
Your iter-3 P1 was correct: `_TRANSIENT_SECTION_FAILURES` caught builtin `ConnectionError`/`OSError`, which are NOT the exceptions OpenRouter re-raises — so a real transport failure would still crash, and broad `OSError` masked `FileNotFoundError`. Fixed: the tuple now mirrors the EXACT retryable set the client re-raises after MAX_RETRIES (`openrouter_client.py:2046-2059`): `(asyncio.TimeoutError, TimeoutError, httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError, httpx.ReadError)`. Dropped the broad `OSError`; deliberately NOT `httpx.TransportError` parent (would swallow ProxyError/UnsupportedProtocol/DecodingError) and NOT `httpx.HTTPStatusError`. Added `import httpx`. New tests: parametrized over `RemoteProtocolError`/`ConnectError`/`ReadError`/`ReadTimeout` (→ gap-stub), plus `FileNotFoundError` and `httpx.HTTPStatusError` (→ propagate fail-loud). 11 A1 tests + 62 regression pass.

## ITER-2 RESOLUTION (all 3 findings fixed — please verify)
Your iter-2 verdict was REQUEST_CHANGES (2 P1 + 1 P2). All fixed:
- **P1 (siblings not actually cancelled):** you were right — plain `asyncio.gather` propagates but does NOT cancel siblings. `_gather_sections_isolated` (and the M-50 gather) now drive explicit `asyncio.ensure_future` tasks and, on ANY non-transient exception, `cancel()` the pending siblings + drain (`gather(..., return_exceptions=True)`) BEFORE re-raising. The strengthened test `test_budget_exceeded_propagates_and_cancels_siblings` now asserts the sibling caught `CancelledError` (explicit cancel, not `asyncio.run` teardown).
- **P1 (Budget hard gate swallowed in regen):** the M-44 regen (`:5933`), M-47 regen (`:6136`), and the fact-dedup safe-degrade (`:5825`) now re-raise `(CredibilityPassError, BudgetExceededError)` — the cost-cap gate is fail-loud in all three.
- **P2 (gap-stub leaks into analyst synthesis):** the `verified_prose_joined` join (`:6317`) now filters `if sr.verified_text and not sr.is_gap_stub` — the placeholder text no longer reaches analyst synthesis as verified prose (also closes the same latent leak for the no-evidence stub).
- 6 A1 tests + 62 regression (m50/gap4/m44/limitations) pass.

## ITER-1 RESOLUTION (all 3 of your P1s fixed — please verify)
Your iter-1 verdict was REQUEST_CHANGES with 3 P1s. The fix was a single cleaner restructure that addresses all three:
- **P1-1 (stub silently filtered):** the gap-stub now sets `dropped_due_to_failure=False` (was True), matching the no-evidence stub at `:2762` — so the assembly filter `if not sr.dropped_due_to_failure` RENDERS it as a visible curator-actionable gap. (`is_gap_stub=True` + 0 verified sentences keep it out of verified-prose consumers.)
- **P1-2 (programming defects masked) + P1-3 (hard gates fail-late):** `_gather_sections_isolated` now catches ONLY `_TRANSIENT_SECTION_FAILURES = (asyncio.TimeoutError, TimeoutError, ConnectionError, OSError)` INSIDE each task, and uses a PLAIN `asyncio.gather` (no `return_exceptions`). So a transient timeout → gap-stub (siblings live); ANY other exception — hard gates (`CredibilityPassError` / `BudgetExceededError`) AND programming/config/schema defects (`AttributeError`, `NoEndpointError`, `ReasoningFirstTruncationError`) — PROPAGATES out of the plain gather, which CANCELS the sibling tasks (fail-fast) and aborts. M-50 uses the same catch-inside pattern (transient → drop the additive subsection; everything else propagates).
- **New tests prove it:** `test_programming_defect_propagates_not_stubbed` (AttributeError raises, not stubbed); `test_budget_exceeded_propagates_and_cancels_siblings` (asserts the sibling was cancelled before finishing = fail-fast); `test_credibility_pass_error_propagates_fail_loud`; `test_gap_stub_is_visible_and_zero_verified` (dropped_due_to_failure False). 6 new + 57 regression (m50/gap4/m44) pass.

Verify the updated diff at `.codex/I-arch-004/A1_crash_isolation/codex_diff.patch`. Original brief (still accurate for context) below.

---

- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Your job
VERIFY this diff (hand-delivered evidence pack below — do not hunt). It is the P0 crash-isolation fix for the dead drb_72 run. Red-team it per `.codex/codex_red_team_checklist.md`. The diff is at `.codex/I-arch-004/A1_crash_isolation/codex_diff.patch`; the live edited file is `src/polaris_graph/generator/multi_section_generator.py` and the new test is `tests/polaris_graph/test_section_crash_isolation_iarch004.py`.

## The bug (proven from run data)
The paid run `drb_72_ai_labor` ran 3h20m ($6.74/$25), sailed through retrieval/weight/consolidate/select, then **died composing the V30 narrative section**. `run_log.txt` traceback: `_run_section_with_wallclock:93` raised `TimeoutError` ("section generation exceeded 600s wall-clock x2") → it propagated out of a **bare** `asyncio.gather` at `multi_section_generator.py:5509`, cancelled the sibling sections, hit the broad outer except in `run_honest_sweep_r3.py`, and the whole run became `status=error_unexpected`. One slow section discarded everything.

Three section-path gathers lacked `return_exceptions=True`: contract `:5509`, legacy `:5550`, M-50 subsections `:6432`. (The M-44 regen gather at old `:5846` ALREADY uses `return_exceptions=True` + a CredibilityPassError re-raise — this diff mirrors that existing idiom.)

## What the diff does
1. New constant `_SECTION_FAILED_GAP_STUB_SENTENCE` + helper `_section_failure_to_gap_stub(plan, exc)`: maps a transient section failure to a VISIBLE gap-stub `SectionResult` (`is_gap_stub=True`, `dropped_due_to_failure=True`, `sentences_verified=0`, `error="section_generation_failed: ..."`). Mirrors the existing no-evidence gap-stub at `:2699`.
2. **Fail-loud carve-out (the safety-critical part):** the helper RE-RAISES — never stubs — `CredibilityPassError` (faithfulness-coverage hard gate), `BudgetExceededError` (cost-cap hard gate, invariant #6), and `KeyboardInterrupt`/`SystemExit`/`asyncio.CancelledError`. Only TRANSIENT failures (the wall-clock-x2 TimeoutError, flaky transport) become gap-stubs.
3. New helper `_gather_sections_isolated(plans, runner_for)`: `gather(return_exceptions=True)` + index-aligned mapping via the mapper. Contract (`:5509`) and legacy (`:5550`) gathers now call it.
4. M-50 additive subsection gather: `return_exceptions=True`; a failed additive subsection is dropped (logged), with the SAME fail-loud carve-out re-raised.

## Why faithfulness is NOT relaxed
- The gap-stub carries ZERO verified sentences and `is_gap_stub=True` — every downstream consumer already treats that as "not verified prose" (see the `is_gap_stub` field doc + BB5-P07 exec-summary skip).
- strict_verify / NLI / 4-role / provenance run UNCHANGED on the sections that DID generate.
- `CredibilityPassError` + `BudgetExceededError` still abort the run (re-raised) — no hard gate is downgraded into a content gap.
- OFF/happy path is behavior-identical: with no section failure, `return_exceptions=True` changes nothing (every result is a `SectionResult`).

## Adjacent-file scan (checked and clean)
- All `asyncio.gather` in `multi_section_generator.py`: `:406` (new helper, isolated), `:5915` (M-44 regen, already isolated), `:6504` (M-50, now isolated). No other section-path gather exists.
- `run_honest_sweep_r3.py:6093` outer caller: previously turned the TimeoutError into `error_unexpected`; with this fix the report completes with a gap-stub instead. (A2 — proper timeout sizing so the section actually finishes — is a SEPARATE follow-up PR; this PR is the crash-isolation safety net only.)
- `SectionResult` fields used by the stub match the proven `:2699` no-evidence stub constructor.

## Tests (offline, passing)
`tests/polaris_graph/test_section_crash_isolation_iarch004.py` — 6 tests, all pass:
- timeout → visible gap-stub (zero verified); CredibilityPassError / BudgetExceededError / CancelledError each re-raise (never stubbed); one section timeout does NOT cancel its two siblings (index alignment preserved); CredibilityPassError inside the gather propagates fail-loud.
Regression: existing `test_m50_per_trial_subsections.py` + `test_multi_section_gap4.py` + `test_m44_*` + `test_multi_section_limitations_r1.py` = 62 passed. Module import OK.

## Output — required schema (last `verdict:` line is CI-parsed)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
Specific things to red-team: (a) does any fail-loud exception type still get swallowed into a gap-stub? (b) is the index alignment between `plans` and results actually preserved on the failure path? (c) any consumer of `section_results` that would mis-handle a gap-stub at a NEW position (e.g. cross-trial synthesis, fact-dedup, M-44 regen, assembly)? (d) could `return_exceptions=True` mask a real programming bug that SHOULD crash (vs a transient)?
