**Program status + a hard lesson banked (2026-06-10).**

The 9 issues' release **logic** is done + Codex-approved (withhold→always-release+label; per-claim
gates still binding). That stands.

Re-audit surfaced that the source-**quantity** layer was never measured — the same magic-number class
we keep repeating. The generator pool cap (`PG_LIVE_MAX_EV_TO_GEN`) was a guess (20→150→now **1500**);
the per-section cap 40 traces to a stale OpenRouter body-size guard, not quality; and the actual saved
drb_76 run shows the dominant ~90% source loss is UPSTREAM at fetch→extract→merge (~500 fetched → 46
evidence rows; the cap never engaged), not at the cap we'd been "fixing."

**Lesson:** the Claude–Codex workflow verifies a diff against its brief; it cannot catch a brief that
asserts the wrong number or targets the wrong stage. Measure the funnel FIRST, then brief.

Next execution is tracked in **#1204** (funnel-first): (1) trace the real funnel + classify each drop
legitimate-vs-throttle, (2) fix the dominant stage + bake-off the guessed caps from data (#1085), (3)
paid VM run + §-1.1 audit (operator spend-gated). Run via the Claude Codex Workflow, real-time monitored.
