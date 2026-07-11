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
import hashlib
import os
import pickle
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

# --- basket-level (intra-section) concurrency probe: measures the STEP-1 map-then-reduce achieved
# concurrency (how many baskets compose SIMULTANEOUSLY), the metric the section-level phase2 counter
# above cannot see. Each concurrent basket carries its own writer_fn + verify_fn network call in flight,
# so max concurrent baskets is the real provider-facing "compose concurrency" the mission targets. ---
_basket_lock = threading.Lock()
_basket_active = 0
_basket_max = 0
_basket_calls = 0
_basket_threads = set()


def _wrap_basket(orig):
    def _wrapped(*a, **k):
        global _basket_active, _basket_max, _basket_calls
        with _basket_lock:
            _basket_active += 1
            _basket_calls += 1
            _basket_max = max(_basket_max, _basket_active)
            cur = _basket_active
            _basket_threads.add(threading.get_ident())
        if cur > 1:
            print(f"[BASKET CONC] concurrent={cur} tid={threading.get_ident()} "
                  f"t={time.monotonic():.2f}", flush=True)
        try:
            return orig(*a, **k)
        finally:
            with _basket_lock:
                _basket_active -= 1
    return _wrapped


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


# ─────────────────────────── record / replay A/B shim ───────────────────────────
# Certifies kept/dropped verdict-set IDENTITY between a SERIAL control and the CONCURRENT
# treatment at ZERO LLM cost. One RECORD pass captures every NLI-judge (verdict,reason) and
# every writer draft keyed by a CONTENT hash; two REPLAY passes (control=serial, treatment=
# PG_MAX_PARALLEL_SECTIONS=2, real threads) return those SAME answers deterministically.
#
# The judge is a PURE function of (sentence, span) and the writer of (members, revise_reasons,
# group_mode, section_context) — so a content-keyed lookup returning the FIRST recorded value is
# reorder-invariant and thread-safe (no per-call position counter that could race). Consequently
# ANY difference between the serial and concurrent kept/dropped set is a GENUINE shared-state race
# in the compose/verify path the off-loop fix newly runs on worker threads — exactly the one risk
# structural transparency does not cover. Env: HB_REPLAY_MODE=record|replay, HB_REPLAY_FILE=<pkl>,
# HB_INLINE_TO_THREAD=1 (serial control), PG_MAX_PARALLEL_SECTIONS.


def _writer_key(members, kw) -> str:
    parts = []
    for m in (members or []):
        parts.append(f"{getattr(m, 'evidence_id', '')}\x1f{getattr(m, 'direct_quote', '')}")
    rr = kw.get("revise_reasons") or []
    sc = kw.get("section_context") or {}
    payload = (
        "\x01".join(parts)
        + "\x02" + "\x01".join(str(x) for x in rr)
        + "\x02" + str(kw.get("group_mode"))
        + "\x02" + str(sorted((str(k), str(v)) for k, v in sc.items()))
    )
    return hashlib.sha256(payload.encode("utf-8", "surrogatepass")).hexdigest()


def _judge_key(sentence, span) -> str:
    return hashlib.sha256(
        (str(sentence) + "\x00" + str(span)).encode("utf-8", "surrogatepass")
    ).hexdigest()


_RR_LOCK = threading.Lock()
_RR_STATS = {"judge_calls": 0, "judge_miss": 0, "judge_divergent_keys": 0,
             "writer_calls": 0, "writer_miss": 0}


def _install_record_replay():
    """Patch the two LLM boundaries (_EntailmentJudge.judge, abstractive_writer._call_writer)
    for record or replay. Returns nothing; state persisted via atexit on record."""
    mode = os.environ["HB_REPLAY_MODE"]
    store_path = os.environ["HB_REPLAY_FILE"]
    from src.polaris_graph.llm import entailment_judge as ej
    from src.polaris_graph.generator import abstractive_writer as aw

    if mode == "record":
        judge_store: dict = {}
        writer_store: dict = {}
        orig_judge = ej._EntailmentJudge.judge
        orig_writer = aw._call_writer

        def _rec_judge(self, sentence, span):
            r = orig_judge(self, sentence, span)
            k = _judge_key(sentence, span)
            with _RR_LOCK:
                seq = judge_store.setdefault(k, [])
                if seq and seq[0] != tuple(r):
                    _RR_STATS["judge_divergent_keys"] += 1
                seq.append(tuple(r))
            return r

        async def _rec_writer(members, evidence_pool, **kw):
            d = await orig_writer(members, evidence_pool, **kw)
            k = _writer_key(members, kw)
            with _RR_LOCK:
                writer_store.setdefault(k, []).append(d)
            return d

        ej._EntailmentJudge.judge = _rec_judge
        aw._call_writer = _rec_writer

        import atexit

        def _dump():
            with open(store_path, "wb") as f:
                pickle.dump({"judge": judge_store, "writer": writer_store}, f)
            print(f"[RR record] dumped judge_keys={len(judge_store)} "
                  f"writer_keys={len(writer_store)} divergent_judge_keys="
                  f"{_RR_STATS['judge_divergent_keys']} -> {store_path}", flush=True)

        atexit.register(_dump)
        print(f"[RR record] installed (real LLM) -> {store_path}", flush=True)
    else:  # replay — return the FIRST recorded value per content key (deterministic, race-free)
        with open(store_path, "rb") as f:
            data = pickle.load(f)
        judge_store = data["judge"]
        writer_store = data["writer"]

        def _rep_judge(self, sentence, span):
            k = _judge_key(sentence, span)
            with _RR_LOCK:
                _RR_STATS["judge_calls"] += 1
                seq = judge_store.get(k)
                if not seq:
                    _RR_STATS["judge_miss"] += 1
            # deterministic fallback on an unseen content (should be 0 if replay==record inputs)
            return tuple(seq[0]) if seq else ("NEUTRAL", "replay_miss")

        async def _rep_writer(members, evidence_pool, **kw):
            k = _writer_key(members, kw)
            with _RR_LOCK:
                _RR_STATS["writer_calls"] += 1
                seq = writer_store.get(k)
                if not seq:
                    _RR_STATS["writer_miss"] += 1
            return seq[0] if seq else ""

        ej._EntailmentJudge.judge = _rep_judge
        aw._call_writer = _rep_writer
        print(f"[RR replay] installed (ZERO LLM) judge_keys={len(judge_store)} "
              f"writer_keys={len(writer_store)} from {store_path}", flush=True)


def _replay_main():
    """Record or replay run_s5_i3.main() with the LLM boundaries shimmed. In replay+control mode
    (HB_INLINE_TO_THREAD=1) asyncio.to_thread runs inline so compose is SERIAL on the loop."""
    import scripts.run_s5_i3 as runmod

    _install_record_replay()

    if os.environ.get("HB_INLINE_TO_THREAD", "0") == "1":
        async def _inline_to_thread(fn, *a, **k):
            return fn(*a, **k)
        asyncio.to_thread = _inline_to_thread
        print("[RR] asyncio.to_thread INLINED (serial control arm)", flush=True)

    t0 = time.monotonic()
    asyncio.run(runmod.main())
    print(f"[RR] run complete wall={time.monotonic()-t0:.1f}s stats={_RR_STATS}", flush=True)


def main():
    if os.environ.get("HB_REPLAY_MODE"):
        _replay_main()
        return
    mode = os.environ.get("HB_MODE", "offloop")

    # import AFTER env is set by the launcher wrapper
    import scripts.run_s5_i3 as runmod
    from src.polaris_graph.generator import multi_section_generator as msg

    # patch the authoritative compose entry (bound name in multi_section_generator)
    orig = msg._compose_section_per_basket
    msg._compose_section_per_basket = _wrap_compose(orig)

    # basket-level (intra-section) concurrency: wrap the three per-basket producers the STEP-1 MAP calls
    # so we measure how many baskets compose SIMULTANEOUSLY (the achieved compose concurrency the mission
    # targets). Patch the SOURCE module (verified_compose) so the map's calls pick up the wrap.
    from src.polaris_graph.generator import verified_compose as _vc
    _vc._compose_one_basket = _wrap_basket(_vc._compose_one_basket)
    _vc.compose_basket_multicited_sentence = _wrap_basket(_vc.compose_basket_multicited_sentence)
    _vc.compose_basket_multicited_synth_primary = _wrap_basket(_vc.compose_basket_multicited_synth_primary)

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
    print(f"basket_calls            = {_basket_calls}", flush=True)
    print(f"basket_max_concurrent   = {_basket_max}", flush=True)
    print(f"basket_worker_threads   = {len(_basket_threads)}", flush=True)
    print(f"hb_max_loop_gap_s       = {_hb_max_gap:.2f}", flush=True)
    print(f"hb_samples              = {_hb_samples}", flush=True)
    print("==============================================", flush=True)


if __name__ == "__main__":
    main()
