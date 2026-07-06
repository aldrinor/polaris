# Execution DAG gate — Wave-unit parallel/serial decomposition for the I-deepfix-001 build

You are reviewing the EXECUTION PLAN (not code): how the 9 build units of REAL_PLAN_2026.md should be ordered — which run in PARALLEL, which must be SERIAL — so we get maximum efficiency WITHOUT file-edit conflicts or broken dependencies. Faithfulness is never at stake here (every unit is separately dual-gated + behind default-OFF flags); this gate is purely about the build DAG being CORRECT and SAFE.

## The 9 units + the files each edits (from REAL_PLAN_2026.md what_changes)
- **1a** group-writer contract + bounded repair + labeled fallback: `abstractive_writer.py`, `verified_compose.py`, `multi_section_generator.py`.
- **1b** keystone basket regroup + `PG_FINDING_DEDUP_NLI` strict bidirectional: `finding_dedup.py`, `credibility_pass.py`.
- **1c** offline DeepTRACE self-scorer (triage): NEW `scripts/deeptrace_self_score.py` (standalone; imports the NLI engine read-only).
- **1d** slate + fail-loud shallow-report canaries: `run_honest_sweep_r3.py`, `scripts/dr_benchmark/run_gate_b.py`.
- **2a** plan-driven cross-source pairing INTO the body: `cross_source_synthesis.py`, `depth_synthesis.py`, `multi_section_generator.py`, `claim_graph.py` (numeric match-key).
- **2b** citation minimizer + weight channel: NEW `citation_set_minimizer.py` (module) + a wiring caller (likely `verified_compose.py` and/or render).
- **2c** presentation tables: NEW `presentation_tables.py` (module) + a wiring caller (likely `multi_section_generator.py` render).
- **2d** two-sided debate pass: `multi_section_generator.py`, `expert_facet_planner.py`.
- **2e** rendered-report acceptance harness: NEW standalone script (reads report.md; edits nothing in src).

## Dependency edges (logical)
- 2a needs 1a (the group-writer body path it plugs into) AND 1b (multi-origin baskets must exist to cross-compare).
- 2d needs 1a (composition body path) + the wideners.
- 1d references the flags 1a/1b/wideners create (build the canaries after those flags exist; activation/slate-ON is Wave 3, not 1d).
- 2b/2c MODULES are standalone (new files); their WIRING callers touch shared files.

## Proposed batching (the thing to approve or correct)
- **Batch 1 — PARALLEL now (disjoint files, ≤4 agents in flight):** 1a, 1b, 1c, 2c-module. (2e joins when a slot frees. 2b-module also parallel-safe.)
- **Batch 2 — SERIAL after 1a lands (shared `multi_section_generator.py` + deps):** 2a (also after 1b) → 2d. The 2b/2c WIRING callers land here too (they touch verified_compose/multi_section, so after 1a).
- **Batch 3:** 1d (canaries once flags exist), then Wave 3 (activate + archive).
- Rule applied: two units NEVER edit the same file concurrently (worktree isolation does NOT help — it only defers the merge conflict); shared-file units serialize; a unit builds only after its dependencies. Each unit is still separately dual-gated (Codex+Fable) before commit; commits to shared files are serialized.

## Your verdict (return the schema)
Is this DAG CORRECT and SAFE? Specifically: (1) any file-edit CONFLICT I mis-classified as parallel? (2) any DEPENDENCY edge I missed (a unit that must precede another)? (3) any unit I put SERIAL that is actually safe to parallelize (efficiency left on the table)? (4) is putting the 2b/2c wiring in Batch 2 correct, or can the modules+wiring both parallelize? (5) any risk from building 1a and 1b in parallel (they touch disjoint files but 2a depends on both)?
Output:
```
verdict: APPROVE | REVISE
conflicts_missed: [...]
dependencies_missed: [...]
over_serialized: [...]
corrected_batching: <the batching you would run, if different>
notes: <short>
```
