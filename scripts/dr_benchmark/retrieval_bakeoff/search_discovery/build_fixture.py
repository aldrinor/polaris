"""search_discovery bake-off — gold SOURCE-SET fixture builder + identity matcher.

I-ret-002 (#1294), layer 1 of 7. Builds ``drb_gold_sources.jsonl``: for each
DeepResearch-Bench-II ``info_recall`` required finding (idx 56/62/66/72) a GOLD SOURCE-SET —
the set of canonical sources that, if surfaced in the ranked URL list, satisfy that finding.

Why a SET, not a single URL (the §-1.3 basket-faithfulness fix the brief mandates):
a valid alternate source for the same study (a publisher mirror, a PMC copy, an OA repository
deposit) must score POSITIVE. Recall(f) = 1 iff ANY member of gold(f) is matched by IDENTITY
on the candidate's ranked list — never exact-URL, never registered-domain-alone.

IDENTITY (net-new matcher — the brief flags the prior "reuse _normalize_url + DOI-canon" claim
as FALSE; this module implements the real thing):
  - DOI/PMID-identified source -> matched by the canonical identifier extracted from the
    candidate URL (a doi.org link, a PMC/PubMed id, an embedded ``10.xxxx/...`` in the path).
  - gov / guideline / agency report (no DOI/PMID) -> matched by canonical PAGE/REPORT IDENTITY:
    registered-domain equivalence is NECESSARY but NOT SUFFICIENT — it must ALSO match the
    specific report path/slug, so a different page on the same domain (any fda.gov page) does
    NOT count. This is the headline broad-domain-false-positive guard.
  - URL-equivalence fallback (mirror / ?utm / trailing-slash) uses the existing
    ``_normalize_url`` ONLY for last-resort same-page matching, never as the identity itself.

Builder honesty (the brief + advisor): the judge PROPOSES rows only — it never sets the scored
gold. Untitled findings (idx66 carries titles on only ~3/48) are judge-MAPPED and carry
``confirmation_status="judge_proposed_needs_confirm"``; titled findings resolved + DOI-verified
carry ``confirmation_status="title_verified"``. Ambiguous title->DOI resolution FAILS LOUD
(never guessed). The DRB-II blocked source is excluded before the fixture is written.

OFFLINE-FIRST: nothing here calls the network at import or in the scoring path. The Crossref /
OpenAlex resolvers are injected (a ``ResolverFn``) so the smoke runs with a synthetic resolver,
no network. Live resolution (all ~50-60 DOIs) is the VM/parallel-fixture phase, not this file's
deliverable.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Any, Callable, Optional

# Reuse the proven gold-binding + blocked-source seams (the brief names these explicitly).
from scripts.dr_benchmark.gate0_lineage import (
    DEFAULT_TASKS_PATH,
    SLUG_TO_IDX,
    sha256_text,
)
from scripts.dr_benchmark.qgen_coverage_harness import (
    _normalize_url,
    make_blocked_filter,
)

# A resolver maps a study title (+ optional context) -> a candidate identifier record, OR None
# when it cannot resolve unambiguously. Injected so the build is testable offline.
#   resolve(title: str, context: str) -> {"doi": str|None, "pmid": str|None,
#                                          "canonical_url": str|None, "matched_title": str|None}
ResolverFn = Callable[[str, str], Optional[dict[str, Any]]]

# The slugs this layer scores (the registered DRB-II idxs with info_recall gold).
FIXTURE_SLUGS: tuple[str, ...] = (
    "drb_72_ai_labor",            # idx 56
    "drb_75_metal_ions_cvd",      # idx 62
    "drb_76_gut_microbiota_crc",  # idx 66
    "drb_78_parkinsons_dbs",      # idx 72
)

# Title-quote extraction: info_recall findings name studies inside single quotes, e.g.
#   "... explicitly cite the study 'Can AI help for scientific writing?' ...".
_TITLE_QUOTE_RE = re.compile(r"['‘’“”]([^'‘’“”]{8,200}?)['‘’“”]")

# DOI: the canonical 10.NNNN/suffix shape (case-insensitive). The suffix may contain '/' (DOIs
# legitimately do) but STOPS at whitespace, quotes, angle brackets, and URL-structural
# delimiters '?'/'#'/'&' so a ?utm= query string or #fragment is never folded into the DOI.
_DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"'<>?#&]+)", re.IGNORECASE)
# PMID inside a PubMed/PMC URL or an explicit pmid: token.
_PMC_RE = re.compile(r"/pmc/articles/PMC(\d+)", re.IGNORECASE)
_PUBMED_RE = re.compile(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)", re.IGNORECASE)
_PMID_TOKEN_RE = re.compile(r"\bpmid[:=]\s*(\d+)", re.IGNORECASE)


class FixtureBuildError(RuntimeError):
    """Raised fail-loud on an ambiguous / unresolvable / inconsistent fixture build."""


# ---------------------------------------------------------------------------
# Identity extraction + matching (net-new; the load-bearing scoring primitive).
# ---------------------------------------------------------------------------

def canonicalize_doi(doi: str | None) -> str | None:
    """Lowercase + strip a DOI to its canonical ``10.xxxx/suffix`` form, or None."""
    if not doi:
        return None
    s = str(doi).strip().lower()
    # Drop any leading resolver prefix.
    for pre in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/",
                "http://dx.doi.org/", "doi:"):
        if s.startswith(pre):
            s = s[len(pre):]
    m = _DOI_RE.search(s)
    if not m:
        return None
    # Strip trailing punctuation AND a single trailing '/' (a URL path artifact, e.g.
    # ``dx.doi.org/10.x/y/`` -> ``10.x/y``); a DOI never canonically ends in a bare slash.
    return m.group(1).rstrip(".,);]").rstrip("/").lower()


def extract_identity_from_url(url: str) -> dict[str, Any]:
    """Pull every identity signal out of a single candidate URL.

    Returns {"doi": str|None, "pmid": str|None, "norm_url": str, "domain": str, "path": str}.
    No network. Used both to build gold rows and to match candidate ranked URLs against gold.
    """
    raw = (url or "").strip()
    norm = _normalize_url(raw)  # scheme/www/query/fragment/trailing-slash stripped (reuse)
    domain = norm.split("/", 1)[0] if norm else ""
    path = norm[len(domain):] if domain and len(norm) > len(domain) else ""

    doi = None
    m = _DOI_RE.search(raw)
    if m:
        doi = canonicalize_doi(m.group(1))

    pmid = None
    for pat in (_PMC_RE, _PUBMED_RE, _PMID_TOKEN_RE):
        mm = pat.search(raw)
        if mm:
            pmid = mm.group(1)
            break

    return {"doi": doi, "pmid": pmid, "norm_url": norm, "domain": domain, "path": path}


@dataclass
class GoldSource:
    """One member of a finding's gold SET.

    ``kind`` is "doi_pmid" or "page_report". For page_report, ``domain`` + ``path_slug`` define
    the canonical page identity (domain alone is NEVER sufficient).
    """

    kind: str
    doi: str | None = None
    pmid: str | None = None
    canonical_url: str | None = None
    domain: str | None = None
    path_slug: str | None = None
    title: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "doi": self.doi,
            "pmid": self.pmid,
            "canonical_url": self.canonical_url,
            "domain": self.domain,
            "path_slug": self.path_slug,
            "title": self.title,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "GoldSource":
        return cls(
            kind=d["kind"],
            doi=d.get("doi"),
            pmid=d.get("pmid"),
            canonical_url=d.get("canonical_url"),
            domain=d.get("domain"),
            path_slug=d.get("path_slug"),
            title=d.get("title"),
        )


def _page_slug(path: str) -> str:
    """A coarse but discriminating page-identity slug from a normalized URL path.

    Keeps the full path tail so ``/science/article/pii/S2451958825000673`` is distinct from
    ``/`` (the bare domain) and from a different article on the same domain.
    """
    segs = [s for s in (path or "").strip("/").split("/") if s]
    if not segs:
        return ""
    return "/".join(segs).lower()


def candidate_matches_gold_source(cand_url: str, gold: GoldSource) -> bool:
    """True iff a single candidate URL matches a single gold source by IDENTITY.

    DOI/PMID gold -> identifier match (the strong path).
    page_report gold -> registered-domain match AND specific page-slug match (domain alone is
    NECESSARY-BUT-NOT-SUFFICIENT: a different page on the same domain does NOT match).
    URL-equivalence fallback -> exact normalized-URL equality only (mirror/utm/slash), never a
    looser domain match.
    """
    ident = extract_identity_from_url(cand_url)

    if gold.kind == "doi_pmid":
        if gold.doi and ident["doi"] and ident["doi"] == gold.doi:
            return True
        if gold.pmid and ident["pmid"] and str(ident["pmid"]) == str(gold.pmid):
            return True
        # Fallback: a non-doi.org mirror URL that IS byte-equal (normalized) to the gold's own
        # canonical_url still counts (same page, different decoration).
        if gold.canonical_url and ident["norm_url"] and \
                ident["norm_url"] == _normalize_url(gold.canonical_url):
            return True
        return False

    if gold.kind == "page_report":
        # Domain necessary.
        if not (gold.domain and ident["domain"]):
            return False
        if ident["domain"] != gold.domain:
            return False
        # Page-slug sufficient-test: the specific report path must match (broad-domain guard).
        cand_slug = _page_slug(ident["path"])
        if gold.path_slug and cand_slug and (
            cand_slug == gold.path_slug
            or cand_slug.startswith(gold.path_slug + "/")
            or gold.path_slug.startswith(cand_slug + "/")
        ):
            return True
        return False

    raise FixtureBuildError(f"unknown gold source kind: {gold.kind!r}")


def finding_recall(ranked_urls: list[str], gold_set: list[GoldSource]) -> int:
    """1 iff ANY ranked URL matches ANY gold source in the SET (set-OR membership), else 0.

    This is the §-1.3 basket-faithfulness rule made mechanical: a single alternate-source hit
    satisfies the finding. An empty gold_set is a build error (fail loud), never a silent 0.
    """
    if not gold_set:
        raise FixtureBuildError("finding_recall: empty gold_set — fixture build error")
    for url in ranked_urls:
        for gold in gold_set:
            if candidate_matches_gold_source(url, gold):
                return 1
    return 0


# ---------------------------------------------------------------------------
# Gold-source construction from a resolver record (used at build time).
# ---------------------------------------------------------------------------

def gold_source_from_resolution(resolution: dict[str, Any], title: str | None) -> GoldSource:
    """Turn a resolver record into a GoldSource (doi_pmid if it has an identifier, else page)."""
    doi = canonicalize_doi(resolution.get("doi"))
    pmid = resolution.get("pmid")
    canonical_url = resolution.get("canonical_url")
    if doi or pmid:
        return GoldSource(
            kind="doi_pmid", doi=doi, pmid=(str(pmid) if pmid else None),
            canonical_url=canonical_url, title=title or resolution.get("matched_title"),
        )
    # No identifier: a page/report source. Derive domain + slug from the canonical_url.
    if not canonical_url:
        raise FixtureBuildError(
            f"gold source for {title!r} has neither DOI/PMID nor canonical_url — cannot build "
            f"a page identity; resolve it or drop it (never guess)."
        )
    ident = extract_identity_from_url(canonical_url)
    return GoldSource(
        kind="page_report", canonical_url=canonical_url, domain=ident["domain"],
        path_slug=_page_slug(ident["path"]), title=title or resolution.get("matched_title"),
    )


# ---------------------------------------------------------------------------
# Fixture build (idx -> rows). Resolver injected; FAIL LOUD on ambiguity.
# ---------------------------------------------------------------------------

def _load_idx_record(idx: int, tasks_path: str) -> dict[str, Any]:
    if not os.path.isfile(tasks_path):
        raise FixtureBuildError(f"tasks file not found: {tasks_path}")
    with open(tasks_path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("idx") == idx:
                return rec
    raise FixtureBuildError(f"idx={idx} not found in {tasks_path}")


def extract_title(finding_text: str) -> str | None:
    """Pull a quoted study title out of an info_recall finding, or None if untitled."""
    m = _TITLE_QUOTE_RE.search(finding_text or "")
    if not m:
        return None
    cand = m.group(1).strip()
    # A title should contain a letter and look like a phrase, not a bare token.
    if len(cand) >= 8 and re.search(r"[A-Za-z]", cand):
        return cand
    return None


def build_rows_for_idx(
    idx: int,
    resolver: ResolverFn,
    tasks_path: str = DEFAULT_TASKS_PATH,
) -> list[dict[str, Any]]:
    """Build the gold rows (one per info_recall finding) for a single DRB-II idx.

    Every titled finding is resolved + (in live use) DOI-verified; untitled findings are
    judge-mapped and flagged needs_confirm. The blocked source is excluded. FAIL LOUD on an
    ambiguous resolution (resolver returns a record with ``ambiguous=True``).
    """
    rec = _load_idx_record(idx, tasks_path)
    content = rec.get("content") or {}
    rubric = content.get("rubric") or {}
    findings = rubric.get("info_recall") or []
    if not findings:
        raise FixtureBuildError(f"idx={idx} has no info_recall rubric")

    is_blocked = make_blocked_filter(content.get("blocked"))
    blocked_title = " ".join((content.get("blocked") or {}).get("title", "").split()).lower()

    rows: list[dict[str, Any]] = []
    for f_i, finding in enumerate(findings):
        title = extract_title(finding)
        # Skip a finding whose ONLY named study is the blocked source (no valid gold exists).
        if title and blocked_title and blocked_title in title.lower():
            continue

        if title:
            resolution = resolver(title, finding)
            if resolution is None:
                # Unresolved titled finding: keep it, flag needs_confirm, with NO gold member
                # (a known gap, never a silent fake positive).
                rows.append({
                    "idx": idx, "finding_index": f_i, "finding": finding,
                    "title": title, "confirmation_status": "unresolved_needs_confirm",
                    "gold_sources": [],
                })
                continue
            if resolution.get("ambiguous"):
                raise FixtureBuildError(
                    f"idx={idx} finding {f_i}: title {title!r} resolved AMBIGUOUSLY "
                    f"({resolution.get('ambiguous_note')}); refusing to guess (fail loud)."
                )
            gold = gold_source_from_resolution(resolution, title)
            # Exclude a resolved source that IS the blocked source.
            probe = {"url": gold.canonical_url or "", "text": title}
            if is_blocked(probe):
                continue
            rows.append({
                "idx": idx, "finding_index": f_i, "finding": finding, "title": title,
                "confirmation_status": "title_verified",
                "gold_sources": [gold.to_dict()],
            })
        else:
            # Untitled finding (idx66 case): judge-mapped to its supporting source. The judge
            # PROPOSES only -> flagged needs_confirm; never silently a scored gold.
            resolution = resolver("", finding)
            gold_list: list[dict[str, Any]] = []
            if resolution is not None and not resolution.get("ambiguous"):
                gold_list = [gold_source_from_resolution(resolution, None).to_dict()]
            rows.append({
                "idx": idx, "finding_index": f_i, "finding": finding, "title": None,
                "confirmation_status": "judge_proposed_needs_confirm",
                "gold_sources": gold_list,
            })
    return rows


def build_fixture(
    out_path: str,
    resolver: ResolverFn,
    slugs: tuple[str, ...] = FIXTURE_SLUGS,
    tasks_path: str = DEFAULT_TASKS_PATH,
) -> dict[str, Any]:
    """Build ``drb_gold_sources.jsonl`` for all registered slugs; sha-pin a manifest.

    Returns a manifest dict {slug, idx, n_findings, n_with_gold, fixture_sha256} so the gold can
    be bound into the lineage manifest (gate0_lineage.build_lineage_manifest) keyed by idx and
    cannot drift. Writing happens only here; the scoring path never writes.
    """
    all_rows: list[dict[str, Any]] = []
    per_slug: list[dict[str, Any]] = []
    for slug in slugs:
        if slug not in SLUG_TO_IDX:
            raise FixtureBuildError(
                f"slug {slug!r} not in SLUG_TO_IDX — resolve its idx from the gold file first"
            )
        idx = SLUG_TO_IDX[slug]
        rows = build_rows_for_idx(idx, resolver, tasks_path)
        all_rows.extend(rows)
        per_slug.append({
            "slug": slug, "idx": idx, "n_findings": len(rows),
            "n_with_gold": sum(1 for r in rows if r["gold_sources"]),
        })

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    body = "\n".join(json.dumps(r, sort_keys=True, ensure_ascii=False) for r in all_rows)
    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(body + ("\n" if body else ""))

    return {
        "fixture_path": out_path,
        "fixture_sha256": sha256_text(body),
        "n_rows_total": len(all_rows),
        "per_slug": per_slug,
        "tasks_path": tasks_path,
    }


def load_fixture(path: str) -> dict[int, list[dict[str, Any]]]:
    """Load drb_gold_sources.jsonl -> {idx: [row, ...]}. Used by the scorer (read-only)."""
    if not os.path.isfile(path):
        raise FixtureBuildError(f"gold fixture not found: {path} — build it first")
    by_idx: dict[int, list[dict[str, Any]]] = {}
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            by_idx.setdefault(int(row["idx"]), []).append(row)
    if not by_idx:
        raise FixtureBuildError(f"gold fixture {path} is empty — build error")
    return by_idx


def gold_set_for_row(row: dict[str, Any]) -> list[GoldSource]:
    """Materialize a row's gold SET as GoldSource objects (for finding_recall)."""
    return [GoldSource.from_dict(d) for d in (row.get("gold_sources") or [])]


# ---------------------------------------------------------------------------
# Live resolvers (Crossref + OpenAlex). Network — NOT used by the smoke. Wired for the VM
# fixture-build phase. httpx imported lazily so this module imports with no network deps.
# ---------------------------------------------------------------------------

def make_crossref_openalex_resolver(
    mailto: str | None = None,
    timeout: float = 30.0,
) -> ResolverFn:
    """Build a live title->identifier resolver hitting Crossref then OpenAlex.

    Resolution is unambiguous-or-fail: a returned title must fuzzily match the query title
    (>= a similarity floor) or the record is marked ``ambiguous`` so the build FAILS LOUD rather
    than guessing. Network calls happen ONLY when this resolver is invoked (never at import).
    """
    import difflib

    import httpx  # local import: not needed for the offline smoke

    headers = {"User-Agent": f"POLARIS-retrieval-bakeoff (mailto:{mailto or 'ops@polaris'})"}

    def _similar(a: str, b: str) -> float:
        return difflib.SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio()

    def resolve(title: str, context: str) -> Optional[dict[str, Any]]:
        if not title:
            return None  # untitled -> judge maps it elsewhere; this resolver is title-keyed
        # Crossref title query.
        try:
            with httpx.Client(timeout=timeout, headers=headers) as client:
                r = client.get(
                    "https://api.crossref.org/works",
                    params={"query.bibliographic": title, "rows": 3},
                )
                if r.status_code == 200:
                    items = (r.json().get("message") or {}).get("items") or []
                    for it in items:
                        cand_title = " ".join((it.get("title") or [""])[0].split())
                        sim = _similar(title, cand_title)
                        if sim >= 0.90 and it.get("DOI"):
                            return {
                                "doi": it["DOI"], "pmid": None,
                                "canonical_url": f"https://doi.org/{it['DOI']}",
                                "matched_title": cand_title, "match_similarity": sim,
                            }
                    if items:
                        best = items[0]
                        bt = " ".join((best.get("title") or [""])[0].split())
                        return {
                            "doi": best.get("DOI"), "ambiguous": True,
                            "ambiguous_note": f"best Crossref match {bt!r} sim<0.90",
                        }
        except Exception as exc:  # noqa: BLE001 — network failure reported, not silently zeroed
            return {"ambiguous": True, "ambiguous_note": f"crossref error: {exc}"}
        # OpenAlex fallback.
        try:
            with httpx.Client(timeout=timeout, headers=headers) as client:
                r = client.get(
                    "https://api.openalex.org/works",
                    params={"search": title, "per-page": 3,
                            "mailto": mailto or "ops@polaris"},
                )
                if r.status_code == 200:
                    results = (r.json().get("results") or [])
                    for it in results:
                        cand_title = " ".join((it.get("title") or "").split())
                        sim = _similar(title, cand_title)
                        if sim >= 0.90:
                            doi = (it.get("doi") or "").replace("https://doi.org/", "")
                            return {
                                "doi": doi or None, "pmid": None,
                                "canonical_url": it.get("doi") or it.get("id"),
                                "matched_title": cand_title, "match_similarity": sim,
                            }
        except Exception as exc:  # noqa: BLE001
            return {"ambiguous": True, "ambiguous_note": f"openalex error: {exc}"}
        return None

    return resolve


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the search_discovery gold source-set fixture"
    )
    parser.add_argument(
        "--out", default="tests/fixtures/retrieval_bakeoff/drb_gold_sources.jsonl",
        help="output JSONL path",
    )
    parser.add_argument("--tasks-path", default=DEFAULT_TASKS_PATH)
    parser.add_argument("--mailto", default=os.getenv("CROSSREF_MAILTO"))
    parser.add_argument(
        "--strict", action="store_true",
        help="(live) fail loud if any titled finding is unresolved",
    )
    args = parser.parse_args(argv)

    resolver = make_crossref_openalex_resolver(mailto=args.mailto)
    manifest = build_fixture(args.out, resolver, tasks_path=args.tasks_path)
    print(json.dumps(manifest, indent=2))
    if args.strict:
        unresolved = manifest["n_rows_total"] - sum(
            s["n_with_gold"] for s in manifest["per_slug"]
        )
        if unresolved:
            print(
                f"STRICT: {unresolved} rows lack gold (unresolved/needs_confirm)",
                file=sys.stderr,
            )
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
