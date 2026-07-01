"""beat-both Wave B WS-4 — DOI-tolerant entity coverage credit (FAITHFULNESS-ADJACENT).

Offline, fixture-driven, NO model / GPU / network. Reproduces the measured drb_72 shape (7 required
entities; entity [4] is DOI-only — bare `doi`, empty `url_pattern` — cited by a genuinely-VERIFIED
claim whose evidence row carries the DOI ONLY in its structured `doi` field with `source_url=None`).

Root cause (both in native_gate_b_inputs.py): (1) `normalize_evidence_pool_lookup` never read the raw
record's STRUCTURED `doi`/`pmid` field (only regex-extracted from url/text), so a DOI-only record
reached `_entity_canonical_match` with NO identifier -> uncovered; (2) `_entity_canonical_match`
compared identifiers by raw exact equality, so a doi.org-resolver-URL or a different-case DOI never
matched the bare token. Both ride ONE default-ON kill-switch `PG_ENTITY_COVERAGE_CITATION_CREDIT`.

Proven here:
  * POSITIVE — the DOI-only entity is now credited covered; coverage_fraction rises above 0.571.
  * FALLBACK — a VERIFIED claim citing a SUPPORTS basket member credits coverage without a DOI match.
  * SAFETY (critical) — a NON-verified claim citing the same entity/basket/DOI does NOT credit.
  * SAFETY — a genuinely-uncovered entity (no verified claim, no DOI match, not a basket member) STAYS
    uncovered.
  * SAFETY — DOI-tolerance for an S0 entity still flows the content-requirement conjunction (no S0
    over-credit); the basket path never credits an S0 safety category (D8 must-cover gate unmoved).
  * Kill-switch OFF -> the exact pre-WS-4 behavior, coverage_fraction == 0.571 (byte-identical).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import pytest

from src.polaris_graph.roles import native_gate_b_inputs as ng
from src.polaris_graph.roles.coverage_binder import bind_basket_coverage
from src.polaris_graph.roles.native_gate_b_inputs import (
    _canonical_doi,
    _entity_canonical_match,
    build_native_gate_b_inputs,
    normalize_evidence_pool_lookup,
)
from src.polaris_graph.generator.required_entity_ledger import (
    STATE_GAP_DISCLOSED,
    STATE_VERIFIED,
    build_ledger,
    verified_covered_ids,
)
from src.polaris_graph.roles.release_policy import (
    CoverageLedger,
    D8ClaimRow,
    D8PolicyConfig,
    apply_d8_release_policy,
)

_FLAG = "PG_ENTITY_COVERAGE_CITATION_CREDIT"
_SLUG = "ws4_slug"

# entity [4] — the DOI-only drb_72 entity (brynjolfsson_genai_at_work analog): bare doi, empty url.
_E4_DOI = "10.1093/qje/qjae044"
# entity [5] — covered ONLY via a SUPPORTS basket member whose own DOI differs from the entity's.
_E5_DOI = "10.1000/fff"
_E5_REVIEW_DOI = "10.7777/review"
# entity [6] — genuinely uncovered (no verified claim, no DOI match, not a basket member).
_E6_DOI = "10.9999/zzz"


@pytest.fixture(autouse=True)
def _clear_flag():
    os.environ.pop(_FLAG, None)
    yield
    os.environ.pop(_FLAG, None)


# --- in-test fakes (attribute access only; the builder never imports the generator) ----------
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


@dataclass
class _FakeMulti:
    sections: list


def _model_slugs() -> dict:
    return {"mirror": "m/mirror", "sentinel": "m/sentinel", "judge": "m/judge"}


def _d8_config() -> D8PolicyConfig:
    return D8PolicyConfig(
        coverage_threshold=0.70,
        material_severities=["S0", "S1", "S2"],
        s0_must_cover_categories=["contraindications", "dosing_limits", "black_box_warnings"],
    )


def _template() -> dict:
    """7 required entities, drb_72 shape. e0-e3 exact-covered (baseline 4/7=0.571); e4 DOI-only
    (needs the structured-doi read); e5 basket-only; e6 genuinely uncovered."""
    return {
        "per_query_report_contract": {
            _SLUG: {
                "required_entities": [
                    {"id": "e0", "type": "trial", "severity": "S1", "doi": "10.1000/aaa"},
                    {"id": "e1", "type": "trial", "severity": "S2", "pmid": "11111111"},
                    {
                        "id": "e2",
                        "type": "regulatory",
                        "severity": "S1",
                        "url_pattern": "https://www.example-gov.test/label/aaa",
                    },
                    {"id": "e3", "type": "trial", "severity": "S2", "doi": "10.1000/ddd"},
                    # e4: DOI-only, empty url_pattern (the drb_72 entity [4]).
                    {"id": "e4", "type": "trial", "severity": "S1", "doi": _E4_DOI},
                    # e5: has its own DOI, but the citing source is a corroborating review whose
                    # DOI differs -> only its SUPPORTS basket credits coverage.
                    {
                        "id": "e5",
                        "type": "trial",
                        "severity": "S1",
                        "doi": _E5_DOI,
                        "supports_evidence_ids": ["ev_review_f"],
                    },
                    # e6: genuinely uncovered — a real DOI, no basket, nothing cites it.
                    {"id": "e6", "type": "trial", "severity": "S2", "doi": _E6_DOI},
                ]
            }
        }
    }


def _raw_pool() -> dict:
    """RAW evidence-pool rows (the run's `ev_pool` shape) fed through `normalize_evidence_pool_lookup`
    — so the flag genuinely governs the structured-doi read, exactly like production. e0-e3 carry a
    regex-extractable identifier in `source_url` (covered under BOTH flag states = the baseline). e4 is
    the DOI-only drb_72 shape: the DOI lives ONLY in the STRUCTURED `doi` field, `source_url=None`, and
    it is NOT in the text — so OFF drops it (uncovered) and ON reads it (covered). ev_review_f
    corroborates e5 but its OWN doi differs from e5's declared doi -> e5 covers only via its basket."""
    return {
        "ev_a": {"evidence_id": "ev_a", "source_url": "https://journal.test/doi/10.1000/aaa",
                 "direct_quote": "endpoint met"},
        "ev_b": {"evidence_id": "ev_b", "source_url": "https://pubmed.ncbi.nlm.nih.gov/11111111/",
                 "direct_quote": "trial body"},
        "ev_c": {"evidence_id": "ev_c", "source_url": "https://www.example-gov.test/label/aaa",
                 "direct_quote": "label body"},
        "ev_d": {"evidence_id": "ev_d", "source_url": "https://journal.test/doi/10.1000/ddd",
                 "direct_quote": "second trial"},
        # e4: DOI-only — DOI in the STRUCTURED field, source_url None, NOT in the text (drb_72 input).
        "ev_e4": {"evidence_id": "ev_e4", "doi": _E4_DOI, "source_url": None,
                  "direct_quote": "generative AI at work primary result"},
        # corroborating review supporting e5; its OWN doi differs from e5's declared doi.
        "ev_review_f": {"evidence_id": "ev_review_f", "doi": _E5_REVIEW_DOI,
                        "source_url": "https://journal.test/review", "direct_quote": "review"},
    }


def _verified_multi() -> _FakeMulti:
    """One VERIFIED sentence per covering evidence row. e6 is cited by nothing."""
    return _FakeMulti(
        sections=[
            _FakeSection(
                "S",
                [
                    _FakeSentence("claim a", [_FakeToken("ev_a")]),
                    _FakeSentence("claim b", [_FakeToken("ev_b")]),
                    _FakeSentence("claim c", [_FakeToken("ev_c")]),
                    _FakeSentence("claim d", [_FakeToken("ev_d")]),
                    _FakeSentence("claim e4", [_FakeToken("ev_e4")]),
                    _FakeSentence("claim e5", [_FakeToken("ev_review_f")]),
                ],
            )
        ]
    )


def _build(multi: _FakeMulti):
    # Normalize the RAW pool HERE (after the per-test flag is set) so the flag governs the
    # structured-doi read exactly as production does (run_gate_b normalizes then builds).
    evidence_lookup = normalize_evidence_pool_lookup(_raw_pool())
    return build_native_gate_b_inputs(
        multi=multi,
        template=_template(),
        slug=_SLUG,
        domain="custom",
        evidence_lookup=evidence_lookup,
        model_slugs=_model_slugs(),
        d8_config=_d8_config(),
    )


def _coverage_fraction(bundle, *, overrides: dict | None = None):
    """Run the production ledger chain: audit_map -> verified_covered_ids(final_verdicts) ->
    build_ledger -> (coverage_fraction, ledger, covered_set). Every claim is VERIFIED at the 4-role
    seam unless `overrides` maps one of its cited evidence tags to a non-VERIFIED verdict."""
    overrides = overrides or {}
    final_verdicts: dict[str, str] = {}
    for claim_id, row in bundle.audit_map.items():
        ev_ids = row.get("evidence_ids", [])
        verdict = "VERIFIED"
        for tag, bad in overrides.items():
            if tag in ev_ids:
                verdict = bad
        final_verdicts[claim_id] = verdict
    covered = verified_covered_ids(bundle.audit_map, final_verdicts)
    ledger = build_ledger(_template()["per_query_report_contract"][_SLUG]["required_entities"], covered)
    return ledger.coverage_fraction(), ledger, covered


# ─────────────────────────────────────────────────────────────────────────────────────────────
# unit: _canonical_doi + _entity_canonical_match DOI tolerance
# ─────────────────────────────────────────────────────────────────────────────────────────────
def test_canonical_doi_strips_resolver_and_lowercases():
    assert _canonical_doi("https://doi.org/10.1093/QJE/qjae044") == "10.1093/qje/qjae044"
    assert _canonical_doi("http://dx.doi.org/10.1093/qje/qjae044") == "10.1093/qje/qjae044"
    assert _canonical_doi("10.1093/QJE/qjae044") == "10.1093/qje/qjae044"
    # a non-DOI url / fragment is never a DOI (fail-closed — cannot masquerade as a match).
    assert _canonical_doi("https://www.accessdata.fda.gov/") == ""
    assert _canonical_doi("https://ods.od.nih.gov/factsheets/Iron/") == ""
    assert _canonical_doi(None) == ""
    assert _canonical_doi("") == ""


def test_entity_canonical_match_doi_tolerance_on_and_off():
    entity = {"id": "e", "severity": "S1", "doi": _E4_DOI}
    # record carries the DOI as a doi.org resolver URL, different case, empty bare-doi.
    record = {"url": f"https://doi.org/{_E4_DOI.upper()}", "text": "x"}
    os.environ[_FLAG] = "1"
    assert _entity_canonical_match(entity, record) is True
    # OFF -> exact-equality only, no resolver/case tolerance -> no match.
    os.environ[_FLAG] = "0"
    assert _entity_canonical_match(entity, record) is False


def test_doi_tolerance_never_matches_non_doi_url():
    """§-1.1 lock analog: a non-DOI alternate URL must never DOI-match (no over-credit)."""
    os.environ[_FLAG] = "1"
    entity = {"id": "e", "severity": "S1", "url_pattern": "https://ods.od.nih.gov/factsheets/Iron/"}
    record = {"url": "https://ods.od.nih.gov/factsheets/Iron-Consumer/", "text": "x"}
    assert _entity_canonical_match(entity, record) is False


# ─────────────────────────────────────────────────────────────────────────────────────────────
# unit: normalize_evidence_pool_lookup reads the structured doi/pmid field (the load-bearing fix)
# ─────────────────────────────────────────────────────────────────────────────────────────────
def test_normalize_reads_structured_doi_on_and_off():
    # exact drb_72 row: structured `doi`, source_url None, DOI NOT in the text.
    pool = {"ev_e4": {"evidence_id": "ev_e4", "doi": _E4_DOI, "source_url": None,
                      "direct_quote": "generative AI at work primary result"}}
    os.environ[_FLAG] = "1"
    on = normalize_evidence_pool_lookup(pool)
    assert on["ev_e4"]["doi"] == _E4_DOI  # structured DOI now carried
    # OFF -> byte-identical legacy (regex-only): the structured field is NOT read, so no doi key.
    os.environ[_FLAG] = "0"
    off = normalize_evidence_pool_lookup(pool)
    assert "doi" not in off["ev_e4"]


def test_normalize_reads_structured_pmid_on():
    pool = {"ev_p": {"evidence_id": "ev_p", "pmid": "34170647", "source_url": None,
                     "direct_quote": "body"}}
    os.environ[_FLAG] = "1"
    on = normalize_evidence_pool_lookup(pool)
    assert on["ev_p"]["pmid"] == "34170647"
    os.environ[_FLAG] = "0"
    assert "pmid" not in normalize_evidence_pool_lookup(pool)["ev_p"]


# ─────────────────────────────────────────────────────────────────────────────────────────────
# unit: bind_basket_coverage — SUPPORTS-only, fail-closed
# ─────────────────────────────────────────────────────────────────────────────────────────────
def _validated_e5(basket_key: str, basket_value) -> list:
    entity = {"id": "e5", "severity": "S1", "doi": _E5_DOI, basket_key: basket_value}
    return [(entity, "S1", None)]


def test_basket_credits_supports_member():
    covered = bind_basket_coverage(
        claim_evidence_ids=["ev_review_f"],
        validated_entities=_validated_e5("supports_evidence_ids", ["ev_review_f"]),
    )
    assert covered == {"e5"}


def test_basket_credits_supports_stance_in_evidence_basket():
    covered = bind_basket_coverage(
        claim_evidence_ids=["ev_review_f"],
        validated_entities=_validated_e5(
            "evidence_basket", [{"evidence_id": "ev_review_f", "stance": "SUPPORTS"}]
        ),
    )
    assert covered == {"e5"}


@pytest.mark.parametrize("stance", ["REFUTES", "NEUTRAL", "", "supports_typo"])
def test_basket_refuses_non_supports_stance(stance):
    """FAIL LOUD if a non-SUPPORTS member could credit coverage (over-credit is the wrong direction)."""
    covered = bind_basket_coverage(
        claim_evidence_ids=["ev_review_f"],
        validated_entities=_validated_e5(
            "evidence_basket", [{"evidence_id": "ev_review_f", "stance": stance}]
        ),
    )
    assert covered == set()


def test_basket_no_basket_or_no_cited_credits_nothing():
    # no basket field at all -> nothing.
    assert bind_basket_coverage(
        claim_evidence_ids=["ev_review_f"],
        validated_entities=[({"id": "e5", "severity": "S1", "doi": _E5_DOI}, "S1", None)],
    ) == set()
    # basket present but the claim cites none of its members -> nothing.
    assert bind_basket_coverage(
        claim_evidence_ids=["ev_other"],
        validated_entities=_validated_e5("supports_evidence_ids", ["ev_review_f"]),
    ) == set()
    # empty cited list -> nothing.
    assert bind_basket_coverage(
        claim_evidence_ids=[],
        validated_entities=_validated_e5("supports_evidence_ids", ["ev_review_f"]),
    ) == set()


# ─────────────────────────────────────────────────────────────────────────────────────────────
# seam end-to-end: coverage_fraction before/after (the drb_72 headline metric)
# ─────────────────────────────────────────────────────────────────────────────────────────────
def test_coverage_fraction_off_is_baseline_0571():
    os.environ[_FLAG] = "0"
    frac, ledger, covered = _coverage_fraction(_build(_verified_multi()))
    # OFF: e0-e3 exact-covered; e4 (structured-doi dropped) + e5 (basket off) + e6 uncovered.
    assert covered == {"e0", "e1", "e2", "e3"}
    assert round(frac, 3) == 0.571
    gap_ids = {s.entity_id for s in ledger.gap_slots()}
    assert gap_ids == {"e4", "e5", "e6"}


def test_coverage_fraction_on_rises_above_0571_positive_and_fallback():
    os.environ[_FLAG] = "1"
    frac, ledger, covered = _coverage_fraction(_build(_verified_multi()))
    # ON: POSITIVE (e4 via structured-doi read + DOI-tolerance) + FALLBACK (e5 via basket) covered.
    assert "e4" in covered  # POSITIVE
    assert "e5" in covered  # FALLBACK
    assert covered == {"e0", "e1", "e2", "e3", "e4", "e5"}
    assert frac > 0.571
    assert round(frac, 3) == 0.857
    # SAFETY: the genuinely-uncovered entity STAYS a disclosed gap.
    assert {s.entity_id for s in ledger.gap_slots()} == {"e6"}
    by = {s.entity_id: s for s in ledger.slots}
    assert by["e4"].state == STATE_VERIFIED
    assert by["e5"].state == STATE_VERIFIED
    assert by["e6"].state == STATE_GAP_DISCLOSED


# ─────────────────────────────────────────────────────────────────────────────────────────────
# SAFETY (critical): a NON-verified claim citing the same entity/basket/DOI does NOT credit
# ─────────────────────────────────────────────────────────────────────────────────────────────
def test_non_verified_claim_cannot_credit_at_strict_verify_seam():
    """A strict_verify-UNverified sentence never becomes a claim, so it can never credit coverage —
    even under the flag ON. FAIL LOUD if e4/e5 flip covered via a non-verified sentence."""
    os.environ[_FLAG] = "1"
    multi = _FakeMulti(
        sections=[
            _FakeSection(
                "S",
                [
                    _FakeSentence("claim a", [_FakeToken("ev_a")]),
                    _FakeSentence("claim b", [_FakeToken("ev_b")]),
                    _FakeSentence("claim c", [_FakeToken("ev_c")]),
                    _FakeSentence("claim d", [_FakeToken("ev_d")]),
                    # e4 (DOI) and e5 (basket) cited ONLY by NON-verified sentences.
                    _FakeSentence("claim e4", [_FakeToken("ev_e4")], is_verified=False),
                    _FakeSentence("claim e5", [_FakeToken("ev_review_f")], is_verified=False),
                ],
            )
        ]
    )
    frac, ledger, covered = _coverage_fraction(_build(multi))
    assert covered == {"e0", "e1", "e2", "e3"}  # e4/e5 NOT credited by the non-verified sentences
    assert round(frac, 3) == 0.571
    assert {s.entity_id for s in ledger.gap_slots()} == {"e4", "e5", "e6"}


def test_non_verified_claim_cannot_credit_at_four_role_seam():
    """Even a strict_verify-verified claim that the 4-role DOWNGRADES (non-VERIFIED final verdict)
    does NOT credit coverage — verified_covered_ids filters by final verdict == VERIFIED."""
    os.environ[_FLAG] = "1"
    bundle = _build(_verified_multi())
    # Downgrade the e4 claim (cites ev_e4) and the e5 claim (cites ev_review_f) at the 4-role seam.
    frac, ledger, covered = _coverage_fraction(
        bundle, overrides={"ev_e4": "UNSUPPORTED", "ev_review_f": "PARTIAL"}
    )
    assert "e4" not in covered
    assert "e5" not in covered
    assert covered == {"e0", "e1", "e2", "e3"}
    assert round(frac, 3) == 0.571


# ─────────────────────────────────────────────────────────────────────────────────────────────
# SAFETY: DOI-tolerance for an S0 entity still runs the content conjunction; basket never S0-credits
# ─────────────────────────────────────────────────────────────────────────────────────────────
def test_doi_tolerance_s0_entity_without_content_stays_uncovered():
    """An S0 entity whose evidence matches by DOI-tolerance but whose claim lacks the required
    content tokens is NOT covered — S0 safety credit still demands the content conjunction."""
    os.environ[_FLAG] = "1"
    s0_entity = {
        "id": "s0",
        "type": "regulatory",
        "severity": "S0",
        "doi": _E4_DOI,
        "s0_category": "contraindications",
        "coverage_content_requirements": ["contraindicated", "thyroid"],
    }
    template = {"per_query_report_contract": {_SLUG: {"required_entities": [s0_entity]}}}
    lookup = {"ev_s0": {"doi": _E4_DOI, "text": "body"}}
    multi = _FakeMulti(
        sections=[
            _FakeSection("S", [_FakeSentence("the label was reviewed", [_FakeToken("ev_s0")])])
        ]
    )
    bundle = build_native_gate_b_inputs(
        multi=multi, template=template, slug=_SLUG, domain="clinical",
        evidence_lookup=lookup, model_slugs=_model_slugs(), d8_config=_d8_config(),
    )
    claim = bundle.inputs.claims[0]
    # DOI-tolerance made the canonical match succeed, but the content tokens are absent -> uncovered.
    assert claim.covered_element_ids == []
    assert claim.s0_categories == []
    assert claim.severity == "S3"


def test_basket_credit_does_not_clear_d8_s0_must_cover_gate():
    """A basket-credited element raises coverage_fraction but NEVER credits an s0_category, so the
    D8 S0 must-cover gate (which reads s0_categories on VERIFIED rows) is unmoved — the frozen safety
    floor cannot be relaxed by the basket path."""
    os.environ[_FLAG] = "1"
    s0_entity = {
        "id": "s0",
        "type": "regulatory",
        "severity": "S0",
        "doi": "10.1000/s0doi",
        "s0_category": "contraindications",
        "coverage_content_requirements": ["contraindicated", "thyroid"],
        # basket member whose stance is SUPPORTS — would credit ELEMENT coverage only.
        "supports_evidence_ids": ["ev_review_s0"],
    }
    template = {"per_query_report_contract": {_SLUG: {"required_entities": [s0_entity]}}}
    lookup = {"ev_review_s0": {"doi": "10.7777/other", "text": "corroborating review body"}}
    multi = _FakeMulti(
        sections=[
            _FakeSection("S", [_FakeSentence("a supporting sentence", [_FakeToken("ev_review_s0")])])
        ]
    )
    bundle = build_native_gate_b_inputs(
        multi=multi, template=template, slug=_SLUG, domain="clinical",
        evidence_lookup=lookup, model_slugs=_model_slugs(), d8_config=_d8_config(),
    )
    claim = bundle.inputs.claims[0]
    # element covered via the basket, but NO s0_category credited (safety floor untouched).
    assert "s0" in claim.covered_element_ids
    assert claim.s0_categories == []
    # Feed the claim's shape to the frozen D8 gate: the S0 must-cover category is still MISSING.
    row = D8ClaimRow(
        claim_id=claim.claim_id, severity=claim.severity, verdict="VERIFIED",
        s0_categories=claim.s0_categories,
    )
    decision = apply_d8_release_policy(
        [row],
        required_s0_categories=["contraindications"],
        coverage_ledger=CoverageLedger(required_element_ids=["s0"], covered_element_ids={"s0"}),
        coverage_threshold=0.70,
        rewrite_already_attempted=True,
    )
    assert "d8_s0_must_cover_missing:contraindications" in decision.held_reasons


# ─────────────────────────────────────────────────────────────────────────────────────────────
# flag reader semantics (default ON, off-token idiom)
# ─────────────────────────────────────────────────────────────────────────────────────────────
def test_flag_default_on():
    os.environ.pop(_FLAG, None)
    assert ng._entity_coverage_citation_credit_enabled() is True


@pytest.mark.parametrize("off", ["0", "false", "no", "off", "OFF", "False"])
def test_flag_off_only_on_explicit_off_token(off):
    os.environ[_FLAG] = off
    assert ng._entity_coverage_citation_credit_enabled() is False


@pytest.mark.parametrize("on", ["", "1", "true", "yes", "on", "garbage", "  "])
def test_flag_on_for_unset_empty_or_unrecognized(on):
    os.environ[_FLAG] = on
    assert ng._entity_coverage_citation_credit_enabled() is True
