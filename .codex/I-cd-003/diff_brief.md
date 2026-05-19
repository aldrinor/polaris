HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

DO NOT explore the repository. The COMPLETE diff under review is the single
committed file `.codex/I-cd-003/codex_diff.patch` (42 lines incl. the
`# canonical-diff-sha256:` trailer). Read ONLY that one file.

# Codex DIFF review — I-cd-003 / GH#622: canonical-pin reconciliation

## §A — What this is

The diff implements the Codex-APPROVED brief `.codex/I-cd-003/brief.md` (brief
APPROVE iter 1, zero findings). Two files in the canonical diff:

- `docs/canonical_pin.txt` — 6 SHAs updated to HEAD-blob values; 4 unchanged.
- `state/polaris_restart/iteration_trajectory.md` — the mandatory §8.3.5 log.

Total canonical diff is small (~40 lines). The pin file was regenerated
deterministically from HEAD: for each canonical file `f`,
`$(git show "HEAD:$f" | sha256sum | cut -d' ' -f1)  $f`. No hand-transcription.

## §B — Red-team focus

1. Are the 6 NEW SHAs in `docs/canonical_pin.txt` byte-for-byte equal to the
   sha256 of `git show HEAD:<file>` at the current PR HEAD?
2. Are the 4 UNCHANGED lines truly unchanged (correctly preserved)?
3. Is the file order preserved (matches `CANONICAL_FILES` in
   `stop_hook_v3.py`)?
4. Does anything in the diff touch a file the pin protects? (It must not — that
   would re-introduce drift in the same PR.)
5. Scope: confirm bundling the `_verify_canonical_pin` wiring + autocrlf-aware
   fix (filed as GH#658) into THIS PR would be scope creep, not necessary.

## §C — Output schema — return EXACTLY this

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: []
continuing_p0: []
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
