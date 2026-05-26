# Microsoft Playwright MCP: Source Code Deep Dive

**Commit SHA examined**: ae27b8638aaf3a6be17d378964ae683864d20440  
**Date**: 2026-05-25  
**Repository**: https://github.com/microsoft/playwright-mcp  
**Actual source**: https://github.com/microsoft/playwright/tree/main/packages/playwright-core/src/tools

---

## Overview

The Playwright MCP (Model Context Protocol) implementation is **split across two repositories**:
- **@playwright/mcp** (npm package) at https://github.com/microsoft/playwright-mcp - provides CLI and packaging
- **Actual implementation** in playwright/packages/playwright-core/src/tools - the real backend code

The CLI in @playwright/mcp (`cli.js`, `index.js`) delegates to playwright-core''s MCP implementation:
```javascript
// cli.js line 20-21
const { tools, libCli } = require(''playwright-core/lib/coreBundle'');
tools.decorateMCPCommand(p, packageJSON.version);
```

---

## Question 1: Agent Loop - Stateful or Stateless Per Request?

### Architecture: **Stateful per session, stateless per tool call**

**File**: `/packages/playwright-core/src/tools/backend/browserBackend.ts`

The `BrowserBackend` class implements the actual agent loop and is **stateful**:

```typescript
export class BrowserBackend {
  private _context: Context;
  private _sessionLog: SessionLog | undefined;
  
  async callTool(rawArguments: string, response: Response, signal?: AbortSignal) {
    // Lines: tool.schema.inputSchema.parse(rawArguments)
    // Lines: tool.handle(context, parsedArguments, response, signal)
    // Lines: response.serialize()
  }
}
```

**Key points**:

1. **Persistent State Per Session**: Each browser context maintains:
   - `_context: Context` - holds tabs, video recordings, route rules, pending errors
   - `_sessionLog: SessionLog` - optional recording of all tool invocations and results
   - Lifecycle: Context persists across multiple tool calls until browser closes

2. **Tool Call is Stateless**: Each `callTool()` invocation is self-contained:
   - Input parsing (Zod schema validation)
   - Tool lookup from internal tools array
   - Single async execution
   - Error capture and response serialization
   - No polling or looping within a single tool call

3. **Disconnection Tracking**: The backend sets `isClose: true` in response if browser closes mid-call
   ```
   Browser disconnection is monitored and flagged in response serialization
   ```

**File**: `/packages/playwright-core/src/tools/backend/context.ts`

The `Context` class maintains session-level state:
```typescript
export class Context {
  private _tabs: Tab[] = [];
  private _currentTab: Tab | undefined;
  private _video: { ... };
  private _routes: Map<...>;
  private _pendingUnhandledRejections: Promise<Error>[];
  private _runningToolName: string | undefined;
}
```

---

## Question 2: Screenshot Decision Logic - When Is a Screenshot Triggered?

### Answer: **Purely Advisory - No Built-in "Decide When" Logic**

**Playwright MCP has NO autonomous screenshot decision logic.** It provides tools, not a loop that decides when to use them.

**File**: `/packages/playwright-core/src/tools/backend/screenshot.ts`

The screenshot tool is **passive** - it only executes when called:
```typescript
const screenshot = defineTool({
  capability: ''core'',
  schema: {
    name: ''browser_take_screenshot'',
    title: ''Take a screenshot of the current page'',
    description: ''Take a screenshot of the page...'',
    inputSchema: z.object({
      format: z.enum([''png'', ''jpeg'']).default(''png''),
      target: targetSchema.optional(),
      filename: z.string().optional(),
      fullPage: z.boolean().optional(),
    }),
    type: ''action'',
  },
  handle: async (context, params, response) => {
    // Only runs if this tool is explicitly called by the agent
    // No internal trigger or schedule
  }
});
```

Key constraint visible in schema description:
```
"You can''t perform actions based on the screenshot."
```

**Alternative tool - `browser_snapshot`** (File: `/packages/playwright-core/src/tools/backend/snapshot.ts`):

The MCP server actually **prefers snapshots over screenshots** for accessibility data:
```typescript
const snapshot = defineTool({
  capability: ''core'',
  schema: {
    name: ''browser_snapshot'',
    title: ''Capture accessibility snapshot of the current page'',
    description: ''Capture accessibility snapshot of the current page, this is better than screenshot.'',
    // ... parameters for depth, target, boxes
  },
});
```

**Decision Logic Location**: The calling LLM (Claude/Claude Code) decides when to use `browser_take_screenshot` or `browser_snapshot`. Playwright MCP provides **no built-in heuristics** for this decision.

From README (File: `/microsoft/playwright-mcp/README.md`):
```
"Playwright MCP uses structured accessibility data rather than screenshots"
"LLMs understand page structure without pixel analysis"
```

---

## Question 3: Force Screenshot Before Success - Built-in Mechanism?

### Answer: **No - No Validation Rubric or Forced Screenshots**

**Playwright MCP provides NO built-in mechanism** that forces agents to take a screenshot or validate success before claiming completion.

**File**: `/packages/playwright-core/src/tools/backend/verify.ts`

The project includes optional **verification tools**, but they are **advisory only**:
```typescript
const verifyElement = defineTool({
  capability: ''core'',
  schema: {
    name: ''browser_verify_element'',
    title: ''Verify element is present and visible'',
    description: ''Verify an element with a specific role and name is visible...'',
  },
  handle: async (context, params, response) => {
    // Returns error via response.addError() if element not found
    // But execution doesn''t halt; agent can ignore the error
  }
});
```

**Key Finding**: The `Response` class marks failures but doesn''t prevent further execution:

**File**: `/packages/playwright-core/src/tools/backend/response.ts`
```typescript
addError(message: string) {
  this._errors.push(message);
}

serialize(): CallToolResult {
  // ... accumulates errors, but isError flag is purely informational
  return {
    content: [...],
    isError: this._errors.length > 0,
  };
}
```

**No Rubric or Checklist**: The MCP server does **not** define or enforce:
- Success criteria
- Required verification steps
- Mandatory snapshot/screenshot requirements
- Agent completion checklist

These are entirely the responsibility of the calling LLM agent.

---

## Question 4: Tool Granularity - Architecture

### Answer: **Fine-Grained Tools, Not Monolithic**

**Playwright MCP uses 24+ small, focused tools**, NOT a single `screenshot_and_analyze` mega-tool.

**File**: `/packages/playwright-core/src/tools/backend/tools.ts`

Tool list aggregates from modules:
```typescript
const browserTools = [
  ...common,        // 3 tools: browser_close, browser_type, browser_tabs
  ...config,        // 2 tools: browser_save_session, browser_restore_session
  ...console,       // 1 tool: browser_console_messages
  ...cookies,       // 4 tools: get/set/clear/delete cookies
  ...devtools,      // 2 tools: devtools_*.* (if enabled)
  ...dialogs,       // 1 tool: browser_handle_dialog
  ...evaluate,      // 2 tools: browser_evaluate, browser_run_code_unsafe
  ...files,         // 2 tools: browser_file_upload, browser_download
  ...form,          // 1 tool: browser_fill_form
  ...keyboard,      // 4 tools: browser_press_key, etc.
  ...mouse,         // 5 tools: browser_click, browser_hover, browser_drag, etc.
  ...navigate,      // 3 tools: browser_navigate, browser_navigate_back, etc.
  ...network,       // 5 tools: intercept, block, clear, etc.
  ...pdf,           // 1 tool: browser_pdf_save
  ...route,         // 2 tools: browser_route_*
  ...runCode,       // 1 tool: browser_run_code
  ...screenshot,    // 1 tool: browser_take_screenshot
  ...snapshot,      // 1 tool: browser_snapshot
  ...storage,       // 6 tools: browser_*_storage
  ...tabs,          // 3 tools: browser_new_tab, browser_close_tab, etc.
  ...tracing,       // 2 tools: browser_start_tracing, browser_stop_tracing
  ...verify,        // 4 tools: browser_verify_element, etc.
  ...video,         // 1 tool: browser_start_video
  ...wait,          // 1 tool: browser_wait_for
  ...webstorage,    // 2 tools: getStorageItem, setStorageItem
];
```

**Filtering Function** (File: `/packages/playwright-core/src/tools/backend/tools.ts`):
```typescript
export function filteredTools(config: BrowserModelConfig): Tool[] {
  return browserTools.filter(tool => {
    const capability = tool.capability;
    // 1. Keep ''core'' capability tools always
    if (capability === ''core'') return true;
    // 2. Keep tools explicitly in config.capabilities
    if (config.capabilities?.includes(capability)) return true;
    // 3. Exclude skillOnly tools in MCP mode
    if (tool.skillOnly) return false;
    return true;
  }).map(tool => {
    // Remove selector-related schemas for non-core tools
    if (tool.capability !== ''core'') {
      tool.schema.inputSchema = removeSelectorsFromSchema(tool.schema.inputSchema);
    }
    return tool;
  });
}
```

---

## Question 5: Error Handling - Page Load, Screenshot Failure, Element Not Found

### Answer: **Tool-Specific Error Paths, No Centralized Exception Pattern**

**Playwright MCP follows a distributed error pattern**: each tool handles its own failures.

#### Error Path: Centralized Error Collection

**File**: `/packages/playwright-core/src/tools/backend/browserBackend.ts`

```typescript
async callTool(rawArguments: string, response: Response, signal?: AbortSignal) {
  try {
    // 1. Parse input
    const parsed = tool.schema.inputSchema.parse(JSON.parse(rawArguments));
    
    // 2. Execute tool
    await tool.handle(context, parsed, response, signal);
    
    // 3. Drain pending rejections (JavaScript errors in page)
    while (this._context._pendingUnhandledRejections.length) {
      const err = await this._context._pendingUnhandledRejections.shift();
      response.addError(`Unhandled rejection: {err.message}`);
    }
  } catch (error) {
    response.addError(error.message);
  }
  
  // 4. Check if browser is still connected
  if (browser.isConnected() === false) {
    response.setClose();
  }
  
  return response.serialize();
}
```

**Error Contract**:
- Tool throws → caught in BrowserBackend → `response.addError(message)`
- Tool calls `response.addError()` → included in response
- Response marked with `isError: true` if any errors present
- Client receives full serialized result with error sections

---

## Question 6: Rubric or Checklist - Agent Success Validation

### Answer: **No Built-in Rubric - Entirely LLM-Driven**

**Playwright MCP provides ZERO automatic success validation.**

The tool suite is **purely a capability library**, not an agentic framework with:
- Success criteria definition
- Mandatory verification steps
- Progress tracking
- Agent completion checklist
- Built-in retry loops

**What the MCP Server Provides**:
1. A list of tools via `listTools()`
2. Ability to call each tool and get structured results
3. Optional `browser_verify_*` tools (4 verification tools)
4. Optional `browser_snapshot` for state inspection

**What the Server Does NOT Provide**:
- Any prompt or guidance for when to stop
- Any mechanism checking "did you complete the task?"
- Any enforcement that certain tools must be called
- Any feedback loop saying "success" vs "incomplete"

---

## Critical Architectural Decisions

1. **No Autonomous Agent Loop in Playwright MCP**
   - The server is a tool provider, not a decision-maker
   - LLMs must implement their own "when to stop" logic
   - Stateful per session, stateless per tool call

2. **Snapshots Over Screenshots**
   - `browser_snapshot` is documented as "better than screenshot"
   - Structured accessibility data, not pixel-based
   - No vision model required by Playwright itself

3. **No Validation Enforcement**
   - Tools are advisory
   - Errors don''t halt execution
   - Verification tools exist but are optional

4. **Error Handling is Distributed**
   - Each tool decides how to handle its failures
   - Errors bubble to `BrowserBackend.callTool()`
   - Response object collects errors but doesn''t stop execution

5. **Tool Granularity is Fine**
   - 24+ small tools, not monolithic mega-tools
   - Each tool does one focused thing
   - Filtering applied for capability-based access

---

## Conclusion

**Playwright MCP is a capability provider for LLM agents, NOT an autonomous agent framework.**

The MCP server:
- ✅ Manages stateful browser context
- ✅ Executes focused browser tools atomically
- ✅ Collects and reports errors
- ✅ Provides optional verification tools
- ❌ Does NOT decide when to take screenshots
- ❌ Does NOT enforce success criteria
- ❌ Does NOT halt execution on errors
- ❌ Does NOT provide a rubric or checklist
- ❌ Does NOT implement retry loops or polling

All high-level orchestration (agent loop, success validation, tool selection) is the responsibility of the calling LLM agent.