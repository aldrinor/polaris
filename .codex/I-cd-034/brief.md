# Codex brief — I-cd-034 (#634) — Phase 5b matrix runner

Per Codex scope-consult 2026-05-20 (A > C > B): ship `scripts/run_test_matrix.py` skeleton + carve operator execution to follow-up #696. Runner enumerates 24 rows × 11 journey stages, gates LLM-bound rows via `--include-llm`, emits structured result YAML, returns proper exit codes. Acceptance: runner exists + matrix execution is operator-action.
