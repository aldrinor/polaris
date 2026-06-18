"""Process-wide shared TLS verification context for httpx clients.

BUG 3 — X509 SSL race (Q76 + Q78-first run-killer). Concurrent httpx client
construction on the verify/judge path (per-thread entailment clients +
parallel distill + parallel verify) crashed with::

    ssl.SSLError: [X509] PEM lib (_ssl.c:4166)

This is the known CPython/OpenSSL race: httpx's default ``verify=True`` makes
EVERY client build call ``ssl.create_default_context(cafile=certifi.where())``
-> ``load_verify_locations``, and concurrent PEM parses corrupt the shared
OpenSSL X509 parse state.

Fix: build ONE ``ssl.SSLContext`` ONCE (guarded by a ``threading.Lock`` at
first use) and pass that SAME validated context as ``verify=<ctx>`` to every
httpx client on the concurrent path. httpx then takes its
``create_ssl_context`` ``else: ctx = verify`` branch and NEVER re-parses the
PEM bundle, so concurrent client construction can no longer race the parser.

HARD CONSTRAINT — TLS verification stays ENABLED. This module NEVER uses
``verify=False``. It replicates httpx's exact ``verify is True`` precedence
(``SSL_CERT_FILE`` -> ``SSL_CERT_DIR`` -> ``certifi.where()``) via
``ssl.create_default_context`` (which yields ``verify_mode=CERT_REQUIRED`` and
``check_hostname=True``), so the shared context performs IDENTICAL real
certificate checking to a default per-client context. It only SHARES one
already-validated context instead of re-parsing the bundle per build.
Faithfulness-neutral: nothing about the verify/judge VERDICTS changes — only
the transport-layer TLS context is shared.

A CPython ``ssl.SSLContext`` is explicitly safe to share across threads and
across multiple connections, which is exactly why one shared instance is the
correct fix rather than a workaround.
"""

from __future__ import annotations

import os
import ssl
import threading

# Lazily-built process-wide singleton. None until first use so importing this
# leaf module never eagerly builds (or PEM-parses) a context — preserves the
# off-mode zero-import-cost contract of the llm leaf modules that import it.
_SHARED_SSL_CONTEXT: ssl.SSLContext | None = None
_SHARED_SSL_LOCK = threading.Lock()


def _build_default_verify_context() -> ssl.SSLContext:
    """Build a CERT-verifying context, mirroring httpx's ``verify is True`` branch.

    Precedence is byte-for-byte httpx 0.28.1's ``create_ssl_context``: respect
    ``SSL_CERT_FILE``, then ``SSL_CERT_DIR``, then fall back to
    ``certifi.where()``. Replicating this precedence is what keeps the change
    behavior-neutral — a deploy that points ``SSL_CERT_FILE`` at an internal CA
    (e.g. the sovereign vLLM endpoint behind ``OPENROUTER_BASE_URL``) keeps
    trusting that CA exactly as it did before. ``create_default_context``
    guarantees ``verify_mode=CERT_REQUIRED`` and ``check_hostname=True``.
    """
    import certifi  # local import: only needed on the (one-time) build path

    # trust_env semantics match httpx's default (trust_env=True).
    ssl_cert_file = os.environ.get("SSL_CERT_FILE")
    ssl_cert_dir = os.environ.get("SSL_CERT_DIR")
    if ssl_cert_file:
        return ssl.create_default_context(cafile=ssl_cert_file)
    if ssl_cert_dir:
        return ssl.create_default_context(capath=ssl_cert_dir)
    return ssl.create_default_context(cafile=certifi.where())


def get_shared_ssl_context() -> ssl.SSLContext:
    """Return the process-wide shared, cert-verifying ``ssl.SSLContext``.

    Built exactly ONCE under ``_SHARED_SSL_LOCK`` (double-checked) so the PEM
    bundle is parsed a single time, off the concurrent client-construction
    path. Every subsequent caller — and every concurrent verify/judge worker —
    receives the SAME already-validated context to hand to
    ``httpx.Client(verify=...)`` / ``httpx.AsyncClient(verify=...)``.
    """
    global _SHARED_SSL_CONTEXT
    if _SHARED_SSL_CONTEXT is None:
        with _SHARED_SSL_LOCK:
            if _SHARED_SSL_CONTEXT is None:
                _SHARED_SSL_CONTEXT = _build_default_verify_context()
    return _SHARED_SSL_CONTEXT
