"""I-deepfix-001 B3 (#1370) — Codex+Fable gate-fix P2: fresh-connection SWAP-THEN-CLOSE.

Hermetic, no socket. Proves that on a disconnect (RemoteProtocolError) with
PG_OPENROUTER_FRESH_CONN_ON_DISCONNECT ON, the retry path:

  * BUILDS the fresh client and SWAPS ``self._client`` BEFORE it ``aclose``s the OLD pool — so at the
    moment the old pool is torn down, ``self._client`` already points at the NEW client (the direct
    swap-then-close proof; a sibling reading ``self._client`` after the swap gets the healthy client),
  * re-POSTs on the NEW client, and
  * with the flag OFF (default) never rebuilds/closes at all (byte-identical legacy retry).

The NON-STREAM seam is forced via ``response_format=json_object`` + ``reasoning_enabled=False``.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from src.polaris_graph.llm import openrouter_client

_GEN_REQUEST = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")


def _ok_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": "the answer"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.0001},
            "model": "z-ai/glm-5.2",
            "provider": "Friendli",
        },
        request=_GEN_REQUEST,
    )


async def _noop_sleep(*_a, **_k):
    return None


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-hermetic")
    monkeypatch.setattr(openrouter_client.asyncio, "sleep", _noop_sleep)  # no real backoff
    yield


def _run_nonstream(client):
    return asyncio.run(
        client._call_impl(
            messages=[{"role": "user", "content": "q"}],
            call_type="contract_slot",
            reasoning_enabled=False,
            response_format={"type": "json_object"},
        )
    )


def test_swap_then_close_on_disconnect(monkeypatch):
    monkeypatch.setenv(openrouter_client._ENV_OPENROUTER_FRESH_CONN_ON_DISCONNECT, "1")
    client = openrouter_client.OpenRouterClient(api_key="test-key-hermetic")

    events: list = []
    holder: dict = {}

    class _OldClient:
        async def post(self, *_a, **_k):
            raise httpx.RemoteProtocolError("Server disconnected without sending a response")

        async def aclose(self):
            # SWAP-THEN-CLOSE proof: at teardown, self._client already points at the NEW client.
            events.append(("old_aclose", client._client is holder["new"]))

    class _NewClient:
        async def post(self, *_a, **_k):
            events.append(("new_post", True))
            return _ok_response()

        async def aclose(self):
            events.append(("new_aclose", True))

    old_client = _OldClient()
    new_client = _NewClient()
    holder["new"] = new_client
    client._client = old_client
    monkeypatch.setattr(client, "_build_async_client", lambda: new_client)

    resp = _run_nonstream(client)

    assert resp.content == "the answer"
    # the old pool WAS closed, and at close time self._client had ALREADY been swapped to the new client
    assert ("old_aclose", True) in events
    # the retry POST landed on the NEW client (swap happened before the retry)
    assert ("new_post", True) in events
    # the new (healthy) client was NOT torn down
    assert ("new_aclose", True) not in events
    # final client is the rebuilt one
    assert client._client is new_client
    # ordering: the old-aclose event fired AFTER the swap, BEFORE the successful new-post
    assert events.index(("old_aclose", True)) < events.index(("new_post", True))


def test_flag_off_no_rebuild_byte_identical(monkeypatch):
    """Flag OFF (default): a disconnect is retried on the SAME pool — no rebuild, no aclose — then
    fails closed after MAX_RETRIES (byte-identical legacy retry)."""
    monkeypatch.delenv(openrouter_client._ENV_OPENROUTER_FRESH_CONN_ON_DISCONNECT, raising=False)
    client = openrouter_client.OpenRouterClient(api_key="test-key-hermetic")

    state = {"posts": 0, "closed": False, "rebuilt": False}

    class _StubClient:
        async def post(self, *_a, **_k):
            state["posts"] += 1
            raise httpx.RemoteProtocolError("Server disconnected without sending a response")

        async def aclose(self):
            state["closed"] = True

    client._client = _StubClient()

    def _forbid_rebuild():
        state["rebuilt"] = True
        return _StubClient()

    monkeypatch.setattr(client, "_build_async_client", _forbid_rebuild)

    with pytest.raises(httpx.RemoteProtocolError):
        _run_nonstream(client)

    assert state["posts"] == openrouter_client.MAX_RETRIES + 1  # every attempt retried on same pool
    assert state["rebuilt"] is False   # flag OFF => never rebuilt
    assert state["closed"] is False    # flag OFF => old pool never torn down


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
