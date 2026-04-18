---
target_bug: M-205
scope: evaluator advisory vs release gating
verdict: scoped
recommended_policy: hybrid
new_manifest_statuses: [partial_qwen_advisory, abort_evaluator_critical]
tests_required: 6
rationale: |
  The evaluator currently produces useful signals but no authoritative release decision. Rule checks are partly deterministic and partly keyword/shape heuristics; the Qwen judge is non-same-family but sees only the report text, not the evidence pool. Therefore a single Qwen `needs_revision` should not always abort a run, but critical evaluator failures must prevent `success`. The fix should add an explicit evaluator gate that distinguishes release-blocking deterministic integrity failures, critical Qwen verdict patterns, and advisory quality warnings.
---

# M-205 Deep Dive: Evaluator Advisory vs Gating

## 1. Current Behavior

Reviewed source:

- `src/polaris_graph/evaluator/live_qwen_judge.py`
- `src/polaris_graph/evaluator/external_evaluator.py`
- Orchestrator integration in `scripts/run_honest_sweep_r3.py`

`live_qwen_judge.py` asks Qwen for five per-axis verdicts: `citation_tightness`, `hedging_appropriateness`, `tone_consistency`, `flow`, and `completeness`. Each axis returns `good`, `acceptable`, or `needs_revision`. This is the right shape for a judge output, but the prompt only includes `research_question` and `report_text` (`live_qwen_judge.py:139-142`). Qwen cannot inspect the evidence pool, provenance token spans, contradiction records, or tier-distribution telemetry. Its citation and completeness judgments are therefore report-surface judgments, not proof of evidentiary correctness.

`external_evaluator.py` runs 13 rule checks and returns `EvaluatorOutput`, but it does not compute a gate decision. Several checks are keyword or shape checks rather than semantic validators: PT05 looks for inclusion/exclusion words (`external_evaluator.py:222-230`), PT07 looks for `expected`/`actual` strings plus a tier report object (`:240-250`), PT09/PT10 look for sponsor/injection words (`:272-290`), and PT12 only verifies that numeric citation markers do not exceed bibliography size (`:342-360`). PT13 is explicitly documented as a soft check (`:362-367`).

The orchestrator writes evaluator artifacts and logs Qwen verdicts, but status selection ignores Qwen entirely. It chooses status from outline fallback, `ev_out.rule_check_fail_count >= 3`, adequacy, and completeness (`scripts/run_honest_sweep_r3.py:990-1011`). The manifest stores Qwen counts (`:1057-1064`) but does not use them to prevent `success` or any existing `partial_*` status.

Real artifact: `outputs/honest_sweep_r6_validation/clinical/clinical_afib_anticoagulation/qwen_judge_output.json` has `parse_ok: true` and `citation_tightness: needs_revision` because the limitations section discusses corpus composition without citation support. The run manifest records `evaluator_rule_fail: 0`, `qwen_verdicts.needs_revision: 1`, and currently lacks a release-gating response to that defect.

## 2. Blocking vs Advisory Outputs

Treat evaluator outputs as three classes, not a single pass/fail count.

| Output | Class | Rationale |
|---|---|---|
| Same-family evaluator/generator check failure | release-blocking abort | This invalidates the evaluator independence assumption. Existing `check_family_segregation()` already raises; the manifest should surface it as evaluator failure if caught. |
| PT08 missing contradiction disclosures | release-blocking | If the contradiction detector found a contradiction and the report omits it, the report is materially misleading. This should block `success` regardless of total rule-fail count. |
| PT11 numeric citation failures above threshold | release-blocking | The check is deterministic enough to flag uncited decimal empirical claims. If it fails, the report has ungrounded quantitative claims. |
| PT12 citation marker exceeds evidence pool size | release-blocking | This indicates impossible or invalid bibliography linkage. It should not ship as success. |
| PT02/PT03 model disclosure missing | compliance-blocking partial | The report exists, but required audit disclosures are missing. This should prevent `success`; whether it aborts depends on product policy. |
| PT01/PT04/PT05/PT06/PT07/PT09/PT10 | advisory or partial depending count | These are important PRISMA/reporting signals, but current implementations are mostly keyword presence checks. Multiple failures should keep using `partial_rule_check_warnings`; a single failure should be advisory unless policy requires strict PRISMA publication. |
| PT13 superlative hedging | advisory | The code says this is a soft check. Keep it out of hard gating unless paired with Qwen hedging failure. |
| Qwen `flow: needs_revision` only | advisory | Flow is useful quality feedback but not evidence integrity. |
| Qwen `tone_consistency: needs_revision` only | advisory by default, partial if repeated or paired | Qwen can detect promotional language, but this is report-text-only. Escalate when combined with hedging/completeness or deterministic failures. |
| Qwen parse failure | advisory infrastructure warning | Do not block a release solely because a network/model judge failed, unless the run configuration declares live judge required. Record `qwen_verdicts.error`. |

## 3. Critical Qwen Verdict Definition

A "critical" Qwen verdict should mean more than one noisy `needs_revision`. Because Qwen does not see the evidence pool, do not gate on a single generic complaint except when the axis maps directly to a required surface invariant.

Critical Qwen verdict if `parse_ok == true` and any of these holds:

1. `citation_tightness == needs_revision` and the note or rule telemetry indicates uncited factual/numeric claims, invalid bibliography support, or uncited limitations/provenance claims. For the AF artifact, this is critical enough to prevent `success`, but not enough to abort the produced report.
2. `hedging_appropriateness == needs_revision` and `tone_consistency == needs_revision`. This combination indicates the report may be overconfident and promotional, not merely awkward.
3. `completeness == needs_revision` and deterministic completeness coverage is below threshold, or the run is already `partial_incomplete_corpus`.
4. Three or more Qwen axes are `needs_revision`, regardless of which axes. This is the anti-noise aggregate gate.
5. Two or more Qwen axes are `needs_revision` and at least one is in the high-risk set: `citation_tightness`, `hedging_appropriateness`, or `completeness`.

Non-critical Qwen verdicts remain advisory:

- One `flow: needs_revision`.
- One `tone_consistency: needs_revision` without hedging failure.
- One `completeness: needs_revision` when deterministic completeness is healthy and no evidence-visible gate agrees.
- Any `acceptable` verdict.

## 4. Gating Policy

Add a small evaluator-gate function that runs after rule checks and Qwen output are available, before manifest status selection:

```text
compute_evaluator_gate(ev_out, qwen_result, adequacy, completeness) -> {
  release_allowed: bool,
  gate_class: "pass" | "partial" | "abort" | "advisory_unavailable",
  reasons: [stable reason codes],
  qwen_critical_axes: [axis],
  rule_blockers: [item_id]
}
```

Recommended reason codes:

- `rule_pt08_contradiction_missing`
- `rule_pt11_uncited_numeric_claims`
- `rule_pt12_invalid_citation_marker`
- `rule_model_disclosure_missing`
- `qwen_citation_tightness_needs_revision`
- `qwen_hedging_tone_needs_revision`
- `qwen_completeness_needs_revision`
- `qwen_multi_axis_needs_revision`
- `qwen_parse_failed`

Status policy:

| Gate result | Manifest behavior |
|---|---|
| `pass` | Existing status selection may emit `success` or another non-evaluator `partial_*`. |
| `partial` from non-abort evaluator defects | New `partial_qwen_advisory` if Qwen is the strongest reason; existing `partial_rule_check_warnings` if rule failures are strongest. This means report produced, but not clean success. |
| `abort` from deterministic integrity failure | New `abort_evaluator_critical`. Report artifact can still be written for inspection, but release consumers must treat it as not shippable. |
| Qwen unavailable/parse failed only | Preserve otherwise-computed status, record evaluator gate as `advisory_unavailable`, and include `qwen_parse_failed` in manifest reasons. |

Precedence with existing statuses:

1. Existing hard aborts still win before generation/evaluation: `abort_scope_rejected`, `abort_no_sources`, `abort_corpus_inadequate`, `abort_corpus_approval_denied`, `abort_no_verified_sections`.
2. After report generation, `abort_evaluator_critical` wins over all `success` and `partial_*` statuses if PT08/PT11/PT12 or same-family failures indicate evidence-integrity failure.
3. If no abort but evaluator gate is `partial`, use `partial_rule_check_warnings` for rule-driven degradation or `partial_qwen_advisory` for critical Qwen patterns.
4. If another partial reason already exists (`partial_thin_corpus`, `partial_incomplete_corpus`, `partial_outline_fallback`), preserve that status but add `release_allowed: false` and evaluator reasons when the evaluator gate is partial. This avoids losing the primary degradation cause while still blocking clean release.

Manifest additions:

```json
{
  "status": "partial_qwen_advisory",
  "release_allowed": false,
  "evaluator_gate": {
    "gate_class": "partial",
    "reasons": ["qwen_citation_tightness_needs_revision"],
    "rule_blockers": [],
    "qwen_critical_axes": ["citation_tightness"],
    "qwen_parse_ok": true
  }
}
```

Keep the raw Qwen artifact and `qwen_verdicts` counts. Do not collapse Qwen to a score.

## 5. Test Specification

1. `test_evaluator_gate_blocks_pt12_invalid_citations`: build an `EvaluatorOutput` with PT12 failed and assert `gate_class == "abort"`, reason includes `rule_pt12_invalid_citation_marker`, and manifest status becomes `abort_evaluator_critical`.

2. `test_evaluator_gate_blocks_missing_contradiction_disclosure`: provide a failed PT08 with `contradictions_missing` populated and assert the gate is release-blocking even when total rule failures are below 3.

3. `test_single_qwen_flow_revision_is_advisory`: Qwen parse succeeds with only `flow: needs_revision`; assert status remains otherwise clean and `release_allowed` is not forced false.

4. `test_single_qwen_citation_revision_prevents_success`: Qwen parse succeeds with only `citation_tightness: needs_revision`; assert no `success` status is emitted. Expected status is `partial_qwen_advisory` unless another existing partial status has higher precedence, and evaluator reasons include `qwen_citation_tightness_needs_revision`.

5. `test_three_qwen_axes_needs_revision_is_partial_gate`: Qwen returns three `needs_revision` axes with no rule failures; assert `gate_class == "partial"`, `release_allowed == false`, and reason includes `qwen_multi_axis_needs_revision`.

6. `test_qwen_parse_failure_does_not_mask_success_as_abort`: Qwen parse fails but rule checks pass; assert the manifest records `qwen_parse_failed` under `evaluator_gate.reasons`, preserves the otherwise-computed status, and does not emit `abort_evaluator_critical`.

## 6. Implementation Notes

Do not put the policy inside the Qwen caller. `live_qwen_judge.py` should stay responsible for model I/O, parsing, and axis validation. The gate belongs beside `external_evaluator.py` or in a small new module such as `src/polaris_graph/evaluator/evaluator_gate.py`, because it must combine rule checks, Qwen verdicts, and existing run telemetry.

Also avoid reusing raw `rule_check_fail_count >= 3` as the only rule gate. Some single failures are critical (PT08/PT11/PT12), while several keyword-only failures may be disclosure warnings rather than evidence-integrity blockers. The fix should gate by stable item IDs and reason codes.
