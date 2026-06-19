#!/usr/bin/env python
"""I-arch-011 entailment-deadline DEADLOCK discriminator + §-1.4 regression harness.

Advisor-mandated DIAGNOSTIC-FIRST (run #6 froze 13 min at the 737-source enrichment-section
verify, stack parked in entailment_judge._post_with_total_deadline:127 fut.result()). A bounded
single judge() call should cap at ~2*PG_ENTAILMENT_TOTAL_S then emit the fail-closed sentinel, so a
13-min freeze is anomalous. This harness points the REAL _EntailmentJudge at a LOCAL server that
accepts the connection then TRICKLES body bytes forever (never completing) — the exact
"keep-alive resets the per-read gap timer" wedge HANG-J3 describes — and discriminates:

  (a) total_s not honored / wrong value -> _post_with_total_deadline never bounds (P1 hangs)
  (b) deadline fires but client.close()/retry/rebuild loops forever  (P1 or P2 hangs)
  (c) cross-call client poisoning / leaked wedged worker            (P3 hangs)

FAIL-LOUD: exits non-zero if ANY probe exceeds WALL (= MULT * total_s). After the fix EVERY probe
must bound. This file is BOTH the diagnostic and the banked regression test (re-run post-fix; it
must turn all-GREEN). Real code path, zero mocks of the judge transport.
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time

# ---- knobs (small so the repro is fast; LAW VI env-overridable) -------------------------------
TOTAL_S = float(os.environ.get("REPRO_TOTAL_S", "5"))          # the per-call deadline under test
WALL_MULT = float(os.environ.get("REPRO_WALL_MULT", "6"))      # a probe exceeding MULT*deadline = UNBOUNDED
WALL_S = TOTAL_S * WALL_MULT
MODE = os.environ.get("REPRO_MODE", "trickle")                 # trickle | silent


def _log(msg: str) -> None:
    print(f"[repro {time.strftime('%H:%M:%S')}] {msg}", flush=True)


class WedgeServer:
    """A local TCP server that accepts, reads the request, then NEVER completes the response.

    trickle: send 200 + a huge Content-Length, then drip 1 body byte every 2 s forever — httpx's
             per-read gap timer resets on each byte, so a non-streaming .post() read blocks
             UNBOUNDED (the production OpenRouter/Cloudflare keep-alive trickle).
    silent:  send NOTHING after accept (a truly dead rx=tx=0 socket).
    """

    def __init__(self, mode: str) -> None:
        self.mode = mode
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind(("127.0.0.1", 0))
        self._srv.listen(64)
        self.port = self._srv.getsockname()[1]
        self._stop = False
        self._conns: list[socket.socket] = []
        self._t = threading.Thread(target=self._serve, daemon=True)

    def start(self) -> None:
        self._t.start()

    def _serve(self) -> None:
        while not self._stop:
            try:
                self._srv.settimeout(1.0)
                conn, _ = self._srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            self._conns.append(conn)
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket) -> None:
        try:
            conn.settimeout(2.0)
            try:
                conn.recv(65536)  # drain request headers (best-effort)
            except OSError:
                pass
            if self.mode == "silent":
                while not self._stop:
                    time.sleep(0.5)  # hold open, send nothing
                return
            # trickle: valid status + a Content-Length we will NEVER satisfy, then drip forever
            head = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: application/json\r\n"
                "Content-Length: 1000000000\r\n"
                "Connection: keep-alive\r\n"
                "\r\n"
            )
            conn.sendall(head.encode())
            while not self._stop:
                try:
                    conn.sendall(b" ")  # one keep-alive byte: resets httpx's read-gap timer
                except OSError:
                    return
                time.sleep(2.0)
        except Exception as exc:  # noqa: BLE001
            _log(f"server handler exit: {type(exc).__name__}: {exc}")

    def close(self) -> None:
        self._stop = True
        for c in self._conns:
            try:
                c.close()
            except OSError:
                pass
        try:
            self._srv.close()
        except OSError:
            pass


def _run_probe(name: str, fn) -> dict:
    """Run fn() in a daemon thread, join up to WALL_S. Returns timing + bounded/unbounded verdict."""
    result: dict = {"name": name, "outcome": None, "elapsed": None, "bounded": None}
    start = time.monotonic()

    def _target() -> None:
        try:
            r = fn()
            result["outcome"] = f"returned: {r!r}"
        except BaseException as exc:  # noqa: BLE001 — we WANT to see TimeoutError etc.
            result["outcome"] = f"raised: {type(exc).__name__}: {exc}"
        finally:
            result["elapsed"] = time.monotonic() - start

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(WALL_S)
    if t.is_alive():
        result["elapsed"] = time.monotonic() - start
        result["outcome"] = f"STILL RUNNING after {WALL_S:.0f}s (leaked)"
        result["bounded"] = False
        _log(f"  {name}: UNBOUNDED — {result['outcome']}")
    else:
        result["bounded"] = result["elapsed"] <= WALL_S
        _log(f"  {name}: {result['outcome']}  (elapsed {result['elapsed']:.1f}s, "
             f"{'BOUNDED' if result['bounded'] else 'UNBOUNDED'})")
    return result


def main() -> int:
    # env so the REAL _EntailmentJudge constructs + points at the local wedge server
    os.environ.setdefault("PG_GENERATOR_MODEL", "deepseek/deepseek-v4-pro")
    os.environ.setdefault("PG_ENTAILMENT_MODEL", "z-ai/glm-5.1")  # diff family from generator
    os.environ["OPENROUTER_API_KEY"] = os.environ.get("OPENROUTER_API_KEY", "sk-repro-dummy")
    os.environ["PG_ENTAILMENT_TOTAL_S"] = str(TOTAL_S)
    os.environ.setdefault("PG_ENTAILMENT_TOTAL_DEADLINE_RETRIES", "1")  # the run-slate value
    os.environ.setdefault("PG_ENTAILMENT_RETRIES", "2")
    os.environ.setdefault("PG_ENTAILMENT_RETRY_BACKOFF_S", "0.2")

    srv = WedgeServer(MODE)
    srv.start()
    os.environ["OPENROUTER_BASE_URL"] = f"http://127.0.0.1:{srv.port}/api/v1"
    _log(f"wedge server up on 127.0.0.1:{srv.port} mode={MODE}; TOTAL_S={TOTAL_S} WALL_S={WALL_S}")

    # import AFTER env is set (module reads PG_ENTAILMENT_TOTAL_S at import)
    import importlib
    ej = importlib.import_module("src.polaris_graph.llm.entailment_judge")
    importlib.reload(ej)  # ensure _ENTAILMENT_TOTAL_S picks up our TOTAL_S
    _log(f"module _ENTAILMENT_TOTAL_S = {ej._ENTAILMENT_TOTAL_S} (must equal {TOTAL_S})")

    judge = ej._EntailmentJudge()
    headers = {"Authorization": f"Bearer {judge._api_key}", "Content-Type": "application/json"}
    body = {"model": judge._model, "messages": [{"role": "user", "content": "x"}]}

    results = []
    _log("PROBE P1: _post_with_total_deadline direct (does result(timeout) + close() bound?)")
    results.append(_run_probe(
        "P1_post_with_total_deadline",
        lambda: ej._post_with_total_deadline(judge._client, judge._endpoint, headers, body, TOTAL_S),
    ))

    _log("PROBE P2: full judge.judge() (does the retry/rebuild/sentinel path bound?)")
    results.append(_run_probe(
        "P2_judge_full",
        lambda: judge.judge("A sentence to verify.", "A source span of text."),
    ))

    _log("PROBE P3: SECOND judge.judge() (cross-call client poisoning / leaked-worker block?)")
    results.append(_run_probe(
        "P3_judge_second",
        lambda: judge.judge("Another sentence.", "Another span."),
    ))

    srv.close()

    print("\n==================== DISCRIMINATION ====================", flush=True)
    for r in results:
        print(f"  {r['name']:28s} bounded={r['bounded']!s:5s} elapsed={r['elapsed']:.1f}s "
              f"-> {r['outcome']}", flush=True)
    p1, p2, p3 = results
    if not p1["bounded"]:
        verdict = "HYP (a)/(c): _post_with_total_deadline itself does NOT bound (result()/close() hang)"
    elif not p2["bounded"]:
        verdict = "HYP (b): single call's retry/rebuild/close path hangs (deadline fires, recovery does not)"
    elif not p3["bounded"]:
        verdict = "HYP (c): cross-call client poisoning / leaked wedged worker blocks the NEXT call"
    else:
        verdict = "ALL BOUNDED — fix verified (or repro did not reproduce the wedge)"
    print(f"\n  VERDICT: {verdict}", flush=True)
    print("========================================================", flush=True)

    all_bounded = all(r["bounded"] for r in results)
    return 0 if all_bounded else 3  # FAIL-LOUD non-zero if any probe was unbounded


if __name__ == "__main__":
    sys.exit(main())
