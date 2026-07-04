"""I-meta-005 Phase 7 (#991) — Quantified trade-off modeler (gap 9, PAL rewire).

Pipeline: Extract -> Model -> Execute(DETERMINISTIC) -> Bind -> Verify(Regime C).

This module owns **Model** + the deterministic **Execute template**. It is the
faithfulness wedge extended to COMPUTED numbers: a number rendered in the report
is only allowed to survive verification if it is provably the declared formula
evaluated over declared inputs, where every sourced input is a concrete extracted
datapoint that appears numeric-verbatim in its evidence row.

What this module provides:

  - ``ModelSpec`` (+ ``SourcedInput`` / ``ModeledInput`` / ``OutputField`` /
    ``Sensitivity`` / ``SolveFor``): the validated, hashable computation spec.
  - ``build_quantified_spec(question, sourced_numbers, evidence_rows, *, spec_llm)``:
    the Writer emits a raw JSON spec; we VALIDATE it hard and return
    ``ModelSpec | None`` (fail-closed on any violation). Validation enforces
    (i) datapoint exact-one-match identity + raw-literal+span derivation,
    (ii) pure-arithmetic formula AST, (iii) NUMERIC material dependency (every
    declared input must change >=1 output under perturbation — kills canceling
    formulas), (iv) non-empty outputs, (v) sensitivity well-formedness,
    (vi) solve_for bracket well-formedness.
  - ``render_script(spec)``: DETERMINISTIC template of the validated spec into a
    fixed Python skeleton (NO LLM codegen) for
    ``code_executor.execute_analysis_script`` — every number it prints is the
    declared output formula over the declared inputs.
  - ``_canonical_display(value, unit, display_kind)``: the ONE pinned per-kind
    formatter used by BOTH the executor (to pin a field's display_value) and the
    binder (to render that exact string next to the calc token) so Regime C is an
    exact-string equality + a deterministic replay.

OFF byte-identical: nothing here imports/runs unless the sweep is on-mode.
SPEND-FREE: ``build_quantified_spec`` takes a ``spec_llm`` callable (faked in
tests); ``render_script`` + the executor run FIXED Python — no network.
"""
from __future__ import annotations

import ast
import hashlib
import json
import logging
import math
import os
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ── T4 (I-deepfix-001 #1344) literal_span faithfulness invariant (DeepTRACE #7 citation-accuracy) ──
# LAW VI env kill-switch (default ON). An emitted ``[literal_start, literal_end]`` MUST slice its
# evidence text back to EXACTLY ``raw_literal``. A frame-drifted offset that lands inside an
# unrelated token (the F2 defect: span [40,43]='lfs' inside 'Brynjolfsson') is a citation-accuracy
# defect — the rendered span no longer contains the number it claims to cite. This is a fail-closed
# POST-condition on span derivation: faithfulness-STRENGTHENING (it can only REJECT a bad span,
# never admit one), never relaxes strict_verify / NLI / the 4-role engine.
_LITERAL_SPAN_ENFORCE_ENV = "PG_LITERAL_SPAN_ENFORCE"


def _literal_span_enforce_enabled() -> bool:
    """T4 kill-switch. Default ON; OFF => the invariant is a no-op (pre-fix behaviour)."""
    return os.getenv(_LITERAL_SPAN_ENFORCE_ENV, "1").strip().lower() not in (
        "", "0", "false", "off", "no",
    )


def literal_span_is_faithful(ev_text: str, literal: str, start: int, end: int) -> bool:
    """True iff ``ev_text[start:end]`` equals ``literal`` exactly (the emitted span slices back to the
    number it cites). PURE. Bounds-safe: an out-of-range / inverted offset is unfaithful, not a crash.
    This is the load-bearing T4 invariant — a citation whose span does not contain its literal is a
    DeepTRACE #7 accuracy failure regardless of how the offset was computed."""
    if literal is None or ev_text is None:
        return False
    if not isinstance(start, int) or not isinstance(end, int):
        return False
    if start < 0 or end > len(ev_text) or start >= end:
        return False
    return ev_text[start:end] == literal


# ── V5 (I-deepfix-001 #1344) dual-tag fail-soft kill-switch ───────────────────
# A Writer input tagged BOTH ``modeled`` and ``datapoint_ref`` (the recurring GLM-5.2 /
# deepseek over-tag; captured drb_72 where ONE such input zeroed a 1087-number section)
# is RE-GROUNDED to its datapoint_ref instead of fail-closing the whole quantified
# section. Default ON. OFF => pre-fix behaviour (return _reject at the dual-tag gate).
_DUAL_TAG_FAILSOFT_ENV = "PG_QUANTIFIED_DUAL_TAG_FAILSOFT"


def _dual_tag_failsoft_enabled() -> bool:
    """V5 kill-switch. Default ON; OFF => a both-modeled-and-sourced input is a hard reject."""
    return os.getenv(_DUAL_TAG_FAILSOFT_ENV, "1").strip().lower() not in (
        "", "0", "false", "off", "no",
    )

# ── tolerances (named, Law VI) ───────────────────────────────────────────────
# Literal<->datapoint normalized-value agreement (same extractor normalization
# feeds both, so this is tight).
_LITERAL_MATCH_REL_TOL = 1e-6
_LITERAL_MATCH_ABS_TOL = 1e-9
# Material-dependency perturbation: an input that, when perturbed, moves NO
# output by more than this (relative to the output magnitude) is NOT a real
# input and the whole model is rejected.
_DEPENDENCY_PERTURB_DELTA = 1e-3
_DEPENDENCY_EFFECT_REL_TOL = 1e-9
_DEPENDENCY_EFFECT_ABS_TOL = 1e-12

# Pure-arithmetic formula AST allowlist. Bare function names only (the rendered
# script imports these from math so the inlined formula evaluates identically to
# the modeler's interpreter). NO attribute access, NO subscript, NO comprehension.
_ALLOWED_FORMULA_FUNCS: dict[str, Callable[..., float]] = {
    "min": min,
    "max": max,
    "abs": abs,
    "round": round,
    "sqrt": math.sqrt,
    "log": math.log,
    "log10": math.log10,
    "log2": math.log2,
    "exp": math.exp,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "floor": math.floor,
    "ceil": math.ceil,
    "pow": pow,
}
_DISPLAY_KINDS = frozenset({"number", "currency", "percent", "ratio", "count"})


# ─────────────────────────────────────────────────────────────────────────────
# Spec dataclasses
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class SourcedInput:
    """An input bound to a CONCRETE extracted datapoint.

    ``value`` (float) is what the formula uses; ``raw_literal`` (the
    pre-normalization string e.g. "$1.548 billion") + ``literal_start``/
    ``literal_end`` are the evidence span used to cite the input. The datapoint
    identity (ev_id + label + context + value + unit) is what disambiguates a
    repeated value in the same row.
    """
    name: str
    value: float
    unit: str
    ev_id: str
    label: str
    context: str
    raw_literal: str
    literal_start: int
    literal_end: int


@dataclass(frozen=True)
class ModeledInput:
    name: str
    base: float
    unit: str
    sweep_lo: float
    sweep_hi: float
    sweep_step: float


@dataclass(frozen=True)
class OutputField:
    name: str
    unit: str
    display_kind: str
    formula: str


@dataclass(frozen=True)
class Sensitivity:
    input: str   # a MODELED input name
    output: str   # a declared output name


@dataclass(frozen=True)
class SolveFor:
    var: str      # a MODELED input name whose sweep is the [lo,hi] bracket
    output: str   # a declared output name (break-even = root of formula==0)


@dataclass
class ModelSpec:
    model_id: str
    title: str
    sourced_inputs: list[SourcedInput]
    modeled_inputs: list[ModeledInput]
    outputs: list[OutputField]
    sensitivity: list[Sensitivity] = field(default_factory=list)
    solve_for: SolveFor | None = None
    spec_hash: str = ""

    # convenience lookups -----------------------------------------------------
    def input_names(self) -> list[str]:
        return [i.name for i in self.sourced_inputs] + [
            i.name for i in self.modeled_inputs
        ]

    def modeled_by_name(self, name: str) -> ModeledInput | None:
        for i in self.modeled_inputs:
            if i.name == name:
                return i
        return None

    def output_by_name(self, name: str) -> OutputField | None:
        for o in self.outputs:
            if o.name == name:
                return o
        return None

    def base_env(self) -> dict[str, float]:
        env = {i.name: float(i.value) for i in self.sourced_inputs}
        env.update({i.name: float(i.base) for i in self.modeled_inputs})
        return env


# ─────────────────────────────────────────────────────────────────────────────
# Formula AST: validation + a tiny deterministic interpreter (NO eval)
# ─────────────────────────────────────────────────────────────────────────────
_ALLOWED_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod, ast.FloorDiv)
_ALLOWED_UNARYOPS = (ast.UAdd, ast.USub)


def _formula_names(formula: str, allowed_names: set[str]) -> tuple[bool, str, set[str]]:
    """Validate ``formula`` is pure arithmetic over ``allowed_names`` + allowlisted
    funcs. Returns (ok, reason, referenced_input_names)."""
    try:
        tree = ast.parse(formula, mode="eval")
    except SyntaxError as exc:
        return False, f"formula_syntax_error:{str(exc)[:80]}", set()

    referenced: set[str] = set()

    def _check(node: ast.AST) -> tuple[bool, str]:
        if isinstance(node, ast.Expression):
            return _check(node.body)
        if isinstance(node, ast.BinOp):
            if not isinstance(node.op, _ALLOWED_BINOPS):
                return False, f"disallowed_binop:{type(node.op).__name__}"
            ok, r = _check(node.left)
            if not ok:
                return ok, r
            return _check(node.right)
        if isinstance(node, ast.UnaryOp):
            if not isinstance(node.op, _ALLOWED_UNARYOPS):
                return False, f"disallowed_unaryop:{type(node.op).__name__}"
            return _check(node.operand)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                return False, "non_numeric_constant"
            return True, ""
        if isinstance(node, ast.Name):
            if node.id in _ALLOWED_FORMULA_FUNCS:
                return True, ""
            if node.id not in allowed_names:
                return False, f"unknown_name:{node.id}"
            referenced.add(node.id)
            return True, ""
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FORMULA_FUNCS:
                return False, "disallowed_call"
            if node.keywords:
                return False, "call_keywords_not_allowed"
            for a in node.args:
                ok, r = _check(a)
                if not ok:
                    return ok, r
            return True, ""
        return False, f"disallowed_node:{type(node).__name__}"

    ok, reason = _check(tree)
    return ok, reason, referenced


def _formula_referenced_names(formula: str) -> set[str] | None:
    """Return the set of bare ``Name`` ids in ``formula`` that are NOT allowlisted
    funcs (i.e. candidate input/output references), or None if it does not parse.
    Used only to build the output-dependency graph for inlining — the FULL
    pure-arithmetic safety check still runs via ``_formula_names`` after inlining."""
    try:
        tree = ast.parse(formula, mode="eval")
    except SyntaxError:
        return None
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id not in _ALLOWED_FORMULA_FUNCS:
            names.add(node.id)
    return names


def _inline_output_references(
    raw_outputs: list[dict[str, Any]], input_names: set[str],
) -> tuple[list[dict[str, Any]] | None, str]:
    """I-wire-014 (#1336): deterministically INLINE output->output formula references
    so every output formula is expressed purely over INPUT names before validation.

    ROOT CAUSE this fixes (drb_72 ai-labor, captured offline): the Writer naturally
    chains outputs, e.g.
        net_shift_per_decade = ag_decline_rate - prof_growth_rate
        cumulative_net_shift = net_shift_per_decade * projection_decades
    The validator's ``_formula_names`` only permits references to declared INPUT names,
    so the second formula rejected with ``unknown_name:net_shift_per_decade`` even though
    the model is perfectly defensible. Inlining substitutes the referenced output's
    (parenthesized) formula:
        cumulative_net_shift = (ag_decline_rate - prof_growth_rate) * projection_decades

    This is VALUE-PRESERVING and DETERMINISTIC: the inlined formula computes the IDENTICAL
    number the chained form would, and the deterministic Regime-C re-execution +
    material-dependency + numeric-verbatim gates all run UNCHANGED on the inlined formula.
    It does NOT touch the execution engine (no output-in-env, no dep-ordered exec) — the
    engine never sees an output reference. It also FIXES citation binding: after inlining,
    ``output_referenced_inputs`` correctly attributes a chained output to its TRANSITIVE
    sourced inputs (naive output-ref support would attribute it to a non-sourced output
    name and cite nothing).

    Returns ``(normalized_outputs, "")`` on success or ``(None, reason)`` on a cyclic /
    self-referential / unparseable dependency (left for the caller to ``_reject``). When
    no output references another output, the outputs pass through unchanged (byte-identical).
    """
    # map output name -> raw formula string (skip malformed entries; the caller's
    # output loop rejects those explicitly with output_not_dict / bad_or_dup_output_name)
    formula_by_name: dict[str, str] = {}
    order: list[dict[str, Any]] = []
    for ro in raw_outputs:
        if not isinstance(ro, dict):
            return None, "output_not_dict"
        oname = str(ro.get("name", "")).strip()
        if oname:
            formula_by_name[oname] = str(ro.get("formula", "")).strip()
        order.append(ro)

    out_names = set(formula_by_name)
    if not out_names:
        return raw_outputs, ""

    # build output->output dependency edges (a name that is BOTH an output and not an
    # input is an output reference). A name that is an input takes input precedence.
    deps: dict[str, set[str]] = {}
    for oname, formula in formula_by_name.items():
        refs = _formula_referenced_names(formula)
        if refs is None:
            return None, f"formula_invalid:{oname}:formula_syntax_error"
        out_deps = {r for r in refs if r in out_names and r not in input_names}
        if oname in out_deps:
            return None, f"formula_invalid:{oname}:self_reference"
        deps[oname] = out_deps

    if not any(deps.values()):
        return raw_outputs, ""  # no chaining — unchanged

    # resolve each output to a pure-input formula via memoized DFS with cycle detection
    resolved: dict[str, str] = {}
    visiting: set[str] = set()

    def _resolve(name: str) -> str | None:
        if name in resolved:
            return resolved[name]
        if name in visiting:
            return None  # cycle
        visiting.add(name)
        formula = formula_by_name[name]
        for dep in deps[name]:
            sub = _resolve(dep)
            if sub is None:
                return None
            # substitute the dep output NAME with its parenthesized resolved formula
            # (whole-word only, so a longer name containing this one is not corrupted)
            formula = re.sub(
                rf"\b{re.escape(dep)}\b", f"({sub})", formula,
            )
        visiting.discard(name)
        resolved[name] = formula
        return formula

    for oname in out_names:
        if _resolve(oname) is None:
            return None, f"formula_invalid:{oname}:cyclic_output_reference"

    # emit outputs in the ORIGINAL order with the inlined formulas
    normalized: list[dict[str, Any]] = []
    for ro in order:
        oname = str(ro.get("name", "")).strip()
        if oname and oname in resolved:
            entry = dict(ro)
            entry["formula"] = resolved[oname]
            normalized.append(entry)
        else:
            normalized.append(ro)
    return normalized, ""


def _eval_formula(formula: str, env: dict[str, float]) -> float:
    """Deterministic arithmetic interpreter over a validated formula. NO eval."""
    tree = ast.parse(formula, mode="eval")

    def _ev(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return _ev(node.body)
        if isinstance(node, ast.BinOp):
            l, r = _ev(node.left), _ev(node.right)
            op = node.op
            if isinstance(op, ast.Add):
                return l + r
            if isinstance(op, ast.Sub):
                return l - r
            if isinstance(op, ast.Mult):
                return l * r
            if isinstance(op, ast.Div):
                return l / r
            if isinstance(op, ast.Pow):
                return l ** r
            if isinstance(op, ast.Mod):
                return l % r
            if isinstance(op, ast.FloorDiv):
                return l // r
            raise ValueError(f"binop:{type(op).__name__}")
        if isinstance(node, ast.UnaryOp):
            v = _ev(node.operand)
            return +v if isinstance(node.op, ast.UAdd) else -v
        if isinstance(node, ast.Constant):
            return float(node.value)
        if isinstance(node, ast.Name):
            if node.id in env:
                return float(env[node.id])
            raise ValueError(f"name:{node.id}")
        if isinstance(node, ast.Call):
            fn = _ALLOWED_FORMULA_FUNCS[node.func.id]  # type: ignore[index]
            return float(fn(*[_ev(a) for a in node.args]))
        raise ValueError(f"node:{type(node).__name__}")

    return float(_ev(tree))


# ─────────────────────────────────────────────────────────────────────────────
# Canonical display (the ONE formatter — exact-string equality + replay)
# ─────────────────────────────────────────────────────────────────────────────
def _canonical_display(value: float, unit: str, display_kind: str) -> str:
    """Deterministic, pinned per-kind display string for a computed number.

    Used by BOTH the executor (to pin a field's display_value) and the binder
    (to render that exact string next to the calc token). Regime C compares the
    rendered string adjacent to the calc token against this exact string, with a
    numeric backstop. Changing these formats changes spec replay — treat as LOCKED.
    """
    v = float(value)
    if display_kind == "currency":
        return f"${v:,.2f}"
    if display_kind == "percent":
        return f"{v:.2f}%"
    if display_kind == "ratio":
        return f"{v:.4f}"
    if display_kind == "count":
        return f"{int(round(v)):,}"
    # "number" (default): up to 6 significant figures, thousands-grouped integer
    # part, no trailing zeros, deterministic. NEVER scientific notation — the
    # verifier's adjacency capture is decimal/thousands only, so a "1e+06" display
    # would false-DROP a legitimate computed number (Codex diff-gate iter2 P1). A
    # 6-sig-fig value that Python would render in scientific form is EXPANDED to a
    # plain fixed-point decimal via Decimal.
    if v == 0:
        return "0"
    s = f"{v:.6g}"
    if "e" in s or "E" in s:
        s = format(Decimal(s), "f")   # expand sci -> plain fixed-point decimal
    if "." in s:
        int_part, frac_part = s.split(".")
    else:
        int_part, frac_part = s, ""
    neg = int_part.startswith("-")
    digits = int_part[1:] if neg else int_part
    grouped = f"{int(digits):,}" if digits.isdigit() else digits
    out = ("-" if neg else "") + grouped
    frac_part = frac_part.rstrip("0")     # no trailing zeros after expansion
    if frac_part:
        out += "." + frac_part
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Literal normalization + location (extractor-equivalent; no new extractor spans)
# ─────────────────────────────────────────────────────────────────────────────
# I-deepfix-001 defer-E (#1344): ``trillion`` MUST be in the scale set in lock-step with
# ``evidence_extractor`` — a value scaled to 2.6e12 there can only be located back to its
# source literal if BOTH the capture regex and the normalizer understand "trillion". Omitting
# it dropped the magnitude word from the rendered literal ("$2.6 trillion" -> "$2.6") and made
# _normalize_literal return None (fail-closed reject). Adding it keeps the unit attached.
_SCALE_MULTIPLIERS = {"trillion": 1e12, "billion": 1e9, "million": 1e6, "thousand": 1e3}
# A numeric literal, optionally $-prefixed, optionally followed by a scale word
# or a percent sign. Mirrors evidence_extractor's scale handling.
_LITERAL_RE = re.compile(
    r"\$?\s*-?\d[\d,]*(?:\.\d+)?\s*(?:trillion|billion|million|thousand)?\s*%?",
    re.IGNORECASE,
)


def _normalize_literal(raw: str) -> float | None:
    """Parse a raw literal ("$1.548 billion", "23.4%", "1,200") to a float using
    the SAME scale handling as ``evidence_extractor`` (billion/million/thousand
    multipliers). Percent keeps its face value (23.4 for "23.4%")."""
    s = raw.strip()
    has_pct = s.endswith("%")
    if has_pct:
        s = s[:-1].strip()
    scale = 1.0
    low = s.lower()
    for word, mult in _SCALE_MULTIPLIERS.items():
        if low.endswith(word):
            scale = mult
            s = s[: -len(word)].strip()
            break
    s = s.replace("$", "").replace(",", "").strip()
    if not s:
        return None
    try:
        return float(s) * scale
    except ValueError:
        return None


def _locate_unique_literal(
    text: str, target_value: float
) -> tuple[str, int, int] | None:
    """Find the UNIQUE numeric literal in ``text`` whose extractor-normalized
    value matches ``target_value``. Returns (literal, start, end) or None when
    zero or >=2 candidates match (fail-closed disambiguation)."""
    if not text:
        return None
    matches: list[tuple[str, int, int]] = []
    for m in _LITERAL_RE.finditer(text):
        raw = m.group(0).strip()
        # Skip bare scale/percent fragments with no digit.
        if not re.search(r"\d", raw):
            continue
        norm = _normalize_literal(raw)
        if norm is None:
            continue
        if math.isclose(
            norm, float(target_value),
            rel_tol=_LITERAL_MATCH_REL_TOL, abs_tol=_LITERAL_MATCH_ABS_TOL,
        ):
            # Trim leading/trailing whitespace captured by the regex.
            lit = m.group(0)
            lstrip = len(lit) - len(lit.lstrip())
            rstrip = len(lit) - len(lit.rstrip())
            start = m.start() + lstrip
            end = m.end() - rstrip
            matches.append((text[start:end], start, end))
    if len(matches) == 1:
        return matches[0]
    return None


def _evidence_text(ev_row: dict[str, Any]) -> str:
    """The text used both to verify the literal and to locate its span — the
    same fields Regime A reads (direct_quote, then statement)."""
    return (ev_row.get("direct_quote") or ev_row.get("statement") or "")


# ─────────────────────────────────────────────────────────────────────────────
# Build + validate the spec (fail-closed)
# ─────────────────────────────────────────────────────────────────────────────
def _spec_hash(
    model_id: str,
    sourced: list[SourcedInput],
    modeled: list[ModeledInput],
    outputs: list[OutputField],
    sensitivity: list[Sensitivity],
    solve_for: SolveFor | None,
) -> str:
    """Stable hash binding the calc token to THIS run's model (prevents stale or
    colliding model_ids reaching Regime C)."""
    proj = {
        "model_id": model_id,
        "sourced": sorted(
            [
                {"name": s.name, "value": repr(float(s.value)), "unit": s.unit,
                 "ev_id": s.ev_id}
                for s in sourced
            ],
            key=lambda d: d["name"],
        ),
        "modeled": sorted(
            [
                {"name": m.name, "base": repr(float(m.base)), "unit": m.unit,
                 "sweep": [repr(float(m.sweep_lo)), repr(float(m.sweep_hi)),
                           repr(float(m.sweep_step))]}
                for m in modeled
            ],
            key=lambda d: d["name"],
        ),
        "outputs": sorted(
            [
                {"name": o.name, "unit": o.unit, "display_kind": o.display_kind,
                 "formula": o.formula}
                for o in outputs
            ],
            key=lambda d: d["name"],
        ),
        "sensitivity": sorted(
            [{"input": s.input, "output": s.output} for s in sensitivity],
            key=lambda d: (d["input"], d["output"]),
        ),
        "solve_for": (
            {"var": solve_for.var, "output": solve_for.output}
            if solve_for else None
        ),
    }
    blob = json.dumps(proj, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _matches_datapoint(ref: dict[str, Any], dp: dict[str, Any]) -> bool:
    """Exact-one-match identity on ALL of (ev_id, label, context, value, unit).
    value compared as normalized float (extractor emits str values)."""
    if str(ref.get("ev_id", "")) != str(dp.get("evidence_id", "")):
        return False
    if str(ref.get("label", "")) != str(dp.get("label", "")):
        return False
    if str(ref.get("context", "")) != str(dp.get("context", "")):
        return False
    if str(ref.get("unit", "")) != str(dp.get("unit", "")):
        return False
    try:
        return math.isclose(
            float(ref.get("value")), float(dp.get("value")),
            rel_tol=_LITERAL_MATCH_REL_TOL, abs_tol=_LITERAL_MATCH_ABS_TOL,
        )
    except (TypeError, ValueError):
        return False


def _normalize_raw_spec(raw: dict[str, Any]) -> dict[str, Any]:
    """I-wire-014 (#1336): PURELY STRUCTURAL normalization of the Writer's raw spec
    JSON into the canonical list-of-dicts shape ``build_quantified_spec`` validates.

    ROOT CAUSE this fixes (drb_72 ai-labor, captured via the banked Writer call):
    the GLM-5.2 / deepseek Writer routinely emits the natural, common LLM JSON shape

        "inputs":  {"<name>": {datapoint_ref|modeled...}, ...}   (OBJECT keyed by name)
        "outputs": {"<name>": "<formula>", ...}                  (OBJECT, value=formula str)
        "sensitivity": "<output_name>"                           (bare STRING)
        "solve_for":   "<output_name>"                           (bare STRING)
        "sweep": [lo, hi]                                        (2-elem, no step)

    while the validator hard-requires ``inputs``/``outputs`` to be LISTS of dicts each
    carrying a ``name`` key, ``sensitivity`` a list of ``{input,output}`` dicts, etc.
    The very first gate (``inputs_or_outputs_not_list``) then rejected EVERY otherwise-
    valid model — which is why ``quantified_model.json`` had never once been produced and
    the Phase-7 differentiator silently no-op'd on real runs (firing_status=
    spec_validation_rejected).

    FAITHFULNESS (LAW §-1.3): this is shape-only. It NEVER invents, alters, or drops a
    sourced value, datapoint_ref, ev_id, label, context, unit, or numeric. Every
    downstream gate (exact-one-match datapoint identity, numeric-verbatim literal+span
    location, pure-arithmetic formula AST, material-dependency perturbation) runs
    UNCHANGED on the normalized spec — so a fabricated or mis-cited number still fails
    exactly as before. Canonical list-form input passes through BYTE-IDENTICAL: the
    branches below only fire on the non-canonical (dict/str) shapes. (The sole exception
    is a 2-elem MODELED sweep, which is padded to [lo,hi,step] even in list-form — a
    uncited, never-rendered value, so faithfulness-neutral.) The caller's dict is never
    mutated (a fresh copy is taken before any in-place write).

    Underspecified OPTIONAL clauses (``sensitivity`` / ``solve_for`` that are not
    well-formed) are DROPPED, never guessed — guessing the missing input/var would be
    the faithfulness violation. A 2-elem ``sweep`` on a MODELED (uncited, never-rendered)
    input is padded with a derived step so the modeled-input parse does not IndexError;
    the modeled input feeds only the (possibly-dropped) sensitivity/solve_for and carries
    no citation, so the pad is faithfulness-neutral.
    """
    out: dict[str, Any] = dict(raw)  # shallow copy; never mutate the caller's dict

    # ── inputs: OBJECT keyed by name -> LIST of {name, ...} ──────────────────
    raw_inputs = out.get("inputs")
    if isinstance(raw_inputs, dict):
        norm_inputs: list[Any] = []
        for name, body in raw_inputs.items():
            if isinstance(body, dict):
                entry = dict(body)
                entry.setdefault("name", name)
                norm_inputs.append(entry)
            else:
                # a non-dict input body is malformed; pass it through unchanged so the
                # validator rejects it explicitly (input_not_dict) rather than here.
                norm_inputs.append(body)
        out["inputs"] = norm_inputs
        raw_inputs = norm_inputs

    # pad a 2-elem (or shorter) modeled sweep with a derived step (modeled inputs only;
    # uncited + never-rendered). A 3+-elem sweep is left untouched.
    if isinstance(raw_inputs, list):
        padded_inputs: list[Any] = []
        for entry in raw_inputs:
            if not isinstance(entry, dict):
                padded_inputs.append(entry)
                continue
            sweep = entry.get("sweep")
            if (
                bool(entry.get("modeled"))
                and isinstance(sweep, (list, tuple))
                and len(sweep) == 2
            ):
                try:
                    lo, hi = float(sweep[0]), float(sweep[1])
                    step = (hi - lo) / 10.0 if hi != lo else 1.0
                    if step == 0:
                        step = 1.0
                    # copy the entry before mutating so a LIST-form caller's original
                    # dict is never mutated (out=dict(raw) is only a shallow copy).
                    entry = dict(entry)
                    entry["sweep"] = [sweep[0], sweep[1], step]
                except (TypeError, ValueError):
                    pass  # leave malformed sweep for the validator to reject
            padded_inputs.append(entry)
        out["inputs"] = padded_inputs

    # ── outputs: OBJECT keyed by name -> LIST of {name, formula, ...} ────────
    raw_outputs = out.get("outputs")
    if isinstance(raw_outputs, dict):
        norm_outputs: list[Any] = []
        for name, body in raw_outputs.items():
            if isinstance(body, dict):
                entry = dict(body)
                entry.setdefault("name", name)
                norm_outputs.append(entry)
            elif isinstance(body, str):
                # value-is-formula shorthand: {"<name>": "<formula>"}
                norm_outputs.append({"name": name, "formula": body})
            else:
                norm_outputs.append(body)
        out["outputs"] = norm_outputs

    # ── sensitivity: bare string / dict -> LIST of {input,output} dicts; drop
    #    anything not well-formed (optional clause — never guess the missing key) ─
    raw_sens = out.get("sensitivity")
    if isinstance(raw_sens, str):
        # a bare output name carries no swept INPUT -> cannot form a valid sweep -> drop.
        out["sensitivity"] = []
    elif isinstance(raw_sens, dict):
        # single {input, output} dict -> wrap; drop if it lacks the required pair.
        if raw_sens.get("input") and raw_sens.get("output"):
            out["sensitivity"] = [raw_sens]
        else:
            out["sensitivity"] = []
    elif isinstance(raw_sens, list):
        out["sensitivity"] = [s for s in raw_sens if isinstance(s, dict)]

    # ── solve_for: bare string -> drop (no var); dict passes to the validator ─
    raw_solve = out.get("solve_for")
    if isinstance(raw_solve, str):
        out["solve_for"] = None

    return out


def build_quantified_spec(
    question: str,
    sourced_numbers: list[dict[str, Any]],
    evidence_rows: dict[str, dict[str, Any]],
    *,
    spec_llm: Callable[[str, list[dict[str, Any]]], dict[str, Any] | None],
    on_reject: Callable[[str], None] | None = None,
) -> ModelSpec | None:
    """Build + validate a ModelSpec from a Writer-emitted raw JSON spec.

    ``spec_llm(question, sourced_numbers) -> raw_spec_dict | None`` is the (faked
    in tests / Writer in prod) spec generator. Returns a validated ``ModelSpec``
    or ``None`` (whole model skipped, fail-closed) on ANY violation.

    I-fix-001: ``on_reject`` (additive; default ``None`` => byte-identical) is
    invoked with a SHORT machine-readable reason code at EVERY fail-closed return
    so the caller can stamp ``telem["spec_reject_reason"]`` into the durable
    manifest. Sweep run.log captures stdout, not stderr WARNINGs, so without this
    the exact rejecting gate was invisible post-run — the I-fix-001 silent no-op:
    a cert run recorded ``firing_status=spec_validation_rejected`` with NO
    attributable gate. The reason channel makes the silent failure name itself.
    """
    def _reject(reason: str) -> None:
        # One channel for every fail-closed exit: log (stderr) AND surface the
        # reason to the caller's telemetry (durable manifest). Returns None so
        # callers write ``return _reject(...)``.
        logger.warning("[tradeoff_modeler] reject: %s", reason)
        if on_reject is not None:
            on_reject(reason)
        return None

    try:
        raw = spec_llm(question, sourced_numbers)
    except Exception as exc:  # spec-gen failure is a clean skip, not a crash
        return _reject(f"spec_llm_raised:{str(exc)[:120]}")
    if not isinstance(raw, dict):
        return _reject("raw_not_dict")

    # I-wire-014 (#1336): normalize the Writer's natural object-keyed / string-valued
    # JSON shape into the canonical list-of-dicts form the gates below validate. PURELY
    # STRUCTURAL — list-form input passes through byte-identical; no value/citation is
    # ever invented or altered (see _normalize_raw_spec). This is the root-cause fix for
    # the silent quantified no-op (spec_validation_rejected at inputs_or_outputs_not_list).
    raw = _normalize_raw_spec(raw)

    model_id = str(raw.get("model_id", "")).strip()
    title = str(raw.get("title", "")).strip()
    if not re.fullmatch(r"[A-Za-z0-9_]+", model_id or ""):
        return _reject(f"bad_model_id:{model_id!r}")

    raw_inputs = raw.get("inputs")
    raw_outputs = raw.get("outputs")
    if not isinstance(raw_inputs, list) or not isinstance(raw_outputs, list):
        return _reject("inputs_or_outputs_not_list")
    if not raw_outputs:
        return _reject("outputs_empty")  # (iv) outputs non-empty

    sourced: list[SourcedInput] = []
    modeled: list[ModeledInput] = []
    seen_names: set[str] = set()
    # V5 (#1344): names re-grounded from a both-modeled-and-sourced over-tag to the
    # SOURCED reading. A sweep the Writer declared over such a name is dropped (a
    # measured citation is not a swept assumption), never a whole-spec reject.
    reclassified_sourced: set[str] = set()

    for ri in raw_inputs:
        if not isinstance(ri, dict):
            return _reject("input_not_dict")
        name = str(ri.get("name", "")).strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name or "") or name in seen_names:
            return _reject(f"bad_or_dup_input_name:{name!r}")
        seen_names.add(name)

        is_modeled = bool(ri.get("modeled"))
        has_ref = isinstance(ri.get("datapoint_ref"), dict)
        if is_modeled and has_ref:
            # V5 (I-deepfix-001 #1344) fail-SOFT: the GLM-5.2 / deepseek Writer routinely
            # over-tags ONE input as BOTH modeled AND sourced. Captured drb_72: a single
            # ``programmer_wage_premium`` fail-closed a whole 1087-number quantified section
            # (spec_validation_rejected -> silent no-op); productivity_gain /
            # workforce_share_1900 hit the same gate on sibling runs. Pre-fix this rejected
            # the ENTIRE spec on ONE over-tagged input. RE-GROUND to the SOURCED reading
            # (§-1.3: prefer a REAL evidence span over the ungrounded modeled ``base``): drop
            # the spurious ``modeled`` flag and route the datapoint_ref through the UNCHANGED
            # sourced gates below (exact-one-match identity + numeric-verbatim literal+span).
            # Faithfulness-NEUTRAL — the rendered value is still the evidence-grounded
            # datapoint, re-checked by Regime C; a bad ref STILL fails its own sourced gate;
            # a cited number that affects no output STAYS fatal (non_affecting_input). Keeping
            # the name in the dependency graph avoids orphaning a sibling input's only output.
            # A sweep declared over this now-sourced input is dropped below. LAW VI kill-switch.
            if _dual_tag_failsoft_enabled():
                is_modeled = False
                reclassified_sourced.add(name)
                logger.info(
                    "[tradeoff_modeler] fail-soft: input %r tagged BOTH modeled and sourced "
                    "-> re-grounded to its datapoint_ref (dropped spurious modeled flag); "
                    "keeping the rest of the spec", name,
                )
            else:
                return _reject(f"input_both_modeled_and_sourced:{name}")  # one category
        if not is_modeled and not has_ref:
            return _reject(f"input_neither_sourced_nor_modeled:{name}")  # (P7-9)

        if is_modeled:
            try:
                base = float(ri["base"])
                unit = str(ri.get("unit", ""))
                sweep = ri.get("sweep") or [0.0, 0.0, 0.0]
                lo, hi, step = float(sweep[0]), float(sweep[1]), float(sweep[2])
            except (KeyError, IndexError, TypeError, ValueError):
                return _reject(f"modeled_input_bad_fields:{name}")
            if not all(math.isfinite(x) for x in (base, lo, hi, step)):
                return _reject(f"modeled_input_non_finite:{name}")
            modeled.append(ModeledInput(name, base, unit, lo, hi, step))
            continue

        # ── sourced: exact-one-match identity + literal+span derivation ──────
        ref = ri["datapoint_ref"]
        if not isinstance(ref, dict):
            return _reject(f"datapoint_ref_not_dict:{name}")
        cand = [dp for dp in sourced_numbers if _matches_datapoint(ref, dp)]
        if len(cand) != 1:                                   # (i) exact-one-match
            return _reject(f"datapoint_ref_matched_{len(cand)}:{name}")
        dp = cand[0]
        try:
            value = float(dp["value"])
        except (KeyError, TypeError, ValueError):
            return _reject(f"datapoint_value_unparseable:{name}")
        unit = str(dp.get("unit", ""))
        ev_id = str(dp.get("evidence_id", ""))
        ev_row = evidence_rows.get(ev_id)
        if not isinstance(ev_row, dict):
            return _reject(f"evidence_row_missing:{name}:{ev_id}")
        ev_text = _evidence_text(ev_row)
        located = _locate_unique_literal(ev_text, value)
        if located is None:                                  # (i) literal+span
            # F2 (#1344): literal non-unique in full ev_text (e.g. "15%" x3). Disambiguate
            # via the datapoint context window, but TRANSLATE context-relative offsets into
            # the ev_text frame so literal_start/end index the SAME string every consumer reads.
            ctx = str(dp.get("context", ""))
            ctx_located = _locate_unique_literal(ctx, value)
            if ctx_located is not None and ev_text and ctx:
                anchor = ev_text.find(ctx)
                if anchor >= 0 and ev_text.find(ctx, anchor + 1) == -1:   # context unique => unambiguous
                    _lit, _cs, _ce = ctx_located
                    if ev_text[anchor + _cs: anchor + _ce] == _lit:
                        located = (_lit, anchor + _cs, anchor + _ce)
        if located is None:
            return _reject(f"no_unique_literal_span:{name}:{ev_id}")
        literal, lstart, lend = located
        # T4 (#1344): fail-closed literal_span invariant. The derived [lstart, lend] MUST slice
        # ev_text back to exactly ``literal``; a frame-drifted offset (span landing inside an
        # unrelated token, e.g. a surname) is a citation-accuracy defect. Reject rather than emit a
        # span that does not contain its own literal. Faithfulness-STRENGTHENING; the SAME ev_text
        # frame every consumer reads (_evidence_text) is checked here, so the on-disk literal_span
        # is provably faithful. Kill-switch keeps it enforceable/disable-able (LAW VI).
        if _literal_span_enforce_enabled() and not literal_span_is_faithful(
            ev_text, literal, lstart, lend
        ):
            return _reject(f"literal_span_frame_drift:{name}:{ev_id}")
        sourced.append(SourcedInput(
            name=name, value=value, unit=unit, ev_id=ev_id,
            label=str(dp.get("label", "")), context=str(dp.get("context", "")),
            raw_literal=literal, literal_start=lstart, literal_end=lend,
        ))

    if not sourced and not modeled:
        return _reject("no_inputs")
    allowed = set(seen_names)

    # ── I-wire-014 (#1336): inline output->output formula references ─────────
    # The Writer chains outputs (cumulative = net_shift * decades, net_shift =
    # ag - prof). Substitute each referenced output's parenthesized formula so every
    # output formula is pure over INPUT names before the per-output AST gate below.
    # Value-preserving + deterministic; rejects cyclic/self references as formula_invalid.
    inlined_outputs, _inline_reason = _inline_output_references(raw_outputs, allowed)
    if inlined_outputs is None:
        return _reject(_inline_reason)
    raw_outputs = inlined_outputs

    # ── outputs: pure-arithmetic AST + display_kind ─────────────────────────
    outputs: list[OutputField] = []
    out_names: set[str] = set()
    output_refs: dict[str, set[str]] = {}
    for ro in raw_outputs:
        if not isinstance(ro, dict):
            return _reject("output_not_dict")
        oname = str(ro.get("name", "")).strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", oname or "") or oname in out_names:
            return _reject(f"bad_or_dup_output_name:{oname!r}")
        out_names.add(oname)
        display_kind = str(ro.get("display_kind", "number"))
        if display_kind not in _DISPLAY_KINDS:
            return _reject(f"bad_display_kind:{oname}:{display_kind}")
        formula = str(ro.get("formula", "")).strip()
        ok, reason, refs = _formula_names(formula, allowed)   # (ii)
        if not ok:
            return _reject(f"formula_invalid:{oname}:{reason}")
        output_refs[oname] = refs
        outputs.append(OutputField(oname, str(ro.get("unit", "")), display_kind, formula))

    # ── I-fix-001: prune UNREFERENCED modeled assumptions (NOT fatal) ───────
    # The GLM-5.2 / deepseek-v4-pro Writer routinely declares a scenario
    # coefficient (e.g. coef_low / coef_medium / coef_high) as a modeled input
    # but wires only some of them into the output formulas. The all-or-nothing
    # material-dependency gate below then rejected the ENTIRE otherwise-valid
    # spec because one stray coefficient "materially affects NO output" (captured
    # on a run: the single reject 'coef_medium materially affects NO output').
    # A MODELED input carries NO evidence citation and an UNREFERENCED one is
    # never rendered or labeled, so dropping it changes NO rendered number —
    # faithfulness-neutral. Only UNREFERENCED modeled inputs are safe to drop (a
    # referenced name is needed by a formula and cannot be removed); a non-
    # affecting SOURCED input stays FATAL in the gate below (a cited number that
    # does nothing is a misleading citation), as does a referenced-but-canceling
    # input of either kind. Byte-identical when every modeled input is referenced.
    referenced_by_formula: set[str] = set()
    for _refs in output_refs.values():
        referenced_by_formula |= _refs
    pruned_modeled_names = {
        m.name for m in modeled if m.name not in referenced_by_formula
    }
    if pruned_modeled_names:
        for _nm in sorted(pruned_modeled_names):
            logger.info(
                "[tradeoff_modeler] prune unused modeled assumption %r "
                "(referenced by no output formula) — keeping the rest of the spec",
                _nm,
            )
        modeled = [m for m in modeled if m.name not in pruned_modeled_names]
        seen_names -= pruned_modeled_names
        allowed = set(seen_names)
        if not sourced and not modeled:
            return _reject("no_inputs_after_prune")

    # ── (iii) NUMERIC material dependency — the PRIMARY gate ────────────────
    # Every declared input must move >=1 output under perturbation at a
    # non-degenerate point. Rejects canceling/zero-effect formulas
    # (x - x + y, irrelevant*0 + y) that cite a non-affecting input.
    base_env = {i.name: float(i.value) for i in sourced}
    base_env.update({i.name: float(i.base) for i in modeled})
    try:
        base_out = {o.name: _eval_formula(o.formula, base_env) for o in outputs}
    except (ValueError, ZeroDivisionError, OverflowError) as exc:
        return _reject(f"base_eval_failed:{str(exc)[:80]}")
    if not all(math.isfinite(v) for v in base_out.values()):
        return _reject("base_output_non_finite")
    for nm in allowed:
        bval = base_env[nm]
        perturbed = bval * (1.0 + _DEPENDENCY_PERTURB_DELTA) if bval != 0 else 1.0
        if perturbed == bval:
            perturbed = bval + 1.0
        env2 = dict(base_env)
        env2[nm] = perturbed
        moved = False
        for o in outputs:
            try:
                v2 = _eval_formula(o.formula, env2)
            except (ValueError, ZeroDivisionError, OverflowError):
                continue
            b = base_out[o.name]
            if not math.isclose(
                v2, b,
                rel_tol=_DEPENDENCY_EFFECT_REL_TOL, abs_tol=_DEPENDENCY_EFFECT_ABS_TOL,
            ):
                moved = True
                break
        if not moved:
            # I-fix-001: unreferenced modeled inputs were pruned above, so anything
            # that reaches here and affects no output is either a SOURCED input
            # (misleading citation) or a referenced-but-canceling input — both FATAL.
            return _reject(
                f"non_affecting_input:{nm}"  # canceling/zero-effect dependency
            )

    # ── (v) sensitivity well-formedness ─────────────────────────────────────
    modeled_names = {m.name for m in modeled}
    sensitivity: list[Sensitivity] = []
    for rs in (raw.get("sensitivity") or []):
        if not isinstance(rs, dict):
            return _reject("sensitivity_not_dict")
        sin = str(rs.get("input", ""))
        sout = str(rs.get("output", ""))
        # I-fix-001: a sweep over a PRUNED unused modeled assumption is meaningless
        # (the variable is in no formula) — drop the sensitivity, do not reject.
        # V5 (#1344): a sweep over a RE-GROUNDED sourced input is equally meaningless
        # (a measured citation is not a swept assumption) — drop it, do not reject.
        if sin in pruned_modeled_names or sin in reclassified_sourced:
            logger.info(
                "[tradeoff_modeler] drop sensitivity over %s input %r",
                "pruned modeled" if sin in pruned_modeled_names else "re-grounded sourced",
                sin,
            )
            continue
        if sin not in modeled_names or sout not in out_names:
            return _reject(f"sensitivity_bad_input_or_output:{sin}:{sout}")
        m = next(mm for mm in modeled if mm.name == sin)
        if m.sweep_step == 0 or not math.isfinite(m.sweep_step):
            return _reject(f"sensitivity_bad_step:{sin}")
        if (m.sweep_hi - m.sweep_lo) * m.sweep_step <= 0:
            return _reject(f"sensitivity_step_wrong_direction:{sin}")  # lo -> hi
        sensitivity.append(Sensitivity(sin, sout))

    # ── (vi) solve_for well-formedness ──────────────────────────────────────
    solve_for: SolveFor | None = None
    rsolve = raw.get("solve_for")
    if isinstance(rsolve, dict) and rsolve:
        var = str(rsolve.get("var", ""))
        out = str(rsolve.get("output", ""))
        # I-fix-001: a break-even solve over a PRUNED unused modeled assumption is
        # meaningless — drop the solve_for, do not reject the whole spec.
        # V5 (#1344): a break-even solve over a RE-GROUNDED sourced input is likewise
        # meaningless (you do not solve for a measured citation) — drop it, do not reject.
        if var in pruned_modeled_names or var in reclassified_sourced:
            logger.info(
                "[tradeoff_modeler] drop solve_for over %s input %r",
                "pruned modeled" if var in pruned_modeled_names else "re-grounded sourced",
                var,
            )
        elif var not in modeled_names or out not in out_names:
            return _reject(f"solve_for_bad_var_or_output:{var}:{out}")
        else:
            solve_for = SolveFor(var, out)

    spec_hash = _spec_hash(model_id, sourced, modeled, outputs, sensitivity, solve_for)
    spec = ModelSpec(
        model_id=model_id, title=title, sourced_inputs=sourced,
        modeled_inputs=modeled, outputs=outputs, sensitivity=sensitivity,
        solve_for=solve_for, spec_hash=spec_hash,
    )
    # carry per-output referenced-input sets for binding/labeling
    spec_output_refs = output_refs  # noqa: F841 (kept for callers via helper below)
    _OUTPUT_REFS_CACHE[(model_id, spec_hash)] = output_refs
    return spec


# Per-(model_id, spec_hash) cache of {output_name -> set(referenced input names)}.
# Populated at build time; read by the executor to compute each field's
# modeled/sourced "used" sets without re-parsing formulas.
_OUTPUT_REFS_CACHE: dict[tuple[str, str], dict[str, set[str]]] = {}


def output_referenced_inputs(spec: ModelSpec, output_name: str) -> set[str]:
    """Input names referenced by ``output_name``'s formula (perturb-verified to
    materially affect it). Falls back to a fresh parse if not cached."""
    cached = _OUTPUT_REFS_CACHE.get((spec.model_id, spec.spec_hash))
    if cached is not None and output_name in cached:
        return set(cached[output_name])
    o = spec.output_by_name(output_name)
    if o is None:
        return set()
    _ok, _r, refs = _formula_names(o.formula, set(spec.input_names()))
    return refs


# ─────────────────────────────────────────────────────────────────────────────
# Deterministic Execute template (NO LLM codegen)
# ─────────────────────────────────────────────────────────────────────────────
def _fmt_sweep_x(x: float) -> str:
    """Stable label for a swept value — same string on both the script side
    (field key) and the binder side (token field)."""
    return f"{float(x):.6g}"


def sweep_grid(m: ModeledInput) -> list[float]:
    """The inclusive lo..hi grid (step-spaced) for a modeled input."""
    pts: list[float] = []
    n = int(round((m.sweep_hi - m.sweep_lo) / m.sweep_step))
    for k in range(max(n, 0) + 1):
        pts.append(m.sweep_lo + k * m.sweep_step)
    if not pts:
        pts = [m.sweep_lo]
    return pts


def render_script(spec: ModelSpec) -> str:
    """Template the validated spec into a FIXED Python skeleton that computes and
    prints every field. Deterministic — no codegen LLM. Every printed number is
    the declared output formula over the declared inputs.
    """
    lines: list[str] = ["import json"]
    if spec.solve_for is not None:
        lines.append("from scipy.optimize import brentq")
    lines.append(
        "from math import sqrt, log, log10, log2, exp, sin, cos, tan, floor, ceil"
    )
    lines.append("")
    # one function per output, signature = ALL input names (stable order)
    all_names = spec.input_names()
    sig = ", ".join(all_names)
    for o in spec.outputs:
        lines.append(f"def _f_{o.name}({sig}):")
        lines.append(f"    return ({o.formula})")
    lines.append("")
    # base input values (sourced.value | modeled.base)
    for s in spec.sourced_inputs:
        lines.append(f"{s.name} = {float(s.value)!r}")
    for m in spec.modeled_inputs:
        lines.append(f"{m.name} = {float(m.base)!r}")
    lines.append("")
    lines.append("_outputs = {}")
    for o in spec.outputs:
        call = ", ".join(all_names)
        lines.append(f"_outputs[{o.name!r}] = _f_{o.name}({call})")
    lines.append("")
    lines.append("_sensitivity = {}")
    for s in spec.sensitivity:
        m = spec.modeled_by_name(s.input)
        if m is None:
            continue
        grid = sweep_grid(m)
        pairs = ", ".join(
            f"({_fmt_sweep_x(x)!r}, {float(x)!r})" for x in grid
        )
        lines.append(f"for _xl, _xv in [{pairs}]:")
        callargs = ", ".join(
            ("_xv" if nm == s.input else nm) for nm in all_names
        )
        key_prefix = f"{s.output}@{s.input}="
        lines.append(
            f"    _sensitivity[{key_prefix!r} + _xl] = _f_{s.output}({callargs})"
        )
    lines.append("")
    lines.append("_break_even = {}")
    if spec.solve_for is not None:
        sf = spec.solve_for
        m = spec.modeled_by_name(sf.var)
        if m is not None:
            callargs = ", ".join(
                ("_v" if nm == sf.var else nm) for nm in all_names
            )
            lines.append(f"def _g(_v):")
            lines.append(f"    return _f_{sf.output}({callargs})")
            lines.append(f"_lo, _hi = {float(m.sweep_lo)!r}, {float(m.sweep_hi)!r}")
            lines.append("try:")
            lines.append("    _flo, _fhi = _g(_lo), _g(_hi)")
            lines.append("    if _flo == 0:")
            lines.append(f"        _break_even[{sf.output + '.break_even'!r}] = _lo")
            lines.append("    elif _fhi == 0:")
            lines.append(f"        _break_even[{sf.output + '.break_even'!r}] = _hi")
            lines.append("    elif (_flo < 0) != (_fhi < 0):")
            lines.append("        _root = brentq(_g, _lo, _hi)")
            lines.append(f"        _break_even[{sf.output + '.break_even'!r}] = _root")
            lines.append("except (ValueError, RuntimeError):")
            lines.append("    pass")
    lines.append("")
    lines.append(
        "print(json.dumps({'outputs': _outputs, 'sensitivity': _sensitivity, "
        "'break_even': _break_even}))"
    )
    return "\n".join(lines) + "\n"
