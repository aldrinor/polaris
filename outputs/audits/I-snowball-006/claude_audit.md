# Claude architect audit — I-snowball-006

**Canonical PR diff SHA256:** `be3159105dbc577463706677921af79c6d9ec47da07003e7ff853a7c7aa03dcc`

## Acceptance criteria

| Criterion | Status |
|---|---|
| `exportPNG(cy)` returns Blob via cy.png 4x | ✓ |
| `exportJSON(payload)` canonical (positions-stripped, sorted-by-id, sort_keys) | ✓ |
| Toolbar PNG + JSON buttons | ✓ |
| Playwright e2e (5 cases, mocked fetch) | ✓ |
| Hermetic fixture in repo | ✓ |

## Codex P1 + P2 fixes applied
- Playwright `download.suggestedFilename()` + `.toMatch(/\.png$/)` (not toHaveSuffix)
- LOC: claim_graph.tsx kept under 200 via small onCyReady callback prop (~6 lines added; net within cap)
- JSON canonicalization uses raw `<`/`>` comparator (not localeCompare) + recursive key sort + position strip
- Mocked fetch via `page.route` shipped in this PR

## Deferred
- Audit-bundle backend integration (server posts PNG/JSON to bundle)
- axe-core WCAG-AA test
- Lighthouse perf gate (LCP/INP/first-paint)

## Smoke
`npm run typecheck` PASS

## Verdict
SHIP.
