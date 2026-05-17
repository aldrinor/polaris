# Codex BRIEF review — I-naming-009 / GH #443: rename synthesis/ionic_rebalancer.py → evidence_section_affinity.py

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

GH #443 (I-naming-009) — naming-audit follow-up from #434.
`src/polaris_graph/synthesis/ionic_rebalancer.py` is a chemistry-metaphor
name, cryptic outside the original context. Rename the file
`ionic_rebalancer.py` → `evidence_section_affinity.py` (the name Codex's #434
iter-1 plan-review adjudicated — it matches the module's own docstring
subtitle "Evidence-Section Affinity Rebalancing"). P2, mechanical. Branch
`bot/I-naming-009` (a normal `I-<prefix>-<NNN>` id — CI ISSUE_ID =
`I-naming-009`, no re-cut).

Last of the four chemistry-metaphor synthesis files (#440/#441/#442 merged).

## 2. The rename — file + import-path token

### File rename (`git mv`, history-preserving)
- `src/polaris_graph/synthesis/ionic_rebalancer.py` →
  `src/polaris_graph/synthesis/evidence_section_affinity.py`

### Import-path token: `ionic_rebalancer` → `evidence_section_affinity`

**Verified path-only.** Like #442 (and unlike #440/#441), the token
`ionic_rebalancer` is NOT embedded in any identifier — the public functions
are `analyze_ionic_bonds` / `format_ionic_findings_for_phase_r`
(`ionic_bonds` / `ionic_findings`, different tokens). `grep -rnE
"ionic_rebalancer"` in `src/`+`tests/`+`scripts/` shows the token at 4 sites
across 2 importers, all module-path:
- `synthesizer.py:3034` — `from src.polaris_graph.synthesis.ionic_rebalancer
  import analyze_ionic_bonds` → `…synthesis.evidence_section_affinity import …`.
- `synthesizer.py:3042` — a second `from
  src.polaris_graph.synthesis.ionic_rebalancer import (` → same.
- `cross_section_reflector.py:428` — `from
  src.polaris_graph.synthesis.ionic_rebalancer import (` → same.
- `synthesizer.py:2984` — a comment ("… claim_evidence_binding,
  ionic_rebalancer, cross_section_source_consistency (all vecs @ vecs.T).")
  — the bare module-name `ionic_rebalancer` token → `evidence_section_affinity`
  (the sibling names `claim_evidence_binding` / `cross_section_source_consistency`
  are already the post-#441/#442 renamed names; they stay).

The renamed file's own content has ZERO `ionic_rebalancer` token occurrences,
so the file content is unchanged. Because the token is path-only, a plain
substring replace `ionic_rebalancer` → `evidence_section_affinity` over the
2 importers is exact and cannot touch any identifier.

## 3. Scope boundary — file + import-path ONLY (NOT the metaphor identifiers/schema)

The #437/#440/#441/#442 precedent — the chemistry metaphor pervades the API
and a cross-module data structure, left intact:

- `analyze_ionic_bonds` / `format_ionic_findings_for_phase_r` — public
  functions; `ionic_result` — caller local name.
- **`bond_analysis["ionic"]`** — `"ionic"` is ONE OF FOUR parallel keys
  (`covalent` / `ionic` / `disulfide` / `peptide`) in the shared
  `bond_analysis` dict written by `synthesizer.py` and read by
  `cross_section_reflector.py`. Renaming the key alone desyncs the dict; the
  whole-metaphor refactor is a separate coherent issue.
- The module docstring `MoST Ionic Bond: Evidence-Section Affinity
  Rebalancing` — `MoST <X> Bond` is the 4-file metaphor framing; left intact.

**Question for Codex:** confirm #443 should be file + import-path only — the
`analyze_ionic_bonds` API and the `"ionic"` `bond_analysis` key are
metaphor-system / shared-schema, not filename hygiene. (Codex APPROVE'd this
exact scope on #440, #441, and #442.)

### Doc references — EXCLUDED (both point-in-time audit docs)

- `docs/substrate_audit_2026-05-01.md` — a dated (2026-05-01) audit snapshot
  listing `ionic_rebalancer` among "creative names but real code".
- `docs/pipeline_audit_context/08_env_var_inventory.md` — a numbered
  pipeline-audit-context inventory.

Both excluded as audit-trail records, consistent with the #436-442 precedent.

## 4. Files I have ALSO checked and they're clean

- `grep -rn "ionic_rebalancer"` whole repo: the only `.py` hits are the
  module itself (0 self-refs) + the 2 importers (`synthesizer.py` ×3,
  `cross_section_reflector.py` ×1); no test imports it; `outputs/` /
  `.codex/` / `archive/` / `__pycache__` mentions are historical/build
  artifacts.
- No `importlib` / dynamic-import / string-path reference to the module.
- Both importers use a lazy `from … import` inside `try/except` blocks.
- Target name `evidence_section_affinity` — `grep` → zero pre-existing hits.

## 5. Test / smoke (planned)

`git mv` preserves history. After: `ast.parse` the renamed file + the 2
edited importers; `python -c "from src.polaris_graph.synthesis.evidence_section_affinity
import analyze_ionic_bonds, format_ionic_findings_for_phase_r"` import smoke;
`PYTHONPATH='src;.' python -m pytest tests/unit/test_cross_section_reflector.py
tests/polaris_graph/test_analyst_synthesis.py tests/polaris_graph/test_patch_b_cross_section_polish.py`
(the suites exercising the 2 importers). No test imports the module directly.
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
