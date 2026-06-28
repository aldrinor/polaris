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
    inside a ``with _mineru25_gpu_lock:`` block. If a future refactor moves the
    call out of the critical section (re-opening the concurrency crash), this
    fails loudly in CI without needing a GPU."""
    src = textwrap.dedent(inspect.getsource(AccessBypass._mineru25_extract))
    tree = ast.parse(src)

    # Production serializes via an ALIAS: `_gpu_ctx = _mineru25_gpu_lock if
    # _inproc_vlm else nullcontext()` then `with _gpu_ctx:`. So accept a `with`
    # over _mineru25_gpu_lock directly OR over any name conditionally/directly
    # bound from it. Collect those aliases (a name whose assignment RHS references
    # _mineru25_gpu_lock). If the lock is ever dropped, no alias references it and
    # this still fails loudly.
    lock_aliases = {"_mineru25_gpu_lock"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(n, ast.Name) and n.id == "_mineru25_gpu_lock"
            for n in ast.walk(node.value)
        ):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    lock_aliases.add(tgt.id)

    found_guarded_do_parse = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.With):
            continue
        # Does this `with` use _mineru25_gpu_lock (or an alias bound from it) as a CM?
        guards_lock = any(
            (
                isinstance(item.context_expr, ast.Name)
                and item.context_expr.id in lock_aliases
            )
            for item in node.items
        )
        if not guards_lock:
            continue
        # Is there a call to do_parse(...) anywhere inside this with-body?
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Name)
                and inner.func.id == "do_parse"
            ):
                found_guarded_do_parse = True
                break
        if found_guarded_do_parse:
            break

    assert found_guarded_do_parse, (
        "do_parse(...) must be called inside `with _mineru25_gpu_lock:` in "
        "AccessBypass._mineru25_extract — the concurrency-crash serialization "
        "guard (I-wire-014 ISSUE B). Found do_parse outside the lock or the "
        "lock missing."
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
