"""Entailment judge — LLM-as-judge for strict_verify check (f).

Originally inlined in `polaris_graph.clinical_generator.strict_verify`. Extracted
per I-bug-099 so future call sites (I-bug-100 OpenRouterClient routing,
I-bug-101 FPR audit harness, etc.) can import the judge + telemetry from
a single canonical location.

I-bug-102 — off-mode contract (verified by `test_off_mode_does_not_instantiate_judge`):
when `PG_STRICT_VERIFY_ENTAILMENT=off`, the judge is NEVER instantiated:
- `_get_judge()` is not called from any code path
- `_EntailmentJudge.__init__` does NOT run
- No `httpx.Client` is constructed
- No OpenRouter network call is made
The class definitions are loaded into the module namespace at import
time (Python module evaluation), but no judge object exists. Module-
level imports are kept lightweight: `openrouter_client` is imported
lazily inside the methods that need it (judge construction, ledger
write, budget check), so off-mode pays zero cost beyond reading the
class definitions.

The judge asks an LLM whether a cited SPAN semantically ENTAILS a
SENTENCE's specific claims. It runs AFTER mechanical checks (a)-(e) and
catches residual fabrication patterns the audit on 2026-05-09 surfaced:
  - mechanistic granularity insertion (M2)
  - specificity inflation (C2)
  - numbers nearby but not entailed (C1)

The judge model is the two-family evaluator (Gemma 4 31B by default),
matching the §9.1.1 invariant — different lineage from the generator
(DeepSeek). Calls go through OpenRouter using the existing project
auth substrate. Family segregation is enforced at construction.

Public surface (re-exported via `polaris_graph.clinical_generator.strict_verify`
for backwards compat with monkeypatch test pattern):
  - _EntailmentJudge: synchronous httpx wrapper around an OpenRouter call
  - _get_judge(): lazy singleton accessor
  - _JUDGE_TELEMETRY: process-lifetime gate counters
  - get_judge_telemetry(): read-only snapshot
  - reset_judge_telemetry(): zero in-place
  - _record_judge_outcome(): tick counters from judge result

NOT moved here (still in strict_verify.py because tests rebind via
monkeypatch.setattr on strict_verify):
  - _DEFAULT_MODE
  - _UNKNOWN_MODE_WARNED
  - _entailment_mode()
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import threading
import time

# I-bug-100: import openrouter_client as a MODULE reference (not by-value)
# so monkeypatch.setattr on its globals (`PG_MAX_COST_PER_RUN`,
# `_COST_LEDGER_PATH`, etc.) propagates to the cost-accounting code paths
# in this module. Direct `from … import _COST_LEDGER_PATH` would bind
# the value at import time and tests could not override it without
# reloading the module.
#
# I-bug-102 NOTE: this top-level import IS evaluated even in off-mode.
# The "skip clinical_generator import" goal in I-bug-102 is interpreted as
# "no JUDGE INSTANTIATION + no NETWORK CALL in off-mode" (verified by
# `test_off_mode_does_not_instantiate_judge`), NOT as eliminating the
# module-import side effect. Empirically the openrouter_client import
# is ~50ms cold; off-mode users pay this once at strict_verify import
# time. Eliminating it via per-method lazy-import would complicate the
# `except _orc.BudgetExceededError` semantics (exception types must be
# resolved at except-clause evaluation, which is a hot-path call).
# The test asserts the runtime contract; cold-import cost is accepted.
from src.polaris_graph.llm import openrouter_client as _orc

logger = logging.getLogger(__name__)


# I-arch-002 (operator 2026-06-13): default to the sovereign open-weight evaluator GLM-5.1 (was the stale
# non-reasoning "google/gemma-4-31b-it" leftover — #1249/#1252; only env PG_ENTAILMENT_MODEL had masked it).
_DEFAULT_ENTAILMENT_MODEL = "z-ai/glm-5.1"
_ENTAILMENT_TIMEOUT_S = 30.0
# I-arch-006 HANG-J1/J2 (#1262): the entailment JUDGE is the verifier and had NO total deadline — a bare
# float `httpx.Client(timeout=30.0)` makes 30s the per-read GAP timeout, which httpx RESETS on every byte.
# When OpenRouter/Cloudflare holds the socket ESTABLISHED and trickles keep-alive bytes (rx=tx=0 idle-open),
# the 30s timer never fires and a single judge POST runs UNBOUNDED (drb_78 hung the whole run on this; a
# 14-min judge call was observed). Fix: an EXPLICIT httpx.Timeout with a TIGHT read-stall (no bytes for
# `read` seconds → ReadTimeout → the existing bounded same-provider retry reopens a FRESH socket), so a
# genuinely dead socket (the observed rx=tx=0 signature) trips in seconds instead of hanging. httpx closes
# the connection on a ReadTimeout, and explicit keepalive-expiry reaps the half-open CLOSE_WAIT sockets the
# old pooled client leaked on the error path (HANG-J2). Transport/observability only — the verdict logic,
# the fail-CLOSED `judge_error:` sentinel, and the two-family/model lock are all UNCHANGED. (LAW VI: env-driven.)
_ENTAILMENT_CONNECT_S = float(os.getenv("PG_ENTAILMENT_CONNECT_S", "30"))
_ENTAILMENT_READ_STALL_S = float(os.getenv("PG_ENTAILMENT_READ_STALL_S", "120"))
_ENTAILMENT_WRITE_S = float(os.getenv("PG_ENTAILMENT_WRITE_S", "60"))
_ENTAILMENT_POOL_S = float(os.getenv("PG_ENTAILMENT_POOL_S", "30"))
_ENTAILMENT_MAX_KEEPALIVE = int(os.getenv("PG_ENTAILMENT_MAX_KEEPALIVE", "8"))
_ENTAILMENT_KEEPALIVE_EXPIRY_S = float(os.getenv("PG_ENTAILMENT_KEEPALIVE_EXPIRY_S", "30"))
# I-arch-006 HANG-J3 (overnight 2026-06-15): the read-stall (read=_ENTAILMENT_READ_STALL_S) is a per-read
# GAP timeout that httpx RESETS on every received byte. OpenRouter/Cloudflare holds the judge socket
# ESTABLISHED and TRICKLES keep-alive bytes (SSE comment lines / chunked keep-alives), so the gap timer
# never elapses and a SINGLE judge POST runs UNBOUNDED — 15-22 min hangs were observed freezing entire
# iarch006 resume runs (the run can't finish its ~2500 per-claim verifies before one call hangs forever).
# HANG-J1/J2's read-stall only catches a TRULY dead rx=tx=0 socket; it CANNOT bound a trickle. Fix: a HARD
# TOTAL per-call wall-deadline around the blocking POST (below). On timeout the hung socket is force-closed
# (unsticks the worker) and the existing bounded SAME-provider retry reopens a FRESH connection; on
# exhaustion the UNCHANGED fail-CLOSED ('ENTAILED','judge_error:…') sentinel fires (consumers DROP ->
# faithfulness-safe, never fabricates). Transport-only; verdict logic + the fail-closed contract UNCHANGED.
# LAW VI: env-driven. Default 150s comfortably exceeds a real high-effort GLM-5.1 NLI call (~6-40s observed)
# while bounding the trickle hang; with the 2 retries the worst-case wall per claim is ~3*150s before drop.
_ENTAILMENT_TOTAL_S = float(os.getenv("PG_ENTAILMENT_TOTAL_S", "150"))


def _post_with_total_deadline(client, endpoint, headers, json_body, total_s):
    """HANG-J3: run the blocking judge POST under a HARD total wall-deadline.

    httpx's ``read`` timeout is a per-byte GAP that a trickled keep-alive socket resets indefinitely;
    this bounds the WHOLE call so one hung judge POST can never freeze the run. Runs the POST on a
    worker thread and waits at most ``total_s``. On timeout the client is force-closed (so the worker's
    hung read errors out and the thread exits) and ``concurrent.futures.TimeoutError`` is re-raised for
    the caller's bounded retry to reopen a fresh connection. Returns the ``httpx.Response`` on success.
    """
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    fut = ex.submit(client.post, endpoint, headers=headers, json=json_body)
    try:
        return fut.result(timeout=total_s)
    except concurrent.futures.TimeoutError:
        try:
            client.close()  # force the hung socket closed -> the worker's blocked read unblocks + exits
        except Exception:  # noqa: BLE001
            pass
        raise
    finally:
        # Codex P2 (HANG-J3 gate): deterministic executor teardown on EVERY exit path (success, timeout,
        # or a non-timeout client.post exception). wait=False so a still-unsticking worker never blocks us.
        ex.shutdown(wait=False)
# I-transport-001 (#1191) Site 4 (LAW VI — no magic numbers): bounded SAME-provider retry count
# for a single judge call. A transient transport/parse/empty-choices fault on the entailment judge
# previously fell straight through to the fail-open ('ENTAILED','judge_error:…') sentinel, which the
# consumers DROP in enforce mode — an OVER-DROP of a salvageable verdict (the drb_72-class coverage
# collapse). Retry the POST+parse this many extra times before emitting the sentinel; default 2
# (=> up to 3 total attempts). 0 disables the retry (single attempt, the pre-#1191 behavior).
_DEFAULT_ENTAILMENT_RETRIES = 2
# I-arch-007 A2 (entailment-speed fix): a total-deadline (trickle-hang) timeout re-hangs on the SAME
# pinned mirror provider, so the extra same-provider retries are ~_ENTAILMENT_TOTAL_S of dead wait that
# almost never recovers — the dominant contributor to the hang-path worst case (3x150s=450s). Cap a
# total_deadline_exceeded retry TIGHTER than the general transient-fault budget. DEFAULT here PRESERVES
# current behaviour (= the general retry count, so the OFF path is byte-identical, LAW VI); the run slate
# sets PG_ENTAILMENT_TOTAL_DEADLINE_RETRIES=1 to apply the fix (=> up to 2 attempts on a hang vs 3 on a
# transient fault). Faithfulness-NEUTRAL: the verdict emitted on exhaustion is the SAME fail-closed
# ('ENTAILED','judge_error:…') sentinel the consumers DROP — fewer wasted retries, never a different verdict.
_ENV_ENTAILMENT_TOTAL_DEADLINE_RETRIES = "PG_ENTAILMENT_TOTAL_DEADLINE_RETRIES"
_DEFAULT_ENTAILMENT_TOTAL_DEADLINE_RETRIES = _DEFAULT_ENTAILMENT_RETRIES
# Short fixed backoff between judge retries (seconds). Env-overridable per LAW VI.
_DEFAULT_ENTAILMENT_RETRY_BACKOFF_S = 0.5
# I-arch-002 (#1251 sibling): the judge model (GLM-5.1) is a REASONING model; at max_tokens=100 it burned
# the whole budget on its internal reasoning -> finish=length, EMPTY content -> json.loads(None) NoneType
# error -> fail-open, which the consumers DROP -> the drb_72-class COVERAGE COLLAPSE. Operator 2026-06-13:
# reasoning stays MAX. Fix: UN-STARVE the budget so high-effort reasoning COMPLETES + emits the JSON verdict.
#
# I-arch-004 F19 (#1256, §9.1.8 "max_tokens ALWAYS go to the model REAL max — never starve; a generous cap
# is free, billed by usage not pre-allocated"): the old default 2000 was the SMALL hardcode the governance
# rule prohibits — it left the GLM-5.1 judge one provider hiccup away from a finish=length truncation. This
# side-judge pins to the LOCKED mirror provider chain (`get_role_provider("mirror")`, allow_fallbacks=False —
# see judge() below) exactly like the main Mirror role, so its binding output cap is the SAME chain MIN the
# Mirror transport derived from a LIVE OpenRouter read 2026-06-14 (openrouter_role_transport.py:295,
# `_MIRROR_MAX_TOKENS_CHAIN_MIN`): GLM-5.1 mirror chain order=[atlas-cloud, z-ai, baidu, novita, gmicloud]
# -> max_completion_tokens atlas-cloud 202752 / z-ai|baidu|novita 131072 / gmicloud(ctx 202752) -> MIN 131072.
# A budget ABOVE 131072 would hard-400 ("requested N > max M") on the z-ai/baidu/novita fallbacks under
# allow_fallbacks=False; so the default IS the chain MIN (the model REAL max for this pinned chain), and any
# env override is CLAMPED DOWN to that ceiling (env can lower for cost/testing, never raise past the provider
# cap). max_tokens is a usage-billed CAP not a target, so this generous default never starves AND never over-
# bills. Effort stays "high" (NOT xhigh): the Mirror GLM bake-off (openrouter_role_transport.py:700-705,
# scripts/diagnostics/mirror_glm_provider_bakeoff.py, 2026-06-14) proved xhigh is a NO-OP on GLM that lets
# reasoning eat the whole budget -> blank content -> the very collapse F19 closes; "high" completes
# (finish=stop, valid JSON). RE-DERIVE _ENTAILMENT_MAX_TOKENS_CHAIN_MIN if the mirror chain is re-pinned in
# config/settings/openrouter_provider_routing.yaml to higher-cap-only providers.
_ENV_ENTAILMENT_MAX_TOKENS = "PG_ENTAILMENT_MAX_TOKENS"
# Mirror GLM-5.1 chain MIN max_completion_tokens (live OpenRouter read 2026-06-14; mirrors
# openrouter_role_transport._MIRROR_MAX_TOKENS_CHAIN_MIN — kept as a LOCAL constant so this leaf llm module
# does not import the heavy roles/benchmark transport stack at import time, per the off-mode zero-cost rule).
_ENTAILMENT_MAX_TOKENS_CHAIN_MIN = 131072
_DEFAULT_ENTAILMENT_MAX_TOKENS = _ENTAILMENT_MAX_TOKENS_CHAIN_MIN
_ENV_ENTAILMENT_REASONING_EFFORT = "PG_ENTAILMENT_REASONING_EFFORT"
_DEFAULT_ENTAILMENT_REASONING_EFFORT = "high"

# I-arch-011 (verify-speed): provider-ROTATION on a blank/garbled 200. The mirror role pins ONE provider
# with allow_fallbacks=False, so when that provider hits one of its intermittent empty-body-200 windows
# (z-ai measured doing this under account-QPS load, 2026-06-19) OpenRouter does NOT auto-advance (a blank
# IS an HTTP 200), every retry re-hits the SAME blanking host, and the (ENTAILED,'judge_error:…') sentinel
# DROPS the sentence in enforce mode -> a FAITHFUL-but-NARROW breadth collapse. When PG_JUDGE_PROVIDER_ROTATE
# is on, a blank/parse/bad-verdict fault ADVANCES a cursor through the mirror chain's `order`
# (z-ai->baidu->novita->gmicloud) so the NEXT attempt re-POSTs to the next healthy host. Same glm-5.1 model
# on every host (operator pre-approved judge host non-sovereignty 2026-06-13) -> faithfulness-NEUTRAL-to-
# IMPROVING (a real verdict from baidu strictly beats a z-ai-blank-induced drop; a real NEUTRAL/CONTRADICTED
# still drops). Mirrors the PROVEN generator idiom (openrouter_client BlankCompletionError ignore-on-blank,
# I-arch-004 F02 #1255). Default-OFF -> byte-identical single-provider pin; run_gate_b forces it ON for the
# benchmark + a behavioral gate proves it FIRES. LAW VI: env-gated.
_ENV_JUDGE_PROVIDER_ROTATE = "PG_JUDGE_PROVIDER_ROTATE"


def _judge_provider_rotation_enabled() -> bool:
    return os.environ.get(_ENV_JUDGE_PROVIDER_ROTATE, "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _mirror_provider_chain() -> list[str]:
    """The mirror role's ranked provider ``order`` (z-ai, baidu, novita, gmicloud), for blank-rotation.

    Read from the SAME config the single-provider pin uses
    (``config/settings/openrouter_provider_routing.yaml``). Lazy import keeps this leaf llm module free of
    the roles stack at import time (off-mode zero-cost rule). Returns ``[]`` when routing is
    unconfigured/disabled -> the caller keeps its single-provider pin (byte-identical)."""
    try:
        from src.polaris_graph.roles.provider_routing import role_provider_routing  # noqa: PLC0415
        routing = role_provider_routing("mirror")
    except Exception:  # noqa: BLE001 — config lookup must never break the judge
        return []
    if not routing:
        return []
    return [str(p) for p in (routing.get("order") or []) if str(p).strip()]


# I-arch-007 ITEM 2a (entailment-judge self-heal): substrings/types that mark a CLOSED or
# TLS-POISONED httpx transport — the Q78 run-killer was 2866 consecutive
# "Cannot send a request, as the client has been closed" + the `[X509] PEM lib` TLS-state
# corruption from a cross-thread close-while-in-flight on the (previously shared) client. When a
# retry's exception matches one of these, the client is REBUILT before the next attempt (exactly as
# the TimeoutError branch at judge() already does) so a poisoned transport recovers instead of
# bricking the rest of the run. A PARSE fault (json.JSONDecodeError / KeyError / a garbled verdict)
# is deliberately EXCLUDED — those are payload faults, not transport faults, and must retry WITHOUT
# a needless client rebuild. Matched on type/string only; transport/lifecycle, never verdict logic.
# LAW VI: env-extendable extra markers (comma-separated, lower-cased) without a code change.
_TRANSPORT_POISON_SUBSTRINGS: tuple[str, ...] = (
    "client has been closed",
    "clientstate.closed",
    "[x509]",
    "pem lib",
    "ssl",
    "sslerror",
)


def _is_transport_poison(exc: BaseException) -> bool:
    """True iff `exc` indicates a CLOSED/poisoned httpx transport that a fresh client would heal.

    Match is on the exception TYPE name + its string form ONLY (the spec is explicit: NOT a parse
    fault). A `json.JSONDecodeError`/`KeyError`/bad-verdict is a payload fault → returns False →
    retried WITHOUT a rebuild. Extra markers can be supplied via PG_ENTAILMENT_TRANSPORT_POISON_MARKERS
    (comma-separated) per LAW VI; never raises.
    """
    try:
        if isinstance(exc, (json.JSONDecodeError, KeyError, ValueError)):
            # Payload/parse faults are NOT transport poison — explicit exclusion (ValueError covers
            # json.JSONDecodeError's base + the bad-verdict path's string handling). A genuine
            # ssl.SSLError is NOT a subclass of these, so this exclusion never swallows a real
            # transport poison.
            return False
        markers = list(_TRANSPORT_POISON_SUBSTRINGS)
        extra = os.environ.get("PG_ENTAILMENT_TRANSPORT_POISON_MARKERS", "").strip()
        if extra:
            markers.extend(m.strip().lower() for m in extra.split(",") if m.strip())
        haystack = f"{type(exc).__name__}: {exc}".lower()
        return any(marker in haystack for marker in markers)
    except Exception:  # noqa: BLE001 — predicate must never break the retry loop
        return False


def _is_transport_poison_reason(reason: str) -> bool:
    """True iff a carried `_RetryableJudgeError.reason` string names a CLOSED/poisoned transport.

    A `_RetryableJudgeError` loses the original exception TYPE (it carries a human reason string), so
    a poison surfaced via that path is matched on the reason text alone. The bad-verdict reason
    (`bad_verdict=...`) and a generic parse reason never match these transport markers, so they retry
    without a rebuild — same payload-vs-transport asymmetry as `_is_transport_poison`.
    """
    try:
        markers = list(_TRANSPORT_POISON_SUBSTRINGS)
        extra = os.environ.get("PG_ENTAILMENT_TRANSPORT_POISON_MARKERS", "").strip()
        if extra:
            markers.extend(m.strip().lower() for m in extra.split(",") if m.strip())
        haystack = str(reason).lower()
        return any(marker in haystack for marker in markers)
    except Exception:  # noqa: BLE001
        return False


class _RetryableJudgeError(Exception):
    """I-transport-001 (#1191) Site 4: a transient/recoverable judge fault that should trigger a
    bounded SAME-provider retry. Carries the human-readable `reason` used for the terminal
    ('ENTAILED','judge_error: <reason>') sentinel so a bad-verdict's `bad_verdict=<v>` detail is
    preserved across retries instead of being collapsed into a generic exception type name."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
_ENTAILMENT_PROMPT = """You are a strict entailment judge. You will be given a SPAN of source text and a SENTENCE that cites that span. Decide whether the SPAN entails the SENTENCE.

Rules:
- ENTAILED: every factual assertion in the SENTENCE is supported by the SPAN. Conservative paraphrase is allowed.
- NEUTRAL: the SENTENCE introduces a fact, entity, mechanism, or specificity NOT present in the SPAN (e.g. SPAN says "GLP-1 RAs", SENTENCE says "semaglutide"; SPAN says "adipocyte metabolism", SENTENCE adds "lipid metabolism" or "energy storage"; SPAN has numbers but not the specific claim being made).
- CONTRADICTED: the SENTENCE asserts something the SPAN explicitly disagrees with.

Return STRICT JSON only, no prose:
{{"verdict": "ENTAILED" | "NEUTRAL" | "CONTRADICTED", "reason": "<one short sentence>"}}

SPAN:
{span}

SENTENCE:
{sentence}

JSON:"""


def _select_entailment_prompt() -> str:
    """I-faith-006 (#1180): return the active entailment-prompt template.

    Default (``PG_ENTAILMENT_PROMPT_VARIANT`` unset/"baseline"/unknown) -> the canonical
    ``_ENTAILMENT_PROMPT`` above, BYTE-IDENTICAL to pre-#1180. A widening-aware candidate
    ("widen_a"/"widen_b"/"widen_c") is returned ONLY when explicitly selected — the bakeoff
    (`scripts/dr_benchmark/widening_prompt_bakeoff.py`) scores the candidates against the labeled set
    and the empirical winner is wired by setting this env in the run slate. Read at call time so the
    bakeoff/tests can switch variants without re-import."""
    variant = os.environ.get("PG_ENTAILMENT_PROMPT_VARIANT", "baseline").strip().lower()
    if variant in ("", "baseline"):
        return _ENTAILMENT_PROMPT
    # Lazy import keeps this leaf module free of the candidates dependency in the default path.
    from src.polaris_graph.llm.widening_prompt_candidates import WIDENING_VARIANTS  # noqa: PLC0415

    return WIDENING_VARIANTS.get(variant, _ENTAILMENT_PROMPT)


class _EntailmentJudge:
    """Synchronous httpx wrapper around an OpenRouter entailment call.

    Lazy-initialized via _get_judge() so import-time cost is zero when
    PG_STRICT_VERIFY_ENTAILMENT=off (the default before I-bug-095).
    """

    def __init__(self) -> None:
        import httpx  # local import: avoid forcing the dep when off

        # Lazy-import the family-segregation check so the off-mode path
        # never touches openrouter_client. The judge is acting as a
        # content evaluator (Layer-2), so it MUST differ from the
        # generator family per CLAUDE.md §9.1.1 — fail at construction
        # if PG_ENTAILMENT_MODEL is in the same family as PG_GENERATOR_MODEL.
        from src.polaris_graph.llm.openrouter_client import check_family_segregation

        api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "PG_STRICT_VERIFY_ENTAILMENT requires OPENROUTER_API_KEY"
            )
        self._api_key = api_key
        # I-sov-001: endpoint is env-configurable so the sovereign deploy
        # can point the entailment judge at the OVH H200 vLLM endpoint
        # (set OPENROUTER_BASE_URL=http://<priv-ip>:8000/v1). Default keeps
        # OpenRouter. Mirrors openrouter_client.py:43-45.
        base_url = os.environ.get(
            "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
        ).rstrip("/")
        self._endpoint = f"{base_url}/chat/completions"
        self._model = os.environ.get(
            "PG_ENTAILMENT_MODEL", _DEFAULT_ENTAILMENT_MODEL
        )
        # Two-family invariant per §9.1.1: raises RuntimeError if the
        # entailment judge ends up in the same family as the generator
        # (e.g. an operator setting PG_ENTAILMENT_MODEL to a DeepSeek
        # variant when PG_GENERATOR_MODEL is also DeepSeek). The
        # default model (google/gemma-4-31b-it) is in a different
        # family from DeepSeek by construction.
        check_family_segregation(evaluator_model=self._model)
        # I-arch-007 ITEM 2a (thread-safety): the judge is a process-lifetime SINGLETON (_get_judge)
        # shared across the ThreadPoolExecutor verifier workers. A SHARED mutable httpx client that one
        # worker force-closes (the HANG-J3 total-deadline path) while a sibling is mid-`post` is exactly
        # the cross-thread close-while-in-flight race that produced Q78's `[X509] PEM lib` TLS-state
        # corruption (httpx Discussion #1633 / httpcore #550 explicitly discourage it). Fix: give each
        # worker thread its OWN client via threading.local(); the force-close/rebuild in
        # _post_with_total_deadline then only ever touches the calling thread's client. The `_tls` store
        # MUST exist before the first `self._client` access below (the property reads it).
        self._tls = threading.local()
        # I-arch-006 HANG-J1/J2 (#1262) + HANG-J3 (2026-06-15): build via _build_client so the HANG-J3
        # total-deadline path can force-close + REBUILD a fresh client after a trickle hang.
        self._client = self._build_client()

    @property
    def _client(self):
        """The current thread's httpx judge client (I-arch-007 ITEM 2a — thread-local).

        Lazily builds a per-thread client on first read (each verifier worker gets its OWN client,
        so a sibling's force-close can never poison this thread's transport) and HEALS a closed one
        on the next read. The `is_closed is True` guard is deliberate: a real httpx client exposes a
        BOOL `is_closed`, but injected test doubles do not — a `MagicMock().is_closed` is a truthy
        child mock (NOT `is True`) and a `_FakeJudgeClient` has no such attr (defaults False via
        getattr), so neither spuriously triggers a rebuild that would replace the injected stub. This
        keeps every existing `judge._client = <stub>` test contract byte-intact while only a genuinely
        CLOSED real client self-heals.
        """
        client = getattr(self._tls, "client", None)
        if client is None or getattr(client, "is_closed", False) is True:
            client = self._build_client()
            self._tls.client = client
        return client

    @_client.setter
    def _client(self, value) -> None:
        # Preserve the existing test-injection contract (`judge._client = <stub/MagicMock>`): writes go
        # to THIS thread's thread-local slot, and a subsequent read returns the same object. Production
        # rebuild sites (`self._client = self._build_client()`) likewise rebind only the calling thread's
        # client — the thread-safety guarantee.
        self._tls.client = value

    def _build_client(self):
        """Construct the entailment httpx client. HANG-J1/J2: explicit per-phase read-stall (a dead
        rx=tx=0 socket trips fast and the retry reopens) + bounded keepalive so half-open CLOSE_WAIT
        sockets are reaped. The HANG-J3 total-deadline (see judge()) bounds a TRICKLED socket the
        read-stall alone cannot. Verdict logic untouched."""
        import httpx  # local import: avoid forcing the dep when off

        # BUG 3 (X509 SSL race): pass the process-wide shared, cert-verifying
        # ssl.SSLContext so httpx does NOT re-parse the PEM bundle on this
        # per-thread client build. The Q78 run-killer was concurrent thread-local
        # entailment client construction racing ssl.create_default_context's
        # PEM parse -> `[X509] PEM lib`. TLS verification stays ENABLED — the
        # shared context is CERT_REQUIRED + check_hostname (verify-neutral).
        from src.utils.shared_ssl_context import get_shared_ssl_context
        return httpx.Client(
            verify=get_shared_ssl_context(),
            timeout=httpx.Timeout(
                connect=_ENTAILMENT_CONNECT_S,
                read=_ENTAILMENT_READ_STALL_S,
                write=_ENTAILMENT_WRITE_S,
                pool=_ENTAILMENT_POOL_S,
            ),
            limits=httpx.Limits(
                max_keepalive_connections=_ENTAILMENT_MAX_KEEPALIVE,
                keepalive_expiry=_ENTAILMENT_KEEPALIVE_EXPIRY_S,
            ),
        )

    def judge(self, sentence: str, span: str) -> tuple[str, str]:
        """Return (verdict, reason).

        verdict is one of "ENTAILED", "NEUTRAL", "CONTRADICTED".

        I-transport-001 (#1191) Site 4: a transient transport/parse/empty-choices/bad-verdict
        fault is now RETRIED on the same provider up to `PG_ENTAILMENT_RETRIES` extra times
        (default 2 => 3 total attempts; env-driven per LAW VI) before the method emits the
        ('ENTAILED', 'judge_error: ...') sentinel on exhaustion. This is NOT a fail-OPEN: both
        consumers FAIL CLOSED on that sentinel — `clinical_generator/strict_verify.py:295-301`
        keys on the `judge_error:` PREFIX alone (drops in enforce); `provenance_generator.py:1795`
        sets `judge_error_flag` on `verdict=='ENTAILED' AND reason.startswith('judge_error:')`
        (consumed -> drop). The sentinel stays EXACTLY ('ENTAILED', 'judge_error: ...') so that
        detection is preserved (do NOT flip to NEUTRAL standalone — that bypasses the
        provenance detection at :1795). The retry's only effect is to stop a SINGLE transient
        judge fault from OVER-DROPPING a salvageable verdict (the drb_72-class coverage collapse),
        without loosening the binding faithfulness gate.

        I-bug-100: after each successful httpx call this method records
        the call cost via openrouter_client's module-level helpers
        (`_add_run_cost`, `check_run_budget`, `_COST_LEDGER_PATH`) so
        judge spend is visible to the per-run budget cap and the cost
        ledger. `BudgetExceededError` is explicitly re-raised before
        the broad retry/fail-closed handler so a cap breach aborts the
        sweep cleanly instead of being masked as a transient judge error
        or being retried.
        """
        prompt = _select_entailment_prompt().format(span=span, sentence=sentence)
        started = time.monotonic()
        # I-bug-946 (#932): when Path-B gate is active, force singleton provider routing in
        # the request body to match the resolved-at-preflight per-role provider. Without this,
        # this direct httpx path bypasses the gate's routing intent (the OpenRouterClient path
        # also got the override via openrouter_client.py:1400-1410). Codex iter-2 P1#2.
        # Codex iter-1 diff P1#2: this lookup MUST use an explicit role string, NOT the ambient
        # _ROLE contextvar. The entailment judge fires during section generation (where
        # _ROLE=="generator"), but it posts the evaluator-family model — using the ambient role
        # would route the judge model to the generator's provider.
        # I-arch-004 F09: route via "mirror" (the LOCKED 4-role key), NOT the RETIRED "evaluator"
        # key. The preflight-resolved role_provider_map only carries generator/mirror/sentinel/judge
        # (pathB_runner._LOCKED_ROLES); the legacy "evaluator" key is absent, so get_role_provider(
        # "evaluator") returned None -> NO provider pin -> this side-judge FREE-ROUTED to an unpinned
        # provider instead of the locked mirror chain. Per polaris_runtime_lock.yaml:legacy_compat
        # the retired evaluator role maps_to_role: mirror (GLM-5.1), so the side-judge pins to the
        # SAME provider chain as the main mirror role (allow_fallbacks=False, require_parameters=True).
        try:
            from src.polaris_graph.benchmark import pathB_capture as _pathb_for_routing
            _gate_provider = _pathb_for_routing.get_role_provider("mirror")
        except Exception:
            _gate_provider = None
        # Operator 2026-06-13: reasoning stays MAX; any sub-max/off effort is coerced UP to high so the
        # NLI verdict is never starved. Un-starved max_tokens lets the high-effort reasoning complete AND
        # emit the JSON verdict (the old max_tokens=100 truncated mid-reasoning -> empty -> coverage collapse).
        _ent_effort = (os.environ.get(_ENV_ENTAILMENT_REASONING_EFFORT, "").strip().lower()
                       or _DEFAULT_ENTAILMENT_REASONING_EFFORT)
        if _ent_effort not in ("high", "xhigh"):
            _ent_effort = _DEFAULT_ENTAILMENT_REASONING_EFFORT
        try:
            _ent_maxtok = max(256, int(os.environ.get(_ENV_ENTAILMENT_MAX_TOKENS, _DEFAULT_ENTAILMENT_MAX_TOKENS)
                                       or _DEFAULT_ENTAILMENT_MAX_TOKENS))
        except (TypeError, ValueError):
            _ent_maxtok = _DEFAULT_ENTAILMENT_MAX_TOKENS
        # I-arch-004 F19 (§9.1.8): clamp DOWN to the pinned mirror-chain MIN so a future bad env override can
        # never push max_tokens past the provider cap and hard-400 the judge under allow_fallbacks=False (the
        # default already IS the chain MIN; env can only lower it for cost/testing, never raise past the cap).
        _ent_maxtok = min(_ent_maxtok, _ENTAILMENT_MAX_TOKENS_CHAIN_MIN)
        json_body: dict = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": _ent_maxtok,
            "reasoning": {"effort": _ent_effort},
            "response_format": {"type": "json_object"},
        }
        # I-arch-002 (#1250): operator-directed — skip the single-provider pin when
        # PG_ROLE_ALLOW_FALLBACKS is set so the open-weight evaluator model free-routes to its
        # fastest provider (the model is the sovereign unit; hosting provider may be US/China).
        _free_route = os.environ.get("PG_ROLE_ALLOW_FALLBACKS", "").strip().lower() in (
            "1", "true", "yes", "on",
        )
        # I-arch-011: provider-rotation chain. When rotation is enabled, the mirror `order`
        # (z-ai->baidu->novita->gmicloud) is walked one-host-per-attempt by the retry loop on a
        # blank/garbled 200. `_provider_cursor` is the current index; the first attempt pins the chain
        # LEAD (== _gate_provider, so byte-identical to the single-pin first attempt). Empty/disabled ->
        # [] -> the loop never rotates and the single-provider pin below is authoritative.
        _rotate_chain: list[str] = (
            _mirror_provider_chain() if (_gate_provider and not _free_route
                                         and _judge_provider_rotation_enabled()) else []
        )
        _provider_cursor = 0
        if _gate_provider and not _free_route:
            json_body["provider"] = {
                "order": [_rotate_chain[0] if len(_rotate_chain) > 1 else _gate_provider],
                "allow_fallbacks": False,
                "require_parameters": True,
            }

        def _rotate_provider_on_blank(reason: str) -> bool:
            """Advance the pinned provider to the NEXT mirror-chain host on a blank/parse/bad-verdict
            fault (NOT a transport-poison — those rebuild THIS thread's client + retry the SAME host).
            Returns True iff it actually advanced (so the caller can log it). Faithfulness-neutral:
            same glm-5.1 model, next healthy host; the verdict the next host returns is the real verdict."""
            nonlocal _provider_cursor
            if len(_rotate_chain) <= 1 or "provider" not in json_body:
                return False
            if _provider_cursor >= len(_rotate_chain) - 1:
                return False  # exhausted the chain — let the bounded retry fail closed
            _provider_cursor += 1
            json_body["provider"]["order"] = [_rotate_chain[_provider_cursor]]
            logger.warning(
                "[entailment] provider-rotate on %s: -> %s (chain pos %d/%d)",
                reason, _rotate_chain[_provider_cursor], _provider_cursor + 1, len(_rotate_chain),
            )
            return True

        def _emit_raw_io(status: str, raw_response, duration_ms=None) -> None:
            # I-obs-001 #1141 AC3 (gate iter-1 P1): single capture point so a judge call emits EXACTLY
            # one raw-IO record tagged by its TRUE outcome — "ok" ONLY after a validated verdict;
            # "judge_error" on bad_verdict / parse-failure / transport fail-open. Default-OFF; never raises.
            try:
                _io_sink = _orc.current_raw_io_sink()
                if _io_sink is None:
                    return
                import uuid as _uuid
                _io_sink.record(
                    call_id=_uuid.uuid4().hex, call_type="entailment_judge", role="evaluator",
                    request={**json_body, "messages": [{"role": "user", "content": prompt}]},
                    raw_response=raw_response, duration_ms=duration_ms, status=status,
                )
            except Exception:  # noqa: BLE001
                pass

        # I-transport-001 (#1191) Site 4: bounded SAME-provider retry around post+parse+budget+
        # verdict (LAW VI — env-driven bounds). A single transient transport/parse/empty-choices/
        # bad-verdict fault now RETRIES instead of immediately fail-closing the verdict (which the
        # consumers DROP -> over-drop of a salvageable verdict, the drb_72-class coverage collapse).
        _retries = max(0, int(os.environ.get("PG_ENTAILMENT_RETRIES", _DEFAULT_ENTAILMENT_RETRIES)))
        # I-arch-007 A2: the tighter cap that applies ONLY to a total_deadline_exceeded (trickle-hang)
        # retry. Never exceeds _retries (a total-deadline cap above the general cap is meaningless).
        # Unset -> equals _retries -> byte-identical to the pre-fix path.
        _total_deadline_retries = min(
            _retries,
            max(0, int(os.environ.get(
                _ENV_ENTAILMENT_TOTAL_DEADLINE_RETRIES, _DEFAULT_ENTAILMENT_TOTAL_DEADLINE_RETRIES
            ))),
        )
        _backoff = max(
            0.0,
            float(os.environ.get(
                "PG_ENTAILMENT_RETRY_BACKOFF_S", _DEFAULT_ENTAILMENT_RETRY_BACKOFF_S
            )),
        )
        data = None  # I-obs-001 #1141 AC3: bound before the loop so the terminal judge_error
        # capture can prefer the served response (post ok, parse/verdict failed) over the exc string.
        last_reason = ""
        for attempt in range(_retries + 1):
            data = None  # reset per attempt so a later attempt's terminal capture is not stale.
            try:
                # I-arch-006 HANG-J3: HARD total wall-deadline around the POST so a trickled keep-alive
                # socket (read-gap timer never fires) cannot hang the run. On timeout: force-close +
                # rebuild a fresh client, then raise the RETRYABLE error so the bounded retry reopens.
                try:
                    response = _post_with_total_deadline(
                        self._client,
                        self._endpoint,
                        {
                            "Authorization": f"Bearer {self._api_key}",
                            "Content-Type": "application/json",
                        },
                        json_body,
                        _ENTAILMENT_TOTAL_S,
                    )
                except concurrent.futures.TimeoutError:
                    self._client = self._build_client()  # old one was force-closed in the helper
                    raise _RetryableJudgeError(
                        f"total_deadline_exceeded_{int(_ENTAILMENT_TOTAL_S)}s"
                    )
                response.raise_for_status()
                data = response.json()

                # I-safety-002b (#925): Path-B gate capture. The entailment judge is the
                # evaluator-family LLM call that bypasses OpenRouterClient (direct httpx),
                # so without capturing here the gate's two-family completeness check would
                # be a silent no-op. Best-effort + gate-flagged; lazy import keeps off-mode
                # import cost zero. `data` is the genuinely-served non-stream JSON.
                try:
                    from src.polaris_graph.benchmark import pathB_capture as _pathb
                    if _pathb.is_active():
                        _pathb.capture_llm_call(
                            role="evaluator",
                            messages=[{"role": "user", "content": prompt}],
                            raw_response=data,
                        )
                except Exception:  # noqa: BLE001 — capture must never break the judge
                    pass

                # I-bug-100: cost recording. Reads + records BEFORE verdict
                # parse so a cap breach aborts the sweep regardless of
                # downstream parse outcome. Each real POST (incl. a retried one) bills its OWN
                # tokens — correct, real money was spent — so this runs inside the loop per attempt.
                usage = data.get("usage", {}) or {}
                input_tokens = int(usage.get("prompt_tokens", 0) or 0)
                output_tokens = int(usage.get("completion_tokens", 0) or 0)
                api_cost = float(usage.get("cost", 0) or 0)
                actual_cost = api_cost or _orc._impute_cost_from_tokens(
                    self._model, input_tokens, output_tokens, 0,
                )
                # I-bug-100 iter-1 diff P2 fix: when the entire usage block
                # is absent, both api_cost and the imputed value are 0, which
                # silently bypasses the budget guard. Fall back to a
                # conservative estimate based on typical judge-call shape
                # (~500 prompt + ~100 completion tokens) priced at Opus-tier
                # so the budget cap is preserved on degraded responses.
                if actual_cost == 0 and not usage:
                    actual_cost = _orc._impute_cost_from_tokens(
                        self._model, 500, 100, 0,
                    )
                _orc._add_run_cost(actual_cost)
                duration_ms = (time.monotonic() - started) * 1000.0
                try:
                    _append_judge_ledger_entry(
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        duration_ms=duration_ms,
                        actual_cost=actual_cost,
                    )
                except Exception as exc:  # noqa: BLE001 — ledger IO is non-critical
                    logger.warning("entailment ledger write failed: %s", exc)
                _orc.check_run_budget(0)  # raises BudgetExceededError if cap breached

                content = data["choices"][0]["message"]["content"]
                if _rotate_chain and not (content or "").strip():
                    # I-arch-011: a blank-200 (empty/None content body) is the z-ai intermittent-window
                    # signature. Raise the RETRYABLE error so the loop ROTATES to the next mirror host
                    # below instead of re-POSTing the same blanking provider and exhausting into a
                    # judge_error DROP. Cost was already recorded above. (Rotation-gated -> OFF path is
                    # byte-identical: an empty/None content still flows to json.loads as before.)
                    raise _RetryableJudgeError("blank_200")
                parsed = json.loads(content)
                verdict = str(parsed.get("verdict", "")).upper().strip()
                reason = str(parsed.get("reason", ""))
                if verdict not in ("ENTAILED", "NEUTRAL", "CONTRADICTED"):
                    # Bad verdict = a recoverable failed verification: raise the RETRYABLE error so a
                    # transient garbled verdict re-issues. The reason (with bad_verdict=<v>) is
                    # preserved for the terminal sentinel on exhaustion.
                    raise _RetryableJudgeError(f"bad_verdict={verdict!r}")
                # Validated verdict → the ONE success raw-IO record, AFTER parse (gate iter-1 P1).
                _emit_raw_io("ok", data, duration_ms=(time.monotonic() - started) * 1000.0)
                return verdict, reason
            except _orc.BudgetExceededError:
                # I-bug-100: do NOT fail-open OR retry on cap breach. Propagate immediately so the
                # sweep aborts with a clear cause (this except MUST stay FIRST/outside the retry).
                raise
            except _RetryableJudgeError as exc:
                last_reason = exc.reason
                # I-arch-007 A2: a trickle-hung socket re-hangs on retry, so a total_deadline_exceeded
                # gets the tighter _total_deadline_retries budget; transient transport/parse/bad-verdict
                # faults (which often DO recover on a fresh attempt) keep the full _retries budget.
                _eff_retries = (
                    _total_deadline_retries
                    if exc.reason.startswith("total_deadline_exceeded")
                    else _retries
                )
                if attempt < _eff_retries:
                    # I-arch-007 ITEM 2a: if the retryable reason reflects a CLOSED/poisoned transport,
                    # rebuild this thread's client BEFORE the retry (the total_deadline_exceeded path
                    # already rebuilt at :441; this covers a poison surfaced as a _RetryableJudgeError
                    # reason). A bad_verdict / parse reason is NOT poison -> no needless rebuild.
                    if _is_transport_poison(exc) or _is_transport_poison_reason(exc.reason):
                        self._client = self._build_client()
                    elif not exc.reason.startswith("total_deadline_exceeded"):
                        # I-arch-011: a blank_200 / bad_verdict from THIS provider — rotate to the next
                        # mirror host so the retry can get a REAL verdict (faithfulness-neutral: same
                        # glm-5.1 model, next healthy host). No-op when rotation is disabled. A
                        # total_deadline_exceeded keeps its existing same-provider tighter-retry path.
                        _rotate_provider_on_blank(exc.reason)
                    logger.warning(
                        "entailment judge retryable fault (attempt %d/%d): %s — retrying.",
                        attempt + 1, _eff_retries + 1, exc.reason,
                    )
                    time.sleep(_backoff)
                    continue
                break
            except Exception as exc:  # noqa: BLE001 — transient transport/parse fault: retry then fail-closed
                last_reason = type(exc).__name__
                if attempt < _retries:
                    # I-arch-007 ITEM 2a (the Q78 run-killer): the only rebuild sites before this fix
                    # were the ctor and the TimeoutError branch (:441), so a client closed/poisoned on
                    # this GENERIC path (httpx "Cannot send a request, as the client has been closed",
                    # an SSL/X509/PEM TLS-state fault) was TERMINAL — Q78 logged 2866 consecutive
                    # "client has been closed" over 33 min, only 21 judge calls ever succeeded, 177
                    # sentences fail-closed-DROPPED -> abort_excessive_gap. Heal it: rebuild THIS thread's
                    # client before the retry, exactly as the TimeoutError branch does. A parse fault
                    # (json/KeyError) is NOT poison -> excluded -> retried without a needless rebuild.
                    if _is_transport_poison(exc):
                        self._client = self._build_client()
                    else:
                        # I-arch-011: a non-poison transport/parse fault (a JSONDecodeError on a garbled
                        # body, a KeyError on a malformed envelope, or an HTTP 4xx/5xx such as a provider
                        # that 404s on this request shape) — rotate to the next mirror host before the
                        # retry. No-op when rotation is disabled.
                        _rotate_provider_on_blank(type(exc).__name__)
                    logger.warning(
                        "entailment judge error (attempt %d/%d): %s — retrying.",
                        attempt + 1, _retries + 1, exc,
                    )
                    time.sleep(_backoff)
                    continue
                logger.warning("entailment judge error (final): %s", exc)
                break

        # Retries exhausted: emit EXACTLY ONE terminal judge_error record (no per-attempt emits) and
        # return the fail-CLOSED-at-consumer sentinel. Prefer the bound served data (a parse/verdict
        # failure on a real response) over a bare error string. The sentinel stays ENTAILED+prefix so
        # both consumers DROP it (see method docstring + §5 DIVERGENCE in the brief).
        _emit_raw_io("judge_error", data if data is not None else {"error": last_reason})
        return "ENTAILED", f"judge_error: {last_reason}"


def _append_judge_ledger_entry(
    *,
    input_tokens: int,
    output_tokens: int,
    duration_ms: float,
    actual_cost: float,
) -> None:
    """Append a single entailment-judge call to the cost ledger.

    Schema mirrors `openrouter_client.OpenRouterClient._append_ledger`
    (line ~481-491) so per-run filters that key on `session_id` /
    `call_type` (e.g., scripts/run_honest_sweep_r3.py) include judge
    calls without code changes downstream.

    All `_orc.<attr>` accesses go through the module reference so
    test monkeypatch.setattr on `openrouter_client._COST_LEDGER_PATH`
    propagates correctly.
    """
    # FX-11 (BUG-10): route through the SINGLE canonical cost-ledger writer, which bumps the shared,
    # monotonic per-session accumulator and appends the row atomically (NOT current_run_cost(),
    # which is reset per parallel four-role worker). Best-effort I/O is handled inside the writer.
    _orc.append_cost_ledger_row(
        session_id=_orc._CURRENT_RUN_ID_CTX.get() or "no_run_id",
        call_type="entailment_judge",
        cost_usd=actual_cost,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        duration_ms=duration_ms,
    )


_JUDGE_SINGLETON: _EntailmentJudge | None = None


def _get_judge() -> _EntailmentJudge:
    """Lazy singleton so off-mode pays zero import/connection cost."""
    global _JUDGE_SINGLETON
    if _JUDGE_SINGLETON is None:
        _JUDGE_SINGLETON = _EntailmentJudge()
    return _JUDGE_SINGLETON


# I-bug-096: process-lifetime telemetry counters for the entailment gate.
# In enforce mode the judge fail-open path returns ("ENTAILED",
# "judge_error: ...") on transient API errors. A persistent OpenRouter
# outage or model-format change could make the 6th check silently inert
# — every sentence falls through as ENTAILED while WARNING lines
# accumulate. These counters give an operator a concise "the gate ran N
# times, M of those errored" signal.
#
# Counters are gate-side (not judge-side) per the original I-bug-092
# brief verdict: gate behavior is what we want to measure, not a
# specific judge implementation. Tests with FakeJudge tick these too,
# and a future swapped judge cannot bypass the judge_error counter.
_JUDGE_TELEMETRY: dict[str, int] = {
    "calls": 0,
    "entailed": 0,
    "neutral": 0,
    "contradicted": 0,
    "judge_error": 0,
}

# FX-09 (I-ready-017): per-RUN, concurrency-isolated judge counters. The process-
# lifetime _JUDGE_TELEMETRY above is shared across threads, so a per-run
# judge_error_rate computed from its delta is contaminated when two runs share one
# process (the v6 Dramatiq worker runs `asyncio.run(run_one_query(...))` under
# `--threads 2`). A ContextVar is isolated per OS-thread AND per asyncio Task, so each
# run that calls begin_run_judge_telemetry() gets its OWN {calls, judge_error}
# counter. The global counter (health endpoint) is unaffected.
import contextvars  # noqa: E402  (kept next to the counters it scopes)

_RUN_JUDGE_TELEMETRY: contextvars.ContextVar[dict[str, int] | None] = (
    contextvars.ContextVar("_run_judge_telemetry", default=None)
)


def begin_run_judge_telemetry() -> dict[str, int]:
    """Start a per-run, concurrency-isolated judge counter and return it.

    Bind a fresh {calls, judge_error} dict to the contextvar for THIS run. The judge
    ticks both the process-lifetime counter and (if set) this per-run dict. Read the
    returned dict at the end of the run for an isolated denominator — never
    contaminated by a sibling run sharing the process (FX-09 #1114). Sequential calls
    in one context each rebind to a fresh dict, so no reset is required for
    correctness; the previous run's dict is simply replaced.
    """
    tel = {"calls": 0, "judge_error": 0}
    _RUN_JUDGE_TELEMETRY.set(tel)
    return tel


def get_judge_telemetry() -> dict[str, int]:
    """Snapshot of process-lifetime entailment-judge counters.

    Read once before a job to compute deltas if needed. Operators
    concerned that the gate has gone silently inert can poll this from
    a health endpoint or scripts/observability tooling and alert on
    judge_error rate.
    """
    return dict(_JUDGE_TELEMETRY)


def reset_judge_telemetry() -> None:
    """Zero all judge telemetry counters in-place.

    Public so operators can deliberately reset between jobs / runs.
    Tests use this for isolation; production callers can use it to
    bound the counter arithmetic to a single run window.
    """
    for key in _JUDGE_TELEMETRY:
        _JUDGE_TELEMETRY[key] = 0


def _record_judge_outcome(verdict: str, reason: str) -> None:
    """Tick the appropriate counter based on judge return values.

    Normalizes the existing judge fail-open contract: when reason
    starts with 'judge_error:', the call errored and was returned as
    ENTAILED to keep the run alive. We tick judge_error in that case
    instead of entailed so an operator can distinguish "gate accepted
    the sentence" from "gate failed open."
    """
    _JUDGE_TELEMETRY["calls"] += 1
    # FX-09: also tick the per-run, concurrency-isolated counter if a run scope is active.
    _run_tel = _RUN_JUDGE_TELEMETRY.get()
    if _run_tel is not None:
        _run_tel["calls"] += 1
    if reason.startswith("judge_error:"):
        _JUDGE_TELEMETRY["judge_error"] += 1
        if _run_tel is not None:
            _run_tel["judge_error"] += 1
        return
    key = verdict.lower()
    if key in _JUDGE_TELEMETRY:
        _JUDGE_TELEMETRY[key] += 1
