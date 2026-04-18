# FROZEN / RETIRING: `src/orchestration/` subsystem

**Status**: frozen since 2026-03-16 (33+ days); **retire decision
signed off 2026-04-18** (deep-dive R12). Actual archive move deferred
to a dedicated cleanup session because ~60 scripts under `scripts/`
still import from this subsystem (most are ad-hoc one-offs that will
be archived as part of R2h / future scripts-cleanup).

**Last-audit date**: 2026-04-18.

## What this subsystem is

The "pipeline C" research orchestration: LangGraph-based `run_research()`
invoked by `scripts/full_cycle.py` when the Docker container is started
with the `research` subcommand (see `scripts/docker_entrypoint.sh`).

## Why it's flagged

1. **No commits since 2026-03-16**. The active development focus moved
   to `src/polaris_graph/` (pipeline A, the honest-rebuild, and pipeline
   B, the UI-server graphs v1/v2/v3).
2. **Its Docker entry is partially broken**. `scripts/full_cycle.py`
   imports `scripts/final_audit.py` and `scripts/run_ragas_v3.py`, but
   neither file exists in the repo. The CLI `research` subcommand would
   fail on any non-trivial run.
3. **Not exercised by any test in `tests/polaris_graph/`**. The 305
   passing tests all target pipeline A.

## Decision (2026-04-18, deep-dive R12): option (a) RETIRE

Rationale:
  - 33+ days of no commits; no active owner.
  - `scripts/full_cycle.py` imports two files that don't exist in the
    repo (`scripts/run_ragas_v3.py`, `scripts/final_audit.py`) — the
    Docker `research` subcommand was already broken.
  - Pipeline A (`scripts/run_honest_sweep_r3.py`) now carries all the
    hardening invariants and is the active product path.
  - Pipeline B (`scripts/live_server.py`) will back-port pipeline-A
    invariants via R2a-R2h (graph_v4 shim).
  - Pipeline C has no test coverage and no production users.

Retire execution (staged):

1. **2026-04-18 (done)**: `scripts/docker_entrypoint.sh` no longer
   dispatches to pipeline C. The `research` subcommand now returns a
   deprecation error explaining to use `sweep` (pipeline A) or
   `serve` (pipeline B) instead. See commit 6a0a041 (Phase E).

2. **2026-04-18 (done)**: `README.md` and `architecture.md` list
   pipeline C as FROZEN with a pointer to this file.

3. **Deferred to a dedicated cleanup session (not this one)**:
    - Archive `src/orchestration/` to
      `archive/YYYY-MM-DD-retire-pipeline-c/src/orchestration/`.
    - Archive `scripts/full_cycle.py` to the same archive dir.
    - Archive the ~60 scripts under `scripts/` that import from
      `src/orchestration/` (many are ad-hoc one-offs already flagged
      for R2h).
    - Remove pipeline C entirely from README + architecture.md +
      file_directory.md + runbook.md.
    - Remove the `research` branch from `scripts/docker_entrypoint.sh`
      (currently it just errors; then remove the case entirely).

The deferral is because archiving `src/orchestration/` right now
would break ~60 `scripts/`. Those scripts need to be individually
reviewed for whether they're worth preserving (most are not, per
the R2 Codex scoping pass). That review is a separate session.

Until the deferred archive happens, the code here remains read-only
by convention. No patches should land against this folder.

## Related

- Same freeze applies to the satellite subsystems:
  `src/auth/`, `src/benchmarks/`, `src/llm/` (the non-polaris_graph one),
  `src/memory/` (the non-polaris_graph one), `src/quality/`,
  `src/schemas/` (the non-polaris_graph ones), `src/search/`,
  `src/state/`. All last touched 2026-03-16.
- Active subsystems: `src/polaris_graph/*` (159 commits in last 60 days),
  `src/tools/`, `src/agents/`, `src/audit/`, `src/config/`.

See `docs/live_code_audit.md` for the full dependency-closure analysis.
