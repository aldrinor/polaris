# Codex DIFF review — I-p2-026 (#765): WCAG 2.2 AA automated axe pass + 2 contrast fixes

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Canonical-diff-sha256 `71a923c560d262eaedb14cb10bbeb1caf093c6018b8012f95d125bc3da519220`. web/ only, 5 files, 270-line diff. MERGE AUTHORIZED if mergeable. APPROVE iff zero P0/P1.

## iter-1 → iter-2 delta (your 3 harness findings fixed + what they exposed)
- **P1 (fail-open — FIXED):** the harness now asserts HTTP 2xx + an expected-content selector per page BEFORE axe runs, and ANY page error / non-2xx / readiness-miss is counted as BLOCKING (fail-loud, LAW II). It can no longer pass on a page that didn't render.
- **P2a (impact — FIXED):** blocking now counts ALL WCAG-tagged violations (any impact), not just critical+serious — it's a true AA gate.
- **P2b (hidden tab panels — FIXED):** the inspector page now cycles every `[role=tab]` and re-scans the revealed panel. **This immediately exposed 2 real hidden violations** (Reasoning + Sources tabs), now fixed:
  - `reasoning_trace_timeline.tsx`: the `<dl>` directly contained `<span>` wrappers (invalid — only `<dt>/<dd>/<div>` allowed) → `definition-list` + 10× `dlitem`. Changed to `<div>` grid-item wrappers (HTML5-valid, identical render).
  - `sources_panel.tsx`: the `max-h-[400px] overflow-auto` source-snapshot `<pre>` had no keyboard access → `scrollable-region-focusable` (WCAG 2.1.1). Added `tabIndex=0` + `role=region` + `aria-label` + focus ring.
- **Final hardened re-scan: 0 blocking across all 6 pages, true exit 0** (captured before the pipe).

## Context
#765 = "Verify: WCAG 2.2 AA accessibility pass (automated + manual keyboard/screen-reader)". Operator (2026-05-22) authorized the **automated** slice now (public pages, no creds/cost), fix violations via the normal cycle; the auth-gated routes + manual keyboard/SR remain operator-side. This is that automated slice.

## Diff (3 files)
1. `web/tests/a11y/wcag_axe_scan.mjs` (NEW): `@axe-core/playwright` scan over 6 pages (home, sign-in, inspector, audit/export, knowledge-graph, source-review) with tags `wcag2a/wcag2aa/wcag21a/wcag21aa/wcag22aa`. Backend-driven pages (graph, source-review) get their API intercepted with REAL fixture data — `tests/fixtures/graph_payload.json` + the actual `config/v6_templates/*.json` (read via fileURLToPath for Windows-safe paths) — so the FULL rendered UI is scanned, not offline error states. Exits non-zero on any serious/critical violation.
2. `web/components/ui/tabs.tsx`: inactive `TabsTrigger` inherited `text-muted-foreground` on the `bg-muted` list strip → muted-foreground (oklch L 0.556) on bg-muted (L 0.97) FAILS 4.5:1 (7 inspector tabs flagged SERIOUS). Added explicit `text-foreground/70` to the trigger base (clears AA; still lighter than the `data-[selected]:text-foreground` active tab). Pure visual contrast change, no behavior change.
3. `web/app/source_review/page.tsx`: the "how sources are gathered" callout used `text-muted-foreground` on `bg-muted/40` → same contrast failure (1 SERIOUS). Switched the callout to `bg-card` (muted-foreground on white passes AA, as every other info card on the page already does).

## Evidence (empirical, both scans run)
- **Before:** 8 SERIOUS color-contrast node-violations (inspector ×7 tabs, source-review ×1 callout). home/sign-in/audit/knowledge-graph already clean.
- **After the 2 fixes:** `0 critical+serious violations across all 6 pages` (re-scan output captured). typecheck + `npm run build` green.

## Files I have ALSO checked and they're clean
- `components/ui/tabs.tsx` is used ONLY by `inspector_view.tsx` (grep) — the contrast fix is contained; no other tab surface regresses.
- The token math: `--muted-foreground: oklch(0.556 0 0)`, `--muted: oklch(0.97 0 0)`, `--card: oklch(1 0 0)`, `--foreground: oklch(0.21 ...)`. muted-foreground passes AA on white (home/audit prove it) but not on the 0.97 muted bg — hence both fixes move text/ bg toward white-backed or darker-text.
- `text-foreground/70` rendered contrast verified by axe (it samples computed pixels incl. opacity) — passes.

## Honest scope (partial #765)
This is the AUTOMATED axe slice on the **public/canonical** pages only. NOT covered (operator-side, flagged in the issue + the audit): the auth-gated flow routes (intake/plan/source-review-live/dashboard/compare need prod creds for full content), and the MANUAL keyboard-navigation + screen-reader passes (need a human). #765 stays OPEN after this merges; this is real partial progress + a reusable scan harness, not a full close.

## Review focus
1. Are the 2 contrast fixes correct + sufficient (no behavior/visual regression beyond the intended contrast bump)? Is `text-foreground/70` a sound inactive-tab token vs. the selected `text-foreground`?
2. Is the scan honest (real fixture data, not synthetic; scans rendered UI not error states)? Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```
