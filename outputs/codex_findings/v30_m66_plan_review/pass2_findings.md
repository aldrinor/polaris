# V30 M-66 fix plan v2 review (pass 2)

**Verdict**: CONDITIONAL-blockers

## Pass-1 issue resolution status

1. Blocker 1 (M-66a over-positioning): RESOLVED - M-66a is now telemetry-only this cycle, and M-66a-R is explicitly deferred until after M-66b-T plus drop telemetry confirm legitimate overlap drops. That guarantees source enrichment happens before any verifier relaxation. M-66a-T cannot itself mask a verifier bug because it adds observability only; at worst a latent verifier issue remains undiscovered if M-66b-T already fixes the slot.
2. Blocker 2 (acceptance false-pass): PARTIAL - the 7-efficacy accounting, CVOT deferral, 4-of-6 mandatory regulatory set, and completeness downgrade are real improvements. But the Trial Summary "real content" gate is still specified as prose rather than a concrete negative regression test or validator, so fragment rows can still slip through depending on implementation. The plan text also re-opens a false-pass path by asserting both `Zero dimensions LB` and later that the `2 BB + 4 BO + 1 LB` scenario still meets ship.
3. Medium 1 (M-66b split): RESOLVED - M-66b is meaningfully split into regulatory `url_pattern` fetch vs OA PDF full-text fetch, each with its own acceptance target. `_fetch_url_pattern` is a shared helper, but the leg-specific tests and metrics still let you attribute gains correctly if they assert the distinct dispatch paths.
4. Medium 2 (projection honesty): PARTIAL - narrative-depth honesty is fixed (`LB` acknowledged). Structure is no longer over-projected to `BB`, but `BO` is still somewhat optimistic because the plan adds acceptance checks more clearly than it adds a deterministic table/timeline repair.
5. Medium 3 (RetrievalAttempt fix already landed): RESOLVED - `src/polaris_graph/retrieval/frame_fetcher.py:817-825` now emits the canonical `RetrievalAttempt(...)` shape on the DOI-mismatch rejection path, and `tests/polaris_graph/test_m56_frame_fetcher.py:454-527` covers mismatch reject, match accept, and missing-PubMed-DOI fallback. I also reran `python -m pytest tests/polaris_graph/test_m56_frame_fetcher.py`: 39/39 passed.
6. Nit (M-66c order): RESOLVED - M-66c is genuinely independent of OA full-text. The Thomas clamp row already has abstract-only retrieval, so the field realignment does not depend on M-66b-T. It is cheap, though not critical path.

## Answers

1. Split criteria false-pass prevention: Mostly, but not fully. The subsection accounting and regulatory hard gate now block the big pass-1 false passes. The remaining hole is the Trial Summary "real content" filter: the plan names the bad outputs (`insulin glargine in adults with type`, `at week 18`) but does not yet say how the code or test will deterministically reject truncated comparator, endpoint, and result fragments. I would not call this fully closed until there is an explicit negative regression test or validator spec for those fragment cases. I would keep the 4-of-6 regulatory gate for this cycle; pushing to 6-of-6 would effectively force M-61/manual completion into M-66 scope.
2. Projection achievability: `2 BB + 4 BO + 1 LB` is possible, but it is still a best-case honest projection, not a bankable expected result. The most fragile `BO` cell is Structure: the plan now measures table/timeline integrity, but it still does not describe a deterministic repair to M-42b parsing beyond rejecting obviously junk rows. I would treat Structure as probabilistic `BO`, not pre-booked.
3. Ship decision rule clarity: Not clear enough. `outputs/audits/v30_phase2/fix_plan_run3_v2.md:168-169` says `>=5/7` BB or BO and `Zero dimensions LB`, but `outputs/audits/v30_phase2/fix_plan_run3_v2.md:187-188` says the `1 LB` scenario still meets ship. Those are different gates. If you want the lenient rule, rename it as a Phase-2 checkpoint or ship-and-continue rule; do not label it BEAT-BOTH ship. If you want BEAT-BOTH ship, keep the strict zero-LB gate and accept that M-67 narrative work is pre-ship.
4. Medium #3 test coverage: The 3 new tests are sufficient for the changed branch. A fourth test with CrossRef abstract present plus PubMed DOI mismatch is not required for this fix, because `src/polaris_graph/retrieval/frame_fetcher.py:793` skips PubMed entirely when `abstract_crossref` exists, so the mismatch guard is not on path and PubMed metadata cannot leak through that branch. If you want a fourth test, the better one is "CrossRef abstract present => PubMed not called."
5. New blockers: Yes. New blocker: the ship-rule contradiction above. New medium: the M-66b-R/T test text says "mocked httpx", but the proposed helper is explicitly AccessBypass-backed, so the tests should stub `_fetch_url_pattern` or the AccessBypass result rather than rely on transport mocking alone.

## Findings (if any new)

- Blocker: Ship gate is internally inconsistent. `outputs/audits/v30_phase2/fix_plan_run3_v2.md:168-169` requires zero `LB`, then `outputs/audits/v30_phase2/fix_plan_run3_v2.md:187-188` says the `2 BB + 4 BO + 1 LB` scenario still meets ship. Pick one operative gate before implementation.
- Medium: M-66b acceptance test wording is implementation-misaligned. `outputs/audits/v30_phase2/fix_plan_run3_v2.md:58-73,90-99` routes through AccessBypass-backed `_fetch_url_pattern`, so `mocked httpx` alone is the wrong test seam.

## Next

On CONDITIONAL / REJECT: plan v3.
