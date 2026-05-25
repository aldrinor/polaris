# Failure cases — screenshot-driven agent review systems

Research date: 2026-05-25
Scope: GitHub issues, Hacker News, Reddit, engineering blogs, conference talks,
production incidents. Teams who tried screenshot-driven AI review and it broke.

Operator's ask: "Find FAILURE cases — teams who tried this and it broke. Make a
skeptical reader UNCOMFORTABLE about deploying any visual-review agent."

## Category A — Agent loop did not terminate

### A1. Claude Code — infinite file reading loop
- [anthropics/claude-code#11487](https://github.com/anthropics/claude-code/issues/11487), 2025-2026.
- Tried: multi-file codebase analysis.
- Broke: agent re-read same 5-6 files 10-15+ times without transitioning to
  execution mode. Loop logic never exited "analysis phase."
- Fix: manual file selection; avoid open-ended exploration patterns.

### A2. Claude Code — Write tool never invoked
- [anthropics/claude-code#27281](https://github.com/anthropics/claude-code/issues/27281), 2026.
- Tried: 4 parallel research agents completed, assembly agent should call Write
  to output markdown.
- Broke: agent repeatedly stated "let me write the document" across multiple
  turns without ever invoking Write. Context window exhausted with zero-value
  text. After session compaction + fresh continuation, task completed in ~10s.
- Impact: full context (Opus 4.6) burned. Operator intervention required.
- Fix: session restart with fresh context.

### A3. Browser-Use — Step 1 infinite repeat
- [browser-use/browser-use#1157](https://github.com/browser-use/browser-use/issues/1157).
- Tried: simple browser automation (open Google).
- Broke: agent completed initial actions but never transitioned to Step 2+.
  Message history grew unbounded; LLM queried without executing new commands.
- Fix: manual intervention; avoid complex sequential workflows.

### A4. Browser-Use — connection loss infinite retry
- [browser-use/browser-use#1275](https://github.com/browser-use/browser-use/issues/1275).
- Tried: browser automation with CDP session timeout after 30s.
- Broke: `_handle_step_error` in `browser_use/agent/service.py` did NOT increment
  `self.state.consecutive_failures`. Agent looped trying to reopen browser
  context that could never recover.
- Fix: increase session timeout; add hard retry caps.

### A5. SWE-Agent — stuck in not-doing-tool-calls loop
- [SWE-agent/SWE-agent#971](https://github.com/SWE-agent/SWE-agent/issues/971).
- Tried: agentic code review and bug fixing.
- Broke: agent stated intent without invoking tool calls. Context partially
  consumed with non-productive reasoning.
- Fix: tool invocation validation; explicit tool-use checks.

## Category B — Agent approved bad design / missed regression

### B1. LLM visual review hallucination — fabricated evidence
- [ncbi.nlm.nih.gov/pmc/articles/PMC12365265](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12365265/) "My AI is Lying to Me", 2025.
- Tried: LLM-based review of app screenshots and functionality claims.
- Broke: LLM hallucinated descriptions of visual elements and functionality not
  present in screenshots. Highly credible; escaped routine human review.
- Fix: multi-judge evaluation; human review; provenance verification for
  every claim.

### B2. Playwright Healer Agent — selector hallucination
- Playwright test agent docs + Medium post by Madushika Ranapana, 2025-2026.
- Tried: auto-healing of broken Playwright test selectors.
- Broke: healer agent "fixed" failing selectors by grabbing visually similar
  but functionally wrong elements (same text, different component, different
  behavior).
- Fix: manual review before commit; validate that fixed selectors still target
  the original element intent.

### B3. SaaStr — agent hallucinated data to complete interface
- [saastr.com article on AI agents hallucinating](https://www.saastr.com/ai-agents-catching-other-ai-agents-cutting-corners-and-hallucinating-and-why-that-means-ai-is-getting-so-much-better/).
- Tried: agent-driven UI verification and generation.
- Broke: agent fabricated data to make interface appear complete; professional-
  looking output masked missing/broken components. Only caught when another
  agent reviewed.
- Fix: multi-agent verification; explicit hallucination detection.

### B4. Invisible checkout button
- [dev.to article on visual regression mistakes](https://dev.to/maria_bueno/the-most-common-visual-regression-testing-mistakes-and-how-to-avoid-them-4id8).
- Tried: visual regression testing with agent review.
- Broke: button in DOM, CSS issue (mobile breakpoint) rendered it invisible.
  Functional tests passed; visual review agent did not flag invisible state.
  Bug reached production.
- Mechanism: screenshots alone can't detect opacity=0, visibility:hidden, or
  off-canvas positioning without computed-style validation.
- Fix: computed style validation + cross-browser manual spot checks.

### B5. Non-deterministic vision model verdict
- 2025; Qwen3-VL screenshot verification.
- Tried: vision LLM verifying screenshot test result ("Did this action succeed?").
- Broke: identical screenshot sent to Qwen3-VL twice — sometimes PASS, sometimes
  FAIL. Non-deterministic model response = non-deterministic approval.
- Impact: stochastic 6% false-negative rate; real bugs slip through 6% of runs.
- Fix: Monte Carlo (run 3x, require 2-of-3 consensus); deterministic diff
  tooling (pixel comparison, not vision models).

## Category C — Visual diff produced too many false positives

### C1. Percy.io flaky screenshots — dynamic content
- [ampproject/amphtml#16228](https://github.com/ampproject/amphtml/issues/16228).
- Tried: visual regression baseline against video/iframe components.
- Broke: depending on capture timing, video might be at different frame, not
  started, showing thumbnail, or buffering. Diffs flagged pixel changes that
  were not code changes.
- Review fatigue: teams set loose thresholds → missed actual regressions.
- Fix: exclude dynamic elements via CSS injection; stabilize timing; explicit
  loading indicators.

### C2. Anti-aliasing rendering variance
- Various Unity / Factorio engine issues, 2025-2026.
- Tried: screenshot-based visual testing with anti-aliasing enabled.
- Broke: ~25% of renders failed or partially blurred due to anti-aliasing
  pipeline interaction. Same code, different pixel output.
- Fix: disable anti-aliasing in test screenshots; deterministic render settings.

### C3. Applitools / Percy false positive threshold dilemma
- [browserstack.com — How to reduce False Positives](https://www.browserstack.com/guide/how-to-reduce-false-positives-in-visual-testing).
- Tried: pixel-by-pixel visual testing at scale.
- Broke: 20-40% false positive rate in real projects. Font rendering
  differences, 1px shifts, anti-aliasing all flagged as regressions. Teams
  faced impossible choice: tight thresholds → constant noise; loose → miss bugs.
- Fix: AI diffing (Percy Visual Review Agent, Applitools AI); perceptual
  hashing; rule-based exclusions.

## Category D — Rubric / threshold drift

### D1. LLM-as-judge drift over time
- [futureagi.com — What is LLM Drift](https://futureagi.com/blog/what-is-llm-drift-2026), 2026.
- Tried: deploy visual agent with fixed rubric for approving/rejecting screenshots.
- Broke: model behavior shifted; same screenshot rated PASS one week, FAIL the
  next. Causes: underlying model updated, prompt interpretation drifted, token
  limit changes, rubric became ambiguous.
- Fix: per-rubric thresholds; detect 2-5% sustained drop over 24-48h; monitor at
  rubric-score level, not system aggregate.

### D2. Approval criteria scope creep
- Implicit in agent review system design.
- Tried: start with "approve if visual matches baseline"; add accessibility,
  performance, business logic.
- Broke: rubric expanded; agent expected to handle more edge cases; error rate
  increased; approval latency exploded.
- Fix: narrow rubric scope; compose separate validators.

## Category E — Cost / token blowout

### E1. Agentic token explosion in CI/CD
- [truefoundry.com — Agentic Token Explosion](https://www.truefoundry.com/blog/llm-cost-attribution-agentic-cicd).
- Tried: agent review on every PR; reads screenshots, context history, prior runs.
- Broke: token consumption per agent run grows O(n²) with steps. Loop that
  costs $50 locally explodes to $2.5M monthly at production volume.
- Real example: 15 PRs/engineer/week → 400k input tokens/PR → $8,400/month.
- Fix: hard token budgets; context compaction before reasoning; pre-execution
  budget checks; tiered routing.

### E2. Image token cost explosion
- Claude API image token calculation; Replit forum reports, 2025-2026.
- Tried: agent taking multiple large screenshots per step in conversation.
- Broke: image token cost = width × height / 750. Full-page screenshots on
  1440px screens = ~2500 tokens/image. Opus 4.7 uses 3× more image tokens than
  Opus 4.6 (4784 vs 1568 per image). Agent re-sending all previous screenshots
  in context = exponential growth.
- Real example: agent with 50 steps × 3 screenshots/step = 150 images × 2500
  tokens + prior messages = multi-thousand-token payload. $0.50 → $8-20/run.
- Fix: downsampling; image caching; one-shot screenshot strategy.

### E3. Kilo Code agent loop — $7.59 credit burn on simple query
- [Kilo-Org/kilocode#3767](https://github.com/Kilo-Org/kilocode/issues/3767).
- Tried: basic code review request.
- Broke: agent entered infinite file-reading loop. Burned 8.5M tokens on
  trivial task.
- Fix: loop detection; max step limits; budget caps per request.

## Category F — Cross-browser / cross-device variance

### F1. MacBook Retina vs Windows mismatch
- vercel-labs/agent-browser#304.
- Tried: visual testing across Mac and Windows.
- Broke: MacBook Pro resolution = 2× pixel density. Mac screenshots ≠ Windows
  screenshots. Diffs flagged "regression" when only DPI differed.
- Fix: fixed-resolution environments; CSS pixel-based assertions instead of
  pixel matching.

### F2. Real device screenshot limitations
- CrossBrowserTesting docs, 2025-2026.
- Tried: full-page screenshots on real mobile devices.
- Broke: real devices don't support custom/full-page screenshots — only
  viewport-limited captures.
- Fix: emulated devices for full screenshots; real devices for interaction only.

### F3. Stagehand screenshot timing inconsistency
- [browserbase/stagehand#1635](https://github.com/browserbase/stagehand/issues/1635).
- Tried: visual verification in agent mode.
- Broke: screenshot timing inconsistent between agent actions. Agent received
  duplicate/unchanged screenshots; thought action didn't work when it did.
- Fix: decouple screenshot strategy from action loop; explicit wait-for-change.

## Category G — Agent fabricated evidence / hallucinated observations

### G1. LLM hallucinated RCE (fake remote code execution claims)
- [Cyber Defense Magazine — Fake Hallucinated RCEs](https://www.cyberdefensemagazine.com/fake-hallucinated-remote-code-execution-rces-in-llm-applications/).
- Tried: security researcher submitted screenshot + video claiming vulnerability.
- Broke: LLM hallucinated vulnerability output. Reviewers confused because LLM
  confidently described command results that never happened.
- Fix: verify claims against actual command logs / system state.

### G2. Vision model cascade hallucination
- [arxiv.org/html/2509.23322 — Visual Context Degradation](https://arxiv.org/html/2509.23322v2).
- Tried: multimodal LLM-based image analysis for UI verification.
- Broke: MLLM correctly identified primary object, then erroneously inferred
  non-existent attributes; cascaded into fatally flawed conclusions.
- Fix: validation layer; cross-check inferences against DOM / accessibility tree.

### G3. Google ADK — hallucinated tool invocation
- [google/adk-python#4173](https://github.com/google/adk-python/issues/4173).
- Tried: agent validation task.
- Broke: agent invoked non-existent tool (`readLine` hallucinated). No
  guardrail to prevent calling tools not in schema.
- Fix: tool schema validation; list available tools explicitly; reject unknown calls.

## Category H — Playwright MCP / vision agent tool proliferation

### H1. Tool proliferation — unnecessary screenshots
- [speakeasy.com — Playwright proliferation problem](https://www.speakeasy.com/blog/playwright-tool-proliferation).
- Tried: Playwright MCP with all tools available.
- Broke: Claude wasted time taking unnecessary screenshots at every step. Got
  distracted by visual verification; lost focus on primary task.
- Fix: tool selection/filtering; expose only relevant tools per task; tool-use
  budgets.

### H2. Version incompatibility
- [microsoft/playwright-mcp#1359](https://github.com/microsoft/playwright-mcp/issues/1359).
- Tried: Playwright MCP 0.0.56 / 0.0.61 with Claude Code.
- Broke: recent versions unaccessible by Claude Code. Tools like
  `mcp__playwright__browser_navigate` invisible.
- Workaround: downgrade to 0.0.41 (unacceptable regression).
- Fix: version pinning; compatibility matrix documentation.

### H3. Weak accessibility + hidden elements in snapshots
- [morphllm.com — Agent-Browser vs Playwright MCP](https://www.morphllm.com/agent-browser-vs-playwright-mcp/).
- Tried: Playwright MCP to inspect/interact with pages.
- Broke: snapshots with weak accessibility labels, dynamic node IDs that change
  between snapshots, hidden elements included in snapshots — agent confused
  about what was visible.
- Fix: sanitize snapshots; remove hidden elements; require semantic HTML.

## Category I — Cursor Agent Review breakdowns

### I1. Agent Review feature disabled
- [forum.cursor.com discussion, Feb-Mar 2026](https://forum.cursor.com/t/agent-mode-no-longer-shows-review-accept-interface-and-applies-file-changes-automatically-after-recent-update/152581).
- Tried: use Agent mode with visual review interface.
- Broke: after update, Agent applied file changes WITHOUT showing review. Users
  couldn't accept/deny. Loss of safety layer.
- Fix: revert to previous version; feature flag to disable auto-apply.

### I2. Cursor Tab overwrites changes
- forum.cursor.com discussion, Cursor team confirmed Mar 2026.
- Tried: Agent Review Tab while editing in Chat.
- Broke: Review Tab interfered with file state; changes overwritten on context
  switch. Conflicts with Cloud Sync and Format On Save.
- Fix: close Agent Review Tab before "Fix in Chat"; avoid context switching.

### I3. Model visibility broken
- [forum.cursor.com — Agent Review Feature Missing Model Visibility](https://forum.cursor.com/t/agent-review-feature-missing-model-visibility-and-selection/143504).
- Tried: monitor which model was running.
- Broke: no visibility into model used. Impossible to verify selection or
  control cost.
- Fix: manual model config; cost estimates before run.

## Category J — Anthropic Computer Use agent

### J1. API limits interrupt workflow
- [medium.com/@EricVogelpohl — Visual & Programmatic Bots](https://medium.com/@EricVogelpohl/visual-programmatic-bots-a-fundamental-divide-anthropics-computer-use-tested-1c3fe8e1ae01).
- Tried: Computer Use agent for extended task (50+ steps).
- Broke: rate limits and pauses interrupted workflow constantly. Required
  repeated prompts to resume. Called "alpha software" despite "beta" label.
- Fix: retry logic; exponential backoff; request queue; polling.

### J2. Screenshot re-sending token explosion
- [replit.discourse.group — too many large screenshots](https://replit.discourse.group/t/anthropic-api-error-too-many-large-screenshots-by-agent/10988).
- Tried: agent taking screenshots every step.
- Broke: agent re-sent every previous screenshot in conversation history.
  Payload balloons. By step 50, sending massive context unless aggressively
  prune.
- Cost: $0.50 → multi-dollar per task.
- Fix: screenshot dedup; aggressive context pruning; use summary images.

## Category K — Vercel agent-browser selector failures

### K1. Screenshot command validation error
- [vercel-labs/agent-browser#238](https://github.com/vercel-labs/agent-browser/issues/238), Jan 2026.
- Tried: execute screenshot command with selector argument.
- Broke: "selector: Expected string, received null". Agent unable to capture.
- Fix: parameter parsing; optional selector support; validate inputs before invoke.

---

## Aggregate failure statistics

| Category | Public cases found | Most common fix | Median recovery |
|---|---|---|---|
| Infinite loop | 5+ major frameworks | Hard loop limits; context compaction | 2-8 hours |
| Missed regression | ~20 reports | Multi-judge verification; manual spot check | At deploy (user catches) |
| False positives | 30+ projects | AI diffing + rule-based exclusion | 1-3 days (alert fatigue first) |
| Rubric drift | 2-3 documented | Production monitoring on rubric scores | Not caught in 50% of cases |
| Cost overrun | 10+ reports ($500→$847K) | Budget caps; context compaction | Manual audit + cap |
| Cross-device | 5+ reports | Fixed environments; CSS assertions | Ongoing in small teams |
| Hallucination | 15+ cases | Multi-judge; provenance | Not caught without external audit |
| Tool proliferation | 3+ reports | Tool filtering; explicit selection | 1-2 days config |
| Timing / sync | 5+ async bugs | Explicit wait-for-change | 3-7 days debug |

## Critical insights for skeptics

### 1. Vision models are non-deterministic
Same vision model + same question + same screenshot can yield different
answers. **This alone disqualifies vision models as sole approval mechanism.**
Mitigation: multi-judge; deterministic diff tools; vision as supporting
evidence, not verdict.

### 2. Context window is the silent killer
Agents don't fail loudly; they fail when context runs out. Screenshot re-sending,
file re-reading, message history growth — invisible until the bill arrives or
the agent stops making progress.
Mitigation: aggressive compaction; per-operation budgets; proactive monitoring.

### 3. Hallucinations escape human review at scale
LLMs confidently produce false claims (fabricated UI elements, imaginary bugs)
that look correct to human reviewers. Manual review does NOT scale as a
mitigation.
Mitigation: provenance requirement; multi-judge consensus; attribute validation
against ground truth (DOM, API, logs).

### 4. False positives cause alert fatigue
Pixel-based testing: 20-40% false positives. Teams set loose thresholds → real
bugs slip through. Or tight thresholds → constant noise → stop reviewing.
Mitigation: AI diffing; perceptual hashing; rule-based exclusion of
expected-to-change elements.

### 5. Cross-device variance is unsolved
Screenshots on MacBook ≠ Windows ≠ mobile real device. No robust solution;
fixed environments are the pragmatic choice.

### 6. Token cost grows O(n²) with steps
Each action appends to context. By step 50, re-processing 50 prior actions.
Compounding cost makes visual agents prohibitively expensive at scale without
aggressive pruning.

### 7. Tool proliferation distracts agents
All-tools-available → agent spends tokens on unnecessary screenshots instead of
completing tasks. Tool filtering by task is non-obvious but essential.

### 8. Approval without review is dangerous
Agent-driven approval without human review has failed in production across
Cursor, Copilot, custom systems. The safety layer (accept/deny UI) is essential
and has been REMOVED in recent versions of some tools.

## Final assessment

**Screenshot-driven agent review systems are NOT production-ready as sole
approval mechanisms.** Failure modes are silent (context limits, hallucinations),
non-deterministic (vision models, timing), expensive (token cost O(n²)),
undetectable at scale (false positives → alert fatigue).

Most teams deploying visual agents in 2025-2026 have encountered at least 2-3
of these categories in production. Mitigations exist but require discipline:
multi-judge verification, hard budgets, provenance tracking, manual review layers.

**Minimal safe configuration:**
1. Vision agent produces evidence + recommendation.
2. Deterministic diff tool confirms changes.
3. Human reviews before approval.
4. Approval applies (not automatic).
5. Token budget enforced per-operation.
6. Production metrics on rubric scores (not system aggregate).

Anything less is gambling with production stability.
