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
import logging
import os
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Mapping

from src.polaris_graph.roles.contract_field_prefix import strip_contract_field_prefix
from src.polaris_graph.roles.release_policy import CoverageLedger, D8PolicyConfig
from src.polaris_graph.roles.role_transport import EvidenceDocument
from src.polaris_graph.roles.sweep_integration import (
    FourRoleClaim,
    FourRoleEvaluationInputs,
)

logger = logging.getLogger(__name__)

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

# --- evidence-record normalization (M3b; LOAD-BEARING, deterministic, NO network) ---------
# The raw evidence_pool.json row carries `source_url` + the evidence text under `direct_quote`
# (the field strict_verify's ProvenanceToken spans index into — see provenance_generator.py)
# with `statement` as a fallback. It carries NO doi/pmid/url keys. M3b NORMALIZES each row into
# the builder's `{text, doi?, pmid?, url?}` record contract so coverage can match the entity's
# canonical identifiers. EXACT-equality coverage (P2 #4) means the DOI/PMID must be the bare
# canonical token (e.g. `10.1056/NEJMoa2107519`, `34170647`) — never a URL-embedded fragment.
_RAW_TEXT_KEYS = ("direct_quote", "statement", "text")
_RAW_SOURCE_URL_KEYS = ("source_url", "url")
# Deterministic DOI: the canonical `10.<registrant>/<suffix>` form (CrossRef pattern).
_DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")
# Publisher URL path-suffixes appended AFTER the DOI in a landing-page URL (e.g.
# frontiersin.org/.../10.3389/fphar.2022.1016639/full). Trimmed so the extracted DOI is the
# bare canonical token that EXACTLY equals the entity's `doi` (P2 #4). Order matters: longest
# first. Trailing punctuation (a `.` or `;` lifted from prose) is also stripped.
_DOI_URL_SUFFIXES = ("/full", "/abstract", "/pdf", "/meta", "/html", "/epdf")
_DOI_TRAILING_PUNCT = ".,;)"
# Deterministic PMID: a PubMed URL path id (`pubmed.ncbi.nlm.nih.gov/<id>` or `/pubmed/<id>`)
# or an explicit `PMID: <id>` token. Bare numeric so it `==` the entity's `pmid` (int -> str).
_PMID_URL_RE = re.compile(r"(?:ncbi\.nlm\.nih\.gov/(?:pubmed|m/pubmed)?/?|/pubmed/)(\d+)")
_PMID_TOKEN_RE = re.compile(r"\bPMID:?\s*(\d+)", re.IGNORECASE)


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
    """Lowercase + collapse whitespace (the basis for the deterministic claim_id hash).

    I-deepfix-001 tail-B1 (#1344, finding #10): strip a leaked contract-field label prefix FIRST
    (e.g. an echoed ``Effect estimate with uncertainty:``) so a claim whose ONLY difference from its
    twin is that non-claim label hashes to the SAME claim_id as the twin — the drb_72 01-002 vs 01-007
    divergence. Faithfulness-neutral: only a recognized label at the very start is removed, never a
    number / citation / claim content (see ``contract_field_prefix``)."""
    return _WHITESPACE_RE.sub(" ", strip_contract_field_prefix(sentence).lower()).strip()


def _depth_synthesis_d8_gate_enabled() -> bool:
    """The depth-synthesis D8-gate flag (default ON; env ``PG_DEPTH_SYNTHESIS_D8_GATE``).

    Mirrors ``generator.depth_synthesis.depth_synthesis_d8_gate_enabled`` — the SAME env var, so the
    behavior is identical — read locally to keep this pure-roles module free of a generator import.
    OFF => the DS-* second loop no-ops and this builder is byte-identical to legacy.
    """
    return os.getenv("PG_DEPTH_SYNTHESIS_D8_GATE", "1").strip().lower() not in (
        "", "0", "false", "off", "no",
    )


def _row_text(row: Mapping[str, Any]) -> str:
    """The evidence text the strict_verify spans were validated against (first non-empty).

    Prefers `direct_quote` (the field ProvenanceToken char-spans index into), then `statement`,
    then `text`. Empty text is NOT raised here — the builder's `_resolve_evidence` fails closed
    on empty text at claim-resolution time (so an evidence row never cited stays harmless).
    """
    for key in _RAW_TEXT_KEYS:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _row_source_url(row: Mapping[str, Any]) -> str:
    """The record's full canonical source URL (verbatim), from `source_url` then `url`."""
    for key in _RAW_SOURCE_URL_KEYS:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _extract_doi(*texts: str) -> str | None:
    """Deterministic bare-DOI extraction (`10.<reg>/<suffix>`) from the given strings.

    The greedy DOI body can absorb a publisher landing-page suffix (`/full`, `/pdf`, ...) or a
    trailing punctuation mark lifted from prose. Both are deterministically trimmed so the
    returned DOI is the bare canonical token that EXACTLY equals the entity's `doi` (P2 #4);
    coverage stays fail-closed (a mis-trim simply fails to match — never over-credits).
    """
    for text in texts:
        if not text:
            continue
        match = _DOI_RE.search(text)
        if not match:
            continue
        doi = match.group(0)
        for suffix in _DOI_URL_SUFFIXES:
            if doi.endswith(suffix):
                doi = doi[: -len(suffix)]
                break
        return doi.rstrip(_DOI_TRAILING_PUNCT)
    return None


def _extract_pmid(*texts: str) -> str | None:
    """Deterministic bare-PMID extraction from a PubMed URL or an explicit `PMID:` token."""
    for text in texts:
        if not text:
            continue
        url_match = _PMID_URL_RE.search(text)
        if url_match:
            return url_match.group(1)
        token_match = _PMID_TOKEN_RE.search(text)
        if token_match:
            return token_match.group(1)
    return None


def normalize_evidence_pool_lookup(
    ev_pool: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Build the builder's `evidence_id -> {text, doi?, pmid?, url?}` lookup from a raw pool.

    DETERMINISTIC, NO NETWORK (M3b). Keys are preserved verbatim so they match the
    ProvenanceToken.evidence_id space (the same `ev_pool` keyspace the generator used). For each
    row: `url` = the record's `source_url` (full canonical URL, verbatim); `doi` = a bare DOI
    extracted by regex from the source_url then text (absent if none); `pmid` = a bare PMID from
    a PubMed URL or explicit token (absent if none); `text` = the evidence text strict_verify
    validated against (`direct_quote`/`statement`/`text`). Optional identifiers are only added
    when present so an absent identifier is genuinely absent (the builder treats `None`/`""` as
    no-match, fail-closed). Never reads `outputs/dr_benchmark/`.
    """
    lookup: dict[str, dict[str, Any]] = {}
    for evidence_id, row in ev_pool.items():
        if not isinstance(row, Mapping):
            raise ValueError(
                f"normalize_evidence_pool_lookup: evidence row {evidence_id!r} is not a mapping "
                f"({type(row).__name__}); cannot normalize a non-record (fail-closed)."
            )
        text = _row_text(row)
        url = _row_source_url(row)
        record: dict[str, Any] = {_RECORD_TEXT_KEY: text}
        if url:
            record["url"] = url
        # WS-4 (PG_ENTITY_COVERAGE_CITATION_CREDIT, default ON): a DOI-only evidence row carries the
        # canonical DOI/PMID ONLY in its STRUCTURED `doi`/`pmid` field (its `source_url` is None or
        # DOI-less) — the exact drb_72 case for entities [2]/[3]/[4]. The legacy regex-only extraction
        # below never read that structured field, so those genuinely-cited works reached
        # `_entity_canonical_match` with NO identifier and went un-covered. Under the flag, PREFER the
        # structured identifier (as the first extraction candidate) and fall back to the url/text
        # regex; OFF -> the candidate list is exactly [url, text] and the output is byte-identical.
        credit_on = _entity_coverage_citation_credit_enabled()
        doi_candidates: list[str] = []
        pmid_candidates: list[str] = []
        if credit_on:
            raw_doi = row.get(_RAW_STRUCTURED_DOI_KEY)
            if isinstance(raw_doi, str) and raw_doi.strip():
                doi_candidates.append(raw_doi)
            raw_pmid = row.get(_RAW_STRUCTURED_PMID_KEY)
            # A bare structured PMID ('34170647' or 34170647) is not matched by the PubMed-URL /
            # 'PMID:'-token regex, so wrap it as an explicit 'PMID:' token the extractor recognizes.
            if isinstance(raw_pmid, int):
                pmid_candidates.append(f"PMID: {raw_pmid}")
            elif isinstance(raw_pmid, str) and raw_pmid.strip().isdigit():
                pmid_candidates.append(f"PMID: {raw_pmid.strip()}")
        doi_candidates.extend([url, text])
        pmid_candidates.extend([url, text])
        doi = _extract_doi(*doi_candidates)
        if doi is not None:
            record["doi"] = doi
        pmid = _extract_pmid(*pmid_candidates)
        if pmid is not None:
            record["pmid"] = pmid
        # V4 (whole-basket): carry the source's declared IDENTITY (authors/year/venue/tier) so the
        # D8 adjudication input can prepend a provenance header (§-1.3 basket faithfulness). Gated so
        # an OFF run keeps the normalized record byte-identical to the pre-V4 {text, url?, doi?, pmid?}
        # shape. Additive identity only — coverage functions ignore these keys (see helper docstring).
        if _whole_basket_enabled():
            _attach_provenance_metadata(record, row)
        lookup[evidence_id] = record
    return lookup


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


# --- WS-4 (beat-both Wave B): DOI-tolerant entity coverage credit --------------------------------
# ROOT CAUSE (drb_72): a required entity that is DOI-only (bare `doi`, empty `url_pattern`) went
# UN-credited on genuinely-VERIFIED claims, so `required_entity_ledger` reported coverage_fraction
# 4/7=0.571 and listed VERIFIED entities as gaps. TWO independent gaps caused it, BOTH in this file:
#   (1) `normalize_evidence_pool_lookup` only regex-extracted a DOI from `source_url`/text and NEVER
#       read the raw record's STRUCTURED `doi`/`pmid` field. drb_72 entities [2]/[3]/[4] carry the DOI
#       ONLY in that structured field (their `source_url` is None or DOI-less), so the normalized
#       record reached `_entity_canonical_match` with NO doi at all -> no match, un-covered.
#   (2) `_entity_canonical_match` compared identifiers by RAW EXACT equality, so a DOI expressed as a
#       `https://doi.org/…` resolver URL (or in a different case) never equalled the bare-token DOI on
#       the other side even when they name the SAME work.
# Both fixes ride ONE default-ON kill-switch `PG_ENTITY_COVERAGE_CITATION_CREDIT`; OFF => the exact
# pre-WS-4 behavior, byte-identical (0.571 on the fixture). ADDITIVE ONLY: a DOI is a precise WORK
# identifier — canonical-DOI equality is NEVER a substring/fragment match (two sources sharing a DOI
# ARE the same work), so this cannot over-credit; and the D8 4-role VERIFIED filter downstream
# (sweep_integration credits `covered_element_ids` only on a VERIFIED final verdict) is untouched, so
# a NON-verified claim can never credit coverage.
_ENV_ENTITY_COVERAGE_CITATION_CREDIT = "PG_ENTITY_COVERAGE_CITATION_CREDIT"
# Default-ON off-token idiom (mirrors release_policy.always_release_enabled): OFF only on an EXPLICIT
# off token; unset / empty / unrecognized resolves to ON so the fix cannot be silently disabled by a
# stray value. Read at CALL TIME (never cached) so an OFF run is byte-identical to legacy.
_COVERAGE_CREDIT_OFF_VALUES = frozenset({"0", "false", "no", "off"})
# DOI resolver prefixes stripped to reach the bare canonical DOI token. A DOI is officially
# case-insensitive and a doi.org / dx.doi.org URL is just a resolver wrapper around the same token.
_DOI_RESOLVER_PREFIXES = (
    "https://doi.org/",
    "http://doi.org/",
    "https://dx.doi.org/",
    "http://dx.doi.org/",
)
# Structured identifier keys on the RAW evidence-pool row (read only under the flag).
_RAW_STRUCTURED_DOI_KEY = "doi"
_RAW_STRUCTURED_PMID_KEY = "pmid"


def _entity_coverage_citation_credit_enabled() -> bool:
    """``PG_ENTITY_COVERAGE_CITATION_CREDIT`` — default ON (WS-4). OFF only on an EXPLICIT off token
    ('0'/'false'/'no'/'off'); unset / empty / unrecognized -> ON. OFF reproduces the pre-WS-4
    exact-match behavior byte-identically (0.571 on the drb_72 fixture).
    """
    return (
        os.environ.get(_ENV_ENTITY_COVERAGE_CITATION_CREDIT, "").strip().lower()
        not in _COVERAGE_CREDIT_OFF_VALUES
    )


def _canonical_doi(value: Any) -> str:
    """Return the bare, lowercased canonical DOI for a value, or '' if it is not a DOI.

    Strips a doi.org / dx.doi.org resolver prefix (case-insensitive) then lowercases (DOIs are
    officially case-insensitive). Returns '' unless the remainder starts with '10.' — so a plain
    non-DOI URL / fragment / domain can NEVER masquerade as a DOI match (fail-closed: a fragment can
    never equal a full bare DOI). Precise-identifier equality, never substring — so it cannot
    over-credit.
    """
    if value in (None, ""):
        return ""
    text = str(value).strip()
    lowered = text.lower()
    for prefix in _DOI_RESOLVER_PREFIXES:
        if lowered.startswith(prefix):
            text = text[len(prefix):].strip()
            break
    text = text.lower()
    if not text.startswith("10."):
        return ""
    return text


def _entity_canonical_match(entity: dict, record: Mapping[str, Any]) -> bool:
    """EXACT canonical-identifier match (P2 #4): DOI / PMID / full canonical URL.

    Equality per (entity_key, record_key) pair only — never substring. The URL pair compares
    the entity's `url_pattern` against the record's resolved `url`; a broad `url_pattern`
    FRAGMENT can never equal a full resolved URL, so it fails closed.

    WS-4 (PG_ENTITY_COVERAGE_CITATION_CREDIT, default ON): after the exact pairs, add a DOI-CANONICAL
    tolerance leg. A DOI carried as a `https://doi.org/…` / `http://dx.doi.org/…` resolver URL — in
    the entity's `doi` OR `url_pattern`, or the record's `doi` OR `url` — or in a different case, is
    canonicalized (`_canonical_doi`: strip resolver prefix + lowercase) and matched on the bare DOI
    token. This is precise WORK-identity equality (two sources sharing a DOI ARE the same work), NOT a
    substring/fragment match, so it cannot over-credit. Flag OFF -> this leg is skipped, byte-identical
    to the exact-equality behavior.
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
    if _entity_coverage_citation_credit_enabled():
        entity_doi = _canonical_doi(entity.get("doi")) or _canonical_doi(entity.get("url_pattern"))
        if entity_doi:
            record_doi = _canonical_doi(record.get("doi")) or _canonical_doi(record.get("url"))
            if record_doi and entity_doi == record_doi:
                return True
    return False


# --- I-perm-002 (#1196): semantic contraindication credit (default OFF -> literal-exact) -----
# The CDC contraindication source for `probiotic_immunocompromised_contraindication` says probiotics
# "should be avoided for patients who ... are immunocompromised" — it NEVER uses the word
# "contraindicated". So a FAITHFUL claim grounded in that span (e.g. drb_76 claim 03-001, "not
# recommended for patients who are immunocompromised", VERIFIED + cites the exact CDC url) can never
# contain the literal token, and the S0 `contraindications` category goes un-credited -> the safety
# floor reports insufficient even though the report DID warn. PG_SWEEP_SEMANTIC_CONTRAINDICATION
# relaxes ONLY the contraindication-CONCEPT requirement token to a curated, high-precision set of
# contraindication-DIRECTION phrases; the population token (e.g. "immunocompromised") is NEVER
# relaxed — it stays the literal precision anchor that binds substance+population (R6). A
# deterministic negation guard refuses credit on any opposite-direction / negated phrase so a
# faithful-but-INVERTED claim can never earn S0 safety credit.
#
# Direction of error is deliberate: over-crediting a contraindication is §-1.1-LETHAL (a report that
# wrongly believes it warned); UNDER-crediting is a SAFE disclosed gap under always-release
# (I-perm-001). Every layer therefore errs toward refusing credit. Four independent guards stand
# between a claim and S0 credit: (1) `verification.is_verified` — only strict-verified claims reach
# the matcher; (2) `_entity_canonical_match` — the claim must cite the entity's EXACT source;
# (3) the literal population anchor; (4) this negation guard.
_ENV_SEMANTIC_CONTRAINDICATION = "PG_SWEEP_SEMANTIC_CONTRAINDICATION"
_SEMANTIC_OFF_VALUES = frozenset({"", "0", "false", "no", "off"})
# Requirement tokens that NAME the contraindication concept — only these are relaxed to synonyms.
# Both singular AND plural ("contraindications") so a future config token is also relaxed (Codex P2).
_CONTRAINDICATION_CONCEPT_TOKENS = frozenset(
    {"contraindicated", "contraindication", "contraindications"}
)
# "not recommended" warns UNLESS the "recommend AGAINST" idiom inverts it ("not recommended against
# use" == recommended FOR use). The inverting "against" can be interposed at ANY distance ("not
# recommended by the CDC source against use"), so a FIXED tail window is gameable (Codex P0-3): a
# "not recommended" occurrence counts ONLY when NO "against" follows it anywhere in the remaining
# claim text (whole-tail scan). Over-refusing a warning that merely mentions "against" downstream is
# a SAFE under-credit. Handled separately from the imperatives below, which carry no such idiom.
_RECOMMEND_DIRECTIONAL_INDICATOR = "not recommended"
_RECOMMEND_INVERTER = "against"
# DIRECTIONAL IMPERATIVES — each asserts an action-prohibition for the population ("do not give this
# to this group"). Robustly positive: each already encodes a negation/avoidance, so inverting one in
# place is unnatural — presence => contraindication direction. Bare "avoid"/"unsafe"/"risk" are
# deliberately EXCLUDED (too easily negated / ambiguous). The bare concept stem is handled separately
# below (it is a noun and far easier to invert).
_CONTRAINDICATION_DIRECTIONAL_INDICATORS = (
    "should be avoided",
    "should not be used",
    "should not be given",
    "should not be administered",
    "must not be used",
    "must not be given",
    "must not be administered",
    "not be used in",
)
# The bare contraindication CONCEPT stem (matches "contraindicated" / "contraindication(s)"). A noun
# is easily negated — BEFORE it ("no known contraindications", "not generally / clearly
# contraindicated", "need not be contraindicated", "without contraindication") or AFTER it
# ("contraindications are unknown / not established / absent"). The brittle contiguous-phrase list
# this replaces MISSED every interposed-qualifier form (Codex P0-1: it credited "CDC reports no known
# contraindications ... in immunocompromised patients"). The stem counts as a positive direction
# ONLY when NO negation context surrounds ANY occurrence — one negated mention disqualifies the stem
# signal for the whole claim (conservative = SAFE under-credit, never lethal over-credit).
_CONTRAINDICATION_STEM = "contraindicat"
# Interposition between the negator and the stem (qualifier adverbs / short clauses). Tight 20-char
# window so a SHORT inverting qualifier ("no known", "not generally") is caught while an unrelated
# distant negation ("no doubt probiotics are contraindicated") is NOT — that long form stays a credit.
_CONTRA_NEG_INTERPOSE = r"[\w\s,'()/-]{0,20}?"
_CONTRAINDICATION_NEGATION_RE = re.compile(
    # negator BEFORE the stem (contractions are expanded to `X not` first, so `\bnot\b` covers
    # aren't/isn't/haven't/etc.; "free of"/"devoid of"/"zero" are short absence forms)
    r"\b(?:no|not|never|without|none|neither|nor|lack|lacks|lacking|few|rare|rarely|absent|zero|"
    r"free\s+of|devoid\s+of|unknown|unestablished|unproven|undetermined)\b"
    + _CONTRA_NEG_INTERPOSE + _CONTRAINDICATION_STEM
    # OR a negation/absence predicate AFTER the stem
    + r"|" + _CONTRAINDICATION_STEM + r"\w*" + _CONTRA_NEG_INTERPOSE
    + r"\b(?:unknown|undetermined|unestablished|not\s+(?:been\s+)?established|absent|unclear|"
    r"unlikely|none|negligible|rare|few)\b",
    re.IGNORECASE,
)
# Negative contractions -> expanded `... not` (a SPACE before "not" so the `\bnot\b` negator fires;
# "cannot" would join the word boundary). Apostrophe is normalized to ASCII first so a curly
# right-single-quote (U+2019) in scraped prose does not defeat the lookup. Expanding ALSO helps the
# directional route ("shouldn't be used" -> "should not be used" matches the indicator). Codex P0-2:
# the pre/post regex only knew expanded forms, so `aren't contraindicated` / `haven't been
# established` over-credited.
_NEGATIVE_CONTRACTIONS = {
    "aren't": "are not", "isn't": "is not", "wasn't": "was not", "weren't": "were not",
    "haven't": "have not", "hasn't": "has not", "hadn't": "had not",
    "don't": "do not", "doesn't": "does not", "didn't": "did not",
    "won't": "will not", "wouldn't": "would not", "can't": "can not", "couldn't": "could not",
    "shouldn't": "should not", "mustn't": "must not", "needn't": "need not",
    "mightn't": "might not", "shan't": "shall not", "oughtn't": "ought not",
}


def _expand_negative_contractions(text: str) -> str:
    """Normalize the curly apostrophe to ASCII, then expand negative contractions to `X not`."""
    text = text.replace("’", "'")
    for contraction, expanded in _NEGATIVE_CONTRACTIONS.items():
        text = text.replace(contraction, expanded)
    return text


def _semantic_contraindication_enabled() -> bool:
    """``PG_SWEEP_SEMANTIC_CONTRAINDICATION`` (default OFF -> literal-exact content match)."""
    return os.environ.get(_ENV_SEMANTIC_CONTRAINDICATION, "").strip().lower() not in _SEMANTIC_OFF_VALUES


# I-perm-020 (#1212): the S0 coverage-binder activation flag. Read HERE at CALL TIME (never at import)
# so flag-OFF means the coverage_binder module is NEVER imported and the seam stays byte-identical. ON
# only on an explicit truthy token (a stray value must NOT silently enable it). The flag NAME mirrors
# `coverage_binder._ENV_S0_COVERAGE_BINDER`; this reader is duplicated (not imported) precisely so the
# OFF path never pulls the binder module.
_ENV_S0_COVERAGE_BINDER = "PG_S0_COVERAGE_BINDER"
_S0_COVERAGE_BINDER_ON_VALUES = frozenset({"1", "true", "yes", "on"})


def _s0_coverage_binder_enabled() -> bool:
    """``PG_S0_COVERAGE_BINDER`` (default OFF; explicit-truthy ON). Read at call time, no import."""
    return (
        os.environ.get(_ENV_S0_COVERAGE_BINDER, "").strip().lower()
        in _S0_COVERAGE_BINDER_ON_VALUES
    )


def _contraindication_direction_present(lowered_claim: str) -> bool:
    """True iff the claim asserts a contraindication DIRECTION for the population (not its negation).

    Three independent positive routes, all fail-closed against inversion (over-crediting a
    contraindication is §-1.1-lethal; under-crediting is a safe disclosed gap under always-release):

    1. "not recommended" — UNLESS an "against" follows it anywhere downstream (the "recommend
       against" idiom inverts it; whole-tail scan, not a gameable fixed window — Codex P0-3).
    2. A DIRECTIONAL IMPERATIVE ("should be avoided", "should not be used", ...) — no "against"-style
       in-place inverter applies, so presence => direction.
    3. The bare concept STEM ("contraindicat...") — only when NO negation context (pre OR post)
       surrounds any occurrence; a single negated mention disqualifies the stem for the whole claim.

    Negative contractions are expanded first (`aren't` -> `are not`) so the guard is not defeated by
    contraction spelling (Codex P0-2).
    """
    lowered_claim = _expand_negative_contractions(lowered_claim)
    start = lowered_claim.find(_RECOMMEND_DIRECTIONAL_INDICATOR)
    while start != -1:
        tail = lowered_claim[start + len(_RECOMMEND_DIRECTIONAL_INDICATOR):]
        if _RECOMMEND_INVERTER not in tail:
            return True
        start = lowered_claim.find(_RECOMMEND_DIRECTIONAL_INDICATOR, start + 1)
    if any(indicator in lowered_claim for indicator in _CONTRAINDICATION_DIRECTIONAL_INDICATORS):
        return True
    if _CONTRAINDICATION_STEM in lowered_claim and not _CONTRAINDICATION_NEGATION_RE.search(
        lowered_claim
    ):
        return True
    return False


def _content_requirements_satisfied_impl(
    claim_text: str, entity: dict, *, semantic: bool
) -> bool:
    """Shared content-requirement matcher with an EXPLICIT semantic flag (no env read).

    All `coverage_content_requirements` present in the claim (case-insensitive, exact). FAIL CLOSED
    (Codex P1): if the requirements list is empty — or somehow all-blank — return False rather than
    vacuously True. A bare canonical-evidence citation must NEVER earn S0 credit without a real
    deterministic content match. (Validation in `validate_entity_severity` already blocks empty/blank
    S0 requirements at load; this is the matcher-side backstop.)

    I-perm-002 (#1196): when `semantic` is True, a requirement token that NAMES the contraindication
    concept ("contraindicated"/"contraindication(s)") is satisfied by any high-precision
    contraindication-DIRECTION phrase (negation-guarded); every OTHER token (e.g. "immunocompromised")
    stays literal-exact. `semantic=False` -> byte-identical literal-exact match. The semantic decision
    is taken by the CALLER (the public `_content_requirements_satisfied` reads the
    PG_SWEEP_SEMANTIC_CONTRAINDICATION env flag; the I-perm-020 coverage_binder forces it True), so this
    impl never reads the environment — keeping the credit policy at the call sites, not buried here.
    """
    lowered = claim_text.lower()
    requirements = [
        token
        for token in entity.get(_KEY_ENTITY_CONTENT_REQS) or []
        if isinstance(token, str) and token.strip()
    ]
    if not requirements:
        return False
    for token in requirements:
        token_lower = token.lower()
        if semantic and token_lower in _CONTRAINDICATION_CONCEPT_TOKENS:
            if not _contraindication_direction_present(lowered):
                return False
        elif token_lower not in lowered:
            return False
    return True


def _content_requirements_satisfied(claim_text: str, entity: dict) -> bool:
    """All `coverage_content_requirements` present in the claim (case-insensitive, exact).

    Thin wrapper over `_content_requirements_satisfied_impl` that takes the semantic decision from the
    `PG_SWEEP_SEMANTIC_CONTRAINDICATION` env flag (default OFF -> byte-identical literal-exact match).
    Behavior is unchanged from the pre-refactor function: OFF reads identical, ON relaxes ONLY the
    contraindication concept token to a negation-guarded direction phrase.
    """
    return _content_requirements_satisfied_impl(
        claim_text, entity, semantic=_semantic_contraindication_enabled()
    )


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


# FX-03 / I-ready-017 (#1107): the 4-role seam (Sentinel decomposition + Judge) joins each
# EvidenceDocument.text as the SPAN the claim is checked against. Pre-FX-03 the WHOLE record text
# was passed, so a claim could be graded VERIFIED on support living ANYWHERE in the document, not
# in the cited [start:end] window (BUG-02: confirmed out-of-span false-accept, claim 06-004).
_GATE_B_CITED_SPAN_ENV = "PG_GATE_B_CITED_SPAN"
_GATE_B_SPAN_WINDOW_ENV = "PG_GATE_B_SPAN_WINDOW_BYTES"
_GATE_B_SPAN_WINDOW_DEFAULT = 400

# I-perm-022 (#1214): normalize the cited SPAN text BEFORE the four-role second evaluators
# (Sentinel decomposition + Judge) read it, so a PDF-extraction LIGATURE does not flip a
# genuinely-supported atom to "unsupported" (a false negative surfaced as [confidence:low]).
#
# LIGATURE-ONLY is the ONLY §-1.1-safe span repair. A Latin presentation-form ligature is a
# SINGLE codepoint that decomposes to a FIXED letter sequence with NO word-boundary change, so
# it can neither join nor split words and therefore cannot fabricate support on a genuine
# negative — it only renders the codepoint as the letters an LLM evaluator should have read.
# De-hyphenation and zero-width handling were DELIBERATELY DROPPED as §-1.1-UNSAFE (Codex
# brief-gate iter-2 P1): any JOIN ("re-\nsigned" -> "resigned"; "not<ZWSP>able" -> "notable")
# or SPLIT ("in<ZWSP>effective" -> "in effective") changes meaning and can make an unsupported
# claim appear present. ZERO digit modification (ligature codepoints carry no digits).
_GATE_B_SPAN_NORMALIZE_ENV = "PG_GATE_B_SPAN_NORMALIZE"
# DERIVE the ligature->letters map from Unicode NFKD (the authoritative compatibility
# decomposition), NOT a hand-typed table — a hand value can be wrong (e.g. U+FB05 LONG-S-T
# decomposes to "st", not "ft"; mis-typing it would fabricate "loft" from "lost", Codex
# brief-gate iter-3 P1). Only codepoints whose NFKD is pure ASCII letters are kept, so a
# ligature is ALWAYS replaced by its exact letters with NO word-boundary change.
_LIGATURE_MAP = {
    chr(cp): unicodedata.normalize("NFKD", chr(cp))
    for cp in range(0xFB00, 0xFB07)  # FB00..FB06: ff fi fl ffi ffl st st
    if unicodedata.normalize("NFKD", chr(cp)).isascii()
    and unicodedata.normalize("NFKD", chr(cp)).isalpha()
}
_LIGATURE_RE = re.compile("[" + "".join(_LIGATURE_MAP) + "]")


def _span_normalize_enabled() -> bool:
    return os.getenv(_GATE_B_SPAN_NORMALIZE_ENV, "0").strip() == "1"


def _normalize_span_text(text: str) -> str:
    """Repair ONLY Latin presentation-form ligatures (U+FB00..U+FB06) in a cited span:
    each is a single codepoint -> its canonical letters, with NO word-boundary change and
    ZERO digit modification. Flag OFF (default) -> input returned unchanged (byte-identical).
    I-perm-022 (#1214)."""
    if not _span_normalize_enabled() or not text:
        return text
    return _LIGATURE_RE.sub(lambda m: _LIGATURE_MAP[m.group(0)], text)


# --- V4 (I-deepfix-001): whole-basket D8 adjudication input (§-1.3 BASKET FAITHFULNESS) ---------
# ROOT CAUSE (drb_72): the D8 four-role seam (Sentinel decomposition + Judge) adjudicates a claim
# against ONLY the bare cited-span text of each cited source, stripped of that source's PROVENANCE
# identity. A claim's ATTRIBUTION atom ("Frey and Osborne developed a novel methodology ...") is
# then marked `unsupported` by the Sentinel because the abstract SPAN self-references in the first
# person ("We examine ...") and never re-names its own authors -> the Sentinel returns UNGROUNDED
# -> the LOCKED `_compose_final_verdict` step-2 override downgrades a Judge VERIFIED to UNSUPPORTED
# (measured: claim 01-008 frey_osborne_computerisation). The source RECORD, however, literally
# carries `authors: ['Frey C', 'Osborne M']` — the attribution IS grounded in the cited work's OWN
# declared identity, part of its basket, that the bare span throws away.
#
# FIX (§-1.3 BASKET FAITHFULNESS — decide a claim against its WHOLE basket, never a single bare
# span): the adjudication input for EACH cited source in the claim's basket carries that source's
# DECLARED PROVENANCE IDENTITY (authors / year / venue / doi) as a bounded, clearly-labeled header
# PREPENDED to its FX-03 cited-span window. An attribution / identity atom then grounds against the
# source's real authorship, recovering the single-span false-negative. The verdict CARRIES the
# basket corroboration (source count + tier weights) in the audit_map.
#
# STRENGTHENS, ADMITS NOTHING UNVERIFIED (the binding safety argument, faithfulness-CRITICAL):
#   * The header carries ONLY bibliographic IDENTITY (WHO wrote it, WHEN, WHERE, its DOI) — NEVER
#     the source TITLE and NEVER any body/abstract prose. It can therefore ground a WHO/WHEN/WHERE
#     attribution atom, but it carries NO factual/effect assertion, so it can NEVER ground a WHAT
#     (numeric / mechanism / effect) atom. A claim whose FACTS are unsupported by the cited span
#     still fails — the body window is UNCHANGED (FX-03 / BUG-02 out-of-span defense preserved
#     byte-for-byte; only an identity header is prepended, the window bytes are untouched).
#   * The header shows the source's TRUE authors, so a MIS-attribution (a claim naming an author
#     the source does not have) still fails closed — the header can only ground a TRUE attribution.
#   * A source that declares NO provenance identity yields an EMPTY header -> the adjudication input
#     is byte-identical to the bare span (no fabricated grounding, no vacuous credit).
# Default-ON kill-switch `PG_GATE_B_WHOLE_BASKET`; OFF -> byte-identical to the pre-V4 bare-span seam.
_GATE_B_WHOLE_BASKET_ENV = "PG_GATE_B_WHOLE_BASKET"
_WHOLE_BASKET_OFF_TOKENS = ("0", "false", "no", "off")
# Structured metadata keys carried from the raw evidence row into the normalized record so the header
# builder can read them. IDENTITY ONLY (never `title`, never `direct_quote`/`statement` body). `tier`
# is carried for the corroboration WEIGHT surfaced in the audit_map, NOT for the header text.
_PROVENANCE_HEADER_LABEL = "cited source provenance"


def _whole_basket_enabled() -> bool:
    """``PG_GATE_B_WHOLE_BASKET`` — default ON (V4). OFF only on an EXPLICIT off token
    ('0'/'false'/'no'/'off'); unset / empty / unrecognized -> ON. Read at CALL TIME (LAW VI) so a
    slate/test override after import wins. OFF -> byte-identical to the pre-V4 bare-span seam."""
    return os.getenv(_GATE_B_WHOLE_BASKET_ENV, "1").strip().lower() not in _WHOLE_BASKET_OFF_TOKENS


def _format_authors(authors: Any) -> str:
    """Render the record's `authors` field to a compact identity string, or '' if none.

    Accepts a list/tuple of names (the evidence-pool shape, e.g. ['Frey C', 'Osborne M']) or a bare
    string; drops blanks. This is a WHO identity string, never a factual assertion."""
    if isinstance(authors, str):
        return authors.strip()
    if isinstance(authors, (list, tuple)):
        return ", ".join(str(a).strip() for a in authors if str(a).strip())
    return ""


def _provenance_header(record: Mapping[str, Any]) -> str:
    """Build the bounded, labeled source-IDENTITY header for the whole-basket adjudication input.

    Carries WHO (authors) / WHEN (year) / WHERE (venue) / doi ONLY — NEVER the title, NEVER body
    prose. Returns '' when the record declares no identity, so the adjudication input stays
    byte-identical to the bare cited span (fail-safe: no fabricated grounding). See the module V4
    note for the full faithfulness-CRITICAL safety argument: an identity-only header can ground a
    WHO/WHEN/WHERE attribution atom but never a WHAT (numeric/mechanism/effect) atom."""
    parts: list[str] = []
    authors = _format_authors(record.get("authors"))
    if authors:
        parts.append(f"authors: {authors}")
    year = record.get("year")
    if year not in (None, "", []):
        parts.append(f"year: {str(year).strip()}")
    venue = record.get("journal")
    if isinstance(venue, str) and venue.strip():
        parts.append(f"venue: {venue.strip()}")
    doi = record.get("doi")
    if isinstance(doi, str) and doi.strip():
        parts.append(f"doi: {doi.strip()}")
    if not parts:
        return ""
    return f"[{_PROVENANCE_HEADER_LABEL} | " + " | ".join(parts) + "]"


def _attach_provenance_metadata(record: dict, row: Mapping[str, Any]) -> None:
    """Carry the source's declared IDENTITY (authors / year / venue / tier) from the raw row into the
    normalized record so the whole-basket adjudication input can build a provenance header.

    ADDITIVE IDENTITY ONLY — never body text, never the title. `doi` is already extracted upstream by
    the existing regex/structured path (the header reads that same `record['doi']`). `tier` is carried
    for the corroboration WEIGHT surfaced in the audit_map, not for the header. The coverage functions
    (`_entity_canonical_match` / `_claim_covers_entity`) read only doi/pmid/url + text, so these extra
    keys can NEVER affect entity coverage. Gated by the caller under `PG_GATE_B_WHOLE_BASKET` so an OFF
    run keeps the normalized record byte-identical to the pre-V4 shape."""
    authors = row.get("authors")
    if isinstance(authors, (list, tuple)) and any(str(a).strip() for a in authors):
        record["authors"] = [str(a).strip() for a in authors if str(a).strip()]
    elif isinstance(authors, str) and authors.strip():
        record["authors"] = authors.strip()
    year = row.get("year")
    if year not in (None, "", []):
        record["year"] = year
    journal = row.get("journal")
    if isinstance(journal, str) and journal.strip():
        record["journal"] = journal.strip()
    tier = row.get("tier")
    if isinstance(tier, str) and tier.strip():
        record["tier"] = tier.strip()


def _cited_window_text(full_text: str, token: Any) -> str:
    """Return the cited BOUNDED-WINDOW slice of ``full_text`` for one provenance token.

    When ``PG_GATE_B_CITED_SPAN=1`` the evidence text handed to Sentinel/Judge is sliced to a
    bounded window around the cited ``[start:end]`` range (±``PG_GATE_B_SPAN_WINDOW_BYTES``, default
    400) — the SAME tolerance strict_verify's local-window rescue uses, so the two faithfulness
    layers share ONE windowing policy. BOUNDED (not exact-slice) is deliberate and three-fold safer:
    (1) it tolerates the 06-004-shape imprecise-but-real citation that strict_verify also tolerates;
    (2) ``token.start/end`` index the RAW ``direct_quote`` while the record text here was
    ``_row_text``-STRIPPED, so an exact slice would be offset-shifted by any leading whitespace —
    a bounded window absorbs that small shift; (3) fail-SAFE — a degenerate/empty window falls back
    to the whole text so the judge is never handed a blank span. Flag off (default) returns the whole
    text unchanged (byte-identical), so production is opt-in per the no-silent-downgrade rule; the
    re-run slate activates it.
    """
    if os.getenv(_GATE_B_CITED_SPAN_ENV, "0").strip() != "1":
        return full_text
    try:
        start = int(getattr(token, "start"))
        end = int(getattr(token, "end"))
    except (TypeError, ValueError, AttributeError):
        return full_text
    if end <= start:
        return full_text
    try:
        window = int(os.getenv(_GATE_B_SPAN_WINDOW_ENV, str(_GATE_B_SPAN_WINDOW_DEFAULT)))
    except ValueError:
        window = _GATE_B_SPAN_WINDOW_DEFAULT
    window = max(0, window)
    lo = max(0, start - window)
    hi = min(len(full_text), end + window)
    sliced = full_text[lo:hi].strip()
    return sliced or full_text


def _resolve_evidence(
    tokens: list[Any], evidence_lookup: Mapping[str, Mapping[str, Any]]
) -> tuple[list[EvidenceDocument], list[Mapping[str, Any]]]:
    """Resolve each cited token -> (EvidenceDocument sliced to its cited window, source record).

    FX-03 (#1107): one EvidenceDocument per TOKEN, carrying the bounded cited-window slice (see
    ``_cited_window_text``) instead of the whole record text, so Sentinel/Judge see the SPAN the
    decomposition prompt promises. Fail closed on an unknown id or empty record text.
    """
    documents: list[EvidenceDocument] = []
    records: list[Mapping[str, Any]] = []
    for token in tokens:
        evidence_id = token.evidence_id
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
        # FX-03 body window (UNCHANGED — the out-of-span/BUG-02 defense is preserved byte-for-byte).
        window_text = _normalize_span_text(_cited_window_text(text, token))
        # V4 (whole-basket, §-1.3): PREPEND the cited source's declared PROVENANCE IDENTITY header so
        # an attribution / identity atom grounds against the source's real authorship (recovering the
        # single-span false-negative), while the WHAT (factual/effect) atoms still judge against the
        # UNCHANGED body window. Empty header (record declares no identity) or flag OFF -> the text is
        # byte-identical to the bare span. See the module V4 note for the faithfulness-CRITICAL safety
        # argument (identity-only: never grounds a factual atom, shows the TRUE authors so a
        # misattribution still fails).
        if _whole_basket_enabled():
            header = _provenance_header(record)
            if header:
                window_text = f"{header}\n{window_text}"
        documents.append(EvidenceDocument(doc_id=evidence_id, text=window_text))
        records.append(record)
    return documents, records


def _section_is_gap_stub(section: Any) -> bool:
    """I-deepfix-001 (Codex grpC iter2 P1): True when a section is a rendered gap
    disclosure stub (the BB5-C07 / F10 / U24-withheld paths, and the fact-dedup
    re-resolve at multi_section_generator.py that sets is_gap_stub=True while leaving
    kept_sentences_pre_resolve populated). A gap stub renders ONLY the marker-less stub
    sentence — a non-claim — so it must contribute ZERO verified claims to the binding
    D8 four-role gate. Primary signal: the ``is_gap_stub`` flag (always set on gap stubs).
    Fallback for any section object predating the flag: a gap stub carries zero verified
    sentences AND an empty pre-resolve kept list, in which case it contributes nothing
    regardless. This SKIP only EXCLUDES withheld claims from the D8 INPUT; the frozen D8
    four-role verification logic is untouched.
    """
    if bool(getattr(section, "is_gap_stub", False)):
        return True
    kept = getattr(section, "kept_sentences_pre_resolve", None)
    verified = getattr(section, "sentences_verified", None)
    return verified == 0 and kept is not None and len(kept) == 0


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
        # I-deepfix-001 (Codex grpC iter2 P1): SKIP gap-stub sections. A gap stub renders
        # only the marker-less gap-disclosure stub (a non-claim); feeding its (withheld)
        # sentences into the binding D8 four-role gate would re-admit claims that never
        # reached the render — a faithfulness hole. Defense-in-depth alongside the
        # source-side zeroing in multi_section_generator._run_section (which clears
        # kept_sentences_pre_resolve for the U24-withheld case); keying off is_gap_stub also
        # covers the downstream fact-dedup re-resolve path (which sets is_gap_stub=True while
        # leaving kept_sentences_pre_resolve populated). `continue` (not renumber) preserves
        # section_index for the surviving sections. The frozen D8 engine is UNTOUCHED — this
        # only EXCLUDES withheld claims from its INPUT (it strengthens faithfulness).
        if _section_is_gap_stub(section):
            continue
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
            # FX-03 (#1107): pass the TOKENS (carrying start/end), not just the ids — _resolve_evidence
            # slices each EvidenceDocument.text to the cited bounded window so the seam judges the
            # claim against the cited SPAN, not the whole source doc (BUG-02 out-of-span false-accept).
            # evidence_ids is retained above for the audit_map trail.
            documents, records = _resolve_evidence(verification.tokens, evidence_lookup)

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

            # I-perm-020 (#1212): S0 coverage binder. AFTER per-claim verification (these are the
            # strict_verify-VERIFIED sentences, `verification.is_verified` is the loop guard above),
            # credit a required S0 SAFETY category whose entity this VERIFIED claim satisfies via the
            # FULL I-perm-002 conjunction (canonical evidence match + population anchor +
            # contraindication DIRECTION + negation guard, semantic recognition forced ON inside the
            # binder). Fixes the measured drb_76 false hold (a faithful "not recommended for the
            # immunocompromised" contraindication that the literal-token era left un-credited). DEFAULT
            # OFF: the `PG_S0_COVERAGE_BINDER` flag is read at CALL TIME here (never at import); when OFF
            # the binder module is NEVER imported and NEVER called, so `covered_s0_categories` /
            # `covered_element_ids` / `best_rank` are byte-identical to legacy. The credit is an
            # idempotent set-UNION (harmless if the existing literal path or
            # PG_SWEEP_SEMANTIC_CONTRAINDICATION already credited the same category) and is STILL gated
            # downstream by the 4-role `verdict==VERIFIED` check in release_policy — additive credit, NOT
            # a gate relaxation. The D8 threshold and the release rule are untouched. A bound element is
            # an S0 entity by construction, so it also raises `best_rank` to S0 (a claim that earns an S0
            # category is an S0 claim — keeping severity coherent with s0_categories, exactly as the
            # native loop above promotes severity when it covers an S0 entity).
            if _s0_coverage_binder_enabled():
                from src.polaris_graph.roles.coverage_binder import bind_s0_coverage

                bound_categories, bound_element_ids = bind_s0_coverage(
                    claim_text=sentence,
                    claim_evidence_records=records,
                    validated_entities=validated,
                )
                for category in bound_categories:
                    if category not in covered_s0_categories:
                        covered_s0_categories.append(category)
                for element_id in bound_element_ids:
                    if element_id not in covered_element_ids:
                        covered_element_ids.append(element_id)
                if bound_element_ids:
                    best_rank = max(best_rank, _SEVERITY_RANK[_SEVERITY_S0])

            # WS-4 (PG_ENTITY_COVERAGE_CITATION_CREDIT, default ON): basket-membership FALLBACK credit.
            # AFTER the native canonical-match loop (this is a strict_verify-VERIFIED sentence — the
            # `verification.is_verified` guard above), credit GENERAL entity coverage when this claim
            # cites an evidence_id that is a SUPPORTS member of an entity's OWN basket (the coverage_
            # binder owns the SUPPORTS-only rule; a REFUTES/NEUTRAL member never credits). This handles
            # the case where a VERIFIED claim supports a required entity through a corroborating source
            # whose OWN canonical identifier differs from the entity's declared one. It touches ONLY
            # `covered_element_ids` (the completeness/coverage fraction) and `best_rank` — it NEVER adds
            # a `covered_s0_categories` credit, so the frozen S0 SAFETY floor (which reads s0_categories,
            # gated by the FULL content conjunction) is untouched. Additive + still D8-gated: the D8
            # coverage numerator credits `covered_element_ids` only on a VERIFIED 4-role final verdict
            # (sweep_integration), so a non-verified claim can never credit. DEFAULT ON but a no-op until
            # upstream attaches a SUPPORTS basket to the entity (the caller's wiring); flag OFF -> the
            # binder is never imported and `covered_element_ids` is byte-identical to legacy.
            if _entity_coverage_citation_credit_enabled():
                from src.polaris_graph.roles.coverage_binder import bind_basket_coverage

                basket_covered_ids = bind_basket_coverage(
                    claim_evidence_ids=evidence_ids,
                    validated_entities=validated,
                )
                if basket_covered_ids:
                    _severity_by_id = {
                        entity[_KEY_ENTITY_ID]: severity for entity, severity, _ in validated
                    }
                    for element_id in basket_covered_ids:
                        if element_id not in covered_element_ids:
                            covered_element_ids.append(element_id)
                            best_rank = max(
                                best_rank, _SEVERITY_RANK[_severity_by_id[element_id]]
                            )

            claim_severity = next(
                sev for sev, rank in _SEVERITY_RANK.items() if rank == best_rank
            )
            s0_categories = sorted(set(covered_s0_categories))

            claims.append(
                FourRoleClaim(
                    claim_id=claim_id,
                    # finding #10: the D8 ENTAILMENT input is the claim with any leaked contract-field
                    # label prefix stripped, so a prefixed twin and its clean twin are judged on the
                    # SAME text and cannot settle to divergent verdicts. audit_map["sentence"] keeps the
                    # RAW rendered form for report.md redaction location (below).
                    claim_text=strip_contract_field_prefix(sentence),
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
            # V4 (whole-basket, §-1.3): the verdict CARRIES the basket corroboration — how many
            # distinct sources support the claim (count) and their credibility tier weights. This is
            # a DISCLOSED side-output on the audit row only; it never gates and never relaxes the
            # faithfulness engine. Gated by the flag so an OFF run's audit_map is byte-identical.
            if _whole_basket_enabled():
                audit_map[claim_id]["basket_source_count"] = len(evidence_ids)
                audit_map[claim_id]["basket_weights"] = [
                    str(rec.get("tier"))
                    for rec in records
                    if isinstance(rec, Mapping) and rec.get("tier")
                ]

    # I-deepfix-001 wave-3 (conclusion true-drop) — thread the grounded DEPTH cross-source findings
    # into the SAME 4-role D8 gate the section claims pass. Each finding becomes ONE S3/observe-only
    # DS-* claim so D8 JUDGES the synthesized sentence itself (Mirror/Sentinel/Judge); a non-VERIFIED
    # depth finding is then DROPPED from report.md by the post-seam depth reconcile (TRUE drop-not-
    # sink). RELEASE-NEUTRAL by construction: severity S3 (non-material — never latches / never gates),
    # covered_element_ids=[] (the fixed required denominator + the coverage fraction are unchanged),
    # s0_categories=[] (the S0 must-cover gate is untouched). The DS-* claim_id namespace never
    # collides with the section ``NN-NNN`` ids. Gated on PG_DEPTH_SYNTHESIS_D8_GATE (default ON); OFF
    # or no synthesized_findings => this block no-ops (claims/audit_map byte-identical to legacy). An
    # audit_map row is written for EVERY rendered finding (even one whose evidence fails to resolve),
    # so a finding that could not be JUDGED is caught fail-closed by the depth reconcile
    # ("is_synthesized in audit_map but absent from final_verdicts => drop"). Honors the module
    # contamination invariant: the finding text + tokens come from the generator's own report, and
    # evidence is resolved against the SAME ``evidence_lookup`` the section loop uses — never the gold
    # rubric. The >=2 distinct-origin floor + cross/single tier split live upstream and are untouched.
    synthesized_findings = getattr(multi, "synthesized_findings", None) or []
    if synthesized_findings and _depth_synthesis_d8_gate_enabled():
        for ds_index, finding in enumerate(synthesized_findings):
            if not isinstance(finding, Mapping):
                continue
            rendered_sentence = str(finding.get("sentence", "") or "").strip()
            if not rendered_sentence:
                continue  # nothing rendered in report.md -> nothing to gate / drop
            audit_sentence = str(finding.get("audit_sentence", "") or "").strip()
            tokens = list(finding.get("tokens", None) or [])
            ds_evidence_ids = [token.evidence_id for token in tokens]
            ds_normalized = _normalize_sentence(audit_sentence or rendered_sentence)
            ds_digest = hashlib.sha256(ds_normalized.encode("utf-8")).hexdigest()[:_CLAIM_HASH_HEX_LEN]
            ds_claim_id = f"DS-{ds_index:03d}-{ds_digest}"
            # The audit_map row is ALWAYS written first (marks is_synthesized + the RENDERED [N]
            # sentence that is in report.md) so the depth reconcile can LOCATE + DROP it. "sentence"
            # is the rendered form (report.md has [N], not [#ev:...]); the D8 claim_text below is the
            # PRE-resolve audit sentence (carries [#ev:...] tokens), mirroring the section claims.
            audit_map[ds_claim_id] = {
                "sentence": rendered_sentence,
                "evidence_ids": ds_evidence_ids,
                "severity": _DEFAULT_OBSERVE_ONLY_SEVERITY,
                "is_synthesized": True,
                "tier": finding.get("tier"),
            }
            # A finding missing its D8 inputs (audit sentence / tokens) cannot be JUDGED — leave it out
            # of the claim set; the fail-closed depth reconcile (unjudged is_synthesized => drop)
            # removes it from report.md so it never ships un-D8-gated.
            if not audit_sentence or not tokens:
                continue
            try:
                ds_documents, _ds_records = _resolve_evidence(tokens, evidence_lookup)
            except Exception as ds_exc:  # noqa: BLE001 — evidence/lookup mismatch: drop the CLAIM, keep
                # the audit row so the fail-closed depth reconcile removes the rendered finding. NEVER
                # fabricate an unresolved-evidence claim; NEVER crash the whole builder for one finding.
                logger.warning(
                    "[native_gate_b] depth finding %s evidence resolution failed (%s); "
                    "no D8 claim built -> fail-closed depth reconcile will drop it",
                    ds_claim_id, ds_exc,
                )
                continue
            claims.append(
                FourRoleClaim(
                    claim_id=ds_claim_id,
                    claim_text=audit_sentence,
                    evidence_documents=ds_documents,
                    severity=_DEFAULT_OBSERVE_ONLY_SEVERITY,
                    s0_categories=[],
                    covered_element_ids=[],
                )
            )

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
