# Claude architect review — I-gen-004 (#496): V4 Pro reasoning-trace capture

Reviewer: Claude (architect pass, pre-Codex-diff-review)
Branch: `bot/I-gen-004-reasoning-trace` @ `474f0d6c`
Canonical diff: `.codex/I-gen-004/codex_diff.patch` — 14 files, +827 / -37.

## 1. What this delivers

Operator transparency directive (2026-05-14): keep the **whole** reasoning
log and the output content separated and properly stored, transparently.
DeepSeek V4 Pro is reasoning-first — every generator LLM call emits a large
reasoning channel alongside the final answer; POLARIS discarded
`response.reasoning`. This captures it to a per-run `reasoning_trace.jsonl`,
stored + GPG-signed **separately** from `report.md` / verified prose, and
**never** `strict_verify`'d (it is model-process evidence, not a claim).

## 2. Per-file walkthrough

- **`generator/reasoning_trace.py` (NEW, +224).** Run-scoped
  `ReasoningTraceCollector` + 15-field `ReasoningTraceRecord` dataclass.
  Frozen `CALL_TYPES` / `STATUSES` / `CONTENT_SOURCES`; `record()` fails
  loud on an unknown value. `update()` patches a record in place (the
  finalization semantics). Write-through mode (`out_dir` ctor arg):
  `record()`/`update()` re-flush the full jsonl so the artifact is current
  on disk regardless of which abort/error path the run exits through
  (Codex iter-3 P2 #3 — no run-orchestrator flush call needed). `flush()`
  performs **no** truncation of `reasoning_text`. Imports no LLM client
  (layering-safe).
- **`llm/openrouter_client.py` (+148).** `LLMResponse.trace_call_id`
  field. `set_reasoning_sink` / `current_reasoning_sink` /
  `set_reasoning_call_context` / `current_reasoning_call_context`
  ContextVars + accessors. `_capture_reasoning_trace` records each raw
  completed provider response (called once inside `_call_impl` after the
  raw `LLMResponse` is built — below all promotion / extraction / retry /
  raise). `_finalize_reasoning_trace` patches the record once `generate()`
  resolves the outcome — 8 finalize points: `</think>` extraction →
  `extracted_from_reasoning`; GLM-5 + I-bug-088 promotion →
  `promoted_from_reasoning`; truncation → `status=truncated` **before**
  the `ReasoningFirstTruncationError` raise; retry → `status=retry` on the
  superseded attempt; retry-leg extraction/promotion; SF-15 → `status=error`.
- **Generator call sites threaded** (`set_reasoning_call_context` before
  each `generate()`): `multi_section_generator` — `_call_outline`
  (main + validation retry), `_call_section` (incl. `regen`/`regen_reason`
  for tighter-retry), `_call_trial_summary_table`,
  `_call_m50_per_trial_subsection`, `_call_limitations`, `_m63_llm_call`
  (`contract_slot`), `_dedup_llm_callable` (`fact_dedup`);
  `sentence_repair.py` (`repair`); `analyst_synthesis.py`
  (`analyst_synthesis`).
- **`run_honest_sweep_r3.py` (+12).** `run_one_query` creates a
  `ReasoningTraceCollector(out_dir=run_dir)` and `set_reasoning_sink(...)`
  right after `set_current_run_id(run_id)`; `set_reasoning_sink(None)` in
  the run tail — lifecycle mirrors `set_current_run_id` exactly.
- **`audit_ir/manifest_augment.py` (+28).** `augment_v6_manifest()` adds a
  `reasoning_trace` reference on **every** manifest (success/abort/error,
  v6 or legacy) so an operator can always locate the file.
- **Signed bundle** — `bundle_schema.py` `ContentType += "reasoning_trace"`;
  `manifest_builder.py` `build_manifest_and_files()` gains an `extra_files`
  param (`{path: (bytes, content_type)}`, collision-checked);
  `bundle_builder.py` `build_audit_bundle()` threads it; `audit_bundle_route.py`
  extracts `build_audit_bundle_response()` (shared by the POST route + the
  bridge); `bundle.py` `/runs/{run_id}/bundle.tar.gz` reads
  `artifact_dir/reasoning_trace.jsonl` → `extra_files`. The trace is
  included **and SHA256-hashed** in the GPG-signed manifest.
- **`REVIEWER_README.md` (+15).** Documents the trace as model-process
  evidence, NOT verified claims.
- **`tests/polaris_graph/test_reasoning_trace_capture.py` (NEW, +238).**
  6 tests (see §4).

## 3. Invariants held

- **Separation.** `reasoning_text` lives only in `reasoning_trace.jsonl`.
  The collector's sole writer is `flush()` / `_write_locked`, which writes
  exactly one file. No code path connects the collector to
  `strict_verify` / `provenance_generator` / the `report.md` writer.
- **Capture gating.** `_capture_reasoning_trace` no-ops unless BOTH a sink
  AND a call-context are set — evaluator (`reason()`) / retrieval LLM
  calls set no context, so capture is scoped to generator calls.
- **Best-effort observability.** A sink failure is logged loud, never
  raised — the reasoning trace can never break a generation.
- **Truncation preserved.** The `ReasoningFirstTruncationError` path
  records `status=truncated` BEFORE the raise — the reasoning survives
  even though the call "fails".
- **Signed-bundle integrity.** The trace is hashed into the GPG-signed
  manifest under `content_type=reasoning_trace`.

## 4. Test coverage

6 tests in `test_reasoning_trace_capture.py`, all pass offline:
separation invariant, V4-Pro `content=''`+reasoning promotion,
`generate_retry` per-attempt recording, `ReasoningFirstTruncationError`
→ `status=truncated`, non-reasoning-model uniform schema + capture
gating, long-`reasoning_text` (200k) no-truncation. Blast-radius smoke:
106 tests pass (reasoning-first + all `audit_bundle` + the 6 new),
0 regressions; all 7 modified-module imports clean.

## 5. Residual risks (honest)

- **New call sites added later.** If a future generator call site is added
  without `set_reasoning_call_context`, capture no-ops for it (no record).
  Not a correctness bug — it is a coverage gap, surfaced as a follow-up
  concern, not a blocker.
- **`reason()` not finalized.** Evaluator `reason()` calls set no
  call-context → capture no-ops; intentional — #496 scope is
  generator-side LLM calls.
- **>200-LOC diff.** Inherent to the operator's "whole reasoning log"
  scope (collector + client + 8 call sites + run-orch + manifest +
  signed-bundle + doc + 6 tests). Codex 200-LOC exemption requested.

Verdict: ready for Codex diff review.
