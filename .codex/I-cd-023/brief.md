HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1.
- "Don't pick bone from egg" — P1 only for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex brief review — I-cd-023 (#613) — /intake rebuild G1-G8

## §A Findings

Same pattern as I-cd-022 (home) — /intake currently has its OWN `<header>` (web/app/intake/page.tsx:17-35) that DUPLICATES AppShell's header (now restored on non-`/` routes via AppShellGate from I-cd-022). Result: TWO headers on `/intake`. G1 violation.

Plus G2 violations:
- Line 21: "POLARIS Canada — Slice 001" (Slice = dev language).
- Line 61: "POLARIS v6.2 — Slice 001 (scope + intake)" (footer; double slice + version).

Same G2 violation pattern in `web/app/benchmark/page.tsx`, `web/app/generation/page.tsx`, `web/app/retrieval/page.tsx`, `web/app/retrieval/components/retrieval_runner.tsx`. Per the breakdown, those have their OWN issues (I-cd-024 dashboard, I-cd-027 benchmark, etc.). Out-of-scope for this PR; this PR only fixes `/intake`.

## §B Implementation

1. **Drop the page-level `<header>` from `web/app/intake/page.tsx`** — AppShell already provides the global header on `/intake`. The "Home" button in the dropped header is redundant with the primary nav's Home link.
2. **Drop the page-level `<footer>`** for the same reason — global footer should be in AppShell (or none); page-specific footers create G1 inconsistency.
3. Wrap the content directly under `<main data-testid="intake-page">` without the outer `<div className="flex min-h-screen flex-col">` — AppShell already provides the `<main>` so this becomes a nested-main G6 violation. Actually wait — AppShell's `<main>` wraps `{children}`, so the page `<main>` IS the nested one. Fix: page renders content WITHOUT its own `<main>` — use a `<section>` or `<div data-testid="intake-page">` instead.
4. **Strip G2 dev language** from page text (header + footer are dropped, but verify no inline copy uses "slice").
5. **New Playwright spec** `web/tests/e2e/intake_g1_g8.spec.ts` — mirrors `home_g1_g8.spec.ts` pattern:
   - G1: exactly 1 `<header>` on /intake (the AppShell one)
   - G2: body text matches none of `/slice|scaffold|placeholder|phase 0|post-carney|i-cd-/i`
   - G6: exactly 1 `<main>` (the AppShell one)
   - G8: zero console errors on load
6. **Wire spec into web_ci.yml** as binding gate.

Estimated canonical diff: **~120 LOC** (-30 from intake/page.tsx + 90 from new spec).

## §C Acceptance check

| Gate | Met by |
|---|---|
| G1 — single global header (AppShell) | intake/page.tsx header dropped |
| G2 — no dev language | "Slice 001" + "POLARIS v6.2" stripped via header/footer removal |
| G3 — interactive states | existing shadcn Button/IntakeForm components preserved |
| G4 — async states | IntakeForm already handles loading/error states |
| G5 — responsive | existing max-w-4xl + grid handle 1440 + 1024 |
| G6 — single main | page now uses `<section>` not `<main>` |
| G7 — design tokens | existing token usage preserved |
| G8 — console clean | spec asserts mechanically |
| CI gate runs the spec | web_ci.yml new step |

## §D Red-team checklist

1. **IntakeForm + PdfDropBanner** are sub-components; their styling unchanged.
2. **Existing 4 intake specs** (intake.spec.ts, intake_disambiguation*.spec.ts, intake_edge.spec.ts) — what testids do they assert? `intake-page` is preserved (just moved from `<main>` to `<section>`). Most assertions are inside IntakeForm + on form testids; those are unchanged.
3. **Page metadata** (title + description) unchanged.
4. The dropped header had a "Home" button — already redundant with the primary nav's Home link in AppShell.
5. The dropped footer had `POLARIS v6.2 — Slice 001 (scope + intake)` + `Sovereign Canadian deep research` — both G2 + redundant.

## §E Files I have ALSO checked and they're clean

- `web/components/app_shell.tsx` — provides the global header w/ Home in primary nav.
- `web/components/app_shell_gate.tsx` (I-cd-022) — falls through to AppShell on `/intake`.
- `web/app/intake/components/intake_form.tsx` — sub-component; no change.
- `web/app/intake/components/pdf_drop_banner.tsx` — sub-component; no change.
- `web/tests/e2e/intake*.spec.ts` (4 files) — use testids inside the form, not on the dropped header/footer.

## §F Smoke test

```bash
cd web
npx tsc --noEmit
npx eslint
```

## §G Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
