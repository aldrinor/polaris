# Claude architect audit — I-p2c-004

**Issue:** Core Web Vitals smoke baselines
**Branch:** bot/I-p2c-004
**Canonical-diff-sha256:** 6ea94426843259d79887012c12ec473c08aa21f278edbad6d9889a22c6294466
**Brief verdict:** APPROVE iter 5 (cap reached after 4 P1 iterations on perf-harness wait, INP API options, observer sequencing, timing finiteness)
**Diff verdict:** pending Codex iter 1

## Substrate honesty
- Three chromium-only Playwright tests measure LCP, hover-render avg, and INP via Event Timing API.
- Lighthouse-CI integration explicitly deferred: requires dedicated CI job with Chrome headless + Lighthouse CLI (~1GB), tracked separately.
- INP test uses `durationThreshold: 16` per W3C spec; no-entry case logged via test annotation (not silent pass; not test.fail misuse).
- Hover test rejects `-1` stuck-popup sentinels via `Number.isFinite(t) && t >= 0` filter.

## §9.4 N/A frontend.

## CHARTER §3 LOC cap
- 106 net.

## Tests
- `playwright test perf_core_web_vitals.spec.ts --project chromium`: 3/3 passing in 6.6s.

## Verdict
APPROVE.
