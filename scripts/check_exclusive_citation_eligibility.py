#!/usr/bin/env python3
"""Print read-only samples from the generic retrieval classifiers."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.polaris_graph.retrieval.exclusive_citation_eligibility import (  # noqa: E402
    _unknown_row_has_journal_signal,
    known_non_journal_surface,
    known_preprint_or_working_paper_host,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--sample-size", type=int, default=15)
    args = parser.parse_args()

    with args.corpus.open(encoding="utf-8") as handle:
        evidence = json.load(handle).get("evidence") or []

    non_journal = [row for row in evidence if known_non_journal_surface(row)]
    preprint_hosts = [
        row for row in evidence if known_preprint_or_working_paper_host(row)
    ]
    journal_signals = [
        row for row in evidence if _unknown_row_has_journal_signal(row)
    ]
    print(f"rows={len(evidence)}")
    print(f"known_non_journal_surfaces={len(non_journal)}")
    print(f"known_preprint_or_working_paper_hosts={len(preprint_hosts)}")
    print(f"unknown_rows_with_journal_signal={len(journal_signals)}")
    print("non_journal_sample:")
    for row in non_journal[: args.sample_size]:
        print(f"- {row.get('title', '')}")
    print("journal_signal_sample:")
    for row in journal_signals[: args.sample_size]:
        print(f"- {row.get('title', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
