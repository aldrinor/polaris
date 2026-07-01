HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

# WS-9b D6 weight-label gate

Review `.codex/I-deepfix-001/ws9b_diff.patch`.

**Context:** the corroboration block and the corpus-disclosure block in `run_honest_sweep_r3.py` both printed a number labelled "credibility weight"; the trace determined they hold the SAME quantity, so NO code change was made.

**Trace proof (verify soundness):**
- Corroboration block (`run_honest_sweep_r3.py:2697`) reads `BasketMember.credibility_weight`, projected verbatim at `provenance_generator._basket_for_biblio:3352`.
- Disclosure block (`run_honest_sweep_r3.py:2934`) reads `cwf_disclosed_sources.credibility_weight`, set at `weighted_enrichment.py:537` `best_cred_weight` = per-eid MAX of the SAME `BasketMember.credibility_weight` (`weighted_enrichment.py:437`).
- `EvidenceCredibility` is keyed per `evidence_id` (`credibility_pass.py:817`), so all same-eid members carry one value → the per-eid MAX is a no-op → both blocks read the identical POST-P3 authority-adjusted credibility weight (`clamp01(P2 credibility-judge weight x supersession multiplier)`).
- NEITHER block reads a raw `tier_prior`. The `tier_prior`-or-`authority_score` field is a DIFFERENT object, `weighted_corpus_gate.SourceWeight.credibility_weight` (docstring lines 140/366), consumed by NEITHER render block.
- The plan's claim (one label ~0.08 authority-adjusted, one ~0.30/0.95 raw tier_prior) is NOT supported by the code. Both labels ('each source's credibility weight' at line 2722, 'near-zero credibility weight' at line 2943) correctly name the SAME authority-adjusted quantity. The disclosed sources merely show near-zero VALUES because they are the low-weight demoted set — not a different metric.

**CONFIRM:**
(a) faithfulness-neutral — no number / verdict / gate / weight-computation changed, only label TEXT (here: no change at all).
(b) each label already accurately names its quantity (no NEW mislabel introduced or left standing).
(c) frozen engine untouched — `git diff --name-only` over `strict_verify` / `provenance_generator` / `nli_verifier` / `role_pipeline` / `judge_adapter` / `four_role` / `credibility_pass` is EMPTY.
(d) §-1.3 no drop/cap introduced.

Since `quantities_differ=false` and no change was made, `verdict: NO_CHANGE_NEEDED` is acceptable IF the trace proof is sound. If you find the two labels actually name DIFFERENT quantities (i.e. the trace proof is wrong and a disambiguation IS required), return `REQUEST_CHANGES` and name the exact divergence with file:line evidence.

**Output YAML (last block wins):**
```yaml
verdict: APPROVE | REQUEST_CHANGES | NO_CHANGE_NEEDED
faithfulness_neutral: true | false
label_accurately_names_quantity: true | false
novel_p0: [..]
p1: [..]
summary: <one line>
```
