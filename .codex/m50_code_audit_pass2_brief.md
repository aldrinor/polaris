M-50 pass-2 + M-47 pass-3 audit — close blockers from earlier passes.

## What pass-2 / pass-3 address

**M-50 NOT READY → pass-2**:
- Your blocker: `_m50_select_candidate_trials` selected rows via a
  length-aware check, but returned only `(anchor, row, biblio_num)`.
  `_gen_one` then recomputed `quote = row.get("direct_quote") or
  row.get("_m42b_refetched_quote")` which short-circuits on any
  non-empty direct_quote — sending the THIN quote to the LLM.
- Fix: candidate tuple is now `(anchor, row, biblio_num, quote)`.
  `_gen_one(anchor, row, biblio_num, quote)` takes the pre-selected
  quote and passes it directly to
  `_call_m50_per_trial_subsection(direct_quote=quote, ...)`.
- New regression test
  `test_llm_receives_refetched_quote_when_direct_is_thin`
  monkeypatches the LLM call and asserts the FAT refetched quote
  reaches it.
- Also: `test_equal_length_direct_and_refetch_prefers_direct`
  locks the tie-breaker rule (refetch must be strictly longer to
  win).

**M-47 NEEDS REVISION → pass-3** (non-blocking concerns):
- Extended `_M47_FIELD_CONTEXT_TOKENS` with your suggested clamp
  paraphrases:
  - m_value_pct: + glucose disposal, glucose disposal rate,
    insulin-stimulated glucose disposal, glucose infusion rate,
    sensitivity index
  - glucagon_suppression_pct: + glucagon was suppressed,
    suppressed glucagon, bare glucagon
- Prevents false-negatives on legitimate clamp prose paraphrases.

## Commit

`a8a70b5` PL: M-50 pass-2 + M-47 pass-3 + M-49 + V28 launcher

## What to audit

1. **M-50 blocker closure**: is the new `quote` element in the
   candidate tuple carried all the way through to the LLM call?
   The new test monkeypatches `_call_m50_per_trial_subsection` —
   does that reliably cover the data-flow path?
2. **M-47 paraphrases**: do the added tokens cover the cases you
   cited? Any I missed?
3. **V28 launcher** (`scripts/run_full_scale_v28.py`): clones V27
   + sets `PG_LIVE_MAX_EV_TO_GEN=300`. Env knobs correct?
4. **M-49 preservation suite** (`test_m49_v28_preservation.py`):
   19 tests covering V27 floors + V28 acceptance. Thresholds
   correctly set at V25/V27 baseline rather than V27 actual
   (conservative, allows V28 to ship if it matches but doesn't
   beat V27)?

## Verification

`PYTHONPATH=src python -m pytest tests/polaris_graph/test_m50_per_trial_subsections.py tests/polaris_graph/test_m47_mechanism_clamp_validator.py tests/polaris_graph/test_m49_v28_preservation.py -q` — 298/298 pass (15 V28-gated skips in M-49 pending sweep output).

Full M-series regression: 298/298 + 15 skips across M-32 / M-35 /
M-41 / M-42 (a+b/c/d/e) / M-43 / M-44 / M-45 / M-46 / M-47 / M-48 /
M-49 / M-50.

## On READY / CONDITIONAL-no-blockers

Claude launches V28 full-scale sweep in the background. Expected
~90-120 min. After manifest lands: run M-49 preservation suite, then
step 2a/2b output-level audit per V2 runbook.

Write verdict to
`outputs/codex_findings/m50_code_audit_pass2/findings.md`.
