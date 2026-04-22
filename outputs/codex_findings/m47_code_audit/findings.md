# M-47 Code Audit Findings

Verdict: NEEDS REVISION

Commit audited: `6e85312` (`PL: M-44 pass-3 + M-45 pass-2 + M-47 - close Codex audits, add mechanism validator`)

## Findings

1. **BLOCKER - Field linkage is not enforced, so unrelated same-valued numbers can satisfy the rule.**  
   In `src/polaris_graph/generator/multi_section_generator.py:2343-2352`, `_m47_prose_contains_value()` scans every numeric token in a sentence that cites the clamp ev_id and returns true on value tolerance alone. It does not require the sentence to contain the corresponding field context (`M-value`, `glucagon`, `half-life`, `Tmax`, etc.) or compatible units. This violates the M-47 contract that the same values/fields from the cited row appear in prose. Concrete false pass reproduced locally:
   - evidence direct_quote: `M-value by 63%. Glucagon suppression 42%. Half-life 5 days.`
   - prose: `The trial enrolled 63 participants, lasted 42 weeks, and used a 5 mg dose [1].`
   - result: `passes_threshold=True`, with all three extracted fields matched.
   The existing `test_broad_numeric_tokens_do_not_false_pass` is useful but insufficient because it only tests unrelated numbers that differ from the extracted values. Add coverage for same-valued unrelated field/unit tokens, and make matching field-aware.

2. **BLOCKER - Failed M-47 diagnostics do not trigger the required regeneration or incomplete telemetry.**  
   The V28 plan says to trigger one regen if fewer than three linked findings are present and emit `m47_mechanism_extraction_incomplete` if still missing. Current integration at `src/polaris_graph/generator/multi_section_generator.py:2710-2740` only computes and logs `m47_diag`; it does not regenerate the Mechanism section, fail/drop the section, or emit an incomplete telemetry object. The orchestrator only persists/logs the diagnostic at `scripts/run_honest_sweep_r3.py:1115-1130`. As a result, a Mechanism section can still ship with `passes_threshold=False`, which leaves the original M-47 output failure uncorrected.

3. **CONDITIONAL - Refetched quote fallback only works when `direct_quote` is empty, not when it is thin.**  
   `src/polaris_graph/generator/multi_section_generator.py:2409-2412` uses `row.get("direct_quote") or row.get("_m42b_refetched_quote")`. If a row has a short/thin `direct_quote` plus an accepted `_m42b_refetched_quote` containing the clamp/PK values, M-47 extracts from the thin quote and misses the accepted refetch. The M-42b path treats short quotes as refetch candidates; M-47 should likely mirror that threshold or select the richer accepted quote. This is not as severe as the two blockers if live clamp rows already carry rich direct quotes, but it is a contract gap versus "direct_quote or accepted refetched quote."

## Specific Questions

1. Evidence-linked contract: source-side extraction does use the section subset's cited evidence rows and extracts candidates from the row quote, not from section-wide numbers. However, prose-side matching is value-only, not field-aware, so the full "same values/fields" contract is not met.
2. Unit normalization: half-life days/hours is implemented. I would not add mg/dL/mmol/L in this pass unless baseline glucose is actually added as an extracted field; no current M-47 pattern extracts glucose values, so that normalization would be dead code.
3. Broad-numeric false-pass prevention: insufficient. Add a test where unrelated cited-sentence numbers equal the extracted values but have wrong fields/units.
4. Thresholds: `>=3` matched fields matches the plan, but only after field-aware matching is fixed.
5. Tolerance: `±5%` is reasonable for this validator. The problem is not tolerance width; it is missing field/unit context.
6. Prompt-rule placement: acceptable. M-47 before M-42c is coherent because extraction requirements should be stated before Mechanism length/depth targets.

## Verification

- `python -m pytest tests/polaris_graph/test_m47_mechanism_clamp_validator.py -q` -> 24 passed.
- Plain `pytest ...` was not available on PATH in this PowerShell session; `python -m pytest` worked.
