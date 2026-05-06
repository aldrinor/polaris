# Codex round 3 — M-PROD-1 v3 (R2 P1 closed)

## Pre-flight
- Branch: `polaris`
- Commit: `030f23c`

## R2 closure
**R2 P1 [slash-prefixed route refs invisible]:**
- v3 fixes:
  - 4th regex alternative for `/path/style/refs`
  - `_live_server_routes()` extracts FastAPI routes via
    @app.METHOD / @router.METHOD decorators on
    `scripts/live_server.py` + `inspector_router.py`
  - `_classify()` resolves slash-prefixed refs against the
    extracted route set
- Result: 28/28 intact (vs v2's 26/26 — `/health` and
  `/api/events` now caught)
- Synthetic regression: `/nonexistent/route` correctly reports
  not-exists

## Round-by-round closure
- R1 P0 #1 [rglob fallback]: closed v2
- R1 P0 #2 [regex misses dotfiles/dirs/placeholders]: closed v2
- R2 P1 [slash-prefixed routes]: closed v3

## Severity rubric
- **P0** — production-breaker
- **P1** — phase-rework
- **P2** — governance precision (non-blocking)
- **P3** — polish (non-blocking)

**APPROVE iff zero P0 + zero P1.**

## Reviewer instructions
- Find ALL P0/P1 defects. If zero, write "no P0/P1 found"
  explicitly.
- Do NOT re-raise R1/R2 findings already addressed.
- Spot-check route extraction: rename a route in
  scripts/live_server.py, audit should report the doc reference
  as a gap.

## Skepticism gate
List which files you read + which closures you verified +
whether you ran a synthetic route-rename regression.

## Anti-nits (do NOT flag)
- Prose grammar / docstring style
- R1/R2 findings already addressed
- Test coverage (deferred to v4)

## Verdict format
```
## Files scanned
## R1+R2 closure verification
## Acceptance bar verification
## Findings (NEW only)
## Verdict APPROVE | REQUEST_CHANGES
```

## Round metadata
Round 3 of 5 hard cap.
