#!/usr/bin/env python3
"""STEP 15: compose the REAL scoreable multi-section report from the LIVE agentic run.

The mission's metric-(a) full-corpus gate (cp4_used=agentic on the 329-basket corpus) already
PASSED (docs/agentic_sweep_live_summary_s3gear329.json). What was missing was a *composed*
report we can score. This driver closes that gap: it runs the FULL generator
(``generate_multi_section_report``) with the agentic outliner ON (PG_OUTLINE_AGENT=1 + the
§9.1.8 model lock) over data/cp4_corpus_s3gear_329.json and writes report.md.

Model it on scripts/run_honest_on_prerebuild_corpus.py (which already produced report.md +
multi_section_outline.json), minus the retrieval/scope machinery (the corpus is pre-built).

Faithfulness gate (HARD): after composition, assert ZERO unverified numbers reach any
[CITE:ev_xxx] token in the composed report. The strict_verify lane already enforces this
per-section; this driver re-audits the final assembled text as an independent tripwire.

Run (key MUST be in env):
    set -a && . ./.env && set +a
    PG_OUTLINE_AGENT=1 python scripts/compose_agentic_report_s3gear329.py \
        --corpus data/cp4_corpus_s3gear_329.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=os.environ.get("PG_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
for noisy in ("httpx", "httpcore"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
log = logging.getLogger("compose")


def _tier_fractions(evidence: list[dict]) -> dict[str, float]:
    from collections import Counter
    c = Counter((e.get("tier") or "T?").upper() for e in evidence)
    n = sum(c.values()) or 1
    return {k: v / n for k, v in sorted(c.items())}


# A numeric token that would be a faithfulness breach if it sat inside a [CITE:] sentence
# without having passed strict_verify. We audit the FINAL assembled report: any [CITE:ev_xxx]
# in the verified text is, by construction, already span-grounded — but we re-scan to prove it.
_CITE_RE = re.compile(r"\[CITE:(ev_[0-9a-fA-F]+|[a-z0-9_]+)\]")


def _audit_citations(report_text: str, biblio: list[dict]) -> dict:
    """Independent faithfulness tripwire on the FINAL assembled report.

    strict_verify resolves every kept sentence's provenance token into a global [N] bibliography
    marker and DROPS any sentence whose number failed the span match. So in a faithful final
    report: (1) ZERO raw [CITE:ev_xxx] tokens survive (any survivor is an unverified-number leak
    — the exact breach the mission forbids), and (2) every [N] marker in the prose resolves to a
    real bibliography entry. We assert both."""
    leaked_cites = _CITE_RE.findall(report_text)
    body = report_text.split("\n\n## Bibliography\n", 1)[0]  # markers in prose only
    n_markers = set(int(m) for m in re.findall(r"\[(\d+)\]", body))
    biblio_nums = {int(b.get("num")) for b in biblio if str(b.get("num", "")).isdigit()}
    unresolved = sorted(n for n in n_markers if n not in biblio_nums)
    return {
        "leaked_cite_ev_tokens": len(leaked_cites),
        "leaked_cite_samples": sorted(set(leaked_cites))[:10],
        "distinct_bib_markers_in_prose": len(n_markers),
        "bibliography_entries": len(biblio_nums),
        "unresolved_markers": unresolved,
    }


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--max-parallel", type=int, default=3)
    args = ap.parse_args()

    if not os.getenv("OPENROUTER_API_KEY"):
        log.error("BLOCKED: OPENROUTER_API_KEY not in env — source .env first "
                  "(set -a && . ./.env && set +a)")
        return 2
    # The mission model-lock: agentic outliner ON.
    os.environ.setdefault("PG_OUTLINE_AGENT", "1")

    corpus_path = Path(args.corpus)
    corpus = json.loads(corpus_path.read_text())
    rq = corpus["research_question"]
    evidence = corpus["evidence"]
    raw_clusters = corpus.get("finding_clusters") or []
    clusters = [SimpleNamespace(**c) if isinstance(c, dict) else c for c in raw_clusters]
    swg = corpus.get("same_work_groups")
    domain = corpus.get("domain", "")

    run_id = time.strftime("agentic_report_%Y%m%d_%H%M%S")
    run_dir = ROOT / (args.out_dir or f"outputs/{run_id}")
    run_dir.mkdir(parents=True, exist_ok=True)
    log.info("corpus=%s  evidence=%d  clusters=%d  same_work_groups=%s  domain=%s",
             corpus_path.name, len(evidence), len(clusters),
             len(swg or []), domain or "(none)")
    log.info("PG_OUTLINE_AGENT=%s  out_dir=%s", os.getenv("PG_OUTLINE_AGENT"), run_dir)

    from src.polaris_graph.generator.multi_section_generator import (  # noqa: PLC0415
        generate_multi_section_report,
    )
    from src.polaris_graph.llm.openrouter_client import (  # noqa: PLC0415
        PG_EVALUATOR_MODEL, PG_GENERATOR_MODEL,
    )
    from src.polaris_graph.outline.outline_agent import (  # noqa: PLC0415
        outliner_agent_model, outliner_code_model,
    )

    dist = _tier_fractions(evidence)
    log.info("tier fractions: %s", {k: round(v, 3) for k, v in dist.items()})
    log.info("[gen] agent_model=%s code_model=%s generator=%s",
             outliner_agent_model(), outliner_code_model(), PG_GENERATOR_MODEL)

    t0 = time.time()
    multi = await generate_multi_section_report(
        research_question=rq,
        evidence=evidence,
        finding_clusters=clusters,
        same_work_groups=swg,
        section_temperature=0.3,
        outline_max_tokens=2500,
        section_max_tokens=2400,
        min_kept_fraction=0.4,
        max_parallel_sections=args.max_parallel,
        tier_fractions=dist,
    )
    dt = time.time() - t0
    kept = [s for s in multi.sections if not s.dropped_due_to_failure]
    log.info("[gen] elapsed=%.1fs  outline=%d sections  kept=%d  words=%s  "
             "verified=%s  dropped=%s  in_tok=%s out_tok=%s",
             dt, len(multi.outline), len(kept), getattr(multi, "total_words", "?"),
             getattr(multi, "total_sentences_verified", "?"),
             getattr(multi, "total_sentences_dropped", "?"),
             getattr(multi, "total_input_tokens", "?"),
             getattr(multi, "total_output_tokens", "?"))
    for sr in multi.sections:
        mark = "OK " if not sr.dropped_due_to_failure else "DROP"
        log.info("   [%s] %-42s verified=%s dropped=%s regen=%s",
                 mark, sr.title[:42], sr.sentences_verified,
                 sr.sentences_dropped, sr.regen_attempted)

    # Persist the outline
    (run_dir / "multi_section_outline.json").write_text(
        json.dumps([{"title": p.title, "focus": p.focus, "ev_ids": p.ev_ids}
                    for p in multi.outline], indent=2, sort_keys=True) + "\n",
        encoding="utf-8")

    # Assemble the report body from VERIFIED text only.
    bodies: list[str] = []
    for sr in multi.sections:
        if sr.dropped_due_to_failure or not sr.verified_text:
            continue
        bodies.append(f"### {sr.title}\n\n{sr.verified_text}")
    sections_concat = "\n\n".join(bodies)
    if getattr(multi, "limitations_text", ""):
        sections_concat += f"\n\n### Limitations\n\n{multi.limitations_text}"

    tier_summary = ", ".join(f"{k}={v*100:.0f}%" for k, v in sorted(dist.items()))
    methods = (
        "\n\n## Methods\n"
        f"Corpus: {corpus_path.name} ({len(evidence)} evidence rows, {len(clusters)} baskets; "
        f"domain={domain or 'general'}).\n"
        f"Outliner: AGENTIC (PG_OUTLINE_AGENT=1) — agent {outliner_agent_model()}, "
        f"code {outliner_code_model()}.\n"
        f"Generator: {PG_GENERATOR_MODEL} (multi-section: agentic outline + "
        f"{len(kept)} parallel verified sections + strict_verify + regen-on-failure).\n"
        f"Evaluator/mirror: {PG_EVALUATOR_MODEL}.\n"
        f"Tier distribution: {tier_summary}.\n"
    )
    biblio = getattr(multi, "bibliography", []) or []
    biblio_section = "\n\n## Bibliography\n"
    for b in biblio:
        biblio_section += (f"[{b.get('num')}] {str(b.get('statement',''))[:200]} — "
                           f"{b.get('url','')} (tier {b.get('tier','')})\n")

    final_report = f"# Research report: {rq}\n\n{sections_concat}{methods}{biblio_section}"
    (run_dir / "report.md").write_text(final_report, encoding="utf-8")
    (run_dir / "bibliography.json").write_text(
        json.dumps(biblio, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    audit = _audit_citations(final_report, biblio)
    faithful = (audit["leaked_cite_ev_tokens"] == 0 and not audit["unresolved_markers"])
    log.info("[faithfulness] leaked_[CITE:ev]=%d  bib_markers_in_prose=%d  bib_entries=%d  "
             "unresolved_markers=%s -> %s",
             audit["leaked_cite_ev_tokens"], audit["distinct_bib_markers_in_prose"],
             audit["bibliography_entries"], audit["unresolved_markers"],
             "PASS" if faithful else "FAIL")

    summary = {
        "corpus": corpus_path.name,
        "research_question": rq[:160],
        "evidence_rows": len(evidence),
        "baskets": len(clusters),
        "same_work_groups": len(swg or []),
        "outline_sections": len(multi.outline),
        "kept_sections": len(kept),
        "dropped_sections": len(multi.sections) - len(kept),
        "total_words": getattr(multi, "total_words", None),
        "total_sentences_verified": getattr(multi, "total_sentences_verified", None),
        "total_sentences_dropped": getattr(multi, "total_sentences_dropped", None),
        "bibliography_entries": len(biblio),
        "report_chars": len(final_report),
        "report_words": len(final_report.split()),
        "faithfulness_audit": audit,
        "faithfulness_pass": faithful,
        "moat_quantified_models": len(getattr(multi, "quantified_models", None) or {}),
        "agent_model": outliner_agent_model(),
        "code_model": outliner_code_model(),
        "generator_model": PG_GENERATOR_MODEL,
        "elapsed_seconds": round(dt, 1),
        "out_dir": str(run_dir),
    }
    (run_dir / "compose_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    log.info("WROTE %s (%d chars, %d words) + compose_summary.json",
             run_dir / "report.md", len(final_report), len(final_report.split()))
    print(json.dumps(summary, indent=2))
    return 0 if faithful else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
