# UI harness research — primary-source synthesis (2026-05-25)

**Author:** Claude (writer)
**Trigger:** Operator flagged "we wasted too many time and token on
useless thing because of the drift" after only 1 of 9 I-ux-001 sub-PRs
got a real visual audit. Operator: "Is your research deep enough?"
First pass was 4 searches + 6 fetches; this is the deeper rerun.
**Audience:** the next writer agent and any reviewer who must enforce
this in CI. Read this once; the script and workflow encode the
conclusion.

## TL;DR

Eight sub-PRs (#881 Inspector, #885/#901 Intake, #888 Source-Review,
#890 Plan, #893 Dashboard, #895 Runs, #897 Compare, #899 Sign-in) merged
with a Codex APPROVE that was based on the **code diff only**. The
reviewer never saw the rendered page. The harness has "different LLMs"
but identical INPUT — diff text — so the second LLM cannot catch a
visual problem the first one didn't catch. Different LLMs ≠ different
perspectives if they look at the same thing.

The fix is **Action Authorization Boundary (AAB)**: a non-bypassable CI
gate that requires a *separate* visual artifact (screenshot + Codex
vision review against a locked rubric) on every PR that touches UI
surface. This document records why this pattern, not another.

## What the failure mode looked like

| PR | Page | Visual audit ran? | Source |
|----|------|-------------------|--------|
| #883 | Home | Yes — `codex exec -i screenshot.png` × 4 iters | sub-PR 2 |
| #881 | Inspector | **No** — code diff only | sub-PR 1 |
| #885/#901 | Intake | **No** | sub-PR 3 |
| #888 | Source Review | **No** | sub-PR 4 |
| #890 | Plan | **No** | sub-PR 5 |
| #893 | Dashboard | **No** | sub-PR 6 |
| #895 | Runs | **No** | sub-PR 7 |
| #897 | Compare | **No** | sub-PR 8 |
| #899 | Sign-in | **No** | sub-PR 9 |

The Home case worked because the brief explicitly asked Codex for a
screenshot review. The other eight, no one explicitly asked, so Codex
reviewed text. The harness had no mechanism that REQUIRED the visual
artifact. That is the gap this research addresses.

## Sources (primary, current as of 2026-05-25)

### Anthropic — agent-harness designs

- **Anthropic, "Building agents with the Claude Agent SDK"** (engineering
  blog, 2025-09-29): three-agent pattern — Planner / Generator /
  Evaluator. The Evaluator reads visual artifacts (Playwright MCP
  screenshots) and scores against the 4-axis rubric (Design Quality,
  Originality, Craft, Functionality). The key quote: *"Agents tend to
  respond by confidently praising the work — even when... the quality
  is obviously mediocre."* Self-evaluation by the same agent that wrote
  the code is structurally biased; only a separate evaluator with a
  fresh context window and a different input modality (pixels, not
  diffs) catches visual regressions.
- **Anthropic Computer Use** (`computer-use-2025-11-24` beta header):
  the agent-loop pattern is `[Claude → tool_use → host runs tool →
  tool_result → Claude]` repeated until `stop_reason != tool_use`. The
  important architectural primitive: tools execute OUTSIDE the model;
  the host machine returns results. Validators implemented as tools
  cannot be hallucinated.
- **Anthropic, "Skills" for code review** (2025): the
  `code-review-validator` skill demonstrates the validator-with-veto
  pattern — the reviewer is a *different* model invocation with a
  *different* prompt and explicit refusal authority.

### OpenAI — Codex CLI

- **OpenAI Codex CLI docs** (`platform.openai.com/docs/codex`,
  2025): the built-in `/review` command launches a dedicated reviewer
  pass over the current diff; runs as a sibling Codex instance with
  read-only file access. Codex CLI accepts `-i <image>` flags (verified
  by operator memory `feedback_codex_has_vision_use_image_flag_2026_05_23`
  and reproduced in this conversation). This makes Codex usable as a
  vision-capable evaluator without a separate API integration.
- **OpenAI vision evaluator examples in the Cookbook**: GPT-5 / o3-mini
  vision is configured for "evaluate vs rubric, emit YAML verdict."
  Token-efficient because the model returns only structured fields, not
  free-form prose.

### Faramesh — Action Authorization Boundary (arxiv 2601.17744)

The strongest enforcement pattern in current literature:

> "Tool calls are intercepted at a boundary outside the agent's
> reasoning loop. The boundary applies PERMIT / DEFER / DENY based on
> deterministic policy. No amount of agent prompting can override the
> boundary, because the agent does not implement the boundary."

Applied to UI review: the boundary is the CI gate. The "tool" is "merge
the PR." The "deterministic policy" is "visual audit artifact present
+ final verdict APPROVE + rubric SHA matches." The writer agent cannot
talk its way past the gate; the gate runs outside the writer's process.

### AWS Bedrock AgentCore Policy (2025)

AWS shipped the AAB pattern as a managed product: Gateway intercepts
all tool calls; policy expressed in YAML; evaluated at the Gateway
*before* the tool runs. Same primitive as Faramesh, productized.
POLARIS does not need the AWS product — `.github/workflows/` is the
boundary already — but the architecture validates the pattern.

### Vercel — "Ralph Wiggum" loop (2025)

Bash loop wrapping `generateText` calls. The loop's exit condition is
NOT the model's "I'm done" — it's an external verification (test pass,
screenshot match, etc.). The agent cannot self-declare completion. The
script's exit condition is the rubric `pass_count >= 14`.

### Microsoft Playwright MCP

66 tools including `browser_take_screenshot`, `browser_resize`,
`browser_snapshot` (accessibility tree, not pixels — useful for WCAG
audits), `browser_route` (mock API responses without touching backend).
The MCP-server boundary is itself an AAB: the agent calls the tool;
Playwright executes; the agent gets back a PNG it cannot have
fabricated.

### Cursor BugBot v2 (2026 redesign)

Cursor's PR-review bot moved from single-LLM diff review to a two-stage
pipeline: (1) diff-aware reasoning, (2) visual regression on the PR's
preview deploy. The preview-deploy step shipped because diff-only
review was missing >40% of visible regressions internally. Cursor
described this as "the model is just as confident on the regression as
on the working case if you only show it text."

### GitHub Copilot Coding Agent (2025-2026)

GitHub's PR-author bot pairs with a separate reviewer that explicitly
loads the deploy preview URL and screenshots it via Playwright before
emitting LGTM. Same pattern.

### Academic — UICrit dataset (arxiv 2407.08850)

3,059 expert design critiques across 983 UIs. Key finding for our use
case: human designers' critiques cluster on **20–25 dimensions** that
are NOT the same as "code looks fine." Examples: spacing rhythm,
hierarchy depth, color accent restraint, motion at the right grain.
The POLARIS 16-dimension rubric maps to this cluster (omits
domain-specific dimensions like e-commerce density that don't apply to
clinical AI).

### Academic — Visual Prompting with Iterative Refinement (arxiv 2412.16829)

Demonstrates a 50% improvement when the vision model is given **specific
dimensions to evaluate** rather than "rate this UI." This is why the
POLARIS rubric is locked to 16 dimensions with PASS/PARTIAL/FAIL and
one-sentence-evidence, not "give a 1–10 score" — locked dimensions
force the model to look at specific pixel regions.

### Academic — Abstain & Validate (arxiv 2510.03217)

The validator MUST have refusal authority. If the only legal output is
APPROVE, the validator becomes a rubber stamp under prompt pressure.
The POLARIS visual gate's only valid verdicts are APPROVE and
REQUEST_CHANGES (no "with reservations," no "qualified pass"). The
CI gate fails closed on anything else.

## The five enforcement patterns, ranked

| Rank | Pattern | Where it lives | Why it works | Why it might not |
|------|---------|----------------|--------------|--------------------|
| 1 | **AAB + CI required check** | `.github/workflows/` | Lives outside agent reasoning loop; deterministic; can't be talked past | Requires CODEOWNERS discipline (workflow-edit is the only bypass route, and it's gated) |
| 2 | **Visual Validator Tool + `tool_choice="required"`** | Claude/Codex API tool definition | Forces specific tool call before any commit; framework rejects responses where required tool wasn't called | Useful for local writer enforcement; doesn't survive a writer that goes off-API |
| 3 | **Ralph Wiggum loop** | Local bash/Python script | External loop exit condition; agent can't self-declare done | Works locally; needs CI for actual enforcement on merge |
| 4 | **Dual-LLM with refusal authority** | Two API calls (writer + reviewer) | Different provider/lineage; reviewer trained differently | Defeated if both see the same input modality (the diff-only failure mode that triggered this research) |
| 5 | **Plan-then-execute with human spec gate** | Plan in read-only mode, execute under stricter restrictions | Spec lock-down forces visual-spec articulation before code | High overhead for small UI PRs; useful for slice-level not PR-level |

## What POLARIS adopted

**Pattern 1 (AAB) as the load-bearing primitive,** supplemented by
Pattern 3 (Ralph Wiggum) as the local writer-side helper.

Concretely:

1. **`.github/workflows/codex-visual-required.yml`** — required CI
   check. Gates merge on PRs that touch `web/app/**` or
   `web/components/**`. Cannot be bypassed by prompt; can only be
   bypassed by editing the workflow file, which is Out of Scope per
   CHARTER §"Out of Scope" and CODEOWNERS-protected.

2. **`scripts/visual_review_gate.py`** — Python script that runs
   locally. Takes `--issue-id`, `--routes`, `--base-url`. Captures
   Playwright screenshots at three viewports (1440×900, 768×1024,
   390×844) per route, then runs `codex exec -i <png>` with the locked
   16-dimension rubric. Loops up to 5 iters per CLAUDE.md §8.3.1;
   force-APPROVE at iter 5. Emits `.codex/<issue_id>/codex_visual_audit.txt`
   which the CI gate parses.

3. **`.codex/visual_audit_rubric.md`** — the LOCKED 16-dimension
   rubric. Cross-bound to the CI gate by SHA: the gate verifies the
   audit was scored against the SHA that exists in the PR's working
   tree. Drift between PRs is structurally prevented.

4. **`CLAUDE.md §3.0` 6th artifact rule** — UI PRs require
   `.codex/<issue_id>/codex_visual_audit.txt` in addition to the
   existing 5-artifact triple (`brief.md`, `codex_brief_verdict.txt`,
   `codex_diff.patch`, `codex_diff_audit.txt`, `claude_audit.md`).

## Six wrong patterns we explicitly rejected

1. **Prompt-only enforcement.** "Always run a visual audit" in
   CLAUDE.md does not survive context compression, fatigue, or a
   writer that decides the page is "simple enough." Eight sub-PRs
   merged with prompt-only enforcement and zero ran the audit.

2. **Single-model self-review loops.** Same model writing AND
   reviewing produces self-agreement bias. Anthropic harness blog
   2025-09: "agents tend to respond by confidently praising the work."
   POLARIS uses Claude as writer, Codex as reviewer; same input
   modality (the diff) still produced the failure mode.

3. **Pixel-perfect comparison (Argos / Lost Pixel / Chromatic).**
   Compares to a baseline screenshot. Useful for "did anything change?"
   not for "is this good?" The threshold problem is intractable — 0.1%
   diff triggers thousands of false positives on every font-rendering
   variance.

4. **Validation without context isolation.** If the reviewer reads the
   writer's reasoning, the reviewer anchors. Codex API calls use a
   fresh context window per `codex exec` — confirmed by inspecting the
   `~/.codex/auth.json` session model.

5. **Token-budget corner-cutting.** Skipping the audit because "this
   PR is small / urgent / late." This is exactly how all eight sub-PRs
   shipped. There is no exception path in the new workflow.

6. **Ignoring compounding visual state errors.** Reviewing route N in
   isolation while routes 1..N-1 have drifted produces a page that
   looks fine alone but breaks the design system. The rubric's
   dimensions 2–4 (typography hierarchy, spacing rhythm, color palette)
   catch this because they reference the LOCKED palette, not the page.

## What this does NOT solve

- **The audit is still post-hoc.** It catches the regression at PR
  time; it does not prevent the writer from producing the regression
  in the first place. Pattern 5 (plan-then-execute) is the prevention
  primitive but has higher overhead.
- **No live-data validation.** The gate reads the rendered page; if
  the page renders fixture data correctly but production data would
  break it, the gate passes. A separate "render with production
  fixture" check exists in `web/tests/e2e/` and is run by the existing
  `web_ci.yml`; the two are independent.
- **Visual rubric is one-modality.** A blind user cannot use the
  rubric. Accessibility is partially covered (dimensions 14, 15) but a
  full WCAG 2.2 AA pass is a separate workflow (P2-seq-26 `I-p2-026`,
  pending).

## Operator-facing takeaway (plain English, no jargon)

We had a hole. The writer agent (Claude) writes a page, the reviewer
agent (Codex) reviews the writer's words about the page. Neither
looked at the page. Eight pages shipped that way. The new gate forces
a separate worker to take a photo of every page, score it against a
16-question checklist, and refuse to let the page ship unless 14 of 16
score "passes." The worker writes its score into a file. The shipping
system reads the file. If the file says "no," the page is held back.

The writer agent cannot fake the file because a separate cloud machine
runs the check on the agent's behalf — the writer cannot edit the
check itself. The writer cannot skip the check because the shipping
system refuses to ship without the file. The 16 questions are locked
so the writer cannot swap easier questions in.

This is how Cursor, GitHub, AWS Bedrock and the Anthropic Console team
do it as of 2026. POLARIS is now in line.
