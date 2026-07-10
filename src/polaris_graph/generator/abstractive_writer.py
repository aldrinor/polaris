"""I-beatboth-005 (#1282) — the FAITHFUL ABSTRACTIVE WRITER for per-basket verified-compose.

Replaces the deterministic ``build_short_member_sentence`` render-probe stub (verified_compose.py)
that ships SPAN-FAITHFUL but BROKEN prose (dangling markdown-link fragments, orphaned section
numbers, HR/Reddit chrome) with an LLM writer that rephrases each verified span into CLEAN plain
declarative news-style prose carrying the EXACT canonical provenance token + every span numeric
verbatim. Each rewritten sentence is RE-RUN through the UNCHANGED ``verify_sentence_provenance``
(+ the existing region gate) by the unchanged ``_compose_one_basket`` loop; on FAIL the loop falls
back to today's verbatim K-span. Default-OFF behind ``PG_ABSTRACTIVE_WRITER``; byte-identical OFF.

ARCHITECTURE (design §3, ABSTRACTIVE_WRITER_DESIGN.md):
  * The writer is async (OpenRouter) but ``_compose_one_basket`` calls ``writer_fn`` SYNCHRONOUSLY.
    An async PRE-PASS (:func:`abstractive_pre_pass`) precomputes one verified draft per basket up
    front (LLM + bounded retry, bounded-parallel); the sync ``writer_fn``
    (:func:`make_abstractive_writer_fn`) is a pure dict lookup keyed by the basket's canonical id.
  * The writer-specific verify wrapper (:func:`make_writer_verify_fn`) is STRICTER than the K-span
    path — the four P1 closures, all in the wrapper / pre-pass, ENGINE UNTOUCHED:
      - P1-1: a TRANSPORT entailment ``judge_error`` is a WRITER FAILURE (the wrapper forces
        ``is_verified=False`` -> retry -> K-span). An advisory judge-error never ships as a
        paraphrase, only ever as the grounded-by-construction K-span.
      - P1-2: the wrapper verifies with ``allow_local_window_fallback=False`` (the K-span path keeps
        the ``True`` default via the unwrapped ``verify_fn``); a NEUTRAL/CONTRADICTED bound span
        cannot pass on a same-row local window.
      - P1-3: a numeric COMPLETENESS guard (span->sentence) — every substantive span numeric must
        appear verbatim in the rewrite, else ``is_verified=False`` -> retry -> K-span. The
        guard reuses the ENGINE'S OWN substantive-numeral definition (``_decimals_in`` /
        ``_numbers_in`` / ``_INTEGER_PERCENT_RE`` / ``_strip_dose_patterns``), so "substantive"
        means the same thing in both directions; it lives HERE, never in ``verify_sentence_provenance``.
      - P1-4: the async/sync adapter above.
  * Fail-closed activation (design §3.6 / §5.5): the writer REFUSES to activate (raises, fail-LOUD,
    LAW II) unless ``PG_STRICT_VERIFY_ENTAILMENT`` resolves to ``enforce`` — the writer's only
    semantic guarantee for a paraphrase IS the entailment leg. The env guard is the ACTIVATION
    precondition; the per-call ``judge_error`` demotion (P1-1) is the call-time enforcement.

FAITHFULNESS: ``verify_sentence_provenance`` / NLI / 4-role D8 / provenance / ``build_verified_span_draft``
/ ``_compose_one_basket`` / ``_compose_section_per_basket`` / the region gate are UNTOUCHED. Every
abstractive rewrite is re-run through the unchanged verifier + region gate; fabrication degrades to
the verbatim K-span. Always-release; never strand; never empty.
"""
from __future__ import annotations

import asyncio
import dataclasses
import logging
import math
import os
import re
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# Provenance token shape (``[#ev:<id>:<a>-<b>]``) — stripped before the anti-verbatim check so the
# token itself never counts as shared content between a sentence and its cited span.
_EV_TOKEN_RE = re.compile(r"\[#ev:[^\]]*\]")
# Content-word tokenizer (Unicode letters/digits, underscore excluded) for the anti-verbatim run.
_CONTENT_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)

# ── env knobs (LAW VI — all parameters env-configurable; defaults documented) ────────────────────
_ENV_ENABLE = "PG_ABSTRACTIVE_WRITER"
# Model: the writer is a GENERATOR-role call (design §5.6 / §9.1.8). The campaign generator arm =
# z-ai/glm-5.2 (config/architecture/polaris_runtime_lock.yaml generator.model_slug), which is also
# the operator-specified default for #1282. Resolves to the GENERATOR-role slug at call time so it
# tracks the lock (and the campaign's all-GLM-5.2 override) rather than hardcoding a value that
# could drift from the lock; env-overridable per LAW VI.
_ENV_MODEL = "PG_ABSTRACTIVE_WRITER_MODEL"
_DEFAULT_MODEL = "z-ai/glm-5.2"
_ENV_MAX_RETRIES = "PG_ABSTRACTIVE_WRITER_MAX_RETRIES"
_DEFAULT_MAX_RETRIES = 1                       # 2 total attempts (design §5.2)
_ENV_MAX_TOKENS = "PG_ABSTRACTIVE_WRITER_MAX_TOKENS"
# §9.1.8 "never starve": 2048 STARVED the writer. GLM-5.2 reaches the _ALWAYS_REASON branch
# (openrouter_client.py:1778), which (a) floors max_tokens at PG_GLM5_MIN_MAX_TOKENS=4096 and (b)
# burns a real reasoning budget BEFORE content — so a 2048 cap is bumped to 4096 then largely
# consumed by reasoning, truncating the rephrase on a many-span basket -> empty/degraded synthesis.
# OpenRouter /api/v1/models reports z-ai/glm-5.2 top_provider.max_completion_tokens=32768
# (context_length 1,048,576), verified 2026-06-25. Per §9.1.8 ("reasoning effort + max_tokens ALWAYS
# go MAX", "set max_tokens to the model's REAL OpenRouter limit") the default is the FULL 32768 provider
# cap: ~8x headroom over the 4096 GLM floor, so GLM's reasoning budget can run high WITHOUT truncating
# the content rephrase on a many-span basket. max_tokens is a CAP not a target (billed by actual usage),
# so the generous ceiling is free insurance — never starve the writer.
_DEFAULT_MAX_TOKENS = 32768
_ENV_REASONING_MAX_TOKENS = "PG_ABSTRACTIVE_WRITER_REASONING_MAX_TOKENS"
# I-wire-009 (#1323) SUPERSEDES the prior I-wire-005 effort=high posture for this leg. The
# floor_abstractive writer is the LOCKED active composer and reaches the GLM-5.2 _ALWAYS_REASON
# branch (openrouter_client.py:1778). The I-wire-005 assumption — that a generous 32768 content
# ceiling makes an UNCAPPED effort=high reasoning pool safe — is exactly what this issue disproves:
# at the outline leg GLM-5.2 spent the whole budget reasoning and returned content="" regardless of
# the ceiling. So BOUND the reasoning pool by default (a fixed reasoning_max_tokens is mutually
# exclusive with effort on the GLM branch, openrouter_client.py:1784-1788 — the cap deliberately
# suppresses effort=high here). 16384 matches the analyst-synthesis + legacy-section siblings: a
# generous reasoning slice that still leaves the bulk of the 32768 ceiling for the content rephrase.
# LAW VI: an operator may restore the uncapped effort=high posture for a NON-reasoning-first model
# by setting PG_ABSTRACTIVE_WRITER_REASONING_MAX_TOKENS<=0 (the <=0 -> None escape hatch below).
_DEFAULT_REASONING_MAX_TOKENS = 16384          # I-wire-009: bounded by default; <=0 via env => effort=high
_ENV_CONCURRENCY = "PG_ABSTRACTIVE_WRITER_CONCURRENCY"
_DEFAULT_CONCURRENCY = 8                       # bounded fan-out (§3.5), matches campaign verify fan-out
_ENV_TEMPERATURE = "PG_ABSTRACTIVE_WRITER_TEMPERATURE"
_DEFAULT_TEMPERATURE = 0.2                     # low — faithful rephrase, not creative
_ENV_CALL_DEADLINE_S = "PG_ABSTRACTIVE_WRITER_CALL_DEADLINE_S"
_DEFAULT_CALL_DEADLINE_S = 120.0               # per-call total deadline -> force-close to K-span (§3.5)
# OUTER wall-deadline on the WHOLE pre-pass (I-arch-007 wall+abandon pattern, async-native form).
# The per-call deadline (above) bounds ONE call; under a provider connection/429 storm the bounded pool
# of N calls + their retry backoffs can still balloon the pre-pass wall-clock with NO outer bound, and
# an asyncio.wait_for cancellation that stalls in httpx client teardown (the proven hang class) would
# wedge asyncio.gather forever. The pre-pass therefore runs the basket tasks under asyncio.wait(timeout)
# and ABANDONS (never awaits) any still-pending task at the wall -> those baskets are simply absent from
# the precomputed dict -> the unchanged compose loop K-span-falls-back (always-release, disclosed,
# fail-OPEN). Sized comfortably above the legit worst case (a healthy basket = (max_retries+1) *
# call_deadline ~= 240s; observed real waves ran ~180-200s) so HEALTHY baskets are never abandoned.
_ENV_WALL_DEADLINE_S = "PG_ABSTRACTIVE_WRITER_WALL_DEADLINE_S"
# Sized to NOT abandon HEALTHY baskets under uniform provider slowness. Worst-case makespan =
# ceil(n_baskets / concurrency) waves * (max_retries+1) attempts * call_deadline. At the default
# 23 baskets / 8 concurrency / 1 retry / 120s call = ceil(23/8)=3 waves * 2 * 120 = 720s. The wall is
# set to that worst case so a uniformly-slow-but-eventually-healthy run completes rather than abandons
# its last wave; observed real waves ran ~180-200s, so the wall only ever bites a genuinely stuck call.
_DEFAULT_WALL_DEADLINE_S = 720.0               # outer wall -> abandon stuck baskets to K-span (never infinite)

# ── I-deepfix-001 B3/B4 (#1370): writer throughput + transport-resilience knobs (all DEFAULT-OFF) ──
# B4 root cause: the flat 720s wall was sized in-code for 23 baskets @ concurrency 8 (the makespan note
# above). drb_72 sections carry 71-113 baskets, so under a provider slowdown the wall exhausts and
# ABANDONS the whole still-pending wave to K-span (19/104, 14/86, 9/113 drafted). The fixes are all
# THROUGHPUT / RESILIENCE mechanisms, NEVER a blind time-wall raise:
#   * PG_WRITER_WALL_BASKET_SCALED — size the wall from the code's OWN makespan formula on the ACTUAL
#     basket count (not the frozen 23-basket budget). max(flat, scaled) so it only ever scales UP for
#     big sections and never shrinks below the proven-safe flat baseline. DEFAULT OFF => flat 720s.
#   * PG_WRITER_KSPAN_RECOVERY_PASS — after the wall bites, run ONE bounded second pass over the still-
#     undrafted baskets before dumping them to K-span. DEFAULT OFF => the legacy immediate-abandon path.
#   * PG_WRITER_DEADLINE_TRANSPORT_AWARE — (a) _call_writer catches the httpx transport-disconnect family
#     (ConnectTimeout/ConnectError/RemoteProtocolError/ReadError) into a clean K-span so a raw
#     ConnectTimeout never escapes as an unretrieved-task leak; (b) a per-call transport stall does NOT
#     consume a PRODUCTIVE retry attempt (reconnect/stall time is not charged — a bounded set of fresh
#     reconnect windows is granted); (c) the outer wall gets one bounded reconnect-window of headroom.
#     DEFAULT OFF => byte-identical (no catch, single hard per-call deadline, no wall headroom).
# The bounded concurrency raise is B4's fourth lever but is an ENV-VALUE change only
# (PG_ABSTRACTIVE_WRITER_CONCURRENCY, already wired at _DEFAULT_CONCURRENCY / line ~640) — the box runs
# verify at 30, so the relaunch sets 24. No code default changes here (§-1.3: no hardcoded target).
_ENV_WALL_BASKET_SCALED = "PG_WRITER_WALL_BASKET_SCALED"
_ENV_KSPAN_RECOVERY_PASS = "PG_WRITER_KSPAN_RECOVERY_PASS"
_ENV_DEADLINE_TRANSPORT_AWARE = "PG_WRITER_DEADLINE_TRANSPORT_AWARE"

# ── P0-1(d) ANTI-VERBATIM gate (2026-07-10 compose gear-loop) ──────────────────────────────────────
# The LLM writer must SYNTHESIZE in its own words, never copy a raw span. A lazy GLM draft that pastes
# a span verbatim self-entails its own span and passes strict_verify trivially (quote-dump). FAIL any
# writer sentence that shares a contiguous run of >= this many CONTENT WORDS verbatim with its cited
# span, feeding the "verbatim_copy" reason back into the existing repair loop. General + question-
# agnostic (a form/structure test, no topic list). Numbers-only and short quoted phrases are exempt by
# the run-length floor (a lone figure or a <8-word phrase never reaches the threshold). Env-tunable.
_ENV_VERBATIM_COPY_MAX_RUN = "PG_WRITER_VERBATIM_COPY_MAX_CONTENT_WORDS"
_DEFAULT_VERBATIM_COPY_MAX_RUN = 8

# Sentinel returned by _call_writer when (and only when) the transport-aware catch swallows an httpx
# disconnect — a value that can NEVER appear in real model content, so _pre_pass_one_basket can tell a
# transport disconnect apart from a genuine empty completion and never leak it into a draft.
_WRITER_TRANSPORT_DISCONNECT = "\x00__polaris_writer_transport_disconnect__\x00"


def _flag_enabled(name: str) -> bool:
    """Generic DEFAULT-OFF env flag (same falsey vocabulary as ``_abstractive_writer_enabled``)."""
    return os.getenv(name, "0").strip().lower() not in ("", "0", "false", "off", "no")


def _wall_basket_scaled_enabled() -> bool:
    return _flag_enabled(_ENV_WALL_BASKET_SCALED)


def _kspan_recovery_pass_enabled() -> bool:
    return _flag_enabled(_ENV_KSPAN_RECOVERY_PASS)


def _deadline_transport_aware_enabled() -> bool:
    return _flag_enabled(_ENV_DEADLINE_TRANSPORT_AWARE)


def _makespan_wall_seconds(
    n_baskets: int, concurrency: int, max_retries: int, call_deadline_s: float,
) -> float:
    """The code's OWN worst-case makespan for the pre-pass (design note at lines ~102-107):
    ``ceil(n_baskets / concurrency)`` waves * ``(max_retries + 1)`` attempts * ``call_deadline_s``.

    Invariant proof (the frozen flat default): (23, 8, 1, 120.0) => ceil(23/8)=3 waves * 2 * 120 = 720.0,
    exactly ``_DEFAULT_WALL_DEADLINE_S`` — so the scaled wall is a generalization of the flat budget to
    the ACTUAL basket count, never an arbitrary raise. n_baskets<=0 => 0.0 (caller floors it)."""
    if n_baskets <= 0:
        return 0.0
    concurrency = max(1, concurrency)
    waves = math.ceil(n_baskets / concurrency)
    return float(waves) * float(max_retries + 1) * float(call_deadline_s)


# ── teardown-drain mechanism (I-wire-001 W6 #1314) ────────────────────────────────────────────────
# PROVEN pattern ported VERBATIM-IN-STRUCTURE from src/tools/access_bypass.py:1861-2026 (I-cd-032
# #632). A bare ``t.cancel()`` on a still-pending basket task is INSUFFICIENT: a task wedged inside
# httpx client teardown — or any task that swallows ``CancelledError`` and re-blocks — IGNORES the
# cancel and stays pending. ``asyncio.run``'s built-in shutdown then calls ``_cancel_all_tasks`` which
# ``gather``-awaits EVERY still-pending task BEFORE ``loop.close()`` — so one uncancellable task hangs
# the whole process at shutdown. Mitigation (mirrors access_bypass exactly): at the wall we (a) register
# each abandoned task in a module-level detached set, (b) ``cancel()`` it best-effort, then (c)
# FORCE-CLOSE its underlying coroutine via ``_coro.close()`` (raises GeneratorExit -> finally/except
# blocks run synchronously, no new await is possible, the task is finalized as ``done()``). A finalized
# task is excluded from ``_cancel_all_tasks``'s await-list, so shutdown completes. Belt-and-suspenders:
# :func:`install_teardown_drain_hook` ALSO patches the loop's ``_cancel_all_tasks`` phase so an
# UNTRACKED wedged task (not in the detached set) is force-closed before it is awaited. Faithfulness
# engine UNTOUCHED — this is purely a process-teardown safety net on the abandon (fail-open) path.
_DETACHED_WRITER_TASKS: "set[asyncio.Task]" = set()


def _drain_detached_writer_task(task: "asyncio.Task") -> None:
    """Done-callback for a detached basket task: drop the strong ref and retrieve any exception so
    asyncio does not log 'exception never retrieved'. Mirrors access_bypass._drain_detached."""
    _DETACHED_WRITER_TASKS.discard(task)
    if not task.cancelled():
        try:
            task.exception()
        except Exception:  # noqa: BLE001 — exception retrieval is best-effort
            pass


def _force_drop_detached_writer_task(task: "asyncio.Task") -> None:
    """Forcibly finalize a wedged detached basket task so ``asyncio.run``'s ``_cancel_all_tasks``
    cannot await it. Closes the task's underlying coroutine via ``_coro.close()`` — that raises
    GeneratorExit into the coroutine's current suspension point, runs any finally/except blocks
    SYNCHRONOUSLY (GeneratorExit suppresses new yields, so the frame cannot re-block), and finalizes
    the task as cancelled/done. Best-effort: if ``_coro`` is absent the strong ref is simply dropped.
    Mirrors access_bypass._force_drop_detached_task (I-cd-032 #632)."""
    if task.done():
        _DETACHED_WRITER_TASKS.discard(task)
        return
    coro = getattr(task, "_coro", None)
    if coro is None:
        _DETACHED_WRITER_TASKS.discard(task)
        return
    try:
        coro.close()
    except Exception:  # noqa: BLE001 — close() must never raise here
        pass
    _DETACHED_WRITER_TASKS.discard(task)


def install_teardown_drain_hook(loop: "asyncio.AbstractEventLoop") -> None:
    """Belt-and-suspenders teardown guard. ``asyncio.run`` calls the loop's ``_cancel_all_tasks``
    phase (which ``gather``-awaits every pending task) BEFORE ``loop.close()``, so an UNTRACKED wedged
    task — one not in :data:`_DETACHED_WRITER_TASKS` — would still hang shutdown. This patches
    ``loop.close`` to first force-close every still-tracked detached task; the primary defense remains
    the abandon-time force-close in :func:`abstractive_pre_pass`, which finalizes tracked tasks before
    ``_cancel_all_tasks`` ever runs. Idempotent. Mirrors access_bypass.install_teardown_drain_hook."""
    if getattr(loop, "_polaris_writer_drain_installed", False):
        return
    original_close = loop.close

    def _drain_then_close() -> None:
        for task in list(_DETACHED_WRITER_TASKS):
            _force_drop_detached_writer_task(task)
        original_close()

    loop.close = _drain_then_close  # type: ignore[method-assign]
    try:
        loop._polaris_writer_drain_installed = True  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 — marker is best-effort
        pass


def _abstractive_writer_enabled() -> bool:
    """``PG_ABSTRACTIVE_WRITER`` gate. DEFAULT-OFF => the caller keeps the deterministic
    ``build_short_member_sentence`` stub + bare ``_vc_verify`` byte-identical; ON => the LLM
    abstractive writer is the per-basket prose producer (behind the fail-closed activation guard)."""
    return os.getenv(_ENV_ENABLE, "0").strip().lower() not in ("", "0", "false", "off", "no")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("[abstractive_writer] %s=%r not an int; using default %d", name, raw, default)
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("[abstractive_writer] %s=%r not a float; using default %s", name, raw, default)
        return default


def _resolve_model() -> str:
    """The writer model. ``PG_ABSTRACTIVE_WRITER_MODEL`` overrides; else the GENERATOR-role slug
    (``PG_GENERATOR_MODEL``, which the lock pins to the campaign generator arm), falling back to the
    operator-specified ``z-ai/glm-5.2`` default if the generator knob is unset. The writer is a
    generator-role call (§9.1.8) so it tracks the lock rather than hardcoding a slug that could drift."""
    override = os.getenv(_ENV_MODEL, "").strip()
    if override:
        return override
    gen = os.getenv("PG_GENERATOR_MODEL", "").strip()
    return gen or _DEFAULT_MODEL


def _basket_key(basket: Any) -> str:
    """A STABLE per-basket key for the precomputed-draft dict — the basket's canonical
    ``claim_cluster_id`` (credibility_pass.ClaimBasket). Empty/missing => "" (the sync writer_fn
    treats a missing key as a writer-empty basket -> K-span fallback, never a crash)."""
    return str(getattr(basket, "claim_cluster_id", "") or "")


# ── P1-3 numeric COMPLETENESS guard helpers (reuse the ENGINE'S substantive-numeral definition) ──
def _substantive_span_numerics(span_text: str) -> set[str]:
    """The set of SUBSTANTIVE numerals in a span, using the ENGINE'S OWN definition so "substantive"
    means the same thing in both directions (design §3.2c): every decimal (``_decimals_in`` over
    dose-stripped text) PLUS every percent-expressed integer (``_INTEGER_PERCENT_RE``). Structural /
    study-marker integers (``STEP 1``, ``week 68``, ``104 weeks``, ``phase 3``) are NOT substantive
    — the engine's sentence->span numeric check exempts them via ``_DECIMAL_NUMBER_RE``, so the
    reverse span->sentence guard must exempt them too (else it would demand study markers the engine
    itself ignores and force a universal K-span no-op)."""
    from src.polaris_graph.generator.provenance_generator import (  # noqa: PLC0415
        _INTEGER_PERCENT_RE,
        _decimals_in,
        _numbers_in,
        _strip_dose_patterns,
    )
    stripped = _strip_dose_patterns(span_text or "")
    decimals = _decimals_in(stripped)
    # Percent-expressed integers (e.g. "50%", "19 percent") ARE claimed values; capture them but
    # exclude any that are already decimals.
    pct_ints = {m.group(1) for m in _INTEGER_PERCENT_RE.finditer(stripped)} - decimals
    # Restrict pct_ints to genuine integers present as standalone numbers in the span (mirrors the
    # engine's claimed_pct_ints handling, which subtracts decimals and checks integer membership).
    span_numbers = _numbers_in(stripped)
    pct_ints = {n for n in pct_ints if n in span_numbers}
    return decimals | pct_ints


def _numeral_appears_verbatim(numeral: str, sentence: str) -> bool:
    """True iff ``numeral`` appears verbatim among the sentence's numbers (after the same
    dose-strip + unicode-minus normalization the engine applies), so e.g. "13.0" vs "13" is not a
    false match. Reuses ``_numbers_in`` so extraction matches the engine exactly."""
    from src.polaris_graph.generator.provenance_generator import (  # noqa: PLC0415
        _numbers_in,
        _strip_dose_patterns,
    )
    return numeral in _numbers_in(_strip_dose_patterns(sentence or ""))


def _verbatim_copy_max_run() -> int:
    """``PG_WRITER_VERBATIM_COPY_MAX_CONTENT_WORDS`` (default 8, clamp >= 2). The contiguous-content-word
    run length at/above which a writer sentence is judged a verbatim COPY of its cited span. A value < 2
    would flag trivial single-word overlaps, so it floors at 2."""
    raw = os.getenv(_ENV_VERBATIM_COPY_MAX_RUN, "").strip()
    if not raw:
        return _DEFAULT_VERBATIM_COPY_MAX_RUN
    try:
        return max(2, int(raw))
    except ValueError:
        return _DEFAULT_VERBATIM_COPY_MAX_RUN


def _content_word_sequence(text: str) -> list[str]:
    """The lowercased CONTENT-WORD token sequence of ``text`` with provenance tokens removed — the unit
    over which the anti-verbatim contiguous-run is measured. Pure."""
    stripped = _EV_TOKEN_RE.sub(" ", text or "")
    return [w.lower() for w in _CONTENT_WORD_RE.findall(stripped)]


def _max_contiguous_shared_run(a_words: list[str], b_words: list[str]) -> int:
    """Longest CONTIGUOUS run of content words appearing verbatim (in order) in BOTH sequences — a
    classic longest-common-substring over token lists (rolling DP, O(len_a * len_b)). Pure; used to
    detect a writer sentence that pasted a chunk of its cited span verbatim instead of synthesizing."""
    if not a_words or not b_words:
        return 0
    prev = [0] * (len(b_words) + 1)
    best = 0
    for i in range(1, len(a_words) + 1):
        cur = [0] * (len(b_words) + 1)
        ai = a_words[i - 1]
        for j in range(1, len(b_words) + 1):
            if ai == b_words[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


def _sentence_is_verbatim_copy(sentence: str, span_text: str) -> bool:
    """True iff ``sentence`` shares a contiguous run of >= ``_verbatim_copy_max_run()`` content words
    verbatim with its cited ``span_text`` (both provenance-token-stripped, content-word tokenized). A
    lazy verbatim paste is caught; a genuine rephrase (that reorders/reworks the wording) is not, because
    a long IDENTICAL contiguous run only survives copy-paste. Numbers-only / short quoted phrases never
    reach the run floor. Fail-open: an empty span (unresolved) returns False (never flags on no evidence)."""
    span_words = _content_word_sequence(span_text)
    if not span_words:
        return False
    sent_words = _content_word_sequence(sentence)
    return _max_contiguous_shared_run(sent_words, span_words) >= _verbatim_copy_max_run()


def _cited_span_text_for(tokens: list, scoped_pool: dict) -> str:
    """The combined CITED sub-span text for the parsed provenance ``tokens`` against ``scoped_pool``,
    i.e. ``direct_quote[token.start:token.end]`` per token (NOT the whole row — the whole-row text
    would demand OTHER claims' numerics and force a universal K-span no-op). Used by the
    completeness guard's span->sentence direction. Bounds-safe (out-of-range slices to "")."""
    parts: list[str] = []
    for tok in tokens or []:
        eid = str(getattr(tok, "evidence_id", "") or "")
        row = (scoped_pool or {}).get(eid) or {}
        haystack = str(row.get("direct_quote") or row.get("statement") or "")
        start = int(getattr(tok, "start", -1))
        end = int(getattr(tok, "end", -1))
        if 0 <= start < end <= len(haystack):
            parts.append(haystack[start:end])
    return " ".join(parts)


# ── Fix 1 (2026-07-10 compose gear-loop iter 2) — SATISFIABLE span->sentence numeric completeness ────
# DECIMAL-AWARE source-segment terminator: a period BETWEEN two digits is a decimal point (``1.5``),
# NOT a sentence boundary — so a figure never straddles two segments. ``!``/``?`` and a period not
# flanked by digits are terminators. Used ONLY to scope the completeness denominator to the source
# SENTENCE-SEGMENT the writer sentence rests on (never a faithfulness verdict).
_SOURCE_SEGMENT_TERMINATOR_RE = re.compile(r"(?<!\d)[.](?!\d)|[!?]")


def _split_source_segments(text: str) -> list[str]:
    """Split a source span into decimal-aware sentence segments (a figure like ``1.5 percent`` stays in
    ONE segment). Pure. Scopes the numeric-completeness denominator to the segment the sentence rests
    on — it is NOT a faithfulness gate (the NLI entailment + per-number membership legs are unchanged)."""
    s = text or ""
    if not s.strip():
        return []
    segs: list[str] = []
    start = 0
    for m in _SOURCE_SEGMENT_TERMINATOR_RE.finditer(s):
        end = m.end()
        if s[start:end].strip():
            segs.append(s[start:end])
        start = end
    if start < len(s) and s[start:].strip():
        segs.append(s[start:])
    return segs


def _completeness_span_numerics(result_sentence: str, scoped_pool: dict) -> set[str]:
    """The span numerals the writer sentence is RESPONSIBLE for completing — scoped to the MINIMAL
    source sub-span(s) the sentence actually rests on, NOT the whole cited span (Fix 1, 2026-07-10
    compose gear-loop iter 2).

    ROOT: for a chunk-sized cp3 member the cited token's span is the whole ~8000-char document; the old
    gate demanded EVERY numeral in it appear in ONE sentence -> ``writer_numeric_dropped`` killed 100% of
    drafts -> every basket fell to the deterministic whole-span verbatim emission (the chrome / quote-
    dump / repetition root). FIX: anchor on NUMERIC CO-LOCATION — the sentence's OWN numerals locate the
    source SENTENCE-SEGMENT(s) they were drawn from; completeness then requires only the OTHER numerals
    in THOSE same segments (a dropped SIBLING figure in the same source sentence, e.g. writing the 86.6%
    treatment arm but hiding the 47.6% comparator). This is NUMERIC-anchored, NEVER lexical — it never
    reintroduces the removed content-word-overlap gate (the ghost). Satisfiable AND strict: a genuine
    cherry-pick is still caught; a legitimate one-figure synthesis is not false-dropped.

    Tokens are parsed from ``result_sentence`` (``res.sentence`` per Fable). A sentence carrying NO
    numeral has nothing to complete (a faithful QUALITATIVE synthesis of a quantitative span is judged by
    the NLI entailment leg, not this gate) -> empty set. Bounds-safe."""
    from src.polaris_graph.generator.provenance_generator import (  # noqa: PLC0415
        _numbers_in,
        _strip_dose_patterns,
        parse_provenance_tokens,
    )
    sent_nums = set(_numbers_in(_strip_dose_patterns(result_sentence or "")))
    if not sent_nums:
        return set()
    out: set[str] = set()
    for tok in parse_provenance_tokens(result_sentence) or []:
        eid = str(getattr(tok, "evidence_id", "") or "")
        row = (scoped_pool or {}).get(eid) or {}
        haystack = str(row.get("direct_quote") or row.get("statement") or "")
        start = int(getattr(tok, "start", -1))
        end = int(getattr(tok, "end", -1))
        if not (0 <= start < end <= len(haystack)):
            continue
        cited = haystack[start:end]
        for seg in _split_source_segments(cited):
            seg_nums = _substantive_span_numerics(seg)
            if seg_nums & sent_nums:  # this source segment is one the sentence drew a numeral from
                out |= seg_nums
    return out


def make_writer_verify_fn(base_verify: Callable[..., Any]) -> Callable[..., Any]:
    """The WRITER-SPECIFIC verify wrapper injected as ``_compose_one_basket``'s ``verify_fn``
    (design §3.2). Pure (verify-only; no retry, no LLM). The K-span path keeps the bare
    ``base_verify`` (default ``allow_local_window_fallback=True``); ONLY the writer path wraps it.
    ``_compose_one_basket``'s signature + body are byte-identical — it just receives a different
    ``verify_fn``. The wrapper is STRICTER than the K-span path:

      P1-2: verifies with ``allow_local_window_fallback=False`` (no same-row local-window rescue).
      P1-1: a TRANSPORT entailment ``judge_error`` (the durable ``SentenceVerification.judge_error``
            field) is forced to ``is_verified=False`` (``writer_judge_error_fail_closed``).
      P1-3: a DROPPED substantive span numeric (span->sentence completeness) forces
            ``is_verified=False`` (``writer_numeric_dropped``).
    """

    def _wrapped(sentence: str, scoped_pool: dict, *args: Any, **kwargs: Any) -> Any:
        # P1-2: pin the local-window loophole shut for the writer path. (The K-span path keeps the
        # bare base_verify default True via the unwrapped verify_fn — the shared default is untouched.)
        kwargs.setdefault("allow_local_window_fallback", False)
        res = base_verify(sentence, scoped_pool, *args, **kwargs)

        # P1-1: a TRANSPORT entailment judge_error is a WRITER FAILURE. The shared verifier (with
        # PG_ENTAILMENT_JUDGE_ERROR_ADVISORY=1, the I-arch-010 default) advisory-KEEPS such a result
        # as is_verified=True and sets the durable judge_error=True marker. That advisory keep is
        # CORRECT for the deterministic K-span (a verbatim substring is grounded by construction) but
        # WRONG for an abstractive paraphrase, whose ONLY semantic guarantee is the entailment leg.
        # Read the BOOL FIELD (the canonical marker), not the soft_warnings string.
        if getattr(res, "judge_error", False) and bool(getattr(res, "is_verified", False)):
            res = dataclasses.replace(
                res,
                is_verified=False,
                failure_reasons=[*list(getattr(res, "failure_reasons", []) or []),
                                 "writer_judge_error_fail_closed"],
            )

        # P1-3: span->sentence numeric COMPLETENESS (the reverse direction the engine does NOT check).
        # Only meaningful when the sentence is otherwise verified (a sentence already failing for
        # another reason needs no completeness escalation). The cited span text is resolved from the
        # parsed tokens of the INPUT sentence against the scoped pool (the exact cited sub-spans), so
        # the denominator is the writer's own cited spans — never the whole row.
        if bool(getattr(res, "is_verified", False)):
            from src.polaris_graph.generator.provenance_generator import (  # noqa: PLC0415
                parse_provenance_tokens,
            )
            # Fix 1 (2026-07-10 compose gear-loop iter 2): parse the tokens from the verifier's RESULT
            # sentence (res.sentence) and scope the completeness denominator to the MINIMAL source
            # sub-span the sentence rests on via NUMERIC CO-LOCATION — never the whole cited token span
            # (which is the entire ~8000-char chunk for a chunk-sized member, an impossible completeness
            # bar that killed 100% of drafts). cited_span_text (for the anti-verbatim leg below) is still
            # the full cited span; only the numeric-completeness denominator is narrowed.
            result_sentence = str(getattr(res, "sentence", "") or "") or sentence
            cited_span_text = _cited_span_text_for(
                parse_provenance_tokens(result_sentence), scoped_pool
            )
            span_numerics = _completeness_span_numerics(result_sentence, scoped_pool)
            if span_numerics and not all(
                _numeral_appears_verbatim(n, sentence) for n in span_numerics
            ):
                res = dataclasses.replace(
                    res,
                    is_verified=False,
                    failure_reasons=[*list(getattr(res, "failure_reasons", []) or []),
                                     "writer_numeric_dropped"],
                )
        # P0-1(d) ANTI-VERBATIM (2026-07-10): a writer sentence that pasted a long verbatim run of its
        # cited span is a quote-dump, not synthesis — FAIL it (only when still verified; a sentence
        # already failing needs no escalation) so the existing repair loop re-drafts it. The reason
        # string is fed back to the writer verbatim. Only the WRITER path is wrapped, so a deliberate
        # verbatim K-span (bare verify_fn, never this wrapper) is untouched.
        if bool(getattr(res, "is_verified", False)) and _sentence_is_verbatim_copy(
            sentence, cited_span_text
        ):
            res = dataclasses.replace(
                res,
                is_verified=False,
                failure_reasons=[*list(getattr(res, "failure_reasons", []) or []),
                                 "verbatim_copy — rewrite in your own words"],
            )
        return res

    return _wrapped


# ── the writer prompt contract (design §3.3) ─────────────────────────────────────────────────────
_WRITER_SYSTEM = (
    "You rewrite already-verified evidence spans into clean, plain, declarative news-style "
    "sentences. You NEVER add a fact that is not in a provided span. You copy every number "
    "(decimal, percent, integer, dose) exactly as written — never round, never convert units. "
    "You end each sentence with the exact provenance token supplied for the span it rephrases, "
    "copied character-for-character; you never invent or edit a token. You write subject-verb-object "
    "sentences that name the specific finding, number, and actor. You copy every epistemic or "
    "scope qualifier bound to a number exactly as written — hedges ('may', 'approximately', "
    "'up to'), non-factive verbs ('estimated', 'projected', 'suggests'), source attribution "
    "('according to', 'reportedly'), and conditional / scenario restrictors ('if', 'under the "
    "... scenario') — never restate a hedged or conditional figure as a settled fact. You do NOT "
    "use markdown, links, "
    "bullets, headings, section numbers, captions, or academic chrome like 'this study' or "
    "'the framework'. You output exactly one sentence per span, nothing else."
)


# I-deepfix-001 Wave-1a (#1344) — the GROUP writer contract. IDENTICAL faithfulness rules to
# ``_WRITER_SYSTEM`` (never a fact outside a span; every number verbatim; every sentence ends with its
# exact provenance token copied char-for-char; every epistemic/scope qualifier preserved; no markdown /
# chrome) EXCEPT the final clause: instead of "one sentence per span" the group contract asks for ONE
# coherent connected multi-sentence narrative over a GROUP of verified spans. Selected at call time by
# ``group_mode`` (default OFF => never referenced) so ``_WRITER_SYSTEM`` stays byte-unchanged and the
# gate-B force-set ``PG_ABSTRACTIVE_WRITER`` path is byte-identical when ``PG_SYNTH_PRIMARY`` is unset.
_WRITER_SYSTEM_GROUP = (
    "You rewrite already-verified evidence spans into clean, plain, declarative news-style "
    "sentences. You NEVER add a fact that is not in a provided span. You copy every number "
    "(decimal, percent, integer, dose) exactly as written — never round, never convert units. "
    "You end each sentence with the exact provenance token supplied for the span it rephrases, "
    "copied character-for-character; you never invent or edit a token. You write subject-verb-object "
    "sentences that name the specific finding, number, and actor. You copy every epistemic or "
    "scope qualifier bound to a number exactly as written — hedges ('may', 'approximately', "
    "'up to'), non-factive verbs ('estimated', 'projected', 'suggests'), source attribution "
    "('according to', 'reportedly'), and conditional / scenario restrictors ('if', 'under the "
    "... scenario') — never restate a hedged or conditional figure as a settled fact. You do NOT "
    "use markdown, links, "
    "bullets, headings, section numbers, captions, or academic chrome like 'this study' or "
    "'the framework'. Write ONE coherent, connected multi-sentence narrative that covers this "
    "GROUP of verified spans in a logical order; each sentence ends with the exact provenance "
    "token(s) of the span(s) it rests on; you may order and connect the facts with plain "
    "connectives, but never state a fact not present in a provided span, and never merge two "
    "spans' numbers into a new aggregate."
)


def _section_outline_lead(section_context: "dict | None") -> str:
    """P0-2 OUTLINE-ECHO (2026-07-10): the prompt lead that grounds the writer in the SECTION it is
    composing — its title, focus, and the research question — so it synthesizes prose that FULFILLS the
    focus and OMITS spans irrelevant to it. General + question-agnostic (the title/focus/question are
    threaded from the plan, never hardcoded). Empty when no section context is supplied (byte-identical)."""
    if not section_context:
        return ""
    title = " ".join(str(section_context.get("title", "") or "").split())
    focus = " ".join(str(section_context.get("focus", "") or "").split())
    question = " ".join(str(section_context.get("research_question", "") or "").split())
    if not (title or focus or question):
        return ""
    return (
        f"You are writing the section titled \"{title}\" whose focus is \"{focus}\" for the research "
        f"question \"{question}\". Synthesize the spans into prose that FULFILLS this focus; OMIT a span "
        "irrelevant to this focus; never describe the document — state what it FOUND; skip "
        "chrome/boilerplate/bibliographic-export text entirely. Fix 6 (2026-07-10): SKIP any span whose "
        "content is authorship, author affiliation, an author bio, acknowledgments, funding, copyright, "
        "or institutional self-description (who wrote, funded, or published the document, or what an "
        "institute 'conducts') — that is page furniture, never a research finding; write only the "
        "documents' substantive findings."
    )


def _build_writer_prompt(
    members: list,
    evidence_pool: dict,
    *,
    revise_reasons: Optional[list[str]] = None,
    group_mode: bool = False,
    section_context: "dict | None" = None,
) -> str:
    """Build the user prompt: one SUPPORTS member per line, each given its verified span text and
    the EXACT canonical token (the same ``[#ev:<id>:<start>-<end>]`` ``build_verified_span_draft``
    would emit, computed by ``_member_global_span``). The writer rephrases each span into one
    declarative sentence ending with that token. On a retry, the specific wrapper failure reasons
    are fed back (RARR-style revise).

    P0-2 OUTLINE-ECHO: when ``section_context`` (``{title, focus, research_question}``) is supplied it
    is echoed as the FIRST prompt line so the writer synthesizes to the section's focus and omits
    off-focus spans. None => byte-identical to the pre-outline-echo prompt."""
    from src.polaris_graph.generator.verified_compose import _member_global_span  # noqa: PLC0415

    # I-deepfix-001 Wave-1a (#1344): the lead instruction is the ONLY difference in group mode; the
    # spans+tokens block and the revise_reasons block below are UNCHANGED. group_mode=False =>
    # byte-identical to the pre-Wave-1a prompt.
    if group_mode:
        lead = (
            "Write ONE connected paragraph covering ALL the verified spans below, in a logical "
            "order; each sentence ends with the exact provenance token for the span(s) it rests on, "
            "copied character-for-character. Copy every number verbatim. Order and connect the facts "
            "with plain connectives, but never state a fact not present in a provided span, and "
            "never merge two spans' numbers into a new aggregate."
        )
    else:
        lead = (
            "Rewrite each verified evidence span below into ONE clean, plain, declarative "
            "news-style sentence. End each sentence with the exact provenance token shown for it, "
            "copied character-for-character. Copy every number verbatim. Output one sentence per span, "
            "in order, one per line, and nothing else."
        )
    outline_lead = _section_outline_lead(section_context)
    lines: list[str] = ([outline_lead, ""] if outline_lead else []) + [lead, ""]
    for i, m in enumerate(members, start=1):
        eid = str(getattr(m, "evidence_id", "") or "")
        gspan = _member_global_span(m, evidence_pool)
        quote = str(getattr(m, "direct_quote", "") or "").strip()
        if not eid or gspan is None or not quote:
            continue
        start, end = gspan
        token = f"[#ev:{eid}:{start}-{end}]"
        lines.append(f"SPAN {i}: {quote}")
        lines.append(f"TOKEN {i} (append verbatim to sentence {i}): {token}")
        lines.append("")
    if revise_reasons:
        lines.append(
            "Your previous attempt FAILED verification for these reasons — fix them and try again:"
        )
        for r in revise_reasons:
            lines.append(f"  - {r}")
        lines.append("")
    return "\n".join(lines)


# ── the async per-basket LLM writer call ─────────────────────────────────────────────────────────
async def _call_writer(
    members: list,
    evidence_pool: dict,
    *,
    model: str,
    max_tokens: int,
    reasoning_max_tokens: int,
    temperature: float,
    revise_reasons: Optional[list[str]] = None,
    group_mode: bool = False,
    catch_transport: bool = False,
    section_context: "dict | None" = None,
) -> str:
    """ONE LLM writer call for a basket: rephrase the SUPPORTS members' verified spans into clean
    declarative prose carrying the canonical tokens. Returns the raw draft text (re-verified by the
    unchanged compose loop). On any error returns "" -> the loop falls back to the K-span (fail-loud
    to the K-span, never a silent crash).

    I-deepfix-001 Wave-1a (#1344): ``group_mode`` selects the GROUP writer contract
    (``_WRITER_SYSTEM_GROUP`` + the connected-paragraph lead) — one coherent multi-sentence narrative
    over the whole basket's spans instead of one sentence per span. Default False => byte-identical.

    I-deepfix-001 B3 (#1370): ``catch_transport`` (set only by the transport-aware pre-pass branch)
    catches the httpx transport-DISCONNECT family — ConnectTimeout / ConnectError / RemoteProtocolError
    / ReadError — and returns the ``_WRITER_TRANSPORT_DISCONNECT`` sentinel instead of letting the
    exception escape as an unretrieved-task leak ("Task exception was never retrieved"). Default False =>
    NO catch => byte-identical (the exception propagates exactly as before, K-span via the caller)."""
    import httpx  # noqa: PLC0415 — local import (transport-disconnect classes; B3 catch only)

    from src.polaris_graph.llm.openrouter_client import OpenRouterClient  # noqa: PLC0415

    prompt = _build_writer_prompt(
        members, evidence_pool, revise_reasons=revise_reasons, group_mode=group_mode,
        section_context=section_context,
    )
    system = _WRITER_SYSTEM_GROUP if group_mode else _WRITER_SYSTEM
    client = OpenRouterClient(model=model)
    # §9.1.8: a NEGATIVE/zero reasoning cap is the "unset" sentinel -> pass None so GLM-5.2's
    # _ALWAYS_REASON branch runs at effort=high (its default) instead of a starving fixed cap.
    reasoning_arg = reasoning_max_tokens if reasoning_max_tokens and reasoning_max_tokens > 0 else None
    try:
        response = await client.generate(
            prompt=prompt,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
            reasoning_max_tokens=reasoning_arg,
        )
        return str(getattr(response, "content", "") or "")
    except (
        httpx.ConnectTimeout,
        httpx.ConnectError,
        httpx.RemoteProtocolError,
        httpx.ReadError,
    ) as exc:
        # B3: only the transport-aware branch requests this catch. It converts a transport DISCONNECT
        # into a clean sentinel (the caller then grants a fresh reconnect window without charging a
        # productive attempt, and the basket K-span-falls-back if the budget is exhausted) — the raw
        # ConnectTimeout never orphans as an unretrieved task. Flag OFF => re-raise => legacy behavior.
        if not catch_transport:
            raise
        logger.warning(
            "[abstractive_writer] writer call transport-disconnect (%s) -> clean reconnect sentinel",
            type(exc).__name__,
        )
        return _WRITER_TRANSPORT_DISCONNECT
    finally:
        try:
            await client.close()
        except Exception:  # noqa: BLE001  — best-effort teardown; never mask the writer result
            logger.debug("[abstractive_writer] client.close() raised on teardown", exc_info=True)


def _draft_passes_wrapper(
    draft: str,
    basket: Any,
    evidence_pool: dict,
    writer_verify_fn: Callable[..., Any],
) -> tuple[bool, list[str]]:
    """Verify a candidate draft with the WRITER WRAPPER + region gate against the basket-scoped pool
    — exactly the gate ``_compose_one_basket`` will apply — to decide whether the pre-pass needs a
    retry. Returns (all_sentences_pass, failure_reasons). This MIRRORS the loop's accept condition;
    the loop remains the authoritative gate (the pre-pass only proposes)."""
    from src.polaris_graph.generator.verified_compose import (  # noqa: PLC0415
        _basket_member_regions,
        _basket_scoped_pool,
        _tokens_within_basket_regions,
        split_into_sentences,
    )
    scoped_pool = _basket_scoped_pool(basket, evidence_pool)
    regions = _basket_member_regions(basket, evidence_pool)
    sentences = split_into_sentences(draft or "")
    if not sentences:
        return False, ["writer_empty_draft"]
    reasons: list[str] = []
    for sentence in sentences:
        res = writer_verify_fn(sentence, scoped_pool)
        verified_text = str(getattr(res, "sentence", "") or "").strip() or sentence.strip()
        if not (bool(getattr(res, "is_verified", False))
                and _tokens_within_basket_regions(verified_text, regions)):
            rs = list(getattr(res, "failure_reasons", []) or [])
            reasons.extend(rs or ["writer_sentence_rejected"])
            return False, reasons
    return True, reasons


async def _pre_pass_one_basket(
    basket: Any,
    evidence_pool: dict,
    *,
    writer_verify_fn: Callable[..., Any],
    model: str,
    max_retries: int,
    max_tokens: int,
    reasoning_max_tokens: int,
    temperature: float,
    call_deadline_s: float,
    group_mode: bool = False,
    section_context: "dict | None" = None,
) -> Optional[str]:
    """Compute one basket's draft: call the LLM writer, verify the candidate with the writer wrapper,
    and on failure retry up to ``max_retries`` times feeding the specific failure reasons back. The
    LAST attempt's draft is returned (even if failing) — the unchanged compose loop re-verifies it
    and falls back to the K-span if it does not pass (the pre-pass NEVER emits the K-span itself).
    Returns None only when the basket has no resolvable SUPPORTS member (writer skipped).

    I-deepfix-001 Wave-1a (#1344): ``group_mode`` selects the GROUP writer contract on the attempt-0
    draft (one coherent multi-sentence narrative over the whole basket) so the SYNTH_PRIMARY keystone
    effect materializes on the FIRST draft — not only after a compose-level repair. Default False =>
    byte-identical single-sentence-per-span pre-pass."""
    from src.polaris_graph.generator.verified_compose import (  # noqa: PLC0415
        _basket_supports_members,
        _compose_junk_screen,
    )

    members = _basket_supports_members(basket)
    if not members:
        return None

    # §3.1 input-screen (#1289, advisor 2026-06-21): drop chrome members BEFORE the LLM writer call.
    # The abstractive path emits via the precomputed dict, NOT build_verified_span_draft, so the §3.4
    # OUTPUT junk screen never runs on it — AND a paraphrase mangles the multi-word chrome markers, so
    # only an INPUT screen catches them. Reuse the §3.4 high-precision allowlist screen on each
    # member's verified span text. Faithfulness-safe (§-1.3): boilerplate is not a corroborating
    # source. A MIXED basket (chrome member + real member) keeps the real member + its citation; an
    # ALL-chrome basket leaves zero members -> writer skipped (None) -> the loop K-span-falls-back and
    # §3.4 screens that too, so the all-chrome basket emits nothing (it never cascades a REAL section
    # to empty — only baskets that carry no real content drop out).
    screened_members = [
        m for m in members
        if not _compose_junk_screen(str(getattr(m, "direct_quote", "") or ""))
    ]
    if not screened_members:
        logger.info(
            "[abstractive_writer] basket=%s all SUPPORTS members screened as chrome -> writer skipped "
            "(K-span fallback)", _basket_key(basket),
        )
        return None
    members = screened_members

    # I-deepfix-001 B3 (#1370): the transport-aware retry (default OFF => the verbatim legacy for-loop).
    if not _deadline_transport_aware_enabled():
        revise_reasons: Optional[list[str]] = None
        last_draft = ""
        for attempt in range(max_retries + 1):
            try:
                draft = await asyncio.wait_for(
                    _call_writer(
                        members, evidence_pool,
                        model=model, max_tokens=max_tokens,
                        reasoning_max_tokens=reasoning_max_tokens, temperature=temperature,
                        revise_reasons=revise_reasons, group_mode=group_mode,
                        section_context=section_context,
                    ),
                    timeout=call_deadline_s,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "[abstractive_writer] basket=%s writer call exceeded %.0fs deadline (attempt %d) "
                    "-> K-span fallback", _basket_key(basket), call_deadline_s, attempt + 1,
                )
                break
            except Exception:  # noqa: BLE001 — any writer error degrades to K-span, never crashes the run
                logger.warning(
                    "[abstractive_writer] basket=%s writer call raised (attempt %d) -> K-span fallback",
                    _basket_key(basket), attempt + 1, exc_info=True,
                )
                break
            last_draft = draft
            passed, reasons = _draft_passes_wrapper(draft, basket, evidence_pool, writer_verify_fn)
            if passed:
                return draft
            revise_reasons = reasons or None
        # P0-1(a) (2026-07-10): on TRUE exhaustion (nothing produced) return None — the basket is then
        # ABSENT from the precomputed dict (eligible for the K-span recovery pass) and the exhaust path
        # emits the LABELED unverified-synthesis line, never a raw span. A non-empty failing draft is
        # still returned so the synth-primary repair loop can work on it.
        return last_draft if last_draft.strip() else None

    # ── transport-aware branch (PG_WRITER_DEADLINE_TRANSPORT_AWARE ON) ────────────────────────────
    # A transport DISCONNECT / per-call stall does NOT consume a PRODUCTIVE retry attempt: it is granted
    # a FRESH ``call_deadline_s`` reconnect window (reconnect/stall time not charged), bounded by
    # ``max(1, max_retries)`` extra reconnect windows so a persistently-dead provider still degrades to
    # K-span in finite time (the outer wall is the hard ceiling). Only a completed writer draft that
    # FAILS verification burns a productive attempt — the productive budget is identical to the legacy
    # ``range(max_retries + 1)``. The _call_writer catch (catch_transport=True) makes the disconnect a
    # clean sentinel, killing the "Task exception was never retrieved" leak.
    revise_reasons = None
    last_draft = ""
    productive_attempt = 0
    transport_reattempt = 0
    max_transport_reattempts = max(1, max_retries)
    while productive_attempt <= max_retries:
        try:
            draft = await asyncio.wait_for(
                _call_writer(
                    members, evidence_pool,
                    model=model, max_tokens=max_tokens,
                    reasoning_max_tokens=reasoning_max_tokens, temperature=temperature,
                    revise_reasons=revise_reasons, group_mode=group_mode,
                    catch_transport=True, section_context=section_context,
                ),
                timeout=call_deadline_s,
            )
        except asyncio.TimeoutError:
            # A per-call stall is a TRANSPORT event under transport-awareness: grant a fresh window
            # without charging a productive attempt, bounded by max_transport_reattempts.
            if transport_reattempt < max_transport_reattempts:
                transport_reattempt += 1
                logger.warning(
                    "[abstractive_writer] basket=%s writer call stalled at %.0fs -> fresh reconnect "
                    "window (transport %d/%d, productive %d/%d)",
                    _basket_key(basket), call_deadline_s, transport_reattempt,
                    max_transport_reattempts, productive_attempt + 1, max_retries + 1,
                )
                continue
            logger.warning(
                "[abstractive_writer] basket=%s writer stall reconnect budget exhausted -> K-span",
                _basket_key(basket),
            )
            break
        except Exception:  # noqa: BLE001 — any non-transport writer error degrades to K-span
            logger.warning(
                "[abstractive_writer] basket=%s writer call raised -> K-span fallback",
                _basket_key(basket), exc_info=True,
            )
            break
        if draft == _WRITER_TRANSPORT_DISCONNECT:
            # A clean transport-disconnect sentinel: same treatment as a stall (fresh reconnect window,
            # no productive attempt charged, never leaked into last_draft).
            if transport_reattempt < max_transport_reattempts:
                transport_reattempt += 1
                logger.warning(
                    "[abstractive_writer] basket=%s transport-disconnect -> fresh reconnect window "
                    "(transport %d/%d, productive %d/%d)",
                    _basket_key(basket), transport_reattempt, max_transport_reattempts,
                    productive_attempt + 1, max_retries + 1,
                )
                continue
            logger.warning(
                "[abstractive_writer] basket=%s transport-disconnect budget exhausted -> K-span",
                _basket_key(basket),
            )
            break
        last_draft = draft
        passed, reasons = _draft_passes_wrapper(draft, basket, evidence_pool, writer_verify_fn)
        if passed:
            return draft
        revise_reasons = reasons or None
        productive_attempt += 1
    # P0-1(a) (2026-07-10): true exhaustion with nothing produced => None (absent from the dict, the
    # exhaust path emits the LABELED line, never a span). A non-empty failing draft is kept for repair.
    return last_draft if last_draft.strip() else None


async def abstractive_pre_pass(
    baskets: list,
    evidence_pool: dict,
    *,
    writer_verify_fn: Callable[..., Any],
    group_mode: bool = False,
    section_context: "dict | None" = None,
) -> dict:
    """ASYNC pre-pass (design §3.4a): precompute one verified draft per basket up front, under a
    ``PG_ABSTRACTIVE_WRITER_CONCURRENCY`` semaphore with a per-call total deadline AND an OUTER
    wall-deadline. Keyed by the basket's canonical ``claim_cluster_id`` so the sync ``writer_fn`` is a
    deterministic dict lookup. A basket that the writer skipped/failed/was abandoned at the wall is
    simply absent (or maps to a failing draft) -> the sync writer_fn returns "" / the failing draft ->
    the unchanged loop K-span-falls-back. Never raises on a per-basket failure (always-release).

    HANG FIX (I-wire-001 W6 #1314, I-arch-007 wall+abandon pattern in its async-native form): the
    per-call ``asyncio.wait_for(call_deadline_s)`` bounds ONE writer call, but under a provider
    connection/429 storm the bounded pool's calls + retry backoffs can balloon the pre-pass wall-clock
    with NO outer bound, and a ``wait_for`` cancellation that stalls inside httpx client teardown (the
    proven hang class) would wedge ``asyncio.gather`` forever (gather awaits EVERY task incl. an
    uncancellable one). So the basket tasks run under ``asyncio.wait(timeout=wall_deadline_s)`` and any
    still-pending task at the wall is ABANDONED (cancelled best-effort, NEVER awaited) — its basket is
    absent from ``out`` -> the loop K-span-falls-back (fail-OPEN, disclosed). The wall is finite and
    env-configurable (``PG_ABSTRACTIVE_WRITER_WALL_DEADLINE_S``); it is NEVER infinite."""
    model = _resolve_model()
    max_retries = max(0, _env_int(_ENV_MAX_RETRIES, _DEFAULT_MAX_RETRIES))
    max_tokens = max(1, _env_int(_ENV_MAX_TOKENS, _DEFAULT_MAX_TOKENS))
    reasoning_max_tokens = max(0, _env_int(_ENV_REASONING_MAX_TOKENS, _DEFAULT_REASONING_MAX_TOKENS))
    temperature = _env_float(_ENV_TEMPERATURE, _DEFAULT_TEMPERATURE)
    call_deadline_s = max(1.0, _env_float(_ENV_CALL_DEADLINE_S, _DEFAULT_CALL_DEADLINE_S))
    wall_deadline_s = max(1.0, _env_float(_ENV_WALL_DEADLINE_S, _DEFAULT_WALL_DEADLINE_S))
    concurrency = max(1, _env_int(_ENV_CONCURRENCY, _DEFAULT_CONCURRENCY))

    # I-deepfix-001 B4 (#1370): basket-count-SCALED wall from the code's own makespan formula (NOT a
    # blind time-wall raise). The flat _DEFAULT_WALL_DEADLINE_S was sized for 23 baskets @ conc 8; a
    # 71-113-basket drb_72 section overruns it and abandons the whole wave. max(flat, scaled) scales UP
    # for big sections while NEVER shrinking below the proven-safe flat baseline for small ones. OFF =>
    # the flat/env wall is used verbatim. I-deepfix-001 B3: transport-awareness adds ONE bounded
    # reconnect-window of headroom so a wall that would bite purely on transport-stall gets one more
    # window before abandoning (finite; not a blind raise).
    n_keyed = sum(1 for b in (baskets or []) if _basket_key(b))
    if _wall_basket_scaled_enabled():
        scaled = _makespan_wall_seconds(n_keyed, concurrency, max_retries, call_deadline_s)
        if scaled > wall_deadline_s:
            logger.info(
                "[abstractive_writer] basket-scaled wall: n=%d conc=%d retries=%d call=%.0fs -> "
                "wall=%.0fs (flat floor %.0fs)",
                n_keyed, concurrency, max_retries, call_deadline_s, scaled, wall_deadline_s,
            )
            wall_deadline_s = scaled
    if _deadline_transport_aware_enabled():
        wall_deadline_s += call_deadline_s

    # P0-2 OUTLINE-ECHO activation marker: prove the section {title, focus} reached the writer.
    if section_context:
        logger.info(
            "[activation] outline_echo: title=%r focus_len=%d q_len=%d",
            str(section_context.get("title", "") or "")[:80],
            len(str(section_context.get("focus", "") or "")),
            len(str(section_context.get("research_question", "") or "")),
        )

    sem = asyncio.Semaphore(concurrency)
    out: dict = {}

    async def _one(basket: Any, semaphore: "asyncio.Semaphore") -> None:
        key = _basket_key(basket)
        if not key:
            return
        async with semaphore:
            draft = await _pre_pass_one_basket(
                basket, evidence_pool,
                writer_verify_fn=writer_verify_fn,
                model=model, max_retries=max_retries,
                max_tokens=max_tokens, reasoning_max_tokens=reasoning_max_tokens,
                temperature=temperature, call_deadline_s=call_deadline_s,
                group_mode=group_mode, section_context=section_context,
            )
        if draft is not None:
            # mutate the shared dict as a SIDE EFFECT so an abandoned (never-awaited) task's
            # already-completed siblings are still captured — out is the source of truth, not gather().
            out[key] = draft

    def _abandon_pending(pending_tasks: "set[asyncio.Task]") -> None:
        # ABANDON the stuck baskets — do NOT await (awaiting a task wedged in httpx teardown, or one
        # that swallows CancelledError and re-blocks, is the very hang we are bounding). A bare
        # t.cancel() is INSUFFICIENT for such a task. So we port the access_bypass detach/drain/
        # force-close pattern: register each abandoned task in the detached set, attach the drain
        # done-callback, cancel() best-effort, then FORCE-CLOSE its underlying coroutine via
        # _coro.close() so the task is finalized as done() NOW -> excluded from asyncio.run's
        # _cancel_all_tasks await-list -> shutdown cannot hang. Those baskets are absent from `out`
        # -> the compose loop K-span-falls-back. This is the wall's fail-OPEN, always-release behavior.
        for t in pending_tasks:
            _DETACHED_WRITER_TASKS.add(t)
            t.add_done_callback(_drain_detached_writer_task)
            t.cancel()
            _force_drop_detached_writer_task(t)

    def _surface_completed_exceptions(done_tasks: "set[asyncio.Task]") -> None:
        # Surface any non-cancellation exception from a COMPLETED task (never let one die silently) — a
        # per-basket writer error already degrades to "" inside _pre_pass_one_basket, so a completed
        # task raising here is a genuine unexpected fault worth logging (still non-fatal: always-release).
        for t in done_tasks:
            exc = t.exception()
            if exc is not None:
                logger.warning("[abstractive_writer] a pre-pass basket task raised: %r", exc)

    tasks = [asyncio.ensure_future(_one(b, sem)) for b in (baskets or [])]
    if not tasks:
        logger.info("[abstractive_writer] pre-pass complete: 0/0 baskets drafted (model=%s)", model)
        return out

    # Install the belt-and-suspenders teardown hook on the running loop BEFORE the wall can bite, so an
    # untracked wedged task is also force-closed at shutdown (the primary defense is the abandon-time
    # force-close below, which finalizes tracked tasks before _cancel_all_tasks ever runs).
    try:
        install_teardown_drain_hook(asyncio.get_running_loop())
    except Exception:  # noqa: BLE001 — hook install is best-effort, never fatal to the pre-pass
        logger.debug("[abstractive_writer] teardown-drain hook install skipped", exc_info=True)

    done, pending = await asyncio.wait(tasks, timeout=wall_deadline_s)
    if pending:
        logger.warning(
            "[abstractive_writer] pre-pass WALL-DEADLINE %.0fs hit: ABANDONING %d/%d still-pending "
            "basket task(s) -> K-span fallback (fail-open, disclosed). %d drafted before the wall.",
            wall_deadline_s, len(pending), len(tasks), len(out),
        )
        _abandon_pending(pending)
    _surface_completed_exceptions(done)

    # I-deepfix-001 B4 (#1370): bounded K-span RECOVERY second-pass. Before the still-undrafted baskets
    # fall to K-span, give them ONE more bounded pass with FRESH tasks (the abandoned originals were
    # wedged on a dead socket; a clean re-submit — especially with B3's fresh-connection routing — often
    # succeeds). Bounded by its own makespan wall over just the recovery set; anything still undrafted
    # after it K-span-falls-back exactly as before. DEFAULT OFF => this block is skipped => the legacy
    # immediate-abandon path is byte-identical. Faithfulness-neutral: K-span remains the ultimate
    # fallback and every recovered draft still passes through the unchanged compose-loop verifier.
    if pending and _kspan_recovery_pass_enabled():
        recovery_baskets = [
            b for b in (baskets or [])
            if _basket_key(b) and _basket_key(b) not in out
        ]
        if recovery_baskets:
            rec_wall = max(
                1.0, _makespan_wall_seconds(len(recovery_baskets), concurrency, max_retries, call_deadline_s),
            )
            logger.warning(
                "[abstractive_writer] K-span recovery pass: re-drafting %d still-undrafted basket(s) "
                "under a %.0fs bounded wall before K-span.", len(recovery_baskets), rec_wall,
            )
            rec_sem = asyncio.Semaphore(concurrency)
            rec_before = len(out)
            rec_tasks = [asyncio.ensure_future(_one(b, rec_sem)) for b in recovery_baskets]
            rec_done, rec_pending = await asyncio.wait(rec_tasks, timeout=rec_wall)
            if rec_pending:
                logger.warning(
                    "[abstractive_writer] K-span recovery wall %.0fs hit: ABANDONING %d/%d recovery "
                    "task(s) -> K-span.", rec_wall, len(rec_pending), len(rec_tasks),
                )
                _abandon_pending(rec_pending)
            _surface_completed_exceptions(rec_done)
            logger.info(
                "[abstractive_writer] K-span recovery pass complete: %d/%d basket(s) recovered.",
                len(out) - rec_before, len(recovery_baskets),
            )

    logger.info(
        "[abstractive_writer] pre-pass complete: %d/%d baskets drafted (model=%s, retries=%d, "
        "wall=%.0fs, abandoned=%d)",
        len(out), len(baskets or []), model, max_retries, wall_deadline_s, len(pending),
    )
    return out


def make_abstractive_writer_fn(precomputed: dict) -> Callable[[Any, dict], str]:
    """The SYNC ``writer_fn`` ``_compose_one_basket`` reads: a pure dict lookup keyed by the basket's
    canonical id. A MISSING key returns "" — the loop treats a writer-empty basket as a K-span
    fallback (never a crash). So a pre-pass that skipped/failed a basket degrades safely."""

    def _writer_fn(basket: Any, _scoped_pool: dict) -> str:
        return str(precomputed.get(_basket_key(basket), "") or "")

    return _writer_fn


def assert_activation_preconditions() -> None:
    """Fail-closed activation guard (design §3.6 / §5.5). When the writer is ON it REFUSES to
    activate (raises, fail-LOUD per LAW II — no silent downgrade) unless the entailment leg resolves
    to ``enforce``: the writer's ONLY semantic guarantee for a paraphrase is the entailment leg, so
    activating it with entailment ``off``/``warn`` would ship un-entailment-checked rewritten prose.
    The env guard is the ACTIVATION precondition; the per-call ``judge_error`` demotion (P1-1) is the
    per-sentence call-time enforcement — both are required."""
    from src.polaris_graph.clinical_generator.strict_verify import _entailment_mode  # noqa: PLC0415

    mode = _entailment_mode()
    if mode != "enforce":
        raise RuntimeError(
            "abort_abstractive_writer_unsafe_activation: PG_ABSTRACTIVE_WRITER is ON but "
            f"PG_STRICT_VERIFY_ENTAILMENT resolves to {mode!r}, not 'enforce'. The abstractive "
            "writer's only semantic guarantee for a paraphrase is the entailment leg; activating it "
            "without entailment=enforce would ship un-entailment-checked rewritten prose. Set "
            "PG_STRICT_VERIFY_ENTAILMENT=enforce or disable PG_ABSTRACTIVE_WRITER."
        )
