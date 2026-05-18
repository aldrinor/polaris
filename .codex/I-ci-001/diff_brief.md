# Codex DIFF review — GH #571 (I-ci-001): codex-required ISSUE_ID regex supports -followup + carved a-z IDs

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## 1. What you are reviewing

The commit-1 diff for #571 (I-ci-001) — `git diff origin/polaris...HEAD`
excluding `.codex/I-ci-001/` and `outputs/audits/I-ci-001/` (canonical diff
in `.codex/I-ci-001/codex_diff.patch`, sha256 trailer). Implements the
Codex-APPROVE'd brief `.codex/I-ci-001/brief.md` (brief review APPROVE iter
1; 0 P0/P1, 1 non-blocking P2). **2 files, +152/-4.**

## 2. The change

`.github/workflows/codex-required.yml` — the `extract_and_validate_issue_id`
step's arm-1 regex:

```
- if [[ "$HEAD_REF" =~ ^bot/(I-[a-z0-9]{2,8}-[0-9]{3})(-[a-z0-9_-]+)?$ ]]; then
+ if [[ "$HEAD_REF" =~ ^bot/(I-[a-z0-9]{2,8}-[0-9]{3}(-followup|[a-z])?)(-[a-z0-9_-]+)?$ ]]; then
```

plus comment-only edits in the same step: a new I-ci-001 explanatory
paragraph, extended GATE examples, and the reject-arm `echo` schema string
(`I-[a-z0-9]{2,8}-[0-9]{3}[-followup|<a-z>][-<NAME>]`).

`tests/test_codex_required_issue_id_regex.py` — NEW. Extracts the live ERE
from the workflow YAML (regex `=~\s+(\^bot/\(I-[^\n]*?)\s+\]\]`) and asserts
a 25-row branch-name table via `re.match(...).group(1)`.

## 3. Brief P2 → implementation response (front-loaded so you VERIFY)

The brief proposed `[a-c]` (the issue's literal acceptance text). Codex
brief-review P2: carved IDs beyond `c` exist in repo history
(`I-arch-001d/e/f`). The implementation **widens to `[a-z]`** — this is the
deliberate resolution of that P2. Verify: `[a-z]` keeps the regex fully
unambiguous because the discriminator between a carved letter and a
descriptive slug is the *leading dash* (`bot/I-rdy-014a` carved vs
`bot/I-rdy-014-a` slug), not the letter range. The `claude_audit.md` §4
records this.

## 4. Verify

1. **`-followup` no longer collapses.** `bot/I-rdy-019-followup-test-matrix`
   → `BASH_REMATCH[1]` = `I-rdy-019-followup`, not the parent `I-rdy-019`.
   The `-followup` literal is inside group 1's nested `(-followup|[a-z])`;
   `-test-matrix` falls to group 3.
2. **Carved IDs no longer rejected.** `bot/I-rdy-014a` → `I-rdy-014a`
   (was: regex no-match → catch-all `bot/*` reject → `exit 1`).
3. **`BASH_REMATCH[1]` only.** The code (line 81) reads only group 1;
   the descriptive-slug group shifting 2→3 is inert. Confirm nothing
   else references `BASH_REMATCH[2]`.
4. **Additive — zero regression.** `(-followup|[a-z])?` matches empty
   whenever the next char is `-` (slug) or end-of-ref. Every pre-existing
   form (`I-ci-001`, `I-bug-079`, `I-f1-001-scope-discovery`,
   `I-hand-003-final`, `I-rdy-014-a`) resolves byte-identically.
5. **POSIX ERE.** bash `[[ =~ ]]` ERE — only literals / char classes /
   `{m,n}` / `?` / alternation / anchors; no `(?:)` / backrefs. The Python
   `re` test is therefore 1:1 with bash matching.
6. **Test cannot drift.** The test reads the regex OUT of the YAML rather
   than hardcoding it; a future workflow edit is automatically re-tested.
   Confirm the extraction regex would fail loud (AssertionError) if the
   arm-1 line were moved/renamed.
7. **Downstream paths.** `.codex/${ISSUE_ID}/` + the canonical-diff
   `:(exclude)` pathspecs consume the full ID — a followup/carved PR
   creates/excludes its own dir. No `verify_codex_artifacts` step logic
   changed.
8. **Comment edits are comment-only** — no shell logic in the edited
   comment lines.

## 5. Files I have ALSO checked and they are clean

- `codex-required.yml` `elif` infra-allowlist arm (line ~94), `else`
  non-bot arm, `verify_codex_artifacts` + `skip_summary` steps — logic
  unchanged; only arm-1 regex + comments touched.
- `scripts/ci/codex_artifact_gate.py`, `scripts/extract_codex_verdict.py`
  — consume a passed `ISSUE_ID` / read `.codex/<id>/`; do not parse the
  branch ref. Not modified.
- `.github/workflows/cleanup_pr_ancestry_check.yml` — separate gate, no
  issue-ID derivation. Not modified.
- `tests/v6/` + `tests/` root — no prior test exercised this regex; the
  new file is net-new, no collision.

## 6. Smoke state

YAML valid (`yaml.safe_load`). Test `ast.parse` clean.
`pytest tests/test_codex_required_issue_id_regex.py` — 25 passed.
Old-regex-fails proof script: OLD → `I-rdy-019` / `<no match>` for the
followup + carved cases; NEW → correct IDs; regression block confirms all
pre-existing forms unchanged.

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
