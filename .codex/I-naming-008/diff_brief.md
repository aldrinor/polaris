# Codex DIFF review — I-naming-008 / GH #442: rename synthesis/covalent_binder.py → claim_evidence_binding.py

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 1. What you are reviewing

The commit-1 diff for #442 — `git diff origin/polaris...HEAD` excluding
`.codex/I-naming-008/` and `outputs/audits/I-naming-008/` (the canonical diff
in `.codex/I-naming-008/codex_diff.patch`, sha256 trailer). It implements the
Codex-APPROVE'd brief `.codex/I-naming-008/brief.md` (brief APPROVE iter 1,
clean). Pure rename — 2 files, +2/-2, 1 history-preserving `git mv`. Sibling
of #440/#441 (merged).

## 2. The diff

- `git mv` `synthesis/covalent_binder.py` → `claim_evidence_binding.py` (100%).
- `synthesizer.py` — `from …synthesis.covalent_binder import` →
  `…synthesis.claim_evidence_binding import`, and a comment mention
  `covalent_binder` → `claim_evidence_binding`.

## 3. Verify against the brief

1. Zero `covalent_binder` residue in `src/` + `tests/` + `scripts/`.
2. `covalent_binder` is path-only — the public function
   `analyze_covalent_bonds` (a different token) is UNCHANGED; confirm
   `grep -rc "analyze_covalent_bonds"` shows it intact.
3. The metaphor identifiers + `bond_analysis["covalent"]` key are UNCHANGED
   (file+import-path scope — confirmed correct in your brief review).
4. `git mv` preserved history (diff shows `rename … (100%)`).
5. `import …synthesis.claim_evidence_binding` resolves the 2 public fns.
6. No behaviour change — pure rename.

## 4. Files I have ALSO checked and they're clean

- `grep -rn "covalent_binder"` whole repo: the only `.py` hits were the
  module + `synthesizer.py`'s import/comment — all updated. `synthesizer.py`
  is the SOLE importer (`cross_section_reflector.py` reads only the
  `bond_analysis["covalent"]` key — no import). No test imports the module.
- `docs/substrate_audit_2026-05-01.md` (dated audit snapshot) +
  `docs/pipeline_audit_context/08_env_var_inventory.md` (pipeline-audit-context
  inventory) — left intact as point-in-time audit-trail records, per the
  #436-441 precedent.
- No `importlib` / dynamic-import / string-path reference to the module.

## 5. Test state

`ast.parse` 2/2 clean. Import smoke resolves the 2 public functions.
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
