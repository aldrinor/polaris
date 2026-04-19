# 8-query sweep output index (cycle 3, post-M-10)

### clinical_afib_anticoagulation
- status: partial_thin_corpus  release: True
- tier_fractions: {'T1': 0.15, 'T3': 0.05, 'T4': 0.45, 'T7': 0.35}
- gate.reasons: []
- path: outputs/sweep_r3_final/clinical/clinical_afib_anticoagulation

### clinical_tirzepatide_t2dm
- status: partial_thin_corpus  release: True
- tier_fractions: {'T1': 0.2, 'T3': 0.05, 'T4': 0.2, 'T5': 0.05, 'T7': 0.5}
- gate.reasons: []
- path: outputs/sweep_r3_final/clinical/clinical_tirzepatide_t2dm

### dd_lilly_tirzepatide_manufacturing
- status: abort_corpus_inadequate  release: None
- tier_fractions: {'T1': 0.0625, 'T3': 0.0625, 'T4': 0.1875, 'T5': 0.25, 'T6': 0.375, 'UNKNOWN': 0.0625}
- gate.reasons: []
- path: outputs/sweep_r3_final/due_diligence/dd_lilly_tirzepatide_manufacturing

### dd_novo_nordisk_obesity_position
- status: abort_corpus_inadequate  release: None
- tier_fractions: {'T4': 0.05, 'T5': 0.5, 'T6': 0.35, 'UNKNOWN': 0.1}
- gate.reasons: []
- path: outputs/sweep_r3_final/due_diligence/dd_novo_nordisk_obesity_position

### policy_fda_ai_devices
- status: abort_corpus_inadequate  release: None
- tier_fractions: {'T1': 0.037, 'T3': 0.3333, 'T4': 0.1852, 'T5': 0.1111, 'T6': 0.0741, 'T7': 0.2593}
- gate.reasons: []
- path: outputs/sweep_r3_final/policy/policy_fda_ai_devices

### policy_medicare_drug_price
- status: success  release: True
- tier_fractions: {'T1': 0.2, 'T3': 0.15, 'T4': 0.25, 'T7': 0.35, 'UNKNOWN': 0.05}
- gate.reasons: ['advisory_pt13_unhedged_superlatives']
- path: outputs/sweep_r3_final/policy/policy_medicare_drug_price

### tech_long_context_transformer
- status: abort_corpus_inadequate  release: None
- tier_fractions: {'T1': 0.05, 'T4': 0.75, 'T6': 0.1, 'T7': 0.05, 'UNKNOWN': 0.05}
- gate.reasons: []
- path: outputs/sweep_r3_final/tech/tech_long_context_transformer

### tech_rag_architectures_2024
- status: abort_corpus_inadequate  release: None
- tier_fractions: {'T4': 0.7, 'T5': 0.05, 'T6': 0.25}
- gate.reasons: []
- path: outputs/sweep_r3_final/tech/tech_rag_architectures_2024

