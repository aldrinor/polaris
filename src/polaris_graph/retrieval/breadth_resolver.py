"""S1.b breadth resolver — size the retrieval budget from the user ask, bounded by env ceilings.

Design 7 D1 (SIZING side) + master execution plan v2 §4 (S1.b) + ruling R11. The breadth
DIRECTIVE parse ("comprehensive" -> WIDE) is an S0 extractor (R11) and is NOT done here; this
module only SIZES a run from an already-resolved ``breadth_class`` + the structural width of the
ask. It is PURE: no network, no LLM, no import of ``live_retriever``.

Precedence, per master §1.3 + ruling R9 (highest wins):
    control-panel / CLI  >  prompt-parsed  >  env var  >  breadth-class table  >  code default
When a ``RunConfig`` object is present it has ALREADY applied panel>parsed>env for each knob
(master §1.5 ``run_config.get(knob_id)``); the resolver trusts that value. When RunConfig is
absent (today, until WAVE-0 lands ``run_config.py``) the resolver reads the explicit env var,
then the class-table value, then the historical code default — byte-identical to today when the
resolver flag is OFF (the spine keeps its raw env reads; this module is never called).

Wiring: one flag ``PG_BREADTH_RESOLVER`` (default OFF). Spine seam
``scripts/run_honest_sweep_r3.py:9734-9736`` consults the resolver for ``_max_serper`` /
``_max_s2`` / ``_fetch_cap``; the qgen seam passes ``max_queries=plan.query_budget`` into
``_run_fs_researcher_retrieval`` (``run_honest_sweep_r3.py:10436``). The resolved plan is
DISCLOSED in the manifest / run log (auditable). §-1.3: the budget is a compute-safety CEILING
sized to the requirement, never a target the loop pads to — issued counts still EMERGE from
facets + dedup + the wall + checklist saturation; the widen lanes still raise it additively.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("polaris_graph.breadth_resolver")

# The historical code defaults — the byte-identical OFF values (Design 7 §3 bar #1: 35/12/12/200).
# These are the ULTIMATE fallback if the class table is missing/broken (fail-open); every real run
# resolves through the class table or an explicit env/RunConfig value first.
_CODE_DEFAULTS: dict[str, int] = {
    "query_budget": 35,
    "serper_k": 12,
    "s2_k": 12,
    "fetch_cap": 200,
}

# knob_id -> the legacy env var that pins it (LAW VI: the resolver honors an explicit env override).
_KNOB_ENV: dict[str, str] = {
    "query_budget": "PG_QGEN_FS_RESEARCHER_MAX_QUERIES",
    "serper_k": "PG_SWEEP_MAX_SERPER",
    "s2_k": "PG_SWEEP_MAX_S2",
    "serper_total": "PG_SERPER_TOTAL_PER_QUERY",
    "fetch_cap": "PG_SWEEP_FETCH_CAP",
}

_CLASSES_YAML_REL = "config/settings/breadth_classes.yaml"
_DEFAULT_CLASS = "STANDARD"
_ON_VALUES = ("1", "true", "on", "yes")


def breadth_resolver_enabled() -> bool:
    """True iff the breadth resolver is flag-enabled. Default OFF => the spine keeps its raw env
    reads (byte-identical) and this module is never called."""
    return os.getenv("PG_BREADTH_RESOLVER", "0").strip().lower() in _ON_VALUES


@dataclass
class KnobResolution:
    """One resolved breadth knob + WHERE its value came from (disclosed in the manifest)."""

    value: int
    source: str          # run_config | parsed | env | class:<CLASS> | code_default (+ '+clamped')
    env_var: str

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "source": self.source, "env_var": self.env_var}


@dataclass
class BreadthPlan:
    """The sized retrieval budget for one run. ``serper_total`` is optional (None => the retriever
    keeps its own env default, byte-identical); the spine wires only query_budget/serper_k/s2_k/
    fetch_cap (Design 7 D1 wiring). Every value carries provenance for disclosure."""

    query_budget: int
    serper_k: int
    s2_k: int
    fetch_cap: int
    serper_total: Optional[int]
    breadth_class: str
    class_source: str    # run_config | env | structural | default
    rationale: str
    resolutions: dict[str, KnobResolution] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_budget": self.query_budget,
            "serper_k": self.serper_k,
            "s2_k": self.s2_k,
            "fetch_cap": self.fetch_cap,
            "serper_total": self.serper_total,
            "breadth_class": self.breadth_class,
            "class_source": self.class_source,
            "rationale": self.rationale,
            "resolutions": {k: v.to_dict() for k, v in self.resolutions.items()},
        }


def _repo_root() -> Path:
    # src/polaris_graph/retrieval/breadth_resolver.py -> repo root is parents[3].
    return Path(__file__).resolve().parents[3]


def _load_classes() -> dict[str, Any]:
    """Load the breadth-class table (LAW VI — no magic numbers in code). Fail-open: a missing or
    malformed file yields an empty table, and the resolver then falls to explicit env / code
    defaults (never a hard crash on a paid run)."""
    try:
        import yaml  # noqa: PLC0415 — lazy so a non-YAML unit path never imports it
        path = _repo_root() / _CLASSES_YAML_REL
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(data, dict):
            return data
    except Exception as exc:  # noqa: BLE001 — fail-open to env/code defaults
        logger.warning("[breadth_resolver] class table unavailable (%s); using env/code defaults", exc)
    return {}


def _rc_get(run_config: Any, knob_id: str) -> Optional[int]:
    """Duck-typed read of one knob from a RunConfig (WAVE-0 ``run_config.py``, not yet built) OR a
    plain dict. Returns an int or None. Accepts a bare int, a ``{'value': N, ...}`` rich-knob
    mapping, or an object with a ``.value`` attribute. Any fault / non-numeric => None (fail-open)."""
    if run_config is None:
        return None
    try:
        getter = getattr(run_config, "get", None)
        raw = getter(knob_id) if callable(getter) else None
        if raw is None:
            return None
        if isinstance(raw, dict):
            raw = raw.get("value")
        elif hasattr(raw, "value"):
            raw = raw.value
        if raw is None:
            return None
        return int(raw)
    except Exception:  # noqa: BLE001 — a malformed RunConfig never breaks sizing
        return None


def _env_int(env_var: str) -> Optional[int]:
    """An EXPLICITLY-set integer env var, else None. Empty / unparseable => None (fall through)."""
    raw = os.getenv(env_var)
    if raw is None or raw.strip() == "":
        return None
    try:
        return int(raw.strip())
    except ValueError:
        logger.warning("[breadth_resolver] %s=%r is not an int; ignoring", env_var, raw)
        return None


def _abs_ceiling(env_var: str) -> Optional[int]:
    """The compute-safety absolute ceiling for a knob (``PG_<ENV>_ABS_MAX``). Default None (no
    ceiling). A user/panel ask above the ceiling clamps LOUDLY (§1.3 safety ceilings)."""
    return _env_int(env_var + "_ABS_MAX")


def _resolve_knob(
    knob_id: str,
    run_config: Any,
    class_row: dict[str, Any],
    breadth_class: str,
    code_default: Optional[int],
) -> Optional[KnobResolution]:
    """Resolve ONE knob by precedence: RunConfig (already panel>parsed>env) > explicit env >
    class-table value > code default. Then clamp to the abs ceiling (loud). ``code_default=None``
    with no class/env/RunConfig value => the knob is unset (None) and the caller leaves the
    downstream default in place (used for the optional ``serper_total``)."""
    env_var = _KNOB_ENV[knob_id]
    value: Optional[int] = None
    source = ""

    rc = _rc_get(run_config, knob_id)
    if rc is not None:
        value, source = rc, "run_config"
    else:
        ev = _env_int(env_var)
        if ev is not None:
            value, source = ev, "env"
        else:
            cv = class_row.get(knob_id)
            if cv is not None:
                try:
                    value, source = int(cv), f"class:{breadth_class}"
                except (TypeError, ValueError):
                    value = None
            if value is None and code_default is not None:
                value, source = int(code_default), "code_default"

    if value is None:
        return None

    ceiling = _abs_ceiling(env_var)
    if ceiling is not None and value > ceiling:
        logger.warning(
            "[breadth_resolver] %s=%d exceeds abs ceiling %s=%d — clamping LOUDLY (§1.3 safety ceiling)",
            knob_id, value, env_var + "_ABS_MAX", ceiling,
        )
        value, source = ceiling, source + "+clamped"

    return KnobResolution(value=value, source=source, env_var=env_var)


def _structural_class(facets: Any, protocol: Any, table: dict[str, Any]) -> Optional[str]:
    """Widen/narrow the class from the STRUCTURAL width of the ask (facet count + date-window
    span). Pure + deterministic. Returns None when there is no clear signal (=> caller uses the
    table default). §-1.3: this is SIZING from the requirement's shape, never a breadth target."""
    sw = table.get("structural_width") or {}
    try:
        narrow_facets = int(sw.get("narrow_facets", 3))
        wide_facets = int(sw.get("wide_facets", 8))
        wide_window_years = int(sw.get("wide_window_years", 10))
    except (TypeError, ValueError):
        narrow_facets, wide_facets, wide_window_years = 3, 8, 10

    n_facets: Optional[int] = None
    try:
        if facets is not None:
            n_facets = len(facets)
    except TypeError:
        n_facets = None

    # A wide publication window is a WIDE signal even with few facets.
    window_years: Optional[int] = None
    try:
        uc = (protocol or {}).get("user_constraints") if isinstance(protocol, dict) else None
        if isinstance(uc, dict):
            ys, ye = uc.get("date_start_year"), uc.get("date_end_year")
            if isinstance(ys, int) and isinstance(ye, int) and ye >= ys:
                window_years = ye - ys
    except Exception:  # noqa: BLE001 — protocol shape is best-effort
        window_years = None

    if window_years is not None and window_years > wide_window_years:
        return "WIDE"
    if n_facets is None:
        return None
    if n_facets >= wide_facets:
        return "WIDE"
    if n_facets <= narrow_facets:
        return "NARROW"
    return "STANDARD"


def _resolve_class(run_config: Any, facets: Any, protocol: Any, table: dict[str, Any]) -> tuple[str, str]:
    """Choose the breadth class: RunConfig (S0-parsed directive / panel) > ``PG_BREADTH_CLASS`` env
    > structural width > table default. Returns (CLASS, source)."""
    rc = _rc_get_class(run_config)
    if rc:
        return rc, "run_config"
    env = os.getenv("PG_BREADTH_CLASS")
    if env and env.strip():
        return env.strip().upper(), "env"
    cls = _structural_class(facets, protocol, table)
    if cls:
        return cls, "structural"
    return str(table.get("default_class", _DEFAULT_CLASS)).upper(), "default"


def _rc_get_class(run_config: Any) -> Optional[str]:
    """Read a resolved ``breadth_class`` string from a RunConfig / dict (duck-typed). None on any
    fault or absence (fail-open to env / structural)."""
    if run_config is None:
        return None
    try:
        getter = getattr(run_config, "get", None)
        raw = getter("breadth_class") if callable(getter) else None
        if isinstance(raw, dict):
            raw = raw.get("value")
        elif raw is not None and hasattr(raw, "value"):
            raw = raw.value
        if raw:
            return str(raw).strip().upper()
    except Exception:  # noqa: BLE001
        return None
    return None


def resolve_breadth(
    question: str,
    protocol: Any = None,
    facets: Any = None,
    run_config: Any = None,
) -> BreadthPlan:
    """Size the retrieval budget for one run. Pure — no network, no LLM. Returns a fully-resolved
    :class:`BreadthPlan` with per-knob provenance for manifest disclosure.

    ``question`` is accepted for signature-parity with Design 7 D1 (and future S0-side sizing) but
    the sizing here reads only ``run_config`` / env / the class table / structural width — never the
    LLM directive parse, which is S0's job (R11)."""
    table = _load_classes()
    breadth_class, class_source = _resolve_class(run_config, facets, protocol, table)
    classes = table.get("classes") if isinstance(table, dict) else None
    class_row = (classes or {}).get(breadth_class) if isinstance(classes, dict) else None
    if not isinstance(class_row, dict):
        class_row = {}

    resolutions: dict[str, KnobResolution] = {}
    for knob_id in ("query_budget", "serper_k", "s2_k", "fetch_cap"):
        res = _resolve_knob(knob_id, run_config, class_row, breadth_class, _CODE_DEFAULTS[knob_id])
        # code_default is always set for these four, so res is never None here.
        resolutions[knob_id] = res  # type: ignore[assignment]

    serper_total_res = _resolve_knob("serper_total", run_config, class_row, breadth_class, None)
    if serper_total_res is not None:
        resolutions["serper_total"] = serper_total_res

    rationale = (
        f"class={breadth_class} (source={class_source}); "
        + ", ".join(f"{k}={r.value}[{r.source}]" for k, r in resolutions.items())
    )

    plan = BreadthPlan(
        query_budget=resolutions["query_budget"].value,
        serper_k=resolutions["serper_k"].value,
        s2_k=resolutions["s2_k"].value,
        fetch_cap=resolutions["fetch_cap"].value,
        serper_total=serper_total_res.value if serper_total_res is not None else None,
        breadth_class=breadth_class,
        class_source=class_source,
        rationale=rationale,
        resolutions=resolutions,
    )
    logger.info("[activation] breadth_resolver: %s", plan.rationale)
    return plan
