HARD ITERATION CAP: 5 per document. This is iter 5 of 5 (FINAL — cap hit after this).
- Front-load ALL real findings. No drip-feeding.
- Reserve P0/P1 for real execution risks; classify non-blockers P2/P3.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## iter-4 REQUEST_CHANGES — the P1 + P2 FIXED (re-verify):
- **iter-4 P1 (same-concept coordinated assertions collapsed):** `_split_clauses` now ALSO splits on
  coordinating `and`/`or`, so `"safe in pregnancy AND contraindicated in lactation"` yields TWO assertions
  (ABSENT@pregnancy + PRESENT@lactation), each bound to its own condition; the orphaned-subject fallback
  carries the drug. A real pregnancy ABSENT-vs-PRESENT cross-source conflict is now caught, not missed.
  Over-splitting a compound condition only UNDER-captures (trailing fragment has no concept cue) — never a
  false conflict. New test `test_same_concept_coordinated_assertions_not_collapsed`.
- **iter-4 P2 (definite-vs-soft review noise):** the determinable-different object_slot guard now applies to
  the definite-vs-soft path too, via a CONTAINMENT-aware `_objects_disjoint` (so 'nausea' vs 'pancreatitis'
  is disjoint → no review, but 'an increased risk of pancreatitis' vs 'pancreatitis' is NOT disjoint →
  still reviews). Applied to BOTH guards. New test `test_definite_vs_soft_disjoint_outcomes_no_review_noise`.

Evidence: 29/29 detector tests PASS (incl. the 2 new regression tests). iter-4 verdict confirmed the
reverse-order leak fix + all other invariants hold. NO SPEND.

## iter-3 REQUEST_CHANGES — the single residual P1 FIXED (re-verify):
- **iter-3 P1 (reverse-order coordination leak):** `_local_window` now CLIPS the window at the nearest
  coordinating boundary (`,` `;` `and` `or` + termination terms) on BOTH sides before applying the token
  cap. So `"... contraindicated in pregnancy AND may be co-administered with metformin"` clips the
  contraindication window at `and` → the permissive cue is excluded → contraindication stays PRESENT; the
  DDI permissive remains its own ABSENT assertion in its own segment. New test
  `test_coordinated_and_cue_does_not_leak_reverse_order` (asserts BOTH orders + that the DDI ABSENT is not
  lost). iter-3 verdict confirmed everything else aligns (Pass A owner-skip, Pass B exact-pair suppress,
  STATISTICAL_NULL/INDETERMINATE cannot anchor, dataclass+finite floats, fail-open imports, kill-switch,
  fail-loud lexicon). 27/27 detector tests PASS. NO SPEND.

## iter-2 REQUEST_CHANGES — both P1 FIXED in the regenerated patch (re-verify):
- **iter-2 P1.a (clause-global cues):** high-precedence cue classes (permissive/statistical/uncertainty/
  hedge) are now evaluated in a BOUNDED `_local_window` of `scope_token_cap` words around the matched
  concept — NOT clause-wide. `"may be co-administered with metformin AND is contraindicated in pregnancy"`
  now keeps the contraindication PRESENT (the permissive cue is outside the contraindication's window).
  New test `test_coordinated_and_cue_does_not_leak_across_concept`.
- **iter-2 P1.b (overlapping negation double-count):** `_net_negation_flip` now matches real-negation cues
  LONGEST-FIRST and MASKS each match so a shorter overlapping cue cannot re-count. `"no evidence of
  contraindication"` counts ONE negation (not 'no evidence of' + 'no') → resolves ABSENT. New test
  `test_no_evidence_of_negation_not_double_counted`.

Evidence: 26/26 detector tests PASS (incl. the 2 new regression tests). NO SPEND.

---
## (iter-1 fixes from the prior round, retained:)

## iter-1 REQUEST_CHANGES — all 3 P1 + 2 P2 FIXED in the regenerated patch (re-verify):
- **P1.1 (Pass A unresolved owner hard-fired):** Pass A now SKIPS any full-key group whose OWNER slot
  (object_slot for DDI/AE/warning/eligibility, condition_scope for contraindication) is empty → routes to
  Pass B review. `"Avoid metformin."` vs `"Metformin may be co-administered."` (both co-drug unresolved) →
  review, NOT hard. New test `test_unresolved_owner_both_sides_is_review_not_hard`.
- **P1.2 (Pass B over-suppression):** `hard_keys` now keyed by the FULL identity
  `(subject, concept_type, object_slot, condition_scope, src_a, src_b)`; Pass B suppresses ONLY the exact
  pair already hard-conflicted. A pregnancy hard conflict A/B no longer suppresses a renal review A/B. New
  test `test_hard_conflict_one_scope_does_not_suppress_review_another_scope_same_sources`.
- **P1.3 (sentence-wide cue leak):** extraction is now CLAUSE-scoped (`_split_clauses` on commas/semicolons
  + termination terms); `_classify_status` sees only the concept's clause. `"may be co-administered with
  metformin, but is contraindicated in pregnancy"` keeps the contraindication PRESENT. A clause with no drug
  inherits the sentence subject. New test `test_cross_clause_cue_does_not_leak`.
- **P2.1 (import outside fail-open):** ALL detector imports (incl. `qualitative_conflict_enabled`) are now
  inside the sweep's fail-open `try` — an import failure logs + skips, never aborts.
- **P2.2 (multi-word condition cues never match):** lexicon condition_scope_cues are now SINGLE-WORD only.

Evidence: 24/24 detector tests PASS (incl. the 3 new regression tests); 86 PASS no-regression (numeric
detector + audit_ir loader); `py_compile scripts/run_honest_sweep_r3.py` OK. NO SPEND.

RULE NOW — emit the YAML verdict block FIRST. Read ONLY the patch at
`.codex/I-meta-002-q1d-qualitative-conflict/codex_diff.patch` (4 files, +897/-2). Do NOT explore beyond it.
CLINICAL-SAFETY-CRITICAL (§-1.1): a FALSE qualitative conflict floods the safety report; a MISSED one hides
a real present-vs-absent contraindication/DDI disagreement. NO SPEND (rule-cue only; LLM-judge default OFF).

## Output schema (emit FIRST)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

# Codex diff-gate (iter 1) — PR6: qualitative present-vs-absent clinical conflict detection (#944)

Verify the diff implements the brief-gate-APPROVE'd design (brief APPROVE at iter 3; the two REVISED SPEC
sections in `.codex/I-meta-002-q1d-qualitative-conflict/brief.md` are binding).

## What to verify against the brief
1. **Cue precedence (iter-2 P1.a):** in `qualitative_conflict_detector._classify_status`, precedence is
   permissive_allow → statistical_null → uncertainty → real_negation(net XOR) → antonym base → hedge.
   `may be co-administered` (permissive, in drug_interaction.absent_cues + permissive_allow) resolves ABSENT
   and HARD-fires vs `avoid`; `may be contraindicated` resolves INDETERMINATE.
2. **Statistical-null suppression (the lethal FP):** `not associated with an increased risk` /
   `no significant difference` → STATISTICAL_NULL, cannot anchor a hard conflict; opposing a definite →
   review_flag (not a hard conflict, not dropped).
3. **Antonym/variant recall (the lethal FN):** `contraindicated` vs `safe in` with NO negation token →
   hard conflict; `did not lead to` vs `a leading cause of` → hard conflict.
4. **Two-pass + object_slot fail-safe (iter-1 P1.2 + iter-2 P1.b):** Pass A full key (subject, concept_type,
   object_slot, condition_scope) = hard conflicts; Pass B coarse key (subject, concept_type) routes
   missing/unresolved/broad object_slot OR differing/missing condition_scope OR definite-vs-INDETERMINATE/
   STATISTICAL_NULL to review_flag; ONLY both object_slots resolved+different is a no-flag non-conflict.
   Pass B does not skip a coarse group that already has a hard conflict (iter-2 P2.a).
5. **Source-distinctness:** `_normalize_source_id` (NCT/DOI/PMID/host) — same source self-quoted = ONE
   source, cannot raise a conflict; conflict requires ≥2 DISTINCT sources.
6. **Condition-scope discrimination (iter-1):** `_extract_condition_scope` returns organ + adjacent
   severity/normality qualifier ONLY (never the concept verb), so `renal impairment` ≠ `normal renal
   function` (review, not hard) while `pregnancy` == `pregnancy` (hard conflict). [I FIXED a self-found bug
   here: the first window impl swallowed the concept word and split same-condition conflicts to review.]
7. **Loader-safe serialization (iter-1 P1.1 + P1.4):** `QualitativeConflictRecord` is a `@dataclass` with
   `predicate` + `claims:list[dict]` (each claim has evidence_id/predicate/value), so the sweep's existing
   `[asdict(c) for c in contradictions] + [asdict(qr) for qr in qualitative_records]` serializes a
   HOMOGENEOUS dataclass list (no mixed serializer). Finite float per claim: PRESENT 1.0 / ABSENT 0.0 /
   INDETERMINATE 0.5 / STATISTICAL_NULL 0.5.
8. **Renderer branches on type/severity (iter-1 P1.5):** report.md adds a separate "Qualitative safety-
   conflict disclosures" section rendering assertion_status TEXT (NOT the float) + separate hard-conflict vs
   review-flag counts; log line `numeric_contradictions=N qualitative_conflicts=M qualitative_review_flags=K`.
   audit_ir loader UNCHANGED (tolerant; severity flows). Web inspector qualitative render = follow-up #964.
9. **No-spend + kill-switch:** `qualitative_conflict_enabled()` (default ON; `PG_SWEEP_QUALITATIVE_CONFLICT=0`
   off); LLM-judge flag default off → no network; lexicon validated fail-loud (missing section → RuntimeError);
   sweep wiring is fail-open (detector error logged, never aborts).

## Evidence (verified by Claude main-thread, NO SPEND)
- 21 tests PASS (`tests/polaris_graph/test_qualitative_conflict_detector.py`): antonym hard conflict (no
  negation token); permissive-DDI hard conflict not downgraded; ae_causation did-not-lead-vs-leading-cause;
  statistical-null → review not hard; different subject/concept_type → no conflict; condition-stratified →
  review not hard; double-negation agrees → no conflict; same-source → no conflict; permissive-may=ABSENT vs
  epistemic-may=INDETERMINATE; uncertainty cannot-be-excluded → review not dropped; missing object_slot →
  review not dropped; determinable-different object_slot → no flag; coarse group with hard conflict still
  emits review; finite-float all 4 statuses; audit_ir.loader round-trip; lexicon missing section → fail-loud;
  kill-switch on/off; offline smoke full path; empty inputs.
- 109 PASS no-regression across numeric contradiction_detector + audit_ir loader + serializer.
- `python -m py_compile scripts/run_honest_sweep_r3.py` OK.
- HONEST: subject extraction reuses the GLP-1 allowlist `scope_gate._DRUG_NAME_RE` (sufficient for the golden
  GLP-1 benchmark; unknown drugs → subject='' → fail-safe routes to review, never false hard-conflict).
  Generalizing the drug lexicon = follow-up #965. Pre-existing repo-wide collection errors in unrelated
  intake/scope/sovereignty modules are NOT caused by this diff (my 4 files import + test clean).

## Constraints / frozen
snake_case; explicit imports; no except:pass (the sweep's one broad except is fail-open + logged, never
silent). Untouched: strict_verify / provenance / numeric contradiction_detector / runtime lock / verified
core / audit_ir loader. LOC: NEW isolated module (482) + config (96 data) + 54-line wiring + 267 tests — one
cohesive safety PR per brief-gate P2 ruling (no hard automated LOC gate in CI; new-module exemption).

## The real risks to rule on
1. Does `_classify_status` precedence actually make `may be co-administered` ABSENT (hard-fire) AND
   `may be contraindicated` INDETERMINATE, with the net-negation XOR collapsing double negation?
2. Is `_extract_condition_scope` discriminating enough (renal impairment ≠ normal renal) WITHOUT splitting
   genuine same-condition conflicts (pregnancy == pregnancy)?
3. Pass B fail-safe: is any silent-drop path left for definite-disagreeing distinct-source pairs with
   missing/unresolved object_slot or condition_scope?
4. Is the merged contradictions.json loader-safe for EVERY emitted record (predicate+claims≥2, value float)?
5. Any way a STATISTICAL_NULL or INDETERMINATE can anchor a HARD conflict (it must not)?
6. Fail-open + kill-switch + lexicon-fail-loud — all correct and no-spend?

APPROVE iff the diff implements the brief-APPROVE'd design with no silent-drop path, no way for
STATISTICAL_NULL/INDETERMINATE to anchor a hard conflict, loader-safe records, default-ON no-spend kill-switch,
and leaves strict_verify/numeric detector/verified core untouched.
