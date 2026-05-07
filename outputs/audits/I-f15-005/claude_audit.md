# Claude architect audit — I-f15-005

**Issue:** F15 adversarial: paywalled, 500MB resumable, partial run
**Branch:** bot/I-f15-005
**Canonical-diff-sha256:** 29b6fd88ff6b9f698acd7b4a6581b19d3396dd5af95556d42440a4a94ae9ef51
**Brief verdict:** APPROVE iter 2 (0/0/0/0)
**Diff verdict:** APPROVE iter 1 (0/0/0/0, accept_remaining)

## Substrate honesty
- Pure test-only addition. No production code touched.
- Tests cover existing HEAD behavior: snippet fallback (snapshot_sources.py:64), per-source 200KB cap (snapshot_sources.py:27), abort on non-success verdict (manifest_builder.py:97).
- 500MB framing scoped to per-source cap per Codex iter-1 P1 resolution; total bundle assertion deferred to I-f15-005-pool follow-up.

## §9.4 compliance
- No mocks. No magic numbers. No `try: pass`. No TODO/FIXME.

## Test integrity
- 3/3 PASS locally on Python 3.13.13.
- Hermetic.

## CHARTER §1 LOC cap
- 142 net. Under 200.

## Verdict
APPROVE on architect review. Ready to ship.
