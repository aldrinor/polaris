#!/usr/bin/env python
"""I-wire-014 quantified replay harness (#1336).

Reproduce the Phase-7 quantified SILENT NO-OP (firing_status=spec_validation_rejected)
on the BANKED drb_72 corpus, WITHOUT a full sweep. Two modes:

  --writer   : ONE billed Writer (spec_provider) call on the VM (GLM-5.2). Banks the
               raw_spec JSON to <out>/raw_spec.json so all downstream iteration is offline.
  (default)  : load <out>/raw_spec.json (banked) and run build_quantified_spec +
               run_quantified_section OFFLINE with on_reject capturing the exact gate.

LAW II: real banked corpus, no synthetic data. LAW VI: paths/model via args/env.
SPEND: --writer is the ONLY billed step (one call); the offline mode is spend-free.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

# repo root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.polaris_graph.tools.evidence_extractor import extract_numbers_from_evidence


def _load_evidence_pool(corpus_dir: str) -> dict[str, dict]:
    """Load the banked evidence_pool.json (a list) into the {ev_id: row} dict the
    quantified path expects (mirrors run_honest_sweep_r3.py _q_ev_pool build)."""
    path = os.path.join(corpus_dir, "evidence_pool.json")
    with open(path, encoding="utf-8") as fh:
        rows = json.load(fh)
    if isinstance(rows, dict):
        rows = list(rows.values())
    pool = {
        ev["evidence_id"]: ev
        for ev in rows
        if isinstance(ev, dict) and ev.get("evidence_id")
    }
    return pool


def _load_question(corpus_dir: str) -> str:
    snap = os.path.join(corpus_dir, "corpus_snapshot.json")
    with open(snap, encoding="utf-8") as fh:
        d = json.load(fh)
    return d.get("question", "")


async def _writer_call(question: str, sourced: list[dict], out_dir: str) -> dict | None:
    """Replicate the run_honest_sweep_r3.py _q_spec_provider Writer call EXACTLY, then
    bank both the raw response text and the parsed raw_spec for offline iteration."""
    from src.polaris_graph.llm.openrouter_client import (
        OpenRouterClient,
        PG_GENERATOR_MODEL,
    )
    from scripts.run_honest_sweep_r3 import parse_quantified_spec_response

    shortlist = [
        {"evidence_id": d.get("evidence_id"), "label": d.get("label"),
         "context": d.get("context"), "value": d.get("value"),
         "unit": d.get("unit")}
        for d in sourced[:40]
    ]
    prompt = (
        "You are modeling a quantified trade-off for a research "
        "report. Using ONLY the sourced numbers below, emit a "
        "SINGLE JSON object (no prose) with keys model_id, title, "
        "inputs, outputs, sensitivity, solve_for per the POLARIS "
        "ModelSpec schema. Each SOURCED input MUST carry "
        "datapoint_ref:{ev_id,label,context,value,unit} copied "
        "EXACTLY from one listed number; mark every ASSUMPTION "
        "input modeled:true with base+unit+sweep. Every output "
        "formula must be pure arithmetic over the declared input "
        "names. If the numbers do not support a defensible model, "
        'return {"model_id":"none"} and nothing else.\n\n'
        f"QUESTION: {question}\n\n"
        f"SOURCED NUMBERS (JSON): {json.dumps(shortlist)[:8000]}"
    )
    max_tokens = int(os.environ.get("PG_QUANTIFIED_SPEC_MAX_TOKENS", "32768"))
    reasoning_max = int(os.environ.get("PG_QUANTIFIED_SPEC_REASONING_MAX_TOKENS", "8192"))
    client = OpenRouterClient(model=PG_GENERATOR_MODEL)
    try:
        resp = await client.generate(
            prompt, max_tokens=max_tokens, temperature=0.0,
            reasoning_max_tokens=reasoning_max,
            response_format={"type": "json_object"},
        )
    finally:
        await client.close()
    txt = getattr(resp, "content", "") or ""
    if not txt.strip():
        txt = getattr(resp, "reasoning", "") or ""
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "writer_raw_text.txt"), "w", encoding="utf-8") as fh:
        fh.write(txt)
    with open(os.path.join(out_dir, "writer_shortlist.json"), "w", encoding="utf-8") as fh:
        json.dump(shortlist, fh, indent=2)
    raw_spec = parse_quantified_spec_response(txt, sourced_count=len(sourced))
    with open(os.path.join(out_dir, "raw_spec.json"), "w", encoding="utf-8") as fh:
        json.dump(raw_spec, fh, indent=2)
    print(f"[writer] model={PG_GENERATOR_MODEL} content_chars={len(txt)} "
          f"raw_spec={'dict' if isinstance(raw_spec, dict) else raw_spec}")
    return raw_spec


def _offline_build(question: str, sourced: list[dict], pool: dict, out_dir: str) -> None:
    """Run build_quantified_spec on the banked raw_spec with on_reject capture."""
    from src.polaris_graph.synthesis.tradeoff_modeler import build_quantified_spec

    raw_path = os.path.join(out_dir, "raw_spec.json")
    with open(raw_path, encoding="utf-8") as fh:
        raw_spec = json.load(fh)
    if not isinstance(raw_spec, dict):
        print(f"[offline] raw_spec is not a dict ({raw_spec!r}) -> declined_no_spec")
        return
    reasons: list[str] = []
    spec = build_quantified_spec(
        question, sourced, pool,
        spec_llm=lambda _q, _s: raw_spec,
        on_reject=reasons.append,
    )
    print(f"[offline] inputs in raw_spec: {len(raw_spec.get('inputs', []))}")
    print(f"[offline] outputs in raw_spec: {len(raw_spec.get('outputs', []))}")
    if spec is None:
        print(f"[offline] REJECTED. reason(s): {reasons}")
    else:
        print(f"[offline] SPEC BUILT. model_id={spec.model_id} "
              f"sourced={len(spec.sourced_inputs)} modeled={len(spec.modeled_inputs)} "
              f"outputs={len(spec.outputs)}")


async def _offline_section(question: str, pool: dict, out_dir: str) -> None:
    """Run the full run_quantified_section using the banked raw_spec as the provider."""
    from src.polaris_graph.generator.quantified_analysis import run_quantified_section

    raw_path = os.path.join(out_dir, "raw_spec.json")
    with open(raw_path, encoding="utf-8") as fh:
        raw_spec = json.load(fh)

    async def _provider(_q, _s):
        return raw_spec

    section_md, telem = await run_quantified_section(
        question, pool, spec_provider=_provider, run_dir=out_dir,
    )
    print(f"[section] firing_status={telem.get('firing_status')} "
          f"quantified_status={telem.get('quantified_status')} "
          f"spec_reject_reason={telem.get('spec_reject_reason')} "
          f"verified_sentences={telem.get('verified_sentences')} "
          f"spec_produced={telem.get('spec_produced')}")
    if section_md:
        print("=== SECTION MD ===")
        print(section_md[:2000])
    with open(os.path.join(out_dir, "section_telem.json"), "w", encoding="utf-8") as fh:
        json.dump(telem, fh, indent=2, default=str)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--writer", action="store_true",
                    help="make the ONE billed Writer call and bank raw_spec.json")
    args = ap.parse_args()

    pool = _load_evidence_pool(args.corpus_dir)
    question = _load_question(args.corpus_dir)
    sourced = extract_numbers_from_evidence(pool)
    print(f"[harness] evidence rows={len(pool)} sourced_numbers={len(sourced)} "
          f"question[:60]={question[:60]!r}")
    os.makedirs(args.out_dir, exist_ok=True)
    # bank the extracted sourced numbers for offline label/context inspection
    with open(os.path.join(args.out_dir, "sourced_numbers.json"), "w", encoding="utf-8") as fh:
        json.dump(sourced[:60], fh, indent=2)

    if args.writer:
        asyncio.run(_writer_call(question, sourced, args.out_dir))
        return

    _offline_build(question, sourced, pool, args.out_dir)
    asyncio.run(_offline_section(question, pool, args.out_dir))


if __name__ == "__main__":
    main()
