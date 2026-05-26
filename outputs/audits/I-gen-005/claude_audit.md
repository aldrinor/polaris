# PR #906 — I-gen-005 Step 3b Claude architect review

## Scope

Wires the post-hoc atom_refusal_validator (PR #905) into the multi_section_generator orchestrator's final-remap hook. Atom-first generation contract becomes end-to-end at runtime when PG_ATOM_REFUSAL_MODE env flag is enabled.

## 8-commit delivery (4 main + 4 iter-fixes)

Main:
1. strict_verify _verifier_cleaned_text helper (atom/ev/biblio stripped from ALL verifier internal checks; SentenceVerification.sentence preserves originals)
2. validator citation-strip + paragraph preservation (claim detection on stripped copy; paragraph boundaries via finditer; sentence_index monotonic)
3. _call_section returns 4-tuple with atom_catalog (same catalog V4 Pro saw in prompt)
4. SectionResult fields + final-remap validator hook + PG_ATOM_REFUSAL_MODE flag (off/log_only/strict)

Codex iter-fixes (all P1s caught BEFORE merge — exactly what the cap is for):
- iter-1 fix: entailment + content-word paths also use cleaned text
- iter-2 fix: separated rendered sentence body from word-count check
- iter-3 fix: splitter handles .[N] glued boundary
- iter-4 fix: finditer-based splitter PRESERVES [N] in preceding sentence

## LAW compliance

- LAW II: 99/99 real tests pass; every Codex P1 addressed in-line
- LAW III: Codex consulted at design (3-iter APPROVE_DESIGN) + diff review (5-iter APPROVE)
- LAW V: snake_case, explicit imports, fail-soft at boundaries
- LAW VI: PG_ATOM_REFUSAL_MODE env-driven, not hardcoded

## §-1.1 clinical-safety check

Default mode "off" preserves pre-PR behavior. log_only mode gives observability without behavior change. strict mode replaces unsupported claims with refusal disclosure — false negative recoverable, false positive (the lethal mode) prevented.

## Follow-up scope (acknowledged P2s)

1. write_gaps_sidecar() production caller in run_honest_sweep_r3.py
2. Strict mode + empty-catalog contract sections (skip or atom-enable)
3. Real-run log_only calibration before any strict flip

Ready for merge.
