#!/usr/bin/env python3
"""Fetch-stage corpus replay + INDEPENDENT junk/chrome line scan.

Purpose (operator core question 2026-07-10): run the FIXED fetch seam over the REAL
``source_url`` set from a previous run's ``corpus_snapshot.json`` and read EVERY LINE of the
span the gate ACCEPTS, to confirm whether any chrome / junk / front-matter leaks THROUGH the
gate (i.e. survives inside a span whose ``failure_mode`` is empty = accepted).

This scanner is DELIBERATELY INDEPENDENT of the production predicates (I-wire-013 lesson: a
gate cannot validate itself). It imports ONLY the fetch seam; the junk markers below are its
own explicit list. Every hit is QUOTED (never a bare count) so the operator reads the actual
offending text (§-1.1). Read-only vs src/.

Run on the VM:
  set -a && . ./.env && set +a
  PYTHONPATH=/workspace/POLARIS PYTHONIOENCODING=utf-8 python3 scripts/fetch_corpus_replay.py \
      --snapshot outputs/paid_drb72_deep/workforce/drb_72_ai_labor/corpus_snapshot.json
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import sys
import threading
import time
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.environ.get("PYTHONPATH", "/workspace/POLARIS"))
from src.polaris_graph.retrieval.live_retriever import (  # noqa: E402
    refetch_for_extraction_with_diagnostics,
)

# --- INDEPENDENT junk markers (own list; NOT a production import) ------------------------
# HIGH = unambiguous non-article chrome/junk. A HIGH hit inside an ACCEPTED span == a LEAK.
HIGH_MARKERS: list[tuple[str, re.Pattern]] = [
    ("gov_banner", re.compile(r"official website of the United States government", re.I)),
    ("crossref", re.compile(r"\bCrossref\s*\d", re.I)),
    ("reading_time", re.compile(r"\d+\s*Minute\s*Read\s*Time", re.I)),
    ("skip_nav", re.compile(r"\bSkip to (?:content|main content|search)\b", re.I)),
    ("bot_wall", re.compile(r"Just a moment|Performing security verification|not a bot|"
                            r"Verifying you are human|Enable JavaScript|Checking your browser", re.I)),
    ("error_page", re.compile(r"Something went wrong\. Wait a moment|Access denied|"
                              r"Page not found|The page you requested|\b404\b", re.I)),
    ("cookie", re.compile(r"We use cookies|Accept all cookies|cookie policy|consent to the use of cookies", re.I)),
]
# MED = often junk but can appear in legit prose/references. FLAGGED for the human read, not auto-verdict.
MED_MARKERS: list[tuple[str, re.Pattern]] = [
    ("frontmatter_thanks", re.compile(r"would like to thank|Authorized for distribution|"
                                      r"Prepared by|Suggested citation|The views expressed", re.I)),
    ("imf_wp", re.compile(r"International Monetary Fund|WP/\d+/\d+", re.I)),
    ("masthead", re.compile(r"Editorial Board|редакционн|Recenzovan|Proceedings of the .*Conference|"
                            r"International Scientific and Practical Conference|\bUDC\b", re.I)),
    ("login_paywall", re.compile(r"Sign in to (?:read|continue)|Create an account|Purchase PDF|"
                                 r"Get full access|Subscribe to (?:read|continue)", re.I)),
]
_LINK_RE = re.compile(r"\[[^\]]*\]\([^)]*\)")  # markdown link / empty-anchor [](url)
# A nav_link_density hit that carries a citation signal is a LEGIT reference line (false positive),
# not junk. Every other high marker (bot_wall/cookie/gov_banner/error_page/skip_nav/reading_time) is
# always real junk. This is the deterministic real-vs-FP split the fix→retest loop judges on.
_CITATION_SIGNAL = re.compile(
    r"10\.\d{4,9}/|\bet\s+al\b|\b(?:19|20)\d{2}\b|\bpp?\.\s*\d|\d+\s*\(\d+\)|"
    r"\barxiv\b|\bpmid\b|\bisbn\b|\bdoi\b|retrieved from|accessed", re.I)


def _real_high_hits(record: dict) -> list[dict]:
    """The subset of a record's HIGH hits that are genuine junk (not a legit citation/reference line)."""
    out: list[dict] = []
    for hit in record.get("high_hits", []):
        if hit["marker"] != "nav_link_density" or not _CITATION_SIGNAL.search(hit["text"]):
            out.append(hit)
    return out


def _link_density(line: str) -> float:
    if not line.strip():
        return 0.0
    link_chars = sum(len(m.group(0)) for m in _LINK_RE.finditer(line))
    return link_chars / max(len(line), 1)


def scan_span(span: str) -> dict:
    """Line-by-line scan of an accepted span. Returns high/med hits (each with the quoted line)."""
    high: list[dict] = []
    med: list[dict] = []
    for i, raw in enumerate(span.splitlines()):
        line = raw.strip()
        if not line:
            continue
        for name, pat in HIGH_MARKERS:
            if pat.search(line):
                high.append({"line_no": i, "marker": name, "text": line[:220]})
        # nav-link chrome: a line dominated by links with little prose
        if _link_density(line) >= 0.5 and len(_LINK_RE.findall(line)) >= 2:
            high.append({"line_no": i, "marker": "nav_link_density", "text": line[:220]})
        for name, pat in MED_MARKERS:
            if pat.search(line):
                med.append({"line_no": i, "marker": name, "text": line[:220]})
    return {"high": high, "med": med}


def load_rows(snapshot: str) -> list:
    data = json.load(open(snapshot, encoding="utf-8"))
    if isinstance(data, list):
        return data
    for value in data.values():
        if isinstance(value, list):
            return value
    return []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--max-chars", type=int, default=8000)
    parser.add_argument("--parallel", type=int, default=12)
    parser.add_argument("--limit", type=int, default=0, help="0 = all unique urls")
    parser.add_argument("--urls-file", default=None,
                        help="newline-delimited urls OR evidence_ids; restrict the run to just these "
                             "(fast re-test of the leaking subset)")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    subset: set[str] | None = None
    if args.urls_file:
        subset = {ln.strip() for ln in open(args.urls_file, encoding="utf-8") if ln.strip()}
        print(f"[replay] subset mode: {len(subset)} urls/ids from {args.urls_file}", flush=True)

    rows = load_rows(args.snapshot)
    seen: set[str] = set()
    work: list[tuple] = []
    for row in rows:
        url = row.get("source_url")
        if not url or url in seen:
            continue
        if subset is not None and url not in subset and row.get("evidence_id") not in subset:
            continue
        seen.add(url)
        work.append((row.get("evidence_id"), url, row.get("direct_quote") or "", row.get("tier"), row.get("title")))
    if args.limit:
        work = work[: args.limit]
    total = len(work)
    print(f"[replay] {total} unique urls | snapshot={args.snapshot} | max_chars={args.max_chars}", flush=True)

    results: list[dict] = []
    lock = threading.Lock()
    counter = {"done": 0, "leak": 0}

    def do_one(item):
        ev, url, banked, tier, title = item
        t0 = time.time()
        failure_mode = ""
        access = ""
        span = ""
        try:
            out = refetch_for_extraction_with_diagnostics(url, args.max_chars)
            if isinstance(out, tuple):
                span = out[0] or ""
                diag = out[1] if len(out) > 1 and isinstance(out[1], dict) else {}
            else:
                span = out or ""
                diag = {}
            failure_mode = diag.get("failure_mode", "") or ""
            access = diag.get("access_method") or diag.get("access") or diag.get("method") or ""
        except Exception as exc:  # noqa: BLE001 — record the failure honestly, never swallow silently
            failure_mode = f"exception:{type(exc).__name__}"
        accepted = failure_mode == ""
        scan = scan_span(span) if accepted else {"high": [], "med": []}
        rec = {
            "ev": ev, "url": url, "tier": tier, "title": title,
            "failure_mode": failure_mode, "access": access, "chars": len(span),
            "accepted": accepted,
            "high_hits": scan["high"], "med_hits": scan["med"],
            "head": span[:300], "banked_head": (banked or "")[:180],
            "elapsed": round(time.time() - t0, 1),
        }
        with lock:
            counter["done"] += 1
            if accepted and scan["high"]:
                counter["leak"] += 1
                mk = scan["high"][0]
                print(f"[LEAK] {ev} {url}\n       {mk['marker']}: {mk['text']!r}", flush=True)
            if counter["done"] % 25 == 0:
                print(f"[replay] {counter['done']}/{total} (leaks so far={counter['leak']})", flush=True)
        return rec

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.parallel) as pool:
        for rec in pool.map(do_one, work):
            results.append(rec)

    mode_tally = Counter(r["failure_mode"] or "accepted" for r in results)
    accepted = [r for r in results if r["accepted"]]
    leaks_high = [r for r in accepted if r["high_hits"]]
    leaks_med = [r for r in accepted if r["med_hits"] and not r["high_hits"]]
    # REAL junk vs legit-reference false positives (the loop's stop condition = real_junk == 0)
    real_junk = [{"url": r["url"], "ev": r["ev"], "hits": _real_high_hits(r)}
                 for r in leaks_high if _real_high_hits(r)]
    real_junk_urls = sorted({r["url"] for r in real_junk})
    fp_only = [r for r in leaks_high if not _real_high_hits(r)]
    print(f"[replay] DONE. accepted={len(accepted)}/{total} | "
          f"LEAK(high junk inside accepted)={len(leaks_high)} | med-flag={len(leaks_med)} | "
          f"failure_modes={dict(mode_tally)}", flush=True)
    print(f"[replay] SUMMARY real_junk={len(real_junk_urls)} reference_fp={len(fp_only)} "
          f"total_high_leaks={len(leaks_high)}", flush=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out or f"/workspace/POLARIS/outputs/fetch_corpus_replay_{stamp}")
    out_dir.mkdir(parents=True, exist_ok=True)
    json.dump(results, open(out_dir / "results.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)

    with open(out_dir / "report.md", "w", encoding="utf-8") as fh:
        fh.write(f"# Fetch corpus replay + independent junk scan\nsnapshot: {args.snapshot}\n")
        fh.write(f"unique_urls: {total}\naccepted(failure_mode=''): {len(accepted)}\n")
        fh.write(f"LEAK (accepted span with HIGH-confidence junk lines): {len(leaks_high)}\n")
        fh.write(f"MED-flag (accepted span with only medium markers, human-read): {len(leaks_med)}\n")
        fh.write(f"failure_modes: {dict(mode_tally)}\n\n")
        fh.write("## LEAKS — accepted spans carrying HIGH-confidence junk (every hit quoted)\n")
        for r in leaks_high:
            fh.write(f"\n### {r['ev']} T{r['tier']} {r['url']}\n")
            fh.write(f"accepted via={r['access']} chars={r['chars']} title={r['title']!r}\n")
            for h in r["high_hits"][:12]:
                fh.write(f"- [{h['marker']}] L{h['line_no']}: {h['text']!r}\n")
        fh.write("\n## MED-flag accepted spans (read to judge — may be legit)\n")
        for r in leaks_med[:40]:
            fh.write(f"\n### {r['ev']} T{r['tier']} {r['url']}\n")
            for h in r["med_hits"][:6]:
                fh.write(f"- [{h['marker']}] L{h['line_no']}: {h['text']!r}\n")
        fh.write("\n## Rejected-by-gate tally (these did NOT leak — gate caught them)\n")
        for mode, n in mode_tally.most_common():
            if mode == "accepted":
                continue
            fh.write(f"- {mode}: {n}\n")
        fh.write("\n## Clean accepted samples (spot-read that clean == real article)\n")
        clean = [r for r in accepted if not r["high_hits"] and not r["med_hits"]][:12]
        for r in clean:
            fh.write(f"\n### {r['ev']} T{r['tier']} {r['url']}\n  head: {r['head']!r}\n")
    # machine-readable summary + the still-real-junk urls for the next loop round
    json.dump(
        {"total": total, "accepted": len(accepted), "real_junk_count": len(real_junk_urls),
         "reference_fp_count": len(fp_only), "real_junk": real_junk[:80],
         "failure_modes": dict(mode_tally)},
        open(out_dir / "summary.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    with open(out_dir / "next_leaks.txt", "w", encoding="utf-8") as nf:
        nf.write("\n".join(real_junk_urls))
    print(f"[replay] report: {out_dir}/report.md | summary: {out_dir}/summary.json | "
          f"next_leaks: {out_dir}/next_leaks.txt", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
