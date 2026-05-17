# Codex BRIEF review — I-naming-003 / GH #437: rename v30_sweep_integration.py → honest_sweep_integration.py

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 0.1 Review stage — PRE-IMPLEMENTATION brief review

This is the **brief** review (the plan). The working tree is intentionally
unmodified; the diff review later verifies the applied rename. Evaluate §2-§3
as a plan — especially the §3 scope-boundary call.

## 1. Issue

GH #437 (I-naming-003) — naming-audit follow-up from #434.
`src/polaris_graph/v30_sweep_integration.py` is a version-only filename (§4.1
forbids version numbers in names). Rename to `honest_sweep_integration.py`.
P3, mechanical. Branch `bot/I-naming-003` (a normal `I-<prefix>-<NNN>` id —
no re-cut needed).

## 2. The rename — file + import-path ONLY

### File renames (`git mv`, history-preserving)
- `src/polaris_graph/v30_sweep_integration.py` → `honest_sweep_integration.py`
- `tests/polaris_graph/test_v30_sweep_integration.py` →
  `test_honest_sweep_integration.py`

### Import-path token: `v30_sweep_integration` → `honest_sweep_integration`
Applied as a substring replacement over exactly 3 files. **Verified**: the
token `v30_sweep_integration` occurs ONLY as an import path / the test
filename / two doc-comments — it is NOT embedded inside any identifier (grep
`v30_sweep_integration` in `src/`+`tests/`+`scripts/` minus import/comment/
test-filename lines → zero hits). So the substring replace is exactly the
file-rename scope and cannot touch anything else.
- `src/polaris_graph/honest_sweep_integration.py` (the renamed module — only
  if its own docstring/comments reference the path token; "V30 sweep
  integration" *prose* with spaces is NOT the token and is kept).
- `scripts/run_honest_sweep_r3.py:2846` — `from src.polaris_graph.v30_sweep_integration
  import (...)` → `...honest_sweep_integration import`; plus the two comments
  at `:2855` ("in v30_sweep_integration module docstring") and `:2867`
  ("in tests/polaris_graph/test_v30_sweep_integration.py").
- `tests/polaris_graph/test_honest_sweep_integration.py` — 21 `from
  src.polaris_graph.v30_sweep_integration import` statements.

## 3. Scope boundary — file + import-path ONLY (NOT the identifiers)

Unlike #436 (where the version-tagged identifiers had a tiny pure-Python
footprint and were renamed), #437's `V30`/`v30` identifiers are entangled
with serialization / config / report output and are **deliberately left
intact** — out of a P3 filename-hygiene rename:
- `class V30SweepResult` + the functions `merge_v30_into_manifest` /
  `run_v30_post_generation` — public API imported by
  `run_honest_sweep_r3.py`; `merge_v30_into_manifest` writes manifest keys.
- `v30_enabled` / `v30_error` / `v30_warnings` / `v30_skipped_reason` — these
  are `V30SweepResult` fields and/or **manifest.json keys** written by
  `merge_v30_into_manifest`; renaming them is a serialized-schema change (it
  would need a dual-read shim, far beyond a P3 rename).
- `PG_V30_ENABLED` — the feature-flag **env-var name** operators set.
- `## V30 Phase-1 Retrieval Coverage Disclosure` — a section **heading
  emitted into `report.md`** (a Codex audit pass-5 explicitly verified this
  exact heading); renaming it changes report output.
- `[V30]` log tags + "V30 sweep integration" docstring prose — "V30" is the
  legitimate name of the audit-oriented sweep feature this module wires.

**Question for Codex:** confirm #437 should be file + import-path only — the
`V30Sweep*` / `merge_v30_*` / `run_v30_*` API and the `v30_*` schema keys are
genuinely schema/config/output, not filename hygiene. (If you judge the
public function names *should* also move, that is a wider API change worth a
separate issue, not folded into a P3.)

## 4. Files I have ALSO checked and they're clean

- `grep -rn "v30_sweep_integration"` whole repo (excl. `.codex/`, `archive/`,
  `codex_tmp*`, `state/`, `__pycache__`): the only code refs are the module,
  the test, and `run_honest_sweep_r3.py`'s import + 2 comments.
  `outputs/audits/**` + `outputs/codex_findings/**` mentions are historical
  audit records — deliberately NOT rewritten.
- No `importlib` / dynamic / string-path reference to the module.
- The import at `run_honest_sweep_r3.py:2846` is guarded by
  `PG_V30_ENABLED` — the env var is unchanged, so the guard still works.

## 5. Test / smoke

`git mv` preserves history. After: `ast.parse` the renamed module + the 2
updated importers; `PYTHONPATH='src;.' pytest tests/polaris_graph/test_honest_sweep_integration.py`
(20 `test_` cases) + a `python -c "import src.polaris_graph.honest_sweep_integration"`
import smoke. No behaviour test applies — pure rename.

## 6. Required output schema (§8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

Loose verdict prose is rejected — emit the schema.
