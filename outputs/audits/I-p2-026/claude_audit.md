# Claude audit — I-p2-026 (#765): WCAG 2.2 AA automated axe pass

## Scope (partial, operator-authorized)
Operator (2026-05-23) authorized the **automated** WCAG slice now (public +
canonical-bundle pages, no creds/cost); the auth-gated flow routes + manual
keyboard/screen-reader passes remain operator-side. This is that automated slice
+ a committed, reusable scan harness. **#765 stays OPEN** after merge — this is
real partial progress, not a full close.

## Deliverable
`web/tests/a11y/wcag_axe_scan.mjs` — an `@axe-core/playwright` scan over 6 pages
(home, sign-in, inspector, audit/export, knowledge-graph, source-review) against
`wcag2a/wcag2aa/wcag21a/wcag21aa/wcag22aa`. Backend-driven pages get their API
intercepted with REAL fixture data (`graph_payload.json` + the authoritative
`config/v6_templates/*.json`) so the FULL rendered UI is scanned. Fail-loud:
non-2xx, missing expected-content selector, nav error, or ANY WCAG-tagged
violation exits non-zero. The inspector cycles every `[role=tab]` so hidden
tab-panel content is covered.

## Findings + fixes (axe-core, empirical before/after)
First pass: 8 serious color-contrast. Tab-cycling (added after Codex iter-1)
exposed 11 more on hidden inspector panels. All 4 root causes fixed:

| File | Violation | Fix |
|------|-----------|-----|
| `components/ui/tabs.tsx` | inactive `TabsTrigger` `text-muted-foreground` on `bg-muted` fails 4.5:1 (7× inspector tabs) | explicit `text-foreground/70` (clears AA, still lighter than selected) |
| `app/source_review/page.tsx` | callout `text-muted-foreground` on `bg-muted/40` fails 4.5:1 | `bg-card` (white-backed, passes like the other info cards) |
| `components/inspector/reasoning_trace_timeline.tsx` | `<dl>` contained `<span>` wrappers → `definition-list` + 10× `dlitem` | `<div>` grid-item wrappers (HTML5-valid, identical render) |
| `components/inspector/sources_panel.tsx` | `max-h` scrollable `<pre>` had no keyboard access → `scrollable-region-focusable` (WCAG 2.1.1) | `tabIndex=0` + `role=region` + `aria-label` + focus ring |

**Final hardened re-scan: 0 blocking (page-errors + all WCAG violations) across
all 6 pages, true exit 0.**

## Codex
DIFF review: **APPROVE at iter 2**, zero P0/P1, MERGE AUTHORIZED. iter 1
REQUEST_CHANGES caught the harness's fail-open P1 (page errors ignored for the
exit code, no readiness assertion) — fixed (HTTP-2xx + expected-selector gates,
all errors blocking). The iter-1 P2b (cycle tabs) directly surfaced the 11
hidden-panel violations above — exactly the value of that finding.

## Residual / NOT covered (operator-side or future)
- **Manual** WCAG 2.2 AA: keyboard-only navigation walkthrough + screen-reader
  (NVDA/VoiceOver) passes — need a human.
- **Auth-gated flow routes** (intake, plan, source-review-live, dashboard,
  compare) — need prod credentials for full authenticated content scanning.
- Harness hardening (Codex iter-2 P2, non-blocking, future): tighten the status
  gate (currently allows 3xx), specific home/sign-in readiness selectors, and
  capture `page.on('pageerror')` runtime errors as blocking.

These keep #765 open; this slice is the automated public-pages pass + the
reusable harness.
