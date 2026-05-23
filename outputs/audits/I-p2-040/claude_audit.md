# Claude architect audit — I-p2-040 (#827): pin_replay empty state → EmptyState kit

## Scope (Codex UI-direction P3 — constrained empty-state consistency)
pin_replay was the one cred-independent page hand-rolling its empty state (bare <p>)
instead of the shared EmptyState kit (#750) used by 8 other pages.

## Shipped (1 file: app/pin_replay/page.tsx, empty branch only)
EmptyState(icon=History, title, description, action=Ask-a-question→/intake) + an intro
explaining the feature; "query"→"question" jargon kill; data-testid preserved; populated
view untouched.

## Verification (LAW II)
next build compiled; eslint + prettier clean; local screenshot = structured empty state
(icon + title + explainer + brand-red CTA), void gone. pin_replay spec asserts no empty
copy → no break. Honest copy (no overclaim).

## Codex
Brief APPROVE; diff APPROVE (iter 1), zero P0/P1/P2.

## Residual / follow-up
- P1 (demo-journey-middle live audit) — cred-gated.
- Other empty/loading states across the product already use the kit; this closed the one gap.
