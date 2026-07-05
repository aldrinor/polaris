"""I-meta-005 Phase 7 (#991) — Quantified analysis executor + binder (gap 9).

Owns the **Execute** (run the deterministic script in the existing sandbox) and
**Bind** (attach one calc token per rendered computed number) stages of the
Extract -> Model -> Execute -> Bind -> Verify pipeline.

``execute_quantified_model`` renders the validated spec to a FIXED Python script
(``tradeoff_modeler.render_script`` — no codegen LLM), runs it via the EXISTING
``code_executor.execute_analysis_script`` (sandbox unchanged), and pins each
computed field's canonical ``display_value`` (via the ONE shared
``_canonical_display``) so Regime C verification is an exact-string equality plus
a numeric backstop, and so the spec replays deterministically (gap-19).

The ``QuantifiedResult`` it returns is intentionally self-describing with plain
data (no tradeoff_modeler dataclasses leak into the verifier): each field carries
``value`` / ``display_value`` / ``modeled_used`` (names that must be labeled
"(modeled assumption)") / ``sourced_tokens`` (the evidence spans Regime C returns
so resolve_provenance_to_citations cites the inputs).

SPEND-FREE: deterministic render + sandbox execution of FIXED Python; no network.
"""
from __future__ import annotations

import ast
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

from src.polaris_graph.synthesis.tradeoff_modeler import (
    ModelSpec,
    _canonical_display,
    output_referenced_inputs,
)
from src.polaris_graph.tools.code_executor import execute_analysis_script

logger = logging.getLogger(__name__)

# ``{{calc:<field>}}`` placeholder the Writer/section template emits where a
# computed number should be rendered + bound.
_CALC_PLACEHOLDER_RE = re.compile(r"\{\{calc:(?P<field>[^}]+)\}\}")

# Two extracted datapoints describing the SAME quantity (same label + unit) whose
# values disagree by more than this are a sourced-input conflict — surfaced in
# manifest telemetry so the operator sees the corpus contradiction (named, Law VI).
_CALC_CONFLICT_REL_TOL = float(os.environ.get("PG_CALC_CONFLICT_REL_TOL", "0.05"))

# I-pipe-012 (#1237): typed-status discrimination for the quantified differentiator.
# The pre-fix function returned a bare ``None`` at three distinct death points
# (spec_provider raised / returned non-dict / build_quantified_spec rejected /
# execution failed / no verified sentences) that a caller could only tell apart by
# scraping the free-text log. ``telem["quantified_status"]`` is the discrete, machine-
# readable verdict so a post-run audit can separate "no numbers to model" (decline)
# from "the differentiator silently broke" (transport/parse failure). The success path
# stamps ``ok``. None of these statuses changes a VERIFIED claim — they only label WHY
# the (already strict_verify/Regime-C-gated) section did or did not land.
QUANTIFIED_STATUS_OK = "ok"                       # spec validated, executed, ≥1 sentence survived Regime C
QUANTIFIED_STATUS_DECLINED_NO_SPEC = "declined_no_spec"  # Writer returned no dict (decline OR collapsed transport — see cross-file)
QUANTIFIED_STATUS_EMPTY_TRANSPORT = "empty_transport"    # reserved: a true empty-200/404 transport miss (only reachable once the caller stops collapsing it into None — see cross_file_deferred)
QUANTIFIED_STATUS_PARSE_ERROR = "parse_error"     # spec_provider RAISED, or emitted a dict that failed hard validation / execution

# Kill-switch (LAW VI): default-ON typed-status + bounded transient retry. Set to
# "0"/"false" to REVERT to the pre-fix behavior — a bare ``None`` return with NO
# ``quantified_status`` key added to telem and a SINGLE spec_provider call (no retry).
_TYPED_STATUS_ENABLED = os.environ.get("PG_QUANTIFIED_TYPED_STATUS", "1").strip().lower() not in (
    "0", "false", "no", "off",
)

# Bounded retries for a TRANSIENT spec_provider transport/parse failure (the RAISED
# path only — a non-dict return is a Writer DECLINE, never retried; re-billing a
# decline is waste). Total attempts = 1 + retries. Default 1 retry (2 attempts).
_SPEC_PROVIDER_RETRIES = max(0, int(os.environ.get("PG_QUANTIFIED_SPEC_RETRIES", "1")))

# FIX-2 (#1344) — quantified filler suppression (LAW VI kill-switch, default-ON).
# Withholds invented unit-free scalar OUTPUTS that merely relate >=2 distinct sourced
# inputs (e.g. "displacement productivity ratio 2.14286", "restructuring efficiency 5",
# "net job shift 1" — dimensionless numbers built by dividing unrelated percentages from
# different studies x a free scaling_factor). FLAG/withhold-not-faithfulness: a dimensioned
# result (currency/percent/count, or a transform of a single sourced number) passes through,
# nothing in the corpus/bibliography is dropped, and the faithfulness engine is untouched.
# Set PG_QUANTIFIED_FILLER_SUPPRESS=0 to revert to byte-identical legacy rendering.
_FILLER_SUPPRESS_ENABLED = os.environ.get(
    "PG_QUANTIFIED_FILLER_SUPPRESS", "1"
).strip().lower() not in ("0", "false", "no", "off")
_DIMENSIONLESS_DISPLAY_KINDS = frozenset({"number", "ratio"})
_FILLER_MIN_SOURCED_INPUTS = max(
    2, int(os.environ.get("PG_QUANTIFIED_FILLER_MIN_SOURCED", "2"))
)


# U27 (#1344) — Writer-shortlist curation (LAW VI kill-switch, default-ON).
# The quantified-spec Writer (the ONLY billed step) previously received the FIRST
# N extracted datapoints in raw evidence-pool iteration order (`sourced[:N]` in the
# run_honest_sweep_r3.py `_q_spec_provider` closure). On real large clinical corpora
# the LEADING datapoints are scrape chrome / binary garbage — PDF object offsets
# ("%PDF- 13 0 obj"), base64 auth blobs, CDN image dimensions ("382x200px" parsed as
# 204669%), and phone numbers ("tel:080 4669 4311") — so the Writer was handed an
# incoherent, absurd-valued set and correctly returned {"model_id":"none"} (->
# no_spec_returned), even though many clean modelable clinical numbers (2.5%
# infections, carbidopa bioavailability 99%, levodopa AUC +55%, half-life 1.5h) sat
# buried deeper in the list. This curates the shortlist so clean, well-labeled,
# plausibly-valued datapoints reach the Writer instead of raw iteration-order junk.
#
# INPUT HYGIENE, NOT a faithfulness filter (faithfulness_risk: neutral): the FULL
# extracted pool still flows to build_quantified_spec for datapoint matching, no
# source is dropped, and every downstream gate (strict_verify / Regime C / provenance)
# is untouched. Set PG_QUANTIFIED_SHORTLIST_CLEAN=0 to REVERT to byte-identical
# ``sourced[:N]`` (no curation, no added telemetry).
_SHORTLIST_CLEAN_ENABLED = os.environ.get(
    "PG_QUANTIFIED_SHORTLIST_CLEAN", "1"
).strip().lower() not in ("0", "false", "no", "off")

# Absolute ceiling on a plausible percentage magnitude. Junk CDN dims / phone numbers
# parse as 5-6 digit "percentages" (204669%, 82972%, 206921%); real clinical/economic
# percentages sit far below this generous cap (the clean drb_78 max is 99%). LAW VI
# env-tunable — a CAP, not a target; it only ever REMOVES a garbage candidate.
_SHORTLIST_MAX_PCT = float(os.environ.get("PG_QUANTIFIED_SHORTLIST_MAX_PCT", "1000"))

# Substrings whose presence in a datapoint's label OR context marks it as scrape
# chrome / binary / markup garbage rather than a modelable clinical/economic number:
# URL schemes, markdown link/image syntax, tel:/mailto: links, PDF-binary markers,
# HTML entities, CDN crop params, and the Unicode replacement char (binary noise).
_SHORTLIST_JUNK_MARKERS = (
    "http://", "https://", "www.", "](", "![", "tel:", "mailto:",
    "%pdf", "endobj", "endstream", "/bbox", "/length", "xref",
    "&amp;", "&#", "crop=fp", "fp_zoom", "cdn-assets", "�",
)
# I-deepfix-001 U27 iter2 (Codex): the bare substrings " obj" and "stream" were REMOVED — they
# false-positived on ordinary clinical prose (" objective", "bloodstream") and would wrongly drop
# valid numbers, falsely triggering `no_modelable_numbers`. PDF binary junk is now caught by the
# UNAMBIGUOUS keywords above (endobj/endstream/%pdf/xref//length//bbox) plus a PRECISE PDF
# object-header regex ("13 0 obj") below — none of which occur in clinical/economic prose.
_SHORTLIST_PDF_OBJ_RE = re.compile(r"\b\d+\s+\d+\s+obj\b")
# A long unbroken alphanumeric run = base64 auth blob / hash / accession, never prose
# (English words / clinical labels break well under this length).
_SHORTLIST_BASE64_RE = re.compile(r"[A-Za-z0-9+/]{24,}")


def is_junk_modelable_datapoint(datapoint: dict[str, Any]) -> bool:
    """True iff ``datapoint`` is scrape-chrome / binary / markup garbage that must
    NOT be offered to the quantified-spec Writer (U27, #1344).

    Deterministic, offline, faithfulness-neutral: this only decides whether a
    candidate NUMBER is coherent enough to put in front of the (billed) spec LLM. It
    NEVER drops a source and NEVER touches a verification gate — the full extracted
    pool still flows to ``build_quantified_spec`` for datapoint matching. When the
    kill-switch is OFF it is never consulted (see ``select_writer_candidate_numbers``).

    A datapoint is junk when ANY of: (1) it has no label (nothing to reason over);
    (2) its label or context contains a URL / markdown-link / image / tel / PDF-binary
    / HTML-entity / CDN chrome marker; (3) its label or context contains a long
    unbroken alphanumeric run (base64 blob / hash / accession); (4) its unit is a
    percentage but the value exceeds the plausible-percentage ceiling.
    """
    label = str(datapoint.get("label") or "")
    context = str(datapoint.get("context") or "")
    hay = f"{label}\n{context}".lower()

    # (1) empty label — no describable quantity for the Writer.
    if not label.strip():
        return True
    # (2) URL / markdown-link / image / tel / PDF-binary / HTML-entity / CDN chrome.
    for marker in _SHORTLIST_JUNK_MARKERS:
        if marker in hay:
            return True
    # PDF object header ("13 0 obj") — precise, does not match "objective"/other prose.
    if _SHORTLIST_PDF_OBJ_RE.search(hay):
        return True
    # (3) base64 auth blob / hash / accession (a long unbroken alphanumeric run).
    if _SHORTLIST_BASE64_RE.search(label) or _SHORTLIST_BASE64_RE.search(context):
        return True
    # (4) an absurd percentage magnitude (CDN dims / phone numbers parsed as %); a
    #     non-numeric "value" under a % unit is itself garbage.
    unit = str(datapoint.get("unit") or "").strip()
    if unit in ("%", "percent"):
        try:
            if abs(float(datapoint.get("value"))) > _SHORTLIST_MAX_PCT:
                return True
        except (TypeError, ValueError):
            return True
    return False


def select_writer_candidate_numbers(
    datapoints: list[dict[str, Any]], *, limit: int | None = None,
) -> list[dict[str, Any]]:
    """Curate the quantified-spec Writer shortlist (U27, #1344).

    Returns the first ``limit`` CLEAN datapoints (junk dropped by
    ``is_junk_modelable_datapoint``), preserving the input order so the result is
    deterministic (same input -> same output, byte-for-byte). ``limit=None`` returns
    every clean datapoint.

    With ``PG_QUANTIFIED_SHORTLIST_CLEAN=0`` (kill-switch OFF) this is byte-identical
    to ``datapoints[:limit]`` — the legacy unranked/unfiltered slice — so a revert is
    a pure no-op. Faithfulness-neutral: this only orders/filters the LLM's INPUT
    shortlist; the full pool is still used downstream for datapoint matching.
    """
    if not _SHORTLIST_CLEAN_ENABLED:
        return datapoints[:limit] if limit is not None else list(datapoints)
    clean = [dp for dp in datapoints if not is_junk_modelable_datapoint(dp)]
    return clean[:limit] if limit is not None else clean


def is_low_value_filler_output(field: dict[str, Any]) -> bool:
    """True iff ``field`` is a unit-free number/ratio scalar relating >=2 distinct
    sourced inputs — the invented-filler signature. Counts sourced INPUTS (not ev_ids),
    so "3% - 2%" from the SAME source is still caught. A dimensioned result, a non-
    number/ratio display kind, or a scalar over <2 sourced inputs is NOT filler."""
    if not _FILLER_SUPPRESS_ENABLED:
        return False
    if str(field.get("unit") or "").strip():
        return False
    if str(field.get("display_kind") or "number") not in _DIMENSIONLESS_DISPLAY_KINDS:
        return False
    n_sourced = sum(
        1 for t in (field.get("sourced_tokens") or []) if isinstance(t, dict)
    )
    return n_sourced >= _FILLER_MIN_SOURCED_INPUTS


# ── FINDING #4 (I-deepfix-001 tail B3, #1344) — unit-compatibility + cited-operand
#    gate for composed quantified quantities (LAW VI kill-switch, default ON) ──────
# THE DEFECT (drb_72 forensic rank 4): the modeler emitted
#   "The wage to employment impact ratio is 2.1.[4]"
# — a pipeline division ``0.42% / 0.2 percentage-points`` rendered with a PRIMARY
# citation as if the source stated it. Two independent faults:
#   (b) it divides a PERCENT by a PERCENTAGE-POINT — incompatible units in the SAME
#       dimension (both proportions) — so the resulting dimensionless "ratio" is
#       dimensionally MEANINGLESS; and
#   (a) it is a computed number attributed to a source that never states it.
# The FIX-2 filler suppressor above only withholds unit-FREE scalars over >=2 sourced
# inputs; it does NOT check unit COMPATIBILITY (a percent-/currency-typed output that
# divides %/pp escapes it) and does not gate a ratio that mixes a cited number with an
# uncited (modeled) assumption. This gate is the precise dimensional-validity +
# cited-operand check the finding asks for.
#
# FAITHFULNESS (LAW §-1.3): a RENDER-ONLY withhold at the composition seam (same
# category as FIX-2). A withheld output stays in the spec + quantified_model.json; NO
# source, corpus row, basket, or verified claim is dropped; strict_verify / Regime C /
# NLI / the 4-role D8 engine are untouched. It never adds a cap/target/thinner — it only
# refuses to RENDER a dimensionally-invalid or non-cited computed number. Set
# ``PG_QUANTIFIED_UNIT_COMPAT=0`` to REVERT byte-identically.
_UNIT_COMPAT_ENABLED = os.environ.get(
    "PG_QUANTIFIED_UNIT_COMPAT", "1"
).strip().lower() not in ("0", "false", "no", "off")

# A dimensionless output (empty unit) declared as one of these kinds is a "ratio" in the
# plain sense — its operands' units are supposed to CANCEL. Dividing incompatible units
# and calling the result dimensionless is exactly the finding's category error.
_RATIO_DISPLAY_KINDS = frozenset({"number", "ratio"})

# Unit classes that share a DIMENSION but must NOT be divided into a dimensionless ratio
# (their ratio is semantically meaningless). Members of the SAME family divided by each
# other are ratio-incompatible; DIFFERENT families divided (e.g. currency / time = a
# legitimate rate) are ALLOWED. Extend via config, never a hardcoded per-run target.
_UNIT_FAMILY = {"percent": "proportion", "percentage_point": "proportion"}


def _unit_class(unit: Any) -> str | None:
    """Normalize a raw unit string to a coarse unit CLASS, or ``None`` for a neutral /
    dimensionless / unknown unit (an empty unit, or one we do not recognize — treated as
    neutral so it never triggers a false incompatibility). PURE, offline."""
    u = str(unit or "").strip().lower().rstrip(". ")
    if not u:
        return None
    if u in {"%", "percent", "percentage", "percentages", "pct", "per cent"}:
        return "percent"
    if u in {
        "pp", "ppt", "ppts", "pps", "pctpt", "pct pt", "pct pts",
        "percentage point", "percentage points",
        "percentage-point", "percentage-points",
    }:
        return "percentage_point"
    if u in {"$", "usd", "us$", "dollar", "dollars"}:
        return "currency_usd"
    if u in {"€", "eur", "euro", "euros"}:
        return "currency_eur"
    if u in {"£", "gbp", "pound", "pounds"}:
        return "currency_gbp"
    return u


def _ratio_incompatible(a: str | None, b: str | None) -> bool:
    """True iff dividing a class-``a`` operand by a class-``b`` operand yields a
    dimensionally-meaningless ratio: two DIFFERENT members of the SAME unit family
    (e.g. percent / percentage-point). Neutral (None) operands never trigger it."""
    if a is None or b is None or a == b:
        return False
    fam_a = _UNIT_FAMILY.get(a)
    return fam_a is not None and fam_a == _UNIT_FAMILY.get(b)


def formula_units_incompatible(formula: str, unit_class_by_name: dict[str, str | None]) -> bool:
    """True iff ``formula`` combines incompatible units anywhere in its AST:

    * an ``Add`` / ``Sub`` of two DIFFERENT non-neutral unit classes (adding across
      classes is never valid — you cannot add dollars to years), OR
    * a ``Div`` of two DIFFERENT members of the SAME unit family (a meaningless
      same-dimension ratio, e.g. percent / percentage-point).

    Multiplication and cross-family division (a legitimate rate, e.g. currency / time)
    are ALLOWED. PURE + offline; an unparseable formula is treated as NOT-incompatible
    (fail-open — never a false drop on a formula we cannot analyze)."""
    try:
        tree = ast.parse(str(formula or ""), mode="eval")
    except SyntaxError:
        return False
    bad = False

    def _classes(node: ast.AST) -> set[str]:
        """Return the set of non-neutral unit classes among ``node``'s leaves; set the
        enclosing ``bad`` flag on any incompatible combination."""
        nonlocal bad
        if isinstance(node, ast.Expression):
            return _classes(node.body)
        if isinstance(node, ast.Name):
            c = unit_class_by_name.get(node.id)
            return {c} if c is not None else set()
        if isinstance(node, ast.Constant):
            return set()
        if isinstance(node, ast.UnaryOp):
            return _classes(node.operand)
        if isinstance(node, ast.BinOp):
            left = _classes(node.left)
            right = _classes(node.right)
            op = node.op
            if isinstance(op, (ast.Add, ast.Sub)):
                combined = left | right
                if len({c for c in combined if c is not None}) >= 2:
                    bad = True
                return combined
            if isinstance(op, ast.Div):
                if len(left) == 1 and len(right) == 1:
                    (lc,) = tuple(left)
                    (rc,) = tuple(right)
                    if _ratio_incompatible(lc, rc):
                        bad = True
                    if lc == rc:
                        return set()  # same class -> units cancel -> dimensionless
                return left | right
            # Mult / Pow / Mod / FloorDiv -> product/other; allowed to mix classes.
            return left | right
        if isinstance(node, ast.Call):
            out: set[str] = set()
            for a in node.args:
                out |= _classes(a)
            # abs/min/max/round preserve the operand class; other funcs (sqrt/log/exp/…)
            # take a dimensionless argument -> a dimensionless result.
            if getattr(node.func, "id", "") in {"abs", "min", "max", "round"}:
                return out
            return set()
        return set()

    _classes(tree)
    return bad


def _leaf_unit_classes(
    node: ast.AST, unit_class_by_name: dict[str, str | None]
) -> set[str]:
    """Set of the NON-NEUTRAL unit classes among ``node``'s operand leaves (a neutral /
    unknown / dimensionless leaf — an unrecognized unit or a bare constant — contributes
    nothing). PURE + offline. Used to test whether a division's numerator and denominator
    each resolve to one shared, cancelling unit class."""
    if isinstance(node, ast.Expression):
        return _leaf_unit_classes(node.body, unit_class_by_name)
    if isinstance(node, ast.Name):
        c = unit_class_by_name.get(node.id)
        return {c} if c is not None else set()
    if isinstance(node, ast.UnaryOp):
        return _leaf_unit_classes(node.operand, unit_class_by_name)
    if isinstance(node, ast.BinOp):
        return (
            _leaf_unit_classes(node.left, unit_class_by_name)
            | _leaf_unit_classes(node.right, unit_class_by_name)
        )
    if isinstance(node, ast.Call):
        out: set[str] = set()
        for a in node.args:
            out |= _leaf_unit_classes(a, unit_class_by_name)
        return out
    return set()


def _dimension_preserving_only(node: ast.AST) -> bool:
    """True iff ``node`` combines its leaves using ONLY dimension-PRESERVING operations
    (Add / Sub / unary +/- / abs / round / min / max) — no Mult / Div / Pow / Mod /
    FloorDiv, which would compound or cancel dimensions. So the node's overall dimension
    equals its single leaf unit class, which is precisely what makes a division of two
    such nodes a genuine units-cancel ratio. PURE + offline."""
    if isinstance(node, ast.Expression):
        return _dimension_preserving_only(node.body)
    if isinstance(node, (ast.Name, ast.Constant)):
        return True
    if isinstance(node, ast.UnaryOp):
        return _dimension_preserving_only(node.operand)
    if isinstance(node, ast.BinOp):
        if not isinstance(node.op, (ast.Add, ast.Sub)):
            return False
        return (
            _dimension_preserving_only(node.left)
            and _dimension_preserving_only(node.right)
        )
    if isinstance(node, ast.Call):
        if getattr(node.func, "id", "") not in {"abs", "min", "max", "round"}:
            return False
        return all(_dimension_preserving_only(a) for a in node.args)
    return False


def formula_is_same_unit_cancelling_ratio(
    formula: str, unit_class_by_name: dict[str, str | None]
) -> bool:
    """True iff ``formula``'s dimensionless value is PRODUCED by a genuine same-unit
    cancelling division: the top-level operation is a ``Div`` whose numerator and
    denominator EACH resolve to the SAME single NON-NEUTRAL unit class (so the units
    cancel to dimensionless — e.g. ``a / b`` over two USD amounts).

    A SUM / DIFFERENCE / PRODUCT (``a + b`` / ``a - b`` / ``a * b``), a division whose
    two operands do NOT share exactly one non-neutral class (``percent / percentage-point``
    or ``currency / years``), or a division whose operands themselves compound dimensions
    (contain Mult / Div / Pow, e.g. ``a * b / c``) does NOT qualify. An unparseable
    formula is NOT a cancelling ratio (fail-CLOSED for the exemption — defer to the FIX-2
    filler suppressor). PURE + offline; mirrors ``formula_units_incompatible``'s AST view."""
    try:
        tree = ast.parse(str(formula or ""), mode="eval")
    except SyntaxError:
        return False
    node: ast.AST = tree.body if isinstance(tree, ast.Expression) else tree
    # Peel dimension-preserving unary/abs/round wrappers around the top division.
    while True:
        if isinstance(node, ast.UnaryOp):
            node = node.operand
            continue
        if (
            isinstance(node, ast.Call)
            and getattr(node.func, "id", "") in {"abs", "round"}
            and node.args
        ):
            node = node.args[0]
            continue
        break
    if not (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)):
        return False
    if not (
        _dimension_preserving_only(node.left)
        and _dimension_preserving_only(node.right)
    ):
        return False
    left = _leaf_unit_classes(node.left, unit_class_by_name)
    right = _leaf_unit_classes(node.right, unit_class_by_name)
    if len(left) != 1 or len(right) != 1:
        return False
    (lc,) = tuple(left)
    (rc,) = tuple(right)
    return lc is not None and lc == rc


def should_withhold_composed_output(output_field: Any, spec: Any) -> bool:
    """FINDING #4 composition-time drop decision for a single declared ``OutputField``.

    Returns True to WITHHOLD the output's rendered sentence when EITHER:
      (b) its formula combines incompatible units (``formula_units_incompatible``), OR
      (a) it is a dimensionless RATIO (empty unit, number/ratio kind) that MIXES a cited
          (sourced) operand with an uncited (modeled/assumed) operand — presenting an
          assumption-laden ratio as if the source stated it.

    Kill-switch OFF (``PG_QUANTIFIED_UNIT_COMPAT=0``) => always False (byte-identical).
    PURE except for the kill-switch read; no faithfulness gate is touched."""
    if not _UNIT_COMPAT_ENABLED:
        return False
    unit_class_by_name: dict[str, str | None] = {}
    kind_by_name: dict[str, str] = {}
    for s in spec.sourced_inputs:
        unit_class_by_name[s.name] = _unit_class(s.unit)
        kind_by_name[s.name] = "sourced"
    for m in spec.modeled_inputs:
        unit_class_by_name[m.name] = _unit_class(m.unit)
        kind_by_name[m.name] = "modeled"

    # (b) unit-incompatibility anywhere in the formula.
    if formula_units_incompatible(getattr(output_field, "formula", ""), unit_class_by_name):
        logger.info(
            "[quantified_analysis] FINDING#4 withhold %r: unit-incompatible formula %r",
            getattr(output_field, "name", "?"), getattr(output_field, "formula", ""),
        )
        return True

    # (a) a dimensionless ratio mixing a cited operand with an uncited (modeled) one.
    is_dimensionless_ratio = (
        not str(getattr(output_field, "unit", "") or "").strip()
        and str(getattr(output_field, "display_kind", "number") or "number")
        in _RATIO_DISPLAY_KINDS
    )
    if is_dimensionless_ratio:
        refs = output_referenced_inputs(spec, getattr(output_field, "name", ""))
        ref_kinds = {kind_by_name.get(r) for r in refs}
        if "sourced" in ref_kinds and "modeled" in ref_kinds:
            logger.info(
                "[quantified_analysis] FINDING#4 withhold %r: dimensionless ratio mixes "
                "a cited (sourced) operand with an uncited (modeled) assumption",
                getattr(output_field, "name", "?"),
            )
            return True
    return False


def is_valid_cited_ratio(output_field: Any, spec: Any) -> bool:
    """FINDING #4 iter-2 (#1344 tail B3): True iff ``output_field`` is a dimensionally-
    VALID, fully-CITED dimensionless ratio that the unit-compat gate has AFFIRMATIVELY
    cleared — a same-unit (units-cancel) ratio over sourced operands with NO modeled
    (uncited) operand.

    THE ITER-2 P1 FIX: such a quantity is legitimate and MUST render under production
    defaults. The older coarse FIX-2 filler-suppressor (``is_low_value_filler_output``)
    blanks EVERY unit-free number/ratio over >=2 sourced inputs and would wrongly blank a
    valid same-unit (e.g. USD/USD) cited ratio; the caller uses this predicate to let the
    unit-compat gate GOVERN that path so FIX-2 never blanks a valid cited ratio.

    Returns False (defers entirely to the legacy FIX-2 behaviour — byte-identical) when:
    the unit-compat gate is OFF; FINDING #4 would WITHHOLD the output (unit-mismatch or a
    cited+modeled mix); the output is not a dimensionless number/ratio; it references no
    cited (sourced) operand OR any modeled operand; OR — the ITER-3 P1 fix — its formula is
    not a GENUINE same-unit cancelling division (a dimensionless-declared SUM / DIFFERENCE /
    PRODUCT over cited operands is NOT a units-cancel ratio). PURE except for the kill-switch
    read; touches no faithfulness gate."""
    if not _UNIT_COMPAT_ENABLED:
        return False
    is_dimensionless_ratio = (
        not str(getattr(output_field, "unit", "") or "").strip()
        and str(getattr(output_field, "display_kind", "number") or "number")
        in _RATIO_DISPLAY_KINDS
    )
    if not is_dimensionless_ratio:
        return False
    # The unit-compat gate must have CLEARED it (compatible units, not a cited+modeled mix).
    if should_withhold_composed_output(output_field, spec):
        return False
    refs = output_referenced_inputs(spec, getattr(output_field, "name", ""))
    sourced_names = {s.name for s in spec.sourced_inputs}
    modeled_names = {m.name for m in spec.modeled_inputs}
    refs_sourced = any(r in sourced_names for r in refs)
    refs_modeled = any(r in modeled_names for r in refs)
    if not (refs_sourced and not refs_modeled):
        return False
    # ITER-3 P1 (Codex): the exemption from the FIX-2 filler suppressor is ONLY for a
    # GENUINE same-unit cancelling ratio — the formula's dimensionless value must arise
    # from a Div of two operands sharing one non-neutral unit class (units cancel). Without
    # this, ANY dimensionless-declared output over cited-only operands escaped FIX-2, so a
    # plain SUM ``a + b`` of two cited USD amounts (empty unit, display_kind="number") was
    # wrongly exempted and rendered — reopening the FIX-2 filler hole for non-ratio
    # dimensionless multi-source fillers. A sum / difference / product does NOT qualify.
    unit_class_by_name: dict[str, str | None] = {}
    for s in spec.sourced_inputs:
        unit_class_by_name[s.name] = _unit_class(s.unit)
    for m in spec.modeled_inputs:
        unit_class_by_name[m.name] = _unit_class(m.unit)
    return formula_is_same_unit_cancelling_ratio(
        getattr(output_field, "formula", ""), unit_class_by_name
    )


def detect_sourced_conflicts(
    sourced_numbers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Flag datapoints that describe the SAME quantity (same label+unit) but whose
    values disagree by > ``PG_CALC_CONFLICT_REL_TOL``. Telemetry only — does not
    gate. Returns a list of conflict records {label, unit, values, rel_spread}."""
    groups: dict[tuple[str, str], list[float]] = {}
    for dp in sourced_numbers:
        label = str(dp.get("label", "")).strip().lower()
        unit = str(dp.get("unit", "")).strip().lower()
        if not label:
            continue
        try:
            val = float(dp.get("value"))
        except (TypeError, ValueError):
            continue
        groups.setdefault((label, unit), []).append(val)

    conflicts: list[dict[str, Any]] = []
    for (label, unit), vals in groups.items():
        if len(vals) < 2:
            continue
        lo, hi = min(vals), max(vals)
        denom = max(abs(lo), abs(hi), 1e-9)
        rel_spread = abs(hi - lo) / denom
        if rel_spread > _CALC_CONFLICT_REL_TOL:
            conflicts.append({
                "label": label, "unit": unit,
                "values": sorted(set(vals)), "rel_spread": rel_spread,
            })
    return conflicts


@dataclass
class QuantifiedResult:
    model_id: str
    spec_hash: str
    spec: ModelSpec
    script: str
    # field_id -> {value, display_value, modeled_used: [names],
    #             sourced_tokens: [{ev_id,start,end,raw}]}
    fields: dict[str, dict[str, Any]] = field(default_factory=dict)

    def key(self) -> tuple[str, str]:
        return (self.model_id, self.spec_hash)

    def display_value(self, field_id: str) -> str | None:
        f = self.fields.get(field_id)
        return None if f is None else f.get("display_value")

    def calc_token(self, field_id: str) -> str:
        return f"[#calc:{self.model_id}:{self.spec_hash}:{field_id}]"


def _modeled_set(spec: ModelSpec) -> set[str]:
    return {m.name for m in spec.modeled_inputs}


def _sourced_tokens_for(spec: ModelSpec, refs: set[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for s in spec.sourced_inputs:
        if s.name in refs:
            out.append({
                "ev_id": s.ev_id,
                "start": int(s.literal_start),
                "end": int(s.literal_end),
                "raw": s.raw_literal,
            })
    return out


def _output_for_field(field_id: str) -> str:
    """Map a field id to its underlying output name.

    output            -> "tco"
    sensitivity point -> "tco@discount=0.06"  -> "tco"
    break-even        -> "tco.break_even"     -> "tco"
    """
    base = field_id.split("@", 1)[0]
    if base.endswith(".break_even"):
        base = base[: -len(".break_even")]
    return base


async def execute_quantified_model(
    spec: ModelSpec,
    evidence_rows: dict[str, dict[str, Any]],
    *,
    run_dir: str | None = None,
    timeout: int | None = None,
) -> QuantifiedResult | None:
    """Render -> execute (sandbox) -> pin per-field display_value -> persist.

    Returns a ``QuantifiedResult`` or ``None`` if execution fails (fail-closed:
    a model that does not execute cleanly contributes no verified numbers).
    """
    from src.polaris_graph.synthesis.tradeoff_modeler import render_script

    script = render_script(spec)
    exec_result = await execute_analysis_script(script, input_data=None, timeout=timeout)
    if not exec_result.get("success") or not isinstance(exec_result.get("result"), dict):
        logger.warning(
            "[quantified_analysis] execute failed for model %s: %s",
            spec.model_id, str(exec_result.get("error"))[:160],
        )
        return None

    parsed = exec_result["result"]
    raw_outputs = parsed.get("outputs") or {}
    raw_sens = parsed.get("sensitivity") or {}
    raw_be = parsed.get("break_even") or {}
    modeled_names = _modeled_set(spec)

    fields: dict[str, dict[str, Any]] = {}

    def _add_output_field(field_id: str, value: Any, *, exclude: str | None = None):
        out_name = _output_for_field(field_id)
        out = spec.output_by_name(out_name)
        if out is None:
            return
        try:
            fval = float(value)
        except (TypeError, ValueError):
            return
        is_break_even = field_id.endswith(".break_even")
        # break-even renders the solve-var VALUE (a threshold), not the output's
        # currency/percent — display it as a plain number.
        if is_break_even:
            disp_unit, disp_kind = "", "number"
        else:
            disp_unit, disp_kind = out.unit, out.display_kind
        display = _canonical_display(fval, disp_unit, disp_kind)
        refs = output_referenced_inputs(spec, out_name)
        modeled_used = sorted((refs & modeled_names) - ({exclude} if exclude else set()))
        fields[field_id] = {
            "value": fval,
            "display_value": display,
            # display_kind + unit let Regime C RE-CANONICALIZE the adjacent number
            # (Codex diff-gate P1-1/P1-2): the parsed adjacent value must format to
            # EXACTLY display_value — no suffix-match, no magnitude-scaled drift.
            "display_kind": disp_kind,
            "unit": disp_unit,
            "modeled_used": modeled_used,
            "sourced_tokens": _sourced_tokens_for(spec, refs),
        }

    for name, value in raw_outputs.items():
        _add_output_field(str(name), value)
    for fid, value in raw_sens.items():
        # "tco@discount=0.06" -> the swept var is stated as the point, exclude it
        swept = None
        if "@" in fid:
            after = fid.split("@", 1)[1]
            swept = after.split("=", 1)[0]
        _add_output_field(str(fid), value, exclude=swept)
    for fid, value in raw_be.items():
        out_name = _output_for_field(str(fid))
        var = spec.solve_for.var if spec.solve_for else None
        _add_output_field(str(fid), value, exclude=var)

    result = QuantifiedResult(
        model_id=spec.model_id, spec_hash=spec.spec_hash, spec=spec,
        script=script, fields=fields,
    )

    if run_dir:
        try:
            _persist(result, run_dir)
        except OSError as exc:
            logger.warning("[quantified_analysis] persist failed: %s", str(exc)[:160])

    return result


def _persist(result: QuantifiedResult, run_dir: str) -> str:
    """Write the audit/replay bundle (gap-19): spec + rendered script + per-field
    canonical display values + spec_hash."""
    spec = result.spec
    bundle = {
        "model_id": result.model_id,
        "spec_hash": result.spec_hash,
        "title": spec.title,
        "script": result.script,
        "sourced_inputs": [
            {"name": s.name, "value": s.value, "unit": s.unit, "ev_id": s.ev_id,
             "raw_literal": s.raw_literal, "literal_span": [s.literal_start, s.literal_end]}
            for s in spec.sourced_inputs
        ],
        "modeled_inputs": [
            {"name": m.name, "base": m.base, "unit": m.unit,
             "sweep": [m.sweep_lo, m.sweep_hi, m.sweep_step]}
            for m in spec.modeled_inputs
        ],
        "outputs": [
            {"name": o.name, "unit": o.unit, "display_kind": o.display_kind,
             "formula": o.formula}
            for o in spec.outputs
        ],
        "fields": {
            fid: {
                "value": f["value"], "display_value": f["display_value"],
                "display_kind": f.get("display_kind"), "unit": f.get("unit"),
                # Codex diff-gate P2-1: persist the full per-field audit record
                # (modeled inputs that must be labeled + the source-input spans).
                "modeled_used": f.get("modeled_used", []),
                "sourced_tokens": f.get("sourced_tokens", []),
            }
            for fid, f in result.fields.items()
        },
    }
    path = os.path.join(run_dir, "quantified_model.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(bundle, fh, indent=2, sort_keys=True)
    return path


def bind_calc_tokens(prose: str, result: QuantifiedResult) -> str:
    """Replace each ``{{calc:<field>}}`` placeholder with the field's canonical
    display value IMMEDIATELY followed by its calc token, so the verifier binds
    the token to the exact rendered number (token adjacency, brief §1.4)."""
    def _sub(m: re.Match) -> str:
        fid = m.group("field")
        disp = result.display_value(fid)
        if disp is None:
            return m.group(0)  # leave unknown placeholder untouched (will fail verify)
        return f"{disp}{result.calc_token(fid)}"

    return _CALC_PLACEHOLDER_RE.sub(_sub, prose)


def render_decision_matrix_prose(spec: ModelSpec, result: QuantifiedResult) -> str:
    """Deterministically template a one-sentence-per-number trade-off paragraph
    with ``{{calc:<field>}}`` placeholders + per-sentence "(modeled assumption)"
    labels where the field uses a modeled input. NOT an LLM call — the NUMBERS
    come from the verified executor; only the connective prose is templated, so
    no model can confabulate a computed value. One calc number per sentence
    (sentence-level keep/drop, brief §1.5)."""
    def _label(field_id: str) -> str:
        f = result.fields.get(field_id) or {}
        return (" " + _MODELED_LABEL_TEXT) if f.get("modeled_used") else ""

    sents: list[str] = []
    for o in spec.outputs:
        if o.name in result.fields:
            # FINDING #4 (#1344 tail B3) — the unit-compat gate is AUTHORITATIVE for the
            # ratio path and runs FIRST: withhold a unit-incompatible ratio (e.g. a
            # percent divided by a percentage-point) or a dimensionless ratio that mixes
            # a cited operand with an uncited (modeled) assumption — a dimensionally-
            # meaningless / non-cited computed number attributed to a source.
            if should_withhold_composed_output(o, spec):
                continue
            # FIX-2 (#1344): withhold unit-free scalar outputs that merely relate >=2
            # sourced inputs (invented "ratio"/"number" filler). Break-even / sensitivity
            # render on their own exempt branch below, so they are never suppressed here.
            # ITER-2 P1: a same-unit, fully-cited ratio that FINDING #4 has AFFIRMATIVELY
            # cleared (``is_valid_cited_ratio``) is a valid quantity and MUST render — the
            # coarse FIX-2 filler-suppressor must NOT blank it. Only outputs FINDING #4 did
            # not clear as a valid cited ratio are still subject to the FIX-2 suppressor.
            if not is_valid_cited_ratio(o, spec) and is_low_value_filler_output(
                result.fields[o.name]
            ):
                continue
            human = o.name.replace("_", " ")
            sents.append(f"The {human} is {{{{calc:{o.name}}}}}{_label(o.name)}.")
    if spec.solve_for is not None:
        be = f"{spec.solve_for.output}.break_even"
        if be in result.fields:
            var = spec.solve_for.var.replace("_", " ")
            sents.append(f"The break-even {var} is {{{{calc:{be}}}}}{_label(be)}.")
    return " ".join(sents)


_MODELED_LABEL_TEXT = "(modeled assumption)"


def _stamp_status(telem: dict[str, Any], status: str) -> None:
    """I-pipe-012 (#1237): ADD the discrete typed ``quantified_status`` to telem,
    but ONLY when the kill-switch is ON. With ``PG_QUANTIFIED_TYPED_STATUS=0`` this
    is a no-op so the returned telem dict is byte-identical to the pre-fix shape
    (existing ``firing_status`` + every other key is preserved either way — this
    only ever ADDS a key, never mutates or removes an existing one)."""
    if _TYPED_STATUS_ENABLED:
        telem["quantified_status"] = status


async def _call_spec_provider_with_retry(
    spec_provider, question: str, sourced_numbers: list[dict[str, Any]],
) -> tuple[Any, BaseException | None]:
    """I-pipe-012 (#1237): call the (billed) ``spec_provider`` with a BOUNDED retry
    on a TRANSIENT transport/parse failure (the RAISED path only).

    Returns ``(raw_spec, last_exc)``. On success ``raw_spec`` is the provider's
    return value (which may legitimately be a non-dict DECLINE) and ``last_exc`` is
    None. If every attempt raised, ``raw_spec`` is None and ``last_exc`` is the final
    exception. A non-dict return is NOT retried here (that is a Writer decline, not a
    transient fault — re-billing it is waste); only a raised exception is retried.

    When the kill-switch is OFF, exactly ONE attempt is made (no retry), preserving
    the pre-fix single-call billing profile. NEVER fabricates a spec on failure."""
    attempts = (1 + _SPEC_PROVIDER_RETRIES) if _TYPED_STATUS_ENABLED else 1
    last_exc: BaseException | None = None
    for attempt in range(attempts):
        try:
            raw_spec = await spec_provider(question, sourced_numbers)
            return raw_spec, None
        except Exception as exc:  # noqa: BLE001 — transient transport/parse fault; bounded retry
            last_exc = exc
            if attempt + 1 < attempts:
                logger.warning(
                    "[quantified_analysis] spec_provider raised (attempt %d/%d), retrying: %s",
                    attempt + 1, attempts, str(exc)[:160],
                )
    return None, last_exc


async def run_quantified_section(
    question: str,
    evidence_pool: dict[str, dict[str, Any]],
    *,
    spec_provider,
    run_dir: str | None = None,
    credibility_analysis: Any = None,  # I-cred-008b (#1162): advisory per-claim disclosure; None => byte-identical
) -> tuple[str | None, dict[str, Any]]:
    """Sweep-facing orchestrator: Extract -> Model -> Execute -> Bind ->
    Verify(Regime C) -> verified "Quantified Trade-off" section.

    ``spec_provider`` is an ASYNC callable ``(question, sourced_numbers) ->
    raw_spec_dict | None`` (the Writer in prod; a fake in tests) — the ONLY
    billed step, isolated here so the sync validation in ``build_quantified_spec``
    and the deterministic execute/verify stay spend-free-testable.

    Returns ``(section_markdown | None, telemetry)``. The section is produced
    ONLY when a spec validates, executes, and at least one computed sentence
    survives Regime C.
    """
    from src.polaris_graph.generator.provenance_generator import (
        resolve_provenance_to_citations,
        strict_verify,
    )
    from src.polaris_graph.synthesis.tradeoff_modeler import build_quantified_spec
    from src.polaris_graph.tools.evidence_extractor import (
        extract_numbers_from_evidence,
    )

    # FIX D-2 (#1182): ``firing_status`` is the LOUD, single-field reason the
    # quantified differentiator did or did not land — set at EVERY return point so a
    # ``spec_produced=False`` / ``fired=False`` manifest is never silent about WHERE it
    # died. The consumer ``quantified_degradation_disclosure`` (run_honest_sweep_r3.py)
    # already reads ``telemetry.get("firing_status")`` for its reader-facing disclosure,
    # but this producer never populated it — so a no-op surfaced only as a buried log.
    # Distinct values let a post-run audit tell "broken" (spec_provider_error /
    # execution_failed) apart from "legitimately inapplicable" (no_spec_returned with a
    # genuine Writer decline) without reading the raw log. Default = the pre-spec state.
    telem: dict[str, Any] = {
        "enabled": True, "spec_produced": False, "execution_success": False,
        "outputs": 0, "sourced_inputs": 0, "modeled_inputs": 0,
        "verified_sentences": 0, "dropped_sentences": 0, "conflicts": [],
        "firing_status": "started",
    }

    sourced_numbers = extract_numbers_from_evidence(evidence_pool)
    telem["conflicts"] = detect_sourced_conflicts(sourced_numbers)
    telem["sourced_numbers_extracted"] = len(sourced_numbers)

    # U27 (#1344): curate the Writer shortlist so clean, plausibly-valued datapoints
    # reach the (billed) spec LLM instead of raw iteration-order chrome/binary junk.
    # INPUT HYGIENE only — the FULL sourced pool still flows to build_quantified_spec
    # for datapoint matching below, and every verification gate is untouched. The
    # closure that actually shortlists to the Writer (run_honest_sweep_r3.py) applies
    # the SAME deterministic select_writer_candidate_numbers, so this telemetry mirrors
    # what the Writer will see. Kill-switch (PG_QUANTIFIED_SHORTLIST_CLEAN=0) => no
    # curation, no added telem keys, no short-circuit => byte-identical to the pre-fix path.
    if _SHORTLIST_CLEAN_ENABLED:
        _writer_candidates = select_writer_candidate_numbers(sourced_numbers)
        telem["writer_candidates"] = len(_writer_candidates)
        telem["sourced_numbers_junk"] = len(sourced_numbers) - len(_writer_candidates)
        # HONEST DISCLOSURE, not a silent no-op: if numbers WERE extracted but EVERY one
        # is scrape-chrome/binary garbage, there is a genuine data-shape reason the Writer
        # cannot model. Surface it as a DISTINCT status ("no_modelable_numbers") and skip
        # the wasted billed call, rather than letting the Writer decline on junk into the
        # ambiguous "no_spec_returned". Classed HONEST-EMPTY (declined_no_spec typed
        # status) — the differentiator did not silently break; the corpus simply carried
        # no clean modelable number. When at least one clean candidate survives, we DO
        # proceed to the Writer (this is the U27 fix: clean numbers now reach the LLM).
        if sourced_numbers and not _writer_candidates:
            telem["firing_status"] = "no_modelable_numbers"
            _stamp_status(telem, QUANTIFIED_STATUS_DECLINED_NO_SPEC)
            logger.warning(
                "[quantified_analysis] NO-OP (no_modelable_numbers): %d numbers were "
                "extracted but ALL were scrape-chrome/binary junk after shortlist "
                "curation (no clean modelable datapoint to offer the Writer)",
                len(sourced_numbers),
            )
            return None, telem

    # I-pipe-012 (#1237): bounded retry on a TRANSIENT raised transport/parse fault
    # (kill-switch ON). With PG_QUANTIFIED_TYPED_STATUS=0 this is a single call (no
    # retry) and the except-branch below is byte-identical to the pre-fix path.
    raw_spec, _spec_exc = await _call_spec_provider_with_retry(
        spec_provider, question, sourced_numbers,
    )
    if _spec_exc is not None:
        # UNAMBIGUOUSLY broken: the Writer/transport raised (e.g. a 404 on the
        # generator route surfaced as an exception). Loud, distinct, non-aborting.
        telem["firing_status"] = "spec_provider_error"
        telem["firing_error"] = str(_spec_exc)[:200]
        # I-pipe-012 (#1237): a raised provider is a transport/parse fault (we already
        # exhausted the bounded retry) — the discrete "silently broke" verdict.
        _stamp_status(telem, QUANTIFIED_STATUS_PARSE_ERROR)
        logger.warning(
            "[quantified_analysis] NO-OP (spec_provider_error): spec_provider raised: %s",
            str(_spec_exc)[:160],
        )
        return None, telem
    if not isinstance(raw_spec, dict):
        # AMBIGUOUS by construction: a prod ``spec_provider`` (the Writer closure in
        # run_honest_sweep_r3.py) collapses BOTH a transport failure (404 / empty 200 →
        # no JSON parsed) AND a legitimate Writer decline ({"model_id":"none"}) into a
        # bare ``None`` before it reaches us. We CANNOT tell broken from inapplicable
        # here — the caller lane must stop collapsing the two (see module summary). Tag
        # it honestly rather than guess a confident reason we can't support.
        telem["firing_status"] = "no_spec_returned"
        # I-pipe-012 (#1237): a non-dict return is the Writer DECLINE (or a caller-
        # collapsed transport miss — see cross-file note). We map it to
        # declined_no_spec because that is all we can HONESTLY assert module-side; the
        # true empty_transport status only becomes reachable once the caller stops
        # collapsing a 404/empty-200 into the same bare None (cross_file_deferred).
        _stamp_status(telem, QUANTIFIED_STATUS_DECLINED_NO_SPEC)
        logger.warning(
            "[quantified_analysis] NO-OP (no_spec_returned): spec_provider returned "
            "no dict (transport failure OR legitimate Writer decline — caller collapses "
            "both into None; %d sourced numbers were available)",
            len(sourced_numbers),
        )
        return None, telem

    spec = build_quantified_spec(
        question, sourced_numbers, evidence_pool,
        spec_llm=lambda _q, _s: raw_spec,
        # I-fix-001: capture the EXACT fail-closed gate into telemetry so the silent
        # no-op names itself in the DURABLE manifest. Sweep run.log captures stdout,
        # not the stderr WARNINGs build_quantified_spec emits — so before this the
        # cert-run spec_validation_rejected had no attributable gate. Additive: the
        # key is written only when a reason fires (None spec_llm => byte-identical).
        on_reject=lambda _r: telem.__setitem__("spec_reject_reason", _r),
    )
    if spec is None:
        # The Writer returned a dict but it FAILED hard validation in
        # build_quantified_spec (datapoint identity, formula AST, material-dependency,
        # etc.). A defensible-but-rejected model, not a transport failure.
        telem["firing_status"] = "spec_validation_rejected"
        # I-pipe-012 (#1237): the Writer emitted a dict that FAILED hard validation —
        # a malformed/unparseable spec, classed with the parse_error family (the
        # differentiator broke on a bad payload, not a clean decline).
        _stamp_status(telem, QUANTIFIED_STATUS_PARSE_ERROR)
        logger.warning(
            "[quantified_analysis] NO-OP (spec_validation_rejected): Writer emitted a "
            "spec dict but it failed build_quantified_spec validation (fail-closed): %s",
            telem.get("spec_reject_reason", "unattributed"),
        )
        return None, telem
    telem["spec_produced"] = True
    telem["model_id"] = spec.model_id
    telem["sourced_inputs"] = len(spec.sourced_inputs)
    telem["modeled_inputs"] = len(spec.modeled_inputs)

    result = await execute_quantified_model(spec, evidence_pool, run_dir=run_dir)
    if result is None:
        telem["firing_status"] = "execution_failed"
        # I-pipe-012 (#1237): the sandbox returned no clean outputs — a parse/execution
        # fault on an otherwise-valid spec, classed with the parse_error family.
        _stamp_status(telem, QUANTIFIED_STATUS_PARSE_ERROR)
        logger.warning(
            "[quantified_analysis] NO-OP (execution_failed): spec validated but the "
            "deterministic sandbox execution did not return clean outputs (model %s)",
            spec.model_id,
        )
        return None, telem
    telem["execution_success"] = True
    telem["outputs"] = len(spec.outputs)

    prose = render_decision_matrix_prose(spec, result)
    bound = bind_calc_tokens(prose, result)
    # FIX-2 (#1344): if every computed output was suppressed as low-value unit-free
    # filler (and there is no break-even/sensitivity sentence), the bound prose is empty.
    # Withhold the section under a DISTINCT honest status rather than letting it fall
    # through to the Regime-C ``no_verified_sentences`` path (which would mislabel an
    # intentional filler-withhold as a faithfulness failure).
    if not bound.strip():
        telem["firing_status"] = "suppressed_low_value_quantified"
        telem["quantified_filler_suppressed"] = True
        _stamp_status(telem, QUANTIFIED_STATUS_DECLINED_NO_SPEC)
        logger.warning(
            "[quantified_analysis] NO-OP (suppressed_low_value_quantified): all computed "
            "outputs were unit-free filler scalars relating >=2 sourced inputs (model %s)",
            spec.model_id,
        )
        return None, telem
    report = strict_verify(
        bound, evidence_pool, quantified_models={result.key(): result},
    )
    telem["verified_sentences"] = report.total_kept
    telem["dropped_sentences"] = report.total_dropped
    if report.total_kept == 0:
        # The spec executed but EVERY computed sentence failed Regime C (e.g. an
        # unlabeled modeled assumption, a number≠display mismatch). No verified prose.
        telem["firing_status"] = "no_verified_sentences"
        # I-pipe-012 (#1237): the spec executed but EVERY computed sentence failed
        # Regime C — this is the faithfulness gate doing its job (a legitimate,
        # NON-broken decline-to-emit). Class it as declined_no_spec (the
        # differentiator did not silently break; it correctly emitted nothing).
        _stamp_status(telem, QUANTIFIED_STATUS_DECLINED_NO_SPEC)
        logger.warning(
            "[quantified_analysis] NO-OP (no_verified_sentences): %d computed "
            "sentence(s) all failed Regime C verification (model %s)",
            report.total_dropped, spec.model_id,
        )
        return None, telem

    # I-cred-008b (#1162) SITE 4/4 (quantified trade-off): populate the advisory per-claim disclosure
    # on the kept SVs BEFORE resolve. This path returns (section_md, telem) — it has NO SectionResult,
    # so the populated SVs do NOT flow through kept_sentences_pre_resolve. To SURFACE them, we emit the
    # per-claim disclosure rows in `telem["claim_disclosure"]` (the runner merges them into
    # claim_disclosure.json). None => byte-identical (no populate, no telem key).
    if credibility_analysis is not None:
        from src.polaris_graph.synthesis.credibility_pass import apply_disclosure_to_svs
        report.kept_sentences = apply_disclosure_to_svs(
            report.kept_sentences, credibility_analysis,
        )
        telem["claim_disclosure"] = [
            {
                "sentence": getattr(_sv, "sentence", ""),
                "span_verdict": getattr(_sv, "span_verdict", ""),
                "credibility_weight": getattr(_sv, "credibility_weight", None),
                "independent_origin_count": getattr(_sv, "independent_origin_count", None),
                "certainty_label": getattr(_sv, "certainty_label", ""),
                "soft_warnings": list(getattr(_sv, "soft_warnings", None) or []),
            }
            for _sv in report.kept_sentences
        ]

    # Reached only when a spec validated, executed, and ≥1 computed sentence survived
    # Regime C — the differentiator actually FIRED.
    telem["firing_status"] = "fired"
    # I-pipe-012 (#1237): the success verdict — a parseable spec produced a verified
    # payload (the kept sentences, surfaced via verified_sentences / the rendered
    # section). "ok+payload" per the acceptance criteria.
    _stamp_status(telem, QUANTIFIED_STATUS_OK)

    rendered, _biblio = resolve_provenance_to_citations(
        report.kept_sentences, evidence_pool,
    )
    # I-deepfix-001 F3 (#1344): surface the section-LOCAL bibliography so the caller can
    # remap this section's local ``[N]`` markers onto the GLOBAL multi-section bibliography
    # (the quantified section is assembled outside the multi-section pipeline, so its local
    # [1][2] otherwise collide with global [1]=Acemoglu/[2]=Autor and its input sources never
    # appear in References). Additive telemetry field; byte-identical when unused.
    telem["section_biblio"] = _biblio
    section_md = f"### Quantified Trade-off\n\n{rendered}"
    return section_md, telem
