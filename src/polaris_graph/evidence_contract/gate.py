"""Evidence Contract Gate enforcement (I-ecg-002).

Given a (contract, pool, report) triple, evaluate whether the report
addresses every contract expectation. Pure function; no I/O.

`assert_generation_has_contract` is the IMPORT-time guarantee: callers
that try to run generation without a contract get a structured refusal.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from polaris_graph.evidence_contract.schema import EvidenceContract, Jurisdiction
from polaris_graph.clinical_generator.provenance import extract_tokens
from polaris_graph.clinical_generator.verified_report import VerifiedReport
from polaris_graph.clinical_retrieval.evidence_pool import EvidencePool, Source, SourceTier

JURISDICTION_DOMAINS: dict[Jurisdiction, frozenset[str]] = {
    Jurisdiction.CA: frozenset({"canada.ca", "gc.ca", "cochrane.org", "hc-sc.gc.ca"}),
    Jurisdiction.US: frozenset({"fda.gov", "nih.gov", "cdc.gov", "nlm.nih.gov"}),
    Jurisdiction.EU: frozenset({"ema.europa.eu", "efsa.europa.eu", "europa.eu"}),
    Jurisdiction.UK: frozenset({"nice.org.uk", "gov.uk", "mhra.gov.uk"}),
    Jurisdiction.GLOBAL: frozenset({"who.int", "cochrane.org"}),
}


class ContractRequiredError(Exception):
    """Raised when generation is invoked without an EvidenceContract."""


class GateVerdict(BaseModel):
    """Outcome of evaluating a report against its evidence contract.

    `passed` is True iff `failures` is empty. Each failure is a structured
    `reason:detail` code (e.g. `entity_not_covered:...`,
    `insufficient_t1_sources:...`). `contract_id`/`report_id` identify the
    evaluated pair.
    """

    passed: bool
    failures: list[str] = Field(default_factory=list)
    contract_id: str
    report_id: str


def assert_generation_has_contract(
    contract: EvidenceContract | None, *, report_id: str | None = None
) -> None:
    """Guarantee a contract is present before generation proceeds.

    A no-op when `contract` is provided; raises `ContractRequiredError` when it
    is None so callers cannot run generation without a contract. `report_id`, if
    given, is included in the error message for traceability.
    """
    if contract is None:
        raise ContractRequiredError(
            f"Evidence Contract required: generation cannot proceed without a contract"
            f"{f' (report_id={report_id!r})' if report_id else ''}"
        )


def _kept_sentence_texts(report: VerifiedReport) -> list[str]:
    out: list[str] = []
    for section in report.sections:
        if section.section_status == "dropped":
            continue
        for sentence in section.verified_sentences:
            if sentence.verifier_pass:
                out.append(sentence.sentence_text.lower())
    return out


def _sentence_cited_ids(sentence) -> set[str]:
    ids: set[str] = set()
    for tok in extract_tokens(sentence.sentence_text):
        ids.add(tok.source_id)
    for raw in sentence.provenance_tokens:
        for tok in extract_tokens(raw):
            ids.add(tok.source_id)
    return ids


def _cited_sources(report: VerifiedReport, pool: EvidencePool) -> list[Source]:
    cited_ids: set[str] = set()
    for section in report.sections:
        if section.section_status == "dropped":
            continue
        for sentence in section.verified_sentences:
            if not sentence.verifier_pass:
                continue
            cited_ids |= _sentence_cited_ids(sentence)
    return [s for s in pool.sources if s.source_id in cited_ids]


def _claim_covering_sources(
    report: VerifiedReport, pool: EvidencePool, claim_statement_lower: str
) -> list[Source]:
    """Sources cited by sentences whose text contains the claim statement substring."""
    cited_ids: set[str] = set()
    for section in report.sections:
        if section.section_status == "dropped":
            continue
        for sentence in section.verified_sentences:
            if not sentence.verifier_pass:
                continue
            if claim_statement_lower in sentence.sentence_text.lower():
                cited_ids |= _sentence_cited_ids(sentence)
    return [s for s in pool.sources if s.source_id in cited_ids]


def _domain_matches_jurisdiction(domain: str, jurisdiction: Jurisdiction) -> bool:
    domain_lower = domain.lower()
    return any(
        domain_lower == d or domain_lower.endswith("." + d)
        for d in JURISDICTION_DOMAINS.get(jurisdiction, frozenset())
    )


def evaluate_contract(
    contract: EvidenceContract, pool: EvidencePool, report: VerifiedReport
) -> GateVerdict:
    """Evaluate whether a report satisfies every expectation in the contract.

    Checks that each expected entity and claim is covered by kept, verifier-
    passing sentences, that each claim's required jurisdictions are backed by a
    citing source in a matching domain, and that cited-source tier counts meet
    the contract's minimum coverage. Pure function (no I/O).

    Returns:
        A `GateVerdict` whose `passed` is True only when no expectation failed;
        otherwise `failures` lists every unmet expectation as a structured code.
    """
    failures: list[str] = []
    sentence_texts = _kept_sentence_texts(report)
    blob = " ".join(sentence_texts)
    cited = _cited_sources(report, pool)

    for entity in contract.expected_entities:
        names = [entity.name.lower()] + [a.lower() for a in entity.aliases if a.strip()]
        if not any(n in blob for n in names if n):
            failures.append(f"entity_not_covered:{entity.name}")

    for claim in contract.expected_claims:
        statement_lower = claim.statement.lower()
        if not any(statement_lower in t for t in sentence_texts):
            failures.append(f"claim_not_covered:{claim.claim_id}")
        claim_sources = _claim_covering_sources(report, pool, statement_lower)
        for jurisdiction in claim.required_jurisdictions:
            if not any(_domain_matches_jurisdiction(s.domain, jurisdiction) for s in claim_sources):
                failures.append(
                    f"jurisdiction_not_covered:{claim.claim_id}:{jurisdiction.value}"
                )

    cov = contract.expected_source_coverage
    counts = {SourceTier.T1: 0, SourceTier.T2: 0, SourceTier.T3: 0}
    for s in cited:
        counts[s.tier] += 1
    if counts[SourceTier.T1] < cov.tier_t1_min:
        failures.append(f"insufficient_t1_sources:{counts[SourceTier.T1]}<{cov.tier_t1_min}")
    if counts[SourceTier.T2] < cov.tier_t2_min:
        failures.append(f"insufficient_t2_sources:{counts[SourceTier.T2]}<{cov.tier_t2_min}")
    if counts[SourceTier.T3] < cov.tier_t3_min:
        failures.append(f"insufficient_t3_sources:{counts[SourceTier.T3]}<{cov.tier_t3_min}")

    return GateVerdict(
        passed=not failures,
        failures=failures,
        contract_id=contract.contract_id,
        report_id=report.report_id,
    )
