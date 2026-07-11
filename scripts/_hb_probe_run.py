"""Heartbeat + phase-2 concurrency probe for the compose off-loop fix.

Runs the REAL run_s5_i3.main() compose path on a SMALL selection (2 sections,
cap-primary 1) with:
  (1) an event-loop heartbeat coroutine measuring MAX loop-gap (freeze detector),
  (2) a monkeypatch around the AUTHORITATIVE _compose_section_per_basket that
      counts CONCURRENT phase-2 (max overlap) + logs thread ident (proves off-loop).

Mode is chosen by env HB_MODE:
  HB_MODE=offloop  -> real code (asyncio.to_thread wrap active)   [TREATMENT]
  HB_MODE=onloop   -> asyncio.to_thread patched to INLINE-sync    [CONTROL / pre-fix]

Does NOT edit any production file.
"""
import asyncio
import os
import sys
import threading
import time
import types

# --- probe state ---
_phase2_lock = threading.Lock()
_phase2_active = 0
_phase2_max = 0
_phase2_calls = 0
_phase2_threads = set()
_main_thread_ident = threading.get_ident()

_hb_max_gap = 0.0
_hb_last = None
_hb_samples = 0


def _wrap_compose(orig):
    def _wrapped(*a, **k):
        global _phase2_active, _phase2_max, _phase2_calls
        with _phase2_lock:
            _phase2_active += 1
            _phase2_calls += 1
            _phase2_max = max(_phase2_max, _phase2_active)
            cur = _phase2_active
            _phase2_threads.add(threading.get_ident())
        off = threading.get_ident() != _main_thread_ident
        print(f"[PHASE2 ENTER] concurrent={cur} off_loop_thread={off} "
              f"tid={threading.get_ident()} t={time.monotonic():.2f}", flush=True)
        t0 = time.monotonic()
        try:
            return orig(*a, **k)
        finally:
            dt = time.monotonic() - t0
            with _phase2_lock:
                _phase2_active -= 1
                cur2 = _phase2_active
            print(f"[PHASE2 EXIT] dt={dt:.1f}s remaining_concurrent={cur2} "
                  f"t={time.monotonic():.2f}", flush=True)
    return _wrapped


async def _heartbeat():
    global _hb_max_gap, _hb_last, _hb_samples
    _hb_last = time.monotonic()
    while True:
        await asyncio.sleep(0.25)
        now = time.monotonic()
        gap = now - _hb_last
        _hb_last = now
        _hb_samples += 1
        if gap > _hb_max_gap:
            _hb_max_gap = gap
        if gap > 2.0:
            print(f"[HB FREEZE] loop_gap={gap:.1f}s t={now:.2f}", flush=True)


async def _driver(main_coro_fn):
    hb = asyncio.create_task(_heartbeat())
    try:
        await main_coro_fn()
    finally:
        hb.cancel()


def main():
    mode = os.environ.get("HB_MODE", "offloop")

    # import AFTER env is set by the launcher wrapper
    import scripts.run_s5_i3 as runmod
    from src.polaris_graph.generator import multi_section_generator as msg

    # patch the authoritative compose entry (bound name in multi_section_generator)
    orig = msg._compose_section_per_basket
    msg._compose_section_per_basket = _wrap_compose(orig)

    # stage timers: log wall-time of on-loop candidate hot spots so any residual
    # freeze can be localized against the [HB FREEZE] timestamps.
    def _time_stage(name, fn, is_async):
        if is_async:
            async def _aw(*a, **k):
                t = time.monotonic()
                try:
                    return await fn(*a, **k)
                finally:
                    print(f"[STAGE {name}] dt={time.monotonic()-t:.1f}s "
                          f"tid={threading.get_ident()} t={time.monotonic():.2f}", flush=True)
            return _aw
        def _sy(*a, **k):
            t = time.monotonic()
            try:
                return fn(*a, **k)
            finally:
                print(f"[STAGE {name}] dt={time.monotonic()-t:.1f}s "
                      f"tid={threading.get_ident()} t={time.monotonic():.2f}", flush=True)
        return _sy

    msg._rewrite_draft_with_spans = _time_stage(
        "rewrite_spans", msg._rewrite_draft_with_spans, False)
    msg._repair_untokened_draft = _time_stage(
        "repair_untokened", msg._repair_untokened_draft, False)
    import src.polaris_graph.generator.sentence_repair as _sr
    _sr.repair_dropped_section_sentences = _time_stage(
        "repair_dropped", _sr.repair_dropped_section_sentences, True)
    import src.polaris_graph.generator.section_polish as _sp
    _sp.coherence_rewrite_section = _time_stage(
        "coherence", _sp.coherence_rewrite_section, True)
    # rebind the name imported into multi_section_generator (imported inside _run_section, so
    # patch the source module — the local import will pick up the patched attr)

    if mode == "onloop":
        # CONTROL: reproduce the PRE-FIX world — asyncio.to_thread runs inline on the loop.
        _orig_to_thread = asyncio.to_thread
        async def _inline_to_thread(fn, *a, **k):
            return fn(*a, **k)
        asyncio.to_thread = _inline_to_thread
        print("[PROBE] MODE=onloop (CONTROL): asyncio.to_thread patched to INLINE-sync", flush=True)
    else:
        print("[PROBE] MODE=offloop (TREATMENT): real asyncio.to_thread wrap active", flush=True)

    t0 = time.monotonic()
    asyncio.run(_driver(runmod.main))
    wall = time.monotonic() - t0

    print("\n================ PROBE SUMMARY ================", flush=True)
    print(f"mode                    = {mode}", flush=True)
    print(f"wall_s                  = {wall:.1f}", flush=True)
    print(f"phase2_calls            = {_phase2_calls}", flush=True)
    print(f"phase2_max_concurrent   = {_phase2_max}", flush=True)
    print(f"phase2_worker_threads   = {len(_phase2_threads)} (main={_main_thread_ident})", flush=True)
    print(f"hb_max_loop_gap_s       = {_hb_max_gap:.2f}", flush=True)
    print(f"hb_samples              = {_hb_samples}", flush=True)
    print("==============================================", flush=True)


if __name__ == "__main__":
    main()
