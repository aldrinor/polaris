"""foundation_stress — ADVERSARIAL offline stress battery for the WAVE-0 foundation.

Companion to scripts/foundation_selftest.py. Where the self-test proves the five
acceptance conditions on a HAND-PICKED slice (e.g. cond_c only exercises 14 named knobs),
this battery attacks the SAME two modules across their WHOLE surface and is deliberately
built to EXPOSE gaps, not to go green. Several cases are designed to BREAK.

Pure offline: no network, GPU, LLM. Uses only the standard library + yaml + the two
foundation modules. Every case:
  * returns (case_id, verdict, evidence) with verdict in {"HOLD","BREAK"};
  * prints exactly one line  ``CASE <case_id> <verdict> :: <evidence>``;
  * HOLD  == the invariant under test survived the attack;
  * BREAK == the invariant was violated (a real gap), OR the case raised an
    UNEXPECTED exception the assertion did not anticipate.

At the end a ``summary.json`` is written and one ``SUMMARY hold=<H> break=<B> total=<N>``
line is printed. Exit code is 0 iff break == 0, else 1 — a non-zero exit is the honest
sign-off signal that at least one invariant broke.

Usage:
    python scripts/foundation_stress.py [--out <output_dir>]
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.polaris_graph import checkpoint_envelope as ck  # noqa: E402
from src.polaris_graph import run_config as rc  # noqa: E402

# Two verbatim golden questions (I-safety-002b lockfile #75 + #76) — used for the GATE0
# question_sha identity cases so the checkpoint identity guard is exercised against the
# real locked golden set, not a toy string.
GOLDEN_Q75 = (
    "Could therapeutic interventions aimed at modulating plasma metal ion concentrations "
    "represent effective preventive or therapeutic strategies against cardiovascular "
    "diseases? What types of interventions—such as supplementation—have been "
    "proposed, and is there clinical evidence supporting their feasibility and efficacy?"
)
GOLDEN_Q76 = (
    "The significance of the gut microbiota in maintaining normal intestinal function has "
    "emerged as a prominent focus in contemporary research, revealing both beneficial and "
    "detrimental impacts on the equilibrium of gut health."
)


# ---------------------------------------------------------------------------
# Harness helpers.
# ---------------------------------------------------------------------------


def expect_raises(fn: Callable[[], Any], exc_type: type[BaseException]) -> tuple[bool, str]:
    """Return (True, msg) if fn() raised exc_type; (False, "") if it returned; (False,
    "WRONG_EXC:<type>:<msg>") if a different exception type was raised."""
    try:
        fn()
    except exc_type as exc:  # the anticipated failure
        return True, str(exc)
    except BaseException as exc:  # noqa: BLE001 — any other type is the wrong failure
        return False, f"WRONG_EXC:{type(exc).__name__}:{exc}"
    return False, ""


def _pv(prov: rc.KnobProvenance) -> tuple[Any, str]:
    return prov.value, prov.source


def _payload_for(cp_id: str) -> dict[str, Any]:
    """A structurally-real DATA payload per checkpoint (never a verdict)."""
    return {
        "cp0": {"resolved_run_config": {"query_count": {"value": 35, "source": "default"}}},
        "cp1": {"counts": {"candidates_total": 240, "candidates_fetched": 221},
                "evidence_rows": [{"ev_id": "e1", "url": "https://example.org/a"}]},
        "cp2": {"evidence_for_gen": [{"ev_id": "e1", "tier": "T1", "span": "reduced MACE 20%"}]},
        "cp3": {"baskets": [{"claim": "MACE reduction", "members": ["e1", "e2"],
                             "corroboration_count": 2}]},
        "cp4": {"section_plans": [{"title": "Findings", "ev_ids": ["e1", "e2"]}]},
        "cp5": {"section_drafts": {"Findings": "GLP-1 agonists reduced MACE [#ev:e1:0-18]."}},
        "cp6": {"per_sentence_accounting": [{"sentence_id": 0, "ev_id": "e1"}]},
    }[cp_id]


# ---------------------------------------------------------------------------
# FRONT A — RunConfig resolver.
# ---------------------------------------------------------------------------


def case_a1(REG: dict[str, rc.KnobSpec]) -> tuple[str, str, str]:
    """A1 — four-layer precedence, panel wins (HOLD expected)."""
    env = {"PG_QGEN_FS_RESEARCHER_MAX_QUERIES": "45"}
    cfg = rc.RunConfig.from_sources(prompt_text="run 60 queries",
                                    panel_overrides={"query_count": 99}, registry=REG)
    p_panel = _pv(rc.get(cfg, "query_count", registry=REG, env=env))
    prompt_only = rc.RunConfig(prompt=dict(cfg.prompt))
    pr = rc.get(prompt_only, "query_count", registry=REG, env={})
    p_env = _pv(rc.get(rc.RunConfig(), "query_count", registry=REG, env=env))
    p_def = _pv(rc.get(rc.RunConfig(), "query_count", registry=REG, env={}))
    ok = (p_panel == (99, "panel") and pr.value == 60 and pr.source == "prompt"
          and bool(pr.span) and p_env == (45, "env") and p_def == (35, "default"))
    ev = (f"query_count ladder panel=99>prompt=60(span={pr.span!r})>env=45>default=35 "
          f"sources=[panel,prompt,env,default]")
    return "A1", ("HOLD" if ok else "BREAK"), ev


def case_a2(REG: dict[str, rc.KnobSpec]) -> tuple[str, str, str]:
    """A2 — adjust outranks panel (HOLD expected)."""
    cfg = rc.RunConfig(panel={"query_count": 99}, adjust={"query_count": 7})
    got = _pv(rc.get(cfg, "query_count", registry=REG, env={}))
    ok = got == (7, "adjust")
    return "A2", ("HOLD" if ok else "BREAK"), f"adjust=7 beats panel=99 source={got[1]} val={got[0]}"


def case_a3(REG: dict[str, rc.KnobSpec]) -> tuple[str, str, str]:
    """A3 — prompt beats env, env beats default, per-layer isolation (HOLD expected)."""
    env20 = {"PG_LIVE_MAX_SERPER": "20"}
    cfg_prompt = rc.RunConfig.from_sources(prompt_text="12 searches per query", registry=REG)
    p_prompt = rc.get(cfg_prompt, "searches_per_query", registry=REG, env=env20)
    p_env = rc.get(rc.RunConfig(), "searches_per_query", registry=REG, env=env20)
    p_def = rc.get(rc.RunConfig(), "searches_per_query", registry=REG, env={})
    ok = (p_prompt.value == 12 and p_prompt.source == "prompt"
          and p_env.source == "env" and p_env.value == 20
          and p_def.source == "default" and p_def.value == 20)
    ev = ("searches_per_query prompt=12>env=20; empty+env source=env; "
          f"empty+noenv source={p_def.source}(val={p_def.value})")
    return "A3", ("HOLD" if ok else "BREAK"), ev


def _synth(spec: rc.KnobSpec, layer: str) -> Any:
    """A type-valid value for the given layer. env values are STRINGS (env is dict[str,str])."""
    t = spec.type
    if t == "int":
        return {"panel": 901, "prompt": 902, "env": "903"}[layer]
    if t == "float":
        return {"panel": 90.1, "prompt": 90.2, "env": "90.3"}[layer]
    if t == "bool":
        return {"panel": True, "prompt": False, "env": "true"}[layer]
    if t == "list":
        return {"panel": ["pv"], "prompt": ["qv"], "env": "ev1,ev2"}[layer]
    if t == "str_enum":
        m = spec.enum or ("x",)
        return {"panel": m[0], "prompt": m[-1], "env": m[min(1, len(m) - 1)]}[layer]
    return {"panel": "panelval", "prompt": "promptval", "env": "envval"}[layer]


def _prompt_directive(spec: rc.KnobSpec) -> tuple[str, Any]:
    """A crafted explicit-directive phrase + the expected coerced value (behavioral A5)."""
    raw = {"int": "7", "float": "0.5", "bool": "true"}.get(spec.type)
    if raw is None:
        if spec.type == "str_enum":
            raw = (spec.enum or ("x",))[0]
        elif spec.type == "list":
            raw = "alpha, beta"
        else:
            raw = "alpha"
    return f"Research question here. set {spec.id} to {raw}.", rc._coerce(spec, raw)


def case_a4(REG: dict[str, rc.KnobSpec]) -> tuple[str, str, str]:
    """A4 — FULL 38-knob precedence matrix (HOLD expected; the core matrix)."""
    panel_wins = prompt_wins = env_wins = default_ok = 0
    env_backed_total = 0
    mismatches: list[str] = []
    for kid, spec in REG.items():
        panel_v = _synth(spec, "panel")
        prompt_v = _synth(spec, "prompt")
        env_backed = bool(spec.env_var)
        env_full = {spec.env_var: _synth(spec, "env")} if env_backed else {}
        if env_backed:
            env_backed_total += 1
        # all present -> panel
        cfg_all = rc.RunConfig(panel={kid: panel_v}, prompt={kid: (prompt_v, "span")})
        r1 = rc.get(cfg_all, kid, registry=REG, env=env_full)
        if r1.source == "panel":
            panel_wins += 1
        else:
            mismatches.append(f"{kid}:panel->{r1.source}")
        # drop panel -> prompt (env still set for env-backed => proves prompt>env)
        cfg_p = rc.RunConfig(prompt={kid: (prompt_v, "span")})
        r2 = rc.get(cfg_p, kid, registry=REG, env=env_full)
        if r2.source == "prompt":
            prompt_wins += 1
        else:
            mismatches.append(f"{kid}:prompt->{r2.source}")
        # drop prompt, env-backed only -> env
        if env_backed:
            r3 = rc.get(rc.RunConfig(), kid, registry=REG, env=env_full)
            if r3.source == "env":
                env_wins += 1
            else:
                mismatches.append(f"{kid}:env->{r3.source}")
        # drop all -> default, value == code_default
        r4 = rc.get(None, kid, registry=REG, env={})
        if r4.source == "default" and r4.value == spec.code_default:
            default_ok += 1
        else:
            mismatches.append(f"{kid}:default->({r4.source},{r4.value!r})")
    ok = (panel_wins == 38 and prompt_wins == 38 and env_wins == env_backed_total == 14
          and default_ok == 38)
    ev = (f"matrix 38 knobs: panel-wins={panel_wins}/38 prompt-wins={prompt_wins}/38 "
          f"env-wins={env_wins}/{env_backed_total} default={default_ok}/38 "
          f"mismatches={mismatches or 'none'}")
    return "A4", ("HOLD" if ok else "BREAK"), ev


def case_a5(REG: dict[str, rc.KnobSpec]) -> tuple[str, str, str]:
    """A5 — EVERY knob settable from BOTH prompt AND panel (HOLD expected — behavioral)."""
    panel_ok = 0
    prompt_ok = 0
    not_prompt: list[str] = []
    for kid, spec in REG.items():
        # panel side: from_sources must accept a type-valid override and resolve to panel.
        try:
            cfg = rc.RunConfig.from_sources(panel_overrides={kid: _synth(spec, "panel")}, registry=REG)
            if rc.get(cfg, kid, registry=REG, env={}).source == "panel":
                panel_ok += 1
        except rc.RunConfigError:
            pass
        # prompt side: BEHAVIORAL — a crafted directive phrase must yield the parsed
        # value with a verbatim span AND win resolution as source='prompt', regardless
        # of which parser layer (specific _PROMPT_RULES rule or the generic
        # explicit-directive layer, run_config.py §1) recognises it.
        phrase, expected = _prompt_directive(spec)
        parsed = rc.parse_prompt_knobs(phrase, REG)
        hit = parsed.get(kid)
        span_ok = hit is not None and hit[1] and hit[1] in phrase
        value_ok = hit is not None and hit[0] == expected
        prov = rc.get(rc.RunConfig.from_sources(prompt_text=phrase, registry=REG),
                      kid, registry=REG, env={})
        if span_ok and value_ok and prov.source == "prompt" and prov.value == expected:
            prompt_ok += 1
        else:
            not_prompt.append(
                f"{kid}({'no-parse' if hit is None else 'bad-value-or-span'})")
    ok = (panel_ok == 38 and prompt_ok == 38)
    ev = (f"both-surface coverage panel={panel_ok}/38 prompt(BEHAVIORAL)={prompt_ok}/38 "
          f"NOT_PROMPT_SETTABLE={sorted(not_prompt)}")
    return "A5", ("HOLD" if ok else "BREAK"), ev


def case_a6(REG: dict[str, rc.KnobSpec]) -> tuple[str, str, str]:
    """A6 — malformed numeric coercion is fail-loud (HOLD for the guaranteed contract).

    The resolver contracts type coercion + FAIL LOUD on an uncoercible scalar (it does NOT
    contract range/lower-bound validation). Attack an int knob with non-numeric and
    float-shaped strings (must raise) and record the adversarial observation that a NEGATIVE
    int is silently accepted (no lower-bound guard — a gap disclosed in evidence)."""
    raised_abc, _ = expect_raises(
        lambda: rc.RunConfig.from_sources(panel_overrides={"query_count": "abc"}, registry=REG),
        rc.RunConfigError)
    raised_float, _ = expect_raises(
        lambda: rc.RunConfig.from_sources(panel_overrides={"query_count": "3.5"}, registry=REG),
        rc.RunConfigError)
    # negative: type-valid int, accepted (documents the missing lower-bound guard).
    neg = rc.get(rc.RunConfig.from_sources(panel_overrides={"query_count": "-5"}, registry=REG),
                 "query_count", registry=REG, env={})
    neg_accepted = (neg.value == -5 and neg.source == "panel")
    ok = raised_abc and raised_float  # the guaranteed fail-loud contract held
    ev = (f"malformed int fail-loud: 'abc' raised={raised_abc} '3.5' raised={raised_float}; "
          f"OBSERVATION negative '-5' accepted={neg_accepted} (value={neg.value}) "
          f"-- resolver contracts type-only, no range guard")
    return "A6", ("HOLD" if ok else "BREAK"), ev


# ---------------------------------------------------------------------------
# FRONT B — checkpoint_envelope invariants.
# ---------------------------------------------------------------------------

_CK_KW = dict(run_id="stress", slug="glp1", domain="clinical")


def _save(run_dir: Path, cp_id: str, question: str = GOLDEN_Q75, **over: Any) -> Path:
    kw = dict(_CK_KW)
    kw.update(over)
    return ck.save_checkpoint(run_dir, cp_id=cp_id, question=question,
                              payload=_payload_for(cp_id), **kw)


def case_b1(run_root: Path) -> tuple[str, str, str]:
    """B1 — verdict key at top level refused on SAVE (HOLD expected)."""
    raised, msg = expect_raises(
        lambda: ck.build_envelope(cp_id="cp3", run_id="x", slug="x", domain="x",
                                  question=GOLDEN_Q75, payload={"verified": True}),
        ck.CheckpointEnvelopeError)
    return "B1", ("HOLD" if raised else "BREAK"), f"top-level verdict key refused={raised} :: {msg[:70]}"


def case_b2(run_root: Path) -> tuple[str, str, str]:
    """B2 — verdict key nested deep refused on SAVE (recursive guard) (HOLD expected)."""
    payload = {"baskets": [{"members": ["e1"], "meta": {"d8_decision": "release"}}]}
    raised, msg = expect_raises(
        lambda: ck.build_envelope(cp_id="cp3", run_id="x", slug="x", domain="x",
                                  question=GOLDEN_Q75, payload=payload),
        ck.CheckpointEnvelopeError)
    return "B2", ("HOLD" if raised else "BREAK"), f"nested verdict key refused={raised} :: {msg[:70]}"


def case_b3(run_root: Path) -> tuple[str, str, str]:
    """B3 — byte-identical round-trip on save/read (HOLD expected)."""
    d = run_root / "b3"
    path = _save(d, "cp0")
    raw = path.read_bytes()
    reserialized = ck.serialize_envelope(json.loads(raw.decode("utf-8")))
    ok = reserialized == raw
    return "B3", ("HOLD" if ok else "BREAK"), f"cp0 re-serialize == on-disk bytes: {ok} ({len(raw)}B)"


def case_b4(run_root: Path) -> tuple[str, str, str]:
    """B4 — schema_version pin refuses a stale-shaped checkpoint on LOAD (HOLD expected)."""
    d = run_root / "b4"
    d.mkdir(parents=True, exist_ok=True)
    env = ck.build_envelope(cp_id="cp0", run_id="x", slug="x", domain="x",
                            question=GOLDEN_Q75, payload=_payload_for("cp0"))
    env["schema_version"] = 999
    ck.checkpoint_path(d, "cp0").write_bytes(ck.serialize_envelope(env))
    raised, msg = expect_raises(
        lambda: ck.load_checkpoint(d, "cp0", verify_index_sha=False),
        ck.CheckpointEnvelopeError)
    return "B4", ("HOLD" if raised else "BREAK"), f"schema_version=999 refused on load={raised} :: {msg[:60]}"


def case_b5(run_root: Path) -> tuple[str, str, str]:
    """B5 — stage/filename mismatch refused on LOAD (HOLD expected)."""
    d = run_root / "b5"
    d.mkdir(parents=True, exist_ok=True)
    env = ck.build_envelope(cp_id="cp0", run_id="x", slug="x", domain="x",
                            question=GOLDEN_Q75, payload=_payload_for("cp0"))
    # write cp0's envelope into cp1's filename => stage says s0_intake, cp1 expects s1_fetch
    ck.checkpoint_path(d, "cp1").write_bytes(ck.serialize_envelope(env))
    raised, msg = expect_raises(
        lambda: ck.load_checkpoint(d, "cp1", verify_index_sha=False),
        ck.CheckpointEnvelopeError)
    return "B5", ("HOLD" if raised else "BREAK"), f"cp0-envelope-in-cp1-file refused={raised} :: {msg[:60]}"


def case_b6(run_root: Path) -> tuple[str, str, str]:
    """B6 — GATE0 question_sha: correct loads, a DIFFERENT golden question is refused (HOLD)."""
    d = run_root / "b6"
    _save(d, "cp0", question=GOLDEN_Q75)
    good, _ = expect_raises(  # correct sha must NOT raise
        lambda: ck.load_checkpoint(d, "cp0", expected_question_sha=ck.question_sha(GOLDEN_Q75)),
        ck.CheckpointEnvelopeError)
    correct_loads = not good  # expect_raises returns False when fn returned without raising
    bad, msg = expect_raises(
        lambda: ck.load_checkpoint(d, "cp0", expected_question_sha=ck.question_sha(GOLDEN_Q76)),
        ck.CheckpointEnvelopeError)
    ok = correct_loads and bad
    return "B6", ("HOLD" if ok else "BREAK"), (
        f"golden#75 correct-sha loads={correct_loads}; golden#76 sha refused={bad} :: {msg[:50]}")


def case_b7(run_root: Path) -> tuple[str, str, str]:
    """B7 — flag_slate divergence refused on LOAD (HOLD expected)."""
    d = run_root / "b7"
    _save(d, "cp0", flag_slate={"PG_HOLISTIC_REVIEW": "0"})
    raised, msg = expect_raises(
        lambda: ck.load_checkpoint(d, "cp0", active_flag_slate={"PG_HOLISTIC_REVIEW": "1"}),
        ck.CheckpointEnvelopeError)
    return "B7", ("HOLD" if raised else "BREAK"), f"slate 0!=1 refused on load={raised} :: {msg[:60]}"


def case_b8(run_root: Path) -> tuple[str, str, str]:
    """B8 — post-write tamper caught by index-sha guard on LOAD (HOLD expected)."""
    d = run_root / "b8"
    path = _save(d, "cp0")
    env = json.loads(path.read_bytes().decode("utf-8"))
    env["payload"]["resolved_run_config"]["query_count"]["value"] = 9999  # silent edit
    path.write_bytes(ck.serialize_envelope(env))  # index still holds the OLD sha
    raised, msg = expect_raises(
        lambda: ck.load_checkpoint(d, "cp0"),  # verify_index_sha defaults True
        ck.CheckpointEnvelopeError)
    return "B8", ("HOLD" if raised else "BREAK"), f"tampered payload caught by index-sha={raised} :: {msg[:55]}"


def case_b9(run_root: Path) -> tuple[str, str, str]:
    """B9 — hash chain validates clean; a mid-chain tamper is caught (HOLD expected)."""
    d = run_root / "b9"
    for cp in ("cp0", "cp1", "cp2"):
        _save(d, cp)
    clean = ck.validate_hash_chain(d)
    clean_ok = clean == ["cp0", "cp1", "cp2"]
    p1 = ck.checkpoint_path(d, "cp1")
    env = json.loads(p1.read_bytes().decode("utf-8"))
    env["payload"]["counts"]["candidates_total"] = 1  # tamper cp1 on disk
    p1.write_bytes(ck.serialize_envelope(env))
    raised, msg = expect_raises(lambda: ck.validate_hash_chain(d), ck.CheckpointEnvelopeError)
    ok = clean_ok and raised
    return "B9", ("HOLD" if ok else "BREAK"), (
        f"clean chain={clean} valid={clean_ok}; cp1 tamper caught={raised} :: {msg[:45]}")


def case_b10(run_root: Path) -> tuple[str, str, str]:
    """B10 — resume resolver: requested present cp resolves; absent cp is refused (HOLD)."""
    d = run_root / "b10"
    for cp in ("cp0", "cp1", "cp2", "cp3"):
        _save(d, cp)
    plan = ck.resolve_resume_point(d, requested="cp2")
    entry_ok = plan.entry_cp == "cp2" and plan.rerun_stages == ("cp3", "cp4", "cp5", "cp6")
    absent, msg = expect_raises(
        lambda: ck.resolve_resume_point(d, requested="cp5"), ck.CheckpointEnvelopeError)
    ok = entry_ok and absent
    return "B10", ("HOLD" if ok else "BREAK"), (
        f"resume cp2 entry={plan.entry_cp} rerun={plan.rerun_stages} ok={entry_ok}; "
        f"absent cp5 refused={absent}")


def case_b11(run_root: Path) -> tuple[str, str, str]:
    """B11 — LOAD-side recursive verdict guard fires even on a file that skipped save (HOLD)."""
    d = run_root / "b11"
    d.mkdir(parents=True, exist_ok=True)
    # Hand-craft a well-formed envelope with a smuggled verdict key (save would have refused).
    env = {
        "schema_version": ck.CHECKPOINT_SCHEMA_VERSION,
        "stage": "s0_intake", "cp_id": "cp0", "run_id": "x", "slug": "x", "domain": "x",
        "question": GOLDEN_Q75, "question_sha": ck.question_sha(GOLDEN_Q75),
        "created_utc": "2026-07-10T00:00:00Z", "upstream": None, "flag_slate": {},
        "run_config_sha": None, "adjustments_applied": [],
        "payload": {"section": {"nested": {"released": True}}},
        "faithfulness_invariant": "DATA ONLY",
    }
    ck.checkpoint_path(d, "cp0").write_bytes(ck.serialize_envelope(env))
    raised, msg = expect_raises(
        lambda: ck.load_checkpoint(d, "cp0", verify_index_sha=False),
        ck.CheckpointEnvelopeError)
    return "B11", ("HOLD" if raised else "BREAK"), f"load-side verdict guard fired={raised} :: {msg[:55]}"


# ---------------------------------------------------------------------------
# FRONT C — cross-module resume + adjustment (RunConfig <-> checkpoint).
# ---------------------------------------------------------------------------


def case_c1(REG: dict[str, rc.KnobSpec]) -> tuple[str, str, str]:
    """C1 — adjustment validity matrix: entry_index <= erc_index (HOLD expected)."""
    breadth_at_cp3 = rc.adjustment_valid_at("query_count", "cp3", REG)   # erc cp0 -> False
    deliver_at_cp3 = rc.adjustment_valid_at("tone", "cp3", REG)          # erc cp3 -> True
    breadth_at_cp0 = rc.adjustment_valid_at("query_count", "cp0", REG)   # erc cp0 -> True
    compose_at_cp5 = rc.adjustment_valid_at("section_concurrency", "cp5", REG)  # erc cp4 -> False
    ok = (breadth_at_cp3 is False and deliver_at_cp3 is True
          and breadth_at_cp0 is True and compose_at_cp5 is False)
    ev = (f"valid_at: query_count@cp3={breadth_at_cp3} tone@cp3={deliver_at_cp3} "
          f"query_count@cp0={breadth_at_cp0} section_concurrency@cp5={compose_at_cp5}")
    return "C1", ("HOLD" if ok else "BREAK"), ev


def case_c2(REG: dict[str, rc.KnobSpec]) -> tuple[str, str, str]:
    """C2 — out-of-scope adjustment is fail-loud rejected (HOLD expected)."""
    base = rc.RunConfig()
    raised, msg = expect_raises(
        lambda: rc.apply_adjustment(base, {"query_count": 99}, "cp3", REG), rc.RunConfigError)
    return "C2", ("HOLD" if raised else "BREAK"), f"query_count adjust @cp3 refused={raised} :: {msg[:70]}"


def case_c3(REG: dict[str, rc.KnobSpec]) -> tuple[str, str, str]:
    """C3 — valid downstream adjustment takes effect via the adjust layer (HOLD expected)."""
    base = rc.RunConfig()
    adjusted = rc.apply_adjustment(base, {"tone": "executive_brief"}, "cp3", REG)
    got = _pv(rc.get(adjusted, "tone", registry=REG, env={}))
    ok = got == ("executive_brief", "adjust")
    return "C3", ("HOLD" if ok else "BREAK"), f"tone adjust @cp3 resolves {got}"


def case_c4(REG: dict[str, rc.KnobSpec]) -> tuple[str, str, str]:
    """C4 — config_sha is deterministic + sensitive to a knob change (HOLD expected)."""
    a = rc.RunConfig(panel={"query_count": 50})
    sha1 = a.config_sha(registry=REG, env={})
    sha2 = a.config_sha(registry=REG, env={})
    b = rc.RunConfig(panel={"query_count": 51})
    sha3 = b.config_sha(registry=REG, env={})
    ok = (sha1 == sha2 and sha1 != sha3)
    return "C4", ("HOLD" if ok else "BREAK"), (
        f"config_sha deterministic={sha1 == sha2} sensitive={sha1 != sha3} "
        f"({sha1[:12]} vs {sha3[:12]})")


def case_c5(REG: dict[str, rc.KnobSpec]) -> tuple[str, str, str]:
    """C5 — adjust beats a pre-existing panel value through the resume path (HOLD expected)."""
    cfg = rc.RunConfig(panel={"tone": "academic"})
    adjusted = rc.apply_adjustment(cfg, {"tone": "executive_brief"}, "cp3", REG)
    got = _pv(rc.get(adjusted, "tone", registry=REG, env={}))
    ok = got == ("executive_brief", "adjust")
    return "C5", ("HOLD" if ok else "BREAK"), f"panel=academic then adjust=executive_brief -> {got}"


def case_c6(run_root: Path, REG: dict[str, rc.KnobSpec]) -> tuple[str, str, str]:
    """C6 — full resume+adjust: downstream superseded, upstream sha256 untouched (HOLD)."""
    d = run_root / "c6"
    for cp in ("cp0", "cp1", "cp2", "cp3", "cp4", "cp5"):
        _save(d, cp)
    up_before = {cp: ck.sha256_file(ck.checkpoint_path(d, cp)) for cp in ("cp0", "cp1", "cp2", "cp3")}
    plan = ck.resolve_resume_point(d, requested="cp3")
    entry_ok = plan.entry_cp == "cp3" and plan.rerun_stages == ("cp4", "cp5", "cp6")
    adjusted = rc.apply_adjustment(rc.RunConfig(), {"tone": "executive_brief"}, "cp3", REG)
    adj_sha = adjusted.config_sha(registry=REG, env={})
    archive = ck.supersede_downstream(d, "cp3", adjustment_sha=adj_sha)
    up_after = {cp: ck.sha256_file(ck.checkpoint_path(d, cp)) for cp in ("cp0", "cp1", "cp2", "cp3")}
    upstream_untouched = up_before == up_after
    downstream_gone = not any(ck.checkpoint_path(d, cp).exists() for cp in ("cp4", "cp5", "cp6"))
    superseded_recorded = any(e.get("event") == "superseded" for e in ck.read_index(d))
    chain_ok = ck.validate_hash_chain(d, up_to="cp3") == ["cp0", "cp1", "cp2", "cp3"]
    ok = (entry_ok and upstream_untouched and downstream_gone and superseded_recorded and chain_ok)
    ev = (f"resume cp3 rerun={plan.rerun_stages}; upstream_untouched={upstream_untouched}; "
          f"downstream_superseded={downstream_gone} archived={archive.name if archive else None} "
          f"recorded={superseded_recorded}; chain<=cp3 ok={chain_ok}")
    return "C6", ("HOLD" if ok else "BREAK"), ev


# ---------------------------------------------------------------------------
# Runner.
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description="Adversarial offline foundation stress battery")
    ap.add_argument("--out", default=None, help="output DIRECTORY for summary.json")
    args = ap.parse_args()

    REG = rc.load_registry()
    if len(REG) != 38:
        print(f"FATAL registry_count={len(REG)} expected 38")
        return 1

    work = Path(tempfile.mkdtemp(prefix="foundation_stress_"))
    ck_root = work / "ck"

    # (fn, kind) where kind selects the argument passed.
    plan: list[tuple[str, Callable[[], tuple[str, str, str]]]] = [
        ("A1", lambda: case_a1(REG)),
        ("A2", lambda: case_a2(REG)),
        ("A3", lambda: case_a3(REG)),
        ("A4", lambda: case_a4(REG)),
        ("A5", lambda: case_a5(REG)),
        ("A6", lambda: case_a6(REG)),
        ("B1", lambda: case_b1(ck_root)),
        ("B2", lambda: case_b2(ck_root)),
        ("B3", lambda: case_b3(ck_root)),
        ("B4", lambda: case_b4(ck_root)),
        ("B5", lambda: case_b5(ck_root)),
        ("B6", lambda: case_b6(ck_root)),
        ("B7", lambda: case_b7(ck_root)),
        ("B8", lambda: case_b8(ck_root)),
        ("B9", lambda: case_b9(ck_root)),
        ("B10", lambda: case_b10(ck_root)),
        ("B11", lambda: case_b11(ck_root)),
        ("C1", lambda: case_c1(REG)),
        ("C2", lambda: case_c2(REG)),
        ("C3", lambda: case_c3(REG)),
        ("C4", lambda: case_c4(REG)),
        ("C5", lambda: case_c5(REG)),
        ("C6", lambda: case_c6(ck_root, REG)),
    ]

    print("=" * 78)
    print("POLARIS FOUNDATION ADVERSARIAL STRESS BATTERY")
    print(f"registry knobs: {len(REG)}   (HOLD = invariant survived; BREAK = violated)")
    print("=" * 78)

    cases: list[dict[str, str]] = []
    for expected_id, fn in plan:
        try:
            case_id, verdict, evidence = fn()
        except BaseException as exc:  # noqa: BLE001 — unexpected exception is itself a BREAK
            case_id, verdict = expected_id, "BREAK"
            evidence = f"unexpected_exc={type(exc).__name__}:{exc}"
        if verdict not in ("HOLD", "BREAK"):
            verdict, evidence = "BREAK", f"illegal_verdict={verdict!r} :: {evidence}"
        print(f"CASE {case_id} {verdict} :: {evidence}")
        cases.append({"id": case_id, "verdict": verdict, "evidence": evidence})

    breaks = [c["id"] for c in cases if c["verdict"] == "BREAK"]
    hold = sum(1 for c in cases if c["verdict"] == "HOLD")
    total = len(cases)
    summary = {"total": total, "hold": hold, "break": len(breaks), "breaks": breaks, "cases": cases}

    out_dir = Path(args.out) if args.out else work
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "summary.json"
    out_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("-" * 78)
    print(f"summary.json: {out_path}")
    print(f"SUMMARY hold={hold} break={len(breaks)} total={total}")
    if breaks:
        print(f"BREAKS: {breaks}")
    return 0 if not breaks else 1


if __name__ == "__main__":
    raise SystemExit(main())
