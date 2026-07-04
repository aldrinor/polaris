"""Box-C (I-deepfix-001): the mineru25 in-process VLM crash class is RETIRED.

HISTORY: I-wire-014 ISSUE B (#1313) + I-deepfix-001 U1 (#1344) serialized MinerU's
in-process ``do_parse`` under a process-wide ``_mineru25_gpu_lock`` because
pypdfium2 page rasterization is process-global / non-thread-safe (the native
SIGSEGV that killed drb_78/drb_90) and MinerU's model manager is a
process-singleton sharing one VLM model.

Box-C RETIRED that entire path: ``AccessBypass._mineru25_extract`` now shells out
to the isolated-venv ``mineru`` CLI in ``vlm-http-client`` mode (the PROVEN
transport), talking to the dedicated-GPU ``mineru-vllm-server``. Rasterization
runs in the CLI CHILD process (its own venv, its own pypdfium2 state) and the VLM
runs in the resident server — so there is nothing left to serialize client-side,
and the crash class is gone (not merely mitigated): a child crash is a non-zero
exit, never a pipeline-process SIGSEGV.

These tests are the regression guard for the retirement: the extractor must NOT
call the in-process ``do_parse`` and must NOT re-introduce a client-side GPU lock
(either would resurrect the crash class Box-C removed). They are GPU-free /
CI-runnable structural checks on the extractor source.
"""
import inspect
import re

from src.tools.access_bypass import AccessBypass


def _extractor_src() -> str:
    return inspect.getsource(AccessBypass._mineru25_extract)


def test_extractor_does_not_call_in_process_do_parse():
    """The extractor must NOT invoke MinerU's in-process ``do_parse`` — that is
    the pypdfium2 / process-singleton-VLM crash class Box-C removed by moving
    extraction into the mineru CLI child process and the resident
    ``mineru-vllm-server``."""
    src = _extractor_src()
    assert re.search(r"\bdo_parse\s*\(", src) is None, (
        "Box-C retirement regression: _mineru25_extract must NOT call the "
        "in-process MinerU do_parse. Extraction runs in the mineru CLI child "
        "process via the vlm-http-client protocol."
    )


def test_extractor_does_not_hold_client_side_gpu_lock():
    """The extractor must NOT acquire a client-side GPU serialization lock —
    rasterization + the VLM moved into the server process, so there is nothing to
    serialize here (re-adding the lock would signal the in-process path returned)."""
    src = _extractor_src()
    assert "_mineru25_gpu_lock" not in src, (
        "Box-C retirement regression: _mineru25_extract must NOT reference a "
        "client-side GPU serialization lock — the crash class it guarded moved "
        "into the mineru CLI child process and the resident mineru-vllm-server."
    )


def test_extractor_uses_proven_vlm_http_client_subprocess():
    """Positive invariant: the extractor shells out to the PROVEN vlm-http-client
    CLI (``subprocess`` + ``client_cli_argv``) — the transport that gave the real
    Box-A extraction — NOT an httpx POST to a ``mineru-api`` ``/file_parse`` server
    that was never launched/proven (that client 404'd against mineru-vllm-server)."""
    src = _extractor_src()
    assert "subprocess.run(" in src, "the extractor must invoke the mineru CLI via subprocess."
    assert "client_cli_argv(" in src, (
        "the extractor must build the proven vlm-http-client CLI argv."
    )
    # It must NOT POST via httpx to the unproven mineru-api /file_parse server
    # (that client 404'd against the proven mineru-vllm-server). Guard the actual
    # call, not the docstring which legitimately explains the retired path.
    assert "httpx.post(" not in src, (
        "the extractor must NOT POST via httpx to the unproven /file_parse server."
    )
