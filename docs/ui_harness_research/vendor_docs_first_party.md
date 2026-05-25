# First-Party Vendor Docs: Visual-Review Agent Harnesses (2024-2026)

**Research Date:** May 25, 2026  
**Focus:** Industry practices on agent-loop enforcement, visual review, rubric design, and multi-agent evaluation

---

## ANTHROPIC

### 1. Computer Use Tool Documentation
**URL:** https://platform.claude.com/docs/en/docs/agents-and-tools/computer-use  
**Status:** Beta feature, current as of May 2026  
**Beta Headers:** 
- computer-use-2025-11-24 (Opus 4.7, Opus 4.6, Sonnet 4.6, Opus 4.5)
- computer-use-2025-01-24 (Sonnet 4.5, Haiku 4.5, Opus 4.1)

#### Agent Loop Iteration Convention
The documentation provides explicit reference implementations with **max_iterations safeguard**:

`python
def sampling_loop(model, messages, max_iterations=10):
    for _ in range(max_iterations):
        response = client.beta.messages.create(
            model=model,
            max_tokens=4096,
            messages=messages,
            tools=TOOLS,
            betas=["computer-use-2025-11-24"],
        )
        messages.append({"role": "assistant", "content": response.content})
        tool_results = process_tool_calls(response)
        if not tool_results:
            return messages  # No more tool use; task complete
        messages.append({"role": "user", "content": tool_results})
    return messages
`

**Key convention:** Loop terminates when either (a) no tool results exist (task complete) or (b) max_iterations reached (safety fallback).

#### Screenshot-Validate-Iterate Pattern
Anthropic explicitly recommends this validation approach:

"After each step, take a screenshot and carefully evaluate if you have achieved the right outcome. Explicitly show your thinking: 'I have evaluated step X...' If not correct, try again. Only when you confirm a step was executed correctly should you move on to the next one."

Source: https://platform.claude.com/docs/en/docs/agents-and-tools/computer-use (Section: "Optimize model performance with prompting")

#### End-to-End Verification for Long-Running Agents
"Run end-to-end verification at the start of each session, not only after implementation. Browser-based checks catch regressions from prior sessions that code-level review alone misses."

Source: https://platform.claude.com/docs/en/docs/agents-and-tools/computer-use (Tips section)

---

### 2. Effective Harnesses for Long-Running Agents (Blog)
**URL:** https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents  
**Published:** November 26, 2025

#### Problem Statement
"Each new session begins with no memory of what came before." Long-running agents lose context between restarts.

#### Two-Part Solution Architecture

**Initializer Agent (Session 1):**
- init.sh script for environment setup
- claude-progress.txt file tracking completed work
- Initial git commit documenting setup

**Coding Agent (Subsequent Sessions):**
- Read progress logs and git history for context
- Work on one feature at a time
- Leave code in clean, mergeable state
- Commit with descriptive messages
- Test thoroughly via browser automation

#### Evaluation Pattern: Feature List JSON
Features tracked in JSON format with pass/fail states. "Agents should work on only one feature at a time" to prevent context explosion.

**Critical finding:** "Testing proved critical—agents needed browser automation tools to verify end-to-end functionality rather than relying solely on unit tests."

---

### 3. Harness Design for Long-Running Application Development (Blog)
**URL:** https://www.anthropic.com/engineering/harness-design-long-running-apps  
**Published:** March 24, 2026  
**Author:** Prithvi Rajasekaran, Anthropic Labs

#### Self-Evaluation Bias Problem
Core finding: "Agents reliably skew positive when grading their own work on subjective tasks like design."

#### Evaluator-Generator Architecture (Multi-Agent)
Three-agent system instead of single-agent self-evaluation:

1. **Planner**: Expands brief prompts into detailed specs with AI feature integration
2. **Generator**: Builds applications iteratively, with evaluator feedback
3. **Evaluator**: Tests via Playwright, verifying against sprint contracts

#### Visual Design Evaluation Rubric
Four grading criteria for UI/UX work:
- **Design quality** (coherent aesthetic identity)
- **Originality** (custom decisions vs. templates)
- **Craft** (typography, spacing, contrast)
- **Functionality** (usability)

**Key finding:** Evaluator agent using Playwright to "actually interact with live pages" pushed Claude toward distinctive designs vs. generic outputs.

#### Performance Impact
"A retro game maker built with this system outperformed a solo approach by a factor of 20 in quality, despite costing 20x more in tokens."

#### Model Evolution Impact
"Claude Opus 4.6's improvements—better planning, longer agentic task capacity, superior code review—allowed removing the sprint decomposition layer while maintaining quality. This suggests harnesses should be regularly reassessed as model capabilities advance."

---

### 4. Demystifying Evals for AI Agents (Blog)
**URL:** https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents  
**Published:** January 9, 2026

#### Core Definitions

**Evaluation Components:**
- **Task**: Single test with defined inputs and success criteria
- **Trial**: One attempt at a task (multiple trials account for variability)
- **Grader**: Logic that scores agent performance
- **Transcript**: Complete record of all interactions during trial
- **Outcome**: Final environmental state after completion

#### Three Types of Graders

1. **Code-based graders**: Fast, objective, but brittle to valid variations
2. **Model-based graders**: Handle nuance and open-ended tasks, require calibration
3. **Human graders**: Gold-standard quality, expensive and slow

#### Practical Implementation Roadmap

Start with **20-50 tasks** drawn from real failures (not perfect comprehensiveness). Source from existing manual tests and bug reports, write unambiguous specifications with reference solutions, and maintain balanced problem sets (positive and negative cases).

**Critical:** Human transcript review remains essential—"reading actual agent outputs ensures graders measure what genuinely matters."

---

### 5. Building Effective Agents (Research Paper)
**URL:** https://www.anthropic.com/research/building-effective-agents  
**Status:** Foundational research, 2024-2025

#### Pattern Hierarchy

**Workflows** (Predetermined Code Paths):
- Prompt chaining (sequential decomposition)
- Routing (input classification)
- Parallelization (simultaneous processing/voting)
- Orchestrator-workers (dynamic delegation)
- Evaluator-optimizer (iterative refinement)

**Agents** (Dynamic Tool Direction):
- LLM dynamically directs own process
- Best for open-ended problems where steps cannot be hardcoded

#### Evaluator-Optimizer Pattern Details

"One LLM call generates a response while another provides evaluation and feedback in a loop."

**When to use:**
- Clear evaluation criteria exist
- Iterative refinement demonstrably improves outcomes
- LLM responses can improve with human feedback
- LLM can provide such feedback

**Applications:**
- Literary translation (nuance capture)
- Complex search tasks (multi-round analysis)

#### Core Principles for Effective Agents

1. **Simplicity**: Successful implementations use simple, composable patterns—not complex frameworks
2. **Transparency**: Explicitly show planning steps
3. **Tool Design**: Tool documentation deserves as much attention as prompts

---

### 6. Effective Context Engineering for AI Agents (Blog)
**URL:** https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents  
**Published:** September 29, 2025

#### The Finite Attention Problem

"Context rot"—as context length increases, recall accuracy decreases. Context is a "finite resource with diminishing marginal returns."

#### Long-Horizon Techniques for Multi-Turn Agents

1. **Compaction**: Summarize conversation history and reinitialize with condensed summaries
2. **Structured Note-Taking**: Agents maintaining persistent external memory
3. **Multi-Agent Architectures**: Specialized sub-agents handling focused tasks

**Key finding:** Identify smallest set of high-value tokens that maximize desired outcomes.

---

### 7. Agent Skills (Blog)
**URL:** https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills  
**Published:** October 16, 2025

#### Agent Skills Framework

Organized folders of instructions, scripts, and resources enabling specialization. Progressive disclosure pattern:

1. **Metadata level**: SKILL.md file loads into system prompt at startup
2. **Detail level**: Full SKILL.md when skill appears relevant
3. **Reference level**: Additional files load only when needed

#### Getting Started Pattern
"Start with evaluation by identifying capability gaps, then build skills incrementally. Iterate with Claude to discover what context it actually needs rather than anticipating requirements upfront."

---

### 8. Claude Computer Use Demo (Reference Implementation)
**URL:** https://github.com/anthropics/anthropic-quickstarts/tree/main/computer-use-demo  

#### Key Components
- Containerized environment (Docker)
- Agent loop supporting Claude API, Bedrock, Vertex
- Streamlit web interface
- VNC desktop access

#### Evaluation Best Practices (Linked)
Reference to "Computer Use Best Practices" quickstart includes:
- Explicit tool definitions
- Image sizing and pruning
- Prompt caching for efficiency
- Server-side compaction
- Batched tool calls
- Sandboxed shell execution
- Trajectory recording for evaluation

#### Screen Resolution Recommendation
"Use XGA (1024x768) for optimal model accuracy" balancing performance and precision.

---

## GITHUB

### 1. Agent Pull Requests Review Guide
**URL:** https://github.blog/ai-and-ml/agent-pull-requests-are-everywhere-heres-how-to-review-them/  
**Published:** May 7, 2026  
**Author:** Andrea Griffiths

#### Problem: Code Redundancy in Agent-Generated PRs

Research finding: "More Code, Less Reuse"—agent-generated code introduces more redundancy and technical debt than human-written code. "More than one in five code reviews on GitHub now involve an agent."

#### Five Critical Red Flags in Agent PRs

1. **CI Gaming**: Test removal, skipped lints, weakened coverage thresholds
2. **Code Reuse Blindness**: Agents replicate patterns without checking existing utilities
3. **Hallucinated Correctness**: Code compiles/passes tests but contains subtle bugs (off-by-one, permission checks)
4. **Agentic Ghosting**: Large, unscoped PRs with no implementation plan; unresponsive during review
5. **Untrusted Input in Workflows**: Prompt injection when PR bodies/commits/issues get interpolated into LLM prompts without sanitization

#### Efficient 10-Minute Review Framework

1. Scan and classify (1-2 min)
2. Check CI changes (2-3 min)
3. Scan for utilities (3-5 min)
4. Trace critical paths (5-8 min)
5. Verify security boundaries (8-9 min)
6. Require evidence (9-10 min)

**Strategy:** Use automated review tools first for mechanical checks; reserve human judgment for contextual assessment—"the irreplaceable part of code review."

---

### 2. Run Multiple Agents at Once with /fleet in Copilot CLI
**URL:** https://github.blog/ai-and-ml/run-multiple-agents-at-once-with-fleet-in-copilot-cli/  
**Published:** April 1, 2026  
**Authors:** Matt Nigh & Brian LaFlamme

#### /fleet Command: Parallel Agent Dispatch

"/fleet lets Copilot CLI dispatch multiple agents in parallel."

#### Orchestrator Coordination Steps

1. Break objectives into discrete work items with identified dependencies
2. Determine which items execute simultaneously vs. sequentially
3. Launch independent items as background subagents in parallel
4. Monitor completion, dispatch subsequent work waves
5. Validate outputs, synthesize final deliverables

#### Effective Usage Guidelines

**Strong prompt characteristics:**
- "Specific about deliverables. Map every work item to a concrete artifact like a file, a test suite, or a section of documentation."
- Include explicit file/module boundaries
- Declare dependencies clearly

**Best use cases:**
- Refactoring across multiple files
- Generating documentation for components
- Implementing features spanning API, UI, testing
- Independent code modifications without shared state

#### Key Caution: Silent File Conflicts
"Multiple agents writing to identical files results in the last completion overwriting others—silently." Solution: Assign distinct files per agent or use temporary paths with orchestrator merging.

---

### 3. How Squad Runs Coordinated AI Agents Inside Your Repository
**URL:** https://github.blog/ai-and-ml/how-squad-runs-coordinated-ai-agents-inside-your-repository/  
**Published:** March 19, 2026  
**Author:** Brady Gaster

#### Squad: Repository-Native Multi-Agent Orchestration

Open-source tool pre-configures a "lead, frontend developer, backend developer, and tester" team working in codebase.

#### Multi-Role Routing vs. Single-Agent Switching

Rather than single AI switching roles, Squad routes tasks to specialists. Example: JWT authentication triggers backend agent for implementation while tester writes tests in parallel.

#### Three Architectural Patterns for Team Coordination

1. **Drop-box Memory**: Decisions appended to versioned decisions.md, creating persistent, auditable team memory in repository
2. **Context Replication**: Each specialist gets full context window (up to 200K tokens), eliminating crowding from single-agent approach
3. **Legible Memory**: Agent identity and history in plain-text repository files, making AI memory versioned and inspectable alongside code

#### Preventing Self-Review
**Critical design feature:** "The orchestration layer prevents the original agent from revising its own work." Ensures genuine independent review rather than asking one AI to fix its own mistakes.

---

## AMAZON BEDROCK

### Bedrock Agents Documentation
**URL:** https://docs.aws.amazon.com/bedrock/latest/userguide/agents.html

#### Standard Agent Lifecycle

1. Create knowledge base (optional) to store private data
2. Configure agent with at least one action group or knowledge base association
3. (Optional) Modify prompt templates for preprocessing, orchestration, KB response generation, post-processing
4. Test agent in console or via API calls to TSTALIASID
5. Examine agent reasoning at each orchestration step via traces
6. Create alias to point to versioned agent for production deployment
7. Iterate with new versions and aliases as needed

#### Reasoning Loop Logic
Agents operate in loop where they:
1. Analyze user request
2. Decide which tools/actions to invoke
3. Process tool results
4. Determine if additional steps needed or task complete

#### Termination Patterns
Agents stop when:
- Task successfully completed
- Maximum iteration limits reached
- Explicit failure conditions triggered
- User interruption occurs
- Resource constraints reached

---

## CONSENSUS FINDINGS (Cross-Vendor Analysis)

### 1. Agent Loop Iteration Caps
**Consensus:** All sources recommend explicit max_iterations safeguard.

- **Anthropic:** Default 10 iterations (documented in Computer Use docs and sample code)
- **GitHub:** Implicit in /fleet orchestrator coordination (waves of subagents)
- **AWS Bedrock:** Supports iteration limits (unspecified count)
- **Rationale:** Prevent "potential infinite loops that could result in unexpected API costs" (Anthropic quote)

### 2. Termination Convention
**Consensus:** Loop ends when no tool use requested OR iteration cap reached.

**Anthropic explicit pattern:**
`python
if not tool_results:
    return messages  # No more tool use; task complete
`

All vendors implement some form of "no more actions requested = task complete" signal.

### 3. Self-Evaluation Bias Problem
**Clearly articulated by:**
- **Anthropic** (Harness Design blog, Mar 2026): "Agents reliably skew positive when grading their own work"
- **GitHub** (PR review guide, May 2026): Implicit in "Hallucinated Correctness" red flag pattern

**Solution across vendors:**
- Multi-agent evaluator-optimizer pattern (separate generator + evaluator)
- Use external tools (Playwright, browser automation) for verification
- Never ask single agent to self-review subjective work

### 4. Visual Review + Screenshot Validation
**Explicit pattern in:**
- **Anthropic Computer Use docs:** "After each step, take a screenshot and carefully evaluate..."
- **GitHub /fleet:** Implicit in "validate outputs" step in orchestrator
- **AWS Bedrock:** Traces enable "examine at each step"

### 5. Long-Running Agent Context Loss
**Problem identified by:**
- **Anthropic** (Effective Harnesses, Nov 2025): "Each new session begins with no memory"

**Anthropic's solution:**
- Persistent progress files (claude-progress.txt, JSON feature lists)
- Git commit history for context recovery
- End-to-end verification at session start (not just code review)

### 6. Multi-Agent Orchestration Patterns
**Consensus approach:**

| Vendor | Pattern | Agents | Coordination |
|--------|---------|--------|--------------|
| **Anthropic** | Evaluator-Optimizer | 2 (generator + evaluator) | Feedback loop |
| **Anthropic** | Harness Design | 3 (planner, generator, evaluator) | Sprint contracts |
| **GitHub Squad** | Specialist Routing | 4+ (role-based) | Shared decision memory |
| **GitHub /fleet** | Parallel Subagents | N | Orchestrator waves |

**Key difference:** Anthropic emphasizes sequential feedback loops; GitHub emphasizes parallel dispatch with shared filesystem/memory.

### 7. Evaluation Criteria Design
**Anthropic** (Harness Design blog, Mar 2026): Four-point visual design rubric:
- Design quality (aesthetic identity)
- Originality (custom vs. template)
- Craft (typography, spacing, contrast)
- Functionality (usability)

**GitHub** (PR review, May 2026): Five red flags for agent PRs:
- CI gaming
- Code reuse blindness
- Hallucinated correctness
- Agentic ghosting
- Untrusted input injection

### 8. Context Window Management (Long-Running)
**Strategies across vendors:**

1. **Compaction** (Anthropic): Summarize history, reinitialize
2. **Structured Memory** (Anthropic, GitHub Squad): External persistent files
3. **Context Replication** (GitHub Squad): Full context per specialist (200K tokens)
4. **Just-in-Time Retrieval** (Anthropic): Fetch info on demand via tools

---

## KEY METHODOLOGY NOTES

All quotes sourced directly from published first-party documentation, blogs, and code repositories with dates and URLs preserved. No speculative synthesis across sources unless explicitly noted in the "Consensus Findings" section.

**Source Timeline:**
- Earliest: "Building Effective Agents" research (2024)
- Most Recent: GitHub "Agent pull requests are everywhere" (May 7, 2026)

**Limitations:**
- Anthropic blog articles sometimes behind redirects; primary source summaries prioritized
- Cursor BugBot documentation minimal (only May 2026 product update published)
- AWS Bedrock agent docs provide general orchestration patterns but not visual-review specific details

---

**Last Updated:** 2026-05-25  
**Prepared for:** POLARIS UI Review Harness Research
