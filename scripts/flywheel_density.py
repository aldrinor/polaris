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
# Scrape prefixes a search engine prepends to a mirrored copy of a paper ("[PDF] Automation ...").
_SCRAPE_PREFIX_RE = re.compile(r"^\s*\[(pdf|html|doc|epub)\]\s*", re.IGNORECASE)
# DRB task 72 instructs: cite only high-quality, English-language JOURNAL articles. Tier compliance
# is therefore an instruction-following metric, not a nicety -- RACE grades it.
_QUALITY_TIERS = frozenset({"T1", "T2", "T3"})
# Mirrors disagree on the tail of a title (the corpus truncates them), so match on a PREFIX.
_TITLE_PREFIX = 45


def _norm_title(title: str) -> str:
    """Normalize a title so a work's MIRRORS collapse onto it.

    ``[PDF]``/``[HTML]`` scrape prefixes must go BEFORE punctuation stripping: otherwise
    "[PDF] Automation and New Tasks" keeps a leading "pdf" token and never matches the T1
    journal entry it is a mirror of -- which is precisely how a T4 preprint scrape got counted
    as a work distinct from the paper it copies.
    """
    t = _MIRROR_SUFFIX_RE.sub(" ", str(title or ""))
    t = _SCRAPE_PREFIX_RE.sub(" ", t).lower()
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


def _count_works(entries: list[dict], work_of: dict[str, str]) -> int:
    """Number of distinct WORKS among cited entries, collapsing mirrors by UNION-FIND.

    A priority chain (same_work_group -> DOI -> title) CANNOT do this, and two earlier cuts of
    this function proved it by reporting 94 works where there are ~68:

      * the title lives under ``source_title``; reading ``title`` (absent) made every title ""
        and keyed each entry by its own ev_id -- collapsing nothing;
      * with that fixed, DOI-before-title still failed, because a work WITH a doi never meets
        its doi-LESS mirror: [1] Acemoglu-Restrepo keys as doi:10.1257/jep.33.2.3 while [13],
        the IZA "[PDF]" scrape of the same paper, keys by title. Same for "Generative AI at
        Work" [42] vs its arXiv mirror [78].

    No single key identifies a work, because the mirrors disagree on WHICH field they carry.
    So merge on ANY agreement: same_work_group, or DOI, or normalized title prefix. Title
    prefix (not full title) because the corpus stores truncated titles ("... Displaces and
    ..."), so a full-string match misaligns a mirror against its own paper.

    Inflating this number flatters the LONG arms specifically -- they cite more mirrors -- i.e.
    exactly the arms being sold. It is the metric the depth claims are graded on, so it gets
    union-find rather than a convenient key.
    """
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for e in entries:
        ev = str(e.get("evidence_id") or e.get("ev_id") or "")
        node = f"ev:{ev}"
        find(node)
        if ev in work_of:
            union(node, work_of[ev])
        doi = str(e.get("doi") or "").strip().lower()
        if doi:
            union(node, f"doi:{doi}")
        title = _norm_title(e.get("source_title") or e.get("title") or "")
        if len(title) >= _TITLE_PREFIX:
            union(node, f"t:{title[:_TITLE_PREFIX]}")
        elif title:
            union(node, f"t:{title}")

    return len({find(f'ev:{e.get("evidence_id") or e.get("ev_id") or ""}') for e in entries})


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
    n_works = _count_works(cited_entries, work_of)
    per_1k = 1000.0 * n_works / words if words else 0.0
    quality = [e for e in cited_entries if str(e.get("tier") or "").upper() in _QUALITY_TIERS]
    return {
        "run": run_dir.name,
        "words": words,
        "bib_entries": len(entries),
        "cited_entries": len(cited_entries),
        "distinct_works": n_works,
        "works_per_1k_words": round(per_1k, 2),
        "entry_inflation": round(len(cited_entries) / n_works, 2) if n_works else 0.0,
        "quality_tier_pct": round(100.0 * len(quality) / len(cited_entries), 1) if cited_entries else 0.0,
    }


def main() -> int:
    corpus = Path(sys.argv[1])
    rows = [density(Path(d), corpus) for d in sys.argv[2:]]
    hdr = (
        f'{"run":26}{"body_w":>7}{"cited":>7}{"works":>7}{"works/1k":>10}'
        f'{"inflation":>11}{"T1-T3%":>8}'
    )
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(
            f'{r["run"]:26}{r["words"]:>7}{r["cited_entries"]:>7}'
            f'{r["distinct_works"]:>7}{r["works_per_1k_words"]:>10}{r["entry_inflation"]:>10}x'
            f'{r["quality_tier_pct"]:>7}%'
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
