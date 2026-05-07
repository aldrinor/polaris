"""Generator orchestrator — slice 003 main entry.

Per `.codex/slices/slice_003/architecture_proposal.md` §"generator.py".

Pipeline:
    EvidencePool (slice 002 output, adequacy.is_adequate=True)
        ↓
    blueprint_for_scope_class()  -> ordered list of SectionPlan
        ↓
    For each section:
        completion_fn(prompt, section_plan, pool)  -> raw_text
        ↓
        split into sentences
        ↓
        verify_sentence_to_record() per sentence  -> VerifiedSentence
        ↓
        compute section_pass_rate
        ↓
        if rate < threshold: regenerate ONCE; if still < threshold, mark dropped
    ↓
    If every section dropped: VerifiedReport(verdict='abort_no_verified_sections')
    Else: VerifiedReport(verdict='success', kept sections only)

Network-free by design: callers inject completion_fn (GeneratorCompletionFn
protocol). The default _default_completion_fn raises NotImplementedError so
tests + golden tests can never accidentally call a real LLM. PR 7 will ship
the real OpenRouter-backed completion_fn behind the same Protocol.
"""

from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Protocol

from polaris_graph.generator2.section_blueprint import (
    Blueprint,
    SectionPlan,
    blueprint_for_scope_class,
)
from polaris_graph.generator2.strict_verify import (
    section_pass_rate,
    verify_sentence_to_record,
)
from polaris_graph.generator2.verified_report import (
    GenerationError,
    Section,
    VerifiedReport,
    VerifiedSentence,
)
from polaris_graph.retrieval2.evidence_pool import EvidencePool


DEFAULT_VERIFIER_PASS_THRESHOLD = 0.40
DEFAULT_GENERATOR_MODEL_LABEL = "stub-generator"


# ---------------------------------------------------------------------------
# completion_fn protocol
# ---------------------------------------------------------------------------

class GeneratorCompletionFn(Protocol):
    """LLM adapter contract.

    Given a prompt + section context, return raw generated text. The
    orchestrator parses the returned text into sentences and runs each
    through strict_verify. Implementations must be deterministic-given-
    input enough to be testable.
    """

    def __call__(
        self,
        prompt: str,
        section_plan: SectionPlan,
        pool: EvidencePool,
    ) -> str: ...


def _default_completion_fn(
    prompt: str,
    section_plan: SectionPlan,
    pool: EvidencePool,
) -> str:
    """Sentinel — refuses to run.

    PR 6 ships orchestrator with NO real LLM adapter. Callers MUST inject
    one. PR 7 will ship the real OpenRouter completion_fn.
    """
    raise NotImplementedError(
        "no completion_fn injected. slice 003 PR 7 ships the real "
        "OpenRouter-backed generator; for unit tests inject a stub."
    )


# ---------------------------------------------------------------------------
# Sentence splitter (simple — replace with spaCy if needed)
# ---------------------------------------------------------------------------

# Split on sentence-ending punctuation followed by whitespace + capital
# letter or end-of-string. Conservative; preserves provenance tokens.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\[])")


def _split_sentences(text: str) -> list[str]:
    """Split `text` into sentences. Strips empty/whitespace-only entries."""
    raw = _SENTENCE_SPLIT_RE.split(text.strip())
    return [s.strip() for s in raw if s.strip()]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_pool(pool: EvidencePool) -> GenerationError | None:
    if not pool.adequacy.is_adequate:
        return GenerationError(
            code="inadequate_pool",
            message=(
                f"pool {pool.pool_id} adequacy.is_adequate=False; "
                f"reason: {pool.adequacy.failure_reason}"
            ),
            pool_id=pool.pool_id,
            decision_id=pool.decision_id,
        )
    return None


# ---------------------------------------------------------------------------
# Per-section generation + verification
# ---------------------------------------------------------------------------

def _generate_and_verify_section(
    section_plan: SectionPlan,
    pool: EvidencePool,
    completion_fn: GeneratorCompletionFn,
    threshold: float,
) -> Section:
    """Run completion_fn for one section, verify each sentence,
    regenerate ONCE if pass-rate is below threshold."""

    def attempt() -> tuple[list[VerifiedSentence], float]:
        raw = completion_fn(
            prompt=section_plan.section_brief,
            section_plan=section_plan,
            pool=pool,
        )
        sentences = _split_sentences(raw)
        records = [
            verify_sentence_to_record(s, section_plan.section_id, pool)
            for s in sentences
        ]
        return records, section_pass_rate(records)

    records, rate = attempt()
    status = "verified"

    if rate < threshold:
        records2, rate2 = attempt()
        if rate2 >= threshold:
            records = records2
            rate = rate2
            status = "regenerated"
        else:
            # Both attempts failed — mark dropped + keep the better attempt
            # so audit bundle shows what was tried.
            if rate2 > rate:
                records, rate = records2, rate2
            status = "dropped"

    return Section(
        section_id=section_plan.section_id,
        section_title=section_plan.section_title,
        verified_sentences=records,
        section_verify_pass_rate=rate,
        section_status=status,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Public orchestrator
# ---------------------------------------------------------------------------

def process_generation(
    pool: EvidencePool,
    completion_fn: GeneratorCompletionFn = _default_completion_fn,
    blueprint: Blueprint | None = None,
    verifier_pass_threshold: float = DEFAULT_VERIFIER_PASS_THRESHOLD,
    scope_class: str | None = None,
    generator_model: str = DEFAULT_GENERATOR_MODEL_LABEL,
) -> VerifiedReport | GenerationError:
    """Run an EvidencePool through generator + strict-verify.

    Returns:
        VerifiedReport on either success path or all-sections-dropped abort.
        GenerationError when input pool is structurally invalid OR
            completion_fn is the sentinel default OR raises persistently.
    """
    err = _validate_pool(pool)
    if err is not None:
        return err

    started = datetime.now(timezone.utc)
    t_start = time.perf_counter()

    if blueprint is None:
        # scope_class is preferred; falls back to DEFAULT_BLUEPRINT (efficacy)
        # when None. EvidencePool does not currently carry scope_class —
        # callers (e.g. the FastAPI route) must thread it through from the
        # ScopeDecision that triggered retrieval.
        blueprint = blueprint_for_scope_class(scope_class)

    # Derive a real generator_model label when the injected completion_fn
    # exposes one (e.g. RealCompletion.model_label). Stub functions used
    # in tests don't have it, so we fall back to the explicit arg.
    effective_model = generator_model
    if generator_model == DEFAULT_GENERATOR_MODEL_LABEL:
        candidate = getattr(completion_fn, "model_label", None)
        if isinstance(candidate, str) and candidate.strip():
            effective_model = candidate

    # Generate all sections in parallel. Each section calls the LLM 1-2
    # times (regen on threshold-fail). With 4 sections, parallel reduces
    # latency from ~4-8 LLM calls serial to ~1-2 LLM calls wall-clock.
    sections_by_idx: dict[int, Section] = {}
    fatal_error: GenerationError | None = None

    with ThreadPoolExecutor(max_workers=len(blueprint.sections)) as pool_exec:
        future_to_idx = {
            pool_exec.submit(
                _generate_and_verify_section,
                plan,
                pool,
                completion_fn,
                verifier_pass_threshold,
            ): idx
            for idx, plan in enumerate(blueprint.sections)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                sections_by_idx[idx] = future.result()
            except NotImplementedError:
                fatal_error = GenerationError(
                    code="completion_backend_unavailable",
                    message=(
                        "completion_fn is the sentinel default; inject a real "
                        "fn (PR 7) or test stub"
                    ),
                    pool_id=pool.pool_id,
                    decision_id=pool.decision_id,
                )
                break
            except Exception as exc:  # noqa: BLE001
                fatal_error = GenerationError(
                    code="completion_backend_unavailable",
                    message=f"completion_fn raised {type(exc).__name__}: {exc}",
                    pool_id=pool.pool_id,
                    decision_id=pool.decision_id,
                )
                break

    if fatal_error is not None:
        return fatal_error

    # Preserve blueprint section order
    sections: list[Section] = [
        sections_by_idx[i] for i in range(len(blueprint.sections))
    ]

    finished = datetime.now(timezone.utc)
    elapsed_ms = int((time.perf_counter() - t_start) * 1000)

    # Aggregate pass rate over ALL sentences (kept + dropped) across non-dropped sections.
    kept_sections = [s for s in sections if s.section_status != "dropped"]
    if kept_sections:
        total = sum(len(s.verified_sentences) for s in kept_sections)
        passed = sum(
            sum(1 for v in s.verified_sentences if v.verifier_pass)
            for s in kept_sections
        )
        overall_rate = passed / total if total > 0 else 0.0
        pipeline_verdict = "success"
    else:
        # Every section dropped -> abort. For schema validation, we must
        # carry only dropped sections through.
        sections = [s for s in sections if s.section_status == "dropped"]
        overall_rate = 0.0
        pipeline_verdict = "abort_no_verified_sections"

    # When verdict=success, the schema requires sections list to contain
    # only non-dropped OR the verdict consistency check fails. Filter:
    if pipeline_verdict == "success":
        sections = kept_sections

    return VerifiedReport(
        pool_id=pool.pool_id,
        decision_id=pool.decision_id,
        sections=sections,
        overall_verify_pass_rate=overall_rate,
        pipeline_verdict=pipeline_verdict,  # type: ignore[arg-type]
        generator_model=effective_model,
        evaluator_model="strict_verify_v1",
        family_segregation_passed=True,
        verifier_pass_threshold=verifier_pass_threshold,
        started_at_utc=started,
        finished_at_utc=finished,
        latency_ms=elapsed_ms,
        cost_usd=0.0,
    )
