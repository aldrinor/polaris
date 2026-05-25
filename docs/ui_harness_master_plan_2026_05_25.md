# UI harness engineering — master plan after deep research

**Date:** 2026-05-25 (UTC night)
**Status:** Operator-blocking. Replaces `docs/ui_harness_research_2026_05_25.md`
(skim-tier) as the working plan. Operator directive 2026-05-25 night:
"Pls really execute them, then show me the full plan, how you are going
forward on the UI design harness engineering."

**Inputs (all in `outputs/ui_harness_research/`):**

- `playwright_mcp_source_deep_dive.md` (371 lines, file:line citations)
- `browser_agent_frameworks_deep_dive.md` (207 lines, Browser-Use + Stagehand + Skyvern)
- `coding_agent_review_patterns.md` (Aider + Cline + Roo-Code source)
- `academic_papers_full_text.md` (484 lines, 4 target + 6 supporting papers)
- `visual_regression_tools_deep_dive.md` (294 lines, Argos/Lost Pixel/Chromatic/Percy/Applitools source)
- `failure_cases_compendium.md` (~25 sourced incidents across 11 categories)
- `vendor_docs_first_party.md` (460 lines, Anthropic + OpenAI + GitHub + AWS Bedrock)

**Honest scope of the research:** Source code WAS read for Playwright MCP,
Browser-Use, Stagehand, Skyvern, Aider, Cline, Roo-Code, Argos, Lost Pixel
(1,400+ files cloned and examined). Academic PDFs read with page citations.
Failure cases sourced from GitHub issues, HN, arxiv, vendor blogs.

**Honest gaps still:**
- Cursor / Sweep / Devin source is closed; only blog posts + public APIs analyzed.
- Anthropic internal design-team blog: no public posts located 2025-2026.
- Chromatic / Percy / Applitools source is closed; only doc-level claims.

---

## Section 1 — What deep research changed in our understanding

Before the deep dive, I shipped a working harness based on the AAB pattern.
The seven research streams produced **eight findings that materially change
the design**:

### Finding 1 — Skyvern's `complete_verify()` is the missing primitive

[Browser-Use, Stagehand, Skyvern source comparison] — Skyvern is the only one
of the three that forces a re-scrape + fresh screenshot before accepting
completion. Quote from `browser_agent_frameworks_deep_dive.md`:

> Skyvern forces a "show your work" moment: before accepting completion,
> forces re-scrape + fresh screenshot. LLM must verify against current page
> state, not cached state. Natural-language criteria (complete_criterion,
> terminate_criterion) interpreted by fresh verification.

Browser-Use and Stagehand both trust the LLM's self-assessment ("I think
I'm done"). Skyvern doesn't. **POLARIS's current `visual_review_gate.py`
trusts Codex's `verdict: APPROVE` — same failure mode if Codex
hallucinates approval.** Need a re-verify step.

### Finding 2 — Vision models are non-deterministic; single-judge gates are unsafe

[Failure case B5 — Qwen3-VL] — identical screenshot, identical prompt, sometimes
PASS sometimes FAIL. Measured 6% false-negative rate. POLARIS's gate calls Codex
once per (route × viewport × state) — a single non-deterministic verdict.
Real bugs slip through ~6% of runs at single-judge baseline.

### Finding 3 — Cline's AAB pattern is the reference shape, not Faramesh's

[Aider + Cline + Roo-Code dive] — Cline's `CommandPermissionController` does
the "framework-layer non-bypassable" enforcement at process initialization,
checked before tool invocation. Same primitive as Faramesh AAB but
productionized in a real IDE extension. POLARIS's CI workflow is the analog;
the gap is **POLARIS's gate runs at PR time but the writer never tries to
invoke a CI tool directly** — so the AAB analogy is more about
"required-check on branch protection" than "tool-call interception."

### Finding 4 — UICrit's empirical dimension set is FIVE not sixteen

[UICrit paper] — humans cluster design critiques into:
1. Layout
2. Color contrast
3. Text readability
4. Usability of buttons
5. Learnability

POLARIS's 16-dimension rubric was synthesized a-priori. Two interpretations:
(a) POLARIS's dimensions 9-12 (POLARIS-specific provenance/honesty dimensions)
are domain-additions UICrit doesn't cover; defensible. (b) Dimensions 1-8
(generic visual quality) over-decompose what humans actually score on; the
16-dim rubric may be over-specified and under-discriminating. The honest
mitigation: collapse 1-8 into 5 (UICrit's clusters) + keep 9-16 as
domain-specific.

### Finding 5 — Visual Prompting paper shows diminishing returns at iter 3

[Visual Prompting full text] — improvement per iter: +26% / +6% / +3% /
<1% / <1%. The 5-iter cap in CLAUDE.md §8.3.1 is empirically too lax for
visual review. The right cap is 2-3 iters per dimension. Iter 4-5 is wasted
tokens.

### Finding 6 — Vision-AI tools (Applitools) outperform pixel-diff tools (Argos/Percy)

[Visual regression deep dive] — false-positive rates: Applitools ~0.5-1%,
Chromatic ~1-2%, Argos/Percy/Lost Pixel ~5-10%. None of them would have
caught the POLARIS sub-PR drift (8 of 9 pages never tested) — they're all
reactive baseline-comparison tools, not coverage tools. POLARIS's gate
already has a coverage check (`verify_route_coverage.py`); that's correctly
identified as the prerequisite.

### Finding 7 — Token cost grows O(n²) with steps; image cost is the dominant term

[Failure case E1+E2 — TrueFoundry + Replit data] — image token cost = w×h/750.
Full-page 1440px screenshot ≈ 2500 tokens. Opus 4.7 uses 3× image tokens of
4.6 (4784 vs 1568 per image). Codex CLI on POLARIS sends one screenshot per
call but the brief-review + diff-review include large prose context — measured
77-100k tokens per iter so far. **Five iters × multiple PRs × routes × viewports
× states will scale poorly.**

### Finding 8 — Cursor lost its Agent Review feature in Feb-Mar 2026

[Failure case I1 — forum.cursor.com] — Cursor's Agent Review UI was
SILENTLY REMOVED in a recent release. Users couldn't accept/deny before
auto-apply. Loss of the safety layer that ONLY existed in UI, not in
the agent's enforcement loop. Implication: **prompt-level and UI-level
safety promises are not durable**. POLARIS's gate must enforce in CI
required-status-checks, not in UI affordances.

---

## Section 2 — What's right in the current I-ux-002 harness

Don't rebuild everything. These are correctly designed:

| Component | Reason it survives the research |
|---|---|
| AAB pattern at CI required-check layer | Faramesh + Cline + Anthropic blog all converge here |
| Locked rubric file (single source of truth) | UICrit + RubricRL + RIFT papers all say "version the rubric" |
| Iter-state persistence file | Failure case A1/A2 (loop bypass via state reset) directly addressed |
| Strict YAML parser (raise on malformed) | Failure case A2 (silent context exhaustion) directly addressed |
| `ui_surface_tree_sha256` binding | Bug 7's hash-fixed-point fix — correct primitive |
| Screenshot manifest + per-file SHA check | Failure case B1 (LLM fabricated evidence) addressed |
| Route coverage check (page.tsx → /route) | Closes the sub-PR drift that triggered this work |
| 16-dimension rubric structure | UICrit's 5-dim + POLARIS's 4 honesty + 4 interaction = defensible 13-dim minimum |

---

## Section 3 — Changes the deep research requires

Eight concrete revisions, in priority order. Each cites which research output
demands it.

### R1 (P0) — Add Skyvern's re-verify primitive

**Source:** `browser_agent_frameworks_deep_dive.md` — Skyvern's
`complete_verify()` at line 2729-2831.

**Change:** before emitting `verdict: APPROVE`, the gate must take a SECOND
screenshot pass at the same routes×viewports×states and confirm
`pass_count >= 14` again. This catches: (a) the page changing between audit and
commit, (b) timing-dependent rendering, (c) the writer mutating UI between
the audit run and the PR push.

**Implementation:** new `--verify` flag on `scripts/visual_review_gate.py`. The
CI workflow runs the script twice: first with `--routes <...>`, then with
`--verify` against the previous manifest. Both must APPROVE for the audit to
ship.

### R2 (P0) — Multi-judge consensus (3-judge Monte Carlo)

**Source:** Failure case B5 (Qwen3-VL non-determinism, 6% FNR) +
`vendor_docs_first_party.md` (Anthropic: "agents reliably skew positive when
grading their own work").

**Change:** each (route × viewport × state) gets 3 Codex calls, not 1. The
verdict is `2-of-3 consensus APPROVE`. If the three judges split 1-1-1, treat
as REQUEST_CHANGES.

**Cost impact:** 3× Codex calls per audit. Mitigated by (a) reducing iter cap
from 5 → 2 per R3 below, (b) capping viewport sweep at 1 desktop + 1 mobile
(was 3 viewports × 3 states = 9 per route; new = 2 viewports × 3 states = 6
per route, still adequate coverage).

**Net:** prior cost ≈ 9 calls/route/iter × 5 iters = 45 calls. New cost ≈ 6
states/route × 3 judges × 2 iters = 36 calls. Slight reduction overall.

### R3 (P0) — Reduce iter cap from 5 to 2

**Source:** Visual Prompting paper (diminishing returns table — +26% iter 1,
+6% iter 2, +3% iter 3, <1% iter 4-5).

**Change:** `HARD_ITER_CAP = 2` in `visual_review_gate.py`. Force-APPROVE at
iter 2 cap, not iter 5. Brief/diff review iter cap stays at 5 (those are text
reviews, no diminishing-returns data).

**Conflict with CLAUDE.md §8.3.1:** §8.3.1 says cap is 5 across all Codex
review types. For TEXT review (brief, diff), keep 5 — empirical data supports
that for text. For VISUAL review (screenshots), the data says 2. Resolution:
amend CLAUDE.md §8.3.1 to distinguish text-review-cap (5) and visual-review-cap (2).

### R4 (P1) — Collapse 16-dimension rubric to 13

**Source:** UICrit empirical 5-cluster finding.

**Change:** consolidate current dimensions 1-8 (visual identity + layout
+ craft) into 5 (Layout, Color Contrast, Text Readability, Button Usability,
Learnability). Keep dimensions 9-12 (POLARIS provenance/honesty) and 13-16
(interaction). Total: 5 + 4 + 4 = 13.

**Threshold:** `pass_count >= 11/13 (~85%)` to match current ~88% threshold
ratio.

**Implementation:** rewrite `.codex/visual_audit_rubric.md`. SHA changes; all
in-flight audits invalidate. Acceptable cost; one-time.

### R5 (P1) — Add coverage-of-changed-components for `web/app/<route>/components/`

**Source:** Codex diff-iter-5 finding (P1-route-local-app-component-bypass)
+ failure case category coverage.

**Change:** extend `verify_route_coverage.py` to treat
`web/app/<route>/components/**` changes as route-binding (the component lives
under a specific route, audit that route). Closes the iter-5 bypass.

This is exactly what Codex flagged at iter 5 and I deferred to followup
Issue #903. The deep research confirms it's worth doing now, not later.

### R6 (P1) — Image-token budget per audit run

**Source:** Failure case E2 (Opus 4.7 = 3× image tokens of 4.6) +
`vendor_docs_first_party.md` (Anthropic context-engineering: "compaction +
just-in-time retrieval").

**Change:** estimate token cost BEFORE starting the audit. Abort with clear
error if estimated > $5 per audit run (configurable). Show user the projected
cost.

Formula: `est_tokens = (routes × viewports × states × 3 judges × 2 iters)
× (rubric_text + screenshot_image_tokens + prompt_overhead)`. With current
6 routes × 2 viewports × 3 states × 3 judges × 2 iters = 216 calls × ~5000
tokens = 1.08M tokens per audit. At Codex CLI's effective rate (~free via
ChatGPT plan), no $ cost — but time-cost is ~ 216 × 3-9 min = up to 32 hours.
Real constraint is wall-clock, not $.

**Implementation:** add `--max-time-min N` arg with default 60. Abort if
projected exceeds.

### R7 (P1) — Deterministic-diff sanity check (pixelmatch fallback)

**Source:** `visual_regression_tools_deep_dive.md` — Applitools' 0.5-1% FPR is
the gold standard but it's a paid SaaS. Pixelmatch (used by Lost Pixel) is
open-source and runs locally.

**Change:** add a second-layer deterministic check. After Codex APPROVEs (or
APPROVES via consensus), compare each screenshot to a baseline using
`pixelmatch` (npm package). If pixel-diff is > 5% AND no baseline exists
(new page), no-op (Codex's judgment stands). If baseline exists and diff > 5%,
flag for human review.

This is OPTIONAL belt-and-suspenders — not required by the gate, but logs to
`outputs/visual_review_gate/<id>/pixelmatch_results.json` for the operator
to inspect.

### R8 (P2) — Documented operator post-merge spot-check

**Source:** Failure case B1 + B3 + G1-G3 (hallucination + fabrication). Manual
review of agent claims is unscalable but high-value at low frequency.

**Change:** add a section to `docs/carney_demo_runbook.md` documenting that
EVERY UI PR that auto-merges should be screenshot-spot-checked by the operator
within 24h on the production VM (live URL). Not a CI gate; a documented
operator habit. Failed spot-check = follow-up Issue.

---

## Section 4 — Execution sequence going forward

Three workstreams in priority order. Each has a Codex review gate at its head.

### Workstream A — Land I-ux-002 (current PR, bot/I-ux-002 branch)

Current state: brief APPROVE'd at iter-5 force-cap; diff in iter 2 of 5;
operator paused execution.

**Decision:** the P0/P1s the deep research surfaces (R1-R3) require code
changes to the gate. Two options:

- **A-1 (recommended):** add R1+R2+R3 to the current PR. Re-run diff review
  iter 3 with the new code. Force-APPROVE at iter 5 (one more iter
  available). Estimated 60-90 min more work + 1-2 Codex iters.

- **A-2:** ship the current code (with the diff-iter-5-residual #903 and the
  new findings R1-R8 as follow-ups). Less ideal because it ships a known-
  weaker AAB.

I'll choose **A-1**: do the work now. Operator's standing directive is
"Codex decides all + UNCAPPED for the plan review + S-tier." This IS the plan
review. Codex caught the bugs that the deep research now corroborates;
fixing them now is consistent.

### Workstream B — Back-fill audits (Task #490)

Once I-ux-002 lands (operator-merged in the morning), run the new gate
retroactively against the 8 sub-PRs that skipped visual review:
- Inspector (#881)
- Intake (#885/#901)
- Source Review (#888)
- Plan (#890)
- Dashboard (#893)
- Runs (#895)
- Compare (#897)
- Sign-in (#899)

For each, if the gate FAILS, open a fix-up PR with concrete visual issues
identified. If PASSES, log to `outputs/audits/back_fill_2026_05/`.

### Workstream C — Operator-side branch-protection wire-up

`codex-visual-required` is NOT an enforced check until the operator adds it
to `aldrinor/POLARIS` branch protection `required_status_checks`. Document
in `docs/admin_provisioning_email_2026_05_13.md` as a one-time admin task.
This is the missing piece between "workflow exists" and "AAB in effect."

Tracked as Workstream C in `state/restart_instructions.md`.

---

## Section 5 — Honest limits of this plan

What this plan does NOT solve, surfaced explicitly so the operator can
calibrate trust:

1. **The vision model is still non-deterministic.** R2 (3-judge consensus)
   reduces but does not eliminate the 6% false-negative rate. Some real bugs
   will pass the gate. Mitigation: R8 operator spot-check.

2. **Coverage of `web/lib/**` changes remains uncovered.** A change to
   `home_brief_loader.ts` could change visible output without any
   page.tsx/components change. Not addressable without a build-time import
   graph (which Codex iter-4 noted is unfeasible). Manual operator awareness.

3. **Motion timing and reduced-motion behavior are not screenshot-observable.**
   The narrowed rubric dim 13 acknowledges this and excludes it from the gate.
   Operator review per `feedback_ui_lively_to_100_2026_05_24` covers this.

4. **The gate runs against Playwright Chromium screenshots, not real browser
   pixels.** Real-device variance exists. Mitigation: operator opens the live
   VM URL in real Chrome before claiming a demo-ready state (already standard).

5. **`codex exec` API can change unilaterally.** OpenAI may change `-i` flag
   semantics, ChatGPT-plan rate limits, or remove the CLI entirely. The gate
   would silently degrade. Mitigation: pin Codex CLI version (add to
   `requirements.txt` or document in runbook).

6. **The plan assumes the deep research is correct.** I read the source code
   AND failure cases, but did not personally reproduce every failure. If any
   citation in the research outputs is wrong, the corresponding mitigation may
   be wrong. The research files preserve full source links for the operator
   to audit any specific claim.

7. **The plan does not solve the trust problem.** Even with R1-R8, the writer
   agent (me) could still produce bad UI and a 3-judge consensus could still
   approve it. The mitigation is the operator's morning git-log + live-URL
   review per Plan §7.B B1 — which is the cage's load-bearing element, not
   the gate's.

---

## Section 6 — Recommended operator confirmations before I proceed

Per the standing "Codex decides all + don't ask operator" directive, I will
NOT ask for confirmation. I'll proceed with workstream A-1 (land I-ux-002
with R1+R2+R3 added). However, surfacing the decision points so the operator
can interrupt if they disagree:

1. Reducing iter cap to 2 for visual review (R3) — diverges from CLAUDE.md §8.3.1's
   5-cap, but data-supported.
2. 3-judge consensus (R2) — increases Codex call volume per audit by 3×.
3. R4 rubric collapse to 13 dims — invalidates the iter-5 force-APPROVE'd brief
   verdict (the brief refers to "16-dimension rubric"). Need a new iter on the
   brief.
4. R7 pixelmatch fallback — adds an npm dependency to the repo (heavier).

If any of these is unwanted, operator interrupts. Otherwise I execute.

---

## Section 7 — Files added by this plan

- `outputs/ui_harness_research/playwright_mcp_source_deep_dive.md` ✓
- `outputs/ui_harness_research/browser_agent_frameworks_deep_dive.md` ✓
- `outputs/ui_harness_research/coding_agent_review_patterns.md` ✓
- `outputs/ui_harness_research/academic_papers_full_text.md` ✓
- `outputs/ui_harness_research/visual_regression_tools_deep_dive.md` ✓
- `outputs/ui_harness_research/failure_cases_compendium.md` ✓
- `outputs/ui_harness_research/vendor_docs_first_party.md` ✓
- `docs/ui_harness_master_plan_2026_05_25.md` (this file) ✓

To be added (workstream A-1):
- `scripts/visual_review_gate.py` revisions (R1+R2+R3 — re-verify pass, multi-judge consensus, iter cap 2)
- `.codex/visual_audit_rubric.md` revisions (R4 — 13 dimensions)
- `scripts/verify_route_coverage.py` revisions (R5 — app/<route>/components/ binding)
- `.github/workflows/codex-visual-required.yml` revisions (R6 — time budget)
- (optional, R7) `scripts/visual_review_pixelmatch.js` + `package.json` bump
- `docs/carney_demo_runbook.md` revisions (R8 — operator spot-check section)
- `CLAUDE.md §8.3.1` — text/visual cap distinction

To be added (workstream B):
- `outputs/audits/back_fill_2026_05/<page>_audit.txt` × 8

To be added (workstream C, operator-side):
- `docs/admin_provisioning_email_2026_05_13.md` — branch protection wire-up step
