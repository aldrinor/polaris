# Execution DAG gate — DUAL-APPROVED (Codex + Fable 5), 2026-07-05

**Codex: APPROVE** (`exec_dag_gate_codex_verdict.txt`) — no conflicts missed, no dependencies missed; one NEEDS-CODE-CHECK on 2b wiring files.
**Fable 5: APPROVE** (task a658d8148fb489842) — verified every load-bearing cite in the real repo; two file-map corrections that REINFORCE the serialization + one extra parallel split.

## Corrected batching (the approved build order)
- **Batch 1 — PARALLEL** (file-disjoint, ≤4 in flight): `1a`, `1b`, `1c`, `2b-module`, `2c-module`, `2e` (with 2e's marker spec pinned first). RUNNING now: 1a, 1b, 1c.
- **Batch 2 — after 1a AND 1b:** `2a` FIRST (bigger blast radius than first mapped — also edits `verified_compose.py` [`compose_cross_source_analytical_units` call ~2228-2236] + `scripts/run_honest_sweep_r3.py` [depth fail-open tail ~15964-16012]); THEN `{2d ∥ 2b-wiring}` in parallel (2d=multi_section_generator.py + expert_facet_planner.py:44; 2b-wiring=verified_compose.py + run_honest_sweep_r3.py:3245 `_basket_corroboration_block` — disjoint); THEN `2c-wiring` (after 2d — shares the multi_section render seam 4924-5030).
- **Batch 3:** `1d` AFTER ALL of Batch 2 (its canaries test telemetry 2a creates; the slate must include 2b `PG_MIN_CITE_SET` + 2c `PG_PRESENTATION_TABLES`), then Wave 3 activate+archive.

## File-map corrections (Fable, verified against repo — cosmetic path fixes to REAL_PLAN)
- `finding_dedup.py` and `claim_graph.py` are under `src/polaris_graph/synthesis/`, NOT `generator/` (REAL_PLAN what_changes lists them under generator/ — cosmetic). Build agents locate the real path via grep.
- `_normalized_key_numeric` = `synthesis/claim_graph.py:229`; keystone flag `synthesis/credibility_pass.py:65`; `_entails`/`entails_directional` = `consolidation_nli.py:334/:346` (1b consumes, need not fork).

## Rule (unchanged, dual-approved)
Two units NEVER edit the same file concurrently (worktree isolation does not help — defers the merge conflict). Shared-file units serialize; commits to shared files serialized. Each unit's diff is separately dual-gated (Codex + Fable) before commit.
