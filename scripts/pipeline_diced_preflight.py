#!/usr/bin/env python3
"""DICED preflight harness (I-deepfix-001 #1344): run every pipeline DICE in ISOLATION
against a banked drb_72 corpus_snapshot fixture and assert its §-1.3 / §-1.4 invariant
FAIL-LOUD, then print a per-stage GREEN/RED table and a final GO / NO-GO.

WHY THIS EXISTS
---------------
A preflight that GREENs on a known-bad fixture is useless (§-1.4 false-green guard). This
harness is built and CALIBRATED so that, on the CURRENT (pre-breadth-fix) banked drb_72
artifacts, it goes RED exactly on the stages the recent eruptions hit:

  * BREADTH under-surface  -> D2_composition_breadth  (cited-distinct / generator-pool < floor)
                              D3_relevance_gate_fetch_budget (the upstream front-half reduction:
                              the B4 relevance gate + fetch budget -- RED on the OLD banked manifest
                              that predates the A5c relevance_gate demote-not-drop disclosure)
  * REPETITION (forced floor padding) -> D2_composition_repetition (n-gram repeat-rate ceiling)
  * FALSE-CONTRADICTION     -> D3_contradiction_only_comparable (headline count vs comparable)

...while the HONEST stages stay GREEN (selection dropped==0, consolidation baskets form,
strict_verify is the only drop, render is clean by the INDEPENDENT detector, the pipeline-
verdict gates do not thin sources). A blanket-RED harness would be just as useless as a
blanket-GREEN one.

I-deepfix-001 #1344 adds 5 LATENT GUARD-GAP dice the stage map surfaced (each GREEN where the
stage was healthy on the banked fixture, RED where the gap is real):
  * D4_relevance_weight_not_drop   -- relevance WEIGHTS not DROPS (structural keep-all; weight
                                      floor LIVE)           [GREEN on banked: dropped_count==0]
  * D5_credibility_honest_tiering  -- credibility is honest WEIGHT-tiering, every source
                                      classified              [GREEN on banked: 149==149, weaker
                                      tiering_mode invariant deferred to LIVE]
  * D6_topic_gate_env_guard        -- the §-1.3-banned scope hard-filter escape hatch is unset
                                                              [GREEN on banked: env unset]
  * D1_consolidation_qualitative_basket -- consolidation forms a QUALITATIVE (non-numeric) basket
                                      [KNOWN-RED-BY-DESIGN on the current numeric-only fact_dedup;
                                      exposes the blind spot the behavioral fix closes post-commit
                                      -- it is NOT weakened to pass, so the gate stays NO-GO until
                                      a real qualitative basket forms]
  * FX06_population_coupling        -- adequacy(D7) population == approval(D8) distribution total
                                                              [GREEN on banked: 149==149==149]
And it RE-ATTRIBUTES D3 (see ``dice_d3_relevance_gate_fetch_budget``): the 760-source pre-fetch
reduction is the B4 RELEVANCE GATE + fetch BUDGET, not the (OFF) prefetch off-topic filter.

ARCHITECTURE (§-1.3 WEIGHT-not-FILTER / CONSOLIDATE-not-DROP / BASKET-FAITHFULNESS)
----------------------------------------------------------------------------------
The ONLY sanctioned DROP in the whole pipeline is ``strict_verify``. Every other stage is a
WEIGHT (relevance / credibility / topic / selection-reorder) or a CONSOLIDATION (finding/fact
dedup -> corroboration baskets) or a pipeline-VERDICT gate (scope / adequacy / approval, which
abort the WHOLE question, never thin sources). Each DICE below asserts the slice of that law it
owns, in isolation, on the fixture.

OFFLINE-DETERMINISTIC dice are real assertions over the banked JSON checkpoints + report.md
(``load the stage's JSON checkpoint``) or over the actual stage function on a controlled fixture
(D6 calls the real ``report_redactor.reconcile_report_against_verdicts``; D7 shells out to the
INDEPENDENT clean-room render detector ``scripts/iwire013_sec11_forensic_audit.py`` -- NOT the
BLIND production chrome predicate, per I-wire-013).

LIVE-ONLY dice (4-role judge 429-storm / seam tear; GPU OOM) cannot be validated by a banked
replay (the I-wire-013/014 false-PASS lesson: a banked replay structurally cannot validate a
live-transport completion fix or a fetch-side truncation fix). Those emit a clearly-labelled
``LIVE-SMOKE-REQUIRED`` line with the exact tiny command to run that dice live. This harness
NEVER makes a paid call.

LAW VI: every threshold + path is an env var / CLI arg (``PG_DICED_*``). No magic numbers.
LAW II / §8.4: no network, no model load, no heavy import in the default offline path. The only
src import is the stdlib-only ``report_redactor`` module, loaded by file path so the heavy
``src/polaris_graph`` package __init__ never runs.

Usage
-----
    python scripts/pipeline_diced_preflight.py                 # default drb_72 fixture
    python scripts/pipeline_diced_preflight.py --fixture DIR   # repeatable; search order
    python scripts/pipeline_diced_preflight.py --json out.json # machine-readable sidecar

Exit code: 0 == GO (no offline dice RED), 1 == NO-GO (>=1 offline dice RED), 2 == harness error.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import traceback
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

# --------------------------------------------------------------------------------------------
# Paths / constants
# --------------------------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRATCH = _REPO_ROOT / "scratchpad"

# Default drb_72 fixture = the two real banked dirs (search order: forensic2 first so report.md
# + manifest.json + contradictions.json + four_role_*.json come from the SAME run; run1_audit
# supplies evidence_pool.json + the richer disclosure checkpoints).
_DEFAULT_FIXTURE_DIRS = [
    _SCRATCH / "deepfix_replay_forensic2",
    _SCRATCH / "deepfix_run1_audit",
]

_INDEPENDENT_RENDER_DETECTOR = _REPO_ROOT / "scripts" / "iwire013_sec11_forensic_audit.py"
_REPORT_REDACTOR_PATH = _REPO_ROOT / "src" / "polaris_graph" / "roles" / "report_redactor.py"

GREEN = "GREEN"
RED = "RED"
LIVE = "LIVE-SMOKE-REQUIRED"


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _env_str(name: str, default: str) -> str:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip()


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return list(default)
    return [p.strip() for p in raw.split(",") if p.strip()]


# --------------------------------------------------------------------------------------------
# Env-tunable thresholds (LAW VI) -- defaults calibrated against the banked drb_72 fixture so the
# eruption stages go RED and the honest stages stay GREEN.
# --------------------------------------------------------------------------------------------

@dataclass
class Thresholds:
    breadth_floor: float = field(default_factory=lambda: _env_float("PG_DICED_BREADTH_FLOOR", 0.30))
    repetition_ceiling: float = field(default_factory=lambda: _env_float("PG_DICED_REPETITION_CEILING", 0.05))
    repetition_ngram: int = field(default_factory=lambda: _env_int("PG_DICED_REPETITION_NGRAM", 8))
    repetition_max_phrase_count: int = field(default_factory=lambda: _env_int("PG_DICED_REPETITION_MAX_PHRASE_COUNT", 8))
    prefetch_max_drop: int = field(default_factory=lambda: _env_int("PG_DICED_PREFETCH_MAX_DROP", 0))
    min_corroborated_baskets: int = field(default_factory=lambda: _env_int("PG_DICED_MIN_CORROBORATED_BASKETS", 1))
    backbone_min_present: float = field(default_factory=lambda: _env_float("PG_DICED_BACKBONE_MIN_PRESENT", 0.90))
    chrome_max: int = field(default_factory=lambda: _env_int("PG_DICED_CHROME_MAX", 0))
    truncation_max: int = field(default_factory=lambda: _env_int("PG_DICED_TRUNCATION_MAX", 0))
    contradiction_noise_max: int = field(default_factory=lambda: _env_int("PG_DICED_CONTRADICTION_NOISE_MAX", 0))
    # I-deepfix-001 #1344 -- thresholds for the re-labelled D3 + the 5 latent guard-gap dice.
    min_demoted_fetched_to_fill: int = field(
        default_factory=lambda: _env_int("PG_DICED_MIN_DEMOTED_FETCHED_TO_FILL", 1))
    min_qualitative_baskets: int = field(
        default_factory=lambda: _env_int("PG_DICED_MIN_QUALITATIVE_BASKETS", 1))
    degraded_tiering_mode: str = field(
        default_factory=lambda: _env_str("PG_DICED_DEGRADED_TIERING_MODE", "rules_floor_degraded"))
    fetch_budget_caps: list[str] = field(
        default_factory=lambda: _env_list("PG_DICED_FETCH_BUDGET_CAPS", ["PG_LIVE_FETCH_CAP"]))
    topic_gate_hard_drop_env: str = field(
        default_factory=lambda: _env_str("PG_DICED_TOPIC_GATE_HARD_DROP_ENV", "PG_SCOPE_TOPIC_GATE_HARD_DROP"))


# --------------------------------------------------------------------------------------------
# Fixture resolver -- search the roots in order; fail loud on a required-but-absent artifact.
# --------------------------------------------------------------------------------------------

class FixtureResolver:
    def __init__(self, roots: list[Path]):
        self.roots = [Path(r) for r in roots]
        live = [r for r in self.roots if r.is_dir()]
        if not live:
            raise FileNotFoundError(
                "no fixture directory exists among: " + ", ".join(str(r) for r in self.roots)
            )
        self.roots = live

    def find(self, name: str) -> Optional[Path]:
        # honor a per-artifact override env var, e.g. PG_DICED_REPORT for report.md
        ov = os.environ.get("PG_DICED_" + name.replace(".", "_").replace("-", "_").upper())
        if ov:
            p = Path(ov)
            return p if p.exists() else None
        for r in self.roots:
            p = r / name
            if p.exists():
                return p
        return None

    def require(self, name: str) -> Path:
        p = self.find(name)
        if p is None:
            raise FileNotFoundError(
                f"required fixture artifact '{name}' not found in any root: "
                + ", ".join(str(r) for r in self.roots)
            )
        return p

    def load_json(self, name: str) -> object:
        return json.loads(self.require(name).read_text(encoding="utf-8"))

    def read_text(self, name: str) -> str:
        return self.require(name).read_text(encoding="utf-8")


# --------------------------------------------------------------------------------------------
# Dice result + context
# --------------------------------------------------------------------------------------------

@dataclass
class DiceResult:
    name: str
    lane: str
    mode: str                # OFFLINE | LIVE
    status: str              # GREEN | RED | LIVE-SMOKE-REQUIRED
    invariant: str
    detail: str
    live_command: str = ""
    by_design: bool = False  # True => a KNOWN-RED exposing dice (the gap is not yet fixed); the
    # RED is intentional and keeps the gate at NO-GO until the behavioral fix lands, NOT a
    # regression. Surfaced in the table + sidecar so the persistent NO-GO cause is legible.


@dataclass
class Ctx:
    fx: FixtureResolver
    th: Thresholds


# --------------------------------------------------------------------------------------------
# Shared measurement helpers (deterministic, pure)
# --------------------------------------------------------------------------------------------

def _normalize_prose(text: str) -> str:
    text = re.sub(r"\[#ev:[^\]]+\]", " ", text)   # strip provenance tokens
    text = re.sub(r"\[\d+\]", " ", text)          # strip [N] citation markers
    text = re.sub(r"[^a-z0-9 ]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def _ngram_repetition(text: str, n: int) -> tuple[float, int, str]:
    """Return (repeat_rate, max_phrase_count, top_phrase). repeat_rate = 1 - distinct/total."""
    words = _normalize_prose(text).split()
    if len(words) <= n:
        return 0.0, 0, ""
    grams = [" ".join(words[i:i + n]) for i in range(len(words) - n + 1)]
    counts = Counter(grams)
    total = len(grams)
    distinct = len(counts)
    repeat_rate = 1.0 - (distinct / total) if total else 0.0
    top_phrase, top_count = counts.most_common(1)[0]
    return repeat_rate, top_count, top_phrase


def _distinct_citation_keys(report_text: str) -> int:
    return len(set(re.findall(r"\[(\d+)\]", report_text)))


def _generator_pool_size(manifest: dict) -> int:
    sel = manifest.get("evidence_selection", {}) or {}
    for key in ("evidence_selected", "evidence_total"):
        v = sel.get(key)
        if isinstance(v, int) and v > 0:
            return v
    # fall back to the corpus count if selection counts are absent
    return int((manifest.get("corpus", {}) or {}).get("count", 0))


# --------------------------------------------------------------------------------------------
# OFFLINE DICE -- each is independent, named, and asserts ONE invariant on the fixture.
# Returns DiceResult. Any exception => RED (fail-loud), handled by the runner wrapper.
# --------------------------------------------------------------------------------------------

# ---- FRONT-HALF lane -----------------------------------------------------------------------

def dice_d0_scope_no_source_drop(ctx: Ctx) -> DiceResult:
    inv = "scope is a question-level accept/reject verdict, never a per-source thinner"
    m = ctx.fx.load_json("manifest.json")
    status = m.get("status", "")
    intent = m.get("intent_frame", {}) or {}
    ok = (status != "abort_scope_rejected") and bool(intent)
    detail = f"status={status!r}; intent_frame present={bool(intent)} (scope accepted, 0 sources dropped)"
    return DiceResult("D0_scope_no_source_drop", "front", "OFFLINE",
                      GREEN if ok else RED, inv, detail)


def dice_d1_retrieval_reconcile(ctx: Ctx) -> DiceResult:
    inv = "fetched + failed reconciles to candidates_processed; the funnel is fully accounted"
    m = ctx.fx.load_json("manifest.json")
    r = m.get("retrieval", {}) or {}
    fetched = int(r.get("fetched", 0))
    failed = int(r.get("failed", 0))
    processed = int(r.get("candidates_processed", 0))
    ok = (fetched + failed) == processed and processed > 0
    detail = f"fetched={fetched} + failed={failed} == candidates_processed={processed} -> {ok}"
    return DiceResult("D1_retrieval_reconcile", "front", "OFFLINE",
                      GREEN if ok else RED, inv, detail)


def dice_d3_relevance_gate_fetch_budget(ctx: Ctx) -> DiceResult:
    """RE-ATTRIBUTED (I-deepfix-001 #1344): the drb_72 760-source pre-fetch reduction is the B4
    RELEVANCE GATE (PG_RELEVANCE_FLOOR ordering) + the disclosed PG_LIVE_FETCH_CAP fetch BUDGET --
    NOT the prefetch off-topic filter, which was OFF on this run (prefetch_offtopic=None,
    kept_by_offtopic=926, dropped ZERO). The old dice blamed the off-topic filter and gated on
    `dropped_pre_fetch==0`, mis-labelling the drop. The §-1.3 WEIGHT-not-FILTER proof lives in the
    A5c-landed manifest field `retrieval.relevance_gate.demoted_fetched_to_fill` (below-floor
    candidates the BUDGET still FETCHED -> proof the floor only ORDERS, never hard-cuts). On a
    FRESH (B4-ON) manifest the dice is GREEN when that demote-not-drop disclosure is present
    (demoted_fetched_to_fill>0) and the only bound is the disclosed fetch budget; on the OLD banked
    manifest (no relevance_gate key) it stays RED -- honest, pre-fix."""
    inv = ("the pre-fetch reduction is the B4 relevance gate (PG_RELEVANCE_FLOOR) WEIGHT-demotion "
           "+ disclosed fetch budget, NOT a hard filter: off-topic filter drops 0, "
           "relevance_gate.demoted_fetched_to_fill>0 (demote-not-drop), budget is the only bound")
    m = ctx.fx.load_json("manifest.json")
    r = m.get("retrieval", {}) or {}
    caps = r.get("retrieval_caps", {}) or {}
    dropped = int(caps.get("dropped_pre_fetch", 0))
    discovered = int(caps.get("candidates_discovered", 0))

    # (1) the off-topic filter is NOT the dropper -- it is a SEPARATE weight, OFF on drb_72.
    # prefetch_offtopic is None (filter off) or a disclosure dict; pull its hard-drop count if any.
    pf = r.get("prefetch_offtopic")
    if isinstance(pf, dict):
        offtopic_dropped = int(pf.get("rejected", pf.get("dropped", 0)) or 0)
    else:
        offtopic_dropped = 0
    kept_by_offtopic = r.get("kept_by_offtopic")
    offtopic_ok = offtopic_dropped <= ctx.th.prefetch_max_drop

    # (2) the disclosed fetch BUDGET cap (the §-1.3 cost bound that the drop must reflect).
    truncs = caps.get("search_truncations", []) or []
    budget_caps = {c.upper() for c in ctx.th.fetch_budget_caps}
    budget_entry = next(
        (st for st in truncs if str(st.get("cap", "")).upper() in budget_caps), None)
    budget_disclosed = budget_entry is not None

    # (3) the A5c DEMOTE-NOT-DROP disclosure (None on the OLD banked manifest => RED, honest).
    rg = r.get("relevance_gate")
    has_rg = isinstance(rg, dict)
    demoted_below_floor = int(rg.get("demoted_below_floor", 0)) if has_rg else 0
    demoted_fetched_to_fill = int(rg.get("demoted_fetched_to_fill", 0)) if has_rg else 0
    demoted_tail = int(rg.get("demoted_tail", 0)) if has_rg else 0
    unfetched_relevant_tail = int(rg.get("unfetched_relevant_tail", 0)) if has_rg else 0
    # Robust weight-not-filter proof (the dropped_pre_fetch funnel = discovered-fetched-failed is a
    # DIFFERENT count from the gate's scored pool -- seeds bypass scoring -- so a strict equality is
    # unsafe; the budget-only attribution is proven by (a) the demote disclosure existing,
    # (b) demoted_fetched_to_fill>0, and (c) the disclosed budget being the bound). The exact
    # arithmetic (gate tail vs dropped_pre_fetch) is surfaced advisory + confirmed by LIVE smoke.
    weight_to_fill = demoted_fetched_to_fill >= ctx.th.min_demoted_fetched_to_fill
    gate_tail = unfetched_relevant_tail + demoted_tail
    ok = has_rg and weight_to_fill and offtopic_ok and budget_disclosed

    budget_str = (f"{budget_entry.get('cap')}={budget_entry.get('value')} bit={budget_entry.get('bit')}"
                  if budget_entry else "NONE-DISCLOSED")
    if has_rg:
        detail = (f"dropped_pre_fetch={dropped} of discovered={discovered}; off-topic filter "
                  f"dropped={offtopic_dropped} (kept_by_offtopic={kept_by_offtopic}, NOT the dropper); "
                  f"fetch_budget[{budget_str}]; relevance_gate demote-not-drop: below_floor="
                  f"{demoted_below_floor} fetched_to_fill={demoted_fetched_to_fill} "
                  f"tail={demoted_tail} unfetched_relevant_tail={unfetched_relevant_tail} "
                  f"(gate_tail={gate_tail}); fetched_to_fill>=min({ctx.th.min_demoted_fetched_to_fill}) "
                  f"-> {'WEIGHT-not-FILTER (budget-only)' if ok else 'NOT PROVEN'}")
    else:
        detail = (f"dropped_pre_fetch={dropped} of discovered={discovered}; off-topic filter "
                  f"dropped={offtopic_dropped} (prefetch_offtopic={pf!r}, kept_by_offtopic="
                  f"{kept_by_offtopic}) so it is NOT the dropper; fetch_budget[{budget_str}]; "
                  f"retrieval.relevance_gate ABSENT (B4 OFF / pre-A5c banked manifest) -> the demote-"
                  f"not-drop proof (demoted_fetched_to_fill) cannot be read -> the {dropped}-drop is "
                  f"the B4 relevance gate + fetch budget but UN-disclosed-as-weight -> RED (honest pre-fix)")
    return DiceResult("D3_relevance_gate_fetch_budget", "front", "OFFLINE",
                      GREEN if ok else RED, inv, detail)


def dice_d7_adequacy_proceed(ctx: Ctx) -> DiceResult:
    inv = "corpus-adequacy is a pipeline-verdict gate (proceed/expand/abort), never a source drop"
    m = ctx.fx.load_json("manifest.json")
    a = m.get("adequacy", {}) or {}
    decision = a.get("decision")
    ok = decision in ("proceed", "expand") and m.get("status") != "abort_corpus_inadequate"
    detail = (f"decision={decision!r} findings_ok={a.get('findings_ok')}/"
              f"{a.get('findings_total')} (gate verdict; corpus length unchanged)")
    return DiceResult("D7_adequacy_proceed", "front", "OFFLINE",
                      GREEN if ok else RED, inv, detail)


def dice_d8_approval_no_drop(ctx: Ctx) -> DiceResult:
    inv = "corpus-approval is a verdict gate over ALL sources; tier mix is disclosed, not thinned"
    m = ctx.fx.load_json("manifest.json")
    c = m.get("corpus", {}) or {}
    approved = bool(c.get("approved"))
    ok = approved and m.get("status") != "abort_corpus_approval_denied"
    detail = (f"approved={approved} count={c.get('count')} "
              f"material_deviation={c.get('material_deviation')} (disclosed; 0 dropped)")
    return DiceResult("D8_approval_no_drop", "front", "OFFLINE",
                      GREEN if ok else RED, inv, detail)


def dice_d9_selection_keep_all(ctx: Ctx) -> DiceResult:
    inv = "selection keep-all: dropped_count==0 (only strict_verify, downstream, may drop)"
    m = ctx.fx.load_json("manifest.json")
    sel = m.get("evidence_selection", {}) or {}
    dropped = sel.get("dropped_count")
    strategy = sel.get("selection_strategy", "")
    ok = dropped == 0
    detail = (f"dropped_count={dropped} strategy={strategy!r} "
              f"selected={sel.get('evidence_selected')} (keep-all path; floor only re-orders)")
    return DiceResult("D9_selection_keep_all", "front", "OFFLINE",
                      GREEN if ok else RED, inv, detail)


def dice_d4_judge_completed_offline(ctx: Ctx) -> DiceResult:
    inv = "4-role judge COMPLETED: final_verdicts non-empty, not abort_role_transport_exhausted"
    m = ctx.fx.load_json("manifest.json")
    fr = m.get("four_role_evaluation", {}) or {}
    fv = fr.get("final_verdicts", {}) or {}
    held = fr.get("held_reasons")
    status = m.get("status", "")
    transport_dead = status == "abort_role_transport_exhausted"
    ok = bool(fv) and not transport_dead
    dist = dict(Counter(fv.values())) if isinstance(fv, dict) else {}
    detail = (f"final_verdicts={len(fv)} dist={dist} status={status!r} "
              f"(offline completion sanity; the 429/seam-tear behaviour itself is LIVE)")
    return DiceResult("D4_judge_completed_offline", "back", "OFFLINE",
                      GREEN if ok else RED, inv, detail)


# ---- BACK-HALF lane ------------------------------------------------------------------------

def dice_d1_consolidation_baskets(ctx: Ctx) -> DiceResult:
    inv = "consolidation forms multi-source corroboration baskets (CONSOLIDATE-keep-all, §-1.3)"
    m = ctx.fx.load_json("manifest.json")
    clusters = (m.get("finding_dedup", {}) or {}).get("clusters", []) or []
    corro = [c for c in clusters if int(c.get("corroboration_count", 0)) > 1]
    n_drops = int((m.get("fact_dedup", {}) or {}).get("n_drops", 0))
    max_corro = max((int(c.get("corroboration_count", 0)) for c in clusters), default=0)
    ok = len(corro) >= ctx.th.min_corroborated_baskets and n_drops == 0
    detail = (f"clusters={len(clusters)} with_corroboration>1={len(corro)} "
              f"(min {ctx.th.min_corroborated_baskets}) max_corroboration={max_corro} "
              f"fact_dedup.n_drops={n_drops} (baskets keep ALL members)")
    return DiceResult("D1_consolidation_baskets", "back", "OFFLINE",
                      GREEN if ok else RED, inv, detail)


def dice_d2_composition_breadth(ctx: Ctx) -> DiceResult:
    inv = "composition surfaces the weighted tail: cited-distinct / generator-pool >= breadth floor"
    m = ctx.fx.load_json("manifest.json")
    report = ctx.fx.read_text("report.md")
    pool = _generator_pool_size(m)
    cited_markers = _distinct_citation_keys(report)
    # cross-check: distinct evidence_ids cited across the composed/audited claims
    cited_evids = 0
    verified_evids = 0
    audit_p = ctx.fx.find("four_role_claim_audit.json")
    if audit_p is not None:
        audit = json.loads(audit_p.read_text(encoding="utf-8"))
        fv = (m.get("four_role_evaluation", {}) or {}).get("final_verdicts", {}) or {}
        allev, veref = set(), set()
        for cid, rec in audit.items():
            if not isinstance(rec, dict):
                continue
            for e in rec.get("evidence_ids", []) or []:
                allev.add(e)
                if fv.get(cid) == "VERIFIED":
                    veref.add(e)
        cited_evids, verified_evids = len(allev), len(veref)
    ratio = (cited_markers / pool) if pool else 0.0
    ok = ratio >= ctx.th.breadth_floor and pool > 0
    detail = (f"cited_distinct_markers={cited_markers} / generator_pool={pool} = {ratio:.3f} "
              f"(floor {ctx.th.breadth_floor:.2f}); cross-check evidence_ids cited={cited_evids} "
              f"(VERIFIED-cited={verified_evids}) -> {'OK' if ok else 'UNDER-SURFACE'}")
    return DiceResult("D2_composition_breadth", "back", "OFFLINE",
                      GREEN if ok else RED, inv, detail)


def dice_d2_composition_repetition(ctx: Ctx) -> DiceResult:
    inv = "length is content-driven: no degenerate repetition (n-gram repeat-rate < ceiling)"
    report = ctx.fx.read_text("report.md")
    rate, max_count, top = _ngram_repetition(report, ctx.th.repetition_ngram)
    ok = rate < ctx.th.repetition_ceiling and max_count <= ctx.th.repetition_max_phrase_count
    detail = (f"{ctx.th.repetition_ngram}-gram repeat_rate={rate:.3f} (ceiling "
              f"{ctx.th.repetition_ceiling:.2f}) max_phrase_count={max_count} "
              f"(max {ctx.th.repetition_max_phrase_count}); top={top[:60]!r} "
              f"-> {'OK' if ok else 'DEGENERATE'}")
    return DiceResult("D2_composition_repetition", "back", "OFFLINE",
                      GREEN if ok else RED, inv, detail)


def dice_d3_contradiction_only_comparable(ctx: Ctx) -> DiceResult:
    inv = "headline contradictions are only-comparable; not_comparable rows excluded from the count"
    m = ctx.fx.load_json("manifest.json")
    records = ctx.fx.load_json("contradictions.json")
    if not isinstance(records, list):
        records = records.get("contradictions", []) if isinstance(records, dict) else []
    headline = int(m.get("contradictions_found", 0))
    comparable = [r for r in records if not r.get("not_comparable")]
    not_comparable = [r for r in records if r.get("not_comparable")]
    ok = headline == len(comparable)
    detail = (f"manifest.contradictions_found={headline} but comparable_records="
              f"{len(comparable)} (not_comparable={len(not_comparable)} of {len(records)}); "
              f"a headline count > comparable means false-contradictions leaked -> "
              f"{'OK' if ok else 'FALSE-CONTRADICTION'}")
    return DiceResult("D3_contradiction_only_comparable", "back", "OFFLINE",
                      GREEN if ok else RED, inv, detail)


def dice_d5_strict_verify_only_drop(ctx: Ctx) -> DiceResult:
    inv = "strict_verify is the ONLY legal drop; consolidation/compose/fact_dedup drop nothing"
    m = ctx.fx.load_json("manifest.json")
    fd = m.get("fact_dedup", {}) or {}
    n_drops = int(fd.get("n_drops", 0))
    n_span_cite_dropped = int(fd.get("n_span_cite_dropped", 0))
    floor_dropped = int(m.get("evidence_floor_dropped", 0))
    # the legal strict_verify drop is generator.sentences_dropped -- NOT a violation
    sv_drops = int((m.get("generator", {}) or {}).get("sentences_dropped", 0))
    ok = n_drops == 0 and n_span_cite_dropped == 0
    detail = (f"fact_dedup.n_drops={n_drops} n_span_cite_dropped={n_span_cite_dropped} "
              f"evidence_floor_dropped={floor_dropped} | legal strict_verify "
              f"sentences_dropped={sv_drops} -> {'OK (only verify drops)' if ok else 'ILLEGAL DROP'}")
    return DiceResult("D5_strict_verify_only_drop", "back", "OFFLINE",
                      GREEN if ok else RED, inv, detail)


def _load_report_redactor():
    """Load the stdlib-only report_redactor module by file path (no heavy package __init__)."""
    spec = importlib.util.spec_from_file_location(
        "polaris_report_redactor_isolated", str(_REPORT_REDACTOR_PATH)
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot build spec for {_REPORT_REDACTOR_PATH}")
    mod = importlib.util.module_from_spec(spec)
    # Register BEFORE exec: @dataclass resolves sys.modules[cls.__module__].__dict__, which is
    # None for an unregistered synthetic module (Py3.12+ dataclasses fail-loud otherwise).
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def dice_d6_redaction_backbone_tear(ctx: Ctx) -> DiceResult:
    inv = "on a simulated seam tear, reconcile SHIPS every VERIFIED claim, quarantines non-VERIFIED"
    redactor = _load_report_redactor()
    # Synthetic torn-seam fixture: one VERIFIED backbone claim + one UNSUPPORTED claim. The
    # "tear" = the seam returned only partial role calls, so the audit map is re-derived from
    # partials and reconcile runs against it. This exercises the REAL stage function.
    ver_sentence = ("The intervention reduced 30-day mortality by 12 percent in the trial "
                    "cohort [#ev:ev_alpha:10-90].")
    uns_sentence = ("The drug eliminates all disease risk permanently for every patient "
                    "[#ev:ev_beta:5-70].")
    report_text = (
        "## Findings\n\n"
        f"- {ver_sentence}\n\n"
        f"- {uns_sentence}\n"
    )
    final_verdicts = {"c_verified": "VERIFIED", "c_unsupported": "UNSUPPORTED"}
    audit_map = {
        "c_verified": {"sentence": ver_sentence, "severity": "S1"},
        "c_unsupported": {"sentence": uns_sentence, "severity": "S1"},
    }
    result = redactor.reconcile_report_against_verdicts(report_text, final_verdicts, audit_map)
    out = result.report_text
    backbone_kept = ver_sentence in out
    non_verified_gone = uns_sentence not in out
    redacted_ids = [rc.claim_id for rc in getattr(result, "redacted", [])]

    # Banked cross-check: on the shipped report.md the recorded VERIFIED backbone must actually
    # be PRESENT (not torn out). Codex P1 (#1344 wave-2): the old code computed this rate but
    # only put it in a note and never GATED it -- so a banked report that dropped most of its
    # VERIFIED backbone could still go GREEN (a gate that lies). Now it is a real gate: when an
    # audit+report fixture is present, the present-rate must meet PG_DICED_BACKBONE_MIN_PRESENT.
    leak_note = ""
    banked_present_rate: float | None = None
    backbone_min = _env_float("PG_DICED_BACKBONE_MIN_PRESENT", 0.90)
    try:
        m = ctx.fx.load_json("manifest.json")
        fv = (m.get("four_role_evaluation", {}) or {}).get("final_verdicts", {}) or {}
        audit_p = ctx.fx.find("four_role_claim_audit.json")
        shipped = _normalize_prose(ctx.fx.read_text("report.md"))
        if audit_p is not None and shipped:
            audit = json.loads(audit_p.read_text(encoding="utf-8"))
            verified = [cid for cid, v in fv.items() if v == "VERIFIED"]
            present = 0
            for cid in verified:
                s = _normalize_prose(audit.get(cid, {}).get("sentence", "")).split()
                probe = " ".join(s[3:11]) if len(s) >= 8 else " ".join(s)
                if probe and probe in shipped:
                    present += 1
            rate = present / len(verified) if verified else 1.0
            banked_present_rate = rate
            leak_note = f"; banked report VERIFIED-backbone present {present}/{len(verified)}={rate:.2f}"
    except Exception as exc:  # the cross-check itself failing == no banked fixture (advisory)
        leak_note = f"; banked cross-check skipped ({type(exc).__name__})"

    # When a banked report IS present, its backbone present-rate is GATED (not advisory).
    banked_backbone_ok = banked_present_rate is None or banked_present_rate >= backbone_min
    ok = backbone_kept and non_verified_gone and banked_backbone_ok
    detail = (f"reconcile(real fn): VERIFIED kept={backbone_kept} UNSUPPORTED quarantined="
              f"{non_verified_gone} redacted_ids={redacted_ids}{leak_note}"
              f"; banked_backbone>={backbone_min:.2f}:{banked_backbone_ok}")
    return DiceResult("D6_redaction_backbone_tear", "back", "OFFLINE",
                      GREEN if ok else RED, inv, detail)


def dice_d7_render_chrome(ctx: Ctx) -> DiceResult:
    inv = ("render is clean by the INDEPENDENT detector: 0 chrome / 0 truncation / "
           "0 false-contradiction-surfaced (the production chrome predicate is BLIND -- I-wire-013)")
    if not _INDEPENDENT_RENDER_DETECTOR.exists():
        raise FileNotFoundError(f"independent detector missing: {_INDEPENDENT_RENDER_DETECTOR}")
    report_p = ctx.fx.require("report.md")
    evidence_p = ctx.fx.require("evidence_pool.json")
    contra_p = ctx.fx.require("contradictions.json")
    # The detector resolves evidence_pool.json + contradictions.json from the report's parent
    # dir. Stage them next to a copy of report.md in an isolated temp snapshot dir.
    with tempfile.TemporaryDirectory(prefix="diced_render_") as td:
        tdp = Path(td)
        (tdp / "report.md").write_text(report_p.read_text(encoding="utf-8"), encoding="utf-8")
        (tdp / "evidence_pool.json").write_text(evidence_p.read_text(encoding="utf-8"), encoding="utf-8")
        (tdp / "contradictions.json").write_text(contra_p.read_text(encoding="utf-8"), encoding="utf-8")
        cmd = [
            sys.executable, str(_INDEPENDENT_RENDER_DETECTOR),
            "--report", str(tdp / "report.md"),
            "--chrome-max", str(ctx.th.chrome_max),
            "--truncation-max", str(ctx.th.truncation_max),
            "--contradiction-noise-max", str(ctx.th.contradiction_noise_max),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    summary = ""
    for line in proc.stdout.splitlines():
        s = line.strip()
        if s.startswith("(a)") or s.startswith("(b)") or s.startswith("(c)") or s.startswith("[forensic] OVERALL"):
            summary += s + " | "
    ok = proc.returncode == 0
    detail = (f"independent detector exit={proc.returncode} (0==clean) :: {summary.strip(' |')}"
              or f"exit={proc.returncode}")
    return DiceResult("D7_render_chrome", "back", "OFFLINE",
                      GREEN if ok else RED, inv, detail)


# --------------------------------------------------------------------------------------------
# I-deepfix-001 #1344 -- the 5 LATENT GUARD-GAP dice the stage map surfaced. Each investigates an
# invariant the existing dice did NOT cover, asserts it on the banked drb_72 fixture, and goes
# GREEN where the stage was healthy / RED where the gap is real. Every threshold is env-tunable
# (LAW VI). All are read-only over the banked JSON (+ os.environ for the env-guard).
# --------------------------------------------------------------------------------------------

def dice_d4_relevance_weight_not_drop(ctx: Ctx) -> DiceResult:
    """GAP: the relevance leg must WEIGHT, never DROP (§-1.3). Banked fixture carries no per-passage
    relevance weights (the run resumed from corpus_snapshot, B4 relevance_gate=None, W2
    content_relevance=None) -> assert the structural keep-all (dropped_count==0) and defer the
    per-passage min-weight>0 floor to a LIVE smoke. A real relevance hard-drop (dropped_count>0)
    flips this RED."""
    inv = ("relevance leg WEIGHTS-not-DROPS: selection kept-all (dropped_count==0); per-passage "
           "min relevance weight>0 is LIVE-SMOKE-REQUIRED when the banked fixture lacks weights")
    m = ctx.fx.load_json("manifest.json")
    sel = m.get("evidence_selection", {}) or {}
    dropped = sel.get("dropped_count")
    strategy = sel.get("selection_strategy", "")
    r = m.get("retrieval", {}) or {}
    fell_back = bool(r.get("semantic_relevance_fell_back"))
    # per-passage relevance weights, if the W2 content-relevance judge persisted them (fresh run).
    cr = r.get("content_relevance")
    weights: list[float] = []
    if isinstance(cr, dict):
        raw_w = cr.get("passage_weights") or cr.get("weights") or []
        if isinstance(raw_w, list):
            weights = [float(w) for w in raw_w if isinstance(w, (int, float))]
    keep_all = (dropped == 0)
    if weights:
        min_w = min(weights)
        ok = keep_all and min_w > 0.0
        detail = (f"per-passage relevance weights n={len(weights)} min_weight={min_w:.4f} "
                  f"dropped_count={dropped} -> {'WEIGHT-not-DROP' if ok else 'DROP/zero-weight'}")
    else:
        ok = keep_all
        detail = (f"dropped_count={dropped} strategy={strategy!r} semantic_relevance_fell_back="
                  f"{fell_back}; banked fixture has NO per-passage relevance weights -> structural "
                  f"keep-all asserted; LIVE-SMOKE-REQUIRED: min relevance weight>0 on a fresh "
                  f"PG_CONTENT_RELEVANCE_JUDGE=1 run -> {'KEEP-ALL OK' if ok else 'RELEVANCE DROP'}")
    return DiceResult("D4_relevance_weight_not_drop", "front", "OFFLINE",
                      GREEN if ok else RED, inv, detail)


def dice_d5_credibility_honest_tiering(ctx: Ctx) -> DiceResult:
    """GAP: credibility/tier is an honest WEIGHT over ALL sources (§-1.3), never a degraded
    rules-floor that silently drops. Strong invariant (when a fresh manifest carries `tiering_mode`):
    mode != rules_floor_degraded AND every source classified (0 dropped). The banked manifest lacks
    `tiering_mode` -> assert the weaker invariant (disclosure present + classified count == sources)
    and emit a LIVE-SMOKE-REQUIRED note for tiering_mode. A classified!=sources mismatch (a drop) or
    a degraded tiering mode flips this RED."""
    inv = ("credibility is honest WEIGHT-tiering: tiering_mode != rules_floor_degraded AND every "
           "source classified (classified count == total_sources, 0 dropped)")
    m = ctx.fx.load_json("manifest.json")
    ccd = m.get("corpus_credibility_disclosure", {}) or {}
    tier_counts = ccd.get("tier_counts", {}) or {}
    classified = sum(int(v) for v in tier_counts.values())
    total_sources = ccd.get("total_sources")
    corpus_count = int((m.get("corpus", {}) or {}).get("count", 0))
    status_present = bool(ccd) and bool(ccd.get("gate") or ccd.get("disclosure_note"))
    count_ok = (total_sources is not None and classified == total_sources
                and total_sources == corpus_count)
    tiering_mode = ccd.get("tiering_mode")
    disclosed_gap = m.get("credibility_disclosed_gap")
    if tiering_mode is not None:
        ok = status_present and count_ok and tiering_mode != ctx.th.degraded_tiering_mode
        detail = (f"tiering_mode={tiering_mode!r} (!= {ctx.th.degraded_tiering_mode!r}); classified="
                  f"{classified} total_sources={total_sources} corpus.count={corpus_count} "
                  f"status_present={status_present} -> {'HONEST TIERING' if ok else 'DEGRADED/DROP'}")
    else:
        ok = status_present and count_ok
        detail = (f"banked manifest lacks tiering_mode -> WEAKER invariant: status_present="
                  f"{status_present} classified={classified}==total_sources={total_sources}=="
                  f"corpus.count={corpus_count} -> {'KEEP-ALL OK' if ok else 'COUNT MISMATCH/DROP'}; "
                  f"credibility_disclosed_gap={str(disclosed_gap)[:60]!r}; LIVE-SMOKE-REQUIRED: "
                  f"tiering_mode != {ctx.th.degraded_tiering_mode!r} + credibility-pass completes "
                  f"in-wall on a fresh run (the banked scoring pass timed out, disclosed)")
    return DiceResult("D5_credibility_honest_tiering", "front", "OFFLINE",
                      GREEN if ok else RED, inv, detail)


def dice_d6_topic_gate_env_guard(ctx: Ctx) -> DiceResult:
    """GAP: the scope topic-gate must stay WEIGHT-not-FILTER (§-1.3-banned scope hard-filter). The
    legacy escape hatch PG_SCOPE_TOPIC_GATE_HARD_DROP (default OFF) re-arms a hard drop -> assert
    the run env does NOT set it truthy (mirroring the production truthiness of
    topic_gate_hard_drop_enabled), AND the banked topic gate, if recorded, kept-all (n_kept==n_in).
    A re-armed hard-drop OR a topic-gate that dropped sources flips this RED."""
    inv = ("scope topic-gate is WEIGHT-not-FILTER: the legacy escape hatch "
           "PG_SCOPE_TOPIC_GATE_HARD_DROP must be unset/falsey AND any recorded topic gate kept-all "
           "(n_kept==n_in)")
    env_name = ctx.th.topic_gate_hard_drop_env
    raw = (os.environ.get(env_name, "0") or "0").strip().lower()
    # mirror src/polaris_graph/retrieval/topic_relevance_gate.py::topic_gate_hard_drop_enabled
    armed = raw not in ("0", "false", "no", "off", "")
    # banked topic-gate telemetry, if the manifest recorded it (resume runs skip the gate entirely).
    m = ctx.fx.load_json("manifest.json")
    tg = None
    for key in ("topic_gate", "scope_topic_gate", "topic_relevance_gate"):
        cand = m.get(key)
        if isinstance(cand, dict):
            tg = cand
            break
    if tg is not None:
        n_in = tg.get("n_in")
        n_kept = tg.get("n_kept")
        gate_ok = (n_in is not None and n_kept == n_in)
        gate_str = f"topic_gate n_in={n_in} n_kept={n_kept} kept_all={gate_ok}"
    else:
        gate_ok = True
        gate_str = "no topic_gate block in manifest (gate not run on this resume; env-guard is binding)"
    ok = (not armed) and gate_ok
    detail = (f"{env_name}={raw!r} armed={armed} (a truthy value re-arms the §-1.3-banned scope "
              f"hard-filter); {gate_str} -> {'WEIGHT-not-FILTER' if ok else 'HARD-FILTER RE-ARMED/DROP'}")
    return DiceResult("D6_topic_gate_env_guard", "front", "OFFLINE",
                      GREEN if ok else RED, inv, detail)


def dice_d1_consolidation_qualitative_basket(ctx: Ctx) -> DiceResult:
    """GAP (KNOWN-RED, exposing): consolidation must CONSOLIDATE qualitative claims too (§-1.3), not
    numeric-only. The current fact_dedup/finding_dedup keys every corroboration basket on a NUMERIC
    finding_key slot, so a non-numeric (qualitative) claim can never form a multi-source basket.
    This dice asserts >=1 corroborated QUALITATIVE basket exists -- EXPECTED to be RED on the banked
    fixture (it exposes the numeric-only blind spot the behavioral fix will close post-commit). It is
    NOT weakened to pass; it goes GREEN only once a real qualitative basket forms."""
    inv = ("consolidation forms a corroboration basket for >=1 QUALITATIVE (non-numeric) claim "
           "(CONSOLIDATE qualitative too, §-1.3), not numeric-only")
    m = ctx.fx.load_json("manifest.json")
    clusters = (m.get("finding_dedup", {}) or {}).get("clusters", []) or []

    def _has_numeric_key(finding_key) -> bool:
        if not isinstance(finding_key, (list, tuple)):
            return False
        for el in finding_key:
            if isinstance(el, bool):
                continue
            if isinstance(el, (int, float)) and float(el) != 0.0:
                return True
        return False

    corro = [c for c in clusters if int(c.get("corroboration_count", 0)) > 1]
    qual_corro = [c for c in corro if not _has_numeric_key(c.get("finding_key", []))]
    n_qual = len(qual_corro)
    ok = n_qual >= ctx.th.min_qualitative_baskets
    detail = (f"corroborated_baskets(>1)={len(corro)} of which QUALITATIVE(non-numeric finding_key)="
              f"{n_qual} (min {ctx.th.min_qualitative_baskets}); fact_dedup keys baskets on a numeric "
              f"finding_key slot ONLY -> the qualitative-consolidation BLIND SPOT "
              f"-> {'OK' if ok else 'KNOWN-RED-BY-DESIGN (exposes the gap; the behavioral fix closes it)'}")
    return DiceResult("D1_consolidation_qualitative_basket", "back", "OFFLINE",
                      GREEN if ok else RED, inv, detail, by_design=not ok)


def dice_fx06_population_coupling(ctx: Ctx) -> DiceResult:
    """GAP (FX-06): D7<->D8 self-consistency. The source population the adequacy gate (D7) evaluated
    must equal the approval (D8) tier-distribution total and the disclosed total_sources. The
    historic 833-vs-639 eruption was exactly this desync. Strong form reads `adequacy.total_sources`
    when a fresh manifest carries it; on the banked fixture (adequacy carries only findings counts)
    it falls back to corpus.count as the adequacy-evaluated population. Any mismatch flips RED."""
    inv = ("D7<->D8 population coupling: adequacy source population == approval tier-distribution "
           "total == disclosed total_sources (the 833-vs-639 desync goes RED)")
    m = ctx.fx.load_json("manifest.json")
    adq = m.get("adequacy", {}) or {}
    corpus = m.get("corpus", {}) or {}
    ccd = m.get("corpus_credibility_disclosure", {}) or {}
    adq_total = adq.get("total_sources")
    if adq_total is None:
        adq_total = corpus.get("count")
        adq_src = "corpus.count (adequacy.total_sources absent on banked manifest)"
    else:
        adq_src = "adequacy.total_sources"
    tier_counts = ccd.get("tier_counts", {}) or {}
    approval_dist_total = sum(int(v) for v in tier_counts.values())
    ccd_total = ccd.get("total_sources")
    ok = (adq_total is not None and approval_dist_total > 0
          and adq_total == approval_dist_total == ccd_total)
    detail = (f"adequacy_population={adq_total} [{adq_src}] vs approval tier-distribution total="
              f"{approval_dist_total} vs disclosed total_sources={ccd_total} "
              f"-> {'COUPLED' if ok else 'POPULATION DESYNC (833-vs-639 class)'}")
    return DiceResult("FX06_population_coupling", "front", "OFFLINE",
                      GREEN if ok else RED, inv, detail)


OFFLINE_DICE: list[Callable[[Ctx], DiceResult]] = [
    # front-half lane (RETRIEVAL -> SELECTION)
    dice_d0_scope_no_source_drop,
    dice_d1_retrieval_reconcile,
    dice_d3_relevance_gate_fetch_budget,
    dice_d4_relevance_weight_not_drop,
    dice_d5_credibility_honest_tiering,
    dice_d6_topic_gate_env_guard,
    dice_d7_adequacy_proceed,
    dice_d8_approval_no_drop,
    dice_d9_selection_keep_all,
    dice_fx06_population_coupling,
    # back-half lane (CONSOLIDATION -> RENDER)
    dice_d1_consolidation_baskets,
    dice_d1_consolidation_qualitative_basket,
    dice_d2_composition_breadth,
    dice_d2_composition_repetition,
    dice_d3_contradiction_only_comparable,
    dice_d4_judge_completed_offline,
    dice_d5_strict_verify_only_drop,
    dice_d6_redaction_backbone_tear,
    dice_d7_render_chrome,
]


# --------------------------------------------------------------------------------------------
# LIVE-ONLY DICE -- cannot be validated by a banked replay (I-wire-013/014 false-PASS lesson).
# Emit an exact tiny command; NEVER make a paid call here. All run on the VM (memory: ALL heavy
# GPU+LLM runs on the VM, never local). Placeholders are env-tunable.
# --------------------------------------------------------------------------------------------

def live_dice(fx: FixtureResolver) -> list[DiceResult]:
    vm = os.environ.get("PG_DICED_VM_HOST", "<vm-ssh-host>")          # e.g. ssh2.vast.ai -p 37450
    snap = os.environ.get("PG_DICED_LIVE_SNAPSHOT", "outputs/<run>/corpus_snapshot.json")
    question = os.environ.get("PG_DICED_LIVE_QUESTION", "drb_72")
    judge_cmd = (
        f"# 4-ROLE JUDGE 429-storm / seam-tear -- a live-transport phenomenon a banked replay "
        f"CANNOT reproduce.\n"
        f"#   ssh {vm} 'cd /workspace/POLARIS && env -u OPENAI_API_KEY "
        f"PG_FOUR_ROLE_SEAM_DEADLINE_S=120 python scripts/run_honest_sweep_r3.py "
        f"--only \"{question}\" --resume {snap} --stop-after four_role 2>&1 | "
        f"tee /tmp/diced_judge_smoke.log'\n"
        f"#   ASSERT: manifest.status != abort_role_transport_exhausted ; "
        f"four_role 429 sidecar 429s-seen==0 ; _seam_held_reason is None ; "
        f"four_role_claim_audit.json has a row for every settled claim."
    )
    oom_cmd = (
        f"# GPU OOM degrade -- needs the real 2xRTX3090Ti VM GPU; offline cannot load the model.\n"
        f"#   ssh {vm} 'cd /workspace/POLARIS && CUDA_VISIBLE_DEVICES=0 python -c "
        f"\"from sentence_transformers import SentenceTransformer as S; "
        f"m=S(\\\"Qwen/Qwen3-Embedding-8B\\\"); print(m.encode([\\\"probe\\\"]*512).shape)\" "
        f"2>&1 | tee /tmp/diced_oom_smoke.log'\n"
        f"#   ASSERT: completes OR fails LOUD with a disclosed OOM-degrade "
        f"(clinical_pdf_winner_degraded / semantic_relevance_fell_back set + LOUD log), "
        f"never a silent empty-embedding."
    )
    return [
        DiceResult("D4_four_role_judge_seam_LIVE", "back", "LIVE", LIVE,
                   "judge COMPLETES under live transport: 0 seam_timeout, 0 429-storm",
                   "the 429/seam tear is a live-transport phenomenon; a banked replay cannot "
                   "validate completion (I-wire-013/014 false-PASS lesson)",
                   judge_cmd),
        DiceResult("GPU_OOM_degrade_LIVE", "infra", "LIVE", LIVE,
                   "GPU OOM degrades LOUD + disclosed, never a silent empty embedding",
                   "OOM only reproduces on the real VM GPU under a full batch; offline cannot "
                   "load the model (memory: heavy GPU runs on the VM, never local)",
                   oom_cmd),
    ]


# --------------------------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------------------------

def _run_offline(ctx: Ctx) -> list[DiceResult]:
    out = []
    for fn in OFFLINE_DICE:
        try:
            out.append(fn(ctx))
        except Exception as exc:  # fail-loud: an un-runnable dice is RED, never skipped
            tb = traceback.format_exc(limit=3).strip().splitlines()[-1]
            out.append(DiceResult(
                getattr(fn, "__name__", "unknown").replace("dice_", ""),
                "?", "OFFLINE", RED,
                "dice could not execute (fail-loud)",
                f"EXCEPTION {type(exc).__name__}: {exc} :: {tb}",
            ))
    return out


def _print_table(offline: list[DiceResult], live: list[DiceResult]) -> None:
    name_w = max([len(r.name) for r in offline + live] + [20])
    print("\n" + "=" * (name_w + 60))
    print("  DICED PREFLIGHT -- per-stage invariant table (drb_72 fixture)")
    print("=" * (name_w + 60))
    print(f"  {'STATUS':<6} {'LANE':<6} {'DICE':<{name_w}}  INVARIANT / DETAIL")
    print("-" * (name_w + 60))
    for r in offline:
        if r.status == GREEN:
            mark = "GREEN"
        else:
            mark = "RED* " if r.by_design else "RED  "   # RED* == KNOWN-RED-BY-DESIGN (exposing dice)
        print(f"  {mark:<6} {r.lane:<6} {r.name:<{name_w}}  {r.invariant}")
        print(f"  {'':<6} {'':<6} {'':<{name_w}}    -> {r.detail}")
    print(f"  (RED* = KNOWN-RED-BY-DESIGN: an exposing dice whose RED is intentional until the "
          f"behavioral fix lands; it is NOT a regression.)")
    if live:
        print("-" * (name_w + 60))
        print("  LIVE-SMOKE-REQUIRED (not run here; no paid call):")
        for r in live:
            print(f"  {LIVE}  {r.lane:<6} {r.name}")
            print(f"        invariant: {r.invariant}")
            print(f"        why-live : {r.detail}")
            for cl in r.live_command.splitlines():
                print(f"        {cl}")
    print("-" * (name_w + 60))


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="DICED preflight harness for the POLARIS pipeline.")
    ap.add_argument("--fixture", action="append", default=None,
                    help="fixture root dir (repeatable; searched in order). "
                         "Default: the banked drb_72 deepfix_replay_forensic2 + deepfix_run1_audit.")
    ap.add_argument("--json", default=None, help="write a machine-readable result sidecar here.")
    args = ap.parse_args(argv)

    if args.fixture:
        roots = [Path(x) for x in args.fixture]
    elif os.environ.get("PG_DICED_FIXTURE_DIRS"):
        roots = [Path(x) for x in os.environ["PG_DICED_FIXTURE_DIRS"].split(os.pathsep) if x]
    else:
        roots = list(_DEFAULT_FIXTURE_DIRS)

    try:
        fx = FixtureResolver(roots)
    except FileNotFoundError as exc:
        print(f"[diced] HARNESS ERROR: {exc}", file=sys.stderr)
        return 2

    th = Thresholds()
    ctx = Ctx(fx=fx, th=th)

    print("[diced] fixture roots (search order):")
    for r in fx.roots:
        print(f"        - {r}")
    print(f"[diced] thresholds: breadth_floor={th.breadth_floor} repetition_ceiling={th.repetition_ceiling} "
          f"repetition_ngram={th.repetition_ngram} prefetch_max_drop={th.prefetch_max_drop} "
          f"chrome/trunc/contra_max={th.chrome_max}/{th.truncation_max}/{th.contradiction_noise_max} "
          f"backbone_min_present={th.backbone_min_present}")
    print(f"[diced] guard-gap thresholds: min_demoted_fetched_to_fill={th.min_demoted_fetched_to_fill} "
          f"min_qualitative_baskets={th.min_qualitative_baskets} "
          f"degraded_tiering_mode={th.degraded_tiering_mode!r} fetch_budget_caps={th.fetch_budget_caps} "
          f"topic_gate_hard_drop_env={th.topic_gate_hard_drop_env!r}")

    offline = _run_offline(ctx)
    live = live_dice(fx)
    _print_table(offline, live)

    red = [r for r in offline if r.status == RED]
    green = [r for r in offline if r.status == GREEN]
    red_eruption = [r for r in red if not r.by_design]
    red_by_design = [r for r in red if r.by_design]
    verdict = "NO-GO" if red else "GO"
    print(f"\n  OFFLINE RESULT: {len(green)} GREEN, {len(red)} RED "
          f"({len(red_eruption)} eruption-RED + {len(red_by_design)} known-RED-by-design)  ->  {verdict}")
    if red_eruption:
        print("  ERUPTION-RED stages (these PROVE the harness catches the real eruptions):")
        for r in red_eruption:
            print(f"    - {r.name}: {r.detail}")
    if red_by_design:
        print("  KNOWN-RED-BY-DESIGN stages (exposing dice; intentional NO-GO until the fix lands):")
        for r in red_by_design:
            print(f"    - {r.name}: {r.detail}")
    print(f"  LIVE dice needing a smoke (run on the VM, not here): "
          f"{', '.join(r.name for r in live)}")
    print("=" * 80)

    if args.json:
        payload = {
            "verdict": verdict,
            "fixture_roots": [str(r) for r in fx.roots],
            "thresholds": th.__dict__,
            "offline": [r.__dict__ for r in offline],
            "live": [r.__dict__ for r in live],
            "red_stages": [r.name for r in red],
            "red_eruption_stages": [r.name for r in red_eruption],
            "red_by_design_stages": [r.name for r in red_by_design],
            "green_stages": [r.name for r in green],
        }
        Path(args.json).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"[diced] wrote sidecar -> {args.json}")

    # Exit non-zero on NO-GO so CI / automation catches a known-bad pre-flight (fail-loud).
    return 1 if red else 0


if __name__ == "__main__":
    sys.exit(main())
