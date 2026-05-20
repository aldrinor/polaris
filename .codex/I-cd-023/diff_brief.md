HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1.
- "Don't pick bone from egg" — P1 only for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex diff review — I-cd-023 (#613) — /intake rebuild

Brief APPROVE'd (force-APPROVE on plan after iter-1 RC findings were all "implementation pending" — addressed in this diff). Canonical-diff-sha256: `782ae85909c1956221cc40b42d6e6794bb61807ebd03e46914fc301c3d2d7e24`. 3 files / +59/-54 LOC + 1 CI step.

## §A Canonical diff summary

- `web/app/intake/page.tsx` — drop page-level `<header>` + `<footer>` + `min-h-screen` wrapper. Page now renders `<section data-testid="intake-page">` directly. AppShell provides the single header + main. Section-title is now a `<div>` (not `<header>`) so the page locator-count for `<header>` is exactly 1.
- `web/tests/e2e/intake_g1_g8.spec.ts` NEW — G1 (1 header), G6 (1 main), G2 (no dev language), G8 (no console errors), G1 nav-parity (primary nav links visible).
- `.github/workflows/web_ci.yml` — `run_e2e_intake_g1_g8` step wires the spec as a binding CI gate.

## §B Acceptance check

| Gate | Met by |
|---|---|
| G1 — single header (AppShell-only) | page header dropped; spec asserts `toHaveCount(1)` on `<header>` |
| G2 — no dev language | "POLARIS Canada — Slice 001" + "POLARIS v6.2 — Slice 001 (scope + intake)" removed via header/footer drop; spec regex-asserts |
| G3 — interactive states | existing shadcn Button + IntakeForm components preserved |
| G4 — async states | IntakeForm already has loading/error states |
| G5 — responsive | existing `max-w-4xl` + grid |
| G6 — single main (AppShell-only) | page `<main>` swapped for `<section>`; spec asserts `toHaveCount(1)` on `<main>` |
| G7 — design tokens | preserved |
| G8 — console clean | spec asserts via `page.on("console", ...)` |
| `intake-page` testid preserved (4 existing intake specs) | line 19 of new page.tsx |
| CI binding gate | web_ci.yml new step |

## §C Red-team checklist

1. **`intake-page` testid** — moved from `<main>` to `<section>`; existing specs assert visibility/role-agnostic, so this is non-breaking.
2. **IntakeForm + PdfDropBanner** — sub-components unchanged.
3. **Page metadata** (title, description) preserved.
4. **Drop section-level `<header>`** for G1 single-header strictness; replaced with `<div>` containing h1 + paragraph.
5. **No new dependencies** — pure structural edit.
6. **TypeScript clean** confirmed via `npx tsc --noEmit`.

## §D Files I have ALSO checked and they're clean

- `web/components/app_shell_gate.tsx` (I-cd-022) — falls through to AppShell on `/intake`, providing the global header + main.
- `web/tests/e2e/intake*.spec.ts` (4 files) — assert on form testids inside IntakeForm, not on the dropped header/footer.
- `web/app/intake/components/intake_form.tsx` — sub-component unchanged.

## §E Smoke test

```bash
cd web && npx tsc --noEmit
# rc=0
```

## §F Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
