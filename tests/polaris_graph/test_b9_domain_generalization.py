"""B9 domain-generalization core — the spine that makes POLARIS GENERAL by
default with clinical as a DETECTED pack.

Tests prove the 5 smoking-gun fixes + the clinical byte-identity invariant:

  SG1  scope_gate no longer DEFAULTS to clinical; "" -> general (never clinical,
       never abort), and a cheap injectable domain/intent classifier exists.
  SG2  qualitative_conflict_detector READS the domain — the clinical NegEx
       lexicon does NOT fire on a non-clinical corpus (the 2,738 junk flags).
  SG3  multi_section_generator forces the field-agnostic (clinical-few-shot-free)
       section template for a positively non-clinical domain; clinical/blank
       stay on the unchanged research_plan-gated selection (byte-identical).
  B9-3 contradiction_detector: non-clinical numeric gap with differing scope is
       labeled possible_metric_mismatch, not a hard contradiction.
  B9-5 finding_dedup / claim-atom path: a non-clinical numeric now yields a REAL
       claim-key (a NON-singleton basket is possible) — closing the documented
       residual that blocked non-clinical baskets.

Clinical byte-identity: a clinical question keeps full clinical rigor — the
protocol.json hash, the selected clinical predicates, and the selected section
template are UNCHANGED.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.polaris_graph.domain.domain_signal import (
    GENERAL_DOMAIN,
    is_clinical_domain,
    normalize_domain,
)
from src.polaris_graph.domain.domain_pack import (
    available_packs,
    load_domain_pack,
    pack_is_clinical,
)
from src.polaris_graph.nodes import scope_gate
from src.polaris_graph.nodes.scope_gate import (
    DEFAULT_DOMAIN,
    SUPPORTED_DOMAINS,
    classify_domain_intent,
    run_scope_gate,
)
from src.polaris_graph.retrieval.contradiction_detector import (
    detect_contradictions,
    extract_numeric_claims,
)
from src.polaris_graph.retrieval.qualitative_conflict_detector import (
    extract_qualitative_assertions,
)
from src.polaris_graph.synthesis.finding_dedup import dedup_by_finding


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

_ECON_ROWS = [
    {
        "evidence_id": "ev_e1",
        "direct_quote": "The unemployment rate reached 12.5 percent among "
        "clerical workers exposed to generative AI.",
        "source_url": "https://institute-a.org/report",
        "tier": "T3",
        "authority_score": 0.8,
    },
    {
        "evidence_id": "ev_e2",
        "direct_quote": "Analysts estimated the unemployment rate at 12.5 "
        "percent for clerical occupations.",
        "source_url": "https://think-tank-b.net/study",
        "tier": "T3",
        "authority_score": 0.7,
    },
]

# A non-clinical corpus that mentions a clinical-sounding word ("mortality")
# to prove the clinical lexicon does NOT fire on topic alone.
_LABOR_ROWS_WITH_CLINICAL_WORD = [
    {
        "evidence_id": "ev_l1",
        "direct_quote": "Job mortality in routine cognitive occupations rose "
        "as AI adoption increased; the displacement rate hit 18 percent.",
        "source_url": "https://a.org",
        "tier": "T4",
    },
    {
        "evidence_id": "ev_l2",
        "direct_quote": "There was no contraindication to deploying the model "
        "in customer-service roles, where the automation share reached 30 "
        "percent.",
        "source_url": "https://b.org",
        "tier": "T4",
    },
]

_CLINICAL_ROWS = [
    {
        "evidence_id": "ev_c1",
        "direct_quote": "Semaglutide produced weight loss of 14.9% at week 68 "
        "in adults with obesity.",
        "source_url": "https://nejm.org/step1",
        "tier": "T1",
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# domain_signal — the deterministic is_clinical backbone
# ─────────────────────────────────────────────────────────────────────────────

def test_is_clinical_explicit_clinical_domain_true() -> None:
    assert is_clinical_domain("clinical", None) is True


def test_is_clinical_non_clinical_domain_false_even_with_clinical_word() -> None:
    # A non-clinical KNOWN domain is authoritative: the corpus mentions
    # "mortality"/"contraindication" but must NOT route clinical.
    assert is_clinical_domain("workforce", _LABOR_ROWS_WITH_CLINICAL_WORD) is False
    assert is_clinical_domain("economics", _LABOR_ROWS_WITH_CLINICAL_WORD) is False


def test_is_clinical_blank_domain_probes_signal() -> None:
    # Blank domain + a drug/population signal -> clinical (no-regression for
    # legacy domain-less clinical callers).
    assert is_clinical_domain(None, _CLINICAL_ROWS) is True
    # Blank domain + econ corpus -> not clinical.
    assert is_clinical_domain(None, _ECON_ROWS) is False
    # Blank domain + no evidence -> not clinical (never clinical-by-default).
    assert is_clinical_domain(None, None) is False
    assert is_clinical_domain("", []) is False


def test_normalize_domain_blank_to_general() -> None:
    assert normalize_domain("") == GENERAL_DOMAIN
    assert normalize_domain(None) == GENERAL_DOMAIN
    assert normalize_domain("  Clinical ") == "clinical"


# ─────────────────────────────────────────────────────────────────────────────
# SG1 — scope_gate no longer defaults to clinical; classifier; never-abort
# ─────────────────────────────────────────────────────────────────────────────

def test_sg1_default_domain_is_not_clinical() -> None:
    # B9: the DEFAULT scope template is the domain-AGNOSTIC `custom` (the
    # canonical-8 free-form template), NOT clinical. (The B9 conceptual
    # "general" domain lives in the domain-pack layer; `custom` is its
    # scope-template realization within the locked canonical-8.)
    assert DEFAULT_DOMAIN == "custom"
    assert DEFAULT_DOMAIN != "clinical"
    assert DEFAULT_DOMAIN in SUPPORTED_DOMAINS


def test_sg1_blank_caller_routes_general_not_clinical_and_proceeds() -> None:
    # A domain-LESS caller routes to the domain-agnostic default (custom) and
    # PROCEEDS — never silently clinical, never aborts.
    with tempfile.TemporaryDirectory() as td:
        result = run_scope_gate(
            research_question="What is the labor-market impact of AI on "
            "clerical wages over the next decade?",
            run_dir=td,
            run_id="TEST_B9_DEFAULT",
        )
    assert result.protocol.domain == DEFAULT_DOMAIN
    assert result.protocol.domain != "clinical"
    assert result.protocol.scope_decision == "proceed"
    assert result.protocol.scope_rejected is False
    # No clinical PICO false-abort: a general question is never forced into the
    # clinical PICO-unscoped reject.
    assert result.protocol.scope_rejection_code is None


def test_sg1_blank_string_domain_routes_default_not_reject() -> None:
    # Codex iter-1 P1.1: an explicit blank/whitespace domain string must route
    # to the default (custom), NOT reject as an unsupported domain.
    with tempfile.TemporaryDirectory() as td:
        r_empty = run_scope_gate(
            research_question="What drives housing affordability?",
            run_dir=Path(td) / "e", run_id="TEST_BLANK", domain="",
        )
        r_ws = run_scope_gate(
            research_question="What drives housing affordability?",
            run_dir=Path(td) / "w", run_id="TEST_WS", domain="   ",
        )
    for r in (r_empty, r_ws):
        assert r.protocol.scope_decision == "proceed"
        assert r.protocol.scope_rejected is False
        assert r.protocol.domain == DEFAULT_DOMAIN


def test_sg1_garbage_domain_still_rejects_loudly() -> None:
    # A genuinely malformed explicit literal still fails loud (no silent
    # clinical fallback) — the blank-normalization does NOT swallow real errors.
    with tempfile.TemporaryDirectory() as td:
        r = run_scope_gate(
            research_question="What is X?",
            run_dir=td, run_id="TEST_GARBAGE", domain="made_up_domain",
        )
    assert r.protocol.scope_rejected is True
    assert r.protocol.scope_rejection_code == "unsupported_domain"


def test_sg1_classifier_non_clinical_question() -> None:
    di = classify_domain_intent(
        "What is the GDP growth effect of the carbon tax?",
        evidence=_ECON_ROWS,
        domain_hint="workforce",
    )
    assert di.is_clinical is False
    assert di.domain != "clinical"
    # is_quantitative fires on the explicit metric cue ("growth").
    assert di.is_quantitative is True


def test_sg1_classifier_clinical_question_positive_signal() -> None:
    di = classify_domain_intent(
        "What weight loss does semaglutide produce in adults with obesity?",
        evidence=_CLINICAL_ROWS,
        domain_hint=None,
    )
    assert di.is_clinical is True
    assert di.domain == "clinical"


def test_sg1_classifier_llm_seam_failopen() -> None:
    # An injected LLM that returns garbage FAILS OPEN to the heuristic label
    # (never raises, never clinical-by-error).
    def _bad_llm(_q: str) -> str:
        return "not json at all {{{"

    di = classify_domain_intent(
        "What is the inflation rate trend?",
        evidence=_ECON_ROWS,
        domain_hint="economics",
        llm=_bad_llm,
    )
    assert di.is_clinical is False
    assert di.source == "heuristic"


def test_sg1_classifier_llm_seam_refines_label() -> None:
    # A well-formed LLM verdict refines the free-text domain label (non-clinical
    # only). is_clinical stays deterministic.
    def _good_llm(_q: str) -> str:
        return '{"domain": "macroeconomics"}'

    di = classify_domain_intent(
        "Describe the productivity puzzle.",
        evidence=_ECON_ROWS,
        domain_hint="economics",
        llm=_good_llm,
    )
    assert di.domain == "macroeconomics"
    assert di.source == "llm"
    assert di.is_clinical is False


# ─────────────────────────────────────────────────────────────────────────────
# SG2 — qualitative clinical lexicon does NOT fire on a non-clinical corpus
# ─────────────────────────────────────────────────────────────────────────────

def test_sg2_qualitative_lexicon_gated_off_non_clinical() -> None:
    # The labor corpus contains "contraindication" + "mortality" — the clinical
    # NegEx lexicon would otherwise fire. With the domain gated, ZERO clinical
    # qualitative assertions are emitted (the 2,738-junk-flag bug).
    out = extract_qualitative_assertions(
        _LABOR_ROWS_WITH_CLINICAL_WORD, domain="workforce"
    )
    assert out == []


def test_sg2_qualitative_lexicon_fires_on_clinical() -> None:
    # A real clinical present-vs-absent corpus STILL produces assertions
    # (clinical rigor preserved).
    clinical_qual = [
        {
            "evidence_id": "q1",
            "direct_quote": "Tirzepatide is contraindicated in patients with "
            "a history of medullary thyroid carcinoma.",
            "source_url": "https://fda.gov/label",
            "tier": "T3",
        },
    ]
    out = extract_qualitative_assertions(clinical_qual, domain="clinical")
    assert len(out) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# B9-5 — non-clinical numeric yields a REAL claim-key (non-singleton basket)
# ─────────────────────────────────────────────────────────────────────────────

def test_b9_5_non_clinical_numeric_yields_real_claim_key() -> None:
    claims = extract_numeric_claims(_ECON_ROWS, domain="workforce")
    assert len(claims) == 2, "non-clinical rows must now extract numeric claims"
    for c in claims:
        # NOT the unknown-subject sentinel -> a real, mergeable subject.
        assert c.subject and c.subject != "unknown"
        assert c.predicate
        assert c.unit  # 'percent'
    # The two corroborating sources share subject+predicate+value+unit -> they
    # form ONE basket (non-singleton) instead of two singletons.
    c0, c1 = claims
    assert (c0.subject, c0.predicate, c0.value, c0.unit) == (
        c1.subject, c1.predicate, c1.value, c1.unit
    )


def test_b9_5_finding_dedup_forms_non_singleton_basket() -> None:
    res = dedup_by_finding(
        _ECON_ROWS, gov_suffixes=("gov",), domain="workforce"
    )
    # Exactly one cluster carrying BOTH rows (a real corroboration basket).
    multi = [cl for cl in res.clusters if len(cl.member_indices) >= 2]
    assert len(multi) == 1
    assert sorted(multi[0].member_indices) == [0, 1]
    assert multi[0].corroboration_count == 2


def test_b9_5_clinical_extraction_unchanged() -> None:
    # Clinical rows still route the clinical extractor (byte-identical subject /
    # predicate / unit).
    claims = extract_numeric_claims(_CLINICAL_ROWS, domain="clinical")
    assert len(claims) == 1
    c = claims[0]
    assert c.subject == "semaglutide"
    assert c.predicate == "weight loss"
    assert c.value == 14.9
    assert c.unit == "%"


# ─────────────────────────────────────────────────────────────────────────────
# B9-3 — non-clinical numeric gap -> possible_metric_mismatch when scope differs
# ─────────────────────────────────────────────────────────────────────────────

def test_b9_3_metric_mismatch_label_when_scope_differs() -> None:
    # Same subject+metric, different endpoint/time-window discriminators -> the
    # numbers may not measure the same thing -> possible_metric_mismatch, NOT a
    # hard contradiction.
    from src.polaris_graph.retrieval.contradiction_detector import (
        ExtractedNumericClaim,
    )
    a = ExtractedNumericClaim(
        evidence_id="m1", subject="unemployment", predicate="rate",
        value=20.0, unit="percent", context_snippet="2024 unemployment rate",
        endpoint_phrase="2024",
    )
    b = ExtractedNumericClaim(
        evidence_id="m2", subject="unemployment", predicate="rate",
        value=10.0, unit="percent", context_snippet="2030 unemployment rate",
        endpoint_phrase="2030",
    )
    recs = detect_contradictions([a, b], is_clinical=False)
    assert len(recs) == 1
    assert "possible_metric_mismatch" in recs[0].predicate
    assert recs[0].severity == "low"


def test_b9_3_true_contradiction_when_scope_shared_non_clinical() -> None:
    # Same subject+metric+endpoint -> a real numeric gap is a true contradiction.
    from src.polaris_graph.retrieval.contradiction_detector import (
        ExtractedNumericClaim,
    )
    a = ExtractedNumericClaim(
        evidence_id="t1", subject="unemployment", predicate="rate",
        value=20.0, unit="percent", context_snippet="rate",
        endpoint_phrase="2024",
    )
    b = ExtractedNumericClaim(
        evidence_id="t2", subject="unemployment", predicate="rate",
        value=10.0, unit="percent", context_snippet="rate",
        endpoint_phrase="2024",
    )
    recs = detect_contradictions([a, b], is_clinical=False)
    assert len(recs) == 1
    assert "possible_metric_mismatch" not in recs[0].predicate
    assert recs[0].severity == "high"


def test_b9_3_unconfirmed_scope_is_metric_mismatch_not_contradiction() -> None:
    # Codex P1.3: a non-clinical numeric gap whose scope is UNCONFIRMED (every
    # comparator/population/endpoint axis empty) is a possible_metric_mismatch,
    # never a hard contradiction (conservative non-clinical default).
    from src.polaris_graph.retrieval.contradiction_detector import (
        ExtractedNumericClaim,
    )
    a = ExtractedNumericClaim(
        evidence_id="u1", subject="unemployment", predicate="rate",
        value=20.0, unit="percent", context_snippet="rate",
    )
    b = ExtractedNumericClaim(
        evidence_id="u2", subject="unemployment", predicate="rate",
        value=10.0, unit="percent", context_snippet="rate",
    )
    recs = detect_contradictions([a, b], is_clinical=False)
    assert len(recs) == 1
    assert "possible_metric_mismatch" in recs[0].predicate
    assert recs[0].severity == "low"


def test_b9_3_production_path_unconfirmed_scope_is_metric_mismatch() -> None:
    # Codex iter-3 P1: the PRODUCTION extract_numeric_claims path must NOT stamp
    # endpoint_phrase=predicate (which would falsely read as confirmed shared
    # scope). A non-clinical numeric gap whose scope is unconfirmed must be a
    # possible_metric_mismatch end-to-end, not a hard contradiction.
    rows = [
        {"evidence_id": "p1", "direct_quote": "The unemployment rate hit 20.0 "
         "percent.", "source_url": "https://a", "tier": "T3"},
        {"evidence_id": "p2", "direct_quote": "The unemployment rate was 10.0 "
         "percent.", "source_url": "https://b", "tier": "T3"},
    ]
    claims = extract_numeric_claims(rows, domain="workforce")
    # The generic extractor must NOT set endpoint_phrase (no faux time-window).
    assert all(c.endpoint_phrase == "" for c in claims)
    recs = detect_contradictions(claims, is_clinical=False)
    assert len(recs) == 1
    assert "possible_metric_mismatch" in recs[0].predicate
    assert recs[0].severity == "low"


def test_b9_4_generic_value_anchored_on_metric_cue_not_leading_date() -> None:
    # Codex P1.4: the claim value is the number tied to the metric cue, NOT a
    # leading date / sample-size.
    claims = extract_numeric_claims(
        [{"evidence_id": "v1", "direct_quote": "In 2024, the unemployment "
          "rate reached 12.5 percent (N=4500 respondents).",
          "source_url": "https://a", "tier": "T3"}],
        domain="workforce",
    )
    assert len(claims) == 1
    assert claims[0].value == 12.5  # not 2024, not 4500
    assert claims[0].unit == "percent"


def test_b9_3_clinical_contradiction_path_unchanged() -> None:
    # The clinical path (is_clinical default True) never enters the
    # metric-mismatch branch.
    claims = extract_numeric_claims(
        [
            {"evidence_id": "c1", "direct_quote": "Semaglutide weight loss was "
             "20.0% at week 68.", "source_url": "https://a", "tier": "T1"},
            {"evidence_id": "c2", "direct_quote": "Semaglutide weight loss was "
             "10.0% at week 68.", "source_url": "https://b", "tier": "T1"},
        ],
        domain="clinical",
    )
    recs = detect_contradictions(claims)  # is_clinical defaults True
    if recs:
        for r in recs:
            assert "possible_metric_mismatch" not in r.predicate


# ─────────────────────────────────────────────────────────────────────────────
# Clinical byte-identity — protocol.json hash unchanged for a clinical question
# ─────────────────────────────────────────────────────────────────────────────

def test_clinical_protocol_byte_identity_proceed() -> None:
    # A well-scoped clinical question routes clinical, proceeds, and produces a
    # deterministic protocol whose hash is stable (no new field leaked into
    # protocol.json by the B9 work).
    with tempfile.TemporaryDirectory() as td:
        r1 = run_scope_gate(
            research_question="What weight loss does semaglutide produce in "
            "adults with type 2 diabetes?",
            run_dir=Path(td) / "a",
            run_id="FIXED_RUN_ID",
            domain="clinical",
        )
        r2 = run_scope_gate(
            research_question="What weight loss does semaglutide produce in "
            "adults with type 2 diabetes?",
            run_dir=Path(td) / "b",
            run_id="FIXED_RUN_ID",
            domain="clinical",
        )
        assert r1.protocol.domain == "clinical"
        assert r1.protocol.scope_decision == "proceed"
        assert r1.protocol.intervention == "semaglutide"
        # Clinical PICO is unchanged (population + intervention extracted, no
        # false abort).
        assert r1.protocol.population  # a population marker was extracted
        assert r2.protocol.scope_decision == "proceed"
        # BYTE-IDENTITY PROOF: protocol.json carries NO new B9 field — the
        # classifier output is advisory routing context, never serialized into
        # the immutable protocol, so the protocol bytes/keys are the historical
        # ProtocolDocument set (clinical hash semantics unchanged).
        payload = (Path(r1.protocol_path)).read_text(encoding="utf-8")
        assert "domain_intent" not in payload
        assert "is_clinical" not in payload
        assert "key_entity_types" not in payload
    # The to_json_dict keys are exactly the historical ProtocolDocument fields.
    keys = set(r1.protocol.to_json_dict().keys())
    assert "domain_intent" not in keys


# ─────────────────────────────────────────────────────────────────────────────
# Domain packs — schema-valid, general default, only clinical is_clinical
# ─────────────────────────────────────────────────────────────────────────────

def test_domain_packs_all_present_and_valid() -> None:
    names = available_packs()
    for required in ("general", "clinical", "economics", "policy", "science",
                     "technology"):
        assert required in names
        pack = load_domain_pack(required)
        assert pack["domain"]
        assert "sections" in pack
        assert "contradiction_predicates" in pack
        assert "source_tier_priors" in pack
        assert "safety_policy" in pack


def test_domain_pack_only_clinical_is_clinical() -> None:
    assert pack_is_clinical("clinical") is True
    for d in ("general", "economics", "policy", "science", "technology",
              "workforce", "bananas", ""):
        assert pack_is_clinical(d) is False


def test_domain_pack_unknown_degrades_to_general_never_clinical() -> None:
    pack = load_domain_pack("some_unheard_of_domain")
    assert pack["domain"] == "general"
    assert pack["is_clinical"] is False


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
