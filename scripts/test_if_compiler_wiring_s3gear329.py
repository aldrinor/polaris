#!/usr/bin/env python3
"""Acceptance test for STEP 5 — the instruction-following compiler wiring in
compose_agentic_report_s3gear329.py (behind the default-OFF PG_IF_COMPILER flag).

Fast, offline, hermetic. The heavy generator (generate_multi_section_report) is
MOCKED to capture the kwargs the driver passes and to return a minimal fake
MultiSectionResult; the constraint-extractor LLM is MOCKED via an injected
client-free path (we monkeypatch extract_constraints_async). NO network, no real
compose. Run:

    python scripts/test_if_compiler_wiring_s3gear329.py
"""
from __future__ import annotations

import asyncio
import importlib
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DRIVER_MOD = "scripts.compose_agentic_report_s3gear329"


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

# Two rows: one is a positive-proof journal article (aeaweb.org publisher host =>
# ELIGIBLE), one is a hard-ineligible host (wikipedia.org => WITHHELD).
_ELIGIBLE_ROW = {
    "evidence_id": "ev_ok",
    "statement": "Eligible journal claim.",
    "source_url": "https://www.aeaweb.org/articles/pdf/doi/10.1257/jep.1.1.1",
    "tier": "T1",
    "title": "A journal paper",
}
_INELIGIBLE_ROW = {
    "evidence_id": "ev_bad",
    "statement": "Wikipedia claim.",
    "source_url": "https://en.wikipedia.org/wiki/Something",
    "tier": "T3",
    "title": "A wiki page",
}


def _write_corpus(path: Path) -> None:
    corpus = {
        "research_question": "Please write a literature review on X, citing only "
        "high-quality English-language journal articles, covering wages and "
        "employment.",
        "evidence": [_ELIGIBLE_ROW, _INELIGIBLE_ROW],
        "finding_clusters": [],
        "same_work_groups": None,
        "domain": "economics",
    }
    path.write_text(json.dumps(corpus), encoding="utf-8")


def _fake_multi_result():
    """Minimal object exposing every attribute main() reads off `multi`."""
    sec = SimpleNamespace(
        dropped_due_to_failure=False,
        title="Body",
        verified_text="A verified sentence.",
        sentences_verified=1,
        sentences_dropped=0,
        regen_attempted=False,
    )
    plan = SimpleNamespace(title="Body", focus="f", ev_ids=["ev_ok"])
    return SimpleNamespace(
        sections=[sec],
        outline=[plan],
        total_words=3,
        total_sentences_verified=1,
        total_sentences_dropped=0,
        total_input_tokens=0,
        total_output_tokens=0,
        limitations_text="",
        bibliography=[],
        outline_agent_stats={"cp4_used": "agentic", "turns": 1},
        quantified_models={},
    )


def _install_generator_mock(driver, captured: dict):
    """Replace generate_multi_section_report with a capturing async stub."""
    import src.polaris_graph.generator.multi_section_generator as msg  # noqa: PLC0415

    async def _stub(**kwargs):
        captured["kwargs"] = kwargs
        return _fake_multi_result()

    # The driver imports the symbol INSIDE main() from the module, so patching the
    # module attribute is what the driver's `from ... import generate_multi_section_report`
    # resolves to at call time.
    msg.generate_multi_section_report = _stub


def _install_constraint_mock(monkeypatched: dict):
    """Replace extract_constraints_async so the ON path never hits the network."""
    import src.polaris_graph.instruction.constraint_extractor as ce  # noqa: PLC0415

    async def _stub(prompt, **kwargs):
        return {
            "source_types": ["peer_reviewed"],
            "languages": ["en"],
            "recency": None,
            "required_coverage": ["Wages", "Employment"],
            "exclusions": [],
            "format": "literature_review",
            "length": None,
            "tone": "academic",
        }

    monkeypatched["orig"] = ce.extract_constraints_async
    ce.extract_constraints_async = _stub


async def _run_driver(corpus_path: Path, out_dir: Path, env: dict) -> dict:
    """Import the driver fresh, install mocks, run main(), return captured kwargs."""
    # Fresh import so module-level state / prior monkeypatches don't leak.
    if DRIVER_MOD in sys.modules:
        importlib.reload(sys.modules[DRIVER_MOD])
    driver = importlib.import_module(DRIVER_MOD)

    captured: dict = {}
    _install_generator_mock(driver, captured)
    _install_constraint_mock({})

    # A fake API key so the OPENROUTER_API_KEY guard passes; no live call is made
    # (generator + constraint extractor are both mocked).
    old_environ = dict(os.environ)
    try:
        os.environ["OPENROUTER_API_KEY"] = "test-key-not-used"
        for k, v in env.items():
            os.environ[k] = v
        argv = [
            "prog",
            "--corpus", str(corpus_path),
            "--out-dir", str(out_dir),
            "--rq-drb-task", "",  # keep the corpus RQ (no DRB prompt file needed)
            "--max-parallel", "1",
        ]
        old_argv = sys.argv
        sys.argv = argv
        try:
            rc = await driver.main()
        finally:
            sys.argv = old_argv
        assert rc in (0, 1), f"main() returned unexpected rc={rc}"
    finally:
        os.environ.clear()
        os.environ.update(old_environ)
    return captured["kwargs"]


# --------------------------------------------------------------------------- #
# Assertions
# --------------------------------------------------------------------------- #

# The exact kwarg set the driver passed BEFORE this change (byte-identical target).
_LEGACY_KWARGS = {
    "research_question",
    "evidence",
    "finding_clusters",
    "same_work_groups",
    "section_temperature",
    "outline_max_tokens",
    "section_max_tokens",
    "min_kept_fraction",
    "max_parallel_sections",
    "tier_fractions",
    "domain",
    "credibility_pass_gov_suffixes",
}


def _test_off_path(tmp: Path):
    corpus = tmp / "corpus_off.json"
    _write_corpus(corpus)
    kwargs = asyncio.run(_run_driver(corpus, tmp / "out_off", env={"PG_IF_COMPILER": "0"}))

    # 1) The two new kwargs are present in the signature but MUST be None (OFF => byte-identical).
    assert kwargs.get("deliverable_spec") is None, kwargs.get("deliverable_spec")
    assert kwargs.get("scope_spec") is None, kwargs.get("scope_spec")

    # 2) Dropping the two always-None new keys, the passed kwargs equal the legacy set exactly.
    passed = set(kwargs.keys()) - {"deliverable_spec", "scope_spec"}
    assert passed == _LEGACY_KWARGS, (
        f"OFF-path kwargs drifted from legacy:\n  extra={passed - _LEGACY_KWARGS}\n"
        f"  missing={_LEGACY_KWARGS - passed}"
    )

    # 3) The citable evidence is the UNTOUCHED corpus (both rows, same order/identity).
    ev = kwargs["evidence"]
    assert [r["evidence_id"] for r in ev] == ["ev_ok", "ev_bad"], ev
    print("[OFF] PASS — new kwargs None, kwarg set byte-identical, evidence untouched (2 rows).")


def _test_on_path(tmp: Path):
    corpus = tmp / "corpus_on.json"
    _write_corpus(corpus)
    kwargs = asyncio.run(_run_driver(corpus, tmp / "out_on", env={"PG_IF_COMPILER": "1"}))

    # 1) deliverable_spec populated from constraint_extractor.required_coverage.
    dspec = kwargs.get("deliverable_spec")
    assert isinstance(dspec, dict), dspec
    assert dspec.get("required_sections") == ["Wages", "Employment"], dspec

    # 2) scope_spec populated with source_types.
    sspec = kwargs.get("scope_spec")
    assert isinstance(sspec, dict), sspec
    assert sspec.get("source_types"), sspec

    # 3) The INELIGIBLE row (wikipedia.org) is EXCLUDED from the citable set; the eligible
    #    (aeaweb.org publisher host) row remains.
    ev = kwargs["evidence"]
    ids = [r["evidence_id"] for r in ev]
    assert ids == ["ev_ok"], f"citable menu should exclude ev_bad, got {ids}"
    assert "ev_bad" not in ids, "ineligible wikipedia row leaked into the citable menu"
    print(f"[ON ] PASS — deliverable_spec={dspec}  scope_spec={sspec}  citable_ids={ids} "
          f"(ev_bad withheld).")


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _test_off_path(tmp)
        _test_on_path(tmp)
    print("\nALL ACCEPTANCE ASSERTIONS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
