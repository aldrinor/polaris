# POLARIS Todo List

**Last Updated**: 2026-04-20 (M-25 planning post-DR pass 4)

## ACTIVE: Full-Scale DR Auto-Loop (user directive 2026-04-19)

**Procedure**: `state/full_scale_auto_loop_procedure.md`
**Memory**: `C:\Users\msn\.claude\projects\C--POLARIS\memory\full_scale_dr_auto_loop.md`
**Handover**: `state/autoloop_handover_2026-04-20.md`

Loop (no cycle cap, auto-continue):
1. Claude fixes → unit tests → smoke
2. Codex code audit line-by-line
   - BLOCKED → claude fixes, loop
   - GREEN → full-scale at MAX CAPACITY (serper/s2=50, fetch_cap=500, ev=400, $10/query budget)
3. Codex DEEP DR-level output audit (every URL, every citation, every sentence — no pattern matching, no cherry picking)
   - BLOCKED → full issues list → claude fixes, loop back to step 1
   - GREEN at GPT-5.4-DR / Gemini-3.1-Pro-DR top-tier quality → STOP

**Current cycle**: Iteration 7 — V10 complete + DR pass 4 MATERIAL-GAPS. M-25 planning.

Pass sequence:
- V4-V5-V6 DR passes 1-3 → all MATERIAL-GAPS
- V7-V9 MATERIAL-GAPS: low citation count, paywall stubs on NEJM/Lancet
- **M-23 a-f** (commits 6c999e8 + ff68b86): access_bypass fixes (done)
- **M-24 a-b** (commit 6c999e8 + hotfix): outline/section prompts (done)
- **V10 completed** at commit `ff68b86`:
  - status=abort_evaluator_critical, release_allowed=false
  - T1=20%, T2=14% (BEST corpus tier mix), 309 sources
  - 3 sections, 834 words, 16 unique citations
  - PT08+PT11 fail, Qwen citation_tightness=needs_revision
- **DR pass 4 dispatched + completed** at commit `5502ddb`:
  - Live-fetch mandate satisfied (no metadata-only verdicts)
  - 18 FAITHFUL / 1 FABRICATED / 1 EMBELLISHED / 4 UNVERIFIABLE
  - Verdict: MATERIAL-GAPS-FIX-AND-RESWEEP

### Pass-4 root-cause diagnosis (advisor-gated before M-25)

1. **Outline section count 3 not 5**: NOT a fallback. LLM outline parsed
   OK; prompt permits "3-5 sections", LLM chose minimum. Need to force
   5 where corpus supports it. `manifest.generator.outline_sections=
   ["Efficacy","Safety","Comparative"]`.
2. **FABRICATED #20 = generator trial-binding bug**: ev_015 IS the
   SURMOUNT-3 paper (correctly labeled). Generator wrote a SURMOUNT-1
   sentence and bound it to ev_015 SURMOUNT-3. strict_verify passed —
   no trial-name gate prevented the mismatch.
3. **EMBELLISHED #12 = scope leak**: Safety section cites PG-102 phase I
   (bispecific GLP-1/GLP-2 — NOT tirzepatide). No drug-name gate.
4. **4 UNVERIFIABLE**: Codex couldn't live-fetch 4 sources. Deferred
   inspection of cached corpus content.

### M-25 plan (post-pass-4, advisor-gated)

- [ ] **M-25a (HIGH)**: Trial-name match in strict_verify. If sentence
      names trial (SURPASS-N/SURMOUNT-N/SELECT/LEADER/etc.), cited
      evidence must have trial in title OR explicit post-hoc link.
      Prevents FABRICATED-#20 class. Add failing test first.
- [ ] **M-25b (HIGH)**: Outline "choose 5 when supported" — raise
      minimum from 3 to 5 (4 allowed only if ≥2 sections would have
      <8 ev_ids). Expands 3→5 sections and 834→~1400+ words.
- [ ] **M-25c (MEDIUM)**: Drug/population scope gate in safety writer.
      Reject evidence rows lacking tirzepatide OR explicitly non-T2DM.
      Addresses EMBELLISHED #12.
- [ ] **M-25d (MEDIUM)**: Emit M-23 telemetry to run_log.txt
      (Unpaywall hits, OA swaps, winner-backend, quality score).
- [ ] **M-25e (LOW)**: Citation adjacency in limitations + contradictions.
      Prompt + post-processing; PT11+PT08.
- [ ] **M-25f (DEFER)**: Adjudicated contradiction table. Post-M-25.

Do NOT launch V11 until M-25a + M-25b + green suite.

Tasks: #153-156 completed (V10 + DR pass 4). #157 M-25 IN PROGRESS.

---

Highest-priority items at the top. Older entries are in
`archive/2026-04-18-pre-audit-cleanup/docs/todo_list_legacy.md` (see
note at end of this file).

---

## Active

### Pass 5 ✅ CONDITIONAL → M-5 fixed — ready for 8-query sweep

Codex pass 5 (commit `b2b6f5a`) declared **CONDITIONAL** with one
gating medium (M-5 PT12 false positive). Fixed in commit `5cf6959`:

- [x] **M-5 PT12 bibliography year bracket false positive** —
  PT12 citation-marker scan restricted to pre-bibliography prose
  (split at `\n## bibliography`). Bibliography entry titles like
  "Best Guide on RAG Pipeline [2025]" no longer flag as out-of-range
  citation markers. Two regression tests:
  - `test_pt12_ignores_bibliography_title_year_brackets` (the exact
    tech-smoke regression case)
  - `test_pt12_still_flags_real_out_of_range_citation_in_prose`
    (guard against fix being too permissive)

Codex pass 5 confirmed non-gating:
- M-1 substantive (no deadline-boundary race)
- M-2 substantive (content-aware span doesn't trivialize strict_verify)
- PT13 advisory-only (release_gate doesn't block on it)

Post-fix tech smoke: `status=success, release_allowed=true,
12/13 rule checks pass, 19/20 fetched, 682 words, 3.8% drop rate`.

**Status: READY for 8-query full sweep pending user go.**

Remaining non-gating follow-ups (pass 4 + 5):

- [x] **M-6 PT13 question-inherited superlative exemption** — fixed.
  PT13 now skips the first `# ` title line and exempts
  single-word superlatives that appear in
  `protocol["research_question"]`. Multi-word phrases
  ("better than placebo") still flag when unhedged. Two tests in
  `test_external_evaluator.py::test_pt13_exempts_title_and_question_inherited_superlatives`
  and `::test_pt13_still_flags_real_generator_superlatives`.
- [x] **M-3 PT13 advisory surfacing** — fixed. Added `ADVISORY_RULES`
  map in `evaluator_gate.py`; PT13 failures now emit
  `advisory_pt13_unhedged_superlatives` into
  `manifest.evaluator_gate.reasons` without changing `gate_class` or
  `release_allowed`. Tests in `test_m205_evaluator_gate.py`.
- [x] **M-4 tier material_deviation communications** — fixed.
  `docs/runbook.md` §8 now has a "corpus.material_deviation=true on a
  released manifest" section explaining that such runs are pipeline
  reliability signals, not content-quality benchmarks, and listing
  concrete re-run levers (PG_LIVE_MAX_SERPER_PER_Q, academic-first
  backends, narrower question).
- [x] **M-2 legacy content starvation mitigation options** —
  DEFERRED. The content-aware span finder (commit `b2b6f5a`) already
  addressed the dominant root cause: clinical smoke drop rate
  80% → 15%, words 174 → 605; tech 32% → 3.7%, words 529 → 689.
  Further levers (prompt tightening, per-template overlap, lenient
  Methods mode) remain available if specific 8-query sweep queries
  show thin output — not required pre-sweep.

### Pass 4 ✅ CONDITIONAL → M-1 fixed — 3 accepted mediums

Codex pass 4 (commit `81b18de`) declared **CONDITIONAL** after live
smoke testing exposed a real-world regression pass 3 didn't catch.
Single gating medium fixed in commit `ac593e1`:

- [x] **M-1 worker-join deadline** — `live_retriever._fetch_content`
  now uses `worker.join(timeout=PG_FETCH_DEADLINE_SECONDS)` (default
  90s; override via env; set 0 to disable). On timeout: log a
  warning, fall back to naive httpx, leave the daemon thread to
  exit on its own so the sweep never hangs on a wedged Crawl4AI
  browser cleanup. Regression test in
  `tests/polaris_graph/test_fetch_access_bypass_wiring.py::test_fetch_content_times_out_falls_back`.

Remaining mediums accepted as follow-ups (non-blocking):

- [ ] **M-2 content starvation risk** — clinical smoke produced
  146 words total (3/4 sections kept, 20/24 sentences dropped by
  strict_verify). By-design honesty discipline, transparent in the
  manifest. Possible mitigation: widen generator prompts so more
  sentences have verifiable provenance, or relax content-overlap
  threshold for limitations-section claims.
- [ ] **M-3 PT13 advisory rule** — tech smoke failed PT13 (unhedged
  "best") but `release_allowed=True` because qwen-judge returned
  5/5 good. Expected: the eval_gate treats qwen as primary gate and
  PT13 as advisory. Consider surfacing the rule-check failure more
  prominently in `manifest.evaluator_gate.reasons` even when release
  is still allowed.
- [ ] **M-4 tier material_deviation** — both smoke runs had
  material_deviation=True (clinical 40% T7, tech 70% T4). Expected
  for web retrieval; corpus_approval_gate enforces and the manifest
  reports honestly. Documentation follow-up: add a runbook note
  explaining that 8-query sweep outputs should be read as pipeline
  reliability signal, not as a quality benchmark of the report content.

### Deep-dive rounds in progress

Priority order per Codex scoping pass:

- [x] R1 orchestration — BUG-B-101 manifest status contract (commit `c764ddb`, 9 tests)
- [~] R2 pipeline_b_parity — BUG-B-102 UI un-hardened. **SCOPED (strategy C accepted); implementation queued as R2a-R2h** (see below)
- [x] R3 intake_scope — BUG-B-100 scope gate never rejects (commit `95a9709`, 7 tests)
- [x] R4 generation — BUG-M-203 outline collapse + fallback (9 tests)
- [x] R5 evaluator — BUG-M-205 evaluator gate (10 tests)
- [x] R6 retrieval_tiering — BUG-M-201 tier-balanced selector (9 tests)
- [~] R7 contradictions — BUG-M-202 MVP done (domain routing + 5-domain predicates + 9 tests); **followup R7b** = generic numeric-claim mining + domain YAML profile loader + per-row multi-claim emission per Codex R7 §4
- [x] R8 + R11 — BUG-M-206 per-run cost ledger + BUG-N-301 ambient run_id (10 tests, combined commit)
- [x] R9 testing — BUG-M-207 invariant coverage audit (11 tests)
- [x] R10 strict_verify — BUG-M-204 limitations telemetry verifier (10 tests)
- [x] R12 frozen_c_disposition — BUG-M-208 **decision: RETIRE** (staged in `src/orchestration/FROZEN_SINCE_2026-03-16.md`; archive move deferred to dedicated cleanup session because ~60 scripts import from `src/orchestration/`)

### Pass 3 ✅ READY — follow-up mediums tracked as non-blockers

Codex pass 3 (commit `427b6ff`) declared **READY**. Zero blockers. Two accepted-risk mediums tracked as follow-ups:

- [ ] **M-210 v4 UI JSON auxiliary shape** — `_adapt_pipeline_a_to_ui_json` doesn't populate `evidence`, `sections`, `claims`, `iteration_count`, `trace_summary`, `smart_art_diagrams`, `evaluator_output` — citation-chain / source-preview / mindmap UI tabs degrade to empty for v4 runs. Main report + bibliography work. Fix: adapter loads `live_corpus_dump.json` + selected_evidence into auxiliary fields. ~2-3 hours.
- [ ] **M-211 SSE trace granularity** — v4 only emits `pipeline_start`/`report_assembled`/`pipeline_end`. v3 had per-phase events. Users see dead period mid-run. Fix: thread tracer through `run_one_query` (or use ambient `_current_tracer` ContextVar from tracing.py) and emit per-phase events (scope/retrieval/adequacy/approval/generation/evaluation).

### R2 (pipeline_b_parity) sub-tasks — multi-session implementation

Strategy C per Codex: add `graph_v4` shim wrapping pipeline A. See
`outputs/codex_findings/deep_dive_round_2/` for scope.

- [ ] **R2a**: extract pipeline-A `run_one_query` into reusable
  `src/polaris_graph/sweep_orchestrator.py::orchestrate_one_query`.
  `scripts/run_honest_sweep_r3.py` becomes a thin wrapper. Zero behavior change.
- [ ] **R2b**: add `config/scope_templates/custom.yaml` +
  `config/completeness_checklists/custom.yaml` as fallbacks for free-form UI queries.
- [ ] **R2c**: write `src/polaris_graph/graph_v4.py` with v1/v2/v3-compatible
  signature delegating to orchestrator.
- [ ] **R2d**: add trace-event sink to orchestrator so SSE progress events
  emit during the run.
- [ ] **R2e**: add `v4` branch to `live_server.py::_run_pipeline` as OPT-IN
  via `PG_GRAPH_VERSION=v4`. Do not change default yet.
- [ ] **R2f**: write the 8 integration tests Codex specified.
- [ ] **R2g**: after R2a-R2f land + soak, flip default dispatch to v4.
- [ ] **R2h**: either parameterize tests across v1/v2/v3 OR deprecate
  legacy variants and remove from dispatch (prefer removal).

Estimated total: 10-14 hours across 8 sub-rounds.

### Frozen subsystem decision (pending)

- [ ] **Pipeline C disposition** — decide retire / repair / leave for `src/orchestration/` + `scripts/full_cycle.py`. See `src/orchestration/FROZEN_SINCE_2026-03-16.md` for the decision tree. Blocking: the Docker `research` subcommand is broken (missing `final_audit.py`, `run_ragas_v3.py`).

### Pipeline B alignment (deferred)

- [ ] **Back-port honest-rebuild invariants to pipeline B (UI server)**. Pipeline A's strict_verify + corpus-approval + delimiter sanitization are not wired into `scripts/live_server.py`'s v1/v2/v3 paths. Users hitting the UI still get the old un-hardened behavior.
- [ ] **Consolidate UI graphs** — `graph.py`, `graph_v2.py`, `graph_v3.py` all coexist. Pick one, deprecate the rest.

### Scripts/ cleanup (second pass)

- [ ] **Archive remaining one-off scripts**. Phase A archived 61 files but 130 remain — many are `loopback_*`, `pg_micro_test_*`, `pg_empirical_*`, `monitor_*`, `debug_*` scripts that are single-use. Second-pass cleanup needed after the full audit identifies which are still valuable as probes.

### Tests

- [ ] **Add a live-network integration test** for pipeline A so a Serper/OpenRouter outage doesn't cause a silent production failure caught only when the 8-query sweep runs.
- [ ] **Mark unused `src/utils/` modules** — `circuit_breaker.py`, `quality_metrics.py`, `result_cache.py` are only kept because tests import them; if those tests become obsolete, these libs can be archived too.

### Docs

- [ ] **Write `docs/runbook.md`** — how to run each pipeline end-to-end, how to add a new query, how to add a new domain, how to replace the default model pair, how to interpret manifest statuses. (This is Task #61 in the cleanup plan.)
- [ ] **Reconcile CLAUDE.md §5 Repository Layout** with the new three-pipeline reality. The template in CLAUDE.md mentions `src/phases/` (no longer exists) and a "13 phases as binaries" invariant that doesn't apply to the current pipelines.

### Observability

- [ ] **Add a PID/host/hash stamp to every run's `manifest.json`** so two concurrent runs on the same machine can be distinguished without guessing.
- [ ] **Emit a `manifest.schema.json` file** alongside each sweep so consumers can validate the contract without reading `scripts/run_honest_sweep_r3.py` source.

---

## Completed (recent)

- [x] **5-round Codex↔Claude audit closed READY** (2026-04-18). Commits `724edf5`, `9493326`, `3a90b4f`, `c2570b2`, `248382e`, `db59e22`. Five blockers closed; 85 regression tests added. Test suite 220 → 305.
- [x] **Phase 1a/1b/1c/1d (partial)/1e/1f** of the honest-by-construction rebuild — see
  `archive/2026-04-18-pre-audit-cleanup/docs/todo_list_legacy.md` for the full history.
- [x] **Repo cleanup Phase A-C** (2026-04-18): 162 orphan files archived, 37 stale
  docs archived, 56MB of scratch dirs (`loopback/`, `tmp/`, `wiki/`, `cache/`)
  archived, root-level junk cleaned, `.gitignore` updated to prevent re-accumulation,
  README and `architecture.md` rewritten from scratch to reflect three-pipeline reality.

---

## Deferred / explicit non-goals

- **Autonomous systematic review** — user-confirmed non-goal on 2026-04-17.
  Honest-by-construction grounded research is the product, not machine-driven
  literature review.
- **ChromaDB as the primary LTM** — pipeline A does not use ChromaDB. It is
  retained only for pipeline B's checkpoint/memory behavior.
- **Model-ensemble evaluation** — currently one generator + one evaluator, with
  two-family constraint enforced. Multi-model ensembling deferred indefinitely.

---

## Note on prior todos

The previous `todo_list.md` (~320 lines, session-60-through-62 detail from the
honest-rebuild phase) was archived to
`archive/2026-04-18-pre-audit-cleanup/docs/todo_list_legacy.md` as part of the
repo cleanup. Historical decisions and completion records for the honest-rebuild
phases are preserved there. The new file above focuses on what is ACTIONABLE
going forward.
