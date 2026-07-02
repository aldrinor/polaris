"""I-beatboth-001 (#1276) — behavioral fail-loud test for the cited-span fetch-shell gate.

§-1.4 behavioral acceptance: the effect must APPEAR in the real output path, not just a leaf
unit. These tests prove, on the ACTUAL run-#7 [1] CAPTCHA span (drb_78 corpus, ev_128, 476
chars), that:
  1. the detector flags it AND a claim grounded on it FAILS verify_sentence_provenance
     (the run-#7 self-citation hole — prose verbatim-copies the junk span — is now closed);
  2. it propagates to the render gate: the shell member's isolated span_verdict is UNSUPPORTED,
     it is ABSENT from select_unbound_supports_by_weight (the "Corroborated Weighted Findings"
     surfacing) and never increments verified_support_origin_count — no weight_mass<=0 filter;
  3. NORMAL real clinical spans STILL pass, including adversarial-borderline tokens (a methods
     span with "verification", a bibliography span with "CrossRef", a nutrition span with
     "cookie"): the gate is high-precision, never a §-1.3 breadth loss;
  4. PG_CITED_SPAN_SHELL_DETECT=0 reverts to byte-identical legacy behaviour.

The gate is faithfulness-TIGHTENING (junk rejected) — it never relaxes strict_verify / NLI /
4-role / provenance.

FAITHFULNESS DIRECTION (iter-2, anchored to the merge base = HEAD, which has NO cited-span shell
gate): this change is STRICTLY TIGHTENING vs HEAD. Every shell catch here is NEW; ZERO
previously-caught shells regress (at HEAD nothing was caught at this layer). The iter-2 precision
work additionally STOPS 4 real false-drops (real DBS/Parkinson's articles ev_694/ev_679/ev_295/
ev_693 that carry an incidental cookie / download-citation footer), which the iter-1 any-length
chrome firing would have wrongly dropped — false-drops are themselves a §-1.3 breadth loss.

CEDED-BY-DESIGN (disclosed, NOT a relaxation — none were caught at HEAD): a handful of real
drb_78 shells are STRING-INDISTINGUISHABLE from legitimate short abstracts/articles, so a
deterministic string gate cannot net them without re-introducing false-drops (the exact P1 #1
defect). These are deliberately left to the relevance / NLI / strict_verify layers (§-1.3: the
faithfulness engine is the hard gate, not a string list), captured as a follow-up issue:
  * ev_689 — 1500-char CrossRef/Scite citation-manager chrome page (>800, identical in form to the
    ``bibliography_with_crossref`` legit negative; also off-topic → relevance-gate's job).
  * ev_715 / ev_109 / ev_272 — 559-char cookie-consent banners whose phrasing ("utilizes
    technologies such as cookies" + "accept the default settings") does not match the exact
    co-occurrence tuples; adding more phrasings is the §-1.3-banned whack-a-mole.
  * ev_082 / ev_671 — 602/693-char content-starved abstract SKELETONS ("Abstract Objective:
    Background: Methods: Results: Conclusions:" + incidental CrossRef text); their defect is
    empty-section, which is ``is_content_starved``'s retrieval-layer job, not a shell-vocab match.
NOTE on render-dump indices: the PHASE1_ISSUES P0-1 ``[424]/[440]/[448]`` (YouTube) and ``[612]``
(language-nav) are ``live_corpus_dump.json`` render indices, not ``evidence_for_gen`` ev_ids — no
YouTube / language-selector shell rows exist in this corpus snapshot (0 of 794), so they cannot be
asserted here; that boundary is stated explicitly rather than left silently unchecked.

CI vs LOCAL coverage (honesty): the drb_78 ``corpus_snapshot.json`` lives under ``outputs/`` which
is gitignored (CLAUDE.md §5), so the ``test_iter2_real_corpus_*`` block ``pytest.skip``s when the
snapshot is absent — it is LOCAL replay proof, not CI-enforced. The CI-ENFORCED guarantee is the
SYNTHETIC cases (the CAPTCHA reject, ``long_article_with_cookie_footer`` / ``..._download_citation``
/ ``abstract_with_access_denied_once`` not-shell, the ambiguous short-vs-long pair, the kill-switch)
— they encode the SAME behaviors and run unconditionally.
"""

from __future__ import annotations

import os

import pytest

from src.polaris_graph.generator.provenance_generator import verify_sentence_provenance
from src.polaris_graph.retrieval.shell_detector import (
    is_access_denial_stub,
    is_cited_span_shell,
)

# ── The ACTUAL run-#7 [1] CAPTCHA span (drb_78 corpus_snapshot, ev_128, 476 chars). This is the
# Lancet DBS-RCT anchor (doi 10.1016/s0140-6736(21)00218-x) that grounded 6 top-of-report units. ──
RUN7_CAPTCHA_SPAN = (
    "Title: Just a moment... URL Source: https://doi.org/10.1016/s0140-6736(21)00218-x "
    "Warning: This page maybe requiring CAPTCHA, please make sure you are authorized to access "
    "this page. Markdown Content: ![Image 1: Icon for www.thelancet.com]"
    "(https://www.thelancet.com/favicon.ico) ## www.thelancet.com ## Performing security "
    "verification This website uses a security service to protect against malicious bots. This "
    "page is displayed while the website verifies you are not a bot."
)

# ── Adversarial NEGATIVES: real clinical spans that CONTAIN a borderline shell token but are
# legitimate article prose. They MUST pass (a false-drop is a §-1.3 breadth loss). ──
LEGIT_METHODS_SPAN = (
    "In this randomized controlled trial, deep brain stimulation of the subthalamic nucleus "
    "reduced motor symptoms by 9.5 points; outcome verification was performed by blinded "
    "assessors using the UPDRS scale across 156 patients over 24 months of follow-up."
)
LEGIT_BIBLIOGRAPHY_SPAN = (
    "Kocabicak E, Alptekin O. References are indexed in CrossRef and PubMed with full citation "
    "metadata. Deep brain stimulation improved quality of life in advanced Parkinson disease "
    "patients, as reported in this Movement Disorders systematic review of 1240 participants."
)
LEGIT_NUTRITION_SPAN = (
    "A Mediterranean diet rich in antioxidants may slow neurodegeneration; one cohort study of "
    "240 elderly adults that included a cookie-baking adherence intervention found a 3.4 point "
    "cognitive benefit over 12 months relative to the control group."
)

# ── I-beatboth-001 iter-2 (Codex 2×P1) adversarial NEGATIVES: the EXACT false-drop scenarios
# Codex named. A long real article body that incidentally carries page-chrome (cookie footer /
# publisher "download citation" widget) is NOT a shell; a legit short abstract that says an
# ambiguous phrase ("access denied") ONCE with no second shell signal is NOT a shell. These MUST
# pass — a false-drop is a §-1.3 breadth loss. Built to genuinely EXCEED the chrome-dominance
# ceiling (so they exercise the new dominance logic, not the old length gate). ──

# A ~3.6k-char real Parkinson's/DBS article body with a cookie-consent footer appended. The cookie
# co-occurrence ("we use cookies" + "accept all") matches but is a tiny incidental fraction of a
# long real body, so chrome-dominance must NOT fire.
_REAL_ARTICLE_PROSE = (
    "Deep brain stimulation of the subthalamic nucleus is an established therapy for advanced "
    "Parkinson disease. In this multicentre randomized controlled trial, 156 patients with motor "
    "fluctuations were assigned to bilateral subthalamic stimulation or best medical therapy and "
    "followed for 24 months. The primary outcome was the change in motor symptoms measured on the "
    "Unified Parkinson Disease Rating Scale part III in the practically defined off-medication "
    "state. Stimulation reduced motor symptoms by 9.5 points relative to a 1.2 point change in the "
    "medical therapy group, a between-group difference that was both statistically significant and "
    "clinically meaningful. Quality of life on the PDQ-39 summary index improved by 7.8 points in "
    "the stimulation group. Dyskinesia duration fell from 4.2 to 1.6 hours per day and the daily "
    "off time decreased by 3.1 hours. Adverse events included three intracerebral haemorrhages and "
    "transient dysarthria; serious device-related events occurred in 8 percent of participants. "
    "Cognitive outcomes were stable across the cohort with no significant decline on the Mattis "
    "Dementia Rating Scale. The investigators concluded that subthalamic stimulation provides a "
    "durable motor benefit and improved quality of life over best medical therapy in carefully "
    "selected patients with advanced Parkinson disease and disabling motor complications, while "
    "noting that surgical and stimulation-related adverse events require an experienced "
    "multidisciplinary team and careful patient selection to mitigate. Long-term follow-up data "
    "from the same cohort confirmed persistence of the motor benefit at five years, with attenuated "
    "but maintained quality-of-life gains and no unexpected late safety signals across the surgical "
    "and neurostimulation domains evaluated in the extension phase of the trial."
) * 1  # ~1.6k chars of real prose
REAL_ARTICLE_WITH_COOKIE_FOOTER = (
    _REAL_ARTICLE_PROSE
    + _REAL_ARTICLE_PROSE  # double it so the body is well above the 800-char chrome ceiling
    + " We use cookies to improve your experience. Accept all and continue."
)

# A ~3.3k-char real bibliography-rich article body with a publisher "download citation" widget +
# CrossRef inside genuine content. The ("download citation", "crossref") class matches but is a
# tiny fraction of a long real body, so it must NOT fire.
REAL_ARTICLE_WITH_DOWNLOAD_CITATION = (
    _REAL_ARTICLE_PROSE
    + _REAL_ARTICLE_PROSE
    + " References are indexed in CrossRef and PubMed. Download Citation for offline use."
)

# A ~1.5k-char legitimate abstract that says "access denied" ONCE (describing a data-access barrier
# reported in the study) with NO second shell signal. Must pass — ambiguous phrase alone, body far
# above the tight ambiguous ceiling, no corroborating signal.
LEGIT_ABSTRACT_WITH_ACCESS_DENIED = (
    "This systematic review examined barriers to deep brain stimulation in advanced Parkinson "
    "disease across 18 health systems. Among the most frequently reported structural barriers was "
    "that access denied on the basis of age or insurance status accounted for a substantial share "
    "of patients who were eligible but never referred for surgical evaluation. Across the included "
    "cohorts, roughly 22 percent of clinically eligible patients faced an administrative barrier "
    "before specialist assessment. The authors analysed referral pathways, reimbursement policy, "
    "and geographic distance to implanting centres, and found that streamlined referral protocols "
    "reduced the proportion of eligible patients turned away by 14 percentage points over a "
    "two-year period. They concluded that policy-level interventions, rather than clinical "
    "contraindications alone, drive much of the observed undertreatment, and recommended structured "
    "referral criteria and centralised eligibility review to reduce inappropriate denial of access "
    "to an effective therapy for disabling motor complications in this population."
)

_LEGIT_SPANS = {
    "methods_with_verification": LEGIT_METHODS_SPAN,
    "bibliography_with_crossref": LEGIT_BIBLIOGRAPHY_SPAN,
    "nutrition_with_cookie": LEGIT_NUTRITION_SPAN,
    # iter-2 (Codex 2×P1) false-drop scenarios:
    "long_article_with_cookie_footer": REAL_ARTICLE_WITH_COOKIE_FOOTER,
    "long_article_with_download_citation": REAL_ARTICLE_WITH_DOWNLOAD_CITATION,
    "abstract_with_access_denied_once": LEGIT_ABSTRACT_WITH_ACCESS_DENIED,
}


def _grounded_sentence(span: str, eid: str = "ev_128") -> tuple[str, dict]:
    """A claim whose prose verbatim-copies the span (the self-citation hole) + its pool."""
    sentence = f"{span} [#ev:{eid}:0-{len(span)}]"
    pool = {eid: {"evidence_id": eid, "direct_quote": span}}
    return sentence, pool


# ─────────────────────────────────────────────────────────────────────────────
# 1. The detector flags the real CAPTCHA shell; the run-#7 grounded claim FAILS verify.
# ─────────────────────────────────────────────────────────────────────────────


def test_run7_captcha_span_is_detected_as_shell():
    assert is_cited_span_shell(RUN7_CAPTCHA_SPAN) is True
    # The pre-existing retrieval-time stub gate must also agree (single-sourced vocab).
    assert is_access_denial_stub(RUN7_CAPTCHA_SPAN) is True


def test_run7_captcha_grounded_claim_fails_verify_sentence_provenance(monkeypatch):
    monkeypatch.setenv("PG_CITED_SPAN_SHELL_DETECT", "1")
    sentence, pool = _grounded_sentence(RUN7_CAPTCHA_SPAN)
    result = verify_sentence_provenance(sentence, pool)
    assert result.is_verified is False, (
        "the run-#7 self-citation hole is OPEN: a claim grounded on the CAPTCHA span verified"
    )
    assert any(r.startswith("fetch_shell_cited_span:") for r in result.failure_reasons), (
        f"expected a fetch_shell_cited_span failure, got {result.failure_reasons}"
    )


def test_shell_cannot_ride_on_a_real_co_token(monkeypatch):
    """A multi-token sentence citing BOTH a shell and a real span must still DROP (option (a)):
    a shell token poisons the whole sentence so the junk citation can never render on the back
    of a legitimate co-token."""
    monkeypatch.setenv("PG_CITED_SPAN_SHELL_DETECT", "1")
    real = LEGIT_METHODS_SPAN
    sentence = (
        f"Deep brain stimulation reduced motor symptoms by 9.5 points. "
        f"[#ev:ev_real:0-{len(real)}] [#ev:ev_128:0-{len(RUN7_CAPTCHA_SPAN)}]"
    )
    pool = {
        "ev_real": {"evidence_id": "ev_real", "direct_quote": real},
        "ev_128": {"evidence_id": "ev_128", "direct_quote": RUN7_CAPTCHA_SPAN},
    }
    result = verify_sentence_provenance(sentence, pool)
    assert result.is_verified is False
    assert any(r.startswith("fetch_shell_cited_span:ev_128") for r in result.failure_reasons)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Render-gate PROPAGATION: shell → UNSUPPORTED → absent from the corroborated surfacing.
# ─────────────────────────────────────────────────────────────────────────────


def test_shell_member_is_unsupported_in_isolated_verify(monkeypatch):
    monkeypatch.setenv("PG_CITED_SPAN_SHELL_DETECT", "1")
    from src.polaris_graph.synthesis.credibility_pass import (
        MEMBER_TIER_UNVERIFIED,
        _verify_member_in_isolation,
    )

    row = {"evidence_id": "ev_128", "direct_quote": RUN7_CAPTCHA_SPAN, "authority_score": None}
    # I-deepfix-001 Wave-3 P1b (#1344): _verify_member_in_isolation now returns a 3-tuple
    # (span_verdict, member_tier, judge_unavailable). A shell span deterministically FAILS -> not a
    # judge outage, so judge_unavailable is False.
    verdict, tier, judge_unavailable = _verify_member_in_isolation(
        "Performing security verification protect against malicious bots.",
        row,
        verify_fn=verify_sentence_provenance,
    )
    assert verdict == "UNSUPPORTED"
    assert tier == MEMBER_TIER_UNVERIFIED
    assert judge_unavailable is False


def test_shell_absent_from_corroborated_weighted_findings(monkeypatch):
    """The render gate, proven to fire — NOT a weight_mass<=0 filter. A shell member with
    authority/weight_mass=0 (the §-1.3 case) never reaches the surfacing because its isolated
    span_verdict is UNSUPPORTED, and it never increments verified_support_origin_count."""
    monkeypatch.setenv("PG_CITED_SPAN_SHELL_DETECT", "1")
    from types import SimpleNamespace

    from src.polaris_graph.generator.weighted_enrichment import (
        select_unbound_supports_by_weight,
    )
    from src.polaris_graph.synthesis.credibility_pass import (
        BasketMember,
        ClaimBasket,
        _verify_member_in_isolation,
    )

    row = {"evidence_id": "ev_128", "direct_quote": RUN7_CAPTCHA_SPAN, "authority_score": None, "tier": "T7"}
    # I-deepfix-001 Wave-3 P1b (#1344): 3-tuple return (judge_unavailable ignored here).
    verdict, tier, _judge_unavailable = _verify_member_in_isolation(
        "Performing security verification protect against malicious bots.",
        row,
        verify_fn=verify_sentence_provenance,
    )
    member = BasketMember(
        evidence_id="ev_128", source_url="", source_tier="T7",
        origin_cluster_id="origin::ev_128", credibility_weight=None, authority_score=0.0,
        span=(0, len(RUN7_CAPTCHA_SPAN)), direct_quote=RUN7_CAPTCHA_SPAN,
        span_verdict=verdict, member_tier=tier,
    )
    basket = ClaimBasket(
        claim_cluster_id="clm_shell", claim_text="x", subject="", predicate="",
        supporting_members=[member], refuter_cluster_ids=(), weight_mass=0.0,
        total_clustered_origin_count=1,
        verified_support_origin_count=(1 if verdict == "SUPPORTS" else 0),
        basket_verdict="unverified",
    )
    analysis = SimpleNamespace(baskets=[basket])
    selection = select_unbound_supports_by_weight(
        evidence_pool={"ev_128": row}, credibility_analysis=analysis, contract_plans=[],
    )
    assert "ev_128" not in selection, "shell leaked into the Corroborated Weighted Findings render"
    assert basket.verified_support_origin_count == 0, "shell counted as a corroborated origin"


# ─────────────────────────────────────────────────────────────────────────────
# 3. NEGATIVES — adversarial-borderline legitimate spans MUST pass (no false-drop).
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name,span", list(_LEGIT_SPANS.items()))
def test_legit_borderline_span_not_flagged_as_shell(name, span):
    assert is_cited_span_shell(span) is False, f"false-positive shell on {name}"


@pytest.mark.parametrize("name,span", list(_LEGIT_SPANS.items()))
def test_legit_borderline_grounded_claim_still_verifies(monkeypatch, name, span):
    monkeypatch.setenv("PG_CITED_SPAN_SHELL_DETECT", "1")
    sentence, pool = _grounded_sentence(span, eid="ev_real")
    result = verify_sentence_provenance(sentence, pool)
    assert result.is_verified is True, (
        f"false-drop on a legitimate span ({name}): {result.failure_reasons}"
    )


def test_other_shell_classes_detected():
    """Cookie-consent banner, HTTP 404, citation-UI chrome, social boilerplate — all shells."""
    cookie = (
        "We use cookies to improve your experience. Accept all cookies or manage your cookie "
        "preferences. Cookie policy. Privacy policy."
    )
    not_found = (
        "404 Not Found. The requested URL was not found on this server. Pàgina no trobada."
    )
    citation_ui = (
        "Download Citation. Export to EndNote, Mendeley, RefWorks. Track citations via CrossRef "
        "and Scite. Add to citation manager."
    )
    youtube = (
        "Autoplay is paused. Up next. Subscribe. Watch later. Share. New comments cannot be "
        "posted and votes cannot be cast."
    )
    for body in (cookie, not_found, citation_ui, youtube):
        assert is_cited_span_shell(body) is True, f"missed shell class: {body[:40]!r}"


# ─────────────────────────────────────────────────────────────────────────────
# 3b. I-beatboth-001 iter-2 (Codex 2×P1) — PRECISION: the new dominance + multi-signal logic.
# ─────────────────────────────────────────────────────────────────────────────


def test_iter2_long_real_article_with_cookie_footer_is_not_shell():
    """Codex P1 #1: a long real article body that incidentally carries a cookie footer
    ("we use cookies" + "accept all") is NOT a shell — the chrome class is SHORT-body only, and the
    body must genuinely exceed the chrome ceiling so this exercises the new gate, not the old
    any-length firing."""
    from src.polaris_graph.retrieval.shell_detector import _chrome_max_chars

    assert len(REAL_ARTICLE_WITH_COOKIE_FOOTER.strip()) > _chrome_max_chars(), (
        "test body too short — would not exercise the chrome short-body ceiling"
    )
    low = REAL_ARTICLE_WITH_COOKIE_FOOTER.lower()
    assert "we use cookies" in low and "accept all" in low, "the cookie co-occurrence must match"
    assert is_cited_span_shell(REAL_ARTICLE_WITH_COOKIE_FOOTER) is False


def test_iter2_long_real_article_with_download_citation_is_not_shell():
    """Codex P1 #1: a long real bibliography-bearing article body with a publisher
    "Download Citation" + CrossRef widget inside genuine content is NOT a shell."""
    from src.polaris_graph.retrieval.shell_detector import _chrome_max_chars

    assert len(REAL_ARTICLE_WITH_DOWNLOAD_CITATION.strip()) > _chrome_max_chars()
    low = REAL_ARTICLE_WITH_DOWNLOAD_CITATION.lower()
    assert "download citation" in low and "crossref" in low, "the citation-UI class must match"
    assert is_cited_span_shell(REAL_ARTICLE_WITH_DOWNLOAD_CITATION) is False


def test_iter2_legit_abstract_with_access_denied_once_is_not_shell():
    """Codex P1 #2: a legit ~1.5k-char abstract that says "access denied" ONCE, with NO second
    shell signal, is NOT a shell — an ambiguous phrase alone above the tight ceiling does not fire."""
    from src.polaris_graph.retrieval.shell_detector import _ambiguous_short_body_max_chars

    assert "access denied" in LEGIT_ABSTRACT_WITH_ACCESS_DENIED.lower()
    assert len(LEGIT_ABSTRACT_WITH_ACCESS_DENIED.strip()) > _ambiguous_short_body_max_chars()
    assert is_cited_span_shell(LEGIT_ABSTRACT_WITH_ACCESS_DENIED) is False


def test_iter2_real_cookie_shell_still_caught_short_body():
    """A genuine tiny cookie-consent page (chrome IS the whole body) still fails closed via the
    short-body dominance clause — tightening did NOT relax the real-shell catch."""
    cookie_shell = (
        "We use cookies to improve your experience. Accept all cookies or manage your cookie "
        "preferences. Cookie policy."
    )
    assert is_cited_span_shell(cookie_shell) is True


def test_iter2_ambiguous_multi_signal_fires_on_short_body():
    """Multi-signal on a SHORT body: TWO ambiguous phrases co-occurring in a short stub fail closed
    via the ambiguous multi-signal clause — corroboration, not a bare phrase, drives it."""
    short_two_ambiguous = "Access denied. Security verification required before continuing."
    low = short_two_ambiguous.lower()
    assert "access denied" in low and "security verification" in low
    assert is_cited_span_shell(short_two_ambiguous) is True


def test_iter2_ambiguous_multi_signal_does_not_fire_on_long_body():
    """Bounded corroboration (advisor catch): TWO ambiguous phrases inside a LONG real body must
    NOT fail closed — the multi-signal clause is gated to a short body, so a long off-clinical
    (security/IT/systems-methods) article using both "access denied" and "security verification"
    is NOT a §-1.3 false-drop."""
    from src.polaris_graph.retrieval.shell_detector import _short_body_max_chars

    long_two_ambiguous = (
        "This systems-security methods paper evaluates authorization controls in clinical data "
        "platforms. When access denied events were logged, the security verification subsystem "
        "recorded the failed attempt for audit. "
        + ("Detailed real methodological content describing the evaluation and results. " * 60)
    )
    assert len(long_two_ambiguous.strip()) > _short_body_max_chars()
    low = long_two_ambiguous.lower()
    assert "access denied" in low and "security verification" in low
    assert is_cited_span_shell(long_two_ambiguous) is False


def test_iter2_bare_access_denied_stub_still_caught_very_short_body():
    """A bare "Access Denied" stub page (very short body, single ambiguous phrase, no second
    signal) still fails closed via the much-tighter ambiguous short-body ceiling."""
    bare_stub = "Access Denied. You do not have permission to view this page."
    assert is_cited_span_shell(bare_stub) is True


def test_iter2_change_language_nav_requires_corroboration():
    """"change language" moved to the ambiguous set: a real multilingual page that merely offers a
    "change language" control inside a long real body is NOT dropped; a bare nav-only stub is."""
    long_real = (
        "This guideline describes the management of advanced Parkinson disease. "
        + ("Detailed real clinical content describing therapy and outcomes. " * 30)
        + " You may change language using the menu at the top of the page."
    )
    assert is_cited_span_shell(long_real) is False
    nav_stub = "Change language. Select your language. English Español Français Deutsch 日本語."
    assert is_cited_span_shell(nav_stub) is True


# ─────────────────────────────────────────────────────────────────────────────
# 3c. I-beatboth-001 iter-2 — REAL-CORPUS replay (§-1.4 behavioral acceptance on the actual
#     drb_78 corpus_snapshot, not synthetic stand-ins). This is the evidence that the iter-2
#     precision change loses ZERO genuine shells and stops the real false-drops Codex flagged.
# ─────────────────────────────────────────────────────────────────────────────

_DRB78_CORPUS = os.path.join(
    "outputs", "corpus_backups", "extracted", "drb_78_parkinsons_dbs", "corpus_snapshot.json"
)


def _load_drb78_rows():
    import json

    if not os.path.exists(_DRB78_CORPUS):
        pytest.skip(f"drb_78 corpus snapshot not present at {_DRB78_CORPUS}")
    with open(_DRB78_CORPUS, encoding="utf-8") as fh:
        snap = json.load(fh)
    return {r["evidence_id"]: (r.get("direct_quote") or "") for r in snap["evidence_for_gen"]}


# The genuine shells the run-#7 audit (PHASE1_ISSUES.md P0-1) found in this corpus. ALL must remain
# fail-closed after the iter-2 precision change — faithfulness is NEVER relaxed to widen breadth.
_REAL_SHELL_EVIDENCE_IDS = (
    "ev_099",  # 476-char Lancet CAPTCHA / "Just a moment" security-verification interstitial
    "ev_118",  # ditto (duplicate fetch)
    "ev_030",  # 376-char "are you a robot" / captcha-challenge bot wall
    "ev_704",  # 417-char Catalan "Pàgina no trobada" 404
    "ev_540",  # 1500-char Dove Press "Target URL returned error 404" crawler shell
    "ev_717",  # 6639-char conference "Page not found" + "Target URL returned error 404" 404 shell
)

# The real DBS/Parkinson's ARTICLES in this corpus that carry an INCIDENTAL chrome footer (cookie /
# download-citation) inside genuine long prose. These are the exact false-drops Codex P1 #1 named —
# the OLD any-length chrome firing would have wrongly dropped them. ALL must PASS (not-shell).
_REAL_ARTICLE_WITH_INCIDENTAL_CHROME_IDS = (
    "ev_694",  # 8836-char "Familial young-onset Parkinson's disease… SNCA duplication" + download-citation
    "ev_679",  # 8800-char "Optimal target localisation… eight-year outcome for subthalamic stimulation"
    "ev_295",  # 7074-char "Methodological aspects of deep brain stimulation" + we-use-cookies footer
    "ev_693",  # 2016-char Toft & Dietrichs (Mov Disord) real article + cookie + download-citation chrome
)


@pytest.mark.parametrize("eid", _REAL_SHELL_EVIDENCE_IDS)
def test_iter2_real_corpus_genuine_shell_still_rejected(eid):
    """No faithfulness relaxation: every genuine shell in the real drb_78 corpus still fails closed,
    including the 6639-char ev_717 crawler-404 that the short-body gate alone would have passed
    (caught by the any-length crawler-error CHALLENGE signature added this iter)."""
    rows = _load_drb78_rows()
    assert eid in rows, f"{eid} missing from corpus snapshot"
    assert is_cited_span_shell(rows[eid]) is True, (
        f"{eid} (len={len(rows[eid].strip())}) leaked through — faithfulness was relaxed"
    )


@pytest.mark.parametrize("eid", _REAL_ARTICLE_WITH_INCIDENTAL_CHROME_IDS)
def test_iter2_real_corpus_article_with_footer_now_passes(eid):
    """Codex P1 #1 on REAL data: a genuine long DBS/Parkinson's article carrying an incidental
    cookie / download-citation footer is NOT a shell. The OLD any-length chrome firing false-dropped
    these; the iter-2 short-body chrome ceiling fixes it."""
    rows = _load_drb78_rows()
    assert eid in rows, f"{eid} missing from corpus snapshot"
    body = rows[eid]
    assert len(body.strip()) > 800, f"{eid} should be a long body, got {len(body.strip())}"
    assert is_cited_span_shell(body) is False, (
        f"{eid} (len={len(body.strip())}) false-dropped — a real article was lost (§-1.3 breadth)"
    )


def test_iter2_crawler_error_signature_fires_only_on_real_shells_corpuswide():
    """The any-length crawler-error signature ("target url returned error" + "not found") must fire
    on the 2 genuine 404 shells and ZERO real articles across all 794 drb_78 rows — the empirical
    proof (not 'never in real prose' reasoning) that the any-length firing is safe. Uses the actual
    cited-span-only constant, NOT a hand-copied phrase, so the test tracks the source of truth."""
    from src.polaris_graph.retrieval.shell_detector import CITED_SPAN_ANY_LENGTH_COOCCURRENCE

    rows = _load_drb78_rows()
    fired = [
        eid
        for eid, body in rows.items()
        if any(all(t in body.lower() for t in combo) for combo in CITED_SPAN_ANY_LENGTH_COOCCURRENCE)
    ]
    assert set(fired) == {"ev_540", "ev_717"}, (
        f"crawler-error signature fired on {sorted(fired)} — expected exactly the 2 real 404 shells"
    )


def test_iter2_retrieval_gate_stays_byte_identical_on_crawler_shell():
    """The crawler-error signature is CITED-SPAN-ONLY: the retrieval-time ``is_access_denial_stub``
    must NOT see it, so its behaviour is byte-identical to pre-iter-2 (the patch invariant). ev_717
    (6639-char 404) is caught by the cited-span gate but NOT by the retrieval stub gate."""
    rows = _load_drb78_rows()
    body = rows["ev_717"]
    assert is_cited_span_shell(body) is True
    assert is_access_denial_stub(body) is False, (
        "retrieval gate changed — the crawler signature must be cited-span-only"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 4. Kill-switch — OFF reverts to byte-identical legacy behaviour.
# ─────────────────────────────────────────────────────────────────────────────


def test_off_switch_restores_legacy_behaviour(monkeypatch):
    monkeypatch.setenv("PG_CITED_SPAN_SHELL_DETECT", "0")
    sentence, pool = _grounded_sentence(RUN7_CAPTCHA_SPAN)
    result = verify_sentence_provenance(sentence, pool)
    # Pre-#1276 the verbatim-copied junk span verified on numeric/content overlap.
    assert result.is_verified is True
    assert not any(r.startswith("fetch_shell_cited_span") for r in result.failure_reasons)
