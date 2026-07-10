"""MASTER_EXECUTION_PLAN v2 §1 — the ONE RunConfig object + knob registry + precedence resolver.

WHAT THIS MODULE IS
    Full user-adjustability lives in ONE object. Every knob in the pipeline is user-controllable
    two ways — written in the natural-language prompt (parsed) OR set on an explicit control panel
    / CLI override file — and every stage reads its knobs through ONE resolver with ONE precedence
    rule. This is the WAVE-0 foundation every other section builds against (§7 dependency spine).

THE FOUR LAYERS AND THE ONE PRECEDENCE RULE (§1.3, ruling R9)
        code_default  <  env var (incl. the Gate-B slate)  <  prompt-parsed  <  panel / CLI
    ``RunConfig.get(knob_id)`` returns the winning value. An EMPTY RunConfig (no parsed, no panel)
    resolves every knob to ``os.getenv(env_var, code_default)`` coerced by the registry type — i.e.
    BYTE-IDENTICAL to today's behavior. That empty-RunConfig byte-identity is this package's bar.

LAW VI (zero hard-coding)
    The registry (``config/settings/run_config_knobs.yaml``) is the single source of knob truth.
    A stage NEVER hardcodes a threshold; it swaps its ``os.getenv`` for ``run_config.get(knob_id)``
    (per-stage migration is later-wave, surgical — §1.5). This module reads the registry; it writes
    no literal of its own except the resolver machinery.

§-1.3 DAY-WASTER BAN, ENFORCED AT THE SCHEMA (not by vigilance)
    ``dna_class`` must be one of {breadth_budget, scope_constraint, presentation, stage_tuning};
    the known number-forcing env vars are on an explicit denylist. A knob that would exist "to make
    a quality number hit X" cannot register. Breadth/quality EMERGE from honest weighted
    multi-attribution — they are never forced by a knob (§1.7).

NOT REGISTERED (operator-locked, NOT user knobs — §1.2 / §1.7 / §9.1.8)
    Model choice, max_tokens / reasoning-effort caps, and the faithfulness engine's thresholds are
    operator-locked, never RunConfig knobs. The foundation therefore sets NO model/token parameter,
    so "read the OpenRouter API, never guess a cap" has nothing to bite on in this layer.

THE RESUME VALIDITY MATRIX IS TWO-SIDED (§1.4)
    A resume loads checkpoint cpN and re-runs stages S(N+1)..S7. An adjustment to a knob is valid
    at ``resume_from=cpN`` iff the stage the knob shapes (``affects_stage``) still RE-RUNS, i.e.
    ``index(affects_stage) > index(resume_from)`` over the resume-stage order (the 7 checkpointed
    stages plus the terminal render stage S7, which re-runs on EVERY resume). ``affects_stage`` is
    the REAL stage each knob shapes — knob-dependent, not one anchor per block:
        breadth (s1_fetch)          → valid ONLY at cp0
        scope   (s2_select)         → valid at cp0, cp1                (scope-at-cp4 is a hard error)
        deliverable structure (s4)  → valid at cp0..cp3               ("resume from the outline step")
        deliverable tone/length (s5)→ valid at cp0..cp4               (compose re-runs)
        deliverable render (s7)     → valid at cp0..cp6               (render re-runs on every resume)
    This spans the plan's terse "deliverable valid from cp3+": different deliverable knobs are
    honorable at different — and later — resume points, up to render-only at cp6.

    NOTE (foundation → WP-4a): the exact per-knob deliverable ``affects_stage`` values are grounded
    in Design 3's consumer wiring (style block = compose §4-S5-FixC; reference-style + assembler
    ordering = render §4-S7) but that wiring is not yet built; the deliverable-knob assignments are
    finalized under the Codex+Fable gate in WP-4a. breadth (cp0) and scope (cp0/cp1) are stable.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from src.polaris_graph.generator import checkpoint_envelope as ce

# The canonical registry location (LAW VI: one file owns the knob truth).
_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY_PATH = _REPO_ROOT / "config" / "settings" / "run_config_knobs.yaml"

# The four allowed DNA classes. Any other value on a registry row = fail loud at load (§1.2).
ALLOWED_DNA_CLASSES = frozenset(
    {"breadth_budget", "scope_constraint", "presentation", "stage_tuning"}
)
ALLOWED_BLOCKS = frozenset({"breadth", "scope", "deliverable", "stages"})

# S7 ADJUDICATE+RENDER is terminal — it has NO checkpoint (D8 verdicts are never replayed, §-1.3)
# so it is absent from checkpoint_envelope.STAGE_ORDER. But render (assembler / reference-style /
# ordering) DOES re-run on every resume, so a render knob is honorable at any resume point. This
# resume-stage order appends the terminal render stage for the validity-matrix index ONLY (never a
# resumable-past checkpoint). ``affects_stage: s7_render`` marks a render-only deliverable knob.
STAGE_S7_RENDER = "s7_render"
RESUME_STAGE_ORDER: tuple[str, ...] = ce.STAGE_ORDER + (STAGE_S7_RENDER,)

# The precedence layer labels, weakest→strongest (recorded in KnobProvenance.source).
SOURCE_DEFAULT = "default"
SOURCE_ENV = "env"
SOURCE_PARSED = "parsed"
SOURCE_PANEL = "panel"

# §-1.3 BANNED anti-pattern: knobs that exist only to force a breadth/quality NUMBER. Any registry
# row whose env_var is one of these REFUSES to register — the day-waster ban made structural.
DAY_WASTER_ENV_DENYLIST = frozenset(
    {
        "PG_SPAN_PER_SOURCE_CITE_CAP",
        "PG_LEGACY_SECTION_BREADTH_TARGET",
        "PG_BREADTH_CANARY_MIN",
    }
)

# Bool-string OFF tokens (matches the polaris intake-extractor kill-switch convention).
_OFF_TOKENS = frozenset({"", "0", "false", "no", "off"})


class RunConfigError(RuntimeError):
    """Raised on a malformed registry, an unknown knob, or an invalid resume adjustment.

    FAIL LOUD (LAW II): a bad knob config or an illegal adjustment must NEVER silently fall back
    to a default — it would mask a real misconfiguration on a paid run.
    """


def coerce(value: Any, type_name: str) -> Any:
    """Coerce a raw layer value (env string, parsed string, or already-typed panel JSON) to the
    knob's registry type. A malformed value fails loud rather than silently defaulting."""
    if type_name == "str":
        return "" if value is None else str(value)
    if type_name == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        return str(value).strip().lower() not in _OFF_TOKENS
    if type_name == "int":
        if isinstance(value, bool):  # guard: bool is an int subclass; keep them distinct
            return int(value)
        if isinstance(value, int):
            return value
        try:
            return int(str(value).strip())
        except (TypeError, ValueError) as exc:
            raise RunConfigError(f"cannot coerce {value!r} to int") from exc
    if type_name == "float":
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise RunConfigError(f"cannot coerce {value!r} to float") from exc
    if type_name in ("list", "json"):
        if isinstance(value, (list, dict)):
            return value
        try:
            return json.loads(value)
        except (TypeError, ValueError) as exc:
            raise RunConfigError(f"cannot coerce {value!r} to {type_name}") from exc
    raise RunConfigError(f"unknown knob type {type_name!r}")


@dataclass(frozen=True)
class KnobSpec:
    """One registry row: everything the resolver needs to know about a knob."""

    id: str
    block: str
    dna_class: str
    type: str
    env_var: str
    code_default: Any
    affects_stage: str
    status: str = "planned"          # existing (live read site) | planned (feature not yet built)
    prompt_parseable: bool = False
    panel_widget: str | None = None
    read_site: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)  # choices / abs_max_env / band / note / ...

    def coerced_default(self) -> Any:
        return coerce(self.code_default, self.type)


@dataclass(frozen=True)
class KnobProvenance:
    """Per-knob resolution record surfaced in cp0 + the Methods disclosure (§1.3)."""

    value: Any
    source: str            # one of SOURCE_*
    span: str | None = None  # verbatim prompt trigger for a parsed knob, else None

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "source": self.source, "span": self.span}


class RunConfigRegistry:
    """The loaded, validated knob registry — the single source of knob truth (§1.2)."""

    def __init__(self, version: int, knobs: dict[str, KnobSpec], block_dna_class: dict[str, str]):
        self.version = version
        self._knobs = knobs
        self._block_dna_class = block_dna_class

    @classmethod
    def load(cls, path: str | os.PathLike[str] | None = None) -> "RunConfigRegistry":
        path = Path(path) if path is not None else DEFAULT_REGISTRY_PATH
        if not path.is_file():
            raise RunConfigError(f"knob registry not found at {path}")
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        version = int(raw.get("registry_version", 0))
        block_dna_class = dict(raw.get("block_dna_class") or {})
        # Every block must declare exactly one dna_class, and it must be an allowed class.
        if set(block_dna_class) != set(ALLOWED_BLOCKS):
            raise RunConfigError(
                f"block_dna_class must cover exactly {sorted(ALLOWED_BLOCKS)}; got "
                f"{sorted(block_dna_class)}"
            )
        for block, dna in block_dna_class.items():
            if dna not in ALLOWED_DNA_CLASSES:
                raise RunConfigError(
                    f"block {block!r} maps to dna_class {dna!r} not in {sorted(ALLOWED_DNA_CLASSES)}"
                )
        knobs: dict[str, KnobSpec] = {}
        for row in raw.get("knobs") or []:
            spec = cls._parse_row(row, block_dna_class)
            if spec.id in knobs:
                raise RunConfigError(f"duplicate knob id {spec.id!r} in the registry")
            knobs[spec.id] = spec
        return cls(version=version, knobs=knobs, block_dna_class=block_dna_class)

    @staticmethod
    def _parse_row(row: dict[str, Any], block_dna_class: dict[str, str]) -> KnobSpec:
        try:
            knob_id = str(row["id"])
            block = str(row["block"])
            env_var = str(row["env_var"])
            type_name = str(row["type"])
            affects_stage = str(row["affects_stage"])
        except KeyError as exc:
            raise RunConfigError(f"registry row missing required key {exc} in {row!r}") from exc
        if block not in ALLOWED_BLOCKS:
            raise RunConfigError(f"knob {knob_id!r} block {block!r} not in {sorted(ALLOWED_BLOCKS)}")
        # dna_class is DERIVED from the block (block<->dna_class is 1:1) so a row cannot smuggle a
        # bad class or a class inconsistent with its block. §-1.3 enforced structurally.
        dna_class = block_dna_class[block]
        if env_var in DAY_WASTER_ENV_DENYLIST:
            raise RunConfigError(
                f"knob {knob_id!r} env_var {env_var!r} is a §-1.3 DAY-WASTER (a number-forcing "
                "cap/target/thinner) and is REFUSED at the registry. Breadth/quality EMERGE from "
                "honest weighted multi-attribution; they are never forced by a knob."
            )
        if affects_stage not in RESUME_STAGE_ORDER:
            raise RunConfigError(
                f"knob {knob_id!r} affects_stage {affects_stage!r} is not a section stage "
                f"(expected one of {list(RESUME_STAGE_ORDER)})"
            )
        if type_name not in ("str", "bool", "int", "float", "list", "json"):
            raise RunConfigError(f"knob {knob_id!r} has unknown type {type_name!r}")
        known = {"id", "block", "type", "env_var", "code_default", "affects_stage",
                 "status", "prompt_parseable", "panel_widget", "read_site"}
        extra = {k: v for k, v in row.items() if k not in known}
        return KnobSpec(
            id=knob_id,
            block=block,
            dna_class=dna_class,
            type=type_name,
            env_var=env_var,
            code_default=row.get("code_default"),
            affects_stage=affects_stage,
            status=str(row.get("status", "planned")),
            prompt_parseable=bool(row.get("prompt_parseable", False)),
            panel_widget=row.get("panel_widget"),
            read_site=row.get("read_site"),
            extra=extra,
        )

    def spec(self, knob_id: str) -> KnobSpec:
        try:
            return self._knobs[knob_id]
        except KeyError as exc:
            raise RunConfigError(f"unknown knob {knob_id!r} (not in the registry)") from exc

    def ids(self) -> list[str]:
        return list(self._knobs)

    def block_ids(self, block: str) -> list[str]:
        return [k for k, s in self._knobs.items() if s.block == block]

    def earliest_resume_checkpoint(self, knob_id: str) -> str:
        """The checkpoint immediately upstream of the stage the knob shapes — the LATEST resume
        entry at which an adjustment for this knob is still honorable in full (disclosure vocab).
        A render-only knob (affects s7_render) clamps to the last checkpoint (cp6): render re-runs
        on every resume, so it is honorable even resuming at cp6."""
        spec = self.spec(knob_id)
        idx = RESUME_STAGE_ORDER.index(spec.affects_stage)
        if idx == 0:
            return ce.STAGE_ORDER[0]
        return ce.STAGE_ORDER[min(idx - 1, len(ce.STAGE_ORDER) - 1)]


# ── stage normalization (cpN alias → canonical stage id), local so block-1 stays untouched ──────
_CP_TO_STAGE: dict[str, str] = {}
for _stage, _fname in ce.STAGE_FILENAMES.items():
    _CP_TO_STAGE[_stage] = _stage
    _CP_TO_STAGE[_fname.split("_", 1)[0]] = _stage          # "cp4"
    _CP_TO_STAGE[_fname[: -len(".json")]] = _stage           # "cp4_outline_snapshot"


def normalize_stage(token: str) -> str:
    key = (token or "").strip().lower()
    if key in _CP_TO_STAGE:
        return _CP_TO_STAGE[key]
    raise RunConfigError(
        f"resume stage token {token!r} does not name a checkpoint "
        f"(expected a stage id or a cpN alias in {sorted(set(ce.STAGE_FILENAMES))})"
    )


@dataclass
class RunConfig:
    """The fully-resolved run configuration: one value + one provenance per registered knob, plus
    an optional typed structured sub-object per block (DeliverableSpec / UserConstraints+
    ScopeConstraints / BreadthPlan — populated by later-wave extractors; the slot exists now)."""

    registry: RunConfigRegistry
    resolved: dict[str, Any]
    provenance: dict[str, KnobProvenance]
    structured: dict[str, Any] = field(default_factory=lambda: {b: None for b in ALLOWED_BLOCKS})

    def get(self, knob_id: str) -> Any:
        """Resolve a knob by precedence panel/CLI > parsed > env > code_default (§1.3)."""
        if knob_id not in self.resolved:
            # Registered but never resolved (a partially-built config) — resolve on demand.
            spec = self.registry.spec(knob_id)
            return spec.coerced_default()
        return self.resolved[knob_id]

    def source(self, knob_id: str) -> str:
        return self.provenance[knob_id].source

    def block_values(self, block: str) -> dict[str, Any]:
        if block not in ALLOWED_BLOCKS:
            raise RunConfigError(f"unknown block {block!r}")
        return {k: self.resolved[k] for k in self.registry.block_ids(block)}

    def non_default_knobs(self) -> dict[str, KnobProvenance]:
        """Every knob whose winning layer is NOT the code default — the Methods disclosure set."""
        return {k: p for k, p in self.provenance.items() if p.source != SOURCE_DEFAULT}

    def values_only(self) -> dict[str, Any]:
        """The resolved (knob_id -> value) map, provenance stripped — the identity of the config."""
        return dict(sorted(self.resolved.items()))

    def sha(self) -> str:
        """Deterministic content hash of the resolved VALUES only (sorted). Pins cp0 + every
        downstream checkpoint's ``run_config_sha`` (resume refuses on drift for run stages)."""
        canonical = json.dumps(self.values_only(), sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def assert_adjustment_valid(self, knob_id: str, resume_from: str) -> None:
        """FAIL LOUD if adjusting ``knob_id`` on a resume entering at ``resume_from`` is illegal.

        Valid iff the stage the knob shapes still re-runs: index(affects_stage) > index(resume).
        Reproduces the three plan anchors (breadth cp0-only; scope cp0/cp1; deliverable cp0..cp3).
        """
        spec = self.registry.spec(knob_id)
        entry_stage = normalize_stage(resume_from)   # a real checkpoint stage (S7 is never a resume entry)
        affect_idx = RESUME_STAGE_ORDER.index(spec.affects_stage)
        entry_idx = RESUME_STAGE_ORDER.index(entry_stage)
        if affect_idx <= entry_idx:
            latest = self.registry.earliest_resume_checkpoint(knob_id)
            raise RunConfigError(
                f"resume adjustment REJECTED: knob {knob_id!r} shapes stage {spec.affects_stage!r} "
                f"which does NOT re-run when resuming from {entry_stage!r}; an adjustment can never "
                f"mutate a frozen upstream stage. Resume from {latest!r} or earlier to change it."
            )


# ── population: merge the four layers into one resolved RunConfig ───────────────────────────────

def build_run_config(
    *,
    registry: RunConfigRegistry | None = None,
    env: dict[str, str] | None = None,
    parsed: dict[str, Any] | None = None,
    panel: dict[str, Any] | None = None,
) -> RunConfig:
    """Merge the four layers into a fully-resolved RunConfig.

    ``env`` defaults to ``os.environ``; ``parsed`` maps knob_id -> value OR (value, span); ``panel``
    maps knob_id -> value. Unknown knob ids in ``parsed``/``panel`` fail loud (no silent drop).
    Precedence per knob: panel > parsed > env-var-if-set > code_default (§1.3, R9).
    """
    registry = registry or default_registry()
    env = dict(os.environ if env is None else env)
    parsed = dict(parsed or {})
    panel = dict(panel or {})
    for surface_name, surface in (("parsed", parsed), ("panel", panel)):
        for knob_id in surface:
            if knob_id not in registry.ids():
                raise RunConfigError(f"{surface_name} names unknown knob {knob_id!r}")

    resolved: dict[str, Any] = {}
    provenance: dict[str, KnobProvenance] = {}
    for knob_id in registry.ids():
        spec = registry.spec(knob_id)
        if knob_id in panel:
            value = coerce(panel[knob_id], spec.type)
            provenance[knob_id] = KnobProvenance(value=value, source=SOURCE_PANEL)
        elif knob_id in parsed:
            raw, span = _split_parsed(parsed[knob_id])
            value = coerce(raw, spec.type)
            provenance[knob_id] = KnobProvenance(value=value, source=SOURCE_PARSED, span=span)
        elif env.get(spec.env_var) is not None:
            value = coerce(env[spec.env_var], spec.type)
            provenance[knob_id] = KnobProvenance(value=value, source=SOURCE_ENV)
        else:
            value = spec.coerced_default()
            provenance[knob_id] = KnobProvenance(value=value, source=SOURCE_DEFAULT)
        resolved[knob_id] = value
    return RunConfig(registry=registry, resolved=resolved, provenance=provenance)


def _split_parsed(entry: Any) -> tuple[Any, str | None]:
    """Accept a parsed knob as a bare value or a (value, span) tuple/list — the span is the
    verbatim prompt trigger recorded for anti-invention disclosure (§1.3)."""
    if isinstance(entry, (tuple, list)) and len(entry) == 2:
        return entry[0], (None if entry[1] is None else str(entry[1]))
    return entry, None


_DEFAULT_REGISTRY: RunConfigRegistry | None = None


def default_registry() -> RunConfigRegistry:
    """Process-wide singleton for the canonical registry (loaded once)."""
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = RunConfigRegistry.load()
    return _DEFAULT_REGISTRY


# ── --run-config CLI intake (the panel/CLI override surface, §1.3 surface b) ─────────────────────

def load_overrides_file(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Read a RunConfig-overrides document (the control-panel / CLI override file).

    Shape: ``{"panel": {knob_id: value, ...}, "parsed": {knob_id: [value, span], ...}}`` — or a
    bare ``{knob_id: value}`` map, treated as the panel layer. FAIL LOUD (LAW II) on a missing or
    malformed file; never silently ignore an override the operator asked for.
    """
    path = Path(path)
    if not path.is_file():
        raise RunConfigError(f"--run-config override file not found at {path}")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RunConfigError(f"--run-config override file at {path} is unreadable/malformed: {exc}") from exc
    if not isinstance(doc, dict):
        raise RunConfigError(f"--run-config override file at {path} must be a JSON object")
    if "panel" in doc or "parsed" in doc:
        return {"panel": dict(doc.get("panel") or {}), "parsed": dict(doc.get("parsed") or {})}
    return {"panel": dict(doc), "parsed": {}}


# ── cp0 writer — the pinned RunConfig checkpoint other sections read (§1.4 / §5) ─────────────────

def cp0_payload(run_config: RunConfig, question: str) -> dict[str, Any]:
    """The FROZEN cp0 payload contract (DATA only — no verdict at any depth).

    Shape (what every downstream section + the resume resolver reads):
        {question, question_sha, run_config_sha, registry_version,
         blocks:{breadth,scope,deliverable,stages}: {knob_id: value},
         structured:{breadth,scope,deliverable,stages}: null|{...},
         provenance:{knob_id: {value, source, span}}}
    """
    return {
        "question": question,
        "question_sha": ce.question_sha(question),
        "run_config_sha": run_config.sha(),
        "registry_version": run_config.registry.version,
        "blocks": {block: run_config.block_values(block) for block in sorted(ALLOWED_BLOCKS)},
        "structured": {block: run_config.structured.get(block) for block in sorted(ALLOWED_BLOCKS)},
        "provenance": {k: p.to_dict() for k, p in sorted(run_config.provenance.items())},
    }


def write_cp0(
    run_dir: str | os.PathLike[str],
    run_config: RunConfig,
    *,
    run_id: str,
    slug: str,
    domain: str,
    question: str,
    flag_slate: dict[str, str] | None = None,
    created_utc: str | None = None,
) -> tuple[Path, str]:
    """Write ``cp0_run_config.json`` through the shared checkpoint envelope and index it.

    cp0 is the hash-chain ROOT (no upstream). It pins ``run_config_sha`` so every downstream
    checkpoint (and every resume) can refuse on RunConfig drift for stages already run (§1.4).
    Returns (written_path, content_sha256).
    """
    return ce.save_checkpoint(
        Path(run_dir),
        stage=ce.STAGE_S0_INTAKE,
        run_id=run_id,
        slug=slug,
        domain=domain,
        question=question,
        payload=cp0_payload(run_config, question),
        upstream_stage=None,                 # cp0 is the chain root
        flag_slate=flag_slate,
        run_config_sha=run_config.sha(),
        created_utc=created_utc,
    )
