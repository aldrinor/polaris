"""M3b (I-deepfix-001) — abstract gather-all-then-pick-richest + Semantic Scholar
3rd source, fully offline via a dependency-injected fake httpx.Client.

Exercises the REAL ``frame_fetcher._fetch_frame_entity_inner`` for the two
canonical closed-access primaries (robots_jobs JPE 2020 ; eloundou Science 2024),
proving:

  * the OpenAlex/S2 gather is consulted EVEN WHEN CrossRef returned an abstract
    (PG_FRAME_MULTI_ABSTRACT default ON), so a degenerate first-source fragment
    can no longer short-circuit the gather → ``_pick_richest_abstract`` picks the
    longest;
  * the new Semantic Scholar source lands a full abstract, DOI-consistency-guarded;
  * both kill-switches OFF restore the legacy short-circuit byte-identically.

No paid API, no GPU, no network — every HTTP call is served by FakeClient.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

# Hermetic: CORE OA full-text path off (it is only reached on an OA locator anyway,
# which these paywalled primaries never have, but keep the test self-contained).
os.environ["PG_CORE_ENABLED"] = "0"
# Prefer-abstract flag is a module-level import-time constant; leave it default OFF.
os.environ.pop("PG_FRAME_PREFER_ABSTRACT", None)

from src.polaris_graph.nodes.frame_compiler import EvidenceBinding  # noqa: E402
from src.polaris_graph.retrieval import frame_fetcher as ff  # noqa: E402

ROBOTS_DOI = "10.1086/705716"
ELOUNDOU_DOI = "10.1126/science.adj0998"

# eloundou's real degenerate first-source fragment shape (the 56-char trap).
ELOUNDOU_FRAGMENT = "Research is needed to estimate how jobs may be affected by"
ELOUNDOU_FULL = (
    "We investigate the potential implications of large language models (LLMs), "
    "such as Generative Pre-trained Transformers (GPTs), on the U.S. labor market, "
    "focusing on the increased capabilities arising from LLM-powered software "
    "compared to LLMs on their own. Using a new rubric, we assess occupations based "
    "on their alignment with LLM capabilities, integrating both human expertise and "
    "GPT-4 classifications. Our findings reveal that around 80% of the U.S. workforce "
    "could have at least 10% of their work tasks affected by the introduction of LLMs."
)
ROBOTS_OPENALEX = (
    "We study the effects of industrial robots on US labor markets. We show "
    "theoretically that robots may reduce employment and wages and that their local "
    "impacts can be estimated using variation in exposure to robots across commuting "
    "zones. We estimate robust negative effects of robots on employment and wages "
    "across commuting zones between 1990 and 2007. One more robot per thousand workers "
    "reduces the employment-to-population ratio by about 0.2 percentage points and "
    "wages by 0.42%."
)
ROBOTS_S2_SHORT = "Industrial robots reduce employment and wages in exposed US commuting zones."


def _inverted_index(text: str) -> dict[str, list[int]]:
    inv: dict[str, list[int]] = {}
    for i, w in enumerate(text.split()):
        inv.setdefault(w, []).append(i)
    return inv


@dataclass
class FakeResponse:
    status_code: int
    _json: object = None
    text: str = ""

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json


class FakeClient:
    """Routes by URL substring to canned responses; records every requested URL.
    Any unexpected source raises so a test can never silently hit the network."""

    def __init__(self, routes: dict[str, FakeResponse]):
        self.routes = routes
        self.calls: list[str] = []

    def get(self, url, headers=None, params=None):  # noqa: D401 - mirrors httpx.Client.get
        self.calls.append(url)
        if "api.crossref.org" in url:
            key = "crossref"
        elif "api.unpaywall.org" in url:
            key = "unpaywall"
        elif "api.openalex.org" in url:
            key = "openalex"
        elif "semanticscholar.org" in url:
            key = "s2"
        elif "eutils.ncbi" in url:
            key = "pubmed"
        else:
            raise AssertionError(f"unexpected outbound URL: {url}")
        if key not in self.routes:
            raise AssertionError(f"no canned response for source {key!r} (url={url})")
        return self.routes[key]

    def close(self):
        pass


def _crossref(*, doi: str, title: str, abstract: str | None) -> FakeResponse:
    msg: dict = {"title": [title], "DOI": doi, "author": [],
                 "container-title": ["J"], "published-print": {"date-parts": [[2020]]}}
    if abstract is not None:
        msg["abstract"] = abstract
    return FakeResponse(200, {"message": msg})


def _unpaywall_closed() -> FakeResponse:
    return FakeResponse(200, {"is_oa": False, "best_oa_location": None})


def _openalex(*, doi: str, title: str, abstract: str | None) -> FakeResponse:
    body: dict = {"doi": f"https://doi.org/{doi}", "display_name": title,
                  "publication_year": 2020, "authorships": [], "primary_location": {}}
    body["abstract_inverted_index"] = _inverted_index(abstract) if abstract else None
    return FakeResponse(200, body)


def _s2(*, ext_doi: str, title: str, abstract: str | None) -> FakeResponse:
    return FakeResponse(200, {"title": title, "abstract": abstract, "year": 2024,
                              "venue": "Science", "externalIds": {"DOI": ext_doi}})


def _binding(doi: str) -> EvidenceBinding:
    return EvidenceBinding(
        entity_id="e1", entity_type="economic_report",
        primary_identifier=f"doi:{doi}", secondary_identifiers=(),
        rendering_slot="body", required_fields=("thesis",),
        min_fields_for_completion=1,
    )


def _set_flags(*, multi: str | None, s2: str | None):
    for name, val in (("PG_FRAME_MULTI_ABSTRACT", multi), ("PG_FRAME_S2_ABSTRACT", s2)):
        if val is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = val


# ── tests ────────────────────────────────────────────────────────────────────

def test_robots_jobs_openalex_lands_abstract():
    """Previously-empty primary: CrossRef no-abstract, OpenAlex 600+ char abstract,
    S2 short → richest (OpenAlex) lands as ABSTRACT_ONLY direct_quote."""
    _set_flags(multi=None, s2=None)  # both default ON
    client = FakeClient({
        "crossref": _crossref(doi=ROBOTS_DOI, title="Robots and Jobs", abstract=None),
        "unpaywall": _unpaywall_closed(),
        "openalex": _openalex(doi=ROBOTS_DOI, title="Robots and Jobs", abstract=ROBOTS_OPENALEX),
        "s2": _s2(ext_doi=ROBOTS_DOI, title="Robots and Jobs", abstract=ROBOTS_S2_SHORT),
    })
    row = ff._fetch_frame_entity_inner(_binding(ROBOTS_DOI), client)
    assert row.provenance_class == ff.ProvenanceClass.ABSTRACT_ONLY, row.provenance_class
    assert row.quote_source == "openalex_abstract", row.quote_source
    assert row.direct_quote == ROBOTS_OPENALEX, repr(row.direct_quote[:60])
    assert len(row.direct_quote) > 400


def test_eloundou_multi_consults_s2_and_full_beats_fragment():
    """KEY MULTI test: CrossRef returns the 56-char fragment, but with MULTI ON the
    gather still consults S2 (which carries the FULL abstract) and the full wins —
    the degenerate fragment can no longer short-circuit the gather."""
    _set_flags(multi=None, s2=None)  # both default ON
    client = FakeClient({
        "crossref": _crossref(doi=ELOUNDOU_DOI, title="GPTs are GPTs", abstract=ELOUNDOU_FRAGMENT),
        "unpaywall": _unpaywall_closed(),
        "openalex": _openalex(doi=ELOUNDOU_DOI, title="GPTs are GPTs", abstract=None),
        "s2": _s2(ext_doi=ELOUNDOU_DOI, title="GPTs are GPTs", abstract=ELOUNDOU_FULL),
    })
    row = ff._fetch_frame_entity_inner(_binding(ELOUNDOU_DOI), client)
    assert row.direct_quote == ELOUNDOU_FULL, repr(row.direct_quote[:60])
    assert row.quote_source == "s2_abstract", row.quote_source
    assert len(row.direct_quote) > len(ELOUNDOU_FRAGMENT)
    assert any("semanticscholar.org" in u for u in client.calls)


def test_multi_and_s2_off_restores_crossref_fragment_byte_identical():
    """Both kill-switches OFF: the legacy short-circuit holds — CrossRef's abstract
    wins (even the 56-char fragment), S2 is never called."""
    _set_flags(multi="0", s2="0")
    client = FakeClient({
        "crossref": _crossref(doi=ELOUNDOU_DOI, title="GPTs are GPTs", abstract=ELOUNDOU_FRAGMENT),
        "unpaywall": _unpaywall_closed(),
        # openalex/s2 present but MUST NOT be consulted on the OFF path
        "openalex": _openalex(doi=ELOUNDOU_DOI, title="GPTs are GPTs", abstract=ELOUNDOU_FULL),
        "s2": _s2(ext_doi=ELOUNDOU_DOI, title="GPTs are GPTs", abstract=ELOUNDOU_FULL),
    })
    row = ff._fetch_frame_entity_inner(_binding(ELOUNDOU_DOI), client)
    assert row.direct_quote == ELOUNDOU_FRAGMENT, repr(row.direct_quote)
    assert row.quote_source == "crossref_abstract", row.quote_source
    assert not any("api.openalex.org" in u for u in client.calls), client.calls
    assert not any("semanticscholar.org" in u for u in client.calls), client.calls


def test_s2_doi_mismatch_rejected():
    """S2 returns a wrong-paper DOI in externalIds → the DOI-consistency guard
    rejects its abstract (never extract from the wrong work); a mismatch attempt is
    logged for source 's2', and the slot honestly stays METADATA_ONLY."""
    _set_flags(multi=None, s2=None)
    client = FakeClient({
        "crossref": _crossref(doi=ROBOTS_DOI, title="Robots and Jobs", abstract=None),
        "unpaywall": _unpaywall_closed(),
        "openalex": _openalex(doi=ROBOTS_DOI, title="Robots and Jobs", abstract=None),
        "s2": _s2(ext_doi="10.9999/wrong-paper", title="Some Other Paper",
                  abstract="A wrong-paper abstract that must NOT be extracted."),
    })
    row = ff._fetch_frame_entity_inner(_binding(ROBOTS_DOI), client)
    assert row.provenance_class == ff.ProvenanceClass.METADATA_ONLY, row.provenance_class
    assert row.direct_quote == "", repr(row.direct_quote)
    s2_mismatch = [a for a in row.retrieval_attempts
                   if a.source == "s2" and "doi_mismatch" in a.outcome]
    assert s2_mismatch, [(a.source, a.outcome) for a in row.retrieval_attempts]


def test_s2_off_no_s2_attempt_openalex_still_lands():
    """PG_FRAME_S2_ABSTRACT=0 removes S2 entirely (no s2 attempt), while OpenAlex
    still lands under MULTI ON — proves the two switches are independent."""
    _set_flags(multi=None, s2="0")
    client = FakeClient({
        "crossref": _crossref(doi=ROBOTS_DOI, title="Robots and Jobs", abstract=None),
        "unpaywall": _unpaywall_closed(),
        "openalex": _openalex(doi=ROBOTS_DOI, title="Robots and Jobs", abstract=ROBOTS_OPENALEX),
        "s2": _s2(ext_doi=ROBOTS_DOI, title="Robots and Jobs", abstract=ROBOTS_S2_SHORT),
    })
    row = ff._fetch_frame_entity_inner(_binding(ROBOTS_DOI), client)
    assert row.direct_quote == ROBOTS_OPENALEX, repr(row.direct_quote[:60])
    assert not any("semanticscholar.org" in u for u in client.calls), client.calls
    assert not any(a.source == "s2" for a in row.retrieval_attempts)


def test_pick_richest_abstract_s2_unit():
    """Unit: _pick_richest_abstract admits s2 as a candidate (longest wins); the
    default s2=None keeps legacy 3-source behavior byte-identical."""
    long_s2 = "x" * 500
    text, src = ff._pick_richest_abstract(
        crossref="short cross", openalex="med openalex text", pubmed=None, s2=long_s2,
    )
    assert src == "s2_abstract" and text == long_s2
    # s2 omitted => legacy
    t2, s2src = ff._pick_richest_abstract(
        crossref="aaaa", openalex="bbbbbbbb", pubmed=None,
    )
    assert s2src == "openalex_abstract" and t2 == "bbbbbbbb"


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
            n += 1
    print(f"\nM3b: {n}/{n} passed")
