# Codex DIFF review — I-gen-004 / GH #496: capture + store the V4 Pro reasoning trace separately

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 0. What you are reviewing

A **DIFF review** — verify the implemented code is correct against the
Codex-APPROVE'd brief (`.codex/I-gen-004/brief.md`, brief APPROVE iter 3).

The canonical diff is `.codex/I-gen-004/codex_diff.patch` (14 files,
+827 / -37; the last line is a `# canonical-diff-sha256:` trailer — not
part of the diff). Read it, and read the actual source files on disk
(branch `bot/I-gen-004-reasoning-trace` @ `474f0d6c`) for full context.
Claude's architect review is `outputs/audits/I-gen-004/claude_audit.md`.

## 1. Diff-size exemption (requested)

The diff exceeds the 200-LOC isolated-CODE cap. This is **inherent to the
operator's "whole reasoning log" scope** — #496 spans a new collector
module + the OpenRouterClient capture machinery + 8 generator call sites
+ run orchestration + manifest centralization + the signed-bundle
interface + the reviewer doc + 6 tests. The brief §3 diff-size note
already flagged this and instructed "request the Codex diff-review
exemption rather than narrowing coverage." Please grant the exemption (or
state explicitly why the scope should have been split) — do not REQUEST_
CHANGES solely on LOC count.

## 2. The change (per `claude_audit.md` §2)

- `generator/reasoning_trace.py` (NEW): run-scoped `ReasoningTraceCollector`
  + 15-field `ReasoningTraceRecord`; frozen vocabularies; write-through
  mode (`out_dir` ctor arg → `record()`/`update()` re-flush); `flush()`
  never truncates `reasoning_text`.
- `llm/openrouter_client.py`: `LLMResponse.trace_call_id`;
  `set_reasoning_sink` / `set_reasoning_call_context` ContextVars +
  accessors; `_capture_reasoning_trace` (called in `_call_impl` after the
  raw `LLMResponse`); `_finalize_reasoning_trace` (8 finalize points in
  `generate()` — extraction / promotion / truncation / retry / error).
- Generator call sites threaded with `set_reasoning_call_context`:
  `multi_section_generator` (`_call_outline` main+retry, `_call_section`
  incl. regen, `_call_trial_summary_table`, `_call_m50_per_trial_subsection`,
  `_call_limitations`, `_m63_llm_call`, `_dedup_llm_callable`),
  `sentence_repair.py`, `analyst_synthesis.py`.
- `run_honest_sweep_r3.py`: per-run collector + `set_reasoning_sink`
  lifecycle in `run_one_query`.
- `audit_ir/manifest_augment.py`: `reasoning_trace` reference on every
  manifest.
- Signed bundle: `bundle_schema.py` ContentType; `manifest_builder.py`
  `extra_files` param; `bundle_builder.py` passthrough;
  `audit_bundle_route.py` extracted `build_audit_bundle_response()`;
  `bundle.py` bridge reads `artifact_dir/reasoning_trace.jsonl`.
- `REVIEWER_README.md` doc; 6 tests.

## 3. Acceptance criteria (verify each against the code)

1. A run-scoped collector captures `reasoning` + `reasoning_tokens` from
   every raw completed provider response for generator-side LLM calls,
   via the `OpenRouterClient` sink — including internal `generate_retry`
   attempts and the `ReasoningFirstTruncationError` path.
2. Per-run `reasoning_trace.jsonl`, one record per response, 15-field
   schema; `reasoning_text` lives in the jsonl only — never merged into
   `report.md` / `verified_text` / the verified-sentence stream.
3. `manifest.json` references the trace; the signed `bundle.tar.gz`
   includes + hashes it under `content_type=reasoning_trace`.
4. `REVIEWER_README.md` documents the trace as process evidence, not claims.
5. Separation invariant + tests (the 6 in `test_reasoning_trace_capture.py`).
6. Non-reasoning models (`reasoning` empty/None) → record still written,
   empty `reasoning_text`, uniform schema, no crash.

## 4. Specific things to scrutinize

- Capture point: is `_capture_reasoning_trace` truly BELOW all promotion
  / `</think>` extraction / retry / raise — so the recorded
  `reasoning_text` is the raw provider response?
- Finalization: do the 8 `_finalize_reasoning_trace` calls cover every
  path `generate()` can take? Any path where a record is captured but
  never finalized to its true `status`/`content_source`?
- ContextVar lifecycle: `set_reasoning_sink` is set in `run_one_query`
  and cleared in the tail; `set_reasoning_call_context` is set per call
  site. Any leak across runs / across async tasks? (The sink + run_id
  use the same ContextVar lifecycle — is that sound?)
- Write-through: does `record()`/`update()` re-flushing cover EVERY
  abort/error early-return in `run_honest_sweep_r3.py` without an explicit
  flush call? (Codex iter-3 P2 #3 — this was the chosen alternative.)
- `extra_files` collision handling in `build_manifest_and_files()`.
- The `build_audit_bundle_response()` extraction — does the POST
  `/audit-bundle` route still behave identically?

## 5. Files I have ALSO checked and they're clean

- `cross_trial_synthesis.py`, `cross_jurisdiction_synthesizer.py`,
  `regulatory_synthesizer.py` — grep confirms ZERO `.generate(` /
  `.reason(` / `OpenRouterClient` calls; they are deterministic
  synthesizers, nothing to thread.
- `live_deepseek_generator.generate_live_draft()` — called ONLY by the
  legacy scripts `run_honest_on_prerebuild_corpus.py` +
  `run_live_honest_cycle.py`, NOT by `run_honest_sweep_r3.py`; brief §2.2
  scopes standalone-legacy invocations out — left unthreaded.
- `post_audit_bundle_preview` — calls `build_manifest_and_files` with no
  `extra_files`; the param defaults to `None`, behavior byte-identical.
- 106 blast-radius tests pass (reasoning-first + all `audit_bundle` + the
  6 new); all 7 modified modules import clean.

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
