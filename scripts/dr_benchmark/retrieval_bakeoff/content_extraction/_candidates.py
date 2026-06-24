"""Candidate extractor registry for the content_extraction bake-off.

Each candidate is registered by its EXACT pip/HF id with a role that the harness
honors STRUCTURALLY (advisor pt 5):

  * role="baseline" / "candidate"  -> eligible to win (deterministic extractive).
  * role="yardstick_non_sovereign" -> ReaderLM-v2: benched for reference only,
    NEVER content-of-record, NEVER crowned (generative => fabrication risk +
    CC-BY-NC license). Enforced by `is_eligible_to_win` below, not a comment.

needs_gpu candidates (MinerU-HTML, ReaderLM-v2) are gated behind a runtime check
in run_bakeoff.py: registered-but-skipped honestly when no GPU, never faked.

Extractor callables raise `ExtractorLoadError` on import/load failure so the
GATE-0 liveness canary can distinguish a DEAD candidate (fail loud) from a
genuinely-low score on a hard page (a real result). They return the empty string
ONLY when the underlying tool genuinely produced nothing -- which the liveness
canary treats as a failure ON THE KNOWN-GOOD page.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable


class ExtractorLoadError(RuntimeError):
    """Raised fail-loud when an extractor cannot load/import (dead candidate)."""


@dataclass(frozen=True)
class Candidate:
    """A registered extractor candidate."""

    name: str
    key: str  # short key matching PUBLISHED_ANCHORS where applicable
    impl_id: str  # exact pip/HF id (web-verified 2026-06-23)
    license: str
    role: str  # baseline | candidate | yardstick_non_sovereign
    needs_gpu: bool
    extractive: bool  # deterministic verbatim (True) vs generative (False)
    extract: Callable[[str], str] = field(repr=False)


def is_eligible_to_win(candidate: Candidate) -> bool:
    """STRUCTURAL never-crown: only extractive non-yardstick roles can win.

    A higher ROUGE for ReaderLM-v2 can never crown it: this is checked by role,
    so the decision rule cannot be gamed by a bigger number.
    """
    return candidate.extractive and candidate.role != "yardstick_non_sovereign"


# ---------------------------------------------------------------------------
# Extractor implementations (lazy imports -> ExtractorLoadError on failure).
# ---------------------------------------------------------------------------


def _extract_trafilatura(html: str) -> str:
    """Production-faithful Trafilatura via the guarded POLARIS entrypoint.

    Uses the prod kwargs (markdown, tables, no links) and the size-gate +
    SIGSEGV containment of safe_trafilatura_extract (access_bypass.py:943).
    """
    try:
        from src.tools.access_bypass import safe_trafilatura_extract
    except Exception as exc:  # noqa: BLE001 -- a missing seam is a dead candidate
        raise ExtractorLoadError(f"trafilatura seam import failed: {exc!r}") from exc
    out = safe_trafilatura_extract(
        html,
        output_format="markdown",
        include_tables=True,
        include_links=False,
    )
    return out or ""


def _extract_resiliparse(html: str) -> str:
    try:
        from resiliparse.extract.html2text import extract_plain_text  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise ExtractorLoadError(f"resiliparse import failed: {exc!r}") from exc
    return extract_plain_text(html, main_content=True) or ""


def _extract_justext(html: str) -> str:
    try:
        import justext  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise ExtractorLoadError(f"justext import failed: {exc!r}") from exc
    # MUST set English stoplist for the clinical fixture (raw-json note: its
    # published 0.4782 is partly a multilingual mis-set artifact).
    paragraphs = justext.justext(html, justext.get_stoplist("English"))
    return "\n".join(p.text for p in paragraphs if not p.is_boilerplate)


def _extract_readability(html: str) -> str:
    try:
        from readability import Document  # type: ignore  (readability-lxml)
    except Exception as exc:  # noqa: BLE001
        raise ExtractorLoadError(f"readability-lxml import failed: {exc!r}") from exc
    return Document(html).summary() or ""


def _extract_union(html: str) -> str:
    """Deterministic line-level union of trafilatura+resiliparse+justext.

    Pure-extractive (every line comes verbatim from a member extractor) ->
    faithfulness-safe. Near-dup line collapse uses the named POLARIS
    ContentDeduplicator seam (seed-42 deterministic) rather than adding
    datasketch -- keeps determinism and avoids a new dependency.
    """
    members = [_extract_trafilatura(html), _extract_resiliparse(html), _extract_justext(html)]
    lines: list[str] = []
    seen_exact: set[str] = set()
    for body in members:
        for raw_line in (body or "").splitlines():
            line = raw_line.strip()
            if not line or line in seen_exact:
                continue
            seen_exact.add(line)
            lines.append(line)
    # Near-dup collapse across members (a line >=2 extractors emit slightly
    # differently) via the existing deterministic deduplicator.
    try:
        from src.utils.content_deduplicator import (
            ContentDeduplicator,
            DeduplicationConfig,
        )

        dedup = ContentDeduplicator(
            DeduplicationConfig(near_duplicate_threshold=0.92, min_content_length=0)
        )
        items = [{"content": ln} for ln in lines]
        unique = dedup.get_unique_content(items)
        lines = [it["content"] for it in unique]
    except Exception:  # noqa: BLE001 -- dedup is a refinement, not load-bearing;
        # if the seam is unavailable the exact-dup pass above already ran.
        pass
    return "\n".join(lines)


def _extract_mineru_html(html: str) -> str:
    """MinerU-HTML (opendatalab/MinerU-HTML, base Qwen3-0.6B) -- needs GPU/vLLM.

    CONFIRMED EXTRACTIVE (Dripper paper: DOM-block label-and-reconstruct, no
    paraphrase). This callable is only invoked on a GPU host; on a CPU/smoke
    host the harness skips it via needs_gpu gating before calling.
    """
    try:
        from mineru_html import extract as mineru_extract  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise ExtractorLoadError(
            f"mineru-html import failed (needs_gpu; pip install .[baselines] "
            f"from github.com/opendatalab/MinerU-HTML): {exc!r}"
        ) from exc
    return mineru_extract(html) or ""


def _extract_readerlm_v2(html: str) -> str:
    """ReaderLM-v2 (jinaai/ReaderLM-v2) -- GENERATIVE yardstick, needs GPU.

    Structurally barred from being crowned (role=yardstick_non_sovereign). The
    faithfulness substring check is EXPECTED to flag it -- that is the §-1.1
    anti-gaming demonstration, not a bug.
    """
    try:
        from vllm import LLM, SamplingParams  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise ExtractorLoadError(
            f"vLLM import failed for ReaderLM-v2 (needs_gpu): {exc!r}"
        ) from exc
    model_id = os.getenv("PG_READERLM_MODEL", "jinaai/ReaderLM-v2")
    llm = LLM(model=model_id)
    prompt = f"Extract the main content of this HTML as Markdown:\n{html}"
    result = llm.generate([prompt], SamplingParams(max_tokens=8192))
    return result[0].outputs[0].text if result else ""


def build_candidate_registry() -> list[Candidate]:
    """All extractor candidates, exact ids web-verified 2026-06-23."""
    return [
        Candidate(
            name="Trafilatura 2.x (incumbent content-of-record)",
            key="trafilatura",
            impl_id="pip: trafilatura==2.1.0",
            license="Apache-2.0",
            role="baseline",
            needs_gpu=False,
            extractive=True,
            extract=_extract_trafilatura,
        ),
        Candidate(
            name="Resiliparse (recall-biased ensemble partner)",
            key="resiliparse",
            impl_id="pip: chatnoir-resiliparse",
            license="Apache-2.0",
            role="candidate",
            needs_gpu=False,
            extractive=True,
            extract=_extract_resiliparse,
        ),
        Candidate(
            name="jusText (3rd union member)",
            key="justext",
            impl_id="pip: justext",
            license="Apache-2.0/BSD-2-Clause",
            role="candidate",
            needs_gpu=False,
            extractive=True,
            extract=_extract_justext,
        ),
        Candidate(
            name="readability-lxml (last-resort fallback baseline)",
            key="readability",
            impl_id="pip: readability-lxml==0.8.4.1",
            license="Apache-2.0",
            role="baseline",
            needs_gpu=False,
            extractive=True,
            extract=_extract_readability,
        ),
        Candidate(
            name="union(trafilatura+resiliparse+justext)",
            key="union",
            impl_id="composite (deterministic line-union + ContentDeduplicator collapse)",
            license="Apache-2.0 (union of Apache components)",
            role="candidate",
            needs_gpu=False,
            extractive=True,
            extract=_extract_union,
        ),
        Candidate(
            name="MinerU-HTML (Dripper SLM, clinical/table lane)",
            key="mineru_html",
            impl_id="HF: opendatalab/MinerU-HTML (v1.1, base Qwen/Qwen3-0.6B)",
            license="Apache-2.0",
            role="candidate",
            needs_gpu=True,
            extractive=True,
            extract=_extract_mineru_html,
        ),
        Candidate(
            name="ReaderLM-v2 (generative upper-bound yardstick)",
            key="readerlm_v2",
            impl_id="HF: jinaai/ReaderLM-v2",
            license="CC-BY-NC-4.0 (non-commercial -> YARDSTICK ONLY)",
            role="yardstick_non_sovereign",
            needs_gpu=True,
            extractive=False,
            extract=_extract_readerlm_v2,
        ),
    ]
