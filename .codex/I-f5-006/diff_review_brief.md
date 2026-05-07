# Codex Diff Review — I-f5-006 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

**Issue:** I-f5-006 — Inspector synthesis-claim badge
**Brief:** APPROVED iter 3
**Canonical-diff-sha256:** `c2b18a4f19fffdb053547a408c1cd590601414a9a937605895326ff469157776`
**LOC:** 172 net (under CHARTER §1 200-cap)

## Files

```
src/polaris_graph/generator2/verified_report.py           +33 (is_synthesis_claim field + validator)
src/polaris_graph/generator2/strict_verify.py             +13 (is_synthesis_claim param + tokenless pass path)
tests/polaris_graph/generator2/test_verified_report.py    +44 (4 new tests)
tests/polaris_graph/generator2/test_strict_verify.py      +25 (2 new tests)
web/lib/api.ts                                            +1
web/app/generation/components/sentence_inspector.tsx      +18 (SynthesisClaimBadge + render condition)
web/app/sentence_hover_test/_demo.tsx                     +10 (sec_x:15)
web/tests/e2e/sentence_inspector_synthesis.spec.ts        NEW +28 (2 Playwright tests)
```

## What changed

### Backend
- `VerifiedSentence.is_synthesis_claim: bool = False` field added with description.
- New `_synthesis_claim_consistency` validator forbids: (a) is_synthesis_claim=True + verifier_pass=False, (b) is_synthesis_claim=True + provenance_tokens not empty, (c) is_synthesis_claim=False + verifier_pass=True + provenance_tokens=[].
- `verify_sentence(... is_synthesis_claim=False)` — when True AND no tokens, returns (True, None) without running token checks. When False, preserves existing no_provenance_token behavior.
- `verify_sentence_to_record(... is_synthesis_claim=False)` propagates the flag and constructs valid VerifiedSentence with empty tokens + verifier_pass=True + evaluator_agrees=True + is_synthesis_claim=True.

### Backend tests
- 4 new VerifiedSentence schema tests: synthesis-claim allowed, with-tokens forbidden, with-pass-false forbidden, kept-non-synthesis-must-have-tokens.
- 2 new strict_verify tests: synthesis-claim verify_sentence pass path, verify_sentence_to_record record construction.
- 144 generator2/ tests pass.

### Frontend
- `web/lib/api.ts`: `is_synthesis_claim?: boolean` (OPTIONAL).
- `sentence_inspector.tsx`: `SynthesisClaimBadge` component (testid `inspector-synthesis-claim`, violet border + tooltip rationale). Rendered alongside AgreementBadge when `sentence.is_synthesis_claim === true`.
- `_demo.tsx`: APPENDED sec_x:15 — synthesis-claim sentence (no tokens, verifier_pass=true, is_synthesis_claim=true).
- 2 Playwright tests: synthesis-claim sentence shows badge; non-synthesis sentence does NOT.

## Verification
- `PYTHONPATH=src pytest tests/polaris_graph/generator2/`: 144 passed.
- `npx tsc --noEmit` (web/): exit 0.

## Risks for Codex Red-Team

1. **Validator interaction:** three validators on VerifiedSentence (`_drop_reason_consistency`, `_evaluator_agreement_consistency`, `_synthesis_claim_consistency`) all run mode="after". No conflicts because synthesis-claim path requires verifier_pass=True (which already requires drop_reason=None and is compatible with evaluator_agrees=True).
2. **Existing fixtures back-compat:** `is_synthesis_claim` defaults to False. No fixture changes required.
3. **Schema gap closed:** non-synthesis kept sentences with empty provenance_tokens are now schema-rejected (closes Codex iter-1 P2). Today's strict_verify already prevents this at runtime; the schema-level guard is defense-in-depth.
4. **Frontend defensive default:** `is_synthesis_claim` is optional in TS; undefined/false → no badge.
5. **§9.4 N/A frontend.**
6. **CHARTER §1 LOC cap:** 172 net. Under 200.
7. **No new package dep.**

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
