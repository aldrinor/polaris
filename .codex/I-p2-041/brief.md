# Brief — I-p2-041 (#829): P2 visual redo, page 1 — Contracts editor D+ → B-

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the doc is force-APPROVE'd on remaining non-P0/P1 findings.
- If you're holding back a P1 for the next round — DON'T. Surface it now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Context
P2 visual redo (#829): every prior P2 Codex review was code-only — Codex never saw
pixels. New protocol: dual visual verification (Claude views + Codex `codex exec -i`)
+ this code-correctness review. Contracts was the worst page (your visual audit: **D+**,
"raw internal form"). This is the page-1 remediation.

## Change (one file: `app/contracts/_editor.tsx`)
VISUAL-LAYER rebuild only. ALL state/logic (`buildContract`/`validateContract`/state/
handlers) and EVERY `data-testid` preserved. Native `<input>`/`<fieldset>`/`<legend>`/
black `bg-foreground` button → design system: Card sections, labelled fields with
plain-language tier hints (kills bare "T1/T2/T3"), accessible chip-toggles for
jurisdictions + claim-jurisdictions (sr-only checkbox inside a styled `<label>` —
preserves `input[type=checkbox]` semantics + the `ce-jur-*` testids), 3-col coverage
grid, claims sub-card, ghost icon remove-buttons, brand primary "Save + download".
The entity-type control stays a (class-styled) native `<select>` for now.

## Acceptance criteria
- AC1: design-system controls; no raw native inputs except the (styled) entity-type select.
- AC2: every `data-testid` preserved; `contract_editor.spec.ts` (fills text + submits, never
  touches jurisdiction/type controls) still passes.
- AC3: honest copy; no overclaim. prod build + eslint + prettier green.

## Visual verification (the new gate — already run)
Claude viewed + Codex `-i` re-graded: **D+ → B-** ("credible product surface, demo-ready").
Verdict file: `.codex/ui_visual_audit/contracts_regrade_verdict.txt`. Residual A-gaps Codex
named (native select → needs a real Select component; hierarchy; chip polish; intro copy)
are tracked for the A-polish pass — NOT claimed done here.

## Files I have ALSO checked and they're clean
- `contract_editor.spec.ts` (only fills ce-question/ce-by/ce-ent-name-0/ce-claim-stmt-0/
  ce-claim-ents-0 + clicks submit; no jurisdiction/type interaction → chip-toggle safe).
- `visual_60_baselines.spec.ts` snapshots `/contracts` (F11) → baseline needs
  `--update-snapshots` (intentional pixel change; non-required lane).
- `components/ui/{card,input,button}.tsx` (APIs used), `lib/contracts.ts` (logic untouched).

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
