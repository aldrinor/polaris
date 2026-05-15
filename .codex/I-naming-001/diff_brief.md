# Codex DIFF review — I-naming-001 (#434): BPEI → ambiguity_detector rename

**Type:** DIFF review, iter 1 of 5. Brief APPROVED (`codex_brief_verdict.txt`). Retrospective redo-gate of PR #435 per Codex disposition `A_redo_gate` — this binds the verdict to the actual canonical diff via `canonical-diff-sha256`.

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

I-naming-001 (#434): rename the banned legacy module name `BPEI` → `ambiguity_detector` (`docs/polaris_locked_scope.md` §1.4). Brief APPROVED. This reviews the 32-file rename diff.

## §2. The diff — `.codex/I-naming-001/codex_diff.patch` (32 files, +268/−57)
- Module rename: `src/polaris_v6/bpei/` → `src/polaris_v6/ambiguity_detector/`.
- ~30 import-path / identifier reference updates across `src/polaris_graph/`, `src/polaris_v6/`, `tests/`, `web/`.
- `src/polaris_graph/api/intake.py:96` docstring "BPEI pipeline" → "ambiguity-detection pipeline".

## §3. Verify
1. The rename is complete — no `BPEI`/`bpei` that *names the module or pipeline* remains in demo-facing code.
2. No broken imports — `ambiguity_detector` resolves at every updated call site.
3. Tests updated (`tests/v6/test_ambiguity_detector.py`).
4. The retained `bpei` references are correctly retained, NOT misses: the literal `"BPEI"` disambiguation **example string** in `cluster_labeler.py` / `disambiguation_clusterer.py`, and the `Historical:` rename-explainer comments + `bpei_phantom_completion_lessons.md` memory-file citations.

## §4. Output schema (CLAUDE.md §8.3.9)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
verdict_reasoning: <text>
```
