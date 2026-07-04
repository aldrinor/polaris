"""I-deepfix-001 fix I3 — per-run verdict idempotency cache for the runtime faithfulness judge.

WHY THIS EXISTS (the ~178-calls-per-report availability problem)
----------------------------------------------------------------
The entailment judge (``entailment_judge._EntailmentJudge.judge``) is the runtime faithfulness gate's
LLM leg (strict_verify check (f)). A drb_72-class report fires it ~178 times under ThreadPool concurrency,
and the SAME ``(claim sentence, cited span)`` pair recurs across sections (a consolidated basket's member
span is re-verified everywhere the claim is composed, and identical corroborator spans repeat). Every one
of those repeats is a fresh OpenRouter call that (a) costs money and (b) adds load to the judge provider
pool — the exact pressure that 429s the judge and OVER-DROPS grounded claims (the render-blocker I3
targets).

THE FIX — a process-local, per-(model, normalized-claim, normalized-span, prompt-variant) verdict cache
------------------------------------------------------------------------------------------------------
An identical ``(model, sentence, span, prompt_variant)`` tuple is a deterministic input to the judge
(temperature=0.0), so its verdict is idempotent. Caching the FIRST real verdict and serving every
identical later call from the cache removes the redundant network calls without changing any verdict. The
resolved-prompt variant is part of the key so a same-process prompt bakeoff (which switches the entailment
prompt per call) never serves one variant's verdict for another variant's prompt.

FAITHFULNESS-NEUTRAL, by construction
-------------------------------------
  * The cache returns the SAME ``(verdict, reason)`` the judge already produced for that exact input —
    it can never manufacture, relax, or flip a verdict. The downstream strict_verify / provenance
    consumers run byte-identically on the cached tuple (same telemetry, same drop/keep decision).
  * A fail-CLOSED sentinel (``verdict == 'ENTAILED'`` AND ``reason`` starts ``judge_error:``) is NEVER
    cached — a transient judge fault must stay retryable, so a later identical call still gets a fresh
    attempt at a REAL verdict. ``put`` refuses the sentinel defensively even if a caller mis-calls it.
  * Only the two legit terminal verdicts on a real response are cached: NEUTRAL / CONTRADICTED, and
    ENTAILED whose reason is NOT a ``judge_error:`` sentinel.

SCOPE / LIFETIME
----------------
Process-local (in-memory), NOT on disk: a cached verdict is only trusted within the process that produced
it, so there is zero staleness / cross-run-poisoning surface. ``reset_cache`` clears it (tests + a fresh
run boundary). Bounded by ``PG_JUDGE_VERDICT_CACHE_MAX`` with FIFO eviction so a long-lived process cannot
grow the map without bound.

LAW VI: every knob is env-driven.
  * ``PG_JUDGE_VERDICT_CACHE``      default ``1`` (on). ``0``/``false``/``no``/``off`` => the cache is a
    no-op (``get`` always misses, ``put`` never stores) => the judge path is byte-identical to pre-I3.
  * ``PG_JUDGE_VERDICT_CACHE_MAX``  default ``100000`` entries; FIFO eviction of the oldest above the cap.

Leaf module — stdlib only (``hashlib``/``os``/``threading``/``collections``) — so off-mode side judges pay
zero import cost.
"""
from __future__ import annotations

import hashlib
import os
import re
import threading
from collections import OrderedDict
from typing import Optional, Tuple

_ENV_ENABLED = "PG_JUDGE_VERDICT_CACHE"
_ENV_MAX = "PG_JUDGE_VERDICT_CACHE_MAX"
_DEFAULT_MAX = 100000

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}

# collapse any run of unicode whitespace to a single ASCII space (normalization only merges inputs that
# are the SAME claim/span modulo whitespace — never two distinct claims).
_WS = re.compile(r"\s+")

# module-level store (process-lifetime, shared across the ThreadPool verifier workers via the lock).
_LOCK = threading.RLock()
_STORE: "OrderedDict[str, Tuple[str, str]]" = OrderedDict()

# observability counters (read by the behavioral test + any run telemetry). Not faithfulness state.
_STATS = {"hits": 0, "misses": 0, "stores": 0, "skipped_sentinel": 0, "evictions": 0}


def cache_enabled() -> bool:
    """True unless ``PG_JUDGE_VERDICT_CACHE`` is an explicit falsey value. Default ON."""
    raw = os.environ.get(_ENV_ENABLED, "").strip().lower()
    if raw in _FALSE:
        return False
    # unset or any truthy value => enabled (default-on).
    return True


def _max_entries() -> int:
    try:
        v = int(os.environ.get(_ENV_MAX, "").strip() or _DEFAULT_MAX)
    except (TypeError, ValueError):
        return _DEFAULT_MAX
    return v if v > 0 else _DEFAULT_MAX


def _normalize(text: object) -> str:
    return _WS.sub(" ", str(text)).strip()


def make_key(model: str, sentence: str, span: str, prompt_variant: str = "") -> str:
    """Stable content key for a ``(model, sentence, span, prompt_variant)`` tuple.

    Whitespace-normalized and hashed (sha256) so the map holds fixed-size keys instead of full span text.
    The components are joined with a delimiter that cannot appear inside a single component after
    normalization collapses whitespace, so distinct tuples cannot collide by concatenation.

    ``prompt_variant`` (I3 P1 fix, Fable gate iter1): the judge's verdict is a function of the RESOLVED
    entailment PROMPT, not just the (model, sentence, span). The prompt is a call-time variable
    (``PG_ENTAILMENT_PROMPT_VARIANT`` is read per call so the widening bakeoff can switch variants in ONE
    process). Omitting the variant from the key would make a same-process bakeoff serve variant-1's verdict
    for every later variant — a silent WRONG measurement. Including the active variant id makes each
    distinct prompt a distinct cache decision. Default ``""`` (single-variant production runs) keeps the
    key stable across the whole run."""
    norm = "\x1f".join(
        (_normalize(model), _normalize(sentence), _normalize(span), _normalize(prompt_variant))
    )
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def _is_fail_closed_sentinel(verdict: str, reason: str) -> bool:
    """The entailment judge's fail-CLOSED terminal sentinel: ('ENTAILED', 'judge_error: <reason>').
    Never cached (a transient judge fault must stay retryable)."""
    return str(verdict).strip().upper() == "ENTAILED" and str(reason).lstrip().startswith("judge_error:")


def get(model: str, sentence: str, span: str, prompt_variant: str = "") -> Optional[Tuple[str, str]]:
    """Return the cached ``(verdict, reason)`` for this exact tuple, or ``None`` on a miss / when the
    cache is disabled. ``prompt_variant`` is part of the key (see ``make_key``) so a different resolved
    entailment prompt is a distinct cache decision. A hit refreshes recency (moves the entry to the FIFO
    tail is NOT done — FIFO is by INSERTION order, not access, so the eviction policy stays predictable)."""
    if not cache_enabled():
        return None
    key = make_key(model, sentence, span, prompt_variant)
    with _LOCK:
        val = _STORE.get(key)
        if val is None:
            _STATS["misses"] += 1
            return None
        _STATS["hits"] += 1
        # return a copy-safe tuple (tuples are immutable, so the stored object is safe to hand back).
        return val


def put(
    model: str,
    sentence: str,
    span: str,
    verdict: str,
    reason: str,
    prompt_variant: str = "",
) -> bool:
    """Store a REAL terminal verdict for this tuple. Returns True iff stored. ``prompt_variant`` is part
    of the key (see ``make_key``) so a verdict is only ever served back for the SAME resolved prompt.

    Refuses (returns False) when the cache is disabled OR the value is the fail-closed
    ('ENTAILED','judge_error:…') sentinel (defensive: a transient fault must never be memoized)."""
    if not cache_enabled():
        return False
    if _is_fail_closed_sentinel(verdict, reason):
        with _LOCK:
            _STATS["skipped_sentinel"] += 1
        return False
    key = make_key(model, sentence, span, prompt_variant)
    with _LOCK:
        if key in _STORE:
            # already cached (a concurrent worker won the race) — keep the first, do not double-count.
            return True
        _STORE[key] = (str(verdict), str(reason))
        _STATS["stores"] += 1
        cap = _max_entries()
        while len(_STORE) > cap:
            _STORE.popitem(last=False)  # FIFO: evict the oldest insertion
            _STATS["evictions"] += 1
        return True


def reset_cache() -> None:
    """Clear the cache + zero the stats. Call at a fresh-run boundary and in tests."""
    with _LOCK:
        _STORE.clear()
        for k in _STATS:
            _STATS[k] = 0


def stats() -> dict:
    """Read-only snapshot of the observability counters + current size."""
    with _LOCK:
        snap = dict(_STATS)
        snap["size"] = len(_STORE)
        return snap
