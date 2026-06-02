# I-faith-001 — Fix C (narrative anti-fabrication enforced) + regulatory classification

GitHub Issue: #1037. Branch: `bot/I-faith-001-rescue-leak` (continuation — A+B+D already applied).

## What was already on the branch (verified by reading the code, not assumed)
- **Fix A** — `_drop_is_numeric` rescue drop-reason guard in `contract_section_runner.py`.
- **Fix B** — stream separation: `_verify_one_stream(...)` with the narrative stream wired
  `allow_rescue=False`; deterministic stream `allow_rescue=True`.
- **Fix D** — integer SUBSET (not intersection) in `provenance_generator.verify_sentence_provenance`.
- Tests: `test_faith_rescue_guard.py` (Fix A/B/D), `test_m63 ...narrative_origin...end_to_end` (Fix B wiring).

## Fix C — implemented this session

### 1. Narrative anti-fabrication is now an EXPLICIT, TESTED guarantee
Fix B already routes the narrative paragraph through independent `verify_sentence_provenance`
in the rescue-INELIGIBLE stream. Per the fix_plan ("If Fix B already routed narrative through
independent verify, make C the explicit, tested guarantee"), Fix C adds the deterministic
qualitative-closure test that Fix A/B did not have:

- `test_qualitative_fabrication_drops_on_entailment_not_numeric` — the run-9 qualitative leak
  class (NO numbers, SHARES content words with the span → clears the mechanical content-overlap
  floor, but NOT entailed) is dropped by the REAL verifier on `entailment_failed`, and
  `_drop_is_numeric` is False (so Fix A alone would leave it rescue-eligible — the exact gap).
- `test_fix_c_narrative_stream_drops_entailment_fabrication_not_rescued` — end-to-end through the
  REAL `_verify_one_stream` + REAL rewrite path: the deterministic stream RESCUES the
  entailment-dropped sentence (the laundering bug), the narrative stream DROPS it. Isolates the
  closure to the stream's rescue policy (Fix B/C), not the numeric guard (Fix A).
- The entailment judge is a plain deterministic stub installed via the established `_get_judge`
  seam (same surface `test_verification_mode_phase0b.py` uses — NOT a unittest.mock of the
  evidence DB; §9.4-compliant). Runs OFFLINE under `PG_STRICT_VERIFY_ENTAILMENT=enforce`.

### 2. Narrative prompt tightened (`slot_fill.py build_slot_narrative_prompt`)
The VERBATIM CONSTRAINT block now forbids introducing not just new numbers but new QUALITATIVE
specifics — explicitly names attrition / churn / retention / CSAT / NPS / equilibrium /
partial-equilibrium / spillovers (the run-9 fabrications) as forbidden unless verbatim in the
provided fields; instructs "RESTATE ONLY the provided field payloads", "introduce no new named
concepts/metrics/mechanisms/outcomes/subgroups/causal claims", "when in doubt say LESS". The
docstring records that the prompt is the SECOND (defense-in-depth) layer; the per-sentence
re-verify in the rescue-ineligible stream is the HARD gate.

## Regulatory classification — M-70 `render_regulatory_prose` is rescue-INELIGIBLE

Discriminating reason (verified against the parsers):
- **M-58 `render_slot_prose`**: `parse_slot_fill_response` enforces `value == source_span`
  (whitespace-collapse only) — the ENTIRE rendered prose is verbatim source text. The M-69
  rescue premise ("undo content-overlap false-drops on legitimately-verbatim slot prose") holds
  → rescue-ELIGIBLE (unchanged).
- **M-70 `render_regulatory_prose`**: `parse_regulatory_synthesis_response` verbatim-checks ONLY
  the one `source_span` PHRASE against the segment — NOT the LLM-synthesized 50-80 word `value`
  paragraph. So a regulatory paragraph can carry LLM-introduced connective/qualitative content
  beyond the single verified phrase — the SAME fabrication shape as the narrative stream → must
  be rescue-INELIGIBLE.

Implementation: added a THIRD labeled stream (`regulatory`) verified with `allow_rescue=False`
(honest telemetry: a regulatory drop is attributable to its own stream, not conflated with
narrative or deterministic). Per-entity routing in `run_contract_section` now sends
`render_regulatory_prose(payload)` to `slot_reg_prose` (rescue-ineligible) and
`render_slot_prose(payload)` to `slot_det_prose` (rescue-eligible). A slot is M-58 OR M-70 per
entity, so the two never co-occur for the same entity — only the merge ORDER (det, reg, narr) is
defined.

Tests:
- `test_regulatory_stream_is_rescue_ineligible` (helper level): the regulatory stream
  (`allow_rescue=False`) does NOT rescue the same content-overlap-dropped input the deterministic
  stream rescues.
- `test_regulatory_origin_sentence_not_rescued_end_to_end` (wiring, m63): drives
  `run_contract_section` with a real FDA-shaped regulatory entity + canned `llm_call` returning a
  synthesis JSON whose prose `value` carries a fabrication marker (with a verbatim `source_span`
  that passes the M-70 parser). A fake strict_verify drops every sentence non-numerically; the
  marker MUST be absent from `verified_text`. ANTI-VACUITY: a LIVENESS assertion (`_REG_MARKER in
  result.raw_draft`) first proves the regulatory prose was actually produced and entered the
  regulatory stream — so the absence-from-verified_text assertion can only pass for the right
  reason (produced → entered regulatory stream → dropped by rescue-ineligibility), not because the
  prose was never generated. NEGATIVE CONTROL (standalone `_verify_one_stream` run): under the OLD
  routing (`allow_rescue=True`) the marker survives (rescued); under the NEW routing it is dropped.

## Evidence
- Smoke `outputs/q1_run9/smoke_brynjolfsson_leak.py`: S1 (14%) FAIL, S2 (35%) FAIL, S3 (15%) PASS — unchanged.
- Named suites (`test_m58_slot_fill`, `test_m57_contract_outline`, `test_faith_rescue_guard`): 77 passed.
- Including adjacent (`test_m63_contract_section_runner`, `test_m70_regulatory_synthesizer`,
  `test_verification_mode_phase0b`): 132 passed.
- Baseline before edits: 106 passed (m58+m57+faith+m63+m70). After: 110 passed (+4 new tests).
- The 70 full-suite collection ERRORS are PRE-EXISTING (`No module named 'polaris_graph'` — test
  files importing `polaris_graph.*` instead of `src.polaris_graph.*`); confirmed present with my
  changes git-stashed. Not caused by this work; all touched/adjacent suites use `src.polaris_graph`
  and collect+pass cleanly.

## Files changed (Fix C session only)
- `src/polaris_graph/generator/contract_section_runner.py` — regulatory → third rescue-ineligible stream.
- `src/polaris_graph/generator/slot_fill.py` — narrative prompt tightening + docstring.
- `tests/polaris_graph/test_faith_rescue_guard.py` — 3 new tests (qualitative entailment fabrication).
- `tests/polaris_graph/test_m63_contract_section_runner.py` — 1 new regulatory wiring test.
- (provenance_generator.py diff present on branch is the pre-existing Fix D — NOT touched this session.)
