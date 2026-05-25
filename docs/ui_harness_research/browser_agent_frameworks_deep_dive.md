# Browser Agent Frameworks Deep Dive

## Executive Summary

Three production browser-agent frameworks analyzed at source code level:

- **Browser-Use**: 500 step max, screenshots every step, LLM self-decides done, NO re-verification
- **Stagehand**: 10 step max, screenshots after actions, LLM stops tools = done, NO re-verification  
- **Skyvern**: Configurable cap, mandatory visual re-verify before completion, YES fresh screenshot check

**Key Finding**: ONLY Skyvern implements mandatory re-verification against fresh page state before accepting task completion. Browser-Use and Stagehand rely on LLM self-assessment.

## 1. BROWSER-USE

Hard cap: max_steps = 500 (service.py:2485)
Loop: service.py:2580 (while n_steps <= max_steps)
Screenshots: Always, every step (service.py:1083-1088)
Verification: NO - agent self-decides via done action
Budget warning: At 75% (service.py:1540-1553)
Force-stop: Max failures=5 (views.py:62), then abort
Cost tracking: Optional calculate_cost flag, token_cost service (service.py:418-423)
Risk: Hallucination - agent claims done but page doesn't show it

## 2. STAGEHAND

Hard cap: maxSteps = 10 (AnthropicCUAClient.ts:124)
Loop: lines 148-173 (while !completed && step < maxSteps)
Screenshots: After actions only (line 657-672)
Verification: NO - completion when tool_use items empty (line 382-393)
Failure handling: Tools fail silently, no consecutive counter
Cost tracking: OnMetrics callback (observeHandler.ts:134-142)
Risk: Hallucination - model stops tools but goal not actually achieved

## 3. SKYVERN  

Hard cap: Configurable org/task/settings (agent.py:703-708)
Screenshots: Per-action + mandatory refresh (agent.py:2747)
Verification: YES - complete_verify() with fresh screenshot (agent.py:2729-2831)
- Re-scrapes page and takes new screenshot
- Loads verification prompt with updated HTML + criteria
- LLM decides: complete/terminate/continue against live state
- Gated in step loop (agent.py:2835-2877)
Cost tracking: Per-step tokens (agent.py:2095-2109), hard ceiling (line 170)
Lean compression: html_need_skyvern_attrs=False, compress URLs (2805-2812)

## Recommendation for POLARIS

For robust UI test harness: Adopt Skyvern model.
- Screenshot every step
- Before accepting done, re-scrape and take fresh screenshot
- Ask LLM: Given new screenshot and DOM, is goal achieved?
- Only accept if LLM confirms against live state

This prevents hallucination-driven false positives and provides audit trail.



---

## DETAILED FILE ANALYSIS

### Browser-Use

File: /browser_use/agent/service.py (4131 lines)

Main loop at line 2580:
- Checks: n_steps <= max_steps (default 500)
- Checks: consecutive_failures < max_failures (default 5)
- Each iteration: await _execute_step()
- Exit condition: is_done = True (model returned done action)

Screenshot capture at line 1083-1088:
  browser_state_summary = await self.browser_session.get_browser_state_summary(
      include_screenshot=True,
      include_recent_events=self.include_recent_events,
  )

Verification: NONE. Model decides done unilaterally.

Cost tracking at line 418-423:
  self.token_cost_service = TokenCost(include_cost=calculate_cost)
  self.token_cost_service.register_llm(llm)
  self.token_cost_service.register_llm(page_extraction_llm)
  self.token_cost_service.register_llm(judge_llm)

### Stagehand

File: /packages/core/lib/v3/agent/AnthropicCUAClient.ts (1058 lines)

Main loop at line 124-173:
  const maxSteps = options.maxSteps || 10;
  while (!completed && currentStep < maxSteps) {
      const result = await this.executeStep(inputItems, logger);
      completed = result.completed;  // toolUseItems.length === 0
      inputItems = result.nextInputItems;
      currentStep++;
  }

Completion determined at line 382-393:
  const completed = toolUseItems.length === 0;

Screenshots at line 657-672:
  const screenshot = await this.captureScreenshot();
  // Returned as tool result

No verification layer. Task complete when model stops emitting tools.

### Skyvern

File: /skyvern/forge/agent.py (6185 lines)

Re-verification at line 2729-2831:

async def complete_verify(self, page, scraped_page, task, step):
    # STEP 1: RE-SCRAPE PAGE
    scraped_page_refreshed = await scraped_page.refresh(
        draw_boxes=False, 
        scroll=True
    )
    
    # STEP 2: BUILD VERIFICATION PROMPT (includes fresh HTML)
    verification_prompt = load_prompt_with_elements(
        element_tree_builder=scraped_page_refreshed,
        complete_criterion=task.complete_criterion,
        terminate_criterion=task.terminate_criterion,
    )
    
    # STEP 3: CALL LLM WITH FRESH SCREENSHOT
    verification_result = await llm_api_handler(
        prompt=verification_prompt,
        screenshots=scraped_page_refreshed.screenshots,  # NEW
    )
    
    # STEP 4: DECIDE: complete/terminate/continue
    if verification_result.is_complete:
        return VerificationStatus.complete
    elif verification_result.is_terminate:
        return VerificationStatus.terminate
    else:
        return VerificationStatus.continue_step

Integration at line 2835-2877:
  This gates task completion.
  Returns None (continue) if not verified complete.

Token tracking at line 2095-2109:
  input_tokens = first_response.usage.input_tokens or 0
  llm_cost = (3.0 / 1000000) * input_tokens + (12.0 / 1000000) * output_tokens
  incremental_cost, incremental_input_tokens, incremental_output_tokens tracked

---

## Cross-Framework Analysis

Verification Approach:

1. Browser-Use
   - LLM self-decides done
   - No screenshot re-check
   - Risk: False positives (hallucination)

2. Stagehand
   - LLM stops emitting tools = done
   - Uses last screenshot (not refreshed)
   - Risk: Model stops too early

3. Skyvern
   - Re-scrapes page before verification
   - Fresh screenshot + updated DOM
   - LLM re-checks against live state
   - Safe: Multiple checkpoints

Iteration Cap:

1. Browser-Use: 500 steps
2. Stagehand: 10 steps
3. Skyvern: Configurable (org/task/settings)

Cost Management:

1. Browser-Use: Optional tracking, no hard limit
2. Stagehand: Callback-based, no limit
3. Skyvern: Per-step tracking, hard PROMPT_HARD_CEILING_TOKENS

---

## Recommendation

For POLARIS UI test harness:

Adopt Skyvern model because:
1. Mandatory re-verification prevents false positives
2. Fresh screenshot ensures current state validation
3. Natural-language criteria are flexible
4. Per-step token tracking prevents cost overruns
5. Proven at scale (production usage)

Key files to study:
- /skyvern/forge/agent.py:2729-2831 (complete_verify)
- /skyvern/forge/agent.py:2835-2877 (integration)
- /skyvern/forge/agent.py:703-708 (configurable caps)

---

Generated: 2026-05-25
Depth: Source code analysis
Evidence: File:line pairs from production repositories
