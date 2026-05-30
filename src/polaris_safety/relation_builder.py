"""Deterministic scenario-family relation-builder for Gate A cluster adjustment.

Implements the LOCKED spec
`state/polaris_statistical_contract/v3_4_phase_0a_0/0a-1C_metadata_schema_relation_builder_spec.md`:

- §2.1 pairwise relation rule (criteria 1-5, OR, deduplicated), base relations
  over ALL unordered pairs (full lookup table incl. cross-stratum).
- §2.2 per-stratum pairwise DEFF = 1 + 2 * P_S * rho / N_S, where P_S counts
  related pairs with BOTH claims in stratum S.
- §2.3 determinism: float-free Jaccard, dedup-before-Jaccard, UTC inclusive 24h
  boundary, pairwise-not-transitive, fail-closed on null relation-input fields.
- §2.4 per-stratum output schema (stratum, N, P, rho, DEFF, n_eff, within-stratum
  max/p95 degree).

`rho` (ICC ceiling) is a parameter, contract default 0.10 (LAW VI: no hard-coding).
The builder is pure: it operates on parsed manifest rows (dicts), no I/O.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Iterable

# Contract default ICC ceiling (0a.-1.D §2 / contract §3.2). Caller may override
# (e.g. after the §4.4 surrogate-ICC escalation). Never assumed silently.
DEFAULT_ICC_CEILING = 0.10

# Criterion-3 construction-window correlation horizon, in seconds (24h inclusive).
WINDOW_24H_SECONDS = 24 * 60 * 60

# The five §3.4 pairwise-relation criteria (stable identifiers).
CRITERION_SAME_REPORT = "same_report"
CRITERION_EVIDENCE_JACCARD = "evidence_jaccard_ge_0.5"
CRITERION_SAME_TEMPLATE_SME_24H = "same_template_sme_24h"
CRITERION_SAME_PROMPT_FAMILY = "same_prompt_family"
CRITERION_MICROTOPIC_STRATUM_PLUS = "microtopic_stratum_plus"

# The valid severity strata (severity_stratum_manifest enum). A value outside
# this set RAISES (§2.3 fail-closed; matches severity_stratum_manifest.schema.json).
_VALID_STRATA = frozenset({"S0", "S1", "S2", "SUPPORTED"})

# Relation-input fields, typed for fail-closed validation (§2.3). Each is checked
# for presence + non-null; string fields additionally must be non-empty; the
# window field must be an int; list fields must be lists (may be empty).
# A violation RAISES — the builder never treats it as "unrelated".
_CONSTRUCTION_STRING_FIELDS = (
    "claim_id",
    "source_report_id",
    "sme_template_id",
    "constructor_sme_id",
    "generator_prompt_family_id",
    "verifier_prompt_family_id",
    "evidence_packet_id",
)
_CONSTRUCTION_LIST_FIELDS = ("claim_cited_source_ids", "microtopic_tags")
_CONSTRUCTION_INT_FIELDS = ("construction_window_start",)
_PACKET_STRING_FIELDS = ("evidence_packet_id", "packet_class")
_PACKET_LIST_FIELDS = ("canonical_source_ids",)
_STRATUM_STRING_FIELDS = ("claim_id", "severity_stratum")


class RelationInputError(ValueError):
    """Raised when a relation-input field is missing/null (§2.3 fail-closed)."""


@dataclass(frozen=True)
class StratumSummary:
    """Per-stratum DEFF summary (§2.4 locked output schema).

    `relation_table_sha256` + `input_manifest_sha256s` are denormalized onto each
    row (same value across a run) so every summary row is self-describing for the
    0a.-1.E custody audit. `input_manifest_sha256s` is a sorted tuple of
    (manifest_name, sha256) pairs (hashable; equals a dict semantically).
    """

    stratum: str
    n: int
    p: int
    rho: float
    deff: float
    n_eff: float
    max_claim_degree: int
    p95_claim_degree: int
    relation_table_sha256: str
    input_manifest_sha256s: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class RelationResult:
    """Builder output: the full pairwise lookup table + per-stratum summaries."""

    pairwise_relations: list[dict] = field(default_factory=list)
    stratum_summaries: list[StratumSummary] = field(default_factory=list)


def _row_label(row: dict) -> str:
    return repr(row.get("claim_id") or row.get("evidence_packet_id"))


def _require_non_empty_strings(row: dict, fields: tuple[str, ...], kind: str) -> None:
    for name in fields:
        if name not in row or row[name] is None:
            raise RelationInputError(f"{kind} row missing/null field {name!r}: {_row_label(row)}")
        if not isinstance(row[name], str) or not row[name]:
            raise RelationInputError(
                f"{kind} field {name!r} must be a non-empty string, got {row[name]!r}: {_row_label(row)}"
            )


def _require_lists(row: dict, fields: tuple[str, ...], kind: str) -> None:
    for name in fields:
        if name not in row or row[name] is None:
            raise RelationInputError(f"{kind} row missing/null field {name!r}: {_row_label(row)}")
        if not isinstance(row[name], list):
            raise RelationInputError(
                f"{kind} field {name!r} must be a list, got {type(row[name]).__name__}: {_row_label(row)}"
            )


def _require_ints(row: dict, fields: tuple[str, ...], kind: str) -> None:
    for name in fields:
        if name not in row or row[name] is None:
            raise RelationInputError(f"{kind} row missing/null field {name!r}: {_row_label(row)}")
        # bool is a subclass of int — reject it explicitly (a flag is not a timestamp).
        if not isinstance(row[name], int) or isinstance(row[name], bool):
            raise RelationInputError(
                f"{kind} field {name!r} must be an int, got {row[name]!r}: {_row_label(row)}"
            )


def _canonical_sha256(rows: list[dict]) -> str:
    """Deterministic SHA256 of a manifest (canonical JSON of rows sorted by id)."""
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def jaccard_ge_half(set_a: set[str], set_b: set[str]) -> bool:
    """§2.3: criterion-2 Jaccard >= 0.5, float-free via 2*|∩| >= |∪|.

    Empty union (both sets empty) -> Jaccard defined as 0 -> False (§4 0a.-1.D).
    """
    union = set_a | set_b
    if not union:
        return False
    inter = set_a & set_b
    return 2 * len(inter) >= len(union)


def jaccard_in_criterion5_band(set_a: set[str], set_b: set[str]) -> bool:
    """§2.3: criterion-5 evidence overlap in [0.2, 0.5), float-free.

    5*|∩| >= |∪|  (>= 0.2)  AND  2*|∩| < |∪|  (< 0.5). Empty union -> False.
    """
    union = set_a | set_b
    if not union:
        return False
    inter = set_a & set_b
    return (5 * len(inter) >= len(union)) and (2 * len(inter) < len(union))


def _cited_set(construction_row: dict) -> set[str]:
    """Claim-level cited canonical_source_id set (dedup-before-Jaccard, §2.3)."""
    return set(construction_row["claim_cited_source_ids"])


def pair_related(
    row_i: dict,
    row_j: dict,
    packet_class_by_id: dict[str, str],
) -> list[str]:
    """Return the sorted list of §3.4 criteria matched for an unordered pair.

    Empty list => not related. Deduplicated: each criterion appears at most once
    (the relation is OR over criteria; we record which fired).
    """
    matched: set[str] = set()

    # Criterion 1: same source report.
    if row_i["source_report_id"] == row_j["source_report_id"]:
        matched.add(CRITERION_SAME_REPORT)

    set_i = _cited_set(row_i)
    set_j = _cited_set(row_j)

    # Criterion 2: evidence Jaccard >= 0.5.
    if jaccard_ge_half(set_i, set_j):
        matched.add(CRITERION_EVIDENCE_JACCARD)

    # Criterion 3: same SME template, same constructor, within 24h (inclusive).
    if (
        row_i["sme_template_id"] == row_j["sme_template_id"]
        and row_i["constructor_sme_id"] == row_j["constructor_sme_id"]
        and abs(row_i["construction_window_start"] - row_j["construction_window_start"])
        <= WINDOW_24H_SECONDS
    ):
        matched.add(CRITERION_SAME_TEMPLATE_SME_24H)

    # Criterion 4: same prompt family (generator OR verifier).
    if (
        row_i["generator_prompt_family_id"] == row_j["generator_prompt_family_id"]
        or row_i["verifier_prompt_family_id"] == row_j["verifier_prompt_family_id"]
    ):
        matched.add(CRITERION_SAME_PROMPT_FAMILY)

    # Criterion 5: shared microtopic AND same severity stratum AND >=1 of
    # {shared template (any time), shared packet class, evidence-Jaccard [0.2,0.5)}.
    shared_microtopic = bool(set(row_i["microtopic_tags"]) & set(row_j["microtopic_tags"]))
    same_stratum = row_i["_severity_stratum"] == row_j["_severity_stratum"]
    if shared_microtopic and same_stratum:
        shared_template = row_i["sme_template_id"] == row_j["sme_template_id"]
        shared_packet_class = (
            packet_class_by_id[row_i["evidence_packet_id"]]
            == packet_class_by_id[row_j["evidence_packet_id"]]
        )
        evidence_band = jaccard_in_criterion5_band(set_i, set_j)
        if shared_template or shared_packet_class or evidence_band:
            matched.add(CRITERION_MICROTOPIC_STRATUM_PLUS)

    return sorted(matched)


def _index_rows(
    packets: list[dict],
    severity: list[dict],
    construction: list[dict],
) -> tuple[list[dict], dict[str, str]]:
    """Validate + join inputs. Returns construction rows annotated with stratum,
    sorted by claim_id (determinism §2.3), and a packet_class lookup.

    Fail-closed (§2.3): rejects missing/null/empty/wrong-type fields, invalid
    severity strata, AND duplicate manifest IDs (a silent overwrite would corrupt
    the join), in addition to dangling references.
    """
    packet_class_by_id: dict[str, str] = {}
    for prow in packets:
        _require_non_empty_strings(prow, _PACKET_STRING_FIELDS, "source_packet_manifest")
        _require_lists(prow, _PACKET_LIST_FIELDS, "source_packet_manifest")
        pid = prow["evidence_packet_id"]
        if pid in packet_class_by_id:
            raise RelationInputError(f"duplicate evidence_packet_id in source_packet_manifest: {pid!r}")
        packet_class_by_id[pid] = prow["packet_class"]

    stratum_by_claim: dict[str, str] = {}
    for srow in severity:
        _require_non_empty_strings(srow, _STRATUM_STRING_FIELDS, "severity_stratum_manifest")
        if srow["severity_stratum"] not in _VALID_STRATA:
            raise RelationInputError(
                f"invalid severity_stratum {srow['severity_stratum']!r} "
                f"(must be one of {sorted(_VALID_STRATA)}): claim {srow['claim_id']!r}"
            )
        claim_id = srow["claim_id"]
        if claim_id in stratum_by_claim:
            raise RelationInputError(f"duplicate claim_id in severity_stratum_manifest: {claim_id!r}")
        stratum_by_claim[claim_id] = srow["severity_stratum"]

    seen_claims: set[str] = set()
    annotated: list[dict] = []
    for crow in construction:
        _require_non_empty_strings(crow, _CONSTRUCTION_STRING_FIELDS, "construction_manifest")
        _require_lists(crow, _CONSTRUCTION_LIST_FIELDS, "construction_manifest")
        _require_ints(crow, _CONSTRUCTION_INT_FIELDS, "construction_manifest")
        claim_id = crow["claim_id"]
        if claim_id in seen_claims:
            raise RelationInputError(f"duplicate claim_id in construction_manifest: {claim_id!r}")
        seen_claims.add(claim_id)
        if claim_id not in stratum_by_claim:
            raise RelationInputError(
                f"construction claim {claim_id!r} has no severity_stratum_manifest row"
            )
        if crow["evidence_packet_id"] not in packet_class_by_id:
            raise RelationInputError(
                f"construction claim {claim_id!r} references unknown "
                f"evidence_packet_id {crow['evidence_packet_id']!r}"
            )
        merged = dict(crow)
        merged["_severity_stratum"] = stratum_by_claim[claim_id]
        annotated.append(merged)

    # Determinism: canonical ordering by claim_id lexical sort.
    annotated.sort(key=lambda r: r["claim_id"])
    return annotated, packet_class_by_id


def _percentile_nearest_rank(values: list[int], pct: float) -> int:
    """Nearest-rank percentile (deterministic, no interpolation). pct in [0,1].

    Returns 0 for an empty list. Index = ceil(pct * n) clamped to [1, n], 1-based.
    """
    if not values:
        return 0
    ordered = sorted(values)
    n = len(ordered)
    rank = max(1, min(n, math.ceil(pct * n)))
    return ordered[rank - 1]


def build_relations(
    construction_rows: Iterable[dict],
    packet_rows: Iterable[dict],
    severity_rows: Iterable[dict],
    rho: float = DEFAULT_ICC_CEILING,
) -> RelationResult:
    """Build the full pairwise relation table + per-stratum DEFF summaries.

    Base relations are computed over ALL unordered pairs i<j (the full lookup
    table, incl. cross-stratum rows). Per-stratum P_S filters to pairs with both
    claims in S (§2.1/§2.2).
    """
    if not (0.0 <= rho <= 1.0):
        raise ValueError(f"rho (ICC ceiling) must be in [0,1], got {rho!r}")

    construction = list(construction_rows)
    packets = list(packet_rows)
    severity = list(severity_rows)

    # Custody hashes (§2.4 / 0a.-1.E): canonical over each input manifest.
    input_manifest_sha256s = (
        ("construction_manifest", _canonical_sha256(sorted(construction, key=lambda r: r.get("claim_id", "")))),
        ("severity_stratum_manifest", _canonical_sha256(sorted(severity, key=lambda r: r.get("claim_id", "")))),
        ("source_packet_manifest", _canonical_sha256(sorted(packets, key=lambda r: r.get("evidence_packet_id", "")))),
    )

    rows, packet_class_by_id = _index_rows(packets, severity, construction)

    pairwise: list[dict] = []
    # within-stratum adjacency degree: stratum -> claim_id -> count
    degree: dict[str, dict[str, int]] = {}
    p_by_stratum: dict[str, int] = {}

    n = len(rows)
    for a in range(n):
        for b in range(a + 1, n):
            row_i, row_j = rows[a], rows[b]
            matched = pair_related(row_i, row_j, packet_class_by_id)
            related = bool(matched)
            stratum_i = row_i["_severity_stratum"]
            stratum_j = row_j["_severity_stratum"]
            pairwise.append(
                {
                    "claim_id_i": row_i["claim_id"],
                    "claim_id_j": row_j["claim_id"],
                    "related": related,
                    "criteria_matched": matched,
                    "stratum_i": stratum_i,
                    "stratum_j": stratum_j,
                }
            )
            if related and stratum_i == stratum_j:
                s = stratum_i
                p_by_stratum[s] = p_by_stratum.get(s, 0) + 1
                d = degree.setdefault(s, {})
                d[row_i["claim_id"]] = d.get(row_i["claim_id"], 0) + 1
                d[row_j["claim_id"]] = d.get(row_j["claim_id"], 0) + 1

    # N per stratum.
    n_by_stratum: dict[str, int] = {}
    for row in rows:
        s = row["_severity_stratum"]
        n_by_stratum[s] = n_by_stratum.get(s, 0) + 1

    relation_table_sha256 = _canonical_sha256(pairwise)

    summaries: list[StratumSummary] = []
    for stratum in sorted(n_by_stratum):
        n_s = n_by_stratum[stratum]
        p_s = p_by_stratum.get(stratum, 0)
        deff = 1.0 + (2.0 * p_s * rho / n_s) if n_s > 0 else 1.0
        n_eff = n_s / deff if deff > 0 else float(n_s)
        # within-stratum degrees: claims in S with 0 related partners contribute 0
        deg_map = degree.get(stratum, {})
        degrees = [deg_map.get(row["claim_id"], 0) for row in rows if row["_severity_stratum"] == stratum]
        summaries.append(
            StratumSummary(
                stratum=stratum,
                n=n_s,
                p=p_s,
                rho=rho,
                deff=deff,
                n_eff=n_eff,
                max_claim_degree=max(degrees) if degrees else 0,
                p95_claim_degree=_percentile_nearest_rank(degrees, 0.95),
                relation_table_sha256=relation_table_sha256,
                input_manifest_sha256s=input_manifest_sha256s,
            )
        )

    return RelationResult(pairwise_relations=pairwise, stratum_summaries=summaries)
