# Codex VISUAL audit — I-p2-044 (#835) Home, A++/S bar — iter 2 of 5

You have VISION. iter 2. In iter 1 (REQUEST_CHANGES) you raised 2 P1s; both fixed. Re-grade at
the A++/S bar. Front-load all; APPROVE iff zero P0/P1.

## Fixes since iter 1
- **P1 mobile ProofShowcase clipping/overflow** → grid cells now `min-w-0`, claim + cited
  passage `break-words` (+ hyphens), CTA row wraps. The proof artifact is fully readable on
  375w with no horizontal overflow.
- **P1 "N" badge overlapping mobile** → confirmed it is the Next.js DEV-mode indicator (absent
  on the deployed prod site); hidden in these acceptance captures.

## Attached
1. `home_fold_desktop.png` — first viewport desktop (proof leads?).
2. `home_desktop.png` — full desktop.
3. `home_mobile.png` — full mobile 375w (check zero clipping + readable proof).

## Locked (do NOT flag)
- Brand `#c8102e` locked; maple-leaf braille mark is operator element #767 (judge placement
  only). ProofShowcase/RecentRunsStrip render REAL data (don't change content).

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
per_screen_grades: { home_fold: "", home_desktop: "", home_mobile: "" }
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
highest_leverage_change_to_S: "..."
convergence_call: continue | accept_remaining
```
APPROVE iff premium A-/A, proof-led, overclaim-free, zero P0/P1 (P2 polish may remain).
