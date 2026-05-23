# Codex DESIGN+DIFF review — I-p2-015 (#754): plan-review run-start surface

HARD ITERATION CAP: 5. iter 1. Canonical-diff-sha256 `4d4f8a47d567ec2396b27edd45c9fe5246fada4d4734927b0cac652207d3cbeb`. web/ only. MERGE AUTHORIZED if mergeable. APPROVE iff zero P0/P1. (Brief APPROVE'd iter2 — verify the DIFF implements it faithfully, esp. the SAFETY gate.)

## What shipped (per the iter-2-APPROVE'd brief)
- NEW web/app/plan/page.tsx (client, Suspense): reads q+template from searchParams; on mount runs runIntake(q) (the REAL clinical+PICO gate); renders question display-only + decision.scope_class (from the decision, not fabricated) + honest 4-step "what POLARIS will do"; canStart = decision.status==="in_scope" && disambigResolved && !starting; needs_disambiguation -> runDisambiguation -> DisambiguationModal (resolve sets disambigResolved); not-in-scope (out_of_scope/refused/ambiguous) -> blocked alert + Edit->/intake; createRun({template,question,document_ids:[]}) -> /runs/[id]; ConcurrentRunError -> callout; no-question -> EmptyState->/intake.
- web/app/intake/components/intake_form.tsx: on status==="in_scope", a "Continue to plan ->" button -> /plan?q=<encoded>. + Link import.

## Claude visual audit (standalone @1366+@390, sent to operator): top-tier plan page. Start correctly DISABLED without backend (decision null -> not in_scope -> safe default); enables on live VM for in_scope. Keeps app nav (correct for in-app step).

## SAFETY review focus (clinical-safety-critical, §-1.1)
1. Can a run start when NOT in_scope or with unresolved disambiguation? onStart has no internal re-guard beyond the disabled button (canStart). Is button-disabled sufficient, or must onStart re-assert canStart at call time (defence-in-depth)?
2. Question truly immutable (no edit path skipping re-gate)? Uploads absent (document_ids:[]) — no bypass?
3. Honesty: "what POLARIS will do" all true to the pipeline? scope_class from decision only? Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```
