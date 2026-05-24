# Codex brief — I-p2-044 (#835): Home page S-rebuild (front door)

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## What this is
A BRIEF (plan + acceptance-criteria) review, NOT a diff review. The attached images are the
CURRENT LIVE home (https://polarisresearch.ca/, grade B), desktop + mobile — the starting
point. Approve iff the plan moves it to A++/S (proof-led, differentiated), fixes the
correctness issue, and won't break the e2e contract. Diff + dual VISUAL `-i` gate come after.

## Current live home (attached) — honest read
Clean but generic AI-landing-page: centered maple-leaf mark (looks pixelated) → pill
"⬡ Sovereign Canadian deep research" → H1 "Deep research you can check, line by line." →
subtext → search box+Verify → a plain "A REAL VERIFIED CLAIM" ProofShowcase card → 3 plain
text pillars (Provable/Sovereign/Snowball) → footer. The proof — our actual differentiator —
reads as a secondary card, not the hero.

## Correctness fix (not just visual)
Hero pill "Sovereign Canadian deep research" is a present-tense sovereignty OVERCLAIM. Per
honest-sovereignty wording (LLM inference currently routed via OpenRouter-US, disclosed at
/transparency) it MUST read "Canadian-hosted deep research" — matching the footer + rest of
the app. No "fully sovereign"/"no US vendor" present-tense claims.

## Plan (web/app/page.tsx + its home sub-components if needed)
1. Hero: fix the pill -> "Canadian-hosted deep research". Keep the strong H1 + subtext
   (tighten). Keep the maple-leaf signature (operator element #767) but right-size/place it as
   a crafted mark, not a pixelated blob. Keep `home-hero-search` (testid + action="/intake" +
   Verify submit w/ focus-visible — e2e-locked).
2. Proof as the hero (signature move): elevate ProofShowcase so the real verified claim ->
   cited span is the page centerpiece, not a plain card below the fold. Apply S-tier proof
   grammar + brand-tinted card elevation (shadow-card).
3. Pillars: refine Provable/Sovereign/Snowball to crafted, tokenized treatment (not plain text
   columns). Honest wording (the Sovereign pillar already says "built for Canadian-hosted...
   public sources via logged Canadian egress" — keep honest framing).
4. Preserve real data: ProofShowcase (real verified claim + real source span) + RecentRunsStrip
   (real runs). No fabricated proof. Keep SiteFooter.
5. Type scale / spacing / motion / microstates per docs/web/s_tier_design_system.md.

## e2e contract I MUST NOT break (web/tests/e2e/home_g1_g8.spec.ts)
- exactly ONE <header> + exactly ONE <main> (hero uses <section>, not a 2nd <header>).
- `home-hero-search` form visible, action="/intake", input submits `q` (URL gets q=...).
- the Verify submit button inside `home-hero-search` visible + className contains
  `focus-visible`.
- no banned dev-language strings in body text; no console errors on load.

## Files I have ALSO checked and they're clean (no break)
- web/app/components/proof_showcase.tsx, recent_runs_strip.tsx, home_keyboard_shell.tsx
  (real-data components; the shell renders the single <header>/nav).
- web/components/site_footer.tsx, signature/maple_leaf_signature_lazy.tsx — preserved.
- home_g1_g8.spec.ts, demo_journey.spec.ts, performance.spec.ts — contract enumerated above.
- Brand #c8102e + globals.css tokens — reused, not changed.

## Question
APPROVE iff this plan genuinely moves the front door to A++/S (proof-led + differentiated),
fixes the overclaim, and breaks none of the e2e contract. If you see a stronger front-door
structure (e.g. proof integrated INTO the hero vs. below it), say so as P1/P2 with specifics.
