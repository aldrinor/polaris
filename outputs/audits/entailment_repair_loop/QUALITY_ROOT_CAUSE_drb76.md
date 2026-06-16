# ROOT-CAUSE re-frame from the first COMPLETED report (Q76 gut_microbiota, drb_76 walled, 2026-06-16 ~07:57)

The first walled run to FINISH (status=released_insufficient_safety_evidence, $7.32, 107 lines vs gpt 167 / gemini
182) is REAL but THIN — it would NOT beat both. Its own Methods + disclosures name the causes, and they are
QUALITY, not the entailment SPEED we were chasing. Priority order:

1. **FETCH CATASTROPHE (dominant):** report line 47 — "Retrieval fetch outcome: **29 of 740 candidate sources
   fetched; 711 failed or timed out.**" The corpus is starved ~96% BEFORE generation. (Earlier logs: mass
   `trafilatura SSL CERTIFICATE_VERIFY_FAILED`, `Page.goto Timeout 30000ms`, anti-bot ACS-GOTO failures.) Only 5
   sources survive into the bibliography; 0 multi-source corroborated. NOTE: drb_72 earlier fetched 831 — so fetch
   yield is HIGHLY VARIABLE per question; Q76's URL set fetched terribly. Need a fetch-layer forensic: why 711/740
   fail, and is it systemic or per-question.
2. **strict_verify OVER-DROP:** report line 83 — "36 claims REMOVED... entailment_failed: 8,
   **no_content_word_overlap_any_cited_span: 26**, no_integer_overlap: 12." The content-word-overlap rule (the
   operator-suspected over-strict matcher) drops 26 claims. Combined with a 29-source corpus = fragments.
3. **NO BASKET REPAIR (PART B):** dropped claims become FRAGMENTS ("Efficacy. Exposure: dietary fibre.[1]") instead
   of being re-anchored to a sibling basket member or softened+disclosed. This is the §-1.3 Principle-3 gap the
   workflow already identified (rewrite_already_attempted is a phantom flag).
4. **Contract topics unmet:** 5/5 required entities (Probiotic-CRC-RCT, Prebiotic-SCFA-meta, Fusobacterium-CRC,
   Colibactin-pks-Ecoli, immunocompromised-contraindication) "not verified in this run."

## SECONDARY (speed) — real but NOT the beat-both lever
- Entailment runs SERIAL (A1 PG_PARALLEL_VERIFY) — makes a thin report arrive faster, not better.
- NEW: the per-source CREDIBILITY pass is a SECOND serial loop that can trickle-HANG (the a1smoke hung there 11min,
  cpu 0.6%, ep_poll, never reached entailment) — needs the same HANG-J3 total-deadline guard + parallelization.

## REVISED PRIORITY (what actually produces beat-both)
A. **FETCH reliability** — forensic the 711/740 failures; raise fetch success (retry/backoff, Zyte fallback wiring,
   relax SSL-verify for cert-expired hosts, anti-bot handling). DOMINANT quality lever. (Honors §-1.3 weight-not-filter:
   more sources fetched = richer baskets.)
B. **strict_verify over-drop** — the content-word-overlap matcher drops salvageable claims; soften via basket repair
   (PART B), NOT by relaxing the gate. Faithfulness preserved (basket may only downgrade/label).
C. **PART B basket repair loop** — re-anchor/soften dropped claims instead of fragmenting.
D. **Speed (A1/A2 + credibility-pass parallel/timeout)** — supporting, so the fix→test loop is fast.

Faithfulness NEVER relaxed: A/B/C all STRENGTHEN grounding (more real sources, basket-verified re-anchors). The fix
is bigger and different than the entailment-speed plan — re-aim the Codex iteration here.
