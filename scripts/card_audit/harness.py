#!/usr/bin/env python3
"""Tier-1/2/3 Opus semantic audit harness (Sol §3 "Tier 1 / Tier 2 / Tier 3", §Faithfulness, §Numeric
fidelity, §Relevance, §Voice, §4 disposition rules).

Where Tier-0 (`card_audit.tier0`) decides everything provable OFFLINE on structure alone, THIS module
runs the parts that need a model — but it never lets the model manufacture an admit a deterministic gate
already refused:

  FAITHFULNESS is NOT reinvented. The authoritative faithfulness verdict is `report_ast.entailed_by_span`
  called on the exact verified span bytes and the canonically-normalized claim (Sol §Faithfulness step 4,
  and §1 "reuse the entailment judge"). A report-AST FAIL is decisive and CANNOT be overridden by an Opus
  opinion (Sol §Faithfulness, §Tier 3). Opus is asked for its atom-level opinion too, but a card whose
  span does not entail its claim fails no matter what Opus says.

  TIER 1 / TIER 2 are two INDEPENDENT Opus passes (Sol §Tier 1, §Tier 2). Each is a fresh, self-contained
  `claude -p --model opus --effort max` session with a read-only packet: no Agent/Bash/Edit/Write/web
  tools, no access to the other pass's verdict, and a JSON-schema-constrained structured receipt — never
  a reasoning trace (Sol §"Efficient execution", §Phase 2). There is NO cheaper fallback: a provider
  failure retries the SAME model up to N times and then fails closed; Sonnet/Haiku/GLM/"deterministic
  pass" are never substituted (Sol §"Efficient execution").

  TIER 3 adjudicates (Sol §Tier 3) when the two passes disagree, either fails, report-AST passes but Opus
  alleges an unsupported atom, or a repair/edge-removal/OWNED-demotion is proposed. The adjudicator may
  overturn an Opus FALSE POSITIVE, but it CANNOT override a failed byte binding or a failed
  `entailed_by_span` — those require a repaired card and a full rerun.

GENERALITY (Sol Phase 8): there is not one DOI, title, subject, venue or benchmark literal in this file
or in the prompts it builds. Every injected value (research question, contract facets, span, card fields)
is a parameter, so a clinical / legal / economics / CS corpus is audited by the identical harness. The
legacy `scripts/quarantine.py` is deliberately NOT imported (Sol §1: it hardcodes journal-only policy).

The Opus transport is INJECTABLE (`OpusRunner`). Production wires `subprocess_opus_runner`, which shells
`claude -p`; tests inject a deterministic stub, exactly as `report_ast.set_entailment_judge` lets the
faithfulness judge be stubbed. So the whole tier ladder is validated hermetically without a real call.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import provenance as P
import report_ast as RA

from card_audit.audit_schema import PASS, FAIL, UNCERTAIN, NOT_APPLICABLE
from card_audit.tier0 import canonicalize

# =================================================================================================
# Constants: passes, voice, the closed relevance / disposition / numeric-subdimension vocabularies
# =================================================================================================
PASS_A = 'A'          # Tier-1 first Opus pass
PASS_B = 'B'          # Tier-2 second, independent Opus pass
PASS_ADJ = 'ADJ'      # Tier-3 adjudication

# Sol §Voice: the current v2 schema has no voice field, so every incoming card is normalized ATTRIBUTED.
# A failing card is NEVER silently reinterpreted as OWNED; only an explicit repair disposition may create
# an OWNED suggestion, and that is not citeable evidence.
VOICE_ATTRIBUTED = 'ATTRIBUTED'
VOICE_OWNED = 'OWNED'

# Sol §Faithfulness: an ATTRIBUTED card that is structurally unreachable (span cannot be resolved) still
# gets the other semantic judgments, but its faithfulness verdict is UNREACHABLE — never PASS.
FAITH_UNREACHABLE = 'UNREACHABLE'

# Sol §Relevance: pass ONLY these two classifications; everything else fails.
REL_DIRECT = 'DIRECT_ANSWER_EVIDENCE'
REL_CONTEXT = 'NECESSARY_CONTEXT'
REL_PASS_CLASSES = frozenset({REL_DIRECT, REL_CONTEXT})
REL_CLASSES = frozenset({
    REL_DIRECT, REL_CONTEXT,
    'ADJACENT_SUBJECT', 'GENERIC_FILLER', 'OTHER_QUESTION', 'METADATA_OR_METHODS_ONLY',
    'RELEVANCE_OUTSIDE_BINDING',
})

# Sol §Numeric fidelity: all twelve subdimensions must pass for a numeric claim.
NUMERIC_SUBDIMENSIONS = (
    'number', 'direction', 'magnitude', 'unit', 'comparator', 'population',
    'geography', 'period', 'scope', 'uncertainty', 'modality', 'precision',
)

# Sol §4: the closed disposition vocabulary. There is no DELETE.
DISPOSITIONS = frozenset({
    'KEEP_UNCHANGED', 'REPAIR_TIGHTEN', 'REBASE_TO_VALID_SUPPORT', 'REMOVE_BAD_SUPPORT_EDGE',
    'DEMOTE_TO_OWNED_SUGGESTION', 'QUARANTINE_CARD', 'QUARANTINE_SUPPORT_EDGE',
})

# Stable machine reason codes this harness cites (Sol §Report: quarantine counts by stable reason code).
RC_FAITH_NOT_ENTAILED = 'faithfulness.span_does_not_entail_claim'
RC_FAITH_UNREACHABLE = 'faithfulness.span_unreachable'
RC_FAITH_NO_CLAIM = 'faithfulness.no_claim_to_test'
RC_CORR_NOT_ENTAILED = 'faithfulness.corroborator_does_not_entail_primary'
RC_OPUS_SCHEMA = 'opus.response_failed_schema'
RC_OPUS_MODEL = 'opus.model_not_verified_as_opus'
RC_OPUS_TRANSPORT = 'opus.transport_failed_after_retries'
RC_OPUS_DISAGREE = 'opus.pass_a_b_disagree'
RC_OPUS_ALLEGES_ATOM = 'opus.alleges_unsupported_atom_reportast_passed'
RC_OPUS_RELEVANCE = 'opus.card_not_relevant'
RC_OPUS_NUMERIC = 'opus.numeric_atom_failed'
RC_OPUS_COT = 'opus.field_not_clean_content_class'
RC_OPUS_FACET = 'opus.facet_tag_unsupported'
RC_VOICE_LAUNDER = 'voice.attributed_to_owned_launder_blocked'

_LEGAL_VERDICTS = frozenset({PASS, FAIL, UNCERTAIN, NOT_APPLICABLE})


# =================================================================================================
# Faithfulness — REUSE report_ast.entailed_by_span, never reinvent (Sol §1, §Faithfulness)
# =================================================================================================
def resolve_verified_span(card: dict, graph: P.Graph) -> str | None:
    """Sol §Faithfulness steps 1-2: resolve the EXACT raw binding and return
    `manifestation.text[span_start:span_end]` — but only if the binding actually verifies against its
    bytes. A span that does not verify is structurally unreachable, not admissible evidence, and its
    faithfulness verdict is UNREACHABLE (never tested against `card['span']`, wider context, or another
    source). Returns None when unreachable."""
    binding = RA._binding_from_card(card)
    if not binding:
        return None
    try:
        if not graph.verify_span(binding):
            return None
    except Exception:                                   # noqa: BLE001 — an unverifiable binding is unreachable
        return None
    m = graph.manifestations.get(binding['manifestation_id'])
    if m is None:
        return None
    s, e = card.get('span_start'), card.get('span_end')
    if not isinstance(s, int) or not isinstance(e, int) or isinstance(s, bool) or isinstance(e, bool):
        return None
    text = m.text or ''
    if s < 0 or e > len(text) or e <= s:
        return None
    return text[s:e]


def _work_for(card: dict, graph: P.Graph) -> P.Work | None:
    binding = RA._binding_from_card(card)
    if binding:
        m = graph.manifestations.get(binding.get('manifestation_id'))
        if m is not None:
            return graph.works.get(m.work_id)
    return graph.works.get(card.get('work_id') or '')


@dataclass
class FaithfulnessReceipt:
    """The report-AST faithfulness result for one claim/span pair (primary or one corroborator). This is
    AUTHORITATIVE: a FAIL here cannot be overridden by Opus (Sol §Faithfulness, §Tier 3)."""
    verdict: str                       # PASS / FAIL / NOT_APPLICABLE
    faith_label: str                   # ENTAILED / NOT_ENTAILED / UNREACHABLE / NO_CLAIM
    reason_codes: list[str] = field(default_factory=list)
    detail: str = ''
    role: str = 'primary'              # 'primary' | 'corroborator'

    def to_json(self) -> dict:
        return dict(verdict=self.verdict, faith_label=self.faith_label,
                    reason_codes=list(self.reason_codes), detail=self.detail, role=self.role)


def audit_faithfulness_primary(card: dict, graph: P.Graph) -> FaithfulnessReceipt:
    """Sol §Faithfulness: the primary claim must be ENTAILED by its OWN bound span. Normalize the claim
    exactly as the composer does (HTML-unescape, collapse whitespace, strip a single trailing period) and
    call `report_ast.entailed_by_span(normalized_claim, resolved_span, work)`. Pass ONLY on (True, '')."""
    claim = canonicalize(card.get('claim') or '')
    if not claim:
        return FaithfulnessReceipt(NOT_APPLICABLE, 'NO_CLAIM', [RC_FAITH_NO_CLAIM],
                                   'card carries no claim to test', 'primary')
    span = resolve_verified_span(card, graph)
    if span is None:
        return FaithfulnessReceipt(FAIL, FAITH_UNREACHABLE, [RC_FAITH_UNREACHABLE],
                                   'span structurally unreachable — binding does not verify', 'primary')
    ok, why = RA.entailed_by_span(claim, span, _work_for(card, graph))
    if ok:
        return FaithfulnessReceipt(PASS, 'ENTAILED', [], '', 'primary')
    return FaithfulnessReceipt(FAIL, 'NOT_ENTAILED', [RC_FAITH_NOT_ENTAILED],
                               f'entailed_by_span rejected: {why}', 'primary')


def audit_faithfulness_corroborators(card: dict, graph: P.Graph) -> list[FaithfulnessReceipt]:
    """Sol §Faithfulness: "A corroborating span must INDEPENDENTLY entail the primary claim. It never
    inherits the primary card's pass." So each corroborator's own verified span is tested against the
    PRIMARY card's normalized claim — never against the corroborator's own restatement, never concatenated
    with the primary span (that recreates evidence laundering)."""
    claim = canonicalize(card.get('claim') or '')
    out: list[FaithfulnessReceipt] = []
    for i, edge in enumerate(card.get('corroborating_sources') or []):
        if not claim:
            out.append(FaithfulnessReceipt(NOT_APPLICABLE, 'NO_CLAIM', [RC_FAITH_NO_CLAIM],
                                           'primary carries no claim to corroborate', 'corroborator'))
            continue
        span = resolve_verified_span(edge, graph)
        if span is None:
            out.append(FaithfulnessReceipt(FAIL, FAITH_UNREACHABLE, [RC_FAITH_UNREACHABLE],
                                           f'corroborator[{i}] span unreachable', 'corroborator'))
            continue
        ok, why = RA.entailed_by_span(claim, span, _work_for(edge, graph))
        if ok:
            out.append(FaithfulnessReceipt(PASS, 'ENTAILED', [], f'corroborator[{i}]', 'corroborator'))
        else:
            out.append(FaithfulnessReceipt(FAIL, 'NOT_ENTAILED', [RC_CORR_NOT_ENTAILED],
                                           f'corroborator[{i}] does not entail primary: {why}',
                                           'corroborator'))
    return out


# =================================================================================================
# Voice — Sol §Voice: normalize every incoming v2 card ATTRIBUTED; never silently flip to OWNED
# =================================================================================================
def normalize_voice(_card: dict) -> str:
    """The v2 schema has no voice field, so every incoming evidence card is ATTRIBUTED. `card_kind` is not
    voice. Only an explicit repair disposition may later produce an OWNED suggestion (Sol §Voice)."""
    return VOICE_ATTRIBUTED


def voice_launder_blocked(final_disposition: str, faith: FaithfulnessReceipt) -> bool:
    """Sol §Voice / §4 DEMOTE_TO_OWNED_SUGGESTION: a FAILING card must never be laundered into an OWNED
    suggestion that keeps its particulars. A demotion is only sound when the faithfulness failure is not
    being smuggled through as owned prose that still carries the unsupported claim. Here we simply refuse
    the ONE illegal transition — an OWNED demotion of a card whose span does not verify at all (an
    unreachable binding), which has no source bytes to demote FROM."""
    return final_disposition == 'DEMOTE_TO_OWNED_SUGGESTION' and faith.faith_label == FAITH_UNREACHABLE


# =================================================================================================
# The Opus structured-verdict schema and its validator (Sol §Phase 2: validate before accepting)
# =================================================================================================
def opus_response_json_schema() -> dict:
    """The JSON schema passed to `claude -p --json-schema` AND used to validate every response before it
    is accepted (Sol Phase 2 step 6, Phase 3 step 5). Per-dimension objects, machine reason codes, an
    unsupported atom + deciding source substring, a content class for every non-empty field, and — for a
    numeric claim — every numeric subdimension verdict. No free-form reasoning field exists."""
    verdict_enum = sorted(_LEGAL_VERDICTS)
    dim = {
        'type': 'object', 'additionalProperties': False,
        'required': ['verdict'],
        'properties': {
            'verdict': {'type': 'string', 'enum': verdict_enum},
            'reason_code': {'type': 'string'},
            'unsupported_atom': {'type': 'string'},
            'deciding_substring': {'type': 'string'},
            'affected_field': {'type': 'string'},
        },
    }
    numeric = {
        'type': 'object', 'additionalProperties': False,
        'required': ['applicable', 'subdimensions'],
        'properties': {
            'applicable': {'type': 'boolean'},
            'subdimensions': {
                'type': 'object', 'additionalProperties': False,
                'properties': {k: {'type': 'string', 'enum': verdict_enum} for k in NUMERIC_SUBDIMENSIONS},
            },
            'unsupported_atom': {'type': 'string'},
            'deciding_substring': {'type': 'string'},
        },
    }
    relevance = {
        'type': 'object', 'additionalProperties': False,
        'required': ['verdict', 'classification'],
        'properties': {
            'verdict': {'type': 'string', 'enum': verdict_enum},
            'classification': {'type': 'string', 'enum': sorted(REL_CLASSES)},
            'reason_code': {'type': 'string'},
            'connection_to_question': {'type': 'string'},
        },
    }
    facet = {
        'type': 'object', 'additionalProperties': False,
        'required': ['verdict'],
        'properties': {
            'verdict': {'type': 'string', 'enum': verdict_enum},
            'unsupported_tags': {'type': 'array', 'items': {'type': 'string'}},
        },
    }
    content_class = {
        'type': 'object', 'additionalProperties': False,
        'required': ['field', 'content_class', 'verdict'],
        'properties': {
            'field': {'type': 'string'},
            'content_class': {'type': 'string'},
            'verdict': {'type': 'string', 'enum': verdict_enum},
        },
    }
    return {
        'type': 'object', 'additionalProperties': False,
        'required': ['audit_row_id', 'faithfulness', 'numeric', 'relevance', 'facet',
                     'content_classes', 'proposed_disposition'],
        'properties': {
            'audit_row_id': {'type': 'string'},
            'faithfulness': dim,
            'numeric': numeric,
            'relevance': relevance,
            'facet': facet,
            'content_classes': {'type': 'array', 'items': content_class},
            'proposed_disposition': {'type': 'string', 'enum': sorted(DISPOSITIONS)},
        },
    }


class OpusResponseInvalid(Exception):
    """A response that fails schema validation. Sol Phase 1/3: missing/uncertain judge results are
    FAILURES; a malformed judge output is never read as a pass."""


def validate_opus_response(obj, expected_audit_row_id: str) -> dict:
    """Validate a parsed Opus response against `opus_response_json_schema` WITHOUT a third-party jsonschema
    dependency — a small, explicit, fail-closed checker. Raises OpusResponseInvalid on any deviation, so
    an unvalidated response can never enter the verdict set (Sol Phase 3 step 5)."""
    if not isinstance(obj, dict):
        raise OpusResponseInvalid('response is not a JSON object')
    schema = opus_response_json_schema()
    for k in schema['required']:
        if k not in obj:
            raise OpusResponseInvalid(f'missing required key {k!r}')
    unknown = set(obj) - set(schema['properties'])
    if unknown:
        raise OpusResponseInvalid(f'unknown top-level key(s): {sorted(unknown)}')
    if obj['audit_row_id'] != expected_audit_row_id:
        raise OpusResponseInvalid(
            f'audit_row_id {obj["audit_row_id"]!r} != requested {expected_audit_row_id!r}')

    def _check_verdict(v, where):
        if v not in _LEGAL_VERDICTS:
            raise OpusResponseInvalid(f'{where}: illegal verdict {v!r}')

    _check_verdict(obj['faithfulness'].get('verdict'), 'faithfulness')

    num = obj['numeric']
    if not isinstance(num.get('applicable'), bool):
        raise OpusResponseInvalid('numeric.applicable must be a bool')
    subs = num.get('subdimensions') or {}
    if num['applicable']:
        for k in NUMERIC_SUBDIMENSIONS:
            if k not in subs:
                raise OpusResponseInvalid(f'numeric claim missing subdimension {k!r}')
            _check_verdict(subs[k], f'numeric.{k}')
    for k, v in subs.items():
        if k not in NUMERIC_SUBDIMENSIONS:
            raise OpusResponseInvalid(f'unknown numeric subdimension {k!r}')
        _check_verdict(v, f'numeric.{k}')

    rel = obj['relevance']
    _check_verdict(rel.get('verdict'), 'relevance')
    if rel.get('classification') not in REL_CLASSES:
        raise OpusResponseInvalid(f'relevance.classification illegal: {rel.get("classification")!r}')

    _check_verdict(obj['facet'].get('verdict'), 'facet')

    if not isinstance(obj['content_classes'], list):
        raise OpusResponseInvalid('content_classes must be a list')
    for cc in obj['content_classes']:
        if not isinstance(cc, dict) or {'field', 'content_class', 'verdict'} - set(cc):
            raise OpusResponseInvalid('content_classes entry missing field/content_class/verdict')
        _check_verdict(cc['verdict'], f'content_class[{cc.get("field")}]')

    if obj['proposed_disposition'] not in DISPOSITIONS:
        raise OpusResponseInvalid(f'illegal proposed_disposition {obj["proposed_disposition"]!r}')
    return obj


# =================================================================================================
# The Opus transport — INJECTABLE, opus-only, no cheaper fallback (Sol §"Efficient execution")
# =================================================================================================
class OpusUnavailable(Exception):
    """The opus transport could not be used at all (CLI absent, or every retry failed). Fails closed."""


def model_is_opus(result: dict) -> bool:
    """Sol Phase 3 step 5 / §"Efficient execution": REQUIRE response metadata to prove the requested model
    was Opus, and prove it was NOT a cheaper model. Reads the `claude -p --output-format json` envelope:
    `modelUsage` is keyed by the model id(s) actually billed, and `model` names the primary model."""
    usage = result.get('modelUsage') or {}
    hay = ' '.join(list(usage.keys()) + [str(result.get('model') or '')]).lower()
    if 'opus' not in hay:
        return False                                    # no opus anywhere -> rejects sonnet/haiku/glm-only
    # opus IS present. The `claude -p` CLI bills a small auxiliary housekeeping turn on a cheaper model
    # (e.g. a haiku title/summary) even under `--model opus`, so mere co-occurrence is not disqualifying.
    # Require that the SUBSTANTIVE answer came from opus: the model that produced the most OUTPUT tokens
    # must be opus. A decoy where a cheaper model does the real work while opus is billed one token fails.
    _CHEAP = ('sonnet', 'haiku', 'glm', 'gpt', 'gemini', 'llama', 'mistral')

    def _out(v):
        return (v.get('outputTokens') or v.get('output_tokens') or 0) if isinstance(v, dict) else 0

    outs = {k.lower(): _out(v) for k, v in usage.items()}
    if outs and any(outs.values()):
        dominant = max(outs, key=lambda k: outs[k])
        return 'opus' in dominant and not any(c in dominant for c in _CHEAP)
    # No output-token telemetry (e.g. a test stub): accept only if the primary `model` is not a cheaper one.
    primary = str(result.get('model') or '').lower()
    return not (primary and any(c in primary for c in _CHEAP))


# An OpusRunner is a callable(prompt: str, schema: dict) -> dict, returning the parsed `claude -p`
# JSON envelope (the object with `result`, `modelUsage`, `is_error`, ...). Production wires
# `subprocess_opus_runner`; tests inject a deterministic stub.
def subprocess_opus_runner(prompt: str, schema: dict, *, timeout_s: int = 900,
                           max_retries: int = 3) -> dict:
    """Production transport: a fresh `claude -p --model opus --effort max` session with a read-only,
    self-contained packet and NO Agent/Bash/Edit/Write/web/task tools (Sol §"Efficient execution"). A
    provider failure retries the SAME model up to `max_retries` times; there is NO degrade to a cheaper
    model and NO deterministic "pass" (Sol). Raises OpusUnavailable if it cannot get a valid envelope."""
    if not shutil.which('claude'):
        raise OpusUnavailable('claude CLI not on PATH')
    cmd = [
        'claude', '-p',
        '--model', 'opus',
        '--effort', 'max',
        '--permission-mode', 'dontAsk',
        '--output-format', 'json',
        # This CLI takes the JSON SCHEMA INLINE, not a file path (a path is parsed as JSON and rejected).
        '--json-schema', json.dumps(schema),
        # a read-only worker: no tools that could edit the repo, touch the mine, or spawn a subagent.
        '--disallowedTools', 'Agent,Task,Bash,Edit,Write,WebFetch,WebSearch,AskUserQuestion,ExitPlanMode',
    ]
    last_err = ''
    for _attempt in range(max(1, max_retries)):
        try:
            r = subprocess.run(cmd, input=prompt.encode('utf-8'), capture_output=True, timeout=timeout_s)
        except subprocess.TimeoutExpired:
            last_err = f'timeout after {timeout_s}s'
            continue
        except Exception as e:                          # noqa: BLE001
            last_err = f'invocation failed: {e!r}'
            continue
        try:
            envelope = json.loads(r.stdout.decode('utf-8', errors='replace'))
        except Exception:                               # noqa: BLE001
            last_err = f'non-JSON envelope (rc={r.returncode}): {r.stderr.decode("utf-8", "replace")[:200]}'
            continue
        if envelope.get('is_error'):
            last_err = f'claude reported is_error: {envelope.get("subtype")}'
            continue
        return envelope
    raise OpusUnavailable(f'opus transport failed after {max_retries} retries: {last_err}')


# =================================================================================================
# Prompt construction — self-contained, injected values only (Sol Phase 2 step 1, §Generality)
# =================================================================================================
def _card_view(card: dict) -> dict:
    """The read-only, injected card fields a worker sees. No live graph handles, no other card's verdict,
    no policy object — just the serialized values (Sol Phase 2 step 1: prompts accept only injected
    values)."""
    return {k: card[k] for k in sorted(card)
            if k not in ('corroborating_sources', 'same_unit_other_expressions', 'field_provenance')
            and isinstance(card[k], (str, int, float, bool, list))}


def build_opus_packet(card: dict, graph: P.Graph, *, question: str, contract_facets: list[str],
                      det_receipt=None, support_role: str = 'primary') -> dict:
    """Assemble the injected packet for one card (Sol Phase 2 step 1). `resolved_span` is the EXACT
    verified span the worker judges against — the worker never re-resolves bytes and cannot reach beyond
    its binding. Returns a plain dict serialized into the prompt."""
    return dict(
        audit_row_id=(det_receipt.audit_row_id if det_receipt is not None else ''),
        research_question=question,
        contract_facets=list(contract_facets or []),
        support_role=support_role,
        card=_card_view(card),
        resolved_span=resolve_verified_span(card, graph) or '',
        deterministic_receipt=(det_receipt.to_json() if det_receipt is not None else {}),
    )


def build_opus_prompt(packet: dict, schema: dict) -> str:
    """The self-contained instruction. It names NO subject, DOI, venue, benchmark, or fixed source policy
    — the research question and contract facets are injected (Sol Phase 2 step 5). It demands a JSON
    receipt matching `schema` and forbids any prose reasoning trace (Sol §"Efficient execution")."""
    return (
        'You are a STRICT, independent auditor of one evidence card extracted from a source document for '
        'a literature review. You judge ONLY the injected packet below. You may not browse, run tools, or '
        'reason aloud. Return ONE JSON object matching the schema and NOTHING else.\n\n'
        'Judge these dimensions on the card against its RESOLVED_SPAN (the exact verified source bytes) '
        'and the injected RESEARCH_QUESTION and CONTRACT_FACETS:\n'
        '  - faithfulness: does the resolved span, read alone, entail the card\'s claim? A dropped '
        'qualifier, flipped direction, inflated magnitude, widened scope/population/geography, or '
        'upgraded modality is NOT entailed. If the span cannot support an atom, name it in '
        'unsupported_atom and the deciding source words in deciding_substring.\n'
        '  - numeric: if the claim asserts any quantity, set applicable=true and give a verdict for EVERY '
        'subdimension (number, direction, magnitude, unit, comparator, population, geography, period, '
        'scope, uncertainty, modality, precision). percent and percentage points are distinct; '
        'association is not causation; a forecast is not an observation.\n'
        '  - relevance: classify the card. Only DIRECT_ANSWER_EVIDENCE or NECESSARY_CONTEXT (with a '
        'specific connection_to_question) may pass. Adjacent subject matter, generic filler, evidence for '
        'a different question, or bare metadata/methods fail.\n'
        '  - facet: is every facet tag supported by the span and a member of CONTRACT_FACETS?\n'
        '  - content_classes: give a content class for EVERY non-empty card field. Fail any field that is '
        'process narration, model self-talk, instructions, candidate enumeration, confidence commentary, '
        'or prompt/JSON scaffolding. Absence of suspicious phrases is not sufficient.\n'
        '  - proposed_disposition: one of the allowed dispositions.\n\n'
        'Echo audit_row_id exactly. Do not include any field not in the schema.\n\n'
        f'SCHEMA:\n{json.dumps(schema)}\n\n'
        f'PACKET:\n{json.dumps(packet, ensure_ascii=False)}\n'
    )


# =================================================================================================
# One Opus pass — call the runner, validate, prove opus, parse the receipt
# =================================================================================================
@dataclass
class OpusVerdict:
    """One accepted, schema-valid Opus receipt (Sol Phase 3 step 6). It is NEVER the model's reasoning
    trace — only the structured decision."""
    audit_row_id: str
    pass_label: str                    # PASS_A / PASS_B / PASS_ADJ
    model_verified: bool
    verdict: dict                      # the validated response object
    cost_usd: float = 0.0

    def to_json(self) -> dict:
        return dict(audit_row_id=self.audit_row_id, pass_label=self.pass_label,
                    model_verified=self.model_verified, verdict=self.verdict, cost_usd=self.cost_usd)

    @property
    def disposition(self) -> str:
        return self.verdict.get('proposed_disposition', '')


def _extract_response_text(envelope: dict) -> str:
    """The `claude -p --output-format json` envelope carries the model's structured answer in `result`."""
    return envelope.get('result') if isinstance(envelope.get('result'), str) else json.dumps(
        envelope.get('result') or {})


def run_opus_pass(card: dict, graph: P.Graph, *, question: str, contract_facets: list[str],
                  det_receipt, pass_label: str, runner, support_role: str = 'primary') -> OpusVerdict:
    """Run ONE independent Opus pass on one card. `runner` is the injectable transport (Sol: a fresh
    session; the two passes never share context). Validates the response against the schema, proves the
    model was Opus, and refuses anything malformed — a missing/uncertain/garbage response is a FAILURE,
    never a silent pass (Sol Phase 1/3)."""
    schema = opus_response_json_schema()
    packet = build_opus_packet(card, graph, question=question, contract_facets=contract_facets,
                               det_receipt=det_receipt, support_role=support_role)
    prompt = build_opus_prompt(packet, schema)
    envelope = runner(prompt, schema)                   # may raise OpusUnavailable — caller fails closed
    verified = model_is_opus(envelope)
    text = _extract_response_text(envelope)
    m = re.search(r'\{.*\}', text or '', re.S)
    try:
        obj = json.loads(m.group(0)) if m else json.loads(text)
    except Exception as e:                              # noqa: BLE001
        raise OpusResponseInvalid(f'response was not parseable JSON: {type(e).__name__}')
    validated = validate_opus_response(obj, det_receipt.audit_row_id)
    return OpusVerdict(det_receipt.audit_row_id, pass_label, verified, validated,
                       float(envelope.get('total_cost_usd') or 0.0))


# =================================================================================================
# Combination — fail-closed, report-AST is authoritative (Sol §Faithfulness, §Tier 3, §4)
# =================================================================================================
@dataclass
class CombinedVerdict:
    """The join of Tier-0, report-AST faithfulness, and the two Opus passes for one card (Sol Phase 4
    step 1). `needs_adjudication` routes to Tier 3; `final` is only PASS when EVERY applicable dimension
    passes after any repair (Sol §2: no UNCERTAIN reaches the composer)."""
    audit_row_id: str
    final: str                         # PASS / FAIL / UNCERTAIN
    needs_adjudication: bool
    proposed_disposition: str
    reason_codes: list[str] = field(default_factory=list)
    detail: str = ''

    def to_json(self) -> dict:
        return dict(audit_row_id=self.audit_row_id, final=self.final,
                    needs_adjudication=self.needs_adjudication,
                    proposed_disposition=self.proposed_disposition,
                    reason_codes=sorted(set(self.reason_codes)), detail=self.detail)


def _opus_dimension_fail(v: dict) -> list[str]:
    """Which semantic dimensions this Opus verdict says fail (Sol §Relevance/§Numeric/§CoT/§Facet)."""
    rcs: list[str] = []
    rel = v.get('relevance') or {}
    if rel.get('verdict') != PASS or rel.get('classification') not in REL_PASS_CLASSES:
        rcs.append(RC_OPUS_RELEVANCE)
    num = v.get('numeric') or {}
    if num.get('applicable') and any(x == FAIL for x in (num.get('subdimensions') or {}).values()):
        rcs.append(RC_OPUS_NUMERIC)
    if (v.get('facet') or {}).get('verdict') == FAIL:
        rcs.append(RC_OPUS_FACET)
    if any(cc.get('verdict') == FAIL for cc in (v.get('content_classes') or [])):
        rcs.append(RC_OPUS_COT)
    return rcs


def combine_card_verdicts(det_receipt, faith: FaithfulnessReceipt,
                          corr_faith: list[FaithfulnessReceipt],
                          opus_a: OpusVerdict | None, opus_b: OpusVerdict | None) -> CombinedVerdict:
    """Fail-closed join. Authority order (Sol §Faithfulness, §Tier 3):
       1. A Tier-0 deterministic FAIL (structure/binding/caches) => card FAIL, quarantine.
       2. A report-AST faithfulness FAIL => card FAIL; it CANNOT be overridden by Opus.
       3. Both Opus passes must be present, model-verified, and agree; otherwise adjudicate.
       4. report-AST PASS but Opus alleges an unsupported faithfulness atom => adjudicate (do NOT silently
          ship, but do NOT let an Opus opinion override the byte-level PASS either).
       5. Any Opus semantic FAIL (relevance/numeric/facet/CoT) => adjudicate/repair, not KEEP."""
    rid = det_receipt.audit_row_id
    rcs: list[str] = []

    if det_receipt.overall == FAIL:
        for d in det_receipt.dimensions.values():
            rcs.extend(d.reason_codes)
        return CombinedVerdict(rid, FAIL, False, 'QUARANTINE_CARD', rcs,
                               'Tier-0 deterministic failure is decisive')

    if faith.verdict == FAIL:
        return CombinedVerdict(rid, FAIL, True, 'QUARANTINE_CARD', list(faith.reason_codes),
                               'report-AST faithfulness FAIL cannot be overridden by Opus')
    bad_corr = [c for c in corr_faith if c.verdict == FAIL]
    if bad_corr:
        rcs.extend(rc for c in bad_corr for rc in c.reason_codes)
        return CombinedVerdict(rid, FAIL, True, 'QUARANTINE_SUPPORT_EDGE', rcs,
                               f'{len(bad_corr)} corroborator(s) do not independently entail the primary')

    if opus_a is None or opus_b is None:
        return CombinedVerdict(rid, UNCERTAIN, True, 'QUARANTINE_CARD', [RC_OPUS_TRANSPORT],
                               'a required independent Opus pass is missing — fail closed')
    if not (opus_a.model_verified and opus_b.model_verified):
        return CombinedVerdict(rid, UNCERTAIN, True, 'QUARANTINE_CARD', [RC_OPUS_MODEL],
                               'response did not prove the Opus model was used')

    a_fail = _opus_dimension_fail(opus_a.verdict)
    b_fail = _opus_dimension_fail(opus_b.verdict)
    a_faith_fail = opus_a.verdict['faithfulness'].get('verdict') == FAIL
    b_faith_fail = opus_b.verdict['faithfulness'].get('verdict') == FAIL

    # report-AST PASSED faithfulness but an Opus pass alleges an unsupported atom -> Tier 3 (Sol §Tier 3)
    if a_faith_fail or b_faith_fail:
        return CombinedVerdict(rid, UNCERTAIN, True, opus_a.disposition or 'QUARANTINE_CARD',
                               [RC_OPUS_ALLEGES_ATOM],
                               'report-AST passed but Opus alleges an unsupported faithfulness atom')

    if set(a_fail) != set(b_fail) or opus_a.disposition != opus_b.disposition:
        return CombinedVerdict(rid, UNCERTAIN, True, opus_a.disposition or 'QUARANTINE_CARD',
                               sorted(set(a_fail + b_fail + [RC_OPUS_DISAGREE])),
                               'Opus passes disagree — adjudicate')

    if a_fail:                                          # both passes agree on a semantic failure
        return CombinedVerdict(rid, FAIL, True, opus_a.disposition or 'REPAIR_TIGHTEN', sorted(set(a_fail)),
                               'both Opus passes agree the card fails a semantic dimension')

    return CombinedVerdict(rid, PASS, False, 'KEEP_UNCHANGED', [], 'all applicable dimensions pass')


# =================================================================================================
# Tier 3 adjudication (Sol §Tier 3) — resolve a disagreement or an alleged false positive
# =================================================================================================
def build_adjudication_packet(card: dict, graph: P.Graph, det_receipt, faith: FaithfulnessReceipt,
                              opus_a: OpusVerdict, opus_b: OpusVerdict, *, question: str,
                              contract_facets: list[str]) -> dict:
    """Sol §Tier 3: the adjudicator receives the card, exact source bytes, deterministic receipt,
    report-AST result, and BOTH independent Opus verdicts. It must identify the deciding source substring
    and atom."""
    base = build_opus_packet(card, graph, question=question, contract_facets=contract_facets,
                             det_receipt=det_receipt)
    base['report_ast_faithfulness'] = faith.to_json()
    base['opus_pass_a'] = opus_a.to_json()
    base['opus_pass_b'] = opus_b.to_json()
    return base


def build_adjudication_prompt(packet: dict, schema: dict) -> str:
    return (
        'You are the ADJUDICATOR for ONE evidence card. You receive the card, its exact verified source '
        'bytes (RESOLVED_SPAN), the deterministic receipt, the report-AST faithfulness result, and two '
        'independent auditor verdicts (OPUS_PASS_A, OPUS_PASS_B). Decide the card, identifying the '
        'deciding source substring and the deciding atom. You MAY overturn an auditor FALSE POSITIVE. You '
        'may NOT override a failed byte binding or a failed report-AST entailment — if either failed, the '
        'card must be repaired and rerun, not passed. Return ONE JSON object matching the schema and '
        'nothing else. Echo audit_row_id exactly.\n\n'
        f'SCHEMA:\n{json.dumps(schema)}\n\n'
        f'PACKET:\n{json.dumps(packet, ensure_ascii=False)}\n'
    )


def run_adjudication(card: dict, graph: P.Graph, det_receipt, faith: FaithfulnessReceipt,
                     corr_faith: list[FaithfulnessReceipt], opus_a: OpusVerdict, opus_b: OpusVerdict, *,
                     question: str, contract_facets: list[str], runner) -> CombinedVerdict:
    """Sol §Tier 3: run the adjudicator and fold its verdict, still fail-closed. The adjudicator CANNOT
    resurrect a card whose byte binding or report-AST entailment failed — those routes return FAIL
    regardless of what the adjudicator says (Sol §Tier 3: 'it cannot override a failed byte binding or
    failed entailed_by_span')."""
    rid = det_receipt.audit_row_id
    # Hard floors the adjudicator may never lift.
    if det_receipt.overall == FAIL:
        return CombinedVerdict(rid, FAIL, False, 'QUARANTINE_CARD', ['tier0.deterministic_fail'],
                               'adjudicator cannot lift a Tier-0 deterministic failure')
    if faith.verdict == FAIL:
        return CombinedVerdict(rid, FAIL, False, 'QUARANTINE_CARD', list(faith.reason_codes),
                               'adjudicator cannot override a failed report-AST entailment')

    schema = opus_response_json_schema()
    packet = build_adjudication_packet(card, graph, det_receipt, faith, opus_a, opus_b,
                                       question=question, contract_facets=contract_facets)
    prompt = build_adjudication_prompt(packet, schema)
    envelope = runner(prompt, schema)
    if not model_is_opus(envelope):
        return CombinedVerdict(rid, UNCERTAIN, False, 'QUARANTINE_CARD', [RC_OPUS_MODEL],
                               'adjudicator response did not prove the Opus model')
    text = _extract_response_text(envelope)
    m = re.search(r'\{.*\}', text or '', re.S)
    try:
        obj = json.loads(m.group(0)) if m else json.loads(text)
        validated = validate_opus_response(obj, rid)
    except Exception as e:                              # noqa: BLE001
        return CombinedVerdict(rid, UNCERTAIN, False, 'QUARANTINE_CARD', [RC_OPUS_SCHEMA],
                               f'adjudicator response invalid: {type(e).__name__}')
    adj = OpusVerdict(rid, PASS_ADJ, True, validated, float(envelope.get('total_cost_usd') or 0.0))
    disp = adj.disposition
    sem_fail = _opus_dimension_fail(adj.verdict) or adj.verdict['faithfulness'].get('verdict') == FAIL
    # Sol §Voice: block the one illegal ATTRIBUTED->OWNED laundering transition.
    if voice_launder_blocked(disp, faith):
        return CombinedVerdict(rid, FAIL, False, 'QUARANTINE_CARD', [RC_VOICE_LAUNDER],
                               'OWNED demotion of an unreachable card blocked — no source bytes to demote')
    if disp == 'KEEP_UNCHANGED' and not sem_fail:
        return CombinedVerdict(rid, PASS, False, 'KEEP_UNCHANGED', [], 'adjudicator resolved to keep')
    final = FAIL if disp in ('QUARANTINE_CARD', 'QUARANTINE_SUPPORT_EDGE') else UNCERTAIN
    return CombinedVerdict(rid, final, False, disp,
                           (_opus_dimension_fail(adj.verdict) or ['adjudicator.repair_or_quarantine']),
                           'adjudicator disposition')


# =================================================================================================
# End-to-end audit of one card (Sol §7 production sequence, per-card slice) — runner injected
# =================================================================================================
def audit_card(card: dict, graph: P.Graph, det_receipt, *, question: str, contract_facets: list[str],
               runner) -> CombinedVerdict:
    """Run the full semantic ladder on ONE card with an injected Opus transport: report-AST faithfulness
    (authoritative), Tier-1 pass A, Tier-2 pass B, then Tier-3 adjudication when the join requires it.
    A transport failure fails CLOSED (UNCERTAIN + quarantine), never a silent pass."""
    faith = audit_faithfulness_primary(card, graph)
    corr = audit_faithfulness_corroborators(card, graph)

    def _pass(label):
        try:
            return run_opus_pass(card, graph, question=question, contract_facets=contract_facets,
                                 det_receipt=det_receipt, pass_label=label, runner=runner)
        except (OpusUnavailable, OpusResponseInvalid):
            return None

    opus_a = _pass(PASS_A)
    opus_b = _pass(PASS_B)
    combined = combine_card_verdicts(det_receipt, faith, corr, opus_a, opus_b)
    if combined.needs_adjudication and opus_a is not None and opus_b is not None \
            and det_receipt.overall != FAIL and faith.verdict != FAIL:
        try:
            return run_adjudication(card, graph, det_receipt, faith, corr, opus_a, opus_b,
                                    question=question, contract_facets=contract_facets, runner=runner)
        except OpusUnavailable:
            return CombinedVerdict(det_receipt.audit_row_id, UNCERTAIN, False, 'QUARANTINE_CARD',
                                   [RC_OPUS_TRANSPORT], 'adjudicator transport failed — fail closed')
    return combined
