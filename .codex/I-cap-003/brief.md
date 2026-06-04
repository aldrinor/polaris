HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

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

# Brief — I-cap-003 (#1066): NLI benchmark annotator → LLM entailment judge (fix nli_status:unavailable)

## CHANGELOG vs iter 1 (your 4 P1s + 3 P2s — all addressed; verified against the cited lines)
- **P1.1 (threaded budget) FIXED:** NO `asyncio.to_thread`. The judge is called SYNCHRONOUSLY in the async
  annotator (it runs post-generation, the last step — blocking the loop for N sequential entailment calls is
  fine). This keeps `_RUN_COST_CTX` (a ContextVar, openrouter_client.py:88) in the SAME context, so
  `_add_run_cost` accumulates against `PG_MAX_COST_PER_RUN` and `BudgetExceededError` fires correctly. No
  Semaphore/thread offload.
- **P1.2 (caller swallows BudgetExceededError) FIXED:** the `run_one_query` NLI block adds
  `except BudgetExceededError: raise` BEFORE the broad `except Exception` (run_honest_sweep_r3.py:5167).
  `BudgetExceededError` is already imported at run_honest_sweep_r3.py:62.
- **P1.3 (caller logs min_prob → KeyError) FIXED:** the caller `_log` line (run_honest_sweep_r3.py:5155)
  is updated to the new verdict-count schema (entailed/disputed), removing `min_prob`/`mean_prob`.
- **P1.4 (wrong exception type) FIXED:** `_EntailmentJudge.__init__` raises **RuntimeError** for a missing
  `OPENROUTER_API_KEY` (entailment_judge.py:119-121). The annotator checks `os.getenv("OPENROUTER_API_KEY")`
  presence ITSELF (before `_get_judge()`); empty → `NliUnavailableError`. `_get_judge()` construction
  failures (e.g. family-segregation RuntimeError) are NOT caught as unavailable — they fall to the caller's
  error path, so a family collision is never masked as "unavailable".
- **P2.1 (empty-pairs fast path) KEPT:** `if not pairs: return {nli_status:"ok", sentences_checked:0, …}`
  BEFORE the API-key check / `_get_judge()` — so `annotate_nli_entailment([])` never needs OPENROUTER_API_KEY.
- **P2.2 (Gate-B model invariant) FIXED:** REMOVE the `setdefault("PG_NLI_MODEL","flan-t5-large")` from
  `run_gate_b` (added by #1064; obsolete). Do NOT set a conflicting `PG_ENTAILMENT_MODEL` — pathB_run_gate.py:
  284-288 REQUIRES `PG_ENTAILMENT_MODEL == PG_EVALUATOR_MODEL` (both default `google/gemma-4-31b-it`), else
  `GateError`. The judge's default gemma IS the evaluator model, so the gate invariant holds untouched.
- **P2.3 (tests) FIXED:** rewrite `test_nli_benchmark_annotator.py` to mock `_get_judge().judge` returning
  ENTAILED/NEUTRAL/CONTRADICTED and assert verdict counts (no more `load_nli_model`/MiniCheck mocks, no prob
  fields).

## 0. The bug (operator: "not acceptable to still have half-ass bug / incomplete functions")
The Tier-B NLI second-validator (#1064) scores via `nli_verifier.load_nli_model()` → the **minicheck**
library wrapping **flan-t5-large**. On the benchmark VM (and anywhere minicheck is absent),
`load_nli_model()` returns None → the annotator records `nli_status:"unavailable"`. A beat-both run ships
without its second faithfulness validator. Two root problems:
1. `minicheck` is NOT on PyPI; only `git+https://github.com/Liyan06/MiniCheck.git` (requirements.txt:90) —
   fragile GitHub dep + heavy torch on a CPU box.
2. flan-t5-large is an **old/weak encoder (F1 62.1 per the codebase's own comment)** — exactly the
   old-encoder class the operator rejected; the standard is **frontier open-weight LLMs**.

## 1. The fix (use the EXISTING frontier LLM entailment judge)
`src/polaris_graph/llm/entailment_judge.py` already provides a frontier, OpenRouter-based entailment judge:
- `_get_judge() -> _EntailmentJudge` (singleton); `judge(sentence, span) -> (verdict, reason)` where
  `verdict ∈ {ENTAILED, NEUTRAL, CONTRADICTED}`.
- Default model `PG_ENTAILMENT_MODEL=google/gemma-4-31b-it` — **open-weight**, **family-segregated** from the
  generator (`check_family_segregation` raises if same family); the judge is the two-family evaluator.
- **Budget-integrated:** each call books cost via openrouter_client's `_add_run_cost` / `check_run_budget`,
  and RE-RAISES `BudgetExceededError` before its broad fail-open. So judge spend counts against
  `PG_MAX_COST_PER_RUN`.
- Fail-open on transient API/parse error → `("ENTAILED", "judge_error: ...")`.
- Already used by `strict_verify` (`_get_judge().judge(sentence_clean, combined_span)`), so it is proven.

Rewire `nli_benchmark_annotator.annotate_nli_entailment` to score each pair via this LLM judge instead of
flan-t5/minicheck. This removes torch/minicheck from the NLI path entirely; works on the CPU VM via
OpenRouter; frontier quality; operator-aligned.

## 2. Design (the diff)
### 2a. `src/polaris_graph/retrieval/nli_benchmark_annotator.py`
- KEEP `build_nli_pairs` unchanged (token-clean + multi-span concat + `direct_quote`/`statement` field order).
- REWRITE `annotate_nli_entailment(pairs)` (drop the unused `threshold` kwarg — verdicts, not probs):
  ```python
  if not pairs:                                    # P2.1 fast path — no API key needed
      return {"nli_status":"ok","judge":"llm_entailment","sentences_checked":0,
              "entailed_count":0,"neutral_count":0,"contradicted_count":0,
              "disputed_count":0,"disputed":[],"advisory":True}
  import os
  if not os.environ.get("OPENROUTER_API_KEY","").strip():   # P1.4 — fail-loud on genuine config error
      raise NliUnavailableError("OPENROUTER_API_KEY missing — NLI entailment judge cannot run")
  from src.polaris_graph.llm.entailment_judge import _get_judge
  judge = _get_judge()                             # family-segregation RuntimeError PROPAGATES (not masked)
  entailed=neutral=contradicted=0; disputed=[]
  for p in pairs:
      verdict, reason = judge.judge(p["sentence"], p["span"])   # SYNC — same ctx -> budget accumulates (P1.1)
      if verdict == "ENTAILED": entailed += 1
      elif verdict == "CONTRADICTED": contradicted += 1; disputed.append({...verdict,reason...})
      else: neutral += 1; disputed.append({...verdict,reason...})   # NEUTRAL also disputed
  return {"nli_status":"ok","judge":"llm_entailment","model":judge._model,
          "sentences_checked":len(pairs),"entailed_count":entailed,"neutral_count":neutral,
          "contradicted_count":contradicted,"disputed_count":len(disputed),"disputed":disputed,
          "advisory":True}
  ```
  - **No `asyncio.to_thread`** — the judge call is synchronous so `_RUN_COST_CTX` accumulates and
    `BudgetExceededError` (re-raised inside `judge.judge`) propagates out of `annotate_nli_entailment`. (P1.1)
  - `disputed` entry shape: `{section, evidence_id, verdict, reason, sentence}`.
  - No import of `nli_verifier.load_nli_model` anywhere — torch/minicheck/flan-t5 gone from the NLI path.

### 2b. `scripts/run_honest_sweep_r3.py` (the existing NLI block in `run_one_query`)
- Change the success `_log` line (currently `min_prob=_nli_result['min_prob']`, L5155) to:
  `entailed={_nli_result['entailed_count']} disputed={_nli_result['disputed_count']} (advisory)`. (P1.3)
- Add, BEFORE the broad `except Exception as _nli_exc` (L5167):
  ```python
  except BudgetExceededError:   # P1.2 — a cap breach must abort the run, not be masked as nli_status:error
      raise
  ```
  (`BudgetExceededError` already imported at run_honest_sweep_r3.py:62; `NliUnavailableError` except stays.)
- Drop the `threshold=_nli_threshold` arg + the `PG_NLI_DISPUTE_THRESHOLD` read (no longer used).

### 2c. `scripts/dr_benchmark/run_gate_b.py`
- KEEP `setdefault("PG_NLI_IN_BENCHMARK","1")`. REMOVE `setdefault("PG_NLI_MODEL","flan-t5-large")`
  (obsolete; the LLM judge uses `PG_ENTAILMENT_MODEL`). Do NOT add a `PG_ENTAILMENT_MODEL` override —
  pathB_run_gate.py:284-288 requires `PG_ENTAILMENT_MODEL == PG_EVALUATOR_MODEL` (both default gemma); the
  default already satisfies it. (P2.2)

### 2d. `requirements.txt`
- Update the minicheck note: it is no longer required for the benchmark NLI path (the LLM entailment judge
  replaces it). (Keep it documented for Pipeline B's legacy `nli_verifier` if still used there.)

## 3. Invariants
- **No more `unavailable` in normal operation:** the judge is an API call (no local model); `nli_status:"ok"`
  with real per-sentence verdicts. `unavailable` only on a genuine missing-`OPENROUTER_API_KEY` config error.
- **Advisory / non-gating:** still only annotates `manifest['nli_verification']`; never changes
  release/status (4-role D8 single gate).
- **Faithfulness direction:** scores span⊨sentence on delivered sentences; flags, never injects.
- **Budget:** judge spend counts against the run cap; `BudgetExceededError` propagates (not swallowed).
- **Two-family:** judge model family-segregated from the generator (enforced by the judge's `__init__`).
- **CPU-friendly:** no torch/minicheck/flan-t5; pure OpenRouter API.

## 4. Files I have ALSO checked
- `entailment_judge.py`: `judge(sentence, span)` L143 (sync httpx, books cost, re-raises BudgetExceededError,
  fail-open on transient), `_get_judge()` L301, `_DEFAULT_ENTAILMENT_MODEL="google/gemma-4-31b-it"` L79,
  `__init__` raises ValueError on missing OPENROUTER_API_KEY L118-120, family-segregation L140.
- `strict_verify.py:281` already calls `_get_judge().judge(sentence_clean, combined_span)` — proven path.
- `requirements.txt:88-91` minicheck-only-via-git note; flan-t5 F1 62.1 vs FaithLens 87.3 (old/weak).
- `nli_benchmark_annotator.py` (the file to rewire): `build_nli_pairs` (KEEP) + `annotate_nli_entailment`
  (REWRITE) + `NliUnavailableError`.

## 5. Acceptance (GREEN)
- `annotate_nli_entailment` scores via the LLM judge; `nli_status:"ok"` with per-sentence ENTAILED/NEUTRAL/
  CONTRADICTED verdicts; disputed = neutral+contradicted.
- No torch/minicheck import in the NLI path; works on the CPU VM via OpenRouter.
- `BudgetExceededError` propagates; family-segregation holds; advisory (never gates).
- Tests (offline, MOCK `_get_judge().judge`): grounded vs disputed mapping; missing-API-key → unavailable;
  empty pairs → ok/0. Plus a VM smoke (real entailment, 1-2 sentences).
- ≤ ~200 LOC.

## 6. Smoke plan
1. Offline: `pytest` the rewired annotator with a fake judge (monkeypatch `_get_judge` to a stub returning
   ENTAILED/NEUTRAL/CONTRADICTED) — disputed mapping + unavailable-on-missing-key + empty-pairs.
2. VM: a 2-pair real call via OpenRouter (gemma) → confirm real verdicts (tiny spend).
3. `py_compile`; import-smoke the annotator must NOT import torch/minicheck.

## 7. Resolved (iter-1 questions, now decided)
- **disputed = NEUTRAL ∪ CONTRADICTED** (strict_verify's contract is "no unsupported additions"; the per-
  sentence `verdict` field lets the operator distinguish the two).
- **Judge model = the default `google/gemma-4-31b-it`** (open-weight, family-distinct from deepseek/glm/
  minimax/qwen, AND it satisfies the `PG_ENTAILMENT_MODEL == PG_EVALUATOR_MODEL` gate preflight invariant).
  No model override is added, so the preflight stays green.
