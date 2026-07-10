"""S1.b RETRIEVE breadth resolver — size the retrieval budget from the user's ask.

Design 7 D1 + master §1.1/§1.3 (ruling R11). The production retrieval budget knobs
(query_budget / serper_k / s2_k / serper_total / fetch_cap) have always been env-adjustable
but NEVER sized by the USER'S ASK — an "exhaustive global review" and a "one-drug narrow
question" both got the hardcoded 35 queries / 12 results / 200 fetch. This module reads the
ask (an explicit RunConfig number, a breadth directive in the prompt, or the structural
width of the question) and resolves it to a concrete :class:`BreadthPlan`, bounded by
generous compute-safety ceilings.

§-1.3 discipline (WEIGHT-AND-CONSOLIDATE, not FILTER-AND-CAP): the budget is a compute-safety
CEILING sized to the requirement, never a target the loop pads to. The issued query count
still EMERGES from facets + dedup + the retrieval wall + checklist saturation; a wider budget
only RAISES the ceiling so a genuinely broad ask is not starved. No value here drops a source.

Precedence per knob (master ruling R9 amends Design 7 D1):
    RunConfig explicit number (panel/CLI or a prompt-parsed number, e.g. "run 60 queries")
      >  RunConfig breadth CLASS  (a parsed directive: "comprehensive" -> WIDE)
      >  explicit env var         (PG_QGEN_FS_RESEARCHER_MAX_QUERIES / PG_SWEEP_MAX_SERPER / ...)
      >  structural width         (facet count / multilingual / scope width -> a class)
      >  default class            (STANDARD)
A parsed directive beats a merely-default env var; an explicit panel/CLI number beats
everything (the Gate-B slate writes its fixed values at the override layer, R9). Every
resolved value is clamped LOUDLY to its `abs_max` ceiling.

LAW VI: every number lives in `config/settings/breadth_classes.yaml`; this module reads it.
Wiring flag `PG_BREADTH_RESOLVER` (default OFF): the spine consults the resolver only when ON,
so flag-OFF is byte-identical to today's os.getenv defaults (35 / 12 / 12 / 200). This module
is a PURE function — no network, no LLM, no live_retriever import — so it is offline-testable.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger("polaris_graph.breadth_resolver")

# The five sizing knobs, each with its production env-override var (LAW VI). The env var is the
# EXPLICIT per-knob override the spine already reads today; the resolver honors it above the
# class default (R9 "env beats code default") but below a parsed/panel user directive.
_KNOBS: tuple[str, ...] = ("query_budget", "serper_k", "s2_k", "serper_total", "fetch_cap")
_ENV_OVERRIDE: dict[str, str] = {
    "query_budget": "PG_QGEN_FS_RESEARCHER_MAX_QUERIES",
    "serper_k": "PG_SWEEP_MAX_SERPER",
    "s2_k": "PG_SWEEP_MAX_S2",
    "serper_total": "PG_SERPER_TOTAL_PER_QUERY",
    "fetch_cap": "PG_SWEEP_FETCH_CAP",
}
_ABS_MAX_ENV: dict[str, str] = {
    "query_budget": "PG_QGEN_ABS_MAX_QUERIES",
    "serper_k": "PG_SERPER_K_ABS_MAX",
    "s2_k": "PG_S2_K_ABS_MAX",
    "serper_total": "PG_SERPER_TOTAL_ABS_MAX",
    "fetch_cap": "PG_FETCH_CAP_ABS_MAX",
}

_VALID_CLASSES: frozenset[str] = frozenset({"NARROW", "STANDARD", "WIDE"})

# Deterministic breadth-directive lexicon (Design 7 D1 parse side). Regex-primary; a GLM confirm
# pass is the production semantic fallback (S0) but is NOT needed for the deterministic path and
# is never invoked here (this module stays pure/offline).
_WIDE_LEXICON: tuple[str, ...] = (
    "exhaustive", "comprehensive", "systematic review", "global landscape",
    "all available evidence", "as many sources as", "every relevant", "landscape review",
    "in-depth", "deep dive", "thorough",
)
_NARROW_LEXICON: tuple[str, ...] = (
    "brief", "quick", "overview", "summary", "high-level", "at a glance", "short answer",
    "concise",
)


@dataclass
class BreadthPlan:
    """The resolver OUTPUT (Design 7 D1; master R8 keeps this the resolver's internal type).

    Every field is a resolved integer knob the spine wires straight into the retrieval call;
    ``breadth_class`` + ``rationale`` are DISCLOSED into the manifest so the sizing is auditable.
    ``sources`` records, per knob, which precedence layer supplied the value (for §1.3 disclosure
    and the resolver's own tests)."""

    query_budget: int
    serper_k: int
    s2_k: int
    serper_total: int
    fetch_cap: int
    breadth_class: str
    rationale: str = ""
    sources: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_budget": self.query_budget,
            "serper_k": self.serper_k,
            "s2_k": self.s2_k,
            "serper_total": self.serper_total,
            "fetch_cap": self.fetch_cap,
            "breadth_class": self.breadth_class,
            "rationale": self.rationale,
            "sources": dict(self.sources),
        }


def breadth_resolver_enabled() -> bool:
    """True iff the spine should consult the resolver (default OFF => byte-identical today)."""
    return os.getenv("PG_BREADTH_RESOLVER", "0").strip() in ("1", "true", "True")


def _config_path() -> Path:
    """Path to the breadth-class lookup table (LAW VI). Env-overridable for tests/fixtures."""
    override = os.getenv("PG_BREADTH_CLASSES_PATH", "").strip()
    if override:
        return Path(override)
    # repo_root/config/settings/breadth_classes.yaml — this file is
    # <repo>/src/polaris_graph/retrieval/breadth_resolver.py, so parents[3] is <repo>.
    return Path(__file__).resolve().parents[3] / "config" / "settings" / "breadth_classes.yaml"


def load_breadth_classes(path: Optional[Path] = None) -> dict[str, Any]:
    """Load the class lookup table. Fail-LOUD: a missing/broken config is a real error (LAW II),
    never a silent default — the resolver is only consulted when its flag is explicitly ON."""
    p = path or _config_path()
    with open(p, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if "classes" not in data or not isinstance(data["classes"], dict):
        raise ValueError(f"breadth_classes.yaml missing a 'classes' block: {p}")
    return data


def classify_breadth_directive(question: str) -> Optional[str]:
    """Deterministic breadth-directive parse (Design 7 D1 step 2). Returns 'WIDE' / 'NARROW'
    when the prompt carries an explicit breadth word, else None (=> fall through to structural).
    Pure regex over a fixed lexicon; the GLM confirm pass is an S0 concern, not this module's."""
    if not question:
        return None
    q = question.lower()
    # WIDE wins ties: an "exhaustive but brief" ask is a contradiction the widest reading serves
    # (§-1.3 — a generous ceiling is free; it only raises the cap, never forces padding).
    for term in _WIDE_LEXICON:
        if re.search(r"\b" + re.escape(term) + r"\b", q):
            return "WIDE"
    for term in _NARROW_LEXICON:
        if re.search(r"\b" + re.escape(term) + r"\b", q):
            return "NARROW"
    return None


def _structural_class(protocol: Optional[dict], facets: Any) -> tuple[str, str]:
    """Widen/narrow from the STRUCTURAL width of the ask (Design 7 D1 step 3): facet count, a
    multi-jurisdiction / long-window scope, a multilingual profile. Returns (class, reason).
    Conservative — only a clearly wide or clearly narrow structure moves off STANDARD."""
    reasons: list[str] = []
    n_facets = 0
    try:
        n_facets = len(facets) if facets is not None else 0
    except TypeError:
        n_facets = 0

    scope = _scope_from_protocol(protocol)
    juris = {
        f.get("facet_id", "")
        for f in scope.get("facets", [])
        if str(f.get("dimension", "")).startswith(("jurisdiction", "geography"))
    }
    wide_window = False
    uc = scope.get("user_constraints", {})
    ds, de = uc.get("date_start_year"), uc.get("date_end_year")
    if isinstance(ds, int) and isinstance(de, int) and (de - ds) >= 10:
        wide_window = True

    if n_facets >= 8:
        reasons.append(f"facet_count={n_facets}>=8")
        return "WIDE", "; ".join(reasons)
    if len(juris) >= 2:
        reasons.append(f"multi_jurisdiction={len(juris)}")
        return "WIDE", "; ".join(reasons)
    if wide_window:
        reasons.append(f"window_years={de - ds}>=10")
        return "WIDE", "; ".join(reasons)
    if n_facets and n_facets <= 2:
        reasons.append(f"facet_count={n_facets}<=2")
        return "NARROW", "; ".join(reasons)
    return "STANDARD", "default"


def _scope_from_protocol(protocol: Optional[dict]) -> dict[str, Any]:
    """Normalize the protocol's scope blocks into a flat dict (defensive — any missing key
    degrades to empty; the resolver never raises on a thin protocol)."""
    if not isinstance(protocol, dict):
        return {"facets": [], "user_constraints": {}}
    sc = protocol.get("scope_constraints") or {}
    uc = protocol.get("user_constraints") or {}
    facets = sc.get("facets", []) if isinstance(sc, dict) else []
    return {"facets": facets if isinstance(facets, list) else [], "user_constraints": uc if isinstance(uc, dict) else {}}


def _rc_breadth(run_config: Any) -> tuple[dict[str, Any], Optional[str]]:
    """Read the RunConfig breadth block, duck-typed against the master §1.1 contract.

    Accepts either the real RunConfig dataclass (``run_config.breadth`` with ``.query_budget``
    etc. and an optional ``.breadth_class``) OR a plain dict fixture ({"breadth": {...}}). Returns
    (explicit_numbers, requested_class): ``explicit_numbers`` maps knob->int for every field the
    user pinned to a number; ``requested_class`` is the parsed/panel breadth class or None.
    Everything is optional — an empty/None RunConfig yields ({}, None) and the resolver falls
    through to env + structural (foundation-core supplies the real object; here it may be absent)."""
    if run_config is None:
        return {}, None
    block = getattr(run_config, "breadth", None)
    if block is None and isinstance(run_config, dict):
        block = run_config.get("breadth")
    if block is None:
        return {}, None

    def _get(name: str) -> Any:
        if isinstance(block, dict):
            return block.get(name)
        return getattr(block, name, None)

    numbers: dict[str, Any] = {}
    for knob in _KNOBS:
        val = _get(knob)
        if val is None:
            continue
        try:
            numbers[knob] = int(val)
        except (TypeError, ValueError):
            logger.warning("[breadth_resolver] RunConfig.breadth.%s=%r not an int — ignored", knob, val)
    req_class = _get("breadth_class")
    if isinstance(req_class, str):
        req_class = req_class.strip().upper()
        if req_class not in _VALID_CLASSES:
            logger.warning("[breadth_resolver] RunConfig breadth_class=%r not in %s — ignored",
                           req_class, sorted(_VALID_CLASSES))
            req_class = None
    else:
        req_class = None
    return numbers, req_class


def _env_override(knob: str) -> Optional[int]:
    """The explicit per-knob env override, iff PRESENT in the environment (R9: env beats a code/
    class default but not a parsed/panel directive). Absent var => None => class default applies."""
    var = _ENV_OVERRIDE[knob]
    raw = os.environ.get(var)
    if raw is None or raw.strip() == "":
        return None
    try:
        return int(raw.strip())
    except ValueError:
        logger.warning("[breadth_resolver] env %s=%r not an int — ignored", var, raw)
        return None


def _abs_max(knob: str, config: dict[str, Any]) -> int:
    """The generous compute-safety ceiling for a knob (config row, env-overridable)."""
    env = os.environ.get(_ABS_MAX_ENV[knob])
    if env is not None and env.strip():
        try:
            return int(env.strip())
        except ValueError:
            logger.warning("[breadth_resolver] env %s=%r not an int — using config ceiling", _ABS_MAX_ENV[knob], env)
    ceilings = config.get("abs_max", {}) or {}
    return int(ceilings.get(knob, 10 ** 9))


def resolve_breadth(
    question: str,
    protocol: Optional[dict] = None,
    facets: Any = None,
    run_config: Any = None,
    *,
    config: Optional[dict[str, Any]] = None,
) -> BreadthPlan:
    """Resolve the retrieval budget for one run. Pure — no network / LLM / live_retriever.

    See the module docstring for the precedence. Returns a fully-populated :class:`BreadthPlan`
    with per-knob `sources` and a human-readable `rationale` for manifest disclosure."""
    cfg = config or load_breadth_classes()
    classes = cfg["classes"]

    rc_numbers, rc_class = _rc_breadth(run_config)

    # 1. Resolve the CLASS (used for every knob not pinned to an explicit number).
    directive_class = classify_breadth_directive(question)
    struct_class, struct_reason = _structural_class(protocol, facets)
    if rc_class:
        breadth_class, class_reason = rc_class, "RunConfig breadth_class"
    elif directive_class:
        breadth_class, class_reason = directive_class, f"prompt breadth directive -> {directive_class}"
    else:
        breadth_class, class_reason = struct_class, f"structural width ({struct_reason})"

    default_class = str(cfg.get("default_class", "STANDARD")).upper()
    if breadth_class not in classes:
        logger.warning("[breadth_resolver] class %r absent from config — using %s", breadth_class, default_class)
        breadth_class, class_reason = default_class, f"{class_reason} (fallback {default_class})"
    class_row = classes[breadth_class]

    # 2. Resolve each knob by precedence: RunConfig number > class (RunConfig-requested) > env > class.
    values: dict[str, int] = {}
    sources: dict[str, str] = {}
    clamp_notes: list[str] = []
    for knob in _KNOBS:
        ceiling = _abs_max(knob, cfg)
        if knob in rc_numbers:
            raw, src = rc_numbers[knob], "runconfig"
        elif rc_class:
            # A parsed/panel CLASS directive sizes the number and BEATS a merely-default env (R9).
            raw, src = int(class_row[knob]), "runconfig_class"
        else:
            env_val = _env_override(knob)
            if env_val is not None:
                raw, src = env_val, "env"
            else:
                raw, src = int(class_row[knob]), "class"
        val = max(0, int(raw))
        if val > ceiling:
            clamp_notes.append(f"{knob} {val}->{ceiling} (abs ceiling)")
            val = ceiling
        values[knob] = val
        sources[knob] = src

    rationale = (
        f"class={breadth_class} ({class_reason}); "
        f"query_budget={values['query_budget']}[{sources['query_budget']}] "
        f"serper_k={values['serper_k']}[{sources['serper_k']}] "
        f"s2_k={values['s2_k']}[{sources['s2_k']}] "
        f"serper_total={values['serper_total']}[{sources['serper_total']}] "
        f"fetch_cap={values['fetch_cap']}[{sources['fetch_cap']}]"
    )
    if clamp_notes:
        rationale += " | CLAMPED: " + "; ".join(clamp_notes)
        logger.warning("[breadth_resolver] clamped to abs ceilings: %s", "; ".join(clamp_notes))

    plan = BreadthPlan(
        query_budget=values["query_budget"],
        serper_k=values["serper_k"],
        s2_k=values["s2_k"],
        serper_total=values["serper_total"],
        fetch_cap=values["fetch_cap"],
        breadth_class=breadth_class,
        rationale=rationale,
        sources=sources,
    )
    logger.info("[activation] breadth_resolver: %s", rationale)
    return plan
