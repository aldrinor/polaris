# Codex review — I-cd-706 SSE sub-task event instrumentation

HARD ITERATION CAP: 5. iter 1. Front-load ALL findings. P0/P1 for real execution risks only. APPROVE iff zero P0 + zero P1. Per merge protocol (.codex/I-cd-567/DECISION.md) final line includes MERGE AUTHORIZED if mergeable. Touches scripts/run_honest_sweep_r3.py (live pipeline driver) + tests/ — NOT operator-only exclusion list.

Canonical-diff-sha256: `a6bfe2f81c5ecc429c0d6e8b05d8fca519b31250329c1ffcb1825352a029ec47`. 2 files / +78.

## What this implements (your scope-consult plan, .codex/I-cd-706/scope_consult_output.txt)
4 emits threaded into the live driver, all guarded by `if q.get("v6_mode") and q.get("external_run_id")` (matching the existing scope emit at line ~1246), emit_event non-raising:
- corpus_adequacy.completed {pool_size: len(retrieval.evidence_rows), tier_counts: dict(dist.tier_counts)} after the adequacy gate.
- evidence.id_assigned {id, url} over the FINAL evidence_for_gen set (after upload/contract prepends, before the generator call); dict-or-object guarded; only emits when id is truthy.
- strict_verify.section_completed {section, local, global} + generator.section_completed {section, verified, dropped} over ALL multi.sections (incl dropped).

Tests: 4 producer-payload→translate contract tests (corpus/evidence/strict/generator) asserting my emit keys populate the v6 payload. 30 run_events tests pass; driver py_compile OK.

## Review focus (live-pipeline safety)
1. Did I place the 4 emits at the boundaries you specified, with payload keys matching each translator transform_fn input? (corpus: pool_size/tier_counts; evidence: id/url; strict: section/local/global; generator: section/verified/dropped.)
2. Any way these emits change existing terminal-event sequencing or pipeline control flow? (All guarded + non-raising + no run_store touch.)
3. evidence.id_assigned throttling — emitting over the final evidence_for_gen only (not retrieval loops). Acceptable per your maxlen-10k/batch-100 analysis?
4. The dict-or-object guard on evidence rows — correct given rows are dicts (ev["evidence_id"]) but defensively handles objects?
5. Any NOVEL P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
remaining_blockers_for_execution: [...]
```
