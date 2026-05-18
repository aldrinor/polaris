# Claude architect audit — I-hygiene-001 (#432)

**Issue:** GH #432 (I-hygiene-001) — surgical POLARIS root hygiene. This PR
ships **acceptance criterion 5 only**: `.gitignore` updated to prevent future
re-accumulation of root scratch-dir patterns.
**Branch:** `bot/I-hygiene-001` off `polaris` HEAD `486388a5`.
**Commit 1:** `be777332` — 1 file, +27/-0 (`.gitignore`).
**Brief:** `.codex/I-hygiene-001/brief.md` — Codex APPROVE iter 3 (iter 1+2
REQUEST_CHANGES, all P1 fixed — see §5).

## 1. Why this is a one-criterion slice

#432's prior PR **#433 was closed unmerged** (2026-05-15) per Codex
disposition `B_close_recut_fresh`: it was a 233-file mega-PR (+55k/-29k),
28 commits stale, conflicting with polaris's own 2026-05-05 Cleanup-PR-1..8
wave. The disposition directive: *"a fresh root/.codex inventory against
current polaris will recut **small** issue-driven cleanup PRs."* This PR is
that fresh inventory's first small slice. #432 stays **open** after merge.

## 2. Fresh inventory (polaris HEAD `486388a5`, 2026-05-17)

POLARIS root holds **~150 stray scratch directories**. Two facts verified:

- **None are git-tracked** — `git ls-files | grep -E '^(codex_tmp_|tmp[0-9a-z]|pytest-cache-files-|dashboard_probe_|m_int_|manual_|md3_|py_pytest_|\.tmp|\.pytest|POLARIS\.|POLARIStmp)'` → 0 hits.
- **None were `.gitignore`d** (except `.pytest_cache`, already covered by the
  pre-existing `.gitignore:41` rule — Codex iter-3 P2-1). The existing
  "Accidental scratch dirs" block (lines 149-159) only covered literal
  `tmp/ wiki/ cache/ loopback/` + `audit_*.txt`.

Because the strays were untracked-AND-unignored, `git status` descended into
each and emitted ~150 `warning: could not open directory ...: Permission
denied` lines — the dirs are Windows-ACL-locked.

## 3. The change (`.gitignore`, +27 lines, lines 160-186)

A new section after the "Root-level audit/debug dumps" block: a 5-line
comment header + 21 ignore patterns, all **anchored to repo root** (leading
`/`) and **directory-only** (trailing `/`). Each pattern is grounded in an
*observed* scratch family — no speculative patterns. The new pattern lines
are `.gitignore:166`-`186`.

## 4. Verification (both checks RAN — evidence below)

- **VERIFIED — diff is `.gitignore` only, no reflow**: `git diff --numstat`
  → `27  0  .gitignore`. 27 insertions, 0 deletions; CRLF preserved (the
  block was byte-inserted with `\r\n` endings). The dirty `outputs/honest_sweep_r3/**`
  files are pre-existing working-tree noise from before this session — NOT
  staged, NOT part of this PR.
- **VERIFIED — no tracked path shadowed (binding check)**:
  `git ls-files | git check-ignore --no-index --stdin --verbose` filtered to
  `.gitignore:166`-`186` → **empty**. No tracked file is shadowed by any of
  the 21 new patterns. (`--no-index` is required — without it check-ignore
  skips tracked paths, making the test vacuous; the unfiltered output is
  expectedly non-empty from pre-existing ignore/unignore rules and is NOT
  the gate — Codex brief iter-1 + iter-2 P1.)
- **VERIFIED — positive coverage**: `git check-ignore -v` on 23 representative
  dirs across all 11 families — every one matched, each by a new-block line
  (166-186). Notably `.pytest_cache` / `.pytest_tmp` / `.pytest_scope_gate_tmp2`
  all match `.gitignore:172:/.pytest_*/` — the trailing `*` is load-bearing
  (Codex brief iter-1 P1). `.pytest_cache` was already ignored by line 41;
  check-ignore reports the *last* matching rule, so the new line 172 is the
  reported match (Codex iter-3 P2-1, accuracy noted).

## 5. Codex iteration trail (brief)

- **iter 1 REQUEST_CHANGES** (2 P1): the dot-pytest pattern must carry its
  `*`; the shadowing check needs `--no-index` (a bare `git check-ignore`
  skips tracked paths → vacuous). Both fixed in the iter-2 brief.
- **iter 2 REQUEST_CHANGES** (1 P1): `--no-index` against the whole
  `.gitignore` reports pre-existing tracked-path matches → "empty" is not a
  truthful gate. Fixed: scope the check to the new block's line range.
- **iter 3 APPROVE** (2 non-blocking P2 — `.pytest_cache` audit-text accuracy;
  the separate global-excludes permission warning — both folded into this
  audit, neither execution-blocking).

## 6. Scope + residuals (what #432 still needs — user-gated)

- **Physically archiving the ~150 root dirs** to `archive/2026-05-11-root-hygiene/`
  (#432 criteria 1-3): **blocked** — the dirs are Windows-ACL permission-locked;
  git itself cannot open them, so this process cannot `mv` them. Requires a
  user-side elevated / post-reboot cleanup. This is the *same* blocker PR #433
  documented ("91 ACL-locked dirs"; now ~150). The new `.gitignore` rules at
  least make `git status` skip them — silent, clean status output.
- **`.codex/` historical archive** (#432 criterion 4): `.codex/` holds 2060
  tracked files; a mass `git mv` is the 233-file mega-PR shape that closed
  #433. Deferred to its own future small slice.
- Criteria 6-9 (docs/README/session_log/issue_breakdown): the tracked root
  layout does not change in this slice, so nothing to re-document.

#432 stays open; the merge comment records the slice + the user-gated
remainder.

## 7. Risk assessment

Zero runtime risk — `.gitignore` is not executed. The only failure mode of an
ignore rule is shadowing tracked content; the binding check (§4) proves no
new pattern matches any tracked path. The patterns are root-anchored, so they
cannot affect `src/ tests/ scripts/ web/ config/ docs/`. No production code,
no test, no config touched.

## 8. Verdict

Faithful to the iter-3 APPROVE'd brief; criterion 5 satisfied; both binding
and positive verification checks ran and passed; zero tracked-path shadowing.
Ready for Codex diff review.
