# I-ux-001c sub-PR 5 — claude_audit

## Scope
Visual-only marketing-auth chrome evolution of `/plan`. Brief APPROVED Codex iter-1 (0 P0/P1/P2, 5/5 checks PASS). Diff APPROVED Codex iter-2 (accept_remaining, 0 P0/P1, 5/5 checks PASS) after iter-1 P1 fix on the Playwright mock URL pattern.

## Surface (header chrome only)
- Brand-red eyebrow "PLAN · POLARIS CLINICAL RESEARCH" (text-primary, tracking-[0.14em])
- Edit-question link moved to eyebrow row (right side, preserves /intake href)
- Display H1 "Confirm the plan before the run."
- Tightened subtitle locked verbatim

## Preserved verbatim
- runIntake re-check on mount (gate), runDisambiguation, createRun, ConcurrentRunError
- Vetted-question card (display-only) + plan steps
- Start-run button + disable gates (inScope + disambigResolved + !starting)
- Error/concurrent/blocked states
- All existing testids: plan-page, plan-blocked, plan-concurrent, plan-start-run

## Iter trail
- Diff iter-1: REQUEST_CHANGES (mock URL `**/api/v6/intake**` didn't match actual `/api/v6/api/intake`)
- Diff iter-2: APPROVE (mock URL fixed to `**/api/intake**` glob)

## Honest-fail (LAW II) compliance
- No fabricated metrics
- All behavior gates preserved
- No silent fallbacks

## Files I have ALSO checked and they're clean
- web/components/app_shell.tsx — `/plan` in authed routes; no change
- web/components/app_shell_gate.tsx — `/plan` NOT chromeless
- web/lib/api.ts — runIntake/runDisambiguation/createRun unchanged
- web/app/source_review/page.tsx — links to /plan via Continue CTA; unchanged

## Verdict
Ready for operator merge queue.
