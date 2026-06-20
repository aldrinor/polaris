# I-beatboth-001 iter-2 — residual recall gaps ceded by design (follow-up)

**Status:** disclosed, NOT a faithfulness relaxation. None of the rows below were caught at the
merge base (HEAD has no cited-span shell gate), so leaving them uncaught regresses nothing. iter-2
is strictly tightening vs HEAD and additionally stops 4 real false-drops.

## Why these are ceded (not netted with more string tuples)

iter-2's mandate (Codex 2×P1) is PRECISION — stop false-dropping real article bodies. The rows
below are genuine shells but are STRING-INDISTINGUISHABLE from legitimate short abstracts/articles,
so a deterministic string gate cannot catch them without re-introducing the exact false-drop defect
Codex flagged. Adding more cookie/citation phrasing tuples is the §-1.3-banned whack-a-mole
("breadth/quality EMERGE, never forced"). Correct home = the relevance / NLI / strict_verify /
`is_content_starved` layers (§-1.3: the faithfulness engine is the hard gate, not a string list).

## The ceded drb_78 rows (real corpus, evidence_for_gen)

| ev_id | len | class | why a string gate can't safely catch it |
|---|---|---|---|
| ev_689 | 1500 | CrossRef/Scite citation-manager chrome | identical in form to the `bibliography_with_crossref` legit negative; also off-topic (basalts) → relevance-gate's job |
| ev_715 / ev_109 / ev_272 | 559 | cookie-consent banner | phrasing "utilizes technologies such as cookies" + "accept the default settings" ≠ the exact co-occurrence tuples; more phrasings = whack-a-mole |
| ev_082 / ev_671 | 602 / 693 | content-starved abstract skeleton | "Abstract Objective: Background: Methods: Results: Conclusions:" + incidental CrossRef text; defect is empty-section → `is_content_starved`'s retrieval-layer job |

## Render-dump-index boundary (stated, not silently skipped)

PHASE1_ISSUES P0-1 `[424]/[440]/[448]` (YouTube) and `[612]` (language-nav) are
`live_corpus_dump.json` RENDER indices, not `evidence_for_gen` ev_ids. There are ZERO YouTube /
language-selector shell rows in the drb_78 corpus snapshot (0 of 794), so they cannot be asserted
in the cited-span behavioral test against this corpus.

## Recommended follow-up

Open `I-beatboth-00X` to evaluate whether the relevance/NLI/`is_content_starved` layers already
quarantine ev_689/715/109/272/082/671 in the rendered output, and if not, address them at the
correct (content-classification) layer — never by expanding the deterministic shell string list.
