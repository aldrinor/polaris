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

# ── Question-lineage selector (Stage-0 lineage seam) ─────────────────────────
# ``PG_BENCHMARK_QUESTION_LINEAGE`` chooses WHICH canonical question a benchmark slug binds
# to. It is read with an IN-PROCESS DEFAULT (never written to env / never serialized) so the
# default path gains no artifact key and stays byte-for-byte identical to HEAD:
#   * ``drb_ii_idx``        (default) — today's behavior: bind to the DeepResearch-Bench-II
#                                        canonical question by idx (SLUG_TO_IDX + DEFAULT_TASKS_PATH).
#   * ``legacy_race_task``            — bind to the legacy DeepResearch-Bench (RACE) task question
#                                        (SLUG_TO_LEGACY_TASK id in query.jsonl), so a Gate-B/V30 run
#                                        answers the legacy task and is scored by score_report_race.py
#                                        --task-id <n>. NO content lever — only WHICH question text the
#                                        resolver returns changes; every faithfulness gate is untouched.
LINEAGE_SELECTOR_ENV = "PG_BENCHMARK_QUESTION_LINEAGE"
LINEAGE_DRB_II_IDX = "drb_ii_idx"          # in-process default (byte-identical to HEAD)
LINEAGE_LEGACY_RACE_TASK = "legacy_race_task"
ALLOWED_LINEAGES: frozenset[str] = frozenset({LINEAGE_DRB_II_IDX, LINEAGE_LEGACY_RACE_TASK})

# slug -> legacy DeepResearch-Bench (RACE) task id, resolved from the legacy tasks file
# (``query.jsonl``, keyed by ``id``). Only slugs with an EXPLICIT legacy mapping may run under
# ``legacy_race_task`` — a legacy/slug pair with no entry FAILS LOUD (never a guessed id). The
# legacy id is the RACE ``--task-id`` (task-72), NOT the DRB-II idx (56); the two are different
# lineages by construction — a legacy run must NEVER be labelled ``canonical_idx=56``.
SLUG_TO_LEGACY_TASK: dict[str, int] = {
    "drb_72_ai_labor": 72,
}

# Legacy tasks file (the DeepResearch-Bench RACE ``query.jsonl``, keyed by ``id`` + ``prompt``).
# Resolved through the ``third_party/deep_research_bench`` symlink; fail-loud if absent.
DEFAULT_LEGACY_TASKS_PATH = os.path.join(
    "third_party", "deep_research_bench", "data", "prompt_data", "query.jsonl"
)


def resolve_lineage(lineage: str | None) -> str:
    """Normalize + validate a lineage selector value (in-process default ``drb_ii_idx``).

    ``None``/empty => the default ``drb_ii_idx`` (HEAD behavior). An unknown value FAILS LOUD
    (never a silent fallback to default — a typo'd selector must not silently score the wrong
    lineage). Callers pass this through the resolver so branching happens in ONE place.
    """
    value = (lineage or LINEAGE_DRB_II_IDX).strip() or LINEAGE_DRB_II_IDX
    if value not in ALLOWED_LINEAGES:
        raise GateZeroLineageError(
            f"GATE0: unknown {LINEAGE_SELECTOR_ENV} lineage {value!r} — allowed: "
            f"{sorted(ALLOWED_LINEAGES)}. Fix the selector (never guess the lineage)."
        )
    return value


def lineage_from_env() -> str:
    """The effective lineage from the env selector (in-process default ``drb_ii_idx``).

    Read at CALL time (LAW VI) so a slate/operator override after import wins. The default is
    NOT written back to env, so a default run's serialized artifacts gain no selector key."""
    return resolve_lineage(os.getenv(LINEAGE_SELECTOR_ENV, "").strip() or None)

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


def assert_legacy_slug_supported(slug: str) -> None:
    """Fail loud (under ``legacy_race_task``) if a benchmark slug has NO legacy mapping.

    The SHARED legacy-registration seam: EVERY ``drb_*`` benchmark slug absent from
    ``SLUG_TO_LEGACY_TASK`` is rejected — a canonically-mapped slug (``SLUG_TO_IDX``) AND an
    explicit no-gold slug (``DRB_SLUGS_WITHOUT_CANONICAL_GOLD``) alike. Without this, a no-gold
    slug such as ``drb_90_adas_liability`` (a benchmark, in neither ``SLUG_TO_IDX`` nor
    ``SLUG_TO_LEGACY_TASK``) would slip PAST both legacy override branches and silently launch its
    hardcoded DRB-II question under a legacy run — the split-brain this seam exists to prevent.
    Both Gate-B and the direct sweep call THIS one helper so their legacy rejection cannot drift
    apart. Non-benchmark sweep slugs are ignored (never gated). Caller invokes it only when the
    resolved lineage is ``legacy_race_task``; the default path never reaches it (byte-identical).
    """
    if not is_benchmark_slug(slug):
        return
    if slug in SLUG_TO_LEGACY_TASK:
        return
    raise GateZeroLineageError(
        f"GATE0: benchmark slug {slug!r} has NO legacy mapping in SLUG_TO_LEGACY_TASK but "
        f"{LINEAGE_SELECTOR_ENV}={LINEAGE_LEGACY_RACE_TASK} was requested — refusing to run it "
        f"(a benchmark slug with no legacy id would silently answer its DRB-II idx question = "
        f"split brain). Register the slug's legacy query.jsonl id in SLUG_TO_LEGACY_TASK, or run "
        f"it under {LINEAGE_SELECTOR_ENV}={LINEAGE_DRB_II_IDX}."
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


def questions_raw_and_sha_equal(a: str, b: str) -> bool:
    """True iff two questions are RAW-byte equal AND normalized-SHA equal.

    ``sha256_text`` normalizes whitespace first (``_normalize``), so a SHA match alone accepts
    whitespace drift (``"LEGACY   Q"`` vs ``"LEGACY Q"``). Where v2 requires that the registered
    legacy question and the packed/answered/canonical evidence be the SAME bytes — not merely the
    same normalized text — this asserts BOTH: raw string identity (``a == b``) AND the normalized
    SHA (a cheap collision-free re-check on identical inputs). Callers that only need normalized
    equivalence keep using ``sha256_text``; this is the strict RAW gate.
    """
    return a == b and sha256_text(a) == sha256_text(b)


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


def load_legacy_task_question(
    task_id: int, legacy_tasks_path: str = DEFAULT_LEGACY_TASKS_PATH
) -> str:
    """Return the legacy DeepResearch-Bench (RACE) task prompt for a task ``id``, from query.jsonl.

    The legacy file is keyed by ``id`` (NOT ``idx``) and carries the prompt under ``prompt`` —
    the SAME record score_report_race.py --task-id scores against. Fails loud if the file is
    missing or the id is absent (never a silent default), mirroring ``load_canonical_question``.
    """
    if not os.path.isfile(legacy_tasks_path):
        raise GateZeroLineageError(
            f"GATE0: legacy tasks file not found: {legacy_tasks_path} — cannot resolve the "
            f"legacy_race_task question (verify the third_party/deep_research_bench symlink)"
        )
    with open(legacy_tasks_path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("id") == task_id:
                prompt = record.get("prompt")
                if not prompt:
                    raise GateZeroLineageError(
                        f"GATE0: legacy task id={task_id} present but has empty 'prompt' in "
                        f"{legacy_tasks_path}"
                    )
                return prompt
    raise GateZeroLineageError(
        f"GATE0: legacy task id={task_id} not found in legacy tasks file {legacy_tasks_path}"
    )


def canonical_question_for_slug(
    slug: str,
    tasks_path: str = DEFAULT_TASKS_PATH,
    *,
    lineage: str = LINEAGE_DRB_II_IDX,
    legacy_tasks_path: str = DEFAULT_LEGACY_TASKS_PATH,
) -> str:
    """Canonical question for a benchmark slug, per the ``lineage`` selector.

    ``drb_ii_idx`` (default): the DeepResearch-Bench-II canonical question by idx (SLUG_TO_IDX +
    ``tasks_path``) — byte-identical to HEAD. ``legacy_race_task``: the legacy DeepResearch-Bench
    (RACE) task question (SLUG_TO_LEGACY_TASK id in ``legacy_tasks_path``). A legacy/slug pair with
    NO legacy mapping FAILS LOUD (never a guessed id). Positional ``(slug, tasks_path)`` stays valid;
    ``lineage``/``legacy_tasks_path`` are keyword-only.
    """
    resolved = resolve_lineage(lineage)
    if resolved == LINEAGE_LEGACY_RACE_TASK:
        if slug not in SLUG_TO_LEGACY_TASK:
            raise GateZeroLineageError(
                f"GATE0: slug {slug!r} has no legacy_race_task mapping — add it to "
                f"SLUG_TO_LEGACY_TASK (the legacy query.jsonl id) before running under "
                f"{LINEAGE_SELECTOR_ENV}={LINEAGE_LEGACY_RACE_TASK} (never guess the id)"
            )
        return load_legacy_task_question(SLUG_TO_LEGACY_TASK[slug], legacy_tasks_path)
    if slug not in SLUG_TO_IDX:
        raise GateZeroLineageError(
            f"GATE0: slug {slug!r} has no canonical idx mapping — resolve it from the gold "
            f"file and add it to SLUG_TO_IDX before running (never guess the idx)"
        )
    return load_canonical_question(SLUG_TO_IDX[slug], tasks_path)


def assert_launched_question_is_canonical(
    slug: str,
    launched_question: str,
    tasks_path: str = DEFAULT_TASKS_PATH,
    *,
    lineage: str = LINEAGE_DRB_II_IDX,
    legacy_tasks_path: str = DEFAULT_LEGACY_TASKS_PATH,
) -> str:
    """Fail loud unless the launched question equals the canonical question for the slug.

    Returns the canonical question (so callers can launch THAT, not a hardcoded copy).
    This is the structural fix for the drb_72 wrong-question bug. ``lineage`` selects which
    canonical the launched question must equal (default ``drb_ii_idx`` = HEAD).
    """
    canonical = canonical_question_for_slug(
        slug, tasks_path, lineage=lineage, legacy_tasks_path=legacy_tasks_path
    )
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
    *,
    lineage: str = LINEAGE_DRB_II_IDX,
    legacy_tasks_path: str = DEFAULT_LEGACY_TASKS_PATH,
) -> None:
    """Fail loud unless packed == answered == canonical (the split-brain guard).

    `packed_question` = the question handed to the judge/scorer pack.
    `answered_question` = the question the report (corpus_snapshot) actually answered.
    Both must equal the canonical question for the ``lineage`` (default ``drb_ii_idx`` = HEAD;
    ``legacy_race_task`` = the legacy query.jsonl task), or the score is meaningless.
    """
    canonical = canonical_question_for_slug(
        slug, tasks_path, lineage=lineage, legacy_tasks_path=legacy_tasks_path
    )
    # v2 requires BOTH raw-byte equality AND normalized-SHA equality for the packed/answered/
    # canonical evidence — a SHA-only check accepts whitespace drift (the sha is over normalized
    # text), which is exactly the split-brain latitude this guard must refuse. packed == answered
    # == canonical as RAW bytes, or the score is meaningless.
    packed_ok = questions_raw_and_sha_equal(packed_question, canonical)
    answered_ok = questions_raw_and_sha_equal(answered_question, canonical)
    if not (packed_ok and answered_ok):
        c = sha256_text(canonical)
        raise GateZeroLineageError(
            "GATE0 SPLIT-BRAIN: packed/answered/canonical question mismatch for slug "
            f"{slug!r} (raw-byte AND normalized-SHA equality required).\n  "
            f"canonical(sha)={c[:16]}\n  packed   ={'OK' if packed_ok else 'MISMATCH'} "
            f"(sha={sha256_text(packed_question)[:16]})\n  answered ="
            f"{'OK' if answered_ok else 'MISMATCH'} (sha={sha256_text(answered_question)[:16]})"
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
    lineage: str = LINEAGE_DRB_II_IDX,
    legacy_tasks_path: str = DEFAULT_LEGACY_TASKS_PATH,
) -> dict[str, Any]:
    """Build the immutable lineage manifest for a benchmark run.

    Hashes the full artifact chain (task -> question -> answer -> report -> judge input ->
    score) PLUS the reproducibility surface (backbone model, decoding, template, retrieval
    snapshot, judge model/version, scorer config, seed). Asserts canonical equality first (for
    the selected ``lineage``), so a manifest cannot be built for a wrong-question or split-brain
    run. Records the lineage; a ``legacy_race_task`` run is labelled by its legacy task id + is
    NEVER labelled ``canonical_idx`` (the DRB-II idx is a DIFFERENT lineage).
    """
    resolved_lineage = resolve_lineage(lineage)
    canonical = assert_launched_question_is_canonical(
        slug, launched_question, tasks_path,
        lineage=resolved_lineage, legacy_tasks_path=legacy_tasks_path,
    )
    assert_no_split_brain(
        slug, packed_question, answered_question, tasks_path,
        lineage=resolved_lineage, legacy_tasks_path=legacy_tasks_path,
    )
    if resolved_lineage == LINEAGE_LEGACY_RACE_TASK:
        # LEGACY: record the lineage + legacy task id; NEVER label it ``canonical_idx`` (that is
        # the DRB-II idx — a DIFFERENT lineage; labelling a legacy run canonical_idx=56 is the
        # split-brain this seam exists to prevent).
        lineage_label: dict[str, Any] = {
            "lineage": resolved_lineage,
            "legacy_task_id": SLUG_TO_LEGACY_TASK[slug],
        }
    else:
        # DEFAULT (drb_ii_idx): BYTE-IDENTICAL to HEAD — the manifest carries ``canonical_idx``
        # immediately after ``slug`` and gains NO ``lineage`` key (the default path adds no key).
        lineage_label = {
            "canonical_idx": SLUG_TO_IDX[slug],
        }
    return {
        "slug": slug,
        **lineage_label,
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
