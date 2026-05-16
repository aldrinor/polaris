# I-rdy-002/003 (#498, #499) — Claude architect self-review

**Scope:** I-rdy-002 (#498) — Phase 1 gap verification: ground the §3.1 feature
statuses in `docs/polaris_locked_scope.md` against the live deployed system +
static code inspection. I-rdy-003 (#499) — pin the verified statuses.

**Provenance:** clean recut of the I-rdy-002/003 half of PR #517 (Codex
disposition `A_recut`). Branch `bot/I-rdy-002-gap-verification` is **stacked on
`bot/I-rdy-001-scope-lock`** (PR #519) — the work edits
`docs/polaris_locked_scope.md`, which I-rdy-001 creates. The PR base is the
I-rdy-001 branch; GitHub retargets it to `polaris` when #519 merges.

**Deliverable:**
- `.codex/I-rdy-002/verification_findings.md` (49 lines) — the Phase 1
  verification (Codex APPROVE iter 4 at the brief gate).
- `docs/polaris_locked_scope.md` — §3.1 feature statuses flipped
  PROVISIONAL → VERIFIED; §3.2 cross-cutting capabilities explicitly remain
  PROVISIONAL (not covered by the Phase 1 pass).

**Codex:** brief APPROVE iter 4; diff APPROVE iter 2 — iter-1 P1 (the §3 header
said VERIFIED while the Pinning paragraph + §3.2 footer still said PROVISIONAL —
internal contradiction in the locked source-of-truth) fixed by narrowing the
VERIFIED claim to §3.1.

**Note:** stacked PR — `codex-required` runs once #519 merges and GitHub
retargets the base to `polaris`. If #519 is squash-merged, the
`canonical-diff-sha256` is recomputed and the branch rebased onto `polaris`
at that point (the I-rdy-002/003 content is unchanged by the rebase; only the
base differs).
