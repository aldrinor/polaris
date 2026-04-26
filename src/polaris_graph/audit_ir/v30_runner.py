"""V30 Phase-2 sweep wired into the JobRunner abstraction.

Per FINAL_PLAN.md (Phase B M-9): launch the existing V30 Phase-2 sweep
as a subprocess, monitor run_log.txt for phase boundaries, emit
checkpoints at each boundary so pause/cancel work cooperatively.

Design:
- Subprocess approach (NOT in-process refactor) because the sweep is
  ~5000 lines of asyncio orchestration and refactoring it phase-by-phase
  is a Phase C task.
- Phase boundaries derived from run_log.txt timestamps (the sweep
  already writes one line per phase). The runner tails the log and
  emits control.checkpoint() per phase line.
- Cancel: subprocess gets SIGTERM (or terminate() on Windows). Caller
  waits up to 30s for graceful shutdown then SIGKILL.
- Pause: NOT supported for V30 in Phase B. The sweep has no clean
  mid-sweep pause point. JobControl.Paused raises if pause is requested,
  which the worker converts to mark_paused — but the resume path will
  re-run from scratch (no incremental checkpoint state inside V30).
  Phase C M-13 progressive surfaces enable real pause via SSE streaming.

Codex M-9 anticipates:
- Subprocess env passes OPENROUTER_API_KEY etc through to the child
- Python interpreter resolution is sys.executable (matches parent venv)
- Per-job artifact dir: out_root/<domain>/<slug>/ — resolves via the
  manifest_path field returned in checkpoint state
"""

from __future__ import annotations

import logging
import os
import re
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from src.polaris_graph.audit_ir.job_queue import Job
from src.polaris_graph.audit_ir.job_runner import JobControl, JobRunner

logger = logging.getLogger(__name__)


# Canonical phase milestones the V30 sweep emits to run_log.txt. The
# runner uses these to derive progress_pct and progress_message per
# checkpoint. Order matches the sweep's actual execution.
V30_PHASES = (
    ("scope_gate",          5.0,  "Scope gate"),
    ("retrieval_started",   10.0, "Live retrieval"),
    ("retrieval_done",      55.0, "Retrieval complete"),
    ("adequacy_gate",       60.0, "Corpus adequacy gate"),
    ("approval_gate",       65.0, "Corpus approval gate"),
    ("generation_started",  70.0, "Generation"),
    ("strict_verify",       80.0, "Strict-verify provenance"),
    ("evaluator_gate",      85.0, "Evaluator gate"),
    ("v30_phase1",          90.0, "V30 Phase-1 frame coverage"),
    ("v30_phase2",          95.0, "V30 Phase-2 slot-bound generation"),
    ("qwen_judge",          98.0, "Qwen judge"),
    ("complete",            100.0, "Sweep complete"),
)


# Run_log.txt patterns map to phase keys above. Patterns are loose
# substring matches on log lines.
#
# Order matters: more-specific patterns (M-XX, V30 Phase N) come BEFORE
# generic substring ones (e.g. "generation"), so a line like
# "V30 Phase 2: M-58 slot-bound generation" classifies as v30_phase2,
# not generation_started.
_PHASE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("v30_phase2",          "v30 phase 2"),
    ("v30_phase2",          "m-58"),
    ("v30_phase1",          "v30 phase 1"),
    ("v30_phase1",          "m-56"),
    ("complete",            "sweep complete"),
    ("complete",            "wall time:"),
    ("qwen_judge",          "live_qwen_judge"),
    ("qwen_judge",          "qwen_judge"),
    ("evaluator_gate",      "evaluator_gate"),
    ("evaluator_gate",      "phase 5"),
    ("strict_verify",       "strict_verify"),
    ("strict_verify",       "phase 4"),
    ("retrieval_done",      "phase 2 complete"),
    ("retrieval_started",   "phase 2: live retrieval"),
    ("retrieval_started",   "phase 2: starting"),
    ("approval_gate",       "corpus_approval"),
    ("approval_gate",       "approval_gate"),
    ("adequacy_gate",       "corpus_adequacy"),
    ("adequacy_gate",       "adequacy_gate"),
    ("scope_gate",          "scope_gate"),
    ("scope_gate",          "scope decision"),
    ("generation_started",  "phase 3"),
    ("generation_started",  "generation"),
)

_PHASE_PCT: dict[str, float] = {key: pct for key, pct, _ in V30_PHASES}
_PHASE_MSG: dict[str, str] = {key: msg for key, _, msg in V30_PHASES}


@dataclass
class V30RunnerConfig:
    """Runtime configuration for the V30 runner."""

    repo_root: Path
    sweep_script: Path
    out_root: Path
    python_bin: str = sys.executable
    poll_interval_s: float = 1.0
    cancel_grace_s: float = 30.0
    extra_env: Mapping[str, str] | None = None


class V30JobRunner(JobRunner):
    """Runs the V30 Phase-2 sweep as a subprocess, checkpoints per phase.

    Job params (required): {"slug": "<canonical_slug>"}
    Job params (optional): {"domain": "<domain>"} — defaults derived
                                                    from slug map.

    Returns: artifact_dir path on success.
    """

    template_id = "v30_clinical"

    def __init__(self, config: V30RunnerConfig) -> None:
        self._config = config

    def run(self, job: Job, control: JobControl) -> str | None:
        slug = (job.params or {}).get("slug")
        if not slug:
            raise ValueError("v30_clinical: job.params.slug is required")
        cfg = self._config
        if not cfg.sweep_script.exists():
            raise FileNotFoundError(f"Sweep script missing: {cfg.sweep_script}")

        # Subprocess env: inherit + add V30 env extras.
        env = dict(os.environ)
        if cfg.extra_env:
            env.update(cfg.extra_env)

        cmd = [
            cfg.python_bin,
            str(cfg.sweep_script),
            "--only", slug,
            "--out-root", str(cfg.out_root),
        ]

        # Initial checkpoint so the queue shows progress immediately.
        control.checkpoint(
            progress_pct=1.0,
            message="Launching V30 sweep subprocess",
            state={"slug": slug, "phase": "launch"},
        )

        logger.info("V30JobRunner: launching %s", " ".join(cmd))
        proc = subprocess.Popen(
            cmd,
            cwd=str(cfg.repo_root),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        seen_phases: set[str] = set()
        last_phase = "launch"
        last_pct = 1.0
        cancelled = False
        # Tail the subprocess stdout in a thread so we can poll the
        # control surface in the main thread.
        log_lines: list[str] = []
        log_lock = threading.Lock()

        def _drain() -> None:
            assert proc.stdout is not None
            for line in proc.stdout:
                with log_lock:
                    log_lines.append(line)

        drain_thread = threading.Thread(target=_drain, daemon=True, name="v30-stdout-drain")
        drain_thread.start()

        try:
            while True:
                # Detect new phase boundaries from the latest log lines.
                with log_lock:
                    snapshot = list(log_lines)
                    log_lines.clear()
                for line in snapshot:
                    phase = self._classify_phase(line)
                    if phase and phase not in seen_phases:
                        seen_phases.add(phase)
                        last_phase = phase
                        last_pct = _PHASE_PCT[phase]
                        try:
                            control.checkpoint(
                                progress_pct=last_pct,
                                message=_PHASE_MSG[phase],
                                state={
                                    "slug": slug,
                                    "phase": phase,
                                    "log_line": line.strip()[:300],
                                },
                            )
                        except (JobControl.Cancelled, JobControl.Paused):
                            cancelled = True
                            raise

                # Periodic checkpoint even when no new phase fires
                # (so cancel/pause requests are detected within
                # poll_interval_s).
                try:
                    control.checkpoint(
                        progress_pct=last_pct,
                        message=_PHASE_MSG.get(last_phase, last_phase),
                        state={"slug": slug, "phase": last_phase},
                    )
                except (JobControl.Cancelled, JobControl.Paused):
                    cancelled = True
                    raise

                # Subprocess done?
                rc = proc.poll()
                if rc is not None:
                    break
                time.sleep(cfg.poll_interval_s)

        except (JobControl.Cancelled, JobControl.Paused):
            self._terminate_subprocess(proc, cfg.cancel_grace_s)
            raise
        finally:
            drain_thread.join(timeout=2.0)

        if proc.returncode != 0:
            tail = "".join(log_lines[-50:]) if log_lines else ""
            raise RuntimeError(
                f"V30 sweep failed (rc={proc.returncode}). Tail:\n{tail}"
            )

        # Resolve the artifact dir. The sweep's domain layout is
        # out_root/<domain>/<slug>/. We don't have a deterministic
        # domain map up here, so we glob.
        artifact_dir = self._resolve_artifact_dir(cfg.out_root, slug)
        return str(artifact_dir) if artifact_dir else None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_phase(line: str) -> str | None:
        lc = line.lower()
        for phase_key, pattern in _PHASE_PATTERNS:
            if pattern.lower() in lc:
                return phase_key
        return None

    @staticmethod
    def _terminate_subprocess(proc: subprocess.Popen, grace_s: float) -> None:
        if proc.poll() is not None:
            return
        try:
            proc.terminate()  # SIGTERM on POSIX, TerminateProcess on Windows
        except Exception:
            pass
        try:
            proc.wait(timeout=grace_s)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
                proc.wait(timeout=5.0)
            except Exception:
                pass

    @staticmethod
    def _resolve_artifact_dir(out_root: Path, slug: str) -> Path | None:
        """Find the artifact directory for the given slug.

        Layout: out_root/<domain>/<slug>/. We glob for the slug match
        and return the most-recently-modified candidate.
        """
        if not out_root.is_dir():
            return None
        candidates: list[Path] = []
        for domain_dir in out_root.iterdir():
            if not domain_dir.is_dir():
                continue
            slug_dir = domain_dir / slug
            if slug_dir.is_dir() and (slug_dir / "manifest.json").exists():
                candidates.append(slug_dir)
        if not candidates:
            return None
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return candidates[0]


def make_default_v30_runner(repo_root: Path | None = None) -> V30JobRunner:
    """Convenience factory pointing at the canonical sweep script."""
    if repo_root is None:
        # repo_root = src/polaris_graph/audit_ir/v30_runner.py.parents[3]
        repo_root = Path(__file__).resolve().parents[3]
    config = V30RunnerConfig(
        repo_root=repo_root,
        sweep_script=repo_root / "scripts" / "run_full_scale_v30_phase2.py",
        out_root=repo_root / "outputs" / "polaris_v30_jobs",
    )
    return V30JobRunner(config)
