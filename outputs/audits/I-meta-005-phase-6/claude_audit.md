# Claude architect audit — I-meta-005 Phase 6 (#990) domain-general sections + verified synthesis

**Verdict: APPROVE.** Build matches the Codex-APPROVED brief + design rulings A1
(planner `answer_type` → registry-driven advisory; clinical guidance loads ONLY for a
clinical frame) and B-impl-1 / shape-1 (Integrative = a NORMAL planned outline section,
strict_verified like any section; unverified analyst block demoted on-mode). 10 Phase-6
smoke + 229 regression green; OFF byte-identical.

## Build (committed e112a547, fd579988)
- **Part A**: `advisory_text` resolved once in `generate_multi_section_report`
  (`select_advisory_prompt_text(frame.claim_type, frame.answer_type)`, ON-mode only,
  "" OFF), threaded through `_run_section` → `_call_section` (first-pass + regen);
  closure-captured so M-44/M-47 regen inherit it. `answer_type` field + parse
  (fail-soft "general") + canonical pin + planner prompt + registry `by_answer_type`.
- **Part B**: `Integrative` archetype; planner prompt mandates one Integrative
  outline section LAST with broad cross-cutting evidence; it flows through the normal
  `_run_section` → strict_verify path (verified by construction); analyst block
  demoted on-mode (gate `+= research_plan is None`).

## Adversarial multi-lens review (5 lenses → 40 findings → per-finding verify)
A 45-agent workflow attacked the diff across OFF-byte-identity, verification-integrity,
advisory-threading, partial-mode/manifest, and planner/SHA, then adversarially
verified each finding against the code. **Result: 1 confirmed finding, and it is a
positive CONFIRMATION (P3, non-defect)** that the OFF-mode advisory guard
(`multi_section_generator.py:4143-4151`) is sound — `advisory_text` is `""` OFF
(double-guarded: the `research_plan is not None` predicate short-circuits before the
`getattr` on a None frame, AND the consume site `if use_field_agnostic_prompt and
advisory_text:` is doubly gated). 39 of 40 findings were refuted with code evidence.
(16 verify-agents hit Workflow-engine flakiness and returned no structured verdict;
those findings dropped unverified — so the Codex diff-gate is the authoritative
backstop, which is consistent with the standing cage: Codex is the only gate.)

## Axes (CLEAN)
- **off_byte_identity_ok** — every change inert when `research_plan is None`: advisory
  "" OFF; analyst block runs legacy OFF (gate ANDs `research_plan is None`); Integrative
  archetype + planner mandate only on the planner (on-mode) path, never the legacy
  `_call_outline`/`_ALLOWED_SECTIONS`. 229 regression green (OFF paths).
- **verification_integrity_ok** — Integrative is a normal section → strict_verify drops
  ungrounded sentences (no special-casing; `test_p6_4_integrative_not_special_cased`).
  Analyst demoted on-mode → `analyst_synth_words=0`, not added to `total_words` →
  `verified_words = total_words` = sum of strict_verified section words (incl. Integrative).
- **no_clinical_literal_ok** — advisory selection is registry/param driven; no
  `== "clinical"` / `domain == "clinical"` control literal on-path (`test_p6_6`).
- **money_ok** — pure config/parse; zero spend (advisory is a config lookup; the
  Integrative section's LLM call is the generator's existing per-section billing, not new).

## Notes for the diff-gate
1. V30 contract sections (rendered via `render_slot_prose`, not `_run_section`) do NOT
   receive the advisory_text — out of scope (advisory is for the field-agnostic section
   path; contract sections have their own rendering). Confirm acceptable.
2. The Integrative section is mandated by the planner PROMPT (LLM-emitted, like all
   outline sections), not deterministically appended — consistent with how the whole
   outline is LLM-emitted. If the LLM omits it a given run, the report lacks it (no
   correctness bug). Confirm acceptable vs a deterministic guarantee.
3. answer_type is in `to_canonical_dict` → on-mode `plan_sha` changes; Phase-1 SHA tests
   check self-consistency (not a literal), so they pass. Confirm.
