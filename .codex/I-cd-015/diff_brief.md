HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex diff review — I-cd-015 / GH#611

Brief APPROVE'd at iter 4/5. 4 files / +144 / -7 / +137 net LOC.

## §A — Diff summary

- 1 NEW middleware (web/middleware.ts) — 404 + header on 6 harness route roots in prod.
- 1 NEW smoke script (web/scripts/verify_harness_404.sh) — self-locating, asserts 404 + header on 11 harness paths + reachability on 3 non-harness.
- 1 CI workflow edit (.github/workflows/web_ci.yml) — POLARIS_TEST_HARNESS_ENABLED=1 in build_and_start_next env.
- 1 page edit (web/app/benchmark/page.tsx) — removed dead /generation Link button.

## §B — Acceptance verification

| Check | Status |
|---|---|
| 6 harness roots in middleware matcher | YES (base + `:path*` for each) |
| POLARIS_TEST_HARNESS_ENABLED override | YES |
| x-harness-blocked: 1 header on 404 | YES |
| Smoke script self-locates via $BASH_SOURCE/.. | YES |
| Smoke script asserts header AND status | YES |
| CI env propagates to next start process | YES (build_and_start_next env block) |
| /generation dead link removed | YES |

## §C — Codex Red-Team checklist

1. middleware matcher syntax: Next.js path-to-regexp format; `/path/:path*` matches descendants. Does my config correctly match `/charts_test` (bare) AND `/charts_test/foo/bar` (deep)?
2. POLARIS_TEST_HARNESS_ENABLED env propagation to `next start` subprocess: confirmed (set at step env level → inherited).
3. Smoke script self-location: `cd "$(dirname "${BASH_SOURCE[0]}")/.."` works from any invocation path.
4. Header assertion uses `grep -i '^x-harness-blocked:'` which is case-insensitive — middleware can return either case.
5. No accidental file deletions / additions beyond the 4-file scope.

## §D — Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
