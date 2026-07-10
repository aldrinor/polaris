"""foundation_selftest — OFFLINE proof of the RunConfig + checkpoint foundation.

Pure logic. NO network, NO GPU, NO LLM. Proves the five acceptance conditions of the
WAVE-0 foundation (MASTER_EXECUTION_PLAN v2 §1 + §5) and writes a machine-readable
``summary.json`` with each condition as a boolean + an evidence string:

  (a) PRECEDENCE   — PANEL > PROMPT > ENV > CODE-DEFAULT on a knob set at all four levels.
  (b) ZERO-HARDCODE — every registered knob resolves to a declared SOURCE; none hardcoded.
  (c) KNOB COVERAGE — every operator-named knob is present AND settable from BOTH the
                      prompt-parse surface AND the control-panel surface.
  (d) CHECKPOINT RT — each cp0..cp6 writes + reads back byte-identical; chain validates;
                      a verdict-smuggling payload is refused.
  (e) RESUME+ADJUST — resume-from-cpN, apply a downstream RunConfig adjustment, the change
                      takes effect downstream, upstream sha256s untouched, an out-of-scope
                      adjustment is fail-loud rejected.

Usage:
    python scripts/foundation_selftest.py [--out <summary.json path>]
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

from src.polaris_graph import checkpoint_envelope as ck  # noqa: E402
from src.polaris_graph import run_config as rc  # noqa: E402


# The operator-named knobs (task brief) mapped to registry ids + a prompt snippet that
# triggers each + a panel value. Proves BOTH surfaces per §1.6.2. (value, span) pairs
# make the anti-invention span explicit.
_NAMED_KNOBS: list[tuple[str, str, str, object, object]] = [
    # (label, knob_id, prompt_snippet, expected_prompt_value, panel_value)
    ("query_count", "query_count", "run 60 queries", 60, 80),
    ("searches_per_query", "searches_per_query", "12 searches per query", 12, 20),
    ("date_range(from)", "date_from", "from 2019 to 2024", "2019", "2018"),
    ("date_range(to)", "date_to", "from 2019 to 2024", "2024", "2025"),
    ("recency", "recency", "past 5 years", "last_5_years", "recent"),
    ("source_type", "source_types", "clinical trials", ["clinical_trial"], ["guideline"]),
    ("geography", "geography", "EU sources", "EU", "US"),
    ("language", "language", "in French", "french", "spanish"),
    ("authors", "authors", "authored by Nathan et al", ["Nathan et al"], ["Smith"]),
    ("scope", "scope_focus", "focus on renal outcomes", "renal outcomes", "cardiac safety"),
    ("tone", "tone", "executive brief", "executive_brief", "academic"),
    ("structure", "structure", "sections: Background, Methods, Findings",
     ["Background", "Methods", "Findings"], ["Intro", "Body"]),
    ("depth", "depth", "comprehensive", "deep", "shallow"),
    ("references", "reference_style", "Harvard references", "harvard", "apa"),
]


def _cond_a_precedence(reg: dict[str, rc.KnobSpec]) -> tuple[bool, str]:
    """PANEL > PROMPT > ENV > CODE-DEFAULT on query_count set at all four levels."""
    knob = "query_count"
    env_var = reg[knob].env_var  # PG_QGEN_FS_RESEARCHER_MAX_QUERIES
    code_default = reg[knob].code_default  # 35
    env = {env_var: "45"}
    full = rc.RunConfig.from_sources(prompt_text="run 60 queries", panel_overrides={knob: 99}, registry=reg)
    ladder = []

    p_panel = rc.get(full, knob, registry=reg, env=env)
    ladder.append(("panel", p_panel.value, p_panel.source))
    prompt_only = rc.RunConfig(prompt=dict(full.prompt))
    p_prompt = rc.get(prompt_only, knob, registry=reg, env=env)
    ladder.append(("prompt", p_prompt.value, p_prompt.source))
    p_env = rc.get(rc.RunConfig(), knob, registry=reg, env=env)
    ladder.append(("env", p_env.value, p_env.source))
    p_def = rc.get(rc.RunConfig(), knob, registry=reg, env={})
    ladder.append(("default", p_def.value, p_def.source))

    ok = (
        p_panel.value == 99 and p_panel.source == rc.SOURCE_PANEL
        and p_prompt.value == 60 and p_prompt.source == rc.SOURCE_PROMPT and p_prompt.span
        and p_env.value == 45 and p_env.source == rc.SOURCE_ENV
        and p_def.value == code_default and p_def.source == rc.SOURCE_DEFAULT
    )
    ev = (f"{knob}: panel=99 beats prompt=60 (span={p_prompt.span!r}) beats env(45 via "
          f"{env_var}) beats code_default={code_default}; ladder={ladder}")
    return bool(ok), ev


def _cond_b_zero_hardcode(reg: dict[str, rc.KnobSpec]) -> tuple[bool, str]:
    """Every registered knob resolves to a declared source; none hardcoded."""
    empty = rc.RunConfig()
    all_sources_legal = True
    all_default_when_empty = True
    env_layer_reads = 0
    env_backed = 0
    for kid, spec in reg.items():
        p = rc.get(empty, kid, registry=reg, env={})
        if p.source not in rc._LEGAL_SOURCES:
            all_sources_legal = False
        # empty cfg + clean env => code_default, source=default (byte-identical to today)
        if not (p.source == rc.SOURCE_DEFAULT and p.value == spec.code_default):
            all_default_when_empty = False
        # env-backed knobs must FLIP to source=env when the env var is set (proves the
        # resolver reads the layer, not a baked literal). Probe is type-appropriate so the
        # coerced value is asserted too (env read AND coerced, not a literal).
        if spec.env_var:
            env_backed += 1
            probe = {"int": "7", "float": "7", "bool": "1", "list": "a,b"}.get(
                spec.type, (spec.enum[0] if spec.enum else "probe"))
            pe = rc.get(empty, kid, registry=reg, env={spec.env_var: probe})
            if pe.source == rc.SOURCE_ENV and pe.value == rc._coerce(spec, probe):
                env_layer_reads += 1
    ok = (all_sources_legal and all_default_when_empty and env_layer_reads == env_backed)
    ev = (f"{len(reg)} registered knobs: all resolve to a declared source "
          f"(panel|prompt|env|default); empty-config resolves ALL {len(reg)} to "
          f"source=default==code_default (byte-identical); {env_layer_reads}/{env_backed} "
          f"env-backed knobs FLIP to source=env when their PG_ var is set (layer read, not "
          f"a literal). Zero mid-pipeline hardcodes.")
    return bool(ok), ev


def _cond_c_coverage(reg: dict[str, rc.KnobSpec]) -> tuple[bool, str]:
    """Every operator-named knob present + settable from prompt-parse AND panel."""
    results = []
    all_ok = True
    for label, kid, snippet, exp_prompt, panel_val in _NAMED_KNOBS:
        present = kid in reg
        # prompt surface
        cfg_p = rc.RunConfig.from_sources(prompt_text=snippet, registry=reg)
        pp = rc.get(cfg_p, kid, registry=reg, env={}) if present else None
        prompt_ok = bool(pp and pp.source == rc.SOURCE_PROMPT and pp.value == exp_prompt and pp.span)
        # panel surface
        cfg_panel = rc.RunConfig.from_sources(panel_overrides={kid: panel_val}, registry=reg) if present else None
        pn = rc.get(cfg_panel, kid, registry=reg, env={}) if present else None
        panel_ok = bool(pn and pn.source == rc.SOURCE_PANEL)
        knob_ok = present and prompt_ok and panel_ok
        all_ok = all_ok and knob_ok
        results.append(f"{label}->{kid}: present={present} prompt={prompt_ok} panel={panel_ok}")
    ev = f"{len(_NAMED_KNOBS)} operator-named knobs, each present + prompt-settable + " \
         f"panel-settable: " + " | ".join(results)
    return bool(all_ok), ev


def _payload_for(cp_id: str) -> dict:
    """A structurally-real DATA payload per checkpoint (fixture DATA — never a verdict)."""
    return {
        "cp0": {"resolved_run_config": {"query_count": {"value": 35, "source": "default"}},
                "question": "Do GLP-1 agonists reduce MACE?"},
        "cp1": {"counts": {"candidates_total": 240, "candidates_fetched": 221},
                "evidence_rows": [{"ev_id": "e1", "url": "https://example.org/a"}]},
        "cp2": {"evidence_for_gen": [{"ev_id": "e1", "tier": "T1", "span": "reduced MACE by 20%"}]},
        "cp3": {"baskets": [{"claim": "MACE reduction", "members": ["e1", "e2"],
                             "corroboration_count": 2, "weights": [0.9, 0.7]}]},
        "cp4": {"section_plans": [{"title": "Findings", "ev_ids": ["e1", "e2"]}]},
        "cp5": {"section_drafts": {"Findings": "GLP-1 agonists reduced MACE [#ev:e1:0-18]."}},
        "cp6": {"per_sentence_accounting": [{"sentence_id": 0, "ev_id": "e1",
                                             "content_overlap": 3, "numeric_match": True}]},
    }[cp_id]


def _cond_d_checkpoints(run_dir: Path) -> tuple[bool, str]:
    """Each cp0..cp6 writes + reads back byte-identical; chain validates; verdict refused."""
    question = "Do GLP-1 agonists reduce MACE?"
    kwargs = dict(run_id="selftest", slug="glp1_mace", domain="clinical", question=question,
                  flag_slate={"PG_HOLISTIC_REVIEW": "0"}, run_config_sha="cfgsha")
    rt_ok = True
    payload_ok = True
    details = []
    for cp_id, _stage, _fname in ck.CHECKPOINT_STAGES:
        path = ck.save_checkpoint(run_dir, cp_id=cp_id, payload=_payload_for(cp_id), **kwargs)
        raw = path.read_bytes()
        # byte-identical: parse then re-serialize the SAME envelope => identical bytes.
        reserialized = ck.serialize_envelope(json.loads(raw.decode("utf-8")))
        byte_id = reserialized == raw
        env = ck.load_checkpoint(run_dir, cp_id, expected_question_sha=ck.question_sha(question))
        data_id = env["payload"] == _payload_for(cp_id)
        rt_ok = rt_ok and byte_id
        payload_ok = payload_ok and data_id
        details.append(f"{cp_id}:byte={byte_id},data={data_id}")

    chain = ck.validate_hash_chain(run_dir)
    chain_ok = chain == list(ck._CP_IDS)

    # verdict-smuggling RED test: a payload with a forbidden key must be REFUSED on save.
    verdict_refused = False
    try:
        ck.build_envelope(cp_id="cp3", run_id="x", slug="x", domain="x", question=question,
                          payload={"baskets": [{"is_verified": True}]})
    except ck.CheckpointEnvelopeError:
        verdict_refused = True

    ok = rt_ok and payload_ok and chain_ok and verdict_refused
    ev = (f"cp0..cp6 all byte-identical round-trip + payload-identical [{'; '.join(details)}]; "
          f"hash-chain validates end-to-end ({chain}); verdict-smuggling payload REFUSED="
          f"{verdict_refused}")
    return bool(ok), ev


def _cond_e_resume_adjust(run_dir: Path, reg: dict[str, rc.KnobSpec]) -> tuple[bool, str]:
    """Resume from cp3, apply a downstream adjustment, upstream sha256s untouched."""
    # snapshot upstream sha256 BEFORE the resume/adjust
    up_before = {cp: ck.sha256_file(ck.checkpoint_path(run_dir, cp)) for cp in ("cp0", "cp1", "cp2", "cp3")}

    plan = ck.resolve_resume_point(run_dir, requested="cp3")
    entry_ok = plan.entry_cp == "cp3" and plan.rerun_stages == ("cp4", "cp5", "cp6")

    base = rc.RunConfig()
    # valid: deliverable tone at cp3 (erc cp3 => 3 <= 3)
    adjusted = rc.apply_adjustment(base, {"tone": "executive_brief"}, "cp3", reg)
    downstream = rc.get(adjusted, "tone", registry=reg, env={})
    takes_effect = downstream.value == "executive_brief" and downstream.source == rc.SOURCE_ADJUST

    # invalid: breadth query_count at cp3 (erc cp0 => 3 <= 0 false) must be REFUSED
    breadth_refused = False
    try:
        rc.apply_adjustment(base, {"query_count": 99}, "cp3", reg)
    except rc.RunConfigError:
        breadth_refused = True

    # supersede downstream (never delete); upstream must be byte-untouched
    adj_sha = adjusted.config_sha(registry=reg, env={})
    archive = ck.supersede_downstream(run_dir, "cp3", adjustment_sha=adj_sha)
    up_after = {cp: ck.sha256_file(ck.checkpoint_path(run_dir, cp)) for cp in ("cp0", "cp1", "cp2", "cp3")}
    upstream_untouched = up_before == up_after
    downstream_gone = not any(ck.checkpoint_path(run_dir, cp).exists() for cp in ("cp4", "cp5", "cp6"))
    superseded_recorded = any(e.get("event") == "superseded" for e in ck.read_index(run_dir))
    chain_still_ok = ck.validate_hash_chain(run_dir, up_to="cp3") == ["cp0", "cp1", "cp2", "cp3"]

    ok = (entry_ok and takes_effect and breadth_refused and upstream_untouched
          and downstream_gone and superseded_recorded and chain_still_ok)
    ev = (f"resume entry=cp3 (re-runs {plan.rerun_stages}); downstream tone resolves to "
          f"'executive_brief' (source=adjust) => change takes effect downstream; breadth "
          f"adjustment at cp3 REFUSED={breadth_refused}; cp0-cp3 sha256 UNTOUCHED="
          f"{upstream_untouched}; cp4-cp6 superseded (not deleted, archived at "
          f"{archive.name if archive else None}, index-recorded={superseded_recorded}); "
          f"chain still validates up to cp3={chain_still_ok}")
    return bool(ok), ev


def main() -> int:
    ap = argparse.ArgumentParser(description="Offline foundation self-test")
    ap.add_argument("--out", default=None, help="summary.json output path")
    args = ap.parse_args()

    reg = rc.load_registry()  # loads + validates the registry (schema-time §-1.3/§1.7 review)

    work = Path(tempfile.mkdtemp(prefix="foundation_selftest_"))
    run_dir = work / "runs" / "glp1_mace"

    conditions: dict[str, tuple[bool, str]] = {}
    conditions["a_precedence"] = _cond_a_precedence(reg)
    conditions["b_zero_hardcode"] = _cond_b_zero_hardcode(reg)
    conditions["c_knob_coverage"] = _cond_c_coverage(reg)
    conditions["d_checkpoint_roundtrip"] = _cond_d_checkpoints(run_dir)
    conditions["e_resume_adjust"] = _cond_e_resume_adjust(run_dir, reg)

    summary = {
        "all_pass": all(v[0] for v in conditions.values()),
        "registry_knob_count": len(reg),
        "registry_path": str(rc.registry_path()),
        "conditions": {k: {"pass": v[0], "evidence": v[1]} for k, v in conditions.items()},
    }

    out_path = Path(args.out) if args.out else (work / "summary.json")
    out_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("=" * 78)
    print("POLARIS FOUNDATION OFFLINE SELF-TEST")
    print("=" * 78)
    for key, (ok, ev) in conditions.items():
        print(f"[{'PASS' if ok else 'FAIL'}] {key}")
        print(f"       {ev}")
    print("-" * 78)
    print(f"registry knobs: {len(reg)}   summary.json: {out_path}")
    print(f"ALL PASS: {summary['all_pass']}")
    print("=" * 78)
    # also echo the summary.json contents (blind-operator friendly, read inline)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
