"""Insight-density instrument: distinct WORKS cited per 1000 words.

Fable's pre-registered falsifier for the depth levers. Word count alone cannot tell a
deeper report from a padded one -- a run can double its length by restating the same
finding against more sources. Density can: it only rises if the report brings in
genuinely new works.

WORKS, NOT BIBLIOGRAPHY ENTRIES. The bibliography over-counts: one paper occupies several
entries when the corpus holds mirror rows of it (Brynjolfsson/Li/Raymond took SIX slots in
rank7). Reporting entries as "distinct sources" is how a 73-work report gets sold as a
107-source one. Collapse mirrors first, three ways, in order:
  1. same_work_groups from the corpus (authoritative -- the corpus already knows).
  2. DOI, when present (authoritative across mirrors).
  3. normalized title (the fallback: lowercased, stripped of punctuation and an "(also
     mirrored)" suffix, truncated -- catches mirrors the corpus never grouped).
Only entries actually CITED in the prose count. An uncited bibliography entry is not a
source the report used; counting it would re-inflate exactly the number this exists to
deflate.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_MARKER_RE = re.compile(r"\[(\d+)\]")
_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")
_MIRROR_SUFFIX_RE = re.compile(r"\(also mirrored\)", re.IGNORECASE)
# The reference list is part of report.md. Everything from this heading on is NOT prose.
_REFS_HEADING_RE = re.compile(r"^#{1,3}\s+(references|bibliography)\s*$", re.IGNORECASE | re.MULTILINE)


def _norm_title(title: str) -> str:
    t = _MIRROR_SUFFIX_RE.sub(" ", str(title or "")).lower()
    t = _PUNCT_RE.sub(" ", t)
    t = _WS_RE.sub(" ", t).strip()
    return t[:70]


def _entries(bib: object) -> list[dict]:
    if isinstance(bib, list):
        return [e for e in bib if isinstance(e, dict)]
    if isinstance(bib, dict):
        for key in ("entries", "bibliography", "items"):
            v = bib.get(key)
            if isinstance(v, list):
                return [e for e in v if isinstance(e, dict)]
    return []


def _work_key(entry: dict, work_of: dict[str, str]) -> str:
    ev = str(entry.get("evidence_id") or entry.get("ev_id") or "")
    if ev in work_of:
        return work_of[ev]
    doi = str(entry.get("doi") or "").strip().lower()
    if doi:
        return f"doi:{doi}"
    title = _norm_title(entry.get("title") or "")
    if title:
        return f"t:{title}"
    return f"ev:{ev}"


def _same_work_map(corpus_path: Path) -> dict[str, str]:
    """ev_id -> work key, from the corpus's own same_work_groups.

    The groups arrive as DICTS with ``member_evidence_ids`` -- not bare id lists. A version
    of this that assumed bare lists would match nothing and silently report zero mirrors,
    which reads identical to a corpus that genuinely has none.
    """
    if not corpus_path.exists():
        return {}
    corpus = json.loads(corpus_path.read_text())
    groups = corpus.get("same_work_groups") if isinstance(corpus, dict) else None
    out: dict[str, str] = {}
    for g in groups or []:
        if not isinstance(g, dict):
            continue
        members = g.get("member_evidence_ids") or []
        if not members:
            continue
        key = g.get("same_work_id") or g.get("canonical_index") or members[0]
        for m in members:
            out[str(m)] = f"w:{key}"
    return out


def density(run_dir: Path, corpus_path: Path) -> dict:
    report = (run_dir / "report.md").read_text()
    bib = json.loads((run_dir / "bibliography.json").read_text())
    entries = _entries(bib)
    work_of = _same_work_map(corpus_path)

    # BODY ONLY. report.md ends with a numbered "## References" list, so a marker regex over
    # the whole file re-reads the bibliography as prose and reports EVERY entry as cited --
    # cited==bib for every arm, which is the tell. Both the citation count and the word count
    # must exclude the reference list, or density is measured against the wrong denominator.
    body = _REFS_HEADING_RE.split(report)[0]

    # Prose cites by NUMERIC MARKER ([12]), never by ev_id -- an ev_\d+ regex over report.md
    # matches nothing and silently reports zero. Markers are 1-indexed into the bibliography.
    cited_markers = {int(m) for m in _MARKER_RE.findall(body)}
    cited_entries = [e for i, e in enumerate(entries, start=1) if i in cited_markers]

    words = len(body.split())
    works = {_work_key(e, work_of) for e in cited_entries}
    per_1k = 1000.0 * len(works) / words if words else 0.0
    return {
        "run": run_dir.name,
        "words": words,
        "bib_entries": len(entries),
        "cited_entries": len(cited_entries),
        "distinct_works": len(works),
        "works_per_1k_words": round(per_1k, 2),
        "entry_inflation": round(len(cited_entries) / len(works), 2) if works else 0.0,
    }


def main() -> int:
    corpus = Path(sys.argv[1])
    rows = [density(Path(d), corpus) for d in sys.argv[2:]]
    hdr = f'{"run":26}{"words":>7}{"bib":>5}{"cited":>7}{"works":>7}{"works/1k":>10}{"inflation":>11}'
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(
            f'{r["run"]:26}{r["words"]:>7}{r["bib_entries"]:>5}{r["cited_entries"]:>7}'
            f'{r["distinct_works"]:>7}{r["works_per_1k_words"]:>10}{r["entry_inflation"]:>10}x'
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
