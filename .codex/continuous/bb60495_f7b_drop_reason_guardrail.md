# Per-commit Codex brief — `bb60495`

**Commit:** `bb60495 PL: v6.2 F-7b guardrail — a11y test for verified-sentence drop_reason path`
**Format:** v2 minimal
**Files changed (3):**
- `tests/v6/fixtures/evidence_contract_v1/golden_run_with_drop_reason.json` (new fixture)
- `src/polaris_v6/api/bundle.py` (+1 entry in _GOLDEN_RUN_INDEX)
- `web/tests/e2e/accessibility.spec.ts` (+15 lines, new describe + 1 test)

## What this commit does

Closes the test-coverage gap noted in 3cf4737 brief. F-7 fixed the destructive token at `inspector/[runId]/page.tsx:315` ("Dropped: <reason>" annotation) — but no axe test exercised it because no golden fixture populated `drop_reason`. So F-7 was code-correct but regression-gateless.

This commit:
1. **New fixture** — `golden_run_with_drop_reason.json`. A clinical metformin run with 2 verified_sentences:
   - 1 PASSING sentence (ev_drop_001 cited).
   - 1 DROPPED sentence (`drop_reason: "no_provenance_tokens; verifier_local_pass=false"`).
2. **Backend registry** — `_GOLDEN_RUN_INDEX["golden_with_drop_reason"] = ...` in `bundle.py`. Required FastAPI restart to pick up.
3. **New a11y test** — visits `/inspector/golden_with_drop_reason`, clicks "Verified sentences" tab, asserts "Dropped:" text visible, runs axe.

Verified: 9/9 a11y + 9/9 inspector = 18/18 PASS in 24.3s. The test would FAIL on the pre-F-7 token (4.04:1 contrast) and PASSES on the post-F-7 token (~17:1).

## Acceptance criteria

1. **Regression gate** — if a future change reverts F-7 (or introduces a new `text-destructive` token elsewhere on this page), this test surfaces it loudly with axe diagnostic.
2. **Real fixture, not synthetic** — the JSON validates against `EvidenceContract.model_validate_json` (loaded server-side via the same parser as production).
3. **Backend registry update is intentional** — adds 1 entry, doesn't refactor the index. Codex must verify no accidental rename of existing keys.
4. **Test asserts BOTH** that the "Dropped" text appears (proves we're on the right surface) AND axe-clean (proves the regression gate works).
5. **No mocking** — hits real backend `/runs/golden_with_drop_reason/bundle` over HTTP.

## Codex focus

- **P1:** The fixture has 2 verified_sentences; only the second has drop_reason. Should the test ALSO assert that the first sentence (without drop_reason) renders without the annotation? Tighter regression gate against accidentally rendering "Dropped: null" or similar.
- **P2:** No corresponding sycophancy / contradiction fixture covers this multi-state pattern. Likely fine for this commit; flagging for future fixture coverage.
- **P3:** The fixture's `cost_usd: 0.31` and other fields are arbitrary. Document acceptable ranges in the schema or fixture-conventions file? Out of scope; fine for now.

## Cross-review

Lands at `outputs/audits/continuous/bb60495/cross_review.md`. Counter past 5/5 — **about to trigger cycle-3 adversarial subagent** on the post-909eb4c batch (dbe62e0, cc10303, 8ae03b6, 9fe4de9, 3cf4737, bb60495 — 6 commits but cycle-3 brief will scope to the F-7+F-7b+F-8 trio for tightest review).
