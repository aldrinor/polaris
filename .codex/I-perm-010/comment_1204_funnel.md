## Task 1 (funnel trace) DONE — Codex APPROVE (offline, no spend)

Trace: `outputs/audits/I-perm-010/funnel_trace_drb76.json`. Codex gate APPROVE (every count
re-verified against `outputs/audits/beatboth8/drb_76/manifest.json`; no P0/P1).

**Verified funnel (drb_76):** 2981 discovered (retrieval.pre_filter — NOT 800; that was the agentic
sub-lane) → **740** post pre-fetch cull (drop **2241**) → 500 fetched (drop 240 fetch-fail) → 55
evidence rows (drop 445 extraction) → 46 selected (drop 9) → 46 to generator (cap never bound) → 81
sentences generated (fan-out) → 40 strict_verify-survived (drop 41) → 23 4-role-survived (14 redacted).

**Dominant loss = the pre-fetch cull (2981→740, drop 2241)** — ~5× the next stage, ~55× the verifier
drop. It is the **off-topic semantic relevance filter** (`live_retriever.py` step 3,
`filter_search_results`), NOT the generator cap (which never bound here) and NOT the verifier. The
fetch_cap was raised this run so it did not bind either.

**#1 finding — instrumentation gap:** the off-topic filter DOES compute `total_kept / total_rejected /
threshold_used` but only appends them to a local `notes` list that is **never persisted to manifest.json**;
the fetched→finding-row extraction yield (500→55, the 2nd-biggest drop) has no counter at all. So the
**legitimate-vs-throttle split of the single largest source loss cannot be adjudicated from saved
artifacts.** A focused clinical question may legitimately discard most of 2981 candidates — or the
threshold may be over-cutting. We cannot tell until it is instrumented.

**Legitimate + measured:** the 41-sentence verifier drop (29 entailment / 5 no-token / 4 overlap / 2
integer) and the fetch-failure tail are genuine. The run was HELD by the D8 coverage gate (0.40<0.70 +
S0 contraindications must-cover missing), NOT by source count.

## Task 2 reshaped — INSTRUMENT FIRST
Before touching any threshold: persist the off-topic filter's kept/rejected/threshold + the per-reason
`_trace_drop` aggregates + the fetched→finding extraction yield into the manifest (additive telemetry,
zero behavior change). Then a fresh instrumented canary (spend, VM, operator-gated) shows whether the
off-topic filter over-cuts. THEN fix/bake-off with data. Building the instrumentation now via the
Claude Codex Workflow (Codex diff-gate).
