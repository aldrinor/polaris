# Codex VISUAL audit — I-ux-001b hero prototype v4 (iter 4)

## Iter-3 verdict (.codex/I-ux-001b/visual_audit_v3.txt): grade A

v4 addresses all three iter-3 fixes + adds mobile coverage:

1. **"Sentence-to-proof bridge beyond shared ①"** → added an active-status line under the challenged sentence: italic "proved against the SURPASS-2 source span →" in muted-fg with a small green tick at start. This makes the selected sentence read as "activated," not merely highlighted. Also keeps the shared ① marker.

2. **"Source span heavier as climax"** → bumped source-span text 13/22 → 15/26; left rule 3px → 4px; padding bumped 12px → 14px; **bolded matched numbers** −0.15 / −0.39 / −0.45 in verified-fg color (run-level setRangeFontName + setRangeFills) so the eye locks onto the numeric proof inside the prose.

3. **"Mobile bottom-sheet"** → built a Stage 4 frame (390×844, iPhone 14 Pro): status bar / brand / title / provenance chip / challenged-sentence card with green ① marker + green left border above the sheet / bottom-sheet at 75vh with drag handle / inside: ① + claim echo / Verified word + sub-line / italic source intro / source card with T1 pill / source span with BOLD GREEN matched numbers / 4-step ladder / signed-bundle pill / limits disclosure. The same ① marker appears immediately above and inside the sheet so the summoned link works vertically.

## Attached
- web/p2shots/I-ux-001b/hero_stage2_v4_desktop.png (1440×900)
- web/p2shots/I-ux-001b/hero_stage4_v4_mobile.png  (390×844)
- web/p2shots/I-ux-001b/hero_stage2_v3_desktop.png (v3, for delta comparison)

## What I want
At iter 3 you said: "Not yet frontier-beating in front of PM Carney's office, but the remaining gap is product theater and typographic precision, not concept clarity."

Now decide if v4 closes that gap — both desktop AND mobile. If not, what's left? Be SHARP, not gentle. I want this audit to push HARD against frontier competitors (Linear/Stripe/Vercel/Perplexity/Elicit/OpenEvidence).

## Output
```
## Desktop v4 — per iter-3 fix resolved?
- bridge beyond ① → RESOLVED-A+ | RESOLVED-A | RESOLVED-B | PARTIAL | NOT-RESOLVED
- source span as climax → ditto
- typography craft → ditto
- absent emotional moment → ditto

## Mobile v4 — assessment
- summoned proof on mobile → ditto
- source-as-climax on mobile → ditto
- overall mobile bar → ditto

## NEW issues v4 introduced
## What still keeps this from A+
## Verdict
- desktop grade: A+ | A | B+ | B
- mobile grade: A+ | A | B+ | B
- top-3 fixes for iter 5 (or "NONE — ship it")
- one-line: frontier-beating in front of PM Carney's office NOW?
```
