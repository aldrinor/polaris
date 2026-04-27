"""Tests for src/polaris_graph/audit_ir/template_classifier.py (M-10)."""

from __future__ import annotations

import pytest

from src.polaris_graph.audit_ir.template_classifier import (
    DEFAULT_FLOOR_HIGH,
    DEFAULT_FLOOR_REVIEW,
    RouterConfig,
    RoutingCandidate,
    RoutingResult,
    RoutingVerdict,
    classify_query,
)


# ---------------------------------------------------------------------------
# Verdict semantics — the Risk #13 mitigation in action
# ---------------------------------------------------------------------------


def test_empty_query_returns_unsupported() -> None:
    """Empty / whitespace-only queries must not throw — they return
    UNSUPPORTED with a helpful rationale so the UI shows the same
    scope-page CTA in every off-scope branch."""
    for q in ["", "   ", "\n\t  "]:
        r = classify_query(q)
        assert r.verdict == RoutingVerdict.UNSUPPORTED
        assert r.template_id is None
        assert r.confidence == 0.0
        assert "empty" in r.rationale.lower() or "scope" in r.rationale.lower()


def test_obvious_off_scope_returns_unsupported() -> None:
    """A clearly off-scope question (weather, sports, etc.) must
    not silently route to v30_clinical — that's the Risk #13
    failure mode."""
    for q in [
        "What's the weather today?",
        "Who won the World Series last year?",
        "How do I bake sourdough bread?",
        "Best Italian restaurants in NYC",
    ]:
        r = classify_query(q)
        assert r.verdict == RoutingVerdict.UNSUPPORTED, (
            f"off-scope query {q!r} routed as {r.verdict}"
        )


def test_true_positive_clinical_query_routed() -> None:
    """High-confidence clinical drug-condition questions must route
    to v30_clinical."""
    queries = [
        "What is the efficacy of tirzepatide for type 2 diabetes?",
        "Safety profile of semaglutide for obesity",
        "Studies on metformin for diabetes",
    ]
    for q in queries:
        r = classify_query(q)
        assert r.verdict == RoutingVerdict.ROUTED, (
            f"true-positive query {q!r} routed as {r.verdict} "
            f"(score {r.confidence:.2f}, rationale={r.rationale})"
        )
        assert r.template_id == "v30_clinical"
        assert r.confidence >= DEFAULT_FLOOR_HIGH


def test_medical_but_off_scope_goes_to_operator_review() -> None:
    """Off-scope-but-medical-sounding queries land in OPERATOR_REVIEW,
    not UNSUPPORTED. The operator can then decide whether to attempt
    the audit (since v30_clinical might still cover it after a
    reframe). Validates that medical framing alone isn't enough to
    auto-route."""
    r = classify_query("Treatment options for chronic pain")
    assert r.verdict == RoutingVerdict.OPERATOR_REVIEW, (
        f"medical-but-off-scope routed as {r.verdict} "
        f"(rationale={r.rationale})"
    )
    assert r.template_id == "v30_clinical"


def test_keyword_only_query_does_not_route_high() -> None:
    """Queries with clinical keywords but no exemplar match (e.g.
    'FDA drug trial') must NOT auto-route — they're too generic to
    guarantee an in-scope audit. Operator review required."""
    r = classify_query("FDA drug trial")
    assert r.verdict == RoutingVerdict.OPERATOR_REVIEW, (
        f"keyword-only query routed as {r.verdict} "
        f"(rationale={r.rationale})"
    )


# ---------------------------------------------------------------------------
# Score / verdict invariants
# ---------------------------------------------------------------------------


def test_confidence_bounded_in_unit_interval() -> None:
    """Confidence must always be in [0, 1] regardless of input."""
    queries = [
        "",
        "tirzepatide tirzepatide tirzepatide diabetes diabetes diabetes "
        "efficacy efficacy efficacy safety safety",
        "What is the efficacy of tirzepatide for type 2 diabetes?",
        "totally unrelated query about nothing in particular",
    ]
    for q in queries:
        r = classify_query(q)
        assert 0.0 <= r.confidence <= 1.0, (
            f"confidence {r.confidence} out of bounds for query {q!r}"
        )
        for c in r.candidates:
            assert 0.0 <= c.score <= 1.0


def test_routing_is_deterministic() -> None:
    """Same query → same verdict + same confidence on every call."""
    q = "What is the efficacy of tirzepatide for type 2 diabetes?"
    r1 = classify_query(q)
    r2 = classify_query(q)
    r3 = classify_query(q)
    assert r1.verdict == r2.verdict == r3.verdict
    assert r1.template_id == r2.template_id == r3.template_id
    assert r1.confidence == r2.confidence == r3.confidence


def test_candidates_sorted_by_score_descending() -> None:
    r = classify_query("Studies on metformin for diabetes")
    scores = [c.score for c in r.candidates]
    assert scores == sorted(scores, reverse=True)


def test_routed_verdict_has_template_id() -> None:
    """Sanity: ROUTED must include a template_id; UNSUPPORTED must not."""
    r_routed = classify_query(
        "What is the efficacy of tirzepatide for type 2 diabetes?"
    )
    assert r_routed.verdict == RoutingVerdict.ROUTED
    assert r_routed.template_id is not None

    r_unsup = classify_query("What's the weather?")
    assert r_unsup.verdict == RoutingVerdict.UNSUPPORTED
    assert r_unsup.template_id is None


def test_rationale_is_human_readable() -> None:
    r = classify_query("tirzepatide for diabetes")
    assert isinstance(r.rationale, str)
    assert len(r.rationale) >= 20
    # Score values should be in the rationale so operators can
    # debug routing decisions from logs.
    assert any(c.isdigit() for c in r.rationale)


# ---------------------------------------------------------------------------
# Threshold env-overrides (LAW VI)
# ---------------------------------------------------------------------------


def test_router_config_from_env_uses_defaults_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("PG_TEMPLATE_ROUTER_FLOOR_HIGH", raising=False)
    monkeypatch.delenv("PG_TEMPLATE_ROUTER_FLOOR_REVIEW", raising=False)
    cfg = RouterConfig.from_env()
    assert cfg.floor_high == DEFAULT_FLOOR_HIGH
    assert cfg.floor_review == DEFAULT_FLOOR_REVIEW


def test_router_config_from_env_reads_overrides(monkeypatch) -> None:
    monkeypatch.setenv("PG_TEMPLATE_ROUTER_FLOOR_HIGH", "0.80")
    monkeypatch.setenv("PG_TEMPLATE_ROUTER_FLOOR_REVIEW", "0.20")
    cfg = RouterConfig.from_env()
    assert cfg.floor_high == 0.80
    assert cfg.floor_review == 0.20


def test_router_config_clamps_invalid_floors(monkeypatch) -> None:
    """If review_floor >= high_floor, clamp review to high (so the
    review band collapses but never inverts)."""
    monkeypatch.setenv("PG_TEMPLATE_ROUTER_FLOOR_HIGH", "0.50")
    monkeypatch.setenv("PG_TEMPLATE_ROUTER_FLOOR_REVIEW", "0.90")
    cfg = RouterConfig.from_env()
    assert cfg.floor_review <= cfg.floor_high


def test_router_config_handles_garbage_env(monkeypatch) -> None:
    """Garbage env values fall back to defaults rather than crashing."""
    monkeypatch.setenv("PG_TEMPLATE_ROUTER_FLOOR_HIGH", "not_a_float")
    monkeypatch.setenv("PG_TEMPLATE_ROUTER_FLOOR_REVIEW", "also_garbage")
    cfg = RouterConfig.from_env()
    assert cfg.floor_high == DEFAULT_FLOOR_HIGH
    assert cfg.floor_review == DEFAULT_FLOOR_REVIEW


def test_threshold_overrides_change_verdict(monkeypatch) -> None:
    """When floor_high is raised above a query's natural score,
    that query downgrades from ROUTED to OPERATOR_REVIEW."""
    q = "What is the efficacy of tirzepatide for type 2 diabetes?"
    natural = classify_query(q)
    assert natural.verdict == RoutingVerdict.ROUTED

    # Raise floor_high above the natural score.
    raised = RouterConfig(floor_high=natural.confidence + 0.05, floor_review=0.20)
    downgraded = classify_query(q, config=raised)
    assert downgraded.verdict == RoutingVerdict.OPERATOR_REVIEW
    assert downgraded.confidence == natural.confidence


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_query_with_only_punctuation_returns_unsupported() -> None:
    r = classify_query("???!!!")
    assert r.verdict == RoutingVerdict.UNSUPPORTED


def test_query_with_html_or_unicode_does_not_crash() -> None:
    """Defensive: garbage input doesn't crash the classifier."""
    weird = [
        "<script>alert('xss')</script>",
        "Café résumé naïve coöperate",
        "数据 关于 药物 治疗",
        "tirzepatide\x00diabetes",
    ]
    for q in weird:
        r = classify_query(q)
        assert isinstance(r, RoutingResult)
        assert isinstance(r.verdict, RoutingVerdict)


def test_candidates_for_unsupported_still_present() -> None:
    """Even when the verdict is UNSUPPORTED, candidates list is
    populated so the UI can show 'closest match' info if useful."""
    r = classify_query("What's the weather?")
    assert len(r.candidates) >= 1
    assert all(isinstance(c, RoutingCandidate) for c in r.candidates)


# ---------------------------------------------------------------------------
# Codex M-10 review regression: false-positive bypasses where the
# query mimics an exemplar's question scaffold but is off-scope
# (non-pharmaceutical interventions, supplements, generic medical
# queries). v1 routed all four of these as ROUTED with confidence
# > 0.6; v2 must surface them as OPERATOR_REVIEW at most.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        # Non-regulated intervention with a real-shape exemplar match.
        "Safety profile of ibuprofen for back pain",
        "What is the efficacy of turmeric for arthritis?",
        "FDA approval pathway for new supplements",
        "Meta-analysis of psychotherapy in depression",
        # Additional non-drug interventions / supplements.
        "Efficacy of vitamin D supplementation for autoimmune disease",
        "Acupuncture for chronic migraine prevention",
        "Cognitive behavioral therapy for anxiety disorders",
        "Curcumin anti-inflammatory effects in osteoarthritis",
        # Wellness / non-clinical.
        "Mediterranean diet for cardiovascular health",
        "Yoga benefits for back pain",
        # Codex M-10 v2 review regression: umbrella drug-class terms
        # without a specific named drug must not auto-route.
        "Phase 3 trial of biologic for psoriasis",
        "Phase 3 trial of biosimilar for rheumatoid arthritis",
        "Phase 3 trial of monoclonal antibody for eczema",
        "Phase 3 trial of receptor agonist for dermatitis",
        "Meta-analysis of biologics in inflammatory bowel disease",
        "Adverse events of monoclonal antibodies in oncology",
        # Codex M-10 v3 review regression: real drug + scaffold-shape
        # + nonsense suffix bypass. Alien-token gate must catch these.
        "Dulaglutide phase 3 trial outcomes for video game addiction",
        "Atorvastatin efficacy for engine lubrication",
        "Empagliflozin cardiovascular outcomes meta-analysis in server uptime",
        "Cardiovascular safety of GLP-1 receptor agonists for printer firmware",
        "Tirzepatide efficacy for Java compilation errors",
        "Metformin phase 3 trial outcomes for blockchain governance",
        # Codex M-10 v4 review regression: single-alien-token bypass.
        # alien_max=0 must reject these; previously alien<=1 let them
        # route at confidence 0.70-0.95.
        "tirzepatide for diabetes pleasingly",
        "tirzepatide for diabetes printer",
        "dulaglutide phase 3 trial outcomes for type 2 diabetes printer",
        "empagliflozin cardiovascular outcomes meta-analysis in adults with chronic kidney disease and heart failure printer",
        "metformin for type 2 diabetes alongside cryptocurrency",
        "GLP-1 receptor agonists for cardiovascular outcomes wherever",
    ],
)
def test_off_scope_with_exemplar_shape_does_not_route(query: str) -> None:
    """Codex M-10 review regression. Without the drug-keyword gate,
    these all auto-routed because they mimic exemplar scaffold. After
    the v2 fix, none must be ROUTED."""
    r = classify_query(query)
    assert r.verdict != RoutingVerdict.ROUTED, (
        f"off-scope query {query!r} routed with score {r.confidence:.2f} "
        f"and rationale {r.rationale!r}"
    )


def test_every_scope_example_self_routes() -> None:
    """Codex M-10 v4 invariant: every scope_example in the catalog
    must route at confidence ≥ floor_high when submitted as a query.
    Catches vocabulary gaps where an exemplar uses a word that isn't
    in drug_keywords or medical_keywords (so it would be alien)."""
    from src.polaris_graph.audit_ir.template_catalog import list_catalog
    for tmpl in list_catalog():
        for ex in tmpl.scope_examples:
            r = classify_query(ex)
            assert r.verdict == RoutingVerdict.ROUTED, (
                f"scope_example {ex!r} for template {tmpl.template_id} "
                f"failed self-routing: verdict={r.verdict.value}, "
                f"score={r.confidence:.2f}, rationale={r.rationale}"
            )


def test_routed_requires_drug_keyword_hit() -> None:
    """Codex M-10 invariant: ROUTED implies at least one drug_keyword
    hit. The verdict should never rise to ROUTED from medical/
    regulatory keywords + exemplar overlap alone."""
    routed_queries = [
        "What is the efficacy of tirzepatide for type 2 diabetes?",
        "Safety profile of semaglutide for obesity",
        "Studies on metformin for diabetes",
        "Cardiovascular safety of GLP-1 receptor agonists",
        "Empagliflozin cardiovascular outcomes meta-analysis",
    ]
    for q in routed_queries:
        r = classify_query(q)
        assert r.verdict == RoutingVerdict.ROUTED, (
            f"true-positive query {q!r} did not route "
            f"(score {r.confidence:.2f}, rationale={r.rationale})"
        )
        # Top candidate must have at least one drug hit.
        top = r.candidates[0]
        assert len(top.drug_hits) >= 1, (
            f"routed query {q!r} has no drug hits (only medical_hits "
            f"{top.medical_hits}); ROUTED gate violated"
        )


def test_drug_hit_alone_does_not_route_without_jaccard() -> None:
    """A drug name without an exemplar-aligned shape stays in
    OPERATOR_REVIEW (operator decides whether the query can be
    reframed)."""
    r = classify_query("tirzepatide weather forecast")
    assert r.verdict == RoutingVerdict.OPERATOR_REVIEW, (
        f"drug-name-only off-shape query routed as {r.verdict} "
        f"(rationale={r.rationale})"
    )


def test_unicode_hyphen_normalized_in_drug_class_match() -> None:
    """Codex M-10 review fix: copied text like 'GLP‑1' (U+2011
    non-breaking hyphen) must match the same as 'GLP-1' (ASCII).
    Without normalization, copy-pasted PDF text wouldn't trigger
    the drug-class hit."""
    ascii_q = "Cardiovascular safety of GLP-1 receptor agonists"
    nbsp_q = "Cardiovascular safety of GLP‑1 receptor agonists"
    endash_q = "Cardiovascular safety of GLP–1 receptor agonists"
    r_ascii = classify_query(ascii_q)
    r_nbsp = classify_query(nbsp_q)
    r_endash = classify_query(endash_q)
    assert r_ascii.verdict == r_nbsp.verdict == r_endash.verdict
    assert r_ascii.confidence == r_nbsp.confidence == r_endash.confidence


@pytest.mark.parametrize(
    "query",
    [
        # Codex M-10 v6 review regression: hyphen-joined compound
        # modifiers must match the same as space-separated forms.
        "Dulaglutide phase-3 trial outcomes for type 2 diabetes",
        "Dulaglutide phase 3 trial outcomes for type-2 diabetes",
        "Empagliflozin renal composite outcomes in chronic-kidney disease patients",
        "Phase-3 trial of metformin for type-2 diabetes",
        "Type-2 diabetes management with semaglutide",
        # Drug class with optional hyphen (already worked via single
        # canonical form but verify with split).
        "GLP-1 receptor agonists for cardiovascular outcomes",
        # Codex M-10 v7 review regression: Roman-numeral and compact
        # drug-class orthography common in clinical literature.
        "Dulaglutide phase III trial outcomes for type 2 diabetes",
        "Dulaglutide phase 3 trial outcomes for type II diabetes",
        "GLP1 agonists for type 2 diabetes",
        "DPP4 inhibitors for type 2 diabetes",
        "Phase IV trial of empagliflozin in heart failure",
    ],
)
def test_hyphen_compound_orthography_routes(query: str) -> None:
    """Codex M-10 v6 fix: hyphen-joined compound forms ('phase-3',
    'type-2') tokenize the same as space-separated forms after the
    tokenizer's hyphen split."""
    r = classify_query(query)
    assert r.verdict == RoutingVerdict.ROUTED, (
        f"hyphen-compound query {query!r} did not route "
        f"(score {r.confidence:.2f}, rationale={r.rationale})"
    )


def test_renal_composite_outcomes_query_routes() -> None:
    """Codex M-10 v5 review regression: vocab gap. The query
    "empagliflozin renal composite outcomes in chronic kidney
    disease patients" was operator_review at 0.45 because
    'composite' tagged as alien. After adding it to the catalog
    the query routes."""
    r = classify_query(
        "empagliflozin renal composite outcomes in chronic kidney disease patients"
    )
    assert r.verdict == RoutingVerdict.ROUTED, (
        f"got {r.verdict.value} (score {r.confidence:.2f}, "
        f"rationale={r.rationale})"
    )


def test_multiword_keyword_does_not_cross_hit() -> None:
    """Codex M-10 v5 review fix: the multi-word keyword 'phase 2'
    must NOT match a query that contains 'phase 3' + 'type 2
    diabetes'. Set-based subset matching saw {phase, 2} as a subset
    of the query's tokens; the new ordered-subsequence check
    requires the keyword's tokens to appear contiguously.
    """
    from src.polaris_graph.audit_ir.template_classifier import (
        _keyword_hits,
        _tokenize_raw,
        _tokenize_raw_seq,
    )
    q = "Phase 3 trial of monoclonal antibody for type 2 diabetes"
    qset = _tokenize_raw(q)
    qseq = _tokenize_raw_seq(q)
    hits = _keyword_hits(qset, qseq, ("phase 2", "phase 3"))
    assert "phase 3" in hits, "phase 3 should match (it's contiguous in the query)"
    assert "phase 2" not in hits, (
        "phase 2 should NOT match — its tokens are present but not contiguous"
    )


def test_multiword_type_diabetes_cross_hit_blocked() -> None:
    """Companion to test_multiword_keyword_does_not_cross_hit:
    'type 1 diabetes' must NOT match a query that contains 'type
    2 diabetes' + 'phase 1' even though tokens {type, 1, diabetes}
    are all individually present."""
    from src.polaris_graph.audit_ir.template_classifier import (
        _keyword_hits,
        _tokenize_raw,
        _tokenize_raw_seq,
    )
    q = "Phase 1 trial of metformin for type 2 diabetes"
    qset = _tokenize_raw(q)
    qseq = _tokenize_raw_seq(q)
    hits = _keyword_hits(
        qset, qseq, ("type 1 diabetes", "type 2 diabetes", "phase 1")
    )
    assert "type 2 diabetes" in hits
    assert "phase 1" in hits
    assert "type 1 diabetes" not in hits, (
        "type 1 diabetes should NOT match — tokens present but not contiguous"
    )


def test_stopword_filter_disables_scaffold_jaccard() -> None:
    """Codex M-10 review fix: a query that shares only stopwords
    with an exemplar must score 0 on Jaccard. Without filtering,
    'What is the efficacy of X for Y?' shapes inflate jaccard from
    {what, is, the, of, for} alone."""
    # All scaffold-only-overlap with an exemplar.
    r = classify_query("What is the something of nothing for somewhere?")
    assert r.verdict in {
        RoutingVerdict.UNSUPPORTED,
        RoutingVerdict.OPERATOR_REVIEW,
    }, f"got {r.verdict}"
    assert r.confidence < DEFAULT_FLOOR_HIGH, (
        f"scaffold-only query reached confidence {r.confidence:.2f}"
    )


# ---------------------------------------------------------------------------
# Codex M-20 phase-c: tie detection (top-1 vs top-2 narrow-gap demotion).
# When the catalog grows past one template, multiple drug-anchored
# templates may both score above floor_high for the same query
# (e.g. tirzepatide hits a diabetes-specific AND an obesity-specific
# template). Tie detection demotes those queries to OPERATOR_REVIEW
# so the operator picks the right template instead of the router
# silently picking the alphabetically-first one.
# ---------------------------------------------------------------------------


def _make_template(
    template_id: str,
    drugs: tuple[str, ...] = ("druga",),
    medical: tuple[str, ...] = ("efficacy", "diabetes", "trial"),
    examples: tuple[str, ...] = ("druga efficacy in diabetes trial",),
) -> "CuratedTemplate":
    """Build a CuratedTemplate stub for tie-detection tests."""
    from src.polaris_graph.audit_ir.template_catalog import CuratedTemplate
    return CuratedTemplate(
        template_id=template_id,
        display_name=template_id.replace("_", " ").title(),
        description="test stub",
        scope_summary="test stub scope",
        drug_keywords=drugs,
        medical_keywords=medical,
        scope_examples=examples,
    )


def test_tie_detection_demotes_when_top_two_within_margin(monkeypatch) -> None:
    """Two templates score identically (gap == 0 < tie_margin) on a
    query that fits both. Verdict demotes from ROUTED → OPERATOR_REVIEW
    so the operator picks the correct template."""
    tmpl_a = _make_template(template_id="test_template_a")
    tmpl_b = _make_template(template_id="test_template_b")

    monkeypatch.setattr(
        "src.polaris_graph.audit_ir.template_classifier.list_catalog",
        lambda: (tmpl_a, tmpl_b),
    )

    r = classify_query("druga efficacy in diabetes trial")
    assert r.verdict == RoutingVerdict.OPERATOR_REVIEW, (
        f"identical-score top-2 should demote to operator_review, "
        f"got {r.verdict}; rationale={r.rationale!r}"
    )
    rationale_lc = r.rationale.lower()
    assert (
        "multiple templates" in rationale_lc
        or "narrow gap" in rationale_lc
        or "tie" in rationale_lc
    ), f"tie-demotion rationale should explain the tie: {r.rationale!r}"


def test_tie_detection_does_not_fire_when_top2_below_floor_high(
    monkeypatch,
) -> None:
    """If top-2 falls below floor_high, the gap-margin doesn't
    matter — only top-1 is a viable target, ROUTED is correct."""
    # Template A: query matches its exemplar exactly → score ~1.0.
    # Template B: shares the drug but exemplar shape differs → ex_jac
    # below 0.30 → falls to Tier B (drug named, no exemplar match) →
    # score 0.40-0.45 (below floor_high 0.55).
    tmpl_a = _make_template(
        template_id="test_template_a",
        drugs=("druga",),
        medical=("efficacy", "diabetes", "trial"),
        examples=("druga efficacy in diabetes trial",),
    )
    tmpl_b = _make_template(
        template_id="test_template_b",
        drugs=("druga",),
        medical=("safety", "obesity", "phase"),
        # Exemplar shape doesn't match the test query at all.
        examples=("druga safety in obesity phase",),
    )

    monkeypatch.setattr(
        "src.polaris_graph.audit_ir.template_classifier.list_catalog",
        lambda: (tmpl_a, tmpl_b),
    )

    r = classify_query("druga efficacy in diabetes trial")
    assert r.verdict == RoutingVerdict.ROUTED, (
        f"only top-1 above floor_high should route normally, got "
        f"{r.verdict}; rationale={r.rationale!r}"
    )
    assert r.template_id == "test_template_a"


def test_tie_detection_does_not_fire_when_gap_exceeds_margin(
    monkeypatch,
) -> None:
    """When gap >= tie_margin, top-1 wins outright — no demotion."""
    # Both templates cover the same medical vocabulary so neither
    # has alien tokens. Different exemplars produce different
    # example_jaccard scores, putting both above floor_high but
    # with a clear gap.
    shared_medical = ("efficacy", "diabetes", "obesity", "trial", "phase")
    tmpl_a = _make_template(
        template_id="test_template_a",
        drugs=("druga",),
        medical=shared_medical,
        # Exact match with the query → ex_jac=1.0, score=1.0.
        examples=("druga efficacy in diabetes trial phase",),
    )
    tmpl_b = _make_template(
        template_id="test_template_b",
        drugs=("druga",),
        medical=shared_medical,
        # Shares druga/efficacy/trial/phase with query (4 of 5
        # content words) but swaps diabetes → obesity. ex_jac ≈
        # 4/6 ≈ 0.67, score ≈ 0.55 + 0.45*0.67 ≈ 0.85.
        examples=("druga efficacy in obesity trial phase",),
    )

    monkeypatch.setattr(
        "src.polaris_graph.audit_ir.template_classifier.list_catalog",
        lambda: (tmpl_a, tmpl_b),
    )

    # tie_margin tightened to 0.05 so the natural ~0.15 gap clears it.
    monkeypatch.setenv("PG_TEMPLATE_ROUTER_TIE_MARGIN", "0.05")

    r = classify_query("druga efficacy in diabetes trial phase")
    assert r.verdict == RoutingVerdict.ROUTED, (
        f"clear gap should ROUTE on top-1, got {r.verdict}; "
        f"top-1 score={r.candidates[0].score:.3f}, "
        f"top-2 score={r.candidates[1].score:.3f}; "
        f"rationale={r.rationale!r}"
    )
    assert r.template_id == "test_template_a"
    # Sanity check: gap is wider than tie_margin used in this test.
    gap = r.candidates[0].score - r.candidates[1].score
    assert gap > 0.05, f"gap={gap:.3f} should exceed tie_margin=0.05"


def test_tie_margin_env_overridable(monkeypatch) -> None:
    """LAW VI: tie_margin must be overridable via env var."""
    monkeypatch.setenv("PG_TEMPLATE_ROUTER_TIE_MARGIN", "0.25")
    cfg = RouterConfig.from_env()
    assert cfg.tie_margin == 0.25

    monkeypatch.delenv("PG_TEMPLATE_ROUTER_TIE_MARGIN", raising=False)
    cfg2 = RouterConfig.from_env()
    # Default falls back to DEFAULT_TIE_MARGIN.
    from src.polaris_graph.audit_ir.template_classifier import (
        DEFAULT_TIE_MARGIN,
    )
    assert cfg2.tie_margin == DEFAULT_TIE_MARGIN


def test_tie_margin_garbage_env_falls_back_to_default(monkeypatch) -> None:
    """Garbage env values for tie_margin must not crash — fall back."""
    monkeypatch.setenv("PG_TEMPLATE_ROUTER_TIE_MARGIN", "not_a_float")
    cfg = RouterConfig.from_env()
    from src.polaris_graph.audit_ir.template_classifier import (
        DEFAULT_TIE_MARGIN,
    )
    assert cfg.tie_margin == DEFAULT_TIE_MARGIN


def test_real_catalog_has_no_unexpected_ties() -> None:
    """Smoke test: each template's own scope_examples must self-route
    decisively (no false ties surfacing as OPERATOR_REVIEW). This is
    a stricter version of test_every_scope_example_self_routes — it
    also asserts the router doesn't fire tie-detection on these
    examples by accident."""
    from src.polaris_graph.audit_ir.template_catalog import list_catalog
    for tmpl in list_catalog():
        for ex in tmpl.scope_examples:
            r = classify_query(ex)
            # Self-routing must succeed (covered by other test) but
            # ALSO not surface "Multiple templates" rationale — that
            # would mean two real templates accidentally collide.
            if r.verdict == RoutingVerdict.OPERATOR_REVIEW:
                assert "multiple templates" not in r.rationale.lower(), (
                    f"template {tmpl.template_id!r} exemplar "
                    f"{ex!r} accidentally ties with another template; "
                    f"add disambiguating keywords or examples. "
                    f"rationale={r.rationale!r}"
                )
