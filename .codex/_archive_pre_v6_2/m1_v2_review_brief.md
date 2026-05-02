M-1 Audit Graph IR loader v2 — re-review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your pass-1 review of M-1 returned PARTIAL with 8 findings. All 8 are
integrated in v2. Tests: 42/42 green (was 17/17 in v1).

Findings file: `outputs/codex_findings/m1_audit_ir_review/findings.md`

## What changed in v2

1. **verification_details.json now loaded.** New types:
   `VerifiedReport`, `ReportSection`, `ReportSentence`,
   `EvidenceSpanToken`. Stable `claim_id = "<section>:<kept|dropped>:<idx>"`.
   `get_sentence_by_claim_id` + `get_evidence_spans_for_claim` methods
   on AuditIR. M-3 unblocked.

2. **completeness_percent parsing FIXED.** Now reads `covered_fraction`
   first (V30 canonical), then falls back to `total_covered/total_applicable`,
   then to legacy `covered_topics/total_topics`. Test asserts == 100.0
   for run-14.

3. **Deep immutability.** `MappingProxyType` for `tier_mix.fractions`,
   `verified_report.drop_reason_counts`, `retrieval_stats.by_provider`.
   Mutable dict-of-dict `retrieval_attempt_log` replaced with frozen
   `RetrievalAttempt` dataclass. Tests assert `TypeError` on attempted
   mutation.

4. **Manifest enriched.** `EvaluatorGate` is now a rich frozen
   dataclass (gate_class, release_allowed, reasons, rule_blockers,
   qwen_critical_axes, qwen_parse_ok). `v30_warnings` preserved.
   `RetrievalStats` added (pre_filter, fetched, failed, by_provider).

5. **Metadata preservation.**
   - `ContradictionCluster`: subject, severity, relative_difference,
     recommended_action.
   - `FrameCoverageEntry`: section, slot_id, subsection_title,
     min_fields_for_completion, human_curated_provenance.
   - `FrameCoverageReport.semantics_warning`: preserves the V30
     retrieval-coverage caveat ("phase1_retrieval_coverage_only").

6. **IR_SCHEMA_VERSION = "1.0.0"** at top level. Renderers can refuse
   unknown major versions.

7. **AuditIRSchemaError** raised on missing required blocks. Required:
   manifest top-level keys (run_id, slug, status, question,
   protocol_sha256, evaluator_gate, completeness),
   `frame_coverage_report`, `corpus.tier_fractions`,
   contradiction claim `evidence_id`, contradiction cluster `claims`
   list of >=2.

8. **Test coverage 17 → 42.** New tests for each finding. All 42 green.

## Your job

Re-review M-1 v2. Verdict: GREEN / STILL-PARTIAL / DISAGREE.

Quick verification:
- Are all 8 of your pass-1 findings genuinely integrated (not just
  in spirit)?
- Any new issues introduced?
- Is M-3 now safe to depend on the IR for claim/span lookup?
- Schema versioning approach acceptable?
- Anything else?

## Output

Write to `outputs/codex_findings/m1_v2_review/findings.md`:

```markdown
# Codex re-review of M-1 v2

## Verdict
GREEN / STILL-PARTIAL / DISAGREE

## Pass-1 findings integration check
For each of the 8 findings:
- [x/partial/no] integrated correctly
- specific concern if any

## New issues introduced
none / list

## M-3 readiness
Is the IR now ready for View 1 (Report click-to-inspect) to build on?

## Final word
GREEN to proceed to M-2 / STILL-PARTIAL with edits / DISAGREE.
```

Be terse. Under 250 lines. The 8 fixes are concrete and testable;
this should be a quick verification pass.
