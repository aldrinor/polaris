# M-47 Pass-2 Code Audit Findings

Verdict: NEEDS REVISION for one adjacent conditional-closure issue. The core M-47 blocker fixes are materially improved and the targeted M-47 tests pass locally, but the claimed M-50 richer-quote consistency is still incomplete downstream.

## Findings

1. Medium - M-50 selects a fat refetched quote for eligibility, then still sends the thin direct_quote to the subsection generator.

   In `_m50_select_candidate_trials`, the pass-2 code correctly checks `direct_quote` and `_m42b_refetched_quote` and allows a row when either quote is at least 100 chars (`src/polaris_graph/generator/multi_section_generator.py:1767`-`1772`). But the selected quote is stored only in a local `quote` variable and discarded when appending `(anchor, row, biblio_num)`. Later `_gen_one` rebuilds the quote with `row.get("direct_quote") or row.get("_m42b_refetched_quote")` (`src/polaris_graph/generator/multi_section_generator.py:3239`-`3240`), so a non-empty thin `direct_quote` still hides the fat refetch for actual M-50 generation.

   Impact: conditional #3 is closed for M-47 validator extraction, but not consistently for the claimed M-50 pattern. A row with `direct_quote="thin"` and a rich `_m42b_refetched_quote` qualifies for M-50, then generates from `"thin"`.

   Suggested fix: carry the selected quote through the candidate tuple, or mutate/use a normalized quote field before calling `_call_m50_per_trial_subsection`. Add a regression test where `direct_quote` is short, `_m42b_refetched_quote` is >=100 chars, and the generated subsection call receives the refetched text.

## Closure Assessment

Blocker #1: closed. `_m47_prose_contains_value` now requires the cited sentence to contain both a tolerated numeric match and a field-context token (`src/polaris_graph/generator/multi_section_generator.py:2518` onward). The new reproducer rejects "63 participants" as an M-value match.

False-negative note: the M-value token set is probably acceptable for the requested fix, but I would add common clamp paraphrases before calling it complete: `glucose disposal`, `glucose disposal rate`, `insulin-stimulated glucose disposal`, `glucose infusion rate`, and possibly `sensitivity index`. For glucagon, consider accepting bare `glucagon` or `suppressed glucagon`; current tokens require phrases like `glucagon suppression`, which can reject legitimate prose such as "glucagon was suppressed by 42% [1]."

Blocker #2: mostly closed. On M-47 validator failure with candidate fields, the generator builds an explicit hint, reruns `_bounded_run`, revalidates, and replaces the Mechanism section when regen improves the match count or fully passes (`src/polaris_graph/generator/multi_section_generator.py:2974`-`3047`). If the final diagnostic still fails, it sets `m47_mechanism_extraction_incomplete` and logs telemetry (`src/polaris_graph/generator/multi_section_generator.py:3060`-`3065`). One limitation remains: no regen is attempted when a clamp/PK row is detected but `candidate_fields` is empty, because no `hint_lines` are built (`src/polaris_graph/generator/multi_section_generator.py:2987`-`2999`). Telemetry still records incompleteness, so I do not consider this a blocker.

Conditional #3: closed for M-47, not closed for M-50 consistency. M-47 now picks the richer/usable quote before extraction (`src/polaris_graph/generator/multi_section_generator.py:2613`-`2622`). The M-50 downstream call still short-circuits on the thin quote as described in finding #1.

## Verification

`PYTHONPATH=src python -m pytest tests/polaris_graph/test_m47_mechanism_clamp_validator.py -q`

Result: 29 passed. Pytest emitted one cache warning because it could not create `C:\POLARIS\.pytest_cache\v\cache\nodeids`.
