# Codex DIFF review — I-rdy-005 (#501): reconcile templates to the canonical 8

**Type:** DIFF review, iter 2 of 5. Brief Codex-APPROVED iter 3 (`codex_brief_verdict.txt`); scope ruling **A — single PR + 200-LOC-cap exemption**.

**iter 1 → REQUEST_CHANGES (2 P1, 2 P2) — all fixed:**
- P1 — `actors.py`: `TEMPLATE_TO_SCOPE_DOMAIN.get(..., "policy")` silent fallback → now fails loud (raises `ValueError`) on an unknown template id.
- P1 — `test_api_bundle.py:38`: assertion `== "housing"` → `== "policy"` (matches the relabelled fixture).
- P2 — stale template literals re-keyed in `test_schemas.py`, `test_compare.py`, `test_benchmark_schema.py`.
- P2 — `web/app/page.tsx` count label "3 active · 5 to-build" → "1 active · 7 to-build".
- Surfaced + fixed during the re-run: `golden_run_defense.json` relabelled `tech` (not `policy`) so `test_api_followup_compare`'s different-template assertion keeps two distinct runs. `pytest tests/v6 + tests/polaris_v6`: 516 passed, 0 failed.

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

## §1. Context

I-rdy-005 (#501): reconcile every template-id surface to the canonical 8 (`clinical, policy, tech, due_diligence, ai_sovereignty, canada_us, workforce, custom` — the `config/scope_templates/` set). Retires the stale `climate/defense/housing/trade`. Codex ruled scope A (single PR + cap exemption — the diff is large but mostly config data + mechanical re-key).

## §2. The diff — `.codex/I-rdy-005/codex_diff.patch` (42 files, +889/−800)

**Production code:**
- `src/polaris_v6/schemas/run_request.py` — `TemplateId` Literal → canonical 8.
- `src/polaris_v6/queue/actors.py` — `TEMPLATE_TO_SCOPE_DOMAIN` → all-8 identity; stale "Phase 2" comment rewritten.
- `src/polaris_graph/v30_contract_synthesizer.py` — `_TYPE_FOR_TEMPLATE` + `_REQUIRED_FIELDS_FOR_TEMPLATE` re-keyed.
- `config/v6_templates/` — deleted climate/defense/housing/trade.json; authored policy/tech/due_diligence/custom.json (full `TemplateContent`, schema-valid, registry-loaded).
- `web/lib/api.ts`, `web/app/page.tsx`, `web/app/dashboard/page.tsx` — frontend `TemplateId` / template cards / fallback → canonical 8.
- `scripts/v6/benchmark/api_benchmark_runner.py` — `CARNEY_TEMPLATES` → canonical 8.

**Drift guard (NEW):** `tests/v6/test_template_canonical_set.py` — asserts exact set-equality of the canonical 8 across all 11 id-carrying surfaces.

**Test/fixture re-key (empirical — §3b):** ~13 test files re-keyed; v30 golden fixtures regenerated via the deterministic synthesizer for the canonical 4; 6 baseline/evidence fixtures relabelled (`relabel_to_canonical`); 4 e2e specs re-keyed (palette inputs verified against `command_palette.tsx` `score_template`).

## §3. Empirical verification (the §3b GREEN bar)

- `tests/v6/test_template_canonical_set.py` drift guard — **11/11 pass**.
- `pytest tests/v6/ tests/polaris_v6/` — **516 passed, 0 failed**.
- `pytest tests/polaris_graph/` — **4585 passed**; 15 failures are **pre-existing** (content-preservation `test_m42/m49_*`, entailment-judge, demo-smoke — env/data-dependent; none reference templates; verified absent from the I-rdy-005 import closure). I-rdy-005 introduces **zero** new Python failures.
- Playwright e2e: 4 specs re-keyed; CI `e2e` job validates (browser run not done locally).

## §4. Verify
1. Every id-carrying surface is the canonical 8; no `climate/defense/housing/trade` remains as a template id (the 2 e2e hits — `golden_climate_005` run-id, "housing starts" content text — are non-template).
2. The 4 new `v6_templates` JSON are sound `TemplateContent` (real content, no placeholders).
3. The diff introduces no new test failures; the drift guard genuinely enforces.
4. No I-gen-003 / unrelated contamination.

## §5. Output schema (CLAUDE.md §8.3.9)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
verdict_reasoning: <text>
```
