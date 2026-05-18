# Codex BRIEF review — I-hygiene-001 / GH #432: root-folder hygiene — `.gitignore` re-accumulation hardening

HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 0. Stage

This is a **pre-implementation brief review** — you are reviewing the *plan* (acceptance-criteria correctness + scoping), NOT a diff. The diff review is a separate later Codex call. No code is written yet.

## 0.1 HARD CONSTRAINT — scope is deliberately ONE slice of #432

#432 (I-hygiene-001) is a multi-part root + `.codex/` cleanup. Its prior PR **#433 was closed unmerged** per Codex disposition `B_close_recut_fresh`: it was a 233-file mega-PR (+55k/-29k), 28 commits stale, conflicting with polaris's own 2026-05-05 Cleanup-PR-1..8 wave. The disposition directive: *"A fresh root/.codex inventory against current polaris will recut **small** issue-driven cleanup PRs."*

This PR is that fresh-inventory's **first small slice**: `.gitignore` re-accumulation hardening only (#432 acceptance criterion 5). It does NOT close #432. Criteria 1-4/6-9 are out of scope here — see §4 for why (a hard external blocker, and the mega-PR anti-pattern). Do not flag "incomplete vs the issue" as a P0/P1 — partial slicing is the explicit disposition directive.

## 1. Issue

GH #432 (I-hygiene-001) acceptance criterion 5: *"`.gitignore` updated to prevent future re-accumulation of the same temp-dir patterns."*

## 2. Fresh inventory (run against current `polaris` HEAD `486388a5`, 2026-05-17)

POLARIS root currently holds **~150 stray scratch directories** alongside the 22 essential entries. The strays fall into these families (all observed, names verbatim from `ls`):

| Family | Examples | Count (approx) |
|---|---|---|
| Codex review sandboxes | `codex_tmp_i_rdy013_probe`, `codex_tmp_m_int_5_v4_review`, `codex_tmp_review_78ab472a…` | ~100 |
| Codex probes | `codex_probe_i_rdy_018`, `codex_gpg_probe_i_rdy547_t8j3iwn9` | 2 |
| pytest `tmp_path` basetemp leakage | `tmp2ef0ie4p`, `tmp_ae3ucgg`, `tmp_pytest_m_int_3` | ~25 |
| pytest cache/run dirs | `pytest-cache-files-z1miwcyi` (×15), `pytest_run_<hex>` (×3), `pytest_basetemp_i_bug_085_r2`, `py_pytest_<hex>` | ~20 |
| dot-prefixed pytest/codex scratch | `.pytest_tmp`, `.pytest_scope_gate_tmp2`, `.tmp-pytest`, `.tmp_pytest_base`, `.codex_tmp`, `.codex_tmp_m_int_6_v1_review_fresh` | ~8 |
| dashboard probes | `dashboard_probe_zw62d2fs` (×5) | 5 |
| milestone-era manual scratch | `m_int_7_v2_manual_5fgxbzoc`, `m10v2_manual_yz_33hqh`, `m_live_4_r2_3qyr9r66`, `md3_pytest_run2`, `manual_pytest_base_m_int_7`, `manual_tmp_m_int_3_v3`, `python_mode_700_probe` | ~8 |
| non-snake_case pytest basetemp | `POLARIS.tmppytest`, `POLARIStmp_pytest_m_int_3_reviewbasetemp` | 2 |

**Two verified facts that shape the scope:**

1. **None are git-tracked.** `git ls-files | grep -E '^(codex_tmp_|tmp[0-9a-z]|pytest-cache-files-|dashboard_probe_|m_int_|manual_|md3_|py_pytest_|\.tmp|\.pytest|POLARIS\.|POLARIStmp)'` → **0 hits**. They are untracked filesystem clutter.
2. **None are currently `.gitignore`d.** `git check-ignore` on a 6-dir sample → all `NOT-IGNORED`. The existing `.gitignore` "Accidental scratch dirs" block (lines 149-159) only covers literal `tmp/ wiki/ cache/ loopback/` + `audit_*.txt` — it does NOT match any current family above.

Consequence of (2): `git status` emits ~150 `warning: could not open directory '<dir>/': Permission denied` lines on every run, because git tries to descend into untracked-and-unignored dirs that are **Windows-ACL-locked** (open handles / elevated-created). The new ignore patterns make git skip them entirely → silent, clean `git status`.

## 3. The change (criterion 5 — one file: `.gitignore`)

Add one new section, inserted after the existing "Root-level audit/debug dumps" block (after line 159), before "Codex loop ephemera". Patterns are **anchored to repo root** (leading `/`) and **directory-only** (trailing `/`), so they can only ever match root-level directories — never anything under `src/ tests/ scripts/ web/ config/ docs/`.

```
# --- Pytest / Codex review scratch dirs at repo root (I-hygiene-001 / #432) ---
# Anchored to repo root (leading `/`); directory-only (trailing `/`). These
# accumulate from pytest `tmp_path` basetemp leakage + `codex exec` review
# sandboxes and are pure throwaway. Verified 2026-05-17 against polaris HEAD:
# zero of these patterns match any git-tracked path.
/codex_tmp*/
/.codex_tmp*/
/codex_probe*/
/codex_gpg_probe*/
/tmp*/
/.tmp*/
/.pytest_*/
/pytest-cache-files-*/
/pytest_run_*/
/pytest_basetemp*/
/py_pytest_*/
/dashboard_probe_*/
/manual_pytest_*/
/manual_tmp_*/
/m_int_*_manual_*/
/m10v*/
/m_live_4_r2_*/
/md3_pytest_*/
/python_mode_*_probe/
/POLARIS.tmp*/
/POLARIStmp*/
```

Rationale per pattern family: each is grounded in an *observed* family above — no speculative patterns. `/tmp*/` deliberately supersedes the narrower line-152 `/tmp/`-equivalent (`tmp/`) but both are left in place (harmless overlap; the old block also covers `wiki/ cache/ loopback/` which are unrelated). The dot-pytest pattern is `/.pytest_*/` — the trailing `*` is load-bearing: it is what matches `.pytest_tmp` and `.pytest_scope_gate_tmp2` (and `.pytest_cache`); a `*`-less `/.pytest_/` would match none of them (Codex brief-review iter-1 P1).

**Safety verification done at implement time** (will be in `claude_audit.md`), two explicit checks:
1. **Tracked-path shadowing check (binding) — scoped to the NEW patterns only:** run `git ls-files | git check-ignore --no-index --stdin --verbose`, then **filter** the output to lines whose matched rule belongs to the newly-inserted block (i.e. `.gitignore:<linenum>` falls in the new block's line range — exact range recorded in `claude_audit.md`). That **filtered** set MUST be empty — no tracked path is shadowed by any of the 21 new patterns. The `--no-index` flag is required because without it `git check-ignore` silently skips every tracked path (a tracked file is never reported as ignored), making the check vacuous (Codex brief-review iter-1 P1). The *unfiltered* output is expectedly **non-empty** in this repo — the pre-existing `.gitignore` ignore/unignore interactions (`*.jsonl`, `outputs/*`, `state/*`, `.claude/*`, …) legitimately net-match some tracked paths; that is pre-existing and NOT this slice's concern, so "whole-output empty" is explicitly NOT the gate (Codex brief-review iter-2 P1). Only new-block-line matches gate the commit; if any surface, the offending pattern is removed/narrowed.
2. **Positive coverage check:** `git check-ignore -v <dir>` is run for one representative dir per family — explicitly including `.pytest_cache`, `.pytest_tmp`, `.pytest_scope_gate_tmp2` for the dot-pytest family — to confirm each new pattern actually matches its intended targets, and that the matching rule reported is a new-block line.

The `.gitignore` file is CRLF (`core.autocrlf=true` working tree); the new block will be written with CRLF endings so the diff is +N lines only, no whole-file reflow.

## 4. Why criteria 1-4, 6-9 are NOT in this slice

- **Criteria 1-4 (physically archive the ~150 dirs + `.codex/` historicals to `archive/`):** the ~150 root dirs are **Windows-ACL permission-locked** — git itself cannot open them (`Permission denied`), so this Claude process cannot `mv` them either. PR #433 already hit and documented this exact blocker ("91 ACL-locked root dirs require user-side post-reboot/elevated cleanup"; now ~150). Physical archiving is a **user-side elevated/post-reboot operation** — a real external blocker, not a scoping choice.
- **Criterion 4 (`.codex/` historical archive):** `.codex/` holds **2060 tracked files**. A mass `git mv` of historical review artifacts is precisely the 233-file mega-PR shape that got #433 closed. The disposition said recut *small* PRs — so the `.codex/` archive is deferred to its own future small slice, not bundled here.
- **Criteria 6-7 (`docs/file_directory.md`, `README.md` layout):** the tracked root layout does NOT change in this slice (no dirs moved), so there is nothing to re-document. Updating them would be inventing a diff.
- **Criteria 8-9 (`session_log.md`, `issue_breakdown.md`):** session_log is gitignored (`logs/`); the issue record is carried by this PR's `.codex/I-hygiene-001/` artifacts + the `gh issue comment` posted at merge. No tracked-doc edit needed for a one-file `.gitignore` slice.

#432 stays **open** after this PR merges; a merge comment will record what shipped and what remains user-gated.

## 5. Files I have ALSO checked and they're clean

- `.gitignore` lines 149-159 — the existing "Accidental scratch dirs" + "audit/debug dumps" blocks; the new section is inserted directly after, no overlap/conflict with `tmp/ wiki/ cache/ loopback/`.
- `.gitignore` lines 203-210 — the I-sec-001 `.codex/**/codex_*review*.txt` rules; unrelated, untouched.
- `git ls-files` root entries — confirmed no tracked path starts with `codex_tmp`, `tmp`, `pytest`, `py_pytest`, `dashboard_probe`, `manual_`, `m_int_`, `m10v`, `m_live`, `md3_`, `python_mode`, `POLARIS.`, `POLARIStmp`, `.tmp`, `.pytest`, `.codex_tmp` → the new anchored patterns cannot shadow tracked content.
- `.github/workflows/codex-required.yml` — the canonical-diff gate excludes `.codex/I-hygiene-001/` + `outputs/audits/I-hygiene-001/`; a one-file `.gitignore` diff is well within the 200-LOC cap.

## 6. Acceptance criteria for THIS slice

1. `.gitignore` gains the anchored root-scratch-dir section above; criterion 5 of #432 satisfied.
2. `git ls-files | git check-ignore --no-index --stdin --verbose`, **filtered to the new block's `.gitignore` line range**, → empty (no tracked path shadowed by a new pattern) — the binding safety check. The unfiltered output is expectedly non-empty (pre-existing rules) and is not the gate.
3. `git check-ignore -v` confirms positive coverage per family, incl. `.pytest_cache` / `.pytest_tmp` / `.pytest_scope_gate_tmp2`, each matched by a new-block line.
4. Diff is exactly one file (`.gitignore`), ~+24 lines, no whole-file CRLF reflow.
5. #432 left open with a merge comment recording the slice + the user-gated remainder.

## 7. Required output schema (§8.3.9)

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
