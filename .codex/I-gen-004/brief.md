# Codex BRIEF review — I-gen-004 / GH #496: capture + store the V4 Pro reasoning trace separately

HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 0. What you are reviewing

A **BRIEF review** (iter 3) — verify the acceptance criteria + approach are
correct and complete BEFORE the diff is written.

## 0.1 Iter-1 + iter-2 findings — addressed

- **P1-001** (reasoning→content promotion) → `content_source` field + §2.3.
- **P1-002** (scope = all generator LLM calls) → §2.2.
- **P1-003** (signed bundle path) → §2.5.
- **P1-004** (capture point too high — misses internal `generate_retry`
  and the `ReasoningFirstTruncationError` raise path) → **§2.6: capture is
  moved to the `OpenRouterClient` level, before any retry / promotion /
  extraction / raise.**
- **P2-001** (Pipeline-A manifest write sites) → §2.5: trace injection
  centralized in `augment_v6_manifest()`.
- **P2-002** (`live_deepseek_generator.generate_live_draft()`) → §2.2 scope
  note.
- **P2-003** (bundle sidecar-data interface) → §2.5 spells out the
  `build_manifest_and_files()` interface change.

## 1. The issue (GH #496 / I-gen-004)

Operator directive 2026-05-14: "keep the **whole** reasoning log and output
content separated and properly stored, transparently." DeepSeek V4 Pro is
reasoning-first (one outline call: `content=1791 B` + `reasoning=17521 B`).
POLARIS currently discards `response.reasoning`. Dependency I-gen-003 (#495)
is complete.

## 2. Proposed approach

### 2.1 Run-scoped reasoning-trace collector

A run-scoped collector created at run start. It accumulates one record per
raw completed provider response and flushes `reasoning_trace.jsonl` at run
end.

### 2.2 Capture scope — every generator-side LLM call

`_call_section` (+ regen), `_call_outline` (+ retry), sentence-repair
(I-bug-108), `_call_limitations`, `_call_trial_summary_table` (+ fallback),
`_call_m50_per_trial_subsection`, analyst synthesis, fact-dedup rewrite,
cross-trial / cross-jurisdiction / regulatory synthesizers, and the V30
contract-slot / regulatory `_m63_llm_call` path. `live_deepseek_generator.
generate_live_draft()` is covered **when invoked inside a run that carries
a collector**; its standalone-legacy-script invocation (no run context) is
explicitly out of scope (a record cannot be routed without a run).

### 2.3 The reasoning→content promotion (P1-001)

`openrouter_client.py` promotes reasoning→content for reasoning-first models
when `content` is empty (I-bug-088 recovery). The trace record carries
`content_source ∈ {direct, promoted_from_reasoning}`; `reasoning_text`
always records the raw model reasoning channel; `content_text` records what
was used as section content. When `promoted_from_reasoning`, the two
legitimately overlap — the trace discloses it.

### 2.4 Record schema (one JSON object per raw completed provider response)

`{call_id, parent_call_id, section, call_type, regen_reason, attempt_n,
model, status, reasoning_text, content_text, content_source, input_tokens,
output_tokens, reasoning_tokens, timestamp}`

- `call_type ∈ {outline, section, repair, regen, limitations, trial_table,
  m50_subsection, analyst_synthesis, fact_dedup, contract_slot, regulatory}`.
- `status ∈ {ok, retry, truncated, error}` — distinguishes a clean
  response from an internal-retry attempt, a `ReasoningFirstTruncationError`
  capture, and a hard error.
- `regen_reason` disambiguates `regen` (strict-verify retry / M44 / M47);
  `parent_call_id` links a regen/repair/retry to its parent.

### 2.5 Capture point — at the `OpenRouterClient` level (P1-004)

The capture must sit **below** the generator call sites, because
`OpenRouterClient.generate()` internally retries (`generate_retry`),
promotes reasoning→content, extracts `</think>`, and **raises
`ReasoningFirstTruncationError`** — the last of which is exactly the
reasoning-first case #496 exists to preserve, and a generator-call-site
wrapper would never see it.

- The `OpenRouterClient` gains an optional run-scoped `reasoning_sink`
  (a collector handle / callback, default `None` = no-op — keeps the
  client usable outside the generator).
- At the point in `_call` / `generate` where a **raw completed provider
  response** first exists, the client appends a record to the sink —
  BEFORE any promotion, `</think>` extraction, retry decision, or raise.
- The internal `generate_retry` path appends one record per attempt
  (`status=retry` for superseded attempts).
- The `ReasoningFirstTruncationError` path appends the raw truncated
  response (`status=truncated`) to the sink **before raising** — so the
  reasoning is preserved even though the call "fails" and `_call_section`
  catches the exception and returns an empty draft.
- Generator-call context (`section`, `call_type`, `attempt_n`) is supplied
  by the caller via a per-call context the client threads onto the record.

### 2.6 Store + manifest + signed bundle (P1-003, P2-001, P2-003)

- Per run: `reasoning_trace.jsonl` in the run output dir.
- Manifest: trace-file injection is centralized in
  `audit_ir/manifest_augment.py::augment_v6_manifest()` so all three
  `scripts/run_honest_sweep_r3.py` manifest paths (success / abort / error)
  reference it uniformly — not bolted onto each write site.
- Signed bundle: `build_slice_chain()` returns `(decision, pool, report)`
  and `build_manifest_and_files()` currently takes no sidecar input.
  `build_manifest_and_files()` gains an explicit optional
  `extra_files`/artifact-dir parameter; the `/runs/{run_id}/bundle.tar.gz`
  bridge passes `reasoning_trace.jsonl` through it; a new
  `content_type=reasoning_trace` is added so the file is included AND
  hashed in the signed manifest. A bundle test asserts the trace file is
  present and hashed under that content type.
- `REVIEWER_README.md` (+ `/transparency` or the bundle README) documents
  the trace as **model-process evidence, NOT verified claims**.

## 3. Acceptance criteria (verify correct + complete)

1. A run-scoped collector captures `reasoning` + `reasoning_tokens` from
   **every raw completed provider response** for generator-side LLM calls
   (§2.2), via an `OpenRouterClient`-level sink (§2.5) — including internal
   `generate_retry` attempts and the `ReasoningFirstTruncationError` path.
2. Per-run `reasoning_trace.jsonl`, one record per response with the §2.4
   schema; reasoning text lives in the jsonl only — never independently
   merged into `report.md` / `verified_text` / the verified-sentence stream.
3. `manifest.json` references the trace (via `augment_v6_manifest()`); the
   signed `bundle.tar.gz` includes + hashes it under
   `content_type=reasoning_trace`.
4. `/transparency` or bundle `REVIEWER_README.md` documents the trace as
   process evidence, not claims.
5. **Separation invariant + tests:** `reasoning_trace.jsonl` is a separate
   artifact; `strict_verify` runs on the content channel only, never
   independently on `reasoning_text`. Tests: (a) a V4-Pro-style
   `content='', reasoning='SENTINEL'` response → captured, recorded
   `content_source=promoted_from_reasoning`; (b) the internal
   `generate_retry` path → each attempt recorded; (c) the
   `ReasoningFirstTruncationError` path → the truncated raw response
   recorded `status=truncated` before the raise; (d) a normal call →
   `reasoning_text` (the CoT) never appears in `report.md`.
6. Non-reasoning models (`reasoning` empty/None) → record still written,
   empty `reasoning_text`, uniform schema, no crash.
7. Codex diff review APPROVE.

**Diff-size note:** client-level capture + every generator call + manifest
+ signed-bundle interface + tests will likely exceed the 200-LOC isolated-
CODE cap; this is inherent to the operator's "whole reasoning log" scope —
request the Codex diff-review exemption rather than narrowing coverage.

## 4. Code surface

- `src/polaris_graph/llm/openrouter_client.py` — `_call` / `generate` /
  `generate_retry` / promotion / `ReasoningFirstTruncationError`; add the
  `reasoning_sink` (§2.5).
- `src/polaris_graph/generator/` — `multi_section_generator.py`
  (`_call_outline:455`, `_call_section:778`/`:903`,
  `_call_trial_summary_table:1858`, `_call_m50_per_trial_subsection:1989`,
  `_call_limitations:2105`), `sentence_repair.py`, `analyst_synthesis.py`,
  `fact_dedup.py`, `contract_section_runner.py` (`_m63_llm_call`),
  `cross_trial_synthesis.py`, `cross_jurisdiction_synthesizer.py`,
  `regulatory_synthesizer.py`, `live_deepseek_generator.py`.
- `scripts/run_honest_sweep_r3.py` — success/abort/error manifest writes;
  `src/polaris_graph/audit_ir/manifest_augment.py::augment_v6_manifest()`.
- `artifact_to_slice_chain.build_slice_chain()` +
  `audit_bundle.manifest_builder.build_manifest_and_files()` — the signed
  `/runs/{run_id}/bundle.tar.gz` path.

## 5. Required output schema (§8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
