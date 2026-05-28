HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# BRIEF v2: wire pathB_run_gate into a real POLARIS run path (I-safety-002b / #925, step-3 P1-3)

iter-1 verdict was REQUEST_CHANGES with 3 P1 + 3 P2. **All addressed below.** This is the corrected
approach; APPROVE it (or surface remaining blockers) so I can author the diffs (PR-1/2/3 per your split).

## iter-1 P1 fixes (the three real design errors you caught)
1. **Capture at the true completion boundary, not generate/generate_structured.** Confirmed seam:
   `OpenRouterClient._call` (openrouter_client.py:1213) → **`_call_impl` (1242)** is the SINGLE funnel
   for every provider completion — non-stream POST (1402 `/chat/completions`) AND the streaming path
   (`_stream*` ~1121-1137) AND retries AND `reason()`/`generate()`/`generate_structured()` all route
   through `_call`/`_call_impl`. The capture hook goes at `_call_impl`'s completion point, so retries,
   superseded primary attempts, and reason() calls are ALL captured (one LLMCall per provider
   completion, with attempt index).
2. **Capture the direct-httpx entailment judge (the evaluator-family path that bypasses the client).**
   Confirmed: the strict-verify entailment judge lives in `src/polaris_graph/llm/entailment_judge.py`
   and is invoked from `provenance_generator.py` (`_get_judge().judge(...)`, ~1161/1220). It posts
   directly to `/chat/completions` via httpx, NOT through OpenRouterClient. Fix: add the SAME capture
   call inside the judge's request method, building response_metadata from ITS OWN response JSON
   (served provider + model + system_fingerprint), role-tagged "evaluator". (In-place capture, not
   reroute-through-client — reroute is larger surgery + risks changing judge behavior; the gate only
   needs the served-identity + completeness, which in-place capture provides.) This makes the
   two-family completeness check real instead of a silent no-op.
3. **Served-metadata provenance — never request-derived.** Build response_metadata from the ACTUAL
   served response: non-stream → the response JSON `data` (carries `provider`, served `model`,
   `system_fingerprint`); streaming → read `provider`/`model` from the SSE events/final chunk, NOT
   `self.model`. If a served field is genuinely absent (e.g. DeepInfra omits system_fingerprint), it
   is EXCLUDED from the surrogate (never request-filled). The diff will extract served provider+model
   at the point the SSE/JSON is parsed; if the streaming path currently discards served provider, the
   diff adds its capture there. **Request-derived fields are never counted as response-proven** (your
   answer B). If provider is unavailable from the response for a given path, that path FAILS the gate
   (loud), not silently passes.

## iter-1 P2 fixes
- **Scoped role tagging via context manager** `with llm_role("generator"): ...` (contextvar set→token→
  restore in `finally`), NOT a sticky `set_llm_role()`. No stale role leakage to later calls.
- **assert_post_run on ALL run exits** — success AND every early-abort path (scope_rejected,
  corpus_inadequate, no_verified_sections, budget, error_*) — BEFORE any scorer/artifact consumer
  runs. On GateError: mark run INVALID, do not score, surface loudly.
- **Lazy, gate-flagged import** — the `_call_impl` and entailment_judge hooks import `pathB_capture`
  lazily and act only when the gate is registered for the current run; gate-off = zero hot-path cost
  and no hard `src`→`scripts` import.

## Your iter-1 answers, locked into the design
- A: explicit scoped role attribution (context manager). B: per-role preflight probe uses the SAME
  capture/metadata path; request-derived fields never response-proven. C: surrogate = provider_name+
  model when system_fingerprint absent. D: 3-PR split (below). E: 1-question operator-supervised smoke
  on #72 or #90 AFTER wiring, BEFORE the 5 full runs.

## PR split (your D)
- **PR-1**: `src/polaris_graph/benchmark/pathB_capture.py` (contextvar sink, `llm_role` ctx-mgr,
  `record_retrieval_attempt`, `build_response_metadata` dropping None, `request_hash`) + the
  `_call_impl` hook + the entailment_judge capture hook + pure tests (incl. a fake direct-judge call
  proving evaluator capture, and a streaming-shape fake proving served-provider provenance).
- **PR-2**: retrieval-attempt hooks (serper + semantic_scholar call sites in
  `retrieval/{live_retriever,domain_backends}.py`) + runner gate lifecycle in `run_honest_sweep_r3.py`
  (`--pathB-gate` flag: preflight + per-role surrogate probe + register sink + assert_post_run on all
  exits + persist pin to run dir).
- **PR-3**: live/operator-supervised smoke (#72 or #90) + scoring integration (claim_audit_scorer
  consumes only a gate-PASS run). Each PR ≤200 LOC where possible; PR-1 may need an exemption note.

## Output schema (return EXACTLY this)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: []
continuing_p0: []
p1: []
p2: []
p3: []
seam_confirmations:
  call_impl_capture: <ok | concern>
  entailment_judge_capture: <ok | concern>
  served_metadata_provenance: <ok | concern>
convergence_call: continue | accept_remaining
remaining_blockers_for_diff: []
```
Loose verdict prose without this schema will be rejected and resubmitted.
