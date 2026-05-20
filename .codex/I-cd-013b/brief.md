HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# ⚠ HARD CONSTRAINTS — NOT CODEX-NEGOTIABLE ⚠

- **I-cd-013a (#609) MERGED** (PR #670, squash `576ae78b0edb`).
- **Strict global sequence** — operator chose I-cd-013b before I-cd-014 on 2026-05-20.

# Codex brief review — I-cd-013b / GH#669

Closes #669.

## §0 — Iter-1 fold-in (Codex iter-1 verdict REQUEST_CHANGES; 1 P1 + 3 P2)

**iter-1 P1 (WCAG 2.5.8 fix)**: the new Inspector has 2 `text-xs` reveal buttons without ≥24×24 sizing — `verified_report_sections.tsx:105` `toggle-provenance-tokens` + `reasoning_trace_timeline.tsx:99` `toggle-trace-content`. Resolution: ADD `min-h-6 px-2 py-1` Tailwind classes to both buttons. Production component patch is in scope of THIS issue (the target-size sweep we're migrating IS the gate that flags them; fixing the buttons + adding the sweep landing on the new Inspector is unitary). NO scope creep — these 2 patches close the gate.

**iter-1 P2 #1 (playwright.config.ts inconsistency)**: my iter-1 brief said "No change" in the table but "re-add inspector_route.spec.ts to Linux testIgnore" in the text. Resolution: ADD `**/inspector_route.spec.ts` to the Linux `testIgnore` list (matches existing `visual.spec.ts` convention). Visual baselines are chromium-win32 only.

**iter-1 P2 #2 (Inspector-error-states migration)**: the legacy accessibility test at `accessibility.spec.ts:281` hits `/inspector/does_not_exist_runid_404` (verified via grep — only `/inspector/*`, no `/runs/...` reference per my local check). The test intent is "axe-clean on the destructive/info-state surface for an unknown runId." Resolution: MIGRATE (not delete) — add a new `describe` in `accessibility.spec.ts` `"WCAG-AA — Inspector v1-canonical-success + pending CTA (signed-bundle)"` asserting axe-clean on:
   - `/inspector/v1-canonical-success` (success-shape rendered Inspector)
   - `/inspector/v1-canonical` (abort-shape rendered Inspector)
   - `/inspector/does-not-exist` (the new CTA surface — preserves the axe coverage of the destructive/info-state surface).

**iter-1 P2 #3 (perf budget measurement)**: I-cd-013a's loader does `fs.readFile` on local fixtures — fast in practice but unmeasured. Resolution: set wider initial budgets WITH a comment to measure-and-tighten in a follow-up. DOMContentLoaded < 2000ms; FCP < 1500ms. The first CI run will produce observed numbers; a future PR tightens.

## §A — Final scope: 9 file edits + 3 visual-baseline deletions

| # | File | Action |
|---|---|---|
| 1 | `web/components/inspector/verified_report_sections.tsx:105` | Add `min-h-6 px-2 py-1` to the toggle-provenance-tokens button (WCAG 2.5.8). |
| 2 | `web/components/inspector/reasoning_trace_timeline.tsx:99` | Add `min-h-6 px-2 py-1` to the toggle-trace-content button (WCAG 2.5.8). |
| 3 | `web/tests/e2e/inspector.spec.ts` | Delete 3 quarantined Inspector describes (lines 14, 73, 86). Preserve Dashboard scope-discovery describe at line 103+. |
| 4 | `web/tests/e2e/accessibility.spec.ts` | Delete 3 full quarantined Inspector describes (golden_clinical_001, golden_housing_002, drop_reason) + the surgical `test.skip` at line 211 (target-size sweep test for Inspector) + the full quarantined "WCAG-AA — Inspector error states" describe. **Add** new describe `"WCAG-AA — Inspector v1-canonical-success / v1-canonical / pending CTA (signed-bundle, post-I-cd-013a)"` with axe-clean assertions on all 3 fixtures. **Preserve** dashboard + upload-list + target-size-dashboard + keyboard-sweep describes. |
| 5 | `web/tests/e2e/visual.spec.ts` | Delete 2 quarantined Inspector describes. Preserve dashboard describe. |
| 6-8 | `web/tests/e2e/visual.spec.ts-snapshots/inspector-{executive-summary,verified-sentences,error-state}-chromium-win32.png` | DELETE 3 legacy baselines. |
| 9 | `web/tests/e2e/performance.spec.ts` | Delete all 4 quarantined describes. **Add** new describes: "Performance — Inspector cold load on v1-canonical-success" (DOMContentLoaded < 2000ms; relaxed initial budget per iter-1 P2 #3) + "Performance — Inspector FCP on v1-canonical-success" (< 1500ms). Drop Charts-tab + tab-switch-latency cases (no Charts tab; tab-switch UX is different). |
| 10 | `web/tests/e2e/performance_hover.spec.ts` | DELETE the file (hover-to-tooltip latency UX no longer exists; new provenance-token reveal is keyboard-accessible click). |
| 11 | `web/tests/e2e/inspector_route.spec.ts` | Extend with: (a) per-fixture axe-clean assertion via `AxeBuilder`; (b) per-fixture `toHaveScreenshot()` baselines committed at adjacent `inspector_route.spec.ts-snapshots/`; (c) WCAG 2.5.8 target-size sweep on `/inspector/v1-canonical-success`. |
| 12 | `web/playwright.config.ts` | Add `**/inspector_route.spec.ts` to Linux `testIgnore` (iter-1 P2 #1 fix — chromium-win32 baselines only). |

## §B — What this PR does NOT do

- Add NEW test intents beyond axe + visual + perf + target-size (the preserved categories).
- Snapshot `snapshotPathTemplate` config refactor — keep Playwright default-adjacent location (matches every existing visual test). The original I-cd-013b carve-out mentioned this, but I-cd-013a iter-3 P2 #2 confirmed default-adjacent is the right convention.
- Address Codex diff iter-2 P2 of I-cd-013a's REPO_ROOT process.cwd()/.. observation — that's deferred to I-B-08.
- Address Codex diff iter-2 P2 of I-cd-013a's provenance-token click-through observation — that's deferred to a span_indexer follow-up.
- Add chromium-linux / firefox / webkit visual baselines — chromium-win32 only per existing convention.
- Tighten the perf budgets — first CI run produces observed numbers; follow-up PR tightens.

## §C — Smoke + acceptance

- `cd web && npm run lint && npm run typecheck && npm run format:check` — clean.
- `cd web && npx playwright test --project=chromium tests/e2e/inspector_route.spec.ts` — passes including the new axe + visual + target-size cases.
- `cd web && npx playwright test --project=chromium tests/e2e/accessibility.spec.ts` — passes (new Inspector axe describe + preserved dashboard/upload/target-size/keyboard describes; quarantine deletions clean).
- `cd web && npx playwright test --project=chromium` — full suite green.

## §D — Risk surface

- **Production component patch (2 buttons)**: adds Tailwind classes for WCAG 2.5.8 compliance. ZERO behavioral change; CSS-only.
- **Visual baseline deletions**: 3 legacy PNGs are now uncovered. Their replacements (3 new chromium-win32 baselines) auto-write on first Playwright `--update-snapshots` run.
- **Performance budgets**: wider than legacy AuditIR (2000ms vs 1000ms). First CI run produces observed numbers; tightening at follow-up.
- **performance_hover.spec.ts deletion**: removes hover-tooltip latency budget. Hover tooltip UX no longer exists; budget is meaningless.

## §E — Residual questions for Codex iter-2

1. iter-1 P1 (button target-size fix) folded — `min-h-6 px-2 py-1` Tailwind classes the right minimum? Or should this go through the Button component with `size="xs"` (h-7 in `buttonVariants`, which IS ≥24px)?
2. iter-1 P2 #2 — migrating Inspector error states axe to the new CTA surface, NOT deleting — confirmed as the right call?
3. iter-1 P2 #3 — relaxed budgets (2000 / 1500) with measure-and-tighten follow-up — acceptable, OR measure first?
4. Any test files I missed that would still reference the legacy /inspector/golden_* routes after this deletion sweep?

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
