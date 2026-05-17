# Claude architect audit — I-naming-008 (#442)

**Issue:** GH #442 — rename `synthesis/covalent_binder.py` →
`claim_evidence_binding.py` (naming-audit follow-up from #434;
chemistry-metaphor filename, §4.1 cryptic-name hygiene).
**Branch:** `bot/I-naming-008`
**Commit 1 (rename):** `b64baf5a` — 2 files, +2/-2, 1 history-preserving rename.
**Brief:** `.codex/I-naming-008/brief.md` — Codex APPROVE iter 1 (clean — 0
P0/P1/P2).

## 1. What shipped

| Change | Detail |
|---|---|
| `git mv` ×1 | `synthesis/covalent_binder.py` → `claim_evidence_binding.py` (100% similarity). |
| Import-path | `covalent_binder` → `claim_evidence_binding` in `synthesizer.py` — the `from … import` statement (`:3016`) + one bare module-name mention in an O(n²) comment (`:2984`). 2 occurrences total. |

The new filename matches the module's own docstring subtitle "Claim-Evidence
Binding Verification".

## 2. Per-finding verification

- **VERIFIED — token is path-only**: unlike #440/#441, `covalent_binder` is
  NOT embedded in any identifier — the public function is
  `analyze_covalent_bonds` (`covalent_bonds`, a different token). Pre-rename
  `grep` confirmed `covalent_binder` occurs only as the module path in
  `synthesizer.py` (2 sites) and nowhere in the module's own content.
  Post-rename `grep -rn "covalent_binder" --include=*.py src/ tests/ scripts/`
  → **0**. `analyze_covalent_bonds` → 1 in the renamed module + 2 in
  `synthesizer.py` (import + call), all intact.
- **VERIFIED — sole importer**: `cross_section_reflector.py` does NOT import
  this module — it only reads the `bond_analysis["covalent"]` key.
  `synthesizer.py` is the only importer; its lazy `from … import` inside a
  `try/except` is the only thing the rename touches.
- **VERIFIED — scope boundary (Codex-adjudicated APPROVE)**: the metaphor
  identifiers are left intact — `analyze_covalent_bonds`/`apply_auto_fixes`
  (module API) and `bond_analysis["covalent"]` — `"covalent"` is one of four
  parallel keys (`covalent`/`ionic`/`disulfide`/`peptide`) in the shared
  `bond_analysis` dict. Codex's iter-1 brief review confirmed this scope
  (clean APPROVE).
- **VERIFIED — import closure**: `from
  src.polaris_graph.synthesis.claim_evidence_binding import
  analyze_covalent_bonds, apply_auto_fixes` resolves. No
  `importlib`/dynamic/string-path reference.
- **VERIFIED — history preserved**: `git mv` → diff shows `rename …
  covalent_binder.py => claim_evidence_binding.py (100%)`.

## 3. Test / smoke

`ast.parse` clean on the renamed module + the 1 edited importer. Import smoke
resolves the 2 public functions. `PYTHONPATH='src;.' pytest`
`tests/unit/test_cross_section_reflector.py` +
`tests/polaris_graph/test_analyst_synthesis.py` +
`tests/polaris_graph/test_patch_b_cross_section_polish.py` → **44 passed**.
No test imports the module directly; no behaviour test applies — pure rename.

## 4. Scope + residuals

- Commit-1 diff is +2/-2 across 2 files — trivially under the 200-LOC cap.
- `docs/substrate_audit_2026-05-01.md` (dated audit snapshot) +
  `docs/pipeline_audit_context/08_env_var_inventory.md` (pipeline-audit-context
  inventory) are left intact as point-in-time audit-trail records, consistent
  with the #436-441 precedent.
- One of the #440-444 naming-audit series; siblings of #440/#441 (merged).

## 5. Risk assessment

Pure rename — no logic change. The token was grep-proven path-only (not
embedded in any identifier, unlike #440/#441), so a plain substring replace
over the single importer carried zero collision risk. The 44-test dependent
suite passes.

## 6. Verdict

Rename complete, faithful to the iter-1 APPROVE'd brief (clean) + Codex's
scope adjudication; offline suite green. Ready for Codex diff review.
