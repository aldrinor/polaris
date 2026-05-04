"""Load manually-exported ChatGPT/Gemini DR outputs for BEAT-BOTH scoring.

Per `.codex/slices/slice_005/architecture_proposal.md` §"external_loader".

Operators run benchmark questions against ChatGPT Deep Research and
Gemini DR via the respective web UIs and save outputs as plain .txt
files named `{question_id}.txt` in a per-system directory:

    external_outputs/chatgpt/Q01_aspirin_migraine_efficacy.txt
    external_outputs/chatgpt/Q02_metformin_safety_older_adults.txt
    external_outputs/gemini/Q01_aspirin_migraine_efficacy.txt
    ...

Missing files are non-fatal: the benchmark continues with N/A entries
in the scoreboard for those question×system pairs. Operators can
re-export later and re-run scoring.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

_LOG = logging.getLogger(__name__)


# Per-output cap. Real ChatGPT/Gemini DR responses are typically 5-50KB
# of text; cap protects against pasted-debug-output / Word-doc
# accidents in the input directory.
MAX_OUTPUT_BYTES = 1 * 1024 * 1024  # 1 MB


@dataclass(frozen=True)
class ExternalLoadReport:
    """Result of loading a per-system output dir.

    Used by report_renderer to display "X of N questions had outputs"
    so operators can see what's missing.
    """

    system_name: str
    output_dir: Path
    expected_question_ids: tuple[str, ...]
    loaded: dict[str, str]                 # question_id -> text
    missing_question_ids: tuple[str, ...]
    extra_files: tuple[str, ...]           # files in dir not matching expected ids
    truncated_question_ids: tuple[str, ...]  # files exceeding MAX_OUTPUT_BYTES

    def coverage_ratio(self) -> float:
        if not self.expected_question_ids:
            return 1.0
        return len(self.loaded) / len(self.expected_question_ids)


def load_external_outputs(
    system_name: str,
    output_dir: Path | None,
    expected_question_ids: list[str],
) -> ExternalLoadReport:
    """Load .txt files from `output_dir` matching `expected_question_ids`.

    Args:
        system_name: e.g. 'chatgpt' or 'gemini' — used for diagnostics.
        output_dir: directory containing {question_id}.txt files. None
            means no outputs available; returns empty load report.
        expected_question_ids: list of question_id strings the benchmark
            cares about. Files with other names go into `extra_files`.

    Returns:
        ExternalLoadReport with loaded dict + missing list + extras +
        truncated. Never raises on missing files; missing is recorded.

    Raises:
        ValueError if `output_dir` exists but is not a directory.
    """
    if output_dir is None:
        return ExternalLoadReport(
            system_name=system_name,
            output_dir=Path("/dev/null"),
            expected_question_ids=tuple(expected_question_ids),
            loaded={},
            missing_question_ids=tuple(expected_question_ids),
            extra_files=(),
            truncated_question_ids=(),
        )

    output_dir = Path(output_dir)
    if not output_dir.exists():
        _LOG.warning(
            "external output dir %s does not exist; treating as empty",
            output_dir,
        )
        return ExternalLoadReport(
            system_name=system_name,
            output_dir=output_dir,
            expected_question_ids=tuple(expected_question_ids),
            loaded={},
            missing_question_ids=tuple(expected_question_ids),
            extra_files=(),
            truncated_question_ids=(),
        )
    if not output_dir.is_dir():
        raise ValueError(
            f"external output path {output_dir} exists but is not a directory"
        )

    expected_set = set(expected_question_ids)
    loaded: dict[str, str] = {}
    truncated: list[str] = []
    extras: list[str] = []

    for child in sorted(output_dir.iterdir()):
        if not child.is_file():
            continue
        if child.suffix.lower() != ".txt":
            extras.append(child.name)
            continue
        qid = child.stem  # filename without .txt
        if qid not in expected_set:
            extras.append(child.name)
            continue
        try:
            data = child.read_bytes()
        except OSError as exc:
            _LOG.warning("failed to read %s: %s", child, exc)
            continue
        if len(data) > MAX_OUTPUT_BYTES:
            truncated.append(qid)
            data = data[:MAX_OUTPUT_BYTES]
        try:
            loaded[qid] = data.decode("utf-8", errors="replace")
        except UnicodeDecodeError:
            # errors='replace' should never raise, but defensive
            loaded[qid] = data.decode("latin-1", errors="replace")

    missing = sorted(expected_set - set(loaded.keys()))

    return ExternalLoadReport(
        system_name=system_name,
        output_dir=output_dir,
        expected_question_ids=tuple(expected_question_ids),
        loaded=loaded,
        missing_question_ids=tuple(missing),
        extra_files=tuple(sorted(extras)),
        truncated_question_ids=tuple(sorted(truncated)),
    )
