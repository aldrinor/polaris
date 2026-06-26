"""I-wire-004 (#1318) — D8 Sentinel fail-fast: per-role total-deadline + bounded concurrency.

ROOT CAUSE (confirmed in-code + issue #1318): the Sentinel (`minimax/minimax-m2`) is the slow
4-role leg. A single generic 900s per-call wall meant a slow/trickling minimax POST burned the FULL
15-min deadline before the force-close rotation could advance off it — 602 claims x ~900s
force-closes = the multi-hour grind that ran the seam past the outer sweep wall-deadline, so the
verdict-assembly that populates `four_role.final_verdicts` was never reached (zero rows, assertion f
FAIL).

THE FIX (mirrors the proven entailment_judge A2 idiom):
  - PER-ROLE total-deadline: Sentinel default 300s (fail FAST) while Mirror/Judge keep 900s, so the
    slow minimax host is abandoned in seconds and the already-ON force-close rotation advances to the
    next of its 4 providers -> a fast SUCCESSFUL call -> a REAL verdict.
  - tighter total-deadline-retry cap for the Sentinel (PG_ROLE_TRANSPORT_TOTAL_DEADLINE_RETRIES_SENTINEL).
  - bounded Sentinel concurrency (PG_FOUR_ROLE_SENTINEL_CONCURRENCY).

These are TRANSPORT-/aggregation-only assertions. The faithfulness contract is UNTOUCHED:
- a Sentinel that times out degrades the claim to UNGROUNDED -> _compose_final_verdict downgrades a
  Judge VERIFIED/PARTIAL to UNSUPPORTED (a COUNTED row, NEVER a credited VERIFIED), and
- when a verdict truly cannot be formed (Mirror fails closed) the claim is UNSUPPORTED — fail-CLOSED.
No live network calls (mock transport).
"""

from __future__ import annotations

import threading
import time

import pytest

from src.polaris_graph.roles.openrouter_role_transport import (
    OpenRouterRoleTransport,
    _role_transport_total_s,
    sentinel_concurrency_limit,
    _sentinel_semaphore,
)
from src.polaris_graph.roles.openai_compatible_transport import RoleTransportError
from src.polaris_graph.roles.role_pipeline import _compose_final_verdict
from src.polaris_graph.roles.role_transport import RoleRequest
from src.polaris_graph.roles.sentinel_contract import SentinelResult, SentinelVerdict


# ---------------------------------------------------------------------------------------------
# 1) PER-ROLE total-deadline: Sentinel fails FAST (300s) while Mirror/Judge stay generous (900s).
# ---------------------------------------------------------------------------------------------
def test_sentinel_default_total_deadline_is_fast_others_generous(monkeypatch):
    monkeypatch.delenv("PG_ROLE_TRANSPORT_TOTAL_S", raising=False)
    monkeypatch.delenv("PG_ROLE_TRANSPORT_TOTAL_S_SENTINEL", raising=False)
    monkeypatch.delenv("PG_ROLE_TRANSPORT_TOTAL_S_MIRROR", raising=False)
    monkeypatch.delenv("PG_ROLE_TRANSPORT_TOTAL_S_JUDGE", raising=False)
    # The fix: the slow Sentinel leg fails fast (so it can rotate off the slow host), Mirror/Judge
    # keep the generous wall a high-effort reasoning call legitimately needs. 300s (NOT the lighter
    # entailment 150s) — the minimax decomposition is a heavier reasoning call; a too-tight wall
    # would force-close HEALTHY calls -> mass over-drop. Still 3x tighter than the generic 900s.
    assert _role_transport_total_s("sentinel") == 300.0
    assert _role_transport_total_s("mirror") == 900.0
    assert _role_transport_total_s("judge") == 900.0


def test_no_arg_call_is_byte_identical(monkeypatch):
    """The pre-#1318 no-arg signature must stay 900s default + honor the generic env (byte-identical)."""
    monkeypatch.delenv("PG_ROLE_TRANSPORT_TOTAL_S", raising=False)
    assert _role_transport_total_s() == 900.0
    monkeypatch.setenv("PG_ROLE_TRANSPORT_TOTAL_S", "321")
    assert _role_transport_total_s() == 321.0


def test_per_role_env_overrides_generic(monkeypatch):
    monkeypatch.setenv("PG_ROLE_TRANSPORT_TOTAL_S", "900")
    monkeypatch.setenv("PG_ROLE_TRANSPORT_TOTAL_S_SENTINEL", "90")
    # Explicit per-role ALWAYS wins (can tighten OR loosen) — full operator control.
    assert _role_transport_total_s("sentinel") == 90.0
    # Mirror has no per-role override + no coded default -> falls through to the generic knob.
    assert _role_transport_total_s("mirror") == 900.0


def test_explicit_per_role_can_loosen_sentinel(monkeypatch):
    monkeypatch.setenv("PG_ROLE_TRANSPORT_TOTAL_S", "300")
    monkeypatch.setenv("PG_ROLE_TRANSPORT_TOTAL_S_SENTINEL", "600")
    # An explicit per-role env is the ONLY way to loosen the Sentinel past its fail-fast default.
    assert _role_transport_total_s("sentinel") == 600.0


def test_generic_knob_can_only_TIGHTEN_sentinel_not_raise(monkeypatch):
    """THE WIRING-FIX PROPERTY (I-wire-004): a generic PG_ROLE_TRANSPORT_TOTAL_S can only TIGHTEN the
    Sentinel (min), NEVER raise it past the 300s fail-fast default. This is what makes fix-1 fire
    regardless of the slate's generic value — the prior 'generic wins' precedence was inert because
    the slate already sets the generic knob (run_gate_b.py:950) and it did NOT stop the grind."""
    monkeypatch.delenv("PG_ROLE_TRANSPORT_TOTAL_S_SENTINEL", raising=False)
    # generic 900 (loose) -> sentinel STAYS 300 (the fix is wired, not overridden).
    monkeypatch.setenv("PG_ROLE_TRANSPORT_TOTAL_S", "900")
    assert _role_transport_total_s("sentinel") == 300.0
    assert _role_transport_total_s("mirror") == 900.0   # Mirror still tracks the generic knob.
    # generic 120 (tighter than 300) -> sentinel tightens to 120 (min wins).
    monkeypatch.setenv("PG_ROLE_TRANSPORT_TOTAL_S", "120")
    assert _role_transport_total_s("sentinel") == 120.0
    assert _role_transport_total_s("mirror") == 120.0


def test_unparseable_per_role_falls_through(monkeypatch):
    monkeypatch.delenv("PG_ROLE_TRANSPORT_TOTAL_S", raising=False)
    monkeypatch.setenv("PG_ROLE_TRANSPORT_TOTAL_S_SENTINEL", "not-a-number")
    # A garbage per-role value must not crash and must fall through to the sentinel coded default.
    assert _role_transport_total_s("sentinel") == 300.0


# ---------------------------------------------------------------------------------------------
# 2) BOUNDED Sentinel concurrency: default unbounded (None), positive value caps.
# ---------------------------------------------------------------------------------------------
def test_sentinel_concurrency_default_unbounded(monkeypatch):
    monkeypatch.delenv("PG_FOUR_ROLE_SENTINEL_CONCURRENCY", raising=False)
    assert sentinel_concurrency_limit() == 0
    assert _sentinel_semaphore() is None  # no semaphore acquired -> byte-identical to pre-#1318.


def test_sentinel_concurrency_positive_caps(monkeypatch):
    monkeypatch.setenv("PG_FOUR_ROLE_SENTINEL_CONCURRENCY", "3")
    assert sentinel_concurrency_limit() == 3
    sema = _sentinel_semaphore()
    assert sema is not None
    # The semaphore admits exactly the configured count concurrently.
    assert sema.acquire(blocking=False) is True
    assert sema.acquire(blocking=False) is True
    assert sema.acquire(blocking=False) is True
    assert sema.acquire(blocking=False) is False  # 4th blocked -> bounded.
    for _ in range(3):
        sema.release()


# ---------------------------------------------------------------------------------------------
# 3) FAITHFULNESS — the rotate/deadline fix PRODUCES verdicts when N-1 roles succeed, but a
#    sentinel-failed claim is UNSUPPORTED (a counted row), NEVER VERIFIED; and a truly-unformable
#    verdict (Mirror failed closed) is UNSUPPORTED — fail-CLOSED.
# ---------------------------------------------------------------------------------------------
def test_sentinel_failed_claim_is_unsupported_not_verified():
    """N-1 roles succeed (Mirror grounded + Judge VERIFIED) but the Sentinel timed out/failed-closed
    (UNGROUNDED) -> the composed verdict is UNSUPPORTED (a COUNTED final verdict), never VERIFIED."""
    failed_sentinel = SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=False)
    verdict = _compose_final_verdict(
        mirror_failed_closed=False,
        sentinel_result=failed_sentinel,
        raw_judge_verdict="VERIFIED",
    )
    assert verdict == "UNSUPPORTED"  # downgraded, NOT credited VERIFIED -> faithfulness held.


def test_sentinel_none_is_unsupported_not_verified():
    """A wholly-missing Sentinel result (None) on a Judge VERIFIED still downgrades to UNSUPPORTED."""
    verdict = _compose_final_verdict(
        mirror_failed_closed=False,
        sentinel_result=None,
        raw_judge_verdict="VERIFIED",
    )
    assert verdict == "UNSUPPORTED"


def test_mirror_failed_closed_is_unsupported_fail_closed():
    """A verdict that truly cannot be formed (Mirror failed closed) is UNSUPPORTED — fail-CLOSED,
    never a false pass."""
    verdict = _compose_final_verdict(
        mirror_failed_closed=True,
        sentinel_result=None,
        raw_judge_verdict=None,
    )
    assert verdict == "UNSUPPORTED"


# ---------------------------------------------------------------------------------------------
# 4) PRODUCE-VERDICTS (the quality goal): a healthy (fast-success) Sentinel that returns GROUNDED
#    composes a fully-grounded claim to VERIFIED — so final_verdicts is populated with a REAL verdict,
#    not zeroed and not all-UNSUPPORTED. This is a compose-level assertion (the LOCKED rule); the
#    BEHAVIORAL proof that the fail-fast-rotate path PRODUCES that fast-success Sentinel call lives in
#    section 5 below (it drives the real complete() POST-loop).
# ---------------------------------------------------------------------------------------------
def test_healthy_grounded_sentinel_composes_to_verified():
    """A grounded Sentinel + Judge VERIFIED composes to VERIFIED — final_verdicts gets a real,
    non-zero verdict (the fix's quality goal: produce verdicts, do NOT zero them)."""
    grounded = SentinelResult(SentinelVerdict.GROUNDED, parsed_ok=True)
    verdict = _compose_final_verdict(
        mirror_failed_closed=False,
        sentinel_result=grounded,
        raw_judge_verdict="VERIFIED",
    )
    assert verdict == "VERIFIED"  # final_verdicts gets a REAL, non-zero verdict.


# ---------------------------------------------------------------------------------------------
# 5) BEHAVIORAL — drive the REAL complete() POST-loop on a SLOW sentinel: prove (a) it fails FAST
#    (not 900s), (b) it POSTs exactly 1 + total_deadline_retries times (the tighter cap is wired +
#    sentinel-scoped), (c) the rotation ignore-list actually grew (force-close rotation fired).
#    This is the task's headline requirement ("prove the rotate fires on a slow/failed sentinel").
# ---------------------------------------------------------------------------------------------
class _SlowBlockingClient:
    """A client whose POST blocks (a trickle-hung socket) until close() — the force-close releases it.

    Counts post() calls + snapshots the request body's provider.ignore list per POST so the test can
    assert (i) the tighter total-deadline retry cap is honored and (ii) force-close rotation actually
    fired (the slow host was added to `ignore` before the next attempt). Rebuilt-per-attempt by the
    factory so each retry gets a fresh counting client."""

    def __init__(self, registry: list) -> None:
        self.post_calls = 0
        self.closed = False
        self.ignore_snapshots: list[list] = []
        self._unblock = threading.Event()
        registry.append(self)

    def post(self, url, *, json=None, headers=None, timeout=None):
        self.post_calls += 1
        provider = (json or {}).get("provider") or {}
        self.ignore_snapshots.append(list(provider.get("ignore") or []))
        self._unblock.wait(timeout=20)  # blocks like a trickle-hung read until force-closed
        raise AssertionError("post should have been force-closed before returning")

    def close(self):
        self.closed = True
        self._unblock.set()


def test_slow_sentinel_fails_fast_rotates_and_caps_retries(monkeypatch):
    """A trickle-hung Sentinel POST is force-closed at the TIGHT 0.5s deadline, ROTATES to the next
    provider, and is bounded by PG_ROLE_TRANSPORT_TOTAL_DEADLINE_RETRIES_SENTINEL — then fails CLOSED
    (RoleTransportError), which the seam degrades to per-claim UNGROUNDED. NEVER hangs, never a verdict."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-dummy")
    monkeypatch.setenv("PG_ROLE_TRANSPORT_TOTAL_S_SENTINEL", "0.5")   # fail FAST
    monkeypatch.setenv("PG_ROLE_TRANSPORT_RETRIES", "2")              # general fault budget = 2
    monkeypatch.setenv("PG_ROLE_TRANSPORT_TOTAL_DEADLINE_RETRIES_SENTINEL", "1")  # tighter cap = 1
    monkeypatch.setenv("PG_JUDGE_PROVIDER_ROTATE", "1")              # force-close rotation ON
    monkeypatch.setenv("PG_FOUR_ROLE_SENTINEL_CONCURRENCY", "0")     # unbounded (isolate the deadline)

    clients: list[_SlowBlockingClient] = []

    def _factory() -> _SlowBlockingClient:
        return _SlowBlockingClient(clients)

    transport = OpenRouterRoleTransport(_factory(), http_client_factory=_factory)
    request = RoleRequest(
        role="sentinel",
        model_slug="minimax/minimax-m2",
        messages=[{"role": "user", "content": "claim under check"}],
        params={"documents": []},
    )

    started = time.monotonic()
    with pytest.raises(RoleTransportError):
        transport.complete(request)
    elapsed = time.monotonic() - started

    # (a) FAST: ~ (1 + total_deadline_retries) x 0.5s = ~1s, FAR below the old 900s grind.
    assert elapsed < 20.0
    # (b) the tighter total-deadline cap (1) bounds the attempts: 1 initial + 1 retry = 2 POSTs total
    # across the rebuilt-per-attempt clients. With cap=1 it MUST be 2 (not 3 = the general retries),
    # proving the sentinel-scoped tighter cap is wired and APPLIES (not the general transport_retries).
    posting_clients = [c for c in clients if c.post_calls > 0]
    total_posts = sum(c.post_calls for c in posting_clients)
    assert total_posts == 2, f"expected 2 sentinel POSTs (1 + cap-1 retry), got {total_posts}"
    # (c) every client that actually POSTed (i.e. was hung) was force-closed, so its orphan worker
    # unblocked + exited — no hang. (The TimeoutError arm rebuilds a fresh client on EACH timeout
    # incl. the last attempt before the cap check raises, so a trailing never-POSTed client may exist;
    # the load-bearing guarantee is that every HUNG (posting) client is force-closed.)
    assert all(c.closed for c in posting_clients)
    assert len(posting_clients) == 2  # rotation rebuilt a fresh client for the 2nd (different) host.
    # (d) ROTATION FIRED (the task's headline requirement, asserted not just logged): the 1st POST saw
    # an empty/no ignore-list; the 2nd POST saw the slow host appended to provider.ignore, so the retry
    # genuinely targeted a DIFFERENT host. This assertion FAILS if rotation were off — proving wired.
    first_ignore = posting_clients[0].ignore_snapshots[0]
    second_ignore = posting_clients[1].ignore_snapshots[0]
    assert len(second_ignore) > len(first_ignore), (
        f"rotation did not fire: 1st ignore={first_ignore}, 2nd ignore={second_ignore}"
    )


def test_sentinel_total_deadline_retry_cap_is_one_by_default(monkeypatch):
    """fix-2 is WIRED ON by default (NOT slate-dependent): with NO
    PG_ROLE_TRANSPORT_TOTAL_DEADLINE_RETRIES_SENTINEL set and the general PG_ROLE_TRANSPORT_RETRIES=2,
    a slow Sentinel POSTs exactly 2 times (1 + default-1 retry), not 3 — directly fixing the forensic's
    '300s x 3 = 900s/claim' grind. (A non-sentinel role would still use the full general budget.)"""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-dummy")
    monkeypatch.setenv("PG_ROLE_TRANSPORT_TOTAL_S_SENTINEL", "0.5")
    monkeypatch.setenv("PG_ROLE_TRANSPORT_RETRIES", "2")               # general budget = 2 (=> 3 attempts)
    monkeypatch.delenv("PG_ROLE_TRANSPORT_TOTAL_DEADLINE_RETRIES_SENTINEL", raising=False)  # default
    monkeypatch.setenv("PG_JUDGE_PROVIDER_ROTATE", "1")
    monkeypatch.setenv("PG_FOUR_ROLE_SENTINEL_CONCURRENCY", "0")

    clients: list[_SlowBlockingClient] = []

    def _factory() -> _SlowBlockingClient:
        return _SlowBlockingClient(clients)

    transport = OpenRouterRoleTransport(_factory(), http_client_factory=_factory)
    request = RoleRequest(
        role="sentinel",
        model_slug="minimax/minimax-m2",
        messages=[{"role": "user", "content": "claim under check"}],
        params={"documents": []},
    )
    with pytest.raises(RoleTransportError):
        transport.complete(request)
    total_posts = sum(c.post_calls for c in clients)
    assert total_posts == 2, (
        f"default sentinel total-deadline cap should bound to 2 POSTs (1+default-1), got {total_posts}"
    )
