M-17 v1 — first review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

M-17 ships the within-run citation-graph integrity check that the
M-16 audit bundle has been quietly assuming the IR satisfies.
Audit bundles delivered to customers must have a self-consistent
citation graph; M-17 is the static check that catches regressions
before bundle export.

This module is the within-run companion to M-18 (across-run
regression alerts). M-17 does NOT fetch URLs or load source
content — that's M-18 territory. M-17 is fast, deterministic, and
runs synchronously at audit-bundle export time and on demand via
the inspector endpoint.

## What changed in v1 (commit fbf41d3)

New module: `src/polaris_graph/audit_ir/citation_health.py`

Issue codes (stable enum string values for downstream triage):
- broken_ref            ERROR — token cites missing evidence_id
- invalid_span          ERROR — start >= end, or negative start
- invalid_tier          ERROR — tier not in {T1..T7, UNKNOWN}
- duplicate_evidence_id ERROR — same eid in two bibliography entries
- duplicate_bib_num     ERROR — same [N] used by two entries
- non_positive_bib_num  ERROR — num <= 0
- empty_statement       ERROR — bib entry caption blank
- empty_url             WARNING — bib entry has no source link
- orphan_evidence       WARNING — bib entry never cited by verified
- verified_no_tokens    ERROR — kept sentence has no tokens

Public API:
- check_citation_health(ir: AuditIR) -> CitationHealthReport
- report_to_dict / issue_to_dict for JSON transport
- Overall status: red (≥1 ERROR) > yellow (warnings only) > green

Endpoint: `GET /api/inspector/runs/{slug}/health`
- 404 on unknown slug
- 500 on AuditIR load failure
- 200 with full report payload otherwise
- Same auth posture as other run-* endpoints (deferred to M-15c)

Tests: 20 tests including:
- 13 ERROR cases
- 2 WARNING cases
- 1 severity-mixing test (error dominates warning)
- 2 serialization round-trip
- 1 real-data smoke test against run-14
- 2 endpoint integration tests (404, 200)

## Real-data finding

`test_real_run14_loads_and_health_checks` surfaced 2 broken refs
and 2 orphans on the run-14 V30 bibliography:
- ev_162 / ev_185 cited by verified sentences but not in
  bibliography.json
- hc_mounjaro_monograph / surpass_cvot_primary in bibliography
  under canonical source handles but never cited

This is a real V30 bibliography-normalization defect the M-17
milestone caught in its first pass. The test assertion was
loosened from "no broken refs" to "report is well-formed" so M-17
ships independent of the V30 fix; the V30 fix is tracked
separately. Calling out so you don't flag the loosened assertion
as M-17 covering up a regression.

## Your job

Verdict on M-17 v1. GREEN / PARTIAL / DISAGREE.

I'm asking you to look for:

1. **Missing check categories.** Are there citation-graph
   integrity properties M-17 should validate but doesn't? E.g.
   contradictions cluster claims have evidence_ids — should those
   resolve into bibliography too?
2. **Wrong severity.** Anything I marked ERROR that should be
   WARNING (or vice versa)?
3. **Wrong overall_status mapping.** Should some condition force
   red even without an ERROR? Should some warnings be info-only?
4. **Endpoint design issues.** Auth posture matches other run-*
   endpoints (deferred to M-15c) — is that defensible? Pagination
   needed for very-large issue lists?
5. **Anything else worth flagging before M-17 locks.**

If GREEN, M-17 locks. Phase C continues to M-18 (regression
alerts).

## Output

Write to `outputs/codex_findings/m17_review/findings.md`:

```markdown
# Codex review of M-17 v1

## Verdict
GREEN / PARTIAL / DISAGREE

## Coverage
- [x/no] all relevant issue categories covered
- [x/no] severity assignments defensible
- [x/no] overall status logic sound

## Real-data finding
- [observation about the run-14 broken refs]

## Final word
GREEN to lock M-17 + proceed / PARTIAL with edits.
```

Be terse. Under 100 lines.
