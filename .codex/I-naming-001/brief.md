# Codex BRIEF review — I-naming-001 (#434): rename BPEI → ambiguity_detector

**Type:** BRIEF review, iter 1 of 5. **Retrospective redo-gate** of PR #435 per Codex disposition `A_redo_gate` (`.codex/pr_merge_disposition/codex_verdict.txt`). The original review used the older `codex_plan_*` / `codex_diff_*` artifact naming and was never sha256-bound; this re-runs the gate against the canonical filenames so the verdict binds to the actual diff.

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

## §1. Issue

GH#434 (I-naming-001): the legacy name **"BPEI" is banned** in demo-facing code, docs, and config (`docs/polaris_locked_scope.md` §1.4). Rename the module + all references to `ambiguity_detector`.

## §2. The change — 32-file canonical diff (`.codex/I-naming-001/codex_diff.patch`, +268/−57)

- **Module rename:** `src/polaris_v6/bpei/` → `src/polaris_v6/ambiguity_detector/` (`__init__.py`, `ambiguity_detector.py`).
- **~30 reference updates:** import paths + identifiers across `src/polaris_graph/`, `src/polaris_v6/`, `tests/`, `web/` (each ±2 lines).
- **Rename-completion fix (this redo-gate):** `src/polaris_graph/api/intake.py:96` docstring "front-half BPEI pipeline" → "ambiguity-detection pipeline".

## §3. Acceptance criteria
1. Zero `BPEI`/`bpei` references that *name the module/pipeline* remain in demo-facing code.
2. No broken imports — the renamed module resolves at every call site.
3. Tests referencing the module are updated (`tests/v6/test_ambiguity_detector.py`).

## §4. Files I have ALSO checked — the remaining `bpei` hits in `src/`, all legitimate (kept by design)
- `cluster_labeler.py:5`, `disambiguation_clusterer.py:5` — the literal string `"BPEI"` used as the **canonical example of an ambiguous acronym** (BPEI → syndrome / institute / chemical). This is example input data, not a module name — renaming it would destroy the disambiguation example.
- `ambiguity_detector/__init__.py:9,11,14`, `ambiguity_detector.py:4`, `memory/__init__.py:3` — `Historical:` rename-explainer comments + citations of the user-memory file `bpei_phantom_completion_lessons.md` (a file outside this repo; referenced by its real name).

## §5. Output schema (CLAUDE.md §8.3.9)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
verdict_reasoning: <text>
```
