M-D9 phase 1 v2 review (commit 44c8f7b).

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Round 1 (commit d672558) verdict was PARTIAL with 2 findings:
  1. [HIGH] Manifest schema mismatch (synthetic vs live)
  2. [HIGH] validation_set_hash drift was YELLOW, should be RED

This v2 commit addresses both.

## What changed in v2

`src/polaris_graph/audit_ir/regression_lab.py`:

1. ManifestDrift enum updated to live schema
   (verified against scripts/run_honest_sweep_r3.py:95-138,
   1785-1828):
   - `STATUS` (was ABORT_STATUS): top-level unified taxonomy
   - `RELEASE_ALLOWED`: unchanged
   - `ADEQUACY_DECISION`: new (nested `adequacy.decision`)
   - `SENTENCES_VERIFIED_DROPPED_TO_ZERO`: was
     SECTIONS_VERIFIED_DROPPED_TO_ZERO; now reads nested
     `generator.sentences_verified`

2. Status taxonomy ordering (`_status_tier`):
   - success(0) < partial_*(1) < abort_*(2) < error_*(3)
   - Cross-tier degradation = regression (RED)
   - Within-tier flip (e.g. partial_thin_corpus ->
     partial_outline_fallback) = drift but YELLOW
   - Unknown taxonomy values fail closed (RED)

3. Adequacy ordering (`_adequacy_is_regression`):
   - proceed(0) < expand(1) < abort(2)
   - Forward = regression; backward = improvement
   - Unknown values fail closed

4. validation_set_hash severity bumped "config" -> "schema":
   forces diff_regression to return RED (failure-closed).
   The hash IS the benchmark dataset identity; once it
   changes, induction metrics aren't comparable.

5. New `_nested_get(d, *keys)` helper for safely traversing
   nested manifest keys (no KeyError on missing intermediates).

`tests/polaris_graph/test_md9_regression_lab.py`: 25 -> 32 tests
(7 new round-1 regression tests):
  - status taxonomy tier ordering (success->partial,
    success->abort, partial->abort, within-partial)
  - adequacy.decision regression direction
  - generator.sentences_verified->0 detection
  - unknown status fails closed
  - validation_set_hash change is RED

## Your job

GREEN / PARTIAL / DISAGREE on v2.

1. **Round 1 fix integration**:
   - [ ] manifest schema matches live runner output
   - [ ] status taxonomy ordering is correct
   - [ ] adequacy ordering is correct
   - [ ] validation_set_hash now fails closed
   - [ ] no regressions

2. **Manifest field coverage**: with status, release_allowed,
   adequacy.decision, generator.sentences_verified, are
   there other live manifest fields that should be diffed?
   (e.g. evaluator_rule_pass / evaluator_rule_fail counts,
   qwen_verdicts, contradictions_found, evaluator_gate
   nested verdict)

3. **Status tier ordering boundary**: within-partial flips
   are YELLOW. Is that the right call, or are there specific
   partial->partial transitions that should regress (e.g.
   partial_thin_corpus -> partial_qwen_advisory means a new
   integrity issue appeared)?

4. **Per-key env diff**: still emits per-key
   PinDriftField. Any remaining drift-readability concerns
   if many env vars change?

5. **Phase 2 readiness**: with v2 schema-aligned manifest
   diffing, can BEAT-BOTH dimension scoring layer cleanly?

## Output

`outputs/codex_findings/md9_phase1_v2_review/findings.md`:

```markdown
# Codex round 2 — M-D9 phase 1 v2 (commit 44c8f7b)

## Verdict
GREEN / PARTIAL / DISAGREE

## Round 1 fix integration
- [x/no] manifest schema matches live runner
- [x/no] status taxonomy ordering correct
- [x/no] adequacy ordering correct
- [x/no] validation_set_hash fails closed
- [x/no] no regressions

## New findings (if any)
- [...]

## Final word
GREEN to lock M-D9 phase 1 / PARTIAL with edits.
```

Be terse. Under 50 lines.
