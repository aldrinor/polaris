# search_more_evidence — invocation & counting instrumentation

File under audit: `/home/polaris/wt/outline_agent/src/polaris_graph/outline/outline_agent.py`

## TL;DR conclusion

There is **no dedicated counter that increments per `search_more_evidence` call** in the
outline-agent loop. The only "search happened" signal reported in telemetry is
`new_evidence_count` (`outline_agent.py:2639`), which is an **evidence-store size DELTA**, not a
call counter. It measures **net NEW rows that survived the fold-in screen** — i.e. it observes
*outcome (rows kept)*, not ATTEMPTED / SUCCESSFUL / FAILED **calls**. So:

- **Could it read 0 while calls actually happen?** YES — and it demonstrably DID (documented
  "Iter-2 P2-1" aliasing bug, now fixed). It still reads 0 for any run where every search call is
  attempted but keeps zero new rows (all fetched rows deduped/screened out). That is a genuine
  "0 net evidence" result, but it is **indistinguishable from "search never invoked"** in this
  field.
- **Per-call record exists elsewhere**: every invocation is logged as a notebook `AnalysisStep`
  with `tool_name="search_more_evidence"` (`:1792-1797`), serialized in checkpoints as
  `notebook_steps[].tool_name` + `.success` (`:595-604`). That is the ONLY faithful ATTEMPTED-vs-
  SUCCESS record — but it is **not surfaced as a "search count"** anywhere in the return payload.

## How the tool is invoked

- Tool defined/registered: `_tool_search_more_evidence` (`:691`), wrapped by
  `_exec_search_more_evidence` (`:1099`), registered under `name="search_more_evidence"`
  (`:1116`, `execute=...` `:1127`).
- Dispatch: the loop `run()` (`:1982`) → `_execute(decision)` (`:2013` / def `:1722`). Every turn
  that decides `action == "search_more_evidence"` calls `tool_def.execute(...)` (`:1774`).
- **Result success semantics** (`:834-839`):
  ```python
  return ToolResult(
      success=n_kept > 0,
      tool_name="search_more_evidence",
      ...
      error=("" if n_kept > 0 else "no_new_evidence_survived_screen"),
  )
  ```
  So a call that *did fetch* rows but kept none is marked `success=False`. A veto (`:1746-1752`)
  and early-arg failures (`:710`, `:758`, `:799`) are also `success=False` — all still real
  invocations.

## The per-call record (ATTEMPTED vs SUCCESS) — exists but not counted

`_execute` builds a step for EVERY dispatched action and appends it:
```python
# outline_agent.py:1792-1797
step = AnalysisStep(
    step_number=self.workspace.turn, reasoning=decision.reasoning,
    tool_name=decision.action, result=result,
    elapsed_seconds=round(time.monotonic() - t0, 3),
)
self.workspace.notebook.add_step(step)
```
Serialized per checkpoint (`:595-604`): `{"tool_name": s.tool_name, ..., "success": s.result.success}`.
=> To count attempted/successful/failed search calls you must post-hoc filter
`notebook_steps` by `tool_name == "search_more_evidence"` and inspect `success`. **Nothing in the
code does this**; there is no `search_count`/`n_search`/`+= 1` increment on the search path.

## The thing that LOOKS like a counter — and why it's a proxy, not a counter

```python
# outline_agent.py:2637-2639
"ev_store_size": len(final_ws.ev_store),
"ev_store_size_at_seed": ev_store_size_before,
"new_evidence_count": len(final_ws.ev_store) - ev_store_size_before,
```
Snapshot taken BEFORE the loop (`:2452-2453`, correctly ordered before `agent.run()` at `:2607`):
```python
ev_ids_before = set(ev_store.keys())
ev_store_size_before = len(ev_ids_before)
```
This is a **net-rows-kept delta**, not an invocation count. Failure modes for reading 0:
1. **Historic broken instrumentation (now FIXED)** — the "Iter-2 P2-1" comment (`:2442-2453`)
   states `new_evidence_count` was `0` **every run** because `final_ws.ev_store is ev_store`
   (same dict, by reference), so `len(after) - len(after)` was always 0 even while searches ran and
   fetched rows. The pre-loop `ev_store_size_before` snapshot is the fix.
2. **Still-live 0 case** — if every search call keeps 0 rows (`n_kept == 0`: all fetched rows
   url-dup dropped / off-topic screened, see fold-in `:809-823`), `new_evidence_count` is a
   legitimate 0 **despite real, attempted, even partially-"fetched" calls**. This field cannot
   distinguish "searched, nothing survived" from "never searched."

## Not the same counter (different module)

`_exa_session_searches` (`src/polaris_graph/agents/searcher.py:98`, `+= 1` at `:1125`) is a
**global Exa-backend API-call counter**, one layer below the outline agent. It counts backend Exa
calls session-wide, not this loop's `search_more_evidence` tool invocations, and is not read by
`outline_agent.py`.

## Answer to the posed question

- Counter observes: **net NEW evidence rows KEPT** (outcome), NOT attempted/successful/failed calls.
- Broken-instrumentation-reads-0: **was a real bug** (aliasing, P2-1, now fixed); a **residual
  ambiguous 0** remains for the "searched but nothing survived screen" case.
- Genuine-never-invoked vs broken: to tell them apart you MUST read `notebook_steps` for
  `tool_name == "search_more_evidence"` (the only ATTEMPTED/SUCCESS record) — `new_evidence_count`
  alone cannot answer it.
