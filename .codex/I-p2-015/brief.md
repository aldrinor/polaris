# Codex BRIEF review — I-p2-015 (#754): Plan-review page (run-start relocation)

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution/safety risks.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on non-P0/P1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## WHY (operator-locked context — HARD constraints, do not relax)
- #761 (dashboard → monitoring-only) is BLOCKED because the dashboard is the ONLY `createRun` caller in the app. #754 RELOCATES run-start off the dashboard so #761 can proceed. Operator chose this sequence (do #754 first).
- §-1.1 clinical-safety: the mandatory pre-run AMBIGUITY preflight (I-rdy-009 #505) + scope gate MUST be preserved. A run must NOT start on an ambiguous/out-of-scope question. Losing a preflight is a SAFETY regression, not a cosmetic miss.

## DESIGN (advisor-reviewed; relocate, don't rewrite)
New page `/plan` (web/app/plan/page.tsx), client component. Edit policy (a): the **question is DISPLAY-ONLY** on /plan — a single source of preflight truth. /plan is a "confirm + start" surface.

### Flow
1. **On mount:** read `q` (question) + `template` from searchParams. If `q` missing → render an EmptyState linking to /intake (no fake plan).
2. **Preflight on mount (immutable question → ONE-TIME check, no stale-key guarding needed):**
   - `checkScope(template, q)`. If verdict `rejected` → show the scope-rejection (honest reason) + disable Start + offer "Edit question → /intake".
   - If accepted → `checkAmbiguity(q, candidates)` (candidates built from the question as the dashboard does). If `is_ambiguous && clusters.length>0` → open the reused `DisambiguationModal`; Start stays disabled until the operator picks a cluster OR acknowledges. (Question is immutable here, so a single resolved flag suffices — no per-input-key tracking.)
3. **Plan panel (honest, no fabrication):** show the vetted question, the auto-detected template + scope_class, and a truthful "What POLARIS will do" list (retrieve primary sources → corpus-adequacy + corpus-approval gate → section-by-section generation → per-claim span verification → signed bundle). Ties to the corpus-approval gate by naming it. NO invented specifics (no fake source counts).
4. **Uploads (optional):** /plan owns document uploads (matches "editable plan"; intake stays question-only) — reuse `uploadDocument`; collect `document_ids`.
5. **Start research run:** `createRun({template, question, document_ids})` → `router.push('/runs/'+run.run_id)`. Handle `ConcurrentRunError` → dedicated callout linking to the active run (mirror the dashboard).
6. **Edit question:** link back to `/intake` (preflight re-runs there).

### Intake handoff (SAME PR — else intake dead-ends)
Intake's accepted/clear path gains a "Continue to plan →" action → `router.push('/plan?q=<question>&template=<template>')`. Intake stays question-only; its existing runIntake scope/ambiguity gate is unchanged (defence-in-depth: /plan re-checks on mount too, so direct navigation to /plan is also safe).

## Files I have ALSO checked and they're clean
- web/lib/api.ts: createRun(RunRequest{template,question,document_ids})→RunStatusResponse; ConcurrentRunError; checkScope→ScopeDecision{verdict}; checkAmbiguity→AmbiguityResult{is_ambiguous,clusters}; uploadDocument→UploadResponse{document_id}.
- web/app/intake/components/disambiguation_modal.tsx: {open, clusters, onSelectCluster, onCancel} — reusable.
- web/app/dashboard/page.tsx: the relocation SOURCE (still intact; #761 will gut it AFTER this merges).
- web/components/states/state_kit.tsx (EmptyState/ErrorState), AppShellGate (/plan stays gated — keeps the app nav, correct for an in-app step).

## Review focus
1. SAFETY: does the on-mount scope+ambiguity preflight + immutable-question design fully preserve the #505 mandatory ambiguity gate + scope gate? Any path to start an ambiguous/rejected run? Direct-nav to /plan?q= safe?
2. Is edit-policy (a) (question immutable on /plan) the right call vs re-running preflight on edit? Any honesty risk in the "What POLARIS will do" panel?
3. Intake handoff in same PR — correct? ConcurrentRunError handled? Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
```

---
## iter-2 revision (all iter-1 P1+P2 folded)
- **P1#1 (real gate):** /plan uses the FULL intake gate `runIntake(q)` on mount — NOT the weaker `checkScope`+`checkAmbiguity`. runIntake returns IntakeScopeDecision{status: in_scope|ambiguous_needs_clarification|out_of_scope|refused, scope_class, needs_disambiguation, candidate_snippets}. This is the exact clinical+PICO gate intake uses → direct-nav to /plan?q= is now gated by the SAME classifier, not the lenient /scope/check.
- **P1#2 (uploads):** /plan owns NO uploads. Run-start via /plan is QUESTION-ONLY → question is fully immutable on /plan → the one-time on-mount runIntake check is valid (nothing can change post-check). Document-grounded runs keep their existing home at the /upload route + the still-intact dashboard until a dedicated follow-up wires uploads into the new flow (filed as a follow-up issue, NOT silently dropped). This PR does not regress uploads (dashboard intact until #761).
- **P1#3 (needs_clarification/all states):** "Start research run" is enabled ONLY when status==="in_scope" AND not needs_disambiguation (or the disambiguation cluster has been picked). status out_of_scope|refused|ambiguous_needs_clarification → Start disabled + honest message + "Edit question → /intake". Mirror intake's own modal handling (AmbiguityModal/DisambiguationModal already exist + are reused).
- **P2 (scope_class):** show scope_class FROM the runIntake decision (it carries it); never derive/fabricate. Omit if absent.

Net: /plan = run `runIntake` on mount → render the plan (question display-only + decision.scope_class + honest "what happens") → Start enabled only on in_scope+resolved → `createRun({template, question, document_ids: []})` → /runs/[id] (ConcurrentRunError → callout). Edit → /intake. Intake gains "Continue to plan →" on in_scope.
Re-confirm APPROVE or list only true remaining P0/P1.
