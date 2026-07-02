"""I-wire-014 ISSUE B (#1313 W4): regression guard — the in-process mineru25
VLM extraction (``do_parse``) MUST be serialized under the process-wide
``_mineru25_gpu_lock``.

ROOT CAUSE (proven on the VM, 2026-06-27): MinerU's ``do_parse`` is not safe to
call concurrently across threads. PDFium / pypdfium2 (the PDF loader) has
process-global non-thread-safe state ("not allowed to call pdfium functions
simultaneously across threads, not even with different documents" — pypdfium2
#303), and MinerU's model manager is a process-singleton sharing one VLM model.
Production fans each PDF fetch onto its own daemon thread, so two clinical PDFs
fetched concurrently corrupt each other (PdfiumError / torch tensor-shape crash).
The fix serializes ``do_parse`` under a module-wide ``threading.Lock``.

These tests are GPU-free + CI-runnable: they assert the lock primitive EXISTS
and that the ``do_parse`` call site is lexically guarded by ``with
_mineru25_gpu_lock:`` — a structural canary against the lock being dropped /
the call moving outside the critical section in a future refactor. The full
behavioral proof (concurrent extraction corrupts without the lock, succeeds with
it) is VM-artifact-based because CI has no GPU VLM.
"""
import ast
import inspect
import re
import textwrap

from src.tools import access_bypass
from src.tools.access_bypass import AccessBypass


def test_mineru25_gpu_lock_exists_and_is_a_lock():
    """The serialization primitive is present at module scope and is a Lock."""
    lock = getattr(access_bypass, "_mineru25_gpu_lock", None)
    assert lock is not None, "_mineru25_gpu_lock must exist at module scope"
    # threading.Lock() returns a _thread.lock; expose acquire/release semantics.
    assert hasattr(lock, "acquire") and hasattr(lock, "release"), (
        "_mineru25_gpu_lock must be a lock (have acquire/release)"
    )
    # Must be a fresh, non-held lock at import time.
    acquired = lock.acquire(blocking=False)
    assert acquired, "_mineru25_gpu_lock should be free at import"
    lock.release()


def test_do_parse_call_is_guarded_by_the_lock():
    """Structural canary: the ``do_parse(...)`` call in ``_mineru25_extract`` is
    serialized by the process-wide ``_mineru25_gpu_lock``. I-deepfix-001 W09 (#1344)
    refactored the guard from ``with _gpu_ctx:`` to a BOUNDED
    ``_mineru25_gpu_lock.acquire(timeout=...)`` + ``finally: release``, so assert THAT
    structure: the lock is acquired, do_parse is called after the acquire, and the lock
    is released. If a future refactor drops the guard, this fails loudly in CI (no GPU)."""
    src = textwrap.dedent(inspect.getsource(AccessBypass._mineru25_extract))
    acquire_pos = src.find("_mineru25_gpu_lock.acquire")
    call_match = re.search(r"\n\s*do_parse\s*\(", src)
    assert acquire_pos != -1, (
        "_mineru25_gpu_lock.acquire(...) must guard do_parse in _mineru25_extract "
        "(I-wire-014 ISSUE B / W09 bounded lock)."
    )
    assert "_mineru25_gpu_lock.release" in src, (
        "the bounded lock must be released (in a finally) — else the convoy re-opens."
    )
    assert call_match and acquire_pos < call_match.start(), (
        "do_parse(...) must be called AFTER the lock is acquired (inside the guarded region)."
    )


def test_mineru25_lock_covers_all_backends_including_http_client_U1():
    """I-deepfix-001 U1 (#1344): the pdfium serialization lock MUST cover EVERY backend,
    INCLUDING vlm-http-client, because MinerU rasterizes PDF pages client-side with
    pypdfium2 (process-global, non-thread-safe) in ALL backends — only the model
    inference is remote. RED before the fix: the source had
    ``_inproc_vlm = backend != "vlm-http-client"`` which skipped the lock for the
    http-client path -> two fetch threads entered pdfium concurrently -> native SIGSEGV
    that killed drb_78 + drb_90. GREEN after: ``_inproc_vlm = True`` (lock always held)."""
    src = inspect.getsource(AccessBypass._mineru25_extract)
    assert (
        'backend != "vlm-http-client"' not in src
        and "backend != 'vlm-http-client'" not in src
    ), (
        "U1 regression: the mineru GPU lock must NOT be gated OFF for the "
        "vlm-http-client backend — pdfium rasterizes client-side in every backend "
        "(the `_inproc_vlm = backend != 'vlm-http-client'` exclusion must stay removed)."
    )
    assert re.search(r"_inproc_vlm\s*=\s*True", src), (
        "_inproc_vlm must be unconditionally True so the lock serializes pdfium "
        "rasterization for ALL backends (U1 SIGSEGV fix)."
    )


def test_no_unguarded_do_parse_call_in_extractor():
    """Belt-and-suspenders: there is exactly ONE do_parse call and it is the
    guarded one (no second, unprotected invocation sneaked in)."""
    src = inspect.getsource(AccessBypass._mineru25_extract)
    # Count textual do_parse( call sites (excludes the import line + comments by
    # requiring an open paren immediately after).
    call_sites = re.findall(r"\bdo_parse\s*\(", src)
    assert len(call_sites) == 1, (
        f"expected exactly one do_parse(...) call site, found {len(call_sites)} "
        "— a second invocation may be unguarded"
    )
