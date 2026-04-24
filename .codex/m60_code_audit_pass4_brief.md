M-60 code audit pass 4 — verify allowlist fix.

**Skip git status.** Two files only.

## Context

Pass-3 verdict: CONDITIONAL-no-blockers with one residual
(denylist default → True for unknown statuses) and one nit
(stale docstring).

Commit `9ddd568` switches `_is_curator_actionable` to an allowlist:

  Explicit curator-actionable set:
    (True,  FAIL_MIN_FIELDS)
    (True,  FAIL_MISSING_PAYLOAD)
    (False, FAIL_MIN_FIELDS)

  Everything else → engineer (or no-op for PASS).

Also realigned (non-gap, FAIL_MISSING_PAYLOAD) from curator to
engineer routing.

## What to verify

Files (commit `9ddd568`):

1. `src/polaris_graph/generator/frame_manifest.py`
2. `tests/polaris_graph/test_m60_frame_manifest.py`

Check:

1. **Allowlist enforced**: any status NOT in the explicit
   curator-actionable tuple set returns False. Future verdicts
   default to engineer routing.
2. **Non-gap FAIL_MISSING_PAYLOAD → engineer**: new test
   `test_nongap_missing_payload_not_routed_to_curator` locks
   this in.
3. **Gap FAIL_MISSING_PAYLOAD → curator**: new test
   `test_gap_missing_payload_routed_to_curator` verifies the
   gap path still routes correctly.
4. **Stale docstring fixed**.
5. **Fourth-round adversarial attempts**: full xhigh budget.
   Any residual issue with the allowlist? Specifically:
   - Gap + PASS still doesn't emit (all good)
   - Non-gap + FAIL_MIN_FIELDS → curator (RETRIEVAL? no —
     EXTRACTION)
   - Hypothetical new verdict added without updating allowlist
     — verify it defaults to engineer
   - Interaction with pipeline-fault path still correct?
   - is_gap_row derivation correct for all row types
     (ABSTRACT_ONLY, OPEN_ACCESS, METADATA_ONLY,
     FRAME_GAP_UNRECOVERABLE)?
6. **Regression**: 239/239 pass in scoped V30 suite.

## Output

Write to
`outputs/codex_findings/m60_code_audit/pass4_findings.md`.

Format:
```markdown
# Codex M-60 audit — pass 4

**Verdict**: APPROVED | CONDITIONAL-no-blockers | CONDITIONAL-blockers | REJECT

## Pass-3 residual resolution
<verified / still open>

## Fourth-round adversarial attempts
<list each>

## Residual concerns
<anything>

## Next
On APPROVED / CONDITIONAL-no-blockers: Claude proceeds to M-61.
```

Keep under 80 lines. If APPROVED, this concludes M-60 audit
chain; Claude proceeds to M-61.
