# Claude Code Deep Architecture: Lessons for POLARIS

## The Core Surprise: It's Simpler Than You Think

The entire Claude Code engine is one `while(true)` loop:

```
while (true) {
    response = await callAPI(messages)
    for each block in response:
        if tool_use: execute tool, append tool_result
        if text: display
    if stop_reason == "end_turn" and no tool_use: break
}
```

512,000 lines of code, and the actual agent logic is ~200 lines. Everything else is: safety (9,800 lines for BashTool alone), tool definitions, context management, permissions, session persistence, and UI.

**The LLM IS the router, planner, and decomposer.** There is no separate NLU, intent classifier, or planning module. The model decides which tools to use and in what order, guided by the system prompt and conversation history.

---

## Architectural Insights That Change How We Should Work

### 1. Query Engine: No Query Understanding Pipeline Exists

**What we assumed:** Claude Code has a sophisticated query understanding system that classifies intent, decomposes tasks, and routes to specialized handlers.

**What actually exists:** The system prompt is assembled from modular cached sections (static tool definitions + dynamic project context), sent to the API, and the model decides everything. The "intelligence" is in the prompt, not the code.

**Lesson for POLARIS:** Our `polaris_graph` architecture with 9 explicit graph nodes (plan, search, analyze, verify, deepen, evaluate, synthesize, etc.) is MORE structured than Claude Code. This is both our strength (reliability) and weakness (rigidity). Consider: should some nodes be more dynamic, letting the LLM decide whether to skip or reorder?

### 2. Tool System: 184 Tools, But Deferred Loading is the Key Innovation

**What matters:** Not the number of tools, but HOW they're loaded. Since v2.1.69, most tools are "deferred" — only loaded when the model searches for them via `ToolSearchTool`. This saves ~3K tokens per tool from the system prompt.

**Specific tool counts:**
- Core file tools: Read, Write, Edit, Glob, Grep (5 tools, always loaded)
- Bash/PowerShell: 32 files including security analysis
- Agent tools: 19 files for sub-agent spawning
- Task management: 18 files for TaskCreate/Get/List/Update/Stop/Output
- LSP integration: 6 files for go-to-definition, references
- MCP: 11 files for external server integration
- Planning: EnterPlanMode, ExitPlanMode, TodoWrite

**Lesson for POLARIS:** Our pipeline loads ALL capabilities upfront. We should consider deferred loading for optional features (deepener, smart art, MoST) — load them only when the query requires them. This reduces system prompt size and focuses the model.

### 3. Deep Research: No Special Pipeline — Just Sub-Agent Isolation

**What we assumed:** There's a "deep research mode" with multi-cycle search-analyze-synthesize.

**What actually exists:** The model spawns sub-agents with clean context windows. Each sub-agent does its research (Glob, Grep, Read, WebSearch) and returns a summary. The parent agent synthesizes across sub-agent results.

**The critical insight: CONTEXT ISOLATION, not pipeline stages.** Claude Code's research quality comes from each sub-agent having a FRESH context window, not from a predetermined search→analyze→synthesize pipeline.

**Lesson for POLARIS:** Our fixed graph (plan→search→analyze→verify→deepen→synthesize) forces a rigid order. Claude Code's approach is more flexible — the model can spawn N sub-agents in parallel for different aspects, each with clean context, and synthesize at the end. Consider: should our pipeline be graph-based (current) or sub-agent-based (Claude Code style)?

### 4. Context Management: Three-Layer Compaction + AutoDream

**Layer 1: MicroCompact** — no API call, local edits. Removes old tool outputs, truncates large results. Runs silently in background.

**Layer 2: AutoCompact** — API call to generate 20K-token summary when approaching limit. Reserves 13K-token buffer.

**Layer 3: SnipCompact** — collapses individual large tool results into references.

**AutoDream (Memory Consolidation):** Background sub-agent that consolidates memory files — merges related entries, resolves contradictions, prunes MEMORY.md to <200 lines. Parallels biological sleep/dreaming.

**Full transcript always on disk.** Compaction only affects what's sent to the API.

**Lesson for POLARIS:** Our context management is crude — we rely on LangGraph's state management and manual session logging. We should implement:
1. Progressive result truncation (MicroCompact equivalent)
2. Automatic memory consolidation (AutoDream equivalent)
3. Disk-backed full transcript (crash recovery)

### 5. Task Decomposition: TodoWrite Doubles Completion Rate

Anthropic's own data: **task decomposition via TodoWrite doubles the completion rate.** The model breaks a complex request into numbered steps, works through them one by one, and validates before marking complete.

**The "Ralph Loop":** Pick task → Implement → Validate → Commit if passing → Reset context → Repeat.

**Lesson for POLARIS:** We use TaskCreate/TaskUpdate already, but inconsistently. The data says this doubles completion rate. We should make it mandatory for any multi-step task, not optional.

### 6. Tool Composition: Mission-Specific Patterns

| Mission Type | Tool Chain | Key Insight |
|-------------|-----------|-------------|
| **Code edit** | Glob→Read→Edit→Bash(test) | Always verify after edit |
| **Bug investigation** | Grep→Read→AgentTool[explore]→Bash(reproduce)→Edit→Bash(verify) | Use sub-agent for wider search |
| **Research** | AgentTool[explore]→Grep→Read→WebSearch→WebFetch→synthesize | Sub-agent isolation for research |
| **Refactoring** | Glob→Grep→LSP(references)→Edit(each)→Bash(full test) | LSP for completeness |
| **Test writing** | Read(impl)→AgentTool[explore](patterns)→Write(test)→Bash(run)→iterate | Study existing patterns first |
| **Multi-file** | TodoWrite(plan)→[Read→Edit]×N→Bash(lint+test) | Plan ALL changes before starting |

**Lesson for POLARIS:** Our pipeline is monolithic — the same 9-node graph for every query. Claude Code adapts its tool composition based on the task. We should consider task-type detection to optimize the pipeline path.

### 7. Security: 98% of the Code

The ratio of "agent loop" to "safety" code is ~200:9800 lines. BashTool alone has:
- `bashSecurity.ts` — command analysis
- `bashPermissions.ts` — per-command permission checks
- `destructiveCommandWarning.ts` — dangerous pattern detection
- `commandSemantics.ts` — safe vs restricted classification
- OS-level sandboxing (bubblewrap on Linux, seatbelt on macOS)

**Lesson for POLARIS:** Our pipeline has minimal safety checks — we trust the LLM to follow instructions. Claude Code trusts nothing. Every tool call goes through multi-layer permission checking.

### 8. Verification: The Model Verifies, Not the Harness

**No verification module exists in the harness.** The system prompt instructs the model to:
1. Run lint after code changes
2. Run tests after implementation
3. Validate before marking TodoWrite items complete
4. Never declare "done" at 90% — actual verification required

**Lesson for POLARIS:** Our verification is built INTO the graph (verify node with NLI + LLM). Claude Code's approach trusts the model to self-verify, guided by prompts. The hybrid approach (structural graph + prompted self-verification) is likely optimal.

### 9. Session Management: Full Transcript on Disk

Every message, tool use, and tool result stored as JSONL at `~/.claude/projects/<path>/*.jsonl`. Sessions can be:
- **Resumed** after crash
- **Forked** for experiments
- **Exported** for sharing
- **Renamed** for organization

**Lesson for POLARIS:** Our checkpoint system (SQLite) + session log (markdown) is similar but less structured. The JSONL-per-message approach enables fine-grained recovery.

### 10. The 44 Feature Flags

Claude Code has 44 unreleased features behind flags:
- **KAIROS:** Always-on autonomous daemon mode
- **ULTRAPLAN:** Remote planning with Opus 4.6, up to 30 min thinking
- **AutoDream:** Background memory consolidation
- **BUDDY:** Tamagotchi engagement system (18 species, rarity tiers)
- **Agent Teams:** Peer-to-peer multi-agent coordination
- **Auto mode:** Classifier-based safety for unattended operation

**Lesson for POLARIS:** Feature flags for experimental capabilities is a good pattern. We use env vars (PG_MOST_ENABLED, PG_EVIDENCE_DEEPENER, etc.) which is similar but less structured.

---

## What This Means for POLARIS Research Pipeline

### Where POLARIS Is Already Better
1. **Structured evidence pipeline** — our graph enforces quality gates (verify, evaluate) that Claude Code lacks
2. **Multi-source search** — S2, Serper, Exa, OpenAlex, Jina, Crawl4AI vs Claude Code's single WebSearch
3. **Citation management** — our citation mapper, B1 hallucination check, bibliography generation
4. **Domain configuration** — our YAML-based domain lists vs Claude Code's hardcoded patterns
5. **Evidence deepening** — citation chasing, mechanism search, PDF extraction

### Where Claude Code Is Better
1. **Context hygiene** — three-layer compaction vs our reliance on LangGraph state
2. **Sub-agent isolation** — clean context windows for research vs our monolithic graph
3. **Tool deferred loading** — reduces prompt bloat vs our all-upfront approach
4. **Self-verification prompting** — the model verifies, not just structural checks
5. **Crash recovery** — full JSONL transcript vs our partial checkpointing

### Concrete Changes to Adopt

**Immediate (Week 1):**
1. Add "VERIFY BEFORE CLAIMING DONE" to section writer prompt
2. Make TodoWrite/TaskCreate mandatory for multi-step work
3. Add PostToolUse compile hook

**Short-term (Month 1):**
4. Implement progressive result truncation (MicroCompact equivalent)
5. Add sub-agent research mode for evidence gathering (instead of fixed search→analyze pipeline)
6. Implement deferred feature loading (don't load deepener/smart_art unless query warrants it)

**Medium-term (Quarter 1):**
7. AutoDream-style memory consolidation for MEMORY.md
8. Task-type detection to optimize pipeline path
9. Agent Teams for parallel section writing
10. Full JSONL transcript for crash recovery

---

*Research date: 2026-03-31*
*Sources: Official Anthropic docs, public technical analyses of Claude Code architecture (VentureBeat, DEV Community, Victor Antos, Sathwick.xyz, Pierce Freeman, Vrungta, PromptLayer, ZenML), Claw Code repository reference data*
