# Path-B operator-supervised smoke runbook (I-safety-002b #925)

**One operator-supervised single-question POLARIS run BEFORE the 5 full runs.** Confirms
POLARIS's clinical-tuned scope/corpus gates accept the non-clinical golden questions
(#72 AI labor OR #90 ADAS liability), and that the new `--pathB-gate` lifecycle wires up
correctly end-to-end. Per Codex PR-3 design answer E (`one-question` scope).

## Why one non-clinical question first
POLARIS's pipeline (honest_sweep_r3) has clinical-tuned gates landed by `I-bug-771/775/776`
(tier classifier, fetch layer, corpus adequacy for RCTs/guidelines). Two of the 5 golden
DRB-EN questions are non-clinical: **#72 (Education & Jobs)** and **#90 (Crime & Law)**.
A scope rejection or corpus-inadequate abort on these would invalidate the whole
head-to-head — better to know that before spending 5×$0–$40 of real run cost.

**Recommendation: smoke #72** (AI labor lit review). The element-coverage requirements are
academic-economic (Frey & Osborne, A&R, Autor, ALM, etc.) — all retrievable via Serper +
Semantic Scholar with no domain-specific extensions needed. #90 has the same scope risk but
adds case-law verification stress; #72 is the cleaner "does the gate fire?" check.

## Preflight checklist (operator)
- [ ] `git status` clean (or HEAD on `bot/I-ux-002` with PR-1+PR-2+PR-3 committed).
- [ ] `python -m pytest tests/dr_benchmark/ -q` → all green.
- [ ] Env vars set (use `.env`):
      - `OPENROUTER_API_KEY=<sk-...>` (sovereign key, billing ON)
      - `SERPER_API_KEY=<...>`
      - `SEMANTIC_SCHOLAR_API_KEY=<...>`
      - `PG_GENERATOR_MODEL=deepseek/deepseek-v4-pro`
      - `PG_EVALUATOR_MODEL=google/gemma-4-31b-it`
      - `OPENROUTER_PROVIDER_ORDER=deepinfra` (single provider; gate aborts otherwise)
      - `OPENROUTER_ALLOW_FALLBACKS=false` (gate aborts if true)
      - `PG_SWEEP_MAX_SERPER=50`, `PG_SWEEP_MAX_S2=50`, `PG_SWEEP_FETCH_CAP=500`,
        `PG_LIVE_MAX_EV_TO_GEN=300`, `PG_V30_ENABLED=1`, `PG_V30_PHASE2_ENABLED=1`,
        `PG_MAX_COST_PER_RUN=40`
      - `PG_PATHB_GATE_SALT=<random-string-never-logged>` (HMAC salt; gate redacts).
- [ ] Question `#72` added to `SWEEP_QUERIES` in `run_honest_sweep_r3.py` with
      `slug="drb_72_ai_labor"`, `domain="education_jobs"`, the verbatim DRB-EN prompt from
      `.codex/I-safety-002b/golden_questions_locked.md`. (Or use `--only drb_72_ai_labor`
      once the entry is in the table.)
- [ ] Resource state clean: `Get-Process codex,python,node` shows no orphans.

## Smoke run
```powershell
$env:OPENROUTER_ALLOW_FALLBACKS = "false"
$env:OPENROUTER_PROVIDER_ORDER = "deepinfra"
# ... (other PG_* / OPENROUTER_* per the checklist)
python -m scripts.run_honest_sweep_r3 --only drb_72_ai_labor --pathB-gate
```

Expected wall time: 5–15 min for a single question at full power.

## Pass criteria
- [ ] `pathB_gate_pin.json` written to the run_dir (preflight + roles pinned).
- [ ] No `pathB_gate_INVALID` sentinel in run_dir.
- [ ] `pathB_gate_result.json` `verdict: PASS` + `served_identity_by_role` shows both roles.
- [ ] `manifest.json` status `success` (NOT `abort_scope_rejected` /
      `abort_corpus_inadequate` / `abort_no_verified_sections`).
- [ ] `report.md` produced with non-trivial content.
- [ ] Cost recorded in `logs/pg_cost_ledger.jsonl` for the session_id.

## Fail modes + fixes
| Symptom | Likely cause | Fix |
|---|---|---|
| `GateError: ALLOW_FALLBACKS must be false` | `.env` has fallbacks on | Set `OPENROUTER_ALLOW_FALLBACKS=false`. |
| `GateError: PROVIDER_ORDER must pin exactly ONE provider` | empty or multi-value | Set `OPENROUTER_PROVIDER_ORDER=deepinfra`. |
| `GateError: retrieval backend 'serper' unreachable` | bad SERPER_API_KEY | Re-issue key; confirm quota. |
| `GateError: served model X != pinned Y` | `PG_GENERATOR_MODEL` set wrong, or OpenRouter substituted silently | Confirm pin slug matches what `_role_pins()` reads (`PG_GENERATOR_MODEL` → `OPENROUTER_DEFAULT_MODEL` → default). |
| `abort_scope_rejected` | clinical-tuned scope gate rejected the non-clinical question | Open URGENT new GH issue + revisit `nodes/scope_gate.py` non-clinical handling BEFORE proceeding. |
| `abort_corpus_inadequate` | clinical-tuned T1 RCT corpus requirement triggered on academic-econ sources | Open URGENT new GH issue + revisit `nodes/corpus_adequacy_gate.py` per-domain thresholds BEFORE proceeding. |

## After smoke PASS
- Commit the new question entry in `SWEEP_QUERIES` if not yet committed.
- Add the other 4 question entries (#75/#76/#78/#90) and proceed to the 5 full Path-B runs:
  ```powershell
  foreach ($q in @("drb_75_metal_ions","drb_76_gut_microbiota","drb_78_parkinsons","drb_72_ai_labor","drb_90_adas_liability")) {
      python -m scripts.run_honest_sweep_r3 --only $q --pathB-gate
  }
  ```
- Then run the dual §-1.1 line-by-line audit (Claude + Codex), reconcile, build the
  rubric JSON snapshot if not already (`build_rubric_json.py`), score each
  `(system, question)` (`score_run.py`), and aggregate (`aggregate_systems.py`).

## After smoke FAIL
- Do NOT proceed to the 5 full runs. The gate is doing its job — investigate the failure
  via the URGENT GH issue path above. Patch + re-smoke.
