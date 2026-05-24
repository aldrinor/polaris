# Codex VISUAL audit — I-p2-043 (#833) Inspector, A++/S bar — iter 3 of 5

You have VISION. Visual-gate iter 3. In iter 2 (REQUEST_CHANGES) you raised 2 P1s; both fixed.
Re-grade at the A++/S bar. Front-load all remaining findings; APPROVE iff zero P0/P1.

## What I changed in response to your iter-2 P1s
- **P1 "mobile tab rail overflows the viewport"** → the 8-tab rail is now contained in a
  horizontal-scroll lane: desktop hugs content, mobile scrolls within the viewport instead
  of bleeding off-screen.
- **P1 "manifest-open splits trust into two floating islands"** → restructured the trust
  zone into one left-aligned column: the two trust chips (two-family + signature) grouped
  on one row, then the bundle/model/date line, then the "Full manifest" disclosure which
  now expands as one coherent boxed block (muted inset) directly beneath — no side-by-side
  split.

## Attached images (in order)
1. `success_desktop.png` — populated, 1280w.
2. `success_mobile.png` — populated, 375w (check tab rail is contained).
3. `success_manifest_open_desktop.png` — manifest expanded (check it's one coherent artifact).
4. `abort_desktop.png` — abort shape.

## Locked constraints (do NOT flag)
- Brand red `#c8102e` operator-locked; tokens fixed (verified=green/contradiction=amber/
  destructive=maroon).
- Proof Replay split-view INTERNALS are OUT OF SCOPE this PR (separate component issue).
  Judge the proof-header band, hero, trust grid, disclosure, tab containment — not the
  panel internals.

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
per_screen_grades: { success_desktop: "", success_mobile: "", manifest_open: "", abort: "" }
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
highest_leverage_change_to_S: "..."
convergence_call: continue | accept_remaining
```
APPROVE iff the page framing reads as premium A-/A research software with proof leading and
zero P0/P1 (P2 polish may remain). If still blocked, name the specific P1.
