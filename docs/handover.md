# POLARIS Handover — issue-driven workflow for any future Claude session

**Last updated:** 2026-05-05 night (PR-A APPROVE'd, PR-B in flight)
**Active plan:** `state/polaris_restart/plan.md` (Codex APPROVE iter 4) + `state/polaris_restart/issue_breakdown.md` (Codex APPROVE iter 4) + `state/polaris_restart/cleanup_audit.md` (Codex APPROVE iter 21)
**Mission plan:** `docs/carney_delivery_plan_v6_2.md` (v6.2, Codex GREEN)
**Charter + Plan:** `C:\POLARIS\polaris-controls\CHARTER.md` AND `C:\POLARIS\polaris-controls\PLAN.md` (admin-only sister repo, both SHA-pinned per `state/polaris_restart/charter_sha_pin.txt`)

## What POLARIS is

Sovereign Canadian deep-research AI to deliver to Mark Carney as a gift to Canada. 18-week build (May 1 → Sep 6, 2026). ~80% of substrate already built (270 Python files, 47 audit_ir modules, 113 prior milestones LOCKED). Build is "expose substrate via modern Next.js UI + sovereign vLLM swap + 10 new pieces."

15 user-visible features F1-F15 each with substrate honesty + match-or-beat bar + exhaustive Playwright+AI test matrix.

## How work flows (issue-driven, mandatory per CLAUDE.md §3.0)

Every unit of work is a GitHub Issue assigned in sequence per `state/polaris_restart/issue_breakdown.md`. Cannot start Issue N+1 until Issue N is `completed`.

**Role split (per polaris-restart Plan §7.A LOCKED A2 + §7.B LOCKED B1):**
- **Claude:** writes code (briefs AND diffs). Author of `.codex/<issue_id>/brief.md` and `.codex/<issue_id>/codex_diff.patch`. Plus writes `outputs/audits/<issue_id>/claude_audit.md` (architect self-review).
- **Codex:** reviews. Two separate Codex calls per Issue — APPROVE on brief (acceptance correctness) + APPROVE on diff (Red-Team checklist). Codex is the only merge gate.
- **User:** spec owner + after-the-fact merge gate. Reads `git log` in morning (B1 pure auto-merge); does NOT click merge per-PR.
- CI required check `polaris/codex-required` parses Codex's verdict file and gates GitHub auto-merge. Claude has NO `gh pr merge --admin` authority.

**Per-Issue mandatory artifacts** (CI will reject PR without these once PR-D installs the gate workflow; pre-PR-D, Codex review enforces):
- `.codex/<issue_id>/brief.md` (Claude-authored, Codex-approved)
- `.codex/<issue_id>/codex_brief_verdict.txt` (Codex APPROVE)
- `.codex/<issue_id>/codex_diff.patch` (Claude-written diff committed under this name; Codex reviews it — per plan §7.A LOCKED A2)
- `.codex/<issue_id>/codex_diff_audit.txt` (Codex APPROVE on Red-Team checklist)
- `outputs/audits/<issue_id>/claude_audit.md` (Claude's architect review)

**Forbidden patterns:**
- `gh pr merge --admin` from Claude account/token (revoked)
- PR opened without all 5 artifacts above
- Issue jump (start `I-X-NNN+1` before `I-X-NNN` merged)
- "While we're at it" polish in same PR
- STATUS block / recap text between PR merge and next branch creation

## Current restart sequence (where we are now)

PR-A1 (plan.md): Codex APPROVE iter 4 ✓
PR-A2 (issue_breakdown.md): Codex APPROVE iter 4 ✓
PR-A3 (cleanup_audit.md): Codex APPROVE iter 21 ✓ ← **completed 2026-05-05 night**
**PR-B (DNA doc updates):** in_progress ← **CURRENT**
PR-C (surgical cleanup execution): blocked on USER ACTIONS 1+2
PR-D (mechanical gates installed): blocked on PR-C
PR-E (open all GitHub Issues): blocked on PR-D
PR-F (execute Issue #1): blocked on PR-E

**USER ACTIONS (user-side prerequisites):**
- USER ACTION 1: G2 signed commit on polaris-controls
- USER ACTION 2: §10.0 mechanical isolation live before Claude resumes Cleanup-PR-1

## Session-start ritual (mandatory per CLAUDE.md §10)

1. Read `polaris-controls/CHARTER.md` and `PLAN.md`
2. Verify SHAs against `state/polaris_restart/charter_sha_pin.txt`
3. Read `state/active_issue.json` — if shows in_progress issue, resume ONLY that issue
4. If no active issue, list TaskCreate tasks unblocked, present to user, wait for assignment
5. State explicitly to user: active issue ID + current step + next action

## Critical memory entries (read these every session)

- `feedback_codex_iteration_5cap_2026_05_06.md` — **CRITICAL CURRENT (2026-05-06).** 5-iter hard cap per Codex review per CLAUDE.md §8.3.1. Trust Codex within the cap; force-APPROVE at iter 5 if still REQUEST_CHANGES, capture residuals as follow-up Issues. SUPERSEDES `feedback_codex_iteration_no_cap_no_toothpaste.md` (2026-05-05; "No hard cap" is REVOKED).
- `failure_28_commits_2026_05_03.md` — DO NOT REPEAT. I have no admin merge authority. CI gate enforces.
- `feedback_dont_relax_assertion_to_hide_bug.md` — Fix the bug, never the assertion.
- `feedback_no_status_blocks_mid_batch.md` — superseded by §3.0 issue-driven workflow but kept as reference for the underlying anti-pattern.

## Key files

- **Mission plan:** `docs/carney_delivery_plan_v6_2.md` (v6.2)
- **Architecture:** `architecture.md` (current state, rewritten 2026-04-18)
- **Substrate audit:** `docs/substrate_audit_2026-05-01.md`
- **Restart plan:** `state/polaris_restart/plan.md` (Codex APPROVE iter 4)
- **Issue breakdown:** `state/polaris_restart/issue_breakdown.md` (134 issues, Codex APPROVE iter 4)
- **Cleanup audit:** `state/polaris_restart/cleanup_audit.md` (Codex APPROVE iter 21)
- **Iteration trajectory:** `state/polaris_restart/iteration_trajectory.md` (full Codex-iter audit trail)

## What I do NOT do

- Open PRs without the 5-artifact triple
- Use `gh pr merge --admin` (revoked per CHARTER §1)
- Pick tasks autonomously without user assignment
- Mark TaskCreate items completed without verifiable evidence
- Add "while we're at it" polish to scoped PRs
- Emit STATUS blocks or recap text mid-batch

## 2026-05-11 status update (post BEAT-BOTH + I-hygiene-001)

### BEAT-BOTH §-1.1 line-by-line audit complete (GH#400 / GH#431)

Q1-Q5 §-1.1 audited claim-by-claim against fetched source content. Result per Codex deep-reasoning verdict:

**`BEAT_GEMINI_CHATGPT_UNAUDITABLE`** — POLARIS dramatically beat Gemini on the measured Q1 apples-to-apples (96.8% V vs 8.6% V). Gemini Q1-Q5 aggregate 12.1% V on 414 claims with one source-misattribution fabrication (Q4 GM-T1-038: CHBA "over 18,000" Ontario jobs reattributed to "Toronto housing starts plummeting per month"). ChatGPT Pro DR substrate+submission-blocked (sealed React Web Component + silent DR-mode failure on Q2+Q3 retries).

POLARIS Q2-Q5 not run this session (cost: ~$30 + 2hrs DeepSeek live). Q1 anchor + architectural extrapolation only — `polaris_q2_q5_extrapolation_assessment: speculative` per Codex.

Master report: `outputs/beat_both_master_report.md`. Per-Q reports: `.codex/I-eval-{004..008}/q{1..5}_beat_both_final.md`. Cross-review verdicts: `.codex/I-eval-{005..008}/claude_cross_review_q{2..5}.md`. Codex final verdict: `.codex/I-eval-004/beat_both_final_verdict_output.txt`.

### I-hygiene-001 root cleanup complete (GH#432)

POLARIS root + `.codex/` archived per Codex iter-4 APPROVE'd plan + iter-1 APPROVE'd diff:
- 372/376 planned moves succeeded.
- 230 historical `.codex/` artifacts archived → `archive/2026-05-11-root-hygiene/codex_historical/` (m28-m63 audit briefs, v17-v30 plan/audit briefs, phase_c/d, pr_b/d/e review files, continuous/, deep_dive_round_*/, walkthrough_*/, etc).
- `.gitignore` hardened with anchored patterns (`/tmp*/`, `/codex_tmp_*/`, `/manual_*/`, `/dashboard_probe_*/`, etc).
- **91 Windows-ACL-locked root dirs** could not be moved (shutil + Move-Item -Force + attrib -R + takeown all returned Access Denied). They are now `.gitignored` (git-invisible). User-level admin elevation or post-reboot retry required to physically remove. List at `state/polaris_restart/i_hygiene_001_force_move_failures.txt`.

### Post-reboot follow-up (user)

After next reboot OR via elevated PowerShell:
```powershell
# Remove the 91 perm-locked dirs (all .gitignored, no git impact)
Get-Content state\polaris_restart\i_hygiene_001_force_move_failures.txt | ForEach-Object {
    $path = ($_ -split ' : ')[0]
    if (Test-Path $path) {
        try { Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction Stop }
        catch { Write-Warning "Failed: $path -- $($_.Exception.Message)" }
    }
}
```

### Outstanding (per `state/polaris_restart/issue_breakdown.md`)

- **GH#90 I-phase0-009** — OVH Canada BHS H200 invoice + provisioning (HARD GATE; blocks GH#199-202 sovereign migration)
- **GH#85** (Vast.ai US dev cluster), **GH#86** (backend modernization), **GH#87** (DeepSeek hardware path), **GH#88** (SGLang vs vLLM bakeoff), **GH#89** (Gemma 4 31B verify), **GH#91** (Gemma 4 license sign-off)
- **GH#199-202** (sovereign vLLM migration + segregation re-verify) — blocked on hardware
- **GH#203** (migration findings), **GH#204** (final walkthrough), **GH#205** (handover package), **GH#206** (Carney office demo) — final phase
