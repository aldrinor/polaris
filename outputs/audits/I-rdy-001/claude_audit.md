# I-rdy-001 (#497) — Claude architect self-review

**Scope:** `docs/polaris_locked_scope.md` — the anti-drift scope lock for the Carney demo.

**Provenance:** clean recut of PR #517, which bundled this issue with four
unfinished I-gen-003 commits and ~50k lines of GPU-research scratch. Per Codex
disposition `A_recut` (`.codex/pr_merge_disposition/codex_verdict.txt`), branch
`bot/I-rdy-001-scope-lock` is cut fresh off `polaris` and carries only the
I-rdy-001 deliverable.

**Deliverable:**
- `docs/polaris_locked_scope.md` (127 lines) — §1 locked constraints (DeepSeek
  V4 Pro generator + Gemma 4 31B evaluator, Canadian sovereign GPU, v6
  architecture, BPEI name banned, demo scope), §2 canonical 8 templates, §3 the
  15 features + cross-cutting capabilities (statuses PROVISIONAL pending I-rdy-002),
  §4 out-of-scope, §5 operator-owned change protocol.
- `docs/file_directory.md` — registers the new doc; the stale "current
  generator V3.2-Exp" line corrected to the V4 Pro + Gemma lock.

**Codex:** brief APPROVE iter 2; diff APPROVE iter 2 — iter-1 found P1 (dead refs
to untracked `state/*` research docs) + P2 (stale model line); both fixed.

**Notes:** §1 constraints are operator-locked; §3 feature statuses are
provisional and get re-pinned in I-rdy-003 after Phase 1 verification.
