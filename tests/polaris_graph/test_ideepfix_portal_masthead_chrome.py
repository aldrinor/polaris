"""I-deepfix-001 (#1344) FF1-CHROME v2 — RED/GREEN unit test for the four NEW page-furniture
vocabularies the enumerated containment denylist never enumerated (a recurrence of the
I-wire-013 blind-predicate class on unlisted surface vocabularies):

  1. service/dead-fetch interstitial ........ "This journal is currently offline."
  2. OpenAlex/entity-portal record scaffold .. "…DetailsLocations Year: NNNN Type: article Abstract: …"
  3. "Name - Honorific" bare byline stub ..... "Varsha Parikh - Ms."
  4. "Publication date:"/bare NN:N masthead .. "Publication date: December 2022. 87:2 K."

RED (pre-fix, reproduced live): every defect string returns False from the real
``is_render_chrome_or_unrenderable`` (PG_RENDER_CHROME_SCREEN=1) and leaks into the rendered
rollup as a finding. GREEN (post-fix): each returns True.

v2 PRECISION (Codex+Fable build-gate over-strip fix): the v1 RULE 1 used an UNANCHORED
``_SERVICE_OFFLINE_RE.search`` whose narrow ``_has_attributed_cited_finding`` guard (needs a [N]
citation AND a finding VERB — the copula "is" is not one) could NOT rescue a substantive cited
finding that merely CONTAINS an outage phrase, so real claims like
``"Public employment service is unavailable in 37 percent of rural districts [7]."`` were dropped.
v2 WHOLE-UNIT anchors RULE 1 (``^…$`` over the cite-stripped core) and adds the KEEP guard to RULE 4,
so those cited findings STAY False (never dropped). Precision-first per the operator-locked drop-path
law (§-1.3): the safe direction is a leaked furniture unit, never a deleted finding.

The fix is detector-only (FLAG-not-drop) and gated on ``render_chrome_screen_enabled()`` (default ON,
``PG_RENDER_CHROME_SCREEN=0`` kill-switch), so the kill-switch run is byte-identical to the legacy
base screen: all six defect strings return False again.
"""

import importlib

import pytest


DEFECT_STRINGS = [
    # RULE 1 — service/dead-fetch interstitial (grammatically complete, no URL/DOI/ORCID token).
    "This journal is currently offline.",
    # RULE 2 — OpenAlex/entity-portal record scaffold (glued "DetailsLocations" + field ladder).
    "Towards an inclusive labour market DetailsLocations Year: 2026 Type: article Abstract: "
    "We qualitatively compared labour market outcomes.",
    "Algorithmic Accountability DetailsLocations Year: 2020 Type: article Abstract: "
    "How will artificial intelligence (AI) transform government.",
    # RULE 3 — bare "Name - Honorific" byline/directory stub.
    "Varsha Parikh - Ms.",
    # RULE 4 — "Publication date:" label + bare NN:N volume:issue masthead.
    "Publication date: December 2022. 87:2 K.",
    # RULE 4 (co-signal variants) — DOI / Document Version / Published in masthead recital.
    "Salimzadeh, Sara; He, Gaole; Gadiraju, Ujwal DOI 10.1145/3565472.3592959 "
    "Publication date 2023 Document Version Final published version Published in UMAP 2023",
]

# v2 additional service/dead-fetch furniture the anchored RULE 1 still catches whole-unit.
DEFECT_STRINGS_SERVICE_EXTRA = [
    "Service temporarily unavailable",
    "This site can’t be reached.",  # curly apostrophe (v2 covers can[’']t)
    "This repository is currently unavailable.",
]

# Real cited findings that COLLIDE on a surface token with each rule but are substantive prose —
# they MUST stay False (never dropped) both before and after the fix.
REAL_FINDING_CONTROLS = [
    "Generative AI could automate tasks equivalent to 300 million full-time jobs globally by 2030 [4].",
    "Rural clinics that went offline during the outage lost 12 percent of appointments [7].",
    "The report's publication date of December 2022 preceded the ChatGPT launch by one month [3].",
    "Ms. Parikh testified that reskilling budgets rose 8 percent [9].",
]

# v2 OVER-STRIP CONTROLS — the exact live-reproduced cases the Codex+Fable build-gate flagged as the
# P1/P2 over-drop under the v1 UNANCHORED RULE 1 and unguarded RULE 4. These carry a real outage /
# publication-date phrase INSIDE a substantive cited finding and MUST stay False (kept). Under v1 they
# were dropped; under v2 (whole-unit anchor + KEEP guard) they are preserved.
OVER_STRIP_CONTROLS = [
    # P1 — cited service-availability findings (copula "is unavailable"; guard has no matching verb).
    "Public employment service is unavailable in 37 percent of rural districts [7].",
    "The database is temporarily unavailable after cyberattacks, delaying appointments by 12 percent [7].",
    # P2 — a cited finding that recites a publication date next to a bare NN:N ratio.
    "Publication date: March 2021 the study found a 2:1 response ratio [5].",
]


def _load_predicate(monkeypatch, screen_flag):
    """Reload the module under a fixed PG_RENDER_CHROME_SCREEN and return the real predicate.

    The screen gate is read at call time (``render_chrome_screen_enabled()``), so a fresh env is
    honoured without reload; the reload keeps the test hermetic if module-level caching is ever
    introduced.
    """
    monkeypatch.setenv("PG_RENDER_CHROME_SCREEN", screen_flag)
    module = importlib.import_module("src.polaris_graph.generator.weighted_enrichment")
    module = importlib.reload(module)
    return module.is_render_chrome_or_unrenderable


@pytest.mark.parametrize("defect", DEFECT_STRINGS + DEFECT_STRINGS_SERVICE_EXTRA)
def test_new_furniture_vocabularies_are_flagged(monkeypatch, defect):
    """GREEN: with the screen ON, each NEW furniture vocabulary is flagged as chrome.

    (RED, pre-fix: this assertion FAILS — every string returned False and leaked as a finding.)
    """
    predicate = _load_predicate(monkeypatch, "1")
    assert predicate(defect) is True, f"NEW furniture vocabulary leaked as a finding: {defect!r}"


@pytest.mark.parametrize("finding", REAL_FINDING_CONTROLS)
def test_real_cited_findings_are_never_dropped(monkeypatch, finding):
    """Precision guard: a substantive cited finding that merely collides on a surface token with a
    rule MUST stay False (§-1.3 precision-first — never over-strip a real finding)."""
    predicate = _load_predicate(monkeypatch, "1")
    assert predicate(finding) is False, f"real cited finding over-dropped: {finding!r}"


@pytest.mark.parametrize("finding", OVER_STRIP_CONTROLS)
def test_cited_findings_with_furniture_phrase_are_not_over_stripped(monkeypatch, finding):
    """v2 REGRESSION GUARD (Codex+Fable P1/P2): a substantive cited finding that CONTAINS a service
    outage phrase or a publication-date recital must STAY False. Under the v1 UNANCHORED RULE 1 /
    unguarded RULE 4 these were dropped; v2 (whole-unit anchor + KEEP guard) keeps them."""
    predicate = _load_predicate(monkeypatch, "1")
    assert predicate(finding) is False, f"cited finding over-stripped by furniture rule: {finding!r}"


@pytest.mark.parametrize("defect", DEFECT_STRINGS)
def test_kill_switch_is_byte_identical_to_legacy_base_screen(monkeypatch, defect):
    """PG_RENDER_CHROME_SCREEN=0 => the NEW categories are skipped => the six defect strings are
    NOT flagged (byte-identical to the legacy base junk screen). Proves the fix is fully gated."""
    predicate = _load_predicate(monkeypatch, "0")
    assert predicate(defect) is False, (
        f"kill-switch OFF should not flag NEW furniture vocab (base screen only): {defect!r}"
    )
