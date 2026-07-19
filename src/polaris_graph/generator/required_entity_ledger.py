"""I-perm-021 (#1213) — RequiredEntityLedger: report-level required-entity completeness
accounting + honest gap disclosure (Codex design-gate APPROVE; narrow scope).

The completeness gap is largely UPSTREAM (retrieval/extraction); a reduce-time/report-level
ledger CANNOT manufacture coverage. Its job, per the Codex design ruling, is the NARROW
"inclusion + disclosure" surface (NO second LLM generation / recovery round — that is a
deferred follow-up):

  - Phase B (THIS module, report-level, POST-strict_verify): given the pre-registered native
    `required_entities` and the set of entity ids that earned a VERIFIED binding (the UNION of
    every VERIFIED claim's ``covered_element_ids`` from
    ``native_gate_b_inputs.build_native_gate_b_inputs`` — the EXACT same coverage computation,
    reused, never re-implemented), mark each required slot VERIFIED or GAP_DISCLOSED and emit
    an HONEST, DETERMINISTIC, TEMPLATED disclosure (no LLM, no fabricated citation).

§-1.1 SAFETY: this module assigns NO verdicts and adds NO coverage CREDIT. VERIFIED is set
ONLY from the caller's already-computed verified-binding set (which is itself gated by
strict_verify + the 4-role ``verdict==VERIFIED`` rule). It never touches strict_verify / the
4-role evaluator / D8 / the release decision. A gap disclosure is a templated "we could not
verify X" statement — it NEVER fills the gap with an unsupported claim.

Required entities come ONLY from the native scope template (the contamination lock — never
``outputs/dr_benchmark/`` / the gold rubric). The caller reads ``PG_REQUIRED_ENTITY_LEDGER``
at CALL TIME (default OFF, byte-identical when off); this pure module is simply not invoked
when the flag is off.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ── slot state machine ────────────────────────────────────────────────────
# (Phase A states RETRIEVED/MAPPED are produced by the pre-gen retrieval feed, a separate PR;
#  this narrow disclosure module uses only the post-verify VERIFIED / GAP_DISCLOSED transition.)
STATE_MISSING = "missing"
STATE_RETRIEVED = "retrieved"
STATE_MAPPED = "mapped"
STATE_VERIFIED = "verified"
STATE_INCLUDED = "included"
STATE_GAP_DISCLOSED = "gap_disclosed"

# native required-entity dict keys (mirrors native_gate_b_inputs; read-only here).
_KEY_ID = "id"
_KEY_SEVERITY = "severity"
_KEY_ANCHOR = "anchor"
_KEY_RENDERING_SLOT = "rendering_slot"
_KEY_S0_CATEGORY = "s0_category"
# canonical identifier keys, in disclosure-preference order.
_CANONICAL_KEYS = ("doi", "pmid", "url_pattern")


@dataclass
class RequiredSlot:
    """One required entity's completeness state + the metadata needed to disclose it."""
    entity_id: str
    severity: str
    s0_category: str | None
    anchor: str
    rendering_slot: str
    canonical_ids: dict           # {doi?, pmid?, url_pattern?} (only present keys)
    state: str
    note: str = ""                # disclosure qualifier (e.g. url_mismatch); never a claim

    @property
    def is_url_pattern_only(self) -> bool:
        """True iff url_pattern is the ENTITY's only canonical id (no doi/pmid). Such an
        entity is structurally un-flippable by alternate-URL retrieval — coverage requires the
        VERIFIED claim to cite the exact canonical url_pattern (Codex design-gate q7)."""
        return "url_pattern" in self.canonical_ids and not (
            self.canonical_ids.get("doi") or self.canonical_ids.get("pmid")
        )


# Disclosure qualifier (Codex design-gate q7): public-facing, NOT raw internal artifact wording.
_URL_MISMATCH_NOTE = (
    "content for this topic may exist on an alternate source, but coverage remains unmet "
    "unless a verified claim cites the canonical source for this required entity"
)


@dataclass
class RequiredEntityLedger:
    """Tally of the run's required-entity slots and their coverage state.

    Holds one ``RequiredSlot`` per required entity and exposes the
    verified/gap partition plus the coverage fraction. ``to_evidence_gaps``
    renders the un-covered (gap-disclosed) slots as machine-readable records
    for the manifest's audit trail.
    """

    slots: list[RequiredSlot] = field(default_factory=list)

    def verified_slots(self) -> list[RequiredSlot]:
        return [s for s in self.slots if s.state in (STATE_VERIFIED, STATE_INCLUDED)]

    def gap_slots(self) -> list[RequiredSlot]:
        return [s for s in self.slots if s.state == STATE_GAP_DISCLOSED]

    def coverage_fraction(self) -> float:
        return (len(self.verified_slots()) / len(self.slots)) if self.slots else 0.0

    def to_evidence_gaps(self) -> list[dict]:
        """Structured gap records for the manifest (machine-readable, audit trail)."""
        return [
            {
                "entity_id": s.entity_id,
                "severity": s.severity,
                "s0_category": s.s0_category,
                "anchor": s.anchor,
                "rendering_slot": s.rendering_slot,
                "reason": "no_verified_citation",
                "note": s.note,
            }
            for s in self.gap_slots()
        ]


def verified_covered_ids(
    audit_map: dict, final_verdicts: dict[str, str] | None,
) -> set[str]:
    """The set of required-entity ids covered by a 4-role FINAL-VERIFIED claim.

    Codex diff-gate iter-1 P1 (§-1.1): `four_role_claim_audit.json`'s per-claim
    ``covered_element_ids`` is the PRE-D8 builder audit map — it records what a claim WOULD
    cover if verified. But the 4-role seam can DOWNGRADE that claim (UNSUPPORTED / PARTIAL /
    FABRICATED), and D8 only credits coverage for a claim whose final verdict is VERIFIED. So
    the covered set MUST be filtered through ``final_verdicts[claim_id] == "VERIFIED"`` —
    otherwise a downgraded claim would falsely mark its entity covered and SUPPRESS a real
    Coverage-gaps disclosure (hiding a coverage gap = over-claiming completeness, the lethal
    direction). When ``final_verdicts`` is empty/None (e.g. a seam-timeout path) NO claim is
    treated as verified -> every required entity is disclosed as a gap (fail-safe over-disclose,
    never under-disclose)."""
    fv = final_verdicts or {}
    covered: set[str] = set()
    rows = audit_map.items() if isinstance(audit_map, dict) else []
    for claim_id, row in rows:
        if isinstance(row, dict) and fv.get(claim_id) == "VERIFIED":
            covered.update(row.get("covered_element_ids", []) or [])
    return covered


def _canonical_ids(entity: dict) -> dict:
    return {k: entity[k] for k in _CANONICAL_KEYS if entity.get(k) not in (None, "")}


def _norm_id(value: "str | None") -> str:
    """Lowercase + strip a canonical identifier for comparison. PURE."""
    return str(value or "").strip().lower()


def citation_covered_entity_ids(
    required_entities: list[dict],
    cited_evidence_records: "list[dict] | tuple[dict, ...] | None",
) -> set[str]:
    """I-deepfix-001 S2 (#1213/#1344): the set of required-entity ids covered by the CITED evidence
    of the report's VERIFIED claims. The four-role ``covered_element_ids`` path under-credits a
    required entity when the D8 builder never bound the entity to a claim's element ids even though
    the BODY renders a verified, span-grounded claim CITING exactly that entity (drb_72:
    coverage_fraction 0.571 = 4/7). This credits an entity as covered when ANY cited-evidence record
    (a bibliography row / basket SUPPORTS member of a final-VERIFIED claim) matches the entity's
    canonical id: DOI or PMID (exact OR appearing as a substring of the record URL, so a
    doi.org/<doi> locator counts) or the entity's ``url_pattern`` (substring of the record URL).

    §-1.1 SAFETY: this ADDS coverage credit ONLY from evidence the report actually cited — it never
    fabricates a citation, never touches strict_verify / the 4-role evaluator / D8, and is UNIONED
    with (never replaces) the existing ``covered_element_ids`` path. cited_evidence_records must be
    the evidence of VERIFIED claims (the caller passes the report's cited bibliography, which is
    built from verified composed sentences). PURE."""
    doi_index: dict[str, str] = {}
    pmid_index: dict[str, str] = {}
    url_patterns: list[tuple[str, str]] = []
    for entity in required_entities or []:
        entity_id = entity.get(_KEY_ID)
        if entity_id in (None, ""):
            continue
        entity_id = str(entity_id)
        cids = _canonical_ids(entity)
        if cids.get("doi"):
            doi_index[_norm_id(cids["doi"])] = entity_id
        if cids.get("pmid"):
            pmid_index[_norm_id(cids["pmid"])] = entity_id
        if cids.get("url_pattern"):
            url_patterns.append((_norm_id(cids["url_pattern"]), entity_id))
    covered: set[str] = set()
    for rec in cited_evidence_records or ():
        if not isinstance(rec, dict):
            continue
        r_doi = _norm_id(rec.get("doi"))
        r_pmid = _norm_id(rec.get("pmid"))
        r_url = _norm_id(rec.get("url") or rec.get("source_url"))
        for doi, ent_id in doi_index.items():
            if doi and (doi == r_doi or (r_url and doi in r_url)):
                covered.add(ent_id)
        for pmid, ent_id in pmid_index.items():
            if pmid and (pmid == r_pmid or (r_url and pmid in r_url)):
                covered.add(ent_id)
        if r_url:
            for pat, ent_id in url_patterns:
                if pat and pat in r_url:
                    covered.add(ent_id)
    return covered


def build_ledger(
    required_entities: list[dict],
    covered_entity_ids: set[str] | frozenset[str] | list[str],
    extra_covered_ids: "set[str] | frozenset[str] | list[str] | None" = None,
) -> RequiredEntityLedger:
    """Phase B: build the report-level ledger from the native required entities + the
    VERIFIED-binding set (``⋃ verified_claim.covered_element_ids``, computed by
    ``native_gate_b_inputs``). A required entity is VERIFIED iff its id is in
    ``covered_entity_ids`` (the exact existing coverage authority), else GAP_DISCLOSED.
    Assigns NO new credit; this is pure accounting + disclosure over an already-decided set.

    I-deepfix-001 S2 (#1344): ``extra_covered_ids`` UNIONS an additional covered set (the
    citation→entity credit from ``citation_covered_entity_ids``) so an entity cited by a VERIFIED
    body claim is not falsely disclosed as a gap. Only ADDS coverage from cited evidence; it never
    removes a covered id and never touches the faithfulness engine."""
    covered = set(covered_entity_ids) | set(extra_covered_ids or ())
    slots: list[RequiredSlot] = []
    for entity in required_entities:
        entity_id = entity.get(_KEY_ID)
        if entity_id in (None, ""):
            # a config error elsewhere (validate_entity_severity is the fail-loud guard); skip
            # defensively here so the ledger never crashes on a malformed slot.
            continue
        canonical_ids = _canonical_ids(entity)
        verified = entity_id in covered
        slot = RequiredSlot(
            entity_id=str(entity_id),
            severity=str(entity.get(_KEY_SEVERITY, "")),
            s0_category=entity.get(_KEY_S0_CATEGORY),
            anchor=str(entity.get(_KEY_ANCHOR, "")),
            rendering_slot=str(entity.get(_KEY_RENDERING_SLOT, "")),
            canonical_ids=canonical_ids,
            state=STATE_VERIFIED if verified else STATE_GAP_DISCLOSED,
        )
        if not verified and slot.is_url_pattern_only:
            slot.note = _URL_MISMATCH_NOTE
        slots.append(slot)
    return RequiredEntityLedger(slots=slots)


def render_coverage_gaps_section(ledger: RequiredEntityLedger) -> str:
    """Deterministic, public-facing 'Coverage gaps' report section (NO LLM, NO fabricated
    citation, NO raw internal artifact wording — Codex design-gate q5 + P2). Returns "" when
    there are no gaps so the section is omitted entirely (and the OFF path stays byte-identical)."""
    gaps = ledger.gap_slots()
    if not gaps:
        return ""
    lines = [
        "## Coverage gaps",
        "",
        "The following pre-registered required topics could not be supported by a verified "
        "citation in this report. They are disclosed here rather than asserted without "
        "evidence:",
        "",
    ]
    for s in gaps:
        label = s.anchor or s.entity_id
        sev = f" ({s.severity})" if s.severity else ""
        note = f" — {s.note}" if s.note else ""
        lines.append(f"- **{label}**{sev}: not verified in this run{note}.")
    lines.append("")
    return "\n".join(lines)
