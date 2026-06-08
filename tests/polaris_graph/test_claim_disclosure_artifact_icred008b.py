"""I-cred-008b (#1162) — runner-side claim_disclosure.json serialization shape (offline, pure).

Tests _build_claim_disclosure_doc, the pure helper that builds the claim_disclosure.json document:
  * flag-OFF (credibility_analysis is None) => returns None => NO artifact (byte-identical),
  * flag-ON => one entry per section per kept SV with the six advisory disclosure fields,
  * the quantified path (no SectionResult) rides via telemetry["claim_disclosure"].
"""
from __future__ import annotations

from types import SimpleNamespace

from scripts.run_honest_sweep_r3 import _build_claim_disclosure_doc


def _sv(sentence, *, span_verdict="SUPPORTS", cred=0.8, origins=2, certainty="high", warns=()):
    return SimpleNamespace(
        sentence=sentence,
        span_verdict=span_verdict,
        credibility_weight=cred,
        independent_origin_count=origins,
        certainty_label=certainty,
        soft_warnings=list(warns),
    )


def _section(title, kept, *, dropped=False):
    return SimpleNamespace(
        title=title,
        kept_sentences_pre_resolve=kept,
        dropped_due_to_failure=dropped,
    )


def test_flag_off_returns_none_no_artifact():
    """No credibility_analysis => None => the runner writes NO claim_disclosure.json."""
    multi = SimpleNamespace(credibility_analysis=None, sections=[_section("Efficacy", [_sv("s")])])
    assert _build_claim_disclosure_doc(multi, None) is None


def test_flag_on_serializes_section_claims():
    multi = SimpleNamespace(
        credibility_analysis=object(),  # presence is all that matters here
        sections=[
            _section("Efficacy", [
                _sv("Claim A.", cred=0.9, certainty="high"),
                _sv("Claim B.", cred=0.3, certainty="low", warns=["superseded"]),
            ]),
            _section("Safety", [_sv("Claim C.", span_verdict="UNSUPPORTED", certainty="low")]),
        ],
    )
    doc = _build_claim_disclosure_doc(multi, None)
    assert doc is not None
    titles = [s["title"] for s in doc["sections"]]
    assert titles == ["Efficacy", "Safety"]
    efficacy = doc["sections"][0]
    assert len(efficacy["claims"]) == 2
    a = efficacy["claims"][0]
    assert set(a) == {
        "sentence", "span_verdict", "credibility_weight",
        "independent_origin_count", "certainty_label", "soft_warnings",
    }
    assert a["span_verdict"] == "SUPPORTS" and a["credibility_weight"] == 0.9
    assert efficacy["claims"][1]["soft_warnings"] == ["superseded"]


def test_dropped_and_empty_sections_excluded():
    multi = SimpleNamespace(
        credibility_analysis=object(),
        sections=[
            _section("Dropped", [_sv("x")], dropped=True),  # excluded (failure)
            _section("Empty", []),                           # excluded (no kept)
            _section("Kept", [_sv("y")]),
        ],
    )
    doc = _build_claim_disclosure_doc(multi, None)
    assert [s["title"] for s in doc["sections"]] == ["Kept"]


def test_quantified_rows_appended_from_telemetry():
    multi = SimpleNamespace(credibility_analysis=object(), sections=[])
    telem = {
        "claim_disclosure": [
            {"sentence": "TCO is $2.1B.", "span_verdict": "SUPPORTS",
             "credibility_weight": 0.7, "independent_origin_count": 2,
             "certainty_label": "moderate", "soft_warnings": []},
        ],
    }
    doc = _build_claim_disclosure_doc(multi, telem)
    assert doc["sections"][-1]["title"] == "Quantified Trade-off"
    assert doc["sections"][-1]["claims"][0]["sentence"] == "TCO is $2.1B."


def test_quantified_absent_when_no_telemetry_rows():
    multi = SimpleNamespace(credibility_analysis=object(), sections=[_section("S", [_sv("z")])])
    doc = _build_claim_disclosure_doc(multi, {"enabled": True})  # no claim_disclosure key
    assert [s["title"] for s in doc["sections"]] == ["S"]
