"""RunConfig — the one control surface for full user-adjustability (WAVE 0, WP-0b).

MASTER_EXECUTION_PLAN v2 §1 THE RUNCONFIG PRINCIPLE. Every knob in the pipeline is
user-controllable TWO ways: (a) written in the natural-language PROMPT and parsed,
(b) set explicitly on a CONTROL PANEL / CLI override. This module is the single
object + the single resolver that unify both surfaces under one precedence rule.

Precedence (§1.3, ruling R9), highest wins:

    PANEL / CLI explicit  >  PROMPT-parsed  >  ENV (incl. the Gate-B slate)  >  CODE-DEFAULT

Design invariants this module enforces:
  * The knob REGISTRY (config/settings/run_config_knobs.yaml) is the SINGLE SOURCE OF
    KNOB TRUTH. This module holds ZERO knob-specific literals — every code-default,
    env alias, type, and validity checkpoint comes from the registry DATA (LAW VI).
  * ZERO raw env reads for registered knobs downstream: a stage calls
    ``run_config.get(cfg, knob_id)`` and never ``os.getenv`` for a registered knob.
    The resolver is the ONE place the env layer is read, at CALL TIME (LAW VI).
  * Every resolved knob carries PROVENANCE: {value, source, span} where source is one
    of ``panel | prompt | env | default | adjust`` — a resolved value can NEVER be a
    mid-pipeline hardcode; it always traces to one of those four layers.
  * §1.7 EXCLUSIONS enforced at registry load: no model-selection knob, no
    max_tokens / reasoning-effort knob (those are the §9.1.8 operator lock — read real
    OpenRouter caps, never a user knob), no knob that weakens the faithfulness engine,
    no §-1.3 day-waster "make-a-number-hit-X" knob.
  * An EMPTY RunConfig (no panel, no prompt) resolves every knob to its env value if
    set else the registry code-default == the code's own default => byte-identical to
    today (§1.5).

One vocabulary for fresh runs AND resume adjustments (§1.4): a resume ``--adjust`` is a
RunConfig delta in the SAME shape a fresh-run parse produces; the ``adjust`` provenance
source ranks with panel (explicit override). Validity of an adjustment at a given resume
checkpoint keys on each knob's ``earliest_resume_checkpoint`` registry field.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Registry location + checkpoint ordering (both are DATA, not per-knob logic).
# ---------------------------------------------------------------------------

# The knob registry lives beside the other settings YAMLs. Overridable for tests via
# PG_RUN_CONFIG_KNOBS (LAW VI: config path is not hardcoded to one immovable literal).
_REGISTRY_ENV = "PG_RUN_CONFIG_KNOBS"
_DEFAULT_REGISTRY_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "settings" / "run_config_knobs.yaml"
)

# The 7 section checkpoints, in pipeline order. Index i == cp{i}. Used to evaluate the
# resume validity matrix (an adjustment is valid iff entry_index <= erc_index).
CHECKPOINT_ORDER: tuple[str, ...] = ("cp0", "cp1", "cp2", "cp3", "cp4", "cp5", "cp6")

# Legal blocks and dna_classes (schema guard). §1.1 blocks; §1.2 dna_class taxonomy.
_LEGAL_BLOCKS = frozenset({"breadth", "scope", "deliverable", "stages"})
_LEGAL_DNA_CLASSES = frozenset(
    {"breadth_budget", "scope_constraint", "presentation", "stage_tuning"}
)

# Provenance sources, in precedence order (highest first). ``adjust`` is a resume-time
# explicit override; it ranks WITH panel (both are explicit user overrides).
SOURCE_PANEL = "panel"
SOURCE_ADJUST = "adjust"
SOURCE_PROMPT = "prompt"
SOURCE_ENV = "env"
SOURCE_DEFAULT = "default"
_LEGAL_SOURCES = frozenset(
    {SOURCE_PANEL, SOURCE_ADJUST, SOURCE_PROMPT, SOURCE_ENV, SOURCE_DEFAULT}
)

# §-1.3 DAY-WASTER DENYLIST — knob ids that exist only to force a breadth/quality number
# to a target. Registering any of these is a HARD ERROR (structural enforcement of the
# operator's day-waster ban, §-1.3.1). NOT an exhaustive semantic check; the dna_class
# review is the primary guard, this catches the known-bad ids by name.
_DAY_WASTER_DENYLIST = frozenset(
    {
        "pg_span_per_source_cite_cap",
        "pg_legacy_section_breadth_target",
        "pg_breadth_canary_min",
        "span_per_source_cite_cap",
        "legacy_section_breadth_target",
        "breadth_canary_min",
    }
)

# §1.7 / §9.1.8: env aliases that name a model or a token/reasoning budget may NEVER be a
# registered knob. Matched case-insensitively against a knob's env_var.
_FORBIDDEN_ENV_PATTERNS = (
    re.compile(r"_MODEL$", re.IGNORECASE),
    re.compile(r"MODEL", re.IGNORECASE),
    re.compile(r"MAX_TOKENS", re.IGNORECASE),
    re.compile(r"REASONING", re.IGNORECASE),
)


class RunConfigError(RuntimeError):
    """A registry / resolver / adjustment error. FAIL LOUD (LAW II) — never silent."""


# ---------------------------------------------------------------------------
# The registry: one KnobSpec per row, loaded + validated once.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KnobSpec:
    """One registered knob (a row of run_config_knobs.yaml). Immutable DATA."""

    id: str
    block: str
    type: str
    code_default: Any
    env_var: str | None
    earliest_resume_checkpoint: str
    prompt_parseable: bool
    panel_widget: str
    dna_class: str
    enum: tuple[str, ...] | None = None

    @property
    def erc_index(self) -> int:
        return CHECKPOINT_ORDER.index(self.earliest_resume_checkpoint)


def registry_path() -> Path:
    override = os.getenv(_REGISTRY_ENV)
    return Path(override) if override else _DEFAULT_REGISTRY_PATH


def load_registry(path: Path | None = None) -> dict[str, KnobSpec]:
    """Load + VALIDATE the knob registry. Returns {knob_id: KnobSpec}.

    Validation (all FAIL LOUD) enforces the §1.2 / §1.7 schema-time review:
      * unique ids; legal block / dna_class / checkpoint / widget / type;
      * str_enum knobs carry a non-empty ``enum`` and a code_default within it (or null);
      * §-1.3 day-waster ids are refused;
      * §1.7 model / token env aliases are refused.
    """
    p = path or registry_path()
    if not p.exists():
        raise RunConfigError(f"knob registry not found at {p} (PG_RUN_CONFIG_KNOBS?)")
    doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    rows = doc.get("knobs")
    if not isinstance(rows, list) or not rows:
        raise RunConfigError(f"knob registry at {p} has no 'knobs' list")

    specs: dict[str, KnobSpec] = {}
    for row in rows:
        if not isinstance(row, dict) or "id" not in row:
            raise RunConfigError(f"knob registry row is not a dict with an id: {row!r}")
        kid = str(row["id"])
        if kid in specs:
            raise RunConfigError(f"duplicate knob id {kid!r} in registry")
        if kid.lower() in _DAY_WASTER_DENYLIST:
            raise RunConfigError(
                f"knob {kid!r} is on the §-1.3 day-waster denylist (a number-forcing "
                "cap/target/thinner) — it may NOT be registered as a user knob"
            )
        block = str(row.get("block", ""))
        if block not in _LEGAL_BLOCKS:
            raise RunConfigError(f"knob {kid!r}: illegal block {block!r} (allowed {sorted(_LEGAL_BLOCKS)})")
        dna = str(row.get("dna_class", ""))
        if dna not in _LEGAL_DNA_CLASSES:
            raise RunConfigError(
                f"knob {kid!r}: illegal dna_class {dna!r}. A knob whose purpose is to force a "
                f"quality number is REJECTED (§-1.3); allowed {sorted(_LEGAL_DNA_CLASSES)}"
            )
        ktype = str(row.get("type", ""))
        if ktype not in ("int", "float", "str", "bool", "str_enum", "list"):
            raise RunConfigError(f"knob {kid!r}: illegal type {ktype!r}")
        erc = str(row.get("earliest_resume_checkpoint", ""))
        if erc not in CHECKPOINT_ORDER:
            raise RunConfigError(
                f"knob {kid!r}: earliest_resume_checkpoint {erc!r} not in {CHECKPOINT_ORDER}"
            )
        env_var = row.get("env_var")
        env_var = str(env_var) if env_var else None
        if env_var:
            for pat in _FORBIDDEN_ENV_PATTERNS:
                if pat.search(env_var):
                    raise RunConfigError(
                        f"knob {kid!r}: env alias {env_var!r} names a model/token budget — "
                        "excluded by §1.7 / §9.1.8 (models + token caps are the operator lock, "
                        "never a RunConfig knob)"
                    )
        enum_vals = row.get("enum")
        enum_tuple: tuple[str, ...] | None = None
        if ktype == "str_enum":
            if not isinstance(enum_vals, list) or not enum_vals:
                raise RunConfigError(f"knob {kid!r}: str_enum requires a non-empty 'enum' list")
            enum_tuple = tuple(str(v) for v in enum_vals)
        code_default = row.get("code_default")
        if enum_tuple is not None and code_default is not None and str(code_default) not in enum_tuple:
            raise RunConfigError(
                f"knob {kid!r}: code_default {code_default!r} not in enum {enum_tuple}"
            )
        widget = str(row.get("panel_widget", ""))
        if not widget:
            raise RunConfigError(f"knob {kid!r}: missing panel_widget")
        specs[kid] = KnobSpec(
            id=kid,
            block=block,
            type=ktype,
            code_default=code_default,
            env_var=env_var,
            earliest_resume_checkpoint=erc,
            prompt_parseable=bool(row.get("prompt_parseable", False)),
            panel_widget=widget,
            dna_class=dna,
            enum=enum_tuple,
        )
    return specs


# ---------------------------------------------------------------------------
# Provenance + the RunConfig object.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KnobProvenance:
    """The resolved value of one knob + WHERE it came from. Serializable DATA."""

    knob_id: str
    value: Any
    source: str  # panel | adjust | prompt | env | default
    span: str | None = None  # verbatim prompt trigger when source == prompt, else None

    def as_dict(self) -> dict[str, Any]:
        return {"knob_id": self.knob_id, "value": self.value, "source": self.source, "span": self.span}


@dataclass
class RunConfig:
    """The one control surface. Captures the two USER surfaces; env is read live.

    ``panel`` and ``prompt`` are keyed by knob_id. ``prompt`` values are (value, span)
    pairs so the parsed trigger span is preserved for anti-invention disclosure. The
    resolver merges panel > prompt > env > code-default per §1.3.
    """

    panel: dict[str, Any] = field(default_factory=dict)  # surface (b): explicit overrides
    prompt: dict[str, tuple[Any, str]] = field(default_factory=dict)  # surface (a): parsed (value, span)
    adjust: dict[str, Any] = field(default_factory=dict)  # resume-time explicit overrides (§1.4)

    # ---- construction from the two surfaces -----------------------------------

    @classmethod
    def from_sources(
        cls,
        *,
        prompt_text: str | None = None,
        panel_overrides: dict[str, Any] | None = None,
        registry: dict[str, KnobSpec] | None = None,
    ) -> "RunConfig":
        """Build a RunConfig by parsing the prompt AND merging panel overrides.

        Panel overrides are validated against the registry (unknown knob / bad enum =
        FAIL LOUD). Prompt parsing is deterministic + anti-invention: only knobs with a
        verbatim trigger span are set.
        """
        reg = registry if registry is not None else load_registry()
        cfg = cls()
        if prompt_text:
            cfg.prompt = parse_prompt_knobs(prompt_text, reg)
        if panel_overrides:
            for kid, val in panel_overrides.items():
                if kid not in reg:
                    raise RunConfigError(f"panel override for unknown knob {kid!r}")
                cfg.panel[kid] = _coerce(reg[kid], val)
        return cfg

    # ---- resolution -----------------------------------------------------------

    def resolve(self, knob_id: str, *, registry: dict[str, KnobSpec] | None = None,
                env: dict[str, str] | None = None) -> KnobProvenance:
        return get(self, knob_id, registry=registry, env=env)

    def resolve_all(self, *, registry: dict[str, KnobSpec] | None = None,
                    env: dict[str, str] | None = None) -> dict[str, KnobProvenance]:
        reg = registry if registry is not None else load_registry()
        return {kid: get(self, kid, registry=reg, env=env) for kid in reg}

    def non_default(self, *, registry: dict[str, KnobSpec] | None = None,
                    env: dict[str, str] | None = None) -> list[KnobProvenance]:
        """Every knob whose resolved source is NOT ``default`` — the §1.3 disclosure set."""
        return [p for p in self.resolve_all(registry=registry, env=env).values()
                if p.source != SOURCE_DEFAULT]

    def config_sha(self, *, registry: dict[str, KnobSpec] | None = None,
                   env: dict[str, str] | None = None) -> str:
        """Deterministic sha256 of the fully-resolved config (for cp0 pinning, §1.4)."""
        resolved = self.resolve_all(registry=registry, env=env)
        blob = json.dumps(
            {kid: [p.value, p.source] for kid, p in sorted(resolved.items())},
            sort_keys=True, default=str,
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        return {
            "panel": dict(self.panel),
            "prompt": {k: {"value": v[0], "span": v[1]} for k, v in self.prompt.items()},
            "adjust": dict(self.adjust),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunConfig":
        prompt = {
            k: (v.get("value"), str(v.get("span", "")))
            for k, v in (data.get("prompt") or {}).items()
        }
        return cls(panel=dict(data.get("panel") or {}),
                   prompt=prompt,
                   adjust=dict(data.get("adjust") or {}))


def _coerce(spec: KnobSpec, raw: Any) -> Any:
    """Coerce a raw value (env string or panel scalar) into the knob's declared type.

    FAIL LOUD on a bad enum or an uncoercible scalar — never silently drop to a default.
    """
    if raw is None:
        return None
    t = spec.type
    try:
        if t == "int":
            return int(str(raw).strip())
        if t == "float":
            return float(str(raw).strip())
        if t == "bool":
            if isinstance(raw, bool):
                return raw
            return str(raw).strip().lower() in ("1", "true", "yes", "on")
        if t == "list":
            if isinstance(raw, (list, tuple)):
                return [str(x) for x in raw]
            # env / panel string form: comma-separated
            return [s.strip() for s in str(raw).split(",") if s.strip()]
        if t == "str_enum":
            val = str(raw).strip()
            if spec.enum and val not in spec.enum:
                raise RunConfigError(f"knob {spec.id!r}: value {val!r} not in enum {spec.enum}")
            return val
        return str(raw)
    except RunConfigError:
        raise
    except (ValueError, TypeError) as exc:
        raise RunConfigError(f"knob {spec.id!r}: cannot coerce {raw!r} to {t}: {exc}") from exc


def get(cfg: RunConfig | None, knob_id: str, *,
        registry: dict[str, KnobSpec] | None = None,
        env: dict[str, str] | None = None) -> KnobProvenance:
    """THE resolver. Return the resolved KnobProvenance for ``knob_id``.

    Precedence PANEL/ADJUST > PROMPT > ENV > CODE-DEFAULT (§1.3). The value is ALWAYS
    selected from one of those four layers and tagged with its source — it can never be a
    mid-function literal (zero-hardcode guarantee). ``env`` defaults to ``os.environ`` and
    is read at CALL TIME (LAW VI). A ``None`` cfg means "empty RunConfig" (byte-identical
    to today: env if set, else code-default).
    """
    reg = registry if registry is not None else load_registry()
    if knob_id not in reg:
        raise RunConfigError(f"unknown knob {knob_id!r} (not in registry)")
    spec = reg[knob_id]
    environ = env if env is not None else os.environ

    # 1) PANEL / ADJUST (explicit user overrides). adjust ranks with panel; if both set,
    #    adjust (the later, resume-time instruction) wins.
    if cfg is not None and knob_id in cfg.adjust:
        return KnobProvenance(knob_id, _coerce(spec, cfg.adjust[knob_id]), SOURCE_ADJUST)
    if cfg is not None and knob_id in cfg.panel:
        return KnobProvenance(knob_id, _coerce(spec, cfg.panel[knob_id]), SOURCE_PANEL)

    # 2) PROMPT-parsed (carries a verbatim span).
    if cfg is not None and knob_id in cfg.prompt:
        value, span = cfg.prompt[knob_id]
        return KnobProvenance(knob_id, _coerce(spec, value), SOURCE_PROMPT, span or None)

    # 3) ENV (incl. the Gate-B slate). Read live.
    if spec.env_var and spec.env_var in environ and str(environ[spec.env_var]).strip() != "":
        return KnobProvenance(knob_id, _coerce(spec, environ[spec.env_var]), SOURCE_ENV)

    # 4) CODE-DEFAULT (from the registry DATA — the ONLY code-side value, and it is data).
    return KnobProvenance(knob_id, spec.code_default, SOURCE_DEFAULT)


# ---------------------------------------------------------------------------
# Surface (a): deterministic prompt parsing (anti-invention, verbatim spans).
# ---------------------------------------------------------------------------
#
# This is the WAVE-0 DETERMINISTIC seed of the S0 intake extractor. The Design-3 LLM
# semantic pass is a WAVE-1 additive layer; this core recognises explicit directives with
# a verbatim trigger span for every operator-named knob. Anti-invention: a field is set
# ONLY when a trigger span matches — nothing is guessed.

# (knob_id, compiled regex, value-builder(match) -> value). Order matters only within a
# knob; distinct knobs are independent. First match per knob wins.
_PROMPT_RULES: list[tuple[str, re.Pattern[str], Any]] = [
    # breadth
    ("query_count", re.compile(r"\b(?:run|use|issue|at least|up to|no more than|about|around)\s+(\d{1,3})\s+(?:sub-?)?quer", re.I), lambda m: int(m.group(1))),
    ("query_count", re.compile(r"\b(\d{1,3})\s+(?:sub-?)?queries\b", re.I), lambda m: int(m.group(1))),
    ("searches_per_query", re.compile(r"\b(\d{1,3})\s+searches?\s+per\s+quer", re.I), lambda m: int(m.group(1))),
    ("breadth_class", re.compile(r"\b(exhaustive|comprehensive|all available evidence|in-?depth|deep dive)\b", re.I), lambda m: "WIDE"),
    ("breadth_class", re.compile(r"\b(brief overview|quick overview|high-?level|at a glance)\b", re.I), lambda m: "NARROW"),
    # depth (co-signals with breadth_class but a distinct presentation knob)
    ("depth", re.compile(r"\b(exhaustive|comprehensive|in-?depth|deep dive|deeply)\b", re.I), lambda m: "deep"),
    ("depth", re.compile(r"\b(brief overview|quick overview|high-?level|shallow)\b", re.I), lambda m: "shallow"),
    # scope: date window + recency
    ("date_from", re.compile(r"\b((?:19|20)\d{2})\s*(?:-|–|—|to|through|until)\s*(?:19|20)\d{2}\b", re.I), lambda m: m.group(1)),
    ("date_to", re.compile(r"\b(?:19|20)\d{2}\s*(?:-|–|—|to|through|until)\s*((?:19|20)\d{2})\b", re.I), lambda m: m.group(1)),
    ("date_from", re.compile(r"\b(?:since|after|from)\s+((?:19|20)\d{2})\b", re.I), lambda m: m.group(1)),
    ("date_to", re.compile(r"\b(?:before|until|up to)\s+((?:19|20)\d{2})\b", re.I), lambda m: m.group(1)),
    ("recency", re.compile(r"\b(?:last|past|previous)\s+(\d{1,2})\s+years?\b", re.I), lambda m: f"last_{m.group(1)}_years"),
    ("recency", re.compile(r"\b(recent|latest|up-?to-?date)\b", re.I), lambda m: "recent"),
    # scope: source type
    ("peer_reviewed_only", re.compile(r"\bpeer[- ]reviewed\s+only\b", re.I), lambda m: True),
    ("source_types", re.compile(r"\b(peer[- ]reviewed|clinical trials?|guidelines?|systematic reviews?|preprints?|news)\b", re.I), lambda m: [re.sub(r"\s+", "_", m.group(1).lower().rstrip("s"))]),
    # scope: geography
    ("geography", re.compile(r"\b(EU|European Union|Europe|European)\b"), lambda m: "EU"),
    ("geography", re.compile(r"\b(US|U\.S\.|USA|United States|American)\b"), lambda m: "US"),
    ("geography", re.compile(r"\b(UK|United Kingdom|British)\b"), lambda m: "UK"),
    ("geography", re.compile(r"\b(Canada|Canadian)\b", re.I), lambda m: "Canada"),
    # scope: language
    ("language", re.compile(r"\b(?:in|written in)\s+(French|Spanish|German|Chinese|Japanese|Portuguese|Italian)\b", re.I), lambda m: m.group(1).lower()),
    ("language", re.compile(r"\b(French|Spanish|German|Chinese|Japanese|Portuguese|Italian)[- ]language\b", re.I), lambda m: m.group(1).lower()),
    # scope: authors
    ("authors", re.compile(r"\b(?:authored by|by author|papers? (?:by|from))\s+([A-Z][A-Za-z.'-]+(?:\s+(?:et al\.?|[A-Z][A-Za-z.'-]+))?)", re.I), lambda m: [m.group(1).strip()]),
    # scope: focus (freeform)
    ("scope_focus", re.compile(r"\b(?:focus(?:ed|ing)? on|limited to|scoped to|restricted to)\s+([^.;,\n]{3,80})", re.I), lambda m: m.group(1).strip()),
    # deliverable: tone
    ("tone", re.compile(r"\bexecutive (?:brief|memo|summary)\b", re.I), lambda m: "executive_brief"),
    ("tone", re.compile(r"\b(academic|scholarly)\b", re.I), lambda m: "academic"),
    ("tone", re.compile(r"\b(plain[- ]language|accessible|lay(?:person)?)\b", re.I), lambda m: "plain"),
    ("tone", re.compile(r"\bformal\b", re.I), lambda m: "formal"),
    # deliverable: reference style
    ("reference_style", re.compile(r"\b(Harvard)\b", re.I), lambda m: "harvard"),
    ("reference_style", re.compile(r"\b(APA)\b"), lambda m: "apa"),
    ("reference_style", re.compile(r"\b(Vancouver)\b", re.I), lambda m: "vancouver"),
    ("reference_style", re.compile(r"\b(author[- ]year)\b", re.I), lambda m: "author_year"),
    ("reference_style", re.compile(r"\b(numeric|numbered) (?:references|citations)\b", re.I), lambda m: "numeric"),
    # deliverable: length
    ("length_target", re.compile(r"\b(?:cap(?:ped)?(?:\s+at)?|no more than|under|about|around|~)\s*(\d{2,5})\s+words\b", re.I), lambda m: int(m.group(1))),
    ("length_strictness", re.compile(r"\b(?:cap(?:ped)?(?:\s+at)?|no more than|strictly)\s*\d{2,5}\s+words\b", re.I), lambda m: "hard"),
    # deliverable: structure / order
    ("summary_first", re.compile(r"\bsummary[- ]first\b|\b(?:lead|start|begin) with (?:a|an|the)? ?(?:executive )?summary\b", re.I), lambda m: True),
    ("recommendations_last", re.compile(r"\brecommendations? (?:last|at the end)\b", re.I), lambda m: True),
    ("tables", re.compile(r"\b(?:with|include|use) tables?\b", re.I), lambda m: True),
    ("structure", re.compile(r"\bsections?\s*:\s*([^.\n]{3,200})", re.I), lambda m: [s.strip() for s in re.split(r"[;,]", m.group(1)) if s.strip()]),
    # deliverable: audience
    ("audience", re.compile(r"\bfor (?:a|an)\s+([A-Za-z ]{3,40}?)\s+audience\b", re.I), lambda m: m.group(1).strip()),
]


def parse_prompt_knobs(prompt_text: str, registry: dict[str, KnobSpec]) -> dict[str, tuple[Any, str]]:
    """Parse explicit directives from a NL prompt. Returns {knob_id: (value, span)}.

    Deterministic + anti-invention: a knob is set ONLY on a verbatim trigger match, and
    the matched substring is recorded as the span. Only ``prompt_parseable`` knobs are
    considered. First matching rule per knob wins (rules are ordered most-specific-first).
    """
    out: dict[str, tuple[Any, str]] = {}
    for knob_id, pattern, builder in _PROMPT_RULES:
        if knob_id in out:
            continue
        spec = registry.get(knob_id)
        if spec is None or not spec.prompt_parseable:
            continue
        m = pattern.search(prompt_text)
        if not m:
            continue
        try:
            value = builder(m)
        except (ValueError, IndexError):
            continue
        # coerce + enum-validate now so an out-of-enum parse is rejected (anti-invention).
        try:
            value = _coerce(spec, value)
        except RunConfigError:
            continue
        span = m.group(0).strip()
        out[knob_id] = (value, span)
    return out


# ---------------------------------------------------------------------------
# Resume adjustment validity matrix (§1.4).
# ---------------------------------------------------------------------------


def adjustment_valid_at(knob_id: str, entry_checkpoint: str,
                        registry: dict[str, KnobSpec]) -> bool:
    """Is adjusting ``knob_id`` legal when resuming at ``entry_checkpoint``?

    RULE (§1.4): valid iff entry_index <= erc_index. The knob's consuming stage must still
    run after the resume entry point for the adjustment to take effect; resuming later than
    the knob's earliest_resume_checkpoint means the stage already ran => not valid.
    """
    if knob_id not in registry:
        raise RunConfigError(f"unknown knob {knob_id!r}")
    if entry_checkpoint not in CHECKPOINT_ORDER:
        raise RunConfigError(f"unknown checkpoint {entry_checkpoint!r}")
    return CHECKPOINT_ORDER.index(entry_checkpoint) <= registry[knob_id].erc_index


def apply_adjustment(cfg: RunConfig, adjustment: dict[str, Any], entry_checkpoint: str,
                     registry: dict[str, KnobSpec] | None = None) -> RunConfig:
    """Return a NEW RunConfig with a resume-time adjustment merged into the ``adjust`` layer.

    FAIL LOUD if any adjusted knob is not valid at ``entry_checkpoint`` (naming the correct
    earliest checkpoint). The adjustment reconfigures the DOWNSTREAM stages only — it never
    mutates the loaded upstream checkpoint (that is the caller's contract; this only builds
    the downstream config).
    """
    reg = registry if registry is not None else load_registry()
    new = RunConfig(panel=dict(cfg.panel), prompt=dict(cfg.prompt), adjust=dict(cfg.adjust))
    for kid, val in adjustment.items():
        if kid not in reg:
            raise RunConfigError(f"resume --adjust: unknown knob {kid!r}")
        if not adjustment_valid_at(kid, entry_checkpoint, reg):
            raise RunConfigError(
                f"resume --adjust: knob {kid!r} cannot be adjusted when resuming at "
                f"{entry_checkpoint} — its stage already ran; resume at "
                f"{reg[kid].earliest_resume_checkpoint} or earlier to change it"
            )
        new.adjust[kid] = _coerce(reg[kid], val)
    return new
