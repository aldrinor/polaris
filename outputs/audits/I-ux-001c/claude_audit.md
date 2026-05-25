# Claude architect audit — I-ux-001c (#878) sub-PR 1: Inspector Proof Replay v6

## Scope review

Per the brief APPROVED Codex iter-2, this sub-PR rebuilds the Inspector hero band + Proof Replay component to match the v6 prototype (CENTERPIECE).

9 files committed:
1. `web/lib/proof_replay_adapter.ts` (NEW, 211 LOC) — derives `ProofReplayClaim` from real bundle
2. `web/components/global/intended_use_banner.tsx` (NEW, 57 LOC) — amber INTENDED USE band
3. `web/app/globals.css` (+18 LOC) — motion + per-certainty fg tokens
4. `web/components/proof_replay/proof_replay.tsx` (REBUILD, 696 LOC; 487 net additions) — v6 6-beat hero
5. `web/components/inspector/inspector_proof_header.tsx` (REBUILD, +89 LOC net) — v6 two-band provenance + humanized verdicts
6. `web/app/inspector/[runId]/inspector_view.tsx` (+9 LOC) — prop-thread
7. `web/app/inspector/[runId]/page.tsx` (+12 LOC) — IntendedUseBanner mount
8. `web/tests/e2e/inspector_proof_replay.spec.ts` (NEW, 195 LOC) — Playwright e2e
9. `web/tests/a11y/inspector_aa.test.mjs` (NEW, 80 LOC) — axe WCAG 2.2 AA

## Architecture decisions

**Data adapter pattern** (Codex iter-2 P1-3 resolution): `flattenToClaimList` is the single source of truth for v6 claim shape. Both ProofReplay and InspectorProofHeader use it, guaranteeing the header's faithfulness counts and the panel's per-claim verdicts agree on every read. Missing bundle fields render as null and the UI omits the row — no fabricated clinical metadata (LAW II).

**Motion implementation**: CSS transition-delay per-beat (not state-machine timers) keeps the reveal deterministic, testable, and SSR-safe. `prefers-reduced-motion: reduce` is honored via the `@theme` duration tokens (which the @media collapses to 0). The Playwright reduced-motion test validates beats appear within 200ms.

**Keyboard model**: window-level keydown listener with input/textarea guard. Focus return on Esc uses a Map<claimId, buttonRef> for O(1) lookup. Tab order within the proof panel is the natural DOM order (no manual trap needed because the panel has only links/details — no focus-stealing widgets).

**Mobile breakpoint**: matchMedia `(max-width: 767px)` via the lazy-useState pattern (Codex lint guidance — set-state-in-effect avoided). Sheet uses shadcn's built-in dismiss gestures.

## Honest-fail validations

- Adapter `extractNumerics` matches Unicode minus, ASCII minus, decimals, percentages
- `countMatches` is string-contains (no regex special-casing required)
- T1-T7 tiers ALL render via the same pill grammar (Codex iter-2 P2 fix)
- Abort verdicts humanized at the header level — raw `abort_*` tokens NEVER reach the UI (zero-jargon banlist)
- Tri-state SignatureBadge (existing component) wired through end-to-end

## What I did NOT do in this sub-PR (per brief scope cap)

- Other 11 pages (Home, Intake, Source-Review, Plan-Review, Run-progress, Dashboard, Compare, Knowledge-graph, Audit, Sign-in, Transparency) — sub-PRs 2-7
- Cross-page exit affordances (P3 carry-forward from I-ux-001d TRACK 4) — added when paired pages exist
- Per-claim cycling animation between selections (smooth crossfade between claim N and claim N+1) — current implementation snaps to the new claim's beats; the storyboard's <120ms perceived target is met by the snap; smooth transition is a polish item
- Receipt subview / signature key fingerprint display — `signatureKeyFingerprint` is threaded through as a prop and currently unused (reserved for receipt view in a later sub-PR per the brief)

## Smoke test status

- `npm run typecheck`: PASS ✓
- `npm run lint`: PASS ✓ (zero errors; pre-existing warnings in unrelated files)
- `npm run dev` + visual verification: NOT RUN in this session (operator's npm/dev environment)
- Playwright e2e + axe: NOT RUN in this session (requires `next start -p 3738` + SCREENSHOT_BASE_URL)
- Codex visual audit (`codex exec -i` on live render): NOT RUN — requires the dev server up

## Per-Issue 5-artifact triple status

- `.codex/I-ux-001c/brief.md` ✓
- `.codex/I-ux-001c/codex_brief_verdict.txt` ✓ APPROVE iter-2
- `.codex/I-ux-001c/codex_diff.patch` ✓ (this commit)
- `.codex/I-ux-001c/codex_diff_audit.txt` ⏳ Codex diff review next
- `outputs/audits/I-ux-001c/claude_audit.md` ✓ (this file)
