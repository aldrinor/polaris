"""Sentinel adapter — request builder + FAIL-CLOSED caller (3 groundedness modes).

THREE (prompt, parser) contracts, selected by mode (env- + model-aware, LAW VI):
  - "guardian"      (sovereign granite-Guardian): assistant claim turn + a FINAL user
    `<guardian>` groundedness block + `documents`; the model emits `<score>yes|no</score>`
    (parsed by `parse_sentinel_score`, yes=UNGROUNDED).
  - "noninverted"   (general granite): the DIRECT one-word GROUNDED/UNGROUNDED block
    (parsed by `parse_sentinel_grounded_token`).
  - "decomposition" (CERTIFIED MiniMax-M2, I-run11-004): a SINGLE user message with the certified
    claim-DECOMPOSITION + span-coverage prompt (span+claim inline), `response_format` json_object;
    the model emits JSON {verdict, unsupported_atoms, atoms} (parsed by
    `parse_sentinel_decomposition`, "supported"=GROUNDED / "unsupported"=UNGROUNDED). The
    production decomposition call REPLICATES the certified call (verbatim `_DECOMPOSITION_PROMPT`,
    reasoning ON via the transport, max_tokens>=3000) so the 0-false-accept certification transfers.

FAIL CLOSED (lethal-inversion guard, ALL modes): a malformed/empty output OR a transport error
yields `SentinelResult(UNGROUNDED, parsed_ok=False)`. There is NO path that returns GROUNDED on
bad or missing output. Polarity/mapping lives in the contract, never re-derived here.
"""

from __future__ import annotations

import os

# I-meta-008: the Sentinel fail-closed catch must NOT swallow a budget-cap breach. The hook in
# RecordingTransport.complete raises BudgetExceededError from inside transport.complete(); a
# typed re-raise guard ahead of the broad `except` keeps the cap a HARD ABORT (never a
# fail-closed UNGROUNDED verdict). Mirrors entailment_judge.py:255-258.
import src.polaris_graph.llm.openrouter_client as _orc

from src.polaris_graph.roles.openai_compatible_transport import RoleTransportError
from src.polaris_graph.roles.role_transport import (
    EvidenceDocument,
    RoleCallRecord,
    RoleRequest,
    RoleResponse,
    RoleTransport,
)
from src.polaris_graph.roles.sentinel_contract import (
    SentinelResult,
    SentinelVerdict,
    parse_sentinel_decomposition,
    parse_sentinel_grounded_token,
    parse_sentinel_score,
)

_ROLE = "sentinel"

# === GROUNDEDNESS MODE selection (I-run11-002 L1, LAW VI) ====================================
# Two distinct (prompt, parser) contracts, selected by `PG_SENTINEL_GROUNDEDNESS_MODE`:
#   - "noninverted" (DEFAULT for the OpenRouter/benchmark Sentinel): a DIRECT one-word
#     GROUNDED/UNGROUNDED prompt, parsed by `parse_sentinel_grounded_token`. Run 11 proved the
#     general `ibm-granite/granite-4.1-8b` ignores the inverted Guardian instruction and answers
#     naturally, so the inverted contract mislabeled every grounded claim as UNGROUNDED. The
#     non-inverted prompt discriminates cleanly on the same general granite model
#     (outputs/audits/I-run11-002/l1_groundedness_probe.md).
#   - "guardian" (the SOVEREIGN self-host Sentinel): the INVERTED `<guardian>` block + the strict
#     `<score>yes|no</score>` parser (yes=risk=UNGROUNDED). KEPT BYTE-FOR-BYTE because the
#     task-trained self-host `granite-guardian-4.1-8b` is trained on the yes=risk polarity.
#
# DEFAULT WIRING (the runtime-desync guard): when `PG_SENTINEL_GROUNDEDNESS_MODE` is unset, the
# mode is DERIVED from `PG_FOUR_ROLE_TRANSPORT` so the prompt can never silently desync from the
# served model — "self_host" (the sovereign granite-Guardian route) defaults to "guardian";
# "openrouter"/unset (the benchmark general-granite route) defaults to "noninverted". An explicit
# `PG_SENTINEL_GROUNDEDNESS_MODE` always overrides. Both read lazily (per call) so a post-import
# override is honored (mirrors `role_reasoning_enabled` / `four_role_transport_mode`).
_GROUNDEDNESS_MODE_ENV = "PG_SENTINEL_GROUNDEDNESS_MODE"
_MODE_NONINVERTED = "noninverted"
_MODE_GUARDIAN = "guardian"
# I-run11-004: the CERTIFIED MiniMax-M2 claim-decomposition + span-coverage mode (the new lock +
# benchmark Sentinel). Single-user-message span+claim prompt, JSON verdict parsed by
# `parse_sentinel_decomposition`. Valid for PG_SENTINEL_GROUNDEDNESS_MODE=decomposition.
_MODE_DECOMPOSITION = "decomposition"
_VALID_MODES = (_MODE_NONINVERTED, _MODE_GUARDIAN, _MODE_DECOMPOSITION)
# The transport env the default derives from (literals kept in sync with run_gate_b.py's
# `_FOUR_ROLE_TRANSPORT_ENV` / `_TRANSPORT_SELF_HOST`; NOT imported, to avoid a scripts->src cycle).
_FOUR_ROLE_TRANSPORT_ENV = "PG_FOUR_ROLE_TRANSPORT"
_TRANSPORT_SELF_HOST = "self_host"

# I-run11-004: model-aware default mode selection. When PG_SENTINEL_GROUNDEDNESS_MODE is UNSET, the
# default mode depends on the CONFIGURED Sentinel slug so the prompt+parser can never silently
# desync from the served model:
#   - a granite-guardian model -> "guardian"  (the inverted <score>yes|no</score> contract);
#   - a minimax model          -> "decomposition" (the certified MiniMax-M2 detector);
#   - else                     -> the transport-derived default (self_host->guardian, else noninverted).
# Substring tokens (matched case-insensitively against the lock/PG_SENTINEL_MODEL slug). Kept in
# sync with openrouter_client._FAMILY_PREFIXES (granite / minimax) WITHOUT importing it, so the
# adapter has no import-time dependency on the family registry.
_SENTINEL_GUARDIAN_SLUG_TOKEN = "granite-guardian"
_SENTINEL_DECOMPOSITION_SLUG_TOKENS = ("minimax/", "minimax-")

# FIX 2 (A3 sentinel transport-blank retry, I-arch-007). A flaky socket can return
# a success HTTP-200 with an EMPTY raw_text; today that empty body falls straight
# into the parser, which fail-closes to SentinelResult(UNGROUNDED, parsed_ok=False)
# (_FAIL_CLOSED). That collapses a TRANSPORT BLANK ("the verifier returned nothing")
# with a GENUINE UNGROUNDED downstream (role_pipeline._compose_final_verdict), and
# downgrades a Judge VERIFIED/PARTIAL to UNSUPPORTED on a transient empty 200.
#
# This flag enables up to N EXTRA same-request transport.complete calls — and ONLY
# on the RAW-TEXT-BLANK discriminator `not raw_text or not raw_text.strip()`, NEVER
# on parsed_ok==False (which also covers a NON-EMPTY-but-unparseable output and a
# GENUINE clean UNGROUNDED — both must still downgrade exactly as today, no retry).
#
# DEFAULT 0 => byte-identical: no extra transport call, the empty 200 falls into the
# parser exactly as before, and the RoleCallRecord list stays 1 element. On retry
# EXHAUSTION the result STAYS SentinelResult(UNGROUNDED, parsed_ok=False) — the retry
# NEVER converts a blank into GROUNDED. Each attempt is recorded so the blank is
# auditable. A BudgetExceededError (cap breach) is a HARD ABORT, never retried; a
# RoleTransportError (persistent transport fault) still PROPAGATES and HOLDS the
# claim. Read lazily per call (mirrors the mode helpers above).
_SENTINEL_BLANK_RETRIES_ENV = "PG_SENTINEL_BLANK_RETRIES"


def _sentinel_blank_retries() -> int:
    """FIX 2: max EXTRA Sentinel transport calls on a RAW-TEXT-BLANK empty-200.

    DEFAULT 0 (DISABLED) => byte-identical (no extra call). A non-integer or
    negative value clamps to 0 (fail-safe to legacy, never unbounded). Read at
    CALL time so a post-import override / test toggle is honored (LAW VI)."""
    raw = os.getenv(_SENTINEL_BLANK_RETRIES_ENV, "0").strip()
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 0
    return value if value > 0 else 0


def _is_blank_raw_text(raw_text: str | None) -> bool:
    """The transport-blank discriminator: a success HTTP-200 whose body is None,
    empty, or whitespace-only. This is the ONLY predicate that triggers the FIX 2
    retry — NOT parsed_ok==False (which also covers a non-empty-unparseable output
    and a genuine clean UNGROUNDED, neither of which may be retried)."""
    return not raw_text or not raw_text.strip()


def _configured_sentinel_slug() -> str:
    """The active Sentinel model slug (LAW VI), for the model-aware default mode (I-run11-004).

    Reads `PG_SENTINEL_MODEL` from the env (the lock's per-role primary knob), falling back to the
    code default `openrouter_client.PG_SENTINEL_MODEL` (the single source of truth that
    verify_lock pins against the architecture lock). Read lazily so a post-import override is
    honored; returns "" only if neither is set (never raises)."""
    return os.getenv("PG_SENTINEL_MODEL") or getattr(_orc, "PG_SENTINEL_MODEL", "") or ""


def _model_aware_default_mode(slug_override: str | None = None) -> str:
    """Default Sentinel mode when PG_SENTINEL_GROUNDEDNESS_MODE is UNSET (I-run11-004).

    MODEL-AWARE first, so the lock Sentinel (MiniMax-M2) gets the DECOMPOSITION prompt+parser and a
    granite-guardian Sentinel still gets the inverted guardian contract — no silent desync between
    the served model and the prompt:
      - configured slug is a granite-guardian model -> "guardian";
      - configured slug is a minimax model          -> "decomposition";
      - otherwise -> the prior transport-derived default ("self_host" -> "guardian", else
        "noninverted" — the benchmark general-granite route, preserved for back-compat).

    `slug_override` (Codex diff-gate iter-3 P1) is the slug ACTUALLY being served on THIS call — the
    adapter passes its `model_slug` parameter, which on the self-host path is the LOCK slug resolved
    by `role_endpoint`. Deriving the mode from the real served slug (not the `PG_SENTINEL_MODEL` env)
    closes the desync where a stale `PG_SENTINEL_MODEL=granite-guardian` would build the Guardian
    prompt/parser for a lock-served MiniMax model. Falls back to `_configured_sentinel_slug()`.
    """
    slug = (slug_override or _configured_sentinel_slug()).strip().lower()
    if _SENTINEL_GUARDIAN_SLUG_TOKEN in slug:
        return _MODE_GUARDIAN
    if any(token in slug for token in _SENTINEL_DECOMPOSITION_SLUG_TOKENS):
        return _MODE_DECOMPOSITION
    # Model not recognized as guardian/minimax: fall back to the transport-derived default.
    transport = os.getenv(_FOUR_ROLE_TRANSPORT_ENV, "").strip().lower()
    if transport == _TRANSPORT_SELF_HOST:
        return _MODE_GUARDIAN
    return _MODE_NONINVERTED


def sentinel_groundedness_mode(slug_override: str | None = None) -> str:
    """Resolve the active Sentinel groundedness mode (LAW VI).

    Returns "noninverted" | "guardian" | "decomposition".

    Precedence: an explicit `PG_SENTINEL_GROUNDEDNESS_MODE` ("noninverted" | "guardian" |
    "decomposition") ALWAYS wins. An explicit but UNRECOGNIZED value raises ValueError (Codex
    diff-gate P2, no-silent-fallback: a mode typo must not silently desync the prompt+parser from
    the served model). When the env is UNSET, the default is MODEL-AWARE (I-run11-004): a
    granite-guardian slug -> "guardian"; a minimax slug -> "decomposition"; otherwise the
    transport-derived default ("self_host" -> "guardian", else "noninverted").
    """
    override = os.getenv(_GROUNDEDNESS_MODE_ENV)
    if override is not None and override.strip():
        token = override.strip().lower()
        if token in _VALID_MODES:
            return token
        # Fail LOUD on an explicit unrecognized mode (LAW II no-silent-fallback).
        raise ValueError(
            f"{_GROUNDEDNESS_MODE_ENV}={override!r} is invalid; "
            f"expected one of {_VALID_MODES!r}."
        )
    # Unset/blank: model-aware default (then transport-derived for an unrecognized model). The
    # served slug (Codex diff-gate iter-3 P1) is threaded so the mode matches the ACTUAL model.
    return _model_aware_default_mode(slug_override)


def _resolve_mode(mode: str | None, model_slug: str | None = None) -> str:
    """Resolve + VALIDATE the active mode (Codex diff-gate P2, no-silent-fallback). An explicit
    but unrecognized `mode` argument must NOT silently select a parser — it raises ValueError,
    so a caller typo cannot desync the prompt from the parser. None -> env-gated resolution keyed
    on the ACTUAL `model_slug` being served (iter-3 P1: no PG_SENTINEL_MODEL-vs-lock desync)."""
    resolved = mode if mode is not None else sentinel_groundedness_mode(model_slug)
    if resolved not in _VALID_MODES:
        raise ValueError(
            f"sentinel groundedness mode {resolved!r} is invalid; "
            f"expected one of {_VALID_MODES!r}."
        )
    return resolved


# The prescribed groundedness instruction wrapped in the final user `<guardian>` block.
# Documents are carried separately in params["documents"] (Granite's `documents` channel),
# NOT inlined here, so the calling convention stays auditable. SOVEREIGN ("guardian") mode ONLY.
_GUARDIAN_BLOCK = (
    "<guardian>groundedness</guardian>\n"
    "Assess whether the assistant's claim is grounded in the provided documents. "
    "Respond with exactly <score>yes</score> if the claim is NOT grounded (risk present) "
    "or <score>no</score> if it IS grounded (no risk). Output only the score element."
)

# The NON-INVERTED groundedness instruction (BENCHMARK / "noninverted" mode). VALIDATED VERBATIM
# by the L1 probe (scripts/diagnostics/sentinel_groundedness_probe.py `_NONINVERTED_BLOCK`):
# `ibm-granite/granite-4.1-8b` returned GROUNDED on the verbatim-quoted (grounded) fixture and
# UNGROUNDED on the on-topic-fabricated fixture under this exact wording. Asks for ONE word so
# `parse_sentinel_grounded_token` (word-boundary GROUNDED|UNGROUNDED) can read it. Documents are
# rendered model-visible by `_normalize_messages` (the leading evidence message), identical to the
# guardian path; only the FINAL user instruction differs.
_NONINVERTED_BLOCK = (
    "You are a strict groundedness checker. Decide whether the assistant's CLAIM is fully "
    "supported by (entailed by) the EVIDENCE DOCUMENTS shown above. A claim is GROUNDED only if "
    "every factual assertion in it — including any number, percentage, or named entity — is "
    "directly stated in or directly entailed by the documents. If the claim adds any fact, number, "
    "or detail not present in the documents, it is UNGROUNDED.\n"
    "Answer with EXACTLY one word: GROUNDED or UNGROUNDED. Output only that single word."
)

# === CERTIFIED DECOMPOSITION prompt (MiniMax-M2, I-run11-004) =================================
# COPIED VERBATIM from the CERTIFIED harness scripts/diagnostics/sentinel_bakeoff.py `GLM_PROMPT`
# so the certification (0 false-accepts on 28 fabrications, over-flag 0.107 on the 56-item fixture)
# TRANSFERS to production. It has `{span}` and `{claim}` `.format` fields and `{{...}}` escaped
# JSON braces. The atomic-decomposition + grammatical-voice attribution rules are the heart of the
# detector — DO NOT paraphrase or trim. The production decomposition call inlines span+claim in a
# SINGLE user message (NOT the guardian documents-channel layout) so the served call matches the
# certified one exactly.
_DECOMPOSITION_PROMPT = """You are a strict faithfulness checker for a clinical-grade research pipeline. You are given a SPAN of source text and a CLAIM that cites ONLY that span. Your job: decide whether EVERY factual assertion in the CLAIM is supported by the SPAN alone.

STEP 1 — Decompose the CLAIM into atomic sub-assertions. Separate them into:
  - mechanism/fact atoms (what happens, numbers, findings),
  - attribution atoms (WHO said / did / authored / found something — any named person, group, or framework),
  - relation atoms (causal or "offsets / counterbalances / compensates" links between two things).
List every atom; do not merge two assertions into one.

STEP 2 — Check EACH atom against the SPAN ONLY. An atom is:
  - "supported" if the SPAN states it (conservative paraphrase allowed), OR
  - "unsupported" if the SPAN does not state it.

Rules that decide hard cases:
  - SCOPE / OFFSET: if the CLAIM says one thing "offsets / counterbalances / compensates for / cancels" another, the SPAN must actually state that offsetting relation. The SPAN merely listing both things separately (e.g. "raises output" AND "displaces labor") does NOT support an "offset" relation atom — that atom is unsupported.
  - ATTRIBUTION by grammatical voice:
      * If the SPAN attributes a result with FIRST PERSON ("We present...", "We show...", "Our framework..."), then a CLAIM atom that names the cited source's own authors as the source IS supported (the source is speaking about itself).
      * If the SPAN attributes a result with a THIRD-PERSON pronoun that has NO proper-noun antecedent inside the SPAN ("He applies...", "She finds...", "They argue..."), then a CLAIM atom that names a SPECIFIC PERSON as the source is UNSUPPORTED — that named identity is not present in the SPAN.
      * If the SPAN names the person explicitly, an attribution atom naming that same person is supported.
  - SPECIFICITY: if the CLAIM names a specific entity/number/mechanism the SPAN does not contain, that atom is unsupported.

STEP 3 — Verdict: "unsupported" if ANY atom is unsupported; otherwise "supported".

Return STRICT JSON only, no prose outside it:
{{"atoms": [{{"atom": "<text>", "type": "mechanism|attribution|relation", "status": "supported|unsupported", "why": "<short>"}}], "unsupported_atoms": <int>, "verdict": "supported" | "unsupported"}}

SPAN:
{span}

CLAIM:
{claim}

JSON:"""

# The fail-closed result returned on transport error / malformed output. NEVER GROUNDED.
_FAIL_CLOSED = SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=False)


def build_sentinel_request(
    claim: str,
    evidence_documents: list[EvidenceDocument],
    *,
    model_slug: str,
    mode: str | None = None,
) -> RoleRequest:
    """Build a Sentinel groundedness request for the active mode (I-run11-002 L1 / I-run11-004).

    `mode` selects BOTH the message LAYOUT and the FINAL user instruction:
      - "guardian"    -> the INVERTED `<guardian>` block (sovereign self-host granite-Guardian).
      - "noninverted" -> the DIRECT one-word GROUNDED/UNGROUNDED block (general granite).
      - "decomposition" -> the CERTIFIED MiniMax-M2 single-user-message span+claim prompt.

    GUARDIAN / NONINVERTED layout (F3): assistant turn = the claim under check; final user turn =
    the groundedness instruction; documents ride in `params["documents"]` (rendered model-visible by
    the transport). NO structured-output spec — these emit free text the contract parses.

    DECOMPOSITION layout (I-run11-004) REPLICATES the certified call so the certification transfers:
    a SINGLE user message carrying `_DECOMPOSITION_PROMPT.format(span=<all evidence .text joined>,
    claim=claim)` (NOT the guardian documents-channel layout), with `response_format`
    {"type":"json_object"} requested (the transport forwards it; the robust parser also handles
    non-JSON-mode output). Decomposition carries NO documents in params (the SPAN is inlined into the
    single prompt message, exactly as certified) so the transport prepends no separate evidence
    message — the live body is the certified ONE user message (Codex diff-gate iter-2 P1-2).

    When `mode` is None it resolves from `sentinel_groundedness_mode()` (env- + model-aware, LAW VI).
    """
    resolved_mode = _resolve_mode(mode, model_slug=model_slug)
    documents = [{"doc_id": doc.doc_id, "text": doc.text} for doc in evidence_documents]

    if resolved_mode == _MODE_DECOMPOSITION:
        # Certified single-user-message layout: span = all evidence document texts joined (the
        # certified harness passed one `cited_evidence_text` span; multi-doc evidence is joined so
        # the whole cited pool is in-span). response_format requests JSON; the parser is robust to
        # non-JSON output too.
        span = "\n\n".join(doc.text for doc in evidence_documents)
        user_content = _DECOMPOSITION_PROMPT.format(span=span, claim=claim)
        messages = [{"role": "user", "content": user_content}]
        # NO documents in decomposition mode (Codex diff-gate iter-2 P1-2): the SPAN is already
        # inlined into `user_content`, exactly as the certification ran. If documents were carried
        # here, the transport's _normalize_messages would PREPEND a separate evidence user message,
        # making the live body TWO user messages instead of the certified ONE — diverging from the
        # certified call and invalidating the 0-false-accept guarantee. Pass an empty list so the
        # transport prepends nothing; the model reads the span from the single prompt message.
        params = {
            "documents": [],
            "response_format": {"type": "json_object"},
        }
        return RoleRequest(
            role=_ROLE,
            model_slug=model_slug,
            messages=messages,
            params=params,
        )

    instruction = _GUARDIAN_BLOCK if resolved_mode == _MODE_GUARDIAN else _NONINVERTED_BLOCK
    messages = [
        {"role": "assistant", "content": claim},
        {"role": "user", "content": instruction},
    ]
    params = {"documents": documents}
    return RoleRequest(
        role=_ROLE,
        model_slug=model_slug,
        messages=messages,
        params=params,
    )


def run_sentinel(
    transport: RoleTransport,
    claim: str,
    evidence_documents: list[EvidenceDocument],
    *,
    model_slug: str,
    mode: str | None = None,
) -> tuple[SentinelResult, list[RoleCallRecord]]:
    """Call the transport once and parse the groundedness output, FAIL CLOSED.

    Returns the `SentinelResult` and a 1-element `RoleCallRecord` list (one record per
    completion, iter-3 P1-a). A transport error OR a malformed/empty `raw_text` both yield
    `SentinelResult(UNGROUNDED, parsed_ok=False)` — never GROUNDED, in EITHER mode.

    `mode` (None -> `sentinel_groundedness_mode()`, env- + model-aware, LAW VI) selects BOTH the
    prompt (via `build_sentinel_request`) AND the parser, so they always pair correctly:
      - "guardian"      -> inverted `<score>yes|no</score>` parser (`parse_sentinel_score`).
      - "noninverted"   -> direct GROUNDED/UNGROUNDED parser (`parse_sentinel_grounded_token`).
      - "decomposition" -> certified JSON-verdict parser (`parse_sentinel_decomposition`).
    """
    resolved_mode = _resolve_mode(mode, model_slug=model_slug)
    if resolved_mode == _MODE_GUARDIAN:
        parser = parse_sentinel_score
    elif resolved_mode == _MODE_DECOMPOSITION:
        parser = parse_sentinel_decomposition
    else:
        parser = parse_sentinel_grounded_token
    request = build_sentinel_request(
        claim, evidence_documents, model_slug=model_slug, mode=resolved_mode
    )
    # FIX 2: bounded retry budget for a RAW-TEXT-BLANK empty-200 only (default 0 =>
    # exactly one attempt, byte-identical). Each attempt appends a RoleCallRecord so
    # the blank is auditable; at default the list stays a 1-element list.
    max_blank_retries = _sentinel_blank_retries()
    blank_records: list[RoleCallRecord] = []
    try:
        attempt = 0
        while True:
            response: RoleResponse = transport.complete(request)
            # ONLY a raw-text-blank empty-200 is retried. A non-empty-unparseable
            # output and a genuine clean UNGROUNDED both go straight to the parser
            # below (no retry) — the predicate is the raw-text blank, NOT parsed_ok.
            if (
                _is_blank_raw_text(response.raw_text)
                and attempt < max_blank_retries
            ):
                # Record the blank attempt so retries are visible, then re-issue the
                # SAME request on a fresh socket. On exhaustion we fall through to the
                # parser with the (still blank) raw_text -> _FAIL_CLOSED UNGROUNDED.
                blank_records.append(RoleCallRecord(
                    role=_ROLE,
                    model_slug=model_slug,
                    served_model=response.served_model,
                    raw_text=response.raw_text or "",
                    parsed=_FAIL_CLOSED,
                ))
                attempt += 1
                continue
            break
        result = parser(response.raw_text)
        served_model = response.served_model
        raw_text = response.raw_text
    except _orc.BudgetExceededError:
        # I-meta-008: a budget-cap breach (raised by the RecordingTransport cost hook inside
        # transport.complete) is a HARD ABORT, never a fail-closed UNGROUNDED verdict. Re-raise
        # BEFORE the broad except below so the cap actually bites on the Sentinel call. The
        # FIX 2 blank-retry loop is INSIDE this try, so a cap breach on a retry call also aborts
        # hard here (never retried past the cap).
        raise
    except RoleTransportError:
        # I-run11-010 (#1056, D4): a transport fault that SURVIVED the bounded transport retries
        # (openrouter_role_transport, #1053) is NOT a verdict — the verifier never responded. Let it
        # PROPAGATE so the run HOLDS the claim (matching the Mirror/Judge fail-loud behaviour),
        # instead of laundering a persistent network fault into a fail-closed UNGROUNDED verdict.
        # That downgrade (a) silently loses recall and (b) made the SAME blip role-dependent (fatal
        # on Mirror/Judge, swallowed on Sentinel). Genuine VERDICT-level faults (parse/contract
        # errors below) still fail-closed UNGROUNDED. FIX 2: a RoleTransportError on a blank-retry
        # call still propagates (the blank retry is for empty HTTP-200s only, never a transport fault).
        raise
    except Exception as exc:  # noqa: BLE001 — deliberate fail-closed; see comment below.
        # FAIL CLOSED: a VERDICT-level fault (parse / contract failure — the model responded but the
        # output was un-classifiable) must not be read as GROUNDED. We capture a record with the safe
        # (UNGROUNDED, parsed_ok=False) result and the error text as the raw payload so sub-PR-5 can
        # surface the fault rather than silently masking it.
        record = RoleCallRecord(
            role=_ROLE,
            model_slug=model_slug,
            served_model=None,
            raw_text=f"<transport_error>{exc}</transport_error>",
            parsed=_FAIL_CLOSED,
        )
        return _FAIL_CLOSED, [*blank_records, record]

    record = RoleCallRecord(
        role=_ROLE,
        model_slug=model_slug,
        served_model=served_model,
        raw_text=raw_text,
        parsed=result,
    )
    return result, [*blank_records, record]
