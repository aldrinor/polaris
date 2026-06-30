"""I-gen-004 (#496): run-scoped reasoning-trace collector.

DeepSeek V4 Pro is reasoning-first — every generator LLM call emits a large
reasoning trace alongside the final content (one outline call observed at
content=1791 B + reasoning=17521 B). POLARIS historically discarded
``response.reasoning``. This module provides a run-scoped collector that
captures one record per raw completed provider response and flushes them to
``reasoning_trace.jsonl`` — model-process evidence stored SEPARATELY from
``report.md`` / verified prose (operator transparency directive 2026-05-14).

Layering: this module does NOT import the LLM client. The
``OpenRouterClient`` exposes a generic callable sink
(``openrouter_client.set_reasoning_sink``); the generator wires a
``ReasoningTraceCollector`` to it. The collector is a dumb, thread-safe
append/update store — capture-point policy lives in the client, flush
policy lives in the run orchestrator.

The reasoning text is captured here and NOWHERE else: it is never merged
into ``report.md`` / ``verified_text`` and ``strict_verify`` is never run
against it. Reasoning is process-transparency evidence, not a claim source.
"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

# Fixed artifact name (like ``report.md`` / ``manifest.json``) — not a tunable.
REASONING_TRACE_FILENAME = "reasoning_trace.jsonl"

# Frozen vocabularies so the artifact schema is uniform and stable.
CALL_TYPES = frozenset(
    {
        "outline",
        "section",
        # I-deepfix-001: the per-section map-reduce control LLM call
        # (multi_section_generator ``_reduce`` site, set_reasoning_call_context
        # call_type="section_reduce"). Without this the trace record is dropped
        # with "unknown reasoning-trace call_type: 'section_reduce'" — a
        # telemetry loss only (no claim/verdict path touched).
        "section_reduce",
        "repair",
        "regen",
        "limitations",
        "trial_table",
        "m50_subsection",
        "analyst_synthesis",
        "fact_dedup",
        "contract_slot",
        "regulatory",
    }
)
# ok        — a clean completed provider response used as-is
# retry     — a superseded attempt inside an internal client retry loop
# truncated — a reasoning-first response that ran out of token budget
#             (ReasoningFirstTruncationError) — captured before the raise
# error     — a hard provider/transport error
STATUSES = frozenset({"ok", "retry", "truncated", "error"})
# direct                  — content came straight from the provider `content`
# promoted_from_reasoning — content was empty; the raw reasoning was promoted
#                           to content (I-bug-088 response-shape recovery)
# extracted_from_reasoning— content was extracted from a `</think>` block
CONTENT_SOURCES = frozenset(
    {"direct", "promoted_from_reasoning", "extracted_from_reasoning"}
)


@dataclass
class ReasoningTraceRecord:
    """One raw completed provider response from a generator-side LLM call.

    ``reasoning_text`` is the model's raw reasoning channel; ``content_text``
    is what was used as the section content; ``content_source`` discloses
    their relationship (see ``CONTENT_SOURCES``). For a
    ``promoted_from_reasoning`` record the two legitimately overlap — the
    record discloses it rather than hiding it.
    """

    call_id: str
    section: str
    call_type: str
    model: str
    status: str = "ok"
    content_source: str = "direct"
    parent_call_id: Optional[str] = None
    regen_reason: Optional[str] = None
    attempt_n: int = 1
    reasoning_text: str = ""
    content_text: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    timestamp: str = ""


class ReasoningTraceCollector:
    """Run-scoped, thread-safe collector of :class:`ReasoningTraceRecord`.

    ``record()`` appends a record and returns its ``call_id``. ``update()``
    patches an existing record in place — the I-gen-004 finalization
    semantics: a record captured before client-level promotion / retry
    resolution is updated once the final ``status`` / ``content_source`` /
    ``content_text`` are known. ``flush()`` writes the full jsonl with NO
    truncation of ``reasoning_text``.
    """

    def __init__(self, out_dir: Optional[Union[str, Path]] = None) -> None:
        """``out_dir`` enables write-through mode: every ``record()`` /
        ``update()`` re-writes the full ``reasoning_trace.jsonl`` so the
        artifact is current on disk no matter which abort / error / success
        path the run exits through — no run-orchestrator flush call needed
        (I-gen-004 P2). ``out_dir=None`` → pure in-memory; ``flush()`` must
        then be called explicitly (the unit-test path).
        """
        self._records: list[ReasoningTraceRecord] = []
        self._by_id: dict[str, ReasoningTraceRecord] = {}
        self._lock = threading.Lock()
        self._out_dir: Optional[Path] = (
            Path(out_dir) if out_dir is not None else None
        )

    def record(
        self,
        *,
        section: str,
        call_type: str,
        model: str,
        status: str = "ok",
        content_source: str = "direct",
        parent_call_id: Optional[str] = None,
        regen_reason: Optional[str] = None,
        attempt_n: int = 1,
        reasoning_text: str = "",
        content_text: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        reasoning_tokens: int = 0,
        call_id: Optional[str] = None,
    ) -> str:
        """Append one record. Returns the ``call_id`` (generated if absent).

        Fails loud on an unknown ``call_type`` / ``status`` /
        ``content_source`` so a wiring mistake surfaces immediately rather
        than writing a malformed artifact.
        """
        if call_type not in CALL_TYPES:
            raise ValueError(f"unknown reasoning-trace call_type: {call_type!r}")
        if status not in STATUSES:
            raise ValueError(f"unknown reasoning-trace status: {status!r}")
        if content_source not in CONTENT_SOURCES:
            raise ValueError(
                f"unknown reasoning-trace content_source: {content_source!r}"
            )
        rec = ReasoningTraceRecord(
            call_id=call_id or uuid.uuid4().hex,
            section=section,
            call_type=call_type,
            model=model,
            status=status,
            content_source=content_source,
            parent_call_id=parent_call_id,
            regen_reason=regen_reason,
            attempt_n=max(1, int(attempt_n)),
            reasoning_text=reasoning_text or "",
            content_text=content_text or "",
            input_tokens=max(0, int(input_tokens)),
            output_tokens=max(0, int(output_tokens)),
            reasoning_tokens=max(0, int(reasoning_tokens)),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self._records.append(rec)
            self._by_id[rec.call_id] = rec
            if self._out_dir is not None:
                self._write_locked(self._out_dir)
        return rec.call_id

    def update(self, call_id: str, **patch: object) -> None:
        """Patch an already-recorded call in place. Fails loud on an unknown
        ``call_id`` or field — both indicate a wiring bug."""
        with self._lock:
            rec = self._by_id.get(call_id)
            if rec is None:
                raise KeyError(f"reasoning-trace call_id not found: {call_id!r}")
            for key, value in patch.items():
                if not hasattr(rec, key):
                    raise AttributeError(
                        f"ReasoningTraceRecord has no field {key!r}"
                    )
                setattr(rec, key, value)
            if self._out_dir is not None:
                self._write_locked(self._out_dir)

    def records(self) -> list[ReasoningTraceRecord]:
        with self._lock:
            return list(self._records)

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)

    def _write_locked(self, out_dir: Path) -> Path:
        """Write the full ``reasoning_trace.jsonl`` into ``out_dir``. The
        caller MUST hold ``self._lock``. One JSON object per record, full
        ``reasoning_text`` (NO truncation; the trace is the whole reasoning
        log). The file is always written (zero records → an empty file) so
        the artifact + manifest reference are uniform across runs.
        """
        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        path = out_path / REASONING_TRACE_FILENAME
        with path.open("w", encoding="utf-8") as handle:
            for rec in self._records:
                handle.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")
        return path

    def flush(self, out_dir: Union[str, Path]) -> Path:
        """Explicitly write ``reasoning_trace.jsonl`` into ``out_dir`` and
        return the path. In write-through mode (``out_dir`` passed to the
        constructor) the file is already current after every record/update;
        ``flush()`` stays valid and is the in-memory path's only writer.
        Fails loud on a write error.
        """
        with self._lock:
            return self._write_locked(Path(out_dir))
