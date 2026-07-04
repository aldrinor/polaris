"""Box-C behavioral test — MinerU25 extractor rewired to the PROVEN
``vlm-http-client`` subprocess protocol.

Proves the EFFECT ($0 offline, no GPU, no real server) of the Box-C S1b rewrite:
``AccessBypass._mineru25_extract`` no longer imports MinerU or runs ``do_parse``
in-process, and no longer POSTs httpx to a ``mineru-api`` ``/file_parse`` server
that was never launched/proven. It shells out to the isolated-venv ``mineru`` CLI
in ``vlm-http-client`` mode — the EXACT transport that produced the real Box-A
extraction — talking to the resident ``mineru-vllm-server``, and returns the
CLI's VERBATIM markdown.

The in-process crash class (pypdfium2 rasterization / process-singleton VLM /
loop-bound Semaphore / GPU serialization lock) is RETIRED: the CLI runs in its
own venv and its own process. ``subprocess.run`` is monkeypatched so no
network/GPU/child is touched; the tests assert the proven CLI argv, the verbatim
markdown pass-through, and the fail-loud contract.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from src.tools.access_bypass import AccessBypass
from src.polaris_graph.scale.mineru_vllm_config import MineruBackendConfigError

_MINERU_ENV_VARS = (
    "PG_MINERU25_BACKEND",
    "PG_MINERU25_SERVER_URL",
    "PG_MINERU25_CLI_PATH",
    "PG_MINERU25_LANG",
    "PG_MINERU25_HTTP_TIMEOUT_S",
    "PG_MINERU25_TIMEOUT_S",
)

# An absolute path that reliably EXISTS, so the CLI-existence gate passes without
# a real mineru install (the subprocess itself is monkeypatched, never executed).
_EXISTING_CLI = sys.executable


@pytest.fixture(autouse=True)
def _clean_mineru_env(monkeypatch):
    # Start every test from a known-clean env so ambient PG_MINERU25_* cannot
    # perturb the resolved backend / server URL / CLI path.
    for name in _MINERU_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    yield


def _writer_fake(md: str, *, stem: str = "doc", returncode: int = 0):
    """Build a fake ``subprocess.run`` that mimics the mineru CLI: it parses
    ``-o <out_dir>`` from argv and writes ``<out_dir>/<stem>/vlm/<stem>.md``.

    Captures the argv/timeout/env into ``captured`` for assertions.
    """
    captured: dict = {}

    def _fake_run(argv, capture_output=None, text=None, timeout=None, env=None, cwd=None, **_kw):
        captured["argv"] = list(argv)
        captured["timeout"] = timeout
        captured["env"] = env
        captured["cwd"] = cwd
        out_dir = Path(argv[argv.index("-o") + 1])
        if returncode == 0 and md is not None:
            md_path = out_dir / stem / "vlm" / f"{stem}.md"
            md_path.parent.mkdir(parents=True, exist_ok=True)
            md_path.write_text(md, encoding="utf-8")
        return subprocess.CompletedProcess(
            argv, returncode, stdout="ok\n", stderr="" if returncode == 0 else "boom\n"
        )

    return _fake_run, captured


def test_shells_out_proven_vlm_http_client_and_returns_verbatim_markdown(monkeypatch):
    # THE rewrite: the proven CLI `mineru -p <pdf> -o <out> -b vlm-http-client
    # -u <server_url> -l <lang>`, returning the CLI's markdown byte-for-byte.
    monkeypatch.setenv("PG_MINERU25_BACKEND", "vlm-http-client")
    monkeypatch.setenv("PG_MINERU25_SERVER_URL", "http://test-server:30024")
    monkeypatch.setenv("PG_MINERU25_CLI_PATH", _EXISTING_CLI)

    pdf_bytes = b"%PDF-1.7\nreal clinical pdf bytes\n%%EOF"
    server_md = (
        "# Clinical Study\n\n"
        "<table><tr><td>Dose</td><td>n</td><td>Adverse events</td></tr>"
        "<tr><td>5 mg</td><td>120</td><td>3</td></tr></table>\n\n"
        "Tirzepatide reduced HbA1c by 2.1% at 40 weeks."
    )

    fake_run, captured = _writer_fake(server_md)
    monkeypatch.setattr(subprocess, "run", fake_run)

    out = AccessBypass._mineru25_extract(pdf_bytes)

    argv = captured["argv"]
    # The proven transport: the resolved CLI, the vlm-http-client backend, and the
    # resolved server URL (NOT an httpx POST to /file_parse).
    assert argv[0] == _EXISTING_CLI
    assert argv[argv.index("-b") + 1] == "vlm-http-client"
    assert argv[argv.index("-u") + 1] == "http://test-server:30024"
    assert argv[argv.index("-l") + 1] == "en"
    # A finite (never-infinite) timeout is always passed.
    assert isinstance(captured["timeout"], float) and captured["timeout"] > 0
    # PYTHONPATH/VIRTUAL_ENV are stripped so the prod venv can't shadow the CLI venv.
    assert "PYTHONPATH" not in captured["env"]
    assert "VIRTUAL_ENV" not in captured["env"]
    # VERBATIM pass-through: the returned markdown is the CLI's md, unchanged.
    assert out == server_md


def test_lang_overridable(monkeypatch):
    monkeypatch.setenv("PG_MINERU25_BACKEND", "vlm-http-client")
    monkeypatch.setenv("PG_MINERU25_SERVER_URL", "http://h:1/")  # trailing slash
    monkeypatch.setenv("PG_MINERU25_CLI_PATH", _EXISTING_CLI)
    monkeypatch.setenv("PG_MINERU25_LANG", "ch")

    fake_run, captured = _writer_fake("ok body long enough")
    monkeypatch.setattr(subprocess, "run", fake_run)

    AccessBypass._mineru25_extract(b"pdf")
    argv = captured["argv"]
    # Trailing slash on the base URL is normalized.
    assert argv[argv.index("-u") + 1] == "http://h:1"
    assert argv[argv.index("-l") + 1] == "ch"


def test_vlm_http_client_without_url_fails_loud(monkeypatch):
    # The operator-locked no-silent-fallback contract: selecting vlm-http-client
    # with NO server URL must RAISE, never silently degrade to in-process.
    monkeypatch.setenv("PG_MINERU25_BACKEND", "vlm-http-client")
    monkeypatch.setenv("PG_MINERU25_CLI_PATH", _EXISTING_CLI)

    def _no_run(*_a, **_k):  # pragma: no cover - must never be reached
        raise AssertionError("subprocess.run must not be called when URL is missing")

    monkeypatch.setattr(subprocess, "run", _no_run)
    with pytest.raises(MineruBackendConfigError):
        AccessBypass._mineru25_extract(b"pdf")


def test_missing_url_in_process_default_raises_no_silent_inprocess(monkeypatch):
    # Backend unset => in-process default, but the in-process path is RETIRED.
    # With no server URL there is nothing to fall back to in-process, so raise
    # LOUDLY (the async wrapper turns this into a disclosed Docling degrade).
    def _no_run(*_a, **_k):  # pragma: no cover - must never be reached
        raise AssertionError("subprocess.run must not be called when URL is missing")

    monkeypatch.setattr(subprocess, "run", _no_run)
    with pytest.raises(RuntimeError) as exc:
        AccessBypass._mineru25_extract(b"pdf")
    assert "retired" in str(exc.value).lower() or "no server url" in str(exc.value).lower()


def test_missing_cli_fails_loud(monkeypatch):
    # A configured server URL but an unreachable CLI must RAISE (no silent
    # capability downgrade to a lesser extractor); the async wrapper turns this
    # into a disclosed Docling degrade.
    monkeypatch.setenv("PG_MINERU25_BACKEND", "vlm-http-client")
    monkeypatch.setenv("PG_MINERU25_SERVER_URL", "http://s:3")
    monkeypatch.setenv("PG_MINERU25_CLI_PATH", "/nonexistent/venv/bin/mineru")

    def _no_run(*_a, **_k):  # pragma: no cover - must never be reached
        raise AssertionError("subprocess.run must not be called when CLI is missing")

    monkeypatch.setattr(subprocess, "run", _no_run)
    with pytest.raises(RuntimeError) as exc:
        AccessBypass._mineru25_extract(b"pdf")
    assert "cli not found" in str(exc.value).lower()


def test_nonzero_exit_propagates_as_health_failure(monkeypatch):
    # A non-zero CLI exit (server error / child crash) is a genuine mineru HEALTH
    # failure — it must PROPAGATE (the async wrapper counts it toward the circuit
    # breaker + LOUD Docling), never be swallowed into a silent empty return.
    monkeypatch.setenv("PG_MINERU25_BACKEND", "vlm-http-client")
    monkeypatch.setenv("PG_MINERU25_SERVER_URL", "http://s:4")
    monkeypatch.setenv("PG_MINERU25_CLI_PATH", _EXISTING_CLI)

    fake_run, _ = _writer_fake(None, returncode=3)
    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError) as exc:
        AccessBypass._mineru25_extract(b"pdf")
    assert "exited 3" in str(exc.value)


def test_no_markdown_returns_empty_string(monkeypatch):
    # A clean exit with no markdown (landing stub) => return "" so the async
    # wrapper degrades to Docling WITHOUT counting a health failure.
    monkeypatch.setenv("PG_MINERU25_BACKEND", "vlm-http-client")
    monkeypatch.setenv("PG_MINERU25_SERVER_URL", "http://s:5")
    monkeypatch.setenv("PG_MINERU25_CLI_PATH", _EXISTING_CLI)

    fake_run, _ = _writer_fake(None, returncode=0)  # exit 0 but writes no .md
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert AccessBypass._mineru25_extract(b"pdf") == ""


def test_does_not_import_mineru_do_parse(monkeypatch):
    # Structural proof the crash class is retired: the happy path never imports
    # mineru.cli.common.do_parse in the pipeline process. Poison the import so any
    # in-process attempt would blow up; the subprocess path must succeed regardless.
    import builtins

    monkeypatch.setenv("PG_MINERU25_BACKEND", "vlm-http-client")
    monkeypatch.setenv("PG_MINERU25_SERVER_URL", "http://s:6")
    monkeypatch.setenv("PG_MINERU25_CLI_PATH", _EXISTING_CLI)

    real_import = builtins.__import__

    def _poisoned_import(name, *args, **kwargs):
        if name.startswith("mineru"):
            raise AssertionError(f"in-process mineru import attempted: {name}")
        return real_import(name, *args, **kwargs)

    fake_run, _ = _writer_fake("real md body")
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(builtins, "__import__", _poisoned_import)
    assert AccessBypass._mineru25_extract(b"pdf") == "real md body"
