## Why this issue exists

The permanent-fix program (#1194, I-perm-001..009) made the release **logic** correct:
withhold→always-release-with-honest-per-claim-confidence, per-claim faithfulness gates still
binding. That part stands and is Codex-approved.

Re-audit on 2026-06-10 found the **source-quantity layer was never validated** — the same class
of mistake repeated:
- The generator-facing pool cap `PG_LIVE_MAX_EV_TO_GEN` was an unbenchmarked guess: 20 (the
  98%-drop) → 150 (interim, still ~90% of a 1500-row pool) → **now 1500 (full extracted set)**.
- The per-section cap `PG_MAX_EV_PER_SECTION=40` traces to a STALE OpenRouter >100K-token-body
  400 guard (M-24, DeepSeek V3.2 era). Current stack is 200K–1M context, confirmed live on
  OpenRouter — so 40 is bounded by nothing real. Its optimum is a bake-off question, not a guess.
- **The dominant ~90% source loss in the actual saved run is UPSTREAM at extraction, NOT at the
  cap.** `outputs/audits/beatboth8/drb_76/manifest.json`: ~800 discovered, ~500 fetched, but only
  **46 evidence rows** reached the generator (`evidence_selection.evidence_selected=46`,
  `dropped_count=0` — the 150 cap never engaged because 46 < 150). The collapse is fetch→extract→merge.

**Lesson to bank:** briefs asserted quantities (40 / 150 / 0.30 relevance floor) that were never
measured, and no brief targeted the stage where loss actually dominates. The Claude–Codex workflow
verifies a diff **against its brief**; it cannot tell you the brief aimed at the wrong number or the
wrong stage. Fix: measure the funnel FIRST, then write the brief.

## Already done (committed on `bot/I-ready-017-faithfulness`)

- `PG_LIVE_MAX_EV_TO_GEN` 150 → **1500** (full extracted set; no pre-section pool throttle). The
  generator is 1M-context; a section prompt only ever carries `PG_MAX_EV_PER_SECTION` rows, so the
  pool cap had no provider justification.
- Preflight floor locked at 1500 (`_BENCHMARK_EXTRA_ENV_FLOORS`) so it cannot silently regress.
- Three slate test fixtures updated to the new value (not relaxed).

## The 3 tasks (execute via Claude Codex Workflow, real-time monitored)

### Task 1 — FUNNEL TRACE (offline, no spend)
Trace the real source funnel on the saved drb_76 run (and a fresh 1-query canary on the VM if
needed): discovered → fetched → extracted → merged → selected → reached-generator →
survived-verification. Per-stage drop count + per-drop-REASON breakdown at the dominant stage
(dead-link / fetched-200-but-empty / duplicate / low-tier / threshold). Classify each drop as
legitimate (genuinely unusable) vs throttle (good source lost to a number).
**Acceptance:** a per-stage funnel from REAL run data + a reason-classified breakdown of the
dominant loss stage. Counts here are bug-forensics diagnostics, NOT a quality metric (§-1.1).

### Task 2 — FIX THE DOMINANT STAGE + BAKE-OFF THE GUESSED CAPS (offline build, bake-off = spend)
If the dominant loss is an over-aggressive throttle, fix it behind a flag with a real before/after
row count on saved data. Run the empirical bake-off (folds in #1085 / I-ready-001b) to set
`PG_MAX_EV_PER_SECTION` and `PG_RELEVANCE_FLOOR` (0.30) from recall/faithfulness on the locked
slice — no hand-picked numbers.
**Acceptance:** dominant-stage fix flag-gated + measured; caps chosen by data, not guess.

### Task 3 — PAID RUN + §-1.1 AUDIT (spend, OVH VM, operator-gated)
The paid beat-both run on `ubuntu@51.79.90.35`, then the line-by-line §-1.1 faithfulness audit of
each `report.md` vs its cited spans + beat-both scoring vs gpt_5_5_pro / gemini_3_1_pro.
**Acceptance:** per-claim §-1.1 verdict (VERIFIED/PARTIAL/UNSUPPORTED/FABRICATED/UNREACHABLE), not
metadata. **Spend boundary: operator sets `PG_AUTHORIZED_SWEEP_APPROVAL` on the VM — Claude does not.**

## Links
Umbrella #1194 · cap #1070 · selection-90%-throwaway #1197 · extraction #1201 · bake-off #1085 ·
rerank-not-first-N #1078 · the run #1132
