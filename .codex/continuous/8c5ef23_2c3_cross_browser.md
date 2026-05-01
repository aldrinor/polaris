# Per-commit Codex brief — `8c5ef23`

**Commit:** `8c5ef23 PL: v6.2 Phase 2C.3 cross-browser e2e — 27/27 passing on Chromium+Firefox+WebKit`
**Format:** v2 minimal (`./REVIEW_BRIEF_FORMAT_v2.md`)
**Files changed (2):**
- `web/playwright.config.ts` (+8/-0): added firefox + webkit projects
- `docs/todo_list.md` (+1/-1): marked 2C.3 done

## What this commit does

Adds Firefox and WebKit projects to the Playwright config so the existing 9-test e2e suite runs across all 3 modern rendering engines (Blink/Chromium, Gecko/Firefox, WebKit/Safari).

Verified live against the running backend (port 8000) + Next.js production server (port 3738):
- **Chromium**: 9/9 pass (~10s)
- **Firefox**: 9/9 pass (~13s)
- **WebKit**: 9/9 pass (~13s)
- **Total: 27/27 in 38.0s** (single worker, fullyParallel:false)

This validates that the v6 frontend is genuinely cross-browser and not Chrome-only:
- **Vega-Lite SVG renderer** works in all 3 engines (the most likely cross-browser break point given it does inline SVG manipulation).
- **base-ui Tooltip** primitives render consistently in WebKit (where they sometimes rely on `:popover-open` which Safari shipped late).
- **Scope discovery accept/reject** flow has no engine-specific timing flake.

## Acceptance criteria

1. **Engine coverage.** All 3 projects (chromium, firefox, webkit) defined and use the standard `devices["Desktop Chrome|Firefox|Safari"]` presets — no custom UA spoofing.
2. **No conditional skips per engine.** No `test.skip(browserName === 'webkit', ...)` markers added — all 9 tests must pass on every engine.
3. **No regressions.** Chromium baseline (10.9s for 9 tests) still passes; Firefox/WebKit add roughly 27s combined.
4. **Same fixtures + assertions.** Each engine sees identical EvidenceContract bundles and runs identical assertions (no engine-specific fixture variants).
5. **CI-portable.** Browser binaries are downloaded via the standard `npx playwright install firefox webkit` flow, not vendored.

## Codex focus

- **P0:** Are there any test assertions that ONLY pass because of Chromium-specific behaviour (e.g., text rendering, font metrics, exact whitespace) that we'd want to make more flexible?
- **P0:** WebKit doesn't fully support some CSS features used by Tailwind v4 (e.g., `@property` for animated gradients) — does the visual rendering of the Inspector look identical, or are we masking visual regressions because all assertions are text-based?
- **P1:** `fullyParallel:false` + 1 worker means cross-browser run is now 38s. With more browsers in the future (e.g., mobile Safari), this scales linearly. Should we revisit on CI to allow `--workers=3` (one per browser)?
- **P2:** Should we lock browser binary versions in CI for reproducibility? Currently Playwright auto-resolves to the version that ships with the @playwright/test package.

## Cross-review

Lands at `outputs/audits/continuous/8c5ef23/cross_review.md`.
