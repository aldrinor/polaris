# Codex diff review — I-ux-001c sub-PR 3 (Intake v6)

## §0 cap directive (CLAUDE.md §8.3.1, verbatim)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Phase

Diff review (sub-PR 3 of approximately 7 for I-ux-001c). The brief was APPROVED Codex iter-4 (accept_remaining, 0 P0/P1). This call reviews the actual diff against the approved brief.

## Diff under review

`.codex/I-ux-001c-3/codex_diff.patch` — sha256 in the trailer.

## Approved brief acceptance criteria (must verify in diff)

1. Visual-only v6 evolution: brand-red eyebrow + display H1 + tightened subtitle
2. `web/components/ui/textarea.tsx` added (native styled `<textarea>` per Codex brief iter-3 option 2)
3. `web/app/intake/components/auto_domain_chip.tsx` added (8-domain heuristic; returns `null` when no domain crosses threshold — LAW II)
4. Intake form's `Input` swapped to the new `Textarea`; `maxLength={2000}` preserved
5. Backend logic preserved verbatim: `runIntake`, `runDisambiguation`, ambiguity modal, scope_decision_view, `/source_review` handoff
6. STEPS grid dropped from `web/app/intake/page.tsx`
7. PdfDropBanner preserved
8. AppShell chrome preserved (`/intake` is NOT chromeless)
9. ALL existing testids preserved: `intake-page`, `intake-question-input`, `intake-submit`, `intake-form`, `scope-decision-view`, `intake-continue-to-plan`
10. NEW `intake_v6.spec.ts` (4 cases); UPDATED `intake.spec.ts` (eyebrow text swap)
11. Other 4 intake.* tests UNCHANGED (intake_disambiguation, intake_disambiguation_negative, intake_edge, intake_g1_g8)
12. typecheck PASS, lint PASS

## Specific checks (`specific_check_responses`)

- `backend_logic_preserved`: PASS / FAIL — runIntake/runDisambiguation/ambiguity-modal/scope-decision-view/source_review handoff is bit-identical to HEAD before the visual rebuild
- `honest_fail_auto_domain`: PASS / FAIL — auto_domain_chip returns `null` when no domain crosses threshold; no fabricated "custom" fallback
- `textarea_uses_native_with_tokens`: PASS / FAIL — textarea.tsx uses native `<textarea>` (since `@base-ui/react/textarea` doesn't exist) but applies the same design-token classes as input.tsx
- `maxlength_preserved`: PASS / FAIL — `maxLength={2000}` preserved on the new Textarea
- `existing_testids_preserved`: PASS / FAIL — all 6 testids listed in criterion 9 remain on the same DOM nodes
- `appshell_intake_chrome_preserved`: PASS / FAIL — `/intake` continues to render inside AppShell (NOT chromeless)
- `playwright_assertions_real`: PASS / FAIL — `intake_v6.spec.ts` asserts on real DOM shape (testids, text content, attributes) not just presence

## Output schema (BIND)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
specific_check_responses:
  backend_logic_preserved: PASS | FAIL_with_detail
  honest_fail_auto_domain: PASS | FAIL_with_detail
  textarea_uses_native_with_tokens: PASS | FAIL_with_detail
  maxlength_preserved: PASS | FAIL_with_detail
  existing_testids_preserved: PASS | FAIL_with_detail
  appshell_intake_chrome_preserved: PASS | FAIL_with_detail
  playwright_assertions_real: PASS | FAIL_with_detail
```

## Read these for context

- Brief (APPROVE iter-4): `.codex/I-ux-001c-3/brief.md`
- Diff: `.codex/I-ux-001c-3/codex_diff.patch`
- Branch: `bot/I-ux-001c-sub-pr-3-intake`
- Project §-1.1 audit standard: `CLAUDE.md`
