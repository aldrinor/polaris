HARD ITERATION CAP: 5 per document. This is iter 5 of 5 (the cap — if this returns REQUEST_CHANGES the doc is force-APPROVE'd on remaining non-P0/P1 per CLAUDE.md §8.3.1).

## ITER-5 CHANGE — the single iter-4 P1 fixed; rule set is now 3 precision-safe rules, the author rule made multi-signal
Iter-4 returned REQUEST_CHANGES with ONE P1: `_AUTHOR_ATTRIB_RE` was phrase-only and would flag a real
research-integrity finding ("X is listed as an author on the retracted paper"). FIXED by splitting it into
TWO required signals (both must co-occur):
- `_AUTHOR_ATTRIB_PHRASE_RE` — the authorship phrase ("is listed as an author", "are among the listed authors").
- `_MASTHEAD_PORTAL_STATS_RE` — an article-portal MASTHEAD engagement-stats co-signal ("article has received",
  "N accesses|altmetric|citations").
The helper now flags author-attribution ONLY when BOTH co-occur — anchoring it to the masthead block
("Gazdag is listed as an author. The article has received 3258 accesses, 16 citations…"). A real integrity/COI
finding ("X is listed as an author on the retracted paper") has NO portal-stats co-signal → KEPT.
Iter-4 already CONFIRMED `_AFFIL_GLUED_RE` and `_TITLE_AFFIL_RE` are precision-safe (no change to them).

RE-VALIDATED (offline, real data): 0/398 curated-clean content false-positives (CONTENT-PRECISION=1.0000 on
the official gate). Masthead examples caught (Gazdag+stats; "Tuda1, 2 …Department of Economics"; "A Survey of … - 1 Department of"). ALL adversarial real-finding cases KEPT:
- "X is listed as an author on the retracted paper that was later corrected" (the iter-4 P1 case) — KEPT.
- "Smith is listed as an author and the study found a 30% reduction in mortality" — KEPT.
- "Smad1, 5 and Smad2, 3 signaling pathways" (titlecase gene notation) — KEPT.
- "Papers averaged 12 altmetric mentions and 40 citations in the bibliometrics study" — KEPT.
- "Vascular accesses numbered 1240 across the cohort" — KEPT.

## ITER-1..4 history (context)
- iter-1 P1s: stats "accesses"/"altmetric"; affil "Laborator"; biblio date+page — fixed (co-signal/anchor) or dropped.
- iter-2 P1s: downloads/views are real outcomes; gene notation; scattered date+page — fixed/dropped.
- iter-3 P1s: Smad mouse gene; bibliometrics stats — DROPPED those rules (left to canary).
- iter-4 P1: author-attribution phrase flags a real integrity finding — fixed in iter-5 (multi-signal, above).
The DROPPED classes (biblio date+page, bibliometric stats, "Name<digit>, <digit>" superscript) are left to the
chrome-as-claim canary (enforce, floor 0.05) per §-1.3 (precision over recall — never risk dropping a real finding).

REVIEW MODE: STATIC only. No pytest/pipeline/user-input/broad-exploration. Read the diff + the function it extends. Emit the verdict schema at the end.

# I-wire-016 #1338 — render-seam predicate gap-fill (3 high-precision furniture rules)

## This is a §-1.3 WEIGHT/WITHHOLD screen (chrome withheld from the rendered rollup, KEPT in evidence; faithfulness engine UNCHANGED). PRECISION is the binding constraint — it must NEVER flag a real research finding. Review for that.

## Context
#1338 §-1.1-clean: the render-seam screen (`is_render_chrome_or_unrenderable` -> `_contains_forensic_chrome`, called by `sanitize_rendered_report`) leaks chrome classes the legacy categories miss. The OSS survey (3 agents, 2025/26) confirmed NO fetch-time HTML extractor fits the render seam (extracted-text units, precision-first, banked replays). A fuzzy ML classifier was empirically refuted (7-15% real-content drop). The fix extends the deterministic predicate.

## The change (the ONLY diff — `.codex/I-wire-014/iwire016_gapfill.diff`, weighted_enrichment.py)
Adds `_contains_iwire016_gap_furniture(s)` (called at the END of `_contains_forensic_chrome`, after the existing categories) with 3 structure-anchored rules:
- `_AFFIL_GLUED_RE`: a digit GLUED to an affiliation-PREPOSITION institution ("2Department of", "1Institute of", "3Laboratory of"). Anchored to the preposition so "2Laboratory-confirmed cases" / "1Institutional review boards" never match.
- `_TITLE_AFFIL_RE`: dash + digit + institution ("A Survey of … - 1 Department of …").
- author-attribution masthead = `_AUTHOR_ATTRIB_PHRASE_RE` AND `_MASTHEAD_PORTAL_STATS_RE` (BOTH required): the authorship phrase co-occurring with article-portal engagement stats. The phrase alone is NOT enough (iter-4 P1).

## VALIDATION (offline, on real data)
- §-1.3 PRECISION: the 3 gap rules flag 0 of 398 curated-clean real-content units. Official acceptance gate (scripts/iwire016_acceptance_test.py): CONTENT-PRECISION = 1.0000 (398/398 kept) with these rules live.
- RECALL: the affiliation/title-affil/author-masthead gap-class examples (the real leaked units from reconfirm3) are caught. (Offline overall chrome-recall is under-measured because the harness runs known_words=None so the EXISTING corpus-truncation leg is inert; production runs WITH the corpus. End-to-end recall is confirmed by the reconfirm, not this offline gate.)

## Things to verify (be adversarial — precision is the §-1.3 line)
1. Can ANY of the 3 rules flag a real finding? Walk each: affil-glued (digit+preposition-institution, no space); title-affil (dash+digit+institution); author-masthead (authorship phrase AND portal-stats, both required). Is there a real clinical/economics sentence shape that matches?
2. author-masthead multi-signal: is requiring BOTH the authorship phrase AND a portal-stats co-signal sufficient to avoid flagging a real research-integrity / COI finding? Is there a real sentence that names an author AND legitimately reports "N citations"/"N accesses"? (e.g. a bibliometrics finding — does it use the "is listed as an author" phrasing?)
3. The rules are ADDITIVE (only fire if the legacy categories didn't already). No change to faithfulness gates, no DROP from evidence (withhold-from-rollup only). Confirm.
4. Regexes compile (py_compile passed) and are named module constants (LAW VI / §9.4).

## Output schema (REQUIRED, last lines)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
