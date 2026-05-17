# Codex DIFF review — I-naming-006 / GH #440: rename synthesis/peptide_flow.py → narrative_flow_analyzer.py

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 1. What you are reviewing

The commit-1 diff for #440 — `git diff origin/polaris...HEAD` excluding
`.codex/I-naming-006/` and `outputs/audits/I-naming-006/` (the canonical diff
in `.codex/I-naming-006/codex_diff.patch`, sha256 trailer). It implements the
Codex-APPROVE'd brief `.codex/I-naming-006/brief.md` (brief APPROVE iter 1 —
the iter-1 review confirmed the file+import-path scope boundary).
Pure rename — 3 files, +3/-3, 1 history-preserving `git mv`.

## 2. The diff

- `git mv` `src/polaris_graph/synthesis/peptide_flow.py` →
  `narrative_flow_analyzer.py` (100%).
- `synthesizer.py` — `from …synthesis.peptide_flow import` →
  `…synthesis.narrative_flow_analyzer import`, and a comment mention
  `peptide_flow` → `narrative_flow_analyzer`.
- `cross_section_reflector.py` — same `from` statement.

## 3. Verify against the brief

1. **No identifier corruption** — the targeted replace touched only the
   dotted path `synthesis.peptide_flow`; the function name
   `analyze_peptide_flow` (which contains the substring `peptide_flow`) is
   UNCHANGED — confirm `grep -rc "analyze_peptide_flow"` shows it intact in
   both the renamed module and `synthesizer.py`.
2. Zero `synthesis.peptide_flow` / `synthesis/peptide_flow` residue.
3. The metaphor identifiers + `bond_analysis["peptide"]` key are UNCHANGED
   (file+import-path scope — confirmed correct in your brief review).
4. `git mv` preserved history (diff shows `rename … (100%)`).
5. `import …synthesis.narrative_flow_analyzer` resolves the 3 public fns.
6. No behaviour change — pure rename.

## 4. Files I have ALSO checked and they're clean

- `grep -rn "peptide_flow"` whole repo: the only `.py` hits left are the
  function name `analyze_peptide_flow` (in scope to KEEP) + the renamed
  module + `synthesizer.py`'s import/call of it. No test imports the module.
- `docs/substrate_audit_2026-05-01.md:60` (dated audit snapshot) +
  `docs/pipeline_audit_context/08_env_var_inventory.md:544-546` (numbered
  pipeline-audit-context inventory) — left intact as point-in-time
  audit-trail records, per the #436-439 precedent.
- No `importlib` / dynamic-import / string-path reference to the module.

## 5. Test state

`ast.parse` 3/3 clean. Import smoke resolves all 3 public functions.
`PYTHONPATH='src;.' pytest tests/unit/test_cross_section_reflector.py
tests/polaris_graph/test_analyst_synthesis.py
tests/polaris_graph/test_patch_b_cross_section_polish.py` → 44 passed.

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
