# Codex diff — I-cd-033 (#633) — primary-source-over-derivative rule

Canonical-diff-sha256: `f225225cc2ae007c457cdc6065acd2d1bf8b6bc8f537ef9f935c16763707b43f`. 2 files / +85 LOC.

## Diff summary
- `src/polaris_graph/generator/multi_section_generator.py`: append PRIMARY-SOURCE-OVER-DERIVATIVE rule block to the multi-section system prompt. Includes the concrete I-bug-117 pattern (PWBM 2025 vs Goldman Sachs 2023) + tier signal (T1/T3 primary vs T6 derivative).
- `tests/polaris_graph/test_primary_source_over_derivative.py` NEW: 3 tests (rule present, concrete pattern named, tier signal references T1/T3/T6). 3/3 pass.

## Acceptance traceability

Parent #586 acceptance: "A test in tests/polaris_graph/ that catches source-attribution mismatch for the workforce-exposure claim, OR a documented reason a generic test is not feasible."

The 3 prompt-presence tests guard the LLM-facing rule — the regression target. Live generator output verification needs an LLM call against the workforce corpus; that's the dress-rehearsal (Seq 42 / I-D-01) acceptance, not this issue.

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
