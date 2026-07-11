# FABLE GATE — agentic outliner loop, iter 1: PUSH (2 P0, 3 P1)

## Behavioral acceptance (the anti-dormant/anti-runaway gate) — BOTH FAIL

THIN (tirzepatide efficacy seed; Q also asks long-term CV safety):
  outline_mutated=False  update_outline_calls=0  search_calls=3  turns=3  ev 18->67
  - Retrieval HALF fires correctly: checklist[seed] named the exact thin aspect
    (Safety::long-term CV safety / SURMOUNT-MMO), search_more_evidence fired scoped
    on-topic queries, rows folded collision-free with S2 stamps (chrome=0 off-topic=0).
  - BUT the outline NEVER mutates. update_outline never called; 49 fetched rows are
    orphaned (never assigned to any section). after-fold checklist re-flags the SAME
    gap every round -> loop cannot converge, burns all 3 turns re-fetching.
    Harness's own thin acceptance ('the outline mutates') = FAILED.

SATURATED negative control (Q: 'In what year was the Eiffel Tower completed?'):
  search_calls=3  turns=3  ev 10->70  valid_negative_control=False
  - Retrieval did NOT stay at zero. checklist INVENTED gaps (Mechanism: engineering/
    architectural mechanisms, wind resistance/foundation/elevators; Comparative: other
    tall structures; numeric metrics). Fired 3 searches, corpus 10->70 on a single-fact
    question. This is Face-A runaway/gap-invention — the exact killer the design warned of.

## P0 (block sign-off)
P0-1 Saturated negative control fails — loop invents gaps + fires retrieval on a
     trivial single-fact question (10->70 rows). silent-on-saturated VIOLATED.
P0-2 Outline never mutates on thin (update_outline_calls=0, outline_mutated=False).
     No auto-assign of fetched rows to the gap's section AND decide policy never picks
     update_outline -> the agentic REVISION (the whole point) never happens; non-converges.

## P1
P1-1 Gap dedup keys on exact aspect string (GapTodo.key=(section,aspect)); checklist
     rewords the same aspect each round -> fresh PENDING todo each time, defeats the
     per-aspect retry cap (2) -> repeated ~200s re-fetches of the same aspect.
P1-2 Checklist over-generates gaps / weak scope-anchoring: even a single-fact question
     yields 3-5 'deficiencies'. _screen_status_lines does not bound topical over-reach.
     Driver of P0-1.
P1-3 Wall budget not enforced mid-turn: thin elapsed 663s with PG_OUTLINE_AGENT_WALL_SECONDS
     =420. Loop checks wall only between turns; a 218s in-flight search overshoots. The
     hard-wall runaway defense is porous.

## P2/P3
P2-1 new_evidence_count misreports 0 (ev_store aliased + mutated in place; before/after
     lengths both read post-fold). ev_store_size is correct; disclosure undercounts.

## REAL + KEEP (genuinely built, verified)
- id-collision assert present + correct: _offset_renumber raises AssertionError on
  new∩existing; no collision across 6 searches with offset renumber.
- S2 stamp pass runs (content-integrity chrome delete + fail-open topic judge).
- OFF path byte-identical: run_outline_agent_or_legacy early-returns _call_outline with
  identical args when PG_OUTLINE_AGENT unset/0.
- W0 un-starve in diff: outline_lab 2500->PG_OUTLINE_MAX_TOKENS(131072); reasoning
  6144->32768.
- Faithfulness engine untouched: outline agent only enlarges the corpus; strict_verify/
  NLI run downstream at composition, unchanged.

## FIX DIRECTION (iter 2)
1. After a successful search_more_evidence, AUTO-ASSIGN surviving new ev_ids to the
   triggering (section) via a reassign/add op (or force the decide loop to call
   update_outline before re-running the after-fold checklist). Then the checklist can
   actually clear the gap and the loop converges + the outline mutates.
2. Constrain the checklist to the ACTUAL research question scope so a single-fact Q
   yields NONE (fix the negative control at the source). Add a saturation guard: if the
   question is answerable from the seed, checklist returns NONE.
3. Fix dedup to normalize/semantic-match aspects so paraphrases collapse to one todo and
   the retry cap bites.
4. Enforce the wall budget around the in-flight search, not just between turns.
5. Harness bug: valid_negative_control must assert search_more_evidence_calls==0.
