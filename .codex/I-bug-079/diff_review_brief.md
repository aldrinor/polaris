# Codex Diff Review — I-bug-079 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-bug-079 — async/sync collision in clinical_classifier (verification-only)
**Branch:** bot/I-bug-079
**Brief:** APPROVED iter 3 (iter1 REQ_CH 2P1 → iter2 REQ_CH 1P1 not-at-HEAD → iter3 APPROVE 0/0/1P2 accept_remaining; P2 wording-only; non-blocking)
**Canonical-diff-sha256:** `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` (SHA of empty string — diff is empty post-audit-exclusion; deliverable lives entirely in audit-excluded paths)

## What changed

**No source-code changes.** The bug is already fixed at HEAD per `outputs/audits/I-bug-079/verification.md`. This PR ships verification artifacts only:

- `outputs/audits/I-bug-079/verification.md` — file:line refs to the existing fix + reproducible 5-test pytest output.
- `outputs/audits/I-bug-079/claude_audit.md` — standard Issue audit.

Both files are committed on the branch (visible at HEAD via `git show HEAD:outputs/audits/I-bug-079/...`). They are excluded from the canonical-diff-sha256 per Issue convention but ARE present in the PR for direct filesystem read.

## Existing fix at HEAD (no change)

`src/polaris_graph/scope/clinical_classifier.py:214-243`:
- Lines 228-237: `asyncio.get_running_loop()` detection; raises RuntimeError on async-context misuse.
- Lines 239-242: `asyncio.run(client.generate(...))`.
- Line 243: returns `result.content if hasattr(result, "content") else str(result)`.

## Existing 5 regression tests (no change)

`tests/polaris_graph/scope/test_default_llm_completion_async_fix.py` — 5/5 PASS via `PYTHONPATH=src python -m pytest ... -v`. Output captured in `verification.md`.

## Risks for Codex Red-Team

1. **Empty canonical diff.** SHA stamps the empty post-exclusion diff. The deliverable IS the audit artifacts; Codex reads them directly via filesystem (`git show HEAD:outputs/audits/I-bug-079/...`).

2. **No source-code change in PR.** Confirmed via `git diff origin/polaris..HEAD -- :(exclude).codex/I-bug-079/ :(exclude)outputs/audits/I-bug-079/` returning empty. The work is verification + documentation, not a code change.

3. **Real-key smoke not executed.** Per CLAUDE.md §8.4 + cost. Marked WAIVED in `verification.md`. User-driven follow-up if desired.

4. **`PYTHONPATH=src` requirement.** Project doesn't pip-install itself; standard test invocation requires `PYTHONPATH=src`. Documented in `verification.md`.

5. **Brief iter-3 P2 advisory (non-blocking).** Codex noted that the unit test exercises the default path via monkeypatched OpenRouter module, NOT a stubbed `completion_fn`. The coverage is equivalent (both routes verify the async-to-sync bridge); wording in `verification.md:37` could be clarified. Non-blocking — coverage relevant per Codex.

6. **No new package.json / requirements.txt dep.**

7. **CHARTER §1 LOC cap.** 0 source-code LOC. Cap inapplicable.

## Out of scope

- Real-key smoke → user-driven follow-up.
- Refactoring the function for style → LAW V no-polish.

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
