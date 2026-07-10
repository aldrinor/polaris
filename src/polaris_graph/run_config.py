"""S0 INTAKE — the ONE RunConfig object + assembly + cp0 writer (master plan §1).

Full user-adjustability is a HARD, cross-cutting requirement: EVERY pipeline knob must
be settable TWO ways — written in the natural-language prompt (parsed by the S0
extractors) or set explicitly on a control panel / CLI override file — and the two
surfaces merge into ONE object by ONE precedence rule. This module IS that object and
that merge. It is the S0 boundary: a clean question in, a fully-resolved
``cp0_run_config.json`` (every knob + the LAYER that decided it) out.

Precedence (master §1.3, ruling R9):
    code_default (registry yaml)  <  env var  <  PROMPT-PARSED  <  CONTROL PANEL / CLI

Surfaces:
  * Prompt-parsed — the S0 extractors run on the clean question:
      - scope  : ``intake_constraint_extractor`` (dates/language/peer-reviewed) +
                 ``extract_scope_constraints`` (source-type/jurisdiction/named) +
                 three S0 companions here (recency / geography / authors);
      - deliverable : ``deliverable_spec_extractor`` (tone/structure/reference/length);
      - breadth : ``breadth_directive_parser`` (query_count incl 35+, searches_per_query).
  * Control panel / CLI — a plain ``{knob_id: value}`` override dict (the web POST body
    or a ``run_config_overrides.json``). The backend contract is RunConfig JSON only; the
    backend never knows a UI existed.

Guardrails (master §1.7): no knob here weakens the faithfulness engine, hard-drops a
credible on-topic source, selects a model, or exists to force a quality number — the
registry's ``dna_class`` review enforces that at schema time. Zero hardcoded knob values
in this module: every default is read from ``config/settings/run_config_knobs.yaml``
(LAW VI). Pure + offline: extractor LLM passes are INJECTED, never imported/called by
default.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from src.polaris_graph.retrieval.breadth_directive_parser import parse_breadth_directive
from src.polaris_graph.retrieval.deliverable_spec_extractor import extract_deliverable_spec
from src.polaris_graph.retrieval.intake_constraint_extractor import (
    extract_scope_constraints,
    extract_user_constraints,
)

logger = logging.getLogger("polaris_graph.run_config")

_OFF_VALUES = frozenset({"0", "false", "no", "off", "disabled", ""})
_TRUE_VALUES = frozenset({"1", "true", "yes", "on", "enabled"})
_REGISTRY_ENV = "PG_RUN_CONFIG_REGISTRY"
_REGISTRY_REL = "config/settings/run_config_knobs.yaml"
CP0_FILENAME = "cp0_run_config.json"
SCHEMA_VERSION = "cp0-runconfig-1"

# Source layers, most-authoritative last (precedence order).
SOURCE_DEFAULT = "default"
SOURCE_ENV = "env"
SOURCE_PARSED = "parsed"
SOURCE_PANEL = "panel"
_SOURCE_ORDER = (SOURCE_DEFAULT, SOURCE_ENV, SOURCE_PARSED, SOURCE_PANEL)

# ── S0 scope companions (LAW VI: vocab from the scope ontology, no magic numbers) ──
_RECENCY_RE = re.compile(r"\b(?:in\s+the\s+)?(?:last|past|recent)\s+(\d{1,2})\s+years?\b", re.I)
# Author phrasing — a proper name governed by an authorship verb. Conservative: an
# author verb MUST precede the name, so a topic noun is never mistaken for an author.
_AUTHOR_RE = re.compile(
    r"\b(?:papers?|studies|research|work|publications?|articles?|writings?|findings?)\s+"
    r"(?:by|of|from)\s+"
    r"|(?:authored\s+by|written\s+by|according\s+to|attributed\s+to|prioriti[sz]e\s+"
    r"(?:research|work|papers?)\s+by)\s+",
    re.I)
# A proper name: capitalized word(s) or single-letter initials, joined by spaces. A
# trailing sentence period is NOT a connector, so "Fauci. Run at least 60 queries" stops
# at "Fauci" rather than absorbing the next sentence's first word.
_NAME_RE = re.compile(r"((?:Dr\.?\s+|Prof\.?\s+)?[A-Z][a-z'’-]+(?:\s+(?:[A-Z][a-z'’-]+|[A-Z]\.)){0,3})")


def _registry_path() -> Path:
    override = os.getenv(_REGISTRY_ENV, "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / _REGISTRY_REL


def load_knob_registry(path: "str | Path | None" = None) -> list[dict[str, Any]]:
    """Load the knob registry (the single source of knob truth, master §1.2).

    Fail-LOUD: the registry is the source of every code_default (LAW VI). A missing or
    unparseable registry is an intake blocker, never a silent empty default.
    """
    import yaml  # noqa: PLC0415

    p = Path(path) if path else _registry_path()
    if not p.exists():
        raise FileNotFoundError(f"RunConfig knob registry not found: {p}")
    with p.open("r", encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    knobs = doc.get("knobs")
    if not isinstance(knobs, list) or not knobs:
        raise ValueError(f"RunConfig knob registry has no 'knobs' list: {p}")
    return knobs


@dataclass
class KnobProvenance:
    """One resolved knob + the LAYER that decided its value (master §1.1 provenance)."""

    knob_id: str
    value: Any
    source: str                       # default | env | parsed | panel
    block: str
    span: Optional[str] = None        # verbatim prompt trigger (parsed only)
    detail: str = ""                  # env var name / panel note / lexicon note

    def to_dict(self) -> dict[str, Any]:
        return {
            "knob_id": self.knob_id,
            "value": self.value,
            "source": self.source,
            "block": self.block,
            "span": self.span,
            "detail": self.detail,
        }


@dataclass
class BreadthBlock:
    query_budget: Optional[int] = None
    rounds: Optional[int] = None
    serper_k: Optional[int] = None
    s2_k: Optional[int] = None
    serper_total: Optional[int] = None
    fetch_cap: Optional[int] = None
    breadth_class: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class ScopeBlock:
    date_start: Optional[str] = None
    date_end: Optional[str] = None
    recency_years: Optional[int] = None
    source_types: list = field(default_factory=list)
    geography: list = field(default_factory=list)
    jurisdiction: list = field(default_factory=list)
    language: Optional[str] = None
    authors: list = field(default_factory=list)
    peer_reviewed_only: bool = False
    user_constraints: dict = field(default_factory=dict)   # raw UserConstraints.to_dict()
    scope_constraints: dict = field(default_factory=dict)  # raw ScopeConstraints.to_dict()

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class DeliverableBlock:
    deliverable_type: Optional[str] = None
    audience: Optional[str] = None
    tone: Optional[str] = None
    reading_level: Optional[str] = None
    reference_style: Optional[str] = None
    length_target_words: Optional[int] = None
    length_target_pages: Optional[int] = None
    length_strictness: str = "weight"
    summary_first: Optional[bool] = None
    recommendations_last: Optional[bool] = None
    wants_tables: Optional[bool] = None
    structure_slots: list = field(default_factory=list)
    output_format: Optional[str] = None
    deliverable_spec: dict = field(default_factory=dict)   # raw DeliverableSpec.to_dict()

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class StagesBlock:
    knobs: dict = field(default_factory=dict)   # generic {knob_id: value}

    def to_dict(self) -> dict[str, Any]:
        return {"knobs": dict(self.knobs)}


@dataclass
class RunConfig:
    """The one object every stage reads (master §1.1). Empty = today's behavior."""

    breadth: BreadthBlock = field(default_factory=BreadthBlock)
    scope: ScopeBlock = field(default_factory=ScopeBlock)
    deliverable: DeliverableBlock = field(default_factory=DeliverableBlock)
    stages: StagesBlock = field(default_factory=StagesBlock)
    provenance: dict[str, KnobProvenance] = field(default_factory=dict)
    question: str = ""
    question_sha: str = ""

    def get(self, knob_id: str, default: Any = None) -> Any:
        """The §1.5 resolver surface: return the resolved value for ``knob_id``."""
        prov = self.provenance.get(knob_id)
        return prov.value if prov is not None else default

    def source_of(self, knob_id: str) -> Optional[str]:
        prov = self.provenance.get(knob_id)
        return prov.source if prov is not None else None

    def non_default_knobs(self) -> list[dict[str, Any]]:
        """Every knob whose value did NOT come from the code default — the Methods
        disclosure surface (master §1.3: disclose value + source layer)."""
        out = []
        for kid in sorted(self.provenance):
            p = self.provenance[kid]
            if p.source != SOURCE_DEFAULT:
                out.append(p.to_dict())
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "question": self.question,
            "question_sha": self.question_sha,
            "breadth": self.breadth.to_dict(),
            "scope": self.scope.to_dict(),
            "deliverable": self.deliverable.to_dict(),
            "stages": self.stages.to_dict(),
            "provenance": {k: v.to_dict() for k, v in self.provenance.items()},
            "non_default_knobs": self.non_default_knobs(),
        }


# ── coercion ─────────────────────────────────────────────────────────────────
def _coerce(value: Any, knob_type: str) -> Any:
    """Coerce an env-string (or panel scalar) to the registry-declared type. Fail-open:
    an uncoercible value is returned unchanged so the resolver can still record it."""
    if value is None:
        return None
    if knob_type == "int":
        try:
            return int(str(value).strip())
        except (ValueError, TypeError):
            return value
    if knob_type == "bool":
        if isinstance(value, bool):
            return value
        s = str(value).strip().lower()
        if s in _TRUE_VALUES:
            return True
        if s in _OFF_VALUES:
            return False
        return value
    if knob_type == "list":
        if isinstance(value, list):
            return value
        if isinstance(value, str) and value.strip():
            return [p.strip() for p in value.split(",") if p.strip()]
        return value
    return value  # str / free


# ── S0 scope companions ──────────────────────────────────────────────────────
def _parse_recency(question: str) -> Optional[tuple[int, str]]:
    m = _RECENCY_RE.search(question or "")
    if m is None:
        return None
    try:
        return int(m.group(1)), m.group(0).strip()
    except (ValueError, IndexError):
        return None


def _parse_geography(question: str, ontology: "dict[str, Any] | None" = None) -> list[tuple[str, str, str]]:
    """(region_label, iso, span) for each geographic scope directive. Mirrors the
    existing jurisdiction detection (adjective + a source noun) so geography lands exactly
    when the jurisdiction lane would — vocab from the scope ontology (LAW VI)."""
    text = (question or "").strip()
    if not text:
        return []
    try:
        from src.polaris_graph.retrieval.scope_facet_classifier import (  # noqa: PLC0415
            load_scope_ontology,
        )
        ont = ontology if ontology is not None else load_scope_ontology()
    except Exception:  # noqa: BLE001 - fail-open: no ontology => no geography
        return []
    juris = ont.get("jurisdictions") or {}
    suffixes = ont.get("jurisdiction_synonym_suffixes") or ["sources", "source"]
    suffix_re = "(?:" + "|".join(re.escape(str(s)) for s in suffixes) + ")"
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for adj, iso in juris.items():
        adjl = str(adj).lower()
        if not adjl:
            continue
        for m in re.finditer(r"\b(" + re.escape(adjl) + r")\s+" + suffix_re + r"\b", text, re.I):
            key = str(iso)
            if key in seen:
                continue
            seen.add(key)
            out.append((m.group(1), str(iso), m.group(0).strip()))
    return out


def _parse_authors(question: str) -> list[tuple[str, str]]:
    """(author_name, span) for each authorship directive. An author VERB must precede the
    name so a topic noun is never mistaken for an author (fail-safe against over-extract)."""
    text = (question or "").strip()
    if not text:
        return []
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for m in _AUTHOR_RE.finditer(text):
        tail = text[m.end():m.end() + 60]
        nm = _NAME_RE.match(tail.lstrip())
        if nm is None:
            continue
        name = " ".join(nm.group(1).split()).strip(" .,")
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        span = (m.group(0) + nm.group(1)).strip()
        out.append((name, span))
    return out


def _first_directive(directives: list[str], *keywords: str) -> str:
    for d in directives or []:
        low = d.lower()
        if any(k in low for k in keywords):
            return d
    return ""


def _build_parsed_map(
    question: str,
    *,
    deliverable_llm_fn: Optional[Callable[[str], str]],
    scope_llm_fn: Optional[Callable[[str], str]],
    constraint_llm_fn: Optional[Callable[[str], str]],
    breadth_llm_fn: Optional[Callable[[str], str]],
) -> tuple[dict[str, tuple[Any, str]], dict[str, Any]]:
    """Run every S0 extractor and flatten to {knob_id: (value, span)} + the raw blocks.

    Only knobs the prompt ACTUALLY set land in the map (a None/empty extraction is NOT an
    override — the default/env stands). Returns (parsed_map, raw_objects)."""
    uc = extract_user_constraints(question, llm_fn=constraint_llm_fn)
    sc = extract_scope_constraints(question, llm_fn=scope_llm_fn)
    spec = extract_deliverable_spec(question, llm_fn=deliverable_llm_fn)
    bd = parse_breadth_directive(question, llm_fn=breadth_llm_fn)

    parsed: dict[str, tuple[Any, str]] = {}

    # breadth
    if bd.query_count is not None:
        parsed["query_budget"] = (bd.query_count, bd.trigger_spans.get("query_count", ""))
    if bd.searches_per_query is not None:
        parsed["serper_k"] = (bd.searches_per_query, bd.trigger_spans.get("searches_per_query", ""))
    if bd.rounds is not None:
        parsed["rounds"] = (bd.rounds, bd.trigger_spans.get("rounds", ""))
    if bd.breadth_class is not None:
        parsed["breadth_class"] = (bd.breadth_class, bd.trigger_spans.get("breadth_class", ""))

    # scope — dates / language / peer-reviewed from UserConstraints
    ds = uc.date_start_iso()
    if ds is not None:
        parsed["date_start"] = (ds, _first_directive(uc.raw_directives, "since", "from", "after", "last", "past", "recent"))
    de = uc.date_end_iso()
    if de is not None:
        parsed["date_end"] = (de, _first_directive(uc.raw_directives, "before", "until", "by", "up to", "prior"))
    if uc.language is not None:
        parsed["language"] = (uc.language, _first_directive(uc.raw_directives, "english", "french", "spanish", "german", "chinese", "japanese", "portuguese", "italian", "language"))
    # scope — source types + jurisdiction + peer-reviewed from ScopeConstraints facets
    source_types = []
    jurisdiction = []
    st_span = ju_span = pr_span = ""
    peer_reviewed = bool(uc.journal_only)
    if peer_reviewed:
        pr_span = _first_directive(uc.raw_directives, "journal")
    for f in sc.facets:
        if f.dimension == "source_type":
            if f.facet_id not in source_types:
                source_types.append(f.facet_id)
                st_span = st_span or f.trigger_span
            if f.facet_id == "peer_reviewed_journal":
                peer_reviewed = True
                pr_span = f.trigger_span or pr_span  # prefer the verbatim facet phrase
        elif f.dimension == "jurisdiction":
            iso = f.facet_id.split(":", 1)[1] if ":" in f.facet_id else f.facet_id
            if iso not in jurisdiction:
                jurisdiction.append(iso)
                ju_span = ju_span or f.trigger_span
    if source_types:
        parsed["source_types"] = (source_types, st_span)
    if jurisdiction:
        parsed["jurisdiction"] = (jurisdiction, ju_span)
    if peer_reviewed:
        parsed["peer_reviewed_only"] = (True, pr_span)
    # scope — companions (recency / geography / authors)
    rec = _parse_recency(question)
    if rec is not None:
        parsed["recency_years"] = (rec[0], rec[1])
    geos = _parse_geography(question)
    if geos:
        parsed["geography"] = ([g[0] for g in geos], geos[0][2])
        # fold geo ISO into jurisdiction when the facet lane missed it
        merged_juris = list(jurisdiction)
        for _, iso, _span in geos:
            if iso not in merged_juris:
                merged_juris.append(iso)
        if merged_juris != jurisdiction:
            parsed["jurisdiction"] = (merged_juris, parsed.get("jurisdiction", (None, ju_span))[1] or geos[0][2])
    authors = _parse_authors(question)
    named = [n.label for n in sc.named_include]
    all_authors = authors + [(lbl, lbl) for lbl in named if lbl not in {a[0] for a in authors}]
    if all_authors:
        parsed["authors"] = ([a[0] for a in all_authors], all_authors[0][1])

    # deliverable
    d = spec.to_dict()
    for kid in ("deliverable_type", "audience", "tone", "reading_level", "reference_style",
                "length_target_words", "length_target_pages", "summary_first",
                "recommendations_last", "wants_tables", "output_format"):
        if d.get(kid) is not None:
            parsed[kid] = (d[kid], spec.trigger_spans.get(kid, ""))
    if spec.length_strictness and spec.length_strictness != "weight":
        parsed["length_strictness"] = (spec.length_strictness, spec.trigger_spans.get("length_strictness", ""))
    if spec.structure_slots:
        parsed["structure_slots"] = (list(spec.structure_slots), "; ".join(s.get("text", "") for s in spec.structure_slots)[:200])

    raw = {
        "user_constraints": uc.to_dict(),
        "scope_constraints": sc.to_dict(),
        "deliverable_spec": spec.to_dict(),
        "breadth_directive": bd.to_dict(),
    }
    return parsed, raw


def assemble_run_config(
    question: str,
    *,
    panel_overrides: "dict[str, Any] | None" = None,
    env: "dict[str, str] | None" = None,
    registry: "list[dict[str, Any]] | None" = None,
    deliverable_llm_fn: Optional[Callable[[str], str]] = None,
    scope_llm_fn: Optional[Callable[[str], str]] = None,
    constraint_llm_fn: Optional[Callable[[str], str]] = None,
    breadth_llm_fn: Optional[Callable[[str], str]] = None,
) -> RunConfig:
    """Assemble the fully-resolved RunConfig from prompt + panel + env + registry defaults.

    Precedence (master §1.3 / R9): default(registry) < env < prompt-parsed < panel. Every
    knob in the registry is resolved and gets a ``KnobProvenance`` recording the deciding
    layer. Pure + offline when the llm_fn hooks are None (regex-only extraction)."""
    question = question or ""
    panel_overrides = panel_overrides or {}
    env = os.environ if env is None else env
    reg = registry if registry is not None else load_knob_registry()

    parsed, raw = _build_parsed_map(
        question,
        deliverable_llm_fn=deliverable_llm_fn,
        scope_llm_fn=scope_llm_fn,
        constraint_llm_fn=constraint_llm_fn,
        breadth_llm_fn=breadth_llm_fn,
    )

    provenance: dict[str, KnobProvenance] = {}
    resolved: dict[str, Any] = {}
    block_of: dict[str, str] = {}
    for row in reg:
        kid = str(row.get("id") or "")
        if not kid:
            continue
        block = str(row.get("block") or "stages")
        ktype = str(row.get("type") or "str")
        block_of[kid] = block

        value = row.get("code_default")
        source = SOURCE_DEFAULT
        span: Optional[str] = None
        detail = "registry code_default"

        env_var = row.get("env_var")
        if env_var and env_var in env and str(env.get(env_var)).strip() != "":
            value = _coerce(env.get(env_var), ktype)
            source = SOURCE_ENV
            detail = f"env {env_var}"

        if kid in parsed and parsed[kid][0] is not None:
            value = parsed[kid][0]
            source = SOURCE_PARSED
            span = parsed[kid][1] or None
            detail = "prompt-parsed"

        if kid in panel_overrides:
            value = _coerce(panel_overrides[kid], ktype)
            source = SOURCE_PANEL
            span = None
            detail = "control panel / CLI override"

        resolved[kid] = value
        provenance[kid] = KnobProvenance(
            knob_id=kid, value=value, source=source, block=block, span=span, detail=detail,
        )

    breadth = BreadthBlock(
        query_budget=resolved.get("query_budget"),
        rounds=resolved.get("rounds"),
        serper_k=resolved.get("serper_k"),
        s2_k=resolved.get("s2_k"),
        serper_total=resolved.get("serper_total"),
        fetch_cap=resolved.get("fetch_cap"),
        breadth_class=resolved.get("breadth_class"),
    )
    scope = ScopeBlock(
        date_start=resolved.get("date_start"),
        date_end=resolved.get("date_end"),
        recency_years=resolved.get("recency_years"),
        source_types=list(resolved.get("source_types") or []),
        geography=list(resolved.get("geography") or []),
        jurisdiction=list(resolved.get("jurisdiction") or []),
        language=resolved.get("language"),
        authors=list(resolved.get("authors") or []),
        peer_reviewed_only=bool(resolved.get("peer_reviewed_only") or False),
        user_constraints=raw["user_constraints"],
        scope_constraints=raw["scope_constraints"],
    )
    deliverable = DeliverableBlock(
        deliverable_type=resolved.get("deliverable_type"),
        audience=resolved.get("audience"),
        tone=resolved.get("tone"),
        reading_level=resolved.get("reading_level"),
        reference_style=resolved.get("reference_style"),
        length_target_words=resolved.get("length_target_words"),
        length_target_pages=resolved.get("length_target_pages"),
        length_strictness=resolved.get("length_strictness") or "weight",
        summary_first=resolved.get("summary_first"),
        recommendations_last=resolved.get("recommendations_last"),
        wants_tables=resolved.get("wants_tables"),
        structure_slots=list(resolved.get("structure_slots") or []),
        output_format=resolved.get("output_format"),
        deliverable_spec=raw["deliverable_spec"],
    )
    stage_knobs = {kid: resolved[kid] for kid, blk in block_of.items() if blk == "stages"}
    stages = StagesBlock(knobs=stage_knobs)

    return RunConfig(
        breadth=breadth,
        scope=scope,
        deliverable=deliverable,
        stages=stages,
        provenance=provenance,
        question=question,
        question_sha=hashlib.sha256(question.encode("utf-8")).hexdigest(),
    )


def write_cp0_run_config(run_config: RunConfig, run_dir: "str | Path", *, filename: str = CP0_FILENAME) -> Path:
    """Write ``cp0_run_config.json`` atomically (temp + os.replace, sorted deterministic
    bytes). cp0 IS the pinned RunConfig (master §1.4): loaded-never-re-extracted on resume."""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    target = run_dir / filename
    tmp = run_dir / (filename + ".tmp")
    payload = run_config.to_dict()
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True, ensure_ascii=False)
    os.replace(tmp, target)
    logger.info(
        "[run_config] cp0 written: %s (%d knobs, %d non-default) sha-question=%s",
        target, len(run_config.provenance), len(run_config.non_default_knobs()),
        run_config.question_sha[:12],
    )
    return target


def load_cp0_run_config(path: "str | Path") -> RunConfig:
    """Load a pinned cp0 back into a RunConfig (resume path — fail-loud on corruption)."""
    p = Path(path)
    with p.open("r", encoding="utf-8") as fh:
        d = json.load(fh)
    prov = {}
    for kid, pv in (d.get("provenance") or {}).items():
        prov[kid] = KnobProvenance(
            knob_id=pv.get("knob_id", kid), value=pv.get("value"), source=pv.get("source", SOURCE_DEFAULT),
            block=pv.get("block", "stages"), span=pv.get("span"), detail=pv.get("detail", ""),
        )
    b = d.get("breadth") or {}
    s = d.get("scope") or {}
    dl = d.get("deliverable") or {}
    st = (d.get("stages") or {}).get("knobs") or {}
    return RunConfig(
        breadth=BreadthBlock(**{k: b.get(k) for k in BreadthBlock().__dict__}),
        scope=ScopeBlock(**{k: s.get(k, ScopeBlock().__dict__[k]) for k in ScopeBlock().__dict__}),
        deliverable=DeliverableBlock(**{k: dl.get(k, DeliverableBlock().__dict__[k]) for k in DeliverableBlock().__dict__}),
        stages=StagesBlock(knobs=dict(st)),
        provenance=prov,
        question=d.get("question", ""),
        question_sha=d.get("question_sha", ""),
    )
