#!/usr/bin/env python3
"""Pack a POLARIS report into the official DeepTRACE (answer-engine-eval) input schema:
one record per task = {id, Question, Output, S1..S10}. The official scorer
(third_party/answer-engine-eval/Venkit.et.al.2024/populate_scores.py) then scrapes each
S{i} via r.jina.ai, gpt-4o-extracts core statements, and judges (statement, source) support.

THE 10-SOURCE CAP (code-confirmed: populate_scores.py uses `range(1,11)` x3; the body's `[N]`
markers are parsed by utils_misc.extract_citations as source indices N). A POLARIS report
cites hundreds of sources, so this packer reduces the body to a MINIMAL load-bearing set of
<=10 sources via the harness's OWN greedy_set_cover objective (DeepTRACE source-necessity #6),
and RENUMBERS the body citations to `[1..k]`, k<=10. Statements whose only sources are dropped
become uncited (honest — we do not invent support). The full keep-all corroboration set is NOT
listed here (it lives in POLARIS's own bibliography/sidecar, scored by DRB-II independence).

INVARIANTS (eval integrity):
  - NEVER pre-fills S{i}_content (the official scorer scrapes it; pre-filling POLARIS's own
    spans would be the §-1.1 self-serving-eval shortcut — forbidden).
  - Output is the cleaned answer body (masthead/base64/gap-stub stripped via pack_drb2.strip_junk,
    [#ev:] provenance tokens removed, appendix dropped) — never POLARIS-internal meta.
  - Faithfulness untouched: this packs/renumbers existing citations; it judges nothing.
LAW VI: caps are env-overridable.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "scripts" / "dr_benchmark"))
import pack_drb2  # noqa: E402  (reuse strip_junk / answer_body)

MAX_SOURCES = int(os.getenv("PACK_DEEPTRACE_MAX_SOURCES", "10"))  # the official range(1,11) cap

_CITE_RE = re.compile(r"\[([\d,\s]+)\]")          # [N] / [N, M] numbered citations
_EV_TOKEN_RE = re.compile(r"\[#ev:[^\]]*\]")      # POLARIS-internal provenance tokens (stripped)
# Intra-line sentence boundary (applied AFTER the body is split into lines): POLARIS's
# trailing-citation prose style `... end.[1] Next ...[2]`. Fixed-width lookbehind (1-char class).
_INTRA_LINE_SENT_RE = re.compile(r"(?<=[.!?\]])\s+(?=[A-Z0-9])")


def _split_statements(body: str) -> list[str]:
    """Split a report body into the FINEST citation-bearing units for the source-necessity
    matrix. Each Markdown LINE is its own block, so table rows / list items / headings / block
    quotes never collapse into one another (the Codex P1 class — first lists, then tables); a
    table row (`|`-led) is further split per-cell on `|` so two cells citing two sources stay
    distinct; a prose line is split into sentences on terminal punctuation.

    DIRECTIONAL SAFETY: over-splitting is harmless for greedy set-cover (a source that uniquely
    covers any unit is still selected — it never DROPS a load-bearing source); only UNDER-splitting
    (collapsing distinct cited units) drops sources. This matrix is INTERNAL source-selection only;
    the official scorer re-extracts statements from `Output` itself, so granularity here never
    changes what the judge reads — it only makes the <=10 kept sources strictly more conservative."""
    statements: list[str] = []
    for line in body.splitlines():
        s = line.strip()
        if not s:
            continue
        units = [c for c in s.split("|") if c.strip()] if s.startswith("|") else [s]
        for unit in units:
            for seg in _INTRA_LINE_SENT_RE.split(unit):
                if seg.strip():
                    statements.append(seg)
    return statements


def _load_references(bibliography: list) -> dict[int, str]:
    """Map the citation number `num` -> source url from a POLARIS bibliography.json (a list of
    {num, url, ...} entries). Skips malformed entries (no num/url)."""
    refs: dict[int, str] = {}
    for entry in bibliography:
        if not isinstance(entry, dict):
            continue
        num, url = entry.get("num"), entry.get("url")
        if num is None or not url:
            continue
        try:
            refs[int(num)] = str(url)
        except (TypeError, ValueError):
            continue
    return refs


def _citation_matrix(sentences: list[str]) -> dict[int, set[int]]:
    """source_num -> set of sentence indices that cite it (the CITATION bipartite)."""
    m: dict[int, set[int]] = defaultdict(set)
    for i, s in enumerate(sentences):
        for grp in _CITE_RE.findall(s):
            for tok in grp.split(","):
                tok = tok.strip()
                if tok.isdigit():
                    m[int(tok)].add(i)
    return m


def _greedy_set_cover(universe: set[int], subsets: dict[int, set[int]]) -> list[int]:
    """Greedy set cover (mirrors third_party/answer-engine-eval utils_coverage.greedy_set_cover —
    the SAME objective the DeepTRACE source-necessity metric scores). Returns the source nums in
    coverage-priority order; deterministic tie-break by (-new_coverage, num)."""
    covered: set[int] = set()
    cover: list[int] = []
    items = list(subsets.items())
    while covered != universe and items:
        num, subset = max(items, key=lambda kv: (len(kv[1] - covered), -kv[0]))
        gain = len(subset - covered)
        if gain == 0:
            break
        cover.append(num)
        covered |= subset
        items = [(n, s) for n, s in items if n != num]
    return cover


def _renumber_body(body: str, num_to_new: dict[int, int]) -> str:
    """Rewrite `[old]`/`[old, ...]` -> `[new]` for selected sources; DROP citations to
    non-selected sources (the statement becomes uncited — never invent support)."""
    def repl(m: re.Match) -> str:
        new = sorted({num_to_new[int(t.strip())]
                      for t in m.group(1).split(",")
                      if t.strip().isdigit() and int(t.strip()) in num_to_new})
        return "[" + ", ".join(str(n) for n in new) + "]" if new else ""
    return _CITE_RE.sub(repl, body)


def pack_report_for_deeptrace(
    report_md: str, bibliography: list, *, task_id: object, question: str,
    max_sources: int = MAX_SOURCES,
) -> dict:
    """Return one DeepTRACE record {id, Question, Output, S1..S10} for a POLARIS report."""
    refs = _load_references(bibliography)
    # clean body: strip masthead/base64/gap-stub + appendix + provenance tokens.
    cleaned, _ = pack_drb2.strip_junk(report_md)
    body = pack_drb2.answer_body(cleaned)
    body = _EV_TOKEN_RE.sub("", body)
    sentences = _split_statements(body)
    matrix = {n: idxs for n, idxs in _citation_matrix(sentences).items() if n in refs}
    universe = set().union(*matrix.values()) if matrix else set()
    # Clamp the selectable cap to 1..10 — the official scorer dereferences exactly S1..S10
    # (range(1,11)); a cap <10 would KeyError, >10 would emit out-of-range sources (Codex P1).
    n_cap = max(1, min(10, max_sources))
    cover = _greedy_set_cover(universe, matrix)[:n_cap]
    num_to_new = {old: i + 1 for i, old in enumerate(cover)}
    out_body = _renumber_body(body, num_to_new)
    record = {"id": str(task_id), "Question": question, "Output": out_body}
    for i in range(1, 11):  # ALWAYS emit exactly S1..S10 (empty string when unfilled).
        record[f"S{i}"] = refs.get(cover[i - 1], "") if i - 1 < len(cover) else ""
        # NB: S{i}_content is DELIBERATELY NOT set — the official scorer scrapes it via jina.
    return record


def main() -> None:
    ap = argparse.ArgumentParser(description="Pack a POLARIS report for DeepTRACE (answer-engine-eval).")
    ap.add_argument("--report", required=True)
    ap.add_argument("--bibliography", required=True)
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--question", required=True)
    ap.add_argument("--out", required=True, help="output JSON path (a list of one record, appended)")
    args = ap.parse_args()
    bib = json.loads(Path(args.bibliography).read_text(encoding="utf-8"))
    rec = pack_report_for_deeptrace(
        Path(args.report).read_text(encoding="utf-8", errors="replace"), bib,
        task_id=args.task_id, question=args.question,
    )
    out = Path(args.out)
    data = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else []
    data = [d for d in data if d.get("id") != rec["id"]] + [rec]
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    # The record ALWAYS has exactly S1..S10 (the helper clamps the cap to 1..10); count over the
    # real schema, NOT the raw env cap — PACK_DEEPTRACE_MAX_SOURCES=99 would KeyError on S11 (Codex P1).
    n_src = sum(1 for i in range(1, 11) if rec[f"S{i}"])
    print(f"[pack_deeptrace] wrote {out} | id={rec['id']} | listed_sources={n_src} (<= 10)")


if __name__ == "__main__":
    main()
