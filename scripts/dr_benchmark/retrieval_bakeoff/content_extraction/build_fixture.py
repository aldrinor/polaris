"""build_fixture.py -- ground truth for the content_extraction bake-off.

Two ground-truth sources per the brief (§3 content_extraction):

  1. GENERAL axis (REUSE, no build): WebMainBench -- 7,809 human-annotated pages
     with gold Markdown + the OFFICIAL ROUGE-N scorer (`eval_baselines.py` +
     `benchmark/WebMainBench_100.jsonl`, cloned from opendatalab/MinerU-HTML).
     This is the published gold for the exact job + the GATE-0 anchor. We do NOT
     re-annotate it; we load it (or honestly FLAG it absent).

  2. CLINICAL axis (BUILD, needs_fixture): a small fixture (~50-100 real pages
     spanning POLARIS source types: journal HTML / FDA label / EMA SmPC /
     ClinicalTrials.gov / guideline / preprint) with gold main body Markdown +
     gold TABLE TREES (for TEDS). This module ships the SCHEMA + an ingest path
     that pulls raw bodies from banked corpus_snapshot.json files, but the GOLD
     LABELS are a human/two-family hand-labeling step -- they are NEVER
     fabricated. Until labeled, every clinical-axis verdict is honestly
     needs_fixture.

Faithfulness: this builds reference data only; it never touches the faithfulness
engine. The labels are the metric's ground truth, set by humans, not by a judge
(a judge may PROPOSE a label; it never sets the scored label).

Run:  python build_fixture.py --out outputs/ret_bakeoff/content_extraction
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import sys
from dataclasses import asdict, dataclass, field

from _scoring import locate_official_scorer

# ---------------------------------------------------------------------------
# Schema (LAW VI: paths/limits are args/env, not hardcoded)
# ---------------------------------------------------------------------------

SCHEMA_VERSION = "content_extraction_fixture_v1"

# POLARIS clinical source types the clinical fixture must span (oversample
# table-bearing pages). Used as a stratification target, not a hard filter.
CLINICAL_SOURCE_TYPES = (
    "journal_html",
    "fda_label",
    "ema_smpc",
    "clinicaltrials_gov",
    "clinical_guideline",
    "preprint",
)

# Default banked snapshot search globs (the 6 banked corpora referenced across
# the campaign). Env-overridable; never assume a single hardcoded path.
DEFAULT_SNAPSHOT_GLOBS = (
    "outputs/**/corpus_snapshot.json",
    "state/**/corpus_snapshot*.json",
)


@dataclass
class ClinicalGoldPage:
    """One labeled clinical page. gold_* fields are HUMAN-labeled, never faked."""

    page_id: str
    source_type: str  # one of CLINICAL_SOURCE_TYPES
    source_url: str
    raw_html: str  # the byte-identical fetched HTML (shared input, all candidates)
    has_table: bool
    # --- GOLD (human / two-family labeled; needs_fixture until filled) ---
    gold_main_body_md: str = ""  # gold main body Markdown
    gold_table_trees: list = field(default_factory=list)  # gold <table> HTML trees for TEDS
    label_status: str = "needs_fixture"  # needs_fixture | labeled
    label_provenance: str = ""  # who/what produced the label (human/two-family)


@dataclass
class GeneralAxisStatus:
    """WebMainBench reuse status (no build; detect-or-flag)."""

    benchmark: str
    available: bool
    eval_script_path: str
    benchmark_jsonl_path: str
    reason: str
    gold_field: str = "groundtruth_content"  # WebMainBench gold key
    rouge_n: int = 5
    tokenizer: str = "jieba"


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def discover_snapshot_bodies(globs: tuple[str, ...], repo_root: str) -> list[dict]:
    """Ingest raw fetched bodies from banked corpus_snapshot.json files.

    Returns candidate clinical-page stubs with raw HTML/body present but gold
    labels EMPTY (needs_fixture). This is the honest ingest path: real banked
    data in, no synthetic gold out.
    """
    stubs: list[dict] = []
    for pattern in globs:
        for snap_path in glob.glob(os.path.join(repo_root, pattern), recursive=True):
            try:
                with open(snap_path, encoding="utf-8") as fh:
                    snap = json.load(fh)
            except Exception:  # noqa: BLE001 -- skip unreadable; never invent data
                continue
            sources = snap.get("sources") or snap.get("evidence") or []
            if not isinstance(sources, list):
                continue
            for idx, src in enumerate(sources):
                if not isinstance(src, dict):
                    continue
                raw = src.get("raw_html") or src.get("html") or src.get("content") or ""
                url = src.get("url") or src.get("source_url") or ""
                if not raw or not url:
                    continue
                stubs.append(
                    {
                        "page_id": f"{os.path.basename(snap_path)}#{idx}",
                        "source_url": url,
                        "raw_html": raw,
                        "snapshot": os.path.relpath(snap_path, repo_root),
                    }
                )
    return stubs


def build_general_axis_status(repo_root: str) -> GeneralAxisStatus:
    status = locate_official_scorer(os.getenv("PG_WEBMAINBENCH_REPO") or None)
    return GeneralAxisStatus(
        benchmark="WebMainBench (opendatalab/MinerU-HTML, 7809 pages, gold Markdown)",
        available=status.available,
        eval_script_path=status.eval_script_path,
        benchmark_jsonl_path=status.benchmark_jsonl_path,
        reason=status.reason,
    )


def build_fixture(
    *,
    out_dir: str,
    repo_root: str,
    snapshot_globs: tuple[str, ...],
    max_clinical_pages: int,
) -> dict:
    """Build/load both axes; write a manifest. Returns the manifest dict."""
    os.makedirs(out_dir, exist_ok=True)

    general = build_general_axis_status(repo_root)

    # Clinical axis: ingest real banked bodies as needs_fixture stubs. Gold
    # labels are NOT produced here (human/two-family step).
    stubs = discover_snapshot_bodies(snapshot_globs, repo_root)
    clinical_pages = [
        ClinicalGoldPage(
            page_id=s["page_id"],
            source_type="unclassified",  # human labels the type during annotation
            source_url=s["source_url"],
            raw_html=s["raw_html"],
            has_table="<table" in (s["raw_html"] or "").lower(),
            label_status="needs_fixture",
            label_provenance=f"ingested_from:{s['snapshot']}",
        )
        for s in stubs[:max_clinical_pages]
    ]

    clinical_path = os.path.join(out_dir, "clinical_gold_fixture.jsonl")
    with open(clinical_path, "w", encoding="utf-8") as fh:
        for page in clinical_pages:
            fh.write(json.dumps(asdict(page), ensure_ascii=False) + "\n")

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "general_axis": asdict(general),
        "clinical_axis": {
            "fixture_path": os.path.relpath(clinical_path, repo_root),
            "page_count": len(clinical_pages),
            "labeled_count": sum(1 for p in clinical_pages if p.label_status == "labeled"),
            "needs_fixture_count": sum(
                1 for p in clinical_pages if p.label_status == "needs_fixture"
            ),
            "source_types_targeted": list(CLINICAL_SOURCE_TYPES),
            "table_bearing_count": sum(1 for p in clinical_pages if p.has_table),
            "gold_labeling": (
                "HUMAN / two-family hand-labeling required (gold body + table trees). "
                "Judge may PROPOSE; never sets the scored label. needs_fixture until labeled."
            ),
        },
        "fixture_sha256": _sha256_file(clinical_path),
    }
    with open(os.path.join(out_dir, "fixture_manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build content_extraction bake-off fixtures")
    parser.add_argument(
        "--out",
        default=os.getenv(
            "PG_CE_BAKEOFF_OUT", "outputs/ret_bakeoff/content_extraction"
        ),
    )
    parser.add_argument("--repo-root", default=os.getenv("PG_REPO_ROOT", os.getcwd()))
    parser.add_argument(
        "--max-clinical-pages",
        type=int,
        default=int(os.getenv("PG_CE_BAKEOFF_MAX_CLINICAL", "100")),
    )
    args = parser.parse_args(argv)

    manifest = build_fixture(
        out_dir=args.out,
        repo_root=args.repo_root,
        snapshot_globs=DEFAULT_SNAPSHOT_GLOBS,
        max_clinical_pages=args.max_clinical_pages,
    )
    print(json.dumps(manifest, indent=2))
    if not manifest["general_axis"]["available"]:
        print(
            "[FLAG] WebMainBench official scorer NOT located -- GATE-0 published-number "
            "anchor will use blind re-derivation fallback (set PG_WEBMAINBENCH_REPO).",
            file=sys.stderr,
        )
    if manifest["clinical_axis"]["labeled_count"] == 0:
        print(
            "[FLAG] clinical fixture is needs_fixture (0 labeled) -- clinical-axis "
            "(TEDS / in-domain) verdicts are NOT trusted until human/two-family labeling.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
