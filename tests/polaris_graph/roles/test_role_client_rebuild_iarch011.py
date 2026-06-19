"""F3 (I-arch-011, the run5 794->9 D8 seam crash): the role-transport must REBUILD a force-closed
client so the 4-role D8 gate ADJUDICATES instead of tearing down UNADJUDICATED.

WHY (C5 / F3): `_post_with_total_deadline` FORCE-CLOSES this thread's `httpx.Client` on a
total-deadline timeout (`client.close()`), and that rebuild could be missed (a swallowed factory
failure, or a force-close from a path that does not re-enter the timeout handler). The
`_http_client` getter previously rebuilt ONLY an absent (`None`) client, so a force-closed-but-not-
`None` client survived in TLS. The NEXT Mirror/Judge POST then hit a CLOSED client and httpx raised
a plain `RuntimeError: Cannot send a request, as the client has been closed` — which matched NONE of
the retry arms (it is not an httpx.TransportError / httpx.HTTPError / concurrent.futures.TimeoutError),
so it ESCAPED `complete()` and tore down the whole D8 seam (coverage=0.000, report shipped
`released_insufficient_safety_evidence`). The strongest faithfulness gate never adjudicated.

CONTRACT (transport client lifecycle ONLY — NO verdict logic / gate change; a genuinely unavailable
judge still fails closed per existing policy):
  (1) after a force-close (`client.close()`), the NEXT `_http_client` access returns a NON-closed
      (rebuilt) client — the getter heals a closed client, not only an absent one;
  (2) a role call made AFTER a force-close does NOT raise the "client has been closed" RuntimeError to
      the caller — the transport rebuilds and the verdict is returned, so D8 can ADJUDICATE.

PRE-FIX this test FAILS: (1) the getter returns the still-closed client (`is_closed` True), and (2)
`complete()` raises the closed-client RuntimeError out to the caller. POST-FIX both pass.

SPEND-FREE / NO NETWORK: the injected client AND the rebuild factory both use
`httpx.Client(transport=httpx.MockTransport(...))`, so there is NO socket / NO real LLM / NO spend in
any path pytest exercises (the rebuild factory MUST return a MockTransport client, else the rebuilt
client would make a real network POST — see `_make_transport`).
"""

from __future__ import annotations

import httpx
import pytest

from src.polaris_graph.roles.openrouter_role_transport import OpenRouterRoleTransport
from src.polaris_graph.roles.role_transport import RoleRequest

# Benchmark-stage Judge slug (a deliberative reasoning verifier on the D8 seam).
_JUDGE_SLUG = "qwen/qwen3.6-35b-a3b"

_GOOD_PAYLOAD = {
    "model": _JUDGE_SLUG,
    "provider": "DeepInfra",
    "choices": [{"message": {"role": "assistant", "content": "VERIFIED"}}],
    "usage": {"prompt_tokens": 11, "completion_tokens": 5},
}


@pytest.fixture(autouse=True)
def _transport_env(monkeypatch):
    """OpenRouter key (LAW VI) + a clean Judge env so the call path is deterministic and offline."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-or-key")
    monkeypatch.delenv("OPENROUTER_BASE_URL", raising=False)
    monkeypatch.delenv("PG_JUDGE_MODEL", raising=False)
    monkeypatch.delenv("PG_FOUR_ROLE_REASONING_EFFORT", raising=False)


def _mock_client() -> httpx.Client:
    """A fresh in-process client that returns the good Judge verdict (NO socket, NO spend)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_GOOD_PAYLOAD)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _make_transport() -> OpenRouterRoleTransport:
    """Transport whose INJECTED client AND rebuild factory both return MockTransport clients.

    The rebuild factory (`http_client_factory`) is what the getter / the closed-client retry arm
    invoke after a force-close; pinning it to a MockTransport client keeps the rebuilt client OFF the
    network (the default factory builds a real `httpx.Client`)."""
    return OpenRouterRoleTransport(_mock_client(), http_client_factory=_mock_client)


# ----------------------------------------------------------------------------------------------
# (1) the getter HEALS a force-closed client: the next access returns a NON-closed (rebuilt) one.
# ----------------------------------------------------------------------------------------------
def test_getter_rebuilds_a_force_closed_client(_transport_env):
    transport = _make_transport()
    first = transport._http_client
    assert first.is_closed is False, "the injected client starts OPEN"

    first.close()  # the total-deadline FORCE-CLOSE (_post_with_total_deadline :479 client.close()).
    assert first.is_closed is True, "the force-close must mark the client closed"

    rebuilt = transport._http_client
    assert rebuilt.is_closed is False, (
        "PRE-FIX FAILURE: the getter rebuilt only a None client, so a force-closed client survived "
        "in TLS and the next POST hit a CLOSED client. POST-FIX the getter rebuilds any closed "
        "client so D8 can adjudicate."
    )
    assert rebuilt is not first, "a healed client must be a fresh instance, not the closed one"


# ----------------------------------------------------------------------------------------------
# (2) a role call AFTER a force-close does NOT raise the "client has been closed" RuntimeError —
#     the transport rebuilds and the verdict is returned, so the D8 gate ADJUDICATES.
# ----------------------------------------------------------------------------------------------
def test_role_call_after_force_close_does_not_raise_closed_client(_transport_env):
    transport = _make_transport()
    # Force-close THIS thread's client, mirroring the total-deadline force-close, WITHOUT going
    # through the timeout retry arm (which is exactly the path that left the closed client behind).
    transport._http_client.close()

    try:
        resp = transport.complete(
            RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="decide")
        )
    except RuntimeError as exc:  # pragma: no cover - this IS the pre-fix failure we assert against
        if "has been closed" in str(exc):
            pytest.fail(
                "PRE-FIX FAILURE: the role call after a force-close raised the closed-client "
                f"RuntimeError out to the caller (D8 tears down UNADJUDICATED): {exc}"
            )
        raise

    assert resp.raw_text == "VERIFIED", (
        "POST-FIX: the transport rebuilt the force-closed client and returned the verdict, so the "
        "D8 gate adjudicates instead of crashing the seam."
    )
