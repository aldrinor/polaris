#!/usr/bin/env python3
"""Tier-0: the deterministic per-card screen (Sol §3 "Tier 0: deterministic screen on everything").

Everything here decides OFFLINE, with no model call, on structure alone. It runs on every top-level
record, every primary binding, every `corroborating_sources` support edge, and every non-empty field.
It NEVER invents a PASS it cannot prove: a dimension whose truth needs a model (semantic support,
relevance, atom-level faithfulness, ambiguous free text) resolves to NEEDS_OPUS and is routed to
Tier 1 — it is never marked composer-ready here.

REUSE, NOT REINVENTION (Sol §1 non-negotiable enforcement points):
  - `provenance.Graph.verify_span`        — the byte/offset/hash/permitted-set gate.
  - `provenance.Graph.resolve_attribution`— binding-specific identity + source-policy admission.
  - `report_ast._binding_from_card`       — the card->binding adapter `verify_span` demands.
  - `report_ast.number_stands_alone / quantities_in` — the mechanical numeric anti-leak checks.
  - `evidence_miner.number_tokens`        — the exact tokenizer the miner used for `span_numbers`.
  - `evidence_miner.derive_claim`         — the ONLY authority on what `claim` must recompute to.
  - `evidence_miner.is_complete` + REGISTRY — `complete_tuple` and the act table.

GENERALITY (Sol Phase 8): there is not one DOI, title, subject, venue or benchmark literal in this
file. Every rule fires on structure, so a clinical / legal / economics / CS corpus screens identically.
The legacy `scripts/quarantine.py` is deliberately NOT imported (Sol §1: it hardcodes journal-only).
"""
from __future__ import annotations

import hashlib
import html
import json
import re

import provenance as P
import report_ast as RA
import evidence_miner as EM

from card_audit.audit_schema import (
    PASS, FAIL, UNCERTAIN, NOT_APPLICABLE, NEEDS_OPUS, NEEDS_CONTRACT,
    SOURCE_BYTES, CANONICAL_SOURCE_VIEW, DERIVED_CACHE, GRAPH_METADATA, REGISTRY_VALUE,
    ATOMIC_EVIDENCE_VALUE, EMPTY,
    DIM_STRUCTURE, DIM_BINDING, DIM_CACHES, DIM_NUMERIC, DIM_COT, DIM_FACET, DIM_CORROBORATOR,
    TOP_LEVEL_FIELDS, REQUIRED_FIELDS, FIELD_TYPES, SUPPORT_EDGE_BINDING_FIELDS,
    ATOMIC_FIELDS, GRAPH_METADATA_FIELDS, REGISTRY_FIELDS, COT_SKIP_FIELDS,
    RC_SCHEMA_UNKNOWN_FIELD, RC_SCHEMA_MISSING_FIELD, RC_SCHEMA_BAD_TYPE, RC_SCHEMA_EMPTY_ID,
    RC_SCHEMA_DUP_ID, RC_BINDING_UNBOUND, RC_BINDING_SPAN_UNVERIFIED, RC_BINDING_POLICY_REFUSED,
    RC_BINDING_STALE_TARGET, RC_BINDING_IDENTITY, RC_BINDING_EXPR_MISMATCH, RC_BINDING_UNIT_MISMATCH,
    RC_BINDING_POLICY_MISMATCH, RC_CACHE_CLAIM_MISMATCH, RC_CACHE_HAS_NUMBER, RC_CACHE_SPAN_NUMBERS,
    RC_CACHE_COMPLETE_TUPLE, RC_CACHE_COUNTS, RC_NUMERIC_FABRICATED, RC_NUMERIC_UNIT,
    RC_COT_SCAFFOLD, RC_COT_UNCLASSIFIED, RC_COT_STALE_CACHE, RC_ACT_UNKNOWN,
    RC_FACET_NOT_IN_TAXONOMY, RC_FACET_UNSUPPORTED, RC_CORR_INCOMPLETE_BINDING,
    RC_CORR_SPAN_UNVERIFIED,
    DimensionResult, FieldContentClass, DeterministicReceipt,
)

# The identity allowlist lives in the ledger; resolve_attribution enforces it, but the binding
# dimension names the reason precisely, so it reads the two negative verdicts here.
try:                                                   # pragma: no cover - import shape only
    from event_ledger import DIFFERENT_WORK as _DW, UNRESOLVED as _UNR
except Exception:                                      # pragma: no cover
    _DW, _UNR = 'DIFFERENT_WORK', 'UNRESOLVED_BINDING'

_CARD_KINDS = frozenset({'estimate', 'projection', 'qualitative'})
_POLICY_NAMES = frozenset({P.JOURNAL_ONLY.name, P.ANY_VERSION.name})


# =================================================================================================
# Normalization — exactly as Sol §Faithfulness step 3 (HTML-unescape, collapse whitespace, strip a
# single trailing period). Used for the DERIVED_CACHE recompute and the CANONICAL_SOURCE_VIEW test.
# =================================================================================================
def canonicalize(s: str) -> str:
    s = html.unescape(s or '')
    s = re.sub(r'\s+', ' ', s).strip()
    return s[:-1] if s.endswith('.') else s


def _collapse(s: str) -> str:
    return re.sub(r'\s+', ' ', (s or '')).strip().lower()


def audit_row_id(input_sha: str, json_pointer: str, row: dict) -> str:
    """Sol Phase 0 §9: sha256(input_sha + JSON pointer + canonical row JSON) so DUPLICATE CARD IDS
    cannot hide records — the identity of an audited row is its bytes and its position, never its `id`."""
    canon = json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    h = hashlib.sha256()
    h.update((input_sha or '').encode('utf-8'))
    h.update(b'\x00')
    h.update((json_pointer or '').encode('utf-8'))
    h.update(b'\x00')
    h.update(canon.encode('utf-8'))
    return h.hexdigest()


def find_duplicate_ids(cards: list[dict]) -> dict[str, int]:
    """Sol §Structure: `id` must be globally unique in the clean set. Corpus-level, so it is a separate
    census the per-card screen cannot do alone. Returns {id: count} for every id used more than once."""
    counts: dict[str, int] = {}
    for c in cards:
        cid = c.get('id')
        if cid:
            counts[cid] = counts.get(cid, 0) + 1
    return {cid: n for cid, n in counts.items() if n > 1}


# =================================================================================================
# The dimensions
# =================================================================================================
def _dim_structure(card: dict, dup_ids: frozenset[str]) -> DimensionResult:
    rcs: list[str] = []
    details: list[str] = []
    unknown = sorted(set(card) - TOP_LEVEL_FIELDS)
    if unknown:
        rcs.append(RC_SCHEMA_UNKNOWN_FIELD)
        details.append(f'unknown field(s): {unknown[:5]}')
    for f in sorted(REQUIRED_FIELDS):
        v = card.get(f)
        if v is None or (isinstance(v, str) and not v.strip()):
            rcs.append(RC_SCHEMA_MISSING_FIELD)
            details.append(f'missing/empty required field {f!r}')
    for f, typ in FIELD_TYPES.items():
        if f in card and card[f] is not None:
            v = card[f]
            # bool is an int subclass; a numeric-offset field must NOT be a bool.
            if typ is int and isinstance(v, bool):
                rcs.append(RC_SCHEMA_BAD_TYPE)
                details.append(f'{f!r} is bool, expected int')
            elif not isinstance(v, typ):
                rcs.append(RC_SCHEMA_BAD_TYPE)
                details.append(f'{f!r} is {type(v).__name__}, expected {getattr(typ, "__name__", typ)}')
    cid = card.get('id')
    if not (isinstance(cid, str) and cid.strip()):
        rcs.append(RC_SCHEMA_EMPTY_ID)
        details.append('empty/missing id')
    elif cid in dup_ids:
        rcs.append(RC_SCHEMA_DUP_ID)
        details.append(f'duplicate id {cid!r}')
    verdict = FAIL if rcs else PASS
    return DimensionResult(verdict, sorted(set(rcs)), '; '.join(details))


def _dim_binding(card: dict, graph: P.Graph, policy: P.SourcePolicy) -> DimensionResult:
    binding = RA._binding_from_card(card)
    if not binding:
        return DimensionResult(FAIL, [RC_BINDING_UNBOUND],
                               'no manifestation_id/hash/offsets/span_raw — a DOI names a work, not bytes')
    if not graph.verify_span(binding):
        return DimensionResult(FAIL, [RC_BINDING_SPAN_UNVERIFIED],
                               f'span does not verify against {binding["manifestation_id"]}')
    try:
        att = graph.resolve_attribution(binding, policy)
    except KeyError as e:
        return DimensionResult(FAIL, [RC_BINDING_SPAN_UNVERIFIED], f'{e}')
    rcs: list[str] = []
    details: list[str] = []
    if not att.admitted:
        iv = att.identity_verdict
        if iv in (_DW, _UNR) or iv is None or (getattr(att, 'reason_code', '') or '').startswith('IDENT'):
            rcs.append(RC_BINDING_IDENTITY)
        else:
            rcs.append(RC_BINDING_POLICY_REFUSED)
        details.append(f'not admitted: {att.refusal}')
    else:
        stored = card.get('attribution_target_expression_id')
        if stored and stored != att.names_expression_id:
            rcs.append(RC_BINDING_STALE_TARGET)
            details.append(f'stored target {stored!r} != resolved {att.names_expression_id!r}')
    m = graph.manifestations.get(binding['manifestation_id'])
    if m is not None:
        if card.get('expression_id') and card['expression_id'] != m.expression_id:
            rcs.append(RC_BINDING_EXPR_MISMATCH)
            details.append(f'expression_id {card["expression_id"]!r} != manifestation {m.expression_id!r}')
        wid = m.work_id
        if card.get('work_id') != wid or card.get('evidence_unit_id') != wid:
            rcs.append(RC_BINDING_UNIT_MISMATCH)
            details.append(f'work_id/evidence_unit_id disagree with manifestation work {wid!r}')
    if card.get('source_policy') and card['source_policy'] != policy.name:
        rcs.append(RC_BINDING_POLICY_MISMATCH)
        details.append(f'stored source_policy {card["source_policy"]!r} != derived {policy.name!r}')
    verdict = FAIL if rcs else PASS
    return DimensionResult(verdict, sorted(set(rcs)), '; '.join(details))


def _act_of(card: dict):
    return EM.REGISTRY.acts.get(card.get('act') or '')


def _dim_caches(card: dict, graph: P.Graph, policy: P.SourcePolicy) -> DimensionResult:
    act = _act_of(card)
    if act is None:
        return DimensionResult(FAIL, [RC_ACT_UNKNOWN], f'act {card.get("act")!r} not in registry')
    rcs: list[str] = []
    details: list[str] = []
    # claim == derive_claim(card, act) after canonical normalization
    try:
        want = EM.derive_claim(card, act)
    except Exception as e:                              # noqa: BLE001 - a recompute crash is a fail
        want = None
        rcs.append(RC_CACHE_CLAIM_MISMATCH)
        details.append(f'derive_claim raised {type(e).__name__}')
    if want is not None and canonicalize(card.get('claim') or '') != canonicalize(want):
        rcs.append(RC_CACHE_CLAIM_MISMATCH)
        details.append('claim is not the recomputed derive_claim(card, act)')
    # span_numbers / has_number recompute from the SAME field the miner used (card['span'])
    span_nums = EM.number_tokens(card.get('span') or '')
    if sorted(span_nums) != list(card.get('span_numbers') or []):
        rcs.append(RC_CACHE_SPAN_NUMBERS)
        details.append('span_numbers != number_tokens(span)')
    if bool(span_nums) != bool(card.get('has_number')):
        rcs.append(RC_CACHE_HAS_NUMBER)
        details.append('has_number != bool(span_numbers)')
    # complete_tuple == is_complete(card) and act.tuple_bearing
    try:
        want_ct = bool(EM.is_complete(card) and act.tuple_bearing)
        if want_ct != bool(card.get('complete_tuple')):
            rcs.append(RC_CACHE_COMPLETE_TUPLE)
            details.append('complete_tuple != is_complete(card) and act.tuple_bearing')
    except Exception:                                  # noqa: BLE001
        pass
    # n_sources / n_evidence_units must equal VERIFIED independent evidence units, not stored counts.
    verified_units = _verified_evidence_units(card, graph, policy)
    n = len(verified_units)
    if card.get('n_sources') is not None and int(card['n_sources']) != n:
        rcs.append(RC_CACHE_COUNTS)
        details.append(f'n_sources={card.get("n_sources")} but {n} independently-verified unit(s)')
    if card.get('n_evidence_units') is not None and int(card['n_evidence_units']) != n:
        rcs.append(RC_CACHE_COUNTS)
        details.append(f'n_evidence_units={card.get("n_evidence_units")} but {n} verified unit(s)')
    verdict = FAIL if rcs else PASS
    return DimensionResult(verdict, sorted(set(rcs)), '; '.join(details))


def _verified_evidence_units(card: dict, graph: P.Graph, policy: P.SourcePolicy) -> set[str]:
    """The distinct evidence units this card ACTUALLY has bytes for: the primary, plus each corroborator
    whose nested binding is complete AND verifies. A corroborator serialized without span_raw/permitted
    ids (the miner's lossy-consolidation defect) contributes nothing — Sol §Structure/§Report."""
    units: set[str] = set()
    if card.get('evidence_unit_id') and _dim_binding(card, graph, policy).verdict == PASS:
        units.add(card['evidence_unit_id'])
    for edge in (card.get('corroborating_sources') or []):
        if screen_support_edge(edge, graph, policy).verdict == PASS and edge.get('evidence_unit_id'):
            units.add(edge['evidence_unit_id'])
    return units


def _dim_numeric(card: dict) -> DimensionResult:
    """MECHANICAL numeric fidelity (Sol §Numeric fidelity, report-AST mechanical half): every number and
    every (number, unit) the CLAIM asserts must stand alone in the span. A mechanical pass is never an
    admission — Opus atom comparison still runs in Tier 1 — but a mechanical FAIL is decisive offline."""
    claim = card.get('claim') or ''
    span = card.get('span') or ''
    claim_q = RA.quantities_in(claim.lower())
    claim_nums = EM.number_tokens(claim)
    if not claim_nums and not claim_q:
        return DimensionResult(NOT_APPLICABLE, [], 'claim states no quantity')
    span_low = span.lower()
    span_nums = EM.number_tokens(span)
    rcs: list[str] = []
    details: list[str] = []
    fabricated = claim_nums - span_nums
    if fabricated:
        rcs.append(RC_NUMERIC_FABRICATED)
        details.append(f'claim number(s) not standing alone in span: {sorted(fabricated)}')
    span_q = RA.quantities_in(span_low)
    for num, unit in claim_q:
        if not unit:
            continue
        if not any(n == num and u == unit for n, u in span_q):
            rcs.append(RC_NUMERIC_UNIT)
            details.append(f'claim unit for {num}{(" " + unit) if unit else ""} not matched in span')
    verdict = FAIL if rcs else PASS
    return DimensionResult(verdict, sorted(set(rcs)), '; '.join(details))


# ---- CoT contamination: a POSITIVE structural test (Sol §CoT) ------------------------------------
# Structural scaffolding a source span essentially never is. Used ONLY to hard-FAIL; never to PASS.
_ROLE_MARK = re.compile(r'(<\|)|(^|\n)\s*(system|assistant|user)\s*:|"role"\s*:', re.I)
_FENCE = re.compile(r'```')


def _is_scaffold(value: str) -> bool:
    v = value.strip()
    if _FENCE.search(v) or _ROLE_MARK.search(v):
        return True
    # a field whose whole content parses as a JSON object/array is prompt/response scaffolding, not prose
    if (v.startswith('{') and v.endswith('}')) or (v.startswith('[') and v.endswith(']')):
        try:
            json.loads(v)
            return True
        except Exception:                              # noqa: BLE001
            return False
    return False


def _classify_field(field: str, value, card: dict, act) -> FieldContentClass:
    if isinstance(value, list):
        joined = ' '.join(str(x) for x in value)
    else:
        joined = value if isinstance(value, str) else ''
    if not (joined or '').strip():
        return FieldContentClass(field, EMPTY, PASS)
    if _is_scaffold(joined):
        return FieldContentClass(field, '', FAIL, RC_COT_SCAFFOLD)
    if field == 'span_raw':
        return FieldContentClass(field, SOURCE_BYTES, PASS)
    if field == 'span':
        ok = _collapse(card.get('span_raw') or '') == _collapse(joined)
        return FieldContentClass(field, CANONICAL_SOURCE_VIEW, PASS if ok else NEEDS_OPUS,
                                 '' if ok else RC_COT_UNCLASSIFIED)
    if field == 'claim':
        try:
            want = EM.derive_claim(card, act) if act is not None else None
        except Exception:                              # noqa: BLE001
            want = None
        ok = want is not None and canonicalize(joined) == canonicalize(want)
        return FieldContentClass(field, DERIVED_CACHE, PASS if ok else FAIL,
                                 '' if ok else RC_COT_STALE_CACHE)
    if field in GRAPH_METADATA_FIELDS:
        # equality with live graph metadata is enforced by DIM_BINDING; here the CLASS is graph metadata.
        return FieldContentClass(field, GRAPH_METADATA, PASS)
    if field in REGISTRY_FIELDS:
        ok = _registry_member(field, joined)
        return FieldContentClass(field, REGISTRY_VALUE, PASS if ok else NEEDS_OPUS,
                                 '' if ok else RC_COT_UNCLASSIFIED)
    if field in ATOMIC_FIELDS:
        # deterministically clean ONLY when it is a verbatim slice of the span; else a model must judge
        # whether the concise value is genuinely supported by its declared window.
        if _collapse(joined) and _collapse(joined) in _collapse(card.get('span') or ''):
            return FieldContentClass(field, ATOMIC_EVIDENCE_VALUE, PASS)
        return FieldContentClass(field, '', NEEDS_OPUS, RC_COT_UNCLASSIFIED)
    # any other unenumerated free-text field cannot be proven clean offline
    return FieldContentClass(field, '', NEEDS_OPUS, RC_COT_UNCLASSIFIED)


def _registry_member(field: str, value: str) -> bool:
    if field == 'act':
        return value in EM.REGISTRY.acts
    if field == 'act_registry_version':
        return value == EM.REGISTRY.version
    if field == 'card_kind':
        return value in _CARD_KINDS
    if field == 'source_policy':
        return value in _POLICY_NAMES
    # `section` and `text_field` are open registry strings; treat any non-scaffold token as a member.
    return True


def _dim_cot(card: dict) -> tuple[DimensionResult, list[FieldContentClass]]:
    act = _act_of(card)
    classes: list[FieldContentClass] = []
    for f in sorted(card):
        if f in COT_SKIP_FIELDS:
            continue                                   # nested structures / facet / number caches
        v = card[f]
        if isinstance(v, (str, list)):
            classes.append(_classify_field(f, v, card, act))
    fails = [c for c in classes if c.verdict == FAIL]
    needs = [c for c in classes if c.verdict == NEEDS_OPUS]
    if fails:
        rcs = sorted({c.reason_code for c in fails if c.reason_code})
        return DimensionResult(FAIL, rcs, f'{len(fails)} contaminated/uncomputable field(s)'), classes
    if needs:
        return DimensionResult(NEEDS_OPUS, [RC_COT_UNCLASSIFIED],
                               f'{len(needs)} field(s) require Opus content classification'), classes
    return DimensionResult(PASS, [], ''), classes


def _dim_facet(card: dict, taxonomy, tagger) -> DimensionResult:
    if taxonomy is None and tagger is None:
        return DimensionResult(NEEDS_CONTRACT, [],
                               'no contract taxonomy pinned — Sol: the audit must not invent a topic')
    rcs: list[str] = []
    details: list[str] = []
    tags_span = list(card.get('facet_tags_span') or [])
    all_tags = list(card.get('facet_tags') or [])
    if taxonomy is not None:
        for t in set(tags_span) | set(all_tags):
            if t not in taxonomy:
                rcs.append(RC_FACET_NOT_IN_TAXONOMY)
                details.append(f'tag {t!r} not in pinned taxonomy')
    if tagger is not None:
        try:
            recomputed = list(tagger(card.get('span') or ''))
        except Exception as e:                         # noqa: BLE001
            recomputed = None
            details.append(f'tagger raised {type(e).__name__}')
        if recomputed is not None and set(tags_span) != set(recomputed):
            rcs.append(RC_FACET_UNSUPPORTED)
            details.append(f'facet_tags_span {tags_span} != recomputed {recomputed}')
    verdict = FAIL if rcs else PASS
    return DimensionResult(verdict, sorted(set(rcs)), '; '.join(details))


def screen_support_edge(edge: dict, graph: P.Graph, policy: P.SourcePolicy) -> DimensionResult:
    """One `corroborating_sources` support edge. Sol §Structure: it must have a COMPLETE independent
    binding and verify on its own. It never inherits the primary card's pass."""
    missing = [f for f in sorted(SUPPORT_EDGE_BINDING_FIELDS)
               if edge.get(f) is None or (isinstance(edge.get(f), str) and not edge[f].strip())]
    if missing:
        return DimensionResult(FAIL, [RC_CORR_INCOMPLETE_BINDING],
                               f'nested binding missing {missing} (cannot be independently verified)')
    binding = RA._binding_from_card(edge)
    if not binding or not graph.verify_span(binding):
        return DimensionResult(FAIL, [RC_CORR_SPAN_UNVERIFIED],
                               'nested span does not verify against its bytes')
    try:
        att = graph.resolve_attribution(binding, policy)
    except KeyError as e:
        return DimensionResult(FAIL, [RC_CORR_SPAN_UNVERIFIED], f'{e}')
    if not att.admitted:
        return DimensionResult(FAIL, [RC_CORR_SPAN_UNVERIFIED], f'not admitted: {att.refusal}')
    return DimensionResult(PASS, [], '')


def _dim_corroborator(card: dict, graph: P.Graph, policy: P.SourcePolicy) -> DimensionResult:
    edges = card.get('corroborating_sources') or []
    if not edges:
        return DimensionResult(NOT_APPLICABLE, [], 'no corroborating sources')
    rcs: list[str] = []
    n_bad = 0
    for i, edge in enumerate(edges):
        r = screen_support_edge(edge, graph, policy)
        if r.verdict != PASS:
            n_bad += 1
            rcs.extend(r.reason_codes)
    verdict = FAIL if n_bad else PASS
    return DimensionResult(verdict, sorted(set(rcs)),
                           f'{n_bad}/{len(edges)} support edge(s) have no complete verified binding')


# =================================================================================================
# The public entry points
# =================================================================================================
def screen_card(card: dict, graph: P.Graph, policy: P.SourcePolicy, *,
                taxonomy=None, tagger=None, input_sha: str = '', json_pointer: str = '',
                dup_ids: frozenset[str] = frozenset()) -> DeterministicReceipt:
    """Run every Tier-0 dimension on ONE top-level card and return its append-only receipt. Sol Phase 1
    §7: every dimension runs even after a hard failure, so the adversary battery can show each planted
    fault was independently detected."""
    dims: dict[str, DimensionResult] = {}
    dims[DIM_STRUCTURE] = _dim_structure(card, dup_ids)
    dims[DIM_BINDING] = _dim_binding(card, graph, policy)
    dims[DIM_CACHES] = _dim_caches(card, graph, policy)
    dims[DIM_NUMERIC] = _dim_numeric(card)
    cot, classes = _dim_cot(card)
    dims[DIM_COT] = cot
    dims[DIM_FACET] = _dim_facet(card, taxonomy, tagger)
    dims[DIM_CORROBORATOR] = _dim_corroborator(card, graph, policy)

    verdicts = [d.verdict for d in dims.values()]
    if FAIL in verdicts:
        overall = FAIL
    elif NEEDS_OPUS in verdicts or NEEDS_CONTRACT in verdicts or UNCERTAIN in verdicts:
        overall = NEEDS_OPUS
    else:
        overall = PASS
    return DeterministicReceipt(
        audit_row_id=audit_row_id(input_sha, json_pointer, card),
        card_id=card.get('id') or '', scope='top_level', json_pointer=json_pointer,
        overall=overall, dimensions=dims, content_classes=classes)


def screen_corpus(cards: list[dict], graph: P.Graph, policy: P.SourcePolicy, *,
                  taxonomy=None, tagger=None, input_sha: str = '') -> list[DeterministicReceipt]:
    """Screen a whole serialized card list. Duplicate ids are computed once, over the census, and fed to
    every per-card structure check (Sol §Structure: id must be globally unique in the clean set)."""
    dup = frozenset(find_duplicate_ids(cards))
    out: list[DeterministicReceipt] = []
    for i, c in enumerate(cards):
        out.append(screen_card(c, graph, policy, taxonomy=taxonomy, tagger=tagger,
                               input_sha=input_sha, json_pointer=f'/{i}', dup_ids=dup))
    return out
