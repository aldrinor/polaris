# Codex BRIEF review — I-naming-007 / GH #441: rename synthesis/disulfide_bridge.py → cross_section_source_consistency.py

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

GH #441 (I-naming-007) — naming-audit follow-up from #434.
`src/polaris_graph/synthesis/disulfide_bridge.py` is a chemistry-metaphor
name, cryptic outside the original context. Rename the file
`disulfide_bridge.py` → `cross_section_source_consistency.py` (the name
Codex's #434 iter-1 plan-review adjudicated — it matches the module's own
docstring subtitle "Cross-Section Source Consistency"). P2, mechanical.
Branch `bot/I-naming-007` (a normal `I-<prefix>-<NNN>` id — CI ISSUE_ID =
`I-naming-007`, no re-cut).

This is a direct sibling of #440 (`peptide_flow.py` →
`narrative_flow_analyzer.py`, just merged PR #577) — identical shape.

## 2. The rename — file + import-PATH ONLY

### File rename (`git mv`, history-preserving)
- `src/polaris_graph/synthesis/disulfide_bridge.py` →
  `src/polaris_graph/synthesis/cross_section_source_consistency.py`

### Import-path update — TARGETED, not a blind substring replace

Like #440, the token `disulfide_bridge` IS embedded inside an identifier —
the public function `analyze_disulfide_bridges` contains the substring
`disulfide_bridge`. A blind replace would corrupt it. So the rename is
applied as a **targeted replace of the dotted module-path segment
`synthesis.disulfide_bridge` → `synthesis.cross_section_source_consistency`**
(which cannot match `analyze_disulfide_bridges`), plus one comment fix:

- `src/polaris_graph/agents/synthesizer.py:3062` — `from
  src.polaris_graph.synthesis.disulfide_bridge import analyze_disulfide_bridges`
  → `…synthesis.cross_section_source_consistency import …`.
- `src/polaris_graph/synthesis/cross_section_reflector.py:441` — same `from`
  statement.
- `src/polaris_graph/agents/synthesizer.py:2984` — a comment ("…
  covalent_binder, ionic_rebalancer, disulfide_bridge (all vecs @ vecs.T).")
  — the bare module-name `disulfide_bridge` token → `cross_section_source_consistency`
  (the other 2 module names `covalent_binder`/`ionic_rebalancer` stay — they
  are separate issues #442/#443).

The renamed file's own 2 `disulfide_bridge` occurrences are both the function
name `analyze_disulfide_bridges` (def line 28 + 1 docstring cross-reference)
— under the §3 scope they are NOT touched.

## 3. Scope boundary — file + import-path ONLY (NOT the metaphor identifiers/schema)

The #437/#440 precedent — the chemistry metaphor pervades the API and a
cross-module data structure, so the metaphor identifiers are left intact:

- `analyze_disulfide_bridges` / `format_disulfide_findings_for_phase_r` —
  public functions; `disulfide_result` — caller local name.
- **`bond_analysis["disulfide"]`** — `"disulfide"` is ONE OF FOUR parallel
  keys (`covalent` / `ionic` / `disulfide` / `peptide`) in the shared
  `bond_analysis` dict written by `synthesizer.py` and read by
  `cross_section_reflector.py`. Renaming the key alone desyncs the dict; the
  whole-metaphor refactor (all four keys + `bond_analysis`) is a separate
  coherent issue, not a per-file P2.
- The module docstring `MoST Disulfide Bond: Cross-Section Source Consistency`
  — `MoST <X> Bond` is the 4-file metaphor framing; left intact.

**Question for Codex:** confirm #441 should be file + import-path only — the
`analyze_disulfide_bridges` API and the `"disulfide"` `bond_analysis` key are
metaphor-system / shared-schema, not filename hygiene. (Codex APPROVE'd this
exact scope on the sibling #440.)

### Doc references — EXCLUDED (both are point-in-time audit docs)

- `docs/substrate_audit_2026-05-01.md` — a dated (2026-05-01) audit snapshot
  that literally lists `disulfide_bridge` among "creative names but real
  code"; rewriting it would falsify the audit record.
- `docs/pipeline_audit_context/08_env_var_inventory.md` — a numbered
  pipeline-audit-context inventory.

Both excluded as audit-trail records, consistent with the #436-440 precedent.

## 4. Files I have ALSO checked and they're clean

- `grep -rn "disulfide_bridge"` whole repo: the only `.py` hits are the
  module itself + the 2 importers (`synthesizer.py`, `cross_section_reflector.py`);
  no test imports it; `outputs/` / `.codex/` / `archive/` / `__pycache__`
  mentions are historical/build artifacts.
- No `importlib` / dynamic-import / string-path reference to the module.
- The 2 importers use a lazy `from … import` inside a `try/except` block.
- Target name `cross_section_source_consistency` — `grep` → zero
  pre-existing hits, clean.

## 5. Test / smoke (planned)

`git mv` preserves history. After: `ast.parse` the renamed file + the 2
edited importers; `python -c "from src.polaris_graph.synthesis.cross_section_source_consistency
import analyze_disulfide_bridges, format_disulfide_findings_for_phase_r"`
import smoke; `PYTHONPATH='src;.' python -m pytest tests/unit/test_cross_section_reflector.py
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
