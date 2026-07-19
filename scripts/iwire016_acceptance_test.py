#!/usr/bin/env python
"""I-wire-016 (#1338) — OFFLINE pre-wiring acceptance gate for the render-seam predicate.

This is the §-1.3 precision=1.0 acceptance test. It is NOT a wiring step: it imports the
PRODUCTION render-seam predicate ``is_render_chrome_or_unrenderable`` exactly as the render
seam calls it, runs it over three labelled sets, and decides PASS/FAIL.

Sets
----
  * ``accept_chrome.json``      — POSITIVES (real page-furniture / chrome). Must be WITHHELD
                                  (flagged True). Drives ``chrome_recall``.
  * ``accept_truncation.json``  — POSITIVES (mid-word / cut-span truncations). Must be WITHHELD
                                  (flagged True). Drives ``truncation_recall``.
  * ``accept_content.json``     — NEGATIVES (real research findings). Must be KEPT (flagged
                                  False). Drives CONTENT-PRECISION.

Each item is a ``{"text": str, "class": str}`` row. ``class`` is informational; the set a row
belongs to is determined by which file it loads from (positives vs negatives), so the gate is
robust to label noise inside the positives.

The §-1.3 gate
--------------
  PASS iff  CONTENT-PRECISION == 1.0  (ZERO real findings flagged — the over-strip law: deleting a
            real finding is worse than leaking chrome)
       AND  ``chrome_recall`` and ``truncation_recall`` are both REPORTED (computed, not skipped).

The truncation leg in the predicate is corpus-grounded. With ``known_words=None`` (no evidence
basis) the boundary-cut leg no-ops safely and only the unambiguous-marker leg runs — exactly the
render-seam contract when no corpus vocabulary is available. We therefore call the predicate with
an EMPTY/None known-words basis built via ``build_corpus_vocabulary_from_evidence([])`` (returns an empty
set), proving the truncation leg degrades safely. This is intentional: the offline gate has no run
corpus, so it exercises the marker-only truncation signal, which must never over-flag real prose.

Usage
-----
    python scripts/iwire016_acceptance_test.py

Exit code 0 == PASS, 1 == FAIL (so CI / a wiring gate can consume it). DOES NOT wire anything.
"""
from __future__ import annotations

# Standard Library
import json
import sys
from pathlib import Path

# Ensure the repo root is importable when this script is run directly
# (``python scripts/iwire016_acceptance_test.py`` puts ``scripts/`` on sys.path, not the root).
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Local Modules
from src.polaris_graph.generator.weighted_enrichment import (  # noqa: E402
    build_corpus_vocabulary_from_evidence,
    is_render_chrome_or_unrenderable,
)

_AUDIT_DIR = Path(__file__).resolve().parent.parent / "outputs" / "audits" / "iwire016"
_CHROME_FILE = _AUDIT_DIR / "accept_chrome.json"
_TRUNCATION_FILE = _AUDIT_DIR / "accept_truncation.json"
_CONTENT_FILE = _AUDIT_DIR / "accept_content.json"


def _load_units(path: Path) -> list[dict]:
    """Load a labelled acceptance set (list of ``{text, class}`` rows). Raises FileNotFoundError if
    the file is absent (LAW II — fail loudly; a missing positive set must NOT silently pass the gate)
    and ValueError if the shape is wrong."""
    if not path.exists():
        raise FileNotFoundError(
            f"acceptance set missing: {path} (the gate cannot run without it — a sibling task "
            f"builds the positive sets; build them before running this gate)"
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{path}: expected a JSON list of {{text, class}} rows, got {type(raw)!r}")
    units: list[dict] = []
    for i, row in enumerate(raw):
        if not isinstance(row, dict) or "text" not in row:
            raise ValueError(f"{path}[{i}]: each row must be a dict with a 'text' field, got {row!r}")
        units.append(row)
    return units


def _flagged(units: list[dict], known_words: "set[str] | None") -> list[bool]:
    """Apply the PRODUCTION render-seam predicate to every unit. ``True`` == WITHHELD (chrome /
    truncation / unrenderable); ``False`` == KEPT (real renderable finding)."""
    return [
        is_render_chrome_or_unrenderable(u["text"], known_words=known_words)
        for u in units
    ]


def main() -> int:
    # The render-seam contract with no run corpus: an empty/None known-words basis. The truncation
    # boundary-cut leg no-ops safely (only the unambiguous-marker leg runs), so a real finding is
    # never flagged by a missing-corpus span guess.
    known_words = build_corpus_vocabulary_from_evidence([])  # -> empty set, == safe None-equivalent basis
    known_basis = known_words or None  # pass None when empty so the boundary leg is fully inert

    chrome_units = _load_units(_CHROME_FILE)
    truncation_units = _load_units(_TRUNCATION_FILE)
    content_units = _load_units(_CONTENT_FILE)

    # POSITIVES: must be WITHHELD (flagged True).
    chrome_flags = _flagged(chrome_units, known_basis)
    truncation_flags = _flagged(truncation_units, known_basis)
    # NEGATIVES: must be KEPT (flagged False).
    content_flags = _flagged(content_units, known_basis)

    n_chrome = len(chrome_units)
    n_truncation = len(truncation_units)
    n_content = len(content_units)

    chrome_recall = (sum(chrome_flags) / n_chrome) if n_chrome else 0.0
    truncation_recall = (sum(truncation_flags) / n_truncation) if n_truncation else 0.0
    # CONTENT-PRECISION = fraction of content (negative) units NOT flagged.
    content_kept = sum(1 for f in content_flags if not f)
    content_precision = (content_kept / n_content) if n_content else 0.0

    # The real findings the predicate WRONGLY withheld (the §-1.3 violations).
    false_positives = [
        content_units[i]["text"]
        for i, f in enumerate(content_flags)
        if f
    ]

    print("=" * 78)
    print("I-wire-016 (#1338) — render-seam predicate OFFLINE acceptance gate (§-1.3)")
    print("=" * 78)
    print(f"  chrome positives     : {n_chrome:4d}  flagged(withheld)={sum(chrome_flags):4d}"
          f"   chrome_recall      = {chrome_recall:.4f}")
    print(f"  truncation positives : {n_truncation:4d}  flagged(withheld)={sum(truncation_flags):4d}"
          f"   truncation_recall  = {truncation_recall:.4f}")
    print(f"  content negatives    : {n_content:4d}  kept(not flagged)={content_kept:4d}"
          f"   CONTENT-PRECISION  = {content_precision:.4f}")
    print("-" * 78)

    precision_ok = content_precision == 1.0
    recalls_reported = (n_chrome > 0) and (n_truncation > 0)

    if false_positives:
        print(f"  §-1.3 VIOLATION: {len(false_positives)} real finding(s) WRONGLY withheld "
              f"(content-precision must be 1.0):")
        for txt in false_positives[:20]:
            print(f"    - {txt[:140]}")
        if len(false_positives) > 20:
            print(f"    ... and {len(false_positives) - 20} more")

    if not recalls_reported:
        print("  RECALLS NOT REPORTED: a positive set is empty — chrome_recall and "
              "truncation_recall must both be computed over non-empty sets.")

    passed = precision_ok and recalls_reported
    print("-" * 78)
    print(f"  RESULT: {'PASS' if passed else 'FAIL'}  "
          f"(content_precision==1.0: {precision_ok}; recalls_reported: {recalls_reported})")
    print("=" * 78)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
