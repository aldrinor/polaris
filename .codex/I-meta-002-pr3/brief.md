# Codex brief-gate — I-meta-002 sub-PR-3: D8 release policy (occurrence/residual/S0-must-cover) — NO SPEND

HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it P3/P2/cosmetic; reserve P0/P1 for real execution/safety risks.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on remaining non-P0/P1; do not bank for iter 6.
- If you detect "I'm holding back a P1 for the next round" — DON'T. Surface it now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
```

## HARD CONSTRAINTS (operator-locked, NOT consultable)
- 4-role architecture LOCKED. NO MONEY this PR (pure Python + config + tests; no network/GPU).
- Operator is blind — keep the verdict crisp.
- Canonical pipeline = docs/polaris_pipeline_canonical.md; do not drift it.
- The benchmark scorer `src/polaris_graph/benchmark/claim_audit_scorer.py` is FROZEN/
  pre-registered (coverage 0.70 frozen per plan §5). This PR must NOT change its semantics or
  threshold — the D8 production release gate is a SEPARATE layer.

## Context — implements YOUR I-meta-002 design iter-2 D8 findings
sub-PR-1 (lock) and sub-PR-2 (role contracts) are committed + Codex-APPROVED. This is sub-PR-3
of 6. Your iter-2 design verdict gave PR3 this scope and these D8 rulings (quoted):

> FABRICATED should remain occurrence-gated with zero tolerance. UNSUPPORTED should usually be
> residual-gated after one rewrite/reverify or refuse-in-place, because occurrence-gating every
> unsupported material claim would incentivize blank reports and suppress transparent evidence
> gaps. Exceptions: fabricated/missing source identity and missing S0 must-cover elements must
> be occurrence/abort gated.
> Add S0 must-cover gates. A 0.70 residual coverage threshold is not enough for clinical if the
> missing 30% includes contraindications, dosing limits, black-box warnings, pregnancy/renal/
> hepatic cautions, or regulatory status.
> PARTIAL S0/S1 claims should get one rewrite/clarify attempt before shipping as visible advisory.
> [claim_audit_scorer.py:91] is the place to split FABRICATED occurrence gating from UNSUPPORTED
> residual gating; [evaluator_gate.py:89] is the existing manifest gate layer.

## Grounding (already read, file:line)
- `claim_audit_scorer.py`: `Verdict` 5-enum (:22); `ClaimRow` (severity S0–S3, verdict,
  citation_id, span_quote, unreachable_subtype, audit_note) (:34–57); `_COVERAGE_THRESHOLD=0.70`
  (:31, FROZEN); `system_passes_question()` dual-lane hard_fail==0 AND coverage>=0.70 (:111–124,
  FROZEN — do not change). reconcile.py:20 already orders FABRICATED worst.
- sub-PR-2 `src/polaris_graph/roles/judge_contract.py`: `classify_unreachable(subtype, citation_id,
  evidence_pool_ids)` — fabricated-identity-first precedence (unknown id -> FABRICATED) ALREADY
  built + Codex-approved. PR3 CONSUMES it.
- `evaluator_gate.py:89` `compute_evaluator_gate()` — existing manifest gate (rule blockers,
  release_allowed). PR3's D8 decision is an INPUT to / sibling of this, not a rewrite of it.

## Scope of sub-PR-3 (acceptance criteria)
New module `src/polaris_graph/roles/release_policy.py` (production D8 gate; pure function over
claim rows; no network). It does NOT mutate the frozen benchmark scorer.

0. **D8 row wrapper — production-side category + pre-classified verdict signal.** The frozen
   `ClaimRow` has no category field and MUST NOT be mutated. Introduce a production wrapper
   `D8ClaimRow` (dataclass): `claim_id`, `severity`, `verdict` (a `claim_audit_scorer.Verdict`),
   `citation_id` (for gap reporting only), and `s0_categories: list[str]` (which S0 must-cover
   categories THIS claim addresses, empty if none). **(iter-3 fix, Codex P1-1)** D8 does NOT call
   `classify_unreachable` and does NOT receive the evidence pool. The CALLER (sub-PR-5) runs
   `classify_unreachable` UPSTREAM with the evidence pool and stamps the RESULT into `verdict`
   (fabricated identity -> verdict=FABRICATED; genuine fetch-miss -> verdict=UNREACHABLE). D8
   reads `verdict` only. `apply_d8_release_policy` operates over `list[D8ClaimRow]`.
1. `apply_d8_release_policy(d8_rows, *, required_s0_categories, coverage_ledger, coverage_threshold,
   rewrite_already_attempted, prior_fabricated_latched=False) -> ReleaseDecision` where
   `ReleaseDecision` carries `release_allowed: bool`, `held_reasons: list[str]` (stable codes),
   `gaps: list[Gap]`, `needs_rewrite: list[claim_id]`, and **`fabricated_occurrence_latched: bool`**.
   **(iter-3 fix, Codex P1-2)** `coverage_ledger` is an explicit `CoverageLedger` dataclass with
   `required_element_ids: list[str]` and `covered_element_ids: set[str]` (covered = required AND
   satisfied by a citation-supported VERIFIED claim). Coverage fraction = `len(covered ∩ required)
   / len(required)` with the denominator FIXED by the required set — so dropping a claim shrinks the
   numerator (lowers coverage), it cannot inflate it. D8 NEVER computes coverage from the count of
   present rows.
2. **FABRICATED occurrence gate — true persisted latch.** `fabricated_occurrence_latched =
   prior_fabricated_latched OR (any material S0–S2 row in THIS pass has verdict==FABRICATED)`.
   (Fabricated citation identity already arrives as verdict==FABRICATED, stamped upstream per item
   0 — D8 does not re-derive it.) If latched -> release_allowed=False, reason
   `d8_fabricated_occurrence`. The latch ORs in `prior_fabricated_latched`, so a later clean rewrite
   pass CANNOT launder a fabrication: `rewrite_already_attempted=True` does NOT clear it. The caller
   persists `decision.fabricated_occurrence_latched` across passes (one-way latch for the run).
3. **UNSUPPORTED residual gate (coverage from the ledger).** Material UNSUPPORTED claims do NOT
   occurrence-gate. If `rewrite_already_attempted` is False, emit them in `needs_rewrite` (one
   rewrite/refuse-in-place attempt). After the attempt, gate ONLY if the `coverage_ledger` fraction
   < `coverage_threshold` (reason `d8_unsupported_residual_below_coverage`). **(iter-3 fix, Codex
   P1-2)** Because the ledger denominator is the fixed required set, dropping/refusing a claim
   lowers coverage rather than dodging the gate. Refused-in-place claims become visible `gaps`
   (kind=residual_unsupported), never silent drops.
3b. **(iter-3 fix, Codex P1-3) Genuine UNREACHABLE fetch-miss routing.** Material rows with
   verdict==UNREACHABLE (genuine paywall/robots/fetch_failure — NOT fabricated identity, which is
   already FABRICATED) follow the SAME path as UNSUPPORTED: `needs_rewrite` if not yet attempted,
   else a visible `Gap` (kind=residual_unsupported or a dedicated unreachable note), and they count
   as not-covered in the ledger. They are never silently passed. Fabricated identities stay
   occurrence-gated (item 2); genuine fetch-misses are residual/visible-gap.
4. **S0 must-cover gate (occurrence/abort), via the D8 row category signal.** A required S0
   category is "covered" iff there exists a `D8ClaimRow` whose `s0_categories` contains that
   category AND whose verdict==VERIFIED. If ANY `required_s0_categories` element is not covered
   that way -> release_allowed=False, reason `d8_s0_must_cover_missing:<category>`, regardless of
   overall coverage fraction. This is the "missing 30% includes contraindications" guard. (Per
   Codex Q3: VERIFIED is the bar — a PARTIAL or merely citation-present claim does NOT satisfy an
   S0 must-cover element; the safe clinical default is to require a fully VERIFIED claim.)
5. **PARTIAL S0/S1 one-rewrite-then-advisory:** PARTIAL claims at severity S0/S1 go into
   `needs_rewrite` when `rewrite_already_attempted` is False; after the attempt they ship as a
   visible advisory `Gap`, never a silent pass.
6. **`gaps.json` structure:** a `Gap` dataclass (claim_id|category, kind ∈ {uncovered_s0,
   refused_in_place, residual_unsupported, partial_advisory}, severity, note) + a
   `to_gaps_json(decision) -> list[dict]` serializer. (Writing the file to disk is sub-PR-5
   orchestration; PR3 provides the structure + serializer.)
7. **Config (LAW VI, zero hard-coding):** `config/architecture/d8_release_policy.yaml` holding
   the default `coverage_threshold` (0.70, matching the frozen value but as production config),
   `material_severities` (S0,S1,S2), and the default clinical `s0_must_cover_categories`
   (contraindications, dosing_limits, black_box_warnings, pregnancy_renal_hepatic_cautions,
   regulatory_status). Loaded via a small loader; per-question required set is passed in by the
   caller (extraction from the scope protocol wires in at sub-PR-5).
8. Tests under `tests/roles/test_release_policy.py`: FABRICATED occurrence holds even with
   rewrite_already_attempted=True; the latch persists — `prior_fabricated_latched=True` holds
   release even when the CURRENT pass rows are all clean (no laundering); the decision returns
   `fabricated_occurrence_latched=True`; UNSUPPORTED routes to needs_rewrite first then
   residual-gates only when the `coverage_ledger` fraction < threshold; **(iter-3) dropping a
   covered claim LOWERS the ledger fraction (denominator fixed) and so does NOT dodge the residual
   gate**; **(iter-3) a material verdict==UNREACHABLE fetch-miss routes to needs_rewrite then a
   visible gap (not silently passed)**; S0 must-cover missing holds regardless of coverage, driven
   by `D8ClaimRow.s0_categories`, and a PARTIAL/citation-only claim in a required category does NOT
   satisfy it (only VERIFIED does); PARTIAL S0 advisory; **a row arriving with verdict==FABRICATED
   (fabricated identity already stamped upstream) occurrence-gates**; gaps serializer shape; config
   loader.
9. Hygiene: snake_case, explicit imports, named constants, no `except: pass`, no mocks in src/.

## Files I have ALSO checked and they are clean / relevant
- `claim_audit_scorer.py` — REUSED (Verdict, ClaimRow, severity) but NOT mutated; the frozen
  benchmark gate stays intact. D8 is a separate production layer.
- `evaluator_gate.py` — NOT modified in PR3; wiring D8 into the manifest gate is sub-PR-5.
- `pathB_runner.py` `_role_pins()` — still 2 roles; sub-PR-5.
- sub-PR-2 `judge_contract.classify_unreachable` — consumed by the CALLER (sub-PR-5) UPSTREAM of
  D8 to stamp verdict (FABRICATED vs UNREACHABLE); D8 itself does NOT call it (iter-3 P1-1).

## iter-3 changelog (addresses your iter-2 P1s)
- **P1-1 (classify_unreachable needs the pool):** D8 no longer calls `classify_unreachable` and
  takes no evidence pool. The caller runs it upstream and stamps `verdict` (fabricated identity ->
  FABRICATED; genuine fetch-miss -> UNREACHABLE). D8 reads `verdict` only. See items 0, 2.
- **P1-2 (UNSUPPORTED residual under-specified / drop-to-dodge):** added an explicit
  `CoverageLedger` (required_element_ids + covered_element_ids) with a FIXED required denominator;
  residual gating uses that fraction, so dropping/refusing a claim lowers coverage instead of
  dodging the gate. See items 1, 3.
- **P1-3 (genuine UNREACHABLE not routed):** material verdict==UNREACHABLE rows now follow the same
  one-rewrite-then-visible-gap path as UNSUPPORTED; fabricated identities remain occurrence-gated.
  See item 3b.
- iter-1/iter-2 P2 agreements kept (separate module; persisted latch; S0 VERIFIED-only bar).

## Questions for Codex (iter-3)
1. Confirm D8 reading a pre-stamped `verdict` (caller runs classify_unreachable upstream with the
   pool) fully resolves the evidence-pool dependency, with no double-classification risk.
2. Confirm the `CoverageLedger` fixed-denominator design makes claim-dropping LOWER coverage rather
   than dodge the residual gate.
3. Confirm routing genuine UNREACHABLE through the rewrite-then-visible-gap path (while FABRICATED
   identities stay occurrence-gated) is the correct clinical split.
4. Any residual perverse incentive remaining in the policy.

Hand me APPROVE iff the occurrence/residual split, the FABRICATED-latch, the S0 must-cover
gate, and the separate-module boundary are correct and clinically safe.
