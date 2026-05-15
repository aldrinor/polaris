# I-rdy-005 (#501) — Claude architect self-review

**Scope:** reconcile every template-id surface to the canonical 8
(`clinical, policy, tech, due_diligence, ai_sovereignty, canada_us, workforce,
custom` — the `config/scope_templates/` set). Retire the stale
`climate/defense/housing/trade`.

**The change (42-file canonical diff, +889/−800 — single PR + cap exemption per
Codex scope ruling A):**
- **Backend:** `run_request.py` `TemplateId` Literal; `actors.py`
  `TEMPLATE_TO_SCOPE_DOMAIN` (all-8 identity + fail-loud on unknown id);
  `v30_contract_synthesizer.py` `_TYPE_FOR_TEMPLATE` + `_REQUIRED_FIELDS_FOR_TEMPLATE`.
- **`config/v6_templates/`:** deleted climate/defense/housing/trade.json;
  authored policy/tech/due_diligence/custom.json — full `TemplateContent`,
  content grounded in the matching `config/scope_templates/<id>.yaml`,
  schema-valid + registry-loaded.
- **Frontend:** `web/lib/api.ts` `TemplateId`, `web/app/page.tsx` cards +
  count label, `web/app/dashboard/page.tsx` `FALLBACK_TEMPLATES`.
- **Benchmark:** `api_benchmark_runner.py` `CARNEY_TEMPLATES`.
- **Drift guard (NEW):** `tests/v6/test_template_canonical_set.py` — exact
  set-equality of the canonical 8 across all 11 id-carrying surfaces.
- **Tests/fixtures:** ~13 Python test files re-keyed; v30 golden fixtures
  regenerated via the deterministic synthesizer; 6 baseline/evidence fixtures
  relabelled; 4 e2e specs re-keyed (palette inputs verified against
  `command_palette.tsx` `score_template`).

**Verification (the §3b empirical GREEN bar):**
- Drift guard `test_template_canonical_set.py` — 11/11 pass.
- `pytest tests/v6/ tests/polaris_v6/` — 516 passed, 0 failed.
- `pytest tests/polaris_graph/` — 4585 passed; 15 failures are pre-existing
  (content-preservation / entailment-judge / demo-smoke — env/data-dependent;
  none reference templates; absent from the I-rdy-005 import closure). Zero
  new Python failures introduced.
- v30 synthesizer + followup — 44 pass. Playwright e2e: 4 specs re-keyed; the
  CI `e2e` job validates the browser run.

**Codex:** brief APPROVE iter 3; diff APPROVE iter 2 (iter-1 2 P1 + 2 P2 — the
actor silent-fallback, a stale assertion, stale test literals, and the landing
count label — all fixed).

**Note:** I-rdy-005 (#501) depends on I-rdy-003 logically (verification before
reconcile); I-rdy-003's work is done (PR #521). I-rdy-005's diff is independent
of the unmerged chain (touches different files) so it cuts cleanly off
`polaris`.
