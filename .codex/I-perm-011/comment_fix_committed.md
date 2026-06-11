## Fix committed a030b024 — Codex APPROVE (0 P0/P1/P2) — drb_76 re-run live

**Root cause (measured on the live run):** the 0.30 relevance floor in evidence_selector normalized
lexical overlap by the WHOLE ~73-token research question, so it demanded ~22 exact content-word matches
and DROPPED 74 on-topic T1 clinical papers (Nature/Cell/Gut/PMC CRC-microbiota) on vocabulary mismatch.
drb_76: 597 extracted -> only 53 reached the generator.

**Fix:** score each row against its BEST-MATCHING decomposed sub-query (small per-facet denominators);
floor = max(whole-question, best-facet). Flag PG_SELECT_SUBQUERY_FLOOR (default OFF, force-on in Gate-B
slate). MONOTONIC-UP on the floor path (superset — can only OPEN, never drop a previously-kept row);
tier-balanced + flag-off paths byte-identical. + flag-gated extraction telemetry (total_extracted_rows /
selected_to_generator_initial). Cap-lowering DECLINED (respects operator 2026-06-10 decision: pool 597 <
1500, per-section cap 40 is the binding per-prompt guard). **Faithfulness gates untouched.** 25 targeted +
179 total tests green. Codex APPROVE.

**Secondary (deferred, smaller):** the rerank cull (2689->740) sheds 1949, but 63% are bare doi.org
redirectors (~0 snippet) + ~290 reputable-host tail — a smaller loss than the floor; revisit if drb_76
is still thin after this fix.

drb_76 re-run live on VM (tmux funnel_i1, HEAD a030b024, $100 cap). Expect evidence_selected to jump
from 53 as the 74+ dropped on-topic T1 papers now clear the per-facet floor. §-1.1 audit + judgment to follow.
