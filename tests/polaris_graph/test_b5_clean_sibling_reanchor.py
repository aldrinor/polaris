"""B5 (I-deepfix-001 wave-2) — hollow contract-slot re-anchor to a same-work CLEAN
sibling + author/abstract chrome-header strip.

Pure Python for the helpers; the e2e re-anchor routes the sibling span through the
REAL strict_verify K-span (`_kspan_fallback_body`) with the entailment judge OFF.
No network/LLM/GPU.
"""
import pytest

from src.polaris_graph.generator.contract_section_runner import (
    _author_abstract_header_strip_enabled,
    _b5_norm_doi,
    _b5_reanchor_any_enabled,
    _b5_reanchor_clean_kspan,
    _b5_same_work_siblings,
    _contract_bind_doi_fallback_enabled,
    _contract_reanchor_clean_sibling_enabled,
    _strip_author_abstract_header,
)
from src.polaris_graph.generator.live_deepseek_generator import (
    _rewrite_draft_with_spans,
)
from src.polaris_graph.generator.provenance_generator import strict_verify

_DOI = "10.1093/qje/qjae044"
_CHROME = (
    "## Author Listed: * Erik Brynjolfsson * Danielle Li * Lindsey Raymond "
    "## Abstract We study the staggered introduction of a generative AI-based "
    "conversational assistant using data from 5,172 customer support agents. "
    "Access to AI increases worker productivity, measured by issues resolved per "
    "hour, by 15 percent on average."
)
_CLEAN = (
    "We study the staggered introduction of a generative AI-based conversational "
    "assistant using data from 5,172 customer support agents. Access to AI "
    "increases worker productivity, measured by issues resolved per hour, by 15 "
    "percent on average."
)


# ── flag gates default OFF ─────────────────────────────────────────────────
def test_flags_default_off(monkeypatch):
    for f in (
        "PG_AUTHOR_ABSTRACT_HEADER_STRIP",
        "PG_CONTRACT_BIND_DOI_FALLBACK",
        "PG_CONTRACT_REANCHOR_CLEAN_SIBLING",
    ):
        monkeypatch.delenv(f, raising=False)
    assert _author_abstract_header_strip_enabled() is False
    assert _contract_bind_doi_fallback_enabled() is False
    assert _contract_reanchor_clean_sibling_enabled() is False
    assert _b5_reanchor_any_enabled() is False


# ── author/abstract header strip ───────────────────────────────────────────
def test_header_strip_off_byte_identical(monkeypatch):
    monkeypatch.delenv("PG_AUTHOR_ABSTRACT_HEADER_STRIP", raising=False)
    assert _strip_author_abstract_header(_CHROME) == _CHROME  # unchanged


def test_header_strip_on(monkeypatch):
    monkeypatch.setenv("PG_AUTHOR_ABSTRACT_HEADER_STRIP", "1")
    stripped = _strip_author_abstract_header(_CHROME)
    assert stripped.startswith("We study the staggered introduction")
    assert "Author Listed" not in stripped and "## Abstract" not in stripped
    # A quote with no such prefix is returned unchanged.
    assert _strip_author_abstract_header(_CLEAN) == _CLEAN


# ── DOI normalization + sibling discovery ──────────────────────────────────
def test_norm_doi_from_field_and_url():
    assert _b5_norm_doi({"doi": "10.1093/QJE/QJAE044"}) == _DOI
    assert _b5_norm_doi({"doi": "https://doi.org/10.1093/qje/qjae044"}) == _DOI
    assert _b5_norm_doi({"url": "https://academic.oup.com/qje/10.1093/qje/qjae044"}) == _DOI
    assert _b5_norm_doi({"title": "no doi here"}) == ""


def test_same_work_siblings_ranked_cleanest(monkeypatch):
    monkeypatch.setenv("PG_AUTHOR_ABSTRACT_HEADER_STRIP", "1")
    pool = {
        "bound": {"evidence_id": "bound", "doi": _DOI, "direct_quote": _CHROME},
        "ev_915": {"evidence_id": "ev_915", "doi": _DOI, "direct_quote": _CLEAN,
                   "content_relevance_weight": 1.0},
        "unrelated": {"evidence_id": "unrelated", "doi": "10.0/other",
                      "direct_quote": "Different paper."},
    }
    sibs = _b5_same_work_siblings("bound", pool, _DOI, "")
    assert sibs == ["ev_915"], "same-DOI sibling found, primary + unrelated excluded"


# ── e2e re-anchor through the REAL verifier ────────────────────────────────
def _pool():
    return {
        "bound": {"evidence_id": "bound", "doi": _DOI, "direct_quote": _CHROME},
        "ev_915": {
            "evidence_id": "ev_915", "doi": _DOI, "direct_quote": _CLEAN,
            "title": "Generative AI at Work", "content_relevance_weight": 1.0,
            "url": "https://academic.oup.com/qje/qjae044",
        },
    }


def test_reanchor_binds_clean_sibling(monkeypatch):
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    monkeypatch.setenv("PG_CONTRACT_BIND_DOI_FALLBACK", "1")
    monkeypatch.setenv("PG_CONTRACT_REANCHOR_CLEAN_SIBLING", "1")
    monkeypatch.delenv("PG_AUTHOR_ABSTRACT_HEADER_STRIP", raising=False)
    pool = _pool()
    biblio = [{"num": 6, "evidence_id": "bound", "url": "", "tier": "", "statement": "x"}]
    ev_to_num = {"bound": 6}
    result = _b5_reanchor_clean_kspan(
        primary_ev="bound",
        evidence_pool=pool,
        ev_to_num=ev_to_num,
        biblio_slice=biblio,
        rewrite_fn=_rewrite_draft_with_spans,
        strict_verify_fn=strict_verify,
        contract_entity=None,
    )
    assert result is not None, "clean same-DOI sibling re-anchor renders verified content"
    body, chosen = result
    assert chosen == "ev_915"
    assert "productivity" in body
    assert body.rstrip().endswith("]"), "body carries a [N] citation marker"
    assert "ev_915" in ev_to_num and any(b["evidence_id"] == "ev_915" for b in biblio)


def test_reanchor_header_strip_self_retry(monkeypatch):
    # Only the header strip is ON: the bound entity's OWN chrome span is cleaned
    # and rendered (no sibling needed).
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    monkeypatch.setenv("PG_AUTHOR_ABSTRACT_HEADER_STRIP", "1")
    monkeypatch.delenv("PG_CONTRACT_BIND_DOI_FALLBACK", raising=False)
    monkeypatch.delenv("PG_CONTRACT_REANCHOR_CLEAN_SIBLING", raising=False)
    pool = {"bound": {"evidence_id": "bound", "doi": _DOI, "direct_quote": _CHROME}}
    biblio = [{"num": 6, "evidence_id": "bound", "url": "", "tier": "", "statement": "x"}]
    ev_to_num = {"bound": 6}
    result = _b5_reanchor_clean_kspan(
        primary_ev="bound",
        evidence_pool=pool,
        ev_to_num=ev_to_num,
        biblio_slice=biblio,
        rewrite_fn=_rewrite_draft_with_spans,
        strict_verify_fn=strict_verify,
        contract_entity=None,
    )
    assert result is not None
    body, chosen = result
    assert chosen == "bound"
    assert "productivity" in body and "Author Listed" not in body


def test_reanchor_all_flags_off_noop(monkeypatch):
    for f in (
        "PG_AUTHOR_ABSTRACT_HEADER_STRIP",
        "PG_CONTRACT_BIND_DOI_FALLBACK",
        "PG_CONTRACT_REANCHOR_CLEAN_SIBLING",
    ):
        monkeypatch.delenv(f, raising=False)
    # Caller gate is False -> the pass is never even invoked.
    assert _b5_reanchor_any_enabled() is False
    # And even if called directly, all flags off => no candidates => None.
    result = _b5_reanchor_clean_kspan(
        primary_ev="bound",
        evidence_pool=_pool(),
        ev_to_num={"bound": 6},
        biblio_slice=[],
        rewrite_fn=_rewrite_draft_with_spans,
        strict_verify_fn=strict_verify,
        contract_entity=None,
    )
    assert result is None


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
