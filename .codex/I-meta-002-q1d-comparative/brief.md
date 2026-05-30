HARD ITERATION CAP: 5 per document. This is iter 2 of 5.

## iter-1 → iter-2 changelog (Codex P1 ADOPTED)
iter-1 REQUEST_CHANGES P1: "field shared by ≥2 entities" is too weak — it could route narrative/free-text
slots into a comparative prompt and doesn't verify distinct source provenance. ADOPTED a 3-part guard before
ANY generic pattern is emitted:
1. **Comparability guard.** (a) field-name DENYLIST — exclude fields whose name contains any of: rationale,
   interpretation, limitation, narrative, summary, conclusion, discussion, context, note, comment, caveat,
   assessment, background, overview. (b) value-shape ATOMIC guard — the value must be short (≤160 chars) and
   single-clause (no multi-sentence text: at most one sentence-ending `.?!` and no embedded newline). Both
   must hold → only atomic factual slots qualify; free-text/narrative is excluded even under an innocuous
   field name.
2. **Provenance guard.** `SlotFieldFill` carries `bound_ev_id`. A generic pattern for field F requires ≥2
   entities whose F-value passes the comparability guard AND whose `bound_ev_id` values are DISTINCT (≥2
   distinct sources). All-same-`bound_ev_id` → NO pattern (not a real cross-source comparison).
3. **Wording.** Summary is "Extracted {field} values — {entity_A}: {value_A}; {entity_B}: {value_B}." It does
   NOT use "across sources" framing (provenance distinctness is required structurally but the prose stays a
   plain restatement; the downstream strict_verify guards the LLM's integrated sentence).
Tests now prove: narrative-field-name → none; long/multi-sentence value → none; same-`bound_ev_id` pair →
none; atomic field across 2 entities with distinct ev → pattern.


- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd on remaining non-P0/P1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Output schema (emit FIRST, then ≤6 sentences)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

# BRIEF gate — #957 (S2): generalize cross-source comparative synthesis beyond the SURPASS slot contract (no-spend)

Reviewing ACCEPTANCE CRITERIA + DESIGN (not a diff). LOWER-PRIORITY S2. CLINICAL-SAFETY SENSITIVE: a
cross-source comparative inference that the sources don't support is a fabrication (§-1.1 lethal). The bar:
the generalization must NOT introduce any new fabrication surface — it must stay a NEUTRAL restatement of
already-extracted, strict_verify-gated slot values, never a synthesized causal/comparative conclusion.

## The finding (issue #957, Codex-area CONFIRMED #950) — corrected against real code
`cross_trial_synthesis.build_cross_trial_synthesis(contract_slot_payloads)` (called in
multi_section_generator.py:3899, AFTER contract sections render) emits per-section *suggested* synthesis
sentences that the LLM is asked to integrate; the actual fabrication guard is the EXISTING downstream
strict_verify on the generated prose (this module imports `_whitespace_tolerant_substring` but the live
guard is strict_verify, not this module). It is SURPASS-bound in exactly two places:
1. `_aggregate_trial_frames` only keeps entity_ids matching `^([a-z0-9_]+?)_(primary|secondary|cvot)$`
   (trial entities) — every non-trial contract entity is dropped.
2. The 3 detectors (`_detect_dose_response`, `_detect_comparator_class`, `_detect_safety_class`) hardcode
   tirzepatide/T2D prose (GIP/GLP-1 agonism, GLP-1 RA comparator classes, etc.).
`contract_slot_payloads` are LLM-extracted (run_contract_section) structured entity→field payloads that
exist for ANY question whose domain template has contract sections — NOT only trials. So for non-trial
golden Qs the synthesis layer is simply absent because the aggregation drops their entities. (Whether a
specific golden Q's template emits ≥2 contract entities is a separate template-coverage question; this fix
makes the layer domain-agnostic at the point where structured payloads exist.)

## Proposed design (contained, additive, no-spend, no new extraction)
1. `_aggregate_entity_frames(payloads)`: like `_aggregate_trial_frames` but keeps EVERY entity with ≥1
   extracted field; derives a display name from entity_id (trial-name canonicalization kept as a special
   case). Returns frames tagged is_trial (matches the trial regex) vs generic.
2. `_detect_shared_attribute_patterns(generic_frames)`: domain-agnostic, with the iter-2 3-part guard. For
   each field_name present in ≥2 GENERIC (non-trial) entities, the field must (a) pass the comparability
   guard (NOT a narrative field-name; value ATOMIC: ≤160 chars + single-clause), and (b) have ≥2 contributing
   entities with DISTINCT `bound_ev_id`. Only then emit a `_CrossTrialPattern` whose summary is a NEUTRAL
   RESTATEMENT — "Extracted {field} values — {entity_A}: {value_A}; {entity_B}: {value_B}." — with the
   contributing [ev_*] markers (the distinct bound_ev_ids). NO hardcoded domain claim, NO synthesized
   conclusion/connective, NO "across sources" framing; the LLM (guarded by downstream strict_verify) decides
   whether the comparison holds. Section key = "Comparative" (graceful no-op if the outline lacks it).
3. `build_cross_trial_synthesis`: run the EXISTING trial detectors on trial frames (UNCHANGED) AND the new
   generic detector on NON-trial frames only (so existing tirzepatide runs are byte-identical — trial frames
   feed trial detectors; generic detector sees no non-trial entities there). Behind kill-switch
   `PG_SYNTH_GENERIC_COMPARATIVE` (default ON) → OFF = exact prior behavior.
4. The render-block instruction (DO NOT invent beyond these patterns; cite ev markers; payloads are the only
   source of truth) is UNCHANGED and applies to generic patterns too.

## The real risks to rule on
1. Does the neutral restatement introduce a fabrication surface? (Claim: no — values are already-extracted,
   strict_verify-gated slot values; the summary only restates them verbatim with ev markers and asserts NO
   comparative conclusion. The LLM's integrated sentence is still strict_verify-gated downstream as today.)
2. Should the generic detector run on NON-trial frames only (proposed — keeps trial runs byte-identical) or
   on ALL frames (risks duplicating/contradicting the SURPASS detectors on tirzepatide runs)?
3. Is "shared field across ≥2 entities" the right trigger, or should it require the field to be a
   COMPARABLE attribute (e.g. exclude free-text narrative fields)? Any guard you'd require?
4. Section key: is routing all generic patterns to "Comparative" acceptable, or should they map by field?
5. Kill-switch OFF → byte-identical prior behavior?

## Files I have ALSO checked
- multi_section_generator.py:3876 (`contract_plans = [p for p in plans if is_contract_section(p)]`),
  :3899 (build call), :1056 (render call into each section prompt) — generic patterns flow through the same
  render path; no caller change needed.
- slot_fill.py `_whitespace_tolerant_substring` (imported; the live guard is downstream strict_verify).
- The 3 existing tirzepatide detectors stay UNCHANGED (trial-run behavior preserved).
- No retriever/selector/strict_verify change.

## Acceptance criteria
A. `_aggregate_entity_frames` keeps all entities with extracted fields, tags trial vs generic, preserves
   trial-name canonicalization.
B. `_detect_shared_attribute_patterns` emits a NEUTRAL verbatim restatement (no fabricated conclusion, no
   "across sources" framing) ONLY for a COMPARABLE field (not narrative-named; atomic value ≤160 chars +
   single-clause) shared by ≥2 generic entities with DISTINCT `bound_ev_id`, with the contributing ev markers,
   section "Comparative".
C. Existing trial detectors + trial-run output byte-identical; generic detector runs on non-trial frames only.
D. Kill-switch `PG_SYNTH_GENERIC_COMPARATIVE` OFF → exact prior behavior.
E. Tests: 2 non-trial entities, comparable atomic field, distinct ev → pattern with both values + ev;
   NARRATIVE field-name → none; long/multi-sentence value → none; SAME `bound_ev_id` pair → none; trial-only
   payloads → existing detectors unchanged + no generic pattern; <2 entities → none; kill-switch off → none;
   summary contains no fabricated connective / no "across sources". Existing cross_trial tests stay green.

Is this design correct + safe (no new fabrication surface, trial runs unchanged, neutral restatement only)?
