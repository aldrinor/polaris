"""V4 (I-deepfix-001) — whole-basket D8 adjudication input (§-1.3 BASKET FAITHFULNESS).

FIXTURES ONLY — NO NETWORK, NO SPEND. Offline RED->GREEN proof that the D8 four-role seam now
adjudicates a claim against its WHOLE basket (each cited source carrying its DECLARED PROVENANCE
identity), not a bare single span — recovering the measured single-span false-negative while
admitting NOTHING unverified.

ROOT CAUSE reproduced (drb_72 claim 01-008 frey_osborne_computerisation): the Sentinel decomposes
"Frey and Osborne developed a novel methodology ..." and marks the ATTRIBUTION atom "Frey and
Osborne" `unsupported` because the abstract SPAN self-references as "We" and never names its own
authors -> Sentinel UNGROUNDED -> the LOCKED compose override downgrades a Judge VERIFIED to
UNSUPPORTED. The source RECORD carries `authors: ['Frey C', 'Osborne M']`.

We cannot run the live Sentinel offline, so the RED->GREEN assertion is on the ADJUDICATION INPUT
the Sentinel/Judge read: with the fix OFF the input has NO author identity (so the attribution atom
is ungroundable — the false-negative); with the fix ON the input prepends the source's real
authorship (so the attribution atom CAN ground — the false-negative is recovered).
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from src.polaris_graph.roles.native_gate_b_inputs import (
    _provenance_header,
    _resolve_evidence,
    _whole_basket_enabled,
    build_native_gate_b_inputs,
    normalize_evidence_pool_lookup,
)
from src.polaris_graph.roles.release_policy import D8PolicyConfig

_ENV = "PG_GATE_B_WHOLE_BASKET"
_SPAN_ENV = "PG_GATE_B_CITED_SPAN"

# The REAL Frey-Osborne abstract span (0-800 shape) — self-references as "We", NEVER names the
# authors. This is exactly why the single-span Sentinel marked the attribution atom unsupported.
_FREY_SPAN = (
    "Abstract: We examine how susceptible jobs are to computerisation. To assess this, we begin "
    "by implementing a novel methodology to estimate the probability of computerisation for 702 "
    "detailed occupations, using a Gaussian process classifier."
)
_FREY_AUTHORS = ["Frey C", "Osborne M"]
_FREY_TITLE = "The future of employment: How susceptible are jobs to computerisation?"
_FREY_JOURNAL = "Technological Forecasting and Social Change"
_FREY_DOI = "10.1016/j.techfore.2016.08.019"


@dataclass
class _Tok:
    evidence_id: str
    start: int = 0
    end: int = 0


def _frey_record() -> dict:
    return {
        "text": _FREY_SPAN,
        "authors": _FREY_AUTHORS,
        "year": 2017,
        "journal": _FREY_JOURNAL,
        "doi": _FREY_DOI,
        "tier": "T1",
    }


# ── the whole-basket kill-switch ────────────────────────────────────────────────────────────────
def test_flag_default_on(monkeypatch) -> None:
    monkeypatch.delenv(_ENV, raising=False)
    assert _whole_basket_enabled() is True


@pytest.mark.parametrize("tok", ["0", "false", "no", "off", "OFF", "  False  "])
def test_flag_off_tokens(monkeypatch, tok) -> None:
    monkeypatch.setenv(_ENV, tok)
    assert _whole_basket_enabled() is False


# ── RED -> GREEN: the attribution identity enters the adjudication input ─────────────────────────
def test_red_bare_span_lacks_attribution_identity(monkeypatch) -> None:
    """RED (fix OFF): the adjudication input is the bare abstract span — it does NOT name Frey or
    Osborne, so the Sentinel's attribution atom is ungroundable (the measured false-negative)."""
    monkeypatch.setenv(_ENV, "off")
    monkeypatch.delenv(_SPAN_ENV, raising=False)
    docs, _ = _resolve_evidence([_Tok("frey")], {"frey": _frey_record()})
    text = docs[0].text
    assert text == _FREY_SPAN  # byte-identical to the bare span
    assert "Frey" not in text and "Osborne" not in text


def test_green_whole_basket_carries_attribution_identity(monkeypatch) -> None:
    """GREEN (fix ON): the source's declared authorship is prepended, so the attribution atom
    'Frey and Osborne' CAN now ground against the cited work's real identity."""
    monkeypatch.setenv(_ENV, "1")
    monkeypatch.delenv(_SPAN_ENV, raising=False)
    docs, _ = _resolve_evidence([_Tok("frey")], {"frey": _frey_record()})
    text = docs[0].text
    assert "Frey" in text and "Osborne" in text  # attribution now groundable
    assert _FREY_SPAN in text  # the factual body window is still present, unchanged
    assert text.startswith("[cited source provenance |")  # a labeled provenance header, prepended


# ── SAFETY: identity-only — never grounds a WHAT atom, never a title, never body prose ───────────
def test_header_is_identity_only_no_title_no_body(monkeypatch) -> None:
    monkeypatch.setenv(_ENV, "1")
    header = _provenance_header(_frey_record())
    # WHO / WHEN / WHERE / doi present ...
    assert "Frey C, Osborne M" in header
    assert "2017" in header
    assert _FREY_JOURNAL in header
    assert _FREY_DOI in header
    # ... but NEVER the title (a topical/factual grounding vector) and NEVER body prose.
    assert _FREY_TITLE not in header
    assert "computerisation" not in header
    assert "Gaussian process classifier" not in header


def test_fx03_body_window_preserved_with_header(monkeypatch) -> None:
    """The header is a strict PREFIX; the FX-03 body window is byte-for-byte unchanged, so the
    out-of-span / BUG-02 defense holds — far-away factual content is still excluded, and a WHAT atom
    still judges against the bounded window, never the header."""
    monkeypatch.setenv(_ENV, "1")
    monkeypatch.setenv(_SPAN_ENV, "1")
    monkeypatch.setenv("PG_GATE_B_SPAN_WINDOW_BYTES", "100")
    cited = "increases worker productivity by 15% on average"
    full = ("PAD " * 60) + cited + (" FILLER" * 500) + " distant_unrelated_effect_term"
    start = full.index(cited)
    end = start + len(cited)
    rec = {"text": full, "authors": ["Brynjolfsson E"], "year": 2025, "doi": "10.1093/qje/qjae044"}
    docs, _ = _resolve_evidence([_Tok("bryn", start, end)], {"bryn": rec})
    text = docs[0].text
    # header present ...
    assert text.startswith("[cited source provenance |")
    assert "Brynjolfsson E" in text
    # ... body window still bounded: cited content IN, far-away content OUT (no false-accept).
    assert cited in text
    assert "distant_unrelated_effect_term" not in text
    # the header did NOT widen the body: strip the header line, the remainder is the FX-03 window.
    body = text.split("\n", 1)[1]
    assert "distant_unrelated_effect_term" not in body


def test_no_identity_record_is_byte_identical_failsafe(monkeypatch) -> None:
    """A source that declares NO provenance identity yields an EMPTY header -> the adjudication input
    is byte-identical to the bare span. Admits nothing: no fabricated grounding, no vacuous credit."""
    monkeypatch.setenv(_ENV, "1")
    monkeypatch.delenv(_SPAN_ENV, raising=False)
    docs, _ = _resolve_evidence([_Tok("x")], {"x": {"text": _FREY_SPAN}})
    assert docs[0].text == _FREY_SPAN
    assert _provenance_header({"text": _FREY_SPAN}) == ""


def test_misattribution_not_grounded_by_header(monkeypatch) -> None:
    """The header shows the source's TRUE authors, so a claim naming an author the source does NOT
    have gains NO grounding from it — a mis-attribution still fails closed (admits nothing)."""
    monkeypatch.setenv(_ENV, "1")
    rec = {"text": "We report a large effect.", "authors": ["Smith A"], "year": 2020}
    header = _provenance_header(rec)
    assert "Smith A" in header
    assert "Jones" not in header  # a false 'according to Jones' attribution is not in the input


def test_flag_off_byte_identical_even_with_identity(monkeypatch) -> None:
    """Fix OFF -> no header regardless of the record's identity metadata (byte-identical seam)."""
    monkeypatch.setenv(_ENV, "0")
    monkeypatch.delenv(_SPAN_ENV, raising=False)
    docs, _ = _resolve_evidence([_Tok("frey")], {"frey": _frey_record()})
    assert docs[0].text == _FREY_SPAN


# ── normalize_evidence_pool_lookup: carries identity under the flag; byte-identical when OFF ─────
def _raw_row() -> dict:
    return {
        "direct_quote": _FREY_SPAN,
        "authors": _FREY_AUTHORS,
        "title": _FREY_TITLE,
        "journal": _FREY_JOURNAL,
        "year": 2017,
        "doi": _FREY_DOI,
        "tier": "T1",
        "source_url": "https://ora.ox.ac.uk/objects/uuid:x",
    }


def test_normalize_carries_identity_when_on(monkeypatch) -> None:
    monkeypatch.setenv(_ENV, "1")
    rec = normalize_evidence_pool_lookup({"frey": _raw_row()})["frey"]
    assert rec["authors"] == _FREY_AUTHORS
    assert rec["year"] == 2017
    assert rec["journal"] == _FREY_JOURNAL
    assert rec["tier"] == "T1"
    # NEVER carries the title into the record (identity-only, no topical grounding vector).
    assert "title" not in rec
    # the header built from the normalized record grounds the attribution.
    assert "Frey C" in _provenance_header(rec)


def test_normalize_byte_identical_when_off(monkeypatch) -> None:
    monkeypatch.setenv(_ENV, "0")
    rec = normalize_evidence_pool_lookup({"frey": _raw_row()})["frey"]
    # pre-V4 shape only: {text, url?, doi?, pmid?} — no identity keys leak.
    assert set(rec) <= {"text", "url", "doi", "pmid"}
    for k in ("authors", "year", "journal", "tier", "title"):
        assert k not in rec


# ── build_native_gate_b_inputs: the verdict CARRIES basket corroboration (count + weights) ───────
_FIXTURE_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "native_gate_b_scope_template.json"
)
_FIXTURE_SLUG = "fixture_slug"
_TRIAL_DOI = "10.1056/NEJMoa2107519"


@dataclass
class _FakeToken:
    evidence_id: str


@dataclass
class _FakeSentence:
    sentence: str
    tokens: list
    is_verified: bool = True


@dataclass
class _FakeSection:
    title: str
    kept_sentences_pre_resolve: list = field(default_factory=list)
    is_gap_stub: bool = False


@dataclass
class _FakeMulti:
    sections: list


def _d8_config() -> D8PolicyConfig:
    return D8PolicyConfig(
        coverage_threshold=0.70,
        material_severities=["S0", "S1", "S2"],
        s0_must_cover_categories=["contraindications", "dosing_limits", "black_box_warnings"],
    )


def _build_with_tier_lookup(monkeypatch, value: str | None):
    if value is None:
        monkeypatch.delenv(_ENV, raising=False)
    else:
        monkeypatch.setenv(_ENV, value)
    template = json.loads(_FIXTURE_TEMPLATE_PATH.read_text(encoding="utf-8"))
    multi = _FakeMulti(
        sections=[
            _FakeSection(
                title="Efficacy",
                kept_sentences_pre_resolve=[
                    _FakeSentence("The trial showed an effect", [_FakeToken("ev_doi")]),
                ],
            )
        ]
    )
    lookup = {"ev_doi": {"doi": _TRIAL_DOI, "text": "trial primary endpoint", "tier": "T1"}}
    return build_native_gate_b_inputs(
        multi=multi,
        template=template,
        slug=_FIXTURE_SLUG,
        domain="clinical",
        evidence_lookup=lookup,
        model_slugs={"mirror": "m/mirror", "sentinel": "m/sentinel", "judge": "m/judge"},
        d8_config=_d8_config(),
    )


def test_audit_map_carries_corroboration_when_on(monkeypatch) -> None:
    bundle = _build_with_tier_lookup(monkeypatch, "1")
    (claim_id,) = bundle.audit_map
    row = bundle.audit_map[claim_id]
    assert row["basket_source_count"] == 1
    assert row["basket_weights"] == ["T1"]


def test_audit_map_no_corroboration_when_off(monkeypatch) -> None:
    bundle = _build_with_tier_lookup(monkeypatch, "0")
    (claim_id,) = bundle.audit_map
    row = bundle.audit_map[claim_id]
    assert "basket_source_count" not in row
    assert "basket_weights" not in row


def test_claim_id_scheme_unchanged_by_fix(monkeypatch) -> None:
    """The fix does not touch claim_id derivation (adjudication INPUT only)."""
    bundle = _build_with_tier_lookup(monkeypatch, "1")
    (claim_id,) = bundle.audit_map
    normalized = re.sub(r"\s+", " ", "The trial showed an effect".lower()).strip()
    expected = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:8]
    assert claim_id == f"00-000-{expected}"
