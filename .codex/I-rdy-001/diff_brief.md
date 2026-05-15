# Codex DIFF review — I-rdy-001 (#497): lock POLARIS scope

**Type:** DIFF review, iter 2 of 5. The I-rdy-001 brief was Codex-APPROVED (iter 2 — see `codex_brief_verdict_iter2.txt`). This reviews the code/doc diff.

**iter 1 → REQUEST_CHANGES (1 P1, 1 P2), both fixed:**
- P1 (dead refs to untracked `state/*` docs): `docs/file_directory.md` no longer inventories the 5 gitignored `state/*` readiness/research docs; `docs/polaris_locked_scope.md` drops the 3 citations to them. A clean checkout now has zero dead references.
- P2 (stale model line): `file_directory.md:250` now points at the locked V4 Pro + Gemma decision instead of stating V3.2-Exp/Qwen3-8B as "current".

## §0. Cap directive (CLAUDE.md §8.3.1) — verbatim, binding

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## §1. Context

I-rdy-001 (#497): author `docs/polaris_locked_scope.md` — the anti-drift scope lock for the Carney demo (DeepSeek V4 Pro generator + Gemma 4 31B evaluator, v6 architecture, canonical 8 templates, 15 features with VERIFIED statuses, operator-owned change protocol).

**This is a clean recut.** PR #517 bundled this issue with 4 unfinished I-gen-003 commits + ~50k lines of GPU-research scratch. Per Codex disposition `A_recut` (`.codex/pr_merge_disposition/codex_verdict.txt`), branch `bot/I-rdy-001-scope-lock` is cut fresh off `polaris` and carries ONLY the I-rdy-001 deliverable. #517 will be closed.

## §2. The diff (review `.codex/I-rdy-001/codex_diff.patch`)

142 lines, 2 files, pure documentation — no code:
- `docs/polaris_locked_scope.md` — NEW, 127 lines. The scope-lock document.
- `docs/file_directory.md` — +15 lines. Registers the new doc in the inventory.

## §3. Verify
1. The diff is exactly the I-rdy-001 deliverable — no I-gen-003 code, no research scratch leaked in.
2. `docs/polaris_locked_scope.md` is internally consistent and matches the brief's intent (the brief was APPROVED iter 2).
3. `docs/file_directory.md` entry is accurate.
4. No fabricated claims, no contradictions with the canonical stack (V4 Pro + Gemma, v6, 8 templates).

## §4. Output schema (CLAUDE.md §8.3.9)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
verdict_reasoning: <text>
```
