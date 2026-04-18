# FROZEN: `src/orchestration/` subsystem

**Status**: frozen since 2026-03-16 (33+ days).
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

## What to do with it

Three options (pick one deliberately, not by default):

**(a) Retire**: archive this folder + `scripts/full_cycle.py` + the
`research` branch of `docker_entrypoint.sh`. Remove from README and
docs. This is the cleanest option if the pipeline is genuinely abandoned.

**(b) Repair**: re-create the missing `scripts/final_audit.py` and
`scripts/run_ragas_v3.py`, wire them back in, and add integration
tests to prevent rot. Only worth it if this CLI is a real product entry.

**(c) Leave as-is**: acknowledge it's frozen, do not advertise it,
but keep the code around in case a future requirement brings it back.
This README marker serves the "acknowledge" part.

Until an option is chosen, the code here is **read-only by convention**.
No patches should be accepted against this folder without first picking
(a), (b), or (c).

## Related

- Same freeze applies to the satellite subsystems:
  `src/auth/`, `src/benchmarks/`, `src/llm/` (the non-polaris_graph one),
  `src/memory/` (the non-polaris_graph one), `src/quality/`,
  `src/schemas/` (the non-polaris_graph ones), `src/search/`,
  `src/state/`. All last touched 2026-03-16.
- Active subsystems: `src/polaris_graph/*` (159 commits in last 60 days),
  `src/tools/`, `src/agents/`, `src/audit/`, `src/config/`.

See `docs/live_code_audit.md` for the full dependency-closure analysis.
