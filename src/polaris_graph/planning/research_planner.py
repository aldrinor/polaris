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
from dataclasses import dataclass, field
from typing import Any, Callable

from src.polaris_graph.generator.multi_section_generator import (
    SECTION_ARCHETYPES,
)

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

# UPPER bound on emitted sub-queries (brief §2.1). >40 is merged/truncated
# deterministically. The fetch cap (`PG_SWEEP_FETCH_CAP`) bounds FETCHED URLs
# downstream; this bounds the per-question query fan-out.
DEFAULT_MAX_SUBQUERIES = 40
# LOWER bound that triggers ONE fail-loud retry (brief §2.1). A genuinely
# narrow question may legitimately accept fewer after the retry; we never pad.
MIN_SUBQUERIES = 12


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
    """

    archetype: str
    title: str
    evidence_target: int = 0


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
            },
            "sub_queries": list(self.sub_queries),
            "outline": [
                {
                    "archetype": item.archetype,
                    "title": item.title,
                    "evidence_target": item.evidence_target,
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
    case-insensitively, preserve order)."""
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
    return ResearchFrame(
        entities=_as_str_list(raw_frame.get("entities")),
        relations=_as_str_list(raw_frame.get("relations")),
        metrics=_as_str_list(raw_frame.get("metrics")),
        comparators=_as_str_list(raw_frame.get("comparators")),
        constraints=_as_str_list(raw_frame.get("constraints")),
        claim_type=claim_type,
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
        items.append(SectionOutlineItem(
            archetype=valid_tags[tag_raw],
            title=title,
            evidence_target=max(0, evidence_target),
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
        f'     "claim_type": one of [{claim_type_list}]\n'
        "  },\n"
        '  "sub_queries": [faceted search queries, each a focused phrase that '
        "covers ONE facet of the question — collectively spanning every "
        "entity x metric x comparator x constraint combination the question "
        f"implies; aim for {min_subqueries} or more for a broad question, "
        "fewer only for a genuinely narrow one],\n"
        '  "outline": [section objects, each with:\n'
        '       "archetype": one of the field-invariant tags below,\n'
        '       "title":     a QUESTION-SPECIFIC section heading (not a generic label),\n'
        '       "evidence_target": an integer target number of sources for the section\n'
        "  ]\n\n"
        f"ALLOWED ARCHETYPE TAGS (pick the ones the question needs): {archetype_list}\n\n"
        "RULES:\n"
        "- The titles must be specific to THIS question, not generic category "
        "names. The archetype tag is the field-invariant control; the title "
        "is the human-facing heading.\n"
        "- Choose archetypes that fit the question's claim_type. A decision / "
        "comparison question needs a Decision archetype; an explanatory "
        "question needs a Mechanism archetype; etc.\n"
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
    return plan
