# POLARIS Todo List

**Last Updated**: 2026-04-18 (post-audit cleanup)

Highest-priority items at the top. Older entries are in
`archive/2026-04-18-pre-audit-cleanup/docs/todo_list_legacy.md` (see
note at end of this file).

---

## Active

### Deep-dive rounds in progress

Priority order per Codex scoping pass:

- [x] R1 orchestration — BUG-B-101 manifest status contract (commit `c764ddb`, 9 tests)
- [~] R2 pipeline_b_parity — BUG-B-102 UI un-hardened. **SCOPED (strategy C accepted); implementation queued as R2a-R2h** (see below)
- [ ] R3 intake_scope — BUG-B-100 scope gate never rejects — NEXT
- [ ] R4 generation — BUG-M-203 outline collapse
- [ ] R5 evaluator — BUG-M-205 advisory vs gating
- [ ] R6 retrieval_tiering — BUG-M-201 gate/generator divergence
- [ ] R7 contradictions — BUG-M-202 narrow predicates
- [ ] R8 observability — BUG-M-206 cost ledger per-run
- [ ] R9 testing — BUG-M-207 contract coverage
- [ ] R10 strict_verify — BUG-M-204 limitations bypass (light touch)
- [ ] R11 budget_cost — BUG-N-301 session_id threading (light touch)
- [ ] R12 frozen_c_disposition — BUG-M-208 retire/repair/leave decision (user-facing)

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
