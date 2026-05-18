# Codex DIFF review — I-hygiene-001 / GH #432: `.gitignore` re-accumulation hardening

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 1. What you are reviewing

The commit-1 diff for #432 — `git diff origin/polaris...HEAD` excluding
`.codex/I-hygiene-001/` and `outputs/audits/I-hygiene-001/` (the canonical
diff in `.codex/I-hygiene-001/codex_diff.patch`, sha256 trailer). It
implements the Codex-APPROVE'd brief `.codex/I-hygiene-001/brief.md` (brief
APPROVE iter 3 — iter 1+2 REQUEST_CHANGES findings all fixed). **1 file,
+27/-0** (`.gitignore`).

This PR ships #432 acceptance **criterion 5 only** (`.gitignore` re-accumulation
hardening). It is the first small slice of the fresh-inventory recut after
PR #433 (a 233-file mega-PR) was closed per disposition `B_close_recut_fresh`.
#432 stays open. Do NOT flag "incomplete vs the full issue" as P0/P1 — partial
slicing is the explicit disposition directive (see brief §0.1, §4).

## 2. The diff

`.gitignore` gains one section at lines 160-186 (after the "Root-level
audit/debug dumps" block, before "Codex loop ephemera"): a 5-line comment
header + **21 ignore patterns** at lines 166-186. All patterns are anchored
to repo root (leading `/`) and directory-only (trailing `/`):

```
/codex_tmp*/ /.codex_tmp*/ /codex_probe*/ /codex_gpg_probe*/ /tmp*/ /.tmp*/
/.pytest_*/ /pytest-cache-files-*/ /pytest_run_*/ /pytest_basetemp*/
/py_pytest_*/ /dashboard_probe_*/ /manual_pytest_*/ /manual_tmp_*/
/m_int_*_manual_*/ /m10v*/ /m_live_4_r2_*/ /md3_pytest_*/
/python_mode_*_probe/ /POLARIS.tmp*/ /POLARIStmp*/
```

## 3. Verify

1. **No tracked-path shadowing (the one real risk).** Re-run, independently:
   `git ls-files | git check-ignore --no-index --stdin --verbose`, filter to
   lines `.gitignore:166`-`186` → must be empty. `--no-index` is required
   (without it check-ignore skips tracked paths). The *unfiltered* output is
   expectedly non-empty (pre-existing `*.jsonl` / `outputs/*` / `state/*` /
   `.claude/*` ignore-unignore interactions) — that is NOT a finding.
2. **Patterns are root-anchored.** Each leading `/` confines the match to a
   root-level directory — confirm none can affect `src/ tests/ scripts/
   web/ config/ docs/` contents.
3. **No whole-file CRLF reflow.** `.gitignore` is a CRLF file; `git diff
   --numstat` must show `27  0  .gitignore` (pure insertion, 0 deletions).
4. **`/.pytest_*/` carries its `*`** — it must match `.pytest_tmp` /
   `.pytest_scope_gate_tmp2` (brief iter-1 P1). `git check-ignore -v` on
   those dirs should report a `.gitignore:166`-`186` rule.
5. **Each pattern is grounded** in an observed scratch family (brief §2
   inventory table) — no speculative patterns matching hypothetical content.

## 4. Files I have ALSO checked and they're clean

- `.gitignore` lines 149-159 — the existing "Accidental scratch dirs" +
  "audit/debug dumps" blocks; the new section is inserted directly after,
  no overlap/conflict (the old block covers unrelated `tmp/ wiki/ cache/
  loopback/`).
- `.gitignore` lines 41 (`.pytest_cache/`), 203-210 (I-sec-001
  `.codex/**/codex_*review*.txt`) — unrelated, untouched.
- `git ls-files` root entries — no tracked path starts with any new
  pattern's prefix; the binding shadowing check (§3.1) is the proof.
- `.github/workflows/codex-required.yml` — the canonical-diff gate excludes
  `.codex/I-hygiene-001/` + `outputs/audits/I-hygiene-001/`; a one-file
  +27-line diff is far under the 200-LOC cap.

## 5. Verification state

`git diff --numstat` → `27 0 .gitignore`. Tracked-path shadowing check
(filtered to lines 166-186) → empty. Positive coverage: `git check-ignore -v`
on 23 representative dirs across all 11 families → every one matched by a
new-block line. Evidence in `outputs/audits/I-hygiene-001/claude_audit.md` §4.

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
