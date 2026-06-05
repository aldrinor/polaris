# Claude architect audit — I-ready-012 (#1079): semantic/NLI cross-document contradiction layer

Reviewer: Claude (architect). Scope: the END RESULT of the #1079 diff (commits `c70d4f2a` + `a1bb9d49` on `bot/I-ready-012-semantic-conflict-nli`, off `bot/I-ready-013`). Method: §-1.1 line-by-line — each claim verified against the changed code + the consumer it feeds.

## 1. The gap closed (verified, reproduced)

- **Recall hole, reproduced:** two T1 rows "adjuvant chemotherapy improved overall survival" vs "...provided no overall survival benefit" → `extract_numeric_claims/detect_contradictions = 0` and `extract_qualitative_assertions/detect_qualitative_conflicts = 0`. Both rule detectors are blind to a prose-only directional contradiction with no shared number and no NegEx cue. PT08 cannot catch it (it only iterates contradictions the detectors found). In clinical context this is the lethal-miss class. VERIFIED offline.
- **The fix sees it:** `cluster_candidate_rows` groups the two rows by shared salient content words (independent of the rule extractors), and `detect_semantic_conflicts` (with the contradiction judge) emits one `type:"semantic"` record. The clustering is asserted BEFORE any judge call (so the pre-filter is not re-introducing the rule blindness — Codex iter-1 P1-1).

## 2. Faithfulness invariants — line-by-line

- **Additive only; no gate weakened.** The detector adds disclosures and can only make PT08 STRICTER (a detected semantic conflict not disclosed → `pt08=False` → `abort_evaluator_critical`). It does NOT touch strict_verify, provenance, the 4-role seam, the numeric/qualitative detectors, the numeric disclosure renderer, or the generator `contradictions` arg (`:4019` stays numeric-only). VERIFIED: the diff is confined to a new module + a fail-open block + a disclosure block + the PT08 evaluator arg.
- **An error can never fabricate a conflict.** Per-pair judge error → skip (`continue`); `BudgetExceededError` → keep-partial + stop; the production judge fail-opens to `("neutral", 0.0)` on API/parse error (never `contradict`); and a non-finite / out-of-range confidence is dropped before the threshold (commit `a1bb9d49`, Codex diff P2 — guards the NaN-passes-`<` trap). So a degraded judge cannot invent a contradiction that would falsely abort a legitimate run. VERIFIED by 4 parametrized finite-confidence tests + the fail-open tests.
- **Two-family + cost discipline preserved.** `_SemanticContradictionJudge` enforces `check_family_segregation(evaluator_model=...)` at construction, records spend via `_orc._add_run_cost` + `check_run_budget` (the run hard cap still fires), and is isolated from `_EntailmentJudge` so the strict_verify entailment path is byte-unchanged. (Observability deltas — direct judge-ledger entry + Path-B capture — deferred to #1092; non-correctness.)

## 3. Safety / honesty properties

- **Flag-OFF byte-identical.** `PG_SWEEP_NLI_CONFLICT` default OFF → `semantic_conflict_enabled()` False → the `if` guard makes the block inert (no judge constructed, no network), `semantic_records=[]`, and `contradictions.json` / report text / PT08 input are byte-identical to today. VERIFIED (default-off + no-judge-when-no-pairs tests).
- **Routing is real (Codex iter-1 P1-2).** `test_pt08_gate_counts_a_semantic_record_real_evaluator` calls the REAL `run_external_evaluation`: a disclosed semantic conflict → PT08 pass; suppressed → PT08 fail. So the record genuinely reaches + is gated by the evaluator, not merely written to `contradictions.json`. VERIFIED.
- **Loader compatible (Codex iter-1 P2).** Each claim carries `evidence_id`+`predicate`+finite `value` (0.0 sentinel); `test_semantic_record_is_audit_ir_loader_compatible` parses a semantic record via the REAL `loader._parse_contradictions`. VERIFIED. (Typed-IR replacement of the 0.0 sentinel deferred to #1092.)
- **Cost-bounded.** Clustering bounded to top `MAX_ROWS` (200, tier-sorted); pairs capped at `MAX_PAIRS` (60). The judge is never called when OFF. VERIFIED (pair-cap test + no-judge-when-OFF).

## 4. Process note

Codex brief-gate iter-1 caught two REAL P1s I had wrong (pairing reused rule-extractor subject keys that are blind to the target rows; routing assumed disclosure+PT08 plumbing that only consumes the numeric list). Both were corrected in iter-2 (recall lexical clustering + explicit 3-point routing) before any code was written — the brief gate did its job. Diff-gate iter-1 then caught the NaN-confidence correctness edge (folded in) + 2 observability P2s (deferred to #1092).

## 5. Verdict

Faithfulness-safe (additive, never weakens a gate, never fabricates a conflict), flag-OFF byte-identical, recall-closing, routing + loader-compat verified against the REAL evaluator and loader. 16 behavioral + 39 regression tests green; `verify_lock --consistency` OK.

**Architect verdict: APPROVE.** Residuals (judge observability + typed contradiction IR) tracked in #1092, non-blocking.
