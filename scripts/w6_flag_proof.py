#!/usr/bin/env python3
"""W6 proof harness — the shipping vehicle is DEFAULT OFF, and when it is ON it BITES.

Rank11's lesson: a default-off flag that nobody proves is a flag that fires and consolidates ZERO.
So this harness exercises the EXACT seam the composer ships through — ``_maybe_reflow_report``,
imported from scripts/compose_agentic_report_s3gear329.py, the same object the composer calls
between the sections_concat assembly and the report.md write — on a BANKED report.

  A. PG_REPORT_REFLOW unset  -> report.md bytes IDENTICAL (sha256 equal, same object returned,
                                no reflow_audit.json written, no model call).
  B. PG_REPORT_REFLOW=0      -> same.
  C. PG_REPORT_REFLOW=1, model unreachable -> fail-closed: every section reverts, a valid report
                                still ships (the LLM is not a dependency of correctness).
  D. --live: PG_REPORT_REFLOW=1 against the real model -> the document must actually CHANGE
                                (H3s / bullets / tables / class-I), i.e. the lever BITES.

Usage:
    python scripts/w6_flag_proof.py --run outputs/rank12_tierfirst_compose
    set -a && . ./.env && set +a && python scripts/w6_flag_proof.py --run <dir> --live
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import logging
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load_composer():
    spec = importlib.util.spec_from_file_location(
        "_pg_composer", str(ROOT / "scripts" / "compose_agentic_report_s3gear329.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, help="banked compose dir (report.md + bibliography.json)")
    ap.add_argument("--live", action="store_true", help="also run the ON path against the real model")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    run = Path(a.run)
    report = (run / "report.md").read_text(encoding="utf-8")
    biblio = json.loads((run / "bibliography.json").read_text(encoding="utf-8"))
    src_hash = sha(report)
    comp = _load_composer()

    print(f"source           : {run/'report.md'}")
    print(f"source sha256    : {src_hash}  ({len(report)} bytes)")
    fails = 0

    # ---- A/B: DEFAULT OFF => byte-identical -------------------------------------------------
    for label, env in (("A unset", None), ("B '0'", "0"), ("B 'off'", "off")):
        os.environ.pop("PG_REPORT_REFLOW", None)
        if env is not None:
            os.environ["PG_REPORT_REFLOW"] = env
        with tempfile.TemporaryDirectory() as td:
            out = comp._maybe_reflow_report(report, biblio, Path(td))
            audit_written = (Path(td) / "reflow_audit.json").exists()
        ok = sha(out) == src_hash and out is report and not audit_written
        fails += 0 if ok else 1
        print(f"[{'PASS' if ok else '**FAIL**'}] {label:8s} -> sha256 {sha(out)} "
              f"identical={sha(out) == src_hash} same_object={out is report} "
              f"audit_written={audit_written}")

    # ---- D: ON + real model => must BITE ----------------------------------------------------
    # D runs BEFORE C on purpose: C blanks OPENROUTER_API_KEY, and the OpenRouter client caches its
    # settings on first construction, so a C-then-D order silently starves the live run of its key
    # (the first version of this harness did exactly that and D "passed" with every section reverted).
    if a.live:
        os.environ["PG_REPORT_REFLOW"] = "1"
        with tempfile.TemporaryDirectory() as td:
            out = comp._maybe_reflow_report(report, biblio, Path(td))
            audit = json.loads((Path(td) / "reflow_audit.json").read_text())
        bit = audit.get("bit") and sha(out) != src_hash
        fails += 0 if bit else 1
        print(f"[{'PASS' if bit else '**FAIL**'}] D live     -> BIT={audit.get('bit')} "
              f"H3={audit.get('h3_subsections')} bullets={audit.get('bullets')} "
              f"tables={audit.get('tables')} class-I={audit.get('class_I_count')} "
              f"confessions_purged={audit.get('confessions_purged')} "
              f"words {audit.get('src_body_words')}->{audit.get('out_body_words')}")
        (ROOT / "outputs" / "w6_live_reflow.md").write_text(out, encoding="utf-8")
        print(f"           live output written to {ROOT/'outputs'/'w6_live_reflow.md'}")

    # ---- C: ON + model unreachable => fail-closed, still a valid report ----------------------
    os.environ["PG_REPORT_REFLOW"] = "1"
    saved_key = os.environ.pop("OPENROUTER_API_KEY", None)
    os.environ["OPENROUTER_API_KEY"] = ""
    with tempfile.TemporaryDirectory() as td:
        out = comp._maybe_reflow_report(report, biblio, Path(td))
        audit = json.loads((Path(td) / "reflow_audit.json").read_text()) if (
            Path(td) / "reflow_audit.json").exists() else {}
    if saved_key is not None:
        os.environ["OPENROUTER_API_KEY"] = saved_key
    else:
        os.environ.pop("OPENROUTER_API_KEY", None)
    ok_c = bool(out.strip()) and "## References" in out and "[1]" in out
    fails += 0 if ok_c else 1
    print(f"[{'PASS' if ok_c else '**FAIL**'}] C on/no-LLM -> fail-closed report shipped "
          f"({len(out.split())} words, refs kept), audit bit={audit.get('bit')}")

    os.environ.pop("PG_REPORT_REFLOW", None)
    print("\n" + ("ALL CHECKS PASS" if not fails else f"{fails} CHECK(S) FAILED"))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
