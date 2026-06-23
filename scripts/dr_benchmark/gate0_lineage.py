"""GATE 0 — artifact-lineage enforcement for the benchmark harness (I-qgen-001, GH #1291).

The drb_72 disaster had two harness-integrity failures that produced trustworthy-looking
garbage scores:
  1. WRONG QUESTION: the sweep launched a hardcoded "Fourth Industrial Revolution" prompt
     that was NOT the canonical DeepResearch-Bench-II idx-56 question.
  2. SPLIT-BRAIN SCORING: the DeepTRACE/DRB pack used the canonical question while the report
     answered the substituted one.

This module is the single source of truth that makes those impossible. It binds every
benchmark run to the canonical question by idx (no drifting hardcoded copies) and provides a
fail-loud equality check: launched == packed == answered == canonical. Nothing is hardcoded
that can silently drift from the gold file.

No magic numbers, no silent fallbacks: a mismatch raises GateZeroLineageError (fail loud).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from typing import Any

# Canonical gold file (DeepResearch-Bench-II tasks + rubrics).
DEFAULT_TASKS_PATH = os.path.join(
    "third_party", "DeepResearch-Bench-II", "tasks_and_rubrics.jsonl"
)

# slug -> canonical DRB-II idx. The id<->idx offset is real (task72 -> idx 56, NOT 72);
# binding by idx is what prevents the drb_72 wrong-question failure. The slug strings here
# MUST be byte-identical to the launchable slugs in SWEEP_QUERIES (run_honest_sweep_r3.py) —
# bare "drb_76"/"drb_78" never matched the real "drb_76_gut_microbiota_crc"/"drb_78_parkinsons_dbs"
# slugs, so GATE0 silently skipped them (Codex iter-2 P1). Resolve any new slug from the gold
# file before adding it here; never guess.
SLUG_TO_IDX: dict[str, int] = {
    "drb_72_ai_labor": 56,
    "drb_75_metal_ions_cvd": 62,
    "drb_76_gut_microbiota_crc": 66,
    "drb_78_parkinsons_dbs": 72,
}

# DRB-EN slugs the sweep launches that have NO DeepResearch-Bench-II gold task (no canonical
# idx, no info_recall rubric) — they CANNOT be canonically bound or coverage-scored. Listed
# EXPLICITLY so the fail-loud registration check does not trip on them and so the omission is
# documented, never a silent gap. drb_90 (ADAS liability) is simply not in the DRB-II gold file.
DRB_SLUGS_WITHOUT_CANONICAL_GOLD: frozenset[str] = frozenset({"drb_90_adas_liability"})

# A DRB-EN benchmark slug looks like ``drb_<id>_<topic>``. Used to decide whether the
# registration check applies (non-benchmark sweep slugs are never gated).
_DRB_SLUG_PATTERN = re.compile(r"^drb_\d+")


def is_benchmark_slug(slug: str) -> bool:
    """True iff ``slug`` is a DRB-EN benchmark slug (``drb_<id>_...``)."""
    return bool(_DRB_SLUG_PATTERN.match(slug or ""))


def assert_drb_slug_registered(slug: str) -> None:
    """Fail loud if a ``drb_*`` slug is neither canonically mapped nor an explicit no-gold slug.

    Catches a renamed/added benchmark slug (e.g. a future ``drb_NN``) that would otherwise
    launch a hardcoded question with NO canonical binding — the exact silent gap that let
    ``drb_76``/``drb_78`` (bare names) and ``drb_90`` slip past the GATE0 override. Non-benchmark
    slugs are ignored.
    """
    if not is_benchmark_slug(slug):
        return
    if slug in SLUG_TO_IDX or slug in DRB_SLUGS_WITHOUT_CANONICAL_GOLD:
        return
    raise GateZeroLineageError(
        f"GATE0: benchmark slug {slug!r} is UNREGISTERED — neither in SLUG_TO_IDX "
        f"(canonically bound) nor DRB_SLUGS_WITHOUT_CANONICAL_GOLD (explicit no-gold). "
        f"Resolve its gold idx from {DEFAULT_TASKS_PATH} and add it, or register it as no-gold. "
        f"Never let a benchmark slug launch a hardcoded question unbound (the drb_72 failure)."
    )


class GateZeroLineageError(RuntimeError):
    """Raised fail-loud when benchmark artifact lineage is violated.

    A run that raises this is INVALID and must be excluded from any score. This is the
    structural guard against the drb_72 wrong-question / split-brain-scoring failures.
    """


def _normalize(text: str) -> str:
    """Whitespace-normalize a question for comparison (semantics preserved, layout ignored)."""
    return " ".join((text or "").split())


def sha256_text(text: str) -> str:
    """Stable sha256 of normalized text."""
    return hashlib.sha256(_normalize(text).encode("utf-8")).hexdigest()


def load_canonical_question(idx: int, tasks_path: str = DEFAULT_TASKS_PATH) -> str:
    """Return the canonical question prompt for a DRB-II idx, straight from the gold file.

    Fails loud if the gold file is missing or the idx is not present — never returns a
    silent default.
    """
    if not os.path.isfile(tasks_path):
        raise GateZeroLineageError(
            f"GATE0: canonical tasks file not found: {tasks_path} — cannot verify lineage"
        )
    with open(tasks_path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("idx") == idx:
                prompt = record.get("prompt")
                if not prompt:
                    raise GateZeroLineageError(
                        f"GATE0: idx={idx} present but has empty 'prompt' in {tasks_path}"
                    )
                return prompt
    raise GateZeroLineageError(
        f"GATE0: idx={idx} not found in canonical tasks file {tasks_path}"
    )


def canonical_question_for_slug(slug: str, tasks_path: str = DEFAULT_TASKS_PATH) -> str:
    """Canonical question for a benchmark slug (via SLUG_TO_IDX)."""
    if slug not in SLUG_TO_IDX:
        raise GateZeroLineageError(
            f"GATE0: slug {slug!r} has no canonical idx mapping — resolve it from the gold "
            f"file and add it to SLUG_TO_IDX before running (never guess the idx)"
        )
    return load_canonical_question(SLUG_TO_IDX[slug], tasks_path)


def assert_launched_question_is_canonical(
    slug: str, launched_question: str, tasks_path: str = DEFAULT_TASKS_PATH
) -> str:
    """Fail loud unless the launched question equals the canonical question for the slug.

    Returns the canonical question (so callers can launch THAT, not a hardcoded copy).
    This is the structural fix for the drb_72 wrong-question bug.
    """
    canonical = canonical_question_for_slug(slug, tasks_path)
    if sha256_text(launched_question) != sha256_text(canonical):
        raise GateZeroLineageError(
            "GATE0 WRONG-QUESTION: launched question != canonical for slug "
            f"{slug!r}.\n  launched(sha)={sha256_text(launched_question)[:16]} : "
            f"{_normalize(launched_question)[:120]!r}\n  canonical(sha)="
            f"{sha256_text(canonical)[:16]} : {_normalize(canonical)[:120]!r}"
        )
    return canonical


def assert_no_split_brain(
    slug: str,
    packed_question: str,
    answered_question: str,
    tasks_path: str = DEFAULT_TASKS_PATH,
) -> None:
    """Fail loud unless packed == answered == canonical (the split-brain guard).

    `packed_question` = the question handed to the judge/scorer pack.
    `answered_question` = the question the report (corpus_snapshot) actually answered.
    Both must equal the canonical question, or the score is meaningless.
    """
    canonical = canonical_question_for_slug(slug, tasks_path)
    c = sha256_text(canonical)
    p = sha256_text(packed_question)
    a = sha256_text(answered_question)
    if not (p == c and a == c):
        raise GateZeroLineageError(
            "GATE0 SPLIT-BRAIN: packed/answered/canonical question mismatch for slug "
            f"{slug!r}.\n  canonical(sha)={c[:16]}\n  packed(sha)   ={p[:16]} "
            f"({'OK' if p == c else 'MISMATCH'})\n  answered(sha) ={a[:16]} "
            f"({'OK' if a == c else 'MISMATCH'})"
        )


def build_lineage_manifest(
    *,
    slug: str,
    launched_question: str,
    packed_question: str,
    answered_question: str,
    rendered_report: str,
    judge_input: str,
    score_row: Any,
    backbone_model: str,
    decoding_params: dict[str, Any],
    prompt_template_id: str,
    retrieval_snapshot_id: str,
    judge_model_version: str,
    scorer_config_id: str,
    execution_seed: int,
    tasks_path: str = DEFAULT_TASKS_PATH,
) -> dict[str, Any]:
    """Build the immutable lineage manifest for a benchmark run.

    Hashes the full artifact chain (task -> question -> answer -> report -> judge input ->
    score) PLUS the reproducibility surface (backbone model, decoding, template, retrieval
    snapshot, judge model/version, scorer config, seed). Asserts canonical equality first,
    so a manifest cannot be built for a wrong-question or split-brain run.
    """
    canonical = assert_launched_question_is_canonical(slug, launched_question, tasks_path)
    assert_no_split_brain(slug, packed_question, answered_question, tasks_path)
    return {
        "slug": slug,
        "canonical_idx": SLUG_TO_IDX[slug],
        "canonical_question_sha": sha256_text(canonical),
        "launched_question_sha": sha256_text(launched_question),
        "packed_question_sha": sha256_text(packed_question),
        "answered_question_sha": sha256_text(answered_question),
        "rendered_report_sha": sha256_text(rendered_report),
        "judge_input_sha": sha256_text(judge_input),
        "score_row_sha": sha256_text(json.dumps(score_row, sort_keys=True, default=str)),
        "backbone_model": backbone_model,
        "decoding_params_sha": sha256_text(json.dumps(decoding_params, sort_keys=True)),
        "prompt_template_id": prompt_template_id,
        "retrieval_snapshot_id": retrieval_snapshot_id,
        "judge_model_version": judge_model_version,
        "scorer_config_id": scorer_config_id,
        "execution_seed": execution_seed,
    }
