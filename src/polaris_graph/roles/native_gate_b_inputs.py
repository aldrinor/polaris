"""Native Gate-B input builder for the 4-role evaluation (I-meta-002 PR-9 / M3a).

PURE FUNCTIONS, NO NETWORK, NO SPEND. This module turns a finished
`MultiSectionResult` + the question's NATIVE scope contract into a
`FourRoleEvaluationInputs` bundle that the sweep hands to
`run_four_role_evaluation` (sweep_integration.py). It does NO file I/O: it RETURNS a
`NativeGateBBundle` (inputs + audit_map); M3b is responsible for writing
`four_role_claim_audit.json` next to the run (Codex P2 #2).

CONTAMINATION-CRITICAL (§-1.1 LETHAL otherwise — operator-locked, NOT consultable):
This module builds every input ONLY from NATIVE config — the scope template's
`per_query_report_contract[<slug>].required_entities` and the D8 release-policy config
(`d8_config.s0_must_cover_categories`). It MUST NEVER import or read anything under
`outputs/dr_benchmark/` (gold rubric / freeze pin / competitor answers). The required-
element denominator, the claim->element coverage map, and per-claim severity all come
from native pre-registered annotations — never from the benchmark gold rubric.

Canonical-identifier note (Codex P2 #4): the frozen `EvidenceDocument`
(`role_transport.py`) carries only `doc_id` + `text`. The CANONICAL identifiers used for
coverage (DOI / PMID / full canonical URL) therefore come from the `evidence_lookup`
RECORD keyed by evidence_id. The builder's record contract is `{text, doi?, pmid?, url?}`;
M3b NORMALIZES each raw `evidence_pool.json` row (which carries `source_url` and embeds a
DOI) into that `{doi, pmid, url}` shape before calling this builder. The native scope ENTITY
declares its URL identity under `url_pattern` (clinical.yaml regulatory entities) and its
trial identity under `doi`/`pmid`. Coverage is EXACT EQUALITY per (entity-key, record-key)
pair — never substring/`in`/`startswith` — so a broad `url_pattern` FRAGMENT can never `==`
a full resolved URL and thus fails closed (P2 #4). The URL pair is ASYMMETRIC: entity
`url_pattern` vs record `url`.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Mapping

from src.polaris_graph.roles.release_policy import CoverageLedger, D8PolicyConfig
from src.polaris_graph.roles.role_transport import EvidenceDocument
from src.polaris_graph.roles.sweep_integration import (
    FourRoleClaim,
    FourRoleEvaluationInputs,
)

# --- severity vocabulary (mirrors release_policy / d8 config; never an Enum) -------------
_SEVERITY_S0 = "S0"
_SEVERITY_S1 = "S1"
_SEVERITY_S2 = "S2"
_SEVERITY_S3 = "S3"
_VALID_SEVERITIES = (_SEVERITY_S0, _SEVERITY_S1, _SEVERITY_S2, _SEVERITY_S3)
# Rank used to pick the MAX severity over the entities a claim covers (S0 strongest).
_SEVERITY_RANK = {_SEVERITY_S0: 3, _SEVERITY_S1: 2, _SEVERITY_S2: 1, _SEVERITY_S3: 0}
# A claim that covers no required entity is observe-only (S3) — never gates / never latches.
_DEFAULT_OBSERVE_ONLY_SEVERITY = _SEVERITY_S3

# --- native contract keys (read from the scope template ONLY) ----------------------------
_KEY_REPORT_CONTRACT = "per_query_report_contract"
_KEY_REQUIRED_ENTITIES = "required_entities"
_KEY_ENTITY_ID = "id"
_KEY_ENTITY_SEVERITY = "severity"
_KEY_ENTITY_S0_CATEGORY = "s0_category"
_KEY_ENTITY_CONTENT_REQS = "coverage_content_requirements"
# Canonical-identifier match pairs: (entity_key, record_key). The native scope entity
# declares its canonical URL under `url_pattern` (clinical.yaml regulatory entities) and its
# trial identity under `doi`/`pmid`; the resolved evidence RECORD carries the served `url`
# (M3b normalizes `source_url` -> `url`) plus `doi`/`pmid`. The match is EXACT EQUALITY per
# pair (P2 #4): a broad/fragment `url_pattern` can never `==` a full resolved URL, so it
# fails closed. The pairing is intentionally ASYMMETRIC (entity `url_pattern` vs record `url`).
_CANONICAL_MATCH_PAIRS = (("doi", "doi"), ("pmid", "pmid"), ("url_pattern", "url"))
# The entity-side keys the builder recognizes as a canonical identifier (used by the
# fail-loud "entity must declare a recognized identifier" guard).
_ENTITY_CANONICAL_KEYS = tuple(entity_key for entity_key, _ in _CANONICAL_MATCH_PAIRS)
_RECORD_TEXT_KEY = "text"

_WHITESPACE_RE = re.compile(r"\s+")
_CLAIM_HASH_HEX_LEN = 8


@dataclass
class NativeGateBBundle:
    """Builder output (Codex P2 #2): the sweep-ready inputs plus an audit map.

    The builder does NO file I/O — it RETURNS this bundle. M3b writes
    `four_role_claim_audit.json` from `audit_map` next to the run. `inputs` is fed
    verbatim to `run_four_role_evaluation`.
    """

    inputs: FourRoleEvaluationInputs
    audit_map: dict[str, dict]


def _normalize_sentence(sentence: str) -> str:
    """Lowercase + collapse whitespace (the basis for the deterministic claim_id hash)."""
    return _WHITESPACE_RE.sub(" ", sentence.lower()).strip()


def load_required_entities(template: dict, slug: str) -> list[dict]:
    """Return the NATIVE required entities for `slug`; fail closed if absent/empty.

    The native denominator MUST exist — a missing contract or empty entity list raises
    (never a vacuous empty-denominator pass).
    """
    contracts = template.get(_KEY_REPORT_CONTRACT)
    if not isinstance(contracts, dict) or slug not in contracts:
        raise ValueError(
            f"load_required_entities: no {_KEY_REPORT_CONTRACT}[{slug!r}] in the scope "
            f"template; the native required-element denominator must exist (fail-closed)."
        )
    entities = contracts[slug].get(_KEY_REQUIRED_ENTITIES)
    if not isinstance(entities, list) or not entities:
        raise ValueError(
            f"load_required_entities: {_KEY_REPORT_CONTRACT}[{slug!r}].{_KEY_REQUIRED_ENTITIES} "
            f"is missing or empty; cannot build a coverage denominator (fail-closed)."
        )
    return entities


def validate_entity_severity(
    entity: dict, d8_config: D8PolicyConfig
) -> tuple[str, str | None]:
    """§7.E schema-validator (FAIL CLOSED — Codex P1 iter1). Never defaults to S3.

    Returns (severity, s0_category_or_None). Raises on a missing/invalid severity, an entity
    that declares NO builder-recognized canonical identifier (doi/pmid/url_pattern — else it
    would be silently uncoverable), an S0 entity without a valid `s0_category` in the D8
    must-cover vocabulary, or an S0 entity without a non-empty `coverage_content_requirements`.
    """
    severity = entity.get(_KEY_ENTITY_SEVERITY)
    if severity not in _VALID_SEVERITIES:
        raise ValueError(
            f"validate_entity_severity: entity {entity.get(_KEY_ENTITY_ID)!r} has "
            f"severity={severity!r}; must be one of {_VALID_SEVERITIES} (NEVER default S3)."
        )
    # Every required entity MUST declare at least one canonical identifier the builder can
    # match on (doi / pmid / url_pattern). An identifier-less entity is permanently
    # uncoverable — make that a LOUD config error rather than a silent coverage loss.
    if not any(entity.get(key) for key in _ENTITY_CANONICAL_KEYS):
        raise ValueError(
            f"validate_entity_severity: entity {entity.get(_KEY_ENTITY_ID)!r} declares no "
            f"canonical identifier among {_ENTITY_CANONICAL_KEYS}; it would be permanently "
            f"uncoverable (fail-closed)."
        )
    if severity != _SEVERITY_S0:
        return severity, None

    s0_category = entity.get(_KEY_ENTITY_S0_CATEGORY)
    if not s0_category or s0_category not in d8_config.s0_must_cover_categories:
        raise ValueError(
            f"validate_entity_severity: S0 entity {entity.get(_KEY_ENTITY_ID)!r} declares "
            f"s0_category={s0_category!r} which is missing or not in the D8 must-cover "
            f"vocabulary {tuple(d8_config.s0_must_cover_categories)} (fail-closed)."
        )
    content_reqs = entity.get(_KEY_ENTITY_CONTENT_REQS)
    if not isinstance(content_reqs, list) or not content_reqs:
        raise ValueError(
            f"validate_entity_severity: S0 entity {entity.get(_KEY_ENTITY_ID)!r} has no "
            f"non-empty {_KEY_ENTITY_CONTENT_REQS}; an S0 safety category requires "
            f"deterministic content tokens to credit coverage (fail-closed)."
        )
    # Every requirement token must be a NON-BLANK string. A list like [''] or ['   '] or
    # [123] would otherwise pass the truthy-list check above and then let a bare canonical
    # citation wrongly earn S0 credit (Codex P1: never validate an S0 entity whose content
    # requirements are empty/blank/non-string after .strip()).
    for token in content_reqs:
        if not isinstance(token, str) or not token.strip():
            raise ValueError(
                f"validate_entity_severity: S0 entity {entity.get(_KEY_ENTITY_ID)!r} has a "
                f"{_KEY_ENTITY_CONTENT_REQS} element {token!r} that is not a non-blank string; "
                f"every S0 content requirement must be a real deterministic token (fail-closed)."
            )
    return severity, s0_category


def _entity_canonical_match(entity: dict, record: Mapping[str, Any]) -> bool:
    """EXACT canonical-identifier match (P2 #4): DOI / PMID / full canonical URL.

    Equality per (entity_key, record_key) pair only — never substring. The URL pair compares
    the entity's `url_pattern` against the record's resolved `url`; a broad `url_pattern`
    FRAGMENT can never equal a full resolved URL, so it fails closed.
    """
    for entity_key, record_key in _CANONICAL_MATCH_PAIRS:
        entity_value = entity.get(entity_key)
        if entity_value in (None, ""):
            continue
        record_value = record.get(record_key)
        if record_value in (None, ""):
            continue
        if str(entity_value).strip() == str(record_value).strip():
            return True
    return False


def _content_requirements_satisfied(claim_text: str, entity: dict) -> bool:
    """All `coverage_content_requirements` present in the claim (case-insensitive, exact).

    FAIL CLOSED (Codex P1): if the requirements list is empty — or somehow all-blank — return
    False rather than vacuously True. A bare canonical-evidence citation must NEVER earn S0
    credit without a real deterministic content match. (Validation in `validate_entity_severity`
    already blocks empty/blank S0 requirements at load; this is the matcher-side backstop.)
    """
    lowered = claim_text.lower()
    requirements = [
        token
        for token in entity.get(_KEY_ENTITY_CONTENT_REQS) or []
        if isinstance(token, str) and token.strip()
    ]
    if not requirements:
        return False
    return all(token.lower() in lowered for token in requirements)


def _claim_covers_entity(
    claim_evidence_records: list[Mapping[str, Any]],
    claim_text: str,
    entity: dict,
    *,
    is_s0: bool,
) -> bool:
    """Coverage test (§7.D, Codex-tightened + P2 #4).

    ENTITY coverage: True iff the claim cites evidence whose CANONICAL identifier EXACTLY
    matches the entity's. anchor-string-in-sentence alone does NOT grant coverage.

    S0 SAFETY-CATEGORY coverage (stricter): an S0 entity is covered ONLY when BOTH (a) the
    canonical evidence match holds AND (b) the claim text deterministically satisfies the
    entity's `coverage_content_requirements`. A broad source citation without the content
    match does NOT satisfy an S0 safety category.
    """
    if not any(_entity_canonical_match(entity, rec) for rec in claim_evidence_records):
        return False
    if is_s0 and not _content_requirements_satisfied(claim_text, entity):
        return False
    return True


def _resolve_evidence(
    evidence_ids: list[str], evidence_lookup: Mapping[str, Mapping[str, Any]]
) -> tuple[list[EvidenceDocument], list[Mapping[str, Any]]]:
    """Resolve each evidence_id -> (EvidenceDocument, source record); fail closed."""
    documents: list[EvidenceDocument] = []
    records: list[Mapping[str, Any]] = []
    for evidence_id in evidence_ids:
        record = evidence_lookup.get(evidence_id)
        if record is None:
            raise ValueError(
                f"build_native_gate_b_inputs: unknown evidence_id {evidence_id!r}; every "
                f"cited token must resolve to an evidence record (fail-closed)."
            )
        text = str(record.get(_RECORD_TEXT_KEY) or "").strip()
        if not text:
            raise ValueError(
                f"build_native_gate_b_inputs: evidence_id {evidence_id!r} has empty "
                f"evidence text; cannot evaluate a claim against empty evidence (fail-closed)."
            )
        documents.append(EvidenceDocument(doc_id=evidence_id, text=text))
        records.append(record)
    return documents, records


def build_native_gate_b_inputs(
    *,
    multi: Any,
    template: dict,
    slug: str,
    domain: str,
    evidence_lookup: Mapping[str, Mapping[str, Any]],
    model_slugs: dict[str, str],
    d8_config: D8PolicyConfig,
) -> NativeGateBBundle:
    """Build NATIVE 4-role Gate-B inputs from a finished report + native scope contract.

    Pure function (no I/O, no network). Returns a `NativeGateBBundle` (inputs + audit_map);
    M3b persists the audit map. NEVER reads `outputs/dr_benchmark/`. `domain` is carried for
    the audit trail / caller symmetry; the denominator comes from `template[slug]`.
    """
    entities = load_required_entities(template, slug)
    required_element_ids = [entity[_KEY_ENTITY_ID] for entity in entities]

    # Validate every entity up front (fail-closed); cache (severity, s0_category) per entity.
    validated: list[tuple[dict, str, str | None]] = []
    required_s0_categories_set: set[str] = set()
    for entity in entities:
        severity, s0_category = validate_entity_severity(entity, d8_config)
        validated.append((entity, severity, s0_category))
        if s0_category is not None:
            required_s0_categories_set.add(s0_category)

    claims: list[FourRoleClaim] = []
    audit_map: dict[str, dict] = {}
    for section_index, section in enumerate(multi.sections):
        kept = getattr(section, "kept_sentences_pre_resolve", []) or []
        sentence_index = -1
        for verification in kept:
            if not verification.is_verified:
                continue
            sentence_index += 1
            sentence = verification.sentence
            normalized = _normalize_sentence(sentence)
            digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:_CLAIM_HASH_HEX_LEN]
            claim_id = f"{section_index:02d}-{sentence_index:03d}-{digest}"

            evidence_ids = [token.evidence_id for token in verification.tokens]
            documents, records = _resolve_evidence(evidence_ids, evidence_lookup)

            covered_element_ids: list[str] = []
            covered_s0_categories: list[str] = []
            best_rank = _SEVERITY_RANK[_DEFAULT_OBSERVE_ONLY_SEVERITY]
            for entity, severity, s0_category in validated:
                is_s0 = severity == _SEVERITY_S0
                if not _claim_covers_entity(records, sentence, entity, is_s0=is_s0):
                    continue
                covered_element_ids.append(entity[_KEY_ENTITY_ID])
                best_rank = max(best_rank, _SEVERITY_RANK[severity])
                if is_s0 and s0_category is not None:
                    covered_s0_categories.append(s0_category)

            claim_severity = next(
                sev for sev, rank in _SEVERITY_RANK.items() if rank == best_rank
            )
            s0_categories = sorted(set(covered_s0_categories))

            claims.append(
                FourRoleClaim(
                    claim_id=claim_id,
                    claim_text=sentence,
                    evidence_documents=documents,
                    severity=claim_severity,
                    s0_categories=s0_categories,
                    covered_element_ids=covered_element_ids,
                )
            )
            audit_map[claim_id] = {
                "section_index": section_index,
                "section_title": getattr(section, "title", ""),
                "sentence": sentence,
                "evidence_ids": evidence_ids,
                "covered_element_ids": covered_element_ids,
                "severity": claim_severity,
                "s0_categories": s0_categories,
            }

    if not claims:
        raise ValueError(
            "build_native_gate_b_inputs: zero kept (verified) sentences; a 4-role "
            "evaluation over no claims cannot produce a release decision (fail-closed, "
            "no vacuous input)."
        )

    inputs = FourRoleEvaluationInputs(
        claims=claims,
        coverage_ledger=CoverageLedger(required_element_ids=required_element_ids),
        required_s0_categories=sorted(required_s0_categories_set),
        model_slugs=model_slugs,
        rewrite_already_attempted=False,
    )
    return NativeGateBBundle(inputs=inputs, audit_map=audit_map)
