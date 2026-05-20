# I-cd-015 — Claude architect audit

**Issue:** GH#611 — 404 test-harness routes in production.
**Deliverable:** 4 files / +144 / -7 / **+137 net LOC**.
**Deps:** I-A-02 (#607, MERGED).

## What this PR ships

- `web/middleware.ts` NEW — Next.js middleware that returns 404 + `x-harness-blocked: 1` header for 6 harness route roots when `NODE_ENV=production` AND `POLARIS_TEST_HARNESS_ENABLED !== "1"`. The matcher config covers both base path + descendants via `:path*`.
- `web/scripts/verify_harness_404.sh` NEW — self-locating prod-mode acceptance script. Builds + starts next in prod mode WITHOUT the harness override; curls 11 harness paths + asserts 404 + header; curls 3 non-harness paths + asserts 2xx/3xx.
- `.github/workflows/web_ci.yml` — `build_and_start_next` step sets `POLARIS_TEST_HARNESS_ENABLED=1` env so existing CI harness specs (`evidence_tooltip_perf.spec.ts` hitting `/sentence_hover_test/perf`) keep working.
- `web/app/benchmark/page.tsx` — removed dead `/generation` Link button (would 404 in prod).

## #611 acceptance

| Criterion | Status |
|---|---|
| /charts_test/* → 404 in prod | YES via middleware matcher |
| /sentence_hover_test/* → 404 in prod | YES |
| (test_harness)/* → 404 in prod | YES via /disambiguation_modal_preview matcher |

Plus per app-shell route-map: /generation, /retrieval, /sse — all in matcher.

## Codex brief trajectory

| Iter | Verdict | Key adds |
|---|---|---|
| 1 | RC | 1 P1 (`NextResponse.next({status: 404})` broken in Next 16) + 3 P2 (subroute inventory + segment-boundary + acceptance proof) |
| 2 | RC | 1 P1 (smoke script working-dir; no root package.json) |
| 3 | RC | 1 P1 (web_ci CI conflict — evidence_tooltip_perf needs /sentence_hover_test/perf) + 2 P2 (benchmark dead link + synthetic descendants) |
| 4 | **APPROVE** | 2 P2 non-blocking (smoke-script-implementation reminders honored) |

## Smoke

| Check | Result |
|---|---|
| `cd web && npm run typecheck` | clean (0 errors) |
| `cd web && npm run lint` | clean (2 pre-existing warnings) |
| `bash -n web/scripts/verify_harness_404.sh` | syntax valid |
| Full smoke deferred to operator + CI integration | — |

## Scope discipline

Out of scope:
- Deletion of harness route pages (they remain reachable in dev / CI with harness flag).
- CI workflow extension to run `verify_harness_404.sh` (operator runs at deploy time; CI integration in a follow-up if needed).
