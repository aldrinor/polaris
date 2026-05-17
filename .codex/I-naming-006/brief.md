# Codex BRIEF review — I-naming-006 / GH #440: rename synthesis/peptide_flow.py → narrative_flow_analyzer.py

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
unmodified; the later diff review verifies the applied rename. Evaluate §2-§4
as a plan — especially the §3 scope-boundary call (this issue is NOT a clean
substring rename — see §3).

## 1. Issue

GH #440 (I-naming-006) — naming-audit follow-up from #434.
`src/polaris_graph/synthesis/peptide_flow.py` is a chemistry-metaphor name,
cryptic outside the original context. Rename the file `peptide_flow.py` →
`narrative_flow_analyzer.py` (the name Codex's #434 iter-1 plan-review
adjudicated). P2, mechanical. Branch `bot/I-naming-006` (a normal
`I-<prefix>-<NNN>` id — CI ISSUE_ID = `I-naming-006`, no re-cut).

## 2. The rename — file + import-PATH ONLY

### File rename (`git mv`, history-preserving)
- `src/polaris_graph/synthesis/peptide_flow.py` →
  `src/polaris_graph/synthesis/narrative_flow_analyzer.py`

### Import-path update — TARGETED, not a blind substring replace

**Critical difference from #437/#438/#439:** the token `peptide_flow` IS
embedded inside an identifier here — the public function `analyze_peptide_flow`
contains the substring `peptide_flow`. A blind `peptide_flow` →
`narrative_flow_analyzer` replace would corrupt `analyze_peptide_flow` into
`analyze_narrative_flow_analyzer`. So the rename is applied as a **targeted
replace of the dotted module-path segment `synthesis.peptide_flow` →
`synthesis.narrative_flow_analyzer`** (which cannot match
`analyze_peptide_flow`), plus one comment fix:

- `src/polaris_graph/agents/synthesizer.py:3089` — `from
  src.polaris_graph.synthesis.peptide_flow import (` →
  `...synthesis.narrative_flow_analyzer import (`.
- `src/polaris_graph/synthesis/cross_section_reflector.py:454` — same `from`
  statement.
- `src/polaris_graph/agents/synthesizer.py:2983` — a comment ("80+ min CPU
  burn in peptide_flow, covalent_binder, ionic_rebalancer, disulfide_bridge")
  — the bare module-name `peptide_flow` token → `narrative_flow_analyzer`
  (the other 3 module names stay — they are separate issues #441-443).

The renamed file's own 3 `peptide_flow` occurrences are ALL the function name
`analyze_peptide_flow` (def + 2 docstring cross-references) — under the §3
scope they are NOT touched, so the renamed file's content is unchanged.

## 3. Scope boundary — file + import-path ONLY (NOT the metaphor identifiers/schema)

This is the #437 precedent: the issue is P2 filename hygiene, but the
chemistry metaphor pervades the public API and a **cross-module data
structure**, so the metaphor identifiers are deliberately left intact:

- `analyze_peptide_flow` / `apply_auto_fixes` / `format_peptide_findings_for_phase_r`
  — public functions of the module; `peptide_result` / `peptide_auto_fix` —
  caller local names.
- **`bond_analysis["peptide"]`** — `"peptide"` is ONE OF FOUR parallel keys
  (`covalent` / `ionic` / `disulfide` / `peptide`) in the shared
  `bond_analysis` dict, written by `synthesizer.py` and read by
  `cross_section_reflector.py`. Renaming the `"peptide"` key alone would
  desync `bond_analysis`; renaming all four + the `bond_analysis` name is a
  coherent **whole-metaphor refactor**, not a per-file P2.
- The module docstring `MoST Peptide Bond: Narrative Flow Optimization` —
  `MoST <X> Bond` is the 4-file metaphor framing (peptide / disulfide /
  covalent / ionic bonds); leaving it keeps the 4-file system internally
  consistent until a deliberate whole-system rename.

**Question for Codex:** confirm #440 should be file + import-path only — the
`analyze_peptide_flow` API and the `"peptide"` `bond_analysis` key are
metaphor-system / shared-schema, not filename hygiene. (If you judge the
public function names *should* also move, that is a wider API change worth
its own issue; the `"peptide"` dict key genuinely cannot move without the
sibling files #441-443.)

### Doc references — EXCLUDED (both are point-in-time audit docs)

- `docs/substrate_audit_2026-05-01.md:60` — a **dated** (2026-05-01) audit
  snapshot; line 60 literally lists `peptide_flow` among "17 synthesis
  modules ... (creative names but real code)" — rewriting it would falsify
  the audit record.
- `docs/pipeline_audit_context/08_env_var_inventory.md:544-546` — a
  numbered pipeline-audit-context inventory with `path:line` references
  (`peptide_flow.py:329` etc.). Audit-context document set, not a maintained
  top-level architecture doc.

Both excluded as audit-trail records, consistent with the #436-439 precedent
(`outputs/audits/**`, `i_tests_001_triage.md`). **Codex: confirm** — or, if
you judge `08_env_var_inventory.md` is a live inventory that must track the
path, say so and the 3 path strings will be folded in.

## 4. Files I have ALSO checked and they're clean

- `grep -rn "peptide_flow"` whole repo: the only `.py` hits are the module
  itself + the 2 importers (`synthesizer.py`, `cross_section_reflector.py`);
  no test imports it; `outputs/` / `.codex/` / `archive/` / `__pycache__`
  mentions are historical/build artifacts.
- No `importlib` / dynamic-import / string-path reference to the module.
- The 2 importers use a lazy `from ... import` inside a `try/except` block —
  the import path is the only thing the file rename forces to change.
- Target name `narrative_flow_analyzer` — `grep` → zero pre-existing hits,
  clean.

## 5. Test / smoke (planned)

`git mv` preserves history. After: `ast.parse` the renamed file + the 2
edited importers; `python -c "from src.polaris_graph.synthesis.narrative_flow_analyzer
import analyze_peptide_flow, apply_auto_fixes, format_peptide_findings_for_phase_r"`
import smoke; `PYTHONPATH='src;.' python -m pytest tests/unit/test_cross_section_reflector.py
tests/polaris_graph/test_analyst_synthesis.py` (the suites exercising the 2
importers). No test imports the module directly. No behaviour test applies —
pure rename. Any pre-existing failure verified identical on clean `polaris`
HEAD via `git stash` before commit.

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
