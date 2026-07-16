"""Research Planning Gate — typed contract + plan + artifact schema (S1).

This is the durable, typed governance object the gate produces ONCE per request
and every downstream stage consumes. It merges Sol's typed skeleton
(GATE_DESIGN_CONSOLIDATED §3, sol_gate_design §2) with Fable's ``Tagged``
provenance discipline: **every interpreted term carries an origin, a force, and
(for explicit terms) exact prompt spans**, so the no-invention guarantee is a
mechanical type invariant rather than a prompt-time hope.

Design contract (S1 — schema, OFFLINE, no retrieval)
----------------------------------------------------
* **Pure + offline.** No network, no LLM, no I/O. This module is data + strict
  deterministic validators only. The compiler (``research_planning_gate.py``)
  makes the LLM calls and builds these objects; this module never imports a
  client.
* **The no-invention invariant is enforced by TYPE.** A ``ContractTerm`` whose
  ``force == "hard"`` is INVALID unless its ``origin`` is ``explicit``,
  ``user_answer`` or ``user_edit`` (a real prompt span or an affirmative user
  action). ``inferred`` / ``policy_default`` terms may only ``prefer`` / stay
  ``open`` — they can weight, rank or route, never hard-gate or exclude. See
  :func:`validate_contract`.
* **``explicit`` requires quote equality.** An ``explicit`` term must carry at
  least one :class:`PromptSpan` whose ``quote`` exactly equals
  ``prompt[start:end]``. This is the same discipline the S0 candidate adapter
  already guarantees; the validator re-checks it against the original prompt so
  a compiler can never fabricate an offset.
* **Fail-soft parsing.** :func:`contract_from_dict` / :func:`plan_from_dict`
  tolerate missing optional keys (open/null), unknown keys (ignored), and
  scalar-vs-list mismatches — the compiler's JSON is model output. Parsing NEVER
  raises for a *shape* problem it can normalize; the deterministic validators
  (which return a structured error list, not exceptions) are the gate on
  correctness. Only a value that cannot be coerced at all raises ``SchemaError``.
* **Hashing reuses the champion discipline.** :func:`serialize_canonical` mirrors
  ``research_planner.serialize_plan_canonical`` (sort_keys + fixed separators +
  ``ensure_ascii=False``) so the artifact SHAs are reproducible bytes, and
  :func:`sha256_of` is the same construction as ``research_planner.plan_sha256``.

Nothing here is wired into the pipeline. It is the shared vocabulary S2–S6 read.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Controlled vocabularies (small, explicit, validated)
# ---------------------------------------------------------------------------

MODES: frozenset[str] = frozenset({"interactive", "autonomous"})

GATE_STATES: frozenset[str] = frozenset({
    "draft",
    "needs_input",
    "approved",
    "auto_pinned",
    "superseded",
    "unsatisfiable",
})

# Where an interpretation came from. Only the first three are "authoritative"
# (a real prompt span or an affirmative user action) and thus may back a HARD
# term. `inferred` / `policy_default` are always revisable and may never hard-gate.
ORIGIN_EXPLICIT = "explicit"        # supported by exact user text (needs a span)
ORIGIN_USER_ANSWER = "user_answer"  # supplied in a clarification answer
ORIGIN_USER_EDIT = "user_edit"      # approved edit to the draft plan
ORIGIN_INFERRED = "inferred"        # useful interpretation; always revisable
ORIGIN_POLICY_DEFAULT = "policy_default"  # named product policy; never user text

ORIGINS: frozenset[str] = frozenset({
    ORIGIN_EXPLICIT,
    ORIGIN_USER_ANSWER,
    ORIGIN_USER_EDIT,
    ORIGIN_INFERRED,
    ORIGIN_POLICY_DEFAULT,
})

# The set of origins that may back a `hard` term — the mechanical no-invention
# guarantee. An affirmative user action or a real prompt span; nothing inferred.
HARD_ELIGIBLE_ORIGINS: frozenset[str] = frozenset({
    ORIGIN_EXPLICIT,
    ORIGIN_USER_ANSWER,
    ORIGIN_USER_EDIT,
})

# The set of origins that MUST appear in the contract's `assumptions` ledger.
DISCLOSURE_ORIGINS: frozenset[str] = frozenset({
    ORIGIN_INFERRED,
    ORIGIN_POLICY_DEFAULT,
})

FORCE_HARD = "hard"            # binding inclusion / exclusion / shape requirement
FORCE_PREFER = "preference"    # optimize when feasible; may NEVER starve coverage
FORCE_OPEN = "open"            # intentionally unspecified

FORCES: frozenset[str] = frozenset({FORCE_HARD, FORCE_PREFER, FORCE_OPEN})

STAGES: frozenset[str] = frozenset({
    "retrieval",
    "outline",
    "compose",
    "render",
    "audit",
})

# ---------------------------------------------------------------------------
# Generic constraint-IR vocabularies (Phase B — the schema-loss fix)
# ---------------------------------------------------------------------------
# A term carries, IN ADDITION to the back-compat ``dimension``/``value`` pair, a
# generic (subject, attribute, operator, value_set) shape so "only news and press
# releases from 2024 onward" is expressible without a per-type Python branch:
#   {subject: source, attribute: kind, operator: IN,  value_set: [news, press]}
#   {subject: source, attribute: published_at, operator: GTE, value: 2024-01-01}
# Existing dimension/value stay authoritative for the legacy projection; the new
# fields are OPTIONAL and default empty, so an old term round-trips byte-identically
# (``to_dict`` only emits a new key when it is non-default — see ContractTerm).

# The generic relation a term asserts over its value / value_set.
OP_IN = "IN"            # membership: attribute ∈ value_set   (allowed-kind set)
OP_NOT_IN = "NOT_IN"    # exclusion:  attribute ∉ value_set   ("no blogs")
OP_EQ = "EQ"            # equality:   attribute == value
OP_GTE = "GTE"          # lower bound: attribute >= value      (from 2024 onward)
OP_LTE = "LTE"          # upper bound: attribute <= value      (before 2020)
OP_BETWEEN = "BETWEEN"  # interval:   value <= attribute <= value2 (value == "lo..hi")
OP_REQUIRE = "REQUIRE"  # obligation: attribute must be covered/present
OP_PREFER = "PREFER"    # soft optimize: attribute preferred, never gates

OPERATORS: frozenset[str] = frozenset({
    OP_IN, OP_NOT_IN, OP_EQ, OP_GTE, OP_LTE, OP_BETWEEN, OP_REQUIRE, OP_PREFER,
})

# Which stage OWNS a term's enforcement. A retrieval/ranking/eligibility term
# shapes the citable source set; compose/render terms shape the deliverable. This
# is the "no category leakage" axis (a deliverable.format term must NOT land in
# retrieval scope). ``stage_owner`` is a single owning stage; ``enforcement_stages``
# stays a free list for the legacy audit path.
STAGE_OWNERS: frozenset[str] = frozenset({
    "retrieval", "ranking", "eligibility", "compose", "render",
})

# How well the term's value is normalized. ``exact`` = a registry mapped the raw
# phrase to a canonical value/operator. ``proposed`` = the LLM suggested a
# normalization not yet registry-confirmed. ``opaque`` = the phrase is a
# first-class constraint we preserve verbatim but cannot (yet) normalize/enforce.
# An opaque HARD term is lossless-preserved and surfaced as blocked_unsupported —
# never silently dropped.
NORM_EXACT = "exact"
NORM_PROPOSED = "proposed"
NORM_OPAQUE = "opaque"

NORMALIZATION_STATUSES: frozenset[str] = frozenset({
    NORM_EXACT, NORM_PROPOSED, NORM_OPAQUE,
})

# ---------------------------------------------------------------------------
# Canonical SOURCE-scope dimensions (distinct from deliverable.output_language)
# ---------------------------------------------------------------------------
# The gate schema holds ``scope`` as a flat ``ContractTerm`` list keyed by a
# free-string ``dimension``; these are the three canonical SOURCE-scope slots the
# deterministic promoter writes and the retrieval projection reads. They describe
# the SOURCES a citation must come from — NOT the deliverable's output language.
# ``scope.source_languages`` is the language a *cited source* must be in ("cite
# English-language journal articles"); ``deliverable.output_language`` is the
# language the *report* is written in. Conflating them is the task-72 bug, so the
# two live in different groups (scope vs deliverable) with different dimensions.
SCOPE_SOURCE_TYPES = "scope.source_types"          # e.g. journal_article
SCOPE_SOURCE_QUALITY = "scope.source_quality"      # e.g. high (high-quality/peer-reviewed)
SCOPE_SOURCE_LANGUAGES = "scope.source_languages"  # SOURCE language, e.g. en / English

SCHEMA_VERSION = "planning-gate/1.0"


class SchemaError(ValueError):
    """Raised only when a value cannot be coerced into the schema at all.

    Shape problems the parser can normalize (missing optional keys, scalar vs
    list, unknown keys) do NOT raise — they are normalized. Correctness problems
    (a hard inferred term, a bad span) do NOT raise either — they are reported by
    :func:`validate_contract` as a structured error list, so the compiler can run
    one bounded correction retry.
    """


# ---------------------------------------------------------------------------
# Coercion helpers (fail-soft; mirror constraint_extractor discipline)
# ---------------------------------------------------------------------------

def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    items = value if isinstance(value, (list, tuple)) else [value]
    out: list[str] = []
    for it in items:
        if it is None:
            continue
        s = str(it).strip()
        if s:
            out.append(s)
    return out


def _as_opt_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        value = next((v for v in value if v not in (None, "")), None)
        if value is None:
            return None
    s = str(value).strip()
    if not s or s.lower() in ("none", "null", "n/a", "na"):
        return None
    return s


def _as_opt_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


# A small, honest synonym table: maps a phrasing to its canonical enum WITHOUT
# inventing meaning. ``must``/``required`` really do mean hard; ``soft``/``prefer``
# really do mean preference; ``user``/``user_edit`` are affirmative-user origins.
# NOTE: no entry weakens a stated force (e.g. ``mandatory`` maps to hard, never to
# open) — the old silent hard→open default was the weakening bug (RECON §D).
_ENUM_SYNONYMS: dict[str, str] = {
    "soft": FORCE_PREFER,
    "prefer": FORCE_PREFER,
    "preferred": FORCE_PREFER,
    "required": FORCE_HARD,
    "require": FORCE_HARD,
    "must": FORCE_HARD,
    "mandatory": FORCE_HARD,
    "none": FORCE_OPEN,
    "unspecified": FORCE_OPEN,
    "user": ORIGIN_USER_ANSWER,
    "user_answer": ORIGIN_USER_ANSWER,
    "user_edit": ORIGIN_USER_EDIT,
    "default": ORIGIN_POLICY_DEFAULT,
}


def _norm_enum(value: Any, allowed: frozenset[str], default: str) -> str:
    """Normalize a scalar to a member of ``allowed`` or fall back to ``default``.

    Fail-soft on ABSENCE only: a missing value takes ``default``. A present value
    is canonicalized via the honest synonym table but is NEVER silently coerced to
    ``default`` when it is out-of-vocab — an out-of-vocab present value is returned
    verbatim (lowercased) so :func:`validate_contract` can SURFACE it as a
    ``bad_origin``/``bad_force`` error instead of hiding the malformed output
    behind a conservative default (RECON §D; spec deliverable 5).
    """
    s = _as_opt_str(value)
    if s is None:
        return default
    low = s.strip().lower()
    if low in allowed:
        return low
    mapped = _ENUM_SYNONYMS.get(low)
    if mapped in allowed:
        return mapped
    # Out-of-vocab present value: keep it verbatim so the validator surfaces it.
    return low


def _norm_enum_soft(value: Any, allowed: frozenset[str], default: str) -> str:
    """Absence- AND out-of-vocab-tolerant normalization (coerces to ``default``).

    Used for structural enums (coverage kind, query purpose) where an unknown
    value is a harmless mislabel, not a load-bearing authority claim. The
    force/origin path uses the strict :func:`_norm_enum` so bad values surface.
    """
    s = _as_opt_str(value)
    if s is None:
        return default
    low = s.strip().lower()
    if low in allowed:
        return low
    mapped = _ENUM_SYNONYMS.get(low)
    if mapped in allowed:
        return mapped
    return default


# ---------------------------------------------------------------------------
# PromptSpan — verbatim, quote-equality-guaranteed
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PromptSpan:
    """A verbatim prompt span; ``quote`` MUST equal ``prompt[start:end]``.

    The invariant is CHECKED (not merely trusted) by :meth:`matches_prompt`,
    which the contract validator runs against the original prompt for every
    ``explicit`` term.
    """

    start: int
    end: int
    quote: str

    def matches_prompt(self, prompt: str) -> bool:
        if self.start < 0 or self.end < self.start or self.end > len(prompt or ""):
            return False
        return prompt[self.start:self.end] == self.quote

    def to_dict(self) -> dict[str, Any]:
        return {"start": self.start, "end": self.end, "quote": self.quote}

    @classmethod
    def from_dict(cls, d: Any) -> "PromptSpan":
        """Parse a span. Accepts EITHER the full ``{start,end,quote}`` object OR a
        bare quote-string.

        Per the inversion spec (deliverable 5): the model is NEVER asked for
        character offsets — deterministic code owns them via
        :func:`reanchor_contract_spans`. So a bare string ``"journal articles"`` is
        a valid span with placeholder offsets ``(-1,-1)``; re-anchoring derives the
        real offsets from the verbatim quote. Placeholder offsets fail
        ``matches_prompt`` until re-anchored, and a quote absent from the prompt
        stays a failing span (no fabricated support). This deletes the whole
        "span must be an object" failure class (RECON §C).
        """
        if isinstance(d, str):
            return cls(start=-1, end=-1, quote=d)
        if not isinstance(d, dict):
            raise SchemaError(f"span must be an object or a quote string, got {type(d).__name__}")
        quote = str(d.get("quote", ""))
        # Offsets are advisory; a non-int / missing offset becomes the -1
        # placeholder that re-anchoring corrects from the quote (never a raise).
        try:
            start = int(d.get("start"))
        except (TypeError, ValueError):
            start = -1
        try:
            end = int(d.get("end"))
        except (TypeError, ValueError):
            end = -1
        return cls(start=start, end=end, quote=quote)


def _spans_from(value: Any) -> list[PromptSpan]:
    """Parse a spans list PER ITEM: one malformed span is skipped (logged by the
    caller via the resulting empty/short list), never propagated as an exception
    that nukes the whole term/contract (RECON §C; spec deliverable 5).
    """
    if not value:
        return []
    items = value if isinstance(value, (list, tuple)) else [value]
    out: list[PromptSpan] = []
    for it in items:
        try:
            sp = PromptSpan.from_dict(it)
        except SchemaError:
            continue  # skip this one span; keep the rest
        if sp.quote:  # a span with no quote carries no support — drop it
            out.append(sp)
    return out


# ---------------------------------------------------------------------------
# ContractTerm — the tagged-provenance unit
# ---------------------------------------------------------------------------

@dataclass
class ContractTerm:
    """One interpreted term with origin / force / spans (the tagged unit).

    ``value`` is deliberately ``Any | None`` so the same type carries a string
    (language), a bool (peer-review), an int (item count), or a list. ``None``
    means "open / unspecified" — the least-restrictive interpretation.
    """

    term_id: str
    dimension: str
    value: Any = None
    origin: str = ORIGIN_INFERRED
    force: str = FORCE_OPEN
    confidence: float = 0.0
    spans: list[PromptSpan] = field(default_factory=list)
    rationale: str = ""
    policy_id: Optional[str] = None
    enforcement_stages: list[str] = field(default_factory=list)
    editable: bool = True
    # --- generic constraint-IR fields (Phase B; all OPTIONAL / default-empty) ---
    # These make a term's semantics machine-checkable and enforceable without a
    # per-type branch. They are ADDITIVE: an old term with none of them set emits
    # exactly the legacy dict (``to_dict`` skips a field at its default), so an
    # existing artifact hashes byte-identically. See module header.
    subject: str = ""                    # e.g. source, evidence, output, section
    attribute: str = ""                  # e.g. kind, published_at, language, quality
    operator: str = ""                   # one of OPERATORS ("" == unset / legacy)
    value_set: list[Any] = field(default_factory=list)  # for IN / NOT_IN
    boolean_group: str = ""              # coordination group id (AND/OR members share it)
    stage_owner: str = ""                # one of STAGE_OWNERS ("" == unset / legacy)
    capability_id: str = ""              # the registered executable enforcer (Phase D)
    normalization_status: str = ""       # exact | proposed | opaque ("" == unset / legacy)

    def is_hard(self) -> bool:
        return self.force == FORCE_HARD

    def is_opaque(self) -> bool:
        return self.normalization_status == NORM_OPAQUE

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "term_id": self.term_id,
            "dimension": self.dimension,
            "value": self.value,
            "origin": self.origin,
            "force": self.force,
            "confidence": self.confidence,
            "spans": [s.to_dict() for s in self.spans],
            "rationale": self.rationale,
            "policy_id": self.policy_id,
            "enforcement_stages": list(self.enforcement_stages),
            "editable": self.editable,
        }
        # Emit each generic-IR field ONLY when it is set (non-default), so a term
        # that never used the generic axes serializes to the legacy shape and
        # hashes byte-identically. This preserves the OFF-path guardrail.
        if self.subject:
            out["subject"] = self.subject
        if self.attribute:
            out["attribute"] = self.attribute
        if self.operator:
            out["operator"] = self.operator
        if self.value_set:
            out["value_set"] = list(self.value_set)
        if self.boolean_group:
            out["boolean_group"] = self.boolean_group
        if self.stage_owner:
            out["stage_owner"] = self.stage_owner
        if self.capability_id:
            out["capability_id"] = self.capability_id
        if self.normalization_status:
            out["normalization_status"] = self.normalization_status
        return out

    @classmethod
    def from_dict(cls, d: Any) -> "ContractTerm":
        if not isinstance(d, dict):
            raise SchemaError(f"term must be an object, got {type(d).__name__}")
        term_id = _as_opt_str(d.get("term_id")) or ""
        dimension = _as_opt_str(d.get("dimension")) or ""
        try:
            conf = float(d.get("confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            conf = 0.0
        stages = [
            s for s in _as_str_list(d.get("enforcement_stages")) if s in STAGES
        ]
        # Generic-IR fields: read them if present. An out-of-vocab operator /
        # stage_owner / normalization_status is NOT silently coerced to a default
        # (that would hide a malformed proposal); it is kept verbatim so
        # ``validate_contract`` can surface it as a bad-enum error.
        return cls(
            term_id=term_id,
            dimension=dimension,
            value=d.get("value"),
            origin=_norm_enum(d.get("origin"), ORIGINS, ORIGIN_INFERRED),
            force=_norm_enum(d.get("force"), FORCES, FORCE_OPEN),
            confidence=conf,
            spans=_spans_from(d.get("spans")),
            rationale=_as_opt_str(d.get("rationale")) or "",
            policy_id=_as_opt_str(d.get("policy_id")),
            enforcement_stages=stages,
            editable=_as_bool(d.get("editable"), default=True),
            subject=_as_opt_str(d.get("subject")) or "",
            attribute=_as_opt_str(d.get("attribute")) or "",
            operator=_as_opt_str(d.get("operator")) or "",
            value_set=list(d.get("value_set")) if isinstance(d.get("value_set"), (list, tuple)) else [],
            boolean_group=_as_opt_str(d.get("boolean_group")) or "",
            stage_owner=_as_opt_str(d.get("stage_owner")) or "",
            capability_id=_as_opt_str(d.get("capability_id")) or "",
            normalization_status=_as_opt_str(d.get("normalization_status")) or "",
        )


# ---------------------------------------------------------------------------
# Coverage / deliverable / disclosure sub-objects
# ---------------------------------------------------------------------------

COVERAGE_KINDS: frozenset[str] = frozenset({
    "topic", "question", "entity", "comparison", "metric", "time_series",
    "case", "perspective", "counterevidence", "recommendation", "forecast",
    "method",
})


@dataclass
class CoverageRequirement:
    """A required (or optional) content obligation — NOT automatically a heading."""

    requirement_id: str
    kind: str
    statement: ContractTerm
    entity_ids: list[str] = field(default_factory=list)
    compare_on: list[ContractTerm] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    acceptance_hint: Optional[str] = None
    required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "kind": self.kind,
            "statement": self.statement.to_dict(),
            "entity_ids": list(self.entity_ids),
            "compare_on": [t.to_dict() for t in self.compare_on],
            "dependencies": list(self.dependencies),
            "acceptance_hint": self.acceptance_hint,
            "required": self.required,
        }

    @classmethod
    def from_dict(cls, d: Any, *, required: bool = True) -> "CoverageRequirement":
        if not isinstance(d, dict):
            raise SchemaError("coverage requirement must be an object")
        kind = _norm_enum_soft(d.get("kind"), COVERAGE_KINDS, "topic")
        stmt = d.get("statement")
        statement = (
            ContractTerm.from_dict(stmt)
            if isinstance(stmt, dict)
            else ContractTerm(
                term_id=_as_opt_str(d.get("requirement_id")) or "",
                dimension="content.coverage",
                value=_as_opt_str(stmt),
                origin=ORIGIN_INFERRED,
                force=FORCE_OPEN,
            )
        )
        compare_on = [
            ContractTerm.from_dict(c)
            for c in (d.get("compare_on") or [])
            if isinstance(c, dict)
        ]
        return cls(
            requirement_id=_as_opt_str(d.get("requirement_id")) or "",
            kind=kind,
            statement=statement,
            entity_ids=_as_str_list(d.get("entity_ids")),
            compare_on=compare_on,
            dependencies=_as_str_list(d.get("dependencies")),
            acceptance_hint=_as_opt_str(d.get("acceptance_hint")),
            required=_as_bool(d.get("required"), default=required),
        )


@dataclass
class SectionRequirement:
    """A requested deliverable section. Exact-title lock only for explicit terms."""

    section_id: str
    title: ContractTerm
    purpose: str = ""
    order: Optional[int] = None
    required: bool = True
    exact_title_lock: bool = False
    coverage_requirement_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "section_id": self.section_id,
            "title": self.title.to_dict(),
            "purpose": self.purpose,
            "order": self.order,
            "required": self.required,
            "exact_title_lock": self.exact_title_lock,
            "coverage_requirement_ids": list(self.coverage_requirement_ids),
        }

    @classmethod
    def from_dict(cls, d: Any) -> "SectionRequirement":
        if not isinstance(d, dict):
            raise SchemaError("section requirement must be an object")
        title = d.get("title")
        title_term = (
            ContractTerm.from_dict(title)
            if isinstance(title, dict)
            else ContractTerm(
                term_id=_as_opt_str(d.get("section_id")) or "",
                dimension="deliverable.section",
                value=_as_opt_str(title),
                origin=ORIGIN_INFERRED,
                force=FORCE_OPEN,
            )
        )
        # exact_title_lock is only honored when the title term is authoritative
        # (explicit/user). A model claiming a lock on an inferred title is
        # downgraded here — a second belt to the validator's no-inferred-hard.
        claimed_lock = _as_bool(d.get("exact_title_lock"), default=False)
        lock = claimed_lock and title_term.origin in HARD_ELIGIBLE_ORIGINS
        return cls(
            section_id=_as_opt_str(d.get("section_id")) or "",
            title=title_term,
            purpose=_as_opt_str(d.get("purpose")) or "",
            order=_as_opt_int(d.get("order")),
            required=_as_bool(d.get("required"), default=True),
            exact_title_lock=lock,
            coverage_requirement_ids=_as_str_list(d.get("coverage_requirement_ids")),
        )


@dataclass
class Assumption:
    """A disclosed non-explicit interpretation. EVERY inferred/default term maps here."""

    assumption_id: str
    statement: str
    affected_term_ids: list[str] = field(default_factory=list)
    origin: str = ORIGIN_INFERRED
    consequence: str = ""
    reversible: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "assumption_id": self.assumption_id,
            "statement": self.statement,
            "affected_term_ids": list(self.affected_term_ids),
            "origin": self.origin,
            "consequence": self.consequence,
            "reversible": self.reversible,
        }

    @classmethod
    def from_dict(cls, d: Any) -> "Assumption":
        if not isinstance(d, dict):
            raise SchemaError("assumption must be an object")
        return cls(
            assumption_id=_as_opt_str(d.get("assumption_id")) or "",
            statement=_as_opt_str(d.get("statement")) or "",
            affected_term_ids=_as_str_list(d.get("affected_term_ids")),
            origin=_norm_enum_soft(d.get("origin"), DISCLOSURE_ORIGINS, ORIGIN_INFERRED),
            consequence=_as_opt_str(d.get("consequence")) or "",
            reversible=_as_bool(d.get("reversible"), default=True),
        )


@dataclass
class Ambiguity:
    ambiguity_id: str
    text: str
    affected_term_ids: list[str] = field(default_factory=list)
    plausible_interpretations: list[str] = field(default_factory=list)
    current_interpretation: Optional[str] = None
    decision_impact: list[str] = field(default_factory=list)
    confidence: float = 0.0
    material: bool = False
    can_proceed_open: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "ambiguity_id": self.ambiguity_id,
            "text": self.text,
            "affected_term_ids": list(self.affected_term_ids),
            "plausible_interpretations": list(self.plausible_interpretations),
            "current_interpretation": self.current_interpretation,
            "decision_impact": list(self.decision_impact),
            "confidence": self.confidence,
            "material": self.material,
            "can_proceed_open": self.can_proceed_open,
        }

    @classmethod
    def from_dict(cls, d: Any) -> "Ambiguity":
        if not isinstance(d, dict):
            raise SchemaError("ambiguity must be an object")
        try:
            conf = float(d.get("confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            conf = 0.0
        return cls(
            ambiguity_id=_as_opt_str(d.get("ambiguity_id")) or "",
            text=_as_opt_str(d.get("text")) or "",
            affected_term_ids=_as_str_list(d.get("affected_term_ids")),
            plausible_interpretations=_as_str_list(d.get("plausible_interpretations")),
            current_interpretation=_as_opt_str(d.get("current_interpretation")),
            decision_impact=[s for s in _as_str_list(d.get("decision_impact")) if s in STAGES],
            confidence=conf,
            material=_as_bool(d.get("material"), default=False),
            can_proceed_open=_as_bool(d.get("can_proceed_open"), default=True),
        )


@dataclass
class ContractConflict:
    conflict_id: str
    term_ids: list[str] = field(default_factory=list)
    explanation: str = ""
    resolution: Optional[str] = None
    fatal: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "conflict_id": self.conflict_id,
            "term_ids": list(self.term_ids),
            "explanation": self.explanation,
            "resolution": self.resolution,
            "fatal": self.fatal,
        }

    @classmethod
    def from_dict(cls, d: Any) -> "ContractConflict":
        if not isinstance(d, dict):
            raise SchemaError("conflict must be an object")
        return cls(
            conflict_id=_as_opt_str(d.get("conflict_id")) or "",
            term_ids=_as_str_list(d.get("term_ids")),
            explanation=_as_opt_str(d.get("explanation")) or "",
            resolution=_as_opt_str(d.get("resolution")),
            fatal=_as_bool(d.get("fatal"), default=False),
        )


# ---------------------------------------------------------------------------
# ResearchContract — the pinned governance object
# ---------------------------------------------------------------------------

@dataclass
class ResearchContract:
    """The typed contract. Grouped as objective / scope / content / deliverable.

    To keep the schema compact and fail-soft, the grouped specs are held as flat
    ``ContractTerm`` lists keyed by ``dimension`` (e.g. ``objective.question``,
    ``scope.source_types``, ``scope.date``, ``deliverable.kind``) plus the two
    structured collections that need their own shape (``coverage`` and
    ``sections``). Every term is uniformly a :class:`ContractTerm`, so the
    validator's no-invention sweep is a single pass over :meth:`all_terms`.
    """

    schema_version: str = SCHEMA_VERSION
    objective: list[ContractTerm] = field(default_factory=list)
    scope: list[ContractTerm] = field(default_factory=list)
    content_terms: list[ContractTerm] = field(default_factory=list)
    deliverable: list[ContractTerm] = field(default_factory=list)
    coverage: list[CoverageRequirement] = field(default_factory=list)
    sections: list[SectionRequirement] = field(default_factory=list)
    ambiguities: list[Ambiguity] = field(default_factory=list)
    assumptions: list[Assumption] = field(default_factory=list)
    conflicts: list[ContractConflict] = field(default_factory=list)
    complexity: str = "standard"
    compiler_degraded: bool = False

    def all_terms(self) -> list[ContractTerm]:
        """Every :class:`ContractTerm` in the contract (for the validator sweep)."""
        terms: list[ContractTerm] = []
        terms.extend(self.objective)
        terms.extend(self.scope)
        terms.extend(self.content_terms)
        terms.extend(self.deliverable)
        for cr in self.coverage:
            terms.append(cr.statement)
            terms.extend(cr.compare_on)
        for sec in self.sections:
            terms.append(sec.title)
        return terms

    def hard_terms(self) -> list[ContractTerm]:
        return [t for t in self.all_terms() if t.is_hard()]

    # -- S2 retrieval-projection compile methods ------------------------------
    # Thin wrappers over ``retrieval_projection`` (the no-starvation core). Kept
    # on the contract per the S2 task ("contract.to_research_frame() /
    # to_scope_terms() compile methods"); they build a projection over THIS
    # contract with an empty plan (scope routing needs only the contract) so a
    # caller holding just a contract can still route backends. The full
    # query-text projection (which needs the plan's mandatory intents) is built
    # via ``retrieval_projection.from_artifact`` / ``from_contract_and_plan``.
    # Deferred import keeps this module free of the ResearchFrame dependency.

    def to_research_frame(self, plan: Any = None) -> Any:
        """Route this contract's scope onto a champion ``ResearchFrame`` (or
        ``None`` when nothing is routable — the byte-identical champion path)."""
        from src.polaris_graph.planning.retrieval_projection import (  # noqa: PLC0415
            from_contract_and_plan,
        )
        proj = from_contract_and_plan(self, plan or ResearchExecutionPlan())
        return proj.to_research_frame()

    def to_scope_terms(self, plan: Any = None) -> dict[str, list[str]]:
        """The hard/soft scope split + language lanes + routed evidence needs."""
        from src.polaris_graph.planning.retrieval_projection import (  # noqa: PLC0415
            from_contract_and_plan,
        )
        proj = from_contract_and_plan(self, plan or ResearchExecutionPlan())
        return proj.to_scope_terms()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "objective": [t.to_dict() for t in self.objective],
            "scope": [t.to_dict() for t in self.scope],
            "content_terms": [t.to_dict() for t in self.content_terms],
            "deliverable": [t.to_dict() for t in self.deliverable],
            "coverage": [c.to_dict() for c in self.coverage],
            "sections": [s.to_dict() for s in self.sections],
            "ambiguities": [a.to_dict() for a in self.ambiguities],
            "assumptions": [a.to_dict() for a in self.assumptions],
            "conflicts": [c.to_dict() for c in self.conflicts],
            "complexity": self.complexity,
            "compiler_degraded": self.compiler_degraded,
        }


def contract_from_dict(d: Any) -> ResearchContract:
    """Parse a compiler JSON object (fail-soft) into a :class:`ResearchContract`.

    Accepts either the flat shape this module emits, or the grouped shape a
    compiler might emit (``objective``/``scope``/``content``/``deliverable``
    objects whose leaves are terms). Missing groups → empty (open) contract.
    """
    if not isinstance(d, dict):
        raise SchemaError(f"contract must be an object, got {type(d).__name__}")

    def _terms(key: str, *, group_prefix: str) -> list[ContractTerm]:
        raw = d.get(key)
        out: list[ContractTerm] = []
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    out.append(ContractTerm.from_dict(item))
        elif isinstance(raw, dict):
            # grouped object: {dimension_suffix: term-or-value}
            for sub_key, sub_val in raw.items():
                if isinstance(sub_val, dict) and "origin" in sub_val:
                    t = ContractTerm.from_dict(sub_val)
                    if not t.dimension:
                        t.dimension = f"{group_prefix}.{sub_key}"
                    if not t.term_id:
                        t.term_id = f"{group_prefix}.{sub_key}"
                    out.append(t)
                elif sub_val is not None:
                    out.append(ContractTerm(
                        term_id=f"{group_prefix}.{sub_key}",
                        dimension=f"{group_prefix}.{sub_key}",
                        value=sub_val,
                        origin=ORIGIN_INFERRED,
                        force=FORCE_OPEN,
                    ))
        return out

    content_block = d.get("content")
    coverage_raw: list[Any] = []
    if isinstance(content_block, dict):
        coverage_raw = list(content_block.get("required") or [])
        optional_raw = list(content_block.get("optional") or [])
    else:
        coverage_raw = list(d.get("coverage") or d.get("required_coverage") or [])
        optional_raw = list(d.get("optional_coverage") or [])

    coverage: list[CoverageRequirement] = []
    for c in coverage_raw:
        if isinstance(c, dict):
            coverage.append(CoverageRequirement.from_dict(c, required=True))
        elif c is not None:
            coverage.append(CoverageRequirement(
                requirement_id="",
                kind="topic",
                statement=ContractTerm(
                    term_id="", dimension="content.coverage",
                    value=str(c), origin=ORIGIN_INFERRED, force=FORCE_OPEN,
                ),
                required=True,
            ))
    for c in optional_raw:
        if isinstance(c, dict):
            coverage.append(CoverageRequirement.from_dict(c, required=False))

    sections_raw = d.get("sections")
    if sections_raw is None and isinstance(d.get("deliverable"), dict):
        sections_raw = d["deliverable"].get("sections")
    sections = [
        SectionRequirement.from_dict(s)
        for s in (sections_raw or [])
        if isinstance(s, dict)
    ]

    return ResearchContract(
        schema_version=_as_opt_str(d.get("schema_version")) or SCHEMA_VERSION,
        objective=_terms("objective", group_prefix="objective"),
        scope=_terms("scope", group_prefix="scope"),
        content_terms=_terms("content_terms", group_prefix="content"),
        deliverable=_terms("deliverable", group_prefix="deliverable"),
        coverage=coverage,
        sections=sections,
        ambiguities=[Ambiguity.from_dict(a) for a in (d.get("ambiguities") or []) if isinstance(a, dict)],
        assumptions=[Assumption.from_dict(a) for a in (d.get("assumptions") or []) if isinstance(a, dict)],
        conflicts=[ContractConflict.from_dict(c) for c in (d.get("conflicts") or []) if isinstance(c, dict)],
        complexity=_as_opt_str(d.get("complexity")) or "standard",
        compiler_degraded=_as_bool(d.get("compiler_degraded"), default=False),
    )


# ---------------------------------------------------------------------------
# ResearchExecutionPlan — adapts to evidence; contract stays pinned
# ---------------------------------------------------------------------------

QUERY_PURPOSES: frozenset[str] = frozenset({
    "discovery", "primary_source", "quantitative", "comparison",
    "counterevidence", "jurisdiction", "language", "freshness", "gap",
})


@dataclass
class ResearchThread:
    thread_id: str
    question: str
    purpose: str = ""
    parent_thread_id: Optional[str] = None
    dependency_thread_ids: list[str] = field(default_factory=list)
    coverage_requirement_ids: list[str] = field(default_factory=list)
    contract_term_ids: list[str] = field(default_factory=list)
    evidence_need_ids: list[str] = field(default_factory=list)
    mandatory: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "thread_id": self.thread_id,
            "question": self.question,
            "purpose": self.purpose,
            "parent_thread_id": self.parent_thread_id,
            "dependency_thread_ids": list(self.dependency_thread_ids),
            "coverage_requirement_ids": list(self.coverage_requirement_ids),
            "contract_term_ids": list(self.contract_term_ids),
            "evidence_need_ids": list(self.evidence_need_ids),
            "mandatory": self.mandatory,
        }

    @classmethod
    def from_dict(cls, d: Any) -> "ResearchThread":
        if not isinstance(d, dict):
            raise SchemaError("thread must be an object")
        return cls(
            thread_id=_as_opt_str(d.get("thread_id")) or "",
            question=_as_opt_str(d.get("question")) or "",
            purpose=_as_opt_str(d.get("purpose")) or "",
            parent_thread_id=_as_opt_str(d.get("parent_thread_id")),
            dependency_thread_ids=_as_str_list(d.get("dependency_thread_ids")),
            coverage_requirement_ids=_as_str_list(d.get("coverage_requirement_ids")),
            contract_term_ids=_as_str_list(d.get("contract_term_ids")),
            evidence_need_ids=_as_str_list(d.get("evidence_need_ids")),
            mandatory=_as_bool(d.get("mandatory"), default=True),
        )


@dataclass
class QueryIntent:
    intent_id: str
    thread_id: str
    purpose: str = "discovery"
    concepts: list[str] = field(default_factory=list)
    required_terms: list[str] = field(default_factory=list)
    alternate_phrasings: list[str] = field(default_factory=list)
    language: Optional[str] = None
    geography_or_jurisdiction: Optional[str] = None
    source_type: Optional[str] = None
    date_start: Optional[str] = None
    date_end: Optional[str] = None
    contract_term_ids: list[str] = field(default_factory=list)
    mandatory: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "thread_id": self.thread_id,
            "purpose": self.purpose,
            "concepts": list(self.concepts),
            "required_terms": list(self.required_terms),
            "alternate_phrasings": list(self.alternate_phrasings),
            "language": self.language,
            "geography_or_jurisdiction": self.geography_or_jurisdiction,
            "source_type": self.source_type,
            "date_start": self.date_start,
            "date_end": self.date_end,
            "contract_term_ids": list(self.contract_term_ids),
            "mandatory": self.mandatory,
        }

    @classmethod
    def from_dict(cls, d: Any) -> "QueryIntent":
        if not isinstance(d, dict):
            raise SchemaError("query intent must be an object")
        dw = d.get("date_window")
        date_start = date_end = None
        if isinstance(dw, (list, tuple)) and len(dw) == 2:
            date_start = _as_opt_str(dw[0])
            date_end = _as_opt_str(dw[1])
        return cls(
            intent_id=_as_opt_str(d.get("intent_id")) or "",
            thread_id=_as_opt_str(d.get("thread_id")) or "",
            purpose=_norm_enum_soft(d.get("purpose"), QUERY_PURPOSES, "discovery"),
            concepts=_as_str_list(d.get("concepts")),
            required_terms=_as_str_list(d.get("required_terms")),
            alternate_phrasings=_as_str_list(d.get("alternate_phrasings")),
            language=_as_opt_str(d.get("language")),
            geography_or_jurisdiction=_as_opt_str(d.get("geography_or_jurisdiction")),
            source_type=_as_opt_str(d.get("source_type")),
            date_start=_as_opt_str(d.get("date_start")) or date_start,
            date_end=_as_opt_str(d.get("date_end")) or date_end,
            contract_term_ids=_as_str_list(d.get("contract_term_ids")),
            mandatory=_as_bool(d.get("mandatory"), default=True),
        )


@dataclass
class EvidenceNeed:
    need_id: str
    kind: str = ""
    coverage_requirement_ids: list[str] = field(default_factory=list)
    source_policy_term_ids: list[str] = field(default_factory=list)
    sufficient_when: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "need_id": self.need_id,
            "kind": self.kind,
            "coverage_requirement_ids": list(self.coverage_requirement_ids),
            "source_policy_term_ids": list(self.source_policy_term_ids),
            "sufficient_when": self.sufficient_when,
        }

    @classmethod
    def from_dict(cls, d: Any) -> "EvidenceNeed":
        if not isinstance(d, dict):
            raise SchemaError("evidence need must be an object")
        return cls(
            need_id=_as_opt_str(d.get("need_id")) or "",
            kind=_as_opt_str(d.get("kind")) or "",
            coverage_requirement_ids=_as_str_list(d.get("coverage_requirement_ids")),
            source_policy_term_ids=_as_str_list(d.get("source_policy_term_ids")),
            sufficient_when=_as_opt_str(d.get("sufficient_when")) or "",
        )


@dataclass
class OutlineSeed:
    section_id: str
    display_title: str = ""
    purpose: str = ""
    order: int = 0
    exact_title_lock: bool = False
    order_lock: bool = False
    coverage_requirement_ids: list[str] = field(default_factory=list)
    thread_ids: list[str] = field(default_factory=list)
    evidence_need_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "section_id": self.section_id,
            "display_title": self.display_title,
            "purpose": self.purpose,
            "order": self.order,
            "exact_title_lock": self.exact_title_lock,
            "order_lock": self.order_lock,
            "coverage_requirement_ids": list(self.coverage_requirement_ids),
            "thread_ids": list(self.thread_ids),
            "evidence_need_ids": list(self.evidence_need_ids),
        }

    @classmethod
    def from_dict(cls, d: Any) -> "OutlineSeed":
        if not isinstance(d, dict):
            raise SchemaError("outline seed must be an object")
        return cls(
            section_id=_as_opt_str(d.get("section_id")) or "",
            display_title=_as_opt_str(d.get("display_title")) or "",
            purpose=_as_opt_str(d.get("purpose")) or "",
            order=_as_opt_int(d.get("order")) or 0,
            exact_title_lock=_as_bool(d.get("exact_title_lock"), default=False),
            order_lock=_as_bool(d.get("order_lock"), default=False),
            coverage_requirement_ids=_as_str_list(d.get("coverage_requirement_ids")),
            thread_ids=_as_str_list(d.get("thread_ids")),
            evidence_need_ids=_as_str_list(d.get("evidence_need_ids")),
        )


@dataclass
class CoverageBinding:
    """Every binding term → owning stage(s) + (when evidence-bearing) ≥1 lane."""

    contract_term_id: str
    requirement_id: Optional[str] = None
    thread_ids: list[str] = field(default_factory=list)
    query_intent_ids: list[str] = field(default_factory=list)
    section_ids: list[str] = field(default_factory=list)
    owning_stages: list[str] = field(default_factory=list)
    audit_method: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_term_id": self.contract_term_id,
            "requirement_id": self.requirement_id,
            "thread_ids": list(self.thread_ids),
            "query_intent_ids": list(self.query_intent_ids),
            "section_ids": list(self.section_ids),
            "owning_stages": list(self.owning_stages),
            "audit_method": self.audit_method,
        }

    @classmethod
    def from_dict(cls, d: Any) -> "CoverageBinding":
        if not isinstance(d, dict):
            raise SchemaError("coverage binding must be an object")
        return cls(
            contract_term_id=_as_opt_str(d.get("contract_term_id")) or "",
            requirement_id=_as_opt_str(d.get("requirement_id")),
            thread_ids=_as_str_list(d.get("thread_ids")),
            query_intent_ids=_as_str_list(d.get("query_intent_ids")),
            section_ids=_as_str_list(d.get("section_ids")),
            owning_stages=[s for s in _as_str_list(d.get("owning_stages")) if s in STAGES],
            audit_method=_as_opt_str(d.get("audit_method")) or "",
        )


@dataclass
class BudgetEnvelope:
    mandatory_lane_count: int = 0
    max_parallelism: Optional[int] = None
    max_queries: Optional[int] = None
    max_rounds: Optional[int] = None
    overflow_policy: str = "expand"

    def to_dict(self) -> dict[str, Any]:
        return {
            "mandatory_lane_count": self.mandatory_lane_count,
            "max_parallelism": self.max_parallelism,
            "max_queries": self.max_queries,
            "max_rounds": self.max_rounds,
            "overflow_policy": self.overflow_policy,
        }

    @classmethod
    def from_dict(cls, d: Any) -> "BudgetEnvelope":
        if not isinstance(d, dict):
            return cls()
        op = _as_opt_str(d.get("overflow_policy")) or "expand"
        if op not in ("expand", "fail_preflight"):
            op = "expand"
        return cls(
            mandatory_lane_count=_as_opt_int(d.get("mandatory_lane_count")) or 0,
            max_parallelism=_as_opt_int(d.get("max_parallelism")),
            max_queries=_as_opt_int(d.get("max_queries")),
            max_rounds=_as_opt_int(d.get("max_rounds")),
            overflow_policy=op,
        )


@dataclass
class ResearchExecutionPlan:
    plan_version: str = SCHEMA_VERSION
    threads: list[ResearchThread] = field(default_factory=list)
    evidence_needs: list[EvidenceNeed] = field(default_factory=list)
    query_intents: list[QueryIntent] = field(default_factory=list)
    outline_seed: list[OutlineSeed] = field(default_factory=list)
    coverage_matrix: list[CoverageBinding] = field(default_factory=list)
    budget: BudgetEnvelope = field(default_factory=BudgetEnvelope)
    stop_conditions: list[str] = field(default_factory=list)

    def mandatory_query_intents(self) -> list[QueryIntent]:
        return [q for q in self.query_intents if q.mandatory]

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_version": self.plan_version,
            "threads": [t.to_dict() for t in self.threads],
            "evidence_needs": [e.to_dict() for e in self.evidence_needs],
            "query_intents": [q.to_dict() for q in self.query_intents],
            "outline_seed": [o.to_dict() for o in self.outline_seed],
            "coverage_matrix": [c.to_dict() for c in self.coverage_matrix],
            "budget": self.budget.to_dict(),
            "stop_conditions": list(self.stop_conditions),
        }


def plan_from_dict(d: Any) -> ResearchExecutionPlan:
    if not isinstance(d, dict):
        raise SchemaError(f"plan must be an object, got {type(d).__name__}")
    return ResearchExecutionPlan(
        plan_version=_as_opt_str(d.get("plan_version")) or SCHEMA_VERSION,
        threads=[ResearchThread.from_dict(t) for t in (d.get("threads") or []) if isinstance(t, dict)],
        evidence_needs=[EvidenceNeed.from_dict(e) for e in (d.get("evidence_needs") or []) if isinstance(e, dict)],
        query_intents=[QueryIntent.from_dict(q) for q in (d.get("query_intents") or []) if isinstance(q, dict)],
        outline_seed=[OutlineSeed.from_dict(o) for o in (d.get("outline_seed") or []) if isinstance(o, dict)],
        coverage_matrix=[CoverageBinding.from_dict(c) for c in (d.get("coverage_matrix") or []) if isinstance(c, dict)],
        budget=BudgetEnvelope.from_dict(d.get("budget") or {}),
        stop_conditions=_as_str_list(d.get("stop_conditions")),
    )


# ---------------------------------------------------------------------------
# The persisted envelope
# ---------------------------------------------------------------------------

@dataclass
class ClarificationQuestion:
    question_id: str
    prompt: str
    choices: list[str] = field(default_factory=list)
    affected_term_ids: list[str] = field(default_factory=list)
    why_it_matters: str = ""
    answer: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "question_id": self.question_id,
            "prompt": self.prompt,
            "choices": list(self.choices),
            "affected_term_ids": list(self.affected_term_ids),
            "why_it_matters": self.why_it_matters,
            "answer": self.answer,
        }


@dataclass
class ArtifactRevision:
    revision: int
    parent_sha256: Optional[str] = None
    patch: list[dict] = field(default_factory=list)
    actor: str = "compiler"
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "revision": self.revision,
            "parent_sha256": self.parent_sha256,
            "patch": list(self.patch),
            "actor": self.actor,
            "reason": self.reason,
        }


@dataclass
class PlanningGateArtifact:
    """The immutable persisted envelope every downstream stage consumes."""

    run_id: str
    mode: str
    state: str
    original_prompt: str
    contract: ResearchContract
    plan: ResearchExecutionPlan
    artifact_version: str = SCHEMA_VERSION
    created_at: str = ""
    normalized_prompt_language: Optional[str] = None
    clarification_questions: list[ClarificationQuestion] = field(default_factory=list)
    revisions: list[ArtifactRevision] = field(default_factory=list)
    approval_actor: Optional[str] = None
    approval_policy_version: Optional[str] = None
    contract_sha256: str = ""
    plan_sha256: str = ""
    artifact_sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_version": self.artifact_version,
            "run_id": self.run_id,
            "created_at": self.created_at,
            "mode": self.mode,
            "state": self.state,
            "original_prompt": self.original_prompt,
            "normalized_prompt_language": self.normalized_prompt_language,
            "contract": self.contract.to_dict(),
            "plan": self.plan.to_dict(),
            "clarification_questions": [q.to_dict() for q in self.clarification_questions],
            "revisions": [r.to_dict() for r in self.revisions],
            "approval_actor": self.approval_actor,
            "approval_policy_version": self.approval_policy_version,
            "contract_sha256": self.contract_sha256,
            "plan_sha256": self.plan_sha256,
            "artifact_sha256": self.artifact_sha256,
        }

    def recompute_hashes(self) -> "PlanningGateArtifact":
        """Fill in the three SHAs from the canonical bytes (idempotent)."""
        self.contract_sha256 = sha256_of(self.contract.to_dict())
        self.plan_sha256 = sha256_of(self.plan.to_dict())
        envelope = self.to_dict()
        envelope["artifact_sha256"] = ""  # hash excludes itself
        self.artifact_sha256 = sha256_of(envelope)
        return self


# ---------------------------------------------------------------------------
# Canonical serialization + hashing (mirrors research_planner discipline)
# ---------------------------------------------------------------------------

def serialize_canonical(obj: dict[str, Any]) -> str:
    """Canonical JSON: ``sort_keys`` + fixed separators + ``ensure_ascii=False``.

    Byte-for-byte identical construction to
    ``research_planner.serialize_plan_canonical`` so the two share one hashing
    discipline.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_of(obj: dict[str, Any]) -> str:
    """SHA-256 of an object's canonical-JSON bytes."""
    return hashlib.sha256(serialize_canonical(obj).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Span re-anchoring — the quote is authoritative, the offset is not
# ---------------------------------------------------------------------------
#
# The contract compiler is an LLM. Empirically it copies the verbatim `quote`
# for an explicit span correctly, but it CANNOT reliably count characters over a
# multi-hundred-char prompt: its `start`/`end` drift by a few positions, so
# `prompt[start:end] != quote` and the validator raises `span_quote_mismatch` on
# otherwise-correct explicit terms (drb_72: 8 of 8 fatal span errors were pure
# offset drift on quotes that appear verbatim in the prompt).
#
# This mirrors the S0 candidate adapter's own established discipline
# (`candidate_adapter._locate_span`): the trigger PHRASE is the source of truth
# and the offset is RE-DERIVED by locating that phrase verbatim in the prompt —
# an offset is never trusted from an upstream that can't count. Re-anchoring is
# a mechanical, no-invention operation: a span is corrected ONLY when its exact
# `quote` still occurs verbatim in the prompt. A `quote` that is NOT present in
# the prompt (a fabricated/paraphrased span) is left UNTOUCHED, so it stays a
# fatal `span_quote_mismatch` and a hard term built on it is still rejected — the
# no-invention rule (hard ⇒ origin==explicit ⇒ real verbatim span) is preserved.

def _reanchor_span(span: PromptSpan, prompt: str) -> PromptSpan:
    """Return a span whose offsets locate ``span.quote`` verbatim in ``prompt``.

    If the span already matches (``prompt[start:end] == quote``) it is returned
    unchanged. Otherwise, if ``quote`` occurs verbatim in the prompt (exact, then
    case-insensitive with the ACTUAL prompt substring kept as the quote so
    quote-equality holds), the offsets are corrected to that occurrence. If the
    quote cannot be located at all, the span is returned unchanged (it will fail
    validation — a fabricated span is never silently accepted).
    """
    if not prompt or not span.quote:
        return span
    if span.matches_prompt(prompt):
        return span
    idx = prompt.find(span.quote)
    if idx != -1:
        return PromptSpan(idx, idx + len(span.quote), span.quote)
    low = prompt.lower().find(span.quote.lower())
    if low != -1:
        actual = prompt[low:low + len(span.quote)]
        return PromptSpan(low, low + len(actual), actual)
    return span


def reanchor_contract_spans(contract: ResearchContract, prompt: str) -> ResearchContract:
    """Re-derive every term's span offsets from its verbatim quote (in place).

    Called by the compiler after parsing and BEFORE validation so the LLM's
    unreliable character offsets never trip ``span_quote_mismatch`` on a quote
    that is genuinely present in the prompt. A quote absent from the prompt is
    left as-is and still fails validation — this only corrects arithmetic, it
    never invents support for a term. Returns the same contract for chaining.
    """
    prompt = prompt or ""
    for term in contract.all_terms():
        if term.spans:
            term.spans = [_reanchor_span(sp, prompt) for sp in term.spans]
    return contract


# ---------------------------------------------------------------------------
# Deterministic validators — the mechanical no-invention gate
# ---------------------------------------------------------------------------

@dataclass
class ValidationError:
    """One machine-readable validation failure (fed to the correction retry)."""

    code: str
    message: str
    term_id: Optional[str] = None
    span: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "term_id": self.term_id,
            "span": self.span,
        }


def validate_contract(contract: ResearchContract, prompt: str) -> list[ValidationError]:
    """Deterministic contract validation. Returns a (possibly empty) error list.

    NEVER raises for a correctness problem — it accumulates structured errors so
    the compiler can run one bounded correction retry, and so tests can assert on
    specific codes. The checks (design §3 / §4):

    * ``hard_not_explicit`` — a ``force==hard`` term whose ``origin`` is not
      explicit/user_answer/user_edit (the no-invention invariant).
    * ``explicit_without_span`` — an ``origin==explicit`` term with no span.
    * ``span_quote_mismatch`` — an explicit term's span where
      ``prompt[start:end] != quote``.
    * ``bad_origin`` / ``bad_force`` / ``bad_stage`` — out-of-vocab enum leaked in.
    * ``inferred_not_disclosed`` — an inferred/policy_default term with a value
      but no matching :class:`Assumption` (every inferred term must be disclosed).
    * ``duplicate_term_id`` — two terms share a ``term_id`` (IDs must be stable
      and unique for downstream projection).
    """
    errors: list[ValidationError] = []
    prompt = prompt or ""

    seen_ids: set[str] = set()
    disclosed: set[str] = set()
    for a in contract.assumptions:
        disclosed.update(a.affected_term_ids)

    for term in contract.all_terms():
        tid = term.term_id or "<anon>"

        if term.term_id:
            if term.term_id in seen_ids:
                errors.append(ValidationError(
                    "duplicate_term_id",
                    f"term_id {term.term_id!r} appears more than once",
                    term_id=term.term_id,
                ))
            seen_ids.add(term.term_id)

        if term.origin not in ORIGINS:
            errors.append(ValidationError(
                "bad_origin", f"unknown origin {term.origin!r}", term_id=tid))
        if term.force not in FORCES:
            errors.append(ValidationError(
                "bad_force", f"unknown force {term.force!r}", term_id=tid))
        for st in term.enforcement_stages:
            if st not in STAGES:
                errors.append(ValidationError(
                    "bad_stage", f"unknown enforcement stage {st!r}", term_id=tid))

        # -- generic-IR enum + operator/value schema (Phase B) --
        if term.operator and term.operator not in OPERATORS:
            errors.append(ValidationError(
                "bad_operator", f"unknown operator {term.operator!r}", term_id=tid))
        if term.stage_owner and term.stage_owner not in STAGE_OWNERS:
            errors.append(ValidationError(
                "bad_stage_owner",
                f"unknown stage_owner {term.stage_owner!r}", term_id=tid))
        if (
            term.normalization_status
            and term.normalization_status not in NORMALIZATION_STATUSES
        ):
            errors.append(ValidationError(
                "bad_normalization_status",
                f"unknown normalization_status {term.normalization_status!r}",
                term_id=tid))
        # IN / NOT_IN require a non-empty value_set; the scalar operators require a
        # value. A hard set/bound with an empty payload can never be enforced.
        if term.operator in (OP_IN, OP_NOT_IN) and not term.value_set:
            errors.append(ValidationError(
                "operator_value_mismatch",
                f"term {tid!r} operator={term.operator} requires a non-empty value_set",
                term_id=tid))
        if (
            term.operator in (OP_GTE, OP_LTE, OP_EQ, OP_BETWEEN)
            and term.value in (None, "", [], {})
        ):
            errors.append(ValidationError(
                "operator_value_mismatch",
                f"term {tid!r} operator={term.operator} requires a value",
                term_id=tid))

        # THE no-invention invariant: hard requires an authoritative origin.
        if term.is_hard() and term.origin not in HARD_ELIGIBLE_ORIGINS:
            errors.append(ValidationError(
                "hard_not_explicit",
                f"term {tid!r} is force=hard but origin={term.origin!r}; a hard "
                f"term requires origin in {sorted(HARD_ELIGIBLE_ORIGINS)}",
                term_id=tid,
            ))

        # explicit ⇒ at least one span, and every span must quote-match.
        if term.origin == ORIGIN_EXPLICIT:
            if not term.spans:
                errors.append(ValidationError(
                    "explicit_without_span",
                    f"term {tid!r} is origin=explicit but carries no prompt span",
                    term_id=tid,
                ))
            for sp in term.spans:
                if not sp.matches_prompt(prompt):
                    errors.append(ValidationError(
                        "span_quote_mismatch",
                        f"term {tid!r} span quote != prompt[{sp.start}:{sp.end}]",
                        term_id=tid,
                        span=sp.to_dict(),
                    ))

        # No unanchored EXPLICIT-origin hard term: an origin==explicit hard term
        # MUST carry at least one prompt span (the span checks above already fire
        # for the missing/mismatched span; this makes the "hard needs an anchor"
        # rule explicit for the non-explicit hard-eligible origins too — a
        # user_answer/user_edit hard term is allowed WITHOUT a span, but an
        # explicit hard term without a span is a no-invention violation).
        if term.is_hard() and term.origin == ORIGIN_EXPLICIT and not term.spans:
            errors.append(ValidationError(
                "hard_explicit_unanchored",
                f"hard explicit term {tid!r} has no prompt span to anchor it",
                term_id=tid,
            ))

        # inferred/policy_default with a real value must be disclosed.
        if (
            term.origin in DISCLOSURE_ORIGINS
            and term.value not in (None, "", [], {})
            and term.term_id
            and term.term_id not in disclosed
        ):
            errors.append(ValidationError(
                "inferred_not_disclosed",
                f"term {tid!r} is origin={term.origin!r} with a value but has no "
                f"assumption record disclosing it",
                term_id=tid,
            ))

    return errors


def validate_monotonicity(
    contract: ResearchContract, candidate_ids: "set[str] | frozenset[str]"
) -> list[ValidationError]:
    """MONOTONICITY invariant (Phase B core): every deterministic explicit
    candidate SURVIVED into the contract.

    ``candidate_ids`` is the set of stable candidate term_ids the deterministic
    core authored (see ``candidate_adapter.candidate_term_id``). If any one is
    absent from ``contract.all_terms()``, the LLM (or a merge bug) dropped a
    stated constraint — the exact inversion defect. This NEVER mutates; the
    compiler runs it after the monotonic merge and treats a violation as fatal
    (the deterministic term is then force-reinstated, and this is a belt).
    """
    present = {t.term_id for t in contract.all_terms() if t.term_id}
    errors: list[ValidationError] = []
    for cid in sorted(candidate_ids):
        if cid and cid not in present:
            errors.append(ValidationError(
                "candidate_dropped",
                f"deterministic explicit candidate {cid!r} did not survive into "
                f"the contract (monotonic-lossless authority violated)",
                term_id=cid,
            ))
    return errors


def validate_capabilities(contract: ResearchContract) -> list[ValidationError]:
    """Phase D STUB: every hard term should name a registered executable
    capability (``capability_id``) before it can be pinned as executable.

    NOT enforced here (Phase D wires the capability registry + receipts). This
    returns [] today; the compiler calls it so the seam exists and the honest
    ``blocked_unsupported`` state can be derived once capabilities are registered.
    TODO(Phase D): resolve capability_id against a registry and require a
    pass-receipt path; a hard term with no capability → blocked_unsupported.
    """
    return []  # TODO(Phase D): capability-binding enforcement


def validate_plan(
    plan: ResearchExecutionPlan, contract: ResearchContract
) -> list[ValidationError]:
    """Deterministic plan validation (design §4 plan-validation).

    * ``requirement_without_intent`` — a required, evidence-bearing coverage
      requirement with no mandatory query intent referencing it (via a thread).
    * ``mandatory_lane_truncatable`` — ``budget.max_queries`` below
      ``mandatory_lane_count`` under an ``expand``-or-``fail`` overflow policy is
      only OK if the policy is not silent truncation; a smaller cap with a bad
      policy is flagged.
    * ``binding_term_unowned`` — a hard contract term with no coverage binding.
    """
    errors: list[ValidationError] = []

    intent_ids_by_thread: dict[str, list[QueryIntent]] = {}
    for qi in plan.query_intents:
        intent_ids_by_thread.setdefault(qi.thread_id, []).append(qi)

    covered_req_ids: set[str] = set()
    for th in plan.threads:
        has_mandatory_intent = any(
            qi.mandatory for qi in intent_ids_by_thread.get(th.thread_id, [])
        )
        if has_mandatory_intent:
            covered_req_ids.update(th.coverage_requirement_ids)

    for cr in contract.coverage:
        if not cr.required:
            continue
        if cr.requirement_id and cr.requirement_id not in covered_req_ids:
            errors.append(ValidationError(
                "requirement_without_intent",
                f"required coverage {cr.requirement_id!r} has no mandatory query "
                f"intent (via a thread)",
                term_id=cr.requirement_id,
            ))

    bound_term_ids = {cb.contract_term_id for cb in plan.coverage_matrix}
    for term in contract.hard_terms():
        if term.term_id and term.term_id not in bound_term_ids:
            errors.append(ValidationError(
                "binding_term_unowned",
                f"hard term {term.term_id!r} has no coverage binding / owning stage",
                term_id=term.term_id,
            ))

    b = plan.budget
    mandatory = sum(1 for qi in plan.query_intents if qi.mandatory)
    if b.mandatory_lane_count and mandatory and b.mandatory_lane_count != mandatory:
        # advisory: recorded lane count should match the actual mandatory intents
        errors.append(ValidationError(
            "mandatory_lane_count_mismatch",
            f"budget.mandatory_lane_count={b.mandatory_lane_count} but "
            f"{mandatory} mandatory query intents exist",
        ))
    if (
        b.max_queries is not None
        and b.mandatory_lane_count
        and b.max_queries < b.mandatory_lane_count
        and b.overflow_policy != "fail_preflight"
    ):
        errors.append(ValidationError(
            "mandatory_lane_truncatable",
            f"max_queries={b.max_queries} < mandatory_lane_count="
            f"{b.mandatory_lane_count} under overflow_policy={b.overflow_policy!r}; "
            f"a mandatory lane could be silently truncated",
        ))

    return errors
