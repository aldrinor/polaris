# Claude architect audit — I-ecg-002

**Issue:** Evidence Contract gate enforcement
**Branch:** bot/I-ecg-002
**Canonical-diff-sha256:** 9d3e0b5fe5cc14b17841a31d690451c7c645cdebfb4401ece99c6fb41efd9bd9
**Brief verdict:** APPROVE iter 2
**Diff verdict:** APPROVE iter 4 (0/0/0/0; LOC exemption)

## Substrate honesty
- Pure-function gate module; integrated into `/api/generation` ValueError handler via `POLARIS_REQUIRE_CONTRACT=1` env flag.
- Default OFF for legacy callers' migration period (per `feedback_route_policy_questions_to_codex` — env-flag is the safe migration vehicle).
- Diff-iter loop converged tightly: iter1 wired to refuse-without-contract, iter2 added evaluate_contract enforcement on result, iter3 added per-claim-jurisdiction filtering, iter4 APPROVE.

## Algorithm correctness
- `_kept_sentence_texts`: only verifier_pass + non-dropped sections.
- `_cited_sources`: report-wide cited source_ids.
- `_claim_covering_sources`: per-claim sources cited by sentences containing that claim's statement substring (per Codex iter-3 P1).
- Per-sentence claim-substring check (per Codex iter-3 P2).
- Default-deny: blank aliases stripped; entity coverage requires non-empty match.

## §9.4 compliance
- No mocks. No magic numbers (JURISDICTION_DOMAINS named constant). No `try: pass`. No TODO/FIXME.

## Test integrity
- 33/33 PASS locally (9 gate + 11 schema + 13 generation route).
- Hermetic.
- Integration tests cover refuse-without-contract, refuse-unsatisfied-contract, accept-satisfied-contract.

## Out-of-scope follow-ups (named)
- I-ecg-002a: semantic claim match via LLM judge.
- I-ecg-002b: refine JURISDICTION_DOMAINS map; add agency-code aliasing (FDA/EMA/NICE/HC/MHRA → jurisdiction).

## CHARTER §1 LOC cap
- 469 net. Codex granted exemption iter 4 (accept_remaining). Test fixtures + per-claim helper + integration tests across 4 dimensions inseparable.

## Verdict
APPROVE.
