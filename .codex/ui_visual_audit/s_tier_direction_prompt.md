# Codex S-TIER design direction + per-screen audit (DECISION + VISUAL)

You are a world-class product designer + the design decision-maker (CHARTER §1). The operator's bar has moved: **not B-, not "good enough" — A++ to S-tier**, visually competitive with AND differentiated from Perplexity / ChatGPT Deep Research / Gemini. Every tab, page, and step. You will define the design system AND audit each attached screen at that bar.

## Product
POLARIS — sovereign Canadian **clinical deep-research** product; one-shot demo to the PM of Canada (Mark Carney). The DIFFERENTIATOR is **per-sentence verifiability**: every claim links to the exact cited source span (the "Proof Replay" inspector). Lean into that harder than Perplexity leans into sources — proof IS the product.

## Research-backed S-tier invariants (from Stripe/Linear/Vercel + 2026 best practice — use as the floor, then exceed)
- Typography as brand: ONE family (Geist is in use), 4–6 sizes (12/14/16/18/20/24/32), weights 400/500/700, tabular nums + mono for IDs/data, optical alignment.
- Systematic spacing grid: one base scale (4/8/12/16/24/32…), consistent gaps/padding everywhere; generous whitespace (expansive = "expensive").
- Color restraint: near-neutral + ONE brand accent (Canada red) used once/screen, meaning-only (never decoration); semantic tokens (danger/verified/primary).
- SIX microstates on every interactive element: default / hover / focus(custom 2–3px ring, offset) / active / disabled(40–50% opacity) / loading(skeleton matching layout, not a spinner).
- Hairline borders (0.5–1px low-alpha), brand-temperature-tinted shadows (not pure gray), consistent radius (cards 8–12px, inputs ~8, controls). Motion 150–200ms ease, defined once.
- Designed empty/loading/error states (high-trust moments), memorable not generic.
- "Interaction-dense, not visually dense." Every screen has ONE obvious primary action the composition guides toward.

## Attached screens (current live, except #5 is the just-rebuilt Contracts)
1. Home (/) 2. Intake (/intake) 3. Inspector / Proof Replay centerpiece 4. Upload 5. Contracts (REBUILT B-) 6. Pin Replay 7. Sign-in.
NOTE: cred-gated pages (dashboard, benchmark, memory, source-review, and the Plan→Run→Compare journey) are NOT attached — operator will provide a demo cred so they join the audit.

## Deliver (readable markdown)
1. **POLARIS S-tier design language** — the specific token + pattern decisions (type scale, spacing grid, color/semantic tokens, the 6 microstate specs, focus ring, border/shadow/radius, motion, empty/loading) tuned for a clinical-institutional research workbench that out-classes frontier. Be concrete (values).
2. **The signature move** — what ONE design idea makes POLARIS visually unmistakable + S-tier (the proof/verification interface is the candidate). How to make it the hero across the product.
3. **Per-screen audit at the A++/S bar** — for each attached screen: current grade, the gap to S, and the specific moves to get there. Be harsh.
4. **Build order** — foundation-first (which shared tokens/primitives to ship before per-page rebuilds) + the per-tab sequence. Note what's blocked on the demo cred.

Honest constraint: sovereignty wording stays "Canadian-hosted" + OpenRouter-US disclosure (intentional). Judge everything else at the S bar.
