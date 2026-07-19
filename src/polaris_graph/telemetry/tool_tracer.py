"""Per-tool utilization tracer (I-meta-007b).

A thread-safe, spend-free, network-free recorder of external tool / API
invocations made during a single pipeline-A run (pipeline A). Each call
site (Serper search, Semantic Scholar search, content fetch, ...) records a
:class:`ToolCall` describing the outcome — never changing the call's own
behavior or return value.

Design (verified spec ``.codex/I-meta-007/_wiring_specs.txt`` LANE
``wire:tool-tracker``):

* :class:`ToolCall` — one invocation (tool name, target, status, latency,
  bytes, backend, error, free-form metadata, UTC timestamp).
* :class:`ToolTracer` — thread-safe buffer. ``record()`` appends to an
  in-memory list AND (when a ``run_dir`` is set) to ``run_dir/tool_trace.jsonl``.
  ``manifest()`` returns a per-tool summary: ``total_calls``, ``ok_count``,
  ``fail_count``, ``success_rate``, ``latency_stats`` (min/max/mean/p95),
  ``error_reasons`` histogram, and ``backends_used``.
* :func:`get_tool_tracer` — process-global singleton.
* :func:`reset_tool_tracer` — clears the singleton (per-query reset in the
  sweep loop + isolation between tests).

The tracer is purely observational. Call sites MUST wrap ``record()`` in
``try/except`` so a tracer error can never break retrieval (the tracer is
also internally defensive: disk-write failures are swallowed + logged).
"""
from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("polaris_graph.telemetry.tool_tracer")

# Env gate (shared, single truthy convention). The tracer is ON by default so
# the per-run summary is produced; set PG_ENABLE_TOOL_TRACKER=0 to make every
# tracer hook a pure no-op (no tool_trace.jsonl, no tool_summary.json, no
# manifest['tool_utilization'] key — OFF-mode byte-identity).
TOOL_TRACKER_ENV = "PG_ENABLE_TOOL_TRACKER"
_TOOL_TRACKER_TRUTHY = ("1", "true", "True")


def tool_tracker_enabled() -> bool:
    """True iff PG_ENABLE_TOOL_TRACKER selects ON (default ON).

    Single source of truth for the gate so every call site (run wiring,
    _trace_tool in live_retriever, and :func:`attach_tool_utilization`) uses
    the identical truthy convention.
    """
    return os.environ.get(TOOL_TRACKER_ENV, "1").strip() in _TOOL_TRACKER_TRUTHY

# Canonical status values. Record-only: unknown statuses are accepted (any
# value other than "ok" counts as a non-success in the manifest), but these
# are the intended vocabulary so call sites stay consistent.
STATUS_OK = "ok"
STATUS_FAIL = "fail"
STATUS_STUB = "stub"
STATUS_PAYWALL = "paywall"
STATUS_TIMEOUT = "timeout"
STATUS_RETRY = "retry"
STATUS_TRUNCATED = "truncated"

# Truncation caps (avoid unbounded targets / error strings in the trace).
_TARGET_MAX_CHARS = 256
_ERROR_MAX_CHARS = 200
# Error-histogram key cap (mirrors the spec: first token of the error,
# capped) so transient detail (e.g. a long URL) does not explode the bucket.
_ERROR_KEY_MAX_CHARS = 40


def _utc_now_iso() -> str:
    """Current UTC timestamp as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ToolCall:
    """A single tool / API invocation outcome (record-only)."""

    tool_name: str
    target: str
    status: str
    latency_ms: float
    bytes_sent: int = 0
    bytes_received: int = 0
    backend_used: str = ""
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    # Per spec RISK #5: the timestamp is captured by ToolTracer.record() at
    # the moment of recording and passed in explicitly, NOT defaulted in the
    # dataclass (which would fire lazily and skew ordering). A default keeps
    # direct construction valid for tests.
    timestamp: str = field(default_factory=_utc_now_iso)


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Nearest-rank percentile of an already-sorted, non-empty list.

    ``pct`` is a fraction in [0, 1]. Uses the same index convention as the
    verified spec (``sorted[int(pct * n)]`` clamped to the last element).
    """
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    idx = int(pct * n)
    if idx >= n:
        idx = n - 1
    return sorted_values[idx]


class ToolTracer:
    """Thread-safe per-run recorder of external tool/API invocations."""

    def __init__(self, run_dir: Optional[Path] = None) -> None:
        self.run_dir: Optional[Path] = Path(run_dir) if run_dir is not None else None
        self._calls: list[ToolCall] = []
        self._lock = threading.Lock()
        self._call_log_path: Optional[Path] = (
            self.run_dir / "tool_trace.jsonl" if self.run_dir is not None else None
        )

    # ── recording ────────────────────────────────────────────────────────
    def record(
        self,
        tool_name: str,
        target: str = "",
        status: str = STATUS_OK,
        latency_ms: float = 0.0,
        bytes_sent: int = 0,
        bytes_received: int = 0,
        backend_used: str = "",
        error: str = "",
        **metadata: Any,
    ) -> None:
        """Record one tool call. Thread-safe and fail-safe.

        A tracer-internal failure (e.g. a non-serializable metadata value, a
        disk error) is swallowed + logged so the caller's retrieval is never
        broken. Callers SHOULD still wrap this in try/except as a second
        layer of defense.
        """
        try:
            call = ToolCall(
                tool_name=str(tool_name),
                target=(str(target)[:_TARGET_MAX_CHARS] if target else ""),
                status=str(status),
                latency_ms=float(latency_ms),
                bytes_sent=int(bytes_sent),
                bytes_received=int(bytes_received),
                backend_used=str(backend_used or ""),
                error=(str(error)[:_ERROR_MAX_CHARS] if error else ""),
                metadata=dict(metadata),
                timestamp=_utc_now_iso(),
            )
            with self._lock:
                self._calls.append(call)
                if self._call_log_path is not None:
                    self._append_to_log(call)
        except Exception as exc:  # noqa: BLE001 — tracer must never break callers
            logger.warning("tool_tracer: record failed: %s", exc)

    def _append_to_log(self, call: ToolCall) -> None:
        """Append one call to ``tool_trace.jsonl``. No-op when no path set.

        Caller holds ``self._lock``. Disk errors are swallowed + logged so a
        bad path can never abort a run.
        """
        if self._call_log_path is None:
            return
        try:
            self._call_log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._call_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(call), ensure_ascii=False) + "\n")
        except Exception as exc:  # noqa: BLE001 — observability must not abort the run
            logger.warning("tool_tracer: log write failed: %s", exc)

    # ── inspection ───────────────────────────────────────────────────────
    def get_calls(self) -> list[ToolCall]:
        """Snapshot of all recorded calls."""
        with self._lock:
            return list(self._calls)

    def manifest(self) -> dict[str, Any]:
        """Per-tool summary of recorded calls.

        Returns a dict with ``summary_by_tool`` (per tool: ``total_calls``,
        ``ok_count``, ``fail_count``, ``success_rate``, ``latency_stats``
        with ``min_ms``/``max_ms``/``mean_ms``/``p95_ms``, ``error_reasons``
        histogram, ``backends_used``) plus run-level totals and a timestamp
        range.
        """
        with self._lock:
            calls = list(self._calls)

        by_tool: dict[str, list[ToolCall]] = {}
        for call in calls:
            by_tool.setdefault(call.tool_name, []).append(call)

        summary: dict[str, Any] = {}
        for tool, tool_calls in sorted(by_tool.items()):
            ok_count = sum(1 for c in tool_calls if c.status == STATUS_OK)
            fail_count = sum(1 for c in tool_calls if c.status != STATUS_OK)

            latencies = sorted(c.latency_ms for c in tool_calls if c.latency_ms > 0)
            latency_stats = {
                "min_ms": latencies[0] if latencies else 0.0,
                "max_ms": latencies[-1] if latencies else 0.0,
                "mean_ms": (sum(latencies) / len(latencies)) if latencies else 0.0,
                "p95_ms": _percentile(latencies, 0.95) if latencies else 0.0,
            }

            error_reasons: dict[str, int] = {}
            for call in tool_calls:
                if call.status != STATUS_OK and call.error:
                    key = call.error.split(":")[0][:_ERROR_KEY_MAX_CHARS]
                    error_reasons[key] = error_reasons.get(key, 0) + 1

            backends_used = sorted(
                {c.backend_used for c in tool_calls if c.backend_used}
            )

            summary[tool] = {
                "total_calls": len(tool_calls),
                "ok_count": ok_count,
                "fail_count": fail_count,
                "success_rate": (ok_count / len(tool_calls)) if tool_calls else 0.0,
                "latency_stats": latency_stats,
                "error_reasons": error_reasons,
                "backends_used": backends_used,
            }

        return {
            "summary_by_tool": summary,
            "total_calls": len(calls),
            "total_ok": sum(1 for c in calls if c.status == STATUS_OK),
            "total_fail": sum(1 for c in calls if c.status != STATUS_OK),
            "timestamp_range": {
                "start": min((c.timestamp for c in calls), default=""),
                "end": max((c.timestamp for c in calls), default=""),
            },
        }

    def discovery_funnel(self) -> dict[str, Any]:
        """FX-20 (#1128): per-stage requested-vs-actual discovery counts.

        Derived ONLY from the recorded :class:`ToolCall` rows (the SAME source as
        :meth:`manifest`) so the funnel can never fabricate — §-1.1 requires these to EQUAL
        the raw ``tool_trace.jsonl`` tallies. A count a backend does not record is reported
        as ``None`` with a ``*_source`` marker, NOT defaulted to 0 (which would misrepresent
        an unrecorded value as a real zero / a silent under-report).

        Stages:
        * ``serper`` / ``s2`` / ``openalex_search`` — each ``{calls, returned, returned_source,
          requested, requested_source}`` (``requested`` is ``None`` for backends that do not
          record ``num_requested``, e.g. s2).
        * ``fetch_content`` — ``{attempted, succeeded, source}`` where attempted = row count and
          succeeded = rows with ``status == ok`` (stub/fail are NOT successes).
        """
        with self._lock:
            calls = list(self._calls)

        def _sum_meta(rows: list[ToolCall], key: str) -> tuple[int, int]:
            present = [
                int(r.metadata[key])
                for r in rows
                if isinstance(r.metadata, dict)
                and isinstance(r.metadata.get(key), (int, float))
                and not isinstance(r.metadata.get(key), bool)
            ]
            return sum(present), len(present)

        funnel: dict[str, Any] = {}
        for tool in ("serper", "s2", "openalex_search"):
            rows = [c for c in calls if c.tool_name == tool]
            ret_sum, ret_n = _sum_meta(rows, "result_count")
            req_sum, req_n = _sum_meta(rows, "num_requested")
            funnel[tool] = {
                "calls": len(rows),
                "returned": ret_sum if ret_n else None,
                "returned_source": "tool_trace.result_count" if ret_n else "unrecorded",
                "requested": req_sum if req_n else None,
                "requested_source": "tool_trace.num_requested" if req_n else "unrecorded",
            }

        fetch_rows = [c for c in calls if c.tool_name == "fetch_content"]
        funnel["fetch_content"] = {
            "attempted": len(fetch_rows),
            "succeeded": sum(1 for c in fetch_rows if c.status == STATUS_OK),
            "source": "tool_trace.status",
        }
        return funnel

    def clinical_pdf_winner_status(self) -> dict[str, Any]:
        """I-wire-003 B3 (#1317): clinical-PDF winner (W4 mineru25) degradation flag.

        Derived ONLY from the recorded ``pdf_extract`` rows (the SAME source as
        :meth:`manifest` / :meth:`discovery_funnel`) so it can never fabricate — a
        degradation is reported iff the access layer actually recorded a mineru25
        fallback. The W4 selector (``_maybe_mineru25_extract``) records, on EVERY
        non-win branch, a ``pdf_extract`` row with ``requested_extractor=='mineru25'``
        and a ``fallback_reason`` (``no_gpu`` / ``mineru25_empty`` /
        ``mineru25_timeout`` / ``mineru25_error``) plus ``selected_extractor`` (the
        CPU fallback that actually ran, e.g. ``docling``). When the operator did NOT
        request mineru25 (``PG_CLINICAL_PDF_EXTRACTOR`` unset / ``docling``) the
        selector is never called, so no such row exists and ``degraded`` stays False
        — the docling default is a legit baseline, NOT a degradation.

        Returns ALWAYS (every manifest carries the key) with shape::

            {"requested": bool, "degraded": bool, "fallback_count": int,
             "win_count": int, "reasons": {reason: count, ...},
             "selected_extractors": [...], "source": "tool_trace.pdf_extract"}

        ``requested`` is True iff at least one pdf_extract row mentions mineru25 (a
        win OR a fallback), so a future run that asked for the winner but silently ran
        docling on EVERY PDF is observable (``requested`` True, ``win_count`` 0,
        ``degraded`` True). Pure + reset-free: the tracer is reset per query, so the
        flag never leaks across a sweep.
        """
        with self._lock:
            calls = list(self._calls)

        rows = [c for c in calls if c.tool_name == "pdf_extract"]
        fallbacks = [
            c for c in rows
            if isinstance(c.metadata, dict)
            and c.metadata.get("requested_extractor") == "mineru25"
            and c.metadata.get("fallback_reason")
        ]
        wins = [
            c for c in rows
            if isinstance(c.metadata, dict)
            and c.metadata.get("selected_extractor") == "mineru25"
        ]
        reasons: dict[str, int] = {}
        for c in fallbacks:
            key = str(c.metadata.get("fallback_reason"))
            reasons[key] = reasons.get(key, 0) + 1
        selected = sorted(
            {
                str(c.metadata.get("selected_extractor"))
                for c in fallbacks
                if c.metadata.get("selected_extractor")
            }
        )
        return {
            "requested": bool(fallbacks or wins),
            "degraded": bool(fallbacks),
            "fallback_count": len(fallbacks),
            "win_count": len(wins),
            "reasons": reasons,
            "selected_extractors": selected,
            "source": "tool_trace.pdf_extract",
        }


# ── process-global singleton ─────────────────────────────────────────────
_global_tracer: Optional[ToolTracer] = None
_global_lock = threading.Lock()


def get_tool_tracer(run_dir: Optional[Path] = None) -> ToolTracer:
    """Return the process-global :class:`ToolTracer`, creating it if needed.

    ``run_dir`` is honored ONLY when the singleton is first created. To bind
    a NEW run to its own ``run_dir`` (and avoid cross-query accumulation in a
    sweep), call :func:`reset_tool_tracer` first, then
    ``get_tool_tracer(new_run_dir)``.
    """
    global _global_tracer
    with _global_lock:
        if _global_tracer is None:
            _global_tracer = ToolTracer(run_dir)
        return _global_tracer


def reset_tool_tracer() -> None:
    """Drop the process-global tracer.

    Used at the top of each ``run_one_query`` (so per-query traces/summaries
    do not accumulate across a sweep) and between tests for isolation.
    """
    global _global_tracer
    with _global_lock:
        _global_tracer = None


def attach_tool_utilization(manifest: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    """Write ``run_dir/tool_summary.json`` and set ``manifest['tool_utilization']``.

    I-meta-007b (#meta-007) P1 coverage fix: the success path already attached
    a per-run tool-utilization summary, but every post-retrieval ABORT/ERROR
    manifest-write site returned BEFORE that hook, so aborts dropped the
    telemetry. This single helper is called immediately before EVERY
    ``manifest.json`` write (success + all abort/error paths) so the summary
    is uniform across exit paths.

    Gating + byte-identity:
    * When :func:`tool_tracker_enabled` is False (PG_ENABLE_TOOL_TRACKER=0),
      this is a PURE no-op — it returns ``manifest`` unmodified, writes no
      file, and never adds the ``tool_utilization`` key, so OFF-mode
      ``manifest.json`` stays byte-identical to the pre-I-meta-007b output.
    * When ON, it reproduces the EXACT ``tool_utilization`` shape the success
      path emitted (``trace_file`` / ``summary_file`` / ``total_tool_calls`` /
      ``total_ok`` / ``total_fail`` / ``tool_success_rate`` / ``summary_by_tool``)
      so the success-path ON-mode output is unchanged; abort paths now carry
      the same key.

    When ON it ALSO stamps two derived (no-fabrication) keys from the SAME rows:
    ``discovery_funnel`` (FX-20) and ``clinical_pdf_winner_degraded`` (I-wire-003
    B3 #1317 — the W4 mineru25 clinical-PDF winner degradation flag, top-level and
    assertable so a silent docling fallback is observable). Both are OFF-only no-ops.

    Additive + fail-safe: existing manifest keys are never altered, and any
    telemetry error (tracer/import/disk) is swallowed + logged so it can never
    abort the manifest write. Mutates ``manifest`` in place and also returns it.
    """
    if not tool_tracker_enabled():
        return manifest
    try:
        _tracer = get_tool_tracer()
        tool_summary = _tracer.manifest()
        try:
            (Path(run_dir) / "tool_summary.json").write_text(
                json.dumps(tool_summary, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001 — disk error must not abort manifest
            logger.warning("attach_tool_utilization: summary write failed: %s", exc)
        total = tool_summary.get("total_calls", 0)
        ok = tool_summary.get("total_ok", 0)
        manifest["tool_utilization"] = {
            "trace_file": "tool_trace.jsonl",
            "summary_file": "tool_summary.json",
            "total_tool_calls": total,
            "total_ok": ok,
            "total_fail": tool_summary.get("total_fail", 0),
            "tool_success_rate": (ok / total if total else 0.0),
            "summary_by_tool": tool_summary.get("summary_by_tool", {}),
        }
        # FX-20 (#1128): per-stage requested-vs-actual discovery funnel, derived from the SAME
        # recorded rows (no fabrication). Additive + only when the tracker is ON (this whole
        # function is a no-op when OFF), so OFF-mode manifest.json stays byte-identical.
        manifest["discovery_funnel"] = _tracer.discovery_funnel()
        # I-wire-003 B3 (#1317): clinical-PDF winner (W4 mineru25) degradation flag, derived from
        # the SAME pdf_extract rows. Top-level + assertable: a future run that silently degraded the
        # winner to docling shows ``clinical_pdf_winner_degraded.degraded`` True with the reason
        # histogram, so the preflight / run-health backstop can fail LOUD instead of shipping a
        # silent W4 no-op. Additive + ON-only (no-op when OFF) so OFF-mode byte-identity holds.
        _winner_status = _tracer.clinical_pdf_winner_status()
        manifest["clinical_pdf_winner_degraded"] = _winner_status
        # I-deepfix-001 U8 (#1344): MINERU-FIRES belt check. Turn the passive
        # ``clinical_pdf_winner_degraded`` telemetry into a LOUD disclosed flag on the SINGLE
        # manifest chokepoint: when mineru25 was REQUESTED but produced ZERO real GPU-VLM
        # extractions (all clinical PDFs silently degraded to a CPU fallback), stamp
        # ``manifest['mineru_firing']`` (the monitor + manifest can see it) AND emit a loud WARN so
        # the degrade is DISCLOSED, not silent. Telemetry/disclosure only — never a hard abort, never
        # a faithfulness-gate touch. Lazy import avoids an access_bypass<->tool_tracer import cycle.
        try:
            from src.tools.access_bypass import (
                mineru_degrade_canary_enabled,
                mineru_silent_degrade_disclosure,
            )
            if mineru_degrade_canary_enabled():
                _mineru_firing = mineru_silent_degrade_disclosure(_winner_status)
                manifest["mineru_firing"] = _mineru_firing
                if _mineru_firing.get("silent_degrade"):
                    logger.warning(
                        "[W4-CANARY] %s", _mineru_firing.get("disclosure"),
                    )
        except Exception as _mineru_exc:  # noqa: BLE001 — disclosure must never abort the run
            logger.warning("attach_tool_utilization: mineru-fires belt check skipped: %s", _mineru_exc)
    except Exception as exc:  # noqa: BLE001 — telemetry must never abort the run
        logger.warning("attach_tool_utilization: skipped: %s", exc)
    return manifest
