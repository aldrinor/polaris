# Phase 6 BUILD SPEC — domain-general section prompts + verified synthesis (#990). BINDING.

APPROVED brief `.codex/I-meta-005-phase-6/brief.md` (Codex APPROVE iter 1) is the
design contract. Codex ruled **B2** on the part-B question + 3 non-blocking P2s,
folded in below.

## CODEX DESIGN RULINGS (2026-06-01, `design_consult_verdict.txt`) — BINDING
- **decision_a: A1** — add an additive `answer_type` field to `ResearchFrame`
  (planner-extracted, default `"general"`), include it in `to_canonical_dict()`,
  RECONCILE the canonical-JSON / `plan_sha` snapshots (one-time mechanical), and map
  `answer_type: clinical` → `clinical.yaml` in the registry. NOT fragile heuristics.
- **decision_b: B-impl-1** — build integrative synthesis as a NORMAL planned section
  that emits `[ev_XXX]` tokens and passes `strict_verify`; do NOT retrofit
  `analyst_synthesis`. Demote the unverified analyst block (non-verified appendix or
  drop on-mode); it must NEVER count toward `verified_text`/`verified_words` unless it
  passed the same strict-verify path.
- **HARD:** OFF byte-identity; gate all new behaviour to Phase-6 on-mode + handle
  partial-mode intentionally; update plan_sha snapshots; default `answer_type`
  `"general"`; unverified prose stays out of the verified counts.

## Part A — clinical advisory loads ONLY for a clinical frame
- Extend `select_advisory_prompt_text` (multi_section_generator) to resolve via an
  entity-category signal from the frame, config-driven via `_registry.yaml`. NO
  `if domain == "clinical"` literal on-path.
- **P2-1 (tighten trigger):** the mapped entity categories MUST be CLINICALLY
  DISTINCTIVE, not generic `intervention`/`population`/`outcome` (those appear in
  policy/econ frames too). Trigger on a uniquely-clinical combination, e.g. the
  frame's `evidence_needs` including `regulatory` (FDA/EMA labels) AND/OR
  `primary_literature` with clinical-trial entity categories (drug/intervention +
  trial/registration + endpoint) — pick a signal that a policy/GDP frame does NOT
  satisfy. Encode the trigger in config (the registry), not as a Python literal.
- OFF byte-identical (legacy `SECTION_SYSTEM_PROMPT_TEMPLATE` unchanged off-path).

## Part B — verified integrative synthesis (Codex ruling B2)
- Add an INTEGRATIVE/SYNTHESIS section to the planned outline as an archetype, fed
  with evidence and VERIFIED through the SAME `strict_verify` as every other section
  (carries `[ev_XXX]` provenance; ungrounded sentences dropped). Its words count as
  `verified_words`, grounded-by-construction.
- RETIRE or shrink the separate unverified `analyst_synthesis_text` block on-mode:
  keep it ONLY as a clearly-labelled NON-verified appendix (or drop it on-mode). It
  must NEVER be counted as verified.
- **P2-2 (partial-mode):** the integrative section is an outline section, so in
  `partial_mode` (partial_saturation) it MUST respect the Phase-4 pruned-plan +
  appender-disable invariant — i.e. it is NOT an out-of-plan appender that bypasses
  pruning. Add an explicit partial_saturation smoke proving the integrative section
  is pruned/disabled like any planned section, not force-appended.
- OFF byte-identical: off-mode keeps the legacy analyst-synthesis behaviour.

## Files
- `config/section_prompts/_registry.yaml` (+ the entity-category trigger encoding).
- `src/polaris_graph/generator/multi_section_generator.py` (selector extension +
  the B2 verified integrative section; analyst block demoted on-mode).
- `scripts/run_honest_sweep_r3.py` (pass the frame entity signal; manifest
  verified/analyst split adjusted for B2).

## SMOKE — `tests/polaris_graph/generator/test_domain_general_sections_phase6.py`
- P6-1 OFF byte-identity (legacy template + analyst block unchanged).
- P6-2 clinical frame → clinical advisory appended.
- P6-3 non-clinical empirical frame (GDP/policy/battery) → NO clinical advisory.
- P6-4 B2: integrative prose counts as verified ONLY after strict_verify (an
  ungrounded synthesis sentence is NOT in verified_text / verified_words).
- P6-5 (P2-2) partial_saturation: the integrative section respects pruning /
  appender-disable (not force-appended out-of-plan).
- P6-6 (P2-3): the no-clinical-literal assertion targets ON-PATH CODE / control
  flow, NOT config filenames or advisory family names (clinical.yaml in config is
  expected and allowed).
Then a generator regression subset for OFF byte-identity.
