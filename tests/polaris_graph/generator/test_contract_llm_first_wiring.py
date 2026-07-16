"""feat/intake-contract — LLM-FIRST COMPILE wiring tests (Part A).

Pure + offline. The OpenRouter client is NEVER constructed live: the adapter seam
(_build_contract_llm_fn) and the compiler are mocked. NO network, NO paid call, NO
compose/RACE/FACT. Asserts:

  * flag PG_INTAKE_CONTRACT_LLM default OFF;
  * flag OFF => _compile_compose_contract passes llm_fn=None AND never builds an
    adapter/client => byte-identical no-op;
  * flag ON => a non-None llm_fn is threaded into compile_intake_contract;
  * the adapter itself, over a FAKE async client, returns the client's .content as a
    sync string from inside/outside the event loop (isolated-thread bridge works).
"""
from __future__ import annotations

import pytest

import src.polaris_graph.generator.multi_section_generator as msg
import src.polaris_graph.intake.contract_compiler as cc


class _SpyCompile:
    """Records the llm_fn compile_intake_contract was called with; returns a real
    floor-only contract so downstream shape is intact."""

    def __init__(self) -> None:
        self.llm_fns: list = []

    def __call__(self, question, *, llm_fn=None, **kw):
        self.llm_fns.append(llm_fn)
        return cc._floor_contract(question)


def test_flag_default_off(monkeypatch) -> None:
    monkeypatch.delenv("PG_INTAKE_CONTRACT_LLM", raising=False)
    assert msg._intake_contract_llm_enabled() is False
    monkeypatch.setenv("PG_INTAKE_CONTRACT_LLM", "1")
    assert msg._intake_contract_llm_enabled() is True
    monkeypatch.setenv("PG_INTAKE_CONTRACT_LLM", "off")
    assert msg._intake_contract_llm_enabled() is False


def test_flag_off_threads_llm_fn_none_and_builds_no_client(monkeypatch) -> None:
    """Flag OFF (LLM) but an enforcement lane ON (so the compile actually runs):
    llm_fn=None is threaded and the adapter is NEVER built (no client => no-op)."""
    monkeypatch.delenv("PG_INTAKE_CONTRACT_LLM", raising=False)
    monkeypatch.setenv("PG_CONTRACT_ENFORCE_STRUCTURE", "1")  # force a compile

    spy = _SpyCompile()
    monkeypatch.setattr(cc, "compile_intake_contract", spy)

    def _boom_build(_model):
        raise AssertionError("adapter/client must NOT be built when the LLM flag is OFF")

    monkeypatch.setattr(msg, "_build_contract_llm_fn", _boom_build)

    contract = msg._compile_compose_contract("Compare remote vs office work.")
    assert contract is not None
    assert spy.llm_fns == [None], "flag OFF must thread llm_fn=None (byte-identical)"


def test_flag_on_threads_non_none_llm_fn(monkeypatch) -> None:
    """Flag ON => the adapter is built (mocked, no live client) and a non-None
    llm_fn is threaded into the compiler."""
    monkeypatch.setenv("PG_INTAKE_CONTRACT_LLM", "1")
    monkeypatch.setenv("PG_CONTRACT_ENFORCE_STRUCTURE", "1")

    spy = _SpyCompile()
    monkeypatch.setattr(cc, "compile_intake_contract", spy)

    sentinel = lambda prompt: "{}"  # noqa: E731 — a fake llm_fn, never called here
    built: list = []

    def _fake_build(model):
        built.append(model)
        return sentinel

    monkeypatch.setattr(msg, "_build_contract_llm_fn", _fake_build)

    msg._compile_compose_contract("Compare remote vs office work.")
    assert built, "adapter should be built when the LLM flag is ON"
    assert spy.llm_fns == [sentinel], "flag ON must thread the built (non-None) llm_fn"


def test_flag_on_but_no_enforcement_lane_is_noop(monkeypatch) -> None:
    """The LLM flag alone (no enforcement lane) does NOT compile or call any model:
    the compose gate still short-circuits => None, no adapter built."""
    monkeypatch.setenv("PG_INTAKE_CONTRACT_LLM", "1")
    for f in (
        "PG_CONTRACT_ENFORCE_STRUCTURE",
        "PG_CONTRACT_ENFORCE_PRESENTATION",
        "PG_SOURCE_ELIGIBILITY_GATE",
    ):
        monkeypatch.delenv(f, raising=False)

    def _boom_build(_model):
        raise AssertionError("no compile => no adapter build")

    monkeypatch.setattr(msg, "_build_contract_llm_fn", _boom_build)
    assert msg._compile_compose_contract("anything") is None


class _FakeResp:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeAsyncClient:
    """Stand-in for OpenRouterClient: async .generate returns a fake response.
    Records calls; NEVER touches the network."""

    def __init__(self, *a, **kw) -> None:
        self.calls: list[dict] = []

    async def generate(self, prompt, system="", temperature=0.7, **kw):
        self.calls.append({"prompt": prompt, "system": system, "temperature": temperature})
        return _FakeResp('{"tone": "x"}')


def test_adapter_returns_content_string(monkeypatch) -> None:
    """_build_contract_llm_fn wraps the async client into a SYNC str->str fn via the
    isolated-thread bridge, with NO live network. temperature is pinned to 0.0."""
    import src.polaris_graph.llm.openrouter_client as orc

    fake = _FakeAsyncClient()
    monkeypatch.setattr(orc, "OpenRouterClient", lambda *a, **kw: fake)

    fn = msg._build_contract_llm_fn("z-ai/glm-5.2")
    out = fn("compile this prompt")
    assert out == '{"tone": "x"}'
    assert fake.calls and fake.calls[0]["temperature"] == 0.0
    assert fake.calls[0]["prompt"] == "compile this prompt"


@pytest.mark.asyncio
async def test_adapter_works_from_running_event_loop(monkeypatch) -> None:
    """The compose path runs inside a live asyncio loop; the isolated-thread bridge
    must run the coroutine WITHOUT the 'asyncio.run from a running loop' error."""
    import src.polaris_graph.llm.openrouter_client as orc

    fake = _FakeAsyncClient()
    monkeypatch.setattr(orc, "OpenRouterClient", lambda *a, **kw: fake)

    fn = msg._build_contract_llm_fn("z-ai/glm-5.2")
    out = fn("prompt from within a loop")
    assert out == '{"tone": "x"}'
