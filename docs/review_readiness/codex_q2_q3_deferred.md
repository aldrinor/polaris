# Codex Q2/Q3 — outcome: both deferred/skipped (recorded for review)

**Q2 — PG_GENERATOR_MODEL default: DEFERRED to owner (codex DECISION Q2:B, high reasoning).**
The 4 call sites default to NON-EMPTY models when the env var is unset (`deepseek/deepseek-v4-pro`
at two argparse `--model` defaults + a config dict, `z-ai/glm-5.2` at one). Standardizing to `''`
is byte-identical in production (`.env` sets `glm-5.2`, env wins) but CHANGES the unset-env path
(CI/dev): the argparse `--model` default would go from a real model string to `''`, which could
pass an empty model into the pipeline. That violates the provable no-behavior-change rule, so codex
ruled **revert + defer**: PG_GENERATOR_MODEL remains a genuine conflicting-default requiring an owner
decision (which single model the unset fallback should be, or leave the per-site defaults as-is).

**Q3 — lethal_retrieve rename: SKIPPED (codex-confirmed).** Not confined to a retired script — it's
a live function (`src/polaris_graph/wiki/mesh/retrieve/lethal.py:95`) imported by two active tests
(`test_mesh_e2e.py`, `test_mesh_lethal_retrieve.py`) with the name embedded in a persisted test
filename + `.codex` fixture paths. Renaming would break active tests and exceed the "retired, low-risk"
scope, failing codex's rename condition (b). Left unchanged.
