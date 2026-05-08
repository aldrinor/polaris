# Codex Diff Review — I-f14-003 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only — DO NOT spawn dev servers.

**Issue:** I-f14-003 — Cross-session surfacing
**Brief:** APPROVED iter 1 (zero P0/P1)
**Canonical-diff-sha256:** `01f231ed938a0a9f32011cdf30130e731644f9ee999123ed5612768f53e5c3bb`
**LOC:** 113 net (under CHARTER §3 200-cap)

## Files

```
web/lib/relative_time.ts                         NEW +20  (formatRelative pure helper)
web/app/memory/page.tsx                          +22  (Recent research section above main list)
web/tests/e2e/cross_session_surface.spec.ts      NEW +71  (3 mocked entries, freeze Date.now, assert relative labels)
```

## What changed

### `web/lib/relative_time.ts`
- Pure `formatRelative(iso, nowMs)` helper. Accepts ISO timestamp + optional `nowMs` for test injection.
- Boundaries: <1d=today, 1d=yesterday, 2-6d="N days ago", 7d="last week", 8-13d="N days ago", 14-29d="N weeks ago", 30+d="N months ago".

### `web/app/memory/page.tsx`
- Adds `recent_runs = sorted.filter(e => e.kind === "prior_run_summary")` (sorted desc per Codex iter-1 P2 — newest-first).
- Conditionally renders `<section data-testid="recent-runs">` above the main list when prior_run_summary entries exist.
- Each `<li data-testid="recent-run-{entry_id}">` shows content + relative-time label.

### `web/tests/e2e/cross_session_surface.spec.ts`
- `addInitScript` patches `Date.now` to fixed `2026-05-08T12:00:00Z`.
- Mocks `/workspaces/ws_demo/memory` GET with 3 prior_run_summary entries at days-ago = 1, 5, 14.
- Asserts row labels contain "yesterday", "5 days ago", "2 weeks ago".

## Verification

- `npx tsc --noEmit`: exit 0.
- `npx eslint app/memory/page.tsx lib/relative_time.ts tests/e2e/cross_session_surface.spec.ts`: exit 0.
- `npx prettier --check` on changed files: exit 0.
- `npx next build`: succeeds; `/memory` static prerender unchanged.
- `npx playwright test cross_session_surface.spec.ts memory_page_controls.spec.ts --project chromium`: 2/2 passing in 2.2s (no regression on existing memory test).

## Risks for Codex Red-Team

1. **Time-zone:** `formatRelative` uses ms diff, not calendar days; test injects fixed `Date.now` so test deterministic.
2. **Empty-state:** no section rendered when prior_run_summary list is empty — keeps fresh-workspace UI clean.
3. **§9.4 N/A frontend.**
4. **CHARTER §3 LOC cap:** 113 net.

## Output schema (mandatory)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
