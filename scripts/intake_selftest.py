#!/usr/bin/env python3
"""S0 INTAKE offline self-test — proves the five RunConfig conditions with NO network/GPU.

The whole S0 layer is pure logic: regex extractors + a registry-driven precedence
resolver + a cp0 writer. This harness exercises that layer end-to-end with the LLM passes
OFF (``llm_fn=None`` everywhere) and an empty env, so it runs in seconds anywhere and is a
real preflight for the intake contract. It proves, and prints ``summary.json`` with each
as a boolean + an evidence string:

  (a) scope parsed from the prompt — dates / source-type / geography / language / author
      each land in RunConfig with source='parsed';
  (b) deliverable parsed — tone / structure / reference_style / length each land;
  (c) breadth parsed — query_count (incl a 35+ case) + searches_per_query land;
  (d) a control-panel override BEATS the prompt (panel > parsed precedence);
  (e) cp0_run_config.json carries EVERY registry knob + its resolved source, none
      hardcoded (every default value traces to the registry yaml, not a code literal).

Usage:  python scripts/intake_selftest.py [--out summary.json]
Exit code 0 iff all five conditions pass.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.polaris_graph.run_config import (  # noqa: E402
    SOURCE_PANEL,
    SOURCE_PARSED,
    assemble_run_config,
    load_cp0_run_config,
    load_knob_registry,
    write_cp0_run_config,
)

# One rich prompt carrying scope + deliverable + breadth asks, so a/b/c read the SAME
# resolved object (as production would). Every ask is a verbatim phrase the regex parses.
RICH_PROMPT = (
    "Write a two-page plain-language policy memo with Harvard references and an executive "
    "summary first, about 1500 words, on randomized trials of tirzepatide published since "
    "2019 and before June 2023, using peer-reviewed journal articles only, focused on "
    "European sources, in English, and prioritize research by Anthony Fauci. Run at least "
    "45 queries with 20 searches per query. Include a section on cardiovascular outcomes "
    "and organize by region."
)

_ALLOWED_SOURCES = {"default", "env", "parsed", "panel"}


def _prov(rc, knob_id):
    return rc.provenance.get(knob_id)


def _check_scope(rc) -> tuple[bool, str]:
    checks = {
        "dates": ("date_end", rc.scope.date_end),
        "source_type": ("source_types", rc.scope.source_types),
        "geography": ("geography", rc.scope.geography),
        "language": ("language", rc.scope.language),
        "author": ("authors", rc.scope.authors),
    }
    misses = []
    evid = []
    for label, (kid, val) in checks.items():
        p = _prov(rc, kid)
        ok = bool(val) and p is not None and p.source == SOURCE_PARSED
        if not ok:
            misses.append(f"{label}({kid})=parsed? val={val!r} src={getattr(p, 'source', None)}")
        else:
            evid.append(f"{label}={val!r}<-'{p.span}'")
    if misses:
        return False, "MISS: " + "; ".join(misses)
    return True, "all five scope axes parsed: " + " | ".join(evid)


def _check_deliverable(rc) -> tuple[bool, str]:
    length_ok = (rc.deliverable.length_target_words is not None or
                 rc.deliverable.length_target_pages is not None)
    checks = {
        "tone": ("tone", rc.deliverable.tone),
        "structure": ("structure_slots", rc.deliverable.structure_slots),
        "reference_style": ("reference_style", rc.deliverable.reference_style),
        "length": ("length_target_words" if rc.deliverable.length_target_words is not None
                   else "length_target_pages",
                   rc.deliverable.length_target_words if rc.deliverable.length_target_words is not None
                   else rc.deliverable.length_target_pages),
    }
    misses = []
    evid = []
    for label, (kid, val) in checks.items():
        p = _prov(rc, kid)
        ok = bool(val) and p is not None and p.source == SOURCE_PARSED
        if not ok:
            misses.append(f"{label}({kid})=parsed? val={val!r} src={getattr(p, 'source', None)}")
        else:
            evid.append(f"{label}={val if not isinstance(val, list) else f'{len(val)} slots'}<-'{p.span}'")
    if not length_ok:
        misses.append("length: no words/pages parsed")
    if misses:
        return False, "MISS: " + "; ".join(misses)
    return True, "tone/structure/reference_style/length parsed: " + " | ".join(evid)


def _check_breadth(rc) -> tuple[bool, str]:
    qb = rc.breadth.query_budget
    qp = _prov(rc, "query_budget")
    sk = rc.breadth.serper_k
    sp = _prov(rc, "serper_k")
    q_ok = qb is not None and qb >= 35 and qp is not None and qp.source == SOURCE_PARSED
    s_ok = sk is not None and sp is not None and sp.source == SOURCE_PARSED
    if not (q_ok and s_ok):
        return False, (f"MISS: query_budget={qb!r}(>=35 & parsed? {q_ok}) "
                       f"searches_per_query/serper_k={sk!r}(parsed? {s_ok})")
    return True, (f"query_count parsed >=35: query_budget={qb} (35+ case)<-'{qp.span}'; "
                  f"searches_per_query=serper_k={sk}<-'{sp.span}'")


def _check_panel_beats_prompt(registry) -> tuple[bool, str]:
    # Baseline: the prompt asks for 45 queries (parsed). Now set the SAME knob on the panel
    # to a different value; the panel must win.
    baseline = assemble_run_config(RICH_PROMPT, env={}, registry=registry)
    parsed_val = baseline.breadth.query_budget
    parsed_src = baseline.source_of("query_budget")
    override = assemble_run_config(
        RICH_PROMPT, env={}, registry=registry, panel_overrides={"query_budget": 99},
    )
    ov_val = override.breadth.query_budget
    ov_src = override.source_of("query_budget")
    ok = (parsed_src == SOURCE_PARSED and parsed_val == 45
          and ov_val == 99 and ov_src == SOURCE_PANEL)
    if not ok:
        return False, (f"MISS: prompt-parsed query_budget={parsed_val}({parsed_src}); "
                       f"panel override -> {ov_val}({ov_src}) (expected 99/panel)")
    return True, (f"prompt parsed query_budget=45 (source={parsed_src}); control panel set "
                  f"query_budget=99 -> resolved 99 (source={ov_src}) - panel beats prompt")


def _check_cp0_every_knob(rc, registry) -> tuple[bool, str]:
    registry_ids = {str(r.get("id")) for r in registry if r.get("id")}
    default_map = {str(r.get("id")): r.get("code_default") for r in registry if r.get("id")}
    with tempfile.TemporaryDirectory() as td:
        path = write_cp0_run_config(rc, td)
        reloaded = load_cp0_run_config(path)
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    prov_ids = set(raw.get("provenance", {}).keys())
    missing = registry_ids - prov_ids
    bad_source = []
    hardcoded = []
    for kid in registry_ids:
        pv = raw["provenance"].get(kid, {})
        src = pv.get("source")
        if src not in _ALLOWED_SOURCES:
            bad_source.append(f"{kid}={src}")
        # "none hardcoded": a default-sourced knob MUST equal the registry code_default
        # (so the value came from the yaml, never a literal buried in run_config.py).
        if src == "default" and pv.get("value") != default_map.get(kid):
            hardcoded.append(f"{kid}: cp0={pv.get('value')!r} != registry={default_map.get(kid)!r}")
    # round-trip sanity
    rt_ok = reloaded.question_sha == rc.question_sha
    problems = []
    if missing:
        problems.append(f"missing knobs in cp0: {sorted(missing)}")
    if bad_source:
        problems.append(f"bad source layer: {bad_source}")
    if hardcoded:
        problems.append(f"hardcoded (default != registry): {hardcoded}")
    if not rt_ok:
        problems.append("cp0 round-trip question_sha mismatch")
    if problems:
        return False, "MISS: " + "; ".join(problems)
    n_default = sum(1 for kid in registry_ids if raw["provenance"][kid]["source"] == "default")
    return True, (f"cp0 carries all {len(registry_ids)} registry knobs, each with a source in "
                  f"{sorted(_ALLOWED_SOURCES)}; {n_default} default-sourced values all equal "
                  f"the registry code_default (none hardcoded); round-trip sha ok")


def run_selftest() -> dict:
    os.environ.pop("PG_DELIVERABLE_SPEC_LLM", None)
    registry = load_knob_registry()
    rc = assemble_run_config(RICH_PROMPT, env={}, registry=registry)

    conditions = {}
    a_ok, a_ev = _check_scope(rc)
    conditions["a_scope_parsed"] = {"pass": a_ok, "evidence": a_ev}
    b_ok, b_ev = _check_deliverable(rc)
    conditions["b_deliverable_parsed"] = {"pass": b_ok, "evidence": b_ev}
    c_ok, c_ev = _check_breadth(rc)
    conditions["c_breadth_parsed"] = {"pass": c_ok, "evidence": c_ev}
    d_ok, d_ev = _check_panel_beats_prompt(registry)
    conditions["d_panel_beats_prompt"] = {"pass": d_ok, "evidence": d_ev}
    e_ok, e_ev = _check_cp0_every_knob(rc, registry)
    conditions["e_cp0_every_knob_no_hardcode"] = {"pass": e_ok, "evidence": e_ev}

    all_pass = all(c["pass"] for c in conditions.values())
    return {
        "harness": "scripts/intake_selftest.py",
        "offline": True,
        "network_used": False,
        "gpu_used": False,
        "registry_knob_count": len(registry),
        "prompt": RICH_PROMPT,
        "all_pass": all_pass,
        "conditions": conditions,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="S0 INTAKE offline self-test")
    ap.add_argument("--out", default="", help="write summary.json to this path (optional)")
    args = ap.parse_args()

    summary = run_selftest()
    text = json.dumps(summary, indent=2, ensure_ascii=False)
    print(text)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    return 0 if summary["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
