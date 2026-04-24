V30 Phase-2 M-66 fix-plan review — xhigh reasoning.

**Skip git status.** Codex at gpt-5.4 + xhigh (project default).

## Context

V30 Phase-2 run-2 shipped with status=success but failed
BEAT-BOTH. Claude + Codex independent audits at
`outputs/codex_findings/v30_phase2_run2_audit/` agreed on 1 BB +
2 BO + 4 LB (vs BEAT-BOTH ≥5/7 criterion). Fix plan at
`outputs/audits/v30_phase2/fix_plan_run3.md`.

## Your job

Review the fix plan for:

1. **Root-cause vs band-aid**: does M-66a (content-overlap
   loosening for contract slots) address the real SURPASS-6
   drop cause, or does it mask a deeper bug in
   `run_contract_section`'s sentence grouping?

2. **Fix sequencing**: is the bundle M-66a + M-66b + M-66c
   correct? Any of these block another?

3. **M-66b scope creep**: extending M-56 with AccessBypass
   full-text fetch is a real architectural change. Is it the
   right Phase-2 change, or should regulatory-entity
   provisioning move to M-61 (human/licensed completion)
   instead?

4. **Acceptance criteria strength**: are the 7-subsection /
   4-regulatory / ≥6-table-row gates strict enough to prevent
   a false-pass re-run?

5. **Expected dimensional impact**: the "5 BB + 2 BO + 0 LB"
   projection — is that honest, or is any dimension being
   double-counted (e.g., Regulatory + Jurisdiction both lifting
   from the same M-66b fix, is that realistic or would one
   still lag)?

6. **Narrative depth (dim 7)**: the plan projects BO after
   M-66b (more fetched content → LLM has more to paraphrase
   into Safety/Comparative). Is that a real expectation or a
   hand-wave? ChatGPT/Gemini narrative depth comes from
   synthesis, not source quantity.

7. **Thomas clamp (M-66c)**: yaml field realignment is the
   proposed fix. Should we also change the Thomas contract to
   use the FULL paper (not abstract) via the same M-66b fetch
   path? Or is clamp an inherently limited slot?

8. **Risk of regression**: M-66b changes M-56's content shape
   (direct_quote from 500 char abstract → 25K char extract).
   Downstream impacts on prompt tokens, cost, LLM
   extractability. Is the cost ceiling still $10/run OK?

9. **Omitted blockers**: what else that Codex's run-2 audit
   flagged isn't in this fix plan? E.g., SURPASS-CVOT paywall
   gap remains; Trial Summary + Timeline tables are malformed
   but don't have a dedicated fix.

10. **Ship vs ship-and-continue**: after M-66 if we hit
    BEAT-BOTH ≥5/7, is that actually SHIP or is there a
    V31/V32 dimension we still haven't calibrated?

## Format

Write to `outputs/codex_findings/v30_m66_plan_review/findings.md`.

```markdown
# V30 M-66 fix plan review

**Verdict**: APPROVED | CONDITIONAL-no-blockers | CONDITIONAL-blockers | REJECT

## Answers

1. Root-cause vs band-aid: ...
2. Fix sequencing: ...
3. M-66b scope: ...
4. Acceptance criteria: ...
5. Dimensional impact honesty: ...
6. Narrative depth projection: ...
7. Thomas clamp: ...
8. Regression risk: ...
9. Omitted blockers: ...
10. Ship criteria: ...

## Findings (blockers / mediums / nits with file:line)

## Revisions required before Claude implements

1. ...
2. ...

## Next

On APPROVED: Claude implements M-66a/b/c. On CONDITIONAL /
REJECT: Claude re-drafts plan with revisions + resubmits.
```

Under 200 lines. Full xhigh reasoning budget.
