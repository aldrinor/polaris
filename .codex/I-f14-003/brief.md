# Codex Brief Review — I-f14-003 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-f14-003 — Cross-session surfacing. Scope: "you researched X last week". Acceptance: test. LOC estimate 110.
- **Substrate today:** I-f14-002 page lists workspace memory entries via `listMemory`. `prior_run_summary` is one of the kinds. No relative-time formatting exists.
- **Honest framing per CLAUDE.md §9.4:** filter existing memory entries by `kind === "prior_run_summary"` and surface them in a "Recent research" section above the main list with relative-time labels ("yesterday", "2 days ago", "last week"). Production cross-session would also surface from prior runs that didn't get explicit prior_run_summary entries — that's M-INT-0a follow-up. Today's substrate is honest demo against existing endpoint.

## Plan

### `web/lib/relative_time.ts` (NEW)

1. `formatRelative(iso: string, nowMs: number = Date.now()): string` — pure helper, returns "today" / "yesterday" / "N days ago" / "last week" / "N weeks ago" / "N months ago".
2. Boundary breakpoints: <1d=today, 1d=yesterday, 2-6d="N days ago", 7d="last week", 8-13d="N days ago" (still days), 14-29d="N weeks ago", 30+d="N months ago".

### `web/app/memory/page.tsx` (extend)

3. Compute `prior_runs = entries.filter(e => e.kind === "prior_run_summary")`.
4. If non-empty, render a new `<section data-testid="recent-runs">` above the main list with heading "Recent research" + each entry as `<li data-testid="recent-run-{entry_id}">` showing `formatRelative(created_at)` + content.

### Playwright `web/tests/e2e/cross_session_surface.spec.ts` (NEW)

5. Mock `/workspaces/ws_demo/memory` GET to return 3 entries with `kind=prior_run_summary` at created_at 1 day ago, 5 days ago, 14 days ago.
6. Visit `/memory`. Assert `recent-runs` section visible.
7. Assert each row contains the expected relative-time string ("yesterday", "5 days ago", "2 weeks ago").

## Risks for Codex Red-Team

1. **Time-zone:** all comparisons use ms; `formatRelative` is deterministic given `nowMs` argument so test injects a fixed `Date.now()` mock.
2. **Empty-state:** if no prior_run_summary entries, no section rendered (avoids visual noise on fresh workspace).
3. **§9.4 N/A frontend.**
4. **CHARTER §1 LOC cap:** estimated relative_time.ts ~25, page.tsx +25, spec ~50 = ~100. Comfortable under cap.

## Acceptance criteria

1. New `web/lib/relative_time.ts` with `formatRelative` helper.
2. `/memory` page renders "Recent research" section when prior_run_summary entries exist.
3. Playwright spec mocks 3 dated entries and asserts relative labels.
4. CHARTER §1 LOC cap respected (≤200 net).

**Forced enumeration:** before verdict, write one line per criterion 1-4.
**Completeness check:** list files actually read.

## Output schema

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
