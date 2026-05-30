# Claude architect audit — PR6: qualitative present-vs-absent clinical conflict detection (#944)

**Issue:** #944 (q1c-3, depth-fix queue). **Branch:** `bot/I-meta-002-q1d-qualitative-conflict`.
**Both Codex gates APPROVE** — brief `codex_brief_verdict.txt` (iter-3 APPROVE) + diff `codex_diff_audit.txt`
(iter-5 APPROVE, zero P0/P1/P2). **NO SPEND** — rule-cue only, all 29 tests offline; LLM-judge escalation is
a default-OFF opt-in.

## What this fixes and why

Codex-verified gap (#941): `contradiction_detector.py` was numeric-regex ONLY. The most patient-dangerous
disagreements — contraindication PRESENT vs ABSENT, drug-interaction warning present vs absent, eligibility/
exclusion — carry NO number and were structurally invisible (the lethal-error class per
`feedback_qualitative_negation_escapes_regex_2026_05_26`: "Constipation did not lead to discontinuation"
escaping the numeric validator). This adds a parallel, precision-first qualitative assertion-status conflict
path, surfaced into the SAME `contradictions.json` + report.

## Method — NegEx/ConText-grounded (the canonical clinical assertion algorithm)

Cue precedence per concept, in a bounded, coordinator-clipped window: permissive_allow → statistical_null →
uncertainty → real_negation (net XOR) → antonym base → hedge. Status ∈ {PRESENT, ABSENT, INDETERMINATE,
STATISTICAL_NULL}, finite-float encoded (1.0 / 0.0 / 0.5 / 0.5) for loader safety. SME-editable lexicons in
`config/clinical_safety/qualitative_conflict_lexicon.yaml` (LAW VI), validated fail-loud.

## The clinical-safety invariants (what could hurt a patient)

- **The lethal FALSE POSITIVE is suppressed:** "no significant difference / not associated with an increased
  risk" is a STATISTICAL statement → STATISTICAL_NULL, which CANNOT anchor a hard conflict; opposing a
  definite assertion it becomes a review flag, never a phantom safety contradiction.
- **The lethal FALSE NEGATIVE is caught:** an antonym disagreement with NO negation token and NO number —
  "contraindicated in pregnancy" vs "safe in pregnancy", "avoid X with Y" vs "X may be co-administered with
  Y" — hard-fires.
- **Fail-safe = escalate-to-review, never silent:** unresolved owner slot, differing/missing condition
  scope, hedged polarity, or a definite-vs-INDETERMINATE/STATISTICAL_NULL opposition → a surfaced
  `review_flag` (severity "review"), never dropped and never auto-fired as a hard conflict. "High precision"
  means do NOT fire on a DETERMINABLE non-conflict — NOT go quiet when unsure.
- **Precision keys:** a hard conflict requires the SAME (subject, concept_type, object_slot, condition_scope)
  with DIFFERING DEFINITE polarity across ≥2 DISTINCT sources (NCT/DOI/PMID-normalized; a self-quoted source
  cannot raise a conflict). Concept-type alignment, subject match, per-concept object slot (DDI co-drug, AE
  outcome, warning hazard, eligibility criterion), and a discriminating condition scope (renal impairment ≠
  normal renal function) all guard against phantom conflicts.

## The 5-round diff-gate hardening (every finding was a real bug I fixed)

1. iter-1: Pass A hard-fired on unresolved owner; Pass B over-suppressed; cues sentence-wide; import outside
   fail-open; multi-word condition cues never matched. → owner-resolved guard, full-key suppression,
   clause-scoped extraction, imports inside the try, single-word cues.
2. iter-2: cues still clause-global (coordinated "and"); negation XOR double-counted overlapping cues. →
   bounded `_local_window`; longest-first masked negation counting.
3. iter-3: reverse-order coordination leak. → window clipped at `and`/`or`/comma/terminator boundaries.
4. iter-4: same-concept coordinated assertions collapsed (recall miss); definite-vs-soft review noise. →
   split extraction on `and`/`or`; containment-aware `_objects_disjoint` guard on both review paths.
5. iter-5: APPROVE, no findings.

## Honest scope (named, not silently dropped)

- Subject extraction reuses the GLP-1 allowlist `scope_gate._DRUG_NAME_RE` — sufficient for the golden GLP-1
  benchmark; for unknown drugs subject='' degrades to review flags (never false hard-conflicts). Generalize =
  follow-up **#965**.
- Web inspector qualitative/review rendering (branch on `type`/`severity` instead of raw float) is a
  `web/**` change requiring the visual gate → follow-up **#964**. report.md (owned here) already renders by
  assertion_status text + separate hard-conflict vs review-flag counts; the audit-IR loader is unchanged
  (tolerant; severity flows).
- Condition/temporal full extraction is review-routed for v1 (Codex brief-gate ruled acceptable).

## Tests (29, offline, NO SPEND)

Recall (must fire): antonym no-token, permissive-DDI, ae_causation did-not-lead-vs-leading-cause,
coordinated-and (both orders), same-concept coordinated, no-evidence-of negation. Precision (must NOT fire):
statistical-null→review, different subject/concept/object, condition-stratified→review, double-negation
agrees, same-source, disjoint-outcome no-review. Plus status resolution (permissive vs hedge `may`,
uncertainty), Pass-B fail-safes (unresolved owner→review, hard-conflict-doesn't-suppress-other-scope),
finite-float encoding, audit_ir.loader round-trip, lexicon fail-loud, kill-switch on/off, offline smoke. 86
PASS no-regression (numeric detector + audit loader). `py_compile` OK.

## Verdict

Ships a precision-first qualitative present-vs-absent conflict path that suppresses the statistical-null
false-positive class, catches the antonym false-negative class, fail-safes every indeterminate case to a
surfaced review flag, writes loader-safe records into the existing contradictions.json + report, is NO-SPEND
by default and fully testable offline, and leaves strict_verify / the numeric detector / the verified core
untouched. Both gates APPROVE. Ready to queue for operator merge (Option A — no spend, no lock promotion).
