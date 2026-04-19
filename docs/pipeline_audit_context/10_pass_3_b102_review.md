# POLARIS full-audit pass 3 — B-102 critical review + READY check

You are re-auditing POLARIS after B-102 (pipeline-B UI parity) has
been implemented via `graph_v4`. Pass 2 said NOT_READY primarily
because B-102 was deferred. Post-commit `427b6ff` B-102 is CLOSED
(pending your verification) plus three post-pass-2 remediations
(B-201 / M-209 / N-302).

## Context

Commits since pass 2 (55475c8):

- `ddcd1d4` deep-dive R12 pipeline C retire decision
- `427b6ff` **B-102 CLOSED: graph_v4 shim wraps pipeline A for UI**
- And the pass-2 remediation commit you requested (B-201 ContextVar,
  M-209 metric binding, N-302 selector cap)

Test suite: 405 passed (from 387 at pass 2). Zero failing.

## Your mandate — CRITICAL review, not rubber stamp

The user has explicitly asked you to review the B-102 fix critically
and iterate until READY. Previous pattern: Codex finds substantive
defects, Claude fixes, Codex re-verifies. We're in that loop now.

### 1. Verify B-102 is actually closed

Read `src/polaris_graph/graph_v4.py`. Verify:
- `build_and_run_v4` signature matches v1/v2/v3's (so the live_server
  dispatch drop-in is real, not type-error-at-runtime)
- It calls `scripts.run_honest_sweep_r3.run_one_query` (the pipeline-A
  orchestrator that carries ALL the hardening)
- Output JSON at `outputs/polaris_graph/{vector_id}.json` actually
  matches the fields `scripts/live_server.py` reads when serving the
  result endpoint
- Trace events (`pipeline_start`, `pipeline_end`) are emitted
  correctly through `PipelineTracer`
- Error path converts exceptions to `status="error_unexpected"` (in
  UNIFIED_STATUS_VALUES)

Read `scripts/live_server.py:548-575` (the `_run_pipeline` dispatch).
Verify:
- `PG_GRAPH_VERSION` default is `"v4"` (pipeline A-backed)
- The `v4` branch imports `build_and_run_v4`
- v1/v2/v3 are still selectable via explicit env flags (compat)
- Unknown version falls back safely to v4

### 2. Probe edge cases

Specifically look for:

- **Domain inference bypass**: a malicious / crafty query that routes
  through `custom.yaml` but bypasses a hardening invariant because
  the custom template's tier expectations are permissive. Does the
  corpus_approval_gate still reject rubber-stamp notes on material
  deviation? The custom template says "no minimums" — does that
  effectively disable approval enforcement?
- **Concurrent UI runs**: two simultaneous `/api/research` calls.
  Pass 2's B-201 fix used ContextVar, but graph_v4 is called from
  live_server's async task. Verify ContextVar isolation holds in
  the actual live_server execution path.
- **UI output shape drift**: does `_adapt_pipeline_a_to_ui_json`
  produce every field an existing `scripts/live_server.py` endpoint
  reads? If readers access `quality_metrics.faithfulness_score` or
  similar, a missing field would show as a client-side null. Look
  at every `.json` read site in live_server.
- **SSE trace streaming**: the existing frontend watches
  `logs/pg_trace_{vector_id}.jsonl` via `TraceTailer`. graph_v4 only
  emits 2-3 events (start, assembled, end). If the frontend expects
  granular events (retrieval progress, per-section writes), users
  see a long dead period mid-run. Is this a real UX regression?

### 3. Verify post-pass-2 remediations

Pass 2 surfaced three defects. Verify they're substantively fixed:

- **B-201 ContextVar**: `src/polaris_graph/llm/openrouter_client.py`.
  Confirm `_CURRENT_RUN_ID_CTX` and `_RUN_COST_CTX` are `ContextVar`
  instances, NOT module-level scalars. Confirm `set_current_run_id`,
  `current_run_id`, `reset_run_cost`, `current_run_cost`, and
  `_add_run_cost` all go through the ContextVars. Reproducer from
  pass 2 must pass:
  ```python
  # Two async tasks set different run_ids; they must NOT stomp each other.
  ```
- **M-209 metric binding**:
  `src/polaris_graph/generator/provenance_generator.py::verify_limitations_sentence_against_telemetry`.
  Confirm `_TELEMETRY_METRIC_KEYS` list exists and every line is
  checked against it. Pass-2 reproducer
  `"T-cell count of 500"` with `"http_status: 500\n..."` must reject.
- **N-302 selector cap**:
  `src/polaris_graph/retrieval/evidence_selector.py`. Confirm the
  over-allocation loop can deduct below present-HV floors when
  `max_rows < count(present_hv_floors)`. Pass-2 reproducer: 4 rows
  (T1/T2/T3/T7) with `max_rows=2` must return 2 rows, not 3.

### 4. Final verdict

One of:
- **READY**: B-102 is substantively fixed, pass-2 remediations hold,
  no new blockers surfaced
- **NOT_READY**: something above failed; re-raise with reproducer
- **CONDITIONAL**: ship pipeline A + custom-domain UI only; require
  follow-up for a specific deferred item

### READY BAR (anti-circle-jerk)

To grant READY:
- Zero blockers
- ≤2 mediums each with explicit acceptable-risk rationale
- B-102 fix must be **substantive** not cosmetic — the UI path actually
  goes through pipeline-A hardening
- No new silent-failure inputs discoverable in 15-25 min of probing

Do NOT grant READY just because we asked you to. If the v4 shim has
a design flaw or a silent failure path, say so.

## Output

Write to `outputs/codex_findings/full_audit_pass_3/findings.md` with
this frontmatter:

```yaml
---
verdict: READY | NOT_READY | CONDITIONAL
pass: 3
commit: 427b6ff or later
b102_disposition: CLOSED_CONFIRMED | STILL_OPEN | REOPENED
pass_2_remediations_verified: [B-201, M-209, N-302] or subset
new_blockers: <int>
new_mediums: <int>
rationale: |
  <2-4 sentence executive summary>
---
```

Followed by:
- `## 1. B-102 substantivity check` — per-item verdict on graph_v4
- `## 2. Edge-case probes` — domain bypass, concurrency, UI shape drift, SSE
- `## 3. Pass-2 remediation verification`
- `## 4. New defects (if any)` — file:line + reproducer
- `## 5. Final verdict and release guidance`

## Authentication

OAuth (chatgpt). No API-key burn.

## Expected duration

15-25 minutes.

---

Start:

```
git log --oneline 55475c8..HEAD | head -10
git diff 55475c8..HEAD --stat | tail -20
python -m pytest tests/polaris_graph/ -q 2>&1 | tail -5
```

Then walk sections 1-4.
