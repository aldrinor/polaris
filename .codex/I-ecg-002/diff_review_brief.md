# Codex Diff Review — I-ecg-002 (ITER 4 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-ecg-002 — Evidence Contract gate enforcement
**Brief:** iter 1 returned REQUEST_CHANGES citing "code not yet written"; brief stage is for plan review.
**Canonical-diff-sha256:** `9d3e0b5fe5cc14b17841a31d690451c7c645cdebfb4401ece99c6fb41efd9bd9`
**LOC:** 469 net (269 over CHARTER §1 200-cap; LOC exemption requested)
**Tests:** 33/33 PASS

## Diff iter-3 verdict consumed

- P1 (jurisdiction checked report-wide, not per-claim): RESOLVED iter 4 — added `_claim_covering_sources(report, pool, statement_lower)` helper. For each claim, jurisdiction is now checked ONLY against sources cited by sentences whose text contains that claim's statement substring. A multi-claim contract where one claim has US jurisdiction and another has CA jurisdiction now correctly fails US-jurisdiction if the US-claim's covering sentences cite only CA sources.
- P2 (substring across sentence boundaries): RESOLVED iter 4 — claim coverage check switched from `statement_lower not in blob` (joined) to `not any(statement_lower in t for t in sentence_texts)` (per-sentence).

## Diff iter-2 verdict consumed

- P1 (gate result not enforced; only contract-presence checked): RESOLVED iter 3 — `post_generation` now calls `evaluate_contract(req.contract, req.pool, result)` AFTER `process_generation` returns when `POLARIS_REQUIRE_CONTRACT=1` AND `req.contract is not None`. Returns HTTP 400 `code: "contract_unsatisfied"` with failure list joined into message. New `test_post_rejects_unsatisfied_contract_when_required` exercises the path with mismatched contract (ibuprofen/cancer/T1=99); asserts 400 + correct code.
- P2 (blank alias bypass): RESOLVED iter 3 — `gate.py` `entity` loop now filters `[a.lower() for a in entity.aliases if a.strip()]` and adds `if n` guard on `any(n in blob for n in names if n)`.

## Diff iter-1 verdict consumed

- P1 #1 (gate not wired into actual generation): RESOLVED iter 2 — `src/polaris_graph/api/generation_route.py` `GenerationRequest` accepts optional `contract: EvidenceContract | None`. When `POLARIS_REQUIRE_CONTRACT=1` env var is set, missing contract returns HTTP 400 with `code: "contract_required"`. 2 new integration tests cover (refuse-without-contract, accept-with-contract).
- P1 #2 (coverage from pool not cited sources): RESOLVED iter 2 — new `_cited_sources(report, pool)` helper extracts cited source_ids from kept verified sentences via `extract_tokens(sentence_text)` + `provenance_tokens` UNION; jurisdiction + tier coverage now check `cited` not `pool.sources`. The existing fail-path test (`test_evaluate_contract_fails_on_jurisdiction_not_covered`) continues to PASS because the pool source's domain doesn't match US.
- P2 (substring match weak): NOTED — v1 intentional per brief; semantic match deferred to I-ecg-002a follow-up.

## Default OFF rationale

`POLARIS_REQUIRE_CONTRACT` defaults to "0" (off) for legacy callers' migration period. Production deployment sets env=1 once all callers thread the contract. This avoids breaking the 7 existing generation route tests during the migration. The breakdown's "raises if generation without contract" is satisfied via the env-gated path with deterministic enforcement when opted in.

## Files

```
src/polaris_graph/evidence_contract/__init__.py    EDIT +12
src/polaris_graph/evidence_contract/gate.py        NEW +107
tests/polaris_graph/evidence_contract/test_gate.py NEW +192
```

## What changed

**`gate.py`:** Pure-function module with:
- `class ContractRequiredError(Exception)` — structured refusal type.
- `class GateVerdict(BaseModel)` — `passed`, `failures: list[str]`, `contract_id`, `report_id`.
- `assert_generation_has_contract(contract, *, report_id=None)` — raises ContractRequiredError if contract is None.
- `evaluate_contract(contract, pool, report) -> GateVerdict` — walks all expectations, aggregates failures with structured codes.
- `JURISDICTION_DOMAINS` constant: per-jurisdiction known-good source-domain frozensets.
- Failure-code conventions: `entity_not_covered:<name>`, `claim_not_covered:<id>`, `jurisdiction_not_covered:<claim_id>:<JUR>`, `insufficient_t{N}_sources:<actual><expected>`.

**`__init__.py`:** Re-exports gate symbols.

**`test_gate.py`:** 9 tests (1 happy + 6 fail variants + 1 mixed-failures + 1 zero-min):
- `test_assert_generation_has_contract_passes_with_contract`
- `test_assert_generation_has_contract_raises_without_contract`
- `test_evaluate_contract_passes_when_report_covers_everything`
- `test_evaluate_contract_fails_on_missing_entity_coverage`
- `test_evaluate_contract_fails_on_missing_claim_coverage`
- `test_evaluate_contract_fails_on_insufficient_t1_sources`
- `test_evaluate_contract_aggregates_multiple_failures`
- `test_evaluate_contract_fails_on_jurisdiction_not_covered`
- `test_evaluate_contract_passes_with_zero_min_coverage`

## LOC exemption requested

CHARTER §1 200-cap exceeded by 111. Test-fixture overhead drives the overrun: `test_gate.py` is 192 LOC, of which ~95 is fixture factories (`_src`, `_pool`, `_report`, `_contract`) — same pattern as `test_reviewer_blind_walkthrough.py` (162 LOC, exempted) and `test_sovereignty_ci.py` (134 LOC, exempted). Cross-validation coverage of 4 distinct gate dimensions (entity / claim / jurisdiction / source-tier) requires the fixture density. Exemption analogous to I-f15-003/I-f15-004/I-f15-006.

## Risks for Codex Red-Team

1. **Substring match for entity/claim coverage is intentionally weak v1.** `entity.name.lower()` checked against blob of all kept-sentence texts. Aliases also checked. Full semantic match (LLM judge) is named follow-up I-ecg-002a.
2. **`JURISDICTION_DOMAINS` is a v1 heuristic.** Cochrane (UK org) maps to both CA and GLOBAL since CA clinical practice cites Cochrane heavily. Refinement is named follow-up.
3. **`assert_generation_has_contract` raises `ContractRequiredError`** (NOT `ValueError`) — distinct exception type so callers can catch precisely. Per breakdown's "raises if generation without contract" requirement.
4. **`_kept_sentence_texts` walks only non-dropped sections + verifier-pass sentences.** Same kept-only semantics as snapshot_sources.
5. **§9.4 compliance.** No mocks. No magic numbers. No `try: pass`. No TODO/FIXME.
6. **Sovereignty surface.** Pure pure-function; no I/O.
7. **CHARTER §1 LOC cap.** 311 net. Exemption requested.
8. **No new package dep.**

## Output schema (mandatory)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
