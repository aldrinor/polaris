#!/usr/bin/env python3
"""FAIL-LOUD offline harness for I-arch-007-tail: a total_deadline_exceeded now ROTATES the pinned
glm-5.2 host on the bounded retry (was: re-pinned the SAME stuck host every retry -> the compose
wall-time long pole).

Drives the REAL _EntailmentJudge._judge_uncached() retry loop (not a re-implementation) with
_post_with_total_deadline monkeypatched to raise concurrent.futures.TimeoutError for the first two
attempts (each == a total-deadline force-close the handler must rotate off), then return a controlled
success on the third. Captures json_body["provider"]["order"] per POST.

ASSERTIONS (any failure -> sys.exit(1)):
  A. ROTATE-ON: with PG_JUDGE_PROVIDER_ROTATE=1 + spread/off mode the three attempts target THREE
     DISTINCT hosts -> the trickle-hang grind is broken and a real verdict is recovered.
  B. KILL-SWITCH: with PG_JUDGE_PROVIDER_ROTATE=0 there is no provider pin to rotate (byte-identical
     pre-fix behavior) -> the run still terminates on the fail-closed sentinel, no rotation.
FAITHFULNESS: inspects only WHICH host the retry targets; asserts nothing about verdict parsing.
"""
from __future__ import annotations
import concurrent.futures
import copy
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# env BEFORE importing the module (module reads PG_ENTAILMENT_TOTAL_S at import)
os.environ["PG_ENTAILMENT_TOTAL_S"] = "5"
os.environ["PG_ENTAILMENT_TOTAL_DEADLINE_RETRIES"] = "2"
os.environ["PG_ENTAILMENT_RETRIES"] = "2"
os.environ["PG_JUDGE_VERDICT_CACHE"] = "0"
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")

import src.polaris_graph.llm.entailment_judge as ej  # noqa: E402

_CHAIN = ["z-ai", "baidu", "novita", "gmicloud"]


class _FakeResp:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "choices": [{"message": {"content": '{"verdict":"ENTAILED","reason":"ok"}'}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.0},
        }


def _run_case(rotate: str, burst: str, fail_first: int):
    os.environ["PG_JUDGE_PROVIDER_ROTATE"] = rotate
    os.environ["PG_JUDGE_BURST_SPREAD"] = burst
    captured: list = []

    calls = {"n": 0}

    def _fake_post(client, endpoint, headers, json_body, total_s):
        captured.append(copy.deepcopy(json_body.get("provider")))
        calls["n"] += 1
        if calls["n"] <= fail_first:
            raise concurrent.futures.TimeoutError("simulated total-deadline force-close")
        return _FakeResp()

    orig_post = ej._post_with_total_deadline
    orig_chain = ej._mirror_provider_chain
    ej._post_with_total_deadline = _fake_post  # type: ignore[assignment]
    ej._mirror_provider_chain = lambda: list(_CHAIN)  # type: ignore[assignment]
    try:
        import threading as _threading
        j = ej._EntailmentJudge.__new__(ej._EntailmentJudge)
        j._tls = _threading.local()
        j._client = object()
        j._endpoint = "http://x/chat/completions"
        j._api_key = "k"
        j._model = "z-ai/glm-5.2"
        j._build_client = lambda: object()  # type: ignore[assignment]
        verdict, reason = j._judge_uncached("A GOOD sentence.", "A GOOD sentence span.")
    finally:
        ej._post_with_total_deadline = orig_post
        ej._mirror_provider_chain = orig_chain
    return captured, verdict, reason


def _orders(captured):
    out = []
    for p in captured:
        if isinstance(p, dict) and "order" in p:
            out.append(tuple(p["order"]))
        else:
            out.append(None)
    return out


def main() -> int:
    # CASE A: rotation ON, off mode (deterministic cursor 0 start), 2 force-closes then success.
    capA, verdictA, reasonA = _run_case(rotate="1", burst="off", fail_first=2)
    ordersA = _orders(capA)
    print(f"[A rotate=1 off] posts={len(capA)} orders={ordersA} verdict={verdictA} reason={reasonA!r}")
    if len(capA) != 3:
        print("FAIL A: expected 3 POST attempts (2 force-close + 1 success)")
        return 1
    hosts = [o[0] for o in ordersA if o]
    if len(hosts) != 3 or len(set(hosts)) != 3:
        print(f"FAIL A: total_deadline retries did NOT rotate to 3 distinct hosts: {hosts}")
        return 1
    if hosts != _CHAIN[:3]:
        print(f"FAIL A: rotation order unexpected: {hosts} != {_CHAIN[:3]}")
        return 1
    if verdictA != "ENTAILED":
        print(f"FAIL A: expected recovered ENTAILED verdict, got {verdictA!r}")
        return 1
    print("PASS A: total_deadline_exceeded ROTATES z-ai->baidu->novita and recovers a REAL verdict.")

    # CASE B: kill-switch — rotation OFF => no provider pin to rotate (pre-fix behavior preserved).
    capB, verdictB, reasonB = _run_case(rotate="0", burst="off", fail_first=3)
    ordersB = _orders(capB)
    print(f"[B rotate=0] posts={len(capB)} orders={ordersB} verdict={verdictB} reason={reasonB!r}")
    if any(o is not None for o in ordersB):
        print(f"FAIL B: kill-switch OFF still pinned/rotated a provider order: {ordersB}")
        return 1
    if not reasonB.startswith("judge_error"):
        print(f"FAIL B: expected fail-closed sentinel on exhaustion, got reason={reasonB!r}")
        return 1
    print("PASS B: rotation OFF -> no order pin, fail-closed sentinel on exhaustion (pre-fix parity).")
    print("ALL PASS: I-arch-007-tail total_deadline rotation verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
