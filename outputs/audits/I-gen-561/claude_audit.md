# Claude architect audit — I-gen-561 (#561)

**Issue:** GH #561 (I-gen-004-followup) — reasoning-trace capture, 5 P2 polish
fixes from #496's Codex diff review.
**Branch:** `bot/I-gen-561` (re-cut canonical id — the raw `-followup` id
collapses onto #496's `.codex/I-gen-004/` under the codex-required ISSUE_ID
regex; see #571).
**Commit 1 (code+tests):** `fd215d76` — 5 files, +152/-1.
**Brief:** `.codex/I-gen-561/brief.md` — Codex APPROVE iter 1 (0 P0/P1/P2).

## 1. What shipped

| P2 | File | Change |
|---|---|---|
| P2-1 | `src/polaris_graph/llm/openrouter_client.py` | `generate()` is now a thin wrapper that delegates to a renamed `_generate_impl` and clears the per-call reasoning call-context in a `finally` (`set_reasoning_call_context()`). Minimal-diff: the body is renamed, not re-indented; the internal COT-2 retry runs inside `_generate_impl`, so it still sees the context. |
| P2-4 | `src/polaris_graph/llm/openrouter_client.py` | In `_generate_impl`'s COT-2 retry leg, right after `_retry_trace_id = result.trace_call_id`, `_finalize_reasoning_trace(_retry_trace_id, parent_call_id=_primary_trace_id, attempt_n=2)` links the retry record to the primary + marks attempt 2. |
| P2-2 | `scripts/run_honest_sweep_r3.py` | `run_one_query` binds the `ReasoningTraceCollector` to a local, `flush(run_dir)` once immediately (materializes the possibly-empty `reasoning_trace.jsonl`), then `set_reasoning_sink(...)`. |
| P2-3 | `scripts/run_honest_sweep_r3.py` | The 5 early-abort `return summary` sites now clear `set_reasoning_sink(None)` after `set_current_run_id(None)`, mirroring the common tail. |
| P2-5 | `src/polaris_graph/audit_bundle/manifest_builder.py` | New `_RESERVED_TAR_MEMBERS = frozenset({"manifest.yaml", "manifest.yaml.asc"})`; `build_manifest_and_files` rejects an `extra_files` path equal to a reserved tar member. |

## 2. Per-finding verification

- **VERIFIED — P2-1:** `generate()` body wrapped via wrapper-delegate, not a
  245-line re-indent — diff stays small. `set_reasoning_call_context()` (no
  kwargs → `None` per the function's own contract) runs in the `finally` on
  every exit (return/raise/exception from `_generate_impl`). The COT-2 retry
  is inside `_generate_impl` → still captured + P2-4-finalized before the
  wrapper clears. Test `test_p2_1_generate_clears_call_context_on_exit`
  asserts context is `None` after `generate()` and still live during the body.
- **VERIFIED — P2-4:** the finalize call is placed immediately after
  `_retry_trace_id` is bound and before the retry-extraction branch; the later
  `content_source`/`status` finalizes are independent `update()` patches.
  `_finalize_reasoning_trace` no-ops when `_retry_trace_id` is None (no
  sink/context). Test `test_p2_4_retry_record_finalized_with_parent_and_attempt`
  asserts `parent_call_id`/`attempt_n` on the retry record.
- **VERIFIED — P2-2:** `ReasoningTraceCollector.flush()` / `_write_locked`
  write an empty file for zero records (existing behaviour); calling it once
  post-construction materializes the artifact before any `record()`. Test
  `test_p2_2_zero_record_run_flushes_empty_jsonl`.
- **VERIFIED — P2-3:** `grep -c "set_reasoning_sink(None)"` → 6 (5 abort + 1
  tail). The `replace_all` matched exactly the 5 identical 12-space-indented
  abort blocks; the 4-space tail (already with `set_reasoning_sink(None)`) was
  untouched.
- **VERIFIED — P2-5:** `_RESERVED_TAR_MEMBERS` rejection added AFTER the
  existing core-file collision check; `files_bytes` never holds those names so
  the prior check could not catch them. Test
  `test_build_manifest_rejects_reserved_tar_member_extra_file`.

## 3. Test / smoke

`PYTHONPATH='src;.' pytest`: `test_reasoning_trace_capture.py` 9/9 (6 original
+ 3 new), `test_manifest_builder.py` 17/17 (16 + 1 new), full
`tests/polaris_graph/audit_bundle/` 88 passed / 4 skipped (pre-existing
gpg-env skips). `ast.parse` clean on all 3 source + 2 test files. No
regression.

## 4. Scope + residuals

- P2-1 is scoped to `generate()` per the issue (the named bug is
  `judge_report()` → `generate()`). `generate_structured()` / `reason()` also
  route through `_call` but are out of the issue's stated scope — not touched.
- Commit-1 diff is +152/-1 — well under the 200-LOC cap; the wrapper-delegate
  avoided a ~490-LOC re-indent.

## 5. Risk assessment

`openrouter_client.py` is a core file, but the changes are surgical: a
wrapper-delegate (no body logic change) + one finalize call in the existing
retry leg. `run_one_query` changes are lifecycle-only (flush + sink-clear,
mirroring existing patterns). `manifest_builder` adds a stricter reject — no
behaviour change for any valid `extra_files` caller. Two-family / budget
invariants untouched.

## 6. Verdict

Implementation complete, faithful to the iter-1 APPROVE'd brief; all 5 P2s
applied with tests; offline suites green. Ready for Codex diff review.
