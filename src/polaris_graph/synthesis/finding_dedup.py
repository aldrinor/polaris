"""I-meta-005 Phase 5 (#989) — dedup-by-finding + corroboration.

Clusters generator-visible evidence rows by the numeric FINDING they assert,
collapses rehashes of the SAME finding to one representative row, and attaches
``corroboration_count`` = the number of INDEPENDENT registrable-domains carrying
that finding. This is Knowledge-Based Trust (gap D of the re-architecture plan):
the sovereign, domain-general, self-computed trust signal — trust a finding the
rest of the corpus independently confirms, with no external authority service.

CONSERVATIVE-SINGLETON safety rule (brief §2.4 — clinical-lethal if violated):
two findings merge ONLY when subject is KNOWN (not the ``"unknown"`` fallback)
and equal, predicate equal, value (rounded) + unit equal, AND every qualifier the
extractor exposes (dose, arm, endpoint_phrase) is equal — comparing raw field
values so ABSENT==ABSENT matches but ABSENT-vs-PRESENT does not. Any unknown
subject or any qualifier difference keeps the findings SEPARATE. The default on
ambiguity is always "keep separate" — we never drop a distinct finding.

DOCUMENTED RESIDUAL 1 (over-merge bound): ``ExtractedNumericClaim`` does NOT
extract population or comparator. Two findings identical on every extracted field
but differing only in an UNEXTRACTED qualifier (e.g. a T2D vs an obesity
population that share "-2.1%") could merge. This is bounded to a corroboration
OVER-count — a TRUST signal, never a safety gate — and NEVER causes unique-claim
LOSS: the finding the representative asserts (subject/predicate/value/unit/dose/
arm/endpoint) is identical across all members by construction, and all
``member_indices`` + ``member_hosts`` are preserved on the cluster for audit
(manifest + conflict surfacing). A future phase may add a population/comparator
extractor to tighten the key.

DOCUMENTED RESIDUAL 2 (extraction coverage — clinical-tuned): the reused
``extract_numeric_claims`` is clinical-pattern-tuned. Empirically it (a) emits AT
MOST ONE claim per row, and (b) returns NOTHING for non-clinical numerics (GDP,
emissions, model-accuracy, etc.). Consequently a non-clinical numeric row yields
ZERO findings and is kept as a SAFE SINGLETON — never falsely merged, never
dropped — but its finding is NOT clustered and earns NO corroboration_count. So
dedup + corroboration are EFFECTIVE for clinical corpora and INERT-but-SAFE for
non-clinical ones. This is a coverage limitation, not a correctness bug: it can
never cause unique-claim loss or a wrong merge. Gap D's domain-general
corroboration ambition requires a field-agnostic numeric-finding extractor, which
is deliberately deferred to a follow-up rather than risking an over-merging
heuristic here. (The multi-claim-per-row retention logic below is therefore
defensive/future-proof against an extractor that later emits >1 claim per row.)

Pure: constructs no client, no network, no LLM. snake_case; explicit imports.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from src.polaris_graph.authority.corroboration import (
    count_independent_hosts,
    registrable_domain,
)
from src.polaris_graph.retrieval.contradiction_detector import (
    extract_numeric_claims,
)

# The fallback subject `extract_numeric_claims` returns when it cannot identify
# the entity nearest the numeric value. Such claims are NEVER mergeable.
_UNKNOWN_SUBJECT = "unknown"


def _host_of(url: str) -> str:
    """Bare hostname for independent-host counting: urlparse → lowercase →
    strip leading ``www.``. Empty string on an unparseable/missing URL.

    `count_independent_hosts` / `registrable_domain` expect HOSTS, not full
    URLs, so this reduction MUST happen before they are called (else two paths
    on the same domain would count as separate institutions).
    """
    if not url:
        return ""
    host = (urlparse(url).hostname or "").lower().strip()
    if host.startswith("www."):
        host = host[4:]
    return host


def _finding_key(
    claim: Any,
    evidence_id: str,
    claim_index: int,
    *,
    exact_value: bool = False,
) -> tuple:
    """Conservative finding key. An ``unknown`` subject yields a per-CLAIM
    sentinel (evidence_id + claim_index) so it can never collide — even two
    unknown claims on the SAME row stay distinct singletons.

    ``exact_value`` (I-arch-002 (#1246) P3.3, design §2) — under
    ``PG_SWEEP_CREDIBILITY_REDESIGN`` the value slot is the EXACT float (no
    ``round(..., 3)``), matching ``claim_graph._normalized_key_numeric`` (L238)
    so basket clustering keys agree across the two consolidators (a shared
    type-consistency requirement of the design). OFF keeps ``round(value, 3)``
    byte-for-byte (the legacy survivor-selection key).
    """
    subject = getattr(claim, "subject", "") or ""
    if not subject or subject == _UNKNOWN_SUBJECT:
        return ("__unknown__", evidence_id, claim_index)
    raw_value = float(getattr(claim, "value", 0.0) or 0.0)
    value_slot = raw_value if exact_value else round(raw_value, 3)
    return (
        subject,
        getattr(claim, "predicate", "") or "",
        value_slot,
        getattr(claim, "unit", "") or "",
        getattr(claim, "dose", "") or "",
        getattr(claim, "arm", "") or "",
        getattr(claim, "endpoint_phrase", "") or "",
    )


@dataclass
class FindingCluster:
    """One cluster of rows asserting the same finding."""

    finding_key: tuple
    representative_index: int           # row index of the chosen representative
    member_indices: list[int]           # all distinct row indices in the cluster
    member_hosts: list[str]             # sorted unique registrable-domains
    corroboration_count: int            # independent registrable-domains


@dataclass
class FindingDedupResult:
    """Result of `dedup_by_finding`."""

    deduped_rows: list[dict[str, Any]]  # representatives + qualitative rows, in order
    clusters: list[FindingCluster]
    raw_row_count: int
    distinct_finding_count: int
    collapsed_row_count: int


def dedup_by_finding(
    rows: list[dict[str, Any]],
    *,
    gov_suffixes: tuple[str, ...],
    domain: str | None = None,
) -> FindingDedupResult:
    """Cluster `rows` by numeric finding, collapse rehashes, count corroboration.

    Args:
        rows: generator-visible evidence rows (each a dict carrying at least
            `evidence_id`, `source_url`, and `direct_quote`/`statement`; plus the
            `authority_score` + `selection_relevance` sidecars for representative
            ranking).
        gov_suffixes: the PSL multi-level gov-suffix tuple from
            `authority.data_loader.load_authority_data()["psl_gov_suffixes"]` —
            passed in so this module hardcodes NO host/TLD literals.

    Returns:
        FindingDedupResult. `deduped_rows` are SHALLOW COPIES (the caller's rows
        are never mutated); representative copies carry additive
        `corroboration_count` / `independent_hosts` / `finding_keys` keys.

    I-arch-002 (#1246) P3.3 (design §7 / DNA §-1.3 Principle 2 — CONSOLIDATE,
    don't DROP): under ``PG_SWEEP_CREDIBILITY_REDESIGN`` this function STOPS
    being a source-dropper. The non-representative collapse-drop is bypassed so
    EVERY same-claim row flows through as a basket carrying corroboration as
    weight (routed into claim_graph clusters downstream); clustering uses the
    EXACT numeric value (no ``round(..., 3)``). The 3 safe guards are preserved
    in BOTH modes: qualitative pass-through (no-finding rows always kept),
    conservative-singleton (every extracted qualifier must match to cluster),
    and the unknown-subject sentinel (an ``unknown`` subject never merges). The
    faithfulness engine (strict_verify / provenance / NLI / 4-role) is
    untouched. OFF ⇒ the legacy collapse-to-representative drop, byte-identical.
    """
    # Deferred import: the call sites already defer-import this module, and
    # credibility_pass pulls in weight_mass / independence_collapse at module
    # scope — importing the predicate inside the function avoids any import
    # cycle and keeps the activation gate a single source of truth.
    from src.polaris_graph.synthesis.credibility_pass import (
        credibility_redesign_enabled,
    )

    redesign_on = credibility_redesign_enabled()

    rows = list(rows or [])

    # 1. Extract claims per row, group by conservative finding key.
    #
    # B9 domain-generalization: `extract_numeric_claims` now routes a NON-clinical
    # row (deterministic is_clinical signal) to the DOMAIN-AGNOSTIC extractor, so
    # an economics/labor numeric yields a REAL finding key instead of nothing —
    # closing the documented "non-clinical -> singleton" residual (RESIDUAL 2
    # above) so corroborating non-clinical sources can consolidate into a basket.
    # `domain` defaults to None: the per-row is_clinical probe then classifies
    # each row by its own text, so a CLINICAL row still takes the clinical
    # extractor and is byte-identical. A caller MAY pass the run-level `domain`
    # to pin the whole pass. The conservative-singleton + unknown-subject guards
    # below are UNCHANGED in both modes — no merge predicate is relaxed.
    groups: dict[tuple, list[int]] = {}
    row_has_finding: list[bool] = [False] * len(rows)
    for ri, row in enumerate(rows):
        claims = (
            extract_numeric_claims([row], domain=domain)
            if domain is not None else extract_numeric_claims([row])
        )
        if claims:
            row_has_finding[ri] = True
        ev_id = str(row.get("evidence_id", ri))
        for cj, claim in enumerate(claims):
            key = _finding_key(claim, ev_id, cj, exact_value=redesign_on)
            groups.setdefault(key, []).append(ri)

    def _rank(ri: int) -> tuple:
        r = rows[ri]
        return (
            float(r.get("authority_score", 0.0) or 0.0),
            float(r.get("selection_relevance", 0.0) or 0.0),
            -ri,
        )

    # 2. Per cluster: representative + corroboration over INDEPENDENT hosts.
    clusters: list[FindingCluster] = []
    rep_indices: set[int] = set()
    rep_meta: dict[int, dict[str, Any]] = {}
    for key, member_ris in groups.items():
        distinct_ris = sorted(set(member_ris))
        rep_ri = max(distinct_ris, key=_rank)
        hosts_raw = [
            _host_of(str(rows[ri].get("source_url", "")))
            for ri in distinct_ris
        ]
        member_hosts = sorted(
            {registrable_domain(h, gov_suffixes) for h in hosts_raw} - {""}
        )
        corroboration = count_independent_hosts(hosts_raw, gov_suffixes)
        clusters.append(
            FindingCluster(
                finding_key=key,
                representative_index=rep_ri,
                member_indices=distinct_ris,
                member_hosts=member_hosts,
                corroboration_count=corroboration,
            )
        )
        rep_indices.add(rep_ri)
        meta = rep_meta.setdefault(
            rep_ri, {"corr": 0, "hosts": set(), "keys": []}
        )
        meta["corr"] = max(meta["corr"], corroboration)
        meta["hosts"].update(member_hosts)
        meta["keys"].append(list(key))

    # 3. Retain: every row that is the rep of >=1 cluster, plus every row with NO
    #    extractable finding (qualitative rows are never rehashes). Original order.
    #
    #    OFF (legacy): a finding-bearing row that is the rep of nothing is
    #    REDUNDANT -> dropped; every distinct finding it carried survives on that
    #    finding's rep row.
    #
    #    I-arch-002 (#1246) P3.3 (CONSOLIDATE-keep-all): under
    #    ``PG_SWEEP_CREDIBILITY_REDESIGN`` the non-representative DROP is BYPASSED
    #    so ALL same-claim rows flow through as a basket (repetition IS
    #    corroboration). The representative still carries the corroboration
    #    sidecar; non-rep members now survive in original order instead of being
    #    collapsed away. ``collapsed_row_count`` honestly becomes 0.
    deduped_rows: list[dict[str, Any]] = []
    for ri, row in enumerate(rows):
        if not redesign_on and not (ri in rep_indices or not row_has_finding[ri]):
            continue
        new_row = dict(row)  # shallow copy — never mutate the caller's row
        if ri in rep_meta:
            meta = rep_meta[ri]
            new_row["corroboration_count"] = meta["corr"]
            new_row["independent_hosts"] = sorted(meta["hosts"])
            new_row["finding_keys"] = meta["keys"]
        deduped_rows.append(new_row)

    return FindingDedupResult(
        deduped_rows=deduped_rows,
        clusters=clusters,
        raw_row_count=len(rows),
        distinct_finding_count=len(groups),
        collapsed_row_count=len(rows) - len(deduped_rows),
    )
