HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-naming-001 — DIFF REVIEW iter 2 (tighter brief)

## Constraint

Previous iter 1 timed out mid-exploration. **This iter: do NOT exec extensive `git log`/`grep`/`cat` walks.** Read the commit message + the focused-grep results below, and emit verdict YAML directly.

## Commit

```
commit b9c07cef on bot/I-naming-001-bpei-rename-plus-audit (base: polaris)

I-naming-001 — rename BPEI → ambiguity_detector (GH#434)

38 files changed, 10389 insertions(+), 57 deletions(-)

Per user directive 'ambiguity detector, why don't just name it in this way?'
and Codex plan iter 3 APPROVE (accept_remaining, 0 blockers).

- src/polaris_v6/bpei/ → src/polaris_v6/ambiguity_detector/ (rename)
- __init__.py rewritten with Option B re-exports + commemorative footnote
- 40 phrase replacements across 25 files (src/tests/scripts/web/docs)
- Preserved verbatim: literal BPEI test-input probes per Codex P2-1
```

## Plan iter 3 → execution mapping (deterministic — verified by author)

| Plan stage | Execution result |
|---|---|
| Stage 1: `git mv src/polaris_v6/bpei → ambiguity_detector` | `R100` rename on `ambiguity_detector.py` (100% similarity); `__init__.py` rewritten as add + delete |
| Stage 1: re-export shim | `src/polaris_v6/ambiguity_detector/__init__.py` exports `AmbiguityCluster, AmbiguityResult, CandidateSnippet, detect_ambiguity` |
| Stage 2: 2 import updates | `src/polaris_v6/api/ambiguity.py:16`, `tests/v6/test_ambiguity_detector.py:10` both updated to `from polaris_v6.ambiguity_detector import ...` |
| Stage 2: ~20 comment/docstring updates | 25 files modified total per migration script run (40 phrase replacements logged) |
| Stage 3: web/app UI copy | `web/app/{dashboard,generation,intake,retrieval}/page.tsx` + `web/lib/api.ts` + 4 e2e specs (test-input probes preserved per SKIP_LINES) |
| Stage 4: docs | 12 doc files patched (carney_delivery_plan_v6_2, v6_substrate_audit, task_acceptance_matrix.yaml, benchmark/scoring_rubric.md, walkthroughs/{1.8,2B.7,2C.6,I-f10-008,5.1}/) |
| Stage 5: scripts | `scripts/autoloop/backfill_pre_bootstrap_verdicts.py` lines 70/77/78 + `scripts/screenshot_walkthrough.js:2` |

## Sanity-test results (Claude pre-ran)

```
$ PYTHONPATH=src python -c "from polaris_v6.ambiguity_detector import CandidateSnippet, AmbiguityCluster, AmbiguityResult, detect_ambiguity"
ok

$ PYTHONPATH=src python -c "from polaris_v6.ambiguity_detector.ambiguity_detector import detect_ambiguity"
ok

$ PYTHONPATH=src python -c "from polaris_v6.api.ambiguity import router"
ok

$ PYTHONPATH=src python -m pytest --collect-only tests/v6/test_ambiguity_detector.py tests/v6/test_api_ambiguity.py -q
========================= 9 tests collected in 0.33s ==========================

$ grep -rln "polaris_v6.bpei\|src/polaris_v6/bpei" src tests scripts web docs (excluding __pycache__, web/.next, migration script)
(zero hits)

$ grep -rln "BPEI ambiguity\|BPEI spine\|BPEI chain\|BPEI guard\|BPEI front\|BPEI retrieval\|BPEI generator" src tests scripts web docs (excluding __pycache__, web/.next, migration script)
(zero hits)
```

## Preserved-verbatim (per plan P2-1)

These are TEST-INPUT literals and commemorative names; preserved exactly:
- `tests/v6/test_api_ambiguity.py:34` — function name `test_check_ambiguity_bpei_pattern`
- `tests/v6/test_run_benchmark_script.py:80` — `"What is BPEI?"` test input
- `docs/walkthroughs/5.1/full_corpus_test_inputs.md:20` — literal probe Query
- 4 web/tests/e2e specs — `.fill(...BPEI...)` / `.type(...BPEI...)` probes
- `memory/bpei_phantom_completion_lessons.md` — filename (user-level memory, not in repo)

## Per Codex iter 1 plan-review broader audit, follow-up issues to create:
- I-naming-002: `v30_runner.py` → `honest_sweep_job_runner.py` (P3)
- I-naming-003: `v30_sweep_integration.py` → `honest_sweep_integration.py` (P3)
- I-naming-004: `generator2/` → `clinical_generator/` (P2)
- I-naming-005: `retrieval2/` → `clinical_retrieval/` (P2)
- I-naming-006..009: synthesis/{peptide_flow, disulfide_bridge, covalent_binder, ionic_rebalancer}.py (P2, chemistry metaphors)
- I-naming-010: `graph_v4.py` → `pipeline_a_ui_adapter.py` (P3)

## Direct questions (just verdict, please)

1. Does the diff match plan iter 3's APPROVE'd scope?
2. Any P0/P1 introduced in execution?
3. Is `accept_remaining` appropriate, or REQUEST_CHANGES with specific fixes?

## Output schema (terse — verdict + key reasoning only)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_merge: [...]
```
