#!/usr/bin/env python3
"""The DISPOSITION engine (Sol §4 "Disposition rules", Phase 4 "Adjudication and repair").

Tier-0 (`card_audit.tier0`) and the Tier-1/2/3 harness (`card_audit.harness`) DECIDE a card: they emit a
deterministic receipt, a report-AST faithfulness verdict, two independent Opus verdicts, and a fail-closed
`CombinedVerdict` carrying a *proposed* disposition. THIS module ACTS on that decision. It turns one
proposed disposition into exactly one final, accounted outcome, and — for every repairing disposition —
it rebuilds the card as a NEW object and RE-RUNS the entire deterministic screen (and, when an Opus
transport is injected, the full semantic ladder) on that new object. Nothing is ever silently dropped:
every input row and every support edge leaves this engine in exactly one bucket, and the corpus census
must reconcile (Sol Phase 4 acceptance).

THE SEVEN DISPOSITIONS, each with Sol's exact rule:

  KEEP_UNCHANGED            — all applicable dimensions pass; the card ships as-is.
  REPAIR_TIGHTEN            — the span supports a NARROWER claim. A repair proposes TYPED field changes
                              (never replacement claim prose); source bytes/hash/manifestation/offsets are
                              IMMUTABLE; the claim is RECOMPUTED with `evidence_miner.derive_claim`; every
                              deterministic dimension and report-AST entailment are rerun; the original is
                              kept in the lineage as SUPERSEDED (Sol §REPAIR_TIGHTEN 1-8).
  REBASE_TO_VALID_SUPPORT   — the primary span fails but a corroborator INDEPENDENTLY entails the claim:
                              rebuild a COMPLETE binding from that source's graph bytes, make it primary,
                              issue a collision-safe id, recompute attribution and counts, rerun all dims
                              (Sol §REBASE_TO_VALID_SUPPORT). Never merely swap the attribution string.
  REMOVE_BAD_SUPPORT_EDGE   — the primary passes but a corroborator does not: retain the primary, move the
                              bad edge into quarantine WITH ITS REASON, recompute n_sources/n_evidence_units
                              (Sol §REMOVE_BAD_SUPPORT_EDGE). The disappearance is COUNTED as a repair.
  DEMOTE_TO_OWNED_SUGGESTION— sound only for a genuine frame/transition/proof-carrying synthesis that names
                              no number/source/particular and passes `report_ast.validate_node(Owned(...))`
                              (Sol §DEMOTE). It moves to owned_suggestions, NOT audited_cards — a demoted
                              object is not citeable evidence.
  QUARANTINE_CARD           — invalid binding, unresolved identity, no entailed repair, unremovable CoT,
                              numeric contradiction, off-topic, duplicate-id, consolidation loss (Sol §QUAR).
  QUARANTINE_SUPPORT_EDGE   — false corroboration / incomplete nested binding while the primary is valid.

There is NO DELETE (Sol §4).

REUSE, NOT REINVENTION (Sol §1 non-negotiable enforcement points):
  - `evidence_miner.derive_claim`     — the ONLY authority on the recomputed claim; a repair never writes
                                        claim prose.
  - `card_audit.tier0.screen_card`    — the deterministic rerun after any repair.
  - `card_audit.tier0.screen_support_edge` / `_verified_evidence_units` — edge validity and the count
                                        recompute.
  - `card_audit.harness.audit_faithfulness_primary` / `audit_card` — the report-AST + Opus rerun.
  - `report_ast.validate_node(Owned(...), bundle)` — the OWNED-demotion gate (it already refuses a number,
                                        a named source, an oblique attribution, a bare finding, and a
                                        synthesis with < 2 premises — Sol §DEMOTE in one call).
  - `card_audit.harness.voice_launder_blocked` — refuses the ATTRIBUTED->OWNED laundering transition.

GENERALITY (Sol Phase 8): there is not one DOI, title, subject, venue, or benchmark literal in this file.
Every rule fires on STRUCTURE, so a clinical / legal / economics / CS corpus disposes identically. The
legacy `scripts/quarantine.py` is deliberately NOT imported (Sol §1: it hardcodes journal-only policy).
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field

import provenance as P
import report_ast as RA
import evidence_miner as EM

from card_audit import tier0, harness
from card_audit.audit_schema import (
    PASS, FAIL, UNCERTAIN, NOT_APPLICABLE, DeterministicReceipt,
)

# =================================================================================================
# The closed accounting buckets (Sol Phase 4 acceptance) and the disposition->bucket map
# =================================================================================================
KEEP_UNCHANGED = 'KEEP_UNCHANGED'
REPAIR_TIGHTEN = 'REPAIR_TIGHTEN'
REBASE_TO_VALID_SUPPORT = 'REBASE_TO_VALID_SUPPORT'
REMOVE_BAD_SUPPORT_EDGE = 'REMOVE_BAD_SUPPORT_EDGE'
DEMOTE_TO_OWNED_SUGGESTION = 'DEMOTE_TO_OWNED_SUGGESTION'
QUARANTINE_CARD = 'QUARANTINE_CARD'
QUARANTINE_SUPPORT_EDGE = 'QUARANTINE_SUPPORT_EDGE'

# Sol Phase 4:  input_top_level = kept_unchanged + repaired_and_superseded + quarantined
#                                 + demoted_to_owned_suggestion
BUCKET_KEPT = 'kept_unchanged'
BUCKET_REPAIRED = 'repaired_and_superseded'
BUCKET_QUARANTINED = 'quarantined'
BUCKET_DEMOTED = 'demoted_to_owned_suggestion'
TOP_LEVEL_BUCKETS = (BUCKET_KEPT, BUCKET_REPAIRED, BUCKET_QUARANTINED, BUCKET_DEMOTED)

_DISPOSITION_BUCKET = {
    KEEP_UNCHANGED: BUCKET_KEPT,
    REPAIR_TIGHTEN: BUCKET_REPAIRED,
    REBASE_TO_VALID_SUPPORT: BUCKET_REPAIRED,
    REMOVE_BAD_SUPPORT_EDGE: BUCKET_REPAIRED,   # the primary is a NEW superseding object (counts changed)
    DEMOTE_TO_OWNED_SUGGESTION: BUCKET_DEMOTED,
    QUARANTINE_CARD: BUCKET_QUARANTINED,
}

# Sol Phase 4:  input_support_edges = kept_support_edges + repaired_support_edges + quarantined_support_edges
EDGE_KEPT = 'kept_support_edges'
EDGE_REPAIRED = 'repaired_support_edges'
EDGE_QUARANTINED = 'quarantined_support_edges'
EDGE_BUCKETS = (EDGE_KEPT, EDGE_REPAIRED, EDGE_QUARANTINED)

# Stable reason codes this engine cites (Sol §Report: quarantine counts by stable reason code).
RC_REPAIR_TOUCHED_IMMUTABLE = 'repair.touched_immutable_field'
RC_REPAIR_TOUCHED_DERIVED = 'repair.touched_derived_cache_field'
RC_REPAIR_UNKNOWN_FIELD = 'repair.unknown_field'
RC_REPAIR_NO_PROPOSAL = 'repair.no_typed_proposal'
RC_REPAIR_RERUN_FAILED = 'repair.rerun_still_fails'
RC_REBASE_NO_VALID_SUPPORT = 'rebase.no_corroborator_independently_supports'
RC_REBASE_ID_COLLISION = 'rebase.cannot_issue_collision_safe_id'
RC_REMOVE_PRIMARY_NOT_VALID = 'remove_edge.primary_not_valid'
RC_DEMOTE_OWNED_REJECTED = 'demote.owned_node_rejected'
RC_DEMOTE_VOICE_LAUNDER = 'demote.attributed_to_owned_launder_blocked'
RC_QUARANTINE = 'quarantine.card'
RC_QUARANTINE_EDGE = 'quarantine.support_edge'

# Source bytes, hash, manifestation, and offsets remain IMMUTABLE across a repair (Sol §REPAIR_TIGHTEN 2),
# together with the identity coordinates that address them. A repair may never rewrite any of these.
IMMUTABLE_FIELDS = frozenset({
    'id', 'span_raw', 'content_hash', 'manifestation_id', 'span_start', 'span_end',
    'work_id', 'evidence_unit_id', 'expression_id', 'attribution_target_expression_id',
    'permitted_expression_ids', 'source_version',
})

# Derived caches the engine RECOMPUTES from audited fields; a repair proposal may never set them directly
# (Sol §REPAIR_TIGHTEN 3: recompute the claim; do not accept model-written claim prose).
DERIVED_FIELDS = frozenset({
    'claim', 'span_numbers', 'has_number', 'complete_tuple', 'n_sources', 'n_evidence_units',
})


# =================================================================================================
# Lineage — a canonical content hash so a repair records exact before/after (Sol §REPAIR_TIGHTEN 7)
# =================================================================================================
def card_content_hash(card: dict) -> str:
    """A canonical sha256 over the card's serialized content, so a repair can record before/after hashes
    (Sol §REPAIR_TIGHTEN 7) and the lineage ledger can mark the original SUPERSEDED (rule 8)."""
    canon = json.dumps(card, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(canon.encode('utf-8')).hexdigest()


def _changed_fields(before: dict, after: dict) -> list[str]:
    return sorted({k for k in set(before) | set(after) if before.get(k) != after.get(k)})


# =================================================================================================
# The typed repair proposal — TYPED field changes only, never replacement claim prose (Sol §REPAIR 1)
# =================================================================================================
@dataclass
class RepairProposal:
    """What a repair agent (or the deterministic edge logic) proposes for ONE card. It is TYPED: a set of
    field values to change and a set of fields to remove — NOT free replacement prose (Sol §REPAIR_TIGHTEN
    1). The claim and every derived cache are recomputed by the engine, never taken from here. For a
    DEMOTE, `owned_text`/`owned_premise_ids` carry the reviewer-voice replacement the OWNED gate validates.
    For a REBASE, `rebase_edge_index` names the corroborator to promote (or None to let the engine pick the
    first independently-supporting one)."""
    field_changes: dict = field(default_factory=dict)
    remove_fields: tuple[str, ...] = ()
    rebase_edge_index: int | None = None
    owned_text: str = ''
    owned_premise_ids: tuple[str, ...] = ()


def validate_repair_proposal(proposal: RepairProposal) -> list[str]:
    """Refuse a repair that touches an immutable byte/identity field, a recomputed derived cache, or an
    unknown field (Sol §REPAIR_TIGHTEN 2-3). Returns the reason codes for every illegal touch; empty when
    the typed changes are all legal repairable fields."""
    from card_audit.audit_schema import TOP_LEVEL_FIELDS
    rcs: list[str] = []
    touched = set(proposal.field_changes) | set(proposal.remove_fields)
    for f in sorted(touched):
        if f in IMMUTABLE_FIELDS:
            rcs.append(RC_REPAIR_TOUCHED_IMMUTABLE)
        elif f in DERIVED_FIELDS:
            rcs.append(RC_REPAIR_TOUCHED_DERIVED)
        elif f not in TOP_LEVEL_FIELDS:
            rcs.append(RC_REPAIR_UNKNOWN_FIELD)
    return sorted(set(rcs))


def _act_of(card: dict):
    return EM.REGISTRY.acts.get(card.get('act') or '')


def _recompute_caches(card: dict, graph: P.Graph, policy: P.SourcePolicy) -> None:
    """Recompute every derived cache IN PLACE, exactly as Tier-0 expects it (so a repaired card passes
    DIM_CACHES): claim via `derive_claim`, span_numbers/has_number from `card['span']`, complete_tuple from
    `is_complete` and the act, and the source counts from the INDEPENDENTLY-VERIFIED evidence units — not
    the stored counts (Sol §Structure: n_sources equal verified units)."""
    act = _act_of(card)
    if act is not None:
        card['claim'] = EM.derive_claim(card, act)
        card['complete_tuple'] = bool(EM.is_complete(card) and act.tuple_bearing)
    card['span_numbers'] = sorted(EM.number_tokens(card.get('span') or ''))
    card['has_number'] = bool(card['span_numbers'])
    n = len(tier0._verified_evidence_units(card, graph, policy))
    if card.get('n_sources') is not None:
        card['n_sources'] = n
    if card.get('n_evidence_units') is not None:
        card['n_evidence_units'] = n


# =================================================================================================
# Edge classification — which corroborators are valid, and which independently entail the primary
# =================================================================================================
@dataclass
class EdgeStatus:
    index: int
    structurally_valid: bool          # a complete, independently-verifying binding (Tier-0)
    independently_entails: bool       # its own span entails the PRIMARY claim (report-AST)
    reason_codes: list[str] = field(default_factory=list)
    detail: str = ''


def classify_edges(card: dict, graph: P.Graph, policy: P.SourcePolicy) -> list[EdgeStatus]:
    """For every `corroborating_sources` edge, decide (a) whether it has a complete independently-verifying
    binding (Tier-0 `screen_support_edge`) and (b) whether its OWN verified span independently entails the
    primary claim (report-AST, never inheriting the primary's pass — Sol §Faithfulness). Both are needed:
    a structurally valid edge that does not entail the primary is false corroboration."""
    edges = card.get('corroborating_sources') or []
    corr_faith = harness.audit_faithfulness_corroborators(card, graph)
    out: list[EdgeStatus] = []
    for i, edge in enumerate(edges):
        det = tier0.screen_support_edge(edge, graph, policy)
        struct_ok = det.verdict == PASS
        faith = corr_faith[i] if i < len(corr_faith) else None
        entails = bool(faith and faith.verdict == PASS)
        rcs = list(det.reason_codes)
        if faith and faith.verdict == FAIL:
            rcs.extend(faith.reason_codes)
        out.append(EdgeStatus(i, struct_ok, entails, sorted(set(rcs)),
                              det.detail or (faith.detail if faith else '')))
    return out


# =================================================================================================
# The disposition record — one per input top-level card, nothing silently dropped
# =================================================================================================
@dataclass
class EdgeDisposition:
    """One support edge's final outcome (Sol Phase 4: every support edge is accounted)."""
    index: int
    bucket: str                       # EDGE_KEPT / EDGE_REPAIRED / EDGE_QUARANTINED
    reason_codes: list[str] = field(default_factory=list)
    quarantine_reason: str = ''

    def to_json(self) -> dict:
        return dict(index=self.index, bucket=self.bucket, reason_codes=list(self.reason_codes),
                    quarantine_reason=self.quarantine_reason)


@dataclass
class CardDisposition:
    """The final, accounted outcome for ONE input top-level card. Exactly one `bucket`; the resulting
    object (a clean/repaired card, or an owned suggestion, or nothing) is carried explicitly, and the
    lineage records the before/after content hashes and the changed fields (Sol §REPAIR_TIGHTEN 7-8)."""
    audit_row_id: str
    card_id: str
    disposition: str                  # the Sol §4 verb finally applied
    bucket: str                       # a TOP_LEVEL_BUCKETS member
    original_hash: str
    result_hash: str = ''
    result_card: dict | None = None   # goes to audited_cards.json (kept / repaired / rebased primary)
    owned_suggestion: dict | None = None   # goes to owned_suggestions.json (demoted)
    quarantine_reason: str = ''
    reason_codes: list[str] = field(default_factory=list)
    changed_fields: list[str] = field(default_factory=list)
    rerun_overall: str = ''           # the deterministic rerun verdict after a repair
    rerun_final: str = ''             # the full-ladder rerun verdict after a repair (when a runner is used)
    edge_dispositions: list[EdgeDisposition] = field(default_factory=list)
    detail: str = ''

    def to_json(self) -> dict:
        return dict(
            audit_row_id=self.audit_row_id, card_id=self.card_id, disposition=self.disposition,
            bucket=self.bucket, original_hash=self.original_hash, result_hash=self.result_hash,
            has_result_card=self.result_card is not None,
            has_owned_suggestion=self.owned_suggestion is not None,
            quarantine_reason=self.quarantine_reason, reason_codes=sorted(set(self.reason_codes)),
            changed_fields=list(self.changed_fields), rerun_overall=self.rerun_overall,
            rerun_final=self.rerun_final,
            edge_dispositions=[e.to_json() for e in self.edge_dispositions], detail=self.detail)


# =================================================================================================
# Applying each repairing disposition — always to a NEW object, then rerun (Sol Phase 4 step 5/7)
# =================================================================================================
def apply_typed_repair(card: dict, proposal: RepairProposal, graph: P.Graph,
                       policy: P.SourcePolicy) -> tuple[dict | None, list[str]]:
    """Sol §REPAIR_TIGHTEN: apply the TYPED field changes to a NEW copy, leaving source bytes/hash/
    manifestation/offsets immutable, then RECOMPUTE the claim and every derived cache (never accepting
    model-written claim prose). Returns (new_card, []) or (None, reason_codes) if the proposal is illegal."""
    illegal = validate_repair_proposal(proposal)
    if illegal:
        return None, illegal
    if not proposal.field_changes and not proposal.remove_fields:
        return None, [RC_REPAIR_NO_PROPOSAL]
    new = copy.deepcopy(card)
    for f in proposal.remove_fields:
        if f in new and isinstance(new.get(f), str):
            new[f] = ''            # remove a contaminated/unsupported OPTIONAL string field (Sol §REPAIR)
    for f, v in proposal.field_changes.items():
        new[f] = v
    _recompute_caches(new, graph, policy)
    return new, []


def apply_remove_bad_edges(card: dict, bad_indices: list[int], graph: P.Graph,
                           policy: P.SourcePolicy) -> tuple[dict, list[dict]]:
    """Sol §REMOVE_BAD_SUPPORT_EDGE: retain the primary, move each bad edge OUT (returned so it is
    quarantined WITH ITS REASON, never hidden), and recompute n_sources/n_evidence_units. The primary is a
    NEW superseding object because its counts changed."""
    new = copy.deepcopy(card)
    edges = list(new.get('corroborating_sources') or [])
    bad = set(bad_indices)
    removed = [edges[i] for i in sorted(bad) if 0 <= i < len(edges)]
    new['corroborating_sources'] = [e for i, e in enumerate(edges) if i not in bad]
    _recompute_caches(new, graph, policy)
    return new, removed


def _collision_safe_id(base_id: str, edge: dict, existing_ids: frozenset[str]) -> str | None:
    """Sol §REBASE: issue a COLLISION-SAFE card id for the promoted corroborator. Deterministic and
    address-based (manifestation + offsets), with a short content salt so two rebases from one span do not
    themselves collide. Returns None only if even the salted id is already taken."""
    mid = edge.get('manifestation_id') or ''
    s, e = edge.get('span_start'), edge.get('span_end')
    cand = f'{base_id}#rebase:{mid}:{s}-{e}'
    if cand not in existing_ids:
        return cand
    salt = hashlib.sha256(f'{cand}:{edge.get("span_raw", "")}'.encode('utf-8')).hexdigest()[:12]
    cand = f'{cand}:{salt}'
    return cand if cand not in existing_ids else None


def apply_rebase(card: dict, edge_index: int, graph: P.Graph, policy: P.SourcePolicy,
                 existing_ids: frozenset[str]) -> tuple[dict | None, list[str]]:
    """Sol §REBASE_TO_VALID_SUPPORT: the primary failed, but corroborator `edge_index` INDEPENDENTLY
    entails the claim. Rebuild a COMPLETE binding from that source's graph bytes and make it the primary:
    move the binding coordinates (manifestation/hash/offsets/span/permitted set), recompute attribution and
    counts from the LIVE graph (never a copied attribution string), issue a collision-safe id, and drop the
    promoted edge from the corroborator list. The claim's typed fields are unchanged, so `derive_claim`
    yields the same claim — now bound to bytes that actually support it. Returns (new_card, []) or
    (None, reason_codes)."""
    edges = list(card.get('corroborating_sources') or [])
    if not (0 <= edge_index < len(edges)):
        return None, [RC_REBASE_NO_VALID_SUPPORT]
    edge = edges[edge_index]
    binding = RA._binding_from_card(edge)
    if not binding or not graph.verify_span(binding):
        return None, [RC_REBASE_NO_VALID_SUPPORT]
    try:
        att = graph.resolve_attribution(binding, policy)
    except KeyError:
        return None, [RC_REBASE_NO_VALID_SUPPORT]
    if not att.admitted:
        return None, [RC_REBASE_NO_VALID_SUPPORT]
    m = graph.manifestations.get(binding['manifestation_id'])
    if m is None:
        return None, [RC_REBASE_NO_VALID_SUPPORT]

    new = copy.deepcopy(card)
    new_id = _collision_safe_id(card.get('id') or 'card', edge, existing_ids)
    if new_id is None:
        return None, [RC_REBASE_ID_COLLISION]
    new['id'] = new_id
    # move the binding coordinates onto the primary
    new['manifestation_id'] = binding['manifestation_id']
    new['content_hash'] = binding['content_hash']
    new['span_start'] = binding['span_start']
    new['span_end'] = binding['span_end']
    new['span_raw'] = binding['text']
    new['span'] = edge.get('span') or binding['text']
    new['permitted_expression_ids'] = list(binding.get('permitted_expression_ids') or [])
    # recompute identity + attribution from the LIVE graph (never copy the attribution string)
    new['expression_id'] = m.expression_id
    new['work_id'] = m.work_id
    new['evidence_unit_id'] = m.work_id
    new['attribution_target_expression_id'] = att.names_expression_id
    if 'attribution' in new:
        new['attribution'] = att.text or ''
    w = graph.works.get(m.work_id)
    if w is not None:
        for k, wv in (('authors', w.authors), ('venue', w.venue), ('year', w.year), ('doi', w.doi)):
            if k in new:
                new[k] = wv
    new['source_version'] = m.content_hash[:12]
    # the promoted edge leaves the corroborator list
    new['corroborating_sources'] = [e for i, e in enumerate(edges) if i != edge_index]
    _recompute_caches(new, graph, policy)
    return new, []


# =================================================================================================
# OWNED demotion — the gate IS report_ast.validate_node(Owned(...)) (Sol §DEMOTE, §1)
# =================================================================================================
def validate_owned_demotion(text: str, premise_ids, bundle: RA.CardBundle) -> list[RA.Failure]:
    """Sol §DEMOTE_TO_OWNED_SUGGESTION: a demotion is sound ONLY when the reviewer-voice replacement passes
    `report_ast.validate_node(Owned(text, premise_ids), bundle)`. That one call already enforces every one
    of Sol's demotion constraints — it refuses a number, a named source, an oblique attribution to an
    actor, a bare first-order finding, a novel particular, and a synthesis naming fewer than two resolvable
    premises. Returns the (possibly empty) list of failures; empty means the demotion is admissible."""
    owned = RA.Owned(text=text, premise_ids=tuple(premise_ids or ()))
    return RA.validate_node(0, owned, bundle)


def build_owned_suggestion(card: dict, text: str, premise_ids) -> dict:
    """The record that moves to owned_suggestions.json (Sol §DEMOTE: it does NOT remain in audited_cards).
    It is NOT citeable evidence — it carries the reviewer-voice text, the passing premise ids it is a
    synthesis over (if any), and a back-pointer to the card it was demoted from, and NOTHING that would let
    it be resolved as a bound claim."""
    return dict(kind='owned_suggestion', text=text, premise_ids=list(premise_ids or ()),
                demoted_from_card_id=card.get('id') or '')


# =================================================================================================
# The orchestrator — turn one proposed disposition into one accounted outcome, RERUNNING every repair
# =================================================================================================
def _rerun(card: dict, graph: P.Graph, policy: P.SourcePolicy, *, taxonomy, tagger, runner,
           question: str, contract_facets: list[str]) -> tuple[DeterministicReceipt, object]:
    """Sol Phase 4 step 7 / task: RE-RUN the entire audit stack on a repaired card. The deterministic
    screen always reruns; the full semantic ladder reruns too when an Opus transport is injected. Returns
    (deterministic_receipt, combined_verdict_or_None)."""
    det = tier0.screen_card(card, graph, policy, taxonomy=taxonomy, tagger=tagger, json_pointer='/rerun')
    combined = None
    if runner is not None:
        combined = harness.audit_card(card, graph, det, question=question,
                                      contract_facets=contract_facets, runner=runner)
    return det, combined


def _repair_holds(det: DeterministicReceipt, combined, card: dict, graph: P.Graph) -> tuple[bool, str]:
    """A repair is ACCEPTED only if the rerun clears every gate that can be checked (Sol §REPAIR 4-6):
    the deterministic screen must not FAIL, report-AST faithfulness must not FAIL, and — when an Opus
    transport ran — the full-ladder verdict must be PASS. Otherwise the repair did NOT hold and the card is
    quarantined (never silently kept)."""
    if det.overall == FAIL:
        return False, 'deterministic rerun still fails'
    faith = harness.audit_faithfulness_primary(card, graph)
    if faith.verdict == FAIL:
        return False, 'report-AST faithfulness rerun still fails'
    if combined is not None and combined.final != PASS:
        return False, f'full-ladder rerun did not pass ({combined.final})'
    return True, ''


def dispose_card(card: dict, combined, det_receipt: DeterministicReceipt, *,
                 graph: P.Graph, policy: P.SourcePolicy, taxonomy=None, tagger=None,
                 runner=None, question: str = '', contract_facets: list[str] | None = None,
                 proposal: RepairProposal | None = None,
                 existing_ids: frozenset[str] = frozenset(),
                 bundle: RA.CardBundle | None = None) -> CardDisposition:
    """Turn ONE card's `CombinedVerdict` (with its proposed disposition) into exactly one accounted
    `CardDisposition`. Every repairing disposition rebuilds the card as a NEW object and RE-RUNS the whole
    stack; a repair that does not hold falls closed to QUARANTINE. Support edges are classified and
    accounted separately. Nothing is silently dropped."""
    contract_facets = contract_facets or []
    rid = det_receipt.audit_row_id
    cid = card.get('id') or ''
    original_hash = card_content_hash(card)
    proposed = combined.proposed_disposition

    def _quarantine(reason_codes, detail, edges=None):
        return CardDisposition(rid, cid, QUARANTINE_CARD, BUCKET_QUARANTINED, original_hash,
                               quarantine_reason=detail, reason_codes=sorted(set(reason_codes or [RC_QUARANTINE])),
                               detail=detail, edge_dispositions=edges or _edge_dispositions_all_quarantined(card))

    # --- KEEP_UNCHANGED --------------------------------------------------------------------------
    if proposed == KEEP_UNCHANGED and combined.final == PASS:
        edges = _edge_dispositions_from_status(classify_edges(card, graph, policy))
        return CardDisposition(rid, cid, KEEP_UNCHANGED, BUCKET_KEPT, original_hash,
                               result_hash=original_hash, result_card=copy.deepcopy(card),
                               reason_codes=list(combined.reason_codes), edge_dispositions=edges,
                               detail='all applicable dimensions pass')

    # --- QUARANTINE_CARD (explicit) --------------------------------------------------------------
    if proposed == QUARANTINE_CARD:
        return _quarantine(combined.reason_codes, combined.detail or 'quarantine')

    # --- REMOVE_BAD_SUPPORT_EDGE -----------------------------------------------------------------
    if proposed == REMOVE_BAD_SUPPORT_EDGE:
        statuses = classify_edges(card, graph, policy)
        bad = [s.index for s in statuses if not (s.structurally_valid and s.independently_entails)]
        if not bad:
            # nothing actually wrong with the edges — treat as keep if the card itself passes
            if combined.final == PASS:
                edges = _edge_dispositions_from_status(statuses)
                return CardDisposition(rid, cid, KEEP_UNCHANGED, BUCKET_KEPT, original_hash,
                                       result_hash=original_hash, result_card=copy.deepcopy(card),
                                       edge_dispositions=edges, detail='no bad edge to remove')
            return _quarantine([RC_REMOVE_PRIMARY_NOT_VALID], 'primary not valid and no bad edge to remove')
        new, removed = apply_remove_bad_edges(card, bad, graph, policy)
        det, comb = _rerun(new, graph, policy, taxonomy=taxonomy, tagger=tagger, runner=runner,
                           question=question, contract_facets=contract_facets)
        held, why = _repair_holds(det, comb, new, graph)
        edge_disp = []
        for s in statuses:
            if s.index in bad:
                edge_disp.append(EdgeDisposition(s.index, EDGE_QUARANTINED, s.reason_codes,
                                                 s.detail or 'false or unverifiable corroboration'))
            else:
                edge_disp.append(EdgeDisposition(s.index, EDGE_KEPT, s.reason_codes))
        if not held:
            return _quarantine([RC_REPAIR_RERUN_FAILED], f'remove-edge repair did not hold: {why}', edge_disp)
        return CardDisposition(rid, cid, REMOVE_BAD_SUPPORT_EDGE, BUCKET_REPAIRED, original_hash,
                               result_hash=card_content_hash(new), result_card=new,
                               reason_codes=[RC_QUARANTINE_EDGE], changed_fields=_changed_fields(card, new),
                               rerun_overall=det.overall, rerun_final=(comb.final if comb else ''),
                               edge_dispositions=edge_disp,
                               detail=f'removed {len(removed)} bad edge(s); counts recomputed')

    # --- REBASE_TO_VALID_SUPPORT -----------------------------------------------------------------
    if proposed == REBASE_TO_VALID_SUPPORT:
        statuses = classify_edges(card, graph, policy)
        idx = proposal.rebase_edge_index if (proposal and proposal.rebase_edge_index is not None) else None
        if idx is None:
            supporting = [s.index for s in statuses if s.structurally_valid and s.independently_entails]
            idx = supporting[0] if supporting else None
        if idx is None:
            return _quarantine([RC_REBASE_NO_VALID_SUPPORT],
                               'no corroborator independently supports the claim — cannot rebase')
        new, rcs = apply_rebase(card, idx, graph, policy, existing_ids)
        if new is None:
            return _quarantine(rcs, 'rebase could not rebuild a valid primary binding')
        det, comb = _rerun(new, graph, policy, taxonomy=taxonomy, tagger=tagger, runner=runner,
                           question=question, contract_facets=contract_facets)
        held, why = _repair_holds(det, comb, new, graph)
        edge_disp = [EdgeDisposition(idx, EDGE_REPAIRED, [], 'promoted to primary')]
        edge_disp += _edge_dispositions_from_status([s for s in statuses if s.index != idx])
        if not held:
            return _quarantine([RC_REPAIR_RERUN_FAILED], f'rebase did not hold: {why}', edge_disp)
        return CardDisposition(rid, cid, REBASE_TO_VALID_SUPPORT, BUCKET_REPAIRED, original_hash,
                               result_hash=card_content_hash(new), result_card=new,
                               changed_fields=_changed_fields(card, new), rerun_overall=det.overall,
                               rerun_final=(comb.final if comb else ''), edge_dispositions=edge_disp,
                               detail=f'rebased onto corroborator[{idx}] with a fresh collision-safe id')

    # --- REPAIR_TIGHTEN --------------------------------------------------------------------------
    if proposed == REPAIR_TIGHTEN:
        if proposal is None:
            return _quarantine([RC_REPAIR_NO_PROPOSAL],
                               'repair proposed but no typed field-change proposal supplied — fail closed')
        new, rcs = apply_typed_repair(card, proposal, graph, policy)
        if new is None:
            return _quarantine(rcs, 'repair proposal was illegal (immutable/derived/unknown field)')
        det, comb = _rerun(new, graph, policy, taxonomy=taxonomy, tagger=tagger, runner=runner,
                           question=question, contract_facets=contract_facets)
        held, why = _repair_holds(det, comb, new, graph)
        if not held:
            return _quarantine([RC_REPAIR_RERUN_FAILED], f'tighten did not hold: {why}')
        edges = _edge_dispositions_from_status(classify_edges(new, graph, policy))
        return CardDisposition(rid, cid, REPAIR_TIGHTEN, BUCKET_REPAIRED, original_hash,
                               result_hash=card_content_hash(new), result_card=new,
                               changed_fields=_changed_fields(card, new), rerun_overall=det.overall,
                               rerun_final=(comb.final if comb else ''), edge_dispositions=edges,
                               detail='typed tighten; claim recomputed via derive_claim')

    # --- DEMOTE_TO_OWNED_SUGGESTION --------------------------------------------------------------
    if proposed == DEMOTE_TO_OWNED_SUGGESTION:
        # Sol §Voice: block the one illegal ATTRIBUTED->OWNED laundering transition (an unreachable card
        # has no source bytes to demote FROM).
        faith = harness.audit_faithfulness_primary(card, graph)
        if harness.voice_launder_blocked(DEMOTE_TO_OWNED_SUGGESTION, faith):
            return _quarantine([RC_DEMOTE_VOICE_LAUNDER],
                               'OWNED demotion of an unreachable card blocked — no source bytes to demote')
        if proposal is None or not (proposal.owned_text or '').strip():
            return _quarantine([RC_DEMOTE_OWNED_REJECTED],
                               'demotion proposed but no reviewer-voice OWNED replacement supplied')
        if bundle is None:
            return _quarantine([RC_DEMOTE_OWNED_REJECTED],
                               'no clean CardBundle to validate the OWNED replacement against')
        failures = validate_owned_demotion(proposal.owned_text, proposal.owned_premise_ids, bundle)
        if failures:
            return _quarantine([RC_DEMOTE_OWNED_REJECTED],
                               f'OWNED replacement rejected: {failures[0].reason}')
        suggestion = build_owned_suggestion(card, proposal.owned_text, proposal.owned_premise_ids)
        return CardDisposition(rid, cid, DEMOTE_TO_OWNED_SUGGESTION, BUCKET_DEMOTED, original_hash,
                               owned_suggestion=suggestion, detail='validated OWNED suggestion; not citeable',
                               edge_dispositions=_edge_dispositions_all_quarantined(card))

    # --- Anything else (UNCERTAIN with an unhandled disposition) fails CLOSED ---------------------
    return _quarantine(combined.reason_codes or [RC_QUARANTINE],
                       f'unresolved/unsupported disposition {proposed!r} — fail closed')


def _edge_dispositions_from_status(statuses: list[EdgeStatus]) -> list[EdgeDisposition]:
    """A passing primary keeps every VALID corroborator and quarantines any false/unverifiable one."""
    out: list[EdgeDisposition] = []
    for s in statuses:
        if s.structurally_valid and s.independently_entails:
            out.append(EdgeDisposition(s.index, EDGE_KEPT, s.reason_codes))
        else:
            out.append(EdgeDisposition(s.index, EDGE_QUARANTINED, s.reason_codes,
                                       s.detail or 'false or unverifiable corroboration'))
    return out


def _edge_dispositions_all_quarantined(card: dict) -> list[EdgeDisposition]:
    """When the primary itself is quarantined or demoted, its support edges cannot ship either; they are
    quarantined WITH the card, never hidden (Sol: nothing silently dropped)."""
    return [EdgeDisposition(i, EDGE_QUARANTINED, [RC_QUARANTINE_EDGE], 'primary card not in clean set')
            for i in range(len(card.get('corroborating_sources') or []))]


# =================================================================================================
# Corpus reconciliation — the accounting invariant (Sol Phase 4 acceptance): nothing unaccounted
# =================================================================================================
class AccountingError(Exception):
    """The census did not reconcile: a row or edge left the engine unaccounted (Sol Phase 4: no
    unaccounted row or edge is allowed)."""


def reconcile_corpus(dispositions: list[CardDisposition], input_cards: list[dict]) -> dict:
    """Sol Phase 4 acceptance. Assert:
         input_top_level    = kept_unchanged + repaired_and_superseded + quarantined + demoted
         input_support_edges = kept_support_edges + repaired_support_edges + quarantined_support_edges
    Every input row and every support edge must appear in exactly one bucket. Raises AccountingError on any
    mismatch; otherwise returns the reconciled census."""
    n_input = len(input_cards)
    n_input_edges = sum(len(c.get('corroborating_sources') or []) for c in input_cards)

    top = {b: 0 for b in TOP_LEVEL_BUCKETS}
    edge = {b: 0 for b in EDGE_BUCKETS}
    seen_rids: set[str] = set()
    for d in dispositions:
        if d.bucket not in TOP_LEVEL_BUCKETS:
            raise AccountingError(f'card {d.card_id!r} has unknown bucket {d.bucket!r}')
        if d.audit_row_id in seen_rids:
            raise AccountingError(f'audit_row_id {d.audit_row_id!r} accounted twice')
        seen_rids.add(d.audit_row_id)
        top[d.bucket] += 1
        for e in d.edge_dispositions:
            if e.bucket not in EDGE_BUCKETS:
                raise AccountingError(f'edge {d.card_id}[{e.index}] has unknown bucket {e.bucket!r}')
            edge[e.bucket] += 1

    if len(dispositions) != n_input:
        raise AccountingError(f'{len(dispositions)} dispositions for {n_input} input cards')
    top_sum = sum(top.values())
    if top_sum != n_input:
        raise AccountingError(f'top-level buckets sum to {top_sum}, expected {n_input}')
    edge_sum = sum(edge.values())
    if edge_sum != n_input_edges:
        raise AccountingError(f'support-edge buckets sum to {edge_sum}, expected {n_input_edges}')

    return dict(
        input_top_level=n_input, input_support_edges=n_input_edges,
        top_level=top, support_edges=edge,
        reconciled=(top_sum == n_input and edge_sum == n_input_edges),
    )
