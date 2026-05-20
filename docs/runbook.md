# POLARIS Runbook

How to run each pipeline end-to-end, interpret the output, and respond
to common failure modes.

**Document date**: 2026-04-18.

---

## 1. Before you start

### Prerequisites

- Python 3.11+
- A `.env` file at repo root with:
  ```
  OPENROUTER_API_KEY=sk-or-...
  SERPER_API_KEY=...
  # Optional but strongly recommended:
  SEMANTIC_SCHOLAR_API_KEY=...
  ```
- Dependencies installed: `pip install -r requirements.txt`

### Sanity checks

```bash
# 1. All tests pass
python -m pytest tests/polaris_graph/ -v
# Expected: 305 passed

# 2. Module imports resolve
python -c "import scripts.run_honest_sweep_r3 as s; \
  print('OK:', hasattr(s, 'run_one_query') and hasattr(s, 'filter_verified_sections'))"
# Expected: OK: True

# 3. Budget env var present
python -c "import os; from dotenv import load_dotenv; load_dotenv(); \
  print('PG_MAX_COST_PER_RUN:', os.getenv('PG_MAX_COST_PER_RUN', 'default 5.00'))"
```

---

## 2. Pipeline A — the 8-query validation sweep

### Run one query

```bash
python -m scripts.run_honest_sweep_r3 \
    --only clinical_tirzepatide_t2dm \
    --out-root outputs/dev_smoke
```

Available query slugs:

| Slug | Domain |
|---|---|
| `clinical_tirzepatide_t2dm` | clinical |
| `clinical_afib_anticoagulation` | clinical |
| `tech_rag_architectures_2024` | technology |
| `tech_quantum_error_correction` | technology |
| `dd_carbon_credit_due_diligence` | due diligence |
| `dd_semiconductor_supply_chain` | due diligence |
| `policy_ai_act_compliance` | policy |
| `policy_paris_agreement_monitoring` | policy |

### Run all eight

```bash
python -m scripts.run_honest_sweep_r3 --out-root outputs/full_sweep_$(date +%Y%m%d)
```

Expected duration: ~30-90 minutes for all eight, depending on corpus
quality and retrieval backends.

### Per-query outputs

Under `outputs/<sweep_name>/<slug>/`:

```
manifest.json            — pipeline verdict + cost + gate outcomes
report.md                — verified findings OR pipeline-verdict artifact
corpus_approval.json     — tier distribution + approval decision + note
contradictions.json      — numeric-claim contradictions detected
protocol.json            — the scope protocol used
bibliography.json        — merged cross-section bibliography
```

### Manifest statuses — what each means

| Status | Meaning | Report.md contents |
|---|---|---|
| `success` | All gates passed, generator produced verified prose | Actual research findings + bibliography |
| `abort_scope_rejected` | Question failed the scope gate | Pipeline-verdict artifact |
| `abort_corpus_inadequate` | Not enough sources above quality floor | Pipeline-verdict artifact |
| `abort_corpus_approval_denied` | Operator note too trivial for material deviation | Pipeline-verdict artifact |
| `abort_no_verified_sections` | Every generated section failed `strict_verify` | Pipeline-verdict artifact listing per-section verdicts |
| `error_*` | Unexpected failure (API outage, malformed response, etc.) | May be incomplete; check logs/ |

A `report.md` with content under a `## Pipeline verdict` heading is
**not** a research report — it is a refusal artifact and downstream
consumers should NOT treat it as a finding.

---

## 3. Pipeline B — the web UI

### Local dev

```bash
uvicorn scripts.live_server:app --host 0.0.0.0 --port 8000 --reload
```

Visit `http://localhost:8000`.

### Docker

```bash
docker compose up web
# Visit http://localhost:8000
```

The `web` service uses Dockerfile → `docker_entrypoint.sh serve` →
`uvicorn scripts.live_server:app`. ChromaDB is a sidecar at port 8100.

### Submitting a research vector via UI

The UI calls into `src/polaris_graph/graph{,_v2,_v3}.py` — a LangGraph
pipeline DIFFERENT from pipeline A. **None of the pipeline A hardness
invariants (strict_verify, corpus approval, delimiter sanitization)
currently apply to pipeline B.** Backporting those invariants is a
known gap (see `docs/todo_list.md`).

---

## 4. Pipeline C — legacy CLI research (DO NOT USE)

Frozen since 2026-03-16. Broken: `scripts/full_cycle.py` imports
`scripts/final_audit.py` and `scripts/run_ragas_v3.py`, neither of
which exist. Docker `research` subcommand will fail.

See `src/orchestration/FROZEN_SINCE_2026-03-16.md` for the retire /
repair / leave decision tree.

---

## 5. Changing the model pair

Pipeline A enforces a two-family constraint: generator and evaluator
must be from different training lineages.

### Default pair (re-pinned 2026-05-19 per I-cd-009 / GH#624 Carney demo lock)

- Generator: `deepseek/deepseek-v4-pro` (DeepSeek lineage; 1.6T total, 49B active MoE)
- Evaluator: `google/gemma-4-31b-it` (Gemma lineage)

### Override via environment

```
PG_GENERATOR_MODEL=deepseek/deepseek-v4-pro
PG_EVALUATOR_MODEL=google/gemma-4-31b-it
```

### Invalid pairs raise at construction

```python
# This will raise RuntimeError (both in DeepSeek family)
from src.polaris_graph.llm.openrouter_client import check_family_segregation
check_family_segregation("deepseek/deepseek-v4-pro", "deepseek/deepseek-v4-flash")
```

The check handles case variants (`DeepSeek/DeepSeek-V4-Pro`) and
hyphenated org prefixes (`deepseek-ai/DeepSeek-V4-Pro`).

---

## 6. Adjusting the budget cap

```
PG_MAX_COST_PER_RUN=5.00
```

If OpenRouter omits `usage.cost` (some models do), the pipeline imputes
cost from token counts via a per-model price table in
`src/polaris_graph/llm/openrouter_client.py:_PRICE_TABLE_USD_PER_M`.
Unknown-vendor models use an Opus-tier worst-case ($3/$15 per M tokens).

Negative token counts (corrupted API response) are clamped to zero —
they cannot silently reduce the accumulated budget.

---

## 7. Adding a new query to the sweep

Edit `scripts/run_honest_sweep_r3.py`:

1. Append a new entry to `SWEEP_QUERIES` with `slug`, `domain`, `question`, `amplified`.
2. Ensure a scope-template YAML exists in `config/scope_templates/<domain>.yaml`.
3. Ensure a completeness checklist exists in `config/completeness_checklists/<domain>.yaml`.
4. Test: `python -m scripts.run_honest_sweep_r3 --only <your_slug> --out-root outputs/smoke`.

---

## 8. Common failure modes

### `corpus.material_deviation=true` on a released manifest

The corpus tier distribution skewed outside the template's expected
ranges (e.g., clinical template expects T1 ≥ 30%, run retrieved only
25%; tech template allows T4 ≤ 20%, run retrieved 70%).

**When material_deviation is true, auto-approve is disabled.**
`compute_tier_distribution()` sets `auto_approve_allowed=False` and
the sweep runner requires an operator/sweep note. The note
substantivity check (`check_approval_note_substantive()`) is
length/pattern-based: ≥ 30 stripped characters and not one of a
small set of trivial phrases ("ok", "approved", "looks fine"). It
does NOT perform a semantic review. An operator can therefore pass
the check with a generic sentence that references the sweep, so
downstream readers of a `material_deviation=true` release should
cross-check the note content (in `corpus_approval.json`) against
the actual tier skew before trusting the report.

If the note check fails, the sweep emits
`abort_corpus_approval_denied` before any generator token spends.

The run ships only if (1) the note substantivity check passes AND
(2) downstream stages (adequacy, generator, strict_verify, evaluator)
pass.

**How to read a `material_deviation=true` release**: treat the 8-query
sweep output as a **pipeline reliability signal** — the honest-
rebuild machinery worked end-to-end — *not* as a quality benchmark of
the generated report's content. Content quality depends on the tier
mix of actually-retrieved sources; the manifest is transparent about
the skew so the reader can calibrate.

If you need a content-quality benchmark, re-run the affected query
with one or more of:

- `PG_LIVE_MAX_SERPER_PER_Q` higher (widen web retrieval)
- Add an academic-first backend to the scope template
- Narrow the research question so the search is more on-topic

### Sweep aborts with `abort_corpus_approval_denied`

The corpus tier distribution materially deviates from the scope
template (e.g., 70% T5 industry reports when the template asks for
≥40% T1 primary studies) and the operator note is trivial (too short,
too generic). Provide a substantive rationale in the note field of
the approval decision.

### Sweep aborts with `abort_no_verified_sections`

Every generator-produced section failed `strict_verify`. Most likely
causes:

- **Evidence pool too narrow**: the generator had no anchoring data,
  so it fabricated. Widen retrieval (more queries, more backends).
- **Cited evidence IDs invalid**: the generator emitted tokens with
  evidence IDs not in the pool. Check `contradictions.json` and the
  per-section verdict in `report.md`.
- **Content-word overlap too strict**: you can relax with
  `PG_PROVENANCE_MIN_CONTENT_OVERLAP=1` for short-sentence domains,
  but understand you're trading semantic grounding for recall.

### Sweep hits the budget cap

`BudgetExceededError` from `check_run_budget()`. Options:

- Increase `PG_MAX_COST_PER_RUN` (default 5.00)
- Reduce `PG_LIVE_MAX_EV_TO_GEN` (default 20, caps evidence count
  passed to generator)
- Use a cheaper generator: DeepSeek V3.2-Exp is $0.27/$0.38 per M;
  Qwen3-8B is $0.05/$0.40 per M

### OpenRouter returns empty `content` for some models

`openrouter_client` handles this for DeepSeek (uses `reasoning_content`
when length > 200 chars as a fallback — some providers misroute prose
into the reasoning channel). If a new model exhibits empty content,
check the provider's response shape and extend the handler.

### Tests fail after pulling latest

```
python -m pytest tests/polaris_graph/ -v 2>&1 | grep "ModuleNotFoundError"
```

If a module is missing under `src/` (archived too eagerly), restore
from `archive/2026-04-18-pre-audit-cleanup/src/<path>`. See also
`docs/live_code_audit.md` for the static import-closure map that
drove the 2026-04-18 cleanup.

---

## 9. Observability

### Live during a run

- `logs/session_log.md` — append-only operational log (per CLAUDE.md §2.2)
- `logs/bug_log.md` — defects / blockers registry
- `logs/pg_cost_ledger.jsonl` — JSONL per-call cost records

### After a run

- `outputs/<sweep>/<slug>/manifest.json` — pipeline verdict + cost
- `outputs/<sweep>/<slug>/contradictions.json` — numeric claim collisions
- `outputs/<sweep>/<slug>/report.md` — findings OR pipeline-verdict
- `state/progress_ledger.jsonl` (if applicable) — append-only execution log

---

## 10. Reset between sweeps

```python
from src.polaris_graph.llm.openrouter_client import reset_run_cost
reset_run_cost()
```

`reset_run_cost()` zeros the accumulated run cost so the next sweep
starts fresh. Without this, back-to-back sweeps in the same Python
process share the budget guard.

---

## 11. Emergency stop

- Interactive: Ctrl+C. The orchestrator catches `KeyboardInterrupt`
  at query boundaries; a query in progress may finish before the
  sweep terminates.
- File marker: `.codex/STOP` — if this file exists, the Codex↔Claude
  audit loop refuses to launch new rounds. Useful to halt an
  autonomous loop without a user interrupt.
- Hard stop: kill the Python process. `logs/` and `outputs/` are
  append-mostly; a partial sweep is safe to resume from scratch or
  abandon.

---

## 12. When in doubt

Read, in order:

1. `CLAUDE.md` — operational directives
2. `architecture.md` — what each pipeline does
3. `docs/file_directory.md` — where the code lives
4. `docs/live_code_audit.md` — reachability evidence
5. `outputs/codex_findings/round_{1..5}/` — audit history

If the docs and the code disagree, the code is the source of truth
— open a PR updating the docs, don't silently follow the stale doc.

---

## Live-run smoke (I-cd-016a harness)

`scripts/live_run_smoke.py` is an **operator-runs** harness that drives a
real research run end-to-end against a running v6 backend and verifies
the resulting audit bundle. Costs real OpenRouter spend per invocation
(operator-supervised; not for CI).

### Backend prereqs (must be set on the API + Dramatiq worker hosts)

| Env var | Purpose |
|---|---|
| `POLARIS_JWT_SECRET` | ≥32 chars; HS256 signing for /auth/login tokens (I-cd-014). |
| `POLARIS_STATIC_ACCOUNTS_PATH` | Path to operator-provisioned static_accounts.yaml (default `/etc/polaris/static_accounts.yaml`; I-cd-014). |
| `POLARIS_GPG_KEY_ID` | GPG fingerprint for bundle signing (FastAPI signer override + secret-key in keyring). |
| `OPENROUTER_API_KEY` | OpenRouter gateway auth — used by pipeline-A generator + evaluator. |
| `PG_MAX_COST_PER_RUN` | Hard per-run cost cap (BudgetExceededError); enforces spend ceiling. |

### Client prereqs (where you invoke the smoke)

| Env var | Purpose |
|---|---|
| `POLARIS_V6_BACKEND_URL` | Backend URL (default `http://localhost:8000`). |
| `POLARIS_SMOKE_USERNAME` + `POLARIS_SMOKE_PASSWORD` | Credentials from static_accounts.yaml (required unless `POLARIS_SMOKE_AUTH_DISABLED=1`). |
| `POLARIS_SMOKE_TIMEOUT_S` | SSE wallclock cap; default 600. On timeout the smoke posts /runs/{id}/cancel before exiting. |

### Invocation

```bash
python scripts/live_run_smoke.py \
  --question "What does the 2025 ADA guideline say about tirzepatide dosing for type 2 diabetes?" \
  --template clinical
```

### Output

On PASS:
```
PASS: run_id=<uuid> sections=N verified_sentences=M cost_usd=X duration_ms=Y
RESULT: PASS
```

On FAIL: structured stderr error + non-zero exit (see exit codes in the script docstring).

### Known limitations (tracked)

- **Lock-verification assertions deferred to I-cd-016b** (operator-supervised real run after I-cd-016c fixes the audit bridge model fallback). This harness asserts only success + verified content + bundle conformance.
- **GPG preflight is a stub** until I-cd-016d (#676) ships a real signer-health endpoint. For now, operator manually runs `scripts/v6_preflight.py` to verify the secret key is in the keyring.

### Closes #626

This harness alone does NOT close #626. The acceptance criterion is "real question → verified report end-to-end on OpenRouter" — that artifact is produced at **I-cd-016b (#674)** under operator supervision.
