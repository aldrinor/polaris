# Codex BRIEF review — I-gen-561 / GH #561: reasoning-trace capture P2 polish

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 0.1 Review stage — PRE-IMPLEMENTATION brief review

This is the **brief** review (the plan). The working tree is intentionally
unmodified at this stage; the separate diff review later verifies the applied
code. Evaluate §2 below as a *plan* — fix approach, scope, test adequacy.

## 1. Issue

GH #561 (I-gen-004-followup) — Codex diff review of #496 (PR #560) returned
APPROVE iter 1 with 5 non-blocking **P2** findings on the I-gen-004
reasoning-trace capture machinery. This issue applies all 5. Branch re-cut to
the canonical id `I-gen-561` (the raw id `I-gen-004-followup` collapses under
the codex-required ISSUE_ID regex onto `I-gen-004`, #496's merged dir — see
#571).

Acceptance: each of the 5 P2s addressed + a test where applicable; no
regression in `tests/polaris_graph/test_reasoning_trace_capture.py` (6 tests)
or the audit-bundle suite; Codex diff APPROVE.

## 2. The 5 fixes (all line numbers verified against HEAD c30a24ce)

### P2-1 — sticky reasoning call-context (`openrouter_client.py`)

Generator call sites set `set_reasoning_call_context(...)` before each LLM
call but never clear it. A later non-generator `OpenRouterClient.generate()`
in the same task/context (e.g. `live_judge.judge_report()` →
`client.generate()`) is then captured under the stale generator context and
mislabeled. Capture is gated only by `current_reasoning_call_context()` in
`_capture_reasoning_trace` (line 158-159).

**Fix:** in `OpenRouterClient.generate()` (def line 1989; body lines
~2010-2254, with `return` at 2039/2254 and `raise` at 2154/2248), wrap the
method body in `try: … finally: set_reasoning_call_context()` (no kwargs →
clears to None per line 135). Each `generate()` invocation's context is then
scoped to exactly that call. The internal COT-2 retry leg (`_call(call_type=
"generate_retry")` at line 2192) stays INSIDE the try, so it still sees the
context and is captured + finalized; the `finally` clears only after the whole
method (incl. retry) completes.

**Scope note:** the issue scopes P2-1 to `generate()` (the named bug is
`judge_report()` → `generate()`). `generate_structured()` / `reason()` also
route through `_call` but are out of the issue's stated scope — noted, not
touched.

### P2-2 — zero-record runs skip `reasoning_trace.jsonl` (`run_honest_sweep_r3.py`)

`run_one_query` (line 1114) constructs `ReasoningTraceCollector(out_dir=
run_dir)` in write-through mode and registers it as the sink (line 1155). In
write-through mode the jsonl is only (re)written on `record()`/`update()`. A
run that aborts before any generator LLM call (scope-rejected /
corpus-inadequate) calls `record()` zero times → `reasoning_trace.jsonl` is
never created, yet `augment_v6_manifest()` references it unconditionally
(`manifest_augment.py:40-41`) → manifest points at a missing file.

**Fix:** at lines 1151-1155, bind the collector to a local, call
`<collector>.flush(run_dir)` once immediately after construction (materializes
the possibly-empty jsonl per `reasoning_trace.flush()` / `_write_locked`,
which writes an empty file for zero records), then `set_reasoning_sink(
<collector>)`.

### P2-3 — abort paths don't clear `set_reasoning_sink(None)` (`run_honest_sweep_r3.py`)

`run_one_query`'s common tail clears both `set_current_run_id(None)` and
`set_reasoning_sink(None)` (lines 2995-2996). But the 5 early-abort
`return summary` sites (~1386/1528/1754/1845/2414) each run only
`set_current_run_id(None)` then `log_f.close()` then `return summary` — they
leave the sink set. Benign (the next run overwrites it) but the lifecycle
does not mirror `set_current_run_id` on abort.

**Fix:** a single `replace_all` Edit inserting `            set_reasoning_sink(None)`
between `set_current_run_id(None)` and `log_f.close()` in the identical
12-space-indented 3-line abort block, so the 5 abort sites mirror the tail
(set_current_run_id(None) → set_reasoning_sink(None) ordering). The block is
unique to the 5 abort sites (the tail is 4-space-indented and already has
`set_reasoning_sink(None)`); the impl will assert exactly 5 occurrences before
replacing. `set_reasoning_sink` is already imported in `run_one_query`.

### P2-4 — `generate_retry` record metadata not finalized (`openrouter_client.py`)

In `generate()`'s COT-2 retry leg, the retry `_call(call_type=
"generate_retry")` (line 2192) captures a NEW reasoning-trace record via
`_capture_reasoning_trace`, which reads the caller's call-context — so the
retry record inherits `attempt_n` / `parent_call_id` from attempt 1. The
retry record should link to the primary and record attempt 2.

**Fix:** immediately after `_retry_trace_id = result.trace_call_id` (line
2200), add `_finalize_reasoning_trace(_retry_trace_id, parent_call_id=
_primary_trace_id, attempt_n=2)`. `_finalize_reasoning_trace` no-ops if
`_retry_trace_id` is None (no sink/context) — safe. The later
`_finalize_reasoning_trace(_retry_trace_id, content_source=...)` calls in the
retry branch are independent `update()` patches and coexist.

### P2-5 — `extra_files` collision check too narrow (`manifest_builder.py`)

`build_manifest_and_files` (line 130) rejects an `extra_files` path only when
`path in files_bytes` (lines 214-217) — the core content files. `files_bytes`
does NOT contain the reserved tar members `manifest.yaml` / `manifest.yaml.asc`
(written by `bundle_builder` ALONGSIDE the packed `files_bytes`). An
`extra_files` entry named `manifest.yaml` would pass the check and then
collide at pack time. The current `reasoning_trace.jsonl` caller is safe; the
generalized interface should reject the reserved names.

**Fix:** add a module constant `_RESERVED_TAR_MEMBERS = frozenset({
"manifest.yaml", "manifest.yaml.asc"})` and change the collision check to
`if path in files_bytes or path in _RESERVED_TAR_MEMBERS:` with a clear
ValueError naming the reserved-member case.

## 3. Tests

Extend `tests/polaris_graph/test_reasoning_trace_capture.py` (or add a focused
file) with targeted cases:
- P2-2: a write-through `ReasoningTraceCollector` flushed once with zero
  records produces an existing, empty `reasoning_trace.jsonl`.
- P2-4: after a `generate()` COT-2 retry, the retry record has
  `parent_call_id == <primary id>` and `attempt_n == 2` (using a fake sink +
  a stubbed `_call` that returns empty-content twice then reasoning).
- P2-5: `build_manifest_and_files(..., extra_files={"manifest.yaml": ...})`
  raises ValueError.
- P2-1: after `generate()` returns, `current_reasoning_call_context()` is None.
Where a full integration harness is impractical (P2-1/P2-4 need a stubbed
client), keep the test at the smallest faithful unit.

## 4. Files I have ALSO checked

- `_capture_reasoning_trace` (line 142) + `_finalize_reasoning_trace`
  (line 186) — the capture/finalize helpers; unchanged, the fixes use them.
- `reasoning_trace.py` `flush()` / `_write_locked` — write an empty file for
  zero records (P2-2 relies on this; correct as-is).
- `manifest_augment.py:40-41` — references `reasoning_trace.jsonl`
  unconditionally (the P2-2 motivation; not changed — P2-2 makes the file
  always exist instead).
- `run_one_query` common tail (2995-2999) — the abort sites are made to
  mirror it; the tail itself is unchanged.

## 5. Test / smoke

`python -m pytest tests/polaris_graph/test_reasoning_trace_capture.py`
+ the audit-bundle test suite + `ast.parse` on the 3 edited `.py` files.
All green, no regression.

## 6. Required output schema (§8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

Loose verdict prose is rejected — emit the schema.
