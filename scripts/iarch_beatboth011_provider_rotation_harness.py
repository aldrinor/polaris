#!/usr/bin/env python3
"""FAIL-LOUD behavioral harness for #1290 landmine-3 (TRACK termination-ROTATE).

WHAT THIS PROVES (offline, no live LLM / no model load):
    On a total-deadline FORCE-CLOSE, the 4-role OpenRouter transport now ADDS the slow provider to
    `body["provider"]["ignore"]` BEFORE the bounded retry, so the NEXT POST targets a DIFFERENT host
    (the next entry in the pinned `order`). Before this fix, the retry rebuilt the SAME body and
    re-POSTed to the SAME slow provider (live evidence: 339 same-host 300s force-closes, 0 rotations).

HOW (drives the REAL `OpenRouterRoleTransport.complete()` retry loop, not a re-implementation):
    * Monkeypatch the module-level `_post_with_total_deadline` so it raises
      `concurrent.futures.TimeoutError` for the first N attempts (each = a force-close that the REAL
      handler in `complete()` must rotate off), then returns a controlled success response on the
      next attempt. INSIDE the patched function we DEEP-COPY `body["provider"]["ignore"]` per attempt
      (it is mutated IN PLACE across the loop, so a live reference would alias the final list and make
      the growth assertion vacuous — the advisor's pitfall).
    * Monkeypatch `_build_openrouter_body` to a body with a KNOWN multi-provider `order` so the
      targeted-host inference is deterministic and offline (no routing-config dependency).
    * Neutralize the capture / cost side-effect modules so the success path completes without spend.

ASSERTIONS (any failure -> sys.exit(1), FAIL LOUD):
    A. FORCE-CLOSE ROTATES: across the two simulated force-closes the captured per-attempt ignore
       sets GROW monotonically and never re-target an already-ignored host -> attempts 2 and 3 each
       point at a NEW provider (the grind is broken).
    B. SUCCESS PATH UNCHANGED: a clean run (zero force-close) leaves `ignore` byte-identical to the
       pinned baseline (no spurious rotation on the happy path).
    C. KILL-SWITCH: with PG_JUDGE_PROVIDER_ROTATE=0 a force-close does NOT rotate (the pre-fix
       byte-identical behavior is preserved for an operator opt-out).

FAITHFULNESS: this harness only inspects WHICH provider the retry targets. It asserts nothing about
verdict parsing / role adjudication / span-grounding, none of which this fix touches.
"""

from __future__ import annotations

import concurrent.futures
import copy
import os
import sys

# Repo root on sys.path so `src.*` imports resolve when run directly.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import httpx  # noqa: E402

from src.polaris_graph.roles import openrouter_role_transport as ort  # noqa: E402
from src.polaris_graph.roles.role_transport import RoleRequest  # noqa: E402


# A pinned multi-provider order so the targeted-host inference is deterministic and offline.
_PINNED_ORDER = ["z-ai", "baidu", "novita", "gmicloud"]
_BASE_URL = "https://openrouter.example/api/v1"
_MODEL_SLUG = "z-ai/glm-5.1"


class _FakeResponse:
    """Minimal stand-in for the httpx.Response the success path consumes."""

    def __init__(self, payload: dict) -> None:
        self.status_code = httpx.codes.OK
        self.headers: dict = {}
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _NoopCapture:
    """Stub for the pathB capture module (context-manager + no-op call sink)."""

    def llm_role(self, _role):  # noqa: D401 - context manager
        class _Ctx:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc):
                return False

        return _Ctx()

    def capture_llm_call(self, **_kwargs):
        return None


def _install_common_stubs(monkeypatch_targets: dict) -> None:
    """Patch endpoint resolution + body build + capture/cost side effects (offline)."""
    # Endpoint -> controlled tuple (base_url, api_key, model_slug).
    monkeypatch_targets["openrouter_role_endpoint"] = ort.openrouter_role_endpoint
    ort.openrouter_role_endpoint = lambda _role: (_BASE_URL, "sk-test", _MODEL_SLUG)  # type: ignore[assignment]

    # Body build -> a body carrying the pinned provider order (fresh dict per call, like production).
    monkeypatch_targets["_build_openrouter_body"] = ort._build_openrouter_body
    ort._build_openrouter_body = (  # type: ignore[assignment]
        lambda _request, _model_slug, _msgs: {
            "model": _MODEL_SLUG,
            "messages": _msgs,
            "provider": {
                "order": list(_PINNED_ORDER),
                "ignore": [],
                "allow_fallbacks": False,
                "require_parameters": True,
            },
        }
    )

    # Capture + verbatim-IO + cost orchestrator -> no-ops (no spend, no disk, no network).
    monkeypatch_targets["_pathb_capture"] = ort._pathb_capture
    ort._pathb_capture = _NoopCapture()  # type: ignore[assignment]
    monkeypatch_targets["_raw_io_capture"] = ort._raw_io_capture
    ort._raw_io_capture = lambda **_kwargs: None  # type: ignore[assignment]


def _restore(monkeypatch_targets: dict) -> None:
    for name, original in monkeypatch_targets.items():
        setattr(ort, name, original)


def _make_transport() -> ort.OpenRouterRoleTransport:
    # An httpx.Client is injected but never actually used (we patch _post_with_total_deadline).
    return ort.OpenRouterRoleTransport(httpx.Client())


def _success_payload() -> dict:
    return {
        "model": _MODEL_SLUG,
        "provider": "Z.AI",
        "choices": [{"message": {"content": "ENTAILED"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 2},
    }


def _run_scenario(*, force_closes: int, rotate_env: str | None) -> list[list[str]]:
    """Drive the REAL complete() loop; return the per-POST-attempt deep-copied ignore snapshots.

    `force_closes` = how many initial attempts raise concurrent.futures.TimeoutError (force-close);
    the next attempt returns the success payload. `rotate_env` sets PG_JUDGE_PROVIDER_ROTATE.
    """
    targets: dict = {}
    # Give the retry budget enough room for the requested number of force-closes + the success.
    prior_retries = os.environ.get("PG_ROLE_TRANSPORT_RETRIES")
    prior_rotate = os.environ.get("PG_JUDGE_PROVIDER_ROTATE")
    os.environ["PG_ROLE_TRANSPORT_RETRIES"] = str(force_closes + 1)
    if rotate_env is None:
        os.environ.pop("PG_JUDGE_PROVIDER_ROTATE", None)
    else:
        os.environ["PG_JUDGE_PROVIDER_ROTATE"] = rotate_env

    snapshots: list[list[str]] = []
    attempts = {"n": 0}

    def _fake_post(client, url, *, json_body, headers, timeout, total_s):
        # DEEP-COPY the ignore list NOW (it is mutated in place across the loop; a live ref aliases
        # the final list and makes the growth check vacuous).
        provider = json_body.get("provider") or {}
        snapshots.append(copy.deepcopy(provider.get("ignore", [])))
        attempts["n"] += 1
        if attempts["n"] <= force_closes:
            raise concurrent.futures.TimeoutError()
        return _FakeResponse(_success_payload())

    try:
        _install_common_stubs(targets)
        targets["_post_with_total_deadline"] = ort._post_with_total_deadline
        ort._post_with_total_deadline = _fake_post  # type: ignore[assignment]

        transport = _make_transport()
        req = RoleRequest(
            role="mirror",
            model_slug=_MODEL_SLUG,
            messages=[{"role": "user", "content": "verify"}],
            prompt="verify",
            params={},
        )
        resp = transport.complete(req)
        if getattr(resp, "raw_text", None) != "ENTAILED":
            raise AssertionError(
                f"success path did not return the expected verdict; got {resp!r}"
            )
    finally:
        _restore(targets)
        # restore env
        if prior_retries is None:
            os.environ.pop("PG_ROLE_TRANSPORT_RETRIES", None)
        else:
            os.environ["PG_ROLE_TRANSPORT_RETRIES"] = prior_retries
        if prior_rotate is None:
            os.environ.pop("PG_JUDGE_PROVIDER_ROTATE", None)
        else:
            os.environ["PG_JUDGE_PROVIDER_ROTATE"] = prior_rotate

    return snapshots


def _fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def main() -> int:
    print("=== #1290 landmine-3 provider-rotation behavioral harness ===")

    # --- A. FORCE-CLOSE ROTATES (rotation default-ON) ---------------------------------------------
    # Two force-closes then a success: 3 POST attempts. The 1st targets z-ai (slow); rotation must
    # add z-ai to ignore so attempt 2 targets baidu; another force-close adds baidu so attempt 3
    # (success) targets novita.
    snaps = _run_scenario(force_closes=2, rotate_env=None)
    print(f"[A] default-ON, 2 force-closes: per-attempt ignore snapshots = {snaps}")
    if len(snaps) != 3:
        _fail(f"[A] expected 3 POST attempts (2 force-close + 1 success), got {len(snaps)}: {snaps}")
    # The ignore set must GROW monotonically (each force-close adds exactly one new host).
    set0, set1, set2 = set(snaps[0]), set(snaps[1]), set(snaps[2])
    if not (set0 == set() and set0 < set1 < set2):
        _fail(
            "[A] ignore set did NOT grow monotonically across force-closes "
            f"(expected {{}} < ... < ...); got {snaps}"
        )
    if len(set1) != 1 or len(set2) != 2:
        _fail(f"[A] each force-close must add exactly one provider; got sizes {len(set1)},{len(set2)}: {snaps}")
    # The targeted (= first not-yet-ignored) host must differ on each retry -> grind broken.
    targeted = [
        next(p for p in _PINNED_ORDER if p not in snaps[i]) for i in range(3)
    ]
    print(f"[A] provider targeted per attempt = {targeted}")
    if len(set(targeted)) != 3:
        _fail(f"[A] the SAME host was re-targeted across retries (grind not broken): {targeted}")
    if targeted[0] != _PINNED_ORDER[0]:
        _fail(f"[A] first attempt should target the head of order ({_PINNED_ORDER[0]}); got {targeted[0]}")
    print("[A] PASS: force-close rotates off the slow host on every retry (grind broken).")

    # --- B. SUCCESS PATH UNCHANGED ----------------------------------------------------------------
    snaps_ok = _run_scenario(force_closes=0, rotate_env=None)
    print(f"[B] default-ON, 0 force-closes: snapshots = {snaps_ok}")
    if len(snaps_ok) != 1:
        _fail(f"[B] a clean run should POST exactly once; got {len(snaps_ok)}: {snaps_ok}")
    if list(snaps_ok[0]) != []:
        _fail(f"[B] a clean run must NOT rotate (ignore should stay baseline []); got {snaps_ok[0]}")
    print("[B] PASS: happy path leaves the ignore list untouched (no spurious rotation).")

    # --- C. KILL-SWITCH (PG_JUDGE_PROVIDER_ROTATE=0) ----------------------------------------------
    snaps_off = _run_scenario(force_closes=2, rotate_env="0")
    print(f"[C] rotate OFF, 2 force-closes: snapshots = {snaps_off}")
    if len(snaps_off) != 3:
        _fail(f"[C] expected 3 POST attempts, got {len(snaps_off)}: {snaps_off}")
    if any(list(s) != [] for s in snaps_off):
        _fail(
            "[C] with rotation OFF a force-close must NOT mutate ignore (pre-fix byte-identical "
            f"behavior); got {snaps_off}"
        )
    print("[C] PASS: kill-switch preserves the pre-fix no-rotation behavior.")

    print("=== ALL CHECKS PASSED: force-close provider rotation FIRES in the real retry loop ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
