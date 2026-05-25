# Brief: I-ux-001c (#878) sub-PR 2 — Home page hero implementation (proof-as-CTA)

## §0 cap directive (verbatim CLAUDE.md §8.3.1)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iter count.
- "Don't pick bone from egg."
- Verdict APPROVE iff zero P0/P1.
```

## Scope

Per `docs/web/i_ux_001d_route_frame_map.md` row 1 + family template 4 (marketing-auth, `web/p2shots/I-ux-001d/family_templates/family_template_4_marketing_auth_desktop.png`):

Replace `web/app/page.tsx` (currently 205 LOC of templates grid + ProofShowcase + RecentRunsStrip + keyboard shell) with the v6 marketing-auth pattern:

- Tiny brand-red eyebrow label "POLARIS · CANADIAN-HOSTED CLINICAL RESEARCH" (Inter Medium 11px, 12% letter-spacing)
- Display-size H1 "Every sentence proves itself." (Geist Bold 56/68, single line on ≥sm)
- Body-lg subtitle (~19/30 muted) — "POLARIS is a sovereign Canadian deep-research system for clinical decision-makers. Every sentence in every brief is verified against its cited source by an independent model family, then sealed into a signed bundle anyone can audit offline. No verifier, no claim."
- **Proof-as-CTA card** (the differentiator): a REAL verified clinical claim block with continuous 2px verified-green left rule + small VERIFIED CLAIM · LIVE EXAMPLE label + the actual claim text (with green-bolded numerics) + matched-N-of-N stamp + ⬡ Signed bundle pill
- ONE primary CTA: dark pill-button "Try a verified brief →" linking to `/intake`
- IntendedUseBanner mounted above the page chrome (reuse from sub-PR 1)
- Site shell (header + footer) preserved

## What NOT to include in sub-PR 2

- ProofShowcase carousel from the current home — replaced by the SINGLE static proof-as-CTA card per v6 plan §1 "one CTA"
- Templates grid (CLINICAL_DRUG_AUDIT, etc.) — moves to /intake which already lists them
- RecentRunsStrip — belongs to /dashboard, not Home
- HomeKeyboardShell — keyboard-only shortcuts for power users; out of scope for the marketing-auth A+ critical-path hero

These are NOT lost — they're moved to their canonical pages or removed per the v6 marketing-auth contract ("ONE primary action").

## Files this sub-PR touches

1. **REBUILD `web/app/page.tsx`** (~150 LOC target; was 205 LOC) — v6 marketing-auth hero
2. **NEW `web/components/home/proof_as_cta.tsx`** (~90 LOC) — the verified-claim card block; reusable on sign-in + transparency in future sub-PRs
3. **NEW `web/lib/home_brief_loader.ts`** (~40 LOC) — server-side: pick the canonical verified bundle (`v1-canonical-success`), use the existing `flattenToClaimList` adapter to get its first verified claim, return `{ claim_text, journal, year, span_text, matched_numbers, bundle_id }` for the CTA card
4. **NEW `web/tests/e2e/home_proof_as_cta.spec.ts`** — Playwright e2e: page loads; H1 visible; proof-card renders real verified-claim content; CTA links to `/intake`; IntendedUseBanner present
5. **NEW `web/tests/e2e/home_aa.spec.ts`** — axe WCAG 2.2 AA scan

## Apply carry-forward from sub-PR 1 Codex audits

- **P2-002** add `--certainty-*-bg` token pair to `globals.css` (so future ladder backgrounds have proper bg/fg tokens; not consumed in Home itself but the home `proof_as_cta` doesn't need it, sub-PR 2's contribution is just adding the tokens)
- **iter-4 P2 hydration mismatch** does NOT apply to Home (no matchMedia in this page)

## Data honesty (LAW II)

The proof-as-CTA card MUST display a real claim from the actual canonical bundle. If `home_brief_loader` returns null (no canonical bundle on disk):
- Render a humble "fallback" card that says "Verified clinical brief loading — see /inspector/v1-canonical-success" with NO fabricated claim text
- NEVER hard-code a fake claim

## Smoke test plan (corrected commands per sub-PR 1 P2)

```bash
cd web && npm ci && npm run dev   # localhost:3000
# Browser: http://localhost:3000/
# Verify: eyebrow label visible, H1 'Every sentence proves itself.', sub, proof-as-CTA card with real claim, primary 'Try a verified brief →' CTA
cd web && npm run typecheck && npm run lint
cd web && npm run test:e2e -- tests/e2e/home_proof_as_cta.spec.ts tests/e2e/home_aa.spec.ts
```

## Acceptance

- Matches family-template 4 visual reference at Codex A+ bar
- Real verified-claim data loaded from canonical bundle (NOT hard-coded text); honest fallback if bundle missing
- Codex visual audit via `codex exec -i` returns APPROVE on live render
- Playwright e2e passes
- axe WCAG 2.2 AA returns zero violations
- IntendedUseBanner mounted above chrome (reuse from sub-PR 1)

## Codex review iteration plan

- iter 1 = this brief review (acceptance criteria + scope cap)
- iter 2-5 (if needed) = diff review post-implementation
- Visual audit + lively audit = separate `codex exec -i` calls after `npm run dev`

## Files I have ALSO checked and they're clean

- `web/components/global/intended_use_banner.tsx` — reusable from sub-PR 1
- `web/lib/inspector_bundle_loader.ts` + `web/lib/proof_replay_adapter.ts` — server-side data path already exists; home_brief_loader reuses them
- `docs/web/{proof_replay_storyboard, components_catalogue, design_tokens_v2, i_ux_001d_route_frame_map}.md` — locked design spec
- `web/p2shots/I-ux-001d/family_templates/family_template_4_marketing_auth_desktop.png` — visual target

## Output schema (per CLAUDE.md §8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
specific_check_responses:
  scope_cap_appropriate: PASS | FAIL_with_detail
  proof_as_cta_data_honesty: PASS | FAIL_with_detail
  removal_decisions_correct: PASS | FAIL_with_detail
```
