# I-wire-014 FIX-B/C/D — benchmark winners (data-picked, faithfulness-gated) 2026-06-27

Discriminator (per §-1.1, NOT metric-as-quality): the **faithfulness asymmetry** —
over-merge (collapse a distinct claim) / over-drop (delete real content) = LETHAL = AUTO-DISQUALIFY
(preserve-rate MUST = 1.0). Removing chrome / collapsing a true repeat = graded.
Winner = highest graded score among candidates that hold preserve-rate = 1.0.

## CHROME (FIX-B/C) — winner: `extended_deterministic` (whole-unit-collapse)
Gold: `chrome_gold_augmented.json` (686 items: 128 chrome / 558 content; body-prose augmented, labeled blind to the regexes).

| candidate | new-class removal | content_preserved | gate |
|---|---|---|---|
| incumbent `clean_fetch_body` | 0.081 (3/37) | 1.0 | baseline |
| **extended_deterministic** | **0.324 (12/37)** | **1.0** | ✅ WINNER |
| extended + symspell | 0.324 (ties; dehyph is repair not removal) | 1.0 | helper-only |

- First (aggressive) extended design scored 0.117 all-chrome but gutted 2 welded-mid-prose content spans (preserved 0.9964) → **DISQUALIFIED**. Fix = **whole-unit-collapse-only**: strip furniture tokens only to TEST furniture-dominance; if residue < 4 alphabetic words → suppress unit; else return UNCHANGED → preserve=1.0 by construction.
- **Layered implementation** (advisor-corrected — the gold is the RENDERED report, so it validated the RENDER-SEAM semantics, not inline clean_fetch_body strip):
  - (A) render-seam `is_render_chrome_or_unrenderable` (weighted_enrichment.py): whole-unit-collapse + new generalizable furniture signatures (Journal Metrics / email-alerts / Web of Science / Crossref / References Biographies / Cite·Cite / Download-to-ref / rights-permissions / JEL Classification / Associated Records / access-through-org / Section snippets / Member-only / What-you'll-learn / Feature Story / cookie-geo banner / access-challenge / back-matter LABEL RUN). DEDUP vs existing _SHARED_RENDER_CHROME_RE/_MASTHEAD_CHROME_RE. EXCLUDE overfit single-source literals.
  - (B) `clean_fetch_body` (access_bypass.py): add ONLY self-contained WHOLE-LINE furniture (no unit-level partial strips here).
  - (C) SymSpell dehyphenation helper (standalone input hygiene): rejoin "Governan; ce"→"Governance" only when wordfreq zipf(joined)≥3.0 AND not both parts already words (preserves "high risk"/"short- and long-term"/"routine- replacing"/"up- and reskilling").
- **GATE LAW for the PR:** content_preserved_rate MUST stay 1.0 on `chrome_gold_augmented.json` (run `chrome_benchmark.py`); any rule dropping it = AUTO-REJECT (precision over recall on the drop path, §-1.3).

## DEDUP (FIX-D) — winner: mutual-entailment NLI (`PG_CONSOLIDATION_NLI_PROSE`)
Gold: `dedup_gold.json` (63 items: 41 keep / 22 paraphrase_repeat).

| candidate | repeats collapsed | distinct preserved | gate |
|---|---|---|---|
| keep_all | 0% | 1.0 | baseline |
| exact_text + set-cites | 13.6% | 1.0 | pass |
| jaccard 0.82 + set-cites + number-guard | 18.2% | 1.0 | pass |
| **mutual-entailment NLI + set-cites + number-guard** | **54.5% (12/22)** | **1.0** | ✅ WINNER |
| naive cosine 0.82 (no guards) | 90.9% | **0.90 (dropped 4 distinct)** | ❌ DISQUALIFIED |

- Cosine/embedding over-merges (drops distinct claims) → demoted to comparison row, proven empirically.
- Winner = mutual-entailment NLI (`cross-encoder/nli-deberta-v3-base`, VM GPU): merge two units only if entailment is argmax in BOTH directions AND same citation-SET AND no new number → semantic equivalence (safe failure mode). The set-cite + number-guard keep preserve=1.0.
- **Layered implementation:** enable in-tree `PG_FACT_DEDUP_PROSE` (Jaccard pre-filter) + `PG_CONSOLIDATION_NLI_PROSE` (NLI confirmer) at the `multi_section_generator` dedup_pass; PLUS a writer-side "state each distinct claim once" constraint in `abstractive_writer.py` for the residual ~45% (root-cause prevention).
- Run on the VM GPU only (deBERTa load; never local per §8.4).

## Artifacts (outputs/audits/iwire014/benchmark/)
chrome: chrome_gold_augmented.json, chrome_candidates.py, chrome_benchmark.py, chrome_benchmark_results.json, CHROME_BENCHMARK_RESULTS.md, prove_symspell.py
dedup: dedup_gold.json, dedup_benchmark.py, dedup_extra_candidates.py, DEDUP_BENCHMARK_RESULTS.txt
research: research_synthesis.json (33 candidates, 4 agents); vm_env_audit.md
