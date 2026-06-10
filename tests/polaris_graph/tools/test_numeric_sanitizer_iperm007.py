"""I-perm-007 (#1201) numeric sanitizer — drop numbers embedded in DOI/URL/accession identifiers.

Offline, self-contained (an INLINE fixture, not the gitignored saved pool — Codex slice-1 P1):
ON drops the DOI-prefix / accession cruft (e.g. `10.1038` extracted as a percent) while KEEPING
legit clinical numbers — including numeric RANGES and CI bounds (`0.4-6.7%`, `0.47-0.89`) and a
clean percent with a no-space trailing citation; OFF is byte-identical.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.polaris_graph.tools import evidence_extractor as ee
from src.polaris_graph.tools.numeric_sanitizer import is_structural_identifier_number

_FLAG = "PG_SWEEP_NUMERIC_SANITIZER"

# Inline, tracked fixture — each direct_quote is >=20 chars (the extractor skips shorter text).
_FIXTURE = {
    "doi_cruft": {
        "direct_quote": "see scholar_lookup?doi=10.1038%2fnrgastro.2014.66&pmid=24912386 for the source",
        "source_url": "https://scholar.google.com/x",
    },
    "legit_percent": {
        "direct_quote": "the treatment reduced colorectal cancer risk by 99% in the cohort population",
        "source_url": "https://example.org/a",
    },
    "numeric_range": {
        "direct_quote": "cereal fibre relative risk ranged 0.4-6.7% per 10 g/day across the studies",
        "source_url": "https://example.org/b",
    },
    "ci_bounds": {
        "direct_quote": "the hazard ratio was 0.65 (95% CI 0.47-0.89) in the pooled analysis cohort",
        "source_url": "https://example.org/c",
    },
    "trailing_citation": {
        "direct_quote": "the meta-analysis reported a 58%([_9_](https://x.org/p)) reduction overall",
        "source_url": "https://example.org/d",
    },
}


@pytest.fixture(autouse=True)
def _clear_flag():
    os.environ.pop(_FLAG, None)
    yield
    os.environ.pop(_FLAG, None)


# --- unit: structural-identifier detection (token-scoped, never a numeric range) -------------


@pytest.mark.parametrize(
    "text, frag, embedded",
    [
        ("scholar_lookup?doi=10.1038%2fnrgastro.2014.66", "10.1038", True),
        ("DO - 10.1038/s41586-020-2080-8 M3 - Article", "s41586-020-2080-8", True),  # accession
        ("isbn 978-3-16-148410-0 ref", "978-3-16-148410-0", True),  # multi-hyphen id
        ("see https://wwwnc.cdc.gov/eid/article/27/8", "27", True),  # number inside the URL path
        ("relative risk 0.4-6.7% per 10 g", "6.7", False),  # numeric RANGE endpoint -> KEEP
        ("95% CI 0.47-0.89 pooled", "0.47", False),  # CI bound -> KEEP
        ("range 10-100% across arms", "100", False),  # integer range -> KEEP
        (">99% genomic relatedness ([_8_](https://x))", "99", False),  # clean, URL later -> KEEP
        ("a 58%([_9_](https://x)) reduction", "58", False),  # no-space citation -> KEEP
        ("hazard ratio 0.65 (95% CI ...)", "0.65", False),  # plain decimal -> KEEP
    ],
)
def test_structural_identifier_detection(text, frag, embedded):
    start = text.index(frag)
    end = start + len(frag)
    assert is_structural_identifier_number(text, start, end) is embedded


# --- inline fixture: OFF byte-identical, ON drops cruft + keeps legit (incl. ranges/CI) ------


def _values(dps):
    return {(d["value"], d["unit"]) for d in dps}


def test_off_is_byte_identical():
    os.environ.pop(_FLAG, None)
    baseline = ee.extract_numbers_from_evidence(dict(_FIXTURE))
    for falsey in ("0", "false", "no", "off"):
        os.environ[_FLAG] = falsey
        assert ee.extract_numbers_from_evidence(dict(_FIXTURE)) == baseline
    # fixture sanity: the DOI cruft IS extracted with the flag off.
    assert any(d["value"].startswith("10.10") for d in baseline)


def test_on_drops_doi_keeps_legit_and_ranges():
    os.environ[_FLAG] = "1"
    out = ee.extract_numbers_from_evidence(dict(_FIXTURE))
    vals = {d["value"] for d in out}
    # DOI prefix parsed as data -> dropped.
    assert not any(v.startswith("10.10") for v in vals)
    # legit clinical percents kept — INCLUDING a numeric RANGE endpoint (no over-filter; the
    # range "0.4-6.7%" must not be mis-read as an accession). (The extractor only emits
    # unit-bearing numbers like percents — bare HR/CI decimals are out of its scope, so they
    # never appear with OR without the sanitizer; the structural-id unit test covers them.)
    assert "99.0" in vals  # plain percent
    assert "6.7" in vals  # range endpoint of 0.4-6.7% — the Codex P1 over-filter case
    assert "58.0" in vals  # percent with a no-space trailing citation


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[3] / "outputs/audits/beatboth8/drb_76/evidence_pool.json").is_file(),
    reason="saved beatboth8 pool not present (gitignored) — inline fixture covers CI",
)
def test_real_drb76_pool_doi_dropped_range_kept():
    import json

    pool = Path(__file__).resolve().parents[3] / "outputs/audits/beatboth8/drb_76/evidence_pool.json"
    rows = json.loads(pool.read_text(encoding="utf-8"))
    store = {r.get("evidence_id") or f"ev_{i}": r for i, r in enumerate(rows)}
    os.environ[_FLAG] = "1"
    out = ee.extract_numbers_from_evidence(store)
    assert not any(d["value"].startswith("10.10") for d in out)  # DOI cruft gone
    assert any(d["value"] == "6.7" for d in out)  # ev_560 real range endpoint KEPT
