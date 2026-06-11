"""I-perm-004 (#1198) span resolver — keystone unit tests (pure, stub judge).

Covers the deterministic boilerplate classifier and the entailing-span ARGMAX. The §-1.1-lethal
risk is MANUFACTURING support, so the binding assertions are: the resolver returns ONLY a span the
injected judge accepted; a boilerplate-only support yields a LABELED low-confidence result (never a
silent high); and the argmax prefers real prose over a co-entailing title (the drb_76 "re-anchored
to the TITLE" bug).
"""

from __future__ import annotations

from src.polaris_graph.generator import span_resolver as sr


# --- classify_span -------------------------------------------------------------------------


def test_classify_prose():
    assert (
        sr.classify_span(
            "Probiotic use was strongly associated with Saccharomyces fungemia in immunocompromised "
            "patients across five hospitals."
        )
        == sr.QUALITY_PROSE
    )


def test_classify_boilerplate_buckets():
    assert sr.classify_span("https://doi.org/10.3201/eid2708.210018 full text") == sr.QUALITY_URL
    assert sr.classify_span("Altmetric: tweeted by 42, 18 Mendeley readers") == sr.QUALITY_ALTMETRIC
    assert sr.classify_span("[12] Smith J, et al. (2021) doi:10.1056/x pp. 22-30") == sr.QUALITY_REFERENCE_LIST
    assert sr.classify_span("Department of Microbiology, University of Helsinki") == sr.QUALITY_AFFILIATION
    assert sr.classify_span("Skip to main content") == sr.QUALITY_NAV_LINK
    # Codex slice-1 P2: pipe-separated link bar + keyword chrome must be nav (not prose@conf-1.0).
    assert (
        sr.classify_span("home | articles | current issue | archives | about the journal | submit manuscript.")
        == sr.QUALITY_NAV_LINK
    )
    assert (
        sr.classify_span(
            "www.example.com current issue archive author guidelines submit manuscript editorial board contact us."
        )
        == sr.QUALITY_NAV_LINK
    )
    # short, terminator-free, title-case -> title; trailing-colon / very short -> header
    assert sr.classify_span("Saccharomyces boulardii Fungemia and Probiotic Safety") == sr.QUALITY_TITLE
    assert sr.classify_span("Methods:") == sr.QUALITY_HEADER
    assert sr.is_boilerplate_quality(sr.QUALITY_TITLE)
    assert not sr.is_boilerplate_quality(sr.QUALITY_PROSE)


# --- resolve_best_entailing_span -----------------------------------------------------------

# A row whose TITLE (chars 0..52) lexically resembles the claim but a later PROSE span (chars ~120+)
# actually entails it — the drb_76 "re-anchored to the title" shape.
_TITLE = "Saccharomyces boulardii Fungemia: A Probiotic Safety Concern. "
_PROSE = (
    "The registry study found that boulardii probiotic use was strongly associated with fungemia "
    "in immunocompromised patients compared with controls. "
)
_BADGE = "Altmetric badge: tweeted by 31 accounts; 12 Mendeley readers."
_ROW = _TITLE + _PROSE + _BADGE
_CLAIM = "Boulardii probiotic use was strongly associated with fungemia in immunocompromised patients."

_TITLE_SPAN = (0, len(_TITLE))
_PROSE_SPAN = (len(_TITLE), len(_TITLE) + len(_PROSE))
_BADGE_SPAN = (len(_TITLE) + len(_PROSE), len(_ROW))


def _judge_only(*entailing_texts):
    """A stub judge that entails iff the span text is one of the given (stripped) texts."""
    targets = {t.strip() for t in entailing_texts}
    calls = {"n": 0}

    def judge(sentence: str, span_text: str) -> bool:
        calls["n"] += 1
        return span_text.strip() in targets

    judge.calls = calls  # type: ignore[attr-defined]
    return judge


def test_picks_entailing_prose_over_lexical_title():
    # Judge entails ONLY the prose span (the title does not actually support the claim).
    judge = _judge_only(_PROSE)
    res = sr.resolve_best_entailing_span(
        _ROW, _CLAIM, [_TITLE_SPAN, _PROSE_SPAN, _BADGE_SPAN], judge_fn=judge
    )
    assert res is not None
    assert res.best_span == _PROSE_SPAN
    assert res.provenance_quality == sr.QUALITY_PROSE
    assert res.confidence >= 0.7  # prose-entailed -> moderate/high


def test_argmax_prefers_prose_when_both_entail():
    # Even if BOTH title and prose entail, the argmax must pick prose (higher quality).
    judge = _judge_only(_TITLE, _PROSE)
    res = sr.resolve_best_entailing_span(
        _ROW, _CLAIM, [_TITLE_SPAN, _PROSE_SPAN, _BADGE_SPAN], judge_fn=judge
    )
    assert res is not None
    assert res.provenance_quality == sr.QUALITY_PROSE
    assert res.best_span == _PROSE_SPAN


def test_title_only_support_is_labeled_low_not_silent_high():
    # When ONLY the title entails, the claim is recovered but LABELED low-confidence boilerplate.
    judge = _judge_only(_TITLE)
    res = sr.resolve_best_entailing_span(
        _ROW, _CLAIM, [_TITLE_SPAN, _PROSE_SPAN, _BADGE_SPAN], judge_fn=judge
    )
    assert res is not None
    assert res.provenance_quality == sr.QUALITY_TITLE
    assert sr.is_boilerplate_quality(res.provenance_quality)
    assert res.confidence < 0.6  # never reads as high


def test_returns_none_when_nothing_entails():
    judge = _judge_only()  # entails nothing
    res = sr.resolve_best_entailing_span(
        _ROW, _CLAIM, [_TITLE_SPAN, _PROSE_SPAN, _BADGE_SPAN], judge_fn=judge
    )
    assert res is None


def test_only_returns_a_judge_accepted_span():
    # The badge span lexically shares "probiotic"/"fungemia"-ish tokens but the judge rejects it;
    # it must NEVER be returned (no manufactured support).
    judge = _judge_only(_BADGE)  # pretend only the badge "entails"
    res = sr.resolve_best_entailing_span(
        _ROW, _CLAIM, [_TITLE_SPAN, _PROSE_SPAN, _BADGE_SPAN], judge_fn=judge
    )
    assert res is not None and res.best_span == _BADGE_SPAN  # judge is the gate; resolver obeys it
    # ...and conversely, with the badge rejected it is never chosen:
    judge2 = _judge_only(_PROSE)
    res2 = sr.resolve_best_entailing_span(
        _ROW, _CLAIM, [_TITLE_SPAN, _PROSE_SPAN, _BADGE_SPAN], judge_fn=judge2
    )
    assert res2 is not None and res2.best_span != _BADGE_SPAN


def test_judge_calls_bounded_by_top_k():
    judge = _judge_only(_PROSE)
    many_spans = [(i, i + 30) for i in range(0, len(_ROW) - 30, 5)]
    sr.resolve_best_entailing_span(_ROW, _CLAIM, many_spans, judge_fn=judge, top_k=4)
    assert judge.calls["n"] <= 4  # type: ignore[attr-defined]


def test_numeric_mismatch_lowers_confidence():
    claim = "The risk rose by 58 percent in immunocompromised patients."
    span_match = "the risk rose by 58 percent in immunocompromised patients in the cohort study analysis"
    span_nomatch = "the risk rose substantially in immunocompromised patients in the cohort study analysis"
    row = span_match + " || " + span_nomatch
    s1 = (0, len(span_match))
    s2 = (len(span_match) + 4, len(row))

    def numeric_match(sentence: str, span_text: str) -> bool:
        return "58" in span_text

    judge = _judge_only(span_nomatch)  # only the no-number span entails
    res = sr.resolve_best_entailing_span(
        row, claim, [s1, s2], judge_fn=judge, numeric_match_fn=numeric_match
    )
    assert res is not None
    # numeric mismatch penalised -> below the no-penalty prose baseline.
    assert res.confidence < 1.0
