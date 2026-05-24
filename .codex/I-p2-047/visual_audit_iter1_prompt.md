# Codex VISUAL audit — I-p2-047 (#841) Upload, A++/S bar — iter 1 of 5

You have VISION. Audit the rebuilt /upload at the A++/S bar. Front-load all; don't pick bone
from egg; APPROVE iff zero P0/P1.

## What changed (vs the C+ baseline: plain dashed rect, no icon/drag feedback, empty lower half)
- Crafted drop zone: UploadCloud icon in a circle; a real drag-active state (brand-tinted
  border+bg+icon, label flips to "Drop to upload"); idle hover + focus ring + motion primitive.
- Tokenized the upload error (was hardcoded rose).
- A factual 3-step "what happens after upload" band (Drop → Parsed + chunked → Grounds your
  questions) + an "Ask a question with your uploads →" link to /intake, filling the empty
  lower half. No fabricated claims.

## Attached
1. `upload_desktop.png` (idle, full)  2. `upload_dragactive.png` (drag-over state)
3. `upload_mobile.png`

## Locked (do NOT flag)
- Brand `#c8102e` locked; upload/parse logic + testids unchanged; copy factual.

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
per_screen_grades: { upload_desktop: "", upload_dragactive: "", upload_mobile: "" }
novel_p0: [...]
continuing_p0: []
p1: [...]
p2: [...]
highest_leverage_change_to_S: "..."
convergence_call: continue | accept_remaining
```
APPROVE iff an A-tier upload surface (responsive crafted drop zone + intentional page), zero P0/P1.
