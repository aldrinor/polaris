# Codex round 1 — M-INT-6 v1

## Scope
Wires M-D2 phase b substrate (LLMAugmentedInductor +
KeywordInductor + InductorVerdict) into the sweep
telemetry path, with operator-review JSONL queue surfacing
abstain verdicts for human review.

## Acceptance bar
1. ✅ Imported (LLMAugmentedInductor, LLMAugmentedInductorConfig,
   InductorVerdict, KeywordInductor, MockTemplateAffinityClassifier)
2. ✅ Invoked (`_induce_with_llm` from sweep with defense-in-depth wrap)
3. ✅ Run-log evidence (`[M-INT-6] inductor:` line)
4. ✅ Rollback flag PG_USE_AUTO_INDUCTION=0 disables (default 0)
5. ✅ Abstain → operator_review_queue.jsonl in run_dir
6. ✅ Failure does NOT raise (LAW II)
7. ✅ M-D1 validation set still runs as
   tests/polaris_graph/test_md1_auto_induction_harness.py (66/66)

## v1 caveat
- Production classifier is `MockTemplateAffinityClassifier`
  (deterministic keyword-based). Real OpenRouter classifier
  wiring is Phase F (M-LIVE-2 onward).
- Operator-review queue is append-only JSONL (one row per
  abstain). Real persistent DB-backed queue is Phase F.

## Tests
- 7/7 M-INT-6 tests pass
- 66/66 across M-D1 + M-D2 substrate (test_md1_auto_induction_harness,
  test_md2_keyword_inductor, test_md2_llm_inductor)

Branch: PL-honest-rebuild-phase-1
Commit: 8baface

## Verdict
GREEN | PARTIAL | BLOCKED
