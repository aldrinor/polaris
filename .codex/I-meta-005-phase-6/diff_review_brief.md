REVIEW DISCIPLINE: FOCUSED DIFF REVIEW of `.codex/I-meta-005-phase-6/codex_diff.patch`
(458 lines, 4 files) vs the APPROVED brief + design rulings. Do NOT run a repo-wide
audit. Open the 4 changed files + the brief/build_spec. This is iter 1 of 5.

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## What this diff is (your prior rulings: A1 + B-impl-1 / shape-1)
Phase 6 (#990): domain-general section prompts + verified synthesis, behind
`PG_USE_RESEARCH_PLANNER` (default OFF, byte-identical).
- **Part A (A1):** planner emits `answer_type` (ANSWER_TYPES enum, default "general",
  fail-soft, SHA-pinned); registry `by_answer_type` maps clinical→clinical.yaml; the
  selector consults answer_type FIRST; `advisory_text` is resolved once in
  generate_multi_section_report and threaded to every `_call_section` so clinical
  writing guidance is appended ONLY for a clinical frame.
- **Part B (B-impl-1 / shape-1):** `Integrative` archetype + planner-prompt mandate
  for one Integrative outline section with broad cross-cutting evidence; it is a
  NORMAL planned section (strict_verified like any section); the unverified
  analyst_synthesis block is DEMOTED on-mode (gate += `research_plan is None`) so it
  never counts toward verified_text/verified_words.

## Files (4)
- `src/polaris_graph/generator/multi_section_generator.py` (advisory threading +
  Integrative archetype + analyst demotion gate).
- `src/polaris_graph/planning/research_planner.py` (answer_type field/parse/canonical +
  planner prompt: answer_type + Integrative mandate).
- `config/section_prompts/_registry.yaml` (by_answer_type: clinical).
- `tests/.../test_domain_general_sections_phase6.py` (10 cases).

## CRITICAL — verify (each a HARD constraint)
1. **Verification-integrity (clinical-lethal):** the Integrative section MUST be
   strict_verified like every section — NO path lets an Integrative-archetype section
   bypass `_rewrite_draft_with_spans`/strict_verify, and NO ungrounded synthesis
   sentence reaches verified_text/verified_words. Confirm Integrative is not
   special-cased.
2. **Analyst demotion:** on-mode the analyst block is TRULY skipped (gate
   `not partial_mode and research_plan is None and section_results and global_biblio`
   — check boolean precedence) so `analyst_synth_words=0`, NOT added to total_words →
   `verified_words = total_words - analyst_synthesis_words` (run_honest_sweep_r3.py)
   = sum of strict_verified section words. OFF-mode runs the legacy analyst block
   byte-identically.
3. **OFF byte-identity:** `advisory_text=""` OFF (guard `research_plan is not None and
   _p6_frame is not None`); the Integrative archetype + planner mandate live ONLY on
   the planner (on-mode) path, never the OFF legacy `_call_outline`/`_ALLOWED_SECTIONS`.
4. **Clinical-only advisory:** clinical guidance appends ONLY for answer_type=clinical
   (the registry by_answer_type), NOT for a non-clinical empirical frame.
5. **No clinical literal** as an on-path control value (registry/param driven).

## OPEN ITEMS (rule on these)
1. V30 contract sections (render_slot_prose) do NOT receive advisory_text — out of
   scope for Phase 6 (field-agnostic section path)? Acceptable?
2. The Integrative section is planner-PROMPT-mandated (LLM-emitted like all outline
   sections), not deterministically appended. Acceptable, or require a deterministic
   guarantee?
3. answer_type in to_canonical_dict → on-mode plan_sha changes; Phase-1 SHA tests are
   self-consistency (not a literal) → pass. Acceptable?

## Smoke / review evidence
- test_domain_general_sections_phase6.py: 10 passed.
- Regression: 229 (generator/planning/md9/discovery/saturation/adequacy) passed.
- Claude adversarial multi-lens review (5 lenses, 40 findings, per-finding verified):
  0 real defects (1 confirmed finding was a positive OFF-guard confirmation).

## Output schema (REQUIRED)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
