# I-naming-001 (#434) — Claude architect self-review

**Scope:** rename the banned legacy module name `BPEI` → `ambiguity_detector`
(`docs/polaris_locked_scope.md` §1.4).

**Provenance:** retrospective redo-gate of PR #435 per Codex disposition
`A_redo_gate` (`.codex/pr_merge_disposition/codex_verdict.txt`). #435's original
review trail used the older `codex_plan_*` / `codex_diff_*` artifact naming and
was never sha256-bound; this re-runs the §3.0 gate with the canonical filenames
so the verdict binds to the actual canonical diff.

**Change (32-file canonical diff, +268/−57):**
- Module rename `src/polaris_v6/bpei/` → `src/polaris_v6/ambiguity_detector/`.
- ~30 import-path / identifier reference updates across `src/polaris_graph/`,
  `src/polaris_v6/`, `tests/`, `web/`.
- `src/polaris_graph/api/intake.py:96` docstring "front-half BPEI pipeline" →
  "ambiguity-detection pipeline" — a rename-completion miss this redo-gate found.

**Line-by-line verification of residual `bpei` hits in `src/`** (8 total):
- 1 fixed (`intake.py:96`).
- 2 are the literal `"BPEI"` disambiguation **example string** in
  `cluster_labeler.py` / `disambiguation_clusterer.py` — that is the canonical
  ambiguous-acronym example; correctly retained.
- 5 are `Historical:` rename-explainer comments + citations of the user-memory
  file `bpei_phantom_completion_lessons.md`; correctly retained.

**Codex:** brief APPROVE iter 1; diff APPROVE iter 1.

**Note:** #435 also fails the non-required `lint` check on pre-existing `polaris`
debt (`web/app/generation/page.tsx`) — out of scope here; handled by the
dedicated lint cleanup PR.
