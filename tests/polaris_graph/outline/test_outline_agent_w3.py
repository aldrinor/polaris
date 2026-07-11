"""W3 regression tests for OutlineAgent's tool dispatch + tool-failure gap routing.

These are the FIRST tests for ``OutlineAgent``. They lock two fixes:

FIX 1 (``_execute``): the dispatch used to hardcode ``client=None``, so ``execute_python``
    -- registered, ``requires_llm=True``, and ADVERTISED to the decide LLM -- failed 100% of
    calls with "No LLM client available". It now constructs an ``OpenRouterClient`` on the CODE
    model for tools in ``_CODEGEN_TOOLS`` and awaits ``close()`` on every exit path.

FIX 2 (``_tool_failure_gap_check``): a failed ``execute_python`` now lands on the gap ledger via
    ``add_unfillable`` (UNFILLED + disclosed), NOT ``add`` (PENDING). A PENDING "(unassigned)"
    todo is routed to ``search_more_evidence`` by decide rule 1, which burns real web fetches on
    an error string and can auto-assign an outline section literally titled "(unassigned)".

NO NETWORK: ``OpenRouterClient`` is monkeypatched to a recording stub in every test that can
reach the dispatch; the tool executors are fakes registered onto the agent's own registry.
"""

from __future__ import annotations

import asyncio

import pytest

from src.polaris_graph.outline import outline_agent as oa
from src.polaris_graph.outline.outline_agent import (
    _CODEGEN_TOOLS,
    OutlineAgent,
    OutlineWorkspace,
)
from src.polaris_graph.tools.analysis_notebook import AnalysisStep
from src.polaris_graph.tools.react_agent import ReactDecision
from src.polaris_graph.tools.tool_registry import ToolDefinition, ToolResult


# --------------------------------------------------------------------------- fakes


class _StubOpenRouterClient:
    """Records construction + close. NEVER makes a network call."""

    instances: list["_StubOpenRouterClient"] = []

    def __init__(self, model=None, **kwargs):
        self.model = model
        self.closed = 0
        type(self).instances.append(self)

    async def close(self):
        self.closed += 1


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Every OpenRouterClient the agent could construct is the stub above.

    ``_execute`` imports it lazily from ``src.polaris_graph.llm.openrouter_client``, so patching
    the attribute on that module is what the dispatch actually sees.
    """
    _StubOpenRouterClient.instances = []
    import src.polaris_graph.llm.openrouter_client as orc

    monkeypatch.setattr(orc, "OpenRouterClient", _StubOpenRouterClient)
    yield
    _StubOpenRouterClient.instances = []


def _agent() -> OutlineAgent:
    ws = OutlineWorkspace(research_question="does X work?", ev_store={})
    return OutlineAgent(workspace=ws, agent_model="stub/agent", max_turns=1, wall_seconds=5)


def _register(agent: OutlineAgent, name: str, fn) -> None:
    agent.registry.register(
        ToolDefinition(
            name=name, description="fake", requires_data=False, requires_llm=False,
            parameters={}, execute=fn,
        )
    )


def _step(tool_name: str, *, success: bool, error: str = "boom") -> AnalysisStep:
    return AnalysisStep(
        step_number=1, reasoning="r", tool_name=tool_name,
        result=ToolResult(
            success=success, tool_name=tool_name, markdown="", error=error,
        ),
        elapsed_seconds=0.0,
    )


# --------------------------------------------------------------------------- 1


def test_failed_execute_python_lands_unfilled_and_is_never_routed_to_retrieval():
    """ASSERTION 1 (the bug Fable caught): a failed compute must NEVER become a retrieval todo."""
    agent = _agent()
    ledger = agent.workspace.gap_ledger

    agent._tool_failure_gap_check(_step("execute_python", success=False, error="ZeroDivisionError"))

    todos = ledger.all_todos
    assert len(todos) == 1, f"expected exactly one ledger todo, got {todos}"
    todo = todos[0]
    assert todo.status == "UNFILLED", f"status must be UNFILLED, got {todo.status!r}"
    assert todo.disclosure, "an UNFILLED todo must carry a disclosure reason (no silent drop)"
    assert ledger.unfilled == [todo]
    # THE load-bearing one: next_pending() is what decide rule 1 uses to fire
    # search_more_evidence. If this ever returns the compute todo, the loop burns real web
    # fetches on an error string.
    assert ledger.next_pending() is None
    assert ledger.pending_count == 0
    assert "ZeroDivisionError" in todo.aspect


def test_successful_execute_python_records_no_gap():
    agent = _agent()
    agent._tool_failure_gap_check(_step("execute_python", success=True, error=""))
    assert agent.workspace.gap_ledger.all_todos == []


# --------------------------------------------------------------------------- 2


def test_codegen_tools_membership():
    """ASSERTION 2: gate on the tools that CONSUME the client kwarg, not on requires_llm."""
    assert "execute_python" in _CODEGEN_TOOLS
    # search_more_evidence is requires_llm=True but builds its own clients and ignores the
    # kwarg -- gating on the flag would construct+close a wasted client on every search turn.
    assert "search_more_evidence" not in _CODEGEN_TOOLS
    agent = _agent()
    sme = agent.registry.get_tool("search_more_evidence")
    assert sme is not None and sme.requires_llm is True, (
        "premise of this test: search_more_evidence carries requires_llm=True"
    )


# --------------------------------------------------------------------------- 3


def test_execute_passes_real_client_to_execute_python_and_closes_it():
    """ASSERTION 3a: codegen tool gets a NON-None client, on the CODE model, and it is closed."""
    agent = _agent()
    seen: dict = {}

    async def _fake_execute_python(evidence_store, data_points, client, **kw):
        seen["client"] = client
        return ToolResult(success=True, tool_name="execute_python", markdown="ok")

    _register(agent, "execute_python", _fake_execute_python)

    step = asyncio.run(
        agent._execute(ReactDecision(reasoning="r", action="execute_python", action_input={}))
    )

    assert step.result.success is True
    assert seen["client"] is not None, "execute_python must receive a real client (FIX 1)"
    assert isinstance(seen["client"], _StubOpenRouterClient)
    assert seen["client"].model == oa.outliner_code_model()
    assert len(_StubOpenRouterClient.instances) == 1
    assert _StubOpenRouterClient.instances[0].closed == 1, "client must be closed on success"


def test_execute_closes_client_when_the_tool_raises():
    """ASSERTION 3b: the finally: path -- a raising tool must still close the client."""
    agent = _agent()

    async def _boom(evidence_store, data_points, client, **kw):
        raise RuntimeError("codegen blew up")

    _register(agent, "execute_python", _boom)

    step = asyncio.run(
        agent._execute(ReactDecision(reasoning="r", action="execute_python", action_input={}))
    )

    assert step.result.success is False
    assert "codegen blew up" in (step.result.error or "")
    assert len(_StubOpenRouterClient.instances) == 1
    assert _StubOpenRouterClient.instances[0].closed == 1, "client must be closed on the raise path"
    # ... and the failure still lands UNFILLED (FIX 2 runs on the raise path too).
    ledger = agent.workspace.gap_ledger
    assert [t.status for t in ledger.all_todos] == ["UNFILLED"]
    assert ledger.next_pending() is None


def test_execute_passes_none_client_for_a_non_codegen_tool():
    """ASSERTION 3c: a non-codegen tool gets client=None and NO client is constructed at all."""
    agent = _agent()
    seen: dict = {}

    async def _fake_inspect(evidence_store, data_points, client, **kw):
        seen["client"] = client
        return ToolResult(success=True, tool_name="inspect_basket", markdown="ok")

    _register(agent, "inspect_basket", _fake_inspect)

    asyncio.run(
        agent._execute(ReactDecision(reasoning="r", action="inspect_basket", action_input={}))
    )

    assert seen["client"] is None
    assert _StubOpenRouterClient.instances == [], (
        "a non-codegen tool must not construct an OpenRouterClient"
    )


# --------------------------------------------------------------------------- 4


def test_statistical_summary_failure_still_lands_pending():
    """ASSERTION 4: pre-existing behavior must not regress -- a numeric-tool failure is a
    genuine retrieval gap and stays PENDING (it IS fillable by more evidence)."""
    agent = _agent()
    ledger = agent.workspace.gap_ledger

    agent._tool_failure_gap_check(_step("statistical_summary", success=False, error="no rows"))

    todos = ledger.all_todos
    assert len(todos) == 1
    assert todos[0].status == "PENDING"
    assert todos[0].needed_kind == "numeric_rows"
    nxt = ledger.next_pending()
    assert nxt is todos[0], "a statistical_summary gap MUST still be routable to retrieval"


# --------------------------------------------------------------------------- 5 (W4)


def test_successful_execute_python_result_reaches_the_decide_prompt(monkeypatch):
    """W4 ASSERTION: the computed number must reach the string the decide LLM is handed.

    Before W4, ``summary_for_llm()`` -- the ONLY notebook accessor fed to the decide prompt
    (outline_agent.py:1163 -> :1182) -- printed only "{n}. {tool} [{status}] ({elapsed}s) —
    {reasoning[:60]}". A SUCCESSFUL execute_python therefore recorded NO gap (nothing was
    disclosed) while its computed value was unreachable by the planner: an UNDISCLOSED
    UNREACHABLE RESULT, and a tool that burned a turn + an OpenRouterClient for zero effect.

    This drives the REAL _decide() prompt assembly and the REAL AnalysisNotebook; only the
    network egress is stubbed, and it CAPTURES the prompt rather than faking it.
    """
    magic = "1234567.89"
    captured: dict = {}

    class _CapturingClient(_StubOpenRouterClient):
        async def generate_structured(self, prompt, schema, system, **kw):
            captured["prompt"] = prompt
            return ReactDecision(reasoning="r", action="finish_outline", action_input={})

    import src.polaris_graph.llm.openrouter_client as orc
    monkeypatch.setattr(orc, "OpenRouterClient", _CapturingClient)

    agent = _agent()
    agent.workspace.notebook.add_step(AnalysisStep(
        step_number=1,
        reasoning="compute the 30-year NPV from the cited discount rate",
        tool_name="execute_python",
        result=ToolResult(
            success=True, tool_name="execute_python",
            markdown=f"### Computed\nTELUS 30yr NPV = ${magic}\n",
            insights=[f"NPV is ${magic}"],
            statistics={"npv": magic},
        ),
        elapsed_seconds=1.0,
    ))

    asyncio.run(agent._decide())
    prompt = captured["prompt"]

    assert magic in prompt, (
        "the computed value must appear VERBATIM in the decide prompt -- otherwise "
        "execute_python is strictly net-negative"
    )
    assert f"stats: npv={magic}" in prompt
    assert f"insight: NPV is ${magic}" in prompt

    # ...and the DEFAULT accessor is unchanged, so react_agent.py:7875's consumption of
    # summary_for_llm() is not silently mutated under it (the digest is opt-in).
    assert magic not in agent.workspace.notebook.summary_for_llm()


def test_notebook_result_digest_char_cap_is_env_tunable(monkeypatch):
    """LAW VI: every knob env-tunable. PG_NOTEBOOK_SUMMARY_RESULT_CHARS=0 suppresses it."""
    from src.polaris_graph.tools.analysis_notebook import AnalysisNotebook

    nb = AnalysisNotebook(query="q", evidence_ids=[])
    nb.add_step(AnalysisStep(
        step_number=1, reasoning="r", tool_name="execute_python",
        result=ToolResult(
            success=True, tool_name="execute_python",
            markdown="x" * 5000, insights=["i"], statistics={"npv": "42.5"},
        ),
        elapsed_seconds=1.0,
    ))

    monkeypatch.setenv("PG_NOTEBOOK_SUMMARY_RESULT_CHARS", "0")
    assert "42.5" not in nb.summary_for_llm(include_results=True)

    monkeypatch.setenv("PG_NOTEBOOK_SUMMARY_RESULT_CHARS", "80")
    small = nb.summary_for_llm(include_results=True)
    assert "stats: npv=42.5" in small, "statistics are emitted FIRST -- the numbers survive the cap"
    assert len(small) < 600, "the 5000-char markdown must be truncated to the budget"

    monkeypatch.setenv("PG_NOTEBOOK_SUMMARY_RESULT_CHARS", "not-an-int")
    assert "42.5" in nb.summary_for_llm(include_results=True), "a bad knob falls back to default"


def test_failed_step_contributes_no_result_digest():
    """A FAILED step's payload is an error string, not a result -- it must not be digested."""
    from src.polaris_graph.tools.analysis_notebook import AnalysisNotebook

    nb = AnalysisNotebook(query="q", evidence_ids=[])
    nb.add_step(AnalysisStep(
        step_number=1, reasoning="r", tool_name="execute_python",
        result=ToolResult(
            success=False, tool_name="execute_python",
            markdown="Code execution failed: ZeroDivisionError",
            statistics={"bogus": "999"}, error="ZeroDivisionError",
        ),
        elapsed_seconds=1.0,
    ))

    s = nb.summary_for_llm(include_results=True)
    assert "[FAILED]" in s
    assert "999" not in s
    assert "stats:" not in s


# --------------------------------------------------------------------------- 6 (W4 step 2)
# A SUCCESSFUL compute must be DISCLOSED and CARRIED -- and must NOT become a render path.


def _stats_tool(stats, *, success=True, insights=None):
    async def _fn(evidence_store, data_points, client, **kw):
        return ToolResult(
            success=success, tool_name="execute_python", markdown="md",
            statistics=stats, insights=insights or [],
            source_evidence_ids=["ev_1"], error=None if success else "ZeroDivisionError",
        )
    return _fn


def test_successful_compute_is_disclosed_and_carried_but_barred_from_rendering():
    agent = _agent()
    _register(agent, "execute_python", _stats_tool({"npv": 1234567.89}, insights=["NPV positive"]))

    asyncio.run(agent._execute(
        ReactDecision(reasoning="derive NPV", action="execute_python", action_input={})
    ))

    ws = agent.workspace
    assert len(ws.compute_results) == 1
    row = ws.compute_results[0]
    assert row["statistics"] == {"npv": 1234567.89}
    assert row["insights"] == ["NPV positive"]
    # THE binding invariant: exploratory compute is NOT a render path.
    assert row["renderable"] is False
    assert "[#calc:]" in row["bar_reason"]
    # ...and it is DISCLOSED (the "undisclosed unreachable result" is now at worst disclosed).
    assert any("1234567.89" in d and "BARRED from the report" in d for d in ws.disclosures)
    # a SUCCESS is still not a gap
    assert ws.gap_ledger.all_todos == []


def test_failed_compute_carries_no_result_and_stays_unfilled():
    """The FAILURE path of the new hook -- a failed compute's stray statistics must never be
    carried or disclosed as a computed value (it lands UNFILLED via FIX 2 instead)."""
    agent = _agent()
    _register(agent, "execute_python", _stats_tool({"bogus": 999}, success=False))

    asyncio.run(agent._execute(
        ReactDecision(reasoning="derive NPV", action="execute_python", action_input={})
    ))

    ws = agent.workspace
    assert ws.compute_results == []
    assert not any("999" in d for d in ws.disclosures)
    assert [t.status for t in ws.gap_ledger.all_todos] == ["UNFILLED"]


def test_non_codegen_tool_statistics_are_not_carried_as_compute_results():
    agent = _agent()

    async def _statsy(evidence_store, data_points, client, **kw):
        return ToolResult(
            success=True, tool_name="statistical_summary", markdown="md",
            statistics={"mean": 3.5}, data_points_produced=[{"x": 1}],
        )

    _register(agent, "statistical_summary", _statsy)
    asyncio.run(agent._execute(
        ReactDecision(reasoning="r", action="statistical_summary", action_input={})
    ))

    assert agent.workspace.compute_results == []


def test_successful_compute_with_no_statistics_is_not_carried():
    agent = _agent()
    _register(agent, "execute_python", _stats_tool({}))
    asyncio.run(agent._execute(
        ReactDecision(reasoning="r", action="execute_python", action_input={})
    ))
    assert agent.workspace.compute_results == []
