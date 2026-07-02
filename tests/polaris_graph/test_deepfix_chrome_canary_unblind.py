"""I-deepfix-001 (#1344) chrome_canary_unblind — offline RED->GREEN tests.

``_contains_forensic_chrome`` (the chrome-as-claim canary / render-screen containment predicate) was
BLIND to three page-furniture classes (the canary passed 0/226 while the report was chrome-saturated):
an author-affiliation/email byline, a Table-of-Contents dot-leader run, and a "By clicking … you
accept" consent banner. The fix adds high-precision, dual-signal/structure-anchored CONTAINMENT rules.

Detector-only (FLAG-not-drop): a flagged unit is withheld from the rendered rollup and KEPT in
evidence — the FROZEN faithfulness engine (strict_verify / NLI / 4-role D8 / provenance / span-
grounding) is UNCHANGED. Offline: no GPU, no network, no paid LLM.
"""
from __future__ import annotations

import src.polaris_graph.generator.weighted_enrichment as we

_BYLINE = (
    "Results were significant. Correspondence: Department of Cardiology, Harvard "
    "University. Email: jsmith@harvard.edu"
)
_TOC = "Introduction .......... 12"
_COOKIE = "By continuing to browse this site you agree to our use of cookies."


def test_author_email_byline_flagged():
    """An email address CO-OCCURRING with an institution keyword is flagged as chrome."""
    assert we._contains_missed_chrome_class(_BYLINE) is True
    assert we._contains_forensic_chrome(_BYLINE) is True
    assert we.is_render_chrome_or_unrenderable(_BYLINE) is True


def test_toc_dotleaders_flagged():
    """A 4+ dot-leader run followed by a page number is flagged as ToC furniture."""
    assert we._contains_missed_chrome_class(_TOC) is True
    assert we._contains_forensic_chrome(_TOC) is True
    assert we.is_render_chrome_or_unrenderable(_TOC) is True


def test_cookie_consent_banner_flagged():
    """A "By continuing … you agree" consent banner is flagged as chrome."""
    assert we._contains_missed_chrome_class(_COOKIE) is True
    assert we._contains_forensic_chrome(_COOKIE) is True
    assert we.is_render_chrome_or_unrenderable(_COOKIE) is True


def test_precision_real_prose_not_flagged():
    """Precision: real clinical prose is NEVER flagged — an institution finding with NO email,
    a decimal table (digits between the dots), a 3-dot ellipsis, and a real "by clicking" action
    verb (no accept/agree/consent) all pass clean."""
    institution_finding = (
        "The Department of Cardiology reported that mortality fell by twelve percent in the trial."
    )
    decimal_table = "The rates were 0.034 and 0.030 across the two study arms respectively here."
    ellipsis = "The results were striking ... and the effect persisted for twelve weeks in cohort."
    action_verb = (
        "By clicking the enzyme into its active conformation the substrate binding accelerates."
    )
    for text in (institution_finding, decimal_table, ellipsis, action_verb):
        assert we._contains_missed_chrome_class(text) is False


def test_email_alone_is_not_enough():
    """The email signal ALONE (no co-occurring institution keyword) is NOT flagged — a real
    finding could quote a contact address; both signals are required (dual-signal precision)."""
    email_only = (
        "Please contact the trial coordinator at jsmith@example.com for enrollment details today."
    )
    assert we._contains_missed_chrome_class(email_only) is False


def test_predicate_was_blind_pre_fix(monkeypatch):
    """RED-before proof: with the new rule neutralized, the three chrome inputs fall through
    _contains_forensic_chrome UNFLAGGED — confirming the containment predicate was blind to them
    before this fix (no other rule catches them)."""
    monkeypatch.setattr(we, "_contains_missed_chrome_class", lambda text: False)
    assert we._contains_forensic_chrome(_BYLINE) is False
    assert we._contains_forensic_chrome(_TOC) is False
    assert we._contains_forensic_chrome(_COOKIE) is False
