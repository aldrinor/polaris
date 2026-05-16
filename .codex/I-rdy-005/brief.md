# Codex BRIEF review — I-rdy-005 (#501): reconcile templates to the canonical 8

**Type:** BRIEF review (acceptance-criteria correctness), iter 3 of 5.
**iter 1:** REQUEST_CHANGES (2 P1). **iter 2:** REQUEST_CHANGES (2 P1, 2 P2) — both iters' P1s were "test inventory incomplete." iter 3 fixes the *class* of finding: §3b is reframed from paper-enumeration to **empirical full-suite-green acceptance** (a ~35-file rename cannot be inventoried by grep; it is validated by running the suite).

## §0. Cap directive (CLAUDE.md §8.3.1) — verbatim, binding

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## §1. Issue + acceptance

GH #501 (I-rdy-005, Phase 3.2): **one source of truth = `config/scope_templates/`** (canonical 8: `clinical, policy, tech, due_diligence, ai_sovereignty, canada_us, workforce, custom`). Landing page, frontend TS types, and the v6 backend registry all read from it. Acceptance: **zero template mismatch across frontend/backend; Codex APPROVE.** Depends on: I-rdy-003 (in unmerged PR #517).

## §2. Current state

Wrong 4 = `climate, defense, housing, trade`. Missing 4 = `policy, tech, due_diligence, custom`. `config/scope_templates/*.yaml` + `scope_gate.SUPPORTED_DOMAINS` are **already the canonical 8** — everything else converges onto them. Root cause: I-arch-001c (2026-05-13) shipped 4 placeholder templates; `scope_templates/` + `SUPPORTED_DOMAINS` were locked to the canonical 8 (I-rdy-001) and the v6 layer never caught up.

## §3. Change plan — production code (7 files)

1. **`config/v6_templates/`** — delete `climate/defense/housing/trade.json`; author `policy/tech/due_diligence/custom.json` as full schema-conformant `TemplateContent`, content derived from `config/scope_templates/{id}.yaml`. Real content, no placeholders (LAW II).
2. **`src/polaris_v6/schemas/run_request.py:9`** — `TemplateId` Literal → canonical 8.
3. **`src/polaris_v6/queue/actors.py:51-61`** — `TEMPLATE_TO_SCOPE_DOMAIN` → all-8 identity; rewrite the stale "Phase 2" comment.
4. **`src/polaris_graph/v30_contract_synthesizer.py:22-44`** — re-key `_TYPE_FOR_TEMPLATE` + `_REQUIRED_FIELDS_FOR_TEMPLATE`.
5. **`web/lib/api.ts:56-63`** — `TemplateId` union → canonical 8.
6. **`web/app/page.tsx:22`** — landing `templates` array → canonical 8.
7. **`web/app/dashboard/page.tsx:31`** — `FALLBACK_TEMPLATES` → canonical 8.

## §3b. Change plan — tests / fixtures / benchmark — **empirical acceptance**

The §3 change to the source of truth deterministically breaks every test/fixture/spec that hardcodes a removed id. iter 1 named 4 such files; iter 2 named ~10 more; a wider grep finds more still — **paper-enumeration of a ~35-file rename does not converge** (CLAUDE.md §8.3.6). The acceptance criterion is therefore **empirical, not an inventory**:

> **GREEN bar:** after the §3 change, `pytest tests/` and `npx playwright test` (web e2e) BOTH pass with zero failures, and no fixture/spec references a removed id (verified by `grep -rn '\b(climate|defense|housing|trade)\b'` returning only legitimate non-template-id hits). The `codex_diff.patch` includes the full-suite run evidence; Codex's **diff** review verifies suite-green empirically.

**Known starting set** (grep + iter-1/2 findings — re-keyed during the diff, then suite-run completes the inventory):
- Backend tests: `test_v30_contract_synthesizer.py`, `test_template_to_scope_domain.py`, `followup/test_agent.py`, `test_api_templates.py`, `test_api_bundle.py`, `test_api_health_and_runs.py`, `test_benchmark_schema.py`, `test_template_registry.py`, `test_scope.py`, `benchmark/test_api_benchmark_runner_smoke.py`, `test_schemas.py`, `test_compare.py`, `test_paired_prompts_corpus.py`.
- e2e specs: `demo_walkthrough.spec.ts`, `landing_template_grid.spec.ts`, `command_palette_adversarial.spec.ts`, `f1_multi_tab.spec.ts` (+ any other `command_palette*.spec.ts` the suite-run flags).
- Fixtures: `tests/v6/fixtures/baseline_pins/baseline_{climate,housing}.json`, `tests/v6/fixtures/evidence_contract_v1/golden_run_{climate,defense,with_contradiction,abort_no_verified}.json`, `tests/fixtures/v30_contracts/{climate,defense,housing,trade}.json`.

**Fixture strategy (Codex iter-2 ruled `relabel_to_canonical`):** evidence/baseline fixtures — set the `template` field to a canonical id whose rubric the content matches (`climate/defense/housing/trade` were all `policy`-rubric → `policy`), keep descriptive filenames. v30 contract fixtures — **regenerate** the canonical-4 contracts via the deterministic `v30_contract_synthesizer` (sha256 anchors) and **delete** the 4 wrong-id files (do not relabel — the contract bodies must be genuine).

**Benchmark:** `scripts/v6/benchmark/api_benchmark_runner.py:561` `CARNEY_TEMPLATES` → canonical 8.

## §3c. Drift guard

NEW `tests/v6/test_template_canonical_set.py` — assert exact set-equality of the canonical 8 across **all** id-carrying surfaces: (a) `config/scope_templates/*.yaml` stems, (b) `registry.list_template_ids()`, (c) `scope_gate.SUPPORTED_DOMAINS`, (d) `run_request.TemplateId.__args__`, (e) `web/lib/api.ts` `TemplateId` union, (f) `web/app/page.tsx` `templates` array, (g) `web/app/dashboard/page.tsx` `FALLBACK_TEMPLATES`, (h) `api_benchmark_runner.CARNEY_TEMPLATES`. Any drift on any surface fails CI.

## §4. Scope / cap (Codex iter-1 ruled A)

Single PR + 200-LOC-cap exemption. Honest estimate ≈ 800 LOC (≈140 production code + ≈400 schema-validated config JSON + ≈260 mechanical test/fixture re-keying). Exemption ground: bulk is config data + mechanical rename; splitting deliberately preserves a frontend/backend mismatch. One `codex_diff.patch` for the diff gate.

## §5. GREEN criteria
- Zero template mismatch across all 8 id-carrying surfaces in §3c.
- `test_template_canonical_set.py` passes and fails on any drift.
- `pytest tests/` green; `npx playwright test` green; no removed id remains anywhere.
- `/templates` serves the canonical 8; landing + dashboard render the canonical 8.

## §6. Output schema (CLAUDE.md §8.3.9)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
verdict_reasoning: <text>
```
Loose prose without the schema → resubmit.
