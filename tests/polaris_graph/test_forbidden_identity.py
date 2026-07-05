"""I-deepfix-001 P0-1 — forbidden-source-by-IDENTITY leak (DOAJ id + title/author hash).

RED baseline (HEAD c803d427): the per-work blocked-reference deny-list recognises a
forbidden work ONLY by its exact URL, its Crossref DOI, an Elsevier PII, or a fuzzy TITLE
match. A DOAJ MIRROR that carries the SAME DOAJ article id
(``2e2e2ccc110d4455b3269bfdb682b170``) in its URL path or its metadata — but NOT the listed
URL, the DOI, the PII, nor a matchable title — is therefore ADMITTED. It is fetched, tiered
T7, quoted in the body, and counted as VERIFIED independent SUPPORT in the corroboration /
necessity ledgers. (library.kab.ac.ug is the real-world offender.)

GREEN: the registry gains

* a DOAJ-id identity leg (build side parses ``doaj.org/article/<id>`` URLs, ``'doaj_id'``
  fields and labelled ``DOAJ id: <id>`` mentions out of the appendix; match side extracts
  the id from a candidate URL / ``doaj_id`` metadata),
* a title+first-author-hash fallback identity key, and
* a normalized-identity extractor (``extract_source_identity`` / ``is_blocked_source``),

and a pre-composition scope gate (``scope_gate_redact_claims``) that redacts any claim whose
supporting source has a forbidden identity REGARDLESS of the D8 entailment verdict.

The faithfulness engine is never relaxed — this STRENGTHENS the one legitimate hard drop.
No hardcoded Salari: every key is parsed from the question appendix (LAW VI).
"""

from __future__ import annotations

import json

import pytest

from src.polaris_graph.retrieval.blocked_reference_registry import (
    BlockedRegistry,
    build_blocked_registry,
    extract_source_identity,
)

# --- the REAL DRB-II idx-56 forbidden work, specified via its DOAJ mirror ------------------
_BLOCKED_TITLE = (
    "Impacts of generative artificial intelligence on the future of "
    "labor market: A systematic review"
)
_BLOCKED_DOI = "10.1016/j.chbr.2025.100652"
_BLOCKED_PII = "S2451958825000673"
_BLOCKED_DOAJ_ID = "2e2e2ccc110d4455b3269bfdb682b170"

_CLEAN_ASK = (
    "I am researching the impact of Generative AI on the future labor market, please "
    "help me complete a research report."
)

# Appendix in the DRB-II wire format. Note the DOAJ article URL carries the DOAJ id.
_DO_NOT_VIEW_APPENDIX = (
    "\n\n**important**The following is a rule of highest priority that you must not "
    "violate. During the research process, you are not allowed to view the following "
    "article and urls: {'title': '" + _BLOCKED_TITLE + "', 'doi': '" + _BLOCKED_DOI + "', "
    "'urls': ['https://www.sciencedirect.com/science/article/pii/S2451958825000673', "
    "'https://doaj.org/article/" + _BLOCKED_DOAJ_ID + "', "
    "'https://doi.org/10.1016/j.chbr.2025.100652']}. Even if you accidentally read it, "
    "please ignore the content of the article and do not quote it.**"
)
_SALARI_QUESTION = _CLEAN_ASK + _DO_NOT_VIEW_APPENDIX

# A DOAJ MIRROR: the id is in the URL path, but NOT the listed URL, NOT the DOI, NOT the PII,
# and (crucially) NO title is available to the fuzzy-title leg. This is the fan-out offender.
_KAB_DOAJ_MIRROR = (
    "https://library.kab.ac.ug/server/api/core/items/" + _BLOCKED_DOAJ_ID
)
# Same offender, but the id arrives as candidate metadata (URL carries nothing identifying).
_KAB_BARE_URL = "https://library.kab.ac.ug/handle/20.500.12306/9987"


@pytest.fixture()
def registry() -> BlockedRegistry:
    return build_blocked_registry(_SALARI_QUESTION)


# =========================================================================================
# (a) normalized-identity extractor
# =========================================================================================
def test_extract_source_identity_parses_doaj_doi_and_author_hash() -> None:
    ident = extract_source_identity(
        {
            "url": "https://doaj.org/article/" + _BLOCKED_DOAJ_ID,
            "doi": "https://doi.org/" + _BLOCKED_DOI,
            "title": _BLOCKED_TITLE,
            "authors": ["Salari, Amirreza", "Second Author"],
        }
    )
    assert ident.doaj_id == _BLOCKED_DOAJ_ID
    assert ident.doi == _BLOCKED_DOI
    assert ident.title_author_hash  # a stable non-empty fallback key
    # DOAJ id is also recoverable when it only appears in a non-DOAJ mirror URL path.
    ident2 = extract_source_identity({"url": _KAB_DOAJ_MIRROR})
    assert ident2.doaj_id == _BLOCKED_DOAJ_ID


def test_identity_extractor_is_stable_across_field_shapes() -> None:
    """Author list vs single string, doi with/without scheme — same identity keys."""
    a = extract_source_identity(
        {"title": _BLOCKED_TITLE, "authors": ["Salari, Amirreza"], "doi": _BLOCKED_DOI}
    )
    b = extract_source_identity(
        {"title": _BLOCKED_TITLE, "author": "Amirreza Salari",
         "doi": "doi:" + _BLOCKED_DOI}
    )
    assert a.doi == b.doi == _BLOCKED_DOI
    assert a.title_author_hash == b.title_author_hash  # surname-based, order-robust


# =========================================================================================
# (b) block at FETCH by identity — the exact call the fetch seam makes: is_blocked(url=,doi=)
# =========================================================================================
def test_doaj_mirror_in_url_blocked(registry: BlockedRegistry) -> None:
    """RED at HEAD: the kab DOAJ mirror is admitted (no DOAJ-id leg). GREEN: blocked."""
    hit, reason = registry.is_blocked(url=_KAB_DOAJ_MIRROR)
    assert hit, "DOAJ mirror carrying the forbidden article id must be blocked"
    assert reason.startswith("doaj:"), reason


def test_doaj_mirror_via_metadata_blocked(registry: BlockedRegistry) -> None:
    """The id arrives as candidate metadata (doaj_id) even though the URL is opaque."""
    hit, reason = registry.is_blocked(url=_KAB_BARE_URL, doaj_id=_BLOCKED_DOAJ_ID)
    assert hit
    assert reason.startswith("doaj:")


def test_is_blocked_source_on_full_candidate(registry: BlockedRegistry) -> None:
    from src.polaris_graph.retrieval.blocked_reference_registry import is_blocked_source

    hit, reason = is_blocked_source(
        {"url": _KAB_BARE_URL, "doaj_id": _BLOCKED_DOAJ_ID, "title": "Repository item"},
        registry,
    )
    assert hit
    assert reason


def test_doaj_leg_no_overblock_on_different_id(registry: BlockedRegistry) -> None:
    """A DIFFERENT DOAJ article id (a legitimate other paper) is NOT blocked."""
    other = "https://doaj.org/article/ffffffffffffffffffffffffffffffff"
    assert registry.is_blocked(url=other)[0] is False
    assert registry.is_blocked(
        url="https://library.kab.ac.ug/server/api/core/items/"
        "ffffffffffffffffffffffffffffffff"
    )[0] is False


def test_registry_records_doaj_id() -> None:
    reg = build_blocked_registry(_SALARI_QUESTION)
    assert _BLOCKED_DOAJ_ID in reg.doaj_ids
    assert not reg.is_empty


# =========================================================================================
# (a) title+first-author hash leg — exact-match fallback when no id is available
# =========================================================================================
_AUTHORED_APPENDIX = (
    _CLEAN_ASK
    + "\n\n**important**The following is a rule of highest priority that you must not "
    "violate. You are not allowed to view the following article and urls: "
    "{'title': '" + _BLOCKED_TITLE + "', 'authors': ['Salari, Amirreza', 'Ko Author'], "
    "'urls': ['https://uhra.herts.ac.uk/id/eprint/25592/']}. do not quote it.**"
)


def test_title_author_hash_leg_blocks_idless_mirror() -> None:
    reg = build_blocked_registry(_AUTHORED_APPENDIX)
    assert reg.title_author_hashes  # built from the appendix title+author
    # A mirror with NO url-match, NO doi, NO pii, NO doaj id — only the same title+author.
    hit, reason = reg.is_blocked(
        url="https://ssrn.example.org/paper/opaque-id-99",
        title=_BLOCKED_TITLE,
        authors="Amirreza Salari",
    )
    assert hit
    assert reason.startswith("title:") or reason.startswith("title_author:")


# =========================================================================================
# (c) pre-composition scope gate — redact by identity REGARDLESS of D8 verdict
# =========================================================================================
def test_scope_gate_redacts_forbidden_support_despite_supported_verdict(
    registry: BlockedRegistry, tmp_path
) -> None:
    from src.polaris_graph.retrieval.forbidden_identity_gate import (
        scope_gate_redact_claims,
    )

    claims = [
        {
            "claim_id": "c1",
            "text": "GenAI raises labor productivity by 14 percent.",
            "d8_verdict": "SUPPORTED",  # the gate must IGNORE this
            "supporting_sources": [
                {"url": _KAB_DOAJ_MIRROR, "title": "opaque repo item"},
            ],
        },
        {
            "claim_id": "c2",
            "text": "A legitimately supported claim.",
            "d8_verdict": "SUPPORTED",
            "supporting_sources": [
                {"url": "https://www.nature.com/articles/keep-me", "title": "clean"},
            ],
        },
    ]
    logs: list[str] = []
    kept, redacted = scope_gate_redact_claims(
        claims, registry, log=logs.append, run_dir=tmp_path, label="precompose",
    )
    kept_ids = {c["claim_id"] for c in kept}
    assert kept_ids == {"c2"}, "the forbidden-identity claim must be redacted"
    assert len(redacted) == 1
    assert redacted[0]["claim_id"] == "c1"
    # fail-LOUD: telemetry file + log line, never a silent drop
    rec = tmp_path / "scope_gate_redacted_precompose.json"
    assert rec.exists()
    payload = json.loads(rec.read_text(encoding="utf-8"))
    assert payload[0]["claim_id"] == "c1"
    assert logs and "REDACT" in logs[0].upper()


def test_scope_gate_noop_when_registry_empty(tmp_path) -> None:
    from src.polaris_graph.retrieval.forbidden_identity_gate import (
        scope_gate_redact_claims,
    )

    claims = [{"claim_id": "c1", "supporting_sources": [{"url": _KAB_DOAJ_MIRROR}]}]
    kept, redacted = scope_gate_redact_claims(
        claims, BlockedRegistry.empty(), run_dir=tmp_path, label="precompose",
    )
    assert kept is claims  # same object, byte-identical no-op
    assert redacted == []
    assert not (tmp_path / "scope_gate_redacted_precompose.json").exists()


# =========================================================================================
# (d) fail-loud when a forbidden id is detected in the pool
# =========================================================================================
def test_selection_seam_drops_doaj_mirror_row_and_records(tmp_path) -> None:
    """End-to-end through the SELECTION pre-composition seam: a DOAJ-mirror evidence row
    (id in URL, no doi/pii/title) is dropped BEFORE the generator composes."""
    from scripts.run_honest_sweep_r3 import _screen_blocked_references

    reg = build_blocked_registry(_SALARI_QUESTION)
    rows = [
        {"url": _KAB_DOAJ_MIRROR, "direct_quote": "blocked mirror body"},
        {"url": "https://www.nature.com/articles/keep-me", "title": "clean",
         "direct_quote": "kept body"},
    ]
    logs: list[str] = []
    kept_rows, _kept_srcs, excluded = _screen_blocked_references(
        rows, None, reg, log=logs.append, run_dir=tmp_path, label="selection",
    )
    assert {r["url"] for r in kept_rows} == {"https://www.nature.com/articles/keep-me"}
    assert len(excluded["evidence_rows_excluded"]) == 1
    rec = tmp_path / "blocked_reference_excluded_selection.json"
    assert rec.exists()
    payload = json.loads(rec.read_text(encoding="utf-8"))
    assert any("doaj:" in e["reason"] for e in payload["evidence_rows_excluded"])
