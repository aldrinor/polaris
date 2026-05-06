# PR-E Review Brief — Open all 130 GitHub Issues

**Iter:** 3 of N (no hard cap per CLAUDE.md §8.3.1).

## iter-2 findings addressed

- **PRE2-P1-001 FIXED — parenthetical Feature annotations normalized.** Source `Feature: F1 (intake)` for I-bug-079 now resolves to canonical `F1` / `feature-f1` (NOT `feature-f1-intake`). Logic: when explicit Feature contains `(` AND a `default_feature(issue_id)` exists, the default wins. Applied to BOTH `render_body()` AND `issue_label()` (earlier iter only fixed `render_body()`; iter-2 P1-001 caught the asymmetry).

- **PRE2-P1-002 FIXED — accept both `Foundation refs` and `Foundation` field names.** `render_body()` reads `f.get("Foundation refs", "") or f.get("Foundation", "")` so the 4 Issues using bare `Foundation` (lines 275, 356, 441, 504) get their issue-specific reference rendered.

- **PRE2-P1-003 FIXED — label preflight before any Issue create.** New helpers:
  - `gh_existing_labels()` — calls `gh label list --json name` to get existing repo labels.
  - `gh_label_create()` — calls `gh label create <name> --description "Auto-created by PR-E" --force`.
  - `ensure_labels_exist(needed_labels)` — computes `missing = needed - existing`, creates missing one-by-one, raises RuntimeError on any failure (which causes Apply to abort with exit 2 BEFORE creating any Issue).
  - Apply mode now: gh-auth check → label preflight → Issue creation loop.

- **PRE2-P2-001 FIXED — Issue body footer count is now dynamic.** `render_body(issue, issue_total=len(issues))`. Footer reads "one of {ISSUE_TOTAL} opened by PR-E" with `ISSUE_TOTAL = 133` for the current parse.

## iter-2-resubmit dry-run verification

```
Parsed 133 Issues from issue_breakdown.md
I-bug-079 labels: ['phase-1', 'feature-f1']  (canonical, NOT feature-f1-intake)
Footer count: "one of 133 opened by PR-E"  (dynamic, NOT stale 130)
```

## Files in this iter-3 set (3 files)

```
scripts/restart/open_github_issues.py     (UPDATED — all 4 iter-2 fixes)
state/polaris_restart/pr_e_issues_dryrun.txt  (REGENERATED — 133 Issues, canonical Feature labels, dynamic footer count)
.codex/pr_e_open_issues_review_brief.md    (this brief)
```

## Specific risks to audit on iter-3

1. **PRE2-P1-001 closure:** spot-check labels for bug Issues:
   - I-bug-079: source `F1 (intake)` → label `feature-f1` ✓ (verified above)
   - I-bug-082: source `F15 (audit-bundle)` → expect label `feature-f15`
   - I-bug-084: source `F12 (benchmark)` or similar → expect label `feature-f12-benchmark` (per default_feature for `bug-084`)

2. **PRE2-P1-002 closure:** spot-check 4 Issues that use `Foundation` (not `Foundation refs`) at issue_breakdown.md:275/356/441/504. Verify their bodies now include the issue-specific foundation line.

3. **PRE2-P1-003 closure:** verify `ensure_labels_exist()` is called BEFORE the Issue-creation loop. Verify `RuntimeError` from label-create failure aborts with exit 2, NOT silently. Verify `--force` flag on `gh label create` doesn't accidentally overwrite existing labels with different colors/descriptions (it idempotently updates description; that's acceptable).

4. **PRE2-P2-001 closure:** every Issue body's footer says "one of 133 opened by PR-E" (not 130).

5. **Regression check on iter-1 fixes:** all 133 Issues parsed (PRE-001 ✓), zero "(unspecified)" Phase (PRE-002 ✓), `user-blocked` label fires for `YES (...)` source values (PRE-003 ✓).

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

List ALL findings this iteration. Do NOT hold any back to drip-feed across iterations. Same quality bar regardless of iteration count. No hard cap on iterations. Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## iter-1 findings addressed

- **PRE-001 FIXED — bug-issue headers now matched.** Header regex updated from `^### I-...` to `^(?:###|##\s+§[0-9]+)\s+I-...` so both standard `### I-f1-001 — title` AND bug-reissue `## §7 I-bug-079 — async/sync collision (reissued)` headers match. Optional ` (reissued)` suffix stripped via non-capturing trailing group. New parse count: **133 Issues** (was 130; +3 bug Issues now captured). Bug Issues no longer have their fields silently inherited by preceding non-bug Issues (Codex correctly flagged I-f12-004 inheriting bug-084 scope).

- **PRE-002 FIXED — §3a Phase/Feature defaults implemented.** Added `PHASE_BY_PREFIX` + `FEATURE_BY_PREFIX` dicts mapping issue-id prefix → default phase/feature per `state/polaris_restart/issue_breakdown.md:114-125`. Helper `issue_id_prefix()` extracts prefix (special-case for `bug-NNN` to disambiguate by bug number). `default_phase()` + `default_feature()` consulted in BOTH `render_body()` and `issue_label()`. Empirical: zero remaining "(unspecified)" Phase fields in iter-2 transcript.

- **PRE-003 FIXED — `user-blocked` label uses `startswith("YES")`.** Source values like `YES (account, billing, payment)` and `YES (Codex sourcing decision)` now correctly trigger the label. Old exact-equality check (`== "YES"`) only matched bare `YES`, missing all reason-bearing variants.

## Files in this iter-2 set (3 files)

```
scripts/restart/open_github_issues.py     (UPDATED — all 3 P1 fixes)
state/polaris_restart/pr_e_issues_dryrun.txt  (REGENERATED — 133 Issues, full Phase/Feature defaults applied)
.codex/pr_e_open_issues_review_brief.md    (this brief)
```

## Specific risks to audit on iter-2

1. **PRE-001 closure:** verify transcript includes I-bug-079, I-bug-082, I-bug-084 with their own scope/acceptance fields (NOT shared with preceding Issues). Total Issue count = 133.

2. **PRE-002 closure:** spot-check Issues that inherit defaults. Examples to verify:
   - `I-f1-001`: should have Phase=1, Feature=F1, labels=[`phase-1`, `feature-f1`]
   - `I-f6-001`: should have Phase=2B (NOT 2A — iter 3 PHASE-METADATA-CONFLICT resolved F6 → 2B only)
   - `I-cj-001`: should have Phase=side-track, Feature=crown-jewel-preservation
   - `I-bug-079`: should have Phase=1, Feature=F1
   - `I-bug-084`: should have Phase=3, Feature=F12-benchmark
   - `I-hand-001`: should have Phase=5, Feature=handover

3. **PRE-003 closure:** spot-check Issues with `User-blocked: YES (...)` source values. Examples:
   - `I-phase0-003` (Vast.ai): YES (account, billing, payment) → should have `user-blocked` label.
   - `I-phase0-006` (DeepSeek hardware): YES (path decision) → label.
   - `I-phase0-009` (OVH H200): YES (procurement, hardware) → label.

4. **Total parse correctness:** 133 must equal source-of-truth count from issue_breakdown.md:1274 (Codex iter-1 cited 133). Confirm.

5. **Idempotency verification:** re-running `--apply` after a partial success skips Issues already in `issue_github_map.json`. The persistence-after-each-create pattern means even a network failure mid-loop leaves a consistent map.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

List ALL findings this iteration. Do NOT hold any back to drip-feed across iterations. Same quality bar regardless of iteration count. No hard cap on iterations. Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Background

PR-A (restart plan + issue breakdown + cleanup audit), PR-B (DNA doc substrate), PR-B2 (relocate polaris-controls), PR-C (10 cleanup PRs), PR-D (codex-required.yml + cleanup ancestry workflow) all complete and Codex APPROVE'd.

Per plan §6 canonical 10-PR table + cleanup_audit.md, **PR-E opens all 130 GitHub Issues** from `state/polaris_restart/issue_breakdown.md` (Codex APPROVE iter 4) on `aldrinor/polaris`. Each Issue uses the §3 issue body template with the canonical 5-artifact contract documented in PR-D's `.github/workflows/codex-required.yml`.

## Files in this PR

```
scripts/restart/open_github_issues.py     (NEW, ~220 lines, dry-run + apply modes)
state/polaris_restart/pr_e_issues_dryrun.txt  (NEW, ~7400 lines, full transcript of all 130 rendered Issue bodies)
```

After Codex APPROVE on this dry-run, operator (or Claude with appropriate gh token) runs `python scripts/restart/open_github_issues.py --apply` which:
1. Calls `gh auth status` precondition check.
2. Iterates 130 Issues in DAG order (file order in issue_breakdown.md).
3. For each Issue, calls `gh issue create --repo aldrinor/polaris --title "<id> — <short>" --body "<rendered>" --label phase-N --label feature-X [--label user-blocked]`.
4. Records `{issue_id: github_issue_number}` to `state/polaris_restart/issue_github_map.json` AFTER each successful create (resumable on failure).
5. Reports `created=N skipped=M failed=P`. Non-zero exit on any failure.

## What `open_github_issues.py` does

1. **Parser:** reads `issue_breakdown.md`, locates `### I-...` headers, walks each Issue's bullet-list `- **Field:** value` lines, splits compound fields like `- **Phase:** 0 / **Feature:** infra` into separate Phase + Feature entries via per-line FIELD_RE finditer.
2. **Body renderer:** uses §3 template, fills in: Phase / Feature / Scope / Foundation refs (4 default lines + Issue-specific) / Acceptance criteria / Out of scope / Adversarial inputs / LOC estimate / Per-Issue artifacts required (canonical 5-artifact list from CLAUDE.md §3.0 + PR-D iter 4 fix) / Blocks (Blocked by + Blocks + User-blocked).
3. **Label generator:** `safe_label()` strips non-`[a-z0-9_-]` chars, rejects empty values. Phase + Feature + (optional) `user-blocked` labels.
4. **gh CLI invocation:** subprocess `gh issue create ...` per Issue. Persists map after each success.

## Specific risks to audit on iter-1

1. **Body schema correctness:** open `state/polaris_restart/pr_e_issues_dryrun.txt`. Verify any Issue's body contains all required §3 sections in order: Phase/Feature, Scope, Foundation refs (with 4 default lines + optional Issue-specific), Acceptance criteria, Out of scope, Adversarial inputs, LOC estimate, Per-Issue artifacts, Blocks. Look for "(unspecified)" / "(none specified)" markers — these indicate gaps in issue_breakdown.md, not parser bugs (the marker correctly surfaces the gap so operator can update the source-of-truth doc).

2. **Per-Issue artifacts list correctness:** every Issue body lists exactly 5 artifacts:
   - `.codex/<issue_id>/brief.md`
   - `.codex/<issue_id>/codex_brief_verdict.txt`
   - `.codex/<issue_id>/codex_diff.patch` (with canonical-diff-sha256 trailer)
   - `.codex/<issue_id>/codex_diff_audit.txt`
   - `outputs/audits/<issue_id>/claude_audit.md`
   This must match codex-required.yml's `verify_codex_artifacts` step exactly. A mismatch would mean Issues opened by PR-E reference a different artifact contract than the gate enforces.

3. **issue_id format compliance:** all 130 issue IDs in the transcript must match `I-[a-z0-9]{2,8}-[0-9]{3}` (codex-required.yml regex). Any title with a non-canonical ID would fail the gate when its bot-PR opens. Sample IDs: `I-phase0-003`, `I-bug-079`, `I-f1-001`, `I-cj-001`, `I-anti-001`, `I-hand-001`. Look for any ID outside this pattern.

4. **Label safety:** labels like `phase-0`, `feature-infra`, `user-blocked` should NOT contain slashes, asterisks, or other GH-rejected characters. The `safe_label()` function strips these but verify against the dry-run output. (Earlier draft had bug: `'phase-0 / **feature:** infra'` as a single label — fixed by splitting on FIELD_RE finditer per line.)

5. **Compound-field parsing:** the line `- **Phase:** 0 / **Feature:** infra` should produce TWO separate fields `Phase=0` and `Feature=infra`, NOT one field `Phase=0 / **Feature:** infra`. Verify any Issue with this pattern in issue_breakdown.md gets split correctly.

6. **Multi-line field handling:** some fields like `Acceptance` span multiple bullet sub-items in markdown. Current parser captures only the FIRST line value. Verify this is acceptable or whether multi-line capture is needed. (Empirically: most Issues have single-line Acceptance / Scope; multi-line cases would render as truncated. Edge case.)

7. **Apply-mode safety:**
   - `gh issue create` is called per-Issue, not in a single bulk API call. If the script crashes mid-loop (e.g., rate limit, network), the issue_github_map.json persists what was created up to that point, so re-running with --apply skips the already-created Issues.
   - GitHub API rate limit: 5000 req/hour for authenticated users. 130 Issues = 130 requests. Well under limit. No throttling needed.
   - Idempotency: re-running --apply sees existing entries in issue_github_map.json and skips. No duplicate Issues.

8. **Failure mode:** if any Issue fails to create (e.g., body too long, invalid label), script reports `failed > 0` and exits 3. Successful creations stay in the map. Operator inspects, fixes the source data, re-runs.

9. **Out-of-band Issue body content security:** the Issue bodies render verbatim text from issue_breakdown.md. That text passed Codex APPROVE iter 4 review on PR-A2. No HTML / no JS / no exec context — markdown only. GitHub renders Issue bodies as markdown; no XSS surface.

10. **Branch protection compatibility:** PR-E itself is committed via `bot/pr-e-open-github-issues` head ref. Per PR-D iter 6 PRD6-P1-001 fix, `bot/pr-e` is on the infra-branch allowlist → `codex-required.yml` skips the gate cleanly for PR-E. Verify the head-ref name matches the allowlist exactly.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

List ALL findings this iteration. Do NOT hold any back to drip-feed across iterations. Same quality bar regardless of iteration count. No hard cap on iterations. Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
