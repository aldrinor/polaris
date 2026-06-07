"""Flag-gated raw LLM I/O forensic sink (I-obs-001 #1141 AC3).

PURELY ADDITIVE, default-OFF observability. When the runner injects an ``LlmIoSink`` (only
when ``PG_CAPTURE_RAW_LLM_IO`` is on — the runner reads the flag, NOT this module), every LLM
chat-completion call on the Gate-B path persists the EXACT final request body + the RAW provider
response JSON, one file per call, to ``<run_dir>/llm_io/<call_id>.json`` for the §-1.1 forensic
audit (it captures the verifier reasoning that the Path-B channel sanitizes OUT — the two
channels are disjoint: this one is verbatim + decision-INERT + default-OFF; Path-B is sanitized +
decision-feeding + unchanged).

This module MUST NOT be on the strict_verify / 4-role decision path: it only writes files, never
mutates its args, and NEVER raises (a capture IO error can't change a run outcome or a verdict).
It imports nothing from generator/llm/scripts (layering rule), so it is safe to import from the
runner and — lazily — from the verifier role transports + the two evaluator judges.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOG = logging.getLogger(__name__)


class LlmIoSink:
    """Run-scoped sink: one ``<call_id>.json`` per LLM call under ``out_dir`` (``run_dir/llm_io``)."""

    def __init__(self, out_dir: Path | str) -> None:
        self._out_dir = Path(out_dir)
        self._made = False

    def record(
        self,
        *,
        call_id: str,
        call_type: str,
        role: str | None,
        request: Any,
        raw_response: Any,
        duration_ms: float | None = None,
        status: str = "ok",
    ) -> None:
        """Persist one LLM call's exact request + raw response. Best-effort; never raises.

        ``call_id``/``call_type`` are caller-supplied. ``timestamp_utc`` is stamped HERE (not a
        parameter). ``request``/``raw_response`` are treated as READ-ONLY (never mutated). A write
        failure logs a debug line and is swallowed — capture must not perturb the run.
        """
        try:
            if not self._made:
                self._out_dir.mkdir(parents=True, exist_ok=True)
                self._made = True
            payload = {
                "call_id": call_id,
                "call_type": call_type,
                "role": role,
                "status": status,
                "duration_ms": duration_ms,
                "timestamp_utc": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
                "request": request,
                "raw_response": raw_response,
            }
            (self._out_dir / f"{call_id}.json").write_text(
                json.dumps(payload, default=str, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001 — forensic capture must NEVER raise into the run
            _LOG.debug("llm_io_sink record failed (call_type=%s)", call_type, exc_info=True)
