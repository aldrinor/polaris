# Codex DIFF review — I-gen-561 / GH #561: reasoning-trace capture 5 P2 polish

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 1. What you are reviewing

The commit-1 diff for #561 — `git diff origin/polaris...HEAD` excluding
`.codex/I-gen-561/` and `outputs/audits/I-gen-561/` (the canonical diff in
`.codex/I-gen-561/codex_diff.patch`, sha256 trailer). It implements the
Codex-APPROVE'd brief `.codex/I-gen-561/brief.md` (brief review APPROVE iter 1).
5 files, +152/-1.

## 2. The diff — 5 P2 fixes

- **P2-1** `openrouter_client.py`: `generate()` → thin wrapper delegating to a
  renamed `_generate_impl`; the wrapper's `finally` calls
  `set_reasoning_call_context()` (no kwargs → None) so the per-call generator
  context is cleared on every exit. Body renamed, NOT re-indented. The COT-2
  retry runs inside `_generate_impl` (inside the wrapper's `try`) so it still
  sees the context.
- **P2-4** `openrouter_client.py`: in `_generate_impl`'s retry leg, right after
  `_retry_trace_id = result.trace_call_id`,
  `_finalize_reasoning_trace(_retry_trace_id, parent_call_id=_primary_trace_id,
  attempt_n=2)`.
- **P2-2** `run_honest_sweep_r3.py` `run_one_query`: collector bound to a
  local, `flush(run_dir)` once, then `set_reasoning_sink(...)`.
- **P2-3** `run_honest_sweep_r3.py`: the 5 early-abort `return summary` blocks
  now clear `set_reasoning_sink(None)` after `set_current_run_id(None)`.
- **P2-5** `manifest_builder.py`: `_RESERVED_TAR_MEMBERS` constant +
  `build_manifest_and_files` rejects an `extra_files` path equal to a reserved
  tar member.
- **Tests**: +3 `test_reasoning_trace_capture.py`, +1 `test_manifest_builder.py`.

## 3. Verify against the brief

1. P2-1: the wrapper signature matches the original `generate()`; `_generate_impl`
   keeps the full body unchanged; `finally` clears context on return AND on
   exception; the retry inside `_generate_impl` is not prematurely cleared.
2. P2-4: the finalize is before the retry-extraction branch; coexists with the
   later `content_source`/`status` finalizes; no-ops when `_retry_trace_id` is None.
3. P2-2: `flush()` is called once post-construction; the run still registers
   the same collector as the sink.
4. P2-3: exactly the 5 abort sites changed (grep `set_reasoning_sink(None)` → 6
   incl. the tail); the tail unchanged.
5. P2-5: the reserved-member reject is additive — no valid `extra_files` caller
   regresses; the current `reasoning_trace.jsonl` caller is unaffected.
6. Diff is +152/-1 (under 200-LOC cap); no body re-indent.

## 4. Files I have ALSO checked and they're clean

- `reasoning_trace.py` `flush()`/`_write_locked` — write an empty file for 0
  records (P2-2 relies on this); unchanged.
- `_capture_reasoning_trace` / `_finalize_reasoning_trace` — unchanged; the
  fixes call them.
- `run_one_query` common tail (clears both `set_current_run_id` +
  `set_reasoning_sink`) — unchanged; the abort sites now mirror it.
- `manifest_augment.py` references `reasoning_trace.jsonl` unconditionally —
  unchanged; P2-2 makes the file always exist.
- `generate_structured()` / `reason()` — out of the issue's stated P2-1 scope;
  not touched.

## 5. Test state

`PYTHONPATH='src;.' pytest`: `test_reasoning_trace_capture.py` 9/9,
`test_manifest_builder.py` 17/17, full `tests/polaris_graph/audit_bundle/`
88 passed / 4 skipped (pre-existing gpg-env skips). `ast.parse` clean.

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
