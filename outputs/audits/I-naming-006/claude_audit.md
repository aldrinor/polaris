# Claude architect audit — I-naming-006 (#440)

**Issue:** GH #440 — rename `synthesis/peptide_flow.py` →
`narrative_flow_analyzer.py` (naming-audit follow-up from #434;
chemistry-metaphor filename, §4.1 cryptic-name hygiene).
**Branch:** `bot/I-naming-006`
**Commit 1 (rename):** `ed7d46fe` — 3 files, +3/-3, 1 history-preserving rename.
**Brief:** `.codex/I-naming-006/brief.md` — Codex APPROVE iter 1 (0 P0/P1; 1
non-blocking P2 — PowerShell-vs-POSIX pytest syntax note; tests are run via
the Bash tool).

## 1. What shipped

| Change | Detail |
|---|---|
| `git mv` ×1 | `src/polaris_graph/synthesis/peptide_flow.py` → `narrative_flow_analyzer.py` (100% similarity). |
| Import-path | The dotted segment `synthesis.peptide_flow` → `synthesis.narrative_flow_analyzer` in the 2 `from` statements (`synthesizer.py:3089`, `cross_section_reflector.py:454`) + one module-name mention in a `synthesizer.py:2983` comment. |

**Targeted, not blind.** Unlike #438/#439, the token `peptide_flow` IS
embedded inside an identifier — the public function `analyze_peptide_flow`.
A blind `peptide_flow` substitution would corrupt it to
`analyze_narrative_flow_analyzer`. So the rename was applied as a targeted
replace of the literal `synthesis.peptide_flow` (the dotted module path,
which cannot match `analyze_peptide_flow`) plus the one bare-module-name
comment mention.

## 2. Per-finding verification

- **VERIFIED — no identifier corruption**: post-rename `grep -rc
  "analyze_peptide_flow"` → 3 in the renamed module (def + 2 docstring
  refs) + 2 in `synthesizer.py` (the `from … import` line + the call) —
  all intact, untouched. `grep "synthesis.peptide_flow"` /
  `"synthesis/peptide_flow"` → 0 residue.
- **VERIFIED — scope boundary (Codex-adjudicated APPROVE)**: the metaphor
  identifiers are deliberately left intact —
  `analyze_peptide_flow`/`apply_auto_fixes`/`format_peptide_findings_for_phase_r`
  (module public API) and `bond_analysis["peptide"]` — `"peptide"` is one of
  four parallel keys (`covalent`/`ionic`/`disulfide`/`peptide`) in the shared
  `bond_analysis` dict written by `synthesizer.py` and read by
  `cross_section_reflector.py`. Renaming the key alone would desync the dict;
  a whole-metaphor refactor across the 4 sibling files (#440-443) is a
  separate coherent issue. Codex's iter-1 brief review explicitly confirmed
  this scope.
- **VERIFIED — import closure**: `from
  src.polaris_graph.synthesis.narrative_flow_analyzer import
  analyze_peptide_flow, apply_auto_fixes, format_peptide_findings_for_phase_r`
  resolves. The 2 importers use a lazy `from … import` inside `try/except`;
  no `importlib`/dynamic/string-path reference to the module.
- **VERIFIED — history preserved**: `git mv` → diff shows `rename …
  peptide_flow.py => narrative_flow_analyzer.py (100%)`.

## 3. Test / smoke

`ast.parse` clean on the renamed module + the 2 edited importers. Import
smoke resolves all 3 public functions. `PYTHONPATH='src;.' pytest`
`tests/unit/test_cross_section_reflector.py` +
`tests/polaris_graph/test_analyst_synthesis.py` +
`tests/polaris_graph/test_patch_b_cross_section_polish.py` (the suites
exercising the 2 importers) → **44 passed**. No test imports the module
directly; no behaviour test applies — pure rename.

## 4. Scope + residuals

- Commit-1 diff is +3/-3 across 3 files — trivially under the 200-LOC cap.
- `docs/substrate_audit_2026-05-01.md:60` (a dated audit snapshot listing
  `peptide_flow` among "creative names but real code") and
  `docs/pipeline_audit_context/08_env_var_inventory.md:544-546` (a numbered
  pipeline-audit-context inventory) are deliberately left intact as
  point-in-time audit-trail records — consistent with the #436-439 precedent.
- One of the #440-444 naming-audit series; #441/#442/#443 rename the sibling
  chemistry-metaphor files (`disulfide_bridge`, `covalent_binder`,
  `ionic_rebalancer`).

## 5. Risk assessment

Pure rename — no logic change. The collision risk (`peptide_flow` embedded in
`analyze_peptide_flow`) was identified up front and avoided by a targeted
dotted-path replace rather than a blind substring substitution. The 44-test
dependent suite passes.

## 6. Verdict

Rename complete, faithful to the iter-1 APPROVE'd brief + Codex's scope
adjudication; offline suite green. Ready for Codex diff review.
