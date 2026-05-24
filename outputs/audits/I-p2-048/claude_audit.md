# Claude architect audit — I-p2-048 (#843): Pin Replay empty-state S-rebuild

## Goal
Push /pin_replay from C to A. In the demo the pin registry is empty (since #627), so the empty
state is the only visible state (the populated timeseries/diff needs backend pin data).

## What changed (1 file + doc, +42/-2)
- `web/app/pin_replay/page.tsx` (EmptyPinReplay only): a crafted ghost-timeline preview card
  (skeleton bar silhouette + ghost pin nodes + ghost labels, under "Your pinned runs line up
  here as a timeline" + a one-line concept caption) — makes the temporal-evidence-drift
  differentiator tangible + fills the formerly-empty page. SKELETON SHAPES ONLY (aria-hidden,
  motion-reduce:animate-none); no fabricated dates/counts/verdicts. EmptyState (icon/title/CTA)
  + `pin-replay-empty` preserved.
- `docs/web/s_tier_design_system.md`: Pin Replay grade.

## LAW II / honesty
The ghost timeline is explicitly data-free — a designed empty/skeleton state (design-system
"ghost timeseries" pattern), NOT fabricated pin data. The populated-state path (snapshot cards,
PinTimeseries, DiffSidePanel, regression alert + all their testids) is byte-identical.

## e2e — honest status
pin_replay_g1_g8 3/4 pass (G1/G6 single header+main, G2 no banned dev-language, nav parity). G8
(zero console) FAILS on a Next-16 RSC warning ("Set objects are not supported" server→client).
PROVEN PRE-EXISTING: stashed my edit, re-ran G8 against baseline — fails identically. My diff
adds only static JSX (no Set, no server→client prop). Not relaxed; follow-up to find/fix the
Set crossing the RSC boundary on pin_replay. The populated spec needs pinned data the demo
lacks (#627) — untouched.

## Dual Codex gate
- Brief APPROVE (iter 1). Visual `-i` APPROVE (iter 1: desktop A / mobile A-). Code diff APPROVE
  (iter 2; iter-1 P2 motion-reduce applied) — `.codex/I-p2-048/codex_diff_audit.txt`.

## Constraints honored
Brand `#c8102e` untouched; tokens only; populated path/testids preserved; no test relaxation;
no fabricated data.

canonical-diff-sha256: 4370881e4640f8d8d4d9a193af9c9c7befe7322e0d93cba2438c66092827b0e7
