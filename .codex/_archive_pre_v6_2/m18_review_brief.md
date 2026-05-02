M-18 v1 — first review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

M-18 ships the across-run regression-alert engine that builds on
M-16 (run diff) and complements M-17 (within-run citation
health). Where M-17 catches a single run failing integrity, M-18
catches a run that is internally consistent but materially worse
than its baseline. Customer-facing audits must not silently
regress against a prior successful version.

## What changed in v1 (commit c91f7b9)

New module: `src/polaris_graph/audit_ir/regression_alerts.py`

Severity tiers (worst-first):
- CRITICAL: ship-blocker. Operator MUST review.
- HIGH:     surface prominently in inspector UI.
- MEDIUM:   log + surface in alert pane.
- INFO:     telemetry only.

Issue codes (stable enum string values):

| Code | Severity ladder |
| --- | --- |
| `release_not_allowed` | CRITICAL — `release_allowed` True→False |
| `evaluator_gate_downgrade` | CRITICAL — gate_class pass→fail/blocked/abort |
| `adequacy_regression` | CRITICAL — adequacy decision pass→fail |
| `verified_drop` | CRITICAL ≥50% / HIGH ≥20% (env-overridable) |
| `citation_drop` | HIGH ≥50% / MEDIUM ≥20% |
| `tier_downgrade` | HIGH ≥30pp / MEDIUM ≥10pp T1+T2 share drop |
| `new_high_severity_contradiction` | HIGH — severity in {high,critical,severe} |
| `new_contradiction` | MEDIUM — severity in {medium,low,unspecified} |
| `cost_spike` | HIGH ≥3x / MEDIUM ≥1.5x |

LAW VI: all thresholds env-overridable
  PG_REGRESSION_VERIFIED_DROP_PCT (default 0.20)
  PG_REGRESSION_CITATION_DROP_PCT (default 0.20)
  PG_REGRESSION_T1T2_DROP_PP      (default 10.0)
  PG_REGRESSION_COST_SPIKE_RATIO  (default 1.5)
Garbage values fall back to default. Negative values fall back.

Public API:
- `detect_regressions(ir_a, ir_b, *, diff=None) -> RegressionReport`
  Raises `ValueError` on slug mismatch (mirrors `diff_runs`).
  Caller may pass pre-computed `diff` to avoid double work.
- `report_to_dict` / `alert_to_dict` for JSON transport.
- Worst-severity computation: critical > high > medium > info > ok.

New endpoint:
  `GET /api/inspector/runs/regression?slug=...&baseline_slug=...`
- Declared BEFORE /runs/{slug} dynamic route (FastAPI registration
  order — same constraint as /runs/diff).
- 404 on unknown slug or baseline_slug
- 400 on slug mismatch (ValueError surface)
- 500 on AuditIR load failure
- 422 on missing baseline_slug query param
- Same auth posture as other run-* endpoints (M-15c deferred)

Tests: 24 total. Notable shapes:
- Identical runs → no alerts, worst="ok"
- Slug mismatch raises ValueError
- Severity ladder coverage (CRITICAL/HIGH/MEDIUM)
- Below-threshold doesn't alert
- Env override tightens threshold
- Garbage env falls back
- Critical dominates lower severities in worst_severity
- Endpoint path-collision regression: GET /runs/regression with
  no baseline_slug returns 422, not 404 (would mean it routed to
  /runs/{slug} with slug='regression').

Module: 24/24 regression tests green; combined M-16/M-17/M-18/
M-20: 158/158.

## Your job

Verdict on M-18 v1. GREEN / PARTIAL / DISAGREE.

I'm asking you to look for:

1. **Severity-mapping bugs.** Anything I marked CRITICAL that
   should be HIGH (or vice versa)? Especially: is verified-drop
   ≥50% really CRITICAL, or should it be HIGH and only adequacy/
   release-flip be CRITICAL?
2. **Missing alert categories.** Are there regressions M-18
   should detect but doesn't? E.g. completeness % drop, word
   count drop, retrieval source-count drop, frame_coverage
   coverage drop, contradictions resolved-then-regenerated?
3. **Threshold default reasonableness.** 20% verified drop is
   the default — too tight? Too loose? Real Phase 2 runs vary
   ±5-10% on stable templates per re-run noise. False-positive
   cost is operator review burden.
4. **Wrong-direction alerts.** Does my code accidentally flag
   IMPROVEMENTS as regressions anywhere? E.g. release_allowed
   False→True, contradiction count drop, cost decrease?
5. **Endpoint route-order regression.** I added the route-
   collision test but it's only 1 test. Have I covered the case
   where a future regression in route ordering accidentally
   makes /runs/regression unreachable?
6. **Anything else worth flagging before M-18 locks.**

If GREEN, M-18 locks. Phase C continues to M-23 / M-21 / M-19.

## Output

Write to `outputs/codex_findings/m18_review/findings.md`:

```markdown
# Codex review of M-18 v1

## Verdict
GREEN / PARTIAL / DISAGREE

## Severity mapping
- [defensible / list issues]

## Missing alert categories
- [list any]

## Threshold defaults
- [defensible / suggest changes]

## Wrong-direction
- [no / list issues]

## Final word
GREEN to lock M-18 + proceed / PARTIAL with edits.
```

Be terse. Under 100 lines.
