HARD ITERATION CAP: 5 per document. This is iter 2 of 5 (FOCUSED RE-VERIFY).

## CHANGE SINCE ITER 1 (your P1 fixed — re-verify FIRST)
Your iter-1 P1 was correct and is FIXED in `scripts/dr_benchmark/super_heavy_preflight.py` (`_default_credibility_judge_probe`):
- The transient classifier now keys on EXCEPTION TYPE/NAME, not only `str(exc)`:
  `_transient = isinstance(exc, TimeoutError) or "timeout" in type(exc).__name__.lower() or <the prior message substrings>`.
- This catches the cert-run #2 failure class — `concurrent.futures.TimeoutError` with an EMPTY message (in Python 3.11+, which the VM runs, `concurrent.futures.TimeoutError` IS builtin `TimeoutError`) — so the probe now does its bounded backoff/retry across all attempts instead of false-aborting after the first.
- PROVEN on the VM (offline, caller monkeypatched to raise `concurrent.futures.TimeoutError("")`): the probe makes 3 attempts (= PG_PREFLIGHT_JUDGE_PROBE_RETRIES) then raises GateError, AND PG_ROLE_ALLOW_FALLBACKS is restored (popped). Pre-fix it made 1 attempt.

Re-verify the classifier change is correct and complete, and that nothing else in the reviewed region regressed.

## (Original iter-1 brief context follows.)
HARD ITERATION CAP (orig): 5 per document.
- Front-load ALL real findings. Reserve P0/P1 for real execution risks; classify minor issues P2/P3.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on remaining-non-P0/P1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

REVIEW MODE: STATIC ONLY. Read the diff `.codex/I-deepfix-001/cred_probe_fix.patch` and the changed region in `scripts/dr_benchmark/super_heavy_preflight.py` (`_default_credibility_judge_probe`). No pytest/pipeline. Emit the schema at the end.

# I-deepfix-001 (#1344) — credibility-judge PREFLIGHT PROBE fix (cert-run #2 crash, pre-spend)

## Problem (empirical, live VM)
Cert run #2 crashed pre-spend ($0) at the credibility-judge probe:
`GateError: credibility judge slug 'z-ai/glm-5.2' is NOT alive in its production call shape (TimeoutError: ) after 6 attempt(s)`.
Diagnosed on the VM: glm-5.2 is a REASONING model with `reasoning:{effort:high}` forced on; the old probe forced `max_tokens=1`, which STARVES it (reasoning tokens consume the cap) → empty content on a fast provider, or a stalled POST that trips the wall-deadline on a LOADED provider → hard-abort of a $40 run. The run-time fault was a TRANSIENT pinned-provider saturation the probe could not escape (starving shape + single-provider pin + — iter-1 P1 — a message-only transient classifier that missed the empty-message TimeoutError).

## The fix (1 file, `_default_credibility_judge_probe` only)
- max_tokens 1 → non-starving (env PG_PREFLIGHT_CREDIBILITY_PROBE_MAX_TOKENS, default 2048) so high-effort reasoning completes and emits a token (usage-billed; fraction of a cent).
- REQUIRE non-empty content for "alive" (old code ignored the return → empty = false-alive).
- FREE-ROUTE the probe (PG_ROLE_ALLOW_FALLBACKS=1 around the call, restored in `finally`) so a transiently-saturated PINNED provider cannot hard-abort an ADVISORY judge's run before spend (production degrades a dead credibility route to neutral-weight; it NEVER drops a sentence). Hard-abort still fires on a non-transient / dead-across-providers route.
- iter-2: transient classifier keys on exception TYPE/NAME too (the P1 fix above).

## Evidence (already run)
- py_compile clean.
- VM real `_default_credibility_judge_probe()` (slate envs PG_SWEEP_CREDIBILITY_REDESIGN/JUDGE_PROVIDER_ROTATE/RETRIES/total_s) → returns `z-ai/glm-5.2` in 4.55s.
- VM raw caller: max_tokens=1 → empty; 2048 → "OK" (free-route AND friendli pin).
- VM offline P1 proof: empty-message concurrent.futures.TimeoutError → 3 attempts then GateError; env restored.
- File LF in HEAD; edit keeps LF.

## VERIFY HARDEST (adversarial)
1. The iter-1 P1 is fully resolved: an empty-message `concurrent.futures.TimeoutError` is now classified transient and retried across the bound; a non-transient error (404/auth) still breaks immediately and hard-aborts.
2. Faithfulness UNTOUCHED — liveness probe only; the credibility judge is advisory (degrades, never drops). No faithfulness gate relaxed.
3. PG_ROLE_ALLOW_FALLBACKS set→restored in `finally` (incl. the unset→pop case); no env leak into later calls. Preflight is sequential.
4. No false "alive": empty body retries then aborts as degraded; never returns the slug.
5. Control flow: the `continue` on transient exception, the empty-body backoff branch, and the post-loop `_last_exc` vs `_saw_empty` abort-message selection are correct; no path silently passes a dead route; loop is bounded.
6. §-1.3/§9.1.8: removes a starvation (no cap/floor/thinner added); reads real model behavior, doesn't guess.

## Output schema (REQUIRED, last lines)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
