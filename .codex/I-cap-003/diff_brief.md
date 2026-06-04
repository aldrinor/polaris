HARD ITERATION CAP: 5 per document. This is iter 1 of 5. Front-load ALL findings; reserve P0/P1 for real execution risks; APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Output schema (return EXACTLY this, no prose verdict):
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

---

# DIFF gate — I-cap-003 (#1066): NLI benchmark annotator -> LLM entailment judge

DIFF gate against the brief (`.codex/I-cap-003/brief.md`). Patch: `.codex/I-cap-003/codex_diff.patch`
(branch `bot/I-cap-003-nli-llm-judge` on `bot/I-cap-002-tierA-caps`). This fixes the operator-flagged
`nli_status:"unavailable"` incomplete-function bug by rewiring the benchmark NLI scoring backend from
flan-t5/minicheck to the existing frontier LLM entailment judge.

## The diff (5 files)
1. `nli_benchmark_annotator.py`: `annotate_nli_entailment(pairs)` rewritten — empty-pairs fast path
   (no key); missing `OPENROUTER_API_KEY` -> `NliUnavailableError`; `_get_judge()` (family-collision
   RuntimeError PROPAGATES, not masked); **SYNC** `judge.judge(sentence, span)` loop (NO `asyncio.to_thread`)
   so `_RUN_COST_CTX` accumulates + `BudgetExceededError` propagates; disputed = NEUTRAL u CONTRADICTED;
   verdict-count result schema (entailed/neutral/contradicted/disputed_count/disputed[]; model=judge._model).
   No import of `nli_verifier.load_nli_model` -> no torch/minicheck.
2. `run_honest_sweep_r3.py` NLI block: `annotate_nli_entailment(_nli_pairs)` (no threshold); added
   `except BudgetExceededError: raise` BEFORE the broad `except Exception`; log uses `entailed=`/`disputed=`
   (no `min_prob`); removed `PG_NLI_DISPUTE_THRESHOLD`.
3. `run_gate_b.py`: removed `setdefault("PG_NLI_MODEL","flan-t5-large")` (kept `PG_NLI_IN_BENCHMARK=1`); no
   `PG_ENTAILMENT_MODEL` override (pathB preflight requires `PG_ENTAILMENT_MODEL==PG_EVALUATOR_MODEL`; default
   gemma satisfies it).
4. `test_nli_benchmark_annotator.py`: rewritten to mock `_get_judge().judge` (verdict counts; no-key ->
   unavailable; BudgetExceededError propagates; empty-pairs ok). Old MiniCheck/FaithLens/prob mocks gone.
5. `requirements.txt`: minicheck marked legacy/Pipeline-B-only.

## Red-team checklist — confirm
- **Bug fixed:** normal operation (key present) -> `nli_status:"ok"` with real ENTAILED/NEUTRAL/CONTRADICTED
  verdicts; `unavailable` ONLY on a genuine missing-key config error. No torch/minicheck on the NLI path.
- **Budget integrity (the iter-1 P1):** judge called synchronously (same context) so `_add_run_cost`
  accumulates and `BudgetExceededError` (re-raised inside `judge.judge`) propagates out of the annotator AND
  out of the run_one_query block (the new `except BudgetExceededError: raise` precedes the broad catch).
  Any path where judge spend could exceed `PG_MAX_COST_PER_RUN` silently?
- **Family error not masked:** a `_get_judge()` family-segregation RuntimeError is NOT caught as
  `unavailable` (only the explicit pre-construction key check raises `NliUnavailableError`).
- **Advisory/faithfulness:** still only annotates `manifest['nli_verification']`; never gates; scores
  span⊨sentence on delivered sentences; flags, never injects.
- **Schema change:** the caller's log + eligible/skipped augmentation use the new fields; no `min_prob`
  KeyError remains anywhere.
- **Preflight:** no `PG_ENTAILMENT_MODEL` override that would break `PG_ENTAILMENT_MODEL==PG_EVALUATOR_MODEL`.

## Smoke evidence (offline)
- `pytest tests/polaris_graph/test_nli_benchmark_annotator.py` -> 8 passed (verdict mapping; no-key->
  unavailable; BudgetExceededError propagates; empty-pairs ok).
- import smoke: `nli_benchmark_annotator` pulls neither `torch` nor `minicheck`.
- `pytest tests/dr_benchmark/test_benchmark_stack_activation_meta007.py test_run_gate_b_cli.py` -> 21 passed.
- `py_compile` + `ast.parse` on the 3 touched src/scripts files -> OK.
- (A real OpenRouter entailment call is the VM smoke after this gate APPROVEs — tiny spend.)

## Acceptance
Zero P0/P1. The fix removes the fragile dep, restores the second validator at frontier quality, is
budget-correct + advisory + family-segregated. Residual model-choice/tuning concerns are P2.
