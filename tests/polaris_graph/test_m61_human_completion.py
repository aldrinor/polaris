"""M-61 tests: V30 hybrid human/licensed completion (Path B).

Layer 4d. Operator-provided direct_quote content for entities
that M-56 couldn't retrieve. Codex plan review #6 required
structured provenance (not free-text consent_proof).

All tests pure — no network, no LLM.

Covers:
1. parse_completion — well-formed + 8 required-field failures.
2. StructuredProvenance — enumerated source_type, hex sha256,
   ISO-8601 acquired_at with timezone.
3. load_completions — JSON file load + record parse.
4. validate_against_tasks — entity_id match, DOI match,
   unmatched rejection, DOI substitution rejection.
5. to_frame_rows — produces FrameRow with human_curated
   quote_source + artifact_retention_path url threading.
6. compute_artifact_sha256 — canonical utility.
7. compose_methods_disclosure_human_curated — count disclosure.
8. Entity-type-agnostic — statute and dft_primary completions
   work identically.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from src.polaris_graph.retrieval.frame_fetcher import ProvenanceClass
from src.polaris_graph.retrieval.human_gap_completion import (
    HUMAN_CURATED_PROVENANCE,
    CompletionSchemaError,
    HumanCompletionRecord,
    StructuredProvenance,
    compose_methods_disclosure_human_curated,
    compute_artifact_sha256,
    load_completions,
    parse_completion,
    to_frame_rows,
    validate_against_tasks,
)


# ─────────────────────────────────────────────────────────────────────
# Fixture helpers
# ─────────────────────────────────────────────────────────────────────
def _good_provenance(**overrides: Any) -> dict[str, Any]:
    base = {
        "curator_id": "operator@institution",
        "source_type": "licensed_institutional_access",
        "source_locator": "10.1016/S0140-6736(21)01443-4 pp.1811-1824",
        "acquired_at": "2026-04-23T12:00:00+00:00",
        "artifact_sha256": "a" * 64,
        "artifact_retention_path": "/audit/retained/surpass4.pdf",
        "quote_page_range": "p.1812",
        "attestation": (
            "I hereby certify that I accessed the source via my "
            "institutional licensed subscription on 2026-04-23."
        ),
    }
    base.update(overrides)
    return base


def _good_completion(
    entity_id: str = "surpass_4_primary",
    doi: str | None = "10.1016/S0140-6736(21)01443-4",
    quote: str = (
        "In SURPASS-4, 1995 adults with T2D received tirzepatide "
        "or insulin degludec. Primary endpoint met at 52 weeks."
    ),
    source_span: str | None = None,
    provenance_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prov = _good_provenance(**(provenance_overrides or {}))
    return {
        "entity_id": entity_id,
        "doi": doi,
        "direct_quote": quote,
        "source_span": source_span,
        "provenance": prov,
    }


# ─────────────────────────────────────────────────────────────────────
# (1) parse_completion — happy path
# ─────────────────────────────────────────────────────────────────────
class TestParseCompletionHappy:
    def test_well_formed_completion(self) -> None:
        record = parse_completion(_good_completion(), 0)
        assert isinstance(record, HumanCompletionRecord)
        assert record.entity_id == "surpass_4_primary"
        assert record.doi == "10.1016/S0140-6736(21)01443-4"
        assert "SURPASS-4" in record.direct_quote
        assert record.provenance.curator_id == "operator@institution"
        assert record.provenance.source_type == "licensed_institutional_access"
        assert record.provenance.artifact_sha256 == "a" * 64

    def test_doi_null_accepted(self) -> None:
        """Entities without DOI (statute, URL-only regulatory) may
        have doi=null."""
        record = parse_completion(_good_completion(doi=None), 0)
        assert record.doi is None

    def test_source_span_optional(self) -> None:
        record = parse_completion(
            _good_completion(source_span=None), 0,
        )
        assert record.source_span is None

        record2 = parse_completion(
            _good_completion(source_span="specific passage"), 0,
        )
        assert record2.source_span == "specific passage"

    def test_acquired_at_with_z_suffix(self) -> None:
        record = parse_completion(
            _good_completion(provenance_overrides={
                "acquired_at": "2026-04-23T12:00:00Z"
            }),
            0,
        )
        assert record.provenance.acquired_at == "2026-04-23T12:00:00Z"


# ─────────────────────────────────────────────────────────────────────
# (2) parse_completion — required field failures
# ─────────────────────────────────────────────────────────────────────
class TestParseCompletionFailures:
    def test_missing_entity_id_raises(self) -> None:
        bad = _good_completion()
        del bad["entity_id"]
        with pytest.raises(CompletionSchemaError) as exc:
            parse_completion(bad, 0)
        assert "entity_id" in exc.value.reason

    def test_empty_direct_quote_raises(self) -> None:
        bad = _good_completion(quote="")
        with pytest.raises(CompletionSchemaError) as exc:
            parse_completion(bad, 0)
        assert "direct_quote" in exc.value.reason

    def test_missing_provenance_raises(self) -> None:
        bad = _good_completion()
        del bad["provenance"]
        with pytest.raises(CompletionSchemaError) as exc:
            parse_completion(bad, 0)
        # Codex plan review #6: free-text consent_proof must be
        # rejected
        assert "free-text consent_proof" in exc.value.reason
        assert "structured" in exc.value.reason.lower()

    def test_provenance_missing_any_required_field_raises(self) -> None:
        required_fields = [
            "curator_id", "source_type", "source_locator",
            "acquired_at", "artifact_sha256",
            "artifact_retention_path", "quote_page_range",
            "attestation",
        ]
        for field_name in required_fields:
            bad = _good_completion()
            del bad["provenance"][field_name]
            with pytest.raises(CompletionSchemaError) as exc:
                parse_completion(bad, 0)
            assert field_name in exc.value.reason, (
                f"missing field {field_name} should be named in error"
            )

    def test_invalid_source_type_raises(self) -> None:
        bad = _good_completion(
            provenance_overrides={"source_type": "sketchy_pdf"},
        )
        with pytest.raises(CompletionSchemaError) as exc:
            parse_completion(bad, 0)
        assert "source_type" in exc.value.reason
        assert "allowed set" in exc.value.reason

    def test_short_sha256_raises(self) -> None:
        bad = _good_completion(
            provenance_overrides={"artifact_sha256": "a" * 32},
        )
        with pytest.raises(CompletionSchemaError) as exc:
            parse_completion(bad, 0)
        assert "artifact_sha256" in exc.value.reason
        assert "64 hex" in exc.value.reason

    def test_non_hex_sha256_raises(self) -> None:
        bad = _good_completion(
            provenance_overrides={"artifact_sha256": "Z" * 64},
        )
        with pytest.raises(CompletionSchemaError):
            parse_completion(bad, 0)

    def test_naive_datetime_raises(self) -> None:
        """Codex-level defense: naive datetime is ambiguous for
        audit. Require timezone-aware ISO-8601."""
        bad = _good_completion(
            provenance_overrides={"acquired_at": "2026-04-23T12:00:00"},
        )
        with pytest.raises(CompletionSchemaError) as exc:
            parse_completion(bad, 0)
        assert "acquired_at" in exc.value.reason

    def test_malformed_datetime_raises(self) -> None:
        bad = _good_completion(
            provenance_overrides={"acquired_at": "yesterday"},
        )
        with pytest.raises(CompletionSchemaError) as exc:
            parse_completion(bad, 0)
        assert "acquired_at" in exc.value.reason

    def test_non_utc_timezone_raises(self) -> None:
        """Codex M-61 audit Nit: docstring says UTC but earlier
        implementation accepted any timezone-aware offset. Fix
        enforces UTC specifically."""
        bad = _good_completion(
            provenance_overrides={
                "acquired_at": "2026-04-23T12:00:00+05:00",
            },
        )
        with pytest.raises(CompletionSchemaError) as exc:
            parse_completion(bad, 0)
        assert "UTC" in exc.value.reason

    def test_legacy_consent_proof_rejected(self) -> None:
        """Codex M-61 audit Medium: schema closed against legacy
        free-text channels. Passing `consent_proof` (even alongside
        a valid provenance object) is rejected."""
        bad = _good_completion()
        bad["consent_proof"] = "operator-certified; trust me"
        with pytest.raises(CompletionSchemaError) as exc:
            parse_completion(bad, 0)
        assert "consent_proof" in exc.value.reason or \
               "unknown keys" in exc.value.reason

    def test_unknown_provenance_key_rejected(self) -> None:
        bad = _good_completion()
        bad["provenance"]["sneaky_field"] = "something"
        with pytest.raises(CompletionSchemaError) as exc:
            parse_completion(bad, 0)
        assert "unknown keys" in exc.value.reason.lower()

    def test_other_source_type_requires_justification(self) -> None:
        """Codex M-61 audit Medium: source_type='other' MUST
        carry other_justification. The allowlist pressure valve
        needs an audit hook."""
        bad = _good_completion(
            provenance_overrides={"source_type": "other"},
        )
        with pytest.raises(CompletionSchemaError) as exc:
            parse_completion(bad, 0)
        assert "other_justification" in exc.value.reason

    def test_other_source_type_with_justification_accepted(self) -> None:
        good = _good_completion(
            provenance_overrides={
                "source_type": "other",
                "other_justification": (
                    "Source obtained via interlibrary loan with "
                    "licensed institutional partnership."
                ),
            },
        )
        record = parse_completion(good, 0)
        assert record.provenance.source_type == "other"
        assert "interlibrary" in record.provenance.other_justification

    def test_other_justification_on_non_other_source_type_rejected(self) -> None:
        """other_justification is only allowed when
        source_type='other'."""
        bad = _good_completion(
            provenance_overrides={
                "other_justification": "spurious extra field",
            },
        )
        with pytest.raises(CompletionSchemaError) as exc:
            parse_completion(bad, 0)
        assert "unknown keys" in exc.value.reason.lower()


# ─────────────────────────────────────────────────────────────────────
# (3) load_completions — file IO
# ─────────────────────────────────────────────────────────────────────
class TestLoadCompletions:
    def test_load_valid_file(self, tmp_path: Path) -> None:
        completions_data = [
            _good_completion(),
            _good_completion(entity_id="surpass_cvot_primary",
                              doi="10.1056/NEJMoa2509079"),
        ]
        p = tmp_path / "completions.json"
        p.write_text(json.dumps(completions_data), encoding="utf-8")

        records = load_completions(p)
        assert len(records) == 2
        assert records[0].entity_id == "surpass_4_primary"
        assert records[1].entity_id == "surpass_cvot_primary"

    def test_load_non_array_root_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.json"
        p.write_text('{"entity_id": "x"}', encoding="utf-8")
        with pytest.raises(ValueError) as exc:
            load_completions(p)
        assert "JSON array" in str(exc.value)

    def test_load_record_error_names_index(self, tmp_path: Path) -> None:
        # Second record is malformed
        data = [_good_completion(), {"entity_id": "x"}]
        p = tmp_path / "mixed.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(CompletionSchemaError) as exc:
            load_completions(p)
        # Error record_index is 1
        assert exc.value.record_index == 1


# ─────────────────────────────────────────────────────────────────────
# (4) validate_against_tasks — cross-check
# ─────────────────────────────────────────────────────────────────────
class TestValidateAgainstTasks:
    def test_matching_completion_accepted(self) -> None:
        tasks = [{
            "entity_id": "surpass_4_primary",
            "doi": "10.1016/S0140-6736(21)01443-4",
        }]
        completions = (
            parse_completion(_good_completion(), 0),
        )
        result = validate_against_tasks(completions, tasks)
        assert len(result.accepted) == 1
        assert len(result.rejected) == 0

    def test_unmatched_entity_id_rejected(self) -> None:
        tasks = [{
            "entity_id": "surpass_4_primary",
            "doi": "10.1016/S0140-6736(21)01443-4",
        }]
        bogus = parse_completion(
            _good_completion(entity_id="invented_trial"),
            0,
        )
        result = validate_against_tasks((bogus,), tasks)
        assert len(result.accepted) == 0
        assert len(result.rejected) == 1
        record, reason = result.rejected[0]
        assert record.entity_id == "invented_trial"
        assert "no task exists" in reason

    def test_doi_substitution_rejected(self) -> None:
        """Codex plan review #6: operator cannot substitute
        content from a different paper by matching entity_id but
        different DOI."""
        tasks = [{
            "entity_id": "surpass_4_primary",
            "doi": "10.1016/S0140-6736(21)01443-4",
        }]
        wrong_doi = parse_completion(
            _good_completion(doi="10.1111/different_paper.2020"),
            0,
        )
        result = validate_against_tasks((wrong_doi,), tasks)
        assert len(result.accepted) == 0
        assert len(result.rejected) == 1
        _, reason = result.rejected[0]
        assert "doi mismatch" in reason.lower()

    def test_doi_omission_bypass_rejected(self) -> None:
        """Codex M-61 audit Blocker 1: DOI omission is no longer
        a valid bypass. task.doi present + completion.doi=None is
        rejected."""
        tasks = [{
            "entity_id": "surpass_4_primary",
            "doi": "10.1016/S0140-6736(21)01443-4",
        }]
        no_doi = parse_completion(
            _good_completion(doi=None),
            0,
        )
        result = validate_against_tasks((no_doi,), tasks)
        assert len(result.accepted) == 0
        assert len(result.rejected) == 1
        _, reason = result.rejected[0]
        assert "omitting DOI" in reason

    def test_completion_doi_added_when_task_none_rejected(self) -> None:
        """Codex M-61 audit Blocker 1 symmetric: task has no DOI,
        completion adds one — reject. Operator cannot add DOI
        binding where the contract doesn't require it."""
        tasks = [{"entity_id": "statute_42_usc_1983", "doi": None}]
        with_doi = parse_completion(
            _good_completion(
                entity_id="statute_42_usc_1983",
                doi="10.9999/added_by_operator",
            ),
            0,
        )
        result = validate_against_tasks((with_doi,), tasks)
        assert len(result.accepted) == 0
        _, reason = result.rejected[0]
        assert "no DOI" in reason

    def test_duplicate_completion_rejected(self) -> None:
        """Codex M-61 audit Blocker 3: only one completion per
        entity. Duplicates are rejected (audit integrity — the
        in-memory map keyed by entity_id must not be ambiguous)."""
        tasks = [{
            "entity_id": "surpass_4_primary",
            "doi": "10.1016/S0140-6736(21)01443-4",
        }]
        c1 = parse_completion(_good_completion(), 0)
        c2 = parse_completion(_good_completion(), 1)
        result = validate_against_tasks((c1, c2), tasks)
        assert len(result.accepted) == 1
        assert len(result.rejected) == 1
        _, reason = result.rejected[0]
        assert "duplicate completion" in reason

    def test_both_null_doi_accepted(self) -> None:
        """For entities without DOI (statute etc.), both task and
        completion having doi=None is the only valid match."""
        tasks = [{"entity_id": "statute_42_usc_1983", "doi": None}]
        record = parse_completion(
            _good_completion(
                entity_id="statute_42_usc_1983", doi=None,
            ),
            0,
        )
        result = validate_against_tasks((record,), tasks)
        assert len(result.accepted) == 1


# ─────────────────────────────────────────────────────────────────────
# (5) to_frame_rows — pipeline integration
# ─────────────────────────────────────────────────────────────────────
class TestToFrameRows:
    def test_frame_row_carries_permanent_human_curated_marker(self) -> None:
        """Codex M-61 audit Blocker 2 fix: provenance_class is
        now HUMAN_CURATED (new enum value), not ABSTRACT_ONLY.
        The marker is permanent across downstream handoffs."""
        accepted = (
            parse_completion(_good_completion(), 0),
        )
        metadata = {
            "surpass_4_primary": {
                "rendering_slot": "efficacy_surpass_4",
                "entity_type": "pivotal_trial",
            }
        }
        rows = to_frame_rows(accepted, metadata)
        assert len(rows) == 1
        row = rows[0]
        # Blocker 2 fix: provenance_class enum is HUMAN_CURATED
        assert row.provenance_class == ProvenanceClass.HUMAN_CURATED
        # Legacy quote_source marker still set (back-compat)
        assert row.quote_source == HUMAN_CURATED_PROVENANCE
        # Artifact retention path threaded to url for audit
        assert row.url == "/audit/retained/surpass4.pdf"
        # Content rendered as-is from operator
        assert "SURPASS-4" in row.direct_quote
        assert row.entity_id == "surpass_4_primary"
        assert row.rendering_slot == "efficacy_surpass_4"
        assert row.entity_type == "pivotal_trial"
        # Retrieval attempt log is empty (this wasn't retrieved)
        assert row.retrieval_attempts == ()

    def test_frame_row_carries_structured_provenance_dict(self) -> None:
        """Codex M-61 audit Blocker 3 fix: every
        StructuredProvenance field survives the FrameRow boundary
        via human_curated_provenance dict."""
        accepted = (
            parse_completion(_good_completion(), 0),
        )
        metadata = {
            "surpass_4_primary": {
                "rendering_slot": "efficacy_surpass_4",
                "entity_type": "pivotal_trial",
            }
        }
        rows = to_frame_rows(accepted, metadata)
        prov = rows[0].human_curated_provenance
        assert prov is not None
        # All 8 required fields present
        assert prov["curator_id"] == "operator@institution"
        assert prov["source_type"] == "licensed_institutional_access"
        assert "surpass4" in prov["source_locator"].lower() or \
               "0140-6736" in prov["source_locator"]
        assert prov["acquired_at"] == "2026-04-23T12:00:00+00:00"
        assert prov["artifact_sha256"] == "a" * 64
        assert prov["artifact_retention_path"] == "/audit/retained/surpass4.pdf"
        assert prov["quote_page_range"] == "p.1812"
        assert "institutional licensed subscription" in prov["attestation"]

    def test_non_human_rows_have_no_provenance(self) -> None:
        """Sanity: FrameRow.human_curated_provenance defaults to
        None for rows that didn't come from M-61."""
        from src.polaris_graph.retrieval.frame_fetcher import FrameRow
        row = FrameRow(
            entity_id="x", entity_type="t", rendering_slot="s",
            provenance_class=ProvenanceClass.ABSTRACT_ONLY,
            direct_quote="abstract", quote_source="crossref_abstract",
            doi="10.1/x", pmid=None, oa_pdf_url=None, url=None,
            title=None, authors=(), journal=None, year=None,
            failure_reason=None,
        )
        assert row.human_curated_provenance is None


# ─────────────────────────────────────────────────────────────────────
# (6) compute_artifact_sha256 utility
# ─────────────────────────────────────────────────────────────────────
class TestArtifactSha256:
    def test_matches_hashlib(self) -> None:
        content = b"retained PDF bytes"
        expected = hashlib.sha256(content).hexdigest()
        assert compute_artifact_sha256(content) == expected
        assert len(compute_artifact_sha256(content)) == 64


# ─────────────────────────────────────────────────────────────────────
# (7) Methods disclosure
# ─────────────────────────────────────────────────────────────────────
class TestMethodsDisclosure:
    def test_no_human_curated(self) -> None:
        text = compose_methods_disclosure_human_curated(
            n_retrieved=46, n_human_curated=0,
        )
        assert "46 retrieved" in text
        assert "0 human-curated" in text

    def test_with_human_curated(self) -> None:
        text = compose_methods_disclosure_human_curated(
            n_retrieved=46, n_human_curated=3,
        )
        assert "46 retrieved" in text
        assert "3 human-curated" in text
        # Codex M-61 audit Medium: "licensed or attested" since
        # allowed source_type includes author_communication +
        # other-with-justification, not strictly subscription
        assert "licensed or attested sources" in text
        assert "artifact_sha256" in text
        # Codex M-61 audit Blocker 2: the permanent provenance
        # class name is surfaced so readers know where to look
        assert "human_curated" in text


# ─────────────────────────────────────────────────────────────────────
# (8) Entity-type-agnostic (Codex rev #7)
# ─────────────────────────────────────────────────────────────────────
class TestEntityTypeAgnostic:
    def test_statute_completion(self) -> None:
        record = parse_completion(
            _good_completion(
                entity_id="statute_42_usc_1983",
                doi=None,  # statutes don't have DOIs
                quote="42 U.S.C. § 1983 provides civil remedy.",
            ),
            0,
        )
        assert record.entity_id == "statute_42_usc_1983"
        assert record.doi is None

    def test_dft_completion(self) -> None:
        record = parse_completion(
            _good_completion(
                entity_id="dft_smith_2024",
                quote="Band gap calculated as 1.42 eV using PBE.",
            ),
            0,
        )
        assert "Band gap" in record.direct_quote
