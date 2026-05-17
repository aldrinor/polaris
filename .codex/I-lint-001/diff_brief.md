# Codex DIFF review — I-lint-001 / GH #520: Prettier-format the 2 files behind the red web format_check

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 1. What you are reviewing

The commit-1 diff for #520 — `git diff origin/polaris...HEAD` excluding
`.codex/I-lint-001/` and `outputs/audits/I-lint-001/` (the canonical diff in
`.codex/I-lint-001/codex_diff.patch`, sha256 trailer). It implements the
Codex-APPROVE'd brief `.codex/I-lint-001/brief.md` (brief APPROVE iter 1,
clean). Pure Prettier formatting — 2 files, +7/-3, no `git mv`.

## 2. The diff

`npx prettier --write app/generation/page.tsx lib/auth.ts` (repo
`.prettierrc`: printWidth 80, tabWidth 2, endOfLine lf,
prettier-plugin-tailwindcss):
- `web/app/generation/page.tsx` (+2/-2) — a JSX paragraph re-wrapped at the
  80-col boundary.
- `web/lib/auth.ts` (+5/-1) — an inline `return { … }` object literal
  expanded to multi-line.

Pure whitespace/line-break reflow. Zero behaviour change.

## 3. Verify against the brief

1. Exactly 2 files changed — `app/generation/page.tsx` + `lib/auth.ts` —
   the 2 files CI's `format_check` step flagged (CI log PR #576 run
   26003953421: "Code style issues found in 2 files").
2. The diff is **formatting-only** — confirm no string literal, JSX text,
   numeric value, identifier, or logic was changed; only line breaks /
   indentation / object-literal expansion.
3. No `prettier --write .` whole-tree rewrite — only the 2 target files
   (the local Windows-CRLF `format:check` flags ~190 files, a working-tree
   artifact; CI on Linux/LF sees only these 2).
4. No ESLint code change — the 3 lint warnings are pre-existing, in other
   files, tolerated (`eslint` exits 0); out of scope.
5. The 2 files are now `prettier --check`-clean.

## 4. Files I have ALSO checked and they're clean

- CI job log (PR #576, run 26003953421) is the ground truth: `lint` step
  passes (3 warnings / 0 errors / exit 0); `typecheck` passes; only
  `format_check` is red, on exactly these 2 files.
- `npm run lint` → exit 0 (unchanged 3 warnings); `npm run typecheck` →
  exit 0; `npm run build` → success — verified post-fix.
- `.prettierignore` excludes build/vendor dirs; the 2 edited files are
  application code.
- No other web/ source file is touched.

## 5. Test state

`web/`: `npx prettier --check app/generation/page.tsx lib/auth.ts` → clean;
`npm run lint` → exit 0; `npm run typecheck` → exit 0; `npm run build`
(`next build`) → success. Authoritative green signal = the PR's CI
`lint + format + typecheck + build` job (Linux/LF), red→green by this PR.

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
