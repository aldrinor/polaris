---
target_bug: M-203
scope: generation outline collapse in multi_section_generator
verdict: scoped
direction_chosen: C
new_manifest_status: partial_outline_fallback
failure_modes_identified: 12
tests_required: 6
rationale: |
  Choose Direction C: keep a deterministic fallback, but make outline degradation explicit with a new manifest status `partial_outline_fallback`, and harden outline validation so prompt contract violations are no longer silently accepted. Real artifacts show collapsed outlines are common enough that aborting immediately would discard reports that can still contain verified prose; however, the current one-section fallback hides under-coverage from downstream readers and contradicts the planner contract. The fix should retry malformed planner output once with a tighter prompt, then either use a deterministic 3-section evidence-balanced fallback when the evidence pool can support it, or abort if even that cannot produce verifiable sections.
---

# M-203 Deep Dive: Generation Outline Collapse

## 1. Current Code Path

Reviewed source: `src/polaris_graph/generator/multi_section_generator.py`.

The planner prompt requires a JSON object with `"sections"` as a 3-5 item array. It also requires every section to use an allowed title, every section to have at least two evidence IDs, and every `ev_id` to appear in at most one section.

Actual parser behavior in `_parse_outline()`:

- Empty raw response returns `[]`.
- Markdown fences are stripped.
- The parser loads the substring from first `{` to last `}`.
- JSON decode failure logs a warning and returns `[]`.
- Missing or non-list `"sections"` returns `[]`.
- It iterates only `sections_raw[:6]`.
- Non-dict entries are skipped.
- Off-list titles are dropped.
- Non-list `ev_ids` entries are dropped.
- Sections with fewer than two `ev_ids` are dropped.
- Everything else is accepted as `SectionPlan`.

What `_parse_outline()` does **not** validate:

- The final section count is 3-5.
- `ev_ids` are known IDs from the evidence pool.
- `ev_ids` are unique within a section.
- `ev_ids` do not overlap across sections.
- Duplicate section titles do not appear.
- The output has no more than five sections; six valid sections are currently possible because the loop slices `[:6]`.
- The focus is meaningful; empty focus becomes title.
- The outline covers enough of the generator-visible evidence.

`_call_outline()` simply calls the model once and returns `_parse_outline(raw)`. There is no retry, no structured error, and no reason code for why parsing failed.

The fallback path in `generate_multi_section_report()` treats any empty plan as recoverable:

```text
[multi_section] outline empty; falling back to single generic 'Efficacy' section
```

It then creates one `SectionPlan(title="Efficacy", focus="Summarize the efficacy and safety evidence.", ev_ids=all evidence IDs)`. The caller records only `generator.outline_sections`, so a fallback run is indistinguishable from a planner that intentionally selected one valid section.

## 2. Failure Modes Today

The planner output can fail or degrade in these ways:

| Failure mode | Current behavior | Risk |
|---|---|---|
| Empty response | `_parse_outline()` returns `[]`; generator falls back to one generic `Efficacy` section. | Silent report collapse. |
| No JSON object delimiters | Returns `[]`; same fallback. | Silent report collapse. |
| Malformed JSON | Logs decode warning, returns `[]`; same fallback. | Silent report collapse. |
| Valid JSON but missing `"sections"` | Returns `[]`; same fallback. | Silent report collapse. |
| `"sections"` is not a list | Returns `[]`; same fallback. | Silent report collapse. |
| All entries invalid after filtering | Returns `[]`; same fallback. | Silent report collapse. |
| Fewer than 3 valid sections | Accepted as-is. | Violates prompt contract without status signal. |
| More than 5 valid sections | Up to 6 accepted because of `sections_raw[:6]`. | Violates prompt contract and increases generation calls. |
| Duplicate or overlapping `ev_ids` across sections | Accepted as-is. | Same evidence can drive multiple sections, creating artificial breadth. |
| Duplicate `ev_ids` within one section | Accepted as-is. | A section can appear to have two evidence IDs while relying on one source twice. |
| Unknown `ev_ids` | Accepted in the outline, then silently dropped by `_run_section()` when building `ev_subset`; a section can become empty and fail later. | Delayed failure and misleading assignment telemetry. |
| Duplicate section titles | Accepted. | Report can repeat section headings and obscure coverage gaps. |

There is also a status interaction: even when the outline collapses to one section, the orchestrator can still write `success` or an unrelated `partial_*` status. The known production artifact `outputs/honest_sweep_r6_validation/clinical/clinical_afib_anticoagulation/manifest.json` records `outline_sections: ["Efficacy"]`, while `run_log.txt` shows `outline=1 sections` and final `ok_thin_corpus`.

## 3. Anti-Circle-Jerk Check

The fallback is not useless. In the AF anticoagulation run, the one-section fallback produced 4 verified sentences, 0 dropped sentences, a bibliography, and a report that Qwen judged mostly `good`/`acceptable`. The report is thin, but not empty or fabricated by the strict verifier.

The problem is observability and breadth, not simply prose validity. The same report is only 163 generator words, has one findings section, cites one bibliography entry, and still ships under `ok_thin_corpus` rather than an outline-specific degradation status. The artifact scan is also concerning: among 19 manifests under `outputs` with `generator.outline_sections`, 10 have fewer than 3 sections and 8 have exactly one section. Some older artifacts have blank section names, so this is not clean production rate evidence, but it is enough to reject "abort immediately on first planner miss" as too blunt and to reject silent fallback as unsafe.

## 4. Direction Chosen

Choose **Direction C with a retry**:

1. Retry the planner once when validation fails.
2. If retry still fails but there is enough evidence to form a minimal outline, use a deterministic fallback outline and emit `manifest.status = "partial_outline_fallback"`.
3. If neither model output nor deterministic fallback can produce at least one verifiable section, keep the existing `abort_no_verified_sections` path.

This keeps useful verified prose when available, but makes the report contract honest. `partial_outline_fallback` fits the unified taxonomy because a report exists, but the outline planner did not satisfy the intended 3-5 section contract.

## 5. Fix Specification

Add an outline validation result rather than returning only `list[SectionPlan]`.

Recommended shape:

```python
@dataclass
class OutlineParseResult:
    plans: list[SectionPlan]
    ok: bool
    used_fallback: bool = False
    reason_codes: list[str] = field(default_factory=list)
    raw: str = ""
```

Validation rules:

- Accept only 3-5 final sections for model-generated outlines.
- Reject duplicate section titles.
- Reject unknown evidence IDs.
- Deduplicate `ev_ids` within a section before counting; after deduplication, each section still needs at least two IDs.
- Reject overlap across sections for model-generated outlines.
- Reject more than five sections instead of accepting six.
- Preserve existing off-list title and singleton-evidence filtering, but return reason codes when filtering causes invalid final count.

Retry behavior:

- `_call_outline()` should call the model once as today.
- If validation is not `ok`, call the model a second time with a tighter system or prompt suffix that includes the reason codes, the exact allowed evidence IDs, and a hard reminder: "Return 3-5 sections; no evidence ID may appear twice anywhere."
- Do not retry more than once.

Deterministic fallback:

- Replace the single generic `Efficacy` fallback with a deterministic 3-section fallback when there are at least six unique evidence IDs. Suggested title order: `Efficacy`, `Safety`, `Regulatory`, then `Comparative`, `Mechanism` if needed by evidence volume.
- Assign evidence IDs round-robin or contiguous chunks so each fallback section has at least two unique, non-overlapping IDs.
- If fewer than six generator-visible evidence rows exist, allow a smaller deterministic fallback only when unavoidable, but mark the same `partial_outline_fallback` status and record `outline_fallback_reason = "insufficient_evidence_for_3_sections"`.
- If there are fewer than two evidence IDs total, do not synthesize a fallback section; let generation fail into `abort_no_verified_sections` or an earlier corpus gate.

Result propagation:

- Extend `MultiSectionResult` with outline telemetry:
  - `outline_ok: bool`
  - `outline_retry_attempted: bool`
  - `outline_fallback_used: bool`
  - `outline_reason_codes: list[str]`
  - `raw_outline: str` if not too large, or at least a truncated/debug-safe value
- Update `scripts/run_honest_sweep_r3.py` taxonomy:
  - Add `partial_outline_fallback` to `UNIFIED_STATUS_VALUES`.
  - Add a summary mapping such as `"ok_outline_fallback": "partial_outline_fallback"` if keeping legacy summary labels.
  - In success-path status precedence, choose `partial_outline_fallback` before `partial_thin_corpus`, `partial_incomplete_corpus`, and `partial_rule_check_warnings` only if the product wants outline collapse to dominate all other degraded-success signals. If only one status can be emitted, I recommend this precedence because outline fallback directly describes report structure.
- Add manifest generator fields:
  - `outline_sections`
  - `outline_ok`
  - `outline_retry_attempted`
  - `outline_fallback_used`
  - `outline_reason_codes`

Do not change the limitations fallback in this bug. It is a separate deterministic telemetry paragraph path and does not explain report section coverage.

## 6. Test Specification

Add or update these tests:

1. `tests/polaris_graph/test_multi_section_gap4.py`: parser rejects a model outline with only two valid sections and returns reason `section_count_below_min` instead of accepting it.
2. `tests/polaris_graph/test_multi_section_gap4.py`: parser rejects overlapping evidence IDs across otherwise valid sections and reports `overlapping_ev_ids`.
3. `tests/polaris_graph/test_multi_section_gap4.py`: parser deduplicates within-section IDs before counting, so `["ev_001", "ev_001"]` is invalid as `<2 unique ev_ids`.
4. `tests/polaris_graph/test_multi_section_gap4.py`: parser rejects unknown evidence IDs when an allowed evidence ID set is supplied.
5. Generator-level async test with monkeypatched `_call_outline` or client: first outline response malformed, retry response valid; assert retry was attempted and no fallback status telemetry is set.
6. Generator/orchestrator contract test: when both outline calls fail and deterministic fallback is used, `MultiSectionResult.outline_fallback_used` is true and the run manifest status maps to `partial_outline_fallback`.

Also update `tests/polaris_graph/test_manifest_contract.py` so the closed taxonomy expects 11 values, including `partial_outline_fallback`, and so status-prefix tests continue to pass.

## 7. Acceptance Criteria

- No model-generated outline with fewer than 3 or more than 5 sections is accepted as clean.
- No model-generated outline with overlapping evidence assignments is accepted as clean.
- Empty, malformed, or fully filtered planner output triggers one tighter retry.
- Any eventual fallback is visible in `manifest.status` as `partial_outline_fallback`.
- The AF anticoagulation artifact shape would no longer be reported only as `ok_thin_corpus`; it would carry an outline-specific partial status or explicit generator telemetry.
