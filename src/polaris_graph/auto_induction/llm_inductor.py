"""M-D2 phase b: LLM-augmented inductor.

Wraps the M-D2 phase a keyword stub. Decision flow:

  1. Run base inductor (keyword stub). If it accepts, return that
     verdict — the keyword path is the cheap path and produces
     deterministic results.
  2. If base abstains, consult an LLM classifier. The classifier
     answers: "given this query and the candidate curator slugs,
     which slug best matches and with what confidence?"
  3. If LLM confidence >= `llm_accept_floor`, look up the curator
     contract and return accept. Otherwise propagate abstain.

The LLM classifier is dependency-injected. Two implementations
ship:

  - MockTemplateAffinityClassifier: deterministic, rule-based,
    used by unit tests. Simulates an LLM by keyword overlap with
    a richer keyword set (allows broader paraphrase coverage than
    the strict keyword stub).
  - OpenRouterTemplateAffinityClassifier: real LLM call via the
    project's OpenRouterClient, structured JSON output. Costs $$
    per query.

This split lets unit tests run offline (deterministic) and
production swap in the real LLM without changing inductor logic.

Per `docs/phase_d_milestones.md` M-D2 acceptance:
  precision >= 0.80, abstain_recall >= 0.95, abstain_precision
  >= 0.80, operator_review_load <= 0.30 on a balanced 100-200
  case validation set.

The keyword stub locked at v5 with operator_review_load = 0.674
on a negative-tilt set. M-D2 phase b is expected to reduce
operator load by handling the paraphrase / morphology / hyphen
cases the stub conservatively abstains on.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from src.polaris_graph.auto_induction.precision_metrics import (
    InductorVerdict,
    _load_curator_contract,
)


# ---------------------------------------------------------------------------
# Classifier protocol
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClassifierVerdict:
    """One classifier's decision on a query."""

    slug: str | None  # None = "no template matches"
    confidence: float  # in [0, 1]
    reason: str | None = None


class TemplateAffinityClassifier(Protocol):
    """Classifier interface: given a query + candidate slugs,
    return (best_slug or None, confidence)."""

    def classify(
        self,
        query: str,
        candidate_slugs: tuple[str, ...],
    ) -> ClassifierVerdict:
        ...


# ---------------------------------------------------------------------------
# Mock classifier (deterministic; used by unit tests)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _SlugProfile:
    """Richer keyword profile than the stub uses — broader
    paraphrase coverage to simulate LLM-quality routing."""

    slug: str
    keywords: tuple[str, ...]


# Mock-classifier profiles intentionally broader than the stub's.
# These represent what an LLM "knows" implicitly about each
# curator template. Used only by MockTemplateAffinityClassifier.
_MOCK_PROFILES: tuple[_SlugProfile, ...] = (
    _SlugProfile(
        slug="clinical_tirzepatide_t2dm",
        keywords=(
            # Brand + generic + trials
            "tirzepatide", "mounjaro", "zepbound", "surpass", "surmount",
            # Comparators
            "ozempic", "wegovy", "semaglutide", "liraglutide", "victoza",
            # Class names
            "glp-1", "glp1", "gip/glp-1", "incretin",
            # Conditions / metrics
            "type 2 diabetes", "t2dm", "diabetes", "diabetic",
            "hba1c", "a1c", "glycemic", "glycaemic", "glucose",
            # Outcome categories
            "weight loss", "body weight", "cardiovascular",
            "kidney", "renal",
            # Trial / mechanism vocabulary
            "phase 3", "phase iii", "rct", "randomized",
            "clamp", "pharmacokinetic",
        ),
    ),
    _SlugProfile(
        slug="policy_medicare_drug_price",
        keywords=(
            # IRA / negotiation
            "medicare", "part d", "part b", "cms", "ira",
            "inflation reduction act",
            "drug price", "drug pricing", "drug-price", "drug-pricing",
            "negotiation", "negotiated", "negotiating",
            "maximum fair price", "mfp",
            # Process / mechanism
            "rebate", "formulary", "pbm", "pharmacy benefit",
            # Stakeholders
            "pharma", "pharmaceutical", "biotech", "manufacturer",
            # Implementation
            "rule", "regulation", "guidance", "policy",
            "implementation",
        ),
    ),
)


class MockTemplateAffinityClassifier:
    """Rule-based classifier for offline unit tests.

    Deterministic: same query → same verdict, no API call. Uses
    broader keyword profiles than the strict M-D2 stub so it
    handles paraphrase / morphology cases the stub abstains on.
    """

    def classify(
        self,
        query: str,
        candidate_slugs: tuple[str, ...],
    ) -> ClassifierVerdict:
        ql = query.lower()
        candidates = {p.slug: p for p in _MOCK_PROFILES if p.slug in candidate_slugs}
        if not candidates:
            return ClassifierVerdict(
                slug=None, confidence=0.0,
                reason="no candidate slugs known to mock classifier",
            )
        # Score = count of keywords (using simple substring match,
        # broader than the stub's word-boundary regex on purpose:
        # the mock simulates an LLM's looser semantic match).
        scored = []
        for slug, profile in candidates.items():
            count = sum(1 for kw in profile.keywords if kw in ql)
            ratio = count / len(profile.keywords) if profile.keywords else 0.0
            scored.append((slug, count, ratio))
        scored.sort(key=lambda x: x[1], reverse=True)
        best_slug, best_count, best_ratio = scored[0]
        second_count = scored[1][1] if len(scored) > 1 else 0
        margin = best_count - second_count

        if best_count == 0:
            return ClassifierVerdict(
                slug=None, confidence=0.0,
                reason="no template keyword matched",
            )
        if margin < 1:
            return ClassifierVerdict(
                slug=None,
                confidence=best_ratio,
                reason=f"margin {margin} too small (top: {best_slug})",
            )
        # Confidence = clamp((count + 2*margin) / 10, 0, 1)
        # Heuristic that rewards count + margin proportionally.
        confidence = min(1.0, (best_count + 2 * margin) / 10.0)
        return ClassifierVerdict(
            slug=best_slug,
            confidence=confidence,
            reason=f"count={best_count}, margin={margin}",
        )


# ---------------------------------------------------------------------------
# OpenRouter classifier (real LLM, costs $$)
# ---------------------------------------------------------------------------


class OpenRouterTemplateAffinityClassifier:
    """Production classifier using the project's OpenRouterClient.

    Lazy-imports openrouter_client to keep the auto_induction
    package independent of LLM infra when not used. Will raise
    at construction if OPENROUTER_API_KEY is missing.

    Cost: each classify() call = one structured-output LLM call.
    With Qwen 3.5 Plus / GLM 5.1 typical cost ~$0.001-0.005 per
    call. A 100-case validation run = ~$0.10-0.50.
    """

    _SYSTEM_PROMPT = (
        "You are a query router for a research-audit platform. "
        "Given a research question + a list of curator-reviewed "
        "report-contract templates (each with a slug + one-line "
        "scope description), pick the SINGLE template whose scope "
        "best matches the query. Return null if no template "
        "covers the query.\n\n"
        "Output strict JSON: {\"slug\": \"<slug>\" or null, "
        "\"confidence\": <0.0-1.0>, \"reason\": \"<short>\"}.\n\n"
        "Confidence guidance: 0.9+ = exact subject match. "
        "0.7-0.9 = clear subject match with paraphrase. "
        "0.5-0.7 = adjacent / partial match (you are unsure). "
        "<0.5 = wrong template / out of scope. "
        "Be conservative: if in doubt, return null + low confidence."
    )

    _SLUG_DESCRIPTIONS: dict[str, str] = {
        "clinical_tirzepatide_t2dm": (
            "Clinical efficacy of tirzepatide (Mounjaro/Zepbound) "
            "for type 2 diabetes — SURPASS trials, head-to-head "
            "vs semaglutide/Ozempic, HbA1c outcomes, weight "
            "outcomes, cardiovascular outcomes, mechanism "
            "(GIP/GLP-1 dual agonist)."
        ),
        "policy_medicare_drug_price": (
            "U.S. Medicare drug price negotiation under the "
            "Inflation Reduction Act (IRA) — Part D formulary "
            "impact, CMS implementation, PBM rebate effects, "
            "manufacturer R&D investment effects, maximum-fair-"
            "price rule."
        ),
    }

    def __init__(self, *, model: str | None = None) -> None:
        # Lazy import so the auto_induction package doesn't pull
        # in httpx/asyncio when the OpenRouter classifier isn't used.
        from src.polaris_graph.llm.openrouter_client import (
            OpenRouterClient,
        )
        self._client = OpenRouterClient()
        self._model = model

    def classify(
        self,
        query: str,
        candidate_slugs: tuple[str, ...],
    ) -> ClassifierVerdict:
        descriptions = "\n".join(
            f"- {s}: {self._SLUG_DESCRIPTIONS.get(s, '<no description>')}"
            for s in candidate_slugs
        )
        user_prompt = (
            f"Research question:\n{query}\n\n"
            f"Available templates:\n{descriptions}\n\n"
            f"Return strict JSON per the system instructions."
        )
        # Synchronous wrapper around async client — auto_induction
        # callers are sync.
        import asyncio

        async def _go() -> str:
            # OpenRouterClient.generate(prompt, system="", ...) returns
            # LLMResponse with `.content` as the prose output.
            response = await self._client.generate(
                prompt=user_prompt,
                system=self._SYSTEM_PROMPT,
                temperature=0.0,  # deterministic routing
            )
            return response.content

        try:
            raw = asyncio.run(_go())
        except RuntimeError:
            # Already inside an event loop (rare for inductor calls).
            loop = asyncio.new_event_loop()
            try:
                raw = loop.run_until_complete(_go())
            finally:
                loop.close()

        return _parse_classifier_json(raw, candidate_slugs)


def _parse_classifier_json(
    raw: str, candidate_slugs: tuple[str, ...],
) -> ClassifierVerdict:
    """Parse the structured JSON output from the LLM. Tolerant
    of common malformations (code-fence wrappers, trailing prose)."""
    text = raw.strip()
    # Strip markdown code fences if present.
    if text.startswith("```"):
        # Drop first line and last fence.
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    # Find first { and last } — cuts trailing prose.
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return ClassifierVerdict(
            slug=None, confidence=0.0,
            reason=f"non-JSON LLM output: {text[:100]!r}",
        )
    snippet = text[start:end + 1]
    try:
        parsed = json.loads(snippet)
    except json.JSONDecodeError as exc:
        return ClassifierVerdict(
            slug=None, confidence=0.0,
            reason=f"JSON parse failed: {exc}",
        )
    if not isinstance(parsed, dict):
        return ClassifierVerdict(
            slug=None, confidence=0.0,
            reason=f"LLM output not a dict: {parsed!r}",
        )
    raw_slug = parsed.get("slug")
    raw_conf = parsed.get("confidence", 0.0)
    raw_reason = parsed.get("reason")
    # Validate slug.
    if raw_slug is not None and raw_slug not in candidate_slugs:
        return ClassifierVerdict(
            slug=None, confidence=0.0,
            reason=(
                f"LLM returned slug {raw_slug!r} not in candidate "
                f"set {candidate_slugs}"
            ),
        )
    # Clamp confidence.
    try:
        conf = float(raw_conf)
    except (TypeError, ValueError):
        conf = 0.0
    conf = max(0.0, min(1.0, conf))
    return ClassifierVerdict(
        slug=raw_slug,
        confidence=conf,
        reason=str(raw_reason) if raw_reason is not None else None,
    )


# ---------------------------------------------------------------------------
# LLMAugmentedInductor
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LLMAugmentedInductorConfig:
    """Tunable parameters for the LLM-augmented inductor."""

    candidate_slugs: tuple[str, ...] = (
        "clinical_tirzepatide_t2dm",
        "policy_medicare_drug_price",
    )
    # When the LLM classifier confidence falls below this, the
    # inductor abstains. Codex round-1 acceptance: precision
    # depends critically on this floor. Default 0.7 (LLM must be
    # reasonably confident).
    llm_accept_floor: float = 0.7


class LLMAugmentedInductor:
    """M-D2 phase b: keyword stub + LLM-augmented fallback.

    Implements `InductorProtocol`. When the keyword stub abstains,
    consult the LLM classifier. If the classifier is confident
    enough, accept; otherwise propagate abstain.
    """

    def __init__(
        self,
        *,
        base_inductor: Any,  # InductorProtocol (any duck-type works)
        llm_classifier: TemplateAffinityClassifier,
        config: LLMAugmentedInductorConfig | None = None,
    ) -> None:
        self._base = base_inductor
        self._classifier = llm_classifier
        self._config = config or LLMAugmentedInductorConfig()

    def induce(self, query: str) -> InductorVerdict:
        # Step 1: keyword stub (cheap, deterministic).
        base_verdict = self._base.induce(query)
        if base_verdict.decision == "accept":
            return base_verdict

        # If the stub flagged this as terminal (disqualifier hit —
        # "I know this is out of scope"), don't override with LLM.
        # The disqualifier represents domain knowledge the LLM may
        # not have.
        if base_verdict.is_terminal:
            return base_verdict

        # Step 2: LLM classifier (expensive, paraphrase-tolerant).
        llm = self._classifier.classify(query, self._config.candidate_slugs)
        if llm.slug is None:
            return InductorVerdict(
                decision="abstain",
                confidence=llm.confidence,
                abstain_reason=(
                    f"keyword stub abstained AND LLM declined "
                    f"({llm.reason})"
                ),
            )
        if llm.confidence < self._config.llm_accept_floor:
            return InductorVerdict(
                decision="abstain",
                confidence=llm.confidence,
                abstain_reason=(
                    f"keyword stub abstained; LLM confidence "
                    f"{llm.confidence:.2f} < floor "
                    f"{self._config.llm_accept_floor:.2f} "
                    f"({llm.reason})"
                ),
            )

        # Step 3: look up the curator contract.
        try:
            contract = _load_curator_contract(llm.slug)
        except ValueError as exc:
            return InductorVerdict(
                decision="abstain",
                confidence=llm.confidence,
                abstain_reason=(
                    f"LLM picked slug {llm.slug!r} but curator "
                    f"contract not found: {exc}"
                ),
            )
        return InductorVerdict(
            decision="accept",
            induced_contract=contract,
            confidence=llm.confidence,
        )
