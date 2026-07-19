"""Field-agnostic research planner (I-meta-005 Phase 1, #985).

Closes parent-plan gaps #1 (decomposition), #2 (planning), #8 (report
structure), #10 (decision seed). Behind `PG_USE_RESEARCH_PLANNER`; OFF is
byte-identical to the legacy clause-split + clinical-PICO + `_ALLOWED_SECTIONS`
path (this module is simply not invoked when off).

DESIGN (brief §2.1):
- `ResearchFrame` — a generalized PICO that carries NO clinical fields:
  entities / relations / metrics / comparators / constraints + a `claim_type`
  from a field-invariant enum. A housing, physics, or trade-policy question
  produces a usable frame; nothing is clinical-specific.
- `plan_research(question, *, planner_llm)` makes ONE normal Writer call (plus
  AT MOST ONE bounded retry when the honest sub-query count is short). The
  Writer is an INJECTED callable `Callable[[str], str]`, so this module never
  constructs an `OpenRouterClient` or a live HTTP client — build + smoke are
  spend-free. Production threads the existing Writer through the callable.
- Strict JSON parse. Malformed -> raise `PlannerError` (LAW II). There is NO
  silent fallback to the clause-splitter; the dual path lives at the caller.
- Sub-query count is HONEST (brief §2.1):
  * UPPER bound `DEFAULT_MAX_SUBQUERIES` (40): merge/truncate deterministically.
  * LOWER bound is a FAIL-LOUD retry, not deterministic padding: when fewer
    than `MIN_SUBQUERIES` facets come back, retry ONCE asking for more. If a
    genuinely narrow question still yields fewer, ACCEPT the honest smaller
    count and log — never fabricate facets to hit a target.
- `ResearchFrame.to_anchor_protocol()` exposes the frame's own tokens as an
  anchor-protocol dict so planner sub-queries validate against the frame
  (brief §2.4, validator adapter).
- `serialize_plan_canonical()` emits canonical JSON (sort_keys, fixed
  separators) so the caller can SHA-pin the `ResearchPlan` BEFORE retrieval
  (gap #19 extension, brief §2.1).

The archetype tag vocabulary is owned by the generator
(`multi_section_generator._SECTION_ARCHETYPES`); the planner imports it so the
two halves of the dual path share ONE source of truth and the planner stays
field-agnostic (no clinical literal as a control value).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from src.polaris_graph.generator.multi_section_generator import (
    SECTION_ARCHETYPES,
)
from src.polaris_graph.settings import resolve

logger = logging.getLogger("polaris_graph.research_planner")


# Field-invariant claim taxonomy. NOT clinical — these classify the SHAPE of
# the question's answer (does it report measured effects, compare policies,
# forecast, explain a mechanism, or describe a landscape).
CLAIM_TYPES: frozenset[str] = frozenset({
    "empirical",
    "policy-comparison",
    "forecast",
    "mechanism",
    "descriptive",
})

# I-meta-005 Phase 6 (#990, Codex ruling A1): field-invariant ANSWER-TYPE — the
# explicit domain-category signal `claim_type` could not carry (empirical is shared
# by physics/battery/epidemiology). It drives ADVISORY section-writing-guidance
# selection ONLY (the `_registry.yaml` `by_answer_type` map), never routing/
# archetypes/verification. Default "general" = no domain-specific advisory. An
# unknown value fails SOFT to "general" (advisory enrichment must never abort a
# run), UNLIKE the strict `claim_type` contract.
ANSWER_TYPES: frozenset[str] = frozenset({
    "clinical",
    "policy",
    "economics",
    "legal",
    "materials",
    "engineering",
    "environmental",
    "social-science",
    "general",
})
_DEFAULT_ANSWER_TYPE = "general"


# ── I-meta-005 Phase 2 (#986): field-agnostic EVIDENCE-NEED taxonomy ─────────
# A field-INVARIANT enum (10 needs, brief §2.1) that declares WHAT KINDS of
# evidence the question needs — NOT a domain. The planner emits these on the
# frame; source discovery (the need-type registry) routes adapters off these,
# never off a domain enum. `company_filings` keeps the legacy
# due_diligence/sec_edgar capability reachable on-mode; standards/datasets/
# news_press cover engineering bodies / official data portals / institutional
# statements so "any field, any region" reaches the right issuer, never a bare
# open_web fallback.
EVIDENCE_NEEDS: frozenset[str] = frozenset({
    "primary_literature",
    "regulatory",
    "legal",
    "statistical",
    "standards",
    "datasets",
    "news_press",
    "company_filings",
    "code",
    "open_web",
})

# Normalized JURISDICTION code SHAPE (brief §2.1b). ISO-3166 alpha-2 (e.g.
# "CA", "JP") plus the two pseudo-codes "EU" and "INTL". The PARSER validates
# SHAPE only; the scope LOADER validates MEMBERSHIP non-fatally (a valid-shape
# code absent from `jurisdiction_scopes.yaml` logs + yields no scope and is
# NEVER parser-fatal). "EU" matches `^[A-Z]{2}$`; "INTL" is the only 4-letter
# member, allowed explicitly.
_JURISDICTION_ALPHA2_RE = re.compile(r"^[A-Z]{2}$")
_JURISDICTION_EXTRA_CODES: frozenset[str] = frozenset({"EU", "INTL"})


class MalformedPlanError(RuntimeError):
    """Raised when the planner emits a STRUCTURALLY malformed need/jurisdiction
    frame (I-meta-005 Phase 2, brief §2.1/2.1b): an `evidence_needs` value not
    in `EVIDENCE_NEEDS`, or a `jurisdictions` value whose SHAPE is not a valid
    code (`^[A-Z]{2}$` / "EU" / "INTL").

    Distinct from `PlannerError` (unusable LLM output) AND from a fail-OPEN
    adapter/network error: a malformed plan FAILS LOUD before ANY live
    discovery and is re-raised PAST the fail-open dispatch wrapper at the live
    seam — it NEVER silently degrades to core Serper/S2 (brief §2.4 P2-note-1).
    A valid-shape-but-unknown jurisdiction code is NOT malformed (membership is
    a non-fatal scope-loader concern); only a bad SHAPE raises here.
    """


def is_valid_jurisdiction_shape(code: str) -> bool:
    """True iff `code` is a SHAPE-valid normalized jurisdiction code
    (`^[A-Z]{2}$` or "EU"/"INTL"). MEMBERSHIP (presence in the data file) is a
    separate, non-fatal scope-loader concern."""
    if not isinstance(code, str):
        return False
    token = code.strip()
    if not token:
        return False
    if token in _JURISDICTION_EXTRA_CODES:
        return True
    return bool(_JURISDICTION_ALPHA2_RE.match(token))


def validate_evidence_needs(values: list[str]) -> list[str]:
    """Validate + normalize `evidence_needs` (brief §2.1). Each value must be in
    `EVIDENCE_NEEDS` (case-insensitive); an unknown value FAILS LOUD with
    `MalformedPlanError` (NOT a silent fallback — only an EMPTY list is the safe
    older-plan fallback, handled by the router). Returns the normalized,
    order-preserving, deduped lowercased list."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        token = str(raw).strip().lower()
        if not token:
            continue
        if token not in EVIDENCE_NEEDS:
            raise MalformedPlanError(
                f"malformed evidence_need={raw!r}; allowed={sorted(EVIDENCE_NEEDS)}"
            )
        if token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def validate_jurisdiction_shapes(values: list[str]) -> list[str]:
    """Validate + normalize `jurisdictions` SHAPE (brief §2.1b). Each value must
    be a SHAPE-valid normalized code; a malformed SHAPE FAILS LOUD with
    `MalformedPlanError`. A valid-shape-but-unknown code is KEPT (membership is
    checked non-fatally later by the scope loader). Returns the normalized,
    order-preserving, deduped UPPERCASED list."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        token = str(raw).strip().upper()
        if not token:
            continue
        if not is_valid_jurisdiction_shape(token):
            raise MalformedPlanError(
                f"malformed jurisdiction code={raw!r}; expected ISO-3166 "
                f"alpha-2 / 'EU' / 'INTL'"
            )
        if token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out

# UPPER bound on emitted sub-queries (brief §2.1). >40 is merged/truncated
# deterministically. The fetch cap (`PG_SWEEP_FETCH_CAP`) bounds FETCHED URLs
# downstream; this bounds the per-question query fan-out.
# F23 (I-arch-004 A3): env-overridable for slate tuning; default keeps the
# historical literal 40 so an unset env is byte-identical. This is an UPPER
# merge/truncate bound, NOT a §-1.3 breadth-target hard-filter — raising it
# only loosens the fan-out ceiling; it never drops a source to hit a number.
DEFAULT_MAX_SUBQUERIES = int(resolve("PG_PLANNER_MAX_SUBQUERIES"))
# LOWER bound that triggers ONE fail-loud retry (brief §2.1). A genuinely
# narrow question may legitimately accept fewer after the retry; we never pad.
# F23: env-overridable; default keeps the historical literal 12 (byte-identical
# when unset). This is a fail-loud retry trigger, never deterministic padding.
MIN_SUBQUERIES = int(resolve("PG_PLANNER_MIN_SUBQUERIES"))


class PlannerError(RuntimeError):
    """Raised when the planner LLM emits unusable output (LAW II: fail loud,
    no silent fallback to the clause-splitter)."""


@dataclass
class ResearchFrame:
    """Generalized, field-invariant question frame (brief §2.1).

    Carries NO clinical-specific fields. `claim_type` is one of `CLAIM_TYPES`.
    """

    entities: list[str] = field(default_factory=list)
    relations: list[str] = field(default_factory=list)
    metrics: list[str] = field(default_factory=list)
    comparators: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    claim_type: str = "descriptive"
    # I-meta-005 Phase 2 (#986): additive, default [] -> OFF unaffected.
    # `evidence_needs` = the field-agnostic EvidenceNeed values the question
    # needs (brief §2.1). `jurisdictions` = normalized codes for scope routing
    # (brief §2.1b). Both validated at parse time (malformed value/SHAPE ->
    # MalformedPlanError); a valid-shape-unknown jurisdiction is kept (non-fatal
    # membership). Empty `evidence_needs` -> the router's safe generic fallback.
    evidence_needs: list[str] = field(default_factory=list)
    jurisdictions: list[str] = field(default_factory=list)
    # I-meta-005 Phase 6 (#990, Codex ruling A1): explicit domain-category for
    # ADVISORY section-prompt selection. Default "general" -> no domain advisory
    # (OFF/legacy plans without the field deserialize to "general"). NEVER a
    # routing/archetype/verification control.
    answer_type: str = _DEFAULT_ANSWER_TYPE

    def to_anchor_protocol(self, research_question: str) -> dict[str, Any]:
        """Produce an anchor-protocol dict for `validate_amplified_queries`
        (brief §2.4). Bundles the verbatim research_question with the frame's
        own tokens under the additive keys `_build_anchor_tokens` merges. This
        lets planner sub-queries validate against the frame's entities /
        metrics / comparators rather than against clinical PICO fields.
        """
        return {
            "research_question": research_question or "",
            "entities": list(self.entities),
            "relations": list(self.relations),
            "metrics": list(self.metrics),
            "comparators": list(self.comparators),
            "constraints": list(self.constraints),
        }


@dataclass
class SectionOutlineItem:
    """One pre-retrieval outline section (brief §2.1).

    Holds an archetype TAG (field-invariant, from `SECTION_ARCHETYPES`), a
    question-specific TITLE, and a per-section evidence TARGET. It carries NO
    evidence IDs — no evidence exists yet at planning time; the generator's
    on-mode handoff assigns `ev_ids` post-retrieval (brief §2.5).

    I-meta-005 Phase 3 (#987): `sub_query_indices` declares WHICH of the plan's
    `sub_queries` (by index) make THIS section complete — the per-section facet
    mapping the plan-sufficiency gate reads (brief §2.2). Additive, default `[]`
    so OFF / direct construction is inert; on-mode `plan_research` validates
    (≥1 in-range index + evidence_target ≥ 1 + whole-plan facet union) and
    raises `MalformedPlanError` for any empty/stale/orphaned mapping.
    """

    archetype: str
    title: str
    evidence_target: int = 0
    sub_query_indices: list[int] = field(default_factory=list)


@dataclass
class ResearchPlan:
    """The full pre-registered plan (brief §2.1): frame + faceted sub-queries
    + archetype outline. Canonically serialized + SHA-pinned before retrieval.
    """

    research_question: str
    frame: ResearchFrame
    sub_queries: list[str] = field(default_factory=list)
    outline: list[SectionOutlineItem] = field(default_factory=list)

    def to_canonical_dict(self) -> dict[str, Any]:
        """Plain-dict projection for canonical serialization + SHA pinning."""
        return {
            "research_question": self.research_question,
            "frame": {
                "entities": list(self.frame.entities),
                "relations": list(self.frame.relations),
                "metrics": list(self.frame.metrics),
                "comparators": list(self.frame.comparators),
                "constraints": list(self.frame.constraints),
                "claim_type": self.frame.claim_type,
                # I-meta-005 Phase 2 (#986): additive frame fields included in
                # the canonical projection so the SHA-pinned plan covers the
                # declared evidence-needs + jurisdictions.
                "evidence_needs": list(self.frame.evidence_needs),
                "jurisdictions": list(self.frame.jurisdictions),
                # I-meta-005 Phase 6 (#990): answer_type in the SHA-pinned plan so
                # the advisory-selection signal is reproducible from the artifact.
                "answer_type": self.frame.answer_type,
            },
            "sub_queries": list(self.sub_queries),
            "outline": [
                {
                    "archetype": item.archetype,
                    "title": item.title,
                    "evidence_target": item.evidence_target,
                    # I-meta-005 Phase 3 (#987): the per-section facet mapping is
                    # part of the SHA-pinned plan so the sufficiency contract is
                    # reproducible from the pinned artifact (gap #19 audit trail).
                    "sub_query_indices": list(item.sub_query_indices),
                }
                for item in self.outline
            ],
        }


def serialize_plan_canonical(plan: ResearchPlan) -> str:
    """Serialize a `ResearchPlan` as CANONICAL JSON (brief §2.1): `sort_keys`
    + fixed separators so the bytes are reproducible. The caller hashes these
    bytes to SHA-pin the plan before retrieval (gap #19 extension).
    """
    return json.dumps(
        plan.to_canonical_dict(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def plan_sha256(plan: ResearchPlan) -> str:
    """SHA-256 of the canonical-JSON bytes of `plan`."""
    canonical = serialize_plan_canonical(plan)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _strip_code_fence(raw: str) -> str:
    """Remove an optional ```json ... ``` fence and return the inner JSON
    object substring (first `{` .. last `}`)."""
    stripped = (raw or "").strip()
    if stripped.startswith("```"):
        # Drop the opening fence line and a trailing fence if present.
        first_newline = stripped.find("\n")
        if first_newline != -1:
            stripped = stripped[first_newline + 1:]
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[: -3]
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        return ""
    return stripped[start:end + 1]


def _as_str_list(value: Any) -> list[str]:
    """Coerce a JSON value into a clean list[str] (drop empties, dedup
    case-insensitively, preserve order). A non-list value coerces to []
    (lenient — used for the soft frame fields)."""
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, (str, int, float)):
            continue
        text = str(item).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _as_str_list_strict(value: Any, field_name: str) -> list[str]:
    """Coerce a JSON value into list[str] for the HARD-VALIDATED Phase-2 fields
    (`evidence_needs`, `jurisdictions`). Distinguishes ABSENT from MALFORMED
    (Codex diff-gate P1):
      - absent (None / key missing) → [] (legacy/OFF plan; the router's safe
        empty-needs fallback applies). NOT an error.
      - a LIST → coerced like `_as_str_list` (per-element membership/shape is
        then validated downstream, which fails loud on a bad element).
      - any OTHER present shape (a scalar str/int, a dict, a bool) → FAIL LOUD
        with `MalformedPlanError`. A scalar `"evidence_needs": "totally_made_up"`
        must NOT silently coerce to [] and slip into the safe fallback.
    """
    if value is None:
        return []
    if not isinstance(value, list):
        raise MalformedPlanError(
            f"planner emitted non-list {field_name}={value!r}; "
            f"{field_name} must be a JSON array of strings (or absent)"
        )
    return _as_str_list(value)


def _parse_frame(obj: dict[str, Any]) -> ResearchFrame:
    """Build a `ResearchFrame` from the parsed JSON. Unknown `claim_type`
    raises (LAW II) — the planner must commit to a field-invariant claim
    shape, not emit a clinical or free-text category."""
    raw_frame = obj.get("frame")
    if not isinstance(raw_frame, dict):
        raise PlannerError("planner output has no object-valued 'frame'")
    claim_type = str(raw_frame.get("claim_type", "")).strip().lower()
    if claim_type not in CLAIM_TYPES:
        raise PlannerError(
            f"planner emitted unknown claim_type={claim_type!r}; "
            f"allowed={sorted(CLAIM_TYPES)}"
        )
    # I-meta-005 Phase 2 (#986): additive evidence_needs + jurisdictions.
    # Validated HERE at parse time (brief §2.1/2.1b): a malformed evidence_need
    # value OR a malformed jurisdiction SHAPE raises MalformedPlanError (fail
    # loud, NOT a silent fallback). A missing/empty list is fine (older legacy
    # plan / OFF) — only the router treats empty evidence_needs as the safe
    # generic fallback. A valid-shape-unknown jurisdiction is kept (membership
    # is a non-fatal scope-loader concern).
    evidence_needs = validate_evidence_needs(
        _as_str_list_strict(raw_frame.get("evidence_needs"), "evidence_needs")
    )
    jurisdictions = validate_jurisdiction_shapes(
        _as_str_list_strict(raw_frame.get("jurisdictions"), "jurisdictions")
    )
    # I-meta-005 Phase 6 (#990, Codex ruling A1): answer_type drives ADVISORY
    # prompt selection only, so an unknown/absent value fails SOFT to "general"
    # (never aborts a run) — UNLIKE the strict claim_type contract above.
    answer_type = str(raw_frame.get("answer_type", "")).strip().lower()
    if answer_type not in ANSWER_TYPES:
        answer_type = _DEFAULT_ANSWER_TYPE
    return ResearchFrame(
        entities=_as_str_list(raw_frame.get("entities")),
        relations=_as_str_list(raw_frame.get("relations")),
        metrics=_as_str_list(raw_frame.get("metrics")),
        comparators=_as_str_list(raw_frame.get("comparators")),
        constraints=_as_str_list(raw_frame.get("constraints")),
        claim_type=claim_type,
        evidence_needs=evidence_needs,
        jurisdictions=jurisdictions,
        answer_type=answer_type,
    )


def _parse_sub_queries(obj: dict[str, Any]) -> list[str]:
    """Extract + dedup the faceted sub-queries. Empty list raises (LAW II:
    a plan with no facets is unusable)."""
    sub_queries = _as_str_list(obj.get("sub_queries"))
    if not sub_queries:
        raise PlannerError("planner output has no usable 'sub_queries'")
    return sub_queries


def _parse_outline(obj: dict[str, Any]) -> list[SectionOutlineItem]:
    """Extract the archetype-tagged outline. Each item validates its TAG
    against `SECTION_ARCHETYPES`; off-tag items are dropped. An empty outline
    after validation raises (LAW II)."""
    raw_outline = obj.get("outline")
    if not isinstance(raw_outline, list):
        raise PlannerError("planner output has no list-valued 'outline'")
    valid_tags = {tag.lower(): tag for tag in SECTION_ARCHETYPES}
    items: list[SectionOutlineItem] = []
    seen_titles: set[str] = set()
    for entry in raw_outline:
        if not isinstance(entry, dict):
            continue
        tag_raw = str(entry.get("archetype", "")).strip().lower()
        if tag_raw not in valid_tags:
            logger.info(
                "[research_planner] dropped off-tag outline archetype=%r",
                entry.get("archetype"),
            )
            continue
        title = str(entry.get("title", "")).strip()
        if not title:
            continue
        title_key = title.lower()
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)
        target_raw = entry.get("evidence_target", 0)
        try:
            evidence_target = int(target_raw)
        except (TypeError, ValueError):
            evidence_target = 0
        # I-meta-005 Phase 3 (#987): parse the per-section facet mapping. SHAPE
        # only here (coerce int-like entries, drop non-ints); the FAIL-CLOSED
        # range/union validation runs in `plan_research` AFTER the sub_queries
        # list is FINAL (post-truncation), so a parse-time-valid index that goes
        # stale is still caught. Absent/empty -> [] (inert off-mode).
        sub_query_indices: list[int] = []
        for raw_idx in entry.get("sub_query_indices", []) or []:
            try:
                sub_query_indices.append(int(raw_idx))
            except (TypeError, ValueError):
                continue
        items.append(SectionOutlineItem(
            archetype=valid_tags[tag_raw],
            title=title,
            evidence_target=max(0, evidence_target),
            sub_query_indices=sub_query_indices,
        ))
    if not items:
        raise PlannerError(
            "planner outline had no entries with a valid archetype tag"
        )
    return items


def _parse_plan(raw: str, research_question: str) -> ResearchPlan:
    """Strict-parse one planner JSON response into a `ResearchPlan`. Any
    structural failure raises `PlannerError` (LAW II)."""
    payload = _strip_code_fence(raw)
    if not payload:
        raise PlannerError("planner returned no JSON object")
    try:
        obj = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise PlannerError(f"planner JSON decode failed: {exc}") from exc
    if not isinstance(obj, dict):
        raise PlannerError("planner JSON root is not an object")
    frame = _parse_frame(obj)
    sub_queries = _parse_sub_queries(obj)
    outline = _parse_outline(obj)
    return ResearchPlan(
        research_question=research_question,
        frame=frame,
        sub_queries=sub_queries,
        outline=outline,
    )


def _merge_truncate_subqueries(
    sub_queries: list[str],
    *,
    max_subqueries: int,
) -> list[str]:
    """UPPER-bound enforcement (brief §2.1): dedup (already done upstream) and
    deterministically truncate to `max_subqueries`, preserving order."""
    if len(sub_queries) <= max_subqueries:
        return list(sub_queries)
    logger.info(
        "[research_planner] truncating %d sub-queries to upper bound %d",
        len(sub_queries), max_subqueries,
    )
    return list(sub_queries[:max_subqueries])


def _build_prompt(question: str, *, more_facets: bool, min_subqueries: int) -> str:
    """Build the planner prompt. `more_facets=True` is the lower-bound retry
    variant that asks for additional facets. Field-agnostic: the prompt names
    NO domain and NO clinical concept; it asks for a generalized frame +
    facets + archetype outline."""
    archetype_list = ", ".join(SECTION_ARCHETYPES)
    claim_type_list = ", ".join(sorted(CLAIM_TYPES))
    evidence_need_list = ", ".join(sorted(EVIDENCE_NEEDS))
    answer_type_list = ", ".join(sorted(ANSWER_TYPES))
    base = (
        "You are a field-agnostic research planner. Decompose the research "
        "question into a structured plan. The question may be from ANY field "
        "(science, policy, economics, engineering, medicine, history, ...). "
        "Do NOT assume a clinical or any single domain.\n\n"
        f"RESEARCH QUESTION:\n{question}\n\n"
        "Return ONE JSON object with exactly these keys:\n"
        '  "frame": {\n'
        '     "entities":   [the key actors / objects / subjects],\n'
        '     "relations":  [the relationships / actions being studied],\n'
        '     "metrics":    [the quantities / outcomes / measures of interest],\n'
        '     "comparators":[the alternatives / baselines / counterfactuals],\n'
        '     "constraints":[scope limits: population, jurisdiction, timeframe, setting],\n'
        f'     "claim_type": one of [{claim_type_list}],\n'
        '     "evidence_needs": [the KINDS of evidence this question needs — '
        f"choose from: {evidence_need_list}; pick every kind the question "
        "genuinely requires, e.g. a regulatory question needs 'regulatory' "
        "(and likely 'legal'/'statistical'); a software question needs 'code'; "
        "a company question needs 'company_filings'; an engineering-standards "
        "question needs 'standards'; leave EMPTY only if truly generic],\n"
        '     "jurisdictions": [NORMALIZED codes for any country/region the '
        "question is scoped to — ISO-3166 alpha-2 (e.g. \"US\",\"CA\",\"GB\","
        "\"JP\",\"AU\") or \"EU\"/\"INTL\"; EMPTY if the question is not "
        "jurisdiction-specific. Use the CODE, never a country name],\n"
        f'     "answer_type": one of [{answer_type_list}] — the SUBJECT DOMAIN of '
        "the answer, used ONLY to pick domain-appropriate writing guidance (e.g. "
        "\"clinical\" for a medical/drug/trial question; \"economics\" for a "
        "macro/finance question; \"materials\" for a battery/chemistry question; "
        "\"general\" when no single domain dominates). Default to \"general\" if "
        "unsure\n"
        "  },\n"
        '  "sub_queries": [faceted search queries, each a focused phrase that '
        "covers ONE facet of the question — collectively spanning every "
        "entity x metric x comparator x constraint combination the question "
        f"implies; aim for {min_subqueries} or more for a broad question, "
        "fewer only for a genuinely narrow one],\n"
        '  "outline": [section objects, each with:\n'
        '       "archetype": one of the field-invariant tags below,\n'
        '       "title":     a QUESTION-SPECIFIC section heading (not a generic label),\n'
        '       "evidence_target": an integer target number of sources for the section,\n'
        '       "sub_query_indices": [the 0-based indices into "sub_queries" '
        "whose evidence makes THIS section complete — list every sub_query the "
        "section depends on; EVERY sub_query index must appear in some section, "
        "and every section must list at least one]\n"
        "  ]\n\n"
        f"ALLOWED ARCHETYPE TAGS (pick the ones the question needs): {archetype_list}\n\n"
        "RULES:\n"
        "- The titles must be specific to THIS question, not generic category "
        "names. The archetype tag is the field-invariant control; the title "
        "is the human-facing heading.\n"
        "- Choose archetypes that fit the question's claim_type. A decision / "
        "comparison question needs a Decision archetype; an explanatory "
        "question needs a Mechanism archetype; etc.\n"
        "- ALWAYS include EXACTLY ONE \"Integrative\" archetype section LAST "
        "(title e.g. \"Integrative findings\" or a question-specific synthesis "
        "heading). It is the cross-cutting synthesis that ties the report "
        "together. Allocate the BROAD / overview / cross-cutting sub_query "
        "indices to it (the ones that span multiple facets) — it must have a "
        "non-empty sub_query_indices and a reasonable evidence_target so it is "
        "grounded in real evidence, NOT a free-form essay.\n"
        "- Output ONLY the JSON object. No preamble, no markdown fence, no "
        "sign-off.\n"
    )
    if more_facets:
        base += (
            "\nPREVIOUS ATTEMPT returned too few sub_queries. Expand the "
            "faceting: enumerate every entity, every metric, every comparator, "
            "and every constraint as its own focused sub_query so the set is "
            f"comprehensive (at least {min_subqueries} where the question is "
            "broad). Do NOT pad with near-duplicates — add genuinely distinct "
            "facets.\n"
        )
    return base


def plan_research(
    question: str,
    *,
    planner_llm: Callable[[str], str],
    max_subqueries: int = DEFAULT_MAX_SUBQUERIES,
    min_subqueries: int = MIN_SUBQUERIES,
) -> ResearchPlan:
    """Produce a `ResearchPlan` from `question` using ONE Writer call (plus at
    most one bounded lower-bound retry).

    Args:
        question: The raw research question (stored verbatim on the plan).
        planner_llm: Injected Writer callable `prompt -> response_text`. This
            is the ONLY way the planner reaches an LLM; the module never
            constructs an `OpenRouterClient` or a live HTTP client. Tests pass
            a fake; production passes the real Writer.
        max_subqueries: UPPER bound; >this is merged/truncated deterministically.
        min_subqueries: LOWER bound that triggers ONE fail-loud retry.

    Returns:
        A validated `ResearchPlan` (frame + sub_queries + archetype outline).

    Raises:
        ValueError: empty question.
        PlannerError: malformed / unusable planner output (LAW II — no silent
            fallback to the clause-splitter).
    """
    if not question or not question.strip():
        raise ValueError("question must be non-empty.")
    if not callable(planner_llm):
        raise TypeError("planner_llm must be a callable[[str], str].")

    prompt = _build_prompt(
        question, more_facets=False, min_subqueries=min_subqueries,
    )
    raw = planner_llm(prompt)
    plan = _parse_plan(raw, question.strip())
    plan.sub_queries = _merge_truncate_subqueries(
        plan.sub_queries, max_subqueries=max_subqueries,
    )

    # LOWER-bound policy (brief §2.1): a fail-loud retry, NOT padding. If the
    # honest count is short, ask once for more facets. If still short, accept
    # the honest smaller count for a genuinely narrow question and log.
    if len(plan.sub_queries) < min_subqueries:
        logger.info(
            "[research_planner] sub_query count %d < min %d — retrying once "
            "for more facets",
            len(plan.sub_queries), min_subqueries,
        )
        retry_prompt = _build_prompt(
            question, more_facets=True, min_subqueries=min_subqueries,
        )
        retry_raw = planner_llm(retry_prompt)
        retry_plan = _parse_plan(retry_raw, question.strip())
        retry_plan.sub_queries = _merge_truncate_subqueries(
            retry_plan.sub_queries, max_subqueries=max_subqueries,
        )
        # Keep whichever response carried more honest facets.
        if len(retry_plan.sub_queries) > len(plan.sub_queries):
            plan = retry_plan
        if len(plan.sub_queries) < min_subqueries:
            logger.info(
                "[research_planner] accepting honest narrow count %d "
                "(< min %d) after retry — NOT padding",
                len(plan.sub_queries), min_subqueries,
            )
    # I-meta-005 Phase 3 (#987): FAIL-CLOSED post-finalization facet validation.
    # The sub_queries list is now FINAL (post-truncation / retry-winner). Any
    # outline section whose facet mapping is empty / stale / out-of-range, OR a
    # planned sub_query mapped to NO section, makes the plan-sufficiency contract
    # vacuous — so refuse the plan BEFORE any retrieval/generation spend.
    _validate_outline_facet_mapping(plan)
    return plan


def _validate_outline_facet_mapping(plan: ResearchPlan) -> None:
    """FAIL-CLOSED on-mode facet-mapping validation (brief §2.1b / §2.3a),
    run AFTER `plan.sub_queries` is FINAL. Every section MUST:
      * declare ≥1 `sub_query_index`,
      * have every index in range of the FINAL `sub_queries`, AND
      * carry `evidence_target ≥ 1`,
    and the UNION of all sections' `sub_query_indices` MUST equal
    `set(range(len(sub_queries)))` (no orphaned planned facet escapes the gate).
    Any violation raises `MalformedPlanError` (zero spend). Pure / no-network.
    """
    n_sub = len(plan.sub_queries)
    covered: set[int] = set()
    for section in plan.outline:
        indices = list(section.sub_query_indices)
        if not indices:
            raise MalformedPlanError(
                f"outline section {section.title!r} has no sub_query_indices "
                "(every on-mode section must map ≥1 planned sub-query)"
            )
        if int(section.evidence_target) < 1:
            raise MalformedPlanError(
                f"outline section {section.title!r} has evidence_target="
                f"{section.evidence_target} (on-mode requires ≥1)"
            )
        for idx in indices:
            if idx < 0 or idx >= n_sub:
                raise MalformedPlanError(
                    f"outline section {section.title!r} maps sub_query_index "
                    f"{idx} out of range for {n_sub} final sub_queries"
                )
            covered.add(idx)
    expected = set(range(n_sub))
    if covered != expected:
        orphaned = sorted(expected - covered)
        raise MalformedPlanError(
            f"planned sub_queries {orphaned} are mapped to no outline section "
            "(every planned facet must be covered by some section)"
        )
