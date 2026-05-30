"""Tests for the native Gate-B input builder (I-meta-002 PR-9 / M3a).

FIXTURES ONLY — NO NETWORK, NO SPEND. The builder is a pure function; these tests use
small in-test fake structures (a MultiSectionResult-like object with sections +
kept_sentences_pre_resolve, a fake evidence_lookup dict, and a fixture scope template
under tests/fixtures/). They also assert the contamination boundary: the module never
references outputs/dr_benchmark / the gold rubric.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from src.polaris_graph.roles.native_gate_b_inputs import (
    _claim_covers_entity,
    _content_requirements_satisfied,
    build_native_gate_b_inputs,
    load_required_entities,
    validate_entity_severity,
)
from src.polaris_graph.roles.release_policy import D8PolicyConfig

_FIXTURE_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "native_gate_b_scope_template.json"
)
_FIXTURE_SLUG = "fixture_slug"

_DOI_URL = "https://www.nejm.org/doi/full/10.1056/NEJMoa2107519"
_TRIAL_DOI = "10.1056/NEJMoa2107519"
_TRIAL_PMID = "37786396"
_FDA_LABEL_URL = (
    "https://www.accessdata.fda.gov/drugsatfda_docs/label/2023/217806s000lbl.pdf"
)


# --- in-test fakes (attribute-access only; the builder never imports the generator) ------
@dataclass
class FakeToken:
    evidence_id: str


@dataclass
class FakeSentence:
    sentence: str
    tokens: list
    is_verified: bool = True


@dataclass
class FakeSection:
    title: str
    kept_sentences_pre_resolve: list = field(default_factory=list)


@dataclass
class FakeMulti:
    sections: list


def _model_slugs() -> dict:
    return {"mirror": "m/mirror", "sentinel": "m/sentinel", "judge": "m/judge"}


def _d8_config() -> D8PolicyConfig:
    return D8PolicyConfig(
        coverage_threshold=0.70,
        material_severities=["S0", "S1", "S2"],
        s0_must_cover_categories=[
            "contraindications",
            "dosing_limits",
            "black_box_warnings",
        ],
    )


def _load_template() -> dict:
    return json.loads(_FIXTURE_TEMPLATE_PATH.read_text(encoding="utf-8"))


def _entity(template: dict, entity_id: str) -> dict:
    entities = template["per_query_report_contract"][_FIXTURE_SLUG]["required_entities"]
    return next(e for e in entities if e["id"] == entity_id)


# --- load_required_entities --------------------------------------------------------------
def test_load_required_entities_returns_native_denominator():
    template = _load_template()
    entities = load_required_entities(template, _FIXTURE_SLUG)
    assert [e["id"] for e in entities] == [
        "trial_doi_entity",
        "trial_pmid_entity",
        "label_url_entity",
    ]


def test_missing_contract_for_slug_raises():
    with pytest.raises(ValueError):
        load_required_entities(_load_template(), "no_such_slug")


def test_empty_required_entities_raises():
    template = {"per_query_report_contract": {_FIXTURE_SLUG: {"required_entities": []}}}
    with pytest.raises(ValueError):
        load_required_entities(template, _FIXTURE_SLUG)


# --- validate_entity_severity (fail-closed, never default S3) ----------------------------
def test_missing_severity_raises_never_defaults_s3():
    with pytest.raises(ValueError):
        validate_entity_severity({"id": "x"}, _d8_config())


def test_invalid_severity_value_raises():
    with pytest.raises(ValueError):
        validate_entity_severity({"id": "x", "severity": "S9"}, _d8_config())


def test_s0_without_category_raises():
    # Carries a canonical id so the ONLY missing piece is the s0_category.
    entity = {
        "id": "x",
        "severity": "S0",
        "doi": "10.1/x",
        "coverage_content_requirements": ["foo"],
    }
    with pytest.raises(ValueError):
        validate_entity_severity(entity, _d8_config())


def test_s0_with_invalid_category_raises():
    entity = {
        "id": "x",
        "severity": "S0",
        "doi": "10.1/x",
        "s0_category": "not_a_real_category",
        "coverage_content_requirements": ["foo"],
    }
    with pytest.raises(ValueError):
        validate_entity_severity(entity, _d8_config())


def test_s0_without_content_requirements_raises():
    entity = {
        "id": "x",
        "severity": "S0",
        "doi": "10.1/x",
        "s0_category": "contraindications",
    }
    with pytest.raises(ValueError):
        validate_entity_severity(entity, _d8_config())


@pytest.mark.parametrize(
    "bad_reqs",
    [
        [],  # empty list (truthy-list check now insufficient)
        [""],  # single blank string
        ["   "],  # single whitespace-only string
        ["contraindicated", ""],  # one good token but a blank sibling
        [123],  # non-string element
        ["contraindicated", 123],  # one good token but a non-string sibling
    ],
)
def test_s0_with_blank_or_nonstring_content_requirements_raises(bad_reqs):
    # Codex P1: an S0 entity whose coverage_content_requirements are empty / blank / non-string
    # must FAIL validation so a bare canonical citation can never earn S0 credit.
    entity = {
        "id": "x",
        "severity": "S0",
        "doi": "10.1/x",
        "s0_category": "contraindications",
        "coverage_content_requirements": bad_reqs,
    }
    with pytest.raises(ValueError):
        validate_entity_severity(entity, _d8_config())


def test_valid_non_s0_returns_severity_and_none_category():
    entity = {"id": "x", "severity": "S2", "pmid": "123"}
    assert validate_entity_severity(entity, _d8_config()) == ("S2", None)


def test_valid_s0_returns_category():
    entity = {
        "id": "x",
        "severity": "S0",
        "url_pattern": "https://example.org/full/label.pdf",
        "s0_category": "contraindications",
        "coverage_content_requirements": ["foo"],
    }
    assert validate_entity_severity(entity, _d8_config()) == ("S0", "contraindications")


def test_entity_without_any_canonical_identifier_raises():
    # An entity declaring no doi/pmid/url_pattern would be permanently uncoverable -> LOUD.
    entity = {"id": "no_id_entity", "type": "pivotal_trial", "anchor": "X", "severity": "S2"}
    with pytest.raises(ValueError):
        validate_entity_severity(entity, _d8_config())


# --- _claim_covers_entity: exact DOI / PMID / URL; fragments + anchors fail closed -------
def test_entity_coverage_exact_doi_match():
    entity = _entity(_load_template(), "trial_doi_entity")
    records = [{"doi": _TRIAL_DOI, "text": "abc"}]
    assert _claim_covers_entity(records, "any claim", entity, is_s0=False) is True


def test_entity_coverage_exact_pmid_match():
    entity = _entity(_load_template(), "trial_pmid_entity")
    records = [{"pmid": _TRIAL_PMID, "text": "abc"}]
    assert _claim_covers_entity(records, "any claim", entity, is_s0=False) is True


def test_entity_coverage_exact_full_url_match():
    entity = _entity(_load_template(), "label_url_entity")
    records = [{"url": _FDA_LABEL_URL, "text": "abc"}]
    # is_s0 with content present so the URL match alone is the thing under test here.
    claim = "tirzepatide is contraindicated in hypersensitivity"
    assert _claim_covers_entity(records, claim, entity, is_s0=True) is True


def test_broad_url_fragment_does_not_grant_coverage():
    entity = _entity(_load_template(), "label_url_entity")
    # A broad domain fragment is NOT the full canonical URL -> exact-equality fails closed.
    records = [{"url": "https://www.accessdata.fda.gov/", "text": "abc"}]
    claim = "tirzepatide is contraindicated in hypersensitivity"
    assert _claim_covers_entity(records, claim, entity, is_s0=True) is False


def test_anchor_string_in_sentence_alone_does_not_grant_coverage():
    entity = _entity(_load_template(), "trial_doi_entity")
    # The sentence mentions the anchor, but the cited evidence has NO matching canonical id.
    records = [{"url": "https://example.org/other", "text": "abc"}]
    claim = "TRIAL-DOI reported a large effect"
    assert _claim_covers_entity(records, claim, entity, is_s0=False) is False


def test_s0_coverage_requires_evidence_and_content_match():
    entity = _entity(_load_template(), "label_url_entity")
    records = [{"url": _FDA_LABEL_URL, "text": "abc"}]
    # Evidence matches, but the claim does NOT contain the required content tokens.
    bare = "the FDA label was reviewed for tirzepatide"
    assert _claim_covers_entity(records, bare, entity, is_s0=True) is False
    full = "tirzepatide is contraindicated in patients with hypersensitivity"
    assert _claim_covers_entity(records, full, entity, is_s0=True) is True


# --- _content_requirements_satisfied: fail-closed matcher backstop (Codex P1) ------------
def test_content_requirements_satisfied_fails_closed_on_empty():
    # Validation now blocks empty/blank requirements at load, but the matcher itself MUST
    # also fail closed: empty (or all-blank) requirements grant NO S0 credit, never vacuous True.
    claim = "tirzepatide is contraindicated in hypersensitivity"
    assert _content_requirements_satisfied(claim, {"coverage_content_requirements": []}) is False
    assert _content_requirements_satisfied(claim, {}) is False
    assert (
        _content_requirements_satisfied(
            claim, {"coverage_content_requirements": ["", "   "]}
        )
        is False
    )


def test_content_requirements_satisfied_true_only_when_all_tokens_present():
    # A valid non-blank requirement grants credit only when the claim text contains it.
    entity = {"coverage_content_requirements": ["contraindicated", "hypersensitivity"]}
    full = "tirzepatide is contraindicated in patients with hypersensitivity"
    partial = "tirzepatide is contraindicated in patients"
    assert _content_requirements_satisfied(full, entity) is True
    assert _content_requirements_satisfied(partial, entity) is False


def test_s0_credit_fails_closed_when_matcher_sees_empty_requirements():
    # Direct matcher-level fail-closed: a claim citing the S0 entity's evidence but with an
    # entity whose requirements list is empty earns NO S0 credit (covered_element_ids stays
    # closed for S0). validate_entity_severity blocks this at load, so we exercise the matcher
    # directly to prove the backstop independent of validation.
    entity = dict(_entity(_load_template(), "label_url_entity"))
    entity["coverage_content_requirements"] = []
    records = [{"url": _FDA_LABEL_URL, "text": "abc"}]
    claim = "tirzepatide is contraindicated in hypersensitivity"
    # Evidence matches the entity's canonical URL, but with no real requirements the S0
    # content check fails closed -> entity NOT covered.
    assert _claim_covers_entity(records, claim, entity, is_s0=True) is False


# --- build_native_gate_b_inputs: end-to-end fixtures -------------------------------------
def _evidence_lookup() -> dict:
    return {
        "ev_doi": {"doi": _TRIAL_DOI, "url": _DOI_URL, "text": "trial primary endpoint"},
        "ev_pmid": {"pmid": _TRIAL_PMID, "text": "second trial body text"},
        "ev_label": {"url": _FDA_LABEL_URL, "text": "label contraindications section"},
        "ev_unrelated": {"url": "https://example.org/x", "text": "unrelated body"},
    }


def _build(multi: FakeMulti, template: dict | None = None):
    return build_native_gate_b_inputs(
        multi=multi,
        template=template if template is not None else _load_template(),
        slug=_FIXTURE_SLUG,
        domain="clinical",
        evidence_lookup=_evidence_lookup(),
        model_slugs=_model_slugs(),
        d8_config=_d8_config(),
    )


def test_build_populates_claims_severity_coverage_and_audit_map():
    s0_sentence = "tirzepatide is contraindicated in hypersensitivity per the label"
    multi = FakeMulti(
        sections=[
            FakeSection(
                title="Efficacy",
                kept_sentences_pre_resolve=[
                    FakeSentence("The trial showed an effect", [FakeToken("ev_doi")]),
                ],
            ),
            FakeSection(
                title="Regulatory",
                kept_sentences_pre_resolve=[
                    FakeSentence(s0_sentence, [FakeToken("ev_label")]),
                ],
            ),
        ]
    )
    bundle = _build(multi)
    inputs = bundle.inputs

    # Required-element denominator = all native entity ids; numerator stays EMPTY on input.
    assert inputs.coverage_ledger.required_element_ids == [
        "trial_doi_entity",
        "trial_pmid_entity",
        "label_url_entity",
    ]
    assert inputs.coverage_ledger.covered_element_ids == set()
    # required_s0_categories = over ALL S0 entities (the must-cover denominator).
    assert inputs.required_s0_categories == ["contraindications"]

    assert len(inputs.claims) == 2
    doi_claim, s0_claim = inputs.claims

    # DOI claim: covers the S1 trial entity -> per-claim covered_element_ids populated.
    assert doi_claim.covered_element_ids == ["trial_doi_entity"]
    assert doi_claim.severity == "S1"
    assert doi_claim.s0_categories == []

    # S0 claim: evidence + content match -> covered with its s0_category.
    assert s0_claim.covered_element_ids == ["label_url_entity"]
    assert s0_claim.severity == "S0"
    assert s0_claim.s0_categories == ["contraindications"]

    # audit_map keys + structure.
    assert set(bundle.audit_map) == {c.claim_id for c in inputs.claims}
    a = bundle.audit_map[s0_claim.claim_id]
    assert a["section_index"] == 1
    assert a["section_title"] == "Regulatory"
    assert a["evidence_ids"] == ["ev_label"]
    assert a["covered_element_ids"] == ["label_url_entity"]
    assert a["severity"] == "S0"
    assert a["s0_categories"] == ["contraindications"]


def test_claim_covering_nothing_is_s3_observe_only():
    multi = FakeMulti(
        sections=[
            FakeSection(
                title="Misc",
                kept_sentences_pre_resolve=[
                    FakeSentence("an unrelated observation", [FakeToken("ev_unrelated")]),
                ],
            )
        ]
    )
    claim = _build(multi).inputs.claims[0]
    assert claim.covered_element_ids == []
    assert claim.severity == "S3"
    assert claim.s0_categories == []


def test_severity_is_max_over_covered_entities():
    # One claim cites BOTH the S1 trial and the S0 label evidence + S0 content -> MAX = S0.
    sentence = "tirzepatide is contraindicated in hypersensitivity per the trial and label"
    multi = FakeMulti(
        sections=[
            FakeSection(
                title="Combined",
                kept_sentences_pre_resolve=[
                    FakeSentence(sentence, [FakeToken("ev_doi"), FakeToken("ev_label")]),
                ],
            )
        ]
    )
    claim = _build(multi).inputs.claims[0]
    assert set(claim.covered_element_ids) == {"trial_doi_entity", "label_url_entity"}
    assert claim.severity == "S0"
    assert claim.s0_categories == ["contraindications"]


def test_s0_category_credit_requires_content_match_in_build():
    # Cites the S0 label evidence but omits the required content tokens -> no S0 credit.
    multi = FakeMulti(
        sections=[
            FakeSection(
                title="Regulatory",
                kept_sentences_pre_resolve=[
                    FakeSentence("the label was reviewed", [FakeToken("ev_label")]),
                ],
            )
        ]
    )
    claim = _build(multi).inputs.claims[0]
    assert claim.covered_element_ids == []
    assert claim.severity == "S3"
    assert claim.s0_categories == []


def test_claim_id_deterministic_and_unique():
    sent = "identical sentence text"
    multi_a = FakeMulti(
        sections=[FakeSection("S", [FakeSentence(sent, [FakeToken("ev_doi")])])]
    )
    multi_b = FakeMulti(
        sections=[FakeSection("S", [FakeSentence(sent, [FakeToken("ev_doi")])])]
    )
    id_a = _build(multi_a).inputs.claims[0].claim_id
    id_b = _build(multi_b).inputs.claims[0].claim_id
    assert id_a == id_b  # same sentence + position -> same id

    normalized = re.sub(r"\s+", " ", sent.lower()).strip()
    expected_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:8]
    assert id_a == f"00-000-{expected_hash}"

    multi_two = FakeMulti(
        sections=[
            FakeSection(
                "S",
                [
                    FakeSentence("first sentence", [FakeToken("ev_doi")]),
                    FakeSentence("second sentence", [FakeToken("ev_doi")]),
                ],
            )
        ]
    )
    ids = [c.claim_id for c in _build(multi_two).inputs.claims]
    assert len(set(ids)) == len(ids) == 2


def test_unverified_sentences_are_skipped_in_indexing():
    multi = FakeMulti(
        sections=[
            FakeSection(
                "S",
                [
                    FakeSentence("dropped", [FakeToken("ev_doi")], is_verified=False),
                    FakeSentence("kept one", [FakeToken("ev_doi")]),
                ],
            )
        ]
    )
    claims = _build(multi).inputs.claims
    assert len(claims) == 1
    # sentence_index counts only kept sentences -> 000, not 001.
    assert claims[0].claim_id.startswith("00-000-")


def test_unknown_evidence_id_raises():
    multi = FakeMulti(
        sections=[FakeSection("S", [FakeSentence("x", [FakeToken("ev_missing")])])]
    )
    with pytest.raises(ValueError):
        _build(multi)


def test_empty_evidence_text_raises():
    multi = FakeMulti(
        sections=[FakeSection("S", [FakeSentence("x", [FakeToken("ev_empty")])])]
    )
    bundle_args = dict(
        multi=multi,
        template=_load_template(),
        slug=_FIXTURE_SLUG,
        domain="clinical",
        evidence_lookup={"ev_empty": {"doi": _TRIAL_DOI, "text": "   "}},
        model_slugs=_model_slugs(),
        d8_config=_d8_config(),
    )
    with pytest.raises(ValueError):
        build_native_gate_b_inputs(**bundle_args)


def test_zero_kept_sentences_raises():
    multi = FakeMulti(
        sections=[
            FakeSection(
                "S",
                [FakeSentence("dropped", [FakeToken("ev_doi")], is_verified=False)],
            )
        ]
    )
    with pytest.raises(ValueError):
        _build(multi)


def test_no_sections_raises():
    with pytest.raises(ValueError):
        _build(FakeMulti(sections=[]))


# --- contamination guard: never reads outputs/dr_benchmark / the gold rubric -------------
def test_module_never_references_dr_benchmark_or_rubric():
    module_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "polaris_graph"
        / "roles"
        / "native_gate_b_inputs.py"
    )
    source = module_path.read_text(encoding="utf-8")
    # The contamination-boundary comment MUST be present (spec: "Add the module-level
    # comment stating this"). dr_benchmark / rubric / competitor appear ONLY there.
    assert "CONTAMINATION-CRITICAL" in source
    assert "outputs/dr_benchmark/" in source  # named to state the boundary

    # No executable code path imports or reads the benchmark gold rubric / competitor
    # answers. Strip out comments + docstrings, then assert the forbidden tokens are gone
    # from real code, and that no import line touches benchmark/rubric/dr_benchmark.
    code_lines = []
    in_docstring = False
    for raw in source.splitlines():
        stripped = raw.strip()
        if stripped.startswith(('"""', "'''")):
            # Toggle on a docstring delimiter (these tests' modules use balanced triples).
            quote = stripped[:3]
            in_docstring = not (in_docstring or stripped.count(quote) >= 2)
            continue
        if in_docstring:
            continue
        if stripped.startswith("#"):
            continue
        code_lines.append(raw)
        if stripped.startswith(("import ", "from ")):
            assert "benchmark" not in stripped
            assert "rubric" not in stripped
            assert "dr_benchmark" not in stripped
    code = "\n".join(code_lines).lower()
    assert "dr_benchmark" not in code
    assert "outputs/dr_benchmark" not in code
    assert "competitor" not in code
    assert "rubric" not in code
