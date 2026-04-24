# Codex Pass-1 Review: V30 Phase-2 Fix Plan

**Verdict**: CONDITIONAL

Direction is right and the root-cause diagnosis is still correct, but M-63 has concrete integration blockers. Do not start implementation until the revisions below are folded into the plan.

**Per-item verdicts**

- **M-63**: CONDITIONAL. Correct `root_cause` stage, but three blockers:
  1. `_rewrite_draft_with_spans()` only rewrites raw markers matching `[ev_*]`; M-58 emits `[surpass_2_primary]`-style entity ids, so the plan's "existing rewriter works unchanged" claim is false. Direct check returned `converted=0`.
  2. `render_slot_prose()` emits `value. [id]`. `split_into_sentences()` splits on `. [`, so `strict_verify()` sees uncited sentences. Direct check on rendered M-58 prose produced 3 input sentences, 0 kept.
  3. The plan is inconsistent on output grain: prose says "one SectionPlan per ContractSectionPlan" but acceptance says "1 SectionResult per contract slot (15)". The current runner prints one `### {sr.title}` per `SectionResult`, so slot-level results would repeat `### Efficacy` / `### Regulatory` unless assembly changes.
- **M-64**: CONDITIONAL. Validator promotion is the right `root_cause` move for honest report-coverage semantics. Keep `frame_coverage_report`, but do not silently drop the Phase-1 warning with no replacement signal.
- **M-65**: CONDITIONAL. `validation_cycle` classification is correct, but `BEAT_BOTH >= 4` by itself is too weak to prove the frame-driven generator fixed the intended dimensions.

**Specific revisions required**

1. **M-63 citation path**: explicitly choose one of:
   - generalize raw-marker rewrite to accept contract entity ids, or
   - map entity ids to legacy `ev_*` aliases before rewrite.
   Acceptance/tests must prove `[surpass_2_primary]`-style citations convert to `[#ev:...:start-end]`.
2. **M-63 sentence format**: do not ship `value. [id]`. Render citations attached to the same sentence (`value [id].` / `value.[id]` or equivalent) and add a direct `strict_verify` test on rendered M-58 prose.
3. **M-63 output grain**: resolve section-vs-slot dispatch before coding.
   - If slot-level `SectionResult`s: change final assembly so slot `subsection_title` is surfaced and section headings are grouped once.
   - If section-level `SectionResult`s: `_run_contract_slot` must aggregate multiple slot payloads into one section result and acceptance must stop claiming 15 `SectionResult`s.
4. **M-63 M-41c preservation**: do not blanket-skip unless contract prose is deliberately rendered so trial short-names live only in headings/metadata, not body sentences. If trial names remain in body sentences, M-58 prose should satisfy M-41c, not bypass it.
5. **M-64 transition semantics**: keep manifest key `frame_coverage_report`, but replace the Phase-1 warning with an explicit Phase-2 semantic marker (`coverage_semantics=report_coverage` or equivalent). Pure warning removal hides the boundary shift.
6. **M-65 gate**: keep "no regression on current BB dimensions", but add a target-dimension requirement: at least one of Claim Frames or Structural Depth must move off LOSE_BOTH. A raw `>=4 BB` count is not enough by itself.

**Answers to Claude's 5 self-critical questions**

1. **M-41c skip for contract slots**: not as a blanket rule. Best path: render trial names in slot headings/subsection labels, not body sentences, so M-41c becomes mostly irrelevant. If body sentences still name trials, they should pass M-41c.
2. **Outline dispatch**: prefer a separate contract dispatch type over a bare `slot_id` sentinel on legacy `SectionPlan`. The plan already has ambiguity about section-level vs slot-level behavior; a tagged contract type preserves invariants like `subsection_title`, `entity_ids`, `is_gap`, and `is_partial`.
3. **Multi-entity slots**: render N entity blocks inside the slot, each with its own payload and citation ids. Do not merge multiple entities into one undifferentiated block; that weakens M-59 per-entity validation and makes failure attribution ambiguous.
4. **Phase-2 env flag vs CLI arg**: keep the separate env flag for this cycle. It matches `PG_V30_ENABLED`, minimizes sweep-runner churn, and preserves independent Phase-1 vs Phase-2 gating. A CLI override can be added later if needed.
5. **Manifest field rename**: keep `frame_coverage_report`. Do not break Phase-1 consumers. But do not silently change semantics either; add an explicit semantic/version marker or one-cycle informational warning instead of renaming or silent removal.

**Completeness review**

- Claude missed the current `render_slot_prose()` / sentence-splitter incompatibility with `strict_verify`; this is the sharpest technical blocker.
- Claude missed the raw-marker mismatch between M-58 `[entity_id]` citations and `_rewrite_draft_with_spans()`'s `[ev_*]` regex.
- Claude did not specify how `ContractSlotPlan.subsection_title` becomes visible in final `report.md` if slot output is flattened into `SectionResult`s.
- `_run_contract_slot(slot_plan, frame_row, contract_entity, ...)` is still 1:1-shaped even though the architecture already allows N:1 slots. That needs to be resolved in the function contract, not deferred to tests.
- M-65 should tie success to the intended dimensions, not only aggregate BB count.

**Implementation order confirmation**

1. Revise M-63 design first: citation-id rewrite, sentence format, and slot-vs-section assembly contract.
2. Implement M-63.
3. Implement M-64 on top of real M-58 payloads, preserving `frame_coverage_report` with explicit Phase-2 semantics.
4. Run M-65 with the strengthened acceptance gate above.
