M-16 audit bundle export + run diff — code review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Phase C plan v2 GREEN-locked. M-14 + M-15a + M-15b GREEN-locked.
M-16 is the next critical-path milestone per FINAL_PLAN.md
Phase C deliverable #6.

## What landed (commit f005625)

### audit_ir/run_diff.py (NEW, ~280 lines)
- `RunDiff(a_run_id, b_run_id, slug, claim_deltas,
  evidence_deltas, contradiction_deltas, tier_shifts)`.
- `diff_runs(ir_a, ir_b)`:
  - Both runs must share `slug`. Slug mismatch raises
    ValueError (LAW II — diff across different audit shapes
    is meaningless).
  - Note: AuditIR.manifest doesn't carry a `template_id` field.
    `slug` is the audit-shape identifier (e.g.
    "clinical_tirzepatide_t2dm").
- Material changes surface:
  - Claims by stable claim_id (whitespace-only reformatting
    is suppressed because claim_id is keyed on
    section+status+idx, not text).
  - Evidence by evidence_id.
  - Contradictions by (subject, predicate) — NOT cluster_id,
    which is auto-assigned per-run and renumbers across
    re-runs of the same audit. Test
    `test_contradiction_cluster_id_renumber_does_not_surface`
    verifies.
  - Tier mix shifts > threshold (default 10pp, env-overridable
    via PG_RUN_DIFF_TIER_PP per LAW VI).
- `is_material(d)` for M-18 integration.
- `diff_to_dict(d)` for JSON serialization.
- Pure deterministic.

### audit_ir/inspector_router.py
- NEW endpoint:
  `GET /api/inspector/runs/diff?a_slug=...&b_slug=...`
  - 400 on slug mismatch (passes through ValueError).
  - 404 on unknown slug.
  - 500 on AuditIR load failure.
  - Currently unauthenticated (M-15c will retrofit run-* surface
    once jobs propagate to manifest).
- `/api/inspector/runs/{slug}/audit-bundle.zip` extended:
  audit_ir.json embedded in the bundle (best-effort). Without
  this, downstream consumers (M-23 review queue, M-25 private
  corpus sync) re-parse the raw artifact files just to render
  the same Inspector view.

### Tests (19, all green)
- Real-data baseline: self-diff on run-14 artifacts produces
  no deltas + serializes cleanly.
- Slug mismatch raises.
- Added / removed / unchanged claims.
- Whitespace-only change is noise (stable claim_id key
  suppresses it).
- Added / removed evidence by evidence_id.
- Resolved + new contradictions by stable subject+predicate.
- Cluster_id renumber suppressed (the v1 trap I almost stepped
  in).
- Tier shifts above/below threshold; env-overridable.
- is_material true/false.
- JSON round-trip.
- Determinism (same input → same output).

## Anti-scope (per Phase C plan v2)

- Run endpoint authz → M-15c.
- Bundle PGP signatures → Phase D.
- Cross-template comparisons → out of scope.

## Your job

Code review for M-16. Verdict: GREEN / PARTIAL / DISAGREE.

## Specific things to validate

1. **Stable cross-run handles.** I use `claim_id` for claims,
   `evidence_id` for evidence, `(subject, predicate)` for
   contradictions. Are those actually stable across reruns of
   the same audit? Specifically:
   - claim_id format is `<section>:<status>:<idx>` per V30
     loader. If verification iteration order changes, idx
     may shift.
   - evidence_id is generated per-run (e.g. ev_xxxx hex).
     Re-runs of the same retrieval may not produce the same
     ev_id. Is this a real bug for the diff?

2. **Slug as audit-shape identifier.** I treat slug as the
   stable audit-shape handle. If slug changes (e.g. user
   renames between runs), the diff would refuse. Acceptable?

3. **Tier-shift semantics.** Default 10pp threshold biases
   toward "report only big shifts". Should the diff also surface
   the absolute tier counts when a shift is reported?

4. **AuditIR JSON in the bundle.** Best-effort embed (skips on
   exception). Should I make this strict (fail the bundle if
   AuditIR can't project)?

5. **Whitespace-noise suppression.** I rely on the stable
   claim_id rather than text comparison. If V30 changes the
   claim_id format in a future version, this contract breaks.
   Worth a schema-version check?

6. **Anything else.**

## Output

Write to `outputs/codex_findings/m16_review/findings.md`:

```markdown
# Codex review of M-16

## Verdict
GREEN / PARTIAL / DISAGREE

## Specific issues
File:line bugs / gaps.

## Stable cross-run handles
Are claim_id / evidence_id / (subject,predicate) actually stable?

## Recommended changes
If PARTIAL.

## M-20 readiness
After M-16 locks, M-20 (50+ templates) is next. Anything in
M-16 that needs to settle first?

## Final word
GREEN to lock M-16 + proceed to M-20 / PARTIAL with edits.
```

Be terse. Under 200 lines.
