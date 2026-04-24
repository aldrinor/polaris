M-60 code audit pass 3 — verify pass-2 routing realignment.

**Skip git status.** Two files only.

## Context

Pass-2 verdict: CONDITIONAL-blockers. You caught three routing
bugs: fail_unbound_citation + fail_gap_no_language +
fail_payload_mismatch were all routed to curator tasks, and
gap+PASS was emitting "no action needed" entries.

Commit `267220b` implements a strict `_is_curator_actionable()`
predicate:

  PASS, FAIL_UNBOUND_CITATION, FAIL_GAP_NO_LANGUAGE,
  FAIL_PAYLOAD_MISMATCH → False (no task emitted)
  FAIL_MIN_FIELDS, FAIL_MISSING_PAYLOAD (gap or non-gap)
                                        → True (curator task)

human_completion_eligible now derives from this predicate.
_compose_task_needs simplified with defensive catch-all.

## What to verify

Files (commit `267220b`):

1. `src/polaris_graph/generator/frame_manifest.py`
2. `tests/polaris_graph/test_m60_frame_manifest.py`

Check:

1. **Three pass-2 bugs closed**:
   - fail_unbound_citation + non-gap row → no task emitted
   - fail_gap_no_language + gap row → no task emitted
   - gap + PASS → no task emitted
   - fail_payload_mismatch → no task emitted
   Tests in TestHumanCompletionTasks lock in all four.
2. **Curator-actionable cases still work**:
   - gap + fail_min_fields → RETRIEVAL task emitted
   - non-gap + fail_min_fields → EXTRACTION task emitted
3. **Defensive catch-all**: if `_is_curator_actionable` and
   `_compose_task_needs` drift out of sync, the ROUTING CHECK
   message surfaces. Is that a reasonable belt-and-suspenders?
4. **Third-round adversarial attempts**: use full xhigh budget.
   Any remaining routing path that mislabels engineer-owned
   work as curator-owned, or vice versa? Specifically:
   - FAIL_MISSING_PAYLOAD — should curator see this? (Currently
     True — M-58 didn't produce a payload is ambiguous: could
     be M-58 bug (engineer) or truly no content (curator). My
     current choice is True because the content-availability
     interpretation lets the curator deliver content; the
     engineer-bug interpretation gets flagged by
     _compose_task_needs defensive catch-all if provenance
     isn't gap. Agree with this choice?)
   - What about gap row + fail_missing_payload (no M-58
     payload at all)? Still curator-actionable?
   - Any interaction with pipeline-fault path (is_pipeline_fault
     True)?
5. **Regression**: 237/237 pass in scoped V30 suite.

## Output

Write to
`outputs/codex_findings/m60_code_audit/pass3_findings.md`.

Format:
```markdown
# Codex M-60 audit — pass 3

**Verdict**: APPROVED | CONDITIONAL-no-blockers | CONDITIONAL-blockers | REJECT

## Pass-2 bugs closed
<verified / still open>

## Curator-actionable cases still work
<verified>

## Third-round adversarial attempts
<list each, parser behavior>

## Residual concerns
<anything>

## Next

On APPROVED / CONDITIONAL-no-blockers: Claude proceeds to M-61.
```

Keep under 80 lines. Full xhigh budget.
