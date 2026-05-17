# Claude architect audit — I-naming-009 (#443)

**Issue:** GH #443 — rename `synthesis/ionic_rebalancer.py` →
`evidence_section_affinity.py` (naming-audit follow-up from #434;
chemistry-metaphor filename, §4.1 cryptic-name hygiene).
**Branch:** `bot/I-naming-009`
**Commit 1 (rename):** `176ace14` — 3 files, +4/-4, 1 history-preserving rename.
**Brief:** `.codex/I-naming-009/brief.md` — Codex APPROVE iter 1 (clean — 0
P0/P1/P2).

## 1. What shipped

| Change | Detail |
|---|---|
| `git mv` ×1 | `synthesis/ionic_rebalancer.py` → `evidence_section_affinity.py` (100% similarity). |
| Import-path | `ionic_rebalancer` → `evidence_section_affinity` — 4 occurrences across 2 importers: `synthesizer.py` (2 `from … import` statements at `:3034`/`:3042` + 1 O(n²)-comment mention at `:2984`), `cross_section_reflector.py` (1 `from … import` at `:428`). |

The new filename matches the module's own docstring subtitle
"Evidence-Section Affinity Rebalancing". Last of the four chemistry-metaphor
synthesis files (#440/#441/#442 merged).

## 2. Per-finding verification

- **VERIFIED — token is path-only**: `ionic_rebalancer` is NOT embedded in
  any identifier — the public functions are `analyze_ionic_bonds` /
  `format_ionic_findings_for_phase_r` (`ionic_bonds`/`ionic_findings`,
  different tokens). Pre-rename `grep` confirmed `ionic_rebalancer` occurs
  only as the module path (4 sites in 2 importers) and nowhere in the
  module's own content. Post-rename `grep -rn "ionic_rebalancer"
  --include=*.py src/ tests/ scripts/` → **0**. `analyze_ionic_bonds` → 2 in
  the renamed module + 2 in `synthesizer.py`, all intact.
- **VERIFIED — scope boundary (Codex-adjudicated APPROVE)**: the metaphor
  identifiers are left intact — `analyze_ionic_bonds` /
  `format_ionic_findings_for_phase_r` (module API) and
  `bond_analysis["ionic"]` — `"ionic"` is one of four parallel keys
  (`covalent`/`ionic`/`disulfide`/`peptide`) in the shared `bond_analysis`
  dict. Codex's iter-1 brief review confirmed this scope (clean APPROVE).
- **VERIFIED — import closure**: `from
  src.polaris_graph.synthesis.evidence_section_affinity import
  analyze_ionic_bonds, format_ionic_findings_for_phase_r` resolves. Both
  importers use a lazy `from … import` inside `try/except`; no
  `importlib`/dynamic/string-path reference.
- **VERIFIED — history preserved**: `git mv` → diff shows `rename …
  ionic_rebalancer.py => evidence_section_affinity.py (100%)`.

## 3. Test / smoke

`ast.parse` clean on the renamed module + the 2 edited importers. Import
smoke resolves the 2 public functions. `PYTHONPATH='src;.' pytest`
`tests/unit/test_cross_section_reflector.py` +
`tests/polaris_graph/test_analyst_synthesis.py` +
`tests/polaris_graph/test_patch_b_cross_section_polish.py` → **44 passed**.
No test imports the module directly; no behaviour test applies — pure rename.

## 4. Scope + residuals

- Commit-1 diff is +4/-4 across 3 files — trivially under the 200-LOC cap.
- `docs/substrate_audit_2026-05-01.md` (dated audit snapshot) +
  `docs/pipeline_audit_context/08_env_var_inventory.md` (pipeline-audit-context
  inventory) are left intact as point-in-time audit-trail records, consistent
  with the #436-442 precedent.
- This completes the four chemistry-metaphor synthesis-file renames
  (#440-443); #444 (`graph_v4.py`) is the remaining naming-audit issue.

## 5. Risk assessment

Pure rename — no logic change. The token was grep-proven path-only (not
embedded in any identifier), so a plain substring replace over the 2
importers carried zero collision risk. The 44-test dependent suite passes.

## 6. Verdict

Rename complete, faithful to the iter-1 APPROVE'd brief (clean) + Codex's
scope adjudication; offline suite green. Ready for Codex diff review.
