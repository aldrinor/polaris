# Codex DIFF review — I-naming-007 / GH #441: rename synthesis/disulfide_bridge.py → cross_section_source_consistency.py

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 1. What you are reviewing

The commit-1 diff for #441 — `git diff origin/polaris...HEAD` excluding
`.codex/I-naming-007/` and `outputs/audits/I-naming-007/` (the canonical diff
in `.codex/I-naming-007/codex_diff.patch`, sha256 trailer). It implements the
Codex-APPROVE'd brief `.codex/I-naming-007/brief.md` (brief APPROVE iter 1,
clean — the scope boundary was confirmed). Pure rename — 3 files, +3/-3, 1
history-preserving `git mv`. Direct sibling of #440 (merged PR #577).

## 2. The diff

- `git mv` `synthesis/disulfide_bridge.py` →
  `cross_section_source_consistency.py` (100%).
- `synthesizer.py` — `from …synthesis.disulfide_bridge import` →
  `…synthesis.cross_section_source_consistency import`, and a comment mention
  `disulfide_bridge` → `cross_section_source_consistency`.
- `cross_section_reflector.py` — same `from` statement.

## 3. Verify against the brief

1. **No identifier corruption** — the targeted replace touched only the
   dotted path `synthesis.disulfide_bridge`; the function name
   `analyze_disulfide_bridges` (which contains the substring) is UNCHANGED —
   confirm `grep -rc "analyze_disulfide_bridges"` shows it intact in both the
   renamed module and `synthesizer.py`.
2. Zero `synthesis.disulfide_bridge` / `synthesis/disulfide_bridge` residue.
3. The metaphor identifiers + `bond_analysis["disulfide"]` key are UNCHANGED
   (file+import-path scope — confirmed correct in your brief review).
4. `git mv` preserved history (diff shows `rename … (100%)`).
5. `import …synthesis.cross_section_source_consistency` resolves the 2
   public fns.
6. No behaviour change — pure rename.

## 4. Files I have ALSO checked and they're clean

- `grep -rn "disulfide_bridge"` whole repo: the only `.py` hits left are the
  function name `analyze_disulfide_bridges` (in scope to KEEP) + the renamed
  module + `synthesizer.py`'s import/call. No test imports the module.
- `docs/substrate_audit_2026-05-01.md` (dated audit snapshot) +
  `docs/pipeline_audit_context/08_env_var_inventory.md` (pipeline-audit-context
  inventory) — left intact as point-in-time audit-trail records, per the
  #436-440 precedent.
- No `importlib` / dynamic-import / string-path reference to the module.

## 5. Test state

`ast.parse` 3/3 clean. Import smoke resolves the 2 public functions.
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
