# 8-query sweep output index (cycle 2, post-M7+M8)

Generated: 2026-04-19

### clinical_afib_anticoagulation
- domain: clinical
- question: What are current clinical guidelines for oral anticoagulation in adults with non-valvular atrial fibrillation?
- status: success
- release_allowed: True
- cost: $0.0009
- tier_fractions: {'T1': 0.4, 'T4': 0.25, 'T7': 0.35}
- evaluator_gate.reasons: []
  - manifest.json: 2203 bytes
  - report.md: 8081 bytes
  - verification_details.json: 15223 bytes
  - evaluator_rule_checks.json: 2142 bytes
  - qwen_judge_output.json: 2071 bytes
  - run_log.txt: 2052 bytes
  - bibliography.json: 2417 bytes
  - contradictions.json: 4 bytes
  - corpus_adequacy.json: 1413 bytes
  - live_corpus_dump.json: 10753 bytes

### clinical_tirzepatide_t2dm
- domain: clinical
- question: What is the efficacy and safety of tirzepatide for glycemic control and weight loss in adults with type 2 diabetes?
- status: partial_qwen_advisory
- release_allowed: False
- cost: $0.0011
- tier_fractions: {'T1': 0.25, 'T3': 0.05, 'T4': 0.2, 'T5': 0.05, 'T7': 0.45}
- evaluator_gate.reasons: ['qwen_citation_tightness_needs_revision', 'qwen_multi_axis_needs_revision']
  - manifest.json: 2468 bytes
  - report.md: 5705 bytes
  - verification_details.json: 12516 bytes
  - evaluator_rule_checks.json: 2142 bytes
  - qwen_judge_output.json: 2084 bytes
  - run_log.txt: 2249 bytes
  - bibliography.json: 1513 bytes
  - contradictions.json: 1400 bytes
  - corpus_adequacy.json: 1611 bytes
  - live_corpus_dump.json: 10644 bytes

### dd_lilly_tirzepatide_manufacturing
- domain: due_diligence
- question: What is the current state of Eli Lilly's tirzepatide manufacturing capacity and supply outlook?
- status: abort_corpus_inadequate
- release_allowed: None
- cost: $0.0000
- tier_fractions: {'T3': 0.0625, 'T4': 0.1875, 'T5': 0.25, 'T6': 0.4375, 'UNKNOWN': 0.0625}
- evaluator_gate.reasons: []
  - manifest.json: 2699 bytes
  - report.md: 781 bytes
  - run_log.txt: 1038 bytes
  - corpus_adequacy.json: 1662 bytes
  - live_corpus_dump.json: 8452 bytes

### dd_novo_nordisk_obesity_position
- domain: due_diligence
- question: What is Novo Nordisk's competitive position in the obesity pharmaceutical market relative to Eli Lilly and newer entrants?
- status: abort_corpus_inadequate
- release_allowed: None
- cost: $0.0000
- tier_fractions: {'T1': 0.05, 'T5': 0.45, 'T6': 0.3, 'T7': 0.05, 'UNKNOWN': 0.15}
- evaluator_gate.reasons: []
  - manifest.json: 2696 bytes
  - report.md: 821 bytes
  - run_log.txt: 1079 bytes
  - corpus_adequacy.json: 1645 bytes
  - live_corpus_dump.json: 11140 bytes

### policy_fda_ai_devices
- domain: policy
- question: How is the FDA regulating AI-enabled medical devices under the current Predetermined Change Control Plan framework?
- status: partial_qwen_advisory
- release_allowed: False
- cost: $0.0010
- tier_fractions: {'T1': 0.1667, 'T3': 0.3, 'T4': 0.1667, 'T5': 0.0333, 'T6': 0.1, 'T7': 0.2333}
- evaluator_gate.reasons: ['qwen_citation_tightness_needs_revision', 'qwen_multi_axis_needs_revision']
  - manifest.json: 2469 bytes
  - report.md: 8902 bytes
  - verification_details.json: 12036 bytes
  - evaluator_rule_checks.json: 2142 bytes
  - qwen_judge_output.json: 2132 bytes
  - run_log.txt: 2397 bytes
  - bibliography.json: 4569 bytes
  - contradictions.json: 4 bytes
  - corpus_adequacy.json: 1485 bytes
  - live_corpus_dump.json: 10060 bytes

### policy_medicare_drug_price
- domain: policy
- question: What is the impact of Medicare drug-price negotiation under the Inflation Reduction Act on drug list prices and access?
- status: partial_qwen_advisory
- release_allowed: False
- cost: $0.0016
- tier_fractions: {'T1': 0.3448, 'T4': 0.1724, 'T7': 0.3448, 'UNKNOWN': 0.1379}
- evaluator_gate.reasons: ['advisory_pt13_unhedged_superlatives', 'qwen_citation_tightness_needs_revision', 'qwen_multi_axis_needs_revision']
  - manifest.json: 2480 bytes
  - report.md: 7921 bytes
  - verification_details.json: 13741 bytes
  - evaluator_rule_checks.json: 2379 bytes
  - qwen_judge_output.json: 1766 bytes
  - run_log.txt: 2570 bytes
  - bibliography.json: 3048 bytes
  - contradictions.json: 4 bytes
  - corpus_adequacy.json: 1449 bytes
  - live_corpus_dump.json: 10518 bytes

### tech_long_context_transformer
- domain: tech
- question: What techniques extend transformer context length beyond 128K tokens while preserving recall quality?
- status: abort_corpus_inadequate
- release_allowed: None
- cost: $0.0000
- tier_fractions: {'T4': 0.75, 'T6': 0.1, 'UNKNOWN': 0.15}
- evaluator_gate.reasons: []
  - manifest.json: 2635 bytes
  - report.md: 778 bytes
  - run_log.txt: 1040 bytes
  - corpus_adequacy.json: 1632 bytes
  - live_corpus_dump.json: 9000 bytes

### tech_rag_architectures_2024
- domain: tech
- question: What are the current best practices for retrieval-augmented generation architectures as of 2024-2025?
- status: abort_corpus_inadequate
- release_allowed: None
- cost: $0.0000
- tier_fractions: {'T1': 0.05, 'T4': 0.7, 'T5': 0.05, 'T6': 0.2}
- evaluator_gate.reasons: []
  - manifest.json: 2637 bytes
  - report.md: 728 bytes
  - run_log.txt: 986 bytes
  - corpus_adequacy.json: 1623 bytes
  - live_corpus_dump.json: 8758 bytes

