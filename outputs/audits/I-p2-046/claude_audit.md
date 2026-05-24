# Claude architect audit — I-p2-046 (#839): Contracts editor S-rebuild

## Goal
Push /contracts (Evidence Contract editor) from B- (clean but utilitarian; primary action below
the fold) to a confident A-tier config tool.

## What changed (1 file + doc, +24/-7)
- `web/app/contracts/_editor.tsx`: static crafted "Save + download" action bar (ring + brand
  shadow + one-line explainer) at the form end; entity-type `<select>` height matched to inputs
  (h-9) + shared motion; jurisdiction chips on the motion primitive; mobile entity row stacks
  (flex-col sm:flex-row).
- `docs/web/s_tier_design_system.md`: Contracts grade.

## The sticky→static decision (Codex visual iter-1 P1)
iter-1 used a `sticky bottom-4` action bar; the visual gate caught that it OVERLAID editable
fields (Expected entities on desktop, Minimum source coverage on mobile) — wrong for a config
surface where every field is editable. Resolved by making the bar STATIC (a crafted dock at the
form end) — keeps the visual treatment, zero overlay. The form is short enough that
"always-reachable sticky" wasn't worth obscuring inputs.

## Preserved (no logic/contract change)
Every data-testid (contract-form, ce-question, ce-by, ce-jur-*, tier inputs, ce-ent-name/type/
rm-*, ce-add-entity, ce-claim-*, ce-rm-claim-*, ce-add-claim, contract-submit, contract-saved,
contract-errors); the sr-only-checkbox chip toggle; native <select> (fill/select compat); save/
validation logic. contract-submit stays inside <form>.

## e2e
contracts_g1_g8 4/4 pass (1 header/1 main, no banned dev-language, nav parity, no console
errors). contract_editor submit spec needs the save backend (not up in dev) — unchanged path.

## Dual Codex gate
- Brief APPROVE (iter 1). Visual `-i` APPROVE (iter 2: desktop A / mobile A-; iter-1 sticky-
  overlay P1 fixed). Code diff APPROVE (iter 1, zero findings).

## Constraints honored
Brand `#c8102e` untouched; tokens only; logic/testids preserved; no test relaxation.

canonical-diff-sha256: 51106d3d19f2f4a7be6d5bf1327e5fb1262f8c49148ddb9a4113a91511c637e5
