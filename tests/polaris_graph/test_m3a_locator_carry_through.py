"""M3a (I-deepfix-001) — DOI/PMID locator carry-through, offline.

Proves the two real production functions, against the REAL banked drb72 fixture:

  1. ``provenance_generator.resolve_provenance_to_citations_with_count`` (which
     contains the ``_num_for`` bib-row builder) now carries ``doi``/``pmid`` from
     the evidence_pool row onto each bibliography row.
  2. ``run_honest_sweep_r3._render_bibliography_lines`` (with the existing
     ``PG_BIB_REQUIRE_LOCATOR`` doi.org/pubmed fallback) renders a resolvable
     locator for a URL-less-but-DOI-bearing primary instead of the
     "no resolvable URL/DOI locator" gap line.

The two canonical primaries in the fixture (acemoglu_restrepo_robots_jobs JPE 2020
10.1086/705716 ; eloundou_gpts_are_gpts Science 2024 10.1126/science.adj0998) both
carry an EMPTY source_url and a valid DOI — exactly the M3a defect scenario.

No paid API, no GPU, no network.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

# Relevance gate OFF so resolve() takes the byte-identical legacy path (no judge).
os.environ.pop("PG_RELEVANCE_GATE", None)

from src.polaris_graph.generator.provenance_generator import (  # noqa: E402
    ProvenanceToken,
    SentenceVerification,
    resolve_provenance_to_citations_with_count,
)

FIXTURE = ROOT / "tests" / "fixtures" / "drb72" / "evidence_pool.json"

ROBOTS = "acemoglu_restrepo_robots_jobs"
ELOUNDOU = "eloundou_gpts_are_gpts"
ROBOTS_DOI = "10.1086/705716"
ELOUNDOU_DOI = "10.1126/science.adj0998"


def _load_render_fn():
    """Import the 17k-line sweep script by path (import-safe: __main__-guarded,
    no eager torch/chromadb) and return (_render_bibliography_lines, module)."""
    spec = importlib.util.spec_from_file_location(
        "rhs_m3a", str(ROOT / "scripts" / "run_honest_sweep_r3.py")
    )
    m = importlib.util.module_from_spec(spec)
    sys.modules["rhs_m3a"] = m
    spec.loader.exec_module(m)
    return m


def _pool_by_eid() -> dict[str, dict]:
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return {str(r["evidence_id"]): r for r in rows if isinstance(r, dict)}


def _sv(eid: str) -> SentenceVerification:
    raw = f"[#ev:{eid}:0-40]"
    sentence = (
        f"Industrial robots reduced United States local labor market employment {raw}."
    )
    return SentenceVerification(
        sentence=sentence,
        tokens=[ProvenanceToken(evidence_id=eid, start=0, end=40, raw=raw)],
        is_verified=True,
    )


def test_num_for_carries_doi_onto_bib_rows():
    """The real resolve()/_num_for now stashes the row's DOI onto the bib row."""
    pool = _pool_by_eid()
    assert pool[ROBOTS]["doi"] == ROBOTS_DOI and pool[ROBOTS]["source_url"] == ""
    assert pool[ELOUNDOU]["doi"] == ELOUNDOU_DOI and pool[ELOUNDOU]["source_url"] == ""

    _text, biblio, emitted = resolve_provenance_to_citations_with_count(
        [_sv(ROBOTS), _sv(ELOUNDOU)], pool
    )
    assert emitted == 2, emitted
    by_eid = {r["evidence_id"]: r for r in biblio}
    assert by_eid[ROBOTS]["doi"] == ROBOTS_DOI, by_eid[ROBOTS]
    assert by_eid[ELOUNDOU]["doi"] == ELOUNDOU_DOI, by_eid[ELOUNDOU]
    # url stayed empty (carry-through added the DOI; it did not invent a URL)
    assert by_eid[ROBOTS]["url"] == ""
    assert "pmid" in by_eid[ROBOTS]
    return biblio


def test_render_resolves_doi_locator_for_urlless_primaries():
    """With require_locator ON, the URL-less DOI-bearing rows render the doi.org
    locator instead of the 'no resolvable URL/DOI locator' gap line."""
    m = _load_render_fn()
    biblio = test_num_for_carries_doi_onto_bib_rows()
    out = m._render_bibliography_lines(biblio, require_locator=True)
    assert f"https://doi.org/{ROBOTS_DOI}" in out, out
    assert f"https://doi.org/{ELOUNDOU_DOI}" in out, out
    assert "no resolvable URL/DOI locator" not in out, out


def test_render_control_idless_row_still_gaps():
    """A genuinely id-less cited row (no url, no doi, no pmid) still renders the
    disclosed gap line under require_locator — the fix does not paper over a real gap."""
    m = _load_render_fn()
    row = {"num": 99, "url": "", "doi": "", "pmid": "", "tier": "T3",
           "statement": "An entry with no resolvable identifier at all"}
    out = m._render_bibliography_lines([row], require_locator=True)
    assert "no resolvable URL/DOI locator" in out, out


def test_render_pmid_only_row_resolves_pubmed_locator():
    """A URL-less, DOI-less row carrying only a PMID renders the canonical PubMed
    locator (M3a optional extension), never fabricated."""
    m = _load_render_fn()
    row = {"num": 98, "url": "", "doi": "", "pmid": "31234567", "tier": "T1",
           "statement": "A PMID-only primary source"}
    out = m._render_bibliography_lines([row], require_locator=True)
    assert "https://pubmed.ncbi.nlm.nih.gov/31234567/" in out, out
    assert "no resolvable URL/DOI locator" not in out, out


def test_off_path_doi_key_is_render_neutral():
    """require_locator=False (PG_BIB_REQUIRE_LOCATOR OFF): the added doi/pmid keys
    are render-neutral — a row WITH them renders byte-identically to one WITHOUT."""
    m = _load_render_fn()
    row_with = {"num": 1, "url": "", "doi": ROBOTS_DOI, "pmid": "",
                "tier": "T1", "statement": "Robots and Jobs"}
    row_without = {"num": 1, "url": "", "tier": "T1", "statement": "Robots and Jobs"}
    a = m._render_bibliography_lines([row_with], require_locator=False)
    b = m._render_bibliography_lines([row_without], require_locator=False)
    assert a == b, (repr(a), repr(b))
    # and the OFF path does NOT emit the doi.org fallback at all
    assert "https://doi.org/" not in a, a


if __name__ == "__main__":
    n_pass = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
            n_pass += 1
    print(f"\nM3a: {n_pass}/{n_pass} passed")
