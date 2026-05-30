# Codex brief-gate — I-meta-002 sub-PR-5: 4-role orchestration (per-claim pipeline + pins + KG), mock-tested — NO SPEND

> **THIS IS A BRIEF / DESIGN REVIEW, NOT A DIFF REVIEW.** The implementation files do NOT exist
> yet — they are written in the BUILD step AFTER this brief is APPROVE'd and reviewed at the
> separate DIFF-gate (same brief→build→diff cycle as sub-PR-1..4 which you APPROVE'd this way).
> "Files not present" is expected, NOT a finding. Review the ACCEPTANCE CRITERIA / design.

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. Reserve P0/P1 for real execution/safety risks.
- If you are holding back a P1 for the next round — surface it now; iter 6 does not exist.
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
- 4-role architecture LOCKED. **NO MONEY this PR. NO real network calls in code OR tests** —
  the role pipeline takes an INJECTED `RoleTransport` (sub-PR-4) and is exercised ONLY with the
  mock transport. The KG store writes to a temp/in-memory path in tests. No GPU, no Cohere, no Vast.
- Operator is blind — keep the verdict crisp.
- Canonical pipeline = docs/polaris_pipeline_canonical.md (stage 14 Mirror / 15 Sentinel /
  16 Judge / 17 snowball memory); do not drift it.
- The benchmark scorer `claim_audit_scorer.py` stays FROZEN. The runtime lock
  `polaris_runtime_lock.yaml` stays at `codex_approved_pending_operator_signature` this PR
  (promotion to `locked` is sub-PR-6 — and per the gate, while pending, pathB smokes are FROZEN,
  so a full live sweep cannot run yet by design; this PR builds the composable wiring + tests).

## Context — implements YOUR I-meta-002 design iter-2 "PR5" + the 4-role pipeline
sub-PR-1 (lock), 2 (contracts), 3 (D8 release policy), 4 (3 role adapters) committed + Codex-APPROVED.
This is sub-PR-5. Grounding (read this session, file:line):
- `pathB_runner.py:40-68` `_role_pins()` returns ONLY generator+evaluator today (2-role hardcoded);
  `_DEFAULT_GEN_SLUG`/`_DEFAULT_EVAL_SLUG` at :37-38. `RolePin` dataclass at
  `pathB_run_gate.py:147-157`. `preflight(..., enforce_architecture_coverage=True)` at :166.
  `_assert_architecture_coverage()` at :278-332 ALREADY requires every lock role be pinned AND
  RAISES while lock status is `codex_approved_pending_operator_signature` (smokes frozen).
- `pathB_capture.py`: `llm_role(role)` context manager + `capture_llm_call(role, ...)` already
  support ARBITRARY role strings (`_ROLE` contextvar). No 2-role hardcode in capture itself.
- sub-PR-4 adapters: `run_mirror/run_sentinel/run_judge(transport, ...) -> (result, list[RoleCallRecord])`.
- sub-PR-3 D8: `apply_d8_release_policy(d8_rows, ...)`, `D8ClaimRow`, `CoverageLedger`.
- sub-PR-2 contracts: `Verdict`, `parse_*`, `classify_unreachable`.
- Lock reader: `verify_lock.load_lock()` -> `lock["required_roles"][role]["model_slug"]`.
- Memory: `src/polaris_graph/memory/` has evidence/cache stores but **NO verified-claim graph** —
  must be newly created.

## Scope of sub-PR-5 (acceptance criteria) — PROPOSED SCOPE
This PR builds the COMPOSABLE 4-role orchestration + pins + KG store, all mock/offline-tested. It
does NOT perform the deep call-site surgery inside the 3100-line `scripts/run_honest_sweep_r3.py`
production sweep (see Question 1 — Claude proposes deferring that to sub-PR-6 where it is exercised
live in Gate-B; the no-spend Gate-A does not run the full sweep).

1. **4-role pins** — extend `pathB_runner.py:_role_pins()` to return FOUR `RolePin`s (generator,
   mirror, sentinel, judge), reading `PG_MIRROR_MODEL`/`PG_SENTINEL_MODEL`/`PG_JUDGE_MODEL` (defaults
   sourced from the lock via `load_lock()` so pins and lock cannot drift). Update its tests. The
   architecture-coverage gate then sees all 4 (it already enforces this once the lock is `locked`).
   Also call `validate_role_families()` (N-way) on the 4 pinned slugs so the family invariant holds.

2. **Recording transport wrapper** (`roles/role_pipeline.py`, **iter-2 fix, Codex P1-4**): a
   `RecordingTransport` that WRAPS the injected `RoleTransport` and appends a `RoleCallRecord` (role,
   model_slug, served_model, raw_text) to a collected list on EVERY `complete()` call — BEFORE the
   adapter parses or raises. This guarantees the Path-B identity gate sees every served completion
   even on the highest-risk FAIL-CLOSED paths (a Mirror call that then raises MirrorCitationError/
   MirrorBindingError still leaves its served-identity record). The pipeline drives the adapters
   through this wrapper and harvests `wrapper.records` regardless of downstream raises.

3. **Per-claim role pipeline** (`roles/role_pipeline.py`): a pure orchestration over the injected
   (wrapped) `RoleTransport`:
   - `run_claim_pipeline(transport, *, claim_id, claim, evidence_documents, severity, s0_categories,
     model_slugs, timestamp) -> ClaimPipelineResult`. **(iter-2 fix, Codex P1-2)** `claim_id` is a
     REQUIRED caller-supplied param used for `D8ClaimRow.claim_id` — NEVER synthesized from claim
     text (duplicate/edited claims would break rewrite/gap traceability). Runs IN ORDER: Mirror →
     Sentinel → Judge (Judge given the Mirror + Sentinel signals).
   - **(iter-2 fix, Codex P1-1) Fail-closed composition — post-override final_verdict (LOCKED rule).**
     The pipeline computes a `final_verdict` and writes THAT into `D8ClaimRow.verdict`, while
     `ClaimPipelineResult` ALSO preserves `raw_judge_verdict` separately. Rule:
       * Mirror raised MirrorCitationError OR MirrorBindingError -> `final_verdict = UNSUPPORTED`
         (a claim with no grounded/bound citation can NEVER be VERIFIED), regardless of Judge.
       * ELSE if Sentinel == UNGROUNDED OR Sentinel `parsed_ok` is False -> if raw Judge verdict is
         VERIFIED or PARTIAL, OVERRIDE to `final_verdict = UNSUPPORTED`; but if raw Judge verdict is
         FABRICATED / UNREACHABLE / UNSUPPORTED, PRESERVE it (never upgrade a worse verdict to merely
         UNSUPPORTED).
       * ELSE `final_verdict = raw_judge_verdict`.
     A hallucination therefore cannot reach VERIFIED. Document the rule in the source.
   - `ClaimPipelineResult` carries the `D8ClaimRow` (with final_verdict), `raw_judge_verdict`, the
     `list[RoleCallRecord]` (from the RecordingTransport, so complete even on fail-closed paths), and
     the raw Mirror/Sentinel/Judge sub-results for auditability.
   - Mock-transport tests: ordering (Mirror→Sentinel→Judge); Sentinel UNGROUNDED overrides a Judge
     VERIFIED to UNSUPPORTED but PRESERVES a Judge FABRICATED; Mirror fail-closed -> final UNSUPPORTED
     AND its served-identity record is still present in records; claim_id flows into the D8ClaimRow;
     no network.

4. **Verified-claim KG store** (`src/polaris_graph/memory/verified_claim_graph.py`): the snowball
   (canonical stage 17). A `VerifiedClaimGraphStore` (SQLite at an injected path, default under the
   run dir) with `write_claim(claim_text, claim_id, verdict, role_verdicts, timestamp)`,
   `query_related_claims(claim_text)`, and a cross-time **contradiction flag** hook
   (`find_contradictions(claim) -> list[...]`). `timestamp` is PASSED IN (no `datetime.now()` in the
   store). **(iter-2 fix, Codex P1-3) Anti-snowball-poisoning:** `query_related_claims` returns ONLY
   prior claims whose stored verdict == VERIFIED (the reuse pool); `write_claim` MAY persist
   non-VERIFIED rows but ONLY as audit-only records that are EXCLUDED from `query_related_claims`
   reuse (a `reusable`/verdict filter). A FABRICATED/UNSUPPORTED/PARTIAL/UNREACHABLE claim can never
   be reused as prior knowledge. Tests use a temp SQLite path; assert write+read; assert a
   non-VERIFIED claim is NOT returned by query_related_claims; assert the contradiction flag; no network.

5. **4-role pins** — extend `pathB_runner.py:_role_pins()` to return FOUR `RolePin`s (generator,
   mirror, sentinel, judge). **(Codex P2, accepted)** Default slugs are LOCK-SOURCED via
   `load_lock()` with PG_*_MODEL env OVERRIDES applied on top; `validate_role_families()` runs on the
   effective 4-role map. Update its tests. The architecture-coverage gate then sees all 4.

6. **Capture role tags** — thin helpers / document that Mirror/Sentinel/Judge calls are wrapped with
   `llm_role("mirror"|"sentinel"|"judge")` so the Path-B capture records the right role. The judge
   call site that currently mis-tags as "evaluator" is fixed in the sub-PR-6 sweep wiring (Codex P2
   accepted the scope split), NOT touched here.

7. Hygiene: snake_case, explicit imports, named constants, no `except: pass`, NO unittest.mock in
   `src/` (mock transport/temp paths in tests/), no real network anywhere. No `datetime.now()` /
   random in library code (inject timestamps).

## Files I have ALSO checked and they are clean / relevant
- `pathB_run_gate.py:_assert_architecture_coverage` — already enforces 4-role coverage + frozen-lock
  refusal; sub-PR-5 does NOT change it (the 4 pins make it pass once the lock is `locked` in sub-PR-6).
- `evaluator_gate.py:compute_evaluator_gate` — the existing manifest gate; D8 release_policy is a
  sibling. Whether D8 REPLACES or AUGMENTS the evaluator_gate at the manifest seam is part of the
  sweep wiring (Question 1) — NOT decided/changed in this PR.
- sub-PR-4 adapters + sub-PR-3 D8 + sub-PR-2 contracts — consumed as-is, not modified.
- `verified_report.py` (VerifiedSentence.evaluator_agrees) — populated during the sweep wiring
  (sub-PR-6), not here.

## iter-2 changelog (addresses your iter-1 P1s; your P2s adopted)
- **P1-1 (fail-closed composition):** added the LOCKED post-override `final_verdict` rule (item 3):
  Mirror fail-closed -> UNSUPPORTED; Sentinel UNGROUNDED/unparsed overrides Judge VERIFIED|PARTIAL ->
  UNSUPPORTED but PRESERVES FABRICATED/UNREACHABLE/UNSUPPORTED; `D8ClaimRow.verdict = final_verdict`,
  `raw_judge_verdict` preserved separately.
- **P1-2 (claim_id):** `run_claim_pipeline` now takes a REQUIRED `claim_id` from the caller; never
  synthesized from claim text (item 3).
- **P1-3 (snowball poisoning):** `query_related_claims` returns ONLY VERIFIED prior claims;
  non-VERIFIED rows are audit-only and excluded from reuse (item 4).
- **P1-4 (lost records on Mirror fail-closed):** added a `RecordingTransport` wrapper (item 2) that
  records every served completion at the transport boundary BEFORE any adapter parse/raise, so the
  identity gate has no blind spot on fail-closed paths.
- Your P2s adopted: scope split kept (sweep surgery -> sub-PR-6); pins lock-sourced + env override +
  validate_role_families (item 5); SQLite-at-injected-path KG kept (item 4).

## Questions for Codex (iter-2)
1. Confirm the LOCKED `final_verdict` override rule (item 3) makes it impossible for a Sentinel
   UNGROUNDED or a Mirror fail-closed to yield a VERIFIED claim, while not masking a worse Judge
   verdict (FABRICATED/UNREACHABLE preserved).
2. Confirm the `RecordingTransport` boundary-recording closes the fail-closed identity blind spot.
3. Confirm `query_related_claims` VERIFIED-only reuse + audit-only persistence prevents snowball
   poisoning.
4. Any residual correctness/safety gap in the composable orchestration (the sweep surgery is sub-PR-6).

Hand me APPROVE iff the fail-closed final_verdict override, the recording-transport audit capture,
the anti-poisoning KG reuse rule, and the required claim_id are correct and clinically safe.
