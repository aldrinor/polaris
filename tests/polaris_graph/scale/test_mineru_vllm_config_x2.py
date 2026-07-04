"""X2 behavioral test — mineru dedicated-GPU vLLM http-server config resolver.

Proves the EFFECT (RED→GREEN, $0 offline, no GPU): the resolver FAILS LOUD when
the http-client backend is selected without a server URL, so the pipeline can
never SILENTLY fall back to in-process mineru and re-create the
CUBLAS_STATUS_ALLOC_FAILED OOM this fix removes. Also proves the resolved config
pins the dedicated card + bounded gpu-memory-utilization.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.polaris_graph.scale.mineru_vllm_config import (
    MineruBackendConfigError,
    resolve_mineru_backend,
)

_CONFIG = Path("config/serving/mineru_vllm_server.yaml")


def test_http_client_without_url_fails_loud():
    # THE fix: selecting vlm-http-client with no server URL must RAISE — never a
    # silent in-process fall-back (that is the OOM this fix exists to remove).
    env = {"PG_MINERU25_BACKEND": "vlm-http-client"}
    with pytest.raises(MineruBackendConfigError) as exc:
        resolve_mineru_backend(config_path=_CONFIG, env=env)
    assert "server_url" in str(exc.value).lower() or "PG_MINERU25_SERVER_URL" in str(
        exc.value
    )


def test_http_client_with_url_resolves():
    env = {
        "PG_MINERU25_BACKEND": "vlm-http-client",
        "PG_MINERU25_SERVER_URL": "http://127.0.0.1:30024",
    }
    cfg = resolve_mineru_backend(config_path=_CONFIG, env=env)
    assert cfg.is_http_client
    assert cfg.server_url == "http://127.0.0.1:30024"
    assert cfg.source == "env"


def test_default_is_in_process_and_keeps_winner():
    # No env → in-process default (single-GPU boxes), still the mineru25 winner.
    cfg = resolve_mineru_backend(config_path=_CONFIG, env={})
    assert not cfg.is_http_client
    assert cfg.backend == "in-process"


def test_dedicated_card_and_bounded_gpu_util():
    env = {
        "PG_MINERU25_BACKEND": "vlm-http-client",
        "PG_MINERU25_SERVER_URL": "http://127.0.0.1:30024",
    }
    cfg = resolve_mineru_backend(config_path=_CONFIG, env=env)
    # Dedicated card 1; embedder/reranker keep card 0.
    assert cfg.cuda_visible_devices == "1"
    launch_env = cfg.server_launch_env(base_env={})
    assert launch_env["CUDA_VISIBLE_DEVICES"] == "1"
    # Bounded up-front reservation (prevents filling the card).
    assert 0.0 < cfg.gpu_memory_utilization <= 0.5
    argv = cfg.server_launch_argv()
    assert "--gpu-memory-utilization" in argv
    assert str(cfg.gpu_memory_utilization) in argv
    assert "--max-concurrency" in argv


def test_env_overrides_gpu_util_and_bad_value_fails_loud():
    env = {
        "PG_MINERU25_BACKEND": "vlm-http-client",
        "PG_MINERU25_SERVER_URL": "http://127.0.0.1:30024",
        "PG_MINERU25_GPU_MEM_UTIL": "0.3",
    }
    cfg = resolve_mineru_backend(config_path=_CONFIG, env=env)
    assert cfg.gpu_memory_utilization == pytest.approx(0.3)

    bad = dict(env)
    bad["PG_MINERU25_GPU_MEM_UTIL"] = "not_a_float"
    with pytest.raises(MineruBackendConfigError):
        resolve_mineru_backend(config_path=_CONFIG, env=bad)


def test_unknown_backend_fails_loud():
    with pytest.raises(MineruBackendConfigError):
        resolve_mineru_backend(config_path=_CONFIG, env={"PG_MINERU25_BACKEND": "banana"})
