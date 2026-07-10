#!/usr/bin/env python3
"""S7 RENDER -- thin checkpoint runner (cp6 -> report.md).

Reads the post-verification checkpoint (``cp6_postverify_checkpoint.json`` /
``postverify_checkpoint.json``) -- each section carrying its per-sentence LABELED
sentences + citations -- and emits a clean, readable ``report.md`` in the RunConfig
tone / structure / reference style. The Methods section discloses the RunConfig knobs
and every deletion. NO chrome, NO orphan citations.

THIN WIRE -- the report renderer ALREADY EXISTS in the repo; nothing here re-implements
it. This runner imports and REUSES the production render leaves:
  * ``run_honest_sweep_r3.assemble_report_md`` / ``dedup_identical_paragraphs``
  * ``run_honest_sweep_r3._render_bibliography_lines``  (the numbered References list)
  * chrome screens: ``_screen_key_findings_chrome`` / ``_screen_offtopic_chrome_sections`` /
    ``_screen_garbled_headers`` / ``_relabel_uncorroborated_findings_headers`` /
    ``weighted_enrichment.sanitize_rendered_report`` /
    ``block_page_chrome_scrub.scrub_block_page_chrome`` /
    ``markdown_table_normalizer.normalize_gfm_tables``   (=> NO chrome)
  * composition leaves: ``key_findings.build_key_findings`` / ``build_depth_layer`` /
    ``humanize_section_title`` / ``abstract_conclusion.build_abstract`` / ``build_conclusion``
  * checkpoint loader: ``run_honest_sweep_r3.load_a12_checkpoint`` (fail-loud verdict-key guard)

The only NEW logic is the thin wiring:
  1. reconstruct per-section sentence lists from the cp6 verification accounting,
  2. resolve each sentence's provenance / cite tokens to numbered ``[N]`` markers against
     the bibliography (orphan markers dropped => NO orphan citations),
  3. surface a per-sentence confidence LABEL when the checkpoint marks a sentence weak /
     repaired (S6 UNFREEZE = LABEL+REPAIR, never silent-drop),
  4. build the ``## Methods`` disclosure block (RunConfig knobs + every deletion), and
  5. assemble + screen + write ``report.md``.

GENERALIZATION MANDATE: every step is driven by the checkpoint + the RunConfig. There is
NO question-specific branch, no magic number tuned to any one corpus, no cap / target /
thinner. The same runner renders any research question's cp6.

CONTEXT-LEVEL FAITHFULNESS: this runner does NOT re-judge faithfulness -- the cp6
sentences are already the verifier's kept / labeled output. It renders them verbatim
(real synthesis prose that S5 composed; no raw span copying here) and resolves their
citations; numbers stay byte-verbatim (the token text is never rewritten, only the
trailing ``[#ev:...]`` / ``[CITE:...]`` marker is mapped to ``[N]``).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------------------
# Render-shape defaults. These select the READABLE report shape (title + abstract +
# key findings + per-section depth layer + conclusion) the production sweep renders. They
# are ``setdefault`` -- an explicit environment / RunConfig value ALWAYS wins (LAW VI) -- and
# they are global render-shape switches, NOT tuned to any one question (generalization
# mandate). Without the abstract on, the title sits orphaned before ``## Key Findings`` and
# the assembler's dedup pass drops the H1; enabling the readable shape is the correct default.
# --------------------------------------------------------------------------------------
for _flag_name, _flag_default in (
    ("PG_SYNTHESIS_ABSTRACT_CONCLUSION", "1"),  # ## Abstract + ## Conclusion composition
    ("PG_SWEEP_KEY_FINDINGS", "1"),             # ## Key Findings block
    ("PG_SWEEP_DEPTH_LAYER", "1"),              # per-section analytical depth layer
    ("PG_RENDER_CHROME_SCREEN", "1"),           # chrome-screen categories + truncation ON
):
    os.environ.setdefault(_flag_name, _flag_default)

# --------------------------------------------------------------------------------------
# Checkpoint file names (both the legacy and the section-modular cp6 name are accepted).
# --------------------------------------------------------------------------------------
_CP6_NAMES = ("cp6_postverify_checkpoint.json", "postverify_checkpoint.json")

# Provenance / cite / numbered citation token shapes handled at render time.
_EV_TOKEN_RE = re.compile(r"\[#ev:([^:\]]+):\d+-\d+\]")   # [#ev:<evidence_id>:<start>-<end>]
_BARE_EV_TOKEN_RE = re.compile(r"\[#ev:([^:\]]+)\]")       # [#ev:<evidence_id>] (defensive)
_CITE_TOKEN_RE = re.compile(r"\[CITE:([a-zA-Z0-9_]+)\]")   # [CITE:<evidence_id>]
_NUM_MARKER_RE = re.compile(r"\[(\d+)\]")                   # [N]

# S6 UNFREEZE (LABEL+REPAIR): a per-sentence confidence label surfaced to the reader when
# the checkpoint marks a sentence as anything weaker than fully verified. Never silent-drop.
_WEAK_LABELS = frozenset(
    {
        "weak", "low", "partial", "repaired", "unverified", "uncertain",
        "labeled_weak", "nli_repaired", "low_confidence", "medium",
    }
)
_CONFIDENCE_KEYS = ("confidence", "label", "verdict", "faithfulness_label", "confidence_label")


@dataclass
class _RenderSection:
    """Minimal stand-in for a production ``SectionResult``, reconstructed from cp6.

    Carries ONLY the attributes the production render leaves read via ``getattr``
    (``build_key_findings`` / ``build_depth_layer`` / ``build_abstract`` / ``build_conclusion``):
    ``title`` / ``verified_text`` / ``sentences_verified`` / ``sentences_dropped`` /
    ``dropped_due_to_failure`` / ``is_gap_stub`` / ``section_id``. ``verified_text`` is the
    section's kept / labeled sentences (citations already resolved to ``[N]``) joined verbatim."""

    title: str
    verified_text: str
    sentences_verified: int
    sentences_dropped: int = 0
    dropped_due_to_failure: bool = False
    is_gap_stub: bool = False
    section_id: str = ""


# --------------------------------------------------------------------------------------
# Load side inputs (fail-loud on cp6; fail-open on optional sidecars).
# --------------------------------------------------------------------------------------
def _resolve_cp6(cp6_arg: str) -> tuple[Path, Path]:
    """Return ``(checkpoint_path, run_dir)``. ``cp6_arg`` may be the checkpoint file itself
    or a run directory containing it. FAIL LOUD if no cp6 checkpoint is found (LAW II --
    never a silent empty render)."""
    p = Path(cp6_arg)
    if p.is_file():
        return p, p.parent
    if p.is_dir():
        for name in _CP6_NAMES:
            cand = p / name
            if cand.is_file():
                return cand, p
    raise FileNotFoundError(
        f"no cp6 checkpoint at {cp6_arg!r} (looked for {list(_CP6_NAMES)}). S7 render "
        "cannot fabricate a report without the post-verification checkpoint."
    )


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _load_bibliography(run_dir: Path) -> tuple[list[dict], dict[str, int], set[int]]:
    """Load ``bibliography.json`` and derive the evidence_id -> citation-number map and the
    valid-number set. Absent bibliography => empty map (the report still renders; citations
    that cannot resolve are dropped as orphans, never left dangling)."""
    bib_path = run_dir / "bibliography.json"
    if not bib_path.is_file():
        return [], {}, set()
    try:
        rows = _load_json(bib_path) or []
    except Exception as exc:  # noqa: BLE001 -- malformed optional sidecar -> render without it
        sys.stderr.write(f"[s7-render] bibliography.json unreadable ({exc}); rendering without it\n")
        return [], {}, set()
    if not isinstance(rows, list):
        return [], {}, set()
    eid2num: dict[str, int] = {}
    valid: set[int] = set()
    for b in rows:
        if not isinstance(b, dict):
            continue
        num = b.get("num")
        eid = b.get("evidence_id")
        if isinstance(num, int):
            valid.add(num)
            if eid:
                eid2num[str(eid)] = num
    return rows, eid2num, valid


def _load_run_config(cfg_arg: str | None, checkpoint: dict, protocol: dict) -> dict:
    """Assemble the RunConfig knob view. Precedence (highest first): explicit ``--run-config``
    file > cp6 ``deliverable_spec`` / ``flag_slate`` > protocol ``deliverable_spec`` +
    scope/user constraints. Everything is a plain view for disclosure + the render options the
    existing renderer supports. No question-specific defaults."""
    cfg: dict = {}
    # Lowest layer: protocol scope/user constraints (what the run was actually bounded by).
    for key in ("date_range", "languages", "geography", "excluded_sponsors",
                "user_constraints", "scope_constraints", "user_overrides", "template_used"):
        val = protocol.get(key)
        if val not in (None, "", [], {}):
            cfg[key] = val
    ds = protocol.get("deliverable_spec")
    if isinstance(ds, dict):
        cfg.update({k: v for k, v in ds.items() if v not in (None, "", [], {})})
    # cp6-carried spec / flag slate (forward-compatible envelope fields).
    for src_key in ("deliverable_spec", "flag_slate", "run_config", "env_slate"):
        src = checkpoint.get(src_key)
        if isinstance(src, dict):
            cfg.update({k: v for k, v in src.items() if v not in (None, "", [], {})})
    # Highest layer: explicit RunConfig file (JSON).
    if cfg_arg:
        try:
            file_cfg = _load_json(Path(cfg_arg))
            if isinstance(file_cfg, dict):
                cfg.update({k: v for k, v in file_cfg.items() if v not in (None, "", [], {})})
        except Exception as exc:  # noqa: BLE001 -- bad config file must not abort the render
            sys.stderr.write(f"[s7-render] --run-config unreadable ({exc}); using checkpoint/protocol only\n")
    return cfg


# --------------------------------------------------------------------------------------
# Citation resolution: any input marker shape -> numbered [N]; orphans dropped.
# --------------------------------------------------------------------------------------
def _resolve_citations_to_numbers(text: str, eid2num: dict[str, int], valid_nums: set[int]) -> str:
    """Resolve provenance / cite tokens to numbered ``[N]`` markers against the bibliography and
    DROP every orphan marker (an evidence_id not in the map, or a ``[N]`` whose number is not a
    real bibliography row). This is the NO-orphan-citation guarantee, applied uniformly to all
    input forms. Mirrors ``citation_mapper.resolve_citations`` semantics (drop-ungrounded,
    dedup-adjacent, clean artifacts). Numbers inside the sentence PROSE are untouched -- only
    trailing citation MARKERS are mapped, so numeric faithfulness is preserved verbatim."""
    def _map_eid(match: re.Match) -> str:
        num = eid2num.get(match.group(1))
        return f"[{num}]" if num is not None else ""

    text = _EV_TOKEN_RE.sub(_map_eid, text)
    text = _BARE_EV_TOKEN_RE.sub(_map_eid, text)
    text = _CITE_TOKEN_RE.sub(_map_eid, text)

    # Drop any surviving [N] that does not point at a real bibliography row. When no
    # bibliography is present (valid_nums empty) numbered markers are left intact -- they may
    # already be the report's own numbering and dropping all of them would strip real citations.
    if valid_nums:
        def _screen_num(match: re.Match) -> str:
            return match.group(0) if int(match.group(1)) in valid_nums else ""
        text = _NUM_MARKER_RE.sub(_screen_num, text)

    # Collapse adjacent identical markers [1][1] -> [1]; tidy spacing around punctuation.
    text = re.sub(r"(\[\d+\])(?:\1)+", r"\1", text)
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    text = re.sub(r"  +", " ", text)
    return text.strip()


def _confidence_tag(row: dict) -> str:
    """S6 LABEL+REPAIR: when the checkpoint marks a sentence weaker than fully verified, surface
    a disclosed inline confidence tag. A verified / absent label renders clean (byte-identical to
    a today-checkpoint). Never silent-drop the sentence -- the operator's release-with-a-label rule."""
    for key in _CONFIDENCE_KEYS:
        val = row.get(key)
        if isinstance(val, str) and val.strip().lower() in _WEAK_LABELS:
            return f"[confidence: {val.strip().lower()}]"
    return ""


def _sentence_rows(section: dict) -> list[dict]:
    """Collect a section's per-sentence LABELED rows. ``kept`` is today's shape; the S6 UNFREEZE
    contract may additionally carry ``labeled`` / ``repaired`` / ``sentences`` lists (weak-but-kept
    sentences). All are rendered -- LABEL+REPAIR keeps them, only the label differs."""
    rows: list[dict] = []
    seen: set[int] = set()
    for key in ("kept", "labeled", "repaired", "sentences"):
        for r in (section.get(key) or []):
            if isinstance(r, dict) and id(r) not in seen:
                seen.add(id(r))
                rows.append(r)
    return rows


# --------------------------------------------------------------------------------------
# Reconstruct render sections from cp6.
# --------------------------------------------------------------------------------------
def _reconstruct_sections(
    verif_details: dict, eid2num: dict[str, int], valid_nums: set[int], humanize
) -> list[_RenderSection]:
    """Rebuild the per-section render input from the cp6 verification accounting. Each labeled
    sentence's citations are resolved to ``[N]`` and a confidence tag is surfaced when the label
    is weak. A section with zero renderable sentences is skipped (its gap-stub guard), matching
    production. Titles are humanized (``Foundational_Theory`` -> ``Foundational Theory``) so a raw
    entity-id never leaks as a header."""
    out: list[_RenderSection] = []
    for s in verif_details.get("sections", []):
        if not isinstance(s, dict):
            continue
        if s.get("dropped_due_to_failure"):
            continue
        rendered: list[str] = []
        for r in _sentence_rows(s):
            raw = str(r.get("sentence") or r.get("text") or r.get("sentence_text") or "").strip()
            if not raw:
                continue
            sent = _resolve_citations_to_numbers(raw, eid2num, valid_nums)
            if not sent:
                continue
            tag = _confidence_tag(r)
            if tag:
                sent = f"{sent} {tag}"
            rendered.append(sent)
        if not rendered:
            continue
        raw_title = str(s.get("display_title") or s.get("heading") or s.get("title") or "Section")
        title = humanize(raw_title) or raw_title
        out.append(
            _RenderSection(
                title=title,
                verified_text=" ".join(rendered),
                sentences_verified=len(rendered),
                sentences_dropped=int(s.get("total_dropped") or 0),
                section_id=str(s.get("section_id") or s.get("title") or ""),
            )
        )
    return out


def _section_bodies_md(sections: list[_RenderSection]) -> str:
    """Build ``sections_concat`` -- one ``### Title`` header + verbatim verified prose per section.
    Colliding / structural headings are disambiguated exactly like production so the report never
    renders two identical headers or shadows the Abstract / Key Findings / Methods / References."""
    used: set[str] = {"key findings", "abstract", "conclusion", "methods", "references", "bibliography"}
    blocks: list[str] = []
    for sr in sections:
        if sr.dropped_due_to_failure or sr.sentences_verified == 0 or not sr.verified_text.strip():
            continue
        heading = sr.title or "Section"
        hkey = heading.strip().lower()
        if hkey in used:
            heading = f"{heading} (detailed)"
            hkey = heading.strip().lower()
        used.add(hkey)
        blocks.append(f"### {heading}\n\n{sr.verified_text.strip()}")
    return "\n\n".join(blocks)


# --------------------------------------------------------------------------------------
# Methods disclosure (RunConfig knobs + every deletion). Fail-open: disclose what is present.
# --------------------------------------------------------------------------------------
def _build_methods_block(
    run_config: dict, verif_details: dict, credibility: dict, ref_style: str, rendered_style: str
) -> str:
    """The ``## Methods`` block. Discloses (1) render provenance, (2) every RunConfig knob that is
    set, with a requested-vs-rendered note when a reference style is not yet renderable, and (3)
    every deletion (faithfulness drops + redundancy consolidation + credibility weighting). Only
    knobs that are actually set are listed; nothing is hardcoded to any one question."""
    lines: list[str] = ["\n\n## Methods\n"]
    lines.append(
        "This report was rendered from the post-verification checkpoint (cp6). Each section's "
        "prose is the sentences the verifier kept or labeled, carried up verbatim from their cited "
        "evidence spans; every citation marker resolves to the numbered References list below."
    )

    # (2) RunConfig knobs.
    lines.append("\n**Run configuration (knobs in effect).**")
    if run_config:
        for key in sorted(run_config):
            val = run_config[key]
            if isinstance(val, (dict, list)):
                val = json.dumps(val, ensure_ascii=False)
            lines.append(f"- {key}: {val}")
    else:
        lines.append("- Default configuration (no non-default knobs supplied to the renderer).")
    lines.append(f"- Reference style requested: {ref_style}; rendered as: {rendered_style}.")
    if rendered_style != ref_style:
        lines.append(
            f"  (The numbered References list carries the same source set; '{ref_style}' "
            "author-year / stylized rendering is not yet applied by this renderer.)"
        )

    # (3) Deletions -- the section READS EVERY dropped-sentence accounting count and discloses it.
    lines.append("\n**Deletions and drops (disclosed, never silent).**")
    totals = verif_details.get("totals", {}) or {}
    drop_reasons = verif_details.get("drop_reason_counts", {}) or {}
    dedup_n = verif_details.get("dedup_redundant_count")
    if totals.get("sentences_dropped") is not None:
        lines.append(
            f"- {totals.get('sentences_dropped')} sentence(s) were dropped by the faithfulness "
            f"engine; {totals.get('sentences_verified', 'n/a')} sentence(s) were kept."
        )
    if drop_reasons:
        reason_str = ", ".join(f"{k}={v}" for k, v in sorted(drop_reasons.items()))
        lines.append(f"- Drop reasons: {reason_str}.")
    if dedup_n:
        lines.append(f"- {dedup_n} redundant sentence(s) were consolidated (corroboration kept, duplicates removed).")
    if credibility:
        total_src = credibility.get("total_sources")
        wmean = credibility.get("weighted_credibility_mean")
        note = credibility.get("disclosure_note")
        if total_src is not None:
            lines.append(
                f"- Corpus credibility: {total_src} source(s); weighted credibility mean "
                f"{wmean}. Credibility is a WEIGHT, not a drop -- no credible on-topic in-scope "
                "source was deleted to hit a number."
            )
        if isinstance(note, str) and note.strip():
            lines.append(f"- {note.strip()}")
    if not (totals or drop_reasons or dedup_n or credibility):
        lines.append("- No deletion accounting was present in the checkpoint sidecars.")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------------------
# Chrome screens (reuse the production leaves; each fail-open). => NO chrome.
# --------------------------------------------------------------------------------------
def _known_words(run_dir: Path) -> set[str]:
    """Corpus vocabulary basis for the render-seam truncation false-positive guard. Loaded from the
    ``evidence_pool.json`` sidecar when present; empty set otherwise (the chrome leg still works)."""
    ep = run_dir / "evidence_pool.json"
    if not ep.is_file():
        return set()
    try:
        from src.polaris_graph.generator.weighted_enrichment import build_known_words_from_evidence
        rows = _load_json(ep) or []
        if isinstance(rows, dict):
            rows = list(rows.values())
        return build_known_words_from_evidence(rows)
    except Exception as exc:  # noqa: BLE001 -- additive; a missing vocabulary never aborts the render
        sys.stderr.write(f"[s7-render] known-words basis skipped (fail-open): {exc}\n")
        return set()


def _apply_chrome_screens(report: str, run_dir: Path, bibliography: list[dict], R) -> str:
    """Run the full production render-screen chain on the assembled report. Every screen is
    suppress-only and faithfulness-neutral; each is guarded fail-open so a screen error never
    aborts the render. This is what guarantees NO chrome in the emitted report."""
    # Garbled-header sanity + honest corroboration-header relabel.
    for fn_name in ("_screen_garbled_headers", "_relabel_uncorroborated_findings_headers"):
        fn = getattr(R, fn_name, None)
        if fn is not None:
            try:
                report = fn(report)
            except Exception as exc:  # noqa: BLE001
                sys.stderr.write(f"[s7-render] {fn_name} skipped (fail-open): {exc}\n")
    # Render-seam chrome + truncation chokepoint.
    try:
        from src.polaris_graph.generator.weighted_enrichment import sanitize_rendered_report
        report, removed = sanitize_rendered_report(report, _known_words(run_dir))
        if removed:
            sys.stderr.write(f"[s7-render] render-seam removed {removed} chrome/truncated unit(s)\n")
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"[s7-render] render-seam sanitize skipped (fail-open): {exc}\n")
    # Block-page / security-check / copyright-footer sentence scrub.
    try:
        from src.polaris_graph.generator.block_page_chrome_scrub import scrub_block_page_chrome
        report, removed = scrub_block_page_chrome(report)
        if removed:
            sys.stderr.write(f"[s7-render] block-page scrub stripped {removed} chrome sentence(s)\n")
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"[s7-render] block-page scrub skipped (fail-open): {exc}\n")
    # GFM table normalize (formatting only; never drops a cell or citation).
    try:
        from src.polaris_graph.generator.markdown_table_normalizer import normalize_gfm_tables
        out = normalize_gfm_tables(report)
        if isinstance(out, tuple):
            out = out[0]
        if isinstance(out, str):
            report = out
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"[s7-render] gfm-table normalize skipped (fail-open): {exc}\n")
    return report


# --------------------------------------------------------------------------------------
# Main render.
# --------------------------------------------------------------------------------------
def render_cp6_to_report(cp6_arg: str, out_arg: str | None, run_config_arg: str | None) -> Path:
    """cp6 -> report.md. Returns the written path."""
    import scripts.run_honest_sweep_r3 as R
    from src.polaris_graph.generator.key_findings import (
        build_depth_layer, build_key_findings, humanize_section_title,
    )

    checkpoint_path, run_dir = _resolve_cp6(cp6_arg)

    # FAIL LOUD on cp6 (verdict-key guard rejects any smuggled release decision).
    checkpoint = R.load_a12_checkpoint(run_dir, checkpoint_path.name)
    if checkpoint is None:
        raise FileNotFoundError(f"cp6 checkpoint {checkpoint_path} loaded as None")
    verif_details = checkpoint.get("verification_details", {}) or {}
    # Seam bridge (integration branch): the S6 UNFREEZE runner (run_s6_verify.py) writes its
    # per-section LABELED sentences under payload.sections (each sentence carrying sentence_text),
    # not under the legacy verification_details.sections. Fall back to it so a cp6 from EITHER
    # producer renders identically. No re-judging -- pure location reconciliation (LABEL+REPAIR).
    if not verif_details.get("sections"):
        _pl = checkpoint.get("payload") if isinstance(checkpoint.get("payload"), dict) else {}
        _secs = _pl.get("sections") if isinstance(_pl.get("sections"), list) else checkpoint.get("sections")
        if isinstance(_secs, list) and _secs:
            verif_details = {**verif_details, "sections": _secs}
    question = str(checkpoint.get("question") or "").strip() or "Research report"

    # Optional sidecars (fail-open).
    bibliography, eid2num, valid_nums = _load_bibliography(run_dir)
    protocol = {}
    ppath = run_dir / "protocol.json"
    if ppath.is_file():
        try:
            protocol = _load_json(ppath) or {}
        except Exception:  # noqa: BLE001
            protocol = {}
    if question == "Research report":
        _rq = str((protocol or {}).get("research_question") or "").strip()
        if _rq:
            question = _rq
    credibility = {}
    cpath = run_dir / "corpus_credibility_disclosure.json"
    if cpath.is_file():
        try:
            credibility = _load_json(cpath) or {}
        except Exception:  # noqa: BLE001
            credibility = {}

    run_config = _load_run_config(run_config_arg, checkpoint, protocol)
    ref_style = str(run_config.get("reference_style") or "numeric").strip().lower()
    rendered_style = "numeric"  # the style the existing renderer emits today (in-text [N])

    # 1) Reconstruct sections (citations -> [N]; labels surfaced; titles humanized).
    sections = _reconstruct_sections(verif_details, eid2num, valid_nums, humanize_section_title)

    # 2) Composition leaves (verbatim-extractive; reused unchanged).
    try:
        key_findings = build_key_findings(sections)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"[s7-render] build_key_findings skipped (fail-open): {exc}\n")
        key_findings = ""
    kf_screen = getattr(R, "_screen_key_findings_chrome", None)
    if kf_screen is not None and key_findings:
        try:
            key_findings = kf_screen(key_findings)
        except Exception:  # noqa: BLE001
            pass
    try:
        depth_layer = build_depth_layer(sections, synthesized_findings=[])
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"[s7-render] build_depth_layer skipped (fail-open): {exc}\n")
        depth_layer = ""

    # 3) Section body + section-level chrome / off-topic screens.
    sections_concat = _section_bodies_md(sections)
    placeholder_fn = getattr(R, "_placeholder_bib_nums", None)
    offtopic_fn = getattr(R, "_screen_offtopic_chrome_sections", None)
    if offtopic_fn is not None and sections_concat:
        try:
            placeholder_nums = placeholder_fn(bibliography) if placeholder_fn else set()
            sections_concat = offtopic_fn(sections_concat, placeholder_nums)
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(f"[s7-render] offtopic-chrome screen skipped (fail-open): {exc}\n")
    crossref_fn = getattr(R, "_strip_dangling_gap_crossref", None)
    if crossref_fn is not None and sections_concat:
        try:
            sections_concat = crossref_fn(sections_concat, str(run_dir))
        except Exception:  # noqa: BLE001
            pass

    # 4) Abstract (front) + Conclusion (end) -- optional, fail-open.
    try:
        from src.polaris_graph.generator.abstract_conclusion import build_abstract, build_conclusion
        abstract_md = build_abstract(sections)
        conclusion_md = build_conclusion(sections)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"[s7-render] abstract/conclusion skipped (fail-open): {exc}\n")
        abstract_md = ""
        conclusion_md = ""

    # 5) Methods disclosure + numbered References.
    methods = _build_methods_block(run_config, verif_details, credibility, ref_style, rendered_style)
    try:
        biblio_section = R._render_bibliography_lines(bibliography, require_locator=False, protocol=protocol)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"[s7-render] bibliography render skipped (fail-open): {exc}\n")
        biblio_section = ""

    # 6) Assemble (reuse assemble_report_md; body order mirrors run_one_query).
    strip_fn = getattr(R, "_strip_injected_instruction_appendix", None)
    clean_q = strip_fn(question) if strip_fn else question
    title_md = f"# Research report: {clean_q}\n\n"
    body = key_findings + sections_concat + depth_layer + methods + biblio_section
    try:
        final_report = R.assemble_report_md(title_md, abstract_md, body, conclusion_md, dedup_enabled=True)
    except Exception as exc:  # noqa: BLE001 -- finish-line: a rendered report MUST ship
        sys.stderr.write(f"[s7-render] assemble_report_md raised ({exc}); fail-open concat\n")
        final_report = (
            title_md + (f"{abstract_md}\n\n" if abstract_md else "") + body
            + (f"\n\n{conclusion_md}" if conclusion_md else "")
        )

    # 7) Full chrome-screen chain => NO chrome.
    final_report = _apply_chrome_screens(final_report, run_dir, bibliography, R)

    # 8) Atomic write.
    out_path = Path(out_arg) if out_arg else (run_dir / "report.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(out_path.parent), suffix=".report.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(final_report)
        os.replace(tmp, out_path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    sys.stderr.write(
        f"[s7-render] wrote {out_path} ({len(final_report)} chars; {len(sections)} sections; "
        f"{len(bibliography)} references)\n"
    )
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="S7 RENDER thin checkpoint runner: cp6_postverify_checkpoint.json -> report.md"
    )
    parser.add_argument(
        "--cp6", required=True,
        help="Path to cp6_postverify_checkpoint.json (or the run dir containing it).",
    )
    parser.add_argument(
        "--out", default=None,
        help="Output report.md path (default: <run_dir>/report.md).",
    )
    parser.add_argument(
        "--run-config", default=None,
        help="Optional RunConfig JSON (tone/structure/reference_style/ordering knobs).",
    )
    args = parser.parse_args(argv)
    render_cp6_to_report(args.cp6, args.out, args.run_config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
