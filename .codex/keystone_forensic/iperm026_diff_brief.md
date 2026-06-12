# Codex DIFF-gate — #1218 keystone thinness fix (MAP on-topic exhaustiveness + REDUCE one-stat-per-sentence + ev_-prefix marker normalization)

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings. Same quality bar. Reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on remaining-non-P0/P1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## What & why
Parent: keystone collapse #1217 fixed+committed (8d74d1bb). This diff fixes #1218 THINNESS: the distilled "Safety and contraindications" section was faithful but ~2 verified sentences vs legacy ~6. The diff is in `src/polaris_graph/generator/evidence_distiller.py` (+ a test). Read ONLY that file + `tests/polaris_graph/generator/test_evidence_distiller_iperm016.py` + the diff at `.codex/keystone_forensic/iperm026_diff.patch` — do NOT grep the whole repo (access-denied codex_* temp dirs crash exploration). strict_verify / `_find_best_span_for_sentence` / 4-role / D8 are byte-UNCHANGED; every change is MAP-extraction-side or REDUCE-output-shaping-side.

## Changes
1. `_MAP_SYSTEM` + `_render_map_user`: EXHAUSTIVE-BUT-STRICTLY-ON-TOPIC extraction — extract every distinct ON-TOPIC finding (incl. every on-topic numeric outcome) as its own atomic finding; each finding's support_quote must be a CONTIGUOUS source slice containing every number (split scattered numbers). EXPLICIT scope guard: for a safety section ON-TOPIC = harms/adverse-events/contraindications/toxicity/infections/risks of THE INTERVENTION; OFF-TOPIC = general disease-causation/carcinogenesis mechanisms -> no_relevant_findings. (An earlier un-scoped "exhaustive" version over-extracted 19 off-topic bile-acid-carcinogenesis sentences; this scope guard fixed it.)
2. `_REDUCE_SYSTEM` + `render_reduce_user`: USE EVERY finding (>=1 sentence each, co-cite duplicates); ONE numeric statistic per sentence (no multi-source numeric conjunctions) so numbers bind to one span; rewrite source bracket abbreviations ([OR]/[CI]/[RR]) to parentheses; copy the ledger cite=[...] marker EXACTLY (no added/removed prefix).
3. `filter_and_strip_reduce_markers`: NEW `_normalize_ev_prefix` — the evidence pool is inconsistent (457/462 ids start with "ev_", a few key safety ids do NOT); the REDUCE sometimes adds/drops an "ev_" prefix so the marker fails to resolve and strict_verify drops the faithful sentence. Normalize a bare marker to the REAL ledger evidence_id (add/drop "ev_" to match a known id). Faithfulness-safe: only rewrites to a genuine pool/ledger id; the final strict_verify still validates the span.
4. `DISTILLER_VERSION` v4->v7 (cache invalidation for the prompt/logic changes).
5. Tests: new `test_filter_normalizes_ev_prefix_mismatch_1218`; 22/22 distiller + 100/100 generator pass.

## Live result (clean fresh-cache MAXEV=8 A/B, deepseek-v4-pro, OVH VM)
distilled verified 2->13 vs legacy 7 (drop_rate 0.50->0.13). Ledger=15, ALL from the CDC safety source (on-topic). §-1.1 line-by-line on the 13 distilled sentences = ZERO fabrication: every number traced to the source (S. boulardii fungemia OR 14 (95% CI 4-44); case-fatality 22%/37%; "at least 20 (43%) of 46 fungemia patients using the probiotic"; antifungal changed for 23 (50%); the contraindications; the septic-shock death). One sentence redundantly restates the OR-14 (minor quality nit from "use every finding", NOT a faithfulness defect; the attribution is correct — OR 14 is for the bacteremia/candidemia controls, distinct from the nonblood OR 10 which the distiller did not confuse).

## Questions
1. Any correctness bug in `_normalize_ev_prefix` (could it mis-resolve a marker to the WRONG source)? It only rewrites when the prefixed form is NOT a known id and the unprefixed form IS (or vice versa).
2. Is the on-topic scope guard in `_MAP_SYSTEM` sound, or could it cause a safety source to be wrongly skipped (return no_relevant_findings for genuinely on-topic content)?
3. Faithfulness: do any of the prompt/shaping changes create a path for unfaithful content to pass the UNCHANGED strict_verify?
4. The "use every finding" instruction can produce a redundant duplicate sentence (the OR-14 restated). Acceptable as a minor follow-up, or should the REDUCE de-duplicate?
5. Mergeable now (thinness resolved: distilled >= legacy on-topic, §-1.1 clean), or any blocker?

## OUTPUT SCHEMA
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
faithfulness_risk: [...]
mergeable_now: true | false
convergence_call: continue | accept_remaining
```
