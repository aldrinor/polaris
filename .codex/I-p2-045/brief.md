# Codex brief — I-p2-045 (#837): Intake page S-rebuild ("Ask")

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks; polish is P2/P3.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on non-P0/P1; no iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

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

## What this is
A BRIEF (plan) review. Attached: the CURRENT LIVE /intake (grade B-), desktop + mobile.
Approve iff the plan reaches A++/S without breaking the e2e contract. Diff + dual VISUAL `-i`
gate come after.

## Current live /intake (attached) — honest read
A small "Check scope" Card floats in a large mostly-empty viewport: title "Ask a clinical
research question" + explainer, then a Card (question label, default-height input, helper
text, "Check scope" button + sample-question chips). Functional but sparse and un-premium;
the input — the product's primary action — doesn't read as the hero, and the lower ~half of
the page is dead space.

## Plan (web/app/intake/page.tsx + web/app/intake/components/intake_form.tsx)
1. **Input is the hero**: enlarge the question input (h-12+, text-base) so it's the inviting
   focal point; the "Check scope" primary button gets weight; sample chips refined (tokenized
   hover, rounded-full). Keep label "Your question".
2. **Fill the empty surface honestly**: add a crafted "how it works" strip (3 steps:
   Ask → scope-checked so no run is wasted → verified brief where every claim is span-checked)
   OR a proof-forward reassurance band — describing the REAL flow (no fabricated data),
   reinforcing the differentiator. Reduces the floating-card emptiness.
3. **Crafted card**: brand shadow-card elevation; S-tier spacing/type/microstates.
4. **Preserve everything**: testids `intake-page`, `intake-form`, `intake-question-input`,
   `intake-submit`, `intake-error`, `intake-continue-to-plan`, `disambig-picked-label`, and
   the scope-result chain `scope-decision-view`/`scope-status-badge`/`scope-class-value`; the
   `?q=` prefill from the home hero; scope-check + disambiguation modal logic; ErrorState.

## e2e contract I MUST NOT break (intake_g1_g8.spec.ts + intake.spec.ts)
- exactly ONE <header> + ONE <main> (AppShell provides; the page is a <section> — keep it).
- no banned dev-language (slice/scaffold/placeholder/phase 0/post-carney/i-cd-) in body text;
  no console errors; primary nav visible.
- intake-page / intake-question-input / intake-submit visible; submitting a question shows
  scope-decision-view + scope-status-badge + scope-class-value; out-of-scope + injection
  cases still resolve through the same flow.

## Files I have ALSO checked and they're clean (no break)
- web/app/intake/components/{scope_decision_view,ambiguity_modal,disambiguation_modal,
  pdf_drop_banner}.tsx — preserved (scope-result + modal UI; logic untouched).
- @/lib/api (runIntake/runDisambiguation) — untouched. @/components/states/state_kit
  (ErrorState) — reused. Brand #c8102e + globals tokens — reused.

## Question
APPROVE iff this plan makes /intake an A++/S "ask" surface (input-as-hero + intentional, not
empty) without breaking the e2e/scope contract. Stronger structure ideas → P1/P2 with specifics.

---
## iter 2 — resolution of your iter-1 P1 + P2s
- **P1 (stale `/Clinical scope discovery/i` assertion):** verified it exists NOWHERE in the
  current intake code, and the live prod page shows "Ask a clinical research question" — so
  `intake.spec.ts:21` has been failing silently behind the non-functional e2e lane (#720).
  RESOLUTION (your recommendation): add **"Clinical scope discovery"** as a crafted uppercase
  EYEBROW label directly above the H1 (`text-xs tracking-widest uppercase text-muted-foreground`).
  Honest (the scope-check IS clinical scope discovery) + a premium eyebrow pattern + satisfies
  the existing test without editing it. NOT relaxing a test to hide a bug — restoring the
  asserted visible string as an intentional design element.
- **P2.1 (multi-line field):** keeping the single-line `<Input>` (enlarged h-12, text-base) —
  clinical questions are typically one line, and this preserves `intake-question-input`,
  maxLength=2000, disabled/loading, and Playwright fill/inputValue exactly. Textarea deferred.
- **P2.2:** the how-it-works band is a SIBLING <div> after the form card — no nested card, no
  extra header/main landmark.
- **P2.3:** copy stays factual — describes only the real ask → scope-check → span-verified
  brief flow; no fabricated metrics; no banned dev-language.

Re-APPROVE iff this resolves the P1 + holds the e2e/scope contract.
