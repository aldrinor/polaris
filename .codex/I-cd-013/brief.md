HARD ITERATION CAP: 5 per document. This is iter 5 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# ⚠ HARD CONSTRAINTS — NOT CODEX-NEGOTIABLE ⚠

- **Bundle schema SoT**: `bundle_schema.py` (`BundleManifest v1.0`, FROZEN with `extra="forbid"`).
- **TypeScript mirror**: `web/lib/signed_bundle.ts`.
- **App shell + design tokens**: per I-A-02.
- **family_segregation_passed + evaluator_model** SoT is `verified_report.json` (CONFIRMED iter-4 P2 #2).
- **Section field names**: `sections[].section_verify_pass_rate` + `sections[].verified_sentences` (CONFIRMED iter-4 P2 #2).
- **Tabs primitive**: `@base-ui/react ^1.4.1` is in deps; new wrapper at `web/components/ui/tabs.tsx`.
- **Issue split**: legacy migration carved to **I-cd-013b (#669)**.
- **PR-cap exemption**: operator-approved 2026-05-20 — Split A vs B; ~1000 LOC unitary deliverable.

# Codex brief review — I-cd-013a / GH#609

Closes #609.

## §0 — Iter trajectory + iter-4 fold-in

- **iter 1** RC: 2 P1 (runId gating + family badge source) + 3 P2.
- **iter 2** RC: 2 P1 (legacy Playwright scope + visual-gold path) + 3 P2.
- **iter 3** RC: 2 P1 (continuing legacy tests + multi-project Playwright) + 4 P2.
- **iter 4** RC: 1 NEW P1 (`visual.spec.ts:35-68` legacy Inspector cases) + 2 P2 (surgical-not-blanket quarantine + field name confirmation).
- **iter 5** (this iter, cap): all distinct findings folded; quarantine list narrowed per real grep evidence.

**iter-4 P1 (visual.spec.ts:35-68)**: confirmed via local grep — `web/tests/e2e/visual.spec.ts` references `/inspector/golden_clinical_001` (lines 37, 48) + `/inspector/does_not_exist_runid_404` (line 64). Resolution: surgical quarantine of these 3 inspector-related test cases inside visual.spec.ts via `test.skip(true, "Legacy AuditIR Inspector cases — migrated by I-cd-013b (#669)")` or equivalent describe-block skip; PRESERVE the dashboard + other visual cases. Keep `web/tests/e2e/visual.spec.ts-snapshots/inspector-*` baselines on disk for I-cd-013b to migrate or delete.

**iter-4 P2 (surgical quarantine — verified by local grep)**:
- **Full quarantine** (`/inspector/*` is the entire test surface): `inspector.spec.ts`.
- **Surgical quarantine** (mixed file; quarantine `/inspector/*` cases only):
  - `accessibility.spec.ts` — 7 `/inspector/*` references (golden_clinical_001 × 4, golden_climate_005, golden_housing_002, golden_with_drop_reason, does_not_exist_runid_404).
  - `visual.spec.ts` — 3 `/inspector/*` references (per iter-4 P1).
  - `performance.spec.ts` — 6 `/inspector/*` references.
  - `performance_hover.spec.ts` — 2 `/inspector/*` references.
- **No quarantine needed** (`/inspector/*` count = 0 per local grep): `sentence_inspector.spec.ts`, `sentence_inspector_adversarial.spec.ts`, `multi_source_panel.spec.ts`, `chart_click_through.spec.ts`, `p2c_001_chain.spec.ts`, `f1_a11y.spec.ts`. These use harness routes (`/sentence_hover_test`, etc.), NOT `/inspector/*`.

**iter-4 P2 (field name confirmation)**: explicit acknowledgement — `sections[].section_verify_pass_rate` + `sections[].verified_sentences` are correct AND `evaluator_model` + `family_segregation_passed` live on `VerifiedReport` (NOT metadata.json). No further change needed.

## §A — Final scope: 1 shared loader + 1 page rewrite + 1 client view + 9 sub-components + 1 Tabs primitive + 1 route handler + 2 fixture sets + 1 e2e test + 3 visual goldens + 5 legacy-test surgical quarantines

**A1. Shared bundle loader (server-only)** — `web/lib/inspector_bundle_loader.ts` NEW.

**A2. Tabs primitive** — `web/components/ui/tabs.tsx` NEW (wraps `@base-ui/react/tabs`).

**A3. Page + interactive view** — `web/app/inspector/[runId]/page.tsx` REWRITE (1147 → ~200 LOC) + `web/app/inspector/[runId]/inspector_view.tsx` NEW.

**A4. Sub-components**:
- `web/components/inspector/bundle_header.tsx`
- `web/components/inspector/family_segregation_badge.tsx` (from `verified_report.evaluator_model` + `verified_report.family_segregation_passed`)
- `web/components/inspector/scope_decision_card.tsx`
- `web/components/inspector/evidence_pool_table.tsx`
- `web/components/inspector/verified_report_sections.tsx` (uses `sections[].section_verify_pass_rate` + `sections[].verified_sentences` per real schema)
- `web/components/inspector/reasoning_trace_timeline.tsx`
- `web/components/inspector/sources_panel.tsx`
- `web/components/inspector/hash_chain_panel.tsx`
- `web/components/inspector/bundle_pending_cta.tsx` (user-facing copy NO dev-language)

**A5. Stub API route handler** — `web/app/api/inspector_bundle/[runId]/route.ts` NEW.

**A6. Two canonical fixtures**:
- `tests/fixtures/signed_bundle/v1_canonical_success/*` NEW (9 files; pipeline_verdict=success + 2 populated Sections + REVIEWER_README.md as second metadata content_type).
- `scripts/regen_signed_bundle_canonical_fixture.py` EXTEND with `regenerate_success()`.

**A7. New Inspector e2e + visual golds**:
- `web/tests/e2e/inspector_route.spec.ts` NEW. Per-tab assertions + G1-G8 (G2 rendered-text scope). Visual cases gated to chromium via `test.skip(testInfo.project.name !== "chromium", "...")`.
- `web/tests/e2e/inspector_route.spec.ts-snapshots/inspector-v1-canonical-success-chromium-win32.png` NEW.
- `web/tests/e2e/inspector_route.spec.ts-snapshots/inspector-v1-canonical-chromium-win32.png` NEW.
- `web/tests/e2e/inspector_route.spec.ts-snapshots/inspector-pending-chromium-win32.png` NEW.
- `web/playwright.config.ts` — add `inspector_route.spec.ts` to `testIgnore` under Linux (matches existing `visual.spec.ts` convention).

**A8. Legacy-test surgical quarantine (verified scope)**:

| File | Quarantine action |
|---|---|
| `web/tests/e2e/inspector.spec.ts` | Full-file `test.describe.skip(...)` |
| `web/tests/e2e/accessibility.spec.ts` | Surgical — each `/inspector/*` test annotated `test.skip(true, "Legacy AuditIR Inspector — migrated by I-cd-013b (#669)")` |
| `web/tests/e2e/visual.spec.ts` | Surgical — lines 35-68 Inspector describe blocks `.skip()` |
| `web/tests/e2e/performance.spec.ts` | Surgical — 6 `/inspector/*` cases annotated `.skip()` |
| `web/tests/e2e/performance_hover.spec.ts` | Surgical — 2 `/inspector/*` cases annotated `.skip()` |

All other Playwright files (`sentence_inspector*`, `multi_source_panel`, `chart_click_through`, `p2c_001_chain`, `f1_a11y`) are NOT touched — their tests don't hit `/inspector/*` per grep evidence.

**A9. Conformance test extension** — `tests/polaris_graph/audit_bundle/test_conformance.py` adds `test_v1_canonical_success_fixture_conforms` (22 cases total).

## §B — What this PR does NOT do

- Legacy `/inspector/*` Playwright **migration** → I-cd-013b (#669). Quarantined-but-preserved in THIS PR.
- `playwright.config.ts snapshotPathTemplate` → I-cd-013b.
- Real-bundle backend wiring → I-B-08.
- Offline fallback → I-B-09.
- `/runs/[runId]` rebuild → I-cd-025.
- Sign-in / auth wiring → I-cd-014.
- Sentence-level provenance-token → span tooltip → span_indexer follow-up.
- AuditIR type definitions removal → I-cd-025+.

## §C — Smoke + acceptance

- `pytest tests/polaris_graph/audit_bundle/test_conformance.py` (22 cases).
- `cd web && npx prettier --write app/inspector/[runId]/*.tsx components/inspector/*.tsx components/ui/tabs.tsx lib/inspector_bundle_loader.ts app/api/inspector_bundle/[runId]/route.ts tests/e2e/inspector_route.spec.ts`
- `cd web && npm run lint && npm run typecheck && npm run build`
- `cd web && npx playwright test tests/e2e/inspector_route.spec.ts --project=chromium`
- `cd web && npx playwright test --project=chromium` — full suite green (5 quarantine files + 8 new files; no other regression).

## §D — Risk surface (final)

- **Legacy quarantine markers preserve test files for I-cd-013b** — no test intent lost.
- **Visual gold at default `__snapshots__`-adjacent location** — matches existing visual.spec.ts convention; no Playwright config refactor needed.
- **Multi-project gating** — visual screenshots restricted to chromium via per-test skip; G1-G8 non-screenshot assertions run on all projects.
- **Tabs primitive** wraps existing `@base-ui/react ^1.4.1` dep — no new package.
- **Two fixtures** — abort + success — both round-trip through `check_bundle_conformance`. Conformance suite extended to 22 cases.

## §E — Residual question for Codex iter-5 (the cap)

Is the **5-file surgical quarantine list** (inspector + accessibility + visual + performance + performance_hover) exhaustive per the actual `/inspector/*` grep, with the other Playwright files genuinely untouched?

If iter 5 returns REQUEST_CHANGES with anything other than another newly-discovered legacy-test reference, Claude force-APPROVE's per CLAUDE.md §8.3.1 and ships with residuals captured as follow-up Issues. Per the 5-cap, this is the binding iteration.

## §F — Output schema — return EXACTLY this

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
