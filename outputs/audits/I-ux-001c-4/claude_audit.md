# I-ux-001c sub-PR 4 — claude_audit

## Scope
Visual-only marketing-auth chrome evolution of `/source_review`. Brief APPROVED Codex iter-3 (accept_remaining, 0 P0/P1). Diff APPROVED Codex iter-1 (accept_remaining, 0 P0/P1, all 5 specific checks PASS).

## Single source-of-truth file: web/app/source_review/page.tsx

### Changed (header chrome only)
- Brand-red eyebrow "SOURCES · POLARIS CLINICAL RESEARCH" (text-primary, tracking-[0.14em])
- Display H1 "Review the sources POLARIS will check." (text-3xl sm:text-4xl, font-bold)
- Tightened subtitle locked verbatim per iter-2 P2
- Edit-question link moved to eyebrow row (right side) preserving /intake?q= deep-link

### Preserved verbatim
- listTemplates, asTemplateId, TIERS, TIER_DOT, TIER_LABEL, prettyDomain
- TierCard component + minRequired adequacy bar
- ErrorState + LoadingState + retry flow
- No-question fallback Intake link
- Continue CTA /plan?q=...&template=...
- All existing testids

## Brand-red authorization (3 paths, all preserved)
1. Brand identity (NEW eyebrow + existing Continue CTA + decorative)
2. Evidence-role T1 (existing TIER_DOT['T1'] per I-p2-003 #742)
3. Interactive affordance (existing text-primary on links + retry)

## Tests (NEW)
- web/tests/e2e/source_review_v6.spec.ts (2 cases, mocked /api/v6/templates)
- P2 carry-forward: mock fixture shape is not exact TemplateContent type — non-blocking for chrome assertions

## Honest-fail (LAW II) compliance
- No fabricated metrics: page continues to say "the actual sources are retrieved + adequacy-checked during the run"
- No synthetic readiness percentages
- listTemplates contract unchanged → real config/v6_templates/*.json data

## Files I have ALSO checked and they're clean
- web/components/app_shell.tsx — /source_review is in authed routes set; no change
- web/components/app_shell_gate.tsx — /source_review NOT chromeless
- web/lib/api.ts — listTemplates contract unchanged
- web/app/intake/components/intake_form.tsx — links to /source_review?q=... unchanged
- web/app/plan/page.tsx — receives /plan?q=...&template=... unchanged

## Verdict
Ready for operator merge queue.
