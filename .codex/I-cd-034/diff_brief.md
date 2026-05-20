# Codex diff — I-cd-034 (#634) — test-matrix runner

Canonical-diff-sha256: `1e684a9605b71c56ac7737b8f05a0b86cd1c9ae7bde594cc34fc79f759c0daab` (iter 4; iter-1 + iter-2 + iter-3 fixes folded in).

## Iter-3 fixes
- **P1** (stage catalog grid): aligned R03/R15/R19/R20 stages with the doc's Applies-to grid (R03 +J5/J6/J11, R15 +J6/J7/J8/J10, R19 +J6/J7, R20 →J7/J8). The other 20 rows already match.
- **P2** (validation order): row + journey typo + reversed-range checks now run BEFORE env checks + /health probe — operators see config errors immediately without supplying secrets or reachable target.
- **P2** (reversed ranges): explicit error + exit 11 instead of silent empty selection.

## Iter-2 fixes
- **P1-003** (catalog mismatch): `_MATRIX_ROWS` now enumerates the 24 TEST TYPES from `docs/carney_handover/test_matrix.md` (Unit, Integration, Artifact contract, Visual regression, E2E happy/adversarial, Cross-browser, Accessibility, Multi-tab safety, Network resilience, SSE backpressure, Cancellation, Performance, Security, Tenant isolation, Privacy/redaction, Sovereignty, Migration, LLM quality gates, Semantic chart, Anti-sycophancy, Codex review, Layer-3 walkthrough, Fixture governance). Each test-type's `stages` mirrors the doc's "Applies to" list. LLM-bound subset realigned to the actual LLM-bound test types: R03, R05, R06, R19, R21.
- **P2-003** (docstring drift): module docstring + output-format comment now say `.json` (not `.yaml`); "structured YAML" framing clarified as "structured machine-readable; ship JSON for stdlib portability."
- **P2-004** (silent no-op on typos): unknown row id(s) or journey id(s) → exit 11 (config error) with explicit list of valid ranges.

## Iter-1 fixes
- **P1-001** (Windows cp1252): replaced em-dash + unicode arrows in row names with ASCII (`->`, `-`). Default Windows operator host stdout cp1252 cannot encode `→` and crashed before emitting results.
- **P1-002** (llm_bound flag drift): aligned llm_bound flags to documented 5-row spend subset (R03, R05, R07, R09, R11). R04, R08, R10, R12, R17, R21 → False (they verify deployed-system behavior via live OVH, not separate OpenRouter spend).
- **P2-001** (--journey unused): added stage-selection parse + intersection filter against row stages. R22/R24 with empty stages always run (process/infra gates).
- **P2-002** (exit 99 + extension): wrapped main() in try/except for exit 99; output extension now `.json` (was `.yaml.json` which was confusing).

## Diff summary
- `scripts/run_test_matrix.py` NEW: 24-row matrix runner skeleton.
  - Row catalog with id, name, llm_bound flag, journey stages.
  - `_check_reachable(base_url)` probes /health (urllib stdlib only).
  - `_run_row(row, include_llm, base_url)` returns `needs_operator_action` for every row currently — operator wires concrete impls as supervised execution happens.
  - Exit codes 0/10/11/12/99 documented in module docstring.
  - LLM-bound row subset (R03, R05, R07, R09, R11) gated via `--include-llm` flag.
- Follow-up Issue #696 (I-cd-034-followup) filed for operator execution.

Same operator-supervised shape as I-cd-016a → I-cd-016b (smoke harness + operator-run pair).

Output schema:
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
