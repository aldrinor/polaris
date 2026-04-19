---
verdict: APPROVED-FOR-FULL-SCALE-RUN
pass: 16
cycle: 10
tier_label_hallucinations: 3
pipeline_honest_by_construction: true
ready_for_production_with_caveats: true
rationale: |
  Cycle 10 is approvable for a full-scale run because the pipeline now mostly fails closed: seven thin-corpus queries abort before synthesis, and the only synthesized report is held as partial_qwen_advisory rather than released. The remaining T1 hallucinations are narrow R10 fallback promotions on PMC clinical guidance/perspective pages, not broad domain pollution, and they do not create a released clean report. Qwen's partial advisory on the AFib report is conservative and partly noisy, but it is not a pipeline defect because the gate blocks release and the cited prose remains resolving and verification-backed. Production use should document that partial outputs are advisory only and that residual low-confidence R10 biomedical PMC labels remain a known tier-accounting caveat.
---

## Verdict

APPROVED-FOR-FULL-SCALE-RUN, with documented caveats.

The cycle-10 behavior is the intended honest-by-construction shape: thin corpora are refused, generated content stays citation-resolved, and the only synthesized report is not promoted to a clean release because Qwen flagged it. I do not see a material content defect that should block a full-scale run.

## Evidence Reviewed

- Sweep artifacts: `outputs/sweep_r3_final`
- Summary: `outputs/sweep_r3_final/sweep_summary.md`
- Partial report: `outputs/sweep_r3_final/clinical/clinical_afib_anticoagulation/report.md`
- Qwen output: `outputs/sweep_r3_final/clinical/clinical_afib_anticoagulation/qwen_judge_output.json`
- Corpus dumps and adequacy files for all 8 queries.

Cycle 10 status matrix matches the prompt: `clinical_afib_anticoagulation` is `partial_qwen_advisory` with cost `$0.00101691`, 21 verified sentences, 3 dropped sentences, 632 generator words, 13/13 rule checks, and Qwen 3 good / 0 acceptable / 2 needs_revision. The other seven queries are `abort_corpus_inadequate` with `$0.0000` LLM-generation cost.

## T1 Hallucinations

I count 3 remaining false T1 labels, all narrow R10 fallback promotions on biomedical PMC pages:

| slug | URL | observed | expected | why non-blocking |
|---|---|---:|---:|---|
| `clinical_afib_anticoagulation` | `https://pmc.ncbi.nlm.nih.gov/articles/PMC12566413/` | T1 | T4 | Known clinical prescribing/guidance article; in corpus only, not cited in the partial report bibliography. |
| `clinical_afib_anticoagulation` | `https://pmc.ncbi.nlm.nih.gov/articles/PMC12240022/` | T1 | T4 | Title is "2025 Guidelines for direct oral anticoagulants"; cited in the partial report, but the report is not released. |
| `clinical_tirzepatide_t2dm` | `https://pmc.ncbi.nlm.nih.gov/articles/PMC10115620/` | T1 | T4 | Known perspective/review for primary-care providers; query aborts before synthesis. |

Relevant artifact locations:

- `clinical_afib_anticoagulation/live_corpus_dump.json:31` and `:33` show `PMC12566413` promoted by `R10_journal_domain_presumed_primary`.
- `clinical_afib_anticoagulation/live_corpus_dump.json:108` and `:110` show `PMC12240022` promoted by the same R10 fallback.
- `clinical_tirzepatide_t2dm/live_corpus_dump.json:9` and `:11` show `PMC10115620` promoted by the same R10 fallback.

The remaining false positives are therefore narrower than pass 15: no social, market-research, professional-society tool, truncated-title, PubMed title-only, policy, or tech source is being promoted as T1 in this cycle. Guard 1 is visible on truncated journal titles such as the MDPI tirzepatide source, now T4 via `R10_journal_domain_truncated_title_demoted` at `clinical_tirzepatide_t2dm/live_corpus_dump.json:20`; guard 3 is visible on the ACC DOAC dosing PDF, now T3 via `R10_society_tool_demoted` at `clinical_afib_anticoagulation/live_corpus_dump.json:119`.

## Qwen Advisory

The AFib partial advisory is legitimate conservative gating, not a pipeline defect.

Qwen flags `citation_tightness` and `completeness` in `qwen_judge_output.json:8-13`. The citation-tightness complaint is partly noise: the "nearly 60%" DOAC dosing sentence is cited in the report at `report.md:13` and has provenance in `verification_details.json:263-292`. The "No contradictions were detected" sentence at `report.md:21` is a methods/limitations statement rather than an evidence claim, though adding a manifest-backed citation or omitting the sentence would reduce evaluator noise.

The completeness complaint has substance but is handled honestly: the report explicitly says the Population Subgroups evidence was inaccessible due to technical blocks at `report.md:15-17`. The only mismatch is that the methods still say "Completeness checklist: 6/6 topics covered" at `report.md:33`; because the output is partial/advisory and not released, this is a caveat, not a blocker.

## Abort Legitimacy

The seven aborts are honest refusals. Each refused query has adequate total source volume but fails the high-tier evidence thresholds:

| slug | decision basis |
|---|---|
| `clinical_tirzepatide_t2dm` | T1=1, T1+T2=2, T1+T2+T3=3 against clinical thresholds 3/5/6. |
| `policy_fda_ai_devices` | T1=0 and T1+T2=0 despite 9 T3 sources; conservative but honest under the current policy adequacy contract. |
| `policy_medicare_drug_price` | T1=0 and T1+T2=0, with T7 fraction 0.5. |
| `tech_rag_architectures_2024` | T1=0, T1+T2=0, T1+T2+T3=0; mostly T4/T6/UNKNOWN. |
| `tech_long_context_transformer` | T1=0, T1+T2=0, T1+T2+T3=0; mostly T4/T6/UNKNOWN. |
| `dd_novo_nordisk_obesity_position` | T1=0, T1+T2=0, T1+T2+T3=1; mostly T5/T6. |
| `dd_lilly_tirzepatide_manufacturing` | T1=0, T1+T2=0, T1+T2+T3=0; mostly T5/T6/UNKNOWN. |

The abort reports are clear, short refusal artifacts rather than empty failures: each says the corpus did not meet adequacy thresholds and lists the critical failed thresholds.

## Production Caveats

Document these as non-blocking caveats for full-scale use:

1. Partial/advisory reports are not clean releases. Downstream consumers must treat `partial_qwen_advisory` as gated output.
2. R10 low-confidence biomedical PMC fallback can still over-promote clinical guidance/perspective pages to T1 when title metadata lacks the decisive marker.
3. The AFib template should eventually avoid claiming full completeness when a section says evidence was inaccessible, but the current gate already prevents clean release.

No BLOCKED-ON-ISSUE finding remains for cycle 10.
