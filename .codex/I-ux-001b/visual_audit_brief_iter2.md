# Codex VISUAL audit — I-ux-001b hero prototype v2 (iter 2)

## Iter-1 verdict (.codex/I-ux-001b/visual_audit_v1.txt): grade B
Top-3 fixes I addressed in v2:
1. **Underline noise** → REMOVED textDecoration UNDERLINE on all sentence text. Replaced with a 1px hairline tinted bottom border (verified-color at ~35% alpha) on each sentence row. Non-challenged sentences are now dimmed (text fill alpha 0.55, certainty dot alpha 0.45) so the eye knows the challenged one is active.
2. **Two-judgment structural separation** → rebuilt:
   - Beat 2 (Faithfulness): editorial framing question + BIG bold VERIFIED word (22px) + italic "by an independent model family" + a green-tinted **deterministic-check list** ("✓ numeric match — every number in the claim appears in the span (6/6)" etc.). Checklist grammar.
   - Beat 3 (Evidence strength): editorial framing question + a 4-step **HORIZONTAL ORDINAL LADDER** (VERY LOW · LOW · MOD · HIGH) where the current level (HIGH, slate-blue) is taller and bolder than the others. Ladder grammar (ordinal), structurally different from Beat 2's checklist/yes-no grammar.
3. **Challenged sentence border** → corrected to VERIFIED green (storyboard Beat 0: "2px left border of its faithfulness color"). Was incorrectly brand-red in v1.

Plus:
- Title tightened (26px / -2% tracking) to fit on one line.
- Provenance strip rebuilt as a two-band layout (FAITHFULNESS row | EVIDENCE STRENGTH row) with labeled categories — quieter than v1.
- "Click any sentence — POLARIS will prove or limit it." editorial-italic affordance hint added above the section heading.
- Challenged sentence row now has a soft verified-bg tint (alpha 0.4) so it reads as "actively selected" not "errored."

## Attached
- web/p2shots/I-ux-001b/hero_stage2_v2_desktop.png (1440×900)
- Compare against iter-1: web/p2shots/I-ux-001b/hero_stage2_v1_desktop.png

## What I want
Same frontier-bar audit. SPECIFICALLY confirm whether iter-1's three issues are RESOLVED, then push HARDER:
- Is the two-judgment separation now unmistakable to a clinical reviewer?
- Does the proof STILL feel like a sidebar, or has it moved closer to "summoned by the sentence"? (No visual connector added yet — flag if it's still needed.)
- Is the typography craft closer to Stripe/Linear, or still bureaucratic?
- Iter-1 absent finding: "the visceral product moment — click any sentence and watch the system prove what is and is not supported." Did the editorial hint help, or is it still missing?
- What's the v3 highest-leverage fix?

## Output
```
## Per iter-1 finding — resolved?
1. underlines → RESOLVED | PARTIAL | NOT-RESOLVED — <why>
2. two-judgment structural separation → ditto
3. challenged-sentence treatment → ditto
4. proof-as-hero-vs-sidebar → ditto
5. typography craft → ditto
6. empty-space discipline → ditto
7. absent emotional moment → ditto

## NEW findings (v2 introduced) — P0/P1/P2/P3
## Verdict
- grade: A+ | A | B+ | B | C+ | C
- top-3 fixes for iter 3
- one-line: would this be defensible as a frontier-beating clinical-DR hero in front of PM Carney's office?
```
