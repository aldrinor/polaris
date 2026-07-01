"""I-deepfix-001 WS-14 part 2 — DeepResearch-Bench-II (DRB-II) submission WRAPPER (thin, offline).

DRB-II is a REAL, official research-report benchmark (132 tasks / 9,415 expert rubric items, Gemini
rubric judge). It ships its own scorer, ``third_party/DeepResearch-Bench-II/run_evaluation.py``, which:
  * scans a ``--pdf_dir`` tree for ``<model>/idx-<N>.<ext>`` files (``.md``/``.txt``/``.html``/``.pdf``/
    ``.docx``/images),
  * reads each file's ARTICLE text as the ``<passage>`` to grade,
  * pulls the task text + rubric items + ``blocked`` reference from the catalog
    ``tasks_and_rubrics.jsonl`` keyed by the file's ``idx`` (NOT from the submission),
  * asks the Gemini judge for a THREE-WAY (1 / 0 / -1) score per rubric item,
  * appends per-idx results to ``--out_jsonl``.

This module is a THIN ADAPTER only. It does NOT re-implement DRB-II scoring — the official harness stays
the scorer (contrast the DeepTRACE module, which is a re-implementation because DeepTRACE has NO public
scorer). Two responsibilities, both PURE / OFFLINE:

  1. ``build_drbii_submission(report_markdown, task_id, references)`` -> the DRB-II-shaped submission dict
     (article text + DRB-II task idx + normalized reference list + the on-disk ``idx-<N>.md`` filename).
  2. ``drbii_score_command(submission_path, out_path)`` -> the argv that invokes ``run_evaluation.py`` at
     benchmark time. The harness path is parameterized by ``PG_DRBII_EVAL_SCRIPT`` (default: a documented
     placeholder path). The wrapper NEVER imports or requires the harness / Gemini / network at
     import/test time — the actual scoring runs later on the VM.

``write_drbii_submission`` is a convenience materializer that writes the dict into the exact on-disk layout
the harness scans. It is a plain file write (offline).

Honesty / faithfulness notes:
  * task_id IS the DRB-II ``idx``. The run-id <-> idx offset is REAL (run id "task72" is DRB-II idx 56).
    This wrapper does NOT transform ids — the caller passes the resolved DRB-II ``idx``. A wrong idx would
    score the report against the wrong task's rubrics (the §-1.4 silently-wrong-number class); build-time
    validation guards only the shape, not the id-resolution (that lives in ``pack_drb2.py``).
  * ``references`` are OUR article's cited sources, captured for provenance and so a downstream check can
    compare them against the task's ``blocked`` reference. They are NOT the ``blocked`` field (which the
    harness reads from its own catalog).
  * No kill-switch: this is a NEW standalone eval-tooling module with ZERO import into the runtime
    pipeline, so it changes no existing pipeline behavior. The faithfulness engine is untouched.
  * LAW VI: every path/name is env-overridable; nothing is hard-coded into behavior.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

# --- Documented PLACEHOLDER defaults (overridable via env; the wrapper never requires these to exist). ---
# The official DRB-II harness lives OUTSIDE this module's import graph. At benchmark time on the VM, set
# PG_DRBII_EVAL_SCRIPT to the real run_evaluation.py. These defaults are documented placeholders so the
# wrapper stays offline-safe (no filesystem/import dependency) at import/test time.
DEFAULT_EVAL_SCRIPT = "third_party/DeepResearch-Bench-II/run_evaluation.py"
DEFAULT_TASKS_JSONL = "third_party/DeepResearch-Bench-II/tasks_and_rubrics.jsonl"
DEFAULT_MODEL_NAME = "polaris"
SUBMISSION_SCHEMA_VERSION = "drbii-1"

# The official harness's per-file idx pattern is ``^idx-(\d+)(?:\..+)?$`` (run_evaluation.py). The
# submission filename MUST match it, else the harness silently skips the file.
_SUBMISSION_FILENAME_TEMPLATE = "idx-{idx}.md"


def _coerce_task_idx(task_id: Any) -> int:
    """Return the DRB-II integer idx, FAILING LOUD on a non-integer / negative value. A malformed idx
    would produce a filename the harness cannot key to a task (silent skip / wrong rubric)."""
    try:
        idx = int(task_id)
    except (TypeError, ValueError):
        raise ValueError(
            f"[drbii_wrapper] task_id must be the integer DRB-II idx, got {task_id!r}. "
            f"Pass the catalog `idx` (the run id 'task72' is idx 56 — resolve the offset upstream)."
        )
    if idx < 0:
        raise ValueError(f"[drbii_wrapper] task_id (DRB-II idx) must be >= 0, got {idx}.")
    return idx


def _normalize_one_reference(ref: Any, position: int) -> dict[str, Any]:
    """Normalize a single reference to ``{id, title, url, authors}``. Accepts a mapping (any subset of
    id/title/url/authors) or a bare string (a URL if it looks like one, else a title)."""
    default_id = f"ref_{position}"
    if isinstance(ref, Mapping):
        url = str(ref.get("url") or "").strip()
        title = str(ref.get("title") or "").strip()
        authors_raw = ref.get("authors") or []
        if isinstance(authors_raw, (str, bytes)):
            authors = [str(authors_raw).strip()] if str(authors_raw).strip() else []
        elif isinstance(authors_raw, Sequence):
            authors = [str(a).strip() for a in authors_raw if str(a).strip()]
        else:
            authors = []
        ref_id = str(ref.get("id") or ref.get("evidence_id") or default_id).strip() or default_id
        return {"id": ref_id, "title": title, "url": url, "authors": authors}
    # bare string
    text = str(ref).strip()
    if text.lower().startswith(("http://", "https://")):
        return {"id": default_id, "title": "", "url": text, "authors": []}
    return {"id": default_id, "title": text, "url": "", "authors": []}


def _normalize_references(references: Any) -> list[dict[str, Any]]:
    """Normalize the reference list. ``None`` -> ``[]``. A single mapping/string is wrapped in a list."""
    if references is None:
        return []
    if isinstance(references, (Mapping, str, bytes)):
        references = [references]
    if not isinstance(references, Sequence):
        raise ValueError(
            f"[drbii_wrapper] references must be a list of dicts/strings (or None), got {type(references)}."
        )
    return [_normalize_one_reference(r, i + 1) for i, r in enumerate(references)]


def build_drbii_submission(
    report_markdown: str,
    task_id: Any,
    references: Any = None,
    *,
    model: str = DEFAULT_MODEL_NAME,
) -> dict[str, Any]:
    """Prepare a POLARIS rendered report into the DRB-II submission shape (PURE / OFFLINE).

    The returned dict is the structured POLARIS-side representation of one DRB-II submission item:
      * ``article``     : the report markdown text the Gemini judge grades as ``<passage>``.
      * ``task_id`` / ``idx`` : the DRB-II catalog idx this report answers (the caller resolves the
        run-id <-> idx offset; this wrapper does not transform it).
      * ``references``  : normalized cited-source list (id/title/url/authors) — provenance + a hook to
        cross-check against the task's ``blocked`` reference at score time.
      * ``model`` / ``submission_filename`` : the on-disk layout ``<model>/idx-<idx>.md`` the harness scans.
      * honesty fields: ``scorer`` (the official harness) and ``reimplemented=False``.

    ``write_drbii_submission`` materializes this dict into that on-disk layout for the scorer.
    """
    if report_markdown is None:
        raise ValueError("[drbii_wrapper] report_markdown must be a string, got None (fail loud).")
    article = str(report_markdown)
    idx = _coerce_task_idx(task_id)
    refs = _normalize_references(references)
    model_name = str(model or DEFAULT_MODEL_NAME).strip() or DEFAULT_MODEL_NAME
    filename = _SUBMISSION_FILENAME_TEMPLATE.format(idx=idx)
    return {
        "schema_version": SUBMISSION_SCHEMA_VERSION,
        "benchmark": "deepresearch-bench-ii",
        # ---- the scored payload ----
        "article": article,
        "task_id": idx,
        "idx": idx,
        "references": refs,
        # ---- on-disk layout the harness scans (<pdf_dir>/<model>/idx-<idx>.md) ----
        "model": model_name,
        "submission_filename": filename,
        "submission_relpath": f"{model_name}/{filename}",
        # ---- convenience metadata ----
        "article_char_count": len(article),
        "n_references": len(refs),
        # ---- honesty / provenance ----
        "scorer": "third_party/DeepResearch-Bench-II/run_evaluation.py (official Gemini rubric judge)",
        "reimplemented": False,
    }


def write_drbii_submission(submission: Mapping[str, Any], out_dir: str | os.PathLike[str]) -> Path:
    """Materialize a submission dict into ``out_dir/<model>/idx-<idx>.md`` (the layout the harness scans).

    Plain file write — offline, no network, no harness import. Returns the written path. ``out_dir`` is the
    ``--pdf_dir`` root you later pass to :func:`drbii_score_command`."""
    relpath = str(submission.get("submission_relpath") or "").strip()
    if not relpath:
        model = str(submission.get("model") or DEFAULT_MODEL_NAME)
        filename = str(submission.get("submission_filename") or "")
        if not filename:
            raise ValueError("[drbii_wrapper] submission is missing submission_filename/relpath.")
        relpath = f"{model}/{filename}"
    article = submission.get("article")
    if article is None:
        raise ValueError("[drbii_wrapper] submission is missing 'article' text.")
    out_path = Path(out_dir) / relpath
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(str(article), encoding="utf-8")
    return out_path


def drbii_score_command(
    submission_path: str | os.PathLike[str],
    out_path: str | os.PathLike[str],
    *,
    eval_script: Optional[str] = None,
    tasks_jsonl: Optional[str] = None,
    python_executable: Optional[str] = None,
    extra_args: Optional[Sequence[str]] = None,
) -> list[str]:
    """Return the argv to invoke the OFFICIAL DRB-II ``run_evaluation.py`` (does NOT run it).

    ``submission_path`` is the ``--pdf_dir`` ROOT that contains ``<model>/idx-<N>.md`` (NOT a single file —
    the harness scans first-level subdirectories). ``out_path`` is the ``--out_jsonl`` results file.

    Parameterization (LAW VI, all env-overridable; a documented placeholder default so nothing is required
    to exist at build time):
      * eval_script      <- ``eval_script`` arg or ``PG_DRBII_EVAL_SCRIPT`` env or ``DEFAULT_EVAL_SCRIPT``.
      * tasks_jsonl      <- ``tasks_jsonl`` arg or ``PG_DRBII_TASKS_JSONL`` env or ``DEFAULT_TASKS_JSONL``.
      * python_executable<- ``python_executable`` arg or ``PG_DRBII_PYTHON`` env or ``sys.executable``.

    No filesystem checks, no harness import — pure argv construction, offline-safe. The returned list is
    handed to ``subprocess`` on the VM at benchmark time."""
    script = eval_script or os.getenv("PG_DRBII_EVAL_SCRIPT") or DEFAULT_EVAL_SCRIPT
    tasks = tasks_jsonl or os.getenv("PG_DRBII_TASKS_JSONL") or DEFAULT_TASKS_JSONL
    python_exe = python_executable or os.getenv("PG_DRBII_PYTHON") or sys.executable or "python"
    argv = [
        str(python_exe),
        str(script),
        "--pdf_dir",
        str(submission_path),
        "--out_jsonl",
        str(out_path),
        "--tasks_jsonl",
        str(tasks),
    ]
    if extra_args:
        argv.extend(str(a) for a in extra_args)
    return argv
