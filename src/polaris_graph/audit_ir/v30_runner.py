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
from src.polaris_graph.audit_ir.progress_surfaces import (
    SurfaceKind,
    get_surface_bus,
)

logger = logging.getLogger(__name__)


# Codex M-13: map V30 phase keys to progressive Inspector surfaces.
# Per FINAL_PLAN's t-table:
#   t=0      pre-flight estimate          → PREFLIGHT
#   t=0-2    upload/parse progress        → PARSE_PROGRESS
#   t=2-15   live source discovery + tier → TIER_MIX
#   t=15-45  frame coverage manifest      → FRAME_COVERAGE
#   t=45-90  contradiction queue          → CONTRADICTION_QUEUE
#   t=90-120 first verified claim cards   → VERIFIED_CLAIM
#   t=120-145 final synthesis             → SYNTHESIS_COMPLETE
#
# Map each V30 phase to whichever surface it represents. Phases
# that don't represent a user-visible milestone map to None.
_PHASE_TO_SURFACE: dict[str, SurfaceKind | None] = {
    # Codex M-13 v2 review fix: do NOT remap "scope" to PREFLIGHT.
    # The runner emits PREFLIGHT explicitly at t=0 with stable
    # estimate fields (estimated_minutes, cost_cap_usd). If "scope"
    # later overwrote that snapshot, late SSE replayers would lose
    # the estimate. "scope" is a no-op for surface emission; the
    # progress bar still moves via control.checkpoint.
    "scope": None,
    "retrieval": SurfaceKind.TIER_MIX,
    "corpus": SurfaceKind.TIER_MIX,
    "adequacy": SurfaceKind.FRAME_COVERAGE,
    "completeness": SurfaceKind.FRAME_COVERAGE,
    "contradict": SurfaceKind.CONTRADICTION_QUEUE,
    "select": SurfaceKind.VERIFIED_CLAIM,
    "generation": SurfaceKind.VERIFIED_CLAIM,
    "v30_phase2": SurfaceKind.VERIFIED_CLAIM,
    "evaluator": SurfaceKind.VERIFIED_CLAIM,
    "judge": SurfaceKind.VERIFIED_CLAIM,
    "eval_gate": SurfaceKind.VERIFIED_CLAIM,
    "v30_phase1": SurfaceKind.SYNTHESIS_COMPLETE,
    "cost": SurfaceKind.SYNTHESIS_COMPLETE,
    "status": SurfaceKind.SYNTHESIS_COMPLETE,
}


# Canonical phase milestones the V30 sweep emits to run_log.txt.
#
# Codex M-9 review fix: order + percentages now reflect the ACTUAL run-14
# emission order, not the imagined one. Run-14 log shows:
#   [scope] -> [M-28] -> [M-35] -> [retrieval] -> [m48] -> [corpus]
#   -> [adequacy] -> [completeness] -> [contradict] -> [select]
#   -> [generation] -> [V30-P2] (3 lines) -> [m44/m47/m53]
#   -> [evaluator] -> [judge] -> [eval_gate] -> [V30] (5 lines)
#   -> [cost] -> [status]
V30_PHASES = (
    ("scope",              5.0,   "Scope gate"),
    ("retrieval",          50.0,  "Live retrieval (corpus assembly)"),
    ("corpus",             55.0,  "Corpus tier classification"),
    ("adequacy",           58.0,  "Corpus adequacy gate"),
    ("completeness",       60.0,  "Topic completeness check"),
    ("contradict",         62.0,  "Contradiction detection"),
    ("select",             65.0,  "Evidence selection"),
    ("generation",         75.0,  "Multi-section generation"),
    ("v30_phase2",         85.0,  "V30 Phase-2 slot-bound generation"),
    ("evaluator",          90.0,  "Evaluator rule checks"),
    ("judge",              92.0,  "Qwen judge"),
    ("eval_gate",          94.0,  "Evaluator gate decision"),
    ("v30_phase1",         97.0,  "V30 Phase-1 frame coverage"),
    ("cost",               99.0,  "Cost ledger finalized"),
    ("status",             100.0, "Sweep complete"),
)


# Run_log.txt patterns map to phase keys above. Patterns are loose
# substring matches on log lines.
#
# Codex M-9 review fix: patterns now match the actual canonical bracketed
# tags emitted by run_honest_sweep_r3.py. Order is checked sequentially
# (first match wins) so more specific tags come first.
_PHASE_PATTERNS: tuple[tuple[str, str], ...] = (
    # Terminal markers checked first.
    ("status",       "[status]"),
    ("cost",         "[cost]"),
    # V30 Phase-1 (post-eval-gate) and Phase-2 (during generation) are
    # tagged distinctly: [V30] vs [V30-P2].
    ("v30_phase1",   "[v30]"),
    ("v30_phase2",   "[v30-p2]"),
    # Eval pipeline.
    ("eval_gate",    "[eval_gate]"),
    ("judge",        "[judge]"),
    ("evaluator",    "[evaluator]"),
    # Generation + selection.
    ("select",       "[select]"),
    ("generation",   "[generation]"),
    # Pre-generation gates.
    ("contradict",   "[contradict]"),
    ("completeness", "[completeness]"),
    ("adequacy",     "[adequacy]"),
    ("corpus",       "[corpus]"),
    ("retrieval",    "[retrieval]"),
    ("scope",        "[scope]"),
)

_PHASE_PCT: dict[str, float] = {key: pct for key, pct, _ in V30_PHASES}
_PHASE_MSG: dict[str, str] = {key: msg for key, _, msg in V30_PHASES}


def _read_env_float(name: str, default: float) -> float:
    """Codex M-13: env-driven numeric estimate for the PREFLIGHT
    surface. Garbage values fall back to default per LAW VI."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


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

        # Codex M-9 review fix: per-job output root so concurrent or
        # sequential reruns of the same slug never overwrite each other.
        # Layout becomes out_root/<job_id>/<domain>/<slug>/.
        per_job_out_root = cfg.out_root / job.job_id
        per_job_out_root.mkdir(parents=True, exist_ok=True)

        # Subprocess env: inherit + add V30 env extras.
        env = dict(os.environ)
        if cfg.extra_env:
            env.update(cfg.extra_env)

        cmd = [
            cfg.python_bin,
            str(cfg.sweep_script),
            "--only", slug,
            "--out-root", str(per_job_out_root),
        ]

        # Initial checkpoint so the queue shows progress immediately.
        # Codex M-9 v2 review fix: guard this with the same Paused →
        # RuntimeError conversion as the loop checkpoints.
        try:
            control.checkpoint(
                progress_pct=1.0,
                message="Launching V30 sweep subprocess",
                state={"slug": slug, "phase": "launch"},
            )
        except JobControl.Cancelled:
            raise
        except JobControl.Paused:
            raise RuntimeError(
                "Pause is not supported for template_id='v30_clinical' "
                "in Phase B. Use cancel + re-enqueue instead."
            ) from None

        # Codex M-13: emit a PREFLIGHT surface so the Inspector UI
        # can render scope/cost/time estimate immediately at t=0.
        # The actual estimates are derived from the slug + sweep
        # config; richer per-slug estimates land in Phase C.
        self._emit_surface(
            job, SurfaceKind.PREFLIGHT, {
                "slug": slug,
                "estimated_minutes": 145,  # FINAL_PLAN p90 target
                "cost_cap_usd": _read_env_float("PG_MAX_COST_PER_RUN", 10.0),
                "phase": "launch",
            },
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

        # Codex M-9 v3 review fix: subprocess termination MUST happen
        # in `finally`, not in individual `except` blocks. Earlier
        # iterations called `_terminate_subprocess` only inside
        # `except JobControl.Cancelled` / `except JobControl.Paused`.
        # That left a hole: when the inner per-phase or periodic
        # checkpoint converted Paused → RuntimeError, the RuntimeError
        # propagated past the outer Cancelled/Paused excepts (no match)
        # and the V30 child kept running in the background while the
        # job was marked failed. Centralizing termination in `finally`
        # closes that gap for ALL exit paths (Cancelled, Paused,
        # Paused→RuntimeError, any other RuntimeError, normal exit).
        # `_terminate_subprocess` is idempotent — it no-ops if the
        # process has already exited (proc.poll() is not None).
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
                        except JobControl.Cancelled:
                            raise
                        except JobControl.Paused:
                            raise RuntimeError(
                                "Pause is not supported for template_id='v30_clinical' "
                                "in Phase B. Use cancel + re-enqueue instead."
                            ) from None
                        # Codex M-13: emit a progressive surface
                        # for the new phase. Phases that don't map
                        # to a user-visible milestone (PHASE_MAP
                        # entry is None) are skipped. The progress
                        # bar still moves via control.checkpoint
                        # above; surfaces are an additional view.
                        surface_kind = _PHASE_TO_SURFACE.get(phase)
                        if surface_kind is not None:
                            self._emit_surface(
                                job, surface_kind, {
                                    "slug": slug,
                                    "phase": phase,
                                    "progress_pct": last_pct,
                                    "message": _PHASE_MSG[phase],
                                    "log_line": line.strip()[:300],
                                },
                            )

                # Periodic checkpoint even when no new phase fires
                # (so cancel/pause requests are detected within
                # poll_interval_s).
                try:
                    control.checkpoint(
                        progress_pct=last_pct,
                        message=_PHASE_MSG.get(last_phase, last_phase),
                        state={"slug": slug, "phase": last_phase},
                    )
                except JobControl.Cancelled:
                    raise
                except JobControl.Paused:
                    # Codex M-9 review fix: pause is not supported for
                    # V30 in Phase B. Convert to a hard failure so the
                    # user sees "Pause unsupported for v30_clinical"
                    # rather than ending up in a paused/resumable state
                    # that re-runs from scratch on resume.
                    raise RuntimeError(
                        "Pause is not supported for template_id='v30_clinical' "
                        "in Phase B. Use cancel + re-enqueue instead. "
                        "(Phase C M-13 progressive surfaces will enable "
                        "real pause via SSE streaming.)"
                    ) from None

                # Subprocess done?
                rc = proc.poll()
                if rc is not None:
                    break
                time.sleep(cfg.poll_interval_s)

        except JobControl.Paused:
            # Safety net: if Paused escapes through to the outer scope
            # (neither inner except converted it), convert here.
            raise RuntimeError(
                "Pause is not supported for template_id='v30_clinical' "
                "in Phase B. Use cancel + re-enqueue instead."
            ) from None
        finally:
            self._terminate_subprocess(proc, cfg.cancel_grace_s)
            drain_thread.join(timeout=2.0)

        if proc.returncode != 0:
            tail = "".join(log_lines[-50:]) if log_lines else ""
            raise RuntimeError(
                f"V30 sweep failed (rc={proc.returncode}). Tail:\n{tail}"
            )

        # Resolve the artifact dir. Per-job out_root means there's
        # exactly one valid <domain>/<slug>/ underneath; no mtime
        # tie-breaking needed.
        artifact_dir = self._resolve_artifact_dir(per_job_out_root, slug)
        return str(artifact_dir) if artifact_dir else None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _emit_surface(
        job: Job, kind: SurfaceKind, payload: dict[str, Any]
    ) -> None:
        """Codex M-13: best-effort surface emission. Never let a
        bus error fail the audit run — surfaces are auxiliary."""
        try:
            get_surface_bus().emit(job.job_id, kind, payload)
        except Exception:  # pragma: no cover - defensive
            logger.exception("surface emit failed for job %s", job.job_id)

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
