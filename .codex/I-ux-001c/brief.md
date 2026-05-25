# Brief: I-ux-001c (GH #878) — Hero implementation, sub-PR 1: Inspector Proof Replay v6 (centerpiece) — iter 2

## §0 cap directive (verbatim CLAUDE.md §8.3.1)

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Resolution of iter-1 findings (3 P1 + 5 P2 + 2 P3 all addressed)

### iter-1 P1-1: spec conflict on proof-panel vertical order

**Authoritative answer**: spatial order matches temporal reveal order per Codex iter-3 TRACK 1 sub-track A direction (`docs/web/i_ux_001d_motion_still_convention.md` row 1 + `.codex/I-ux-001b/visual_audit_v5.txt` Codex direction):

```
Claim echo  →  Faithfulness  →  [div]  →  Evidence strength  →  [div]  →  Source (climax)  →  [div]  →  Signature  →  Limits disclosure
```

**Mobile**: same temporal/spatial order. Codex TRACK 1 sub-track B mobile audit acknowledged the Figma mobile prototype's spatial reorder did NOT take effect at render time ("temporal narrative still works because ladder appears before source" — `.codex/I-ux-001d/motion_audit_verdict_iter3.txt`). For CODE implementation, the spatial order IS the temporal order; the mobile-prototype rendering artifact does not bind code.

The desktop v6 prototype screenshot (`web/p2shots/I-ux-001b/hero_stage2_v6_desktop.png`) shows the order as `Claim → Verified → Source → Evidence-Strength → Signature → Disclosure` because that was the iter-2 PROTOTYPE render — but TRACK 1 mega-audit's `iter3_carryforward_addressed: PASS` confirmed the temporal/spatial-order intent is the new locked order. **Code implementation follows the locked order, not the v6 prototype screenshot's rendered order.**

### iter-1 P1-2: ProofReplay prop-scope insufficient for tri-state signature

**Resolved**: scope expands to thread the necessary props through InspectorView → ProofReplay.

Current state confirmed via `web/app/inspector/[runId]/inspector_view.tsx`:
```tsx
<ProofReplay
  sections={bundle.verifiedReport.sections}
  evidencePool={bundle.evidencePool}
/>
```

NEW signature for ProofReplay:
```ts
interface ProofReplayProps {
  sections: VerifiedReportSectionShape[];
  evidencePool: unknown;  // (preserve existing)
  // NEW (sub-PR 1):
  signatureState: "missing" | "present_unverified" | "gpg_verified";
  signatureKeyFingerprint?: string;
  manifest: BundleManifest;  // for bundle_id, generator_model, created_at display
  verifiedReport: VerifiedReportShape;  // for research_question + per-claim faithfulness check details
}
```

InspectorView changes (~6 lines): pass `signatureState`, `signatureKeyFingerprint`, `manifest`, `verifiedReport` to ProofReplay. Existing call sites of InspectorView (`web/app/inspector/[runId]/page.tsx`) don't change since LoadedBundle already exposes all needed fields.

### iter-1 P1-3: real bundle data contract missing v6 evidence-strength + source-identity fields

**Resolved**: define an **adapter layer** in `web/lib/proof_replay_adapter.ts` (NEW) that derives v6 display fields from the real `VerifiedReportSectionShape` + evidence-pool entries:

```ts
// web/lib/proof_replay_adapter.ts (NEW)
import type { VerifiedSentenceShape, VerifiedReportSectionShape } from "@/lib/inspector_bundle_loader";

export interface ProofReplayClaim {
  claim_id: string;
  sentence_text: string;
  faithfulness: {
    verdict: "verified" | "partial" | "unsupported";
    matched_numbers: { matched: number; total: number };  // derived from provenance_tokens overlap with cited span text
    content_words_overlap: number;
    span_in_bounds: boolean;
  };
  evidence_strength: {
    level: "very_low" | "low" | "moderate" | "high";  // derived from cited source's tier (T1 RCT → "high"; T2 review → "moderate"; T3 guideline → "high"; T4-T7 → "moderate"/"low"; missing tier → "low")
    study_type: string | null;  // derived from evidencePool entry's metadata.study_type, fallback "—"
    n_participants: number | null;  // derived from evidencePool, fallback null (don't display if missing)
    downgrade_reasons: string[];  // derived from evidence-pool entry's quality_notes, fallback empty (don't claim GRADE if absent)
  };
  source: {
    span_text: string;  // from cited span
    journal: string | null;  // evidencePool entry's metadata.venue, fallback "—"
    year: number | null;
    authors: string | null;  // first author + et al if 3+
    doi: string | null;
    tier: "T1" | "T2" | "T3" | "T4" | "T5" | "T6" | "T7" | null;  // T4+ rendered as same pill class with the tier letter; never hidden
    matched_numbers_in_span: string[];  // the actual decimals matched (for highlighting)
  };
}

export function adaptToClaim(sentence: VerifiedSentenceShape, evidencePool: unknown): ProofReplayClaim;
```

**Honest-fail rules**: any field that the real bundle doesn't carry is rendered as `—` or omitted — NEVER fabricated. The intended-use strip already warns that this is literature synthesis, not clinical advice; the adapter must preserve that honesty.

T4+ tier rendering: `T4`/`T5`/`T6`/`T7` use the SAME pill grammar as T1/T2/T3 (same width, same letter-spacing, same border), just with the tier letter changed. No special-casing. The catalogue's `SourceCard` contract gets an explicit "supports T1..T7" addendum.

### iter-1 P2-1: smoke commands corrected

```bash
# CORRECTED
cd web && npm ci && npm run dev
# then visit http://localhost:3000/inspector/v1-canonical-success in browser

# Playwright (path from web/)
cd web && npm run test:e2e -- tests/e2e/inspector_proof_replay.spec.ts  # NEW file

# axe (from repo root, not web/)
node tests/a11y/wcag_axe_scan.mjs --base http://localhost:3000 --route /inspector/v1-canonical-success
```

### iter-1 P2-2: package manager — npm (not pnpm); `web/package-lock.json` is the lockfile

Confirmed via `ls web/package-lock.json` (exists) and `ls web/pnpm-lock.yaml` (does not). All commands use `npm ci` / `npm run`.

### iter-1 P2-3: storyboard hard rules added to acceptance

New acceptance criteria items:
- **Time-to-first-proof < 400ms**: from claim click to faithfulness verdict visible. Measured via Playwright trace.
- **Claim-to-claim switch < 120ms perceived**: from claim N click to claim N+1 proof panel populated. Measured via Playwright.
- **Keyboard path**: `Enter` on a sentence = click; `Esc` = close/collapse proof panel; `J`/`K` = next/previous sentence; focus returns to the clicked sentence on `Esc`.
- **Focus trap**: while proof panel is open + has focusable controls, Tab cycles within it (escapable via `Esc`).
- **Mobile swipe-to-dismiss**: bottom-sheet honors swipe-down gesture (`touchstart`/`touchmove`/`touchend` handlers) for dismissal.
- **Reduced-motion = instant**: `@media (prefers-reduced-motion: reduce)` collapses every animation to `duration: 0ms`; no opacity ramp, no slide.

### iter-1 P2-4: motion token names corrected per design_tokens_v2.md §5

The locked tokens are 3 durations + 1 easing (NOT named "-fast-out-slow-in"):

```css
--motion-fast    120ms     micro-interactions
--motion-base    200ms     state reveals
--motion-slow    320ms     view transitions
--ease-standard  cubic-bezier(0.2, 0, 0, 1)
```

Tailwind v4 mapping in `globals.css @theme`:
```css
--duration-fast: 120ms;  /* utility: transition-[duration:var(--duration-fast)] */
--duration-base: 200ms;
--duration-slow: 320ms;
--ease-standard: cubic-bezier(0.2, 0, 0, 1);
```

### iter-1 P2-5: T4 tier rendering — addressed in adapter spec above

### iter-1 P3-1: name `IntendedUseBanner` per components_catalogue.md (not `intended_use_strip`)

New file: `web/components/global/intended_use_banner.tsx` (NEW). Used in Inspector first; reusable for other pages in subsequent sub-PRs.

### iter-1 P3-2: cross-page exit affordances deferred per the I-ux-001d carry-forward list

Inspector's "View signed bundle" / "Open knowledge graph" / "Compare with another run" exit affordances are tracked as P2 in `.codex/I-ux-001d/track4_e2e_journey_verdict_iter1.txt` and deferred to the family-page-group sub-PRs (each page-pair handles its own exit affordances when both pages exist in code). Sub-PR 1 ships Inspector hero without these exits — a follow-up sub-PR adds them once Compare + Knowledge-graph code exists.

## Scope (locked iter-2)

This sub-PR rebuilds **only** the Inspector hero band + Proof Replay component to match the v6 locked spec with the new spatial/temporal order. Subsequent sub-PRs (2-7) handle Home / edit-mode pages / monitor-mode pages / Compare / Knowledge-graph / supporting pages.

### Files this sub-PR touches

1. **`web/components/proof_replay/proof_replay.tsx`** — REBUILD: new spatial order, two-judgment grammar, sealed-evidence-block, 6-beat opacity-reveal motion, prefers-reduced-motion. NEW props: `signatureState`, `signatureKeyFingerprint`, `manifest`, `verifiedReport`.
2. **`web/components/inspector/inspector_proof_header.tsx`** — REBUILD: H1 + two-judgment chip row + provenance two-band strip (humanized verdicts) + tri-state SignatureBadge.
3. **`web/components/global/intended_use_banner.tsx`** — NEW: amber band component per `IntendedUseBanner` contract.
4. **`web/lib/proof_replay_adapter.ts`** — NEW: adapter from `VerifiedSentenceShape` + evidence-pool to `ProofReplayClaim`.
5. **`web/app/inspector/[runId]/inspector_view.tsx`** — thread new props through to ProofReplay (~6 lines).
6. **`web/app/inspector/[runId]/page.tsx`** — render `<IntendedUseBanner />` above InspectorView in the layout.
7. **`web/app/globals.css`** — add `@theme` tokens for v6 colors (faithfulness greens/amber/magenta + evidence-strength slate-blues + duration tokens).
8. **`web/tests/e2e/inspector_proof_replay.spec.ts`** — NEW Playwright e2e covering: sentence click → 6-beat reveal; claim-switch perceived <120ms; keyboard Enter/Esc/J/K; focus trap; mobile bottom-sheet swipe-dismiss; reduced-motion instant.
9. **`web/tests/a11y/inspector_aa.test.mjs`** — NEW axe-core scan target zero violations on Inspector route.

LOC estimate: ~200-280 LOC (within 200-LOC PR cap soft target; if exceeded, split point is `proof_replay_adapter.ts` as a separate first PR).

## Smoke test plan (§-1.2 step 3 — corrected commands)

```bash
# 1. Local dev
cd web && npm ci && npm run dev
# Browser: http://localhost:3000/inspector/v1-canonical-success
# Verify visually: H1, two-judgment chips, sentence click → reveal animates, mobile viewport (devtools 390x844) → bottom-sheet variant

# 2. Playwright e2e
cd web && npm run test:e2e -- tests/e2e/inspector_proof_replay.spec.ts

# 3. axe WCAG 2.2 AA (from repo root)
node tests/a11y/wcag_axe_scan.mjs --base http://localhost:3000 --route /inspector/v1-canonical-success

# 4. TypeScript + lint
cd web && npm run lint && npm run type-check

# 5. Build
cd web && npm run build
```

## Acceptance criteria

- Inspector hero matches v6 prototype intent at Codex's A+ bar (verified via `codex exec -i live_render_desktop.png` + `codex exec -i live_render_mobile.png` after `npm run dev`)
- Spatial/temporal order matches the iter-3-locked order (Claim → Faithfulness → Evidence Strength → Source → Signature → Disclosure)
- Mobile bottom-sheet variant per Stage 4 spec; swipe-to-dismiss works
- Motion: 6-beat opacity-reveal in code with `prefers-reduced-motion` honored (instant on reduce)
- Time-to-first-proof <400ms (Playwright trace); claim-switch <120ms perceived
- Keyboard path: Enter/Esc/J/K all work; focus trap inside open proof panel; focus returns to clicked sentence on Esc
- All 12 v6 checklist items pass on the live page (sealed evidence block, two-judgment separation, tri-state signature, intended-use banner, no jargon, semantic-icon restraint, etc.)
- Codex visual audit via `codex exec -i` returns APPROVE
- Playwright e2e passes (sentence click → proof panel populates; signature badge correct state; reduced-motion path)
- axe-core scan returns zero WCAG 2.2 AA violations on `/inspector/[runId]`
- T4-T7 tier rendering verified via a fixture test (NEW: `web/tests/fixtures/source_tier_t4_through_t7.json`)
- Honest-fail rules verified: when adapter sees missing study_type/n/doi, renders `—` not fabricated text

## Codex review iteration plan (military-order continuous gates)

For this and every subsequent sub-PR:
- **iter 1-5 brief review** — acceptance criteria + scope cap (this iter is brief iter-2)
- **diff review** post-implementation (5-iter cap, separate from brief)
- **Codex visual audit** (`codex exec -i`) on the LIVE rendered page (desktop + mobile screenshots from `npm run dev` localhost) — APPROVE required
- **Codex lively audit** — Playwright trace screenshots at key motion timestamps (t=0/120/250/400/600/700ms) reviewed via `codex exec -i` to verify the live motion matches the convention
- **Codex e2e journey audit** — after this sub-PR + the next one merge, the 2-page click-through is reviewed in journey context
- All gates required to merge; operator handles `gh pr merge` in the morning

## Files I have ALSO checked and they're clean

- `web/lib/inspector_bundle_loader.ts` — `signatureState` tri-state correct (I-ux-001a)
- `web/lib/signed_bundle.ts` — schema correct
- `web/components/inspector/bundle_header.tsx` — `SignatureBadge` tri-state correct
- `web/components/inspector/family_segregation_badge.tsx` — correct
- `web/public/canonical_bundles/v1_canonical_success/` — real signed bundle (I-ux-001a #875)
- `docs/web/{proof_replay_storyboard,components_catalogue,design_tokens_v2,i_ux_001d_route_frame_map,i_ux_001d_motion_still_convention}.md` — design source-of-truth, all locked

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
  p1_spatial_order_resolved: PASS | FAIL_with_detail
  p1_prop_threading_resolved: PASS | FAIL_with_detail
  p1_adapter_data_contract_resolved: PASS | FAIL_with_detail
  p2_smoke_commands_corrected: PASS | FAIL_with_detail
  p2_storyboard_hard_rules_in_acceptance: PASS | FAIL_with_detail
  p2_motion_token_names_aligned: PASS | FAIL_with_detail
  p2_tier_rendering_covers_T4_through_T7: PASS | FAIL_with_detail
```
