M-1 Audit Graph IR loader — code review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Building Phase A of the FINAL_PLAN (jointly agreed Claude+Codex pass-4
GREEN). Phase A centerpiece is the Evidence Inspector — 5 views over
V30 run-14 audit artifact.

M-1 is the foundation: a canonical Audit Graph IR loader. Per FINAL_PLAN
the audit graph IR is the canonical object that the Evidence Inspector
renders; all derivative renderers (PDF/DOCX/CSV/charts/brief/deck)
project from it and retain back-links to claim IDs.

## What landed

Files:
- `src/polaris_graph/audit_ir/__init__.py`
- `src/polaris_graph/audit_ir/loader.py`
- `tests/polaris_graph/test_audit_ir_loader.py` (17/17 passing)

Module exposes:
- `load_audit_ir(artifact_dir) -> AuditIR`
- 8 frozen dataclasses (immutable IR — renderers can't mutate canonical truth)
- Lookup methods on AuditIR: `get_bibliography_by_num`, `get_bibliography_by_evidence_id`,
  `get_contradictions_for_evidence`, `get_frame_coverage_for_entity`, `get_tier_counts`

Source files joined:
- `manifest.json` → RunManifest, FrameCoverageReport, TierMix
- `report.md` → raw markdown string
- `bibliography.json` → BibliographyEntry[]
- `contradictions.json` → ContradictionCluster[] (14 clusters in run-14)

Test coverage:
- Loads canonical run-14 artifact
- Verifies 14 contradictions, 15 frame-coverage entries
- Tier fractions sum to 1.0 ± 0.01
- Frozen dataclass immutability
- Fails loudly on missing dir / missing manifest

## Your job

Code review for M-1. Verdict: GREEN / PARTIAL / DISAGREE.

This is the foundation everything else is built on, so I want it tight.

## Specific things to validate

1. **Schema completeness.** Does the IR cover everything the 5 Evidence
   Inspector views need? Specifically:
   - View 1 (Report click-to-inspect): needs report.md + bibliography
     by [N] + per-claim evidence-span lookup. Is anything missing?
   - View 2 (Contradiction Matrix): needs ContradictionCluster + claim
     metadata (subject/predicate/dose/value/tier/snippet). Complete?
   - View 3 (Frame Coverage): needs frame_coverage_report with per-entity
     status, gap reasons, retrieval logs. Complete?
   - View 4 (Methods + Provenance Bundle): needs run hash, model versions,
     retrieval queries, abort gates, reproducibility hash. Manifest
     covers some of this but model_versions and retrieval_queries
     aren't currently captured. Should they be added now?
   - View 5 (Source Tier Mix): needs tier fractions at corpus level.
     Manifest has corpus.tier_fractions; do we also need per-section
     or per-evidence-id tier breakdown?

2. **Dataclass design.** Frozen dataclasses with tuple-of-... for nested
   lists. Is this the right pattern? Should we use Pydantic for JSON
   serialization instead? (FastAPI consumers will need JSON.)

3. **verification_details.json was NOT loaded.** Per the file listing
   that contains per-section drop reasons + per-claim evidence-id
   tokens. Is that acceptable to defer to a later module, or should
   it be in M-1 since the Inspector view 1 needs span lookup?

4. **Backward / forward compatibility.** Schema versioning: should the
   AuditIR version-tag itself so future runs (V31, V32 already shipped;
   V34 cross-jurisdiction is on the roadmap) can declare schema
   changes without breaking old runs?

5. **Performance.** Loader does eager full-load. For run-14 that's
   ~500KB. For larger runs (300-500 PDF Phase D corpus) this could
   matter. Is eager loading the right default, or should it be lazy?

6. **Error handling.** Currently fails loudly on missing manifest /
   missing dir. Should it also fail on schema mismatch (e.g., manifest
   missing `frame_coverage_report` key) or degrade gracefully?

7. **Test coverage gaps.** 17 tests passing — anything important not
   covered?

8. **Anything else you'd push back on.**

## What you should output

Write to `outputs/codex_findings/m1_audit_ir_review/findings.md`:

```markdown
# Codex review of M-1 Audit Graph IR loader

## Verdict
GREEN / PARTIAL / DISAGREE

## Schema completeness check
For each of the 5 Inspector views: does the IR cover what's needed?

## Specific issues
List concrete bugs / gaps / design problems.

## Recommended changes
If PARTIAL: specific edits (file:line).

## What's ready to build on
Confirm what M-2/M-3 can safely depend on.

## Next module dependency check
M-2 is web app skeleton + V30 mounting. M-3 is Inspector view 1 (Report
click-to-inspect). Are there any prerequisites in M-1 that should land
BEFORE M-2/M-3?
```

Be terse. Under 300 lines. This is foundation review — flag any structural
issues now before 4 more modules build on top.
