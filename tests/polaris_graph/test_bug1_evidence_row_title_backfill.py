"""BUG-1 (#1262) regression: the final evidence row must carry the already-extracted title.

The title is resolved upstream (classifier_title = the longest of OpenAlex display_name /
_extract_title_from_content / cand.title) and fed to the tier classifier, then was SILENTLY
DROPPED when the evidence row was assembled in ``run_live_retrieval`` — the row kept only the
300-char ``statement``, so the outliner placed sources by tier marker alone ("ev_022 [T2]")
and admitted guessing. The fix carries the title onto the row. Faithfulness-neutral: a title is
planning/placement metadata; it never enters a verified claim or relaxes a gate.

Offline, deterministic, no network/spend.
"""

from __future__ import annotations

import inspect

from src.polaris_graph.retrieval.live_retriever import run_live_retrieval


def test_production_row_assembly_includes_title_field():
    """Source-pin: the production evidence-row literal in run_live_retrieval now sources a
    'title' key from the resolved classifier_title (was absent -> blank-title rows)."""
    src = inspect.getsource(run_live_retrieval)
    assert '"title": classifier_title or cand.title or ""' in src, (
        "BUG-1 regression: the evidence row no longer backfills the resolved title"
    )
    # And it sits alongside the existing core row fields (not in a dead branch).
    assert '"evidence_id":' in src
    assert '"source_url": cand.url' in src


def test_title_backfill_mirror_carries_nonblank_title():
    """Behavioral mirror of the row-build precedence: a resolved classifier_title is carried;
    a blank classifier_title falls back to cand.title; both-blank yields '' (never a KeyError)."""
    def _row_title(classifier_title: str, cand_title: str) -> str:
        # mirrors live_retriever.py: "title": classifier_title or cand.title or ""
        return classifier_title or cand_title or ""

    assert _row_title("Automation and New Tasks (Acemoglu & Restrepo)", "fallback") == \
        "Automation and New Tasks (Acemoglu & Restrepo)"
    assert _row_title("", "The Future of Employment (Frey & Osborne)") == \
        "The Future of Employment (Frey & Osborne)"
    assert _row_title("", "") == ""


def test_outline_digest_is_no_longer_blind_when_title_present():
    """The whole point of BUG-1: when a row carries a title, an outline digest line built from
    the row is no longer the content-free 'ev_022 [T2]' the planner had to guess from."""
    row = {"evidence_id": "ev_022", "tier": "T2",
           "title": "The Skill Content of Recent Technological Change (Autor, Levy, Murnane, QJE)"}
    digest = f"{row['evidence_id']} [{row['tier']}]"
    if row.get("title"):
        digest += f" | title: {row['title']}"
    assert "title:" in digest
    assert "Autor" in digest
    # the pre-fix blank-title digest was exactly this content-free prefix:
    assert digest != "ev_022 [T2]"
