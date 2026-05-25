# Coding-agent review patterns — Aider, Cline, Roo-Code (deep source dive)

Research date: 2026-05-25
Scope: read actual source code of three production AI coding agents. Operator
specifically named them as relevant to POLARIS writer-reviewer harness design,
even though none is primarily a visual-review tool.

## 1. Aider (Python CLI) — `Aider-AI/aider`

### Self-review / validator before completion
Stub pattern. `reply_completed()` in `aider/coders/base_coder.py:1625` is empty:
```python
def reply_completed(self):
    pass
```
Architect mode (`architect_coder.py`) overrides to ask user confirmation
**before** applying:
```python
def reply_completed(self):
    content = self.partial_response_content
    if not content or not content.strip():
        return
    if not self.auto_accept_architect and not self.io.confirm_ask("Edit the files?"):
        return
```
**Key:** no re-read validation. Once `apply_updates()` runs (`base_coder.py:2296`),
changes are committed immediately. There is NO post-application verification
that changes actually worked.

### Multi-agent or single-agent
Single agent, writer=reviewer. The `Coder` class in `base_coder.py` handles both
generation and application. "Architect" mode is a delegation pattern (spawns
another `Coder` instance with an editor model) but both are the same agent
class doing both write and validation.

### Stop conditions
Unbounded until context exhausted. `base_coder.py:876-923`:
```python
def run(self, with_message=None, preproc=True):
    while True:
        try:
            user_message = self.get_input()
            self.run_one(user_message, preproc)
            self.show_undo_hint()
        except KeyboardInterrupt:
            self.keyboard_interrupt()
```
Stops on: EOFError, `ContextWindowExceededError` (caught at `send_message:1460`),
user Ctrl+C. No built-in max-request limit.

### Tool granularity
Monolithic. No discrete "tool" abstraction — Aider writes to files via
`apply_updates()`, runs shell via `run_cmd()`. Single large edit-format handler
(`editblock_coder.py`: ~20 KB).

### Error handling: malformed output
`apply_updates():2306` increments a counter and reflects the error to the LLM:
```python
except ValueError as err:
    self.num_malformed_responses += 1
    self.io.tool_error("The LLM did not conform to the edit format.")
    self.reflected_message = str(err)
    return edited
```
JSON parse failures handled in `parse_partial_args():2343-2362` with 4
retry-to-complete strategies (appending `]}`, `}]}`, `"}]}` etc.).

### Visual/screenshot
No native screenshot or browser tool. `--browser` mode runs in browser via
FastHTML (`webbrowser.open(urls.release_notes)`); no screenshot, no automation.

### AAB (Action Authorization Boundary)
File whitelist. `allowed_to_edit():2191`:
```python
def allowed_to_edit(self, path):
    full_path = self.abs_root_path(path)
    if full_path in self.abs_fnames:
        self.check_for_dirty_commit(path)
        return True
    if not Path(full_path).exists():
        if not self.io.confirm_ask("Create new file?", subject=path):
            self.io.tool_output(f"Skipping edits to {path}")
            return
```
Hard Python-list membership check. Output is parsed and validated **after**
generation. Non-bypassable except via user confirmation prompt.

---

## 2. Cline (VSCode extension, TypeScript) — `cline/cline`

### Self-review / validator before completion
No automatic re-read. Cline has NO built-in "verify the change worked"
step. Tools write the file (`WriteToFileToolHandler`, `ApplyPatchHandler`) and
move on. Completion only when the model explicitly calls `AttemptCompletionHandler`.

### Multi-agent or single-agent
Single agentic loop per task. `src/core/task/index.ts:1453-1480`:
```typescript
private async initiateTaskLoop(userContent: ClineContent[]): Promise<void> {
    let nextUserContent = userContent
    while (!this.taskState.abort) {
        const didEndLoop = await this.recursivelyMakeClineRequests(
            nextUserContent, includeFileDetails
        )
        if (didEndLoop) break
        nextUserContent = [{ type: "text", text: formatResponse.noToolsUsed(...) }]
    }
}
```
Subagents exist (`NewTaskTool`, `SubagentToolHandler`) but are ad-hoc spawns,
not a true multi-agent system.

### Stop conditions
Bounded with user override. `recursivelyMakeClineRequests():2354-2380`:
```typescript
if (this.taskState.consecutiveMistakeCount >= maxConsecutiveMistakes) {
    if (yoloModeToggled) {
        return true  // Ends loop with failure
    }
    const { response } = await this.ask("mistake_limit_reached", ...)
    if (response === "messageResponse") {
        // Allow user to continue
    }
}
```
User can override the cap.

### Tool granularity
24 discrete tool handlers in `src/core/task/tools/handlers/`:
- `ReadFileToolHandler.ts` — single file read
- `WriteToFileToolHandler.ts` — single file write
- `ExecuteCommandToolHandler.ts` — single command
- `BrowserToolHandler.ts` — screenshot, navigation (Puppeteer)
- `AttemptCompletionHandler.ts` — explicit completion signal

Each tool ~1-5 KB, single-responsibility.

### Error handling: malformed output
`ToolValidator` in `src/core/task/tools/ToolValidator.ts` rejects malformed
tool calls and returns an error result to the model; re-prompted to fix.

### Visual / screenshot
Yes, full browser automation. `BrowserSession.ts` in `src/services/browser/`:
- Puppeteer-launched Chrome
- `screenshot():441` returns base64 PNG/WebP
- Click, scroll, type, navigation supported

Tool is discretionary — model must call it.

### AAB
Environment-variable-based command permissions.
`CommandPermissionController.ts:1-100`:
```typescript
validateCommand(command: string): PermissionValidationResult {
    if (!this.config) {
        return { allowed: true, reason: "no_config" }  // backward-compat
    }
    const dangerousChar = this.detectDangerousCharsOutsideQuotes(command)
    if (dangerousChar) {
        return { allowed: false, reason: "shell_operator_detected", ... }
    }
    const parseResult = this.parseCommandSegments(command)
    // Check allow/deny patterns...
}
```
Configuration via `CLINE_COMMAND_PERMISSIONS` env var. Set at process
initialization, checked **before** any shell command. Non-bypassable: the
controller is consulted by `ExecuteCommandToolHandler`, not by output parser.
Agent cannot call a command that doesn't pass validation.

File write permissions are per-tool via `AutoApprovalHandler` in `task/index.ts`.

---

## 3. Roo-Code (Cline fork, TypeScript) — `RooCodeInc/Roo-Code`

### Self-review / validator before completion
Significant divergence from Cline: adds auto-approval infrastructure
(`AutoApprovalHandler`, `RooProtectedController`) but **still no post-application
verification**. Protected files (`.rooignore`, `.roomodes`, `.roo/**`) bypass
autoapproval and ALWAYS require explicit approval — this is a permission-level
check, not a correctness-level check.

### Multi-agent or single-agent
Single Task instance, task-delegation aware. `Task.ts:2427-2460`:
```typescript
private async initiateTaskLoop(userContent: Anthropic.Messages.ContentBlockParam[]): Promise<void> {
    let nextUserContent = userContent
    while (!this.abort) {
        const didEndLoop = await this.recursivelyMakeClineRequests(
            nextUserContent, includeFileDetails
        )
        if (didEndLoop) break
        nextUserContent = [{ type: "text", text: formatResponse.noToolsUsed() }]
    }
}
```

### Stop conditions
Bounded with user override; same pattern as Cline.

### Tool granularity
24 discrete tools in `/src/core/tools/`. `EditTool.ts` is more sophisticated
(search-replace semantic matching vs Cline's patch format). `UseMcpToolTool.ts`
bridges to MCP tools — visual review can come via MCP servers.

### Error handling: malformed output
Each tool returns an error result; `validateAndFixToolResultIds()` in
`validateToolResultIds.ts` aligns tool result IDs with tool use blocks.

### Visual / screenshot
No native browser tool — removed in deprecation. Relies on external MCP servers
via `UseMcpToolTool`.

### AAB
File protection via `RooProtectedController.ts`:
```typescript
private static readonly PROTECTED_PATTERNS = [
    ".rooignore",
    ".roomodes",
    ".roorules*",
    ".clinerules*",
    ".roo/**",
    ".vscode/**",
    "*.code-workspace",
    "AGENTS.md",
    "AGENT.md",
]

isWriteProtected(filePath: string): boolean {
    return this.ignoreInstance.ignores(relativePath)
}
```
Checked by `WriteToFileTool` before applying edits. Non-bypassable: file is
checked at write time, not at output parsing.

---

## Cross-cutting comparison

| Dimension | Aider | Cline | Roo-Code |
|---|---|---|---|
| Self-review | Stub (user confirm only) | None (explicit AttemptCompletion) | None (autoapproval + protection) |
| Multi-agent | Single (architect = delegation) | Single | Single |
| Stop condition | Unbounded + context | Bounded + user override | Bounded + user override |
| Tool count | Monolithic (1-2 files) | 24 granular handlers | 24 granular tools |
| Error handling | Retry + reflection | Tool validation + reflection | Tool validation + reflection |
| Screenshot | No | Yes (Puppeteer) | No (MCP only) |
| AAB enforcement | File whitelist (pre-check) | Command env var (pre-check) | File protection (pre-check) |

## Strongest AAB: Cline

`CommandPermissionController`:
1. Config read at initialization, not per-request.
2. Validation **before** `ExecuteCommandToolHandler` is invoked.
3. Checks for shell operators (`>`, `|`, `;`, newlines, backticks).
4. ALL segments of chained commands must pass.
5. Even if the model outputs a valid tool call, the handler validates before execution.

`CommandPermissionController.ts:38-45`:
```typescript
/**
 * Controls command execution permissions based on environment variable configuration.
 * Uses glob pattern matching to allow/deny specific commands.
 *
 * 4. Validate EACH segment against allow/deny rules - ALL must pass
 * 5. Recursively validate any subshell contents
 * 6. If no rules are defined (env var not set) → ALLOWED (backward compatibility)
 */
```
Non-delegable to the model. Output is never consulted for permissions.

## Lessons for POLARIS

1. **None of these three implements a true post-action verification loop before
   committing code.** All three rely on permission-checking at write time, not
   correctness-checking afterward. POLARIS's "audit the rendered page after the
   diff" model is more rigorous than any of these.
2. **AAB lives at the framework layer, not the prompt layer.** Cline's pattern
   (env-var policy, command-segment parse, non-delegable check) is the
   reference shape for POLARIS's CI-required-check approach.
3. **Single-agent self-review = self-agreement bias.** None of the three has a
   separate reviewer agent. POLARIS's writer (Claude) + reviewer (Codex) split
   IS the differentiator vs this class of tool — but only if the inputs to
   reviewer aren't the writer's prose (the harness drift incident).
4. **Tool granularity matters for control.** Cline's 24 fine-grained handlers
   make permission checks tractable per-tool. POLARIS's visual gate adds one
   coarse new operation ("audit-and-emit-artifact"); tighter sub-tools may
   reduce the bypass surface area.
