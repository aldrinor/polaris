# Claude audit — I-cd-022 (#612)

## Scope landed

- AppShellGate (new) — pathname-aware client wrapper; suppresses BOTH AppShell header AND its main on `/`.
- HomeKeyboardShell — PRIMARY_NAV moved into the home header; brand cell reformatted; header-sign-in-link + signInLinkRef preserved (5 existing specs back-compat).
- web/app/page.tsx — G2 dev language stripped.
- web/tests/e2e/home_g1_g8.spec.ts — 5 mechanical G1/G2/G3/G6/G8 assertions.
- web_ci.yml — new binding CI step.

## Codex review trajectory

- Brief iter 1: REQUEST_CHANGES — P1 (header removal breaks 5 specs), P2 (nested main, smoke command, G3 wording).
- Brief iter 2: REQUEST_CHANGES — P1 (revised plan would put home header inside AppShell main).
- Brief APPROVE via slim verdict (force-APPROVE on plan; remaining was implementation-shape clarification, addressed in diff).
- Diff iter 1: **APPROVE**. Two P2 test-gaps noted (warnings + nav-link G3 coverage) — non-blocking, can be tightened post-merge if needed.

## G1-G8 coverage

| Gate | Mechanically verified by spec? |
|---|---|
| G1 — single header w/ primary nav | YES — toHaveCount(1) on header + 8 nav links |
| G2 — no dev language | YES — regex against body text |
| G3 — interactive states | PARTIAL — active link focus-visible asserted; nav links not separately asserted (P2) |
| G4 — async states | N/A (static home) |
| G5 — responsive | implicit via grid classes; not separately asserted |
| G6 — a11y + single main | YES — toHaveCount(1) on main + Tab to active link |
| G7 — design tokens | implicit via existing token classes; not separately asserted |
| G8 — console clean | PARTIAL — errors only; warnings noted as P2 test-gap |

## Quality bar

- 6 files / +159/-13 LOC canonical-diff (well under 200-LOC halt).
- TS + lint clean.
- AppShellGate keeps SSR boundary tight (only the gate is client; AppShell + children remain server-renderable).
- header-sign-in-link / signInLinkRef preserved (no break in command_palette + f1 specs).
- No data fabrication; no fake "looks right" claims.
