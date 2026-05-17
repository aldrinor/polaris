# Phase-4 non-sovereign rehearsal procedure

The Phase-4 rehearsal exercises the full POLARIS v6 journey against
**OpenRouter** (V4 Pro generator + Gemma evaluator) before the sovereign
vLLM cutover. It is the *non-sovereign* path: prompts travel to OpenRouter,
a US gateway, so the rehearsal prompt set is **public / non-confidential
only**.

Runner: `scripts/v6/run_rehearsal.py`. Prompt set:
`tests/v6/fixtures/rehearsal_prompts.yaml` (one public question per
canonical template). A captured live run is in `rehearsal_evidence.md`.

---

## 1. Env wiring — the OpenRouter rehearsal config

| Env var | Rehearsal value | Purpose |
|---|---|---|
| `POLARIS_LLM_BACKEND` | `openrouter` | route generation through the OpenRouter gateway |
| `OPENROUTER_API_KEY` | `sk-or-v1-…` | gateway credential (required) |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | gateway endpoint |
| `PG_GENERATOR_MODEL` | `deepseek/deepseek-v4-pro` | V4 Pro generator |
| `PG_EVALUATOR_MODEL` | `google/gemma-4-31b-it` | Gemma evaluator (different lineage) |
| `PG_MAX_COST_PER_RUN` | `5.00` | hard per-run budget cap (`BudgetExceededError` past it) |

`run_rehearsal.py run` sets `PG_GENERATOR_MODEL` / `PG_EVALUATOR_MODEL` /
`PG_MAX_COST_PER_RUN` itself from its flags; `OPENROUTER_API_KEY` must
already be present in the process environment.

## 2. Model-availability check

```
python scripts/v6/run_rehearsal.py check-models
```

Authenticated GET to OpenRouter `/models` (no token spend). Confirms the
configured generator and evaluator model ids are present in the catalogue.
Fails loud if `OPENROUTER_API_KEY` is unset, the request fails, or a model
is absent. Expected tail: `check-models: PASS`.

## 3. The rehearsal run

Validate the wiring first — no LLM call, no spend:

```
python scripts/v6/run_rehearsal.py run --dry-run
```

Then the live billed run (all 8 templates, `$5`/run cap):

```
python scripts/v6/run_rehearsal.py run --max-cost 5.00
```

Each prompt is one full v6 journey, executed through the real actor path
(`enqueue_research_run.fn` — the same q-dict, unique artifact dir, and
`v30_contract_patch` synthesis the production actor uses).

**Start-to-finish pass criteria.** A prompt *passes* when the pipeline
reaches a terminal verdict — `success`, any `abort_*`, or any `partial_*`
(per CLAUDE.md §9.3, `abort_*` are pipeline verdicts, not errors). A prompt
*fails* only on `error_*` or an unhandled exception (the pipeline crashed
before producing a verdict). The rehearsal passes when every prompt passes;
`run_rehearsal.py` prints `RESULT: PASS` and exits 0.

## 4. Key-removal proof procedure

Before the sovereign cutover, prove the OpenRouter credential is gone. The
commands below are **non-disclosing** — they never print the key value.

```
# 1. Unset the credential.
unset OPENROUTER_API_KEY

# 2. The availability check must now fail loud (proves the rehearsal path
#    is dead without the key):
python scripts/v6/run_rehearsal.py check-models   # expect non-zero exit,
                                                  # "OPENROUTER_API_KEY is unset"

# 3. Confirm no OpenRouter key shape survives anywhere in the process env
#    or the deploy .env — COUNT ONLY, never echo the value:
env | grep -c 'sk-or-v1-' || echo "0 OpenRouter keys in env"
grep -c 'sk-or-v1-' /opt/polaris/.env || echo "0 OpenRouter keys in .env"
```

A non-zero count from step 3 means the key is still present — rotate and
re-scrub before the cutover. (See `secret_inventory` / G13 for the full
rotation + teardown sheet.)

## 5. Env-diff — rehearsal config vs sovereign config

The cutover from the OpenRouter rehearsal config to the sovereign vLLM
config (#199 / `I-sov-001`, gated on the OVH H200) is exactly this diff:

| Env var | Rehearsal (OpenRouter) | Sovereign (vLLM) |
|---|---|---|
| `POLARIS_LLM_BACKEND` | `openrouter` | `vllm` |
| `OPENROUTER_API_KEY` | set (`sk-or-v1-…`) | **removed** |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | unused |
| `POLARIS_VLLM_BASE_URL` | unused | set (in-cluster vLLM endpoint, e.g. `http://10.0.0.42:8000/v1`) |
| `PG_GENERATOR_MODEL` | `deepseek/deepseek-v4-pro` | `deepseek/deepseek-v4-pro` (served by sovereign vLLM) |
| `PG_EVALUATOR_MODEL` | `google/gemma-4-31b-it` | `google/gemma-4-31b-it` (served by sovereign vLLM) |

The generator/evaluator **pair is unchanged** — only the serving backend
moves from the US gateway to the in-jurisdiction vLLM cluster. The
two-family invariant (`openrouter_client.check_family_segregation`,
CLAUDE.md §9.1) holds across both configs: DeepSeek and Gemma are different
lineages.
