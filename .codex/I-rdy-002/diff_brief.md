# Codex DIFF review — I-rdy-002/003 (#498, #499): Phase 1 gap verification + pin verified statuses

**Type:** DIFF review, iter 2 of 5. The I-rdy-002 brief was Codex-APPROVED iter 4 (`codex_brief_verdict.txt`). This reviews the diff.

**iter 1 → REQUEST_CHANGES (1 P1), fixed:** the §3 header said VERIFIED while the Pinning paragraph + §3.2 footer still said PROVISIONAL — internal contradiction. Fixed by narrowing the VERIFIED claim to §3.1 (per Codex): the Pinning paragraph now states §3.1 VERIFIED + pinned, §3.2 explicitly still PROVISIONAL; the §3 header is scoped to "§3.1 status values"; the §3.2 footer states the Phase 1 pass did not cover §3.2. The canonical diff is now 9+/5− on `polaris_locked_scope.md`.

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

I-rdy-002 (#498): Phase 1 gap verification — ground the §3 feature statuses in `docs/polaris_locked_scope.md` against the live deployed system + static code inspection. I-rdy-003 (#499): pin the verified statuses.

**Clean recut.** This is the I-rdy-002/003 half of the #517 split (Codex disposition `A_recut`). Branch `bot/I-rdy-002-gap-verification` is **stacked on `bot/I-rdy-001-scope-lock`** (PR #519) because the work edits `docs/polaris_locked_scope.md`, which I-rdy-001 creates. The PR base is the I-rdy-001 branch; it retargets to `polaris` when #519 merges.

## §2. The diff (`.codex/I-rdy-002/codex_diff.patch`)

Canonical diff vs the I-rdy-001 base: `docs/polaris_locked_scope.md` only — 8 lines (4+/4−). The §3 header flips from "Status values are PROVISIONAL" to "Status values are VERIFIED 2026-05-15 ... evidence: `.codex/I-rdy-002/verification_findings.md`", and the §3.1 table header from "Provisional status" to "Verified status".

The substantive deliverable — the Phase 1 verification itself — is `.codex/I-rdy-002/verification_findings.md` (49 lines, Codex-APPROVED at the brief gate iter 4); it lives under `.codex/I-rdy-002/` and is excluded from the canonical code diff.

## §3. Verify
1. The 8-line `polaris_locked_scope.md` change correctly reflects the I-rdy-002 verification — PROVISIONAL → VERIFIED is sound given `verification_findings.md`.
2. No leftover conflict markers, no I-gen-003 / research-scratch contamination.
3. The diff is consistent with the brief (APPROVED iter 4).

## §4. Output schema (CLAUDE.md §8.3.9)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
verdict_reasoning: <text>
```
