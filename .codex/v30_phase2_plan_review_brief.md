V30 Phase-2 fix plan — Codex pass-1 review.

You are Codex, step 6 of autoloop V2. V30 Phase-1 landed
2026-04-23 17:11 and is SEALED at
`outputs/codex_findings/v30_sweep_integration_audit/phase1_live_run_evidence.md`
(5-pass audit chain APPROVED at pass 5). Phase-1 sweep completed
in 8 min / $0.0016 with all plumbing validated end-to-end. 14/15
contract entities retrieved. But report.md content is still
legacy generator — Phase-1 didn't replace it.

Phase-2 replaces the legacy generator with M-58 slot-bound prose
for contract entities, keeps legacy LLM calls only for enrichment
sections. This is where V30 should finally move dimensions vs
V28+V29's 3 BB + 0 BO + 4 LB ceiling.

## Your responsibility

Read Claude's draft plan at `outputs/audits/v30_phase2/fix_plan_phase2.md`.
Evaluate M-63 + M-64 + M-65 against the V2 §5 schema
(causal_stage / prior_mechanism_gap / preservation_risks /
acceptance_criteria / test_coverage / classification).

Answer Claude's 5 self-critical questions:
1. M-41c skip for contract slots: right, or should M-58 prose
   also pass M-41c?
2. Outline dispatch: slot_id sentinel on SectionPlan vs a
   separate ContractSectionPlan dataclass?
3. Multi-entity slot rendering: N blocks per slot with own
   ev_ids, or one merged block with multiple citations?
4. Phase-2 env flag vs sweep CLI arg?
5. Manifest field rename: keep `frame_coverage_report` with
   semantic change, or rename to `report_coverage_report`
   (breaks Phase-1 consumers)?

## V2 protocol

- Plan review ping-pong budget: up to 3 passes per §7 #11.
  Phase-2 pass-1. Budget intact.
- On APPROVED / CONDITIONAL-no-blockers: Claude begins M-63
  implementation immediately per user directive "for all action,
  get Codex green light then auto-run".
- On REJECT: Claude iterates per V2 §7.

## Strategic context

- V30 Phase-1 5-pass audit chain concluded APPROVED.
- Clinical sweep wall was 483.7s at $0.0016. Phase-2 adds ~15
  LLM calls (one per slot) vs legacy ~3-5 calls (one per
  section). Cost bump minimal ($0.005-$0.01 est) well under
  $0.10 cap.
- M-58 module is already fully Codex-audited across 6 passes
  and APPROVED at pass 6. Anti-fabrication enforcement
  (value==source_span) will apply to every M-58 call in Phase-2.
- M-59 already fully Codex-audited + APPROVED.
- multi_section_generator.py is 3500 lines with M-41c / M-44 /
  M-50 existing validators. Phase-2 plan addresses preservation
  for each.

## Specific blockers to evaluate

1. Does M-63's `_run_contract_slot` correctly preserve the
   `SectionResult` shape so downstream assembly (biblio merge,
   sentence counting, strict_verify) works unchanged?

2. Is the M-41c skip justified? Phase-1 plan says M-58 prose
   carries citation per sentence but each sentence has one
   frame element max ("N: 1879") — is that "under-framed" per
   M-41c rule?

3. Will `_rewrite_draft_with_spans` correctly convert
   `[surpass_2_primary]` → `[ev:surpass_2_primary:span-start-end]`
   when the SlotFillPayload's bound_ev_id isn't a legacy
   `ev_xxx` string? (Evidence pool key format question.)

4. M-65 acceptance bar: BEAT_BOTH ≥ 4 on 7 dimensions. Too low
   a bar? V29 hit 3 BB. Is +1 enough to call Phase-2 shipped,
   or should we require ≥5?

5. Is M-64's "drop the phase1_retrieval_coverage_only warning
   when PG_V30_PHASE2_ENABLED=1" safe, or should the warning
   downgrade to "phase2_report_coverage_preview" so the
   transition is visible in manifest?

## Output

Write verdict to
`outputs/codex_findings/v30_phase2_plan_review_pass1/findings.md`.

Structure:
- **Verdict**: APPROVED | CONDITIONAL | REJECT
- **Per-item verdicts**: M-63 / M-64 / M-65
- **Specific revisions required** (if CONDITIONAL/REJECT)
- **Answers to Claude's 5 self-critical questions**
- **Completeness review**: anything Claude missed?
- **Implementation order confirmation**

Keep findings.md under 150 lines. gpt-5.4 + xhigh reasoning is
default.
