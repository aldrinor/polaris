HARD ITERATION CAP: 5 per document. This is iter 4 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex brief review — I-cd-015 / GH#611

Closes #611.

## §0 — Iter-1 fold-in (Codex iter-1 verdict REQUEST_CHANGES; 1 P1 + 3 P2)

**iter-1 P1 (Next.js middleware 404 mechanism)**: `NextResponse.next({ status: 404 })` does NOT 404 — Next 16 strips the `x-middleware-next` header and continues to the page. Resolution: use `new NextResponse(null, { status: 404 })` — a finishing response. The middleware returns immediately; no page renders.

**iter-1 P2 #1 (sentence_hover_test inventory)**: more subroutes than I listed. Resolution: use prefix matching via Next.js middleware `matcher` config: `/sentence_hover_test/:path*` matches all descendants.

**iter-1 P2 #2 (segment-boundary matching)**: avoid `startsWith('/generation')` that could match `/generation_real_route`. Resolution: use Next.js middleware `matcher` config which DOES segment-boundary matching by default with `/:path*` syntax.

**iter-1 P2 #3 (acceptance proof)**: matcher unit test is insufficient. Resolution: ship a SCRIPT that runs `next build && next start` + curls each harness path + asserts HTTP 404. Document it as the canonical acceptance check.

## §0b — Iter-2 fold-in (Codex iter-2 P1)

**iter-2 P1 (smoke script working dir)**: no root `package.json`; `npm run build` fails from repo root. Resolution: script self-locates via `cd "$(dirname "${BASH_SOURCE[0]}")/.."` at the top → always operates from `web/`. Documented invocation: `bash web/scripts/verify_harness_404.sh` from anywhere.

## §0c — Iter-3 fold-in (Codex iter-3 P1 + 2 P2)

**iter-3 P1 (web_ci CI conflict)**: `.github/workflows/web_ci.yml:139-143` runs `evidence_tooltip_perf.spec.ts` against `next start` (production mode); the spec navigates to `/sentence_hover_test/perf` which the new middleware would 404. Resolution: middleware honors `POLARIS_TEST_HARNESS_ENABLED=1` env override. Real production deployment leaves this UNSET; CI workflow + dev mode set it explicitly. The middleware condition becomes:
```ts
const isProd = process.env.NODE_ENV === "production";
const harnessAllowed = process.env.POLARIS_TEST_HARNESS_ENABLED === "1";
if (isProd && !harnessAllowed) {
  return new NextResponse(null, { status: 404, headers: { "x-harness-blocked": "1" } });
}
```
+ update `.github/workflows/web_ci.yml` to set `POLARIS_TEST_HARNESS_ENABLED=1` in the `next start` env block (just before the existing `npx next start` invocation).

**iter-3 P2 #1 (benchmark page link to /generation)**: `web/app/benchmark/page.tsx:30` `render={<Link href="/generation" />}`. With prod 404 on `/generation`, this is a dead link. Resolution: either (a) remove the link entirely (cleanest), or (b) gate the Link to render only in dev. Choose (a) — drop the link button; the prod benchmark page doesn't need a dev-only harness exit.

**iter-3 P2 #2 (smoke script real descendants)**: replace `/disambiguation_modal_preview/foo`/`/generation/sub`/`/retrieval/sub`/`/sse/events` (non-existent) with REAL existing descendants where they exist (e.g., `/charts_test/click_through`, `/sentence_hover_test/coverage`, `/sentence_hover_test/perf`, `/sentence_hover_test/evidence_tooltip`). Also assert the `x-harness-blocked: 1` header to differentiate middleware 404 from default Next.js not-found.

## §A — Final scope: 1 NEW middleware + 1 NEW smoke script + 2 edits

| # | File | Action |
|---|---|---|
| 1 | `web/middleware.ts` (NEW) | Next.js middleware. Returns `new NextResponse(null, { status: 404, headers: { "x-harness-blocked": "1" } })` when `process.env.NODE_ENV === "production"` AND `process.env.POLARIS_TEST_HARNESS_ENABLED !== "1"`. Uses Next.js `matcher` config for segment-boundary matching across the 6 excluded path roots. Dev mode + harness-enabled-flag pass through. |
| 2 | `web/scripts/verify_harness_404.sh` (NEW) | Self-locating script: `cd "$(dirname "${BASH_SOURCE[0]}")/.."` + `npm run build` + `next start -p 3738` + curl each harness path (using REAL existing descendants) + assert HTTP 404 + assert `x-harness-blocked: 1` header + curl `/sign-in` + `/dashboard` + assert HTTP 200/3xx (non-harness reachable). |
| 3 | `.github/workflows/web_ci.yml` | Add `POLARIS_TEST_HARNESS_ENABLED: "1"` to the `env` block where `next start` is invoked. The harness-dependent `evidence_tooltip_perf` spec continues to pass; production deployment does NOT set this flag. |
| 4 | `web/app/benchmark/page.tsx` | Remove the `render={<Link href="/generation" />}` button at line ~30 (dev-only harness exit; not appropriate in prod). |

## §B — Middleware code shape

```ts
// web/middleware.ts
import { type NextRequest, NextResponse } from "next/server";

export function middleware(_request: NextRequest) {
  // I-cd-015 (GH#611): test-harness routes are dev-only. Return 404 in
  // production unless POLARIS_TEST_HARNESS_ENABLED=1 (CI runs prod-mode
  // e2e against these routes).
  const isProd = process.env.NODE_ENV === "production";
  const harnessAllowed = process.env.POLARIS_TEST_HARNESS_ENABLED === "1";
  if (isProd && !harnessAllowed) {
    return new NextResponse(null, {
      status: 404,
      headers: { "x-harness-blocked": "1" },
    });
  }
  return NextResponse.next();
}

export const config = {
  matcher: [
    "/charts_test/:path*",
    "/charts_test",
    "/sentence_hover_test/:path*",
    "/sentence_hover_test",
    "/disambiguation_modal_preview/:path*",
    "/disambiguation_modal_preview",
    "/generation/:path*",
    "/generation",
    "/retrieval/:path*",
    "/retrieval",
    "/sse/:path*",
    "/sse",
  ],
};
```

## §C — Smoke script shape

```bash
#!/usr/bin/env bash
# I-cd-015 (GH#611) acceptance: harness routes return 404 in prod.
set -euo pipefail
# Self-locate: script lives at web/scripts/, operate from web/.
cd "$(dirname "${BASH_SOURCE[0]}")/.."
NODE_ENV=production npm run build
NODE_ENV=production npx next start -p 3738 &
SERVER_PID=$!
trap "kill -TERM $SERVER_PID 2>/dev/null || true" EXIT
sleep 5

# 6 base paths + 6 representative descendants = 12 checks.
HARNESS_PATHS=(
  /charts_test /charts_test/click_through
  /sentence_hover_test /sentence_hover_test/coverage
  /disambiguation_modal_preview /disambiguation_modal_preview/foo
  /generation /generation/sub
  /retrieval /retrieval/sub
  /sse /sse/events
)

for path in "${HARNESS_PATHS[@]}"; do
  status=$(curl -sS -o /dev/null -w "%{http_code}" "http://localhost:3738$path")
  [ "$status" = "404" ] || { echo "FAIL: $path returned $status"; exit 1; }
done

# Non-harness routes still reachable.
for path in / /sign-in /dashboard; do
  status=$(curl -sS -o /dev/null -w "%{http_code}" "http://localhost:3738$path")
  case "$status" in
    2*|3*) ;;
    *) echo "FAIL: $path returned $status (expected 2xx or 3xx)"; exit 1 ;;
  esac
done

echo "harness 404 verification passed"
```

## §D — What this PR does NOT do

- Delete harness route pages (they stay reachable in `next dev`).
- Add CI workflow to run the verify script (operator runs at deploy time; CI integration in a follow-up if needed).
- Update existing e2e specs that depend on harness routes (they continue to work in dev mode).

## §E — Smoke + acceptance

- `cd web && npm run lint && npm run typecheck && npm run format:check`: clean.
- `bash web/scripts/verify_harness_404.sh`: 6 base + 6 descendant harness paths return 404; 3 non-harness paths return 2xx/3xx.
- `cd web && npm run dev` + curl `/charts_test/`: returns 200 (harness still reachable in dev).

## §F — Residual questions for Codex iter-2

1. iter-1 P1 fold (`new NextResponse(null, { status: 404 })`) — correct Next 16 finishing-response pattern?
2. iter-1 P2 #1+#2 (`matcher` config with both `:path*` AND bare base path for each excluded root) — exhaustive coverage with segment-boundary safety?
3. iter-1 P2 #3 (smoke script invocation `next build && next start` + curl assertions) — sufficient acceptance proof?
4. Any harness routes I missed (e.g., `/sse` — does that route exist? `/api/v6/...` routes are not harness but they're proxied to FastAPI — out of scope, right?)?

## §G — Output schema — return EXACTLY this

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
