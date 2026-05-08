# Claude architect audit — I-f14-005

**Issue:** Cited recall — "from prior run" badge for ev_memory_* citations
**Branch:** bot/I-f14-005
**Canonical-diff-sha256:** 07d0535b79da313380610a0749402e1cc74f39eb9c47e2684bb3f8c7db564c96
**Brief verdict:** APPROVE iter 1
**Diff verdict:** pending Codex iter 1

## Substrate honesty
- Inline badge appears below provenance line for sentences whose provenance tokens reference an `ev_memory_*` evidence_id (the prefix produced by the I-f14-004 merger).
- `title` attribute lists the matching memory evidence_ids — substrate-honest about what's available client-side.
- Click-through to the prior run's full report is deferred to follow-up I-f14-005b.

## §9.4 N/A frontend.

## CHARTER §3 LOC cap
- 105 net (verified_report_view.tsx +13, fixture page +63, spec +29).

## Tests
- `playwright test cited_recall_badge.spec.ts --project chromium`: 1/1 passing in 1.5s.

## Verdict
APPROVE.
