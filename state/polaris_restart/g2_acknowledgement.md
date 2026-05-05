# G2 Operator Acknowledgement — POLARIS restart 2026-05-05

**Status:** Staging document, drafted by Claude inside `C:\POLARIS\` per user directive 2026-05-05 night ("everything inside polaris folder, you shall be the one to execute"). User will sign the canonical commit on `polaris-controls` per plan §7.G.

**Operator:** aldrinor (sotaleung@gmail.com)
**Authority:** CHARTER §"Plan Edit Path" — hardware-token-signed commit on admin-only `polaris-controls` repo.
**Effective date:** 2026-05-05.

---

## §1 Anchored SHA pins (mirrored from `state/polaris_restart/charter_sha_pin.txt`)

```
f4935571ed8fff4ba20a945a45ab990206d624f7  polaris-controls/CHARTER.md
0dd0dd80eedcb41493f844172bea0767acffbebe  polaris-controls/PLAN.md
```

These are `git hash-object` blob hashes, computed against the working-tree contents of `polaris-controls/CHARTER.md` and `polaris-controls/PLAN.md` as of 2026-05-05.

By signing this acknowledgement, the operator attests:

1. The two SHAs above are canonical for the current charter generation.
2. POLARIS-side `state/polaris_restart/charter_sha_pin.txt` records exactly these two SHAs in the same `<sha>  polaris-controls/<file>` format the session-start hook expects.
3. Any future drift detected by `scripts/hooks/session_start_check.py` (Python canonical) or `scripts/hooks/session_start_check.sh` (Linux/CI fallback) is to be treated as a HARD STOP per Plan §10 step 0, requiring a fresh operator-signed reconciliation commit before tool calls resume.

## §2 Slice 001 goldens — operator review per plan §7.G LOCKED G2

Per plan §7.G (LOCKED 2026-05-05), the operator hereby:

- Acknowledges the 5 slice 001 golden test JSON files as they exist on `polaris-controls/golden/slice_001/` are byte-for-byte preserved (no content rewrites).
- Affirms operator review of all 5 goldens has been completed.
- Adopts CHARTER §4 invariant going forward: **tests are immutable to Claude and Codex** (admin-only `polaris-controls/` repo, CODEOWNERS-protected).
- Records the pre-G2 origin (Claude drafted, user did not sign at draft time) as a one-time exception logged in plan §2.8.

The `_drafting_notes` field of each slice 001 golden JSON, going forward, may be annotated by the operator with the line:

> "Operator-approved by aldrinor on 2026-05-05 via signed commit `<short-sha>` on polaris-controls."

…where `<short-sha>` is the abbreviated SHA of the commit landing this acknowledgement. (Annotation is optional — the signed commit itself is the operative attestation; the in-file line is only for human-readable provenance.)

## §3 Trust-model decisions ratified

The operator ratifies the 7 LOCKED decisions of plan §12 as in force from this commit forward:

1. §7.A coder identity → **A2** — Claude writes briefs + diffs; Codex reviews.
2. §7.B trust model → **B1** pure auto-merge — Codex APPROVE → CI passes → GitHub auto-merges; operator reads `git log` next morning as after-the-fact human-at-merge surface.
3. §7.C Codex APPROVE rule → **C2** — zero P0 AND zero P1.
4. §7.D drift handling → **ROAD B without cherry-pick** — bugs #79 / #82 / #84 reissued as I-BUG-079 / I-BUG-082 / I-BUG-084.
5. §7.E cleanup destructive ops → **ARCHIVE not DELETE** by default.
6. §7.F Phase 0 hardware → **leapfrog OK** — Phase 1 software work proceeds against OpenRouter API ahead of OVH H200 procurement.
7. §7.G goldens authorship → **G2** (this very acknowledgement).

## §4 What this commit unblocks (sequence)

The signed commit landing this acknowledgement satisfies plan §2 mandatory pre-execution precondition #3 ("§7.G G2 signed commit on polaris-controls"). Specifically, it unblocks the path:

- **PR-C** (surgical cleanup execution per `state/polaris_restart/cleanup_audit.md` Cleanup-PR-1..PR-8 schedule) — currently blocked on USER ACTIONS 1+2 per `state/active_issue.json`. This commit is USER ACTION 1.

PR-C, PR-D (mechanical gates), PR-E (open all GitHub Issues), PR-F (execute Issue #1) remain in sequence. None can start before this commit + USER ACTION 2 (mechanical isolation gates live) both land.

## §5 What this commit does NOT do

- Does not enable GitHub branch protection on `aldrinor/polaris` (USER ACTION 2 part 1 — operator GitHub UI clicks).
- Does not revoke `gh pr merge --admin` from the Claude-side token (USER ACTION 2 part 2 — `gh auth refresh --remove-scopes admin:repo`).
- Does not deploy `.github/workflows/codex-required.yml` (PR-D scope).
- Does not modify any slice 001 golden JSON content (per plan §7.G G2: bytes preserved).

## §6 How to apply this acknowledgement

The operator chooses one of the following equivalent landing methods on the admin-only `polaris-controls` repo (any clone or working tree the operator controls; not POLARIS).

**Method A — commit message body:**
```
cd <polaris-controls working tree>
git commit --allow-empty -S -m "G2: anchor CHARTER+PLAN SHAs

f4935571ed8fff4ba20a945a45ab990206d624f7  CHARTER.md
0dd0dd80eedcb41493f844172bea0767acffbebe  PLAN.md

Operator-approval of slice 001 goldens per plan §7.G LOCKED G2.
Ratifies §12 LOCKED decisions A2 / B1 / C2 / ROAD B / ARCHIVE / leapfrog / G2.
Effective 2026-05-05; reference C:\POLARIS\state\polaris_restart\g2_acknowledgement.md."
```

**Method B — tracked file inside polaris-controls:**
```
cp C:\POLARIS\state\polaris_restart\g2_acknowledgement.md <polaris-controls>\g2_acknowledgement_2026_05_05.md
cd <polaris-controls working tree>
git add g2_acknowledgement_2026_05_05.md
git commit -S -m "G2: anchor CHARTER+PLAN SHAs (per g2_acknowledgement_2026_05_05.md)"
git push origin <branch>
```

Method B is preferred by Codex review record because the file becomes a durable artifact in `polaris-controls` git history.

Either method satisfies plan §2 precondition #3 once the commit reaches `polaris-controls/` origin AND is verifiably signed by the operator's hardware token.
