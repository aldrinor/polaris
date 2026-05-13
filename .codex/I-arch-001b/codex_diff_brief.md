HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-arch-001b DIFF REVIEW iter 1

Brief APPROVE iter 5 (zero P0/P1; 3 P2 nudges noted as follow-up quality work).
Canonical diff SHA256: `4f5668f2bb27d04108553b87147fd9c7349559b8a3915a1a4a942d885b9976e0`.
Patch: `.codex/I-arch-001b/codex_diff.patch` (1386 lines, 1 commit).

## Files

```
src/polaris_graph/v30_contract_synthesizer.py        NEW  164 LOC
src/polaris_v6/queue/actors.py                       MOD  +37 / 0
scripts/run_honest_sweep_r3.py                       MOD  +8 / 0
tests/polaris_graph/test_v30_contract_synthesizer.py NEW  135 LOC (35 tests)
tests/fixtures/v30_contracts/{8}.json                NEW  ~109 LOC each (8 files, ~870 total)

12 files changed, 1218 insertions(+)
```

## Brief iter-5 APPROVE'd criteria → implementation

| Criterion | Implementation |
|---|---|
| `build_v30_contract(v6_template, query_slug, question)` | `v30_contract_synthesizer.py:95-159` |
| schema_version="v30.1" + required_entities + rendering_slots (dict) | `v30_contract_synthesizer.py:130-153` |
| Concrete T1 URL rotation (entity[i] = T1[i % len(T1)]) | `_concrete_url_for_entity` lines 64-82 |
| Stable anchor `<template>:<frame>:<slug[:40]>:<sha256_8>` | `_anchor_for` lines 53-62 |
| Empty-T1 fallback `https://www.canada.ca/en/research.html` | line 81 |
| actors.py loads `polaris_v6.templates.registry.load_template`, logs on failure (FileNotFoundError + generic) | `actors.py:96-122` |
| pipeline-A merges `q["v30_contract_patch"]` after `load_scope_template`, before `compile_frame`/`load_report_contract_for_slug` | `run_honest_sweep_r3.py:1390-1396` |
| 8 golden fixtures | `tests/fixtures/v30_contracts/{ai_sovereignty,canada_us,climate,clinical,defense,housing,trade,workforce}.json` |
| 35 tests | parametrized golden match (8) + round-trip (8) + compile_frame (8) + M-56 fetchability (8) + anchor stability (1) + rotation (1) + empty-T1 (1) |

## Smoke evidence

- `pytest tests/polaris_graph/test_v30_contract_synthesizer.py`: **35/35 pass in 2.15s**
- Full suite `pytest tests/polaris_v6/ tests/v6/ tests/polaris_graph/`: **1988 passed, zero new regressions**
- Pre-existing `test_demo_smoke.py::test_main_returns_0_when_app_healthy` failed in full-suite ordering ONLY; passes in isolation pre AND post my changes (test pollution, not I-arch-001b regression)

## Direct questions

1. Does the diff match the APPROVED brief iter-5 scope (concrete T1 URL rotation + anchor + actors+pipeline-A wiring)?
2. Synthesizer module shape (164 LOC, including `_TYPE_FOR_TEMPLATE` / `_REQUIRED_FIELDS_FOR_TEMPLATE` per-template defaults + section grouping helper) — APPROVE'd?
3. M-56 fetchability test pattern (urlparse scheme + netloc on every binding) — APPROVE'd?
4. actors.py double-except (FileNotFoundError + generic Exception with exc_info=True) — APPROVE'd?
5. pipeline-A guard `if q.get("v6_mode") and q.get("v30_contract_patch") and isinstance(_template, dict)` — APPROVE'd as the non-v6 byte-identical path?
6. Any P0/P1?

## LOC discussion

1218 insertions. Of that:
- 870 = 8 fixture JSONs × ~109 lines (pure data, not source)
- 348 = source + tests (synthesizer 164 + tests 135 + wiring 45)

Fixture JSONs exist solely as regression anchors — synthesizer drift is caught at PR review time via diff against fixture. They are NOT logic; they are deterministic output captured for regression. Splitting them into a separate PR would lose the link between synthesizer change and fixture update.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
convergence_call: continue | accept_remaining
remaining_blockers: [...]
```
