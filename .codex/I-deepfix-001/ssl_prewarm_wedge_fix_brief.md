HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd on remaining non-P0/P1 findings.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## WHAT THIS FIX IS
A paid deep-research run (`run_gate_b.py`) intermittently WEDGED (hard hang) at the start of the
generation-stage credibility pass. Verified-idle signature EVERY time: main thread
`futex_wait_queue_me`, ~4 worker threads all sleeping, 0% GPU, 0 disk I/O (read_bytes flat), 0 network.
Flaky and worse on the faster machine: box1 (A100, faster CPU) wedged 2/2, box2 (3090Ti) 1/2.

ROOT CAUSE (traced from code by the Fable-5 reviewer, symptom-matched):
An IN-PROCESS lock/import deadlock in the shared TLS context. The credibility pass fans out up to
16 judge threads (`multi_section_generator.py` credibility_pass_concurrency + `credibility_skill.py`
ThreadPoolExecutor). Each judge builds its httpx client via `get_shared_ssl_context()`
(`src/utils/shared_ssl_context.py`). That function lazily builds ONE `ssl.SSLContext` under
`_SHARED_SSL_LOCK`, and the build (`_build_default_verify_context`) did `import certifi` WHILE HOLDING
THE LOCK. When >1 thread hits `get_shared_ssl_context()` for the FIRST time concurrently, the
lock-held `import` deadlocks against CPython's import machinery. Symptoms fit exactly: futex_wait on
the lock, sleeping workers, no GPU/torch (no model loaded on this path), read_bytes 0 (certifi PEM
served from page cache), 0 net (wedged before the first POST), flakier on faster CPUs (tighter
thread-timing race).

NOT the earlier CUDA/vLLM theory: on a RESUME run the selection-stage embedder is never called
(evidence loaded from snapshot), so no torch/CUDA init happens — refuted by "0 GPU, 4 threads, no
torch". Killing the mineru vLLM did NOT stop the wedge (box1 wedged again with no vLLM), confirming
in-process, not a GPU-driver race.

## THE FIX (2 files, faithfulness-neutral, mutes nothing)
1. `src/utils/shared_ssl_context.py`: hoist `import certifi` from inside `_build_default_verify_context`
   (ran UNDER `_SHARED_SSL_LOCK`) to MODULE TOP-LEVEL. The lock body no longer imports anything.
   certifi is a pure data package — import time/order does not change the CA bundle or any TLS verdict.
2. `scripts/dr_benchmark/run_gate_b.py`:
   a. In `main()`, right after `enable_faulthandler()`, PRE-WARM the singleton single-threaded:
      `get_shared_ssl_context()`. After this the singleton is non-None, so every one of the 16
      concurrent judge workers takes the lock-free fast-path (the `if _SHARED_SSL_CONTEXT is None:`
      guard is false) — no lock acquire, no import, race structurally impossible. Wrapped in
      try/except that LOGS loud (not silent) and never blocks the run.
   b. In `enable_faulthandler()`, register SIGUSR1 -> faulthandler dump-all-threads (POSIX-only,
      hasattr-guarded) so a future wedge can be captured via `kill -USR1 <pid>` without killing the
      process (diagnostic only).

## FAITHFULNESS / NEUTRALITY (verify this HARD)
- The shared `ssl.SSLContext` is byte-identical (same `create_default_context` precedence:
  SSL_CERT_FILE -> SSL_CERT_DIR -> certifi.where(); CERT_REQUIRED + check_hostname=True unchanged).
  TLS verification stays ENABLED. No `verify=False` anywhere.
- The pre-warm only builds the SAME singleton earlier and single-threaded; every credibility/
  entailment verdict is identical; the 16-way concurrency is preserved (workers just skip the
  one-time build).
- ZERO change to strict_verify / NLI entailment / 4-role D8 / span-grounding / credibility scoring.
- No function is muted/degraded (this is NOT the earlier lexical-fallback idea, which was rejected).

## TEST (offline, passed)
- Both files `py_compile` OK.
- Concurrency test: pre-warm builds 1 ctx (`verify_mode==CERT_REQUIRED`, `check_hostname is True`);
  then 16 concurrent threads call `get_shared_ssl_context()` and ALL return the SAME object via the
  fast-path in 3.6ms with NO hang; certifi confirmed hoisted out of the locked build fn.

## ASK
Review the diff (below). Verify: (1) the pre-warm + import-hoist actually removes the concurrent
lazy-build deadlock; (2) faithfulness-neutral / no verdict change / no muted function; (3) the
try/except is loud not silent; (4) SIGUSR1 registration is safe + POSIX-guarded (no Windows break);
(5) any real execution risk (pre-warm failure mode, import-order side effects, double-checked-locking
correctness of the fast-path). Output schema:
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## THE DIFF
