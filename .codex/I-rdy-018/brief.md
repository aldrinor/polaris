# Codex brief review — I-rdy-018 (#514): OpenRouter V4 Pro rehearsal + evidence package

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (return THIS, nothing else)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

You are reviewing the **brief / acceptance criteria** for GitHub issue #514.

## SCOPE DECISION — RESOLVED (your iter-1 ruling B carried out)

Iter 1 you ruled **B**: #514's acceptance requires a live billed run, and
Claude must not spend autonomously without operator authorization. That was
surfaced on #514. **The operator has now authorized it** — verbatim choice:

> **"All 8 prompts, $5/run cap"** — run all 8 canonical templates
> end-to-end through the real model, `PG_MAX_COST_PER_RUN=5.00`, total
> spend ceiling ~$40.

So the full scope is now in play and this PR **does** execute the live
billed rehearsal run. The implementation below is the full plan: the
capability, the live run, and the evidence package.

## Codex iter-1 P2 findings — resolutions

- **P2-1 (dry-run / check-models must not implicitly load `.env` secrets).**
  Resolved: `run_rehearsal.py` does NOT call `load_dotenv`; it reads only
  the process environment. The test runs `check-models` / `run --dry-run`
  in a subprocess with an `env` dict that explicitly omits
  `OPENROUTER_API_KEY`, proving the no-spend / fail-loud paths.
- **P2-2 (live q-dict must match actor parity — unique artifact dirs +
  `v30_contract_patch`).** Resolved structurally: `run_rehearsal.py run`
  does NOT hand-build a q-dict. It calls the real actor body —
  `run_store.insert_run(run_id, …)` then
  `enqueue_research_run.fn(run_id, {"template":…, "question":…})`. `.fn()`
  invokes the undecorated actor function synchronously (no Redis); the
  actor itself builds the q-dict, synthesizes `v30_contract_patch`, creates
  the unique `outputs/v6_runs/<run_id>` artifact dir, calls `run_one_query`,
  and updates `run_store`. This is the genuine v6 path with zero
  duplication — not a legacy pipeline-A shortcut.
- **P2-3 (key-removal proof commands non-disclosing).** Resolved: the
  procedure doc's key-removal section never prints the key value — it
  greps only for the key *shape* (a redacted match count) and checks
  `check-models` fails loud; on failure it reports "key still present"
  without echoing it.

---

## Issue #514 (I-rdy-018) — verbatim

> **Phase 4. Wire the LLM endpoint as env vars; point at OpenRouter V4 Pro +
> Gemma (test-only, non-confidential). Run the full journey end-to-end with
> the real model. Evidence package: model-availability check, fixed
> non-confidential prompt set, key-removal proof procedure, explicit
> env-diff to the sovereign config.**
> Acceptance: the full non-sovereign rehearsal path passes start-to-finish;
> Codex APPROVE.
> Depends on: Phase 3 complete (I-rdy-014).

Phase 3 / I-rdy-014 (#510) is shipped (PR #545) — dependency met.

## Context — verified against HEAD

- **The journey runs through the actor.** `polaris_v6.queue.actors.
  enqueue_research_run` (a `@dramatiq.actor`) builds the q-dict
  (`domain, slug, question, external_run_id, decision_id, v6_mode,
  out_root_override, template_id`), synthesizes `v30_contract_patch` from
  the v6 template, then `asyncio.run(run_one_query(q, artifact_dir_root))`.
  Calling `enqueue_research_run.fn(...)` runs that body synchronously
  without Redis (it is the undecorated function). Setting
  `POLARIS_V6_QUEUE_USE_STUB=1` lets `actors.py` import without a live
  broker.
- **LLM wiring is env-driven.** `PG_GENERATOR_MODEL` / `PG_EVALUATOR_MODEL`
  select the pair; `OPENROUTER_API_KEY` + `OPENROUTER_BASE_URL`
  (`https://openrouter.ai/api/v1`) drive the gateway. The rehearsal points
  the generator at **`deepseek/deepseek-v4-pro`** (V4 Pro was made to work
  as the generator in #495 / I-gen-003) and the evaluator at the canonical
  Gemma (`google/gemma-4-31b-it`).
- **8 canonical templates** (`actors.py` `TEMPLATE_TO_SCOPE_DOMAIN`):
  `clinical, policy, tech, due_diligence, ai_sovereignty, canada_us,
  workforce, custom`.
- `infra/vexxhost/.env.example` carries `POLARIS_LLM_BACKEND=openrouter`
  (rehearsal config) which flips to `vllm` for the sovereign cutover
  (#199, OVH H200) — the basis for the env-diff.
- `scripts/demo_smoke.py` is the existing $0 in-process smoke; #514 is the
  complementary **real-model** rehearsal.

## Proposed implementation — 5 files (4 new + 1 captured evidence)

### File 1 (NEW) — `scripts/v6/run_rehearsal.py`

Self-contained CLI (`scripts/v6/` pattern), three subcommands:

`check-models` — model-availability check:
- Authenticated GET `OPENROUTER_BASE_URL`/`models` (no token spend).
- Confirm the configured generator (V4 Pro) and evaluator (Gemma) model
  IDs are both present in the catalogue.
- Fail loud (non-zero, clear message) if `OPENROUTER_API_KEY` is unset,
  the HTTP call fails, or a model is absent. Print a present/absent table.

`run` — the rehearsal journey runner (`--dry-run`, `--only <template>`,
`--out-root`, `--max-cost`):
- Load the fixed prompt set (File 2).
- `--dry-run` (validate-only, no spend, no DB write, no LLM call): parse
  the prompt set, confirm every template is in `TEMPLATE_TO_SCOPE_DOMAIN`,
  resolve+print the LLM env config (generator / evaluator / backend /
  base-url / key-present yes-no), print the planned runs. Exit 0.
- live mode: set `PG_GENERATOR_MODEL=deepseek/deepseek-v4-pro`,
  `PG_EVALUATOR_MODEL=google/gemma-4-31b-it`, `PG_MAX_COST_PER_RUN`
  (from `--max-cost`, default 5.00), `POLARIS_V6_QUEUE_USE_STUB=1`; then
  for each prompt: `run_store.insert_run(run_id, template, question)` +
  `enqueue_research_run.fn(run_id, payload)` — the **real actor path**.
  Collect each run's `pipeline_status` + `cost_usd` from `run_store`.
  Print a per-prompt result table; exit 0 iff every run reached a terminal
  status (`success` or a defined `abort_*` — both are start-to-finish
  passes per CLAUDE.md §9.3; only `error_*` / exceptions fail the rehearsal).

### File 2 (NEW) — `tests/v6/fixtures/rehearsal_prompts.yaml`

The fixed non-confidential prompt set — one `{template, question}` per
canonical template (8 entries). Each question a public-policy /
public-clinical query with **zero confidential content** (these prompts
travel to OpenRouter, a US gateway, during the non-sovereign rehearsal;
non-confidentiality is mandatory, stated in the file header). Shared by the
runner and the test.

### File 3 (NEW) — `tests/v6/test_run_rehearsal.py`

Subprocess-driven (harness style of `test_scripts_v6_handover.py`),
exercising wiring with **no LLM call / no spend** — the subprocess `env`
explicitly omits `OPENROUTER_API_KEY`:
- `test_check_models_fails_loud_without_key` — non-zero exit, clear message.
- `test_run_dry_run_validates_wiring` — `run --dry-run` exits 0; stdout
  shows all 8 templates planned + env config resolved.
- `test_rehearsal_prompts_cover_all_templates` — the YAML's templates ==
  the 8 canonical `TEMPLATE_TO_SCOPE_DOMAIN` keys.
- `test_dry_run_makes_no_billed_call` — `run --dry-run` completes with no
  key set and writes no run-store rows.

### File 4 (NEW) — `docs/carney_handover/rehearsal_procedure.md`

The evidence-package document:
1. **Env wiring** — the OpenRouter rehearsal env vars.
2. **Model-availability check** — `run_rehearsal.py check-models` + output.
3. **The rehearsal run** — `run --dry-run` then live `run`; start-to-finish
   pass criteria (every prompt reaches a terminal status under the cap).
4. **Key-removal proof procedure** — non-disclosing: unset
   `OPENROUTER_API_KEY`, confirm `check-models` fails loud, confirm
   `/transparency` reports the vLLM backend, grep the env for the key
   *shape* (count only, never echo the value).
5. **Env-diff to the sovereign config** — explicit table: every env var
   differing between the OpenRouter rehearsal config and the sovereign
   vLLM config.

### File 5 (NEW, captured) — `docs/carney_handover/rehearsal_evidence.md`

The captured evidence of the **executed live run**: UTC timestamp; the
`check-models` result; the per-prompt table (template → run_id →
`pipeline_status` → `cost_usd`); total spend; and a `RESULT:` line. This is
the proof the non-sovereign rehearsal path passed start-to-finish.

## Execution plan (this PR)

1. Implement Files 1-4; commit 1.
2. Run `check-models` (free) — capture.
3. Run `run --dry-run` — validate wiring.
4. Execute the **live billed run**: all 8 prompts, `--max-cost 5.00`
   (operator-authorized, ~$40 ceiling). Capture File 5.
5. `pytest tests/v6/test_run_rehearsal.py`.
6. Codex diff review; ship.

## Out of scope (do not flag as P0/P1)

- The sovereign vLLM cutover — #199 (`I-sov-001`), gated on the OVH H200.
- Per-prompt §-1.1 line-by-line content audit of the rehearsal reports —
  that is the demo-rehearsal audit issue (#473), not Phase-4 wiring.

## LOC estimate + exemption request

~190 `run_rehearsal.py` + ~110 test ≈ **~300 code**, plus a ~40-line YAML
and two docs. Exceeds the 200-LOC cap; all-new files, no existing code path
modified. **Requesting a LOC-cap exemption** (you signalled iter 1 it is
"acceptable for the proposed all-new files"). Confirm.

## Files I have ALSO checked and they're clean

- `src/polaris_v6/queue/actors.py` — `enqueue_research_run` body + `.fn()`
  semantics + `TEMPLATE_TO_SCOPE_DOMAIN`; the runner reuses this path.
- `src/polaris_v6/queue/run_store.py` — `insert_run` / `get_run` the
  runner uses to seed + read results.
- `scripts/run_honest_sweep_r3.py` — `run_one_query` (the journey the
  actor invokes); unchanged.
- `src/polaris_graph/llm/openrouter_client.py` — `OPENROUTER_BASE_URL`,
  the gateway `check-models` targets.
- `infra/vexxhost/.env.example` — `POLARIS_LLM_BACKEND` openrouter/vllm
  switch (env-diff basis).
- `scripts/demo_smoke.py`, `tests/v6/test_scripts_v6_handover.py` — the
  $0-smoke and subprocess-test patterns.

## Acceptance criteria for the resulting PR

1. `scripts/v6/run_rehearsal.py` — `check-models` + `run` (`--dry-run` +
   live); live `run` goes through `enqueue_research_run.fn` (actor parity);
   env-driven; fail-loud on missing key / non-canonical template.
2. `tests/v6/fixtures/rehearsal_prompts.yaml` — 8-template non-confidential
   prompt set.
3. `tests/v6/test_run_rehearsal.py` — passes; wiring tests make no billed call.
4. `docs/carney_handover/rehearsal_procedure.md` — env wiring, availability
   check, run procedure, key-removal proof, env-diff to sovereign config.
5. `docs/carney_handover/rehearsal_evidence.md` — captured live-run evidence;
   every prompt reached a terminal status under the cap; `RESULT: PASS`.
6. `pytest tests/v6/test_run_rehearsal.py` passes; no `tests/v6/` regression.

Return the YAML verdict block only.
