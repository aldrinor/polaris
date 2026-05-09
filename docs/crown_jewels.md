# Crown Jewel registry

Per `state/polaris_restart/issue_breakdown.md` §29, the Crown Jewel side-track ships dedicated tests that pin each non-negotiable invariant from `CLAUDE.md` §9.1. A future regression that weakens any of these invariants causes a `tests/crown_jewels/test_cj_NNN_*` test to fail under an unambiguous identifier.

| Issue | Invariant (CLAUDE.md §9.1) | Test path | Bound source-of-truth |
|---|---|---|---|
| I-cj-001 | §9.1.1 Two-family evaluator | `tests/crown_jewels/test_cj_001_two_family_segregation.py` | `src/polaris_graph/llm/openrouter_client.py::check_family_segregation` |
| I-cj-002 | §9.1.2 Provenance tokens | `tests/crown_jewels/test_cj_002_provenance_tokens.py` | `src/polaris_graph/generator2/provenance.py::extract_tokens` |
| I-cj-003 | §9.1.3 Strict verify | `tests/crown_jewels/test_cj_003_strict_verify.py` | `src/polaris_graph/generator2/strict_verify.py::verify_sentence` |
| I-cj-004 | §9.1.4 Zero-verified abort | `tests/crown_jewels/test_cj_004_zero_verified_abort.py` | `src/polaris_graph/generator2/verified_report.py::VerifiedReport._verdict_consistency` |
| I-cj-005 | §9.1.5 Corpus approval enforcement | `tests/crown_jewels/test_cj_005_corpus_approval.py` | `src/polaris_graph/nodes/corpus_approval_gate.py::check_auto_approve_allowed` |
| I-cj-006 | §9.1.6 Budget cap holds without `usage.cost` | Pending — issued in subsequent CJ Issues | `src/polaris_graph/llm/openrouter_client.py::_impute_cost_from_tokens` |
| I-cj-007 | §9.1.7 Delimiter sanitization | Pending — issued in subsequent CJ Issues | `src/polaris_graph/generator/delimiter_sanitize.py` |
