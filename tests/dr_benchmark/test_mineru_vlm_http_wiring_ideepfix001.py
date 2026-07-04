"""I-deepfix-001 Item-10 (#1344) — mineru25 vlm-http-client backend WIRING (offline, $0, no GPU).

Item 10: on clinical Gate-B runs the W4 winner ``mineru25`` never genuinely ran — the slate forced
``PG_CLINICAL_PDF_EXTRACTOR=mineru25`` but left the mineru BACKEND unset, so ``resolve_mineru_backend``
fell to the YAML default ``in-process``, ``_mineru25_extract`` raised "no server URL configured", every
clinical PDF degraded to the Docling/PyMuPDF loser, and the circuit breaker opened after 3 (proven in
the drb live log). This suite proves the fix's EFFECT:

  1. ``apply_full_capability_benchmark_slate`` now wires the vlm-http-client backend + the standard-local
     server URL as the DEFAULT for clinical runs (``setdefault`` — a box-exported override still WINS).
  2. The WINNER-FIRES W4 preflight helper ``_assert_mineru25_http_backend_ready`` FAILS LOUD before spend
     when the server is unreachable OR the isolated-venv mineru CLI cannot be resolved — so a
     mis-provisioned GPU box can never silently ship the Docling loser.

Everything is OFFLINE: no spend, no network (the /health probe is monkeypatched), no GPU, no model load.
The FROZEN faithfulness engine (strict_verify / NLI / 4-role D8 / provenance / span-grounding) is NEVER
touched — this is extractor-provisioning wiring only.
"""

from __future__ import annotations

import os
import sys

import pytest

from scripts.dr_benchmark.run_gate_b import (
    _assert_mineru25_http_backend_ready,
    apply_full_capability_benchmark_slate,
)

_BACKEND_ENV = "PG_MINERU25_BACKEND"
_SERVER_URL_ENV = "PG_MINERU25_SERVER_URL"
_CLI_PATH_ENV = "PG_MINERU25_CLI_PATH"
_DEFAULT_SERVER_URL = "http://127.0.0.1:30024"


@pytest.fixture(autouse=True)
def _isolate_env():
    """Snapshot os.environ before each test and restore it after so a forced mineru env never leaks
    into a sibling test (mirrors tests/dr_benchmark/test_purity_preflight_gates.py)."""
    snap = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(snap)


class _FakeHealthyResponse:
    """A minimal urlopen() return that mimics a vLLM server GET /health -> 200 (context-manager)."""

    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def getcode(self):
        return 200


# ── (1) slate wiring — vlm-http-client is the DEFAULT for clinical runs ────────────────────────────

def test_slate_wires_mineru_vlm_http_client_default_when_unset():
    """RED before the fix (the slate never set these) / GREEN after: applying the clinical slate points
    mineru25 at the supervised dedicated-GPU vlm-http-client server by default, so
    ``resolve_mineru_backend`` no longer falls to the in-process YAML default and ``_mineru25_extract``
    no longer raises 'no server URL configured'."""
    os.environ.pop(_BACKEND_ENV, None)
    os.environ.pop(_SERVER_URL_ENV, None)

    apply_full_capability_benchmark_slate()

    assert os.environ.get(_BACKEND_ENV) == "vlm-http-client", (
        "slate did not wire the mineru vlm-http-client backend as the clinical-run default"
    )
    assert os.environ.get(_SERVER_URL_ENV) == _DEFAULT_SERVER_URL, (
        "slate did not wire the standard-local mineru-vllm-server URL as the clinical-run default"
    )


def test_slate_mineru_backend_default_resolves_without_raising():
    """The wired defaults must produce a RESOLVABLE http-client config (the whole point — resolve raised
    a MineruBackendConfigError for vlm-http-client without a URL; the wired URL fixes that)."""
    os.environ.pop(_BACKEND_ENV, None)
    os.environ.pop(_SERVER_URL_ENV, None)

    apply_full_capability_benchmark_slate()

    from src.polaris_graph.scale.mineru_vllm_config import resolve_mineru_backend

    cfg = resolve_mineru_backend()
    assert cfg.is_http_client
    assert cfg.server_url == _DEFAULT_SERVER_URL


def test_slate_mineru_env_operator_override_wins():
    """LAW VI: the wiring is a ``setdefault`` DEFAULT, not a hard pin — a box that exports a different
    server URL / backend (its own port, a remote card) KEEPS its value across the slate."""
    os.environ[_BACKEND_ENV] = "vlm-http-client"
    os.environ[_SERVER_URL_ENV] = "http://10.0.0.9:31000"

    apply_full_capability_benchmark_slate()

    assert os.environ[_SERVER_URL_ENV] == "http://10.0.0.9:31000", (
        "the slate CLOBBERED an operator-exported PG_MINERU25_SERVER_URL — must be setdefault (LAW VI)"
    )
    assert os.environ[_BACKEND_ENV] == "vlm-http-client"


# ── (2) WINNER-FIRES W4 readiness — fail loud before spend, never a silent Docling degrade ──────────

def test_readiness_passes_when_server_healthy_and_cli_present(monkeypatch):
    """POSITIVE: http-client backend + a resolvable CLI + a /health-200 server -> no raise (the run is
    genuinely provisioned to run mineru25)."""
    os.environ[_BACKEND_ENV] = "vlm-http-client"
    os.environ[_SERVER_URL_ENV] = _DEFAULT_SERVER_URL
    os.environ[_CLI_PATH_ENV] = sys.executable  # an absolute, existing binary stands in for the CLI

    monkeypatch.setattr("urllib.request.urlopen", lambda *_a, **_k: _FakeHealthyResponse())

    # Must not raise.
    _assert_mineru25_http_backend_ready()


def test_readiness_fails_loud_when_server_unreachable(monkeypatch):
    """NEGATIVE (the Item-10 dark-winner failure): GPU present + CLI present but the mineru-vllm-server is
    NOT running -> the readiness probe FAILS LOUD naming the server URL, BEFORE any paid token, instead of
    silently degrading every clinical PDF to the Docling loser."""
    os.environ[_BACKEND_ENV] = "vlm-http-client"
    os.environ[_SERVER_URL_ENV] = _DEFAULT_SERVER_URL
    os.environ[_CLI_PATH_ENV] = sys.executable

    def _refused(*_a, **_k):
        raise ConnectionRefusedError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", _refused)

    with pytest.raises(RuntimeError) as exc:
        _assert_mineru25_http_backend_ready()
    msg = str(exc.value)
    assert "WINNER-FIRES W4" in msg
    assert _DEFAULT_SERVER_URL in msg and "not reachable" in msg.lower()


def test_readiness_fails_loud_when_cli_unresolvable(monkeypatch):
    """NEGATIVE: http-client backend + a running server but the isolated-venv mineru CLI cannot be
    resolved -> fail loud naming PG_MINERU25_CLI_PATH (the box must set it). The health probe is never
    reached, so a monkeypatched urlopen that would 200 does not mask the CLI fault."""
    os.environ[_BACKEND_ENV] = "vlm-http-client"
    os.environ[_SERVER_URL_ENV] = _DEFAULT_SERVER_URL
    os.environ[_CLI_PATH_ENV] = "/nonexistent/isolated/venv/bin/mineru"

    monkeypatch.setattr("urllib.request.urlopen", lambda *_a, **_k: _FakeHealthyResponse())

    with pytest.raises(RuntimeError) as exc:
        _assert_mineru25_http_backend_ready()
    msg = str(exc.value)
    assert "WINNER-FIRES W4" in msg
    assert "PG_MINERU25_CLI_PATH" in msg and "CLI not found" in msg


def test_readiness_fails_loud_for_stale_in_process_backend_without_url(monkeypatch):
    """Codex P1 (Item-10): a STALE ``PG_MINERU25_BACKEND=in-process`` override must NOT short-circuit the
    probe to a false-green. ``_mineru25_extract`` has NO in-process execution path anymore — it always
    reads ``cfg.server_url``, resolves the CLI, and shells out to the ``vlm-http-client`` CLI. So
    in-process with no server URL raises "no server URL configured" at fetch time and degrades EVERY
    clinical PDF to the Docling loser. The probe must therefore FAIL LOUD before spend, naming the missing
    URL, and must NOT reach the network — the missing-URL fault precedes the /health probe (proven: a
    urlopen that would raise is never called).

    RED before the fix (the old ``if not is_http_client: return`` returned early -> no raise, false-green);
    GREEN after (the server-URL check runs REGARDLESS of the backend label)."""
    os.environ[_BACKEND_ENV] = "in-process"
    os.environ.pop(_SERVER_URL_ENV, None)  # a stale in-process override leaves the URL unset

    def _boom(*_a, **_k):
        raise AssertionError("must fail loud on the missing server URL BEFORE probing /health")

    monkeypatch.setattr("urllib.request.urlopen", _boom)

    with pytest.raises(RuntimeError) as exc:
        _assert_mineru25_http_backend_ready()
    msg = str(exc.value)
    assert "WINNER-FIRES W4" in msg
    assert "server url" in msg.lower()
    assert "retired" in msg.lower()  # names WHY (in-process path is gone) so the fix is actionable


def test_readiness_full_probe_runs_regardless_of_backend_label(monkeypatch):
    """Codex P1 (Item-10): the probe runs the FULL fetch-time checks REGARDLESS of the resolved backend
    LABEL. ``_mineru25_extract`` ignores the label (the ``-b vlm-http-client`` transport is hard-wired in
    ``client_cli_argv``), so a legacy ``in-process`` label that still carries a server URL + a resolvable
    CLI + a healthy server genuinely extracts. The probe must PASS (not fail on the label) AND must
    actually probe the server — proving it is a full probe, not the old early-return.

    RED before the fix (the old early-return skipped /health for the non-http label -> the probe never
    ran, so this assertion that it DID probe fails); GREEN after."""
    os.environ[_BACKEND_ENV] = "in-process"            # legacy/stale label...
    os.environ[_SERVER_URL_ENV] = _DEFAULT_SERVER_URL  # ...but a URL is present (extractor would use it)
    os.environ[_CLI_PATH_ENV] = sys.executable

    _probed = {"health": False}

    def _healthy(*_a, **_k):
        _probed["health"] = True
        return _FakeHealthyResponse()

    monkeypatch.setattr("urllib.request.urlopen", _healthy)

    _assert_mineru25_http_backend_ready()  # must NOT raise
    assert _probed["health"], (
        "the probe returned early on the in-process label instead of running the full /health probe"
    )
