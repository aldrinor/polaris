# Claude architect audit — I-f13-004

**Issue:** F13 adversarial: source retraction during replay
**Branch:** bot/I-f13-004
**Canonical-diff-sha256:** eb557dce0182cfd4f12d411600bb053dacf732926e78e968a0995bfc3821b681
**Brief verdict:** APPROVE iter 2 (P1 fix: pin default-B to "2026-04-30"; P2 fix: pass_rate=0.83 to avoid double alert; P2 fix: attribution scope = newly retracted only)
**Diff verdict:** pending Codex iter 1

## Substrate honesty
- New `retracted_source_ids?: string[]` is optional demo-data; production reads source-retraction status from Crossref/PubMed retraction API (post-Carney M-INT-3+ wiring).
- New `getRetractionContext(a, b)` is a pure helper returning IDs newly retracted between A and B; semantics deliberately scoped to "newly attributed" only (carried-over IDs not re-attributed).
- Page default-B explicitly pinned to "2026-04-30" — single string literal in page.tsx; demo-tier convention. Production fetches the pin list from `/runs/{run_id}/pins` and chooses default per UX policy.
- Sentence-count alert is the only metric to receive retraction-attribution per scope; pass-rate retraction-attribution is a deliberate follow-up (separate semantics: pass_rate aggregates per-sentence verification rate, retraction affects sentences directly).

## §9.4 N/A frontend.

## CHARTER §1 LOC cap
- 84 net (`pin_replay_demo.ts +14`, `pin_regression.ts +27 -2`, `page.tsx +13 -1`, `pin_retraction_handled.spec.ts NEW +29`). Under 200.

## E2E verification
- Production build (`npx next build`) succeeds; `/pin_replay` static prerender unchanged.
- All 4 specs pass against `next start -p 3738` in 3.3s on chromium:
  - `pin_replay.spec.ts` (existing): default-B pin works; original assertions hold.
  - `pin_replay_diff.spec.ts` (existing): +13% delta unchanged.
  - `pin_regression_alert.spec.ts` (existing): unchanged.
  - `pin_retraction_handled.spec.ts` (new): A=2026-04-30 → B=2026-05-15 fires sentence-count alert with attribution to demo-clin-005, NO pass-rate alert, demo-clin-002 NOT in attribution.

## Verdict
APPROVE.
