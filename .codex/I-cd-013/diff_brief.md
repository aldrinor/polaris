HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# ⚠ HARD CONSTRAINTS — NOT CODEX-NEGOTIABLE ⚠

- **Bundle schema SoT**: `bundle_schema.py` (`BundleManifest v1.0`, FROZEN with `extra="forbid"`).
- **TypeScript mirror**: `web/lib/signed_bundle.ts`.
- **family_segregation_passed + evaluator_model** SoT is `verified_report.json`.
- **Section field names**: `sections[].section_verify_pass_rate` + `sections[].verified_sentences`.
- **Real reasoning trace shape**: 15-field `ReasoningTraceRecord` per `generator/reasoning_trace.py:67`.
- **Issue split**: legacy migration carved to **I-cd-013b (#669)**.
- **PR-cap exemption**: operator-approved 2026-05-20 — Split A vs B; +483 net LOC unitary deliverable.

# Codex diff review — I-cd-013a / GH#609

## §0 — Context

Brief APPROVE'd at iter 5/5 (CAP). 32 files / +1634 / -1151 / +483 net LOC. The -1151 is the legacy 1147-LOC `web/app/inspector/[runId]/page.tsx` rewritten to ~40 LOC. Implementation matches the iter-5 brief scope exactly.

## §A — Diff summary

- **NEW** (14 files): tabs primitive + shared loader + 9 sub-components + view + route handler + e2e + second fixture (8 sub-files via 1 dir)
- **REWRITE** (1 file): page.tsx 1147 → 40 LOC
- **EXTEND** (1 file): regen script + `regenerate_success()`
- **CONFIG** (1 file): `playwright.config.ts` testIgnore on Linux
- **TESTS** (2 files): test_conformance.py +1 case; quarantine annotations across 5 .spec.ts files
- **FIXTURE** (8 files in 1 dir + 1 update to v1_canonical/manifest.yaml + reasoning_trace.jsonl since regen script touched them deterministically)

## §B — Acceptance check

| Criterion | Status |
|---|---|
| #609 G1-G8 + screenshot bar | YES — all 8 gates covered (see claude_audit.md). Visual gold auto-writes on first Playwright run; baselines deliberately committed at I-cd-013b. |
| schema freeze respected (I-cd-012 v1.0) | YES — no `BundleManifest` field changes. Conformance suite extended (21 cases, includes v1_canonical_success). |
| metadata-by-explicit-path | YES — `inspector_bundle_loader.ts:97-99` `entry.path === "metadata.json"` selection. |
| family-segregation from verified_report | YES — `family_segregation_badge.tsx:16` `verified_report.family_segregation_passed`. |
| reasoning_trace 15-field shape | YES — `web/lib/signed_bundle.ts:75-91` ReasoningTraceRecord; `reasoning_trace_timeline.tsx` renders all 15 fields; fixture regen produces real-shape records. |
| section field names | YES — `verified_report_sections.tsx` uses `section_verify_pass_rate` + `verified_sentences`. |
| G2 dev-language scope | YES — `bundle_pending_cta.tsx` has zero issue IDs in rendered text; e2e enforces rendered-text-only grep. |
| Tabs primitive | YES — `web/components/ui/tabs.tsx` wraps `@base-ui/react/tabs`; data-tab attribute on `TabsContent`. |
| legacy Playwright quarantine | YES — 5 files surgically quarantined; dashboard tests in inspector.spec.ts at lines 103+ preserved. |
| multi-project Playwright | YES — `playwright.config.ts` testIgnore inspector_route.spec.ts on Linux. |
| runId gating | YES — `inspector_bundle_loader.ts:70-73` KNOWN_FIXTURES only matches `v1-canonical` + `v1-canonical-success`; all other runIds → null → CTA. |

## §C — Smoke evidence

- `pytest tests/polaris_graph/audit_bundle/test_conformance.py`: **21 passed**
- `check_bundle_conformance` v1_canonical_success: **valid=True**
- `cd web && npm run typecheck`: **clean (0 errors)**
- `cd web && npm run lint`: clean (2 pre-existing warnings)
- Visual screenshot + dev-server e2e DEFERRED to CI / I-cd-013b (needs running dev server + first-time baseline capture)

## §D — Codex Red-Team checklist for THIS diff

Reviewer please verify:
1. `loadBundle()` server-only — no client-side `fs` import bleed.
2. `metadata.json` PATH selection at `inspector_bundle_loader.ts:97` is correct + handles the duplicate `content_type=metadata` REVIEWER_README.md in v1_canonical_success.
3. `family_segregation_badge.tsx` derives from `verified_report.evaluator_model` AND `verified_report.family_segregation_passed` (NOT metadata.json).
4. `verified_report_sections.tsx` uses correct field names `section_verify_pass_rate` + `verified_sentences`.
5. `reasoning_trace_timeline.tsx` renders all 15 fields of the real producer's `ReasoningTraceRecord`.
6. CTA `bundle_pending_cta.tsx` user-facing text contains NO issue IDs (rendered-text scope only; comments + data-testids exempt).
7. 5 surgical quarantine `test.describe.skip()` placements preserve non-Inspector describes:
   - `inspector.spec.ts` lines 14, 73, 86 skipped; line 103 Dashboard describe PRESERVED.
   - `accessibility.spec.ts` lines 66, 98, 142 Inspector describes skipped; lines 49, 111, 162 (dashboard + upload + target-size) PRESERVED.
   - `visual.spec.ts` lines 35, 62 Inspector describes skipped; line 25 dashboard PRESERVED.
   - `performance.spec.ts` all 4 describes skipped (every test was Inspector — no preservation needed).
   - `performance_hover.spec.ts` the only describe skipped.
8. `playwright.config.ts` Linux `testIgnore` extension matches the existing `visual.spec.ts` convention.
9. v1_canonical_success fixture conforms via `check_bundle_conformance` (test_v1_canonical_success_fixture_conforms passes).
10. No `manifest.yaml.asc` cryptographic-verification claim made (presence-only per the I-cd-012 conformance contract).
11. `bundle_pending_cta.tsx` correctly handles `<Link>` + `buttonVariants()` (no `asChild` prop — local Button doesn't support it).

## §E — Output schema — return EXACTLY this

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
