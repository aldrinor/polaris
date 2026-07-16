"""Research Planning Gate compiler (S1) — contract + plan, OFFLINE-testable.

Turns a raw task prompt into a pinned :class:`PlanningGateArtifact` via two
bounded structured LLM calls:

  1. **contract compiler** — deterministic candidates (S0 adapter) + the raw
     prompt → a typed :class:`ResearchContract` (every clause dispositioned,
     every term tagged origin/force/spans);
  2. **plan compiler** — the *validated* contract → a
     :class:`ResearchExecutionPlan` (threads, mandatory query intents, outline
     seed, coverage matrix, budget).

Both calls go through the repo LLM gateway (:class:`OpenRouterClient`) resolved
to the small policy model (``z-ai/glm-5.2``, the same arm FS query-gen uses).
The live call is OFF by default: the whole module is spend-free and hermetic
unless a flag is set OR a ``client=`` stub is injected (tests do the latter).

Guardrail posture
-----------------
* **Default-OFF / None-default.** ``run_research_planning_gate`` requires an
  explicit ``client`` (a stub in tests) OR the live flag
  ``PG_PLANNING_GATE_LIVE=1``. With neither, and no client, it raises rather
  than silently hitting the network — the OFF path never fires an LLM.
* **Autonomous mode is pure ``contract→contract``.** It NEVER returns
  ``needs_input``, never blocks, never waits for a human: every would-ask becomes
  a disclosed :class:`Assumption` and the artifact is ``auto_pinned``. This is
  the load-bearing benchmark mode (a test asserts zero blocking with no input
  channel).
* **No invention.** The compiler system prompt forbids inventing constraints and
  requires spans for explicit terms; the deterministic
  :func:`~planning_gate_schema.validate_contract` then MECHANICALLY rejects any
  hard term that is not explicit/user-backed. A rejected contract gets ONE
  correction retry, then a conservative span-verified fallback
  (``compiler_degraded=true``) — never a guessed contract, never a crash.
* **Reuse.** Candidate seeding reuses the S0 ``candidate_adapter``; parsing
  reuses the fence-tolerant discipline of ``constraint_extractor`` /
  ``research_planner``; hashing reuses ``planning_gate_schema.sha256_of`` (same
  construction as ``research_planner.plan_sha256``).

Nothing here is wired into the paid pipeline — that is S2+. This module is the
compiler + its offline harness.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import uuid
from typing import Any, Optional

from src.polaris_graph.planning.candidate_adapter import (
    CandidateConstraint,
    candidate_term_id,
    reconcile_candidates,
)
from src.polaris_graph.planning.gate_flags import gate_enabled
from src.polaris_graph.planning.planning_gate_schema import (
    DISCLOSURE_ORIGINS,
    FORCE_HARD,
    FORCE_OPEN,
    FORCE_PREFER,
    HARD_ELIGIBLE_ORIGINS,
    NORM_EXACT,
    ORIGIN_EXPLICIT,
    ORIGIN_INFERRED,
    SCOPE_SOURCE_LANGUAGES,
    Assumption,
    ContractTerm,
    CoverageRequirement,
    PlanningGateArtifact,
    PromptSpan,
    ResearchContract,
    ResearchExecutionPlan,
    ValidationError,
    contract_from_dict,
    plan_from_dict,
    reanchor_contract_spans,
    sha256_of,
    validate_capabilities,
    validate_contract,
    validate_monotonicity,
    validate_plan,
)

# Honest gate states (spec deliverable 6). These describe the ENFORCEABILITY of
# the pinned contract, distinct from the interactive/autonomous ``GATE_STATES``:
#   pinned_executable  — every hard term is span-verified + (Phase D) has a
#                        capability; ready to enforce.
#   degraded_lossless  — LLM ENRICHMENT was thin/failed, but EVERY deterministic
#                        explicit constraint survived (nothing vanished).
#   blocked_unsupported— a hard term is opaque / has no executable path; preserved
#                        + disclosed, never claimed compliant (Phase D completes).
GATE_ENFORCEMENT_PINNED = "pinned_executable"
GATE_ENFORCEMENT_DEGRADED = "degraded_lossless"
GATE_ENFORCEMENT_BLOCKED = "blocked_unsupported"

logger = logging.getLogger("polaris_graph.research_planning_gate")

# The small policy model — the same arm FS query-gen / the judges use. Overridable
# via env so it tracks the lock rather than pinning a slug that could drift.
_DEFAULT_POLICY_MODEL = "z-ai/glm-5.2"

# I-gate-089 / FX-01 (drb_72 live probe): the policy model (z-ai/glm-5.2) is
# REASONING-FIRST — it is in openrouter_client._ALWAYS_REASON_MODELS, so a
# generate() call runs its reasoning prelude at effort=high on the SAME
# overall max_tokens budget and only floors that budget to PG_GLM5_MIN_MAX_TOKENS
# (4096). On a compound prompt (task 72) the reasoning prelude ate the whole
# 8192 budget: candidate content reached 14022 then 16546 chars and STILL hit
# finish_reason='length' (always_reason_promotion truncation), so the compile
# retried and fell to the conservative fallback. Sol's design (§4) says the
# ~2000-token cap is inadequate and to use the PROVIDER-RESOLVED MAXIMUM for a
# reasoning-first model. Mirror the champion's reasoning-first budget convention
# (multi_section_generator / analyst_synthesis): give the compile a real content
# ceiling AND bound the reasoning POOL so a fixed content slice always survives.
# The client further clamps DOWN to the provider completion cap (B10 resolver),
# so this can never over-request. Env-tunable; the fail-soft conservative-contract
# fallback stays the backstop when the compile still fails.
_CONTRACT_MAX_TOKENS = int(
    os.getenv("PG_PLANNING_GATE_MAX_TOKENS", "32768")
)
_PLAN_MAX_TOKENS = int(
    os.getenv("PG_PLANNING_GATE_MAX_TOKENS", "32768")
)
# Bound the reasoning-first pool so the model always reaches the closing JSON:
# reserve the remainder of the budget for content. glm-5.2 branch-1 honors a
# caller-passed reasoning.max_tokens (openrouter_client ~line 1958), so this
# guarantees content headroom = max_tokens - this pool. Env-tunable (LAW VI).
_PLANNING_GATE_REASONING_MAX_TOKENS = int(
    os.getenv("PG_PLANNING_GATE_REASONING_MAX_TOKENS", "16384")
)


def _resolve_model() -> str:
    override = os.getenv("PG_PLANNING_GATE_MODEL", "").strip()
    if override:
        return override
    policy = os.getenv("PG_POLICY_MODEL", "").strip()
    return policy or _DEFAULT_POLICY_MODEL


def _live_enabled() -> bool:
    """Whether a live LLM call is permitted. Default OFF (hermetic)."""
    return os.getenv("PG_PLANNING_GATE_LIVE", "0").strip().lower() in (
        "1", "true", "yes", "on",
    )


# ---------------------------------------------------------------------------
# System prompts (design §3 / §4 — no-invention discipline is IN the prompt AND
# re-checked by the deterministic validators)
# ---------------------------------------------------------------------------

_CONTRACT_SYSTEM_PROMPT = (
    "You are the POLARIS Research Contract Compiler. Convert the user's complete "
    "request into the supplied ResearchContract JSON schema. Your output is a "
    "contract for a research system, NOT the answer to the research question.\n\n"
    "Rules:\n"
    "1. Account for every imperative, question, entity, comparison dimension, "
    "scope phrase, source rule, exclusion, format request, and rhetorical "
    "instruction in the request.\n"
    "2. A term marked origin=\"explicit\" MUST include the exact VERBATIM QUOTE it "
    "is based on (copy the phrase from the request; DO NOT compute character "
    "offsets — the system re-derives them from your quote). Do not mark "
    "implications or world knowledge as explicit.\n"
    "3. NEVER invent a restriction. If date, geography, jurisdiction, source "
    "type, source language, length, audience, or format is unspecified, "
    "represent it as open/null.\n"
    "4. Inferred and policy-default terms may ONLY be force=\"preference\" or "
    "force=\"open\", NEVER force=\"hard\". Only explicit text or an affirmative "
    "user action may back a hard term. List every inferred/default interpretation "
    "in assumptions and explain its consequence.\n"
    "5. Distinguish source language from output language. Distinguish required "
    "topics from required section headings. Distinguish content scope from "
    "presentation shape.\n"
    "6. Decompose compound and nested questions without dropping qualifiers. "
    "Preserve dependencies (evidence first, comparison second, recommendation "
    "last).\n"
    "7. Identify ambiguity rather than resolving it invisibly. Mark whether it "
    "can safely remain open and which execution stages it changes.\n"
    "8. Preserve conflicting explicit instructions in conflicts; do not silently "
    "choose one.\n"
    "9. Do not set source-count, date-window, jurisdiction, length, or "
    "section-count quotas unless the user supplied them.\n"
    "10. Return JSON only, conforming exactly to the schema. Do not research or "
    "answer.\n\n"
    "Return a JSON object with keys: contract (the ResearchContract) and "
    "clause_coverage (an array dispositioning every operative clause: "
    "{span, term_ids, disposition in [represented|non_instructional|ambiguous], "
    "explanation}).\n"
    "The ResearchContract has keys: schema_version, objective[], scope[], "
    "content_terms[], deliverable[], coverage[], sections[], ambiguities[], "
    "assumptions[], conflicts[], complexity. Each term is "
    "{term_id, dimension, value, origin, force, confidence, spans[], rationale, "
    "enforcement_stages[]}. spans[] may be verbatim QUOTE STRINGS (offsets are "
    "derived for you) or {start,end,quote} objects. origin in [explicit, "
    "user_answer, inferred, policy_default]; force in [hard, preference, open]."
)

_PLAN_SYSTEM_PROMPT = (
    "You are the POLARIS Research Plan Compiler. Produce ResearchExecutionPlan "
    "JSON for the pinned ResearchContract. Do NOT answer the research question "
    "and do NOT change the contract.\n\n"
    "Rules:\n"
    "1. Create the smallest COMPLETE set of research threads that covers every "
    "binding content requirement; scale with complexity rather than targeting a "
    "fixed number.\n"
    "2. Preserve dependencies: descriptive/baseline evidence precedes "
    "comparison, causal analysis, forecast, and recommendation where "
    "applicable.\n"
    "3. Give every requirement needing evidence at least one MANDATORY query "
    "intent. Add distinct lanes when source type, language, jurisdiction, date, "
    "named source, primary-source status, comparison side, or counterevidence "
    "requires a different discovery strategy.\n"
    "4. Scope must shape discovery. Encode explicit hard scope in query intents "
    "(and backend-filter projections); encode soft/inferred scope as ranking "
    "preferences. NEVER plan to satisfy scope solely by filtering a fixed corpus "
    "after retrieval.\n"
    "5. Do not drop a mandatory lane to meet a query cap. Report "
    "mandatory_lane_count and use the budget overflow policy (expand or "
    "fail_preflight).\n"
    "6. Map every contract term to its owning stage(s), thread(s), query "
    "intent(s) when evidence is needed, section(s) when presentation is needed, "
    "and an audit method (coverage_matrix).\n"
    "7. Required topics are NOT automatically headings. Create exact heading "
    "locks only from an explicit/user-approved section instruction. Otherwise use "
    "stable semantic section IDs and revisable display titles.\n"
    "8. Define semantic sufficiency and gap conditions (stop_conditions) without "
    "inventing source counts.\n"
    "9. Return JSON only conforming exactly to ResearchExecutionPlan (keys: "
    "plan_version, threads[], evidence_needs[], query_intents[], outline_seed[], "
    "coverage_matrix[], budget, stop_conditions[])."
)


# ---------------------------------------------------------------------------
# Gate result
# ---------------------------------------------------------------------------

class GateResult:
    """The gate's return: an artifact plus mode/state and any diagnostics.

    ``needs_input`` is True ONLY in interactive mode with material questions; in
    autonomous mode it is ALWAYS False (the load-bearing invariant).
    """

    def __init__(
        self,
        *,
        artifact: PlanningGateArtifact,
        needs_input: bool,
        questions: Optional[list[dict[str, Any]]] = None,
        contract_errors: Optional[list[ValidationError]] = None,
        plan_errors: Optional[list[ValidationError]] = None,
        enforcement_state: str = "",
    ) -> None:
        self.artifact = artifact
        self.needs_input = needs_input
        self.questions = questions or []
        self.contract_errors = contract_errors or []
        self.plan_errors = plan_errors or []
        # Honest enforcement state (deliverable 6): pinned_executable /
        # degraded_lossless / blocked_unsupported. "" when the gate is OFF.
        self.enforcement_state = enforcement_state

    @property
    def contract(self) -> ResearchContract:
        return self.artifact.contract

    @property
    def plan(self) -> ResearchExecutionPlan:
        return self.artifact.plan

    @property
    def state(self) -> str:
        return self.artifact.state


# ---------------------------------------------------------------------------
# JSON extraction (reuse fence-tolerant discipline from constraint_extractor)
# ---------------------------------------------------------------------------

def _extract_json_object(raw: str) -> str:
    """First balanced ``{...}`` object substring, fence-tolerant."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    text = text.strip()
    start = text.find("{")
    if start == -1:
        return text
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return text[start:]


def _loads(raw: str) -> dict[str, Any]:
    obj = _extract_json_object(raw)
    data = json.loads(obj)
    if not isinstance(data, dict):
        raise ValueError("model output was not a JSON object")
    return data


# ---------------------------------------------------------------------------
# Candidate → prompt block (seed the compiler with deterministic spans)
# ---------------------------------------------------------------------------

def _candidates_block(candidates: list[CandidateConstraint]) -> str:
    payload = [c.to_dict() for c in candidates]
    return json.dumps(payload, ensure_ascii=False, indent=None)


def _contract_user_prompt(
    prompt: str, candidates: list[CandidateConstraint], mode: str
) -> str:
    today = _dt.date.today().isoformat()
    return (
        f"CURRENT UTC DATE (context only, NOT a user constraint): {today}\n"
        f"MODE: {mode}\n\n"
        f"DETERMINISTIC CANDIDATES (AUTHORITATIVE — already extracted by "
        f"deterministic code with verbatim spans). You MUST represent EVERY "
        f"span-verified candidate; you may NOT drop, weaken, or re-file one. Your "
        f"job is ADDITIVE: classify any UNSEEN phrasing the extractor missed, "
        f"decompose the objective into coverage/threads, and enrich — referencing "
        f"the candidate values. The deterministic layer owns explicit constraints; "
        f"it overrides you on overlap:\n"
        f"{_candidates_block(candidates)}\n\n"
        f"EXACT USER REQUEST:\n\"\"\"\n{prompt}\n\"\"\"\n\n"
        f"Return the JSON object now (contract + clause_coverage)."
    )


def _plan_user_prompt(contract: ResearchContract) -> str:
    return (
        "PINNED RESEARCH CONTRACT (do not change it):\n"
        f"{json.dumps(contract.to_dict(), ensure_ascii=False)}\n\n"
        "Return the ResearchExecutionPlan JSON object now."
    )


# ---------------------------------------------------------------------------
# Deterministic conservative fallback (never a guessed contract)
# ---------------------------------------------------------------------------

def _conservative_contract(
    prompt: str, candidates: list[CandidateConstraint]
) -> ResearchContract:
    """The LOSSLESS fallback core when the LLM output is unusable twice.

    When PG_GATE is ON this is the registry-driven lossless core
    (:func:`_lossless_fallback_contract`): EVERY deterministic explicit constraint
    survives with its canonical dimension and correct stage owner (no category
    leakage), and an unmappable kind is kept as a first-class OPAQUE term — so
    "degraded" means ENRICHMENT is thin, NEVER that a stated constraint vanished.

    When PG_GATE is OFF this is the legacy conservative fallback (byte-identical to
    the pre-inversion path): raw prompt as the objective, span-verified candidates
    kept, everything else open. It can never invent (only span-backed candidates
    become explicit/hard).
    """
    if gate_enabled():
        return _lossless_fallback_contract(prompt, candidates)

    objective = [ContractTerm(
        term_id="objective.question",
        dimension="objective.question",
        value=prompt.strip(),
        origin=ORIGIN_EXPLICIT if prompt.strip() else ORIGIN_INFERRED,
        force=FORCE_OPEN,
        spans=[PromptSpan(0, len(prompt), prompt)] if prompt.strip() else [],
        rationale="degraded fallback: raw request retained as the objective",
    )]

    scope: list[ContractTerm] = []
    coverage: list[CoverageRequirement] = []
    assumptions: list[Assumption] = []
    n = 0
    for cand in candidates:
        span_ok = any(
            sp.quote == prompt[sp.start:sp.end] for sp in cand.spans
        ) and bool(cand.spans)
        # A hard candidate keeps hard force ONLY with a verbatim span; otherwise
        # it degrades to preference (the mechanical no-invention guarantee).
        force = FORCE_HARD if (cand.force == "hard" and span_ok) else FORCE_PREFER
        origin = ORIGIN_EXPLICIT if span_ok else ORIGIN_INFERRED
        n += 1
        tid = f"scope.cand_{n}"
        spans = [PromptSpan(sp.start, sp.end, sp.quote) for sp in cand.spans]
        term = ContractTerm(
            term_id=tid,
            dimension=cand.dimension,
            value=cand.value,
            origin=origin,
            force=force,
            spans=spans,
            rationale=f"degraded fallback from candidate ({cand.origin})",
        )
        if cand.dimension.startswith("content"):
            coverage.append(CoverageRequirement(
                requirement_id=tid, kind="topic", statement=term, required=False,
            ))
        else:
            scope.append(term)
        if origin in DISCLOSURE_ORIGINS:
            assumptions.append(Assumption(
                assumption_id=f"asm_{n}",
                statement=f"kept {cand.dimension}={cand.value!r} as an open preference "
                          f"(no verbatim span to make it explicit)",
                affected_term_ids=[tid],
                origin=ORIGIN_INFERRED,
                consequence="ranked/routed only; never a hard gate",
            ))

    return ResearchContract(
        objective=objective,
        scope=scope,
        coverage=coverage,
        assumptions=assumptions,
        complexity="degraded",
        compiler_degraded=True,
    )


def _lossless_fallback_contract(
    prompt: str, candidates: list[CandidateConstraint]
) -> ResearchContract:
    """The LOSSLESS fallback (PG_GATE ON): the deterministic-authoritative core
    run as the WHOLE contract when the LLM failed.

    Every span-verified deterministic explicit source/date/exclusion constraint is
    authored (via the registry, canonical dimension, correct force), and every
    content-coverage candidate becomes a coverage requirement. Deliverable/format/
    length/tone candidates land in the DELIVERABLE group — NEVER scope (no category
    leakage). An unmappable kind is preserved as a first-class OPAQUE term. Marked
    ``compiler_degraded=true``: enrichment is thin, but NO explicit constraint
    vanished.
    """
    objective = [ContractTerm(
        term_id="objective.question",
        dimension="objective.question",
        value=prompt.strip(),
        origin=ORIGIN_EXPLICIT if prompt.strip() else ORIGIN_INFERRED,
        force=FORCE_OPEN,
        spans=[PromptSpan(0, len(prompt), prompt)] if prompt.strip() else [],
        rationale="lossless fallback: raw request retained as the objective",
    )]

    # authoritative source/date/exclusion terms + content-coverage terms.
    scope, content = _author_deterministic_terms(candidates, prompt)
    coverage: list[CoverageRequirement] = [
        CoverageRequirement(
            requirement_id=t.term_id, kind="topic", statement=t, required=True,
        )
        for t in content
    ]

    # deliverable / rhetoric candidates: file by stage owner, NEVER in scope.
    deliverable: list[ContractTerm] = []
    n = 0
    for cand in candidates:
        if cand.dimension not in (
            "deliverable.format", "deliverable.length", "rhetoric.tone",
        ):
            continue
        span_ok = _cand_span_ok(cand, prompt)
        if not (cand.value or "").strip():
            continue
        n += 1
        deliverable.append(ContractTerm(
            term_id=f"deliverable.cand_{n}",
            dimension=cand.canonical_dimension(),
            value=cand.value,
            origin=ORIGIN_EXPLICIT if span_ok else ORIGIN_INFERRED,
            force=FORCE_PREFER,   # deliverable shape is a preference, never a gate
            spans=_cand_spans(cand, prompt),
            subject=cand.subject,
            attribute=cand.attribute,
            stage_owner=cand.stage_owner,
            normalization_status=cand.normalization_status or NORM_EXACT,
            rationale="lossless fallback: deliverable shape preserved (render-owned)",
        ))

    return ResearchContract(
        objective=objective,
        scope=scope,
        deliverable=deliverable,
        coverage=coverage,
        complexity="degraded",
        compiler_degraded=True,
    )


# ---------------------------------------------------------------------------
# DETERMINISTIC-AUTHORITATIVE CORE + MONOTONIC MERGE (Phase B — the inversion)
# ---------------------------------------------------------------------------
#
# This REPLACES the deleted ``_promote_source_scope`` task-shaped whitelist. The
# authority is INVERTED: deterministic code (the S0 candidate adapter + the
# candidate→canonical registry) AUTHORS the explicit-constraint contract; the LLM
# is additive-only and MERGED monotonically (it may add/enrich, never delete,
# downgrade, or re-dimension a deterministic explicit term).
#
# No per-type branching: every source/date/exclusion/coverage family is driven by
# ``candidate_adapter.CANDIDATE_REGISTRY`` (the row supplies canonical dimension +
# subject/attribute/operator/stage_owner). An unknown kind stays a first-class
# OPAQUE term — preserved, never dropped.
#
# Gated behind PG_GATE (default OFF): with the flag OFF this whole core is a no-op
# and the compiled contract is byte-identical to the pre-inversion path (the LLM
# compile alone), preserving the OFF guardrail.

# The candidate dimensions whose terms are EXPLICIT authority (a real user rule
# with a verbatim span) — as opposed to advisory coverage the LLM may reshape.
# A span-verified candidate on any of these is authored as an explicit contract
# term the LLM merge can neither drop nor downgrade.
_AUTHORITATIVE_DIMENSIONS: frozenset[str] = frozenset({
    "source.types", "source.quality", "source.language", "source.scope_facet",
    "source.jurisdiction", "source.named", "date.recency", "content.exclusion",
})


def _cand_span_ok(cand: CandidateConstraint, prompt: str) -> bool:
    """A candidate carries at least one verbatim-quote-verified span."""
    return bool(cand.spans) and any(
        0 <= sp.start <= sp.end <= len(prompt) and sp.quote == prompt[sp.start:sp.end]
        for sp in cand.spans
    )


def _cand_spans(cand: CandidateConstraint, prompt: str) -> list[PromptSpan]:
    return [
        PromptSpan(sp.start, sp.end, sp.quote)
        for sp in cand.spans
        if 0 <= sp.start <= sp.end <= len(prompt) and sp.quote == prompt[sp.start:sp.end]
    ]


def _hard_facet_ranges(candidates: list[CandidateConstraint], prompt: str) -> list[tuple[int, int]]:
    """Verbatim spans of hard source-KIND scope clauses. A soft source.language
    whose span sits INSIDE one of these (e.g. "only cites ... English-language
    journal articles") inherits the enclosing "only" hardness — never a
    fabricated hard gate (the range must itself be a span-verified hard facet)."""
    ranges: list[tuple[int, int]] = []
    for c in candidates:
        if c.dimension in ("source.scope_facet", "source.types") and c.force == FORCE_HARD:
            ranges.extend((sp.start, sp.end) for sp in _cand_spans(c, prompt))
    return ranges


def _term_from_candidate(
    cand: CandidateConstraint, prompt: str, idx: int,
    *, hard_ranges: list[tuple[int, int]],
) -> Optional[ContractTerm]:
    """Author ONE explicit contract term from a span-verified deterministic
    candidate, via the registry (generic — no per-type branch). Returns None when
    the candidate has no verbatim span (never a fabricated explicit/hard term).

    Force: the candidate's own observed force, EXCEPT a soft source.language whose
    span is enclosed by a hard source-kind clause, which inherits hard. Origin is
    always ``explicit`` (a span-verified user rule). ``normalization_status``
    carries through: an opaque candidate becomes an opaque (but preserved) term.
    """
    spans = _cand_spans(cand, prompt)
    if not spans:
        return None
    row = None
    from src.polaris_graph.planning.candidate_adapter import _registry_row  # noqa: PLC0415
    row = _registry_row(cand.dimension)
    canonical_dim = row.canonical if row else cand.dimension
    value = (cand.value or "").strip()
    if not value:
        return None

    force = FORCE_HARD if cand.force == FORCE_HARD else FORCE_PREFER
    # language-inside-a-hard-only-clause inheritance (the sole cross-term rule; it
    # never invents — it only propagates an already-hard enclosing span).
    if canonical_dim == SCOPE_SOURCE_LANGUAGES and force != FORCE_HARD:
        for sp in spans:
            if any(lo <= sp.start and sp.end <= hi for lo, hi in hard_ranges):
                force = FORCE_HARD
                break

    norm = cand.normalization_status or NORM_EXACT
    # An OPAQUE hard term is preserved but cannot be claimed enforceable — it is
    # surfaced (the artifact's enforcement state becomes blocked_unsupported).
    operator = cand.operator or ""
    value_set = [value] if operator in ("IN", "NOT_IN") else []
    return ContractTerm(
        term_id=candidate_term_id(cand),
        dimension=canonical_dim,
        value=value,
        origin=ORIGIN_EXPLICIT,
        force=force,
        spans=spans,
        subject=cand.subject or (row.subject if row else "source"),
        attribute=cand.attribute or (row.attribute if row else ""),
        operator=operator,
        value_set=value_set,
        stage_owner=cand.stage_owner or (row.stage_owner if row else ""),
        normalization_status=norm,
        enforcement_stages=["retrieval"],
        rationale="deterministic-authoritative: span-verified explicit constraint "
                  "(the LLM merge may enrich but never drop/downgrade it)",
    )


def _author_deterministic_terms(
    candidates: list[CandidateConstraint], prompt: str,
) -> tuple[list[ContractTerm], list[ContractTerm]]:
    """Author the deterministic explicit contract terms from candidates.

    Returns ``(scope_terms, coverage_content_terms)`` — scope/source/date/
    exclusion terms vs content-coverage terms — so the caller files each in the
    right group with NO category leakage. De-duplicates by canonical term_id
    (hard wins over prefer; spans unioned).
    """
    hard_ranges = _hard_facet_ranges(candidates, prompt)
    by_id: dict[str, ContractTerm] = {}
    for i, cand in enumerate(candidates):
        if cand.dimension not in _AUTHORITATIVE_DIMENSIONS:
            continue
        term = _term_from_candidate(cand, prompt, i, hard_ranges=hard_ranges)
        if term is None:
            continue
        prev = by_id.get(term.term_id)
        if prev is None:
            by_id[term.term_id] = term
        else:
            # merge duplicates: hard wins; union spans.
            if term.force == FORCE_HARD:
                prev.force = FORCE_HARD
            seen = {(s.start, s.end) for s in prev.spans}
            prev.spans.extend(s for s in term.spans if (s.start, s.end) not in seen)

    scope: list[ContractTerm] = []
    content: list[ContractTerm] = []
    for term in by_id.values():
        if term.dimension.startswith("content"):
            content.append(term)
        else:
            scope.append(term)
    return scope, content


def _merge_deterministic_authority(
    contract: ResearchContract,
    candidates: list[CandidateConstraint],
    prompt: str,
) -> ResearchContract:
    """MONOTONIC MERGE: reinstate every deterministic explicit term as authority.

    The LLM contract is treated as ADDITIVE. For each deterministic explicit term:
      * if the LLM already carries a term on the SAME canonical (dimension,value),
        that term is UPGRADED to explicit + the deterministic force (hard wins),
        and given the deterministic spans if it lacked them — the LLM enriched it,
        the deterministic core owns its force/origin;
      * otherwise the deterministic term is APPENDED to the correct group.
    The LLM may have ADDED its own terms; those are left untouched. It can never
    delete/downgrade/re-dimension a deterministic term — that is the inversion.
    Mutates + returns the contract. No-op when PG_GATE is OFF (OFF byte-identical).
    """
    if not gate_enabled():
        return contract

    prompt = prompt or ""
    det_scope, det_content = _author_deterministic_terms(candidates, prompt)

    def _key(dim: str, value: Any) -> tuple[str, str]:
        return (dim, str(value or "").strip().casefold())

    # index existing scope terms for overlap upgrade.
    existing: dict[tuple[str, str], ContractTerm] = {}
    for t in contract.scope:
        existing[_key(t.dimension, t.value)] = t

    for det in det_scope:
        key = _key(det.dimension, det.value)
        llm_term = existing.get(key)
        if llm_term is not None:
            # LLM enriched an overlapping term: deterministic owns force/origin/span.
            llm_term.origin = ORIGIN_EXPLICIT
            if det.force == FORCE_HARD:
                llm_term.force = FORCE_HARD
            elif llm_term.force != FORCE_HARD:
                llm_term.force = det.force
            if not llm_term.spans:
                llm_term.spans = list(det.spans)
            # carry the generic-IR annotations the LLM couldn't be trusted to set.
            llm_term.subject = llm_term.subject or det.subject
            llm_term.attribute = llm_term.attribute or det.attribute
            llm_term.operator = llm_term.operator or det.operator
            llm_term.value_set = llm_term.value_set or det.value_set
            llm_term.stage_owner = llm_term.stage_owner or det.stage_owner
            llm_term.normalization_status = det.normalization_status
            llm_term.rationale = (
                (llm_term.rationale + " | ") if llm_term.rationale else ""
            ) + "deterministic authority upheld (monotonic merge)"
        else:
            contract.scope.append(det)
            existing[key] = det

    # content-coverage terms: reinstate as required coverage requirements if the
    # LLM dropped them (exclusions in particular must never be lost).
    existing_cov_vals = {
        str(cr.statement.value or "").strip().casefold() for cr in contract.coverage
    }
    for det in det_content:
        v = str(det.value or "").strip().casefold()
        if v and v not in existing_cov_vals:
            contract.coverage.append(CoverageRequirement(
                requirement_id=det.term_id,
                kind="topic",
                statement=det,
                required=True,
            ))
            existing_cov_vals.add(v)

    return contract


def _deterministic_candidate_ids(
    candidates: list[CandidateConstraint], prompt: str,
) -> set[str]:
    """The stable term_ids of every span-verified deterministic explicit
    candidate — the set ``validate_monotonicity`` requires survived the merge."""
    ids: set[str] = set()
    for cand in candidates:
        if cand.dimension in _AUTHORITATIVE_DIMENSIONS and _cand_span_ok(cand, prompt):
            if (cand.value or "").strip():
                ids.add(candidate_term_id(cand))
    return ids


def _enforcement_state(contract: ResearchContract) -> str:
    """Derive the honest enforcement state (spec deliverable 6). A hard OPAQUE
    term (or a hard term with no executable path) → blocked_unsupported; a
    degraded compile → degraded_lossless; else pinned_executable."""
    for term in contract.hard_terms():
        if term.is_opaque():
            return GATE_ENFORCEMENT_BLOCKED
    # Phase D seam: a hard term with no registered capability is blocked. The stub
    # returns [] today (capability registry lands in Phase D), so this is inert.
    if validate_capabilities(contract):
        return GATE_ENFORCEMENT_BLOCKED
    if contract.compiler_degraded:
        return GATE_ENFORCEMENT_DEGRADED
    return GATE_ENFORCEMENT_PINNED


# ---------------------------------------------------------------------------
# Autonomous disclosure sweep (least-restrictive + every inferred term recorded)
# ---------------------------------------------------------------------------

def _autonomous_disclose(contract: ResearchContract) -> ResearchContract:
    """Ensure the autonomous invariant: every inferred/policy_default term with a
    value has an :class:`Assumption`, and NO hard term survives without an
    authoritative origin (defense in depth against a slipped-through hard).

    This mutates the contract in place and returns it. It NEVER blocks and NEVER
    asks — it is the pure ``contract→contract`` step that lets autonomous mode
    proceed with disclosed assumptions instead of questions.
    """
    disclosed = set()
    for a in contract.assumptions:
        disclosed.update(a.affected_term_ids)

    next_idx = len(contract.assumptions)
    for term in contract.all_terms():
        # Belt: downgrade any hard term whose origin cannot back a hard force.
        if term.is_hard() and term.origin not in HARD_ELIGIBLE_ORIGINS:
            term.force = FORCE_PREFER
            term.rationale = (
                (term.rationale + " | ") if term.rationale else ""
            ) + "autonomous: downgraded hard→preference (non-explicit origin)"

        if (
            term.origin in DISCLOSURE_ORIGINS
            and term.value not in (None, "", [], {})
            and term.term_id
            and term.term_id not in disclosed
        ):
            next_idx += 1
            contract.assumptions.append(Assumption(
                assumption_id=f"auto_asm_{next_idx}",
                statement=f"assumed {term.dimension}={term.value!r} "
                          f"(least-restrictive default; unspecified in the request)",
                affected_term_ids=[term.term_id],
                origin=term.origin if term.origin in DISCLOSURE_ORIGINS else ORIGIN_INFERRED,
                consequence="preference/routing only; never a hard gate",
                reversible=True,
            ))
            disclosed.add(term.term_id)

    return contract


# ---------------------------------------------------------------------------
# Ask-vs-assume (interactive only; ≤3 material questions)
# ---------------------------------------------------------------------------

def _material_questions(contract: ResearchContract, limit: int = 3) -> list[dict[str, Any]]:
    """Generate ≤``limit`` material questions from the contract's ambiguities.

    Eligible only if the ambiguity is marked material AND cannot proceed open.
    Autonomous mode NEVER calls this. Coupled ambiguities are de-duplicated by
    their affected term set.
    """
    seen_keys: set[tuple[str, ...]] = set()
    out: list[dict[str, Any]] = []
    for amb in contract.ambiguities:
        if not amb.material or amb.can_proceed_open:
            continue
        key = tuple(sorted(amb.affected_term_ids))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        out.append({
            "question_id": f"q_{len(out) + 1}",
            "prompt": amb.text,
            "choices": list(amb.plausible_interpretations) + ["keep broad / use best judgment"],
            "affected_term_ids": list(amb.affected_term_ids),
            "why_it_matters": ", ".join(amb.decision_impact) or "materially changes the plan",
        })
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------------------
# LLM call plumbing
# ---------------------------------------------------------------------------

async def _call(
    client: Any, system: str, user: str, max_tokens: int
) -> str:
    # I-gate-089/FX-01: bound the reasoning-first pool so a fixed content slice
    # (max_tokens - pool) always survives — otherwise glm-5.2's effort=high
    # reasoning prelude eats the whole budget and content truncates at
    # finish_reason='length'. Cap the pool at half the budget so content never
    # loses; glm-5.2's branch-1 honors reasoning.max_tokens. Passed positionally-
    # safe as a kwarg so the OFF/stub paths (which ignore **kwargs) stay identical.
    _reasoning_pool = min(_PLANNING_GATE_REASONING_MAX_TOKENS, max(max_tokens // 2, 1))
    response = await client.generate(
        prompt=user,
        system=system,
        max_tokens=max_tokens,
        temperature=0.0,
        reasoning_max_tokens=_reasoning_pool,
    )
    return getattr(response, "content", None) or ""


def _errors_block(errors: list[ValidationError]) -> str:
    return json.dumps([e.to_dict() for e in errors], ensure_ascii=False)


# Validator error codes that are REPAIRABLE by the autonomous disclosure sweep
# (or are advisory), so they must NOT force the conservative fallback / discard a
# good contract. Everything else (the no-invention + span invariants: bad enums,
# hard_not_explicit, explicit_without_span, span_quote_mismatch, duplicate ids)
# is FATAL and drives the retry → fallback path.
_REPAIRABLE_CODES: frozenset[str] = frozenset({
    "inferred_not_disclosed",
    "mandatory_lane_count_mismatch",
})


# In AUTONOMOUS mode an inferred-hard that survives the retry is not fatal: the
# disclosure sweep downgrades it hard→preference (never a fabricated hard gate),
# so it must not nuke an otherwise-good contract to the raw-prompt fallback. In
# interactive mode it stays fatal (a human can fix it). The span-integrity checks
# stay fatal in BOTH modes — a bad span can never be silently kept.
_AUTONOMOUS_REPAIRABLE_CODES: frozenset[str] = _REPAIRABLE_CODES | frozenset({
    "hard_not_explicit",
})


def _fatal_errors(
    errors: list[ValidationError], *, mode: str = "interactive"
) -> list[ValidationError]:
    repairable = (
        _AUTONOMOUS_REPAIRABLE_CODES if mode == "autonomous" else _REPAIRABLE_CODES
    )
    return [e for e in errors if e.code not in repairable]


# ---------------------------------------------------------------------------
# The gate entry point
# ---------------------------------------------------------------------------

async def run_research_planning_gate(
    prompt: str,
    *,
    mode: str,
    client: Any = None,
    rule_reader: Any = None,
    ontology: Any = None,
    run_id: Optional[str] = None,
    model: Optional[str] = None,
) -> GateResult:
    """Compile ``prompt`` into a pinned :class:`PlanningGateArtifact`.

    Parameters
    ----------
    prompt:
        The raw task prompt.
    mode:
        ``"autonomous"`` (benchmark — never blocks) or ``"interactive"`` (may
        return ``needs_input`` with ≤3 material questions). The caller passes it
        EXPLICITLY; the gate never infers mode from a terminal/timeout.
    client:
        An LLM client with an async ``generate(prompt, system, max_tokens,
        temperature)`` returning an object with ``.content``. Tests inject a
        stub. When ``None``, a real :class:`OpenRouterClient` is built ONLY if
        ``PG_PLANNING_GATE_LIVE=1``; otherwise this raises (the OFF path never
        fires an LLM).
    rule_reader / ontology:
        Forwarded to the S0 ``reconcile_candidates`` candidate seeding.

    Returns
    -------
    GateResult
        Autonomous: ``state`` is ``auto_pinned`` (or ``unsatisfiable`` on a fatal
        explicit contradiction), ``needs_input`` ALWAYS False. Interactive:
        ``needs_input`` True iff there are material questions, else ``approved``.
    """
    mode = (mode or "").strip().lower()
    if mode not in ("interactive", "autonomous"):
        raise ValueError(
            f"mode must be 'interactive' or 'autonomous', got {mode!r} "
            f"(the caller passes it explicitly; the gate never infers it)"
        )

    if client is None:
        if not _live_enabled():
            raise RuntimeError(
                "research planning gate: live LLM disabled. Set "
                "PG_PLANNING_GATE_LIVE=1 for a real call, or pass client= in tests."
            )
        from src.polaris_graph.llm.openrouter_client import (  # noqa: PLC0415
            OpenRouterClient,
        )
        client = OpenRouterClient(model=model or _resolve_model())

    run_id = run_id or f"gate_{uuid.uuid4().hex[:12]}"

    # --- 1. deterministic candidate seeding (S0 adapter) ---
    try:
        candidates = reconcile_candidates(
            prompt, rule_reader=rule_reader, ontology=ontology
        )
    except Exception:  # noqa: BLE001 — candidates are advisory; fail-open to none
        candidates = []

    # --- 2. contract compile (+ one correction retry, then fallback) ---
    contract, contract_errors, degraded = await _compile_contract(
        client, prompt, candidates, mode=mode
    )

    # --- 2b. DETERMINISTIC-AUTHORITATIVE MONOTONIC MERGE (the inversion) ---
    # The LLM contract is ADDITIVE ONLY. Deterministic code (candidate adapter +
    # registry) authored the explicit constraints; here they are reinstated as
    # authority — the LLM can neither drop, downgrade, nor re-dimension them. This
    # subsumes the deleted task-shaped ``_promote_source_scope``. No-op
    # (byte-identical to the pure-LLM compile) when PG_GATE is OFF.
    contract = _merge_deterministic_authority(contract, candidates, prompt)
    contract_errors = validate_contract(contract, prompt)
    # MONOTONICITY invariant: every span-verified deterministic explicit candidate
    # must have survived the merge. A violation means a merge bug dropped a stated
    # constraint — surfaced as a validation error (belt: the merge already
    # reinstates them, so this should be empty when the gate is ON).
    if gate_enabled():
        contract_errors = contract_errors + validate_monotonicity(
            contract, _deterministic_candidate_ids(candidates, prompt)
        )

    # --- 3. mode split (the ONLY node the two modes differ at) ---
    if mode == "autonomous":
        contract = _autonomous_disclose(contract)
        # re-validate after disclosure (should be clean; record if not)
        contract_errors = validate_contract(contract, prompt)
        fatal = any(c.fatal for c in contract.conflicts)
        state = "unsatisfiable" if fatal else "auto_pinned"
        questions: list[dict[str, Any]] = []
        needs_input = False
    else:
        questions = _material_questions(contract)
        needs_input = bool(questions)
        state = "needs_input" if needs_input else "approved"

    # --- 4. plan compile (from the validated contract) ---
    plan, plan_errors = await _compile_plan(client, contract)

    artifact = PlanningGateArtifact(
        run_id=run_id,
        mode=mode,
        state=state,
        original_prompt=prompt,
        contract=contract,
        plan=plan,
        created_at=_dt.datetime.now(_dt.timezone.utc).isoformat(),
        approval_actor="autonomous_policy" if mode == "autonomous" else None,
        approval_policy_version="planning-gate/1.0" if mode == "autonomous" else None,
    )
    for q in questions:
        from src.polaris_graph.planning.planning_gate_schema import (  # noqa: PLC0415
            ClarificationQuestion,
        )
        artifact.clarification_questions.append(ClarificationQuestion(
            question_id=q["question_id"],
            prompt=q["prompt"],
            choices=q["choices"],
            affected_term_ids=q["affected_term_ids"],
            why_it_matters=q["why_it_matters"],
        ))
    if degraded:
        artifact.contract.compiler_degraded = True
    # Honest enforcement state (deliverable 6): pinned_executable /
    # degraded_lossless / blocked_unsupported. Derived from the FINAL contract
    # (after the disclosure sweep) so an opaque hard term surfaces as blocked.
    # Only meaningful when the deterministic authority is ON; OFF path leaves it
    # empty (the enforcement state is a property of the inversion, not champion).
    enforcement_state = (
        _enforcement_state(artifact.contract) if gate_enabled() else ""
    )
    artifact.recompute_hashes()

    return GateResult(
        artifact=artifact,
        needs_input=needs_input,
        questions=questions,
        contract_errors=contract_errors,
        plan_errors=plan_errors,
        enforcement_state=enforcement_state,
    )


async def _compile_contract(
    client: Any,
    prompt: str,
    candidates: list[CandidateConstraint],
    *,
    mode: str = "interactive",
) -> tuple[ResearchContract, list[ValidationError], bool]:
    """Contract compile with one bounded correction retry, then conservative
    fallback. Returns ``(contract, remaining_errors, degraded)``.

    The retry fires on ANY validation error (push the compiler to fix even
    repairable ones). The final keep-vs-fallback decision uses the MODE-AWARE
    fatal set: in autonomous mode an inferred-hard the compiler wouldn't fix is
    downgraded by the disclosure sweep rather than nuking the whole contract to
    the raw-prompt fallback; span-integrity violations stay fatal in both modes.
    """
    user = _contract_user_prompt(prompt, candidates, mode="compile")
    try:
        raw = await _call(client, _CONTRACT_SYSTEM_PROMPT, user, _CONTRACT_MAX_TOKENS)
        data = _loads(raw)
        contract = contract_from_dict(data.get("contract", data))
        # The LLM copies the verbatim quote correctly but drifts on character
        # offsets; re-derive each span from its quote (no-invention: a quote not
        # present in the prompt is left to fail validation). Mirrors the S0
        # candidate adapter's _locate_span discipline.
        reanchor_contract_spans(contract, prompt)
        errors = validate_contract(contract, prompt)
        if not _fatal_errors(errors, mode=mode):
            # No mode-fatal violation. Any remaining errors are repairable (an
            # undisclosed inferred term the autonomous sweep backfills, or an
            # inferred-hard the sweep downgrades), so keep the good contract.
            return contract, errors, False
    except Exception as exc:  # noqa: BLE001
        logger.warning("contract compile failed (attempt 1): %s", exc)
        errors = [ValidationError("compile_exception", str(exc))]
        contract = None  # type: ignore[assignment]

    # --- one correction retry with machine-readable errors ---
    retry_user = (
        user
        + "\n\nYour previous output was rejected by the deterministic validator "
          "with these errors. Fix EVERY one — especially any hard term that is "
          "not origin=explicit, and any explicit term whose span does not quote "
          "the request exactly. Return corrected JSON only.\n"
        + _errors_block(errors)
    )
    try:
        raw2 = await _call(client, _CONTRACT_SYSTEM_PROMPT, retry_user, _CONTRACT_MAX_TOKENS)
        data2 = _loads(raw2)
        contract2 = contract_from_dict(data2.get("contract", data2))
        reanchor_contract_spans(contract2, prompt)
        errors2 = validate_contract(contract2, prompt)
        if not _fatal_errors(errors2, mode=mode):
            return contract2, errors2, False
        # retry still has a mode-fatal violation -> conservative fallback
        logger.warning(
            "contract compile still invalid after retry: %d fatal errors",
            len(_fatal_errors(errors2, mode=mode)),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("contract compile failed (attempt 2): %s", exc)

    fallback = _conservative_contract(prompt, candidates)
    return fallback, validate_contract(fallback, prompt), True


async def _compile_plan(
    client: Any, contract: ResearchContract
) -> tuple[ResearchExecutionPlan, list[ValidationError]]:
    """Plan compile with one bounded correction retry, then a deterministic
    one-thread-per-required-clause fallback (never drop a clause)."""
    user = _plan_user_prompt(contract)
    try:
        raw = await _call(client, _PLAN_SYSTEM_PROMPT, user, _PLAN_MAX_TOKENS)
        data = _loads(raw)
        plan = plan_from_dict(data.get("plan", data))
        errors = validate_plan(plan, contract)
        if not errors:
            return plan, []
    except Exception as exc:  # noqa: BLE001
        logger.warning("plan compile failed (attempt 1): %s", exc)
        errors = [ValidationError("compile_exception", str(exc))]
        plan = None  # type: ignore[assignment]

    retry_user = (
        user
        + "\n\nYour previous plan was rejected by the validator with these "
          "errors. Fix EVERY one — give every required coverage requirement a "
          "mandatory query intent via a thread, and bind every hard contract "
          "term in coverage_matrix. Return corrected JSON only.\n"
        + _errors_block(errors)
    )
    try:
        raw2 = await _call(client, _PLAN_SYSTEM_PROMPT, retry_user, _PLAN_MAX_TOKENS)
        data2 = _loads(raw2)
        plan2 = plan_from_dict(data2.get("plan", data2))
        errors2 = validate_plan(plan2, contract)
        if not errors2:
            return plan2, []
    except Exception as exc:  # noqa: BLE001
        logger.warning("plan compile failed (attempt 2): %s", exc)

    return _fallback_plan(contract), []


def _fallback_plan(contract: ResearchContract) -> ResearchExecutionPlan:
    """Deterministic one-thread-per-required-clause plan — never drops a clause."""
    from src.polaris_graph.planning.planning_gate_schema import (  # noqa: PLC0415
        BudgetEnvelope,
        CoverageBinding,
        QueryIntent,
        ResearchThread,
    )

    threads: list[ResearchThread] = []
    intents: list[QueryIntent] = []
    matrix: list[CoverageBinding] = []

    reqs = [c for c in contract.coverage if c.required] or contract.coverage
    if not reqs:
        # a narrow prompt with no explicit coverage: one discovery thread on the
        # objective (never fabricate facets).
        obj_val = ""
        for t in contract.objective:
            if t.value:
                obj_val = str(t.value)
                break
        threads.append(ResearchThread(
            thread_id="t1", question=obj_val, purpose="objective discovery",
            mandatory=True,
        ))
        intents.append(QueryIntent(
            intent_id="qi1", thread_id="t1", purpose="discovery",
            concepts=[obj_val] if obj_val else [], mandatory=True,
        ))
    else:
        for i, cr in enumerate(reqs, 1):
            tid = f"t{i}"
            qid = f"qi{i}"
            stmt = str(cr.statement.value or cr.requirement_id or f"requirement {i}")
            threads.append(ResearchThread(
                thread_id=tid, question=stmt, purpose="cover requirement",
                coverage_requirement_ids=[cr.requirement_id] if cr.requirement_id else [],
                mandatory=True,
            ))
            intents.append(QueryIntent(
                intent_id=qid, thread_id=tid, purpose="discovery",
                concepts=[stmt], mandatory=True,
            ))

    for term in contract.hard_terms():
        if term.term_id:
            matrix.append(CoverageBinding(
                contract_term_id=term.term_id,
                owning_stages=["retrieval"],
                audit_method="deterministic",
            ))

    return ResearchExecutionPlan(
        threads=threads,
        query_intents=intents,
        coverage_matrix=matrix,
        budget=BudgetEnvelope(
            mandatory_lane_count=len(intents),
            overflow_policy="expand",
        ),
        stop_conditions=["every mandatory thread has usable evidence of the required kind"],
    )
