HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-naming-001 — DIFF REVIEW (execution of APPROVE'd plan)

GH#434. Branch `bot/I-naming-001-bpei-rename-plus-audit`. Plan iter 3 APPROVE iter 3 with `accept_remaining`, 0 blockers. This commit executes that plan.

## Commit summary

```
38 files changed, 10389 insertions(+), 57 deletions(-)
- rename: src/polaris_v6/bpei/ambiguity_detector.py → src/polaris_v6/ambiguity_detector/ambiguity_detector.py (100% similarity)
- delete: src/polaris_v6/bpei/__init__.py
- add:    src/polaris_v6/ambiguity_detector/__init__.py (re-export shim + commemorative footnote)
- add:    scripts/i_naming_001_migrate.py (migration utility, preserved for audit)
- add:    .codex/I-naming-001/codex_plan_*.{md,txt} (review trail)
```

## What changed (per plan stages)

### Stage 1 — directory rename
- `git mv src/polaris_v6/bpei → src/polaris_v6/ambiguity_detector`
- New `__init__.py` re-exports `AmbiguityCluster, AmbiguityResult, CandidateSnippet, detect_ambiguity` (Option B). Preserves commemorative footnote pointing at `memory/bpei_phantom_completion_lessons.md`.

### Stage 2 — Python imports + comments
- 2 import paths updated: `src/polaris_v6/api/ambiguity.py:16`, `tests/v6/test_ambiguity_detector.py:10`.
- ~20 comment/docstring phrase updates in `src/polaris_v6/`, `src/polaris_graph/{api,audit_bundle,intake,scope}/`, `tests/{e2e,polaris_graph,v6}/`.

### Stage 3 — frontend (web/)
- 4 user-facing UI page edits: `web/app/{dashboard,generation,intake,retrieval}/page.tsx`.
- `web/lib/api.ts:827` JSDoc comment.
- 4 e2e specs: BPEI as FEATURE-NAME renamed; BPEI as TYPED-IN-SEARCH-BOX probe preserved.

### Stage 4 — docs
- 12 doc files patched (current: carney_delivery_plan_v6_2.md, carney_handover/5min_video_script.md (none — Codex iter 2 noted no hits), v6_substrate_audit, task_acceptance_matrix.yaml, benchmark/scoring_rubric.md, walkthroughs/{1.8,2B.7,2C.6,I-f10-008,5.1}/).
- Historical docs (carney_delivery_plan_v5*, v6_draft, shippable_plan_v{2,3,4}_draft) left as-is.

### Stage 5 — scripts
- `scripts/autoloop/backfill_pre_bootstrap_verdicts.py` lines 70/77/78 updated.
- `scripts/screenshot_walkthrough.js` line 2 updated.

### What's NOT touched (preserved per plan)
- `memory/bpei_phantom_completion_lessons.md` filename (user-level memory, commemorative).
- `tests/v6/test_api_ambiguity.py:34` function name `test_check_ambiguity_bpei_pattern` (commemorates the test pattern itself).
- `tests/v6/test_run_benchmark_script.py:80` literal probe input `"What is BPEI?"`.
- `docs/walkthroughs/5.1/full_corpus_test_inputs.md:20` literal probe Query.
- 4 e2e specs: `.fill(...BPEI...)` / `.type(...BPEI...)` probe lines.

## Sanity tests passed

```
$ PYTHONPATH=src python -c "from polaris_v6.ambiguity_detector import CandidateSnippet, AmbiguityCluster, AmbiguityResult, detect_ambiguity"
ok (re-export works)

$ PYTHONPATH=src python -c "from polaris_v6.ambiguity_detector.ambiguity_detector import detect_ambiguity"
ok (direct path works)

$ PYTHONPATH=src python -c "from polaris_v6.api.ambiguity import router"
ok (api route imports clean)

$ PYTHONPATH=src python -m pytest --collect-only tests/v6/test_ambiguity_detector.py tests/v6/test_api_ambiguity.py -q
9 tests collected in 0.33s

$ grep -rln "BPEI ambiguity\|BPEI spine\|BPEI chain\|BPEI guard\|BPEI front\|BPEI retrieval\|BPEI generator\|polaris_v6.bpei\|src/polaris_v6/bpei" src tests scripts web docs | grep -v __pycache__ | grep -v "i_naming_001_migrate.py"
(only web/.next/ stale build artifacts remain; regenerated on next `npm run build`)
```

## Broader naming-audit follow-ups (per Codex iter 1 adjudication, deferred)

These are OUT-OF-SCOPE for this PR. Will create follow-up GH issues:
- `src/polaris_graph/audit_ir/v30_runner.py` → I-naming-002 (P3)
- `src/polaris_graph/v30_sweep_integration.py` → I-naming-003 (P3)
- `src/polaris_graph/generator2/` → I-naming-004 (P2)
- `src/polaris_graph/retrieval2/` → I-naming-005 (P2)
- `src/polaris_graph/synthesis/{peptide_flow,disulfide_bridge,covalent_binder,ionic_rebalancer}.py` → I-naming-006..009 (P2, chemistry metaphors)
- `src/polaris_graph/graph_v4.py` → I-naming-010 (P3)

## Questions for Codex iter 1 diff review

1. Any P0/P1 in the 38-file diff?
2. Re-export shim correctness — `from .ambiguity_detector import (AmbiguityCluster, AmbiguityResult, CandidateSnippet, detect_ambiguity)` — does it cover the actual public API exhaustively?
3. Are the preserved-verbatim test-input literals correctly distinguished from feature-name refs?
4. Anything missed that grep didn't catch (e.g. dynamic imports, string-template construction, asset paths)?
5. Should I also create the 9 follow-up GH issues in this PR, or as separate work?

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
followup_issue_creation: in_this_pr | separate_work
convergence_call: continue | accept_remaining
remaining_blockers_for_merge: [...]
```
