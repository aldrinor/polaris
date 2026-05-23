"""I-bug-776 (#817) layer-4 — direct primary-trial DOI seed-candidate injection.

Codex decision (b): inject the anchored trials' known DOIs as DIRECT doi.org
candidate URLs (not search queries), because guideline-dominated search ranking
buries the pivotal OA primaries. They pass the same fetch/tier/adequacy gates
(no laundering). These assert the deterministic config-parsing core.
"""

from __future__ import annotations

from src.polaris_graph.retrieval.primary_trial_expander import (
    _is_valid_doi,
    expand_primary_trial_dois,
)

_AFIB = "clinical_afib_anticoagulation"


def _tmpl(dois: dict) -> dict:
    return {"per_query_primary_trial_dois": {_AFIB: dois}}


def test_afib_dois_become_doiorg_candidates() -> None:
    t = _tmpl({
        "ARISTOTLE": "10.1056/NEJMoa1107039",
        "ROCKET-AF": "10.1056/NEJMoa1009638",
    })
    out = expand_primary_trial_dois(t, _AFIB)
    assert out == [
        "https://doi.org/10.1056/NEJMoa1107039",
        "https://doi.org/10.1056/NEJMoa1009638",
    ]


def test_negative_cases_return_empty() -> None:
    t = _tmpl({"ARISTOTLE": "10.1056/NEJMoa1107039"})
    assert expand_primary_trial_dois(t, "tech_rag_architectures_2024") == []  # unconfigured slug
    assert expand_primary_trial_dois(None, _AFIB) == []                        # no template
    assert expand_primary_trial_dois({}, _AFIB) == []                          # no key
    assert expand_primary_trial_dois({"per_query_primary_trial_dois": []}, _AFIB) == []  # malformed
    assert expand_primary_trial_dois(t, "") == []                              # empty slug


def test_malformed_dois_rejected() -> None:
    t = _tmpl({
        "GOOD": "10.1056/NEJMoa1107039",
        "NO_PREFIX": "NEJMoa1107039",         # missing 10.
        "WHITESPACE": "10.1056/ NEJMoa1",     # interior space
        "QUOTE": '10.1056/NEJM"a',            # quote
        "NOT_STR": 12345,                     # non-string
    })
    out = expand_primary_trial_dois(t, _AFIB)
    assert out == ["https://doi.org/10.1056/NEJMoa1107039"]


def test_is_valid_doi() -> None:
    assert _is_valid_doi("10.1056/NEJMoa1107039")
    assert _is_valid_doi("10.3390/jcm14228079")
    assert not _is_valid_doi("NEJMoa1107039")       # no 10.
    assert not _is_valid_doi("10.1056")             # no slash
    assert not _is_valid_doi("10.1056/a b")         # whitespace
    assert not _is_valid_doi('10.1056/a"b')         # quote
    # iter-1 P2 (Codex): empty-component / non-digit-registrant forms rejected
    assert not _is_valid_doi("10./x")               # empty registrant
    assert not _is_valid_doi("10.1056/")            # empty suffix
    assert not _is_valid_doi("10.abc/x")            # non-digit registrant


def test_dedupe_preserves_order() -> None:
    t = _tmpl({"A": "10.1000/x", "B": "10.1000/x", "C": "10.2000/y"})  # A,B same DOI
    out = expand_primary_trial_dois(t, _AFIB)
    assert out == ["https://doi.org/10.1000/x", "https://doi.org/10.2000/y"]
