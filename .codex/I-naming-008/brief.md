# Codex BRIEF review — I-naming-008 / GH #442: rename synthesis/covalent_binder.py → claim_evidence_binding.py

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
as a plan — especially the §3 scope-boundary call.

## 1. Issue

GH #442 (I-naming-008) — naming-audit follow-up from #434.
`src/polaris_graph/synthesis/covalent_binder.py` is a chemistry-metaphor
name, cryptic outside the original context. Rename the file
`covalent_binder.py` → `claim_evidence_binding.py` (the name Codex's #434
iter-1 plan-review adjudicated — it matches the module's own docstring
subtitle "Claim-Evidence Binding Verification"). P2, mechanical. Branch
`bot/I-naming-008` (a normal `I-<prefix>-<NNN>` id — CI ISSUE_ID =
`I-naming-008`, no re-cut).

Sibling of #440/#441 (`peptide_flow.py`, `disulfide_bridge.py` — both merged).

## 2. The rename — file + import-path token

### File rename (`git mv`, history-preserving)
- `src/polaris_graph/synthesis/covalent_binder.py` →
  `src/polaris_graph/synthesis/claim_evidence_binding.py`

### Import-path token: `covalent_binder` → `claim_evidence_binding`

**Verified path-only.** Unlike #440/#441, the token `covalent_binder` is NOT
embedded in any identifier — the public function is `analyze_covalent_bonds`
(`covalent_bonds`, a different token). `grep -rnE "covalent_binder"` in
`src/`+`tests/`+`scripts/` shows the token occurs in exactly ONE importer,
`synthesizer.py`, at 2 sites:
- `synthesizer.py:3016` — `from src.polaris_graph.synthesis.covalent_binder
  import (analyze_covalent_bonds, apply_auto_fixes as covalent_auto_fix)` →
  `…synthesis.claim_evidence_binding import …`.
- `synthesizer.py:2984` — a comment ("… covalent_binder, ionic_rebalancer,
  cross_section_source_consistency (all vecs @ vecs.T).") — the bare
  module-name `covalent_binder` token → `claim_evidence_binding` (the
  `ionic_rebalancer` name stays — separate issue #443;
  `cross_section_source_consistency` is already the post-#441 name).

The renamed file's own content has ZERO `covalent_binder` token occurrences
(its docstring/identifiers use "Covalent Bond" prose / `analyze_covalent_bonds`
— neither is the `covalent_binder` token), so the file content is unchanged.
`cross_section_reflector.py` does NOT import this module (it only reads the
`bond_analysis["covalent"]` key) — no second importer.

## 3. Scope boundary — file + import-path ONLY (NOT the metaphor identifiers/schema)

The #437/#440/#441 precedent — the chemistry metaphor pervades the API and a
cross-module data structure, left intact:

- `analyze_covalent_bonds` / `apply_auto_fixes` — public functions;
  `covalent_result` / `covalent_auto_fix` — caller local names.
- **`bond_analysis["covalent"]`** — `"covalent"` is ONE OF FOUR parallel keys
  (`covalent` / `ionic` / `disulfide` / `peptide`) in the shared
  `bond_analysis` dict written by `synthesizer.py` and read by
  `cross_section_reflector.py`. Renaming the key alone desyncs the dict; the
  whole-metaphor refactor is a separate coherent issue.
- The module docstring `MoST Covalent Bond: Claim-Evidence Binding
  Verification` — `MoST <X> Bond` is the 4-file metaphor framing; left intact.

**Question for Codex:** confirm #442 should be file + import-path only — the
`analyze_covalent_bonds` API and the `"covalent"` `bond_analysis` key are
metaphor-system / shared-schema, not filename hygiene. (Codex APPROVE'd this
exact scope on #440 and #441.)

### Doc references — EXCLUDED (both point-in-time audit docs)

- `docs/substrate_audit_2026-05-01.md` — a dated (2026-05-01) audit snapshot
  listing `covalent_binder` among "creative names but real code".
- `docs/pipeline_audit_context/08_env_var_inventory.md` — a numbered
  pipeline-audit-context inventory.

Both excluded as audit-trail records, consistent with the #436-441 precedent.

## 4. Files I have ALSO checked and they're clean

- `grep -rn "covalent_binder"` whole repo: the only `.py` hits are the
  module itself (0 self-refs) + the single importer `synthesizer.py` (2
  sites); no test imports it; `outputs/` / `.codex/` / `archive/` /
  `__pycache__` mentions are historical/build artifacts.
- No `importlib` / dynamic-import / string-path reference to the module.
- The importer uses a lazy `from … import` inside a `try/except` block.
- Target name `claim_evidence_binding` — `grep` → zero pre-existing hits.

## 5. Test / smoke (planned)

`git mv` preserves history. After: `ast.parse` the renamed file + the 1
edited importer; `python -c "from src.polaris_graph.synthesis.claim_evidence_binding
import analyze_covalent_bonds, apply_auto_fixes"` import smoke;
`PYTHONPATH='src;.' python -m pytest tests/unit/test_cross_section_reflector.py
tests/polaris_graph/test_analyst_synthesis.py tests/polaris_graph/test_patch_b_cross_section_polish.py`
(the suites exercising the synthesizer). No test imports the module directly.
No behaviour test applies — pure rename. Any pre-existing failure verified
identical on clean `polaris` HEAD via `git stash` before commit.

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
