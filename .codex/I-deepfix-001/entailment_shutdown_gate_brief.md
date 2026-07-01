HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- Reserve P0/P1 for real execution risks. "Don't pick bone from egg."
- Verdict APPROVE iff zero NOVEL P0 AND zero P1.
- Output schema: verdict: APPROVE|REQUEST_CHANGES + faithfulness_neutral + frozen_engine_untouched + novel_p0[] + p1[].

# Codex gate — I-deepfix-001 (#1344) entailment-judge shutdown-race fix

## The bug (traced from a live run)
A paid drb_72 run COMPLETED cleanly at the deliverable level — report.md written, 180/180 per-claim
strict_verify verified, four_role (D8) done — but the run's FINAL status was `error_unexpected` and the
scores manifest was a 750-byte error stub. Root cause (grep'd from the log):
`entailment judge error (final): cannot schedule new futures after interpreter shutdown`.
At the very end, straggler entailment-judge retries (transient DNS/429 -> provider-rotate) called
`ThreadPoolExecutor.submit()` AFTER the interpreter began shutting down. `submit()` raises
`RuntimeError('cannot schedule new futures after interpreter shutdown')`, which was UNHANDLED and
propagated to the run driver as `status=error_unexpected`. Verification was already complete, so these
calls do not affect any verdict — they are pure stragglers.

## The fix — review `.codex/I-deepfix-001/entailment_shutdown_fix.patch`
In `src/polaris_graph/llm/entailment_judge.py::_post_with_total_deadline`, wrap the `ex.submit(...)` in
`try/except RuntimeError`. On the interpreter-shutdown RuntimeError: tear down the executor
(`ex.shutdown(wait=False)`) and RE-RAISE as `concurrent.futures.TimeoutError`. That maps the race into the
function's EXISTING bounded-retry + fail-closed path — after retry exhaustion the UNCHANGED
`('ENTAILED','judge_error:…')` sentinel fires, which consumers DROP in enforce mode (faithfulness-safe).
No unhandled RuntimeError -> no `error_unexpected`. Plus a unit test that patches the module's
ThreadPoolExecutor to a shutdown-raising stand-in and asserts submit-shutdown maps to TimeoutError (PASSES).

## Confirm (each with a P-level if wrong)
1. Faithfulness-neutral: the mapped TimeoutError rides the SAME fail-closed sentinel path (consumers DROP);
   no verdict is changed, invented, or salvaged. The fail-closed contract is unchanged. Correct?
2. Frozen faithfulness engine: entailment_judge.py is a judge-TRANSPORT wrapper (last touched I-wire-008
   #1322 for transport hardening), NOT the frozen verification LOGIC (strict_verify / nli_verifier /
   four_role / provenance). Is this edit transport-only? Any frozen-logic touch?
3. No new hang / no infinite retry: during shutdown each retry re-hits submit -> RuntimeError -> TimeoutError,
   BOUNDED by the existing retry count, then the sentinel. Converges? Any path that loops forever or
   re-raises RuntimeError past the retry loop?
4. Executor teardown: `ex.shutdown(wait=False)` runs on the shutdown path AND the original `finally` still
   runs on the normal path — no double-shutdown crash, no leaked executor?
5. §-1.3 / LAW VI: no drop/cap/thin, no magic number, byte-identical when the RuntimeError does not occur
   (the normal path is unchanged)?

## Output schema (REQUIRED)
```yaml
verdict: APPROVE | REQUEST_CHANGES
faithfulness_neutral: true|false
frozen_engine_untouched: true|false
transport_only: true|false
no_infinite_retry: true|false
novel_p0: [...]
p1: [...]
```
