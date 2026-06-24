"""I-ret-002 (#1294) layer 2 (fetch_crawl) — labeled ground-truth fixture builder.

WHAT THIS BUILDS
----------------
``fetch_crawl_refbody_fixture.jsonl`` — ~60-100 URLs stratified across source-types
(OA / paywalled / gov / news / social) drawn from the 6 banked corpus snapshots. Each
fixture row carries:

  * ``url``                 — the source URL that was fetched on the real run.
  * ``source_type``         — stratification bucket (oa / paywalled / gov / news / social).
  * ``tier``                — the recorded credibility tier (T1..T7 / UNKNOWN) — a WEIGHT
                              surfaced for analysis, NEVER a drop filter (§-1.3).
  * ``reference_body``      — the labeled main-content reference body (the real fetched
                              ``direct_quote`` that the run actually grounded against).
  * ``reference_tokens``    — content-word token SET of ``reference_body`` (the recall target;
                              we score reference-recall against this SET, never a length floor).
  * ``recovery_class``      — the per-URL recovery verdict the engine OUGHT to produce on a
                              healthy fetch: RECOVERED / WALLED / SOFT_STUB / FETCH_FAIL.
  * ``recovery_class_proposed_by`` — provenance of the recovery_class label (the deterministic
                              shell-vocabulary rubric; a judge may PROPOSE only, never set it).

WHY THE SCORED LABEL IS NOT JUDGE-TASTE (Codex anti-pattern guard)
-----------------------------------------------------------------
The SCORED ``recovery_class`` is set by a PRE-REGISTERED OBJECTIVE rubric (the shared
``shell_detector`` vocabulary + an empty-body test), NOT by "reads like a stub". The
``shell_detector`` is the production fetch-shell engine (I-beatboth-001 #1276) — reusing it
here means the fixture label matches the exact deterministic signal the pipeline uses, so a
RECOVERED row is one whose body is NOT a known shell vocabulary AND is non-empty. A two-family
adjudication HOOK (``--emit-adjudication``) writes a side file the operator / Codex can
spot-check; the judge / LLM never sets the scored label (faithfulness invariant: PROPOSE only).

REUSE (per brief): ``src.polaris_graph.retrieval.shell_detector`` for the recovery vocabulary,
banked ``state/reserved_corpus_snapshots`` + ``outputs/corpus_backups/extracted`` snapshots for
the labeled reference bodies. The POLARIS repo root is resolved via ``_polaris_root`` so the
worktree-authored file imports the SAME production seam (no fork).

NO §-1.1 BANNED PROXY: the fixture stores the reference-token SET as the recall target, not a
word/char count. ``recovery_class`` is a verdict, not a count. ``tier`` is a surfaced weight.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Iterable

# Resolve the real POLARIS root and put it on sys.path BEFORE importing the production seams.
from _polaris_root import ensure_on_syspath

_POLARIS_ROOT = ensure_on_syspath()

# shell_detector is the single-source-of-truth fetch-shell vocabulary (LAW V). We import the
# RECOVERY-CLASS rubric from it so the fixture label is the exact deterministic signal prod uses.
from src.polaris_graph.retrieval.shell_detector import (  # noqa: E402  (after sys.path setup)
    is_access_denial_stub,
    is_cited_span_shell,
)

# ── Constants (LAW VI: no magic numbers buried in logic — all named / env-overridable) ──

# Recovery-class verdict vocabulary (the metric's label space — a verdict, not a count).
RECOVERED = "RECOVERED"
WALLED = "WALLED"
SOFT_STUB = "SOFT_STUB"
FETCH_FAIL = "FETCH_FAIL"
RECOVERY_CLASSES = (RECOVERED, WALLED, SOFT_STUB, FETCH_FAIL)

# Source-type stratification buckets.
SOURCE_TYPES = ("oa", "paywalled", "gov", "news", "social")

# Banked corpus-snapshot roots (read-only inputs), relative to the resolved POLARIS root.
_DEFAULT_SNAPSHOT_SUBDIRS = (
    os.path.join("state", "reserved_corpus_snapshots"),
    os.path.join("outputs", "corpus_backups", "extracted"),
)

# Default fixture output path (this layer's directory only — no cross-layer writes).
_DEFAULT_OUT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "fetch_crawl_refbody_fixture.jsonl",
)

# Stratification target band (brief: ~60-100 URLs). Env-overridable.
_ENV_TARGET_MIN = "PG_FETCH_FIXTURE_MIN_URLS"
_ENV_TARGET_MAX = "PG_FETCH_FIXTURE_MAX_URLS"
_DEFAULT_TARGET_MIN = 60
_DEFAULT_TARGET_MAX = 100

# A body shorter than this (after strip) and not a shell is a SOFT_STUB (truncated / abstract-only
# recovery), per the WebMainBench labelling protocol — a *recovery class*, NOT a quality length
# floor: a healthy long article is RECOVERED, a near-empty non-shell stub is SOFT_STUB.
_ENV_SOFT_STUB_MAX = "PG_FETCH_FIXTURE_SOFT_STUB_MAX_CHARS"
_DEFAULT_SOFT_STUB_MAX = 400

# Content-word token regex (drop punctuation; keep alphanumerics incl. unicode).
_WORD_RE = re.compile(r"[^\W\d_]+|\d+", re.UNICODE)

# A tiny stop-set so reference-recall measures CONTENT overlap, not function-word overlap.
_STOPWORDS = frozenset(
    """a an and are as at be by for from has have in is it its of on or that the to was were
    will with this these those we they their there here""".split()
)


@dataclass
class FixtureRow:
    """One labeled fetch_crawl ground-truth row."""

    url: str
    source_type: str
    tier: str
    reference_body: str
    recovery_class: str
    recovery_class_proposed_by: str = "shell_detector_rubric_v1"
    slug: str = ""
    evidence_id: str = ""
    doi: str = ""
    provenance_class: str = ""

    def reference_tokens(self) -> list[str]:
        """Content-word token list of the reference body (the recall target SET source)."""
        return content_tokens(self.reference_body)

    def reference_trustworthy(self) -> bool:
        """True iff the reference body is trustworthy main content (gold == RECOVERED).

        Only on a RECOVERED row did the INCUMBENT get full text — so only there is the reference
        body a valid recall target. A WALLED / SOFT_STUB / FETCH_FAIL gold row is one the incumbent
        FAILED on; its body is a shell, so reference-recall vs it is NOT used to judge an engine
        (the scorer carries this flag to avoid the §-1.3 inversion of punishing a wall-breaker).
        """
        return self.recovery_class == RECOVERED

    def boundary_for_adjudication(self) -> bool:
        """True iff this SOFT_STUB row sits NEAR the length ceiling — a judge should confirm it.

        The SOFT_STUB-vs-RECOVERED split is decided by a length ceiling at the LABELING layer (not
        the metric). Rows whose body length is within a margin of the ceiling are the ambiguous ones
        (a borderline-short real article vs a truncated stub); they are flagged so the two-family
        adjudication hook surfaces them for judge confirmation rather than trusting a bare length cut.
        """
        if self.recovery_class != SOFT_STUB:
            return False
        ceiling = _soft_stub_max_chars()
        body_len = len((self.reference_body or "").strip())
        margin = max(50, ceiling // 4)
        return abs(body_len - ceiling) <= margin

    def to_record(self) -> dict[str, Any]:
        toks = sorted(set(self.reference_tokens()))
        return {
            "url": self.url,
            "source_type": self.source_type,
            "tier": self.tier,
            "reference_body": self.reference_body,
            "reference_tokens": toks,
            "recovery_class": self.recovery_class,
            "reference_trustworthy": self.reference_trustworthy(),
            "boundary_for_adjudication": self.boundary_for_adjudication(),
            "recovery_class_proposed_by": self.recovery_class_proposed_by,
            "slug": self.slug,
            "evidence_id": self.evidence_id,
            "doi": self.doi,
            "provenance_class": self.provenance_class,
        }


def content_tokens(text: str) -> list[str]:
    """Lowercase content-word tokens (stopwords removed). The recall target is the SET of these.

    NOT a length proxy: this is the gold reference-token SET that engine output is recalled
    against (Jaccard / recall), exactly the §-1.1-compliant "real output vs labeled ground truth".
    """
    if not text:
        return []
    out: list[str] = []
    for m in _WORD_RE.findall(text.lower()):
        if len(m) <= 1:
            continue
        if m in _STOPWORDS:
            continue
        out.append(m)
    return out


def _soft_stub_max_chars() -> int:
    try:
        v = int(os.environ.get(_ENV_SOFT_STUB_MAX, _DEFAULT_SOFT_STUB_MAX) or _DEFAULT_SOFT_STUB_MAX)
    except (TypeError, ValueError):
        return _DEFAULT_SOFT_STUB_MAX
    return v if v > 0 else _DEFAULT_SOFT_STUB_MAX


def _target_band() -> tuple[int, int]:
    def _read(name: str, default: int) -> int:
        try:
            v = int(os.environ.get(name, default) or default)
        except (TypeError, ValueError):
            return default
        return v if v > 0 else default

    lo = _read(_ENV_TARGET_MIN, _DEFAULT_TARGET_MIN)
    hi = _read(_ENV_TARGET_MAX, _DEFAULT_TARGET_MAX)
    return (lo, hi) if lo <= hi else (hi, lo)


# ── Recovery-class rubric (the PRE-REGISTERED OBJECTIVE label) ──────────────────────────

def classify_recovery(body: str) -> str:
    """Deterministic recovery-class verdict for a fetched body (the SCORED label rubric).

    PRE-REGISTERED OBJECTIVE rubric — judge / LLM never sets this (PROPOSE-only invariant):
      * empty / whitespace-only      -> FETCH_FAIL  (the fetch returned nothing).
      * a bot-wall / access-denial   -> WALLED      (CAPTCHA / Cloudflare / paywall interstitial).
      * any other known fetch-shell  -> SOFT_STUB   (cookie / 404 / language-nav / citation-UI chrome).
      * a non-shell but tiny body    -> SOFT_STUB   (truncated / abstract-only recovery).
      * a non-shell substantive body -> RECOVERED   (real main content).

    This is the SAME shell vocabulary the production faithfulness gate uses (``shell_detector``),
    so a fixture label is never an opinion — it is the deterministic signal the pipeline trusts.
    """
    if body is None:
        return FETCH_FAIL
    stripped = body.strip()
    if not stripped:
        return FETCH_FAIL
    # Bot-wall / access-denial first (the WALLED class). is_access_denial_stub fires on the
    # unambiguous Cloudflare/CAPTCHA co-occurrence at any length and on short-body denial markers.
    if is_access_denial_stub(stripped):
        return WALLED
    # Any other fetch-shell (cookie banner, 404, language-nav, citation-UI/social chrome) -> SOFT_STUB.
    if is_cited_span_shell(stripped):
        return SOFT_STUB
    # A non-shell but near-empty body is a truncated / abstract-only recovery -> SOFT_STUB.
    if len(stripped) <= _soft_stub_max_chars():
        return SOFT_STUB
    return RECOVERED


# ── Source-type stratification ──────────────────────────────────────────────────────────

# Domain substrings -> source_type. Tier is the credibility WEIGHT; source_type is the FETCH
# difficulty stratum (a different axis). Necessary-but-not-sufficient: registered-domain alone.
_GOV_DOMAINS = (
    ".gov", ".gc.ca", "europa.eu", "ema.europa", "fda.gov", "nih.gov", "ncbi.nlm.nih.gov",
    "who.int", "nice.org.uk", "clinicaltrials.gov", "cdc.gov", "canada.ca", "tga.gov.au",
    "pmda.go.jp", "mhra", "health.gov",
)
_NEWS_DOMAINS = (
    "reuters.com", "bloomberg.com", "nytimes.com", "theguardian.com", "bbc.co", "wsj.com",
    "ft.com", "cnbc.com", "forbes.com", "apnews.com", "economist.com", "washingtonpost.com",
    "statnews.com", "medscape.com",
)
_SOCIAL_DOMAINS = (
    "twitter.com", "x.com", "reddit.com", "youtube.com", "facebook.com", "linkedin.com",
    "medium.com", "substack.com", "researchgate.net", "quora.com", "t.me",
)
# Paywalled-publisher domains (clinical journals that 403 the free cascade — Zyte's home turf).
_PAYWALL_DOMAINS = (
    "nejm.org", "thelancet.com", "jamanetwork.com", "sciencedirect.com", "springer.com",
    "wiley.com", "nature.com", "tandfonline.com", "sagepub.com", "oup.com", "bmj.com",
    "cell.com", "ahajournals.org", "academic.oup.com", "onlinelibrary.wiley.com",
)


def classify_source_type(url: str, provenance_class: str) -> str:
    """Map a URL to a fetch-difficulty stratum (oa / paywalled / gov / news / social).

    Tier is NOT used here (tier is credibility weight; this is fetch-difficulty). Order matters:
    gov / social / news registered-domain checks first; paywalled-publisher domain next;
    open_access provenance or otherwise -> oa (the default easy fetch).
    """
    low = (url or "").lower()
    if any(d in low for d in _GOV_DOMAINS):
        return "gov"
    if any(d in low for d in _SOCIAL_DOMAINS):
        return "social"
    if any(d in low for d in _NEWS_DOMAINS):
        return "news"
    if any(d in low for d in _PAYWALL_DOMAINS):
        return "paywalled"
    if (provenance_class or "").strip().lower() == "open_access":
        return "oa"
    return "oa"


# ── Snapshot loading ────────────────────────────────────────────────────────────────────

def _default_snapshot_roots() -> list[str]:
    return [os.path.join(_POLARIS_ROOT, sub) for sub in _DEFAULT_SNAPSHOT_SUBDIRS]


def _iter_snapshot_files(roots: Iterable[str]) -> list[str]:
    """Enumerate every *corpus_snapshot.json under the given roots."""
    files: list[str] = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in filenames:
                if name.endswith("corpus_snapshot.json"):
                    files.append(os.path.join(dirpath, name))
    return sorted(set(files))


def _evidence_rows(snapshot_path: str) -> tuple[str, list[dict[str, Any]]]:
    """Return (slug, evidence_for_gen rows) for a snapshot; ('', []) on any read error."""
    try:
        with open(snapshot_path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return "", []
    if not isinstance(data, dict):
        return "", []
    slug = str(data.get("slug") or "")
    rows = data.get("evidence_for_gen")
    if not isinstance(rows, list):
        return slug, []
    return slug, [r for r in rows if isinstance(r, dict)]


# ── Fixture build ───────────────────────────────────────────────────────────────────────

def build_rows(roots: Iterable[str] | None = None) -> list[FixtureRow]:
    """Build the stratified labeled fixture rows from banked snapshots.

    Dedups by URL (the first occurrence of a URL wins). Caps per (source_type) bucket so the
    fixture is stratified, not OA-dominated. FAILS LOUD (raises) if no snapshot rows are found,
    so a silent-empty fixture can never slip through (§-1.1 / LAW II).
    """
    roots = list(roots) if roots is not None else _default_snapshot_roots()
    files = _iter_snapshot_files(roots)
    if not files:
        raise RuntimeError(
            f"build_fixture: no corpus_snapshot.json found under {roots!r} — cannot build a "
            f"labeled fetch_crawl fixture from banked corpora (FAIL LOUD, never an empty fixture)."
        )

    target_min, target_max = _target_band()
    # Per-bucket cap so 5 buckets * cap ~= target_max, with a floor so rarer buckets are not starved.
    per_bucket_cap = max(6, (target_max // max(1, len(SOURCE_TYPES))) + 4)

    seen_urls: set[str] = set()
    by_bucket: dict[str, list[FixtureRow]] = {st: [] for st in SOURCE_TYPES}

    for path in files:
        slug, rows = _evidence_rows(path)
        for r in rows:
            url = str(r.get("source_url") or "").strip()
            if not url.lower().startswith("http"):
                continue
            if url in seen_urls:
                continue
            body = str(r.get("direct_quote") or "")
            # Only label rows that carry a real fetched body (the reference body must exist to
            # be a recovery target). A row with no direct_quote cannot anchor reference-recall.
            if not body.strip():
                continue
            source_type = classify_source_type(url, str(r.get("provenance_class") or ""))
            bucket = by_bucket[source_type]
            if len(bucket) >= per_bucket_cap:
                continue
            seen_urls.add(url)
            bucket.append(
                FixtureRow(
                    url=url,
                    source_type=source_type,
                    tier=str(r.get("tier") or "UNKNOWN"),
                    reference_body=body,
                    recovery_class=classify_recovery(body),
                    slug=slug,
                    evidence_id=str(r.get("evidence_id") or ""),
                    doi=str(r.get("doi") or ""),
                    provenance_class=str(r.get("provenance_class") or ""),
                )
            )

    rows_out: list[FixtureRow] = []
    for st in SOURCE_TYPES:
        rows_out.extend(by_bucket[st])

    if not rows_out:
        raise RuntimeError(
            "build_fixture: every snapshot row was skipped (no http URL with a fetched body) — "
            "FAIL LOUD rather than emit an empty fetch_crawl fixture."
        )
    if len(rows_out) < target_min:
        # Honest under-build is allowed (banked data is finite) but is flagged, never hidden.
        print(
            f"[build_fixture] WARNING: built {len(rows_out)} rows < target_min {target_min}; "
            f"banked corpora yielded fewer unique fetched URLs than the target band "
            f"(stratification caps + dedup). Proceeding with the real available set."
        )
    return rows_out


def write_fixture(rows: list[FixtureRow], out_path: str) -> None:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row.to_record(), ensure_ascii=False) + "\n")


def load_fixture(path: str | None = None) -> list[dict[str, Any]]:
    """Load the fixture JSONL into a list of record dicts. FAILS LOUD if the file is missing."""
    path = path or _DEFAULT_OUT
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"load_fixture: fetch_crawl fixture not found at {path} — run build_fixture.py first."
        )
    records: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    if not records:
        raise RuntimeError(f"load_fixture: fixture {path} is EMPTY — FAIL LOUD (never score on empty).")
    return records


def _stratification_summary(rows: list[FixtureRow]) -> dict[str, Any]:
    by_type: dict[str, int] = {st: 0 for st in SOURCE_TYPES}
    by_class: dict[str, int] = {c: 0 for c in RECOVERY_CLASSES}
    boundary = 0
    trustworthy = 0
    for r in rows:
        by_type[r.source_type] = by_type.get(r.source_type, 0) + 1
        by_class[r.recovery_class] = by_class.get(r.recovery_class, 0) + 1
        if r.boundary_for_adjudication():
            boundary += 1
        if r.reference_trustworthy():
            trustworthy += 1
    # Surface skew honestly (the advisor's note): the min/max source-type bucket sizes + the over/
    # under-target flag. Never hide an uneven build.
    counts = [v for v in by_type.values()]
    target_min, target_max = _target_band()
    return {
        "total": len(rows),
        "by_source_type": by_type,
        "by_recovery_class": by_class,
        "trustworthy_reference_rows": trustworthy,
        "boundary_rows_needing_adjudication": boundary,
        "source_type_min_bucket": min(counts) if counts else 0,
        "source_type_max_bucket": max(counts) if counts else 0,
        "over_target_band": len(rows) > target_max,
        "under_target_band": len(rows) < target_min,
        "target_band": [target_min, target_max],
    }


def _emit_adjudication(rows: list[FixtureRow], path: str) -> None:
    """Write the two-family adjudication side file (operator / Codex spot-check surface).

    The judge / second family reviews the PROPOSED recovery_class here; the scored label in the
    fixture stays the deterministic rubric's. This is the PROPOSE-only hook (faithfulness invariant).
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for r in rows:
            handle.write(
                json.dumps(
                    {
                        "url": r.url,
                        "source_type": r.source_type,
                        "tier": r.tier,
                        "proposed_recovery_class": r.recovery_class,
                        "proposed_by": r.recovery_class_proposed_by,
                        # The advisor's secondary note: a SOFT_STUB near the length ceiling is a
                        # length-decided boundary; flag it so the 2nd family confirms it, not a bare cut.
                        "boundary_for_adjudication": r.boundary_for_adjudication(),
                        "reference_trustworthy": r.reference_trustworthy(),
                        "reference_body_head": r.reference_body[:280],
                        "adjudicator_recovery_class": None,  # filled by the 2nd family / operator
                        "adjudicator_note": "",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the fetch_crawl labeled ground-truth fixture.")
    parser.add_argument("--out", default=_DEFAULT_OUT, help="output fixture JSONL path")
    parser.add_argument(
        "--snapshot-root",
        action="append",
        default=None,
        help="corpus-snapshot root (repeatable); defaults to the 2 banked roots under POLARIS root",
    )
    parser.add_argument(
        "--emit-adjudication",
        default=None,
        help="optional path to write the two-family adjudication side file (PROPOSE-only hook)",
    )
    args = parser.parse_args(argv)

    rows = build_rows(args.snapshot_root)
    write_fixture(rows, args.out)
    summary = _stratification_summary(rows)
    print(f"[build_fixture] wrote {summary['total']} rows -> {args.out}")
    print(f"[build_fixture] by_source_type={summary['by_source_type']}")
    print(f"[build_fixture] by_recovery_class={summary['by_recovery_class']}")
    print(f"[build_fixture] trustworthy_reference_rows={summary['trustworthy_reference_rows']} "
          f"(gold RECOVERED — the rows where reference-recall is meaningful)")
    print(f"[build_fixture] boundary_rows_needing_adjudication={summary['boundary_rows_needing_adjudication']} "
          f"(SOFT_STUB near the length ceiling — route to --emit-adjudication for judge confirmation)")
    # Honest skew / target-band surfacing (advisor's note): never hide an uneven build.
    if summary["over_target_band"]:
        print(f"[build_fixture] NOTE: total {summary['total']} > target_max {summary['target_band'][1]} "
              f"(per-bucket caps overshoot slightly; honest artifact of stratification, not hidden).")
    if summary["under_target_band"]:
        print(f"[build_fixture] NOTE: total {summary['total']} < target_min {summary['target_band'][0]}.")
    if summary["source_type_max_bucket"] > 0 and summary["source_type_min_bucket"] > 0:
        print(f"[build_fixture] NOTE: source-type skew min_bucket={summary['source_type_min_bucket']} "
              f"max_bucket={summary['source_type_max_bucket']} (honest artifact of the banked data; "
              f"the metric pairs within-source-type so skew does not bias the winner).")
    if args.emit_adjudication:
        _emit_adjudication(rows, args.emit_adjudication)
        print(f"[build_fixture] adjudication side file -> {args.emit_adjudication}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
