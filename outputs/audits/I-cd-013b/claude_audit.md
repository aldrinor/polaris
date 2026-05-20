# I-cd-013b — Claude architect audit

**Issue:** GH#669 — migrate legacy `/inspector/*` Playwright suite + Playwright snapshot config.
**Deliverable:** 11 files / +141 / -313 / **-172 net LOC** (more deletes than adds; migration not rewrite).
**Deps:** I-cd-013a (PR #670, MERGED) ✓.

## What this PR ships

### Production component patches (WCAG 2.5.8)
- `web/components/inspector/verified_report_sections.tsx:105` — `toggle-provenance-tokens` button: added `min-h-6 px-2 py-1` + `rounded-sm` for ≥24×24 hit target.
- `web/components/inspector/reasoning_trace_timeline.tsx:99` — `toggle-trace-content` button: same patch.

### Legacy quarantine cleanup (5 .spec.ts files + 3 baseline PNGs)
- `inspector.spec.ts` — full rewrite; deleted 3 Inspector describes; preserved Dashboard scope-discovery describe.
- `visual.spec.ts` — full rewrite; deleted 2 Inspector describes; preserved dashboard.
- `visual.spec.ts-snapshots/inspector-{executive-summary,verified-sentences,error-state}-chromium-win32.png` — DELETED.
- `performance.spec.ts` — full rewrite; deleted 4 Inspector describes; added 2 new (cold load + FCP) against `v1-canonical-success`.
- `performance_hover.spec.ts` — FILE DELETED (the 1000ms hover-to-tooltip budget targeted a UX surface that no longer exists in the rebuilt Inspector).
- `accessibility.spec.ts` — surgical:
  - Replaced 3 legacy Inspector axe describes with new `"WCAG-AA — Inspector (signed-bundle, post-I-cd-013a)"` covering v1-canonical-success (Report + Reasoning + Hash chain tabs) + v1-canonical + bundle-pending CTA.
  - The legacy `/inspector/<bad-runid>` error-banner axe test was MIGRATED into the new describe as the CTA axe-clean assertion.
  - The WCAG 2.5.8 target-size `test.skip` migrated to a sweep against v1-canonical-success Reasoning tab.
  - The `/runs/<bad-runid>` axe test EXTRACTED to a new `"WCAG-AA — Run-detail error states"` describe (Codex iter-1 P2 #2 catch — that test was inside the Inspector quarantine describe but targets the `/runs/[runId]` route at I-cd-025).
  - Documented why the `drop_reason` legacy a11y test was deleted (intent preserved as a follow-up when verified_sentences renders drop_reason annotations).

### New visual baselines (deferred to first Playwright run)
- `inspector_route.spec.ts` extended with 3 visual baseline tests (success-Report, abort, pending-CTA). Auto-write on first `--update-snapshots` run; commit in a follow-up.

### Config
- `playwright.config.ts` — re-add `**/inspector_route.spec.ts` to Linux `testIgnore` (chromium-win32 baselines only).

## #669 acceptance

| Criterion | Status |
|---|---|
| All legacy `/inspector/golden_*` Playwright assertions migrated/replaced/deleted with justification | YES — 3 describes deleted in inspector.spec.ts + 3 in accessibility + 2 in visual + 4 in performance + 1 file deleted (performance_hover); intents preserved where applicable. |
| `playwright.config.ts` snapshot resolution wired | YES — re-added inspector_route.spec.ts to Linux testIgnore (matches existing visual.spec.ts convention). No `snapshotPathTemplate` change (default-adjacent location preserved per I-cd-013a iter-3 P2 #2). |
| Legacy `inspector-*-chromium-win32.png` baselines migrated/deleted | YES — 3 PNGs deleted. |
| `accessibility.spec.ts` covers new Inspector route a11y | YES — new "WCAG-AA — Inspector (signed-bundle)" describe covers 5 test cases on the new route. |
| Full Playwright suite green on post-I-cd-013a HEAD | EXPECTED YES (full e2e + visual deferred to CI — visual baselines auto-write on first `--update-snapshots` run). |

## Codex brief trajectory

| Iter | Verdict | Key adds |
|---|---|---|
| 1 | RC | 1 P1 (WCAG 2.5.8 ≥24×24 on 2 reveal buttons) + 3 P2 (playwright.config.ts text inconsistency; preserve /runs/ axe test; measure perf before tightening) |
| 2 | **APPROVE** | novel_p0=0 / continuing_p0=0 / p1=0; 3 P2 non-blocking (continuing /runs/ catch verified + migrated; CI gate scope; capture_screenshots.mjs follow-up) |

## Risk surface

- **Production component patches (2 buttons)**: pure CSS classes, ZERO behavioral change.
- **Test deletions**: legacy tests targeted UI that no longer exists; intent preserved as new tests where applicable.
- **Performance budget relaxation**: 2000ms DOMContentLoaded + 1500ms FCP vs 1000ms/800ms legacy. First CI run produces observed numbers; follow-up PR tightens.
- **Visual baselines auto-write**: 3 new baselines auto-generated on first `--update-snapshots` Playwright run; committed in a follow-up PR or by operator-manual capture.

## Smoke

| Check | Result |
|---|---|
| `cd web && npm run typecheck` | clean (0 errors) |
| `cd web && npm run lint` | clean (2 pre-existing warnings unrelated) |
| `prettier --check` on changed files | clean |
| Full Playwright e2e + visual | DEFERRED to CI; visual baselines auto-write on first --update-snapshots |

## Scope discipline

Out of scope per Codex iter-2 accept_remaining:
- `web/scripts/capture_screenshots.mjs` legacy `/inspector/golden_*` refs → follow-up if the script remains supported.
- Ubuntu CI execution of the target-size sweep → Windows/manual visual acceptance is the convention.
- Tightening perf budgets → follow-up PR after observed CI numbers.
- chromium-linux / firefox / webkit visual baselines → existing convention is chromium-win32 only.
