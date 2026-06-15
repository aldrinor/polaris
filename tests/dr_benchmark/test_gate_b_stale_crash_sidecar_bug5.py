"""BUG-5 (I-arch-006 #1262) regression: a STALE ``gate_b_query_crash.json`` from a
prior FAILED attempt must NOT survive a fresh, healthy re-run of the same question.

Symptom (pre-fix): the Gate-B ``--all`` / ``--only`` loop writes a crash SIDECAR
(``gate_b_query_crash.json``) under ``out_root/<domain>/<slug>/`` only on the
EXCEPT path when a query crashes. Nothing cleaned it up. So if a prior attempt of a
question crashed and left that sidecar behind, a later attempt that completed
NORMALLY would still carry the old crash record on disk — a post-run reader
(sweep auditor / status tool) would misread the out-dir as "crashed" even though
THIS attempt succeeded. A healthy run looked crashed.

Fix: on each FRESH attempt of a question (after ``domain``/``slug`` are known, before
``run_gate_b_query`` runs), best-effort delete any pre-existing crash sidecar for
that out-dir. The except-path re-creates the sidecar ONLY if THIS attempt genuinely
crashes — so real crashes are still recorded durably.

Faithfulness: untouched. The crash sidecar is a benchmark-RUNNER status artifact; the
cleanup never reads, alters, drops, or relabels any verified claim, evidence span, or
faithfulness-gate verdict. All hard gates (strict_verify / NLI / 4-role / span-
grounding) run unchanged inside ``run_gate_b_query``, which is monkeypatched out here.

NO network, NO spend: ``run_gate_b_query`` is monkeypatched per case.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts.dr_benchmark import run_gate_b
from scripts.dr_benchmark.run_gate_b import (
    LOCKED_BENCHMARK_SLUGS,
    load_locked_questions,
    main,
)

_CRASH_SIDECAR_NAME = "gate_b_query_crash.json"
_TEST_SLUG = "drb_72_ai_labor"


@pytest.fixture(autouse=True)
def _isolate_env():
    snap = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(snap)


def _domain_for(slug: str) -> str:
    """Resolve the locked question's domain deterministically (no hardcode)."""
    (q,) = load_locked_questions((slug,))
    return q["domain"]


def _seed_stale_sidecar(out_root: Path, domain: str, slug: str) -> Path:
    """Plant a crash sidecar as if a PRIOR attempt had crashed and left it behind."""
    d = out_root / domain / slug
    d.mkdir(parents=True, exist_ok=True)
    sidecar = d / _CRASH_SIDECAR_NAME
    sidecar.write_text(
        json.dumps(
            {
                "status": "error_query_crashed",
                "slug": slug,
                "domain": domain,
                "error": "STALE record from a prior failed attempt",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return sidecar


def test_stale_crash_sidecar_removed_on_healthy_rerun(monkeypatch, tmp_path) -> None:
    """THE BUG-5 regression: a stale crash sidecar from a prior failed attempt is
    cleaned up by a fresh, SUCCESSFUL re-run — the out-dir no longer masquerades as
    crashed. Pre-fix this assertion FAILED (the stale sidecar survived)."""
    domain = _domain_for(_TEST_SLUG)
    stale = _seed_stale_sidecar(Path(tmp_path), domain, _TEST_SLUG)
    assert stale.exists()  # precondition: a prior crash left the sidecar behind

    async def _ok(q, out_root, **kwargs):
        # A healthy attempt: returns success and writes NO crash sidecar.
        return {"status": "success", "slug": q["slug"]}

    monkeypatch.setattr(run_gate_b, "run_gate_b_query", _ok)
    rc = main(["--only", _TEST_SLUG, "--out-root", str(tmp_path)])

    assert rc == 0
    # The stale crash record is GONE — a status reader sees a clean (uncrashed) out-dir.
    assert not stale.exists(), "stale crash sidecar survived a healthy re-run (BUG-5)"


def test_real_crash_still_writes_sidecar_even_when_stale_existed(monkeypatch, tmp_path) -> None:
    """The cleanup must NOT suppress a GENUINE crash on the fresh attempt: if THIS
    attempt crashes, a NEW crash sidecar describing THIS crash is written, even when a
    stale sidecar from a prior attempt was present at entry."""
    domain = _domain_for(_TEST_SLUG)
    _seed_stale_sidecar(Path(tmp_path), domain, _TEST_SLUG)

    async def _crash(q, out_root, **kwargs):
        raise RuntimeError("fresh transport blowup")

    monkeypatch.setattr(run_gate_b, "run_gate_b_query", _crash)
    monkeypatch.delenv("PG_ABORT_ON_QUERY_ERROR", raising=False)
    rc = main(["--only", _TEST_SLUG, "--out-root", str(tmp_path)])

    assert rc == 1
    sidecar = Path(tmp_path) / domain / _TEST_SLUG / _CRASH_SIDECAR_NAME
    assert sidecar.exists(), "fresh crash failed to write a crash sidecar"
    record = json.loads(sidecar.read_text(encoding="utf-8"))
    # It is THIS attempt's record, not the stale one we seeded.
    assert record["status"] == "error_query_crashed"
    assert "fresh transport blowup" in record["error"]
    assert "STALE record" not in record.get("error", "")


def test_no_preexisting_sidecar_is_a_noop(monkeypatch, tmp_path) -> None:
    """A clean first attempt (no prior sidecar) is unaffected: the cleanup is a no-op
    (missing_ok), the query runs, and no crash sidecar is fabricated on success."""
    domain = _domain_for(_TEST_SLUG)

    async def _ok(q, out_root, **kwargs):
        return {"status": "success", "slug": q["slug"]}

    monkeypatch.setattr(run_gate_b, "run_gate_b_query", _ok)
    rc = main(["--only", _TEST_SLUG, "--out-root", str(tmp_path)])

    assert rc == 0
    sidecar = Path(tmp_path) / domain / _TEST_SLUG / _CRASH_SIDECAR_NAME
    assert not sidecar.exists(), "a successful run must not create a crash sidecar"


def test_cleanup_runs_before_query_so_query_sees_no_stale_sidecar(monkeypatch, tmp_path) -> None:
    """Ordering proof: the stale-sidecar cleanup happens BEFORE run_gate_b_query is
    invoked for the fresh attempt, so the running query already observes a clean
    out-dir (the stale record cannot leak into the attempt's own bookkeeping)."""
    domain = _domain_for(_TEST_SLUG)
    stale = _seed_stale_sidecar(Path(tmp_path), domain, _TEST_SLUG)
    assert stale.exists()
    observed = {}

    async def _observe(q, out_root, **kwargs):
        path = Path(out_root) / q["domain"] / q["slug"] / _CRASH_SIDECAR_NAME
        observed["sidecar_present_at_query_start"] = path.exists()
        return {"status": "success", "slug": q["slug"]}

    monkeypatch.setattr(run_gate_b, "run_gate_b_query", _observe)
    rc = main(["--only", _TEST_SLUG, "--out-root", str(tmp_path)])

    assert rc == 0
    assert observed.get("sidecar_present_at_query_start") is False, (
        "the stale crash sidecar was NOT cleared before the fresh attempt ran"
    )


def test_test_slug_is_a_locked_benchmark_slug() -> None:
    """Guard: the slug this test drives must remain a real locked benchmark slug."""
    assert _TEST_SLUG in LOCKED_BENCHMARK_SLUGS
