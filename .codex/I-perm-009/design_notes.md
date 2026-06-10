# I-perm-009 (#1203) — Proof & measurement: design notes (durable)

See StructuredOutput for the full design. Key code-grounded anchors:

- B2 defect: `src/polaris_graph/roles/native_gate_b_inputs.py:312-352` (`_content_requirements_satisfied`
  + `_claim_covers_entity`) require ALL content tokens in ONE sentence. drb_76 contraindication
  content is split across 03-001/03-002/03-005 (all VERIFIED) → s0_categories=[] each →
  `release_policy.py:255-273` S0 gate emits `d8_s0_must_cover_missing:contraindications`. Saved
  manifest held_reasons literally:
  ["d8_unsupported_residual_below_coverage","d8_s0_must_cover_missing:contraindications","d8_pending_rewrite"].
- Replay substrate: `scripts/dr_benchmark/offline_e2e.py` reconstructs the `four_role_evaluation`
  manifest block via a FAKE RoleTransport (no spend). `build_native_gate_b_inputs` is a PURE function.
- Saved evidence: outputs/audits/beatboth8/drb_76/{manifest.json, four_role_claim_audit.json,
  evidence_pool.json (46 rows only — post-selection), audit_pack.json (24 claims + resolved spans),
  report.md, DRB76_FORENSIC.md}.
- B1 honesty: manifest records funnel (retrieval.fetched=500, evidence_selection.evidence_selected=46)
  but the 500 pre-selection source BODIES are NOT saved (only 46-row pool + raw p1_run.log). So
  ">46 selected" is NOT deterministically replayable from drb_76 artifacts → needs a saved
  pre-selection corpus fixture OR re-run. Assert on RECORDED funnel numbers offline; flag spend-risk.
- Completeness denominator: outputs/dr_benchmark/rubric_v3_frozen.json (questions list, keyed Q75-E1…;
  drb_76 == Q76). Wire claim_audit_scorer.lane2_coverage to Q76 elements.
- Charter: docs/permanent_fix_9_issues.md. I9 = proof/measurement ONLY. The fixes (I1 reframe,
  I2 corpus-wide S0, I3 selection, I4 re-anchor, I8 cruft) are SEPARATE issues; my asserts depend on them.
