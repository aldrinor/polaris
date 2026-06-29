"""I-deepfix-001 BUG-B (#1344): mineru25 (W4 clinical-PDF VLM) circuit breaker.

`_maybe_mineru25_extract` already has a per-call `PG_MINERU25_TIMEOUT_S` (300s)
wall, but had NO circuit breaker. On a GPU host where mineru25 is consistently
failing/timing out (model-load failure, CUDA OOM, hung VLM), EVERY clinical PDF
in a ~1000-URL run pays the full 300s before falling back to Docling — the run
grinds for hours.

BUG-B mirrors the existing module-global jina / firecrawl / zyte / crawl4ai
breakers (access_bypass.py:67-91): after N CONSECUTIVE genuine mineru25 failures
(timeout OR hard exception — NOT a thin/empty per-PDF content outcome), OPEN the
breaker for a cooldown so subsequent PDFs skip mineru25 directly and go straight
to the UNCHANGED Docling -> PyMuPDF fallback (the body STILL gets extracted — no
source dropped, just faster). A genuine success resets the counter.

§-1.3 / faithfulness: this changes only the EXTRACTOR-SELECTION TIMING. The body is
still extracted by the disclosed Docling/PyMuPDF fallback (no source dropped, no
cap/thin/target), and the verbatim text strict_verify grounds is unchanged. Every
open-skip is a LOUD, disclosed degradation (W4-CANARY + tool-trace), never silent.

Default-ON (a healthy run never trips => byte-identical happy path); a disable
sentinel (`PG_MINERU25_CIRCUIT_THRESHOLD <= 0`) turns it off.

Offline + GPU-free: `_gpu_available` is monkeypatched True and `_mineru25_extract`
is replaced with a controllable stub; no GPU, no network, no real VLM.
"""
from __future__ import annotations

import asyncio

import pytest

from src.tools import access_bypass
from src.tools.access_bypass import AccessBypass

_URL = "https://example.org/clinical-trial.pdf"
_PDF = b"%PDF-1.7\n" + b"x" * 4096


@pytest.fixture(autouse=True)
def _reset_breaker_and_env(monkeypatch):
    """Module-global breaker state is process-wide; reset before/after each test so
    the suite is order-independent. Also neutralize the per-call timeout knob and
    the tool-tracer so tests are fast + isolated."""
    access_bypass._mineru25_consecutive_failures = 0
    access_bypass._mineru25_circuit_open_until = 0.0
    monkeypatch.setenv("PG_MINERU25_TIMEOUT_S", "5")
    yield
    access_bypass._mineru25_consecutive_failures = 0
    access_bypass._mineru25_circuit_open_until = 0.0


def _bypass() -> AccessBypass:
    return AccessBypass()


def _force_gpu(monkeypatch) -> None:
    monkeypatch.setattr(AccessBypass, "_gpu_available", staticmethod(lambda: True))


class _Counter:
    """A controllable `_mineru25_extract` replacement that counts invocations and
    returns/raises per a scripted behaviour."""

    def __init__(self, behaviour):
        self.calls = 0
        self.behaviour = behaviour

    def __call__(self, pdf_bytes):
        self.calls += 1
        result = self.behaviour
        if isinstance(result, BaseException):
            raise result
        return result


# ── 1. module-global breaker state + separate knobs ──────────────────────────
def test_breaker_state_defined_in_module_source() -> None:
    """The breaker globals must be DEFINED in the module source (mirroring the
    jina/firecrawl/zyte breakers at 67-77) — not merely fabricated at runtime by a
    test fixture. Read the source so the autouse reset can't mask a missing def."""
    import inspect
    src = inspect.getsource(access_bypass)
    assert "_mineru25_consecutive_failures" in src
    assert "_mineru25_circuit_open_until" in src


def test_breaker_uses_separate_knobs_not_the_shared_threshold() -> None:
    """At 300s/failure the shared `_CIRCUIT_BREAKER_THRESHOLD=8` would need ~40min to
    trip — useless. BUG-B must read its OWN `PG_MINERU25_CIRCUIT_THRESHOLD` /
    `_COOLDOWN` (module-level helpers), and `_maybe_mineru25_extract` must consult
    those helpers (not the shared `_CIRCUIT_BREAKER_THRESHOLD`)."""
    import inspect
    mod_src = inspect.getsource(access_bypass)
    assert "PG_MINERU25_CIRCUIT_THRESHOLD" in mod_src
    assert "PG_MINERU25_CIRCUIT_COOLDOWN" in mod_src
    fn_src = inspect.getsource(AccessBypass._maybe_mineru25_extract)
    assert "_mineru25_circuit_threshold(" in fn_src
    assert "_CIRCUIT_BREAKER_THRESHOLD" not in fn_src, (
        "must NOT reuse the shared fetch-provider threshold (8 => ~40min to trip)"
    )


def test_default_threshold_is_small(monkeypatch) -> None:
    """The default threshold must be small (a 300s-per-failure wall demands quick
    tripping). Assert the default is <= 5 (we ship 3)."""
    monkeypatch.delenv("PG_MINERU25_CIRCUIT_THRESHOLD", raising=False)
    assert access_bypass._mineru25_circuit_threshold() <= 5
    assert access_bypass._mineru25_circuit_threshold() >= 1


# ── 2. the breaker OPENS after N consecutive hard failures ───────────────────
def test_breaker_opens_after_threshold_consecutive_failures(monkeypatch) -> None:
    _force_gpu(monkeypatch)
    monkeypatch.setenv("PG_MINERU25_CIRCUIT_THRESHOLD", "3")
    monkeypatch.setenv("PG_MINERU25_CIRCUIT_COOLDOWN", "120")
    stub = _Counter(RuntimeError("CUDA error: device-side assert"))
    monkeypatch.setattr(AccessBypass, "_mineru25_extract", staticmethod(stub))
    ab = _bypass()

    # First 3 calls each INVOKE the extractor (and fail -> "").
    for _ in range(3):
        out = asyncio.run(ab._maybe_mineru25_extract(_URL, _PDF))
        assert out == ""
    assert stub.calls == 3

    # The breaker is now OPEN: the 4th and 5th calls SKIP the extractor entirely.
    for _ in range(2):
        out = asyncio.run(ab._maybe_mineru25_extract(_URL, _PDF))
        assert out == ""
    assert stub.calls == 3, "breaker open => _mineru25_extract must NOT be invoked"


def test_breaker_opens_after_consecutive_timeouts(monkeypatch) -> None:
    """A hung VLM (timeout) is a genuine failure that must count toward the breaker
    (the dominant grind mode)."""
    _force_gpu(monkeypatch)
    monkeypatch.setenv("PG_MINERU25_CIRCUIT_THRESHOLD", "2")
    monkeypatch.setenv("PG_MINERU25_TIMEOUT_S", "0.05")

    def _hang(pdf_bytes):
        import time as _t
        _t.sleep(5)  # exceeds the 0.05s wall -> asyncio.TimeoutError
        return "x" * 1000

    monkeypatch.setattr(AccessBypass, "_mineru25_extract", staticmethod(_hang))
    ab = _bypass()
    for _ in range(2):
        assert asyncio.run(ab._maybe_mineru25_extract(_URL, _PDF)) == ""
    # Breaker open: a 3rd call returns "" fast (no 5s hang).
    import time as _t
    t0 = _t.perf_counter()
    assert asyncio.run(ab._maybe_mineru25_extract(_URL, _PDF)) == ""
    assert _t.perf_counter() - t0 < 1.0, "open breaker must skip the hung extractor"


# ── 3. a genuine success RESETS the counter ──────────────────────────────────
def test_success_resets_the_failure_counter(monkeypatch) -> None:
    _force_gpu(monkeypatch)
    monkeypatch.setenv("PG_MINERU25_CIRCUIT_THRESHOLD", "3")
    ab = _bypass()

    fail = _Counter(RuntimeError("boom"))
    monkeypatch.setattr(AccessBypass, "_mineru25_extract", staticmethod(fail))
    for _ in range(2):  # 2 < threshold 3 -> not yet open
        assert asyncio.run(ab._maybe_mineru25_extract(_URL, _PDF)) == ""
    assert access_bypass._mineru25_consecutive_failures == 2

    # A genuine success (md > 500 chars) must RESET the counter to 0.
    ok = _Counter("y" * 1000)
    monkeypatch.setattr(AccessBypass, "_mineru25_extract", staticmethod(ok))
    out = asyncio.run(ab._maybe_mineru25_extract(_URL, _PDF))
    assert out == "y" * 1000
    assert access_bypass._mineru25_consecutive_failures == 0


# ── 4. thin/empty output does NOT trip the breaker ───────────────────────────
def test_thin_empty_output_does_not_trip_the_breaker(monkeypatch) -> None:
    """A thin/empty extraction is a per-PDF CONTENT outcome (this PDF was a landing
    stub), not a mineru HEALTH failure. Tripping on it would skip PDFs mineru could
    handle => the breaker must NOT count it."""
    _force_gpu(monkeypatch)
    monkeypatch.setenv("PG_MINERU25_CIRCUIT_THRESHOLD", "2")
    thin = _Counter("short")  # < 500 chars -> disclosed fallback, but NOT a failure
    monkeypatch.setattr(AccessBypass, "_mineru25_extract", staticmethod(thin))
    ab = _bypass()
    for _ in range(5):
        assert asyncio.run(ab._maybe_mineru25_extract(_URL, _PDF)) == ""
    assert thin.calls == 5, "thin/empty must NOT open the breaker (no skip)"
    assert access_bypass._mineru25_consecutive_failures == 0


# ── 5. disable sentinel (threshold <= 0) ─────────────────────────────────────
def test_disable_sentinel_keeps_breaker_off(monkeypatch) -> None:
    _force_gpu(monkeypatch)
    monkeypatch.setenv("PG_MINERU25_CIRCUIT_THRESHOLD", "0")
    fail = _Counter(RuntimeError("boom"))
    monkeypatch.setattr(AccessBypass, "_mineru25_extract", staticmethod(fail))
    ab = _bypass()
    for _ in range(6):
        assert asyncio.run(ab._maybe_mineru25_extract(_URL, _PDF)) == ""
    # Threshold <= 0 disables the breaker entirely -> every call still invokes.
    assert fail.calls == 6, "threshold<=0 must disable the breaker (no skip)"
