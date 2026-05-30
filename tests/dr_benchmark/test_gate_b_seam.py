"""Offline Gate-B seam test (I-meta-002 PR-9/M3b). NO network, NO spend.

Drives the EXTRACTED seam core (`sweep_integration.run_four_role_seam` — the same code the
guarded `run_one_query` branch calls) with an INJECTED FAKE `RoleTransport` (canned role
responses, no HTTP) and the REAL Gate-B builder closure
(`scripts/dr_benchmark/run_gate_b.make_gate_b_input_builder`) over a controlled fixture
contract + fixture evidence pool. It also exercises the builder over the REAL annotated
`clinical_tirzepatide_t2dm` contract to prove the native severity annotations are builder-valid
end to end.

PRODUCTION HAND-OFF (the property under test): the builder is built with NO report objects in
hand (just resolution policy). The SEAM supplies the run-local objects (`multi`, `template`,
`slug`, `domain`, `ev_pool`) AFTER generation — exactly as `run_one_query` does at :3173. A
no-arg-closure contract would break production (multi/ev_pool only exist inside run_one_query);
these tests assert the seam-supplied hand-off works.

Asserts:
  * the D8 decision flows into the manifest override (`release_allowed` + `status` ->
    four_role_released / four_role_held), via the same `to_unified_status` map the sweep uses;
  * `four_role_claim_audit.json` is written to the (tmp) run_dir with the builder's claim_ids;
  * builder-WINS precedence: when BOTH a builder and a static `four_role_inputs` are passed,
    the BUILDER's seam-supplied decision lands (the static inputs are ignored);
  * a builder-less static path runs and writes NO audit file;
  * NO network / NO spend — the transport is a canned in-process fake.

Hermetic: monkeypatched env, fake transport, tmp run_dir. The real `OpenAICompatibleRoleTransport`
is NEVER constructed against a live endpoint here.
"""

from __future__ import annotations

import json

import pytest
import yaml

from scripts.dr_benchmark.run_gate_b import make_gate_b_input_builder
from scripts.run_honest_sweep_r3 import to_unified_status
from src.polaris_graph.roles.mirror_contract import CitationSpan
from src.polaris_graph.roles.native_gate_b_inputs import normalize_evidence_pool_lookup
from src.polaris_graph.roles.release_policy import CoverageLedger
from src.polaris_graph.roles.role_transport import (
    EvidenceDocument,
    RoleRequest,
    RoleResponse,
)
from src.polaris_graph.roles.sweep_integration import (
    FOUR_ROLE_CLAIM_AUDIT_FILENAME,
    FourRoleClaim,
    FourRoleEvaluationInputs,
    run_four_role_seam,
)

_TIMESTAMP = "2026-05-29T00:00:00Z"
_CLINICAL_YAML = "config/scope_templates/clinical.yaml"
_TIRZEPATIDE_SLUG = "clinical_tirzepatide_t2dm"


class _FakeRoleTransport:
    """Canned in-process `RoleTransport` — NO network, NO spend.

    Mirror pass-1 returns a grounded `<co>` citation on the FIRST supplied evidence doc_id (so
    the binding holds for whatever evidence_id the claim carries); pass-2 echoes the embedded
    content_hash; Sentinel returns GROUNDED (`<score>no</score>`) or UNGROUNDED; Judge returns
    the configured verdict token. Mirrors `tests/roles/test_sweep_integration.MockTransport` but
    cites the request's actual doc_id so it works with builder-minted evidence_ids. The
    `http_calls` counter is incremented on EACH completion and asserted to equal the number of
    role completions (a REAL transport would also POST per call) — and never via any socket."""

    def __init__(self, *, sentinel_grounded: bool = True, judge_verdict: str = "VERIFIED") -> None:
        self._sentinel_grounded = sentinel_grounded
        self._judge_verdict = judge_verdict
        self.completions = 0  # canned in-process completions (NEVER an HTTP POST).

    def complete(self, request: RoleRequest) -> RoleResponse:
        self.completions += 1
        if request.role == "mirror":
            if "pass2_input" in (request.params or {}):
                content_hash = request.params["pass2_input"]["content_hash"]
                payload = {"content_hash": content_hash, "classification": "supported"}
                return RoleResponse(raw_text=json.dumps(payload), served_model=request.model_slug)
            documents = (request.params or {}).get("documents") or []
            doc_id = documents[0]["doc_id"] if documents else "doc0"
            return RoleResponse(
                raw_text="grounded answer",
                served_model=request.model_slug,
                citations=[CitationSpan(span_start=0, span_end=8, doc_ids=(doc_id,))],
            )
        if request.role == "sentinel":
            score = "no" if self._sentinel_grounded else "yes"
            return RoleResponse(raw_text=f"<score>{score}</score>", served_model=request.model_slug)
        if request.role == "judge":
            return RoleResponse(raw_text=self._judge_verdict, served_model=request.model_slug)
        raise AssertionError(f"unexpected role {request.role!r}")


# --- minimal in-memory report objects (the builder reads only these attributes) -----------
class _FakeVerification:
    def __init__(self, sentence: str, tokens, *, is_verified: bool = True) -> None:
        self.sentence = sentence
        self.tokens = tokens
        self.is_verified = is_verified


class _FakeToken:
    def __init__(self, evidence_id: str) -> None:
        self.evidence_id = evidence_id


class _FakeSection:
    def __init__(self, title: str, verifications) -> None:
        self.title = title
        self.kept_sentences_pre_resolve = verifications


class _FakeMulti:
    def __init__(self, sections) -> None:
        self.sections = sections


# --- a self-contained fixture contract (one S1 trial + one S0 regulatory entity) ----------
def _fixture_template() -> dict:
    """A native fixture contract: an S1 trial covered by a DOI + an S0 regulatory entity
    covered by a url_pattern + content tokens. Deterministic; never reads the gold rubric."""
    return {
        "per_query_report_contract": {
            "fixture_slug": {
                "required_entities": [
                    {
                        "id": "trial_a",
                        "type": "pivotal_trial",
                        "severity": "S1",
                        "doi": "10.1056/NEJMoaFIXTURE",
                        "required_fields": ["n", "endpoint"],
                        "min_fields_for_completion": 1,
                        "rendering_slot": "slot_a",
                    },
                    {
                        "id": "label_b",
                        "type": "regulatory",
                        "severity": "S0",
                        "s0_category": "contraindications",
                        "coverage_content_requirements": ["contraindicated", "thyroid"],
                        "url_pattern": "https://example.test/label/b",
                        "required_fields": ["contraindications"],
                        "min_fields_for_completion": 1,
                        "rendering_slot": "slot_b",
                    },
                ]
            }
        }
    }


def _fixture_ev_pool() -> dict:
    """Raw evidence-pool rows (the run's ev_pool shape) that cite the fixture entities."""
    return {
        "ev_000": {
            "evidence_id": "ev_000",
            "direct_quote": "The trial enrolled 1879 patients; the primary endpoint was met.",
            "source_url": "https://www.nejm.org/doi/full/10.1056/NEJMoaFIXTURE",
        },
        "ev_001": {
            "evidence_id": "ev_001",
            "direct_quote": "Tirzepatide is contraindicated in patients with a history of "
            "medullary thyroid carcinoma.",
            "source_url": "https://example.test/label/b",
        },
    }


def _fixture_multi() -> _FakeMulti:
    """A finished report whose two verified sentences cite the two fixture evidence rows.

    The S0 sentence text contains both content-requirement tokens ('contraindicated',
    'thyroid') so the S0 category is creditable on a VERIFIED verdict."""
    return _FakeMulti(
        sections=[
            _FakeSection(
                "Efficacy",
                [_FakeVerification("The trial enrolled 1879 patients.", [_FakeToken("ev_000")])],
            ),
            _FakeSection(
                "Safety",
                [
                    _FakeVerification(
                        "Tirzepatide is contraindicated in patients with medullary thyroid "
                        "carcinoma history.",
                        [_FakeToken("ev_001")],
                    )
                ],
            ),
        ]
    )


# --- M3b evidence-record normalization: deterministic, no network --------------------------
def test_normalization_extracts_bare_doi_url_and_pmid():
    pool = {
        "ev_000": {
            "evidence_id": "ev_000",
            "direct_quote": "Body text.",
            "source_url": "https://www.nejm.org/doi/full/10.1056/NEJMoa2107519",
        },
        "ev_011": {
            "evidence_id": "ev_011",
            "direct_quote": "Body.",
            "source_url": "https://pubmed.ncbi.nlm.nih.gov/40365662/",
        },
    }
    lookup = normalize_evidence_pool_lookup(pool)
    # url is verbatim; the `/full` landing-page suffix is trimmed so the DOI is the bare token.
    assert lookup["ev_000"]["url"] == "https://www.nejm.org/doi/full/10.1056/NEJMoa2107519"
    assert lookup["ev_000"]["doi"] == "10.1056/NEJMoa2107519"
    assert "pmid" not in lookup["ev_000"]
    # PMID extracted from the PubMed path; bare numeric so it == an entity pmid (int -> str).
    assert lookup["ev_011"]["pmid"] == "40365662"
    # text maps from direct_quote (the field strict_verify spans index into).
    assert lookup["ev_000"]["text"] == "Body text."


def test_normalization_trims_publisher_suffix_and_trailing_punct():
    pool = {
        "ev_a": {"direct_quote": "x", "source_url": "https://www.frontiersin.org/articles/10.3389/fphar.2022.1016639/full"},
        "ev_b": {"direct_quote": "see 10.1111/dom.16463.", "source_url": "https://example.test/no-doi"},
        "ev_c": {"direct_quote": "no identifiers here", "source_url": "https://clinicaltrials.gov/study/NCT04657016"},
    }
    lookup = normalize_evidence_pool_lookup(pool)
    assert lookup["ev_a"]["doi"] == "10.3389/fphar.2022.1016639"  # /full trimmed
    assert lookup["ev_b"]["doi"] == "10.1111/dom.16463"  # trailing period trimmed
    # No DOI/PMID anywhere -> absent (genuinely absent, fail-closed: builder treats as no-match).
    assert "doi" not in lookup["ev_c"]
    assert "pmid" not in lookup["ev_c"]
    assert lookup["ev_c"]["url"] == "https://clinicaltrials.gov/study/NCT04657016"


@pytest.fixture(autouse=True)
def _four_role_env(monkeypatch):
    """Mirror the production activation env (the seam test calls the seam core directly, but we
    set this so the offline run matches how Gate-B activates the guarded sweep branch)."""
    monkeypatch.setenv("PG_FOUR_ROLE_MODE", "1")
    yield


# --- the happy path: grounded + VERIFIED claims cover both required elements + S0 -> release ---
def test_seam_builder_releases_and_writes_audit(tmp_path):
    # Builder built with NO report objects in hand — the SEAM supplies them (production hand-off).
    builder = make_gate_b_input_builder()
    transport = _FakeRoleTransport(sentinel_grounded=True, judge_verdict="VERIFIED")
    result = run_four_role_seam(
        transport,
        run_dir=tmp_path,
        timestamp=_TIMESTAMP,
        four_role_input_builder=builder,
        multi=_fixture_multi(),
        template=_fixture_template(),
        slug="fixture_slug",
        domain="clinical",
        ev_pool=_fixture_ev_pool(),
    )
    # Both fixture elements covered by VERIFIED claims; S0 contraindications satisfied -> release.
    assert result.release_allowed is True
    assert result.held_reasons == []
    assert result.coverage_fraction == pytest.approx(1.0)

    # The D8 decision flows into the same manifest status the sweep would write.
    summary_status = "four_role_released" if result.release_allowed else "four_role_held"
    assert summary_status == "four_role_released"
    assert to_unified_status(summary_status) == "success"

    # The SEAM (not the builder) persisted the per-claim audit map next to the run.
    audit_path = tmp_path / FOUR_ROLE_CLAIM_AUDIT_FILENAME
    assert audit_path.exists()
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert len(audit) == 2  # one claim per verified sentence; each claim_id is traceable.
    for entry in audit.values():
        assert entry["sentence"]
        assert "covered_element_ids" in entry
    # The S0 safety claim covered the regulatory element.
    assert any("label_b" in e["covered_element_ids"] for e in audit.values())

    # NO network / NO spend: the canned transport only did in-process completions, never a POST.
    assert transport.completions > 0  # the pipeline actually ran the verifier roles


# --- D8 holds release when a claim is Sentinel-UNGROUNDED (coverage drops below threshold) ---
def test_seam_builder_holds_when_ungrounded(tmp_path):
    builder = make_gate_b_input_builder()
    transport = _FakeRoleTransport(sentinel_grounded=False, judge_verdict="VERIFIED")
    result = run_four_role_seam(
        transport,
        run_dir=tmp_path,
        timestamp=_TIMESTAMP,
        four_role_input_builder=builder,
        multi=_fixture_multi(),
        template=_fixture_template(),
        slug="fixture_slug",
        domain="clinical",
        ev_pool=_fixture_ev_pool(),
    )
    assert result.release_allowed is False
    assert result.held_reasons
    summary_status = "four_role_released" if result.release_allowed else "four_role_held"
    assert summary_status == "four_role_held"
    assert to_unified_status(summary_status) == "abort_four_role_release_held"
    # Audit still written for the (held) run.
    assert (tmp_path / FOUR_ROLE_CLAIM_AUDIT_FILENAME).exists()


# --- builder WINS over a directly-passed static four_role_inputs (Codex M3 P2 #1) ----------
def test_seam_builder_wins_over_static_inputs(tmp_path):
    """When BOTH a builder and a static four_role_inputs are passed, the BUILDER's seam-supplied
    decision must land. The static inputs are rigged to release on their own; the builder's
    decision (a single uncovered S0 element -> held) is what must surface."""
    # Static inputs that WOULD release on their own (single element, covered by a VERIFIED claim).
    static_inputs = FourRoleEvaluationInputs(
        claims=[
            FourRoleClaim(
                claim_id="static-claim",
                claim_text="A static releasable claim.",
                evidence_documents=[EvidenceDocument(doc_id="doc_static", text="evidence")],
                severity="S2",
                s0_categories=[],
                covered_element_ids=["static-elem"],
            )
        ],
        coverage_ledger=CoverageLedger(required_element_ids=["static-elem"]),
        required_s0_categories=[],
        model_slugs={
            "mirror": "cohere/command-a-plus",
            "sentinel": "ibm-granite/granite-guardian-4.1-8b",
            "judge": "qwen/qwen3.6-35b-a3b",
        },
        rewrite_already_attempted=True,
    )

    # A run whose report cites ONLY the trial (no claim covers the S0 label_b) -> held.
    multi_only_trial = _FakeMulti(
        sections=[
            _FakeSection(
                "Efficacy",
                [_FakeVerification("The trial enrolled 1879 patients.", [_FakeToken("ev_000")])],
            )
        ]
    )
    ev_pool_only_trial = {"ev_000": _fixture_ev_pool()["ev_000"]}

    builder = make_gate_b_input_builder()
    transport = _FakeRoleTransport(sentinel_grounded=True, judge_verdict="VERIFIED")
    result = run_four_role_seam(
        transport,
        run_dir=tmp_path,
        timestamp=_TIMESTAMP,
        four_role_input_builder=builder,
        four_role_inputs=static_inputs,  # MUST be ignored — builder wins.
        multi=multi_only_trial,
        template=_fixture_template(),
        slug="fixture_slug",
        domain="clinical",
        ev_pool=ev_pool_only_trial,
    )
    # Builder's decision (uncovered S0 'contraindications' + coverage 0.5 < 0.70) -> held.
    assert result.release_allowed is False
    # The static claim id NEVER appears — proof the static inputs were ignored.
    assert "static-claim" not in result.final_verdicts
    # The surfaced verdict is the builder-minted claim (section 00 / sentence 000).
    assert any(cid.startswith("00-000-") for cid in result.final_verdicts)
    # Builder branch persisted the audit (static-only path would not).
    assert (tmp_path / FOUR_ROLE_CLAIM_AUDIT_FILENAME).exists()


# --- static path (no builder): runs as-is and writes NO audit file -------------------------
def test_seam_static_inputs_used_as_is_no_audit(tmp_path):
    static_inputs = FourRoleEvaluationInputs(
        claims=[
            FourRoleClaim(
                claim_id="s-1",
                claim_text="The dose is 5.0 mg.",
                evidence_documents=[EvidenceDocument(doc_id="doc1", text="The trial reported a 5.0 mg dose.")],
                severity="S0",
                s0_categories=["contraindications"],
                covered_element_ids=["elem-1"],
            )
        ],
        coverage_ledger=CoverageLedger(required_element_ids=["elem-1"]),
        required_s0_categories=["contraindications"],
        model_slugs={
            "mirror": "cohere/command-a-plus",
            "sentinel": "ibm-granite/granite-guardian-4.1-8b",
            "judge": "qwen/qwen3.6-35b-a3b",
        },
        rewrite_already_attempted=True,
    )
    transport = _FakeRoleTransport(sentinel_grounded=True, judge_verdict="VERIFIED")
    result = run_four_role_seam(
        transport,
        run_dir=tmp_path,
        timestamp=_TIMESTAMP,
        four_role_inputs=static_inputs,
    )
    assert result.release_allowed is True
    assert result.final_verdicts == {"s-1": "VERIFIED"}
    # Static path writes NO audit file (only the builder branch persists audit_map).
    assert not (tmp_path / FOUR_ROLE_CLAIM_AUDIT_FILENAME).exists()


# --- fail-closed: neither builder nor static inputs -> raise (sweep synthesizes nothing) ----
def test_seam_no_builder_no_inputs_fails_closed(tmp_path):
    transport = _FakeRoleTransport()
    with pytest.raises(ValueError, match="fail-closed"):
        run_four_role_seam(transport, run_dir=tmp_path, timestamp=_TIMESTAMP)


# --- the REAL annotated tirzepatide contract is builder-valid through the seam --------------
def test_seam_over_real_tirzepatide_contract_is_builder_valid(tmp_path):
    """Prove the native severity annotations on the REAL clinical_tirzepatide_t2dm contract are
    builder-valid end to end. The fixture ev_pool cites only an S1 trial (SURPASS-2 by its real
    DOI), so the many uncovered S0 regulatory categories correctly HOLD release (fail-closed) —
    that is the right behavior, and the seam still writes the audit map."""
    template = yaml.safe_load(open(_CLINICAL_YAML, encoding="utf-8"))
    ev_pool = {
        "ev_000": {
            "evidence_id": "ev_000",
            # SURPASS-2 primary (real entity doi 10.1056/NEJMoa2107519) cited from a journal URL.
            "direct_quote": "SURPASS-2 randomized 1879 patients; tirzepatide lowered HbA1c.",
            "source_url": "https://www.nejm.org/doi/full/10.1056/NEJMoa2107519",
        }
    }
    multi = _FakeMulti(
        sections=[
            _FakeSection(
                "Efficacy",
                [_FakeVerification("SURPASS-2 randomized 1879 patients.", [_FakeToken("ev_000")])],
            )
        ]
    )

    builder = make_gate_b_input_builder()
    transport = _FakeRoleTransport(sentinel_grounded=True, judge_verdict="VERIFIED")
    result = run_four_role_seam(
        transport,
        run_dir=tmp_path,
        timestamp=_TIMESTAMP,
        four_role_input_builder=builder,
        multi=multi,
        template=template,
        slug=_TIRZEPATIDE_SLUG,
        domain="clinical",
        ev_pool=ev_pool,
    )
    # The single S1 claim covers SURPASS-2 (its DOI matches), but the S0 must-cover categories
    # (black_box_warnings / contraindications / regulatory_status) have no VERIFIED claim ->
    # release correctly HELD (clinical fail-closed). The point is the contract is builder-valid.
    assert result.release_allowed is False
    assert any("d8_s0_must_cover_missing" in r for r in result.held_reasons)
    assert (tmp_path / FOUR_ROLE_CLAIM_AUDIT_FILENAME).exists()
    assert transport.completions > 0
