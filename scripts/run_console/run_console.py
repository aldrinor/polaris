"""POLARIS live-run console (standalone, minimal, read-only).

A tiny FastAPI app that makes a running ``run_honest_sweep_r3.py`` benchmark
fully visible to a BLIND (screen-reader) operator as ONE chronological,
ChatGPT-style scrolling log, plus a config panel over the PG_* env knobs.

Design contract (LAW VII -- CLI isolation; LAW VI -- no hard-coding):
  * This module NEVER imports pipeline / faithfulness code. It only READS the
    observability files a run already writes, and READS/WRITES one ``.env``
    config file. It can never perturb a run or a verdict.
  * It is read-only on every run artifact. The only write is ``POST /api/config``
    editing a single line of the target ``.env``. The target ``.env`` is a
    SERVER-CONFIGURED path (``--env-file`` / ``PG_CONSOLE_ENV_FILE``, default
    ``<root>/.env`` else ``<repo>/.env``); requests can NEVER point it elsewhere.
    Keys are restricted to ``PG_[A-Z0-9_]+`` and values may not contain newlines,
    so the endpoint cannot smuggle extra keys or escape the intended file.
  * host / port / run-root / env-file come from argparse or env (PG_CONSOLE_HOST,
    PG_CONSOLE_PORT, PG_CONSOLE_ROOT, PG_CONSOLE_ENV_FILE) -- nothing is hard-coded.

Observability files consumed (verified against the live emitters):
  * ``run_status.json``       heartbeat   -> phase / status / progress
      src/polaris_graph/telemetry/run_status_heartbeat.py:97-146
  * ``retrieval_trace.jsonl`` per-URL     -> query / fetch(kept|drop)
      src/polaris_graph/benchmark/pathB_capture.py:219-247
  * ``reasoning_trace.jsonl`` per-call    -> reasoning
      src/polaris_graph/generator/reasoning_trace.py:201-214
  * ``tool_trace.jsonl``      per-tool    -> tool
      src/polaris_graph/telemetry/tool_tracer.py:167-180
  * ``llm_io/<id>.json``      opt-in      -> reasoning (raw LLM I/O, AC3)
      src/polaris_graph/telemetry/llm_io_sink.py:34-72
  * ``report.md``             final       -> report + citation tokens
  * ``manifest.json``         terminal    -> status (+ release_disclosure.disclosed_gaps)

The JSONL files are REWRITTEN in place (reasoning_trace ``"w"`` on every record;
retrieval_trace ``"w"`` flush at end-of-retrieval), so the tailer re-reads the
whole file each poll, tracks the emitted record COUNT, emits ``records[count:]``,
and resets on shrink. A poll landing mid-rewrite reads a truncated tail; the bad
line is skipped and picked up next poll. retrieval_trace records carry no
timestamp, so a single global ts-sorted order is impossible -- each file is
emitted in its own append order and the server stamps ``ts`` from the record's
own timestamp when present, else server-now. This is stated honestly in the UI.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Iterable, Iterator

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

# -- constants (file names are pipeline-fixed artifact names, not tunables) -----
HOST_ENV = "PG_CONSOLE_HOST"
PORT_ENV = "PG_CONSOLE_PORT"
ROOT_ENV = "PG_CONSOLE_ROOT"
ENV_FILE_ENV = "PG_CONSOLE_ENV_FILE"  # server-configured target .env (NEVER request-controlled)
DEFAULT_HOST = "127.0.0.1"  # localhost-only: this process writes a .env from a request body
DEFAULT_PORT = 8787

RUN_STATUS_FILE = "run_status.json"
RETRIEVAL_TRACE_FILE = "retrieval_trace.jsonl"
REASONING_TRACE_FILE = "reasoning_trace.jsonl"
TOOL_TRACE_FILE = "tool_trace.jsonl"
LLM_IO_DIR = "llm_io"
REPORT_FILE = "report.md"
MANIFEST_FILE = "manifest.json"
# GH #1258 PART 1: the per-run launch log is the raw stdout/stderr the run was started with.
# The driver writes it as <root>/launch_<slug>.log (a SIBLING of the <domain>/<slug> run dir, i.e.
# run_dir.parent.parent / "launch_<slug>.log"). Two in-run-dir fallbacks are also tried so a run
# started with a redirected stdout inside its own dir is still tailed.
LAUNCH_LOG_IN_RUN_FALLBACKS = ("run.log", "stdout.log")

POLL_INTERVAL_S = float(os.environ.get("PG_CONSOLE_POLL_S", "1.0"))
_MAX_TEXT = 4000  # per-event text clamp so one giant reasoning blob can't flood the screen reader
_CITATION_RE = re.compile(r"\[#ev:[^\]]+\]")
# bounded /api/config scan
_PG_VAR_RE = re.compile(
    r"""os\.(?:getenv|environ\.get)\(\s*["'](PG_[A-Z0-9_]+)["']\s*(?:,\s*(?P<def>[^)]*?))?\)"""
)
_PG_INDEX_RE = re.compile(r"""os\.environ\[\s*["'](PG_[A-Z0-9_]+)["']\s*\]""")
_CONFIG_SCAN_DIRS = ("src", "scripts")
_CONFIG_SCAN_SUFFIXES = (".py",)
_CONFIG_MAX_FILE_BYTES = 2_000_000

# -- DoS hardening caps (env-overridable; generous so normal artifacts are untouched) --
# Skip/refuse any single observability or env file larger than this when reading.
_MAX_READ_BYTES = int(os.environ.get("PG_CONSOLE_MAX_READ_BYTES", str(8 * 1024 * 1024)))  # 8 MB
# Cap how many llm_io/*.json files we read per poll (newest-first).
_MAX_LLM_IO_FILES = int(os.environ.get("PG_CONSOLE_MAX_LLM_IO_FILES", "200"))
# Bound the /api/runs directory walk (domain dirs, and slug dirs per domain).
_MAX_RUN_DIRS = int(os.environ.get("PG_CONSOLE_MAX_RUN_DIRS", "2000"))
# GH #1258 PART 1: cap how many NEW launch-log lines we emit per poll so a sudden burst of
# raw stdout (the CPU embedding-rerank + agentic phases write progress only to the launch log)
# cannot firehose the screen-reader. Excess lines beyond the cap are coalesced into a single
# "(+N more lines …)" notice; the byte offset still advances past them so they are not re-read.
_MAX_LOG_LINES_PER_POLL = max(1, int(os.environ.get("PG_CONSOLE_MAX_LOG_LINES_PER_POLL", "200")))

# -- /api/config validation: accept ONLY PG_<UPPER/DIGIT/_> keys; mask secret-looking values --
_PG_KEY_RE = re.compile(r"PG_[A-Z0-9_]+")  # used with fullmatch (rejects trailing \n that ^...$ allows)
_SECRET_KEY_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD", "AUTH")
_SECRET_MASK = "********"

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent  # scripts/run_console -> scripts -> repo root

app = FastAPI(title="POLARIS run console", docs_url=None, redoc_url=None)

# Resolved at startup from argparse/env (see main()); a module global so the
# route handlers can read it without a dependency-injection framework.
_RUN_ROOT: Path = Path(os.environ.get(ROOT_ENV, str(_REPO_ROOT / "outputs" / "honest_sweep_r3")))
# Server-configured target .env for /api/config (GET + POST). Resolved in main();
# request bodies/queries can NEVER point the console at a different file.
_ENV_FILE: Path = Path(
    os.environ.get(ENV_FILE_ENV, str(_RUN_ROOT / ".env"))
).resolve()


# -- helpers: safe IO --------------------------------------------------------
def _too_big(path: Path) -> bool:
    """True if path exceeds the read cap (DoS guard). Missing/unstatable -> not big."""
    try:
        return path.stat().st_size > _MAX_READ_BYTES
    except OSError:
        return False


def _read_json(path: Path) -> "dict[str, Any] | None":
    """Best-effort whole-file JSON read. Returns None on absence / mid-write garbage / oversize."""
    if _too_big(path):
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _iter_jsonl(path: Path) -> Iterator[dict]:
    """Yield parsed JSON objects from a .jsonl, skipping blank / mid-rewrite-truncated lines.

    The file is rewritten in place by the emitters, so a poll can land mid-write
    and read a truncated final line; that line fails json.loads and is skipped --
    it parses cleanly on the next poll once the rewrite completes. Files over the
    read cap are skipped entirely (DoS guard).
    """
    if _too_big(path):
        return
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except Exception:
            continue


def _clamp(text: str) -> str:
    if len(text) > _MAX_TEXT:
        extra = len(text) - _MAX_TEXT
        return text[:_MAX_TEXT] + " ... (+" + str(extra) + " chars)"
    return text


def _resolve_run_dir(run: str) -> "Path | None":
    """Resolve a 'domain/slug' (or any sub-path) under the run root, refusing escapes."""
    base = _RUN_ROOT.resolve()
    candidate = (base / run).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None  # path-traversal attempt
    return candidate if candidate.is_dir() else None


def _resolve_launch_log(run_dir: Path) -> "Path | None":
    """Resolve the per-run launch log for ``run_dir`` (GH #1258 PART 1), or None if absent.

    Primary location: ``<root>/launch_<slug>.log`` — a SIBLING of the ``<domain>/<slug>`` run
    dir (``run_dir.parent.parent / ("launch_" + run_dir.name + ".log")``). Fallbacks: a log
    redirected INTO the run dir (``run.log`` / ``stdout.log``). Every candidate is derived from
    ``run_dir`` (already traversal-checked by ``_resolve_run_dir``) and confined under the run
    root, so this adds no new traversal surface. Returns the first EXISTING regular file.
    """
    candidates = [
        run_dir.parent.parent / ("launch_" + run_dir.name + ".log"),
    ]
    for name in LAUNCH_LOG_IN_RUN_FALLBACKS:
        candidates.append(run_dir / name)
    base = _RUN_ROOT.resolve()
    for cand in candidates:
        try:
            resolved = cand.resolve()
            resolved.relative_to(base)  # never tail anything outside the run root
        except (OSError, ValueError):
            continue
        if resolved.is_file():
            return resolved
    return None


def _tail_launch_log(path: Path, offset: int, carry: bytes):
    """Read launch-log bytes after ``offset`` and split into complete lines (GH #1258 PART 1).

    Returns ``(lines, new_offset, new_carry)`` where:
      * ``lines``      = the COMPLETE lines (str) since ``offset``; the trailing partial line, if
                         any, is NOT emitted.
      * ``new_offset`` = the new byte position to resume from next poll.
      * ``new_carry``  = the buffered partial trailing line, held as RAW BYTES (no newline yet).

    The carry is bytes, not text: a poll may end mid-multibyte-UTF-8-char (the read landed mid-char,
    or the per-poll byte cap split one), so we buffer the raw bytes and decode ONLY complete lines
    (those terminated by ``\\n``). Decoding the partial tail as text would freeze a half-char into a
    permanent replacement character; carrying bytes lets the next poll's bytes complete the char.

    Rotation / truncation handling: if the file shrank below ``offset`` (rotated or rewritten),
    the offset and carry both reset to 0/b"" and we re-read from the start. Oversize files (over
    the DoS read cap) and IO errors yield no lines and leave the offset unchanged.
    """
    try:
        size = path.stat().st_size
    except OSError:
        return [], offset, carry
    # Rotation / truncation: file is now smaller than where we left off -> start over.
    if size < offset:
        offset = 0
        carry = b""
    if size == offset:
        return [], offset, carry
    # DoS guard: never read an unbounded backlog in a single poll. Cap the chunk to _MAX_READ_BYTES
    # from the current offset; the offset still advances so the next poll continues from there.
    end = min(size, offset + _MAX_READ_BYTES)
    try:
        with open(path, "rb") as fh:
            fh.seek(offset)
            chunk = fh.read(end - offset)
    except OSError:
        return [], offset, carry
    new_offset = offset + len(chunk)
    buf = carry + chunk
    parts = buf.split(b"\n")
    new_carry = parts.pop()  # trailing element: b"" if buf ended in \n, else the partial-line bytes
    lines = [p.rstrip(b"\r").decode("utf-8", errors="replace") for p in parts]
    return lines, new_offset, new_carry


# -- /api/runs ---------------------------------------------------------------
def _list_runs(root: Path) -> list:
    """List run dirs (domain/slug, two levels deep) under root, newest first, with status.

    The walk is bounded to ``_MAX_RUN_DIRS`` slug dirs so a pathological root with a
    huge number of subdirectories cannot pin CPU/IO (DoS guard).
    """
    runs: list = []
    if not root.is_dir():
        return runs
    walked = 0
    for domain_dir in root.iterdir():
        if walked >= _MAX_RUN_DIRS:
            break
        if not domain_dir.is_dir():
            continue
        for slug_dir in domain_dir.iterdir():
            if walked >= _MAX_RUN_DIRS:
                break
            if not slug_dir.is_dir():
                continue
            walked += 1
            rel = domain_dir.name + "/" + slug_dir.name
            manifest = _read_json(slug_dir / MANIFEST_FILE)
            status_doc = _read_json(slug_dir / RUN_STATUS_FILE)
            status = manifest.get("status") if isinstance(manifest, dict) else None
            stage = status_doc.get("stage") if isinstance(status_doc, dict) else None
            mtimes = []
            for name in (RUN_STATUS_FILE, MANIFEST_FILE, RETRIEVAL_TRACE_FILE):
                p = slug_dir / name
                if p.exists():
                    try:
                        mtimes.append(p.stat().st_mtime)
                    except OSError:
                        pass
            try:
                mtimes.append(slug_dir.stat().st_mtime)
            except OSError:
                pass
            runs.append(
                {
                    "run": rel,
                    "domain": domain_dir.name,
                    "slug": slug_dir.name,
                    "status": status,
                    "stage": stage,
                    "complete": bool(status),
                    "mtime": max(mtimes) if mtimes else 0.0,
                }
            )
    runs.sort(key=lambda r: r["mtime"], reverse=True)
    return runs


# -- event extraction (file -> list of {type, ts, text}) ---------------------
def _ev(etype: str, text: str, ts=None) -> dict:
    return {"type": etype, "ts": ts if ts is not None else time.time(), "text": _clamp(text)}


def _status_event(doc: dict) -> dict:
    stage = doc.get("stage")
    qi, qt = doc.get("query_index"), doc.get("query_total")
    parts = ["stage=" + str(stage)]
    if qi is not None and qt is not None:
        parts.append("query " + str(qi) + "/" + str(qt))
    if doc.get("slug"):
        parts.append("slug=" + str(doc.get("slug")))
    if doc.get("sources_kept") is not None:
        parts.append("sources_kept=" + str(doc.get("sources_kept")))
    if doc.get("sections_done") is not None or doc.get("sections_total") is not None:
        parts.append("sections=" + str(doc.get("sections_done")) + "/" + str(doc.get("sections_total")))
    if doc.get("claims_verified") is not None or doc.get("claims_total") is not None:
        parts.append("claims=" + str(doc.get("claims_verified")) + "/" + str(doc.get("claims_total")))
    if doc.get("running_cost_usd") is not None:
        parts.append("cost=$" + str(doc.get("running_cost_usd")) + "/" + str(doc.get("budget_cap_usd")))
    if doc.get("elapsed_s") is not None:
        parts.append("elapsed_s=" + str(doc.get("elapsed_s")))
    etype = "error" if (isinstance(stage, str) and stage == "error") else ("phase" if stage else "status")
    return _ev(etype, " ".join(parts), ts=doc.get("last_update_utc"))


def _retrieval_event(rec: dict):
    kind = rec.get("kind")
    if kind == "query":
        return _ev(
            "query",
            "[" + str(rec.get("backend")) + "] query -> " + str(rec.get("return_count"))
            + " urls : " + str(rec.get("query", "")),
        )
    if kind == "kept":
        return _ev("fetch", "KEPT  [" + str(rec.get("backend")) + "] " + str(rec.get("url")))
    if kind == "drop":
        return _ev("fetch", "DROP  (" + str(rec.get("reason")) + ") " + str(rec.get("url")))
    return None


def _reasoning_event(rec: dict) -> dict:
    head = (
        "[" + str(rec.get("call_type")) + "/" + str(rec.get("section")) + "] "
        + "model=" + str(rec.get("model")) + " status=" + str(rec.get("status"))
    )
    body = (rec.get("reasoning_text") or "") or (rec.get("content_text") or "")
    return _ev("reasoning", (head + "\n" + body).rstrip(), ts=rec.get("timestamp"))


def _tool_event(rec: dict) -> dict:
    md = rec.get("metadata") or {}
    extra = ""
    if isinstance(md, dict) and "result_count" in md:
        extra = " result_count=" + str(md.get("result_count"))
    text = (
        "[" + str(rec.get("tool_name")) + "] " + str(rec.get("status"))
        + " backend=" + str(rec.get("backend_used")) + " " + str(rec.get("latency_ms"))
        + "ms" + extra + " :: " + str(rec.get("target", ""))
    )
    return _ev("tool", text, ts=rec.get("timestamp"))


def _llm_io_event(doc: dict) -> dict:
    head = (
        "[llm_io " + str(doc.get("call_type")) + "] role=" + str(doc.get("role"))
        + " status=" + str(doc.get("status")) + " " + str(doc.get("duration_ms")) + "ms"
    )
    raw = doc.get("raw_response")
    reasoning = ""
    if isinstance(raw, dict):
        try:
            choice = (raw.get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            reasoning = msg.get("reasoning") or msg.get("content") or ""
        except Exception:
            reasoning = ""
    return _ev("reasoning", (head + "\n" + reasoning).rstrip(), ts=doc.get("timestamp_utc"))


def _report_events(report_path: Path) -> list:
    """One report event (the report landed) plus one citation event per unique [#ev:..] token."""
    out: list = []
    if _too_big(report_path):
        out.append(_ev("report", "report.md present but exceeds read cap; skipped"))
        return out
    try:
        text = report_path.read_text(encoding="utf-8")
    except Exception:
        return out
    out.append(_ev("report", "report.md written (" + str(len(text)) + " chars)"))
    seen: set = set()
    for tok in _CITATION_RE.findall(text):
        if tok not in seen:
            seen.add(tok)
            out.append(_ev("citation", tok))
    return out


def _manifest_event(doc: dict) -> dict:
    status = doc.get("status")
    rel = doc.get("release_disclosure")
    gaps: Iterable = []
    if isinstance(rel, dict):
        g = rel.get("disclosed_gaps")
        if isinstance(g, list):
            gaps = g
    text = "RUN COMPLETE -- status=" + str(status)
    if gaps:
        text += " | disclosed_gaps: " + "; ".join(str(x) for x in gaps)
    etype = "error" if (isinstance(status, str) and status.startswith(("error", "abort"))) else "status"
    return _ev(etype, text)


# -- SSE stream --------------------------------------------------------------
async def _event_stream(run_dir: Path):
    """Poll the run's observability files and yield each NEW event as an SSE frame."""
    counts = {RETRIEVAL_TRACE_FILE: 0, REASONING_TRACE_FILE: 0, TOOL_TRACE_FILE: 0}
    extractors = {
        RETRIEVAL_TRACE_FILE: _retrieval_event,
        REASONING_TRACE_FILE: _reasoning_event,
        TOOL_TRACE_FILE: _tool_event,
    }
    status_sig = None
    seen_llm: set = set()
    report_done = False
    manifest_done = False
    # GH #1258 PART 1: byte-offset state for the raw launch-log tailer. We read ONLY new bytes
    # each poll (seek(offset)+read), buffering a trailing partial line in `log_carry` until its
    # newline arrives, and reset on shrink/rotate. Kept in this closure exactly like `counts`.
    log_offset = 0
    log_carry = b""

    yield _sse(_ev("status", "connected -- tailing " + run_dir.name))

    while True:
        batch: list = []

        # 1) heartbeat (emit only when its signature changes)
        doc = _read_json(run_dir / RUN_STATUS_FILE)
        if isinstance(doc, dict):
            sig = json.dumps(
                {k: doc.get(k) for k in ("stage", "query_index", "sources_kept",
                                         "sections_done", "claims_verified", "running_cost_usd")},
                sort_keys=True,
            )
            if sig != status_sig:
                status_sig = sig
                batch.append(_status_event(doc))

        # 2) rewritten JSONL files: re-read whole, emit records[count:], reset on shrink
        for fname, extractor in extractors.items():
            records = list(_iter_jsonl(run_dir / fname))
            prev = counts[fname]
            if len(records) < prev:
                prev = 0
            for rec in records[prev:]:
                ev = extractor(rec)
                if ev is not None:
                    batch.append(ev)
            counts[fname] = len(records)

        # 3) opt-in raw LLM I/O (one file per call, never rewritten)
        llm_dir = run_dir / LLM_IO_DIR
        if llm_dir.is_dir():
            try:
                files = sorted(llm_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
            except OSError:
                files = []
            # DoS guard: only the newest _MAX_LLM_IO_FILES files are read per poll.
            files = files[-_MAX_LLM_IO_FILES:]
            for f in files:
                if f.name in seen_llm:
                    continue
                d = _read_json(f)
                if isinstance(d, dict):
                    seen_llm.add(f.name)
                    batch.append(_llm_io_event(d))

        # 4) final report.md (one-shot: report event + citation events)
        report_path = run_dir / REPORT_FILE
        if not report_done and report_path.exists():
            report_done = True
            batch.extend(_report_events(report_path))

        # 5) terminal manifest (one-shot, keep the connection open afterwards)
        if not manifest_done:
            mdoc = _read_json(run_dir / MANIFEST_FILE)
            if isinstance(mdoc, dict) and mdoc.get("status"):
                manifest_done = True
                batch.append(_manifest_event(mdoc))

        # 6) GH #1258 PART 1: incrementally tail the raw launch log (the per-run stdout). During
        # the long CPU embedding-rerank + agentic phases the pipeline writes progress ONLY here, so
        # without this the stream goes quiet for minutes even though work is happening. Emit each
        # NEW complete line as a type:"log" event (clamped); cap lines-per-poll so a burst can't
        # firehose the screen reader, coalescing the overflow into one notice.
        log_path = _resolve_launch_log(run_dir)
        if log_path is not None:
            new_lines, log_offset, log_carry = _tail_launch_log(log_path, log_offset, log_carry)
            if len(new_lines) > _MAX_LOG_LINES_PER_POLL:
                dropped = len(new_lines) - _MAX_LOG_LINES_PER_POLL
                new_lines = new_lines[:_MAX_LOG_LINES_PER_POLL]
                new_lines.append("(+" + str(dropped) + " more log lines this poll; raise "
                                 "PG_CONSOLE_MAX_LOG_LINES_PER_POLL to see them)")
            for line in new_lines:
                if line:  # skip blank lines (the screen reader gains nothing from them)
                    batch.append(_ev("log", line))

        for ev in batch:
            yield _sse(ev)

        await asyncio.sleep(POLL_INTERVAL_S)


def _sse(ev: dict) -> bytes:
    return ("data: " + json.dumps(ev, ensure_ascii=False) + "\n\n").encode("utf-8")


# -- /api/config -------------------------------------------------------------
def _scan_pg_vars() -> dict:
    """Bounded walk of src/ + scripts/ for PG_* getenv/environ usage -> {name: default_or_None}."""
    found: dict = {}
    for top in _CONFIG_SCAN_DIRS:
        base = _REPO_ROOT / top
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.suffix not in _CONFIG_SCAN_SUFFIXES or not path.is_file():
                continue
            try:
                if path.stat().st_size > _CONFIG_MAX_FILE_BYTES:
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for m in _PG_VAR_RE.finditer(text):
                name = m.group(1)
                default = m.group("def")
                if default is not None:
                    default = default.strip()
                    if (default.startswith(("'", '"')) and default.endswith(("'", '"'))) or default.isdigit():
                        default = default.strip("'\"")
                    else:
                        default = None
                if name not in found or (found.get(name) is None and default is not None):
                    found[name] = default
            for m in _PG_INDEX_RE.finditer(text):
                found.setdefault(m.group(1), None)
    return found


def _read_env_file(env_path: Path) -> dict:
    values: dict = {}
    if _too_big(env_path):
        return values
    try:
        text = env_path.read_text(encoding="utf-8")
    except Exception:
        return values
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, _, val = s.partition("=")
        values[key.strip()] = val.strip()
    return values


def _is_secret_key(name: str) -> bool:
    """True if a config key name looks secret-bearing (case-insensitive substring match)."""
    upper = name.upper()
    return any(marker in upper for marker in _SECRET_KEY_MARKERS)


def _mask_value(value: "str | None") -> "str | None":
    """Mask a secret-looking value: keep first2+last2 for long values, else a flat mask."""
    if value is None:
        return None
    if len(value) <= 6:
        return _SECRET_MASK
    return value[:2] + _SECRET_MASK + value[-2:]


def _set_env_var(env_path: Path, name: str, value: str) -> None:
    """Set/replace one ``NAME=value`` line, preserving every other line. Append if absent.

    Refuses to read/rewrite an existing file over the read cap (DoS guard).
    """
    if _too_big(env_path):
        raise ValueError("target env file exceeds read cap")
    try:
        existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    except Exception:
        existing = ""
    lines = existing.splitlines()
    pat = re.compile(r"^\s*" + re.escape(name) + r"\s*=")
    replaced = False
    for i, line in enumerate(lines):
        if pat.match(line):
            lines[i] = name + "=" + value
            replaced = True
            break
    if not replaced:
        lines.append(name + "=" + value)
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# -- routes ------------------------------------------------------------------
@app.get("/")
def index() -> FileResponse:
    return FileResponse(_HERE / "index.html", media_type="text/html")


@app.get("/api/runs")
def api_runs() -> JSONResponse:
    # Constrained to the server-configured _RUN_ROOT only. Any request-supplied
    # `root` is ignored so the endpoint cannot enumerate arbitrary directories.
    base = _RUN_ROOT.resolve()
    return JSONResponse({"root": str(base), "runs": _list_runs(base)})


@app.get("/stream")
async def stream(run: str = Query(...)):
    run_dir = _resolve_run_dir(run)
    if run_dir is None:
        return JSONResponse({"error": "run not found under root: " + run}, status_code=404)
    return StreamingResponse(
        _event_stream(run_dir),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/config")
def api_config() -> JSONResponse:
    # Reads ONLY the server-configured _ENV_FILE (no request-controlled path).
    # Secret-looking values are masked so a GET cannot disclose raw secrets.
    declared = _scan_pg_vars()
    current = _read_env_file(_ENV_FILE)
    rows = []
    for name in sorted(set(declared) | {k for k in current if k.startswith("PG_")}):
        raw = current.get(name)
        value = _mask_value(raw) if _is_secret_key(name) else raw
        rows.append(
            {
                "name": name,
                "default_if_any": declared.get(name),
                "current_value_from_env_file": value,
                "secret": _is_secret_key(name),
            }
        )
    return JSONResponse({"env_file": str(_ENV_FILE), "count": len(rows), "vars": rows})


@app.post("/api/config")
async def api_set_config(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)
    name = body.get("name")
    value = body.get("value")
    # Any `env_file` in the body is IGNORED: the write target is the single
    # server-configured _ENV_FILE only (no request-controlled paths).
    if not name or not isinstance(name, str):
        return JSONResponse({"error": "missing 'name'"}, status_code=400)
    if value is None:
        return JSONResponse({"error": "missing 'value'"}, status_code=400)
    if not isinstance(value, str):
        return JSONResponse({"error": "'value' must be a string"}, status_code=400)
    # Validate the key: ONLY PG_<UPPER/DIGIT/_>. fullmatch (not ^...$) so a
    # trailing newline like "PG_FOO\n" is rejected (\\$ would allow it).
    if not _PG_KEY_RE.fullmatch(name):
        return JSONResponse(
            {"error": "invalid 'name': must match PG_[A-Z0-9_]+"}, status_code=400
        )
    # Reject ANY line-break in the value: prevents key smuggling
    # (e.g. value="x\nPG_OTHER=y" injecting a second line into the .env).
    # NOTE: this guards against EVERY separator str.splitlines() breaks on --
    # not just \n/\r but also \v \f \x1c-\x1e \x85     -- because
    # _read_env_file / _set_env_var split the file with splitlines(); a narrower
    # check (only \n/\r) would let "x PG_OTHER=y" smuggle a second key.
    if "\n" in value or "\r" in value or len(value.splitlines()) > 1:
        return JSONResponse(
            {"error": "invalid 'value': must not contain a line break"}, status_code=400
        )
    try:
        _set_env_var(_ENV_FILE, name, value)
    except Exception as exc:
        return JSONResponse({"error": "write failed: " + str(exc)}, status_code=500)
    # Do NOT echo the raw value (it may be a secret). Return the key + the
    # resolved server path only.
    return JSONResponse({"ok": True, "name": name, "env_file": str(_ENV_FILE)})


# -- entrypoint --------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="POLARIS live-run console (read-only)")
    parser.add_argument("--host", default=os.environ.get(HOST_ENV, DEFAULT_HOST))
    parser.add_argument("--port", type=int, default=int(os.environ.get(PORT_ENV, DEFAULT_PORT)))
    parser.add_argument(
        "--root",
        default=os.environ.get(ROOT_ENV, str(_REPO_ROOT / "outputs" / "honest_sweep_r3")),
        help="run output root; run dirs are <root>/<domain>/<slug>/",
    )
    parser.add_argument(
        "--env-file",
        default=os.environ.get(ENV_FILE_ENV),
        help="the ONE .env file /api/config reads and writes "
        "(default: <root>/.env, else <repo>/.env). Requests can never override it.",
    )
    args = parser.parse_args()

    global _RUN_ROOT, _ENV_FILE
    _RUN_ROOT = Path(args.root).resolve()
    if args.env_file:
        _ENV_FILE = Path(args.env_file).resolve()
    else:
        candidate = _RUN_ROOT / ".env"
        _ENV_FILE = candidate.resolve() if candidate.exists() else (_REPO_ROOT / ".env").resolve()

    import uvicorn

    print(
        "[run_console] root=" + str(_RUN_ROOT)
        + "  env_file=" + str(_ENV_FILE)
        + "  http://" + args.host + ":" + str(args.port) + "/"
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
