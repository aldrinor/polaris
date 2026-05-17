# Codex DIFF review — I-sec-001 / GH #535: verdict-only .codex artifacts + CI gate

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 1. What you are reviewing

The commit-1 diff for #535 — `git diff origin/polaris...HEAD` excluding
`.codex/I-sec-001/` and `outputs/audits/I-sec-001/` (the canonical diff in
`.codex/I-sec-001/codex_diff.patch`, sha256 trailer). It implements the
Codex-APPROVE'd brief `.codex/I-sec-001/brief.md` (brief review APPROVE iter 5,
P1 trajectory 2→2→2→1→0). Verify the diff faithfully executes that brief.

## 0.1 iter-1 findings — all addressed

- iter-1 **P1** (`parse_verdict_block` silently dropped non-empty inline
  `[...]` list values) → `_parse_inline_list` added; the list-key branch now
  parses `key: [a, b]`, treats `key: []` as empty, `key:` as block-list, and
  **rejects** any other malformed list value loudly (`return None`).
  Regression tests added (`test_parse_inline_nonempty_list_not_dropped`,
  `test_parse_inline_list_with_comma_inside_quotes`).
- iter-1 **P2-1** (gate rejected top-level `.codex/AUDIT_CYCLE_PROTOCOL.md`) →
  `codex_artifact_gate.py` now applies the slim-artifact allowlist ONLY to
  `.codex/<issue_id>/` paths (≥3 path components); the denylist + secret scan
  still apply to every changed `.codex/**` path including top-level docs.
- iter-1 **P2-2** (file-count) → §2 corrected below.

## 2. The diff (commit 1: 7 files +642; canonical diff = 8 files — also `state/polaris_restart/iteration_trajectory.md` from commit 2)

- **`scripts/extract_codex_verdict.py`** (new, 254 LOC) — `extract` parses the
  LAST §8.3.9 verdict block from a raw transcript (`parse_verdict_block`),
  re-serializes it canonically (`serialize_verdict` — parse-then-emit, so no
  trailing transcript survives), enforces an 8 KB cap, scans the output
  (`scan_for_leaks`: subprocess `scan_for_secrets.py` + local `.env`-value
  substring match), and refuses to write (exit 4) on any hit. `validate`
  (CI mode, no `.env` dependency): byte-cap + parses as a §8.3.9 block +
  full-text round-trip equality (rejects trailing transcript text).
- **`scripts/ci/codex_artifact_gate.py`** (new, 132 LOC) — `changed_codex_paths`
  (`git diff --name-status origin/<base>...HEAD -- .codex/`, drops `D`);
  per path: denylist raw-transcript regexes, allowlist slim basenames,
  `validate` on verdict/audit files, `scan_for_secrets.py --strict`. Fast-pass
  exit 0 when no `.codex/**` changed.
- **`.github/workflows/codex_artifact_gate.yml`** (new) — `pull_request_target`
  (workflow definition sourced from base — PR cannot edit the gate), NO
  `paths:` filter (runs every PR → required-check-safe), checks out base
  (gate scripts) + PR head (read-only data, `persist-credentials:false`),
  runs `base/scripts/ci/codex_artifact_gate.py`.
- **`scripts/autoloop/scan_for_secrets.py`** (+17) — adds `jina_` / `fc-` /
  `fw_` vendor patterns + a configured secret-env-NAME assignment pattern.
- **`.gitignore`** (+9) — raw codex-transcript filename patterns.
- **`.codex/AUDIT_CYCLE_PROTOCOL.md`** (+29) — verdict-only ship-procedure
  policy section.
- **`tests/test_extract_codex_verdict.py`** (new, 140 LOC) — 11 tests.

## 3. Verify against the brief

1. §3.1 — extract parses+validates, not regex-copy (confirm no trailing
   transcript can survive `serialize_verdict`).
2. §3.2 — mandatory scan of the slim output; local `.env`-value match present;
   CI has no `.env` dependency.
3. §3.3 — base-sourced control plane (`pull_request_target`), all changed
   `.codex/**` statuses A/M/R/C covered (not just A), content-validation runs.
4. §3.3 iter-4 — no `paths:` filter; fast-pass on no `.codex/**` change so the
   gate is required-check-safe.
5. §3.4/§3.5 — gitignore variants; vendor + NAME pattern coverage.
6. Bootstrap §3.6 — confirm this PR commits only the slim verdict
   (`.codex/I-sec-001/codex_brief_verdict.txt`, 134 B), not raw transcripts.

## 4. Files I have ALSO checked and they're clean
- `.github/workflows/codex-required.yml` — unchanged; still parses the
  verdict line of the slim file.
- `.git/hooks/{pre-commit,commit-msg}` — stubbed; not touched (not a gate).
- No production code path (`src/**`) is touched — CI/tooling only.

## 5. Known scope calls (not defects — confirm sound)
- Existing pre-existing committed transcripts are NOT tree-removed (operator
  accepted that exposure; `state/resolved_halt_20260517T124325Z_secret_exposure.md`).
- `codex-artifact-gate` is NOT yet a required branch-protection check — that
  is an operator/admin handoff, flagged in the issue.
- CLAUDE.md §3.0 text update is a documented residual (canonical-pin-protected).

## 6. Test state
Offline: `tests/test_extract_codex_verdict.py` 11/11 pass. The pre-existing
`test_manifest_contract.py` 2 failures are unrelated to #535.

## 7. >200-LOC note
+642 LOC, but all-additions of new CI/tooling files (largest is a 254-LOC new
script). Not a refactor of existing code; reviewable as discrete new units.
The exemption is requested if the 200-LOC cap applies to net-new tooling.

## 8. Required output schema (§8.3.9)

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
