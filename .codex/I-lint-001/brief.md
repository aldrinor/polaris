# Codex BRIEF review — I-lint-001 / GH #520: fix the pre-existing red web `format_check` CI step

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 0.1 Review stage — PRE-IMPLEMENTATION brief review

This is the **brief** review (the plan). The working tree is intentionally
unmodified; the later diff review verifies the applied fix. Evaluate §2-§4
as a plan — especially the §2 issue-body discrepancy and the §3 scope call.

## 1. Issue

GH #520 (I-lint-001) — `polaris` carries a red `lint + format + typecheck +
build` web CI check (`.github/workflows/web_ci.yml`), inherited by every
web-touching PR. P2/P3 hygiene-only cleanup, dedicated PR. Branch
`bot/I-lint-001` (a normal `I-<prefix>-<NNN>` id — CI ISSUE_ID =
`I-lint-001`, no re-cut).

## 2. Ground truth — the issue body is FACTUALLY WRONG; verified against CI

The issue body claims 3 ESLint **errors** in `web/app/generation/page.tsx`
(`12:8 BenchmarkDimension`, `507:6 useEffect chartTypes`, `44:27 _text`).
**That is wrong.** I pulled the actual CI log of the `lint + format +
typecheck + build` job from a recent web-touching run (PR #576, run
`26003953421`):

- **`lint` step** — `eslint` reports those 3 items as **warnings, 0 errors**,
  and they are in 3 DIFFERENT files: `app/benchmark/components/benchmark_board.tsx:12`,
  `app/inspector/[runId]/page.tsx:507`, `tests/e2e/frame_coverage_panel.spec.ts:44`.
  `eslint` exits **0** — the `lint` step PASSES. The issue copied the
  `line:col` numbers but mis-attributed every file, and mislabelled warnings
  as errors.
- **`format_check` step** — `prettier --check .` → `[warn]
  app/generation/page.tsx`, `[warn] lib/auth.ts`, "**Code style issues found
  in 2 files**". THIS is the sole cause of the red job.
- `typecheck` (`tsc --noEmit`) → exits 0 locally. Not a failure.

**So the real fix is: Prettier-format the 2 files CI flags —
`web/app/generation/page.tsx` and `web/lib/auth.ts`.** The issue's
acceptance criteria name only `app/generation/page.tsx`; but its stated GOAL
("`polaris` carries a red … check") is only met by fixing BOTH — fixing one
leaves `format_check` red on the other. **Codex: confirm scope = both 2
CI-flagged files** (the GOAL reading), not the issue's literal 1-file
acceptance.

## 3. The fix — `prettier --write` the 2 files, formatting-only

- `cd web && npx prettier --write app/generation/page.tsx lib/auth.ts` —
  applies the repo `.prettierrc` (`semi`, `singleQuote:false`,
  `trailingComma:all`, `printWidth:80`, `tabWidth:2`, `endOfLine:lf`,
  `prettier-plugin-tailwindcss`). Pure whitespace/formatting reflow — **zero
  behaviour change, zero logic change**. No ESLint code change is needed
  (both files are already ESLint-clean — the 3 warnings are elsewhere and
  out of scope; `eslint` already exits 0).

### 3a. Windows-CRLF verification confound (important for the diff review)

This repo has `core.autocrlf=true`; the Windows working tree carries CRLF
line endings. `npm run format:check` (`prettier --check .`, `endOfLine:lf`)
therefore flags **~190 files** locally — every file, because CRLF ≠ LF. That
is a **local Windows artifact only**: CI runs on Linux/LF and sees exactly
the 2 genuinely-misformatted files (confirmed in the CI log above). The fix
must NOT run `prettier --write .` (it would rewrite 190 files). It writes
only the 2 target files; `git` (autocrlf) normalizes EOL to LF on commit, so
the committed diff is content-only. Local verification is per-file
(`prettier --check app/generation/page.tsx lib/auth.ts` → clean after the
write — those 2 files are LF+correct), NOT whole-tree.

## 4. Files I have ALSO checked and they're clean

- `npm run lint` whole-run → 3 warnings / 0 errors / exit 0 — the `lint` step
  is NOT red; no eslint change is in scope. The 3 warnings
  (`benchmark_board.tsx`, `inspector/[runId]/page.tsx`,
  `frame_coverage_panel.spec.ts`) are pre-existing, tolerated, and out of
  this issue's scope.
- `npm run typecheck` → exit 0; not red.
- `.prettierignore` excludes `.next`/`build`/`node_modules`/`public` etc.
- The 2 target files are application code; a formatting reflow does not
  touch any string literal, JSX text, or numeric value semantically.

## 5. Test / smoke (planned)

After `prettier --write` the 2 files: (a) `npx prettier --check
app/generation/page.tsx lib/auth.ts` → clean; (b) `npm run lint` → still
exit 0 (unchanged 3 warnings); (c) `npm run typecheck` → exit 0; (d) `npm
run build` (`next build`) → success — formatting cannot change build
behaviour, but it is run once to confirm. (e) `git diff` inspected to
confirm content-only formatting changes in exactly the 2 files. The
authoritative green signal is the PR's CI `lint + format + typecheck +
build` job (Linux/LF) — which this PR turns from red to green.

## 6. Required output schema (§8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

Loose verdict prose is rejected — emit the schema.
