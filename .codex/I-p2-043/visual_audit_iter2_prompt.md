# Codex VISUAL audit — I-p2-043 (#833) Inspector, A++/S bar — iter 2 of 5

You have VISION. This is visual-gate iter 2. In iter 1 you returned REQUEST_CHANGES with 3
P1s; I rebuilt accordingly. Re-grade the attached screenshots at the A++/S bar. Front-load
ALL remaining findings now; don't pick bone from egg; APPROVE iff zero P0/P1.

## What I changed in response to your iter-1 P1s
- **P1 "trust layer too thin / form metadata"** → consolidated the question + proof + trust
  into ONE crafted proof-header band under the H1: the **verify rate is now the headline
  proof artifact** (large green "100%"), with section count + "every sentence traces to its
  cited source span", and below a hairline divider the two-family invariant chip + signature
  chip + bundle id/model/date + "Full manifest" disclosure. Surface = card + ring + brand
  shadow.
- **P1 "abort loses the hero"** → abort now shows an H1 ("Signed research bundle") + an amber
  verdict pill ("No verified sections") inside the same band. Clear inspector state.
- **P1 "mobile: proof demoted below tab bar"** → the proof band now anchors directly under
  the H1, before the tabs; metadata is one consolidated secondary line in the band.

## Attached images (in order)
1. `success_desktop.png` — populated, 1280w.
2. `success_mobile.png` — populated, 375w.
3. `success_manifest_open_desktop.png` — "Full manifest" disclosure expanded (zero-loss IDs).
4. `abort_desktop.png` — abort shape (now titled + verdict pill).

## Locked constraints (do NOT flag)
- Brand red `#c8102e` operator-locked; tokens verified=green / contradiction=amber /
  destructive=maroon fixed.
- Proof Replay split-view INTERNALS are OUT OF SCOPE this PR (separate component issue).
  Judge the proof-header band, the hero, the trust line, the disclosure, and how the
  centerpiece is promoted — not the panel internals.

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
APPROVE iff the proof-header band reads as a premium, crafted proof artifact (A-/A bar) with
the proof leading, zero P0/P1. If still B-tier, REQUEST_CHANGES with specific fixes.
