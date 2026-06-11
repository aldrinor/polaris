# Codex DIFF review — I-perm-004 (#1198) SLICE 4: #1180 widening-prompt bakeoff substrate

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. Reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on remaining-non-P0/P1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## What this slice does (and explicitly does NOT)
Builds the OFFLINE substrate for the #1180 entailment-judge widening bakeoff: a §-1.1 labeled set, 3 candidate prompts, a pure scorer/winner-picker, an env-selectable prompt, and a spend-gated bakeoff script. It does NOT pick a winner or change judge behavior by default — the empirical pick needs the real judge LLM (spend) and runs with the program's operator-authorized step. Review the substrate's correctness + the byte-identical-default guarantee, NOT a (deferred) empirical result.

## Safety properties to verify (P0 class)
1. **Default byte-identical.** `entailment_judge._select_entailment_prompt()` returns `_ENTAILMENT_PROMPT` (the unchanged canonical prompt) when `PG_ENTAILMENT_PROMPT_VARIANT` is unset / "baseline" / unknown. `judge()` now calls `_select_entailment_prompt().format(...)` instead of the bare constant. Confirm the default path is identical to before (the constant is unchanged; the indirection returns it).
2. **Fail-safe winner pick.** `pick_winner` returns "baseline" if NO candidate clears `entailed_precision >= 0.95` — i.e. a widening prompt that starts false-dropping legitimate support is NEVER selected. Confirm the precision floor genuinely gates (a candidate with great NEUTRAL recall but poor entailed precision loses to baseline).
3. **Candidates are drop-in.** Each variant keeps `{span}`/`{sentence}` and the STRICT-JSON `{"verdict": ...}` contract; `validate_variants()` enforces it. Confirm a malformed variant would be caught.
4. **No spend by default.** The bakeoff script does nothing LLM without `--run` + `OPENROUTER_API_KEY`. Confirm `run_variant` (the only LLM path) is unreachable without `--run`.

## The §-1.1 labeled set (the ground truth — review its correctness)
Each row is a real (span, sentence, gold) entailment judgment. The FIX TARGET is `F02_drb76_strain_to_class` (gold=NEUTRAL: span warns about S. boulardii specifically in at-risk populations; sentence widens to "routine probiotic use" generally). The set ALSO carries strain/scope-PRESERVING ENTAILED positives + paraphrase/numeric positives + a CONTRADICTED anchor so the bakeoff cannot win by blanket-NEUTRAL (which would tank entailed_precision). Challenge any row whose gold label you believe is WRONG under §-1.1 (a mislabeled row would corrupt the empirical pick) — give the row id + correct label.

## Claims ledger
| # | Claim | Where | Status |
|---|---|---|---|
| C1 | default prompt byte-identical | `_select_entailment_prompt` returns `_ENTAILMENT_PROMPT` on baseline/unknown; `_ENTAILMENT_PROMPT` text unchanged | claims-true |
| C2 | winner pick fail-safe to baseline | `pick_winner` filters by precision floor, returns "baseline" if empty | claims-true |
| C3 | candidates drop-in | `validate_variants` + `.format(span,sentence)` | claims-true |
| C4 | no spend without --run | `main` returns before `run_variant` unless `args.run` | claims-true |
| C5 | scorer correct | `score_predictions` recall/precision math | claims-true |

## Files (full diff: `.codex/I-perm-004/slice4_codex_diff.patch`)
- `src/polaris_graph/llm/entailment_judge.py` (+20): `_select_entailment_prompt`; judge uses it.
- `src/polaris_graph/llm/widening_prompt_candidates.py` (new): 3 variants + scorer + picker.
- `scripts/dr_benchmark/widening_prompt_bakeoff.py` (new): spend-gated harness.
- `tests/fixtures/widening_labeled_set.json` (new): the labeled set.
- `tests/polaris_graph/test_widening_prompt_bakeoff_iperm004.py` (new): 8 offline tests.

## Test evidence: 8 bakeoff-substrate + 49 entailment-judge (byte-identical default) green.

Review the diff. Confirm C1 (default byte-identical) + C2 (fail-safe pick). Challenge any mislabeled §-1.1 ground-truth row.
