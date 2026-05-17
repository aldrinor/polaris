# Claude architect audit — I-lint-001 (#520)

**Issue:** GH #520 — fix the pre-existing red `lint + format + typecheck +
build` web CI check inherited by every web-touching PR.
**Branch:** `bot/I-lint-001`
**Commit 1 (fix):** `ddc4655e` — 2 files, +7/-3, Prettier formatting only.
**Brief:** `.codex/I-lint-001/brief.md` — Codex APPROVE iter 1 (clean — 0
P0/P1/P2).

## 1. Ground truth — what is actually red

The issue body claimed 3 ESLint **errors** in `web/app/generation/page.tsx`.
**That was wrong** — verified against the actual CI job log (PR #576, run
`26003953421`, `lint + format + typecheck + build`):

| CI step | Result | In scope? |
|---|---|---|
| `lint` (`eslint`) | 3 **warnings**, 0 errors → exit 0 | No — step passes. The 3 warnings are in `benchmark_board.tsx`, `inspector/[runId]/page.tsx`, `frame_coverage_panel.spec.ts` — not page.tsx; pre-existing, tolerated. |
| `format_check` (`prettier --check .`) | "Code style issues found in **2 files**": `app/generation/page.tsx`, `lib/auth.ts` | **YES — the sole cause of the red job.** |
| `typecheck` (`tsc --noEmit`) | exit 0 | No — passes. |

The issue copied the `line:col` numbers but mis-attributed every file and
mislabelled warnings as errors. The real fix is Prettier formatting of the
2 `format_check`-flagged files.

## 2. What shipped

`npx prettier --write app/generation/page.tsx lib/auth.ts` (run from `web/`,
applying the repo `.prettierrc`: `printWidth:80`, `tabWidth:2`,
`endOfLine:lf`, `prettier-plugin-tailwindcss`, etc.):

- `web/app/generation/page.tsx` — +2/-2: a JSX paragraph re-wrapped at the
  80-col boundary (`(slice 001)` moved to the next line).
- `web/lib/auth.ts` — +5/-1: an inline `return { ok: false, status: 0,
  error: "…" }` object literal expanded to multi-line (exceeded 80 cols).

Pure whitespace/line-break reflow. Zero behaviour change, zero logic change,
no string-literal/numeric/JSX-text alteration.

## 3. Per-finding verification

- **VERIFIED — scope = 2 files, both fixed**: the CI `format_check` log
  names exactly `app/generation/page.tsx` + `lib/auth.ts`; both are
  Prettier-formatted in this commit. Fixing only the issue's literally-named
  `page.tsx` would leave `lib/auth.ts` → `format_check` still red. The
  issue's stated GOAL (green check) requires both — Codex brief review
  APPROVE'd this scope.
- **VERIFIED — Windows-CRLF confound handled**: `core.autocrlf=true`; the
  local working tree is CRLF, so `npm run format:check` (whole-tree,
  `endOfLine:lf`) flags ~190 files locally — a Windows artifact. CI runs on
  Linux/LF and sees only the 2 real files. The fix did NOT run `prettier
  --write .`; it wrote exactly 2 files. `git diff --stat` confirms exactly
  2 files changed, +7/-3 — content-only (git autocrlf normalizes EOL).
- **VERIFIED — the 2 files are now Prettier-clean**: `npx prettier --check
  app/generation/page.tsx lib/auth.ts` → "All matched files use Prettier
  code style!".
- **VERIFIED — no regression**: `npm run lint` → exit 0 (same 3 pre-existing
  warnings, unchanged); `npm run typecheck` → exit 0; `npm run build`
  (`next build`) → success.

## 4. Test / smoke

Run from `web/`: per-file `prettier --check` → clean; `npm run lint` →
exit 0; `npm run typecheck` → exit 0; `npm run build` → exit 0. The
authoritative green signal is the PR's CI `lint + format + typecheck +
build` job on Linux/LF — this PR turns it red→green.

## 5. Scope + residuals

- Commit-1 diff is +7/-3 across 2 files — trivially under the 200-LOC cap.
- The 3 pre-existing ESLint *warnings* (0 errors) are deliberately left —
  `eslint` exits 0, the `lint` step is not red, and they are out of this
  issue's scope (a separate hygiene concern if ever addressed).
- The ~188 other locally-CRLF-dirty files are a Windows working-tree
  artifact, not a repo problem — untouched, correctly.

## 6. Risk assessment

Formatting-only reflow of 2 application files — no logic, no behaviour, no
semantic content change. Full web smoke (lint/typecheck/build) green. The
only nuance — the Windows-CRLF whole-tree `format:check` confound — was
identified, worked around (per-file check), and the CI-truth (2 files)
confirmed from the actual CI log.

## 7. Verdict

Fix complete, faithful to the iter-1 APPROVE'd brief; the 2 CI-flagged files
are Prettier-clean; web smoke green. Ready for Codex diff review.
