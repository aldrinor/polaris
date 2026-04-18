---
verdict: PRIORITIZED
dimension_summary:
  intake_scope: blocker
  retrieval_tiering: medium
  contradictions: medium
  generation: medium
  strict_verify: medium
  evaluator: medium
  orchestration: blocker
  budget_cost: minor
  observability: medium
  testing: medium
  pipeline_b_parity: blocker
  frozen_c_disposition: medium
total_blockers: 3
total_mediums: 8
total_minors: 1
rationale: |
  Pipeline A is materially more hardened than the pre-audit baseline, but this scoping pass found three cross-cutting blocker-class issues that are design/control-plane failures, not just isolated bugs. The most serious are that scope gating never actually aborts, the active UI path bypasses the hardened invariants entirely, and the success-manifest contract is internally inconsistent enough that downstream consumers cannot rely on `manifest.json` as documented. The next tier of risk is silent under-coverage: generation accepts collapsed outlines, contradictions detection is narrow, limitations bypass provenance, and evaluator outputs are advisory rather than enforcing.
recommended_deep_dive_order:
  - orchestration
  - pipeline_b_parity
  - intake_scope
  - generation
  - evaluator
  - retrieval_tiering
  - contradictions
  - observability
  - testing
  - strict_verify
  - budget_cost
  - frozen_c_disposition
---

## Verdict semantics

`PRIORITIZED`: scoping completed; deep-dives are warranted.

## 1. Intake & scope gating

**Severity:** blocker

**Finding:** Design gap. The "scope gate" never rejects; it only annotates `needs_user_review`, and the orchestrator ignores that flag. The documented `abort_scope_rejected` status appears unreachable in pipeline A.

**Evidence:** `src/polaris_graph/nodes/scope_gate.py:388-433` sets `needs_user_review=needs_review` and returns a protocol, but has no rejection branch. `scripts/run_honest_sweep_r3.py:288-317` logs `needs_review` then immediately runs retrieval. Real reproducer: `outputs/honest_sweep_r6_validation/clinical/clinical_afib_anticoagulation/run_log.txt` shows `[scope] ... needs_review=True` followed by retrieval, generation, and final `[status] ok_thin_corpus`.

**Recommendation:** Deep-dive whether scope review is meant to be advisory or a real gate, and reconcile code, docs, and status taxonomy around `abort_scope_rejected`.

## 2. Retrieval & tiering

**Severity:** medium

**Finding:** Design gap. Corpus gates reason over all classified URLs, but generation only sees `evidence_rows[:PG_LIVE_MAX_EV_TO_GEN]` in raw retrieval order, with no tier-balanced or contradiction-aware sampling. This lets the pipeline certify one corpus and synthesize from a smaller, different subset.

**Evidence:** `scripts/run_honest_sweep_r3.py:623-640` uses `evidence_for_gen = retrieval.evidence_rows[:max_ev]`. `src/polaris_graph/retrieval/live_retriever.py:545-583` builds `classified_sources` for every fetched candidate, but only adds `evidence_rows` when content is not starved. Real run: `clinical_afib_anticoagulation/run_log.txt` reports `total=20` corpus sources but `[generation] ... evidence=4`.

**Recommendation:** Deep-dive whether adequacy/approval/completeness should be computed over the generator-visible evidence pool, and whether evidence selection needs explicit tier balancing and deterministic ranking.

## 3. Contradictions detection

**Severity:** medium

**Finding:** Design gap. The contradiction detector is still scoped to a narrow set of obesity/cardiometabolic predicates and extracts at most one numeric claim per evidence row, so it will under-detect contradictions outside that band.

**Evidence:** `src/polaris_graph/retrieval/contradiction_detector.py:77-92` hard-codes predicates such as `"weight loss"`, `"hba1c reduction"`, `"ldl reduction"`, `"incidence of nausea"`. `extract_numeric_claims()` at `:395-456` calls `_find_value_in_context()` once per evidence row and appends one `ExtractedNumericClaim`. Real run: `clinical_afib_anticoagulation/run_log.txt` shows `numeric_claims=0 contradictions=0` on an anticoagulation guideline query with 20 sources.

**Recommendation:** Deep-dive domain coverage and extraction cardinality, especially for clinical/policy/DD queries whose contradictions are not expressible as the current predicate list.

## 4. Generation

**Severity:** medium

**Finding:** Silent under-coverage risk. The outline contract is prompt-only: `_parse_outline()` does not enforce the promised 3-5 sections or non-overlapping evidence assignments, and an empty/invalid outline silently falls back to one generic `Efficacy` section.

**Evidence:** `src/polaris_graph/generator/multi_section_generator.py:159-179` accepts any number of valid sections and does not check overlap. `:624-634` logs `outline empty; falling back to single generic 'Efficacy' section`. Real artifact: `clinical_afib_anticoagulation/manifest.json` records `"outline_sections": ["Efficacy"]`, and `report.md` contains one findings section despite the planner prompt requiring 3-5.

**Recommendation:** Deep-dive whether outline failure should abort or downgrade explicitly instead of silently collapsing report structure.

## 5. Strict verify

**Severity:** medium

**Finding:** Known but still open design gap. Limitations sentences bypass provenance verification and are marked as kept even with zero tokens, so telemetry claims are trusted on generation output alone.

**Evidence:** `src/polaris_graph/generator/provenance_generator.py:755-770` appends every limitations sentence as `is_verified=True` with `soft_warnings=["limitations_paragraph_pass_through"]`. `src/polaris_graph/generator/multi_section_generator.py:437-508` also emits a deterministic fallback limitations paragraph outside `verify_sentence_provenance()`. Real run: `qwen_judge_output.json` for `clinical_afib_anticoagulation` flags `citation_tightness: needs_revision` because the limitations section is uncited.

**Recommendation:** Deep-dive whether telemetry-grounded limitations need a separate deterministic verifier or should be excluded from "verified" counts/status semantics.

## 6. Evaluator

**Severity:** medium

**Finding:** Design weakness. The rule-based evaluator is largely keyword/shape checking, the Qwen judge sees only the report text, and neither evaluator meaningfully gates success. A report can ship while Qwen says `needs_revision`.

**Evidence:** `src/polaris_graph/evaluator/live_qwen_judge.py:139-143` sends only `research_question` plus `report_text`; no evidence pool is provided. `src/polaris_graph/evaluator/external_evaluator.py:223-245` passes PT05/PT07 on keyword presence, and `:342-360` PT12 only checks citation numbers do not exceed bibliography size. `scripts/run_honest_sweep_r3.py:920-928` sets summary status from rule-fail count and adequacy, not Qwen verdicts. Real run: `clinical_afib_anticoagulation/run_log.txt` shows Qwen `citation_tightness=needs_revision` and final status `ok_thin_corpus`.

**Recommendation:** Deep-dive which evaluator outputs are advisory versus release-blocking, and whether rule checks should validate semantics instead of string presence.

## 7. Orchestration

**Severity:** blocker

**Finding:** Contract drift. Successful runs write `manifest.json` without any `status`, while abort runs do include one. The orchestrator also uses a separate summary-only taxonomy (`ok`, `ok_thin_corpus`, `warn_rule_checks`) that does not match the documented per-run verdict schema.

**Evidence:** Success manifest construction in `scripts/run_honest_sweep_r3.py:851-907` has no `"status"` key. Status is computed later only into `summary["status"]` at `:915-929`. The contract bundle says `manifest.status` is authoritative in `docs/pipeline_audit_context/03_json_contracts.md`. Real artifacts: `clinical_afib_anticoagulation/manifest.json` has no `status`; `tech_rag_architectures_2024/manifest.json` does.

**Recommendation:** Deep-dive the run-contract authority: one status taxonomy, one place to read it, and coverage for every success/abort/error exit path.

## 8. Budget + cost ledger

**Severity:** minor

**Finding:** The budget cap itself looks sound after rounds 1-5, but run attribution in the ledger is weak for pipeline A because generator/judge clients are instantiated without a session ID.

**Evidence:** Ledger entries include `"session_id"` at `src/polaris_graph/llm/openrouter_client.py:411-420`, but pipeline-A call sites use `OpenRouterClient(model=model)` with no session ID in `multi_section_generator.py:211,310,456`, `live_deepseek_generator.py:314`, and `live_qwen_judge.py:137`.

**Recommendation:** Deep-dive only if observability consumers depend on per-run cost joins; the budget guard itself does not need priority re-audit.

## 9. Observability

**Severity:** medium

**Finding:** Run observability is split across mismatched scopes: manifests omit success status, cost ledger is global rather than run-local, and sample run directories do not contain the per-run ledger path the audit bundle tells readers to inspect.

**Evidence:** `README.md` and `03_json_contracts.md` describe `manifest.json` as the verdict source, but success manifests lack `status`. The ledger path is global at `src/polaris_graph/llm/openrouter_client.py:39-40` (`logs/pg_cost_ledger.jsonl`). Real artifact check: `outputs/honest_sweep_r6_validation/clinical/clinical_afib_anticoagulation/` contains no `logs/pg_cost_ledger.jsonl`, only run-local JSONs plus `run_log.txt`.

**Recommendation:** Deep-dive artifact contract boundaries: what must live inside each run dir, what is global, and how a consumer is supposed to correlate them deterministically.

## 10. Testing

**Severity:** medium

**Finding:** The 305 passing tests cover the hardened narrow invariants well, but they do not protect several now-live contract/design edges: success-manifest schema, reachable scope rejection, one-section outline collapse, and evaluator non-gating.

**Evidence:** `tests/polaris_graph/` contains focused module/invariant tests, but `rg` over that tree finds abort-status assertions (`test_b2_*`, `test_b3_*`) and no success-manifest `status` assertion. `tests/polaris_graph/test_scope_gate.py` verifies `needs_user_review` but not any abort behavior. The sample success artifact already violates the documented manifest contract without a failing test.

**Recommendation:** Deep-dive missing contract/integration tests, especially artifact-shape tests over real success runs and negative tests for under-covered outlines/scope escalation.

## 11. Pipeline B parity

**Severity:** blocker

**Finding:** Active-user-path blocker. The Docker-default/UI pipeline dispatches into v1/v2/v3 graphs that do not contain pipeline-A strict verification, corpus approval, delimiter sanitization, or abort semantics.

**Evidence:** `scripts/live_server.py:548-602` dispatches to `graph.py`, `graph_v2.py`, or `graph_v3.py`. A repo-wide search for `strict_verify|sanitize_evidence_text|corpus_approval|abort_no_verified_sections|abort_corpus_approval_denied` across `scripts/live_server.py`, `src/polaris_graph/graph.py`, `graph_v2.py`, and `graph_v3.py` returns no matches. The v1/v2/v3 entry points are at `graph.py:1279-1299`, `graph_v2.py:754-773`, and `graph_v3.py:702-719`.

**Recommendation:** First deep-dive after orchestration. Establish which A invariants are mandatory for B, then map exact insertion points per graph version or decide which graph survives.

## 12. Frozen subsystem disposition

**Severity:** medium

**Finding:** Pipeline C is correctly marked frozen, but the broken CLI entrypoint is still present and references missing files, so the repo still ships a dead advertised path unless docs/entrypoints are constrained further.

**Evidence:** `scripts/full_cycle.py:363` imports `scripts.run_ragas_v3`; `:405` imports `scripts.final_audit`. Both files are absent in the workspace. `src/orchestration/FROZEN_SINCE_2026-03-16.md` explicitly states the `research` subcommand is partially broken and untested.

**Recommendation:** Deep-dive only enough to choose retire/repair/leave and align Docker/docs with that decision; no internal code audit is needed.

## Deep-dive priorities

1. `orchestration` — the artifact/status contract is already inconsistent on live success runs.
2. `pipeline_b_parity` — this is an active production path without the audited invariants.
3. `intake_scope` — documented reject semantics are not implemented.
4. `generation` — silent one-section collapse can under-cover without failing.
5. `evaluator` — current evaluator outputs are too weak to counterbalance generation collapse.
