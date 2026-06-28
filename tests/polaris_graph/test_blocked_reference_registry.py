"""I-deepfix-001 B2 (#1346) — per-WORK blocked-reference deny-list.

Behavioral (§-1.4) test against the REAL DeepResearch-Bench-II idx-56 "Salari" blocked
reference (Salari et al., "Impacts of generative artificial intelligence on the future of
labor market: A systematic review", DOI 10.1016/j.chbr.2025.100652, Elsevier PII
S2451958825000673). The blocked dict (title + doaj/herts/scilit/uhra/sciencedirect URLs)
is the verbatim gold record from `third_party/DeepResearch-Bench-II/tasks_and_rubrics.jsonl`
(content.blocked), AUGMENTED with the paper's DOI + its doi.org mirror (derivable from the
PII) so the deny-list enforces the full prohibition set the pipeline actually fans out to.

The whole point of the deny-list is to catch a blocked MIRROR that is NOT literally listed:
* the ``linkinghub`` mirror (a different URL carrying the SAME Elsevier PII) — PII leg,
* a ``library.kab.ac.ug`` / ``semanticscholar`` mirror (URL carries neither URL/DOI/PII) —
  fuzzy TITLE leg.
Both are asserted below, NOT just the listed URLs.
"""

from __future__ import annotations

import json

import pytest

from src.polaris_graph.retrieval.blocked_reference_registry import (
    BlockedRegistry,
    build_blocked_registry,
)

_BLOCKED_TITLE = (
    "Impacts of generative artificial intelligence on the future of "
    "labor market: A systematic review"
)
_BLOCKED_DOI = "10.1016/j.chbr.2025.100652"
_BLOCKED_PII = "S2451958825000673"

# The clean research ask (verbatim DRB-II idx-56 content.task lead-in).
_CLEAN_ASK = (
    "I am researching the impact of Generative AI on the future labor market, please "
    "help me complete a research report. The report needs to be based on academic "
    "research published before June 2023."
)

# The planted do-not-view appendix in the exact DRB-II wire format
# (`**important**The following is ... not allowed to view ... {dict}. ... do not quote it.`).
# URLs = the REAL gold idx-56 mirror set + the doi.org mirror; title + doi as labelled fields.
_DO_NOT_VIEW_APPENDIX = (
    "\n\n**important**The following is a rule of highest priority that you must not "
    "violate. Please put this rule in your task plan and keep it in your memory: "
    "**During the research process, you are not allowed to view the following article "
    "and urls: {'title': '" + _BLOCKED_TITLE + "', 'doi': '" + _BLOCKED_DOI + "', "
    "'urls': ['https://www.sciencedirect.com/science/article/pii/S2451958825000673', "
    "'https://doaj.org/article/2e2e2ccc110d4455b3269bfdb682b170', "
    "'https://researchprofiles.herts.ac.uk/en/publications/impacts-of-generative-"
    "artificial-intelligence-on-the-future-of-la', "
    "'https://www.scilit.com/publications/148571f40af332e6252df0f55e684a57', "
    "'https://uhra.herts.ac.uk/id/eprint/25592/', "
    "'https://doi.org/10.1016/j.chbr.2025.100652']}. Even if you accidentally read it, "
    "please ignore the content of the article and do not quote it.**"
)

_SALARI_QUESTION = _CLEAN_ASK + _DO_NOT_VIEW_APPENDIX

# Mirrors that ARE literally in the appendix (URL leg).
_SCIENCEDIRECT = "https://www.sciencedirect.com/science/article/pii/S2451958825000673"
_DOAJ = "https://doaj.org/article/2e2e2ccc110d4455b3269bfdb682b170"
_HERTS = (
    "https://researchprofiles.herts.ac.uk/en/publications/impacts-of-generative-"
    "artificial-intelligence-on-the-future-of-la"
)
_UHRA = "https://uhra.herts.ac.uk/id/eprint/25592/"
_DOI_ORG = "https://doi.org/10.1016/j.chbr.2025.100652"
# Mirrors that are NOT in the appendix (must be caught by the PII / title legs).
_LINKINGHUB = "https://linkinghub.elsevier.com/retrieve/pii/S2451958825000673"
_KAB = "https://library.kab.ac.ug/items/3f1c2b9a-doaj-mirror"
_SEMANTICSCHOLAR = "https://www.semanticscholar.org/paper/abc123"


@pytest.fixture()
def registry() -> BlockedRegistry:
    return build_blocked_registry(_SALARI_QUESTION)


def test_build_produces_non_empty_registry(registry: BlockedRegistry) -> None:
    assert not registry.is_empty
    assert _BLOCKED_PII in registry.publisher_piis
    assert _BLOCKED_DOI in registry.dois
    # all 6 listed mirror URLs landed in the canonical-url set
    assert len(registry.canonical_urls) == 6
    assert registry.title_keys  # title field parsed


def test_all_six_salari_locators_blocked(registry: BlockedRegistry) -> None:
    """The six locators enumerated in the issue: sciencedirect-PII, linkinghub-PII, herts,
    uhra-handle, kab(doaj), doi.org — each returns True with a leg-tagged reason."""
    cases = {
        "sciencedirect-PII": registry.is_blocked(url=_SCIENCEDIRECT),
        "linkinghub-PII": registry.is_blocked(url=_LINKINGHUB),  # NOT in appendix
        "herts": registry.is_blocked(url=_HERTS),
        "uhra-handle": registry.is_blocked(url=_UHRA),
        "kab(doaj)": registry.is_blocked(url=_KAB, title=_BLOCKED_TITLE),  # NOT in appendix
        "doi.org": registry.is_blocked(url=_DOI_ORG),
    }
    for name, (hit, reason) in cases.items():
        assert hit, f"{name} should be blocked"
        assert reason, f"{name} should carry a leg-tagged reason"


def test_pii_leg_catches_mirror_not_in_appendix(registry: BlockedRegistry) -> None:
    """linkinghub is NOT a listed URL — it must be caught via the shared Elsevier PII."""
    assert _normalize_not_present(registry, _LINKINGHUB)
    hit, reason = registry.is_blocked(url=_LINKINGHUB)
    assert hit
    assert reason.startswith("pii:")


def test_title_leg_catches_mirror_not_in_appendix(registry: BlockedRegistry) -> None:
    """A kab / semanticscholar mirror whose URL carries neither URL, DOI, nor PII must be
    caught by the fuzzy TITLE leg (the actual fan-out bug)."""
    for url in (_KAB, _SEMANTICSCHOLAR):
        hit, reason = registry.is_blocked(url=url, title=_BLOCKED_TITLE)
        assert hit, url
        assert reason.startswith("title:"), reason
    # the same mirror URL WITHOUT the blocked title is not caught (URL alone is not enough)
    assert registry.is_blocked(url=_SEMANTICSCHOLAR)[0] is False


def test_doi_leg(registry: BlockedRegistry) -> None:
    assert registry.is_blocked(doi=_BLOCKED_DOI)[0] is True
    assert registry.is_blocked(doi="doi:10.1016/J.CHBR.2025.100652")[0] is True  # case + prefix
    assert registry.is_blocked(doi="https://dx.doi.org/10.1016/j.chbr.2025.100652")[0] is True


def test_case_scheme_query_trailing_slash_variants(registry: BlockedRegistry) -> None:
    """case / scheme / query-param / trailing-slash variants of a listed mirror still match.
    Tested on the URL-leg-only mirror (uhra) so it is the URL normaliser doing the work,
    not the PII leg."""
    variants = [
        "http://uhra.herts.ac.uk/id/eprint/25592/",          # http scheme
        "https://uhra.herts.ac.uk/id/eprint/25592",          # no trailing slash
        "HTTPS://UHRA.HERTS.AC.UK/id/eprint/25592/",         # upper host+scheme
        "https://www.uhra.herts.ac.uk/id/eprint/25592/",     # leading www.
        "https://uhra.herts.ac.uk/id/eprint/25592/?via=ihub",  # extra query param
        "https://uhra.herts.ac.uk/id/eprint/25592/#section",   # fragment
    ]
    for v in variants:
        assert registry.is_blocked(url=v)[0] is True, v
    # sciencedirect variants (URL + PII belt-and-braces)
    assert registry.is_blocked(
        url="HTTP://WWW.ScienceDirect.com/science/article/pii/S2451958825000673/?via=ihub"
    )[0] is True


def test_no_overblock_on_topic_non_blocked_paper(registry: BlockedRegistry) -> None:
    """A DIFFERENT, on-topic GenAI-labor paper must NOT be blocked (no over-block)."""
    assert registry.is_blocked(
        url="https://www.sciencedirect.com/science/article/pii/S9999999999999999"
    )[0] is False
    assert registry.is_blocked(doi="10.1016/j.jbusres.2024.114512")[0] is False
    assert registry.is_blocked(
        url="https://www.nature.com/articles/s41599-024-12345-6",
        title="Generative AI adoption in manufacturing occupations: a robotics survey",
    )[0] is False


def test_off_flag_makes_registry_empty_and_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PG_BLOCKED_REFERENCE_DENYLIST", "0")
    off = build_blocked_registry(_SALARI_QUESTION)
    assert off.is_empty
    assert off.is_blocked(url=_SCIENCEDIRECT) == (False, "")
    assert off.is_blocked(doi=_BLOCKED_DOI) == (False, "")
    assert off.is_blocked(title=_BLOCKED_TITLE) == (False, "")


def test_no_appendix_yields_empty_registry() -> None:
    assert build_blocked_registry(_CLEAN_ASK).is_empty
    # a benign question that merely contains "**important**" is NOT an appendix
    assert build_blocked_registry(
        "Summarize the trial.\n\n**important** considerations include the endpoint."
    ).is_empty


def test_malformed_and_empty_questions_fail_open() -> None:
    """A malformed/empty/None question must NEVER raise — empty registry, run continues."""
    for bad in ("", "   ", None):  # type: ignore[list-item]
        reg = build_blocked_registry(bad)  # type: ignore[arg-type]
        assert reg.is_empty
        assert reg.is_blocked(url=_SCIENCEDIRECT) == (False, "")


def _normalize_not_present(registry: BlockedRegistry, url: str) -> bool:
    """True iff `url` is NOT one of the literal canonical URLs (so a True is_blocked on it is
    proof a NON-url leg fired)."""
    from src.polaris_graph.retrieval.blocked_reference_registry import _normalize_url

    return _normalize_url(url) not in registry.canonical_urls


# ---------------------------------------------------------------------------------------
# Seam-level offline drive (§-1.4): feed a blocked row through the SELECTION exclusion seam
# and assert the disclosed-exclusion record is emitted (the run-script helper, no network).
# ---------------------------------------------------------------------------------------
def test_selection_seam_excludes_blocked_row_and_records(tmp_path) -> None:
    from scripts.run_honest_sweep_r3 import _screen_blocked_references

    reg = build_blocked_registry(_SALARI_QUESTION)
    rows = [
        {"url": _SCIENCEDIRECT, "title": _BLOCKED_TITLE, "direct_quote": "blocked body"},
        {"url": _KAB, "title": _BLOCKED_TITLE, "direct_quote": "blocked mirror body"},
        {"url": "https://www.nature.com/articles/keep-me", "title": "A legitimate AI labor paper",
         "direct_quote": "kept body"},
    ]
    logs: list[str] = []
    kept_rows, _kept_srcs, excluded = _screen_blocked_references(
        rows, None, reg, log=logs.append, run_dir=tmp_path, label="selection",
    )
    kept_urls = {r["url"] for r in kept_rows}
    assert kept_urls == {"https://www.nature.com/articles/keep-me"}
    assert len(excluded["evidence_rows_excluded"]) == 2  # sciencedirect (pii/url) + kab (title)
    # disclosed-exclusion record emitted (fail-LOUD, never silent)
    record = tmp_path / "blocked_reference_excluded_selection.json"
    assert record.exists()
    payload = json.loads(record.read_text(encoding="utf-8"))
    assert len(payload["evidence_rows_excluded"]) == 2
    assert any("blocked_reference:" in e["reason"] for e in payload["evidence_rows_excluded"])
    assert logs and "PROHIBITED" in logs[0]


def test_selection_seam_noop_when_registry_empty(tmp_path) -> None:
    """Empty registry => original objects returned unchanged, no telemetry file written."""
    from scripts.run_honest_sweep_r3 import _screen_blocked_references

    empty = BlockedRegistry.empty()
    rows = [{"url": _SCIENCEDIRECT, "title": _BLOCKED_TITLE}]
    kept_rows, _kept_srcs, excluded = _screen_blocked_references(
        rows, None, empty, run_dir=tmp_path, label="selection",
    )
    assert kept_rows is rows  # same object, byte-identical no-op
    assert excluded["evidence_rows_excluded"] == []
    assert not (tmp_path / "blocked_reference_excluded_selection.json").exists()
