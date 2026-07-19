# Global gating of `search_more_evidence`

Scope: `/home/polaris/wt/outline_agent/src/polaris_graph/outline/` + outline-agent tool registration.
Method: read the code (registration, registry filters, decide-menu, veto, seat), no guessing.

## Conclusion (up front)

There is **exactly one** flag that can globally disable `search_more_evidence`: the master
**seat `PG_OUTLINE_AGENT` (default OFF)**. When OFF, the whole `OutlineAgent` loop never
runs, so the tool is never registered and never reachable — the legacy `_call_outline` path
runs instead. When ON, the tool is **unconditionally registered as `core=True`** and is
**never filtered out** of the decide menu (the only menu/availability filter is `requires_data`,
and search has `requires_data=False`). No `PG_*` flag toggles search itself; no `requires_llm`
or client-availability condition can drop it. In the acceptance/agentic configs the seat is set
to `1`, so **search IS reachable**.

## Evidence

### 1. Registration is unconditional inside `_build_registry` — no per-tool flag

`outline_agent.py:1115-1128` registers the tool with no env guard:

```
1115  registry.register(ToolDefinition(
1116      name="search_more_evidence",
1117      description=( ... ),
1122      requires_data=False, requires_llm=True,
1123      parameters={ "section": ..., "aspect": ... },
1127      execute=_exec_search_more_evidence, tags=["retrieval"], core=True,
1128  ))
```

`requires_data=False`, `core=True`. There is no `if _env_flag(...)` wrapping this register call
(contrast `PG_OUTLINE_THEME_FLOOR` / `PG_OUTLINE_SECTION_FLOOR` at :2476/:2503 which DO gate
optional post-passes — but those gate outline *floors*, not the search tool).

### 2. The only global gate is the seat `PG_OUTLINE_AGENT` (default OFF)

`outline_agent.py:97-101`:

```
97   def outline_agent_enabled() -> bool:
98       """``PG_OUTLINE_AGENT`` kill-switch. DEFAULT OFF => the legacy ``_call_outline``-only path
...
101      return _env_flag("PG_OUTLINE_AGENT", default_on=False)
```

Enforced at the seam `outline_agent.py:2335-2341`: if `not outline_agent_enabled()` it returns
`_call_outline(...)` directly and the `OutlineAgent` (and thus `_build_registry`, and thus the
search tool) is never constructed. So OFF => search does not exist. This is the ONLY switch that
globally disables/fails-to-register search.

`_env_flag` semantics (`outline_agent.py:71-76`): OFF values are `("0","false","no","off","")`;
default when unset is `"0"` for this flag. So an unset env var means search is unreachable.

### 3. When ON, search is never filtered out of the menu or made unavailable

The decide step builds the tool list at `outline_agent.py:1246` and `:1254-1256`:

```
1246  available = self.registry.available_tools(True) + [_FINISH_ACTION]
1254  tool_descriptions = self.registry.get_decide_menu(
1255      True, core_threshold=_env_int("PG_OUTLINE_DECIDE_CORE_THRESHOLD", 60),
```

The registry filters (`tool_registry.py`):
- `available_tools` (`:71-76`) filters ONLY on `requires_data` — `if not tool.requires_data or has_data`.
  Search has `requires_data=False`, so it is ALWAYS in `available_tools`. `has_data` is hard-passed `True` anyway.
- `get_decide_menu` (`:94-121`) never hides a tool: at/below `core_threshold` (60) it prints the full
  listing; above it, core tools print in full and non-core go to an index. Search is `core=True`, so it
  always prints in full. The docstring (`:101-102`) states it "never hides a tool entirely."

There is **no filter on `requires_llm`** anywhere in these paths. So the `requires_llm=True` on search
cannot drop it from the menu or availability. (At dispatch, `outline_agent.py:1758-1791` gates only the
CODE-model client on `_CODEGEN_TOOLS`; search builds its own clients internally — comment at :1764-1766.)

### 4. There IS a per-call VETO, but it is narrow — not a global disable

`outline_agent.py:1731-1744`: a `search_more_evidence` call is vetoed only when its `section` is in
`workspace.unhomeable_sections` AND `workspace.required_titles` is set AND the section resolves to no
real title. This is a targeted, state-dependent veto of a specific reworded fetch — it cannot globally
disable the tool and is unrelated to any env flag.

### 5. Acceptance / agentic run configs set the seat ON => search reachable

The seat is exported `=1` in the run harnesses:
- `scripts/_run_16way_s3gear329.sh:15` — `export PG_OUTLINE_AGENT=1`
- `scripts/compose_agentic_report_s3gear329.py:198` — `os.environ.setdefault("PG_OUTLINE_AGENT", "1")`
- `scripts/outline_agentic_sweep.py:255` — `os.environ.setdefault("PG_OUTLINE_AGENT", "1")`;
  `:267-268` hard-BLOCKS the run if the seat is not on.
- `docs/agentic_report_s3gear329/report.md:27` records the accepted run as `AGENTIC (PG_OUTLINE_AGENT=1)`.

With the seat ON in these configs, `search_more_evidence` is registered (core, requires_data=False),
appears in every decide menu, and is dispatchable. It is reachable.

## Bottom line

- Global on/off switch: **`PG_OUTLINE_AGENT` (default OFF)** — the ONLY flag that can fail to register /
  globally disable search. Any other-cause "search never fires" would NOT be a global gating flag; it
  would be the narrow state-veto (:1731) or decide-time policy, not tool registration.
- No `PG_*` flag, no `requires_llm` condition, and no client-availability check can drop the search tool
  once the seat is ON.
- In the acceptance/agentic config the seat is `1`, so **search is reachable at the registration/menu level**.
