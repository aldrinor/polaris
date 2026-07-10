"""S7 deliverable-aware RENDER leg (master plan WP-3d; Design 3 consumers 3+4 + §1.3 disclosure).

PURE, stdlib-only, offline-testable. Turns a parsed DeliverableSpec dict (``RunConfig.deliverable``)
and a resolved RunConfig provenance dict into four render artifacts:
  1. reference-STYLE bibliography entry formatting (author-year / APA / Harvard / Vancouver),
  2. report ORDERING / shape transforms (summary-first vs trailing, recommendations-last),
  3. a Methods "Deliverable requirements" adherence block (Design 3 consumer 4),
  4. a Methods "Run configuration" knob-disclosure block (master plan §1.3).

INVARIANTS (clinical-safety-critical — §-1.1 / §-1.3):
- NEVER fabricates a reference-metadata field (author, year). Renders from REAL captured metadata
  ONLY; a missing field degrades to a title/locator form (+ a Methods disclosure), never invented.
- The default reference_style == "numeric" is NEVER routed through this module — the caller keeps
  its byte-identical numeric render, so an empty/absent spec is byte-identical to HEAD.
- Every entry line keeps its leading "[N] " marker (in-text [N] stays in v1) so the D8 / redaction /
  T2 corpus-ledger / source-necessity consumers that key on "^[N] " and the structural
  "## Bibliography" heading are untouched.
- Touches wording / order / label ONLY: no claim text, no number, no citation, and no source is
  added, dropped, re-ordered-within-a-claim, or altered. The faithfulness engine is not on this
  module's path (D8 + strict_verify + provenance + redaction see byte-identical claim-bearing text).

Model/token governance (§9.1.8): this module makes ZERO LLM calls (deterministic string work, no
spend), so there is no model or token budget to read here.
"""

from __future__ import annotations

from typing import Any

# ── reference-style vocabulary (renderer capabilities; unknown => numeric + disclosure) ───────────
NUMERIC_STYLE = "numeric"
_RENDERABLE_STYLES = frozenset({"numeric", "author_year", "apa", "harvard", "vancouver"})
# Styles rendered author-date-first (author (year). title.) vs Vancouver (author. title.; year).
_AUTHOR_DATE_STYLES = frozenset({"author_year", "apa", "harvard"})
# Non-title-case junk that is not a real author name (mirrors citation_mapper._extract_author).
_AUTHOR_JUNK = frozenset({"unknown", "n/a", "none", "anonymous", "null", ""})
# deliverable_type values that read as an executive/leadership brief (disclosure context only).
_BRIEF_TYPES = frozenset({"memo", "brief", "policy_brief", "white_paper", "executive_summary"})


def _norm(value: Any) -> str:
    return str(value or "").strip()


def is_spec_active(spec: "dict | None") -> bool:
    """True iff ``spec`` is a dict carrying at least one populated (non-empty, non-None) field.

    An absent / empty / all-None spec is treated as "no deliverable ask" => the caller must keep the
    byte-identical HEAD render. PURE."""
    if not isinstance(spec, dict):
        return False
    for key, val in spec.items():
        if key in ("source", "raw_directives"):
            continue
        if isinstance(val, bool):
            # a bool present in the spec is a DELIBERATE ask (spec bools default to None when unset),
            # so BOTH True and False count as populated — e.g. summary_first=False ("no top summary").
            return True
        elif isinstance(val, (list, tuple, dict)):
            if val:
                return True
        elif val is not None and _norm(val):
            return True
    return False


def resolve_reference_style(spec: "dict | None") -> "tuple[str, bool]":
    """Return ``(style, is_fallback)`` for the report's reference list. PURE.

    ``style`` is one of ``_RENDERABLE_STYLES``. ``is_fallback`` is True only when the spec named a
    reference style the renderer cannot produce — the renderer then falls back to ``numeric`` and the
    Methods adherence block discloses the fallback (never a silent guess, never a crash). An absent /
    empty reference_style resolves to ``("numeric", False)`` (today's behaviour)."""
    raw = _norm((spec or {}).get("reference_style")).lower().replace("-", "_").replace(" ", "_")
    if not raw:
        return NUMERIC_STYLE, False
    if raw in _RENDERABLE_STYLES:
        return raw, False
    return NUMERIC_STYLE, True  # unknown named style => numeric + disclosure


def _authors_display(row: "dict | None") -> "str | None":
    """A human-readable author string from REAL captured metadata, or ``None`` when none is captured.

    Reads the row's ``authors`` list first, then a single ``author`` string; junk placeholders
    ("unknown"/"n/a"/...) are treated as absent. NEVER fabricates a name. PURE (mirrors
    citation_mapper._format_bibliography_entry's author folding: <=3 joined, else "First et al.")."""
    if not isinstance(row, dict):
        return None
    authors = row.get("authors")
    if isinstance(authors, (list, tuple)):
        names = [_norm(a) for a in authors if _norm(a) and _norm(a).lower() not in _AUTHOR_JUNK]
        if names:
            return ", ".join(names) if len(names) <= 3 else f"{names[0]} et al."
    single = _norm(row.get("author"))
    if single and single.lower() not in _AUTHOR_JUNK:
        return single
    return None


def format_reference_body(
    *,
    num: Any,
    title: str,
    locator: str,
    tier: Any,
    genre_tag: str,
    row: "dict | None",
    year: "int | None",
    style: str,
    has_locator: bool = True,
) -> str:
    """Render ONE bibliography entry line in a NON-numeric ``style`` from REAL metadata only. PURE.

    The line ALWAYS keeps its leading ``[N] `` marker and its trailing `` (tier T){genre_tag}`` so the
    "^[N] " / "## Bibliography" downstream consumers stay untouched. Between the two, author / year /
    title / locator are arranged per style. A missing author or year is simply omitted — NEVER
    fabricated (LAW II). ``has_locator=False`` slots the disclosed-gap phrase in as the locator.

    Numeric style is handled by the caller (byte-identical), so ``style`` here is one of
    author_year / apa / harvard / vancouver."""
    _title = _norm(title) or f"source {_norm(num)}".strip()
    _loc = _norm(locator)
    _authors = _authors_display(row)
    _year = str(year) if isinstance(year, int) and not isinstance(year, bool) else ""
    _tier = _norm(tier) or "n/a"
    tail = f" (tier {_tier}){genre_tag or ''}"

    if style == "vancouver":
        # numbered style: Author(s). Title. Locator; Year.
        lead = f"{_authors}. " if _authors else ""
        yr = f"; {_year}" if _year else ""
        body = f"{lead}{_title}. {_loc}{yr}".rstrip()
    else:  # author_year / apa / harvard — author-date first
        if _authors and _year:
            body = f"{_authors} ({_year}). {_title}. {_loc}"
        elif _authors:
            body = f"{_authors}. {_title}. {_loc}"
        elif _year:
            body = f"{_title} ({_year}). {_loc}"
        else:
            body = f"{_title}. {_loc}"
        body = body.rstrip()
    return f"[{_norm(num)}] {body}{tail}"


def build_report_ordering(spec: "dict | None") -> "dict | None":
    """Distil the render-controllable ORDERING knobs from the deliverable spec, or ``None``. PURE.

    Returns ``None`` (=> caller keeps the default assembly) unless the spec carries an ordering ask.
    S7 render only re-orders the extractive SUMMARY / CONCLUSION wrappers (which section appears
    where inside the body is the OUTLINE's job, not render's). Keys:
      - ``summary_first``: abstract/executive-summary leads (default True) vs trails the body.
      - ``recommendations_last``: the closing Conclusion block sits at the very end (always True here;
        the extractive Conclusion is structurally last — disclosed, never a claim move).
      - ``brief_shape``: the deliverable reads as an executive/leadership brief (disclosure context)."""
    if not is_spec_active(spec):
        return None
    s = spec or {}
    summary_first = s.get("summary_first")
    recommendations_last = s.get("recommendations_last")
    dtype = _norm(s.get("deliverable_type")).lower()
    brief_shape = dtype in _BRIEF_TYPES
    if summary_first is None and recommendations_last is None and not brief_shape:
        return None
    return {
        # default True preserves today's abstract-leads placement when only other asks are present.
        "summary_first": True if summary_first is None else bool(summary_first),
        "recommendations_last": True if recommendations_last is None else bool(recommendations_last),
        "brief_shape": brief_shape,
    }


def assemble_with_ordering(
    title_md: str, abstract_md: str, body_md: str, conclusion_md: str, ordering: "dict | None"
) -> str:
    """Arrange the four extractive blocks per ``ordering``. PURE.

    ``summary_first`` True  => title + abstract + body + conclusion (today's order, byte-identical).
    ``summary_first`` False => title + body + abstract + conclusion (no top summary; conclusion still
    last, honouring recommendations_last by construction). ``body_md`` is passed ALREADY de-duped by
    the caller so dedup behaviour is unchanged. No block text is edited — only its position moves."""
    if not ordering or ordering.get("summary_first", True):
        return title_md + abstract_md + body_md + conclusion_md
    return title_md + body_md + abstract_md + conclusion_md


# ── Methods disclosure blocks (Design 3 consumer 4 + master §1.3) ─────────────────────────────────
_ADHERENCE_HEADER = "\n### Deliverable requirements\n"
_RUNCONFIG_HEADER = "\n### Run configuration\n"
# knob-provenance source layers that are NOT worth disclosing (they are the untouched baseline).
_DEFAULT_SOURCES = frozenset({"default", "code_default", ""})


def render_deliverable_adherence_block(
    spec: "dict | None", *, reference_fallback: bool = False, status_by_field: "dict | None" = None
) -> str:
    """The Methods "Deliverable requirements" adherence block. Returns "" when no spec (byte-identical).

    Lists each parsed directive with a status the render leg can HONESTLY assert:
      - render-controlled fields (reference_style, summary_first, recommendations_last, output_format)
        => HONORED, or PARTIAL when a named reference style fell back to numeric;
      - non-render fields (tone, audience, length, structure) => the caller-supplied ``status_by_field``
        status when known, else a neutral "requested" note — the render leg NEVER over-claims a status
        it did not itself produce (over-claiming completeness is the lethal direction, §-1.1).
    Each line quotes the verbatim trigger span when the spec carries one (anti-invention audit)."""
    if not is_spec_active(spec):
        return ""
    s = spec or {}
    status_by_field = status_by_field or {}
    # raw_directives may be plain strings (Design 3 list[str]) OR {field, span} dicts. Index the dict
    # form by field for inline quoting; keep the plain-string form for a verbatim-spans trailer so the
    # anti-invention audit trail (LAW II) surfaces regardless of shape.
    spans: dict[str, str] = {}
    plain_spans: list[str] = []
    for span in (s.get("raw_directives") or []):
        if isinstance(span, dict):
            fld = _norm(span.get("field"))
            if fld:
                spans[fld] = _norm(span.get("span") or span.get("text"))
        elif _norm(span):
            plain_spans.append(_norm(span))
    lines = [_ADHERENCE_HEADER,
             "Requirements parsed from the request and applied to this report:\n"]

    def _emit(field: str, label: str, status: str) -> None:
        span = spans.get(field)
        quote = f' — "{span}"' if span else ""
        lines.append(f"- {label}: {status}{quote}\n")

    ref_style, _ = resolve_reference_style(s)
    if _norm(s.get("reference_style")):
        if reference_fallback:
            _emit("reference_style", "Reference style",
                  f'PARTIAL (requested "{_norm(s.get("reference_style"))}" not a renderable style; '
                  "rendered numeric)")
        else:
            _emit("reference_style", "Reference style",
                  f"HONORED ({ref_style} entry formatting; the structural \"## Bibliography\" heading "
                  "and in-text [N] markers are retained in v1)")
    if s.get("summary_first") is not None:
        _emit("summary_first", "Executive summary placement",
              "HONORED (summary leads)" if s.get("summary_first") else "HONORED (summary trails body)")
    if s.get("recommendations_last") is not None:
        _emit("recommendations_last", "Recommendations placement", "HONORED (conclusion placed last)")
    if _norm(s.get("output_format")):
        _emit("output_format", "Output format",
              status_by_field.get("output_format", f"requested ({_norm(s.get('output_format'))})"))
    for field, label in (
        ("deliverable_type", "Deliverable type"),
        ("audience", "Audience"),
        ("tone", "Tone"),
        ("reading_level", "Reading level"),
    ):
        val = _norm(s.get(field))
        if val:
            _emit(field, label, status_by_field.get(field, f"requested ({val}); applied in composition"))
    if s.get("length_target_words") or s.get("length_target_pages"):
        tgt = (f"{s.get('length_target_words')} words" if s.get("length_target_words")
               else f"{s.get('length_target_pages')} pages")
        _emit("length", "Length",
              status_by_field.get("length",
                                  f"requested ({tgt}, {_norm(s.get('length_strictness')) or 'weight'}); "
                                  "shapes prose budget, never evidence"))
    for slot in (s.get("structure_slots") or []):
        stitle = _norm(slot.get("title") if isinstance(slot, dict) else slot)
        if stitle:
            lines.append(f"- Requested section \"{stitle}\": "
                         f"{status_by_field.get('structure_slots', 'required-if-grounded (outline)')}\n")
    if plain_spans:
        # verbatim trigger spans (anti-invention audit trail) when raw_directives are plain strings.
        lines.append("Parsed directive spans (verbatim): "
                     + "; ".join(f'"{sp}"' for sp in plain_spans) + "\n")
    return "".join(lines)


def render_run_config_disclosure_block(run_config: "dict | None") -> str:
    """The Methods "Run configuration" block (master §1.3): every NON-default knob + value + source.

    Returns "" when there is no run_config or no non-default knob (byte-identical to HEAD). Accepts
    either a RunConfig dict with a ``provenance`` map or a bare ``{knob: {value, source, span}}`` map.
    PURE; fail-safe on malformed rows (a bad row is skipped, never crashes the render)."""
    if not isinstance(run_config, dict):
        return ""
    prov = run_config.get("provenance") if isinstance(run_config.get("provenance"), dict) else run_config
    if not isinstance(prov, dict) or not prov:
        return ""
    rows: list[str] = []
    for knob_id in sorted(prov.keys()):
        entry = prov.get(knob_id)
        if not isinstance(entry, dict):
            continue
        source = _norm(entry.get("source")).lower()
        if source in _DEFAULT_SOURCES:
            continue  # a knob left at its baseline is not disclosed (it is the untouched default)
        value = entry.get("value")
        span = _norm(entry.get("span"))
        span_clause = f'; prompt: "{span}"' if span else ""
        rows.append(f"- {_norm(knob_id)} = {value} (source: {source or 'set'}{span_clause})\n")
    if not rows:
        return ""
    return _RUNCONFIG_HEADER + "Non-default settings applied to this run:\n" + "".join(rows)
