# R-3 cross-domain sweep — summary matrix

| Domain | Slug | Status | Sources | Verified | Words | Rule checks | Judge good/accept/revise | Cost USD | Wall s |
|---|---|---|---|---|---|---|---|---|---|
| clinical | clinical_tirzepatide_t2dm | ok_thin_corpus | 20 | 22 | 634 | 13/13 | 5/0/0 | 0.0013 | 231.6 |
| clinical | clinical_afib_anticoagulation | ok_thin_corpus | 20 | 17 | 535 | 13/13 | 4/0/1 | 0.0013 | 315.9 |
| policy | policy_fda_ai_devices | abort_corpus_inadequate | 27 | ? | ? | ?/0 | 0/0/0 | 0.0000 | 203.4 |
| policy | policy_medicare_drug_price | ok | 20 | 17 | 581 | 12/13 | 5/0/0 | 0.0014 | 211.0 |
| tech | tech_rag_architectures_2024 | abort_corpus_inadequate | 20 | ? | ? | ?/0 | 0/0/0 | 0.0000 | 128.8 |
| tech | tech_long_context_transformer | abort_corpus_inadequate | 20 | ? | ? | ?/0 | 0/0/0 | 0.0000 | 137.2 |
| due_diligence | dd_novo_nordisk_obesity_position | abort_corpus_inadequate | 20 | ? | ? | ?/0 | 0/0/0 | 0.0000 | 311.9 |
| due_diligence | dd_lilly_tirzepatide_manufacturing | abort_corpus_inadequate | 16 | ? | ? | ?/0 | 0/0/0 | 0.0000 | 230.0 |

**Total sweep cost: $0.0041**
**Per-query budget cap: $0.1000**

## Per-query notes

### clinical / clinical_tirzepatide_t2dm
- Question: What is the efficacy and safety of tirzepatide for glycemic control and weight loss in adults with type 2 diabetes?
- Status: **ok_thin_corpus**
- Artifacts: `outputs\sweep_r3_final\clinical\clinical_tirzepatide_t2dm`

### clinical / clinical_afib_anticoagulation
- Question: What are current clinical guidelines for oral anticoagulation in adults with non-valvular atrial fibrillation?
- Status: **ok_thin_corpus**
- Artifacts: `outputs\sweep_r3_final\clinical\clinical_afib_anticoagulation`

### policy / policy_fda_ai_devices
- Question: How is the FDA regulating AI-enabled medical devices under the current Predetermined Change Control Plan framework?
- Status: **abort_corpus_inadequate**
- Error: `Corpus fails 1 critical threshold(s): ['t1_plus_t2']. Refusing to synthesize a confident report; caller should expand retrieval substantially or ABORT.`
- Artifacts: `outputs\sweep_r3_final\policy\policy_fda_ai_devices`

### policy / policy_medicare_drug_price
- Question: What is the impact of Medicare drug-price negotiation under the Inflation Reduction Act on drug list prices and access?
- Status: **ok**
- Artifacts: `outputs\sweep_r3_final\policy\policy_medicare_drug_price`

### tech / tech_rag_architectures_2024
- Question: What are the current best practices for retrieval-augmented generation architectures as of 2024-2025?
- Status: **abort_corpus_inadequate**
- Error: `Corpus fails 3 critical threshold(s): ['t1_count', 't1_plus_t2', 't1_plus_t2_plus_t3']. Refusing to synthesize a confident report; caller should expand retrieval substantially or ABORT.`
- Artifacts: `outputs\sweep_r3_final\tech\tech_rag_architectures_2024`

### tech / tech_long_context_transformer
- Question: What techniques extend transformer context length beyond 128K tokens while preserving recall quality?
- Status: **abort_corpus_inadequate**
- Error: `Corpus fails 2 critical threshold(s): ['t1_plus_t2', 't1_plus_t2_plus_t3']. Refusing to synthesize a confident report; caller should expand retrieval substantially or ABORT.`
- Artifacts: `outputs\sweep_r3_final\tech\tech_long_context_transformer`

### due_diligence / dd_novo_nordisk_obesity_position
- Question: What is Novo Nordisk's competitive position in the obesity pharmaceutical market relative to Eli Lilly and newer entrants?
- Status: **abort_corpus_inadequate**
- Error: `Corpus fails 3 critical threshold(s): ['t1_count', 't1_plus_t2', 't1_plus_t2_plus_t3']. Refusing to synthesize a confident report; caller should expand retrieval substantially or ABORT.`
- Artifacts: `outputs\sweep_r3_final\due_diligence\dd_novo_nordisk_obesity_position`

### due_diligence / dd_lilly_tirzepatide_manufacturing
- Question: What is the current state of Eli Lilly's tirzepatide manufacturing capacity and supply outlook?
- Status: **abort_corpus_inadequate**
- Error: `Corpus fails 1 critical threshold(s): ['t1_plus_t2']. Refusing to synthesize a confident report; caller should expand retrieval substantially or ABORT.`
- Artifacts: `outputs\sweep_r3_final\due_diligence\dd_lilly_tirzepatide_manufacturing`

