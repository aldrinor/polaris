# Codex M-58 audit — pass 6

**Verdict**: APPROVED

## Structural fix verification
Yes. `src/polaris_graph/generator/slot_fill.py:110` now reduces anti-fabrication check 2 to:
- strict equality, or
- equality after `_whitespace_collapse` (`:160`).

That closes all prior exploit classes because every pass-1..pass-5 failure depended on `value` being a non-identical subset/variant of `source_span`:
- fabricated value with real span: `1880` vs `N=1879` now raises.
- misbound same-quote value: `10 mg` vs `5 mg` now raises.
- case/unit drift: `hba1c` vs `HbA1c`, `5 m` vs `5 M` now raise.
- substring truncation: `879` vs `1879`, `5 mg` vs `15 mg`, `5 mg` vs `(5 mg)` now raise.
- sign/ionic-state truncation: `0.47%` vs `-0.47%`, `Ca2` vs `Ca2+` now raise.

## Prompt-parser alignment
Mostly yes, and the core contract matches.
- Prompt text at `:253`, `:266`, `:273` tells the LLM that `value` and `source_span` must be the same form, with whitespace-collapse as the only tolerated drift.
- Parser enforcement at `:393` and `:405` matches that operationally: `source_span` must be a verbatim substring of `direct_quote`, and `value` must equal that span except for whitespace normalization.
- Minor wording nuance only: the prompt says both are "copied verbatim"; parser actually allows `value` to differ in whitespace form (`tab/newline/NBSP` vs plain space). That is not an exploit, just a slightly stricter prompt than parser.
- Rule 7 is sufficient guidance for a real LLM. A model can still emit mixed forms naturally, but the parser now rejects that deterministically instead of silently accepting drift.

## Sixth-round adversarial attempts
- NFC vs NFD: `value='Caf\u00e9'`, `source_span='Cafe\u0301'` -> reject.
- NBSP vs space: `value='5 mg'`, `source_span='5\u00a0mg'` -> accept via whitespace collapse.
- zero-width space vs none: `value='5mg'`, `source_span='5\u200bmg'` -> reject.
- leading whitespace on one side only: `value='N=1879 participants'`, `source_span=' N=1879 participants'` -> accept via whitespace collapse.
- multi-line span vs single-line value: newline in `source_span`, spaces in `value` -> accept via whitespace collapse.
- Unicode minus vs ASCII hyphen: `-0.47%` vs `\u22120.47%` -> reject.
- fullwidth plus vs ASCII plus: `Ca2+` vs `Ca2\uff0b` -> reject.
- identical hidden char on both sides: `value==source_span=='5\u200bmg'` -> accept, but this is faithful copying of `direct_quote`, not a parser bypass.

## Residual concerns
- No new substring-containment exploit found.
- Remaining risk is out of scope for this check: if `direct_quote` itself contains ambiguous/confusable or invisible characters, exact copying will preserve them. That is source-fidelity behavior, not `value/source_span` drift.
- Regression confirmed on the scoped V30 suite used in prior passes: `test_m54_contract_schema.py` + `test_m55_frame_compiler.py` + `test_m56_frame_fetcher.py` + `test_m57_contract_outline.py` + `test_m58_slot_fill.py` = **194/194 passed**. `test_m58_slot_fill.py` alone is **44/44 passed**.

## Next
Claude proceeds to M-59.
