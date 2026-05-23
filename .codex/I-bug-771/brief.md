# Codex DECISION request — I-bug-771 (#812): tier-classifier mis-tiers authoritative sources -> corpus_inadequate

You are the DECISION-MAKER (CHARTER §1: Codex decides, Claude executes). Decide
the fix approach + guardrails + verification. Clinical-safety-adjacent: source
tiering drives the corpus-adequacy gate AND the brief's evidence base.

## Problem (DOMINANT #763 benchmark reliability blocker)
`abort_corpus_inadequate` is the dominant abort (3 of 6 vectors so far: afib,
long-context, rag). The clinical template requires T1>=3, T2>=2.

## Confirmed root cause: tier-CLASSIFICATION, not retrieval reach
Retrieval finds excellent high-tier sources; the content-based tier_classifier
(src/polaris_graph/retrieval/tier_classifier.py — tiers by content/study-type/
OpenAlex metadata, NOT a domain allow-list) MIS-TIERS them. From the afib
live_corpus_dump (20 sources retrieved):

| source | should be | classifier gave |
|---|---|---|
| ahajournals.org (JAHA, Circulation) | T1/T2 | T7 |
| escardio.org/guidelines (ESC guidelines) | T1 | T4 |
| jacc.org / acc.org (JACC, ACC) | T1/T2 | T4 |
| pmc.ncbi.nlm.nih.gov (PubMed Central) | T1/T2 | T4 |
| mdpi.com (low-quality OA) | ~T4 | T1 (backwards) |

So it's NOT reach and NOT scarcity — the content classifier fails to recognize
peer-reviewed cardiology journals + recognized guideline bodies as T1/T2 (and
over-credits MDPI-class OA to T1). Net: T1/T2 minimums unmet -> abort.

(The classifier deliberately tiers PMC/PubMed "by content, not domain" — comment
at tier_classifier.py:132. The content path is what's failing here.)

## Fix options (decide one or combination)
- **A. Authoritative-source allow-list OVERLAY:** a curated, defensible set of
  recognized high-tier domains (e.g. NEJM, Lancet, JAMA, BMJ, JACC, ahajournals,
  Circulation, Cochrane; guideline bodies ESC/ACC/AHA/NICE; for CS: arXiv/ACL/
  NeurIPS) that sets a T1/T2 FLOOR when the content classifier under-tiers them.
  Pro: deterministic, fixes the demo vectors. Con: curation burden; must be
  defensible (these ARE authoritative).
- **B. Fix the content-signal logic:** improve study-type / venue / OpenAlex
  detection so these are recognized as peer-reviewed primary/review or guidelines.
  Pro: generalizes. Con: harder, may not catch guideline bodies.
- **C. Both:** allow-list floor for recognized authoritative venues + content
  signal for the long tail.
- **D. Also DEMOTE MDPI-class OA** (the precision problem in the other direction).
- **NOT relaxing the adequacy thresholds** without clinical-safety review
  (under-sourced clinical briefs are the risk).

## Hard constraints
- Do NOT degrade precision (don't over-credit low-quality OA / predatory venues
  to T1/T2).
- Tiering is clinical-safety-relevant; the allow-list (if used) must be a
  defensible authoritative-venue set, not "whatever makes the demo pass."

## Decide + return
1. Approach (A/B/C/D/combination)? Why, given clinical-safety + precision?
2. Guardrails + the invariant to assert in tests (e.g. AHA/JACC/ESC -> T1/T2;
   MDPI not T1; predatory venues stay low).
3. Verification: re-run which vectors, what pass bar (reach T1>=3/T2>=2 + ship)?
4. Anything mis-diagnosed?

Return a decision, not a menu.
