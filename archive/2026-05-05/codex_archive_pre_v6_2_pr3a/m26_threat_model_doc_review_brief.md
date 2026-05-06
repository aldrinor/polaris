M-26 threat-model doc review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

After the M-26 v1→v14 audit cycle (13 review rounds, all your prior
findings), I wrote `docs/m26_threat_model.md` to anchor the
threat-model boundary so future contributors don't restart the
loop on out-of-scope attacks (DDL, identity, file-system).

This doc is itself unreviewed. Stress-test it.

## What to verify

1. **Defense surface completeness.** The doc claims "complete
   defense surface enumerated per table per operation". Check the
   tables in the doc against the actual triggers / CHECK
   constraints in `src/polaris_graph/audit_ir/contract_draft_store.py`.
   Any defense in code missing from the doc? Any defense in doc
   that doesn't actually exist?

2. **In-scope/out-of-scope split.** The doc declares 5 out-of-scope
   threats (DDL, identity validation, file-system, transaction-
   isolation, cross-module). Are any of these ACTUALLY defendable
   from inside the schema and shouldn't be classified as out-of-scope?

3. **Audit-trail integrity claim.** The doc claims direct-SQL
   bypasses still leave an audit trail via the v12/v13 auto-log
   triggers. Verify by reproducing: can you bypass the auto-log
   without DDL?

4. **"Decision rules for future contributors" section.** Are the
   rules actually sufficient to prevent a future contributor from
   re-introducing a closed bypass? Or is there a foreseeable
   mistake the rules don't catch?

5. **Internal consistency.** Does the doc contradict itself or
   the actual code anywhere?

## Output

Write to `outputs/codex_findings/m26_threat_model_doc_review/findings.md`:

```markdown
# Codex review of m26_threat_model.md

## Verdict
GREEN / PARTIAL / DISAGREE

## Findings
- [defense table omission, if any]
- [out-of-scope misclassification, if any]
- [audit-trail integrity issue, if any]
- [contributor-rule gap, if any]
- [internal contradiction, if any]

## Final word
GREEN to ship doc as-is / PARTIAL with edits / DISAGREE with [thesis].
```

Be terse. Under 60 lines.
