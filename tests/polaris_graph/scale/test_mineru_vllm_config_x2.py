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
    # The launch command MUST be the PROVEN vLLM inference server. "mineru-vllm-
    # server" IS a real MinerU console script (it wraps `vllm serve` and returns
    # /health 200 on the box) and natively accepts the engine flags below.
    # "mineru-api" is a DIFFERENT script (serves /file_parse, rejects these flags).
    assert argv[0] == "mineru-vllm-server"
    assert cfg.command == "mineru-vllm-server"
    assert "--gpu-memory-utilization" in argv
    assert str(cfg.gpu_memory_utilization) in argv
    # Real vLLM engine flag (the prior --max-concurrency was not a real flag and
    # would abort the launch).
    assert "--max-num-seqs" in argv
    assert "--max-concurrency" not in argv


def test_client_cli_argv_is_the_proven_vlm_http_client_protocol():
    # The shipped client reaches the proven server via the vlm-http-client CLI —
    # NOT an httpx POST to /file_parse (a server that was never launched/proven).
    env = {
        "PG_MINERU25_BACKEND": "vlm-http-client",
        "PG_MINERU25_SERVER_URL": "http://127.0.0.1:30024",
        "PG_MINERU25_CLI_PATH": "/root/mineru_svc/bin/mineru",
    }
    cfg = resolve_mineru_backend(config_path=_CONFIG, env=env)
    assert cfg.client_cli == "/root/mineru_svc/bin/mineru"
    argv = cfg.client_cli_argv("/tmp/doc.pdf", "/tmp/out", "en")
    # Exact proven transport: mineru -p <pdf> -o <out> -b vlm-http-client -u <url> -l <lang>
    assert argv[0] == "/root/mineru_svc/bin/mineru"
    assert argv[1:3] == ["-p", "/tmp/doc.pdf"]
    assert argv[3:5] == ["-o", "/tmp/out"]
    assert "-b" in argv and argv[argv.index("-b") + 1] == "vlm-http-client"
    assert "-u" in argv and argv[argv.index("-u") + 1] == "http://127.0.0.1:30024"
    assert "-l" in argv and argv[argv.index("-l") + 1] == "en"


def test_client_cli_defaults_to_path_lookup_when_unset():
    # No env / yaml override -> "mineru" (resolved on PATH by the caller).
    env = {
        "PG_MINERU25_BACKEND": "vlm-http-client",
        "PG_MINERU25_SERVER_URL": "http://127.0.0.1:30024",
    }
    cfg = resolve_mineru_backend(config_path=_CONFIG, env=env)
    assert cfg.client_cli == "mineru"


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
