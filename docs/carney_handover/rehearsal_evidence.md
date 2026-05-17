# I-rdy-018 — OpenRouter V4 Pro rehearsal evidence (#514)

**Run UTC:** 2026-05-17 ~05:47Z–07:35Z
**Pipeline:** pipeline-A honest rebuild, OpenRouter (non-sovereign) topology
**Generator / verifier:** `deepseek/deepseek-v4-pro` + `google/gemma-4-31b-it`
**Branch under test:** `bot/I-rdy-018-openrouter-rehearsal` (carries the #551
retrieval fan-out timeout fix + the #554 post-retrieval candidate-loop
wall-clock bound, both merged from `polaris`).

## Phase 0 — model availability (`run_rehearsal.py check-models`)

```
OpenRouter /models — 356 models in catalogue
  [OK ] generator: deepseek/deepseek-v4-pro
  [OK ] evaluator: google/gemma-4-31b-it
check-models: PASS — generator + evaluator both available
```

## Phase 4 — 8-prompt billed rehearsal

**Command** (operator-authorized billed run, per-run cost cap $5.00):

```
PYTHONPATH=src python -c "import sys,runpy; from dotenv import load_dotenv; \
  load_dotenv(); sys.argv=['x','run','--max-cost','5.00', \
  '--out-root','outputs/rehearsal_runs']; \
  runpy.run_path('scripts/v6/run_rehearsal.py',run_name='__main__')"
```

### Per-prompt results

| # | template | run_id | pipeline_status | cost_usd |
|---|---|---|---|---|
| 1 | clinical | `rehearsal_clinical_77f75e1c` | `abort_corpus_inadequate` | 0.0000 |
| 2 | policy | `rehearsal_policy_8c16a863` | `partial_qwen_advisory` | 0.0558 |
| 3 | tech | `rehearsal_tech_95c5ece4` | `abort_corpus_inadequate` | 0.0000 |
| 4 | due_diligence | `rehearsal_due_diligence_93ea5821` | `abort_corpus_inadequate` | 0.0000 |
| 5 | ai_sovereignty | `rehearsal_ai_sovereignty_f2333fca` | `partial_qwen_advisory` | 0.0424 |
| 6 | canada_us | `rehearsal_canada_us_74624a9e` | `success` | 0.0500 |
| 7 | workforce | `rehearsal_workforce_367bbdd3` | `partial_thin_corpus` | 0.0376 |
| 8 | custom | `rehearsal_custom_296a7728` | `partial_thin_corpus` | 0.0550 |

**Total cost:** $0.2408 (cap $5.00/run — never approached).

## RESULT: PASS

All 8 prompts reached a **terminal verdict** — the rehearsal harness emitted
`RESULT: PASS — the full non-sovereign rehearsal path passed start-to-finish`.

Terminal verdicts are `success`, `abort_*`, and `partial_*` — each is a clean,
honest pipeline outcome (the pipeline either produced verified prose, declined
on an inadequate corpus, or produced a partial under an explicit advisory).
The only non-passing outcomes would be `error_*` or an unbounded hang; neither
occurred.

## Robustness fixes validated by this run

This rehearsal is the re-run after the prior attempt (`_live_run2.log`) hung
~31 minutes. Two retrieval-robustness fixes were merged into the branch and are
empirically confirmed here:

- **#551** (retrieval fan-out per-backend wall-clock bound) — no fetch-backend
  hang recurred across 8 prompts of live retrieval.
- **#554** (post-`parallel_fetch` candidate-loop wall-clock bound) — the
  `policy` prompt, which hung 31 min at this exact stage in the prior run,
  this time ran fully through retrieval → corpus assembly → generation →
  evaluation to a `partial_qwen_advisory` terminal verdict.

## Observations (non-blocking)

- **OpenRouter 429 rate-limiting:** under sustained load the Gemma entailment
  judge and some generator calls were throttled (HTTP 429). Handled
  gracefully — warn-mode + bounded retry; it slowed the run (≈1h45m wall for 8
  prompts) but produced no failures. For the sovereign cluster (vLLM-served,
  no shared rate limit) this throttling will not apply.
- **`run_events` Redis emit** logged `ConnectionError` to `localhost:6379` —
  expected and non-fatal: the rehearsal harness runs pipeline-A directly, with
  no Redis; event emit is best-effort.
- Three prompts (`clinical`, `tech`, `due_diligence`) aborted at
  `abort_corpus_inadequate` — the corpus-adequacy gate correctly declined
  rather than generate on a thin corpus. One prompt (`canada_us`) produced a
  full `success`.
