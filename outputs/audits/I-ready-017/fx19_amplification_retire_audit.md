# FX-19 §-1.1 audit — RETIRE PG_AMPLIFICATION_VARIANTS from the advertised slate (#1127)

**Standard:** §-1.1 over the REAL held drb_72 artifacts + the static code path, line-by-line. The claim
under audit: `PG_AMPLIFICATION_VARIANTS` is a DEAD knob on the benchmark (agentic) path, so advertising
it as a HIGH-impact full-capability lever is dishonest — RETIRE it (Codex plan-gate Q6).

## The bug, on the real artifact (line-by-line)
1. **Held drb_72 run log — ZERO amplification:** `outputs/audits/I-ready-017/query_breadth_generators_findings.md`
   records `PG_AMPLIFICATION_VARIANTS=8 → 0 "Query amplification" log lines → UNWIRED (dead in benchmark
   path)`. The only place that emits the `"[polaris graph] Query amplification: %d -> %d queries"` line is
   the legacy static path (`searcher.py:305-312`). Zero such lines in the real run ⇒ the amplifier (and
   thus the variants knob) was never invoked on the benchmark.
2. **Code path proof (why):** `execute_searches` (`searcher.py:274`) returns
   `execute_agentic_search(state, client)` early at `searcher.py:291-292` whenever
   `PG_AGENTIC_SEARCH_ENABLED and client`. The amplification block (`:296-323`, which reads
   `PG_AMPLIFICATION_VARIANTS` at `:303,311`) sits AFTER that return, so it is unreachable on the agentic
   slate. The benchmark runs agentic ON ⇒ the knob is provably inert there.
3. **Not in the benchmark slate either:** `scripts/dr_benchmark/run_gate_b.py` has zero references to
   `PG_AMPLIFICATION_VARIANTS` (grep `= 0`) — yet `docs/capability_downgrade_audit_2026_06_04.md:34,80`
   advertised `PG_AMPLIFICATION_VARIANTS=8` as a HIGH-impact lever. That is the dishonesty: a dead knob
   sold as a capability.

## The fix (RETIRE — documentation + comments only; no code-logic change)
- `state.py:71-78` — comment marks `PG_AMPLIFICATION_VARIANTS` legacy-static-path-only, inert under
  `PG_AGENTIC_SEARCH_ENABLED=1`; kept (not deleted) because the non-agentic lane still uses it.
- `searcher.py` amplification block — comment marks it the legacy static path, unreachable under the
  agentic early-return.
- `docs/capability_downgrade_audit_2026_06_04.md` — the row + env token annotated **RETIRED**:
  legacy/inert-under-agentic, "do NOT set for the benchmark." Active agentic breadth comes from the
  planner-decomposer + STORM + the agentic reasoning loop.

## Offline smoke (proves the claim + that RETIRE didn't sever the legacy lane)
`pytest tests/polaris_graph/test_fx19_amplification_retired_iready017.py` → 2 passed:
- **amplifier unreachable under agentic slate**: with `PG_AGENTIC_SEARCH_ENABLED=1`, `execute_searches`
  hands off to `execute_agentic_search` and `_import_amplifier` (monkeypatched to raise) is NEVER called
  — the variants knob is provably skipped.
- **legacy lane still consults the knob**: with `PG_AGENTIC_SEARCH_ENABLED=0` and
  `PG_AMPLIFICATION_VARIANTS=2`, the amplifier IS invoked and the 10 amplified queries are trimmed to the
  cap `original_count(1) * 2 = 2` — confirming the doc/comment-only RETIRE left the legacy behavior intact.

## Faithfulness check
Discovery/observability honesty only. No grounding / strict_verify / 4-role change. Zero behavior change
on any execution path (the knob keeps working on the non-agentic lane it was always confined to; the
agentic/benchmark path never used it). This is a no-silent-downgrade-aligned honesty fix: stop
advertising a capability lever that does nothing on the path that ships.
