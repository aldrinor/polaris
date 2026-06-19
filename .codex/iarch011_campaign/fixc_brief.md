HARD ITERATION CAP: 3 per document. This is iter 1 of 3.
- Front-load ALL real findings. No drip-feeding. Same quality bar regardless of iteration.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks; classify the rest P3/P2/cosmetic.
- If iter 3 returns REQUEST_CHANGES, Claude force-APPROVEs on remaining non-P0/P1 findings.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

FRONTIER-TECH MANDATE: judge against 2025-2026 frontier practice; no grandfathering. The faithfulness engine
(strict_verify / NLI entailment / span-grounding) is NEVER relaxed — flag any change that would.

# Codex diff review — I-arch-011 FIX-C (PG_PARALLEL_VERIFY) — the run-#6 enrichment-verify "freeze"

Review the patch FILE (static only, do NOT run pytest):

    .codex/iarch011_campaign/fixc_diff.patch   (1 file: scripts/dr_benchmark/run_gate_b.py; workdir C:/POLARIS read-only)

## THE DIAGNOSIS (verify the reasoning, then the one-line diff)
Run #6 (the 794->9 collapse fix) PROVED breadth restoration — 737 sources into the baskets, faithful — then
appeared to HANG ~13 min at the FINAL verify of the 737-source breadth-ENRICHMENT section and never rendered.
The runbook called it a per-call entailment DEADLOCK. **That was WRONG.** Evidence, all banked:
 1. `scripts/iarch011_entailment_deadline_repro.py` (real `_EntailmentJudge` vs a local trickle/wedge server):
    `_post_with_total_deadline` raised TimeoutError at EXACTLY the deadline (5.0s); `judge()` bounded at 2x then
    emitted the fail-closed sentinel; a 2nd call bounded — NO deadlock. `concurrent.futures.Future.result(timeout)`
    is a condition-variable timed wait, transport-agnostic — a worker stuck in `ssl.read` cannot change when it wakes.
 2. ROOT CAUSE: `provenance_generator._parallel_verify_workers()` (the I-arch-006 fix#19 BOUNDED-PARALLEL findings
    verify) reads `PG_PARALLEL_VERIFY`, default 1 = SERIAL — and the run_gate_b slate NEVER set it. So the
    737-source section verified its ~1839 sentence-units SERIALLY.
 3. The breadth is REAL + FAITHFUL: on the banked drb_78 corpus + REAL glm-5.1 free-route judge
    (`scripts/iarch011_binding_and_judge_probe.py`), real-judge KEEP-RATE = **39/40 = 97% ENTAILED**, latency
    median 5.7s/p90 14s/max 36s -> **serial ~173min (the "hang") vs 16-way ~11min**. The full behavioral gate
    (`scripts/iarch011_parallel_verify_gate.py`, real judge + PG_PARALLEL_VERIFY=16) confirms it completes in
    17.4 min and keeps 1746 cited / 657 distinct sources on the REAL enforce path.

## THE DIFF
`scripts/dr_benchmark/run_gate_b.py` `_FULL_CAPABILITY_BENCHMARK_SLATE`: add `"PG_PARALLEL_VERIFY": "16"`
(next to the B19 distill block). That engages the existing fix#19 bounded ThreadPoolExecutor verify (cap 16,
matches PG_CREDIBILITY_PASS_MAX_INFLIGHT). Nothing else changes.

## YOUR JOB
A. 3-PRONG: does FIX-C (1) relax any binding gate? (2) grandfather? (3) add a cap/floor/throttle/hard-filter
   or wrong-merge? It is a CONCURRENCY knob only — confirm it adds none.
B. Confirm faithfulness-NEUTRALITY of the existing parallel path it turns on (read provenance_generator.py
   ~2759-2804): it captures the parent contextvars context (so per-run judge telemetry / role / provider-pin
   propagate), `map` PRESERVES input order (so kept/dropped is index-aligned + byte-identical to the serial
   loop — concurrency changes timing not verdicts), and a worker exception PROPAGATES fail-loud. Confirm there
   is no shared-state race that could change a verdict.
C. Hang-safety: note that the per-call total-deadline in entailment_judge (`_post_with_total_deadline`,
   PG_ENTAILMENT_TOTAL_S=45) is what bounds each worker — `list(pool.map())` + `shutdown(wait=True)` would
   otherwise block on a never-returning future. Confirm the deadline is present + load-bearing (it is the real
   hang-safety; parallelism alone is not). Any P0/P1 if a worker could still wedge unbounded?

## OUTPUT SCHEMA (return EXACTLY this; last `verdict:` line is parsed)
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
