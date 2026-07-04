"""X2 — mineru PDF extraction as a dedicated-GPU vLLM http-server (config-only).

The W4 clinical-PDF winner is ``mineru25``. Its vLLM engine reserves ~72GB up
front and does NOT reap crashed worker subprocs, so running it IN-PROCESS on the
shared card fills the GPU and the embedder/reranker then die with
``CUBLAS_STATUS_ALLOC_FAILED`` — hanging the live pipeline on the first real PDF
(corpora are ~72% PDFs). This is a pure INFRA fix (the winner MODEL is kept):
run mineru as a supervised vLLM http-server on a DEDICATED card and talk to it
as an http client; the embedder/reranker keep card 0.

This module is CONFIG-ONLY: it resolves the backend selection from env + the
YAML config, and — critically — FAILS LOUD when ``vlm-http-client`` is selected
without a server URL, so the pipeline can never SILENTLY fall back to in-process
and re-create the OOM this fix exists to prevent (LAW II: no silent fallback).

LAW VI: every value comes from env or ``config/serving/mineru_vllm_server.yaml``.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("polaris_graph.scale.mineru_vllm")

_BACKEND_IN_PROCESS = "in-process"
_BACKEND_HTTP_CLIENT = "vlm-http-client"
_VALID_BACKENDS = {_BACKEND_IN_PROCESS, _BACKEND_HTTP_CLIENT}

# Repo-relative default config path (LAW VI — data lives in config/, not code).
_DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[3]
    / "config"
    / "serving"
    / "mineru_vllm_server.yaml"
)


class MineruBackendConfigError(RuntimeError):
    """Raised when the mineru backend selection is internally inconsistent.

    The canonical case: ``PG_MINERU25_BACKEND=vlm-http-client`` with no server
    URL. Failing loud here is the whole point — a silent fall-back to in-process
    is exactly the OOM this fix removes.
    """


@dataclass
class MineruVllmConfig:
    """Resolved mineru extraction backend configuration."""

    backend: str
    server_url: str = ""
    cuda_visible_devices: str = "1"
    gpu_memory_utilization: float = 0.4
    max_concurrency: int = 20
    host: str = "127.0.0.1"
    port: int = 30024
    # The GPU vLLM inference server the pipeline talks to via the PROVEN
    # ``vlm-http-client`` protocol. ``mineru-vllm-server`` IS a real MinerU
    # console script: it wraps ``vllm serve <MinerU2.5 model>`` and therefore
    # natively accepts the vLLM engine flags (``--gpu-memory-utilization`` /
    # ``--max-num-seqs`` / ``--host`` / ``--port``). It serves the OpenAI-
    # compatible inference API on ``server_url``; the pipeline reaches it through
    # the ``mineru`` CLI in ``vlm-http-client`` mode (``client_cli`` below) — the
    # exact transport that produced the real Box-A extraction (13/13 pages, 6
    # reconstructed tables that Docling loses).
    # NOTE: ``mineru-api`` is a SEPARATE console script that serves POST
    # /file_parse and hosts the engine in-process; it accepts ONLY
    # ``--host``/``--port``/``--reload`` (NOT the engine flags above) and was not
    # the proven server, so it is not the default here.
    command: str = "mineru-vllm-server"
    # The isolated-venv ``mineru`` CLI binary the pipeline shells out to for the
    # ``vlm-http-client`` protocol. The prod venv does NOT ship mineru (it lives
    # in its own venv, e.g. ``/root/mineru_svc/bin/mineru``); running it as a
    # subprocess also process-isolates pypdfium2 page rasterization (a SIGSEGV in
    # the child kills the child, degrades LOUD to Docling — it can never crash the
    # pipeline process). Data-driven (LAW VI): env ``PG_MINERU25_CLI_PATH`` > yaml
    # ``client_cli`` > this default.
    client_cli: str = "mineru"
    source: str = "default"  # provenance: env / yaml / default

    @property
    def is_http_client(self) -> bool:
        return self.backend == _BACKEND_HTTP_CLIENT

    def server_launch_argv(self) -> list[str]:
        """The argv a process supervisor uses to launch the dedicated GPU server.

        The command runs OUTSIDE the pipeline process; the caller sets
        ``CUDA_VISIBLE_DEVICES=<cuda_visible_devices>`` in the child env so the
        server is pinned to the dedicated card and the embedder/reranker keep
        card 0.

        ``mineru-vllm-server`` wraps ``vllm serve``, so it accepts these vLLM
        engine flags NATIVELY: ``--host`` / ``--port`` bind the OpenAI-compatible
        endpoint, ``--gpu-memory-utilization`` bounds the up-front KV-cache
        reservation (the §8.4 0.4 bound that keeps the card from filling), and
        ``--max-num-seqs`` bounds concurrent request batching. (The prior
        ``--max-concurrency`` was NOT a real flag; ``--max-num-seqs`` is the real
        vLLM ``EngineArgs`` name.) Verified on the box: the server logs
        ``start vllm server: [... '--gpu-memory-utilization', '0.4',
        '--max-num-seqs', '20']`` and returns ``/health`` 200.
        """
        return [
            self.command,
            "--host",
            self.host,
            "--port",
            str(self.port),
            "--gpu-memory-utilization",
            str(self.gpu_memory_utilization),
            "--max-num-seqs",
            str(self.max_concurrency),
        ]

    def client_cli_argv(
        self,
        pdf_path: str,
        out_dir: str,
        lang: str,
    ) -> list[str]:
        """The PROVEN ``vlm-http-client`` CLI argv the pipeline shells out to.

        This is the exact transport that produced the real Box-A extraction:
        ``mineru -p <pdf> -o <out_dir> -b vlm-http-client -u <server_url> -l <lang>``.
        The ``mineru`` CLI (isolated venv, ``client_cli``) rasterizes the PDF in
        the CHILD process and sends page images to the resident VLM engine on the
        ``mineru-vllm-server`` at ``server_url`` for inference, then assembles the
        markdown (HTML ``<table>`` cells preserved) under
        ``<out_dir>/<pdf-stem>/vlm/<pdf-stem>.md``.

        Requires the http-client backend + a non-empty ``server_url`` — callers
        resolve the config through ``resolve_mineru_backend`` (which FAILS LOUD on
        a missing URL) before building this argv.
        """
        return [
            self.client_cli,
            "-p",
            pdf_path,
            "-o",
            out_dir,
            "-b",
            _BACKEND_HTTP_CLIENT,
            "-u",
            (self.server_url or "").strip().rstrip("/"),
            "-l",
            lang,
        ]

    def server_launch_env(self, base_env: dict[str, str] | None = None) -> dict[str, str]:
        """Child-process env pinning the server to its dedicated card."""
        env = dict(base_env if base_env is not None else os.environ)
        env["CUDA_VISIBLE_DEVICES"] = self.cuda_visible_devices
        return env


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise MineruBackendConfigError(
            f"mineru vLLM config {path} is not valid YAML: {exc}"
        )
    if not isinstance(data, dict):
        raise MineruBackendConfigError(
            f"mineru vLLM config {path} must be a mapping, got {type(data).__name__}"
        )
    return data


def resolve_mineru_backend(
    config_path: str | Path | None = None,
    env: dict[str, str] | None = None,
) -> MineruVllmConfig:
    """Resolve the mineru extraction backend from env + YAML (env wins).

    Precedence (LAW VI): explicit env var > YAML file > dataclass default.

    FAIL LOUD (LAW II): selecting ``vlm-http-client`` without a non-empty
    ``server_url`` raises ``MineruBackendConfigError`` — the pipeline must NOT
    silently fall back to in-process (that re-creates the CUBLAS OOM). An
    unknown backend value also raises.
    """
    env = os.environ if env is None else env
    path = Path(config_path) if config_path else _DEFAULT_CONFIG_PATH
    yaml_cfg = _load_yaml(path)
    server_yaml = yaml_cfg.get("server", {}) or {}

    backend_env = env.get("PG_MINERU25_BACKEND", "").strip()
    backend = backend_env or str(yaml_cfg.get("backend", _BACKEND_IN_PROCESS)).strip()
    source = "env" if backend_env else ("yaml" if yaml_cfg else "default")
    if backend not in _VALID_BACKENDS:
        raise MineruBackendConfigError(
            f"PG_MINERU25_BACKEND / config backend={backend!r} is not one of "
            f"{sorted(_VALID_BACKENDS)}"
        )

    server_url = (
        env.get("PG_MINERU25_SERVER_URL", "").strip()
        or str(yaml_cfg.get("server_url", "") or "").strip()
    )

    def _num(env_name: str, yaml_key: str, default: Any, cast):
        raw = env.get(env_name, "").strip()
        if raw:
            try:
                return cast(raw)
            except ValueError:
                raise MineruBackendConfigError(
                    f"{env_name}={raw!r} is not a valid {cast.__name__}"
                )
        if yaml_key in server_yaml and server_yaml[yaml_key] is not None:
            return cast(server_yaml[yaml_key])
        return default

    cfg = MineruVllmConfig(
        backend=backend,
        server_url=server_url,
        cuda_visible_devices=str(
            env.get("PG_MINERU25_CUDA_DEVICE", "").strip()
            or server_yaml.get("cuda_visible_devices", "1")
        ),
        gpu_memory_utilization=_num(
            "PG_MINERU25_GPU_MEM_UTIL", "gpu_memory_utilization", 0.4, float
        ),
        max_concurrency=_num(
            "PG_MINERU25_MAX_CONCURRENCY", "max_concurrency", 20, int
        ),
        host=str(server_yaml.get("host", "127.0.0.1")),
        port=_num("PG_MINERU25_SERVER_PORT", "port", 30024, int),
        command=str(server_yaml.get("command", "mineru-vllm-server")),
        # The isolated-venv mineru CLI binary (top-level yaml key, NOT under
        # ``server``): env PG_MINERU25_CLI_PATH > yaml ``client_cli`` > "mineru".
        client_cli=str(
            env.get("PG_MINERU25_CLI_PATH", "").strip()
            or (yaml_cfg.get("client_cli") or "").strip()
            or "mineru"
        ),
        source=source,
    )

    if cfg.is_http_client and not cfg.server_url:
        raise MineruBackendConfigError(
            "PG_MINERU25_BACKEND=vlm-http-client requires a non-empty "
            "PG_MINERU25_SERVER_URL (or server_url in the YAML). Refusing to "
            "silently fall back to in-process mineru — that re-creates the "
            "CUBLAS_STATUS_ALLOC_FAILED OOM this fix removes (LAW II fail loud)."
        )

    logger.info(
        "mineru backend resolved: %s (source=%s, url=%r, card=%s, gpu_util=%s)",
        cfg.backend,
        cfg.source,
        cfg.server_url,
        cfg.cuda_visible_devices,
        cfg.gpu_memory_utilization,
    )
    return cfg
