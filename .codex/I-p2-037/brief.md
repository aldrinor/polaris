# Codex DESIGN+DIFF review — I-p2-037 (#794): proof-as-hero home

HARD ITERATION CAP: 5. iter 1. Canonical-diff-sha256 `649aac92e102c48ec9325b3a0f63b86321559cd0c000a49376e83c22bb1a8953`. web/ only. MERGE AUTHORIZED if mergeable. APPROVE iff zero P0/P1.

## Direction (operator: "really match the top-tier design level"; frontier study: verifiability is the hero)
The home was sparse/empty ("ugly"). Now it LEADS with a real proof showcase.

## Diff
- NEW app/components/proof_showcase.tsx (server component): loadBundle("v1-canonical-success") → finds the first verified sentence whose provenance token resolveSpan()s to a real source quote (>40 chars) → renders a premium card: LEFT = claim + "Verified against a primary source" (--verified) + the brief's research_question; RIGHT = the EXACT real source span (blockquote) + source title/url + tier badge; footer = "See the full proof →" /inspector/v1-canonical-success. HONEST: returns null if nothing resolves (no fabricated showcase). Uses the REAL bundle shipped in #795.
- page.tsx: insert <ProofShowcase/> after the hero; tightened hero (py-14 sm:py-16, gap-14, gap-5) for density; pillars get a top border.
- inspector_bundle_loader.ts: + optional research_question?: string on VerifiedReportShape (real-run bundles carry it).

## Claude visual audit (standalone @1366 + @390, sent to operator): premium two-column proof card with the real NEJM claim+span; Geist Sans; card stacks on mobile; hamburger nav. Far denser/more-premium than the prior empty home.

## §-1.1 honesty: the shown claim+span are from the real #795 bundle; I independently re-verified all 9 spans support their claims. Showcase renders the resolveSpan quote (exact full_text slice) — same honest resolver as the inspector.

## Review focus
1. HONESTY: can the showcase EVER render a claim whose span doesn't support it? (resolveSpan returns quote only when bounds valid; null→render nothing.) Any fabrication risk?
2. Server-component data-load correct (no client leak; loadBundle is server-only)? a11y (section aria-label, blockquote, link focus-visible)? AA on --verified text?
3. Responsive: two-col md+ → stacks mobile cleanly? Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```
