HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. Reserve P0/P1 for real gaps that would let a broken run pass.
- Verdict APPROVE iff the preflight is COMPLETE + correctly behavioral (no missed element, no config-check masquerading as a firing check).

# Codex gate — I-deepfix-001 forensic PREFLIGHT SPEC (completeness + rigor review)

Review `.codex/I-deepfix-001/PREFLIGHT_SPEC.md`. Cross-check it against `.codex/I-deepfix-001/BEATBOTH_MASTER_PLAN.md` (17 workstreams, the 6 residuals D1-D6, the acceptance gate) and `.codex/I-deepfix-001/RESMOKE_S11_FORENSIC_AUDIT.md` (the drb_72 §-1.1 audit that found the 6 residuals + run-level weaknesses). Repo root C:/POLARIS, read-only.

This preflight is the ONLY thing between the operator and a paid A100 acceptance run that must fix all 6 residuals AND beat both scoreboards. The operator demanded it test "every tiny little element". Your job: find what it MISSES or gets wrong.

## VERIFY (be a completeness critic — the cost of a miss is a wasted paid run)
1. **Every residual covered + behaviorally?** D1-D6 each have a GONE assertion that greps the REAL rendered output (report.md/manifest/verification_details), not just a flag. Is any residual's check actually a config-check in disguise? Is any residual missing a sub-symptom the audit found (e.g. D3 has multiple chrome classes — leading header word, in-text (1,2), truncated (YYYY), repeated sentences — are all covered)?
2. **Every winner firing-checked?** WS-2 (consolidation collapsed>0, cross_source_units>0, slate-ON), WS-3 (Evidence-base rendered AND kept_sentences_pre_resolve populated+verified — the P1), WS-13 (no wall-drop). Is any winner only slate-checked but not firing-checked? Recall the master lesson: "in the slate != fired in the output."
3. **Faithfulness never relaxed?** The preflight must not let a run PASS by relaxing the frozen engine or by treating a disclosed-gap as success falsely. Is the frozen-engine-untouched + 0-fabrication + honest-disclosure bar airtight? Any check that could green-light an unfaithful run is a P0.
4. **§-1.3 respected?** No check demands a breadth NUMBER via a cap/floor/target (the banned day-waster). Breadth checks assert SURFACING of the keep-all set, not a forced count. Flag any check that would push someone to add a cap.
5. **Config/model bar correct?** kimi-k2.6 D8 judge (not GLM, not gemma), two-family, PERMIT=1 side-surface only, MAX token budgets, GPU device split, VM-only. Any error?
6. **Thresholds sane?** coverage>=66, unsupported<=5%, acc>=90% — consistent with the boards (DRB-II #1 AI21 64.38; DeepTRACE GPT-5-DR acc 79.1%/unsup 12.5%). Is the DeepTRACE self-scorer caveat (no public scorer -> ESTIMATE) honestly stated?
7. **Missed systemic blocker?** Anything in the audit's run-level weaknesses (GPU-OOM->lexical, judge trickle/429, retrieval wall, quantified-rejected, zero corroboration) NOT covered by a preflight check?
8. **Mechanics sound?** Stage A offline / Stage B VM small render / Stage C §-1.1 audit / fail-loud GO-NO-GO. Is the small-scale VM render genuinely sufficient to validate D3/D4 (retrieval+render-time effects)? Any GO path that could fire with a failed check?

## Output schema (REQUIRED)
```yaml
verdict: APPROVE | REQUEST_CHANGES
covers_all_6_residuals_behaviorally: true | false
covers_all_winners_firing: true | false
faithfulness_bar_airtight: true | false
s13_no_forced_number: true | false
missed_elements: [ ... ]        # the important part — every element the preflight should check but does not
config_or_threshold_errors: [ ... ]
novel_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
```
