# Source-funnel-first execution plan (GitHub #1204)

**Canonical tracker: GitHub issue #1204.** This doc holds the durable engineering content
(funnel-trace methodology + the lesson). If they drift, #1204 wins.

## The lesson (why this plan exists)

The permanent-fix program (#1194) made the release **logic** correct (withhold→always-release+label,
per-claim faithfulness gates still binding — done, Codex-approved). But the source-**quantity** layer
was never measured:

- `PG_LIVE_MAX_EV_TO_GEN` (generator pool cap) was a guess: 20 (98%-drop) → 150 (still ~90% of a
  1500-row pool) → **1500** (full extracted set, fixed 2026-06-10).
- `PG_MAX_EV_PER_SECTION=40` traces to a STALE OpenRouter >100K-token-body 400 guard (M-24, DeepSeek
  V3.2 era). Current stack is 200K–1M context (verified live on OpenRouter), so 40 is bounded by
  nothing real. Its optimum is a bake-off question.
- The dominant ~90% source loss in the **actual saved drb_76 run** is UPSTREAM at fetch→extract→merge
  (~500 fetched → 46 evidence rows; the cap never engaged, `dropped_count=0`), NOT at the cap.

**Banked rule:** the Claude–Codex workflow verifies a diff **against its brief**. It cannot catch a
brief that asserts the wrong number or targets the wrong stage. So: **measure the funnel FIRST, then
write the brief.** Never let a brief assert a quantity that wasn't measured.

## The funnel (what Task 1 must measure on REAL run data)

```
discovered → fetched → fetched-non-empty → extracted(rows) → merged/deduped → relevance-floored
→ selected(to-generator) → assigned-to-sections → generated(sentences) → survived strict_verify+4-role
```

For each arrow: count in, count out, count dropped, and at the **dominant** drop stage a per-REASON
breakdown (dead-link / fetched-200-but-empty / duplicate / low-tier / below-relevance-floor / cap).
Classify each drop **legitimate** (genuinely unusable) vs **throttle** (a good source lost to a number).
Counts here are bug-forensics diagnostics — NOT a report quality metric (§-1.1 ban stands for quality).

## The 3 tasks (execute via Claude Codex Workflow, real-time monitored)

1. **Funnel trace** — offline, no spend. Per-stage funnel from drb_76 (+ fresh 1-query VM canary if
   the saved run predates the current slate). Output: the funnel table + dominant-stage reason split.
2. **Fix the dominant stage + bake-off the guessed caps** — offline build; bake-off = spend. Fix an
   over-aggressive throttle behind a flag with a real before/after row count; set `PG_MAX_EV_PER_SECTION`
   and `PG_RELEVANCE_FLOOR` from recall/faithfulness on the locked slice (folds in #1085 / I-ready-001b).
3. **Paid run + §-1.1 audit** — spend, OVH VM `ubuntu@51.79.90.35`, **operator-gated**. Beat-both run,
   then line-by-line §-1.1 faithfulness audit of each `report.md` vs cited spans + scoring vs
   gpt_5_5_pro / gemini_3_1_pro. **Spend boundary: operator sets `PG_AUTHORIZED_SWEEP_APPROVAL`; Claude
   does not.**

## Already done (committed, `bot/I-ready-017-faithfulness`)

- `PG_LIVE_MAX_EV_TO_GEN` 150 → 1500 + preflight floor locked at 1500 (`run_gate_b.py`).
- 3 slate test fixtures updated to 1500 (not relaxed). 18 gate-B guard tests green.
