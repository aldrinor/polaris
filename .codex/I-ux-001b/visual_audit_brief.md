# Codex VISUAL audit — I-ux-001b hero prototype v1 (Stage 2 Proof Replay)

## Context
- POLARIS = sovereign Canadian clinical deep-research AI. Top-tier S-tier UI is the goal for the Carney gift demo (Sep 2026). Operator: "frontier-competitive, lively, e2e — not half-ass."
- This is iter 1 of the Figma prototype for the I-ux-001 plan §4 hero ("Challenge any sentence"). Spec source: docs/web/proof_replay_storyboard.md, docs/web/components_catalogue.md, docs/web/design_tokens_v2.md.
- Figma file: https://www.figma.com/design/Is7pehpxPdn3ZOOgCsyUjs
- Attached image: web/p2shots/I-ux-001b/hero_stage2_v1_desktop.png (1440×900 desktop).

## What the screenshot shows
- LEFT: brief reading column — title, provenance strip ("18 claims · 16 verified · 2 partial · 0 unsupported · ⬡ signed bundle · evidence-strength: 12 high · 6 moderate"), section heading, 3 verified-claim sentences. The MIDDLE sentence is "challenged" (2px brand-red left border, indent).
- RIGHT: proof panel (480w) docked, showing the 6-beat reveal:
  - Beat 1 — "Challenged sentence" header + the sentence echo (real claim from the shipped bundle: SURPASS-2/3/4 treatment-difference text with the −0.15/−0.39/−0.45 percentage-point estimates).
  - Beat 2 — "IS THIS SENTENCE FAITHFUL TO THE SOURCE?" + green VERIFIED chip + "independent-family check" + deterministic-check sub-line.
  - Beat 3 — "HOW STRONG IS THE EVIDENCE?" + slate-blue HIGH badge (asymmetric corners — square leading edge to signal "different category of read" vs faithfulness chip) + "RCT · Phase 3 · n=1,879" + downgrade line.
  - Beat 4 — SOURCE: SourceCard with journal/year/T1-tier/DOI/why-selected + SourceSpanPreview muted block with underlined matched span.
  - Beat 5 — green Signature pill ⬡ Signed bundle + sealed-in line + verify-offline link.
  - Beat 6 — collapsed "▸ What this does NOT prove" disclosure.

## What I want from this audit
A FRONTIER-BAR (S-tier, Linear/Stripe/Vercel-craft-competitive) visual critique against the storyboard intent. The standard 16-dimension design audit applies (visual, user-flow, data-flow, focus, clarity, frontier-head-to-head, accessibility, provability, responsive, EN-FR-i18n-ready, content/microcopy, security-verified, performance-implied, dense-table UX where relevant, role governance, independent-rendered-verification).

The non-negotiable things to call out HARD if they are broken:
1. **Two-judgment separation** — does the eye instantly read the green faithfulness chip and the slate-blue certainty badge as TWO INDEPENDENT JUDGMENTS, or do they blur? (Lethal-in-clinical-context confusion.)
2. **Proof-as-hero feel** — does the proof panel READ as the differentiating moment, or as a sidebar? When a reviewer's eyes land here, do they think "I've never seen research I could check like this"?
3. **Typography craft** — measure, line-height, weights — does this read as Linear/Stripe-tier, or as a default Tailwind app?
4. **Sentence affordance** — the prose is heavily underlined. Storyboard intent is a HAIRLINE TINT at alpha 0.35, NOT a full hyperlink-style underline. Picky-user verdict: does the brief read as a confident document, or does the underline noise undermine it?
5. **Challenged-sentence treatment** — the 2px red left border is the Beat-0 selection commitment. Is it clear, or is the indent breaking the visual rhythm?
6. **Empty white space discipline** — operator-flagged on the live site. Is the left column padding right? Is anything wasted/cramped?
7. **What's MISSING** that an S-tier hero needs. Be ruthless. If you'd rebuild a section from scratch, say so.

## Output format
```
## What works (briefly — 3-5 lines)
## What does NOT work (per dimension; reserved for issues, not praise)
### Two-judgment separation
### Proof-as-hero feel
### Typography craft
### Sentence affordance
### Challenged-sentence treatment
### Empty space discipline
### Anything else / missing
## Verdict
- grade: A+ | A | B+ | B | C+ | C
- top-3 highest-leverage fixes for iter 2
- absent: is there anything the prototype OMITS that a frontier-beating hero must have?
```

Be picky. Be specific. Cite competitor patterns (Linear, Stripe, Vercel, Perplexity, Elicit, OpenEvidence) where they're doing it better. Don't soften.
