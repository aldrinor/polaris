# Brief: I-ux-001c (#878) sub-PR 2 — Home page hero implementation (proof-as-CTA) — iter 2

## §0 cap directive (verbatim CLAUDE.md §8.3.1)

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iter count.
- "Don't pick bone from egg."
- Verdict APPROVE iff zero P0/P1.
```

## Resolution of iter-1 P1+P2 findings

### P1-001 sovereign-copy overclaim → FIXED

iter-1 brief copied "sovereign Canadian deep-research system" — wrong. The standing operator directive + memory `feedback_sovereignty_threat_model_2026_05_13` says LLM inference currently routes via OpenRouter-US (transitional), so the present-tense "sovereign" framing is a regulatory overclaim. The honest framing per `/transparency` page (sub-PR 5) is "Canadian-hosted".

**Updated subtitle copy (locked):**
> POLARIS is a **Canadian-hosted clinical research system**, built toward sovereign Canadian deployment. Every sentence in every brief is verified against its cited source by an independent model family, then sealed into a signed bundle anyone can audit offline. No verifier, no claim.

H1 unchanged ("Every sentence proves itself.") since it's a product claim, not a sovereignty claim.

### P1-002 signatureState honesty → FIXED

`home_brief_loader` return shape now INCLUDES `signatureState` (tri-valued per I-ux-001a). The proof-as-CTA card renders the signed-bundle pill ONLY when `signatureState === "gpg_verified"`. Other states get the honest counter-state copy from the existing `SignatureBadge` component (or the card omits the pill entirely + adds a small footnote "Signature attached — verify offline" / "Not signed — trust not established").

Updated `home_brief_loader` return type:
```ts
{
  claim_text: string;
  journal: string | null;
  year: number | null;
  span_text: string;
  matched_numbers_in_span: string[];
  matched_total: number;
  bundle_id: string;
  signatureState: "missing" | "present_unverified" | "gpg_verified";
  bundle_loaded: true;  // discriminator
} | { bundle_loaded: false }  // honest fallback
```

### P1-003 stale e2e test cleanup → SCOPE EXPANDED

Removing HomeKeyboardShell + ProofShowcase + RecentRunsStrip + templates grid breaks these existing tests. Sub-PR 2 MUST update/retire them in the same PR or the full e2e regresses:

- `web/tests/e2e/command_palette*.spec.ts` (5 files) — command palette is shell-level (not Home-specific); the HomeKeyboardShell wrapper instantiated it. Move palette to the AppShell or remove these tests. **Decision: keep the palette in AppShell** (the existing `web/components/app_shell.tsx` already has the global palette; the HomeKeyboardShell was redundant). Tests pass unchanged.
- `web/tests/e2e/f1_a11y.spec.ts` — Home a11y; UPDATE to point at the new selectors (eyebrow, H1, proof-as-CTA card, primary CTA button).
- `web/tests/e2e/home_g1_g8.spec.ts` — UPDATE/REPLACE: Home Phase-1 acceptance (G1-G8). The G-criteria need re-mapping to the v6 marketing-auth contract — DELETE this file and replace with `home_proof_as_cta.spec.ts` + `home_aa.spec.ts` (Codex iter-1 P1-003 fix).
- `web/tests/e2e/demo_journey.spec.ts` — walks Home → /intake → /runs etc. The Home step now uses the new selectors. UPDATE the click target from "search-input" / template-card → primary-cta-button.
- `web/tests/e2e/demo_walkthrough.spec.ts` — similar; UPDATE selectors.

Sub-PR 2 must:
1. UPDATE `web/tests/e2e/f1_a11y.spec.ts` (new selectors)
2. DELETE `web/tests/e2e/home_g1_g8.spec.ts` (superseded by home_proof_as_cta + home_aa)
3. UPDATE `web/tests/e2e/demo_journey.spec.ts` (new Home selectors)
4. UPDATE `web/tests/e2e/demo_walkthrough.spec.ts` (new Home selectors)
5. (KEEP `web/tests/e2e/command_palette*.spec.ts` unchanged — palette lives in AppShell, not HomeKeyboardShell — verify this is true; if HomeKeyboardShell uniquely owns palette, MOVE to AppShell in this PR)

### P2-001 loader VERIFIED gate → FIXED

`home_brief_loader` only labels a claim as VERIFIED CLAIM if ALL three hold:
- `faithfulness.verdict === "verified"`
- `faithfulness.span_in_bounds === true` (which now requires `span.quote !== null` per sub-PR 1 iter-3 fix)
- `faithfulness.matched_numbers.total > 0 && matched === total` (numeric claims must be fully matched)

If no claim in the bundle meets all three, fall back to "Verified clinical brief loading — see /inspector/v1-canonical-success" (honest fallback per LAW II).

### P2-002 certainty bg/fg tokens → ADDED to globals.css

Add per-certainty `--certainty-{level}-bg` tokens paired with the existing `-fg`. Expose both via Tailwind v4 `@theme` so `bg-certainty-high` / `text-certainty-high` utility classes work for future ladder backgrounds.

## Locked scope (iter-2)

### Files this sub-PR touches

1. **REBUILD `web/app/page.tsx`** (~150 LOC) — v6 marketing-auth hero with HONEST sovereignty copy
2. **NEW `web/components/home/proof_as_cta.tsx`** (~110 LOC) — verified-claim card; signatureState-aware pill rendering
3. **NEW `web/lib/home_brief_loader.ts`** (~60 LOC) — server-side bundle reader; VERIFIED gate; honest fallback
4. **NEW `web/tests/e2e/home_proof_as_cta.spec.ts`** — Playwright e2e
5. **NEW `web/tests/e2e/home_aa.spec.ts`** — axe WCAG 2.2 AA
6. **UPDATE `web/tests/e2e/f1_a11y.spec.ts`** — new Home selectors
7. **DELETE `web/tests/e2e/home_g1_g8.spec.ts`** — superseded
8. **UPDATE `web/tests/e2e/demo_journey.spec.ts`** — new Home selectors
9. **UPDATE `web/tests/e2e/demo_walkthrough.spec.ts`** — new Home selectors
10. **EDIT `web/app/globals.css`** — add `--certainty-*-bg` tokens + Tailwind `@theme` mappings

If HomeKeyboardShell uniquely owns the command palette (will verify before deleting), the palette moves to AppShell as part of this PR. Otherwise, just delete HomeKeyboardShell + its usage in `web/app/page.tsx`.

## Locked v6 copy

```
EYEBROW (small caps, brand-red): POLARIS · CANADIAN-HOSTED CLINICAL RESEARCH

H1 (display 56/68, Geist Bold): Every sentence proves itself.

SUBTITLE (body-lg muted):
POLARIS is a Canadian-hosted clinical research system, built toward sovereign
Canadian deployment. Every sentence in every brief is verified against its
cited source by an independent model family, then sealed into a signed
bundle anyone can audit offline. No verifier, no claim.

PROOF-AS-CTA CARD label: VERIFIED CLAIM · LIVE EXAMPLE
PROOF-AS-CTA CARD body: <real claim text from canonical bundle, numerics bolded green>
PROOF-AS-CTA CARD footer: ✓ matched <N> of <total> numbers against <journal year> source span. <signature pill conditional on signatureState>

PRIMARY CTA: Try a verified brief →   (links to /intake)
```

## Smoke test plan (npm not pnpm)

```bash
cd web && npm ci && npm run dev
# Browser: http://localhost:3000/
cd web && npm run typecheck && npm run lint
cd web && npm run test:e2e -- tests/e2e/home_proof_as_cta.spec.ts tests/e2e/home_aa.spec.ts tests/e2e/f1_a11y.spec.ts tests/e2e/demo_journey.spec.ts tests/e2e/demo_walkthrough.spec.ts
```

## Acceptance

- Matches family-template 4 visual reference at Codex A+ bar
- HONEST sovereignty wording ("Canadian-hosted", NOT "sovereign Canadian")
- VERIFIED gate enforced (verdict + span_in_bounds + matched_numbers full)
- signatureState-aware pill rendering
- All existing e2e tests still pass after Home refactor
- Codex visual audit via `codex exec -i` returns APPROVE on live render
- Playwright e2e passes
- axe WCAG 2.2 AA returns zero violations
- IntendedUseBanner mounted above chrome

## Files I have ALSO checked and they're clean

- `web/components/global/intended_use_banner.tsx` — reusable from sub-PR 1
- `web/lib/inspector_bundle_loader.ts` + `web/lib/proof_replay_adapter.ts` — already exposes signatureState + verdict + span_in_bounds + matched_numbers
- `web/components/inspector/bundle_header.tsx` SignatureBadge — tri-state component reusable
- `docs/web/i_ux_001d_route_frame_map.md` — locked v6 row 1
- `web/p2shots/I-ux-001d/family_templates/family_template_4_marketing_auth_desktop.png` — visual target
- Memory `feedback_sovereignty_threat_model_2026_05_13` — sovereignty wording rule
- The current `web/components/app_shell.tsx` to confirm the command palette is shell-level (verifying in smoke)

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
  p1_001_sovereignty_copy_fixed: PASS | FAIL_with_detail
  p1_002_signature_state_threaded: PASS | FAIL_with_detail
  p1_003_test_cleanup_scoped: PASS | FAIL_with_detail
  p2_verified_gate_correct: PASS | FAIL_with_detail
  p2_certainty_bg_tokens: PASS | FAIL_with_detail
```
