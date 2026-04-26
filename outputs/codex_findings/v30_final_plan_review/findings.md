# Codex final review of V30 FINAL_PLAN

## Verdict
PARTIAL

All 7 pass-1 fixes are integrated correctly. I do not see a structural disagreement on the audit-only pivot or on Evidence Inspector as the canonical renderer. The remaining issues are consolidation-level: one estimate/phase-label ambiguity, one Phase A concurrency dependency mismatch, and one missing Phase B risk around template misrouting / unsupported-query overclaim.

## Pass-1 fix integration check
For each of the 7 fixes from previous review:

- [x] **Wish #1 renamed correctly.** `Question-Bound Corpus Brief` is now the canonical label, and it is explicitly dependent on bounded upload landing first.
- [x] **Wish #2 estimate raised correctly.** `25-40 eng days` is now used, with the right rationale: workspace data model, permissions, retention, deletion semantics, provenance mapping, parser-status UX.
- [x] **Composition section rewritten correctly.** The canonical object is now the audit graph / audit IR, with Evidence Inspector as the primary renderer and all other outputs as derivative projections with back-links.
- [x] **Memory split corrected.** Session / workspace / global-system memory are separated, and global memory is quarantined from the audit lane by default.
- [x] **1-click UX expanded correctly.** The preview-lane concept is replaced by progressive audit-native surfaces: pre-flight estimate, parse progress, tier mix, frame coverage, contradiction queue, first verified claim cards, final synthesis.
- [x] **PRD bundle scope raised correctly.** `70-110 eng days = 7-11 weeks` is now the planning number.
  Specific edit needed: in the consolidated plan this number is used like the total `Phase A -> B` bundle in some places, but is labeled as `Total Phase B eng work` in another. Clarify which it is.
- [x] **Sequencing note integrated correctly.** The plan now preserves the Codex point that a citation-bound deck beta is the better late-B pull-forward candidate than broadening the corpus-brief promise.

## Audit-lane-only assessment
Single-lane holds up.

I do not see a structural need to reintroduce a prose preview lane if the product truly ships the progressive Inspector state described in the plan. The correct time-to-first-value object is not `first draft prose`; it is `first inspectable evidence state`. The plan now reflects that.

The only caveat is operational, not architectural: if `Phase A` is truly internet-facing before progressive surfaces and before minimal queueing/gating, it should be described as controlled demo traffic rather than open beta. Otherwise the blank-stare and concurrency problems arrive earlier than the sequencing implies.

## Evidence Inspector as canonical renderer
Yes. The final plan now treats Evidence Inspector consistently as the **primary renderer over the canonical audit graph IR**, not as a secondary viewer layered on top of a report. PDF, DOCX, charts, brief, and deck are all framed as derivative projections with back-links to claim IDs. This was the biggest architectural correction from pass-1 and it landed correctly.

## Risk register
The register is mostly strong, but one important Phase B risk is missing:

- **Missing risk: template-router false positives / unsupported-query overclaim.**
  Why it matters: Beta opens custom queries inside a curated template library. The failure mode is not only low-confidence queries routing to review; it is medium-confidence wrong routing that produces a polished but misframed audit. That is earlier than Phase D auto-induction and is a real trust risk in Phase B.
  Suggested entry: `Query-to-template misrouting` | `Medium-High` | `High` | `B` | conservative confidence thresholds, explicit unsupported result, operator review on ambiguity, scope-page reinforcement.

Minor calibration note:

- `Single-run concurrency lock` is correctly high/high, but the mitigation is not fully aligned with the phase plan. See sequencing below.

## Phase sequencing
Mostly clean:

- `Phase A` Evidence Inspector is feasible without bounded upload. It can ship on narrow supported clinical templates over web/curated sources only.
- Bounded upload correctly blocks `Question-Bound Corpus Brief`. That dependency is now stated clearly.
- Evidence Inspector does not need bounded upload to exist; bounded upload needs the Inspector/provenance model, not the other way around.

Remaining sequencing issue:

- The plan says `Phase A` is internet-facing, the risk register marks `single-run concurrency lock` as a Phase A high/high blocker, but queue-backed concurrency only appears as a Phase B deliverable.
- Pick one of these and state it explicitly:
  1. `Phase A` is controlled-access / low-throughput demo traffic, so minimal concurrency is acceptable until Phase B.
  2. Or `Phase A` includes a minimal queue/gating layer before anything is truly internet-facing.
- Without that clarification, the plan under-specifies the operational shape of the demo launch.

Estimate clarity issue:

- The `70-110 eng days = 7-11 weeks` figure appears as the realistic next-ship bundle number, but later it is labeled `Total Phase B eng work`.
- Since the timeline also says `Phase A = 2-3 weeks` and `Phase B = 5-9 weeks after A`, the clean wording is: `70-110 eng days for the combined Phase A -> B bundle`, unless you want to publish a separate incremental Phase B estimate.

## Refusal list
Correct overall.

- Refusing unconstrained WikiLLM, mass-scale ingestion, polished infographics, audio/podcast outputs, silent global memory, preview lane, and broad connector parity is consistent with the moat.
- I do not see a refusal item that should be removed.
- I do not think anything material is missing from the refusal list; the template-router issue is better handled as a risk/guardrail than as a refusal item.

## What Claude missed in consolidation
1. **Estimate ownership is ambiguous.** `70-110 eng days` is used like a total next-ship number in some places and a `Phase B` number in another.
2. **Phase A internet-facing status is not reconciled with the stated Phase A concurrency blocker.** Either gate access in Phase A or move minimal queueing/gating earlier.
3. **The risk register skips the Phase B template-misrouting / unsupported-scope-overclaim failure mode.** That is distinct from Phase D auto-induction hallucination.

## Final verdict
PARTIAL with specific edits listed.

If those three consolidation edits land, I would move this to GREEN. There is no remaining structural disagreement on audit-only, Evidence Inspector primacy, memory split, or the 7-wish triage.
