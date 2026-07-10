#!/usr/bin/env python3
"""Fast compose-stage harness (I-comp-fastloop-001 / Fable design 2026-07-09).

Proves in MINUTES — not the hours-long full pipeline — whether the COMPOSITION /
synthesis / render stage keeps the known I-deepfix-006 defect classes OUT of the
rendered ``report.md`` for a labeled set of REAL banked evidence rows. It chains
off the fetch harness (``--bridge <bodies.json>``) or runs on banked content
alone.

It exercises the PRODUCTION compose path at 100% fidelity through the sanctioned
resume seam:

    run_gate_b.py --only <slug> --resume --out-root <case_out_root>

which re-enters at the post-selection ``corpus_snapshot.json`` and re-runs
generation + strict_verify + NLI + 4-role D8 + render + the external evaluator on
whatever (small) row subset the case supplies — no re-fetch, no re-bill of
retrieval. The harness NEVER reimplements composition; it writes the subset
snapshot, subprocesses the real launcher, then reads the produced artifacts.

TWO independent verdict legs (§-1.1 + the I-wire-013 blind-predicate lesson —
shared code is a shared blind spot):
  * Leg A — the production gates' OWN artifacts (evaluator_rule_checks.json
    PT11/PT13, the render chrome canary, manifest verification /
    synthesis_entailment_verified). Read, never re-implemented.
  * Leg B — HARNESS-OWNED clean-room checks on report.md that import ZERO
    production predicate (own front-matter / chrome / markup / shell / truncated-
    number / doubled-disclosure / confidence-clutter rules). Every FAIL QUOTES the
    offending span (never a count). The extractive/quote-dump tripwire is ADVISORY
    (worst paragraph quoted; the binding call stays the operator's §-1.1 read).

Exit codes (identical semantics to the fetch harness): 0 green, 1 any FAIL /
UNREACHABLE, 2 VOID (a required fix-flag OFF / OPENROUTER key missing / fetch RED
without --allow-unbridged), 3 internal harness error or gate-0 canary red.

Read-only vs ``src/`` (imports + subprocess only; edits nothing). Real banked /
bridged content only (LAW II); the only synthetic fixtures live under
``tests/fixtures/compose_harness/`` and are built from REAL banked defect spans.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import yaml

# Make ``src`` / ``scripts`` importable when run directly (sys.path[0] is scripts/).
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_CASES_PATH = _REPO_ROOT / "config" / "compose_harness_cases.yaml"
_OUTPUT_ROOT = _REPO_ROOT / "outputs" / "compose_harness"
_FIXTURE_DIR = _REPO_ROOT / "tests" / "fixtures" / "compose_harness"
_RUN_GATE_B = _REPO_ROOT / "scripts" / "dr_benchmark" / "run_gate_b.py"
_RENDER_AUDIT = _REPO_ROOT / "scripts" / "iwire013_fast_render_audit.py"
_ACCEPT_HARNESS = _REPO_ROOT / "scripts" / "rendered_report_acceptance_harness.py"

# ── Verdict labels ──────────────────────────────────────────────────────────
PASS = "PASS"
FAIL = "FAIL"
DEGRADED_OK = "DEGRADED_OK"
UNREACHABLE = "UNREACHABLE"
VOID = "VOID"

# ANALYST_SYNTHESIS_DISCLOSURE[:40] as a LOCAL literal (NOT imported — the harness
# never imports the predicate it checks). Verified byte-identical to
# src/polaris_graph/generator/analyst_synthesis.py:64 head (2026-07-09).
_ANALYST_DISCLOSURE_HEAD = "This section is analyst synthesis: inter"

# The 14 I-deepfix-006 flags, each with its module's ``*_enabled()`` reader. All
# default-ON; any OFF => RESULT VOID (a compose fix cannot be proven behind a flag
# that is off). Imported LAZILY inside ``check_flags`` so importing this module
# (e.g. by the offline oracle tests) opens no heavy src import and no socket.
_FLAG_READERS: tuple[tuple[str, str, str], ...] = (
    ("PG_SYNTH_ENTAILMENT_VERIFY", "src.polaris_graph.generator.depth_synthesis", "synthesis_entailment_verify_enabled"),
    ("PG_SYNTH_SINGLE_SOURCE", "src.polaris_graph.generator.depth_synthesis", "single_source_synthesis_enabled"),
    ("PG_SYNTH_D8_PROMOTE", "src.polaris_graph.generator.depth_synthesis", "synth_d8_promote_enabled"),
    ("PG_SYNTH_BODY_LEAD", "src.polaris_graph.generator.multi_section_generator", "_body_lead_enabled"),
    ("PG_COMPOSE_NUMERIC_CITE_GUARANTEE", "src.polaris_graph.generator.multi_section_generator", "_compose_numeric_cite_guarantee_enabled"),
    ("PG_SYNTH_RENDER_CLEAN", "src.polaris_graph.generator.analyst_synthesis", "_render_clean_enabled"),
    ("PG_INLINE_FURNITURE_STRIP", "src.polaris_graph.generator.weighted_enrichment", "_inline_furniture_strip_enabled"),
    ("PG_INLINE_MARKUP_STRIP", "src.polaris_graph.generator.weighted_enrichment", "_inline_markup_strip_enabled"),
    ("PG_SHELL_SOURCE_INPUT_SCREEN", "src.polaris_graph.generator.weighted_enrichment", "_shell_source_input_screen_enabled"),
    ("PG_EVIDENCE_BASE_FINDING_PREFERENCE", "src.polaris_graph.generator.weighted_enrichment", "_evidence_base_finding_preference_enabled"),
    ("PG_UNCOVERED_DISCLOSURE_REFORMAT", "src.polaris_graph.generator.verified_compose", "_uncovered_disclosure_reformat_enabled"),
    ("PG_FULL_QUOTE_WINDOW_SNAP", "src.polaris_graph.generator.verified_compose", "_full_quote_window_snap_enabled"),
    ("PG_SENTENCE_SPLIT_SYMBOL_BOUNDARY", "src.polaris_graph.generator.provenance_generator", "_sentence_split_symbol_boundary_enabled"),
    ("PG_PT13_LEXICON_V2", "src.polaris_graph.generator.provenance_generator", "_pt13_lexicon_v2_enabled"),
)

# ── Oracle tuning (harness-owned; env-tunable per LAW VI, never a hard verdict) ──
_QUOTE_DUMP_ADVISORY_FRAC = float(os.environ.get("PG_COMPOSE_QUOTE_DUMP_FRAC", "0.6") or "0.6")
_QUOTE_DUMP_MIN_SQUASH = 48          # ignore trivially-short verbatim overlaps
_LINK_DENSITY_MIN_FRAC = 0.5         # a body sentence >=50% link tokens is a shell narration
_LINK_DENSITY_MIN_TOKENS = 4

_PROV_TOKEN_RE = re.compile(r"\[#ev:([^:\]]+):[^\]]*\]")
_NUMBER_RE = re.compile(r"(?<![\d.])(\d[\d,]*)(?![\d.])")   # an integer NOT already carrying a decimal
_CONFIDENCE_RE = re.compile(r"\[confidence\s*:", re.IGNORECASE)
_MARKUP_RE = re.compile(
    r"\]\((?:https?://|/)[^)]+\)"     # markdown link target
    r"|https?://\S{6,}"               # naked URL
    r"|&amp;|&nbsp;|&gt;|&lt;"        # html entity debris
    r"|\!\[Image"                     # image-alt debris
    r"|\|[^|\n]*\|[^|\n]*\|",         # >=2-pipe table-row debris
    re.IGNORECASE,
)
_LINK_TOKEN_RE = re.compile(
    r"https?://|www\.|\]\(|\)\[|^/|/\S|\.(?:com|org|net|edu|gov|io|svg|png|pdf)\b", re.IGNORECASE)

# Harness-OWNED squashed fingerprint sets. FRONT-MATTER: own regex/phrase list, NOT
# ``is_issue_front_matter``. CHROME: delivery-widget + gov-banner furniture.
_FRONT_MATTER_PHRASES = (
    "would like to thank", "we thank", "the authors thank", "acknowledgements",
    "suggested citation", "recommended citation", "cite this article as",
    "all rights reserved", "beis research report number",
)
_CHROME_PHRASES = (
    "crossref", "web of science", "google scholar", "altmetric",
    "an official website of the united states government",
    "view all access options", "export citation", "reading time",
)


# ── Block (a): leg-B harness-owned defect oracle (pure; imported by the tests) ──
def squash(text: Optional[str]) -> str:
    """NFKD -> strip combining marks -> casefold -> keep letters+digits only.

    Survives PDF hyphen-breaks, diacritics, case, whitespace. Idempotent (fetch-
    harness style), so pre-squashed fingerprints can be squashed again at load.
    """
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    no_marks = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    return "".join(ch for ch in no_marks.casefold() if ch.isalnum())


def strip_provenance_tokens(text: str) -> str:
    """Remove ``[#ev:<id>:<a>-<b>]`` provenance tokens so a phrase/chrome check never
    matches inside a citation token (they are kept for the number-continuation leg)."""
    return _PROV_TOKEN_RE.sub(" ", text or "")


def _bibliography_cut(report_text: str) -> str:
    """Return report body with any trailing References / Bibliography / Sources /
    Works Cited section removed — chrome that lives ONLY in the bibliography is not a
    prose weld (bibliographies legitimately carry Crossref-style furniture)."""
    lines = (report_text or "").splitlines()
    for i, ln in enumerate(lines):
        if re.match(r"^\s{0,3}#{1,6}\s*(references|bibliography|sources|works cited)\b", ln, re.IGNORECASE):
            return "\n".join(lines[:i])
    return report_text or ""


def body_paragraphs(report_text: str) -> list[str]:
    """Prose paragraphs of the report body: blank-line-separated blocks that are NOT
    markdown headers / table rows / block-quotes / bullet furniture. Provenance
    tokens are stripped (phrase checks) — the raw form is used by the number leg."""
    body = _bibliography_cut(report_text)
    paras: list[str] = []
    for block in re.split(r"\n\s*\n", body):
        stripped = block.strip()
        if not stripped:
            continue
        # Drop blocks that are entirely header / table / rule furniture.
        content_lines = [ln for ln in stripped.splitlines()
                         if ln.strip() and not re.match(r"^\s{0,3}(#{1,6}\s|\||\-{3,}|={3,})", ln)]
        if not content_lines:
            continue
        paras.append(strip_provenance_tokens(" ".join(content_lines)).strip())
    return [p for p in paras if p]


def body_sentences(report_text: str) -> list[str]:
    """Body prose split into sentence-ish units (token-stripped). Used by every
    phrase-based leg so a FAIL can quote the single offending sentence."""
    sents: list[str] = []
    for para in body_paragraphs(report_text):
        for piece in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'Ѐ-ӿ])", para):
            piece = piece.strip()
            if piece:
                sents.append(piece)
    return sents


def _phrase_findings(sentences: list[str], phrases: Iterable[str], kind: str) -> list[dict]:
    needles = [squash(p) for p in phrases if p]
    out: list[dict] = []
    for sent in sentences:
        sq = squash(sent)
        for needle, raw in zip(needles, phrases):
            if needle and needle in sq:
                out.append({"kind": kind, "span": sent[:300], "detail": f"contains {raw!r}"})
                break
    return out


def front_matter_findings(sentences: list[str]) -> list[dict]:
    """Paper front-matter (acknowledgements / suggested-citation / masthead) welded
    into prose. OWN phrase list — never imports ``is_issue_front_matter``."""
    return _phrase_findings(sentences, _FRONT_MATTER_PHRASES, "front_matter_weld")


def chrome_findings(sentences: list[str]) -> list[dict]:
    """Delivery chrome (Crossref widget, gov banner, citation-export furniture) welded
    into prose."""
    return _phrase_findings(sentences, _CHROME_PHRASES, "chrome_weld")


def markup_findings(sentences: list[str]) -> list[dict]:
    """Raw markdown-link / naked-URL / html-entity / table-row debris inside body
    prose (the compose stage should emit clean prose, never source markup)."""
    out: list[dict] = []
    for sent in sentences:
        m = _MARKUP_RE.search(sent)
        if m:
            out.append({"kind": "markup_fragment", "span": sent[:300],
                        "detail": f"markup/url fragment {m.group(0)[:60]!r}"})
    return out


def _link_density(sentence: str) -> float:
    tokens = [t for t in re.split(r"\s+", sentence) if t]
    if len(tokens) < _LINK_DENSITY_MIN_TOKENS:
        return 0.0
    link = sum(1 for t in tokens if _LINK_TOKEN_RE.search(t))
    return link / len(tokens)


def shell_findings(sentences: list[str], must_not_render: Iterable[str]) -> list[dict]:
    """Empty-shell / nav-link-farm source narrated as a finding: a link-density rule
    (>=50% link tokens) plus the case's own ``must_not_render`` shell fingerprints."""
    out: list[dict] = []
    for sent in sentences:
        dens = _link_density(sent)
        if dens >= _LINK_DENSITY_MIN_FRAC:
            out.append({"kind": "shell_narration", "span": sent[:300],
                        "detail": f"link-token density {dens:.0%}"})
    out.extend(_phrase_findings(sentences, must_not_render, "must_not_render"))
    return out


def truncated_number_findings(report_text: str, pool_by_id: dict[str, dict],
                              must_render: Iterable[str], must_not_render: Iterable[str]) -> list[dict]:
    """DETERMINISTIC decimal-truncation check: for every INTEGER in a prose sentence
    that carries a provenance token, look up the cited row's span; FAIL if the span
    shows that integer immediately continued by a decimal (``175`` in prose where the
    span says ``175.2``). Left-boundary-guarded so ``5`` never matches inside ``50``.
    Plus the case's own ``must_render`` (full published form MUST survive) /
    ``must_not_render`` fingerprints."""
    out: list[dict] = []
    # Provenance tokens attach to the sentence they cite, but a following token can be
    # split onto its own line by markdown; associate ids at PARAGRAPH scope (the local
    # citation context) and quote the SENTENCE that carries the number.
    for raw_para in re.split(r"\n\s*\n", _bibliography_cut(report_text)):
        ids = _PROV_TOKEN_RE.findall(raw_para)
        if not ids:
            continue
        clean_para = strip_provenance_tokens(raw_para)
        for sent in re.split(r"(?<=[.!?])\s+", clean_para):
            for num_match in _NUMBER_RE.finditer(sent):
                num = num_match.group(1)
                hit = False
                for eid in ids:
                    row = pool_by_id.get(eid)
                    if not row:
                        continue
                    span = row.get("direct_quote") or ""
                    for sm in re.finditer(re.escape(num), span):
                        left = span[sm.start() - 1] if sm.start() > 0 else ""
                        if left.isdigit() or left == ".":
                            continue                    # not a left boundary
                        after = span[sm.end(): sm.end() + 2]
                        if re.match(r"\.\d", after):     # decimal continuation
                            out.append({
                                "kind": "truncated_number", "span": sent.strip()[:300],
                                "detail": f"prose {num!r} but cited span [{eid}] continues "
                                          f"{span[sm.start(): sm.end() + 4]!r}",
                            })
                            hit = True
                            break
                    if hit:
                        break
    body_sq = squash(strip_provenance_tokens(_bibliography_cut(report_text)))
    for mr in (must_render or []):
        if mr and squash(mr) not in body_sq:
            out.append({"kind": "missing_must_render", "span": str(mr),
                        "detail": "required full published number absent from body"})
    out.extend(_phrase_findings(body_sentences(report_text), must_not_render, "must_not_render"))
    return out


def doubled_disclosure_findings(report_text: str) -> list[dict]:
    """The Analyst-Synthesis disclosure must render at most ONCE. Counts the LOCAL
    literal head (never imported); >1 => FAIL with both line numbers."""
    lines = (report_text or "").splitlines()
    hits = [i + 1 for i, ln in enumerate(lines) if _ANALYST_DISCLOSURE_HEAD in ln]
    if len(hits) > 1:
        return [{"kind": "doubled_disclosure", "span": _ANALYST_DISCLOSURE_HEAD,
                 "detail": f"disclosure rendered {len(hits)}x at lines {hits}"}]
    return []


def confidence_clutter_findings(sentences: list[str]) -> list[dict]:
    """Per-sentence ``[confidence:...]`` clutter must be gone when PG_SYNTH_RENDER_CLEAN
    is ON."""
    out: list[dict] = []
    for sent in sentences:
        if _CONFIDENCE_RE.search(sent):
            out.append({"kind": "confidence_clutter", "span": sent[:300],
                        "detail": "per-sentence [confidence:...] clutter"})
    return out


def quote_dump_advisory(report_text: str, pool_rows: list[dict]) -> dict:
    """ADVISORY extractive tripwire (never a FAIL per §-1.1's ban on counts as
    verdicts): fraction of body sentences that are verbatim (squashed) substrings of a
    pool span, and the WORST paragraph is always quoted for the operator's read."""
    span_sqs = [squash(r.get("direct_quote") or "") for r in (pool_rows or [])]
    span_sqs = [s for s in span_sqs if s]
    worst_para, worst_frac = "", 0.0
    total_verbatim, total_sents = 0, 0
    for para in body_paragraphs(report_text):
        sents = [s for s in re.split(r"(?<=[.!?])\s+", para) if squash(s)]
        if not sents:
            continue
        verbatim = 0
        for s in sents:
            ssq = squash(s)
            if len(ssq) >= _QUOTE_DUMP_MIN_SQUASH and any(ssq in span for span in span_sqs):
                verbatim += 1
        total_verbatim += verbatim
        total_sents += len(sents)
        frac = verbatim / len(sents)
        if frac > worst_frac or (frac == worst_frac and len(para) > len(worst_para)):
            worst_frac, worst_para = frac, para
    overall = (total_verbatim / total_sents) if total_sents else 0.0
    return {
        "overall_verbatim_frac": round(overall, 3),
        "worst_paragraph_frac": round(worst_frac, 3),
        "advisory_threshold": _QUOTE_DUMP_ADVISORY_FRAC,
        "advisory_tripped": worst_frac >= _QUOTE_DUMP_ADVISORY_FRAC,
        "worst_paragraph": worst_para[:600],
        "binding": False,
    }


def run_leg_b_oracle(report_text: str, pool_rows: list[dict], case: dict) -> dict:
    """Run every harness-owned leg on ``report_text``. Returns findings (each with the
    offending span QUOTED) + the advisory quote-dump block. A non-empty ``findings``
    list => the case FAILs leg B."""
    sents = body_sentences(report_text)
    pool_by_id = {r.get("evidence_id"): r for r in (pool_rows or []) if r.get("evidence_id")}
    findings: list[dict] = []
    findings += front_matter_findings(sents)
    findings += chrome_findings(sents)
    findings += markup_findings(sents)
    findings += shell_findings(sents, case.get("must_not_render") or [])
    findings += truncated_number_findings(
        report_text, pool_by_id, case.get("must_render") or [], case.get("must_not_render") or [])
    findings += doubled_disclosure_findings(report_text)
    findings += confidence_clutter_findings(sents)
    return {"findings": findings, "advisory": quote_dump_advisory(report_text, pool_rows)}


# ── Block (b): gate-0 canary (from I-comp-002) ──────────────────────────────
# The deterministic leg kinds a known-bad seeded fixture MUST trip before any case
# verdict is trusted. Shell/markup depend on the exact banked span shape, so the
# canary requires only the deterministic-by-construction legs.
_CANARY_REQUIRED_KINDS = frozenset({
    "front_matter_weld", "chrome_weld", "truncated_number",
    "doubled_disclosure", "confidence_clutter",
})


def gate0_canary(fixture_dir: Path = _FIXTURE_DIR) -> tuple[bool, dict]:
    """FAIL a known-bad seeded report (one of each defect, built from REAL banked
    defect spans) AND PASS a known-clean one. Canary red => the oracle is broken; the
    caller writes NO case verdicts and exits 3."""
    detail: dict = {}
    try:
        bad = (fixture_dir / "known_bad_report.md").read_text(encoding="utf-8")
        clean = (fixture_dir / "known_clean_report.md").read_text(encoding="utf-8")
        pool = json.loads((fixture_dir / "canary_pool.json").read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — a missing fixture is a red canary, not a pass
        return False, {"error": f"canary fixtures unreadable: {exc}"}
    case = {"must_not_render": []}
    bad_res = run_leg_b_oracle(bad, pool, case)
    clean_res = run_leg_b_oracle(clean, pool, case)
    bad_kinds = {f["kind"] for f in bad_res["findings"]}
    missing = _CANARY_REQUIRED_KINDS - bad_kinds
    clean_fail = clean_res["findings"]
    detail = {
        "known_bad_kinds": sorted(bad_kinds),
        "missing_required_kinds": sorted(missing),
        "known_clean_findings": clean_fail,
    }
    ok = (not missing) and (not clean_fail)
    return ok, detail


# ── Block (e): flag-gate refusal (can't fake a pass) ────────────────────────
def _falsey(value: Optional[str]) -> bool:
    return (value or "").strip().lower() in ("0", "false", "off", "no", "disabled")


def check_flags(profile: str) -> tuple[bool, dict]:
    """Assert every I-deepfix-006 fix-flag is ON (each module's own ``*_enabled()``
    reader), plus — for the pipeline profile — PG_STRICT_VERIFY_ENTAILMENT=enforce and
    an OPENROUTER key. Returns (ok, states). Any OFF => the caller writes RESULT VOID."""
    import importlib
    states: dict[str, bool] = {}
    for env_name, module_path, reader in _FLAG_READERS:
        try:
            mod = importlib.import_module(module_path)
            states[env_name] = bool(getattr(mod, reader)())
        except Exception as exc:  # noqa: BLE001 — a reader that will not import is not "ON"
            states[env_name] = False
            states[f"{env_name}__import_error"] = str(exc)[:200]
    if profile == "pipeline":
        states["PG_STRICT_VERIFY_ENTAILMENT_enforce"] = (
            os.environ.get("PG_STRICT_VERIFY_ENTAILMENT", "").strip().lower() == "enforce")
        states["OPENROUTER_KEY_present"] = bool(
            (os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_KEY") or "").strip())
    ok = all(v for k, v in states.items() if not k.endswith("__import_error"))
    return ok, states


# ── Block (d): content bridge (fetch harness -> compose) ────────────────────
def load_bridge(path: Path) -> dict:
    """Load a fetch-harness ``--dump-bodies`` bodies.json into {ev|url -> record}."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    records = data.get("bodies", data) if isinstance(data, dict) else data
    index: dict[str, dict] = {}
    for rec in records or []:
        if rec.get("ev"):
            index[f"ev:{rec['ev']}"] = rec
        if rec.get("url"):
            index[f"url:{rec['url']}"] = rec
    return index


def apply_bridge(rows: list[dict], bridge_index: dict, case: dict) -> tuple[list[dict], dict]:
    """For each row whose bridged fetch verdict is PASS, REPLACE ``direct_quote`` with
    the recovered full body (+ statement head). Tier / authority / title / url stay
    from the banked row — content changes, weight never. FAIL/UNREACHABLE fetch rows
    (and PASS rows with an empty body) are NOT bridged — the banked row is kept and the
    row id is recorded as STALE so ``run_case`` can VOID a mixed bridge (any fetch-RED
    row) unless ``--allow-unbridged`` (design §3 item 3). Returns (rows, stats)."""
    bridged, offered_not, no_body = 0, 0, 0
    stale_ids: list[str] = []
    new_rows: list[dict] = []
    for row in rows:
        rec = bridge_index.get(f"ev:{row.get('evidence_id')}")
        if rec is None and row.get("source_url"):
            rec = bridge_index.get(f"url:{row.get('source_url')}")
        if rec is None:
            new_rows.append(row)
            continue
        if str(rec.get("verdict", "")).upper() != PASS:
            offered_not += 1
            stale_ids.append(str(row.get("evidence_id")))
            new_rows.append(row)
            continue
        body = rec.get("quote") or rec.get("body") or ""
        if not body.strip():
            no_body += 1
            stale_ids.append(str(row.get("evidence_id")))
            new_rows.append(row)
            continue
        merged = dict(row)
        merged["direct_quote"] = body
        merged["statement"] = body[:200]
        new_rows.append(merged)
        bridged += 1
    stats = {"bridged": bridged, "offered_but_not_bridged": offered_not,
             "no_body_kept_banked": no_body, "stale_evidence_ids": stale_ids,
             "total_rows": len(rows)}
    return new_rows, stats


# ── Block (c): orchestrator (pipeline / render profiles) ────────────────────
def load_cases(path: Path = _CASES_PATH) -> dict:
    """Load + normalize the case file (top-level domain/slug/snapshot + cases list)."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    cases = []
    for entry in raw.get("cases", []):
        case = dict(entry)
        case.setdefault("evidence_ids", [])
        case.setdefault("must_not_render", [])
        case.setdefault("must_render", [])
        cases.append(case)
    return {
        "domain": raw.get("domain", "workforce"),
        "slug": raw.get("slug", "drb_72_ai_labor"),
        "snapshot": raw.get("snapshot", ""),
        "diag_snapshot": raw.get("diag_snapshot", ""),
        "cases": cases,
    }


def _load_snapshot(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _subset_rows(snapshot: dict, evidence_ids: list[str]) -> list[dict]:
    """Select the case's evidence rows from the banked snapshot, PRESERVING order and
    keeping ALL of a duplicated id's occurrences (never a silent drop)."""
    wanted = list(evidence_ids)
    rows = snapshot.get("evidence_for_gen", [])
    by_id: dict[str, list[dict]] = {}
    for r in rows:
        by_id.setdefault(r.get("evidence_id"), []).append(r)
    out: list[dict] = []
    for eid in wanted:
        out.extend(by_id.get(eid, []))
    return out


def _write_subset_snapshot(snapshot: dict, rows: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(snapshot)
    payload["evidence_for_gen"] = rows
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")


def _read_leg_a(query_dir: Path) -> dict:
    """Read the production gates' OWN artifacts, defensively (absent => SKIPPED, never
    a false green): evaluator_rule_checks.json PT11/PT13, manifest verification /
    synthesis_entailment_verified."""
    leg_a: dict = {"rule_checks": "SKIPPED (absent)", "manifest": "SKIPPED (absent)"}
    rc_path = query_dir / "evaluator_rule_checks.json"
    if rc_path.is_file():
        try:
            rc = json.loads(rc_path.read_text(encoding="utf-8"))
            blob = json.dumps(rc).lower()
            leg_a["rule_checks"] = {
                "pt11_present": "pt11" in blob or "uncited" in blob,
                "pt13_present": "pt13" in blob or "superlative" in blob,
                "raw_keys": list(rc.keys()) if isinstance(rc, dict) else "list",
            }
        except Exception as exc:  # noqa: BLE001
            leg_a["rule_checks"] = f"UNREADABLE: {exc}"
    mf_path = query_dir / "manifest.json"
    if mf_path.is_file():
        try:
            mf = json.loads(mf_path.read_text(encoding="utf-8"))
            leg_a["manifest"] = {
                "status": mf.get("status"),
                "synthesis_entailment_verified": mf.get("synthesis_entailment_verified"),
                "verification": mf.get("verification"),
            }
        except Exception as exc:  # noqa: BLE001
            leg_a["manifest"] = f"UNREADABLE: {exc}"
    return leg_a


def _run_acceptance_leg(report_path: Path, out_json: Path) -> dict:
    """Run the INDEPENDENT §-1.1 acceptance reader as an oracle leg on report.md."""
    if not report_path.is_file():
        return {"status": "SKIPPED (no report.md)"}
    try:
        subprocess.run(
            [sys.executable, str(_ACCEPT_HARNESS), "--report", str(report_path),
             "--json-out", str(out_json)],
            cwd=str(_REPO_ROOT), capture_output=True, timeout=180, check=False)
        if out_json.is_file():
            return json.loads(out_json.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"status": f"acceptance leg error: {exc}"}
    return {"status": "SKIPPED (no json out)"}


def _kill_proc(proc: Optional[subprocess.Popen]) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            proc.kill()
    except Exception:  # noqa: BLE001
        pass


class _ChildRegistry:
    """Thread-safe live-subprocess registry so a total-deadline breach can kill every
    pipeline child (§8.4 resource discipline)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._live: set[subprocess.Popen] = set()

    def add(self, proc: subprocess.Popen) -> None:
        with self._lock:
            self._live.add(proc)

    def discard(self, proc: subprocess.Popen) -> None:
        with self._lock:
            self._live.discard(proc)

    def kill_all(self) -> None:
        with self._lock:
            procs = list(self._live)
        for p in procs:
            _kill_proc(p)


def pipeline_verdict(leg_a: dict, subprocess_exit: Optional[int],
                     subprocess_tail: Optional[str], report_exists: bool,
                     leg_b_findings: list[dict]) -> tuple[str, list[dict], str]:
    """Bind the pipeline-profile per-case verdict to ALL legs, not leg B alone (pure —
    imported by the offline oracle tests). A green PASS requires ``manifest.status ==
    'success'`` AND a readable leg A; a nonzero subprocess exit or an ``abort_*`` /
    ``error_*`` manifest status is a FAIL with the status/tail QUOTED (per §9.1
    invariant 4 the abort still writes a report.md, so a leg-B-only verdict would
    false-PASS on zero verified prose); a clean report whose leg A was skipped /
    absent / unreadable is DEGRADED_OK — never PASS, never authorized. Returns
    (verdict, findings_that_bind, note)."""
    findings = list(leg_b_findings or [])
    manifest = leg_a.get("manifest") if isinstance(leg_a, dict) else None
    status = manifest.get("status") if isinstance(manifest, dict) else None

    # 1) Hard pipeline failure: a nonzero subprocess exit binds FAIL (tail quoted).
    if isinstance(subprocess_exit, int) and subprocess_exit != 0:
        tail = (subprocess_tail or "").strip()
        findings.insert(0, {
            "kind": "pipeline_subprocess_fail",
            "span": (tail[-300:] if tail else f"exit={subprocess_exit}"),
            "detail": f"run_gate_b exited nonzero ({subprocess_exit}); compose did not complete"})
        return FAIL, findings, f"pipeline subprocess exit {subprocess_exit}"

    # 2) abort_* / error_* manifest status binds FAIL (status quoted) — zero verified prose.
    if isinstance(status, str) and (status.startswith("abort_") or status.startswith("error_")):
        findings.insert(0, {
            "kind": "manifest_abort_status", "span": status,
            "detail": f"manifest.status={status!r}: compose produced no verified prose"})
        return FAIL, findings, f"manifest.status={status}"

    # 3) No report.md and not an abort we caught above => pipeline error before render.
    if not report_exists:
        return UNREACHABLE, findings, (
            f"pipeline produced no report.md (manifest.status={status!r})")

    # 4) Leg-B harness-owned defects bind FAIL (spans already quoted by the oracle).
    if leg_b_findings:
        return FAIL, findings, ""

    # 5) Clean report: PASS only on a fully-green, readable leg A; else DEGRADED_OK.
    rule_checks = leg_a.get("rule_checks") if isinstance(leg_a, dict) else None
    verification = manifest.get("verification") if isinstance(manifest, dict) else None
    leg_a_green = (status == "success"
                   and isinstance(rule_checks, dict)
                   and verification not in (False, "failed", "FAILED"))
    if leg_a_green:
        return PASS, findings, ""
    return DEGRADED_OK, findings, (
        f"leg B clean but leg A not fully green (status={status!r}, "
        f"rule_checks_present={isinstance(rule_checks, dict)}) => DEGRADED_OK, not authorized")


def run_case(case: dict, cfg: dict, run_dir: Path, profile: str,
             bridge_index: Optional[dict], allow_unbridged: bool,
             case_timeout: int, registry: _ChildRegistry) -> dict:
    """Compose ONE case at full production fidelity, then run leg A + leg B. Returns a
    result dict. Never raises — a harness/pipeline error becomes UNREACHABLE."""
    name = case["name"]
    slug, domain = cfg["slug"], cfg["domain"]
    start = time.monotonic()
    base = {
        "name": name, "expect": case.get("expect", "compose_clean"),
        "verdict": UNREACHABLE, "profile": profile,
        "evidence_ids": case.get("evidence_ids", []),
        "requires": case.get("requires", ""), "bridge": {}, "leg_a": {},
        "leg_b_findings": [], "advisory": {}, "acceptance": {},
        "note": "", "elapsed_s": 0.0,
    }

    # requires: diag_snapshot — the case's real defect rows live ONLY in the fresh
    # diagnostic snapshot; if it is not banked => UNREACHABLE (never skipped). When it
    # IS banked the case must be composed FROM the diag snapshot, not the default one.
    snapshot_rel = cfg["snapshot"]
    if case.get("requires") == "diag_snapshot":
        diag_rel = cfg.get("diag_snapshot", "")
        diag = _REPO_ROOT / diag_rel
        if not (diag_rel and diag.is_file()):
            base["note"] = "requires diag_snapshot (not banked) — UNREACHABLE, not skipped"
            base["elapsed_s"] = round(time.monotonic() - start, 2)
            return base
        snapshot_rel = diag_rel

    case_out_root = run_dir / name / "run"
    query_dir = case_out_root / domain / slug
    report_path = query_dir / "report.md"

    try:
        snapshot = _load_snapshot(_REPO_ROOT / snapshot_rel)
    except Exception as exc:  # noqa: BLE001
        base["note"] = f"snapshot unreadable: {exc}"
        base["elapsed_s"] = round(time.monotonic() - start, 2)
        return base

    rows = _subset_rows(snapshot, case.get("evidence_ids", []))
    if bridge_index is not None:
        rows, base["bridge"] = apply_bridge(rows, bridge_index, case)
        stats = base["bridge"]
        # Design §3 item 3: a compose run on bridged content with ANY fetch-RED row is
        # REFUSED (VOID/exit 2) unless --allow-unbridged. A mixed bridge (one PASS row +
        # one FAIL/UNREACHABLE/no-body row) must NOT compose a fix "green" on partly-stale
        # banked content — so VOID on any stale row, not only when zero rows bridged.
        stale = stats["offered_but_not_bridged"] + stats["no_body_kept_banked"]
        if not allow_unbridged and (stats["bridged"] == 0 or stale > 0):
            base["verdict"] = VOID
            if stale > 0:
                base["note"] = (
                    f"fetch RED on {stale} selected row(s) "
                    f"{stats.get('stale_evidence_ids', [])} (offered-but-not-bridged / "
                    f"no-body, banked content kept) and --allow-unbridged not set")
            else:
                base["note"] = "no rows bridged (fetch not PASS) and --allow-unbridged not set"
            base["elapsed_s"] = round(time.monotonic() - start, 2)
            return base

    pool_rows = rows  # the case pool the oracle grounds numbers against

    if profile == "render":
        rc, note = _run_render_profile(cfg, run_dir, name, registry, case_timeout)
        base["note"] = note
        base["leg_a"] = {"d8": "NOT RUN (render profile)", "writer": "NOT RUN (render profile)",
                         "render_audit_exit": rc}
        # A render-profile pass cannot over-claim: only report available legs.
        if report_path.is_file():
            oracle = run_leg_b_oracle(report_path.read_text(encoding="utf-8"), pool_rows, case)
            base["leg_b_findings"] = oracle["findings"]
            base["advisory"] = oracle["advisory"]
            base["verdict"] = FAIL if oracle["findings"] else DEGRADED_OK
        else:
            base["verdict"] = DEGRADED_OK if rc == 0 else UNREACHABLE
        base["elapsed_s"] = round(time.monotonic() - start, 2)
        return base

    # pipeline profile: write the subset snapshot + subprocess the sanctioned launcher.
    _write_subset_snapshot(snapshot, rows, query_dir / "corpus_snapshot.json")
    env = dict(os.environ)
    env.setdefault("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    cmd = [sys.executable, str(_RUN_GATE_B), "--only", slug, "--resume",
           "--out-root", str(case_out_root)]
    proc = None
    try:
        proc = subprocess.Popen(cmd, cwd=str(_REPO_ROOT), env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        registry.add(proc)
        try:
            out, _ = proc.communicate(timeout=case_timeout)
        except subprocess.TimeoutExpired:
            _kill_proc(proc)
            base["note"] = f"pipeline subprocess exceeded per-case deadline {case_timeout}s"
            base["elapsed_s"] = round(time.monotonic() - start, 2)
            return base
        base["subprocess_exit"] = proc.returncode
        base["subprocess_tail"] = (out or "")[-800:]
    except Exception as exc:  # noqa: BLE001
        base["note"] = f"pipeline subprocess error: {exc}"
        base["elapsed_s"] = round(time.monotonic() - start, 2)
        return base
    finally:
        if proc is not None:
            registry.discard(proc)

    base["leg_a"] = _read_leg_a(query_dir)
    report_exists = report_path.is_file()
    leg_b_findings: list[dict] = []
    if report_exists:
        report_text = report_path.read_text(encoding="utf-8")
        oracle = run_leg_b_oracle(report_text, pool_rows, case)
        leg_b_findings = oracle["findings"]
        base["advisory"] = oracle["advisory"]
        base["acceptance"] = _run_acceptance_leg(report_path, query_dir / "acceptance.json")
        base["report_path"] = str(report_path)

    # Verdict binds to ALL legs, not leg B alone: a nonzero subprocess exit or an
    # abort_* / error_* manifest.status FAILs even when leg B is empty (§9.1 invariant 4
    # writes a report.md on abort_no_verified_sections — a leg-B-only PASS there would
    # green-light the paid run on ZERO verified prose); a clean report whose leg A was
    # skipped / unreadable is DEGRADED_OK (never PASS, never authorized).
    verdict, bound_findings, note = pipeline_verdict(
        base["leg_a"], base.get("subprocess_exit"), base.get("subprocess_tail"),
        report_exists, leg_b_findings)
    base["verdict"] = verdict
    base["leg_b_findings"] = bound_findings
    if note:
        base["note"] = note
    base["elapsed_s"] = round(time.monotonic() - start, 2)
    return base


def _run_render_profile(cfg: dict, run_dir: Path, name: str, registry: _ChildRegistry,
                        case_timeout: int) -> tuple[int, str]:
    """Delegate the render profile to the offline iwire013 fast render audit against the
    banked validate snapshot. D8 + writer legs are stamped NOT RUN by the caller."""
    snap_dir = _REPO_ROOT / os.environ.get("PG_COMPOSE_RENDER_SNAPSHOT_DIR", "outputs/iwire013_validate_local")
    if not snap_dir.is_dir():
        return 3, f"render profile: snapshot dir {snap_dir} absent"
    cmd = [sys.executable, str(_RENDER_AUDIT), "--snapshot-dir", str(snap_dir), "--skip-depth"]
    proc = None
    try:
        proc = subprocess.Popen(cmd, cwd=str(_REPO_ROOT), stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True)
        registry.add(proc)
        try:
            out, _ = proc.communicate(timeout=case_timeout)
        except subprocess.TimeoutExpired:
            _kill_proc(proc)
            return 3, "render audit exceeded per-case deadline"
        return proc.returncode, f"render audit exit {proc.returncode}"
    except Exception as exc:  # noqa: BLE001
        return 3, f"render audit error: {exc}"
    finally:
        if proc is not None:
            registry.discard(proc)


# ── Block (f): UX + parallel runner + writer ────────────────────────────────
def _select(cases: list[dict], only: Optional[list[str]]) -> list[dict]:
    if not only:
        return cases
    wanted = {w.strip() for chunk in only for w in chunk.split(",") if w.strip()}
    return [c for c in cases if c.get("name") in wanted]


def run_all(cases: list[dict], cfg: dict, run_dir: Path, profile: str,
            bridge_index: Optional[dict], allow_unbridged: bool,
            max_parallel: int, case_timeout: int, total_timeout: int) -> list[dict]:
    """Run cases on a bounded pool of DAEMON workers under a HARD total wall-clock
    deadline. On breach, kill every live pipeline child (§8.4) and record any
    unfinished case UNREACHABLE(timeout)."""
    registry = _ChildRegistry()
    deadline = time.monotonic() + float(total_timeout)
    results: dict[str, dict] = {}
    lock = threading.Lock()
    done = {c["name"]: threading.Event() for c in cases}
    sem = threading.BoundedSemaphore(max(1, min(max_parallel, len(cases))))

    def _timeout_result(case: dict) -> dict:
        return {"name": case["name"], "expect": case.get("expect", ""), "verdict": UNREACHABLE,
                "profile": profile, "note": "total-deadline breach (child killed)",
                "leg_a": {}, "leg_b_findings": [], "advisory": {}, "elapsed_s": 0.0}

    def _worker(case: dict) -> None:
        try:
            with sem:
                if time.monotonic() >= deadline:
                    res = _timeout_result(case)
                else:
                    res = run_case(case, cfg, run_dir, profile, bridge_index,
                                   allow_unbridged, case_timeout, registry)
        except BaseException:  # noqa: BLE001 — never die silently
            res = _timeout_result(case)
        with lock:
            results.setdefault(case["name"], res)
        done[case["name"]].set()

    threads = [threading.Thread(target=_worker, args=(c,), name=f"compose-{c['name']}", daemon=True)
               for c in cases]
    for t in threads:
        t.start()
    for case in cases:
        remaining = min(float(case_timeout) + 30.0, deadline - time.monotonic())
        if not done[case["name"]].wait(timeout=max(0.0, remaining)):
            with lock:
                results.setdefault(case["name"], _timeout_result(case))
    registry.kill_all()
    for case in cases:
        with lock:
            results.setdefault(case["name"], _timeout_result(case))
    return [results[c["name"]] for c in cases]


def _summarize(results: list[dict]) -> dict:
    tally: dict[str, int] = {}
    for r in results:
        tally[r["verdict"]] = tally.get(r["verdict"], 0) + 1
    clean_ok = all(r["verdict"] == PASS for r in results if r["name"] == "clean_controls") or \
        not any(r["name"] == "clean_controls" for r in results)
    no_fail = not any(r["verdict"] in (FAIL, UNREACHABLE) for r in results)
    # AUTHORIZE the hours-long paid run ONLY when every case is a strict green PASS: a
    # FAIL / UNREACHABLE / VOID or a DEGRADED_OK (leg A red or unexpectedly skipped) must
    # block it, so a partly-verified compose stage can never green-light the full pipeline.
    all_pass = bool(results) and all(r["verdict"] == PASS for r in results)
    return {"tally": tally, "clean_controls_pass": clean_ok, "no_fail": no_fail,
            "all_pass": all_pass, "authorize_full_pipeline": all_pass and clean_ok}


def write_outputs(results: list[dict], flag_states: dict, cfg: dict, profile: str,
                  bridge_info: dict, run_dir: Path) -> dict:
    run_dir.mkdir(parents=True, exist_ok=True)
    summary = _summarize(results)
    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "profile": profile, "domain": cfg["domain"], "slug": cfg["slug"],
        "flag_states": flag_states, "bridge": bridge_info, "summary": summary,
        "cases": results,
    }
    (run_dir / "results.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                                          encoding="utf-8")

    idx = [
        "# Compose fast-loop harness — report index",
        f"generated_utc: {payload['generated_utc']}",
        f"profile: {profile}  domain: {cfg['domain']}  slug: {cfg['slug']}",
        "",
        "## Fix-flag states (all MUST be ON — else RESULT VOID)",
    ]
    for k, v in flag_states.items():
        idx.append(f"- {k}: {v}")
    idx += ["", "## Bridge", f"- {bridge_info}", "", "## Summary",
            f"- tally: {summary['tally']}",
            f"- clean_controls PASS: {summary['clean_controls_pass']}",
            f"- no FAIL / UNREACHABLE: {summary['no_fail']}",
            f"- AUTHORIZE full pipeline: {summary['authorize_full_pipeline']}",
            "", "## Cases (subset is a TEST INPUT, not a production cap — §-1.3)"]
    for r in results:
        idx.append(f"- [{r['verdict']}] {r['name']} expect={r.get('expect','')} "
                   f"rows={len(r.get('evidence_ids', []))} {r.get('elapsed_s', 0)}s"
                   + (f" — {r['note']}" if r.get("note") else ""))
    (run_dir / "report_index.md").write_text("\n".join(idx) + "\n", encoding="utf-8")

    for r in results:
        case_dir = run_dir / r["name"]
        case_dir.mkdir(parents=True, exist_ok=True)
        lines = [f"# Case {r['name']} — {r['verdict']}",
                 f"expect: {r.get('expect','')}   profile: {profile}",
                 f"evidence_ids ({len(r.get('evidence_ids', []))}): {r.get('evidence_ids', [])}",
                 f"note: {r.get('note','')}", "", "## Leg A (production gate artifacts)",
                 f"{json.dumps(r.get('leg_a', {}), ensure_ascii=False, indent=1)}",
                 "", "## Leg B findings (harness-owned; offending span QUOTED)"]
        if r.get("leg_b_findings"):
            for f in r["leg_b_findings"]:
                lines.append(f"\n### {f['kind']} — {f['detail']}")
                lines.append(f"span: {f['span']!r}")
        else:
            lines.append("(none)")
        adv = r.get("advisory") or {}
        if adv:
            lines += ["", "## Extractive/quote-dump tripwire (ADVISORY — never the verdict)",
                      f"worst_paragraph_frac: {adv.get('worst_paragraph_frac')} "
                      f"(threshold {adv.get('advisory_threshold')}, tripped={adv.get('advisory_tripped')})",
                      f"worst_paragraph: {adv.get('worst_paragraph','')!r}"]
        (case_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


def _env_int(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, default) or default)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Fast compose-stage harness (I-comp-fastloop-001)")
    ap.add_argument("--profile", choices=("pipeline", "render"), default="pipeline",
                    help="pipeline (default, full fidelity) or render (offline iwire013)")
    ap.add_argument("--only", action="append", help="case name(s), comma-ok")
    ap.add_argument("--rerun-failures", metavar="RESULTS_JSON",
                    help="rerun only FAIL/UNREACHABLE cases from a prior results.json")
    ap.add_argument("--list", action="store_true", help="list cases and exit")
    ap.add_argument("--case-file", type=Path, default=_CASES_PATH, help="alternate case yaml")
    ap.add_argument("--bridge", type=Path, default=None,
                    help="fetch-harness bodies.json — bridge PASS bodies into the case rows")
    ap.add_argument("--allow-unbridged", action="store_true",
                    help="permit banked-content-only compose even when --bridge yields no PASS row")
    args = ap.parse_args(argv)

    try:
        cfg = load_cases(args.case_file)
    except Exception as exc:  # noqa: BLE001
        print(f"RESULT ERROR - could not load cases: {exc}", file=sys.stderr)
        return 3
    all_cases = cfg["cases"]

    if args.list:
        for c in all_cases:
            print(f"{c['name']:<26} expect={c.get('expect',''):<14} "
                  f"rows={len(c.get('evidence_ids', [])):<3} requires={c.get('requires','') or '-'}")
        return 0

    if args.rerun_failures:
        try:
            prior = json.loads(Path(args.rerun_failures).read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            print(f"RESULT ERROR - bad --rerun-failures file: {exc}", file=sys.stderr)
            return 3
        fail_names = {c["name"] for c in prior.get("cases", [])
                      if c.get("verdict") in (FAIL, UNREACHABLE)}
        cases = [c for c in all_cases if c["name"] in fail_names]
    else:
        cases = _select(all_cases, args.only)
    if not cases:
        print("ERROR: no cases selected", file=sys.stderr)
        return 3

    # Gate-0 canary FIRST — a broken oracle must not emit any case verdict.
    canary_ok, canary_detail = gate0_canary()
    if not canary_ok:
        print(f"RESULT ERROR - gate-0 canary RED: {canary_detail}", file=sys.stderr)
        return 3

    ok, flag_states = check_flags(args.profile)
    if not ok:
        off = [k for k, v in flag_states.items() if not v and not k.endswith("__import_error")]
        print(f"RESULT VOID - FIX FLAGS OFF: {off}", file=sys.stderr)
        return 2

    bridge_index, bridge_info = None, {}
    if args.bridge is not None:
        try:
            bridge_index = load_bridge(args.bridge)
            bridge_info = {"bridge_file": str(args.bridge), "records": len(bridge_index) // 2}
        except Exception as exc:  # noqa: BLE001
            print(f"RESULT ERROR - bad --bridge file: {exc}", file=sys.stderr)
            return 3

    max_parallel = _env_int("PG_COMPOSE_HARNESS_MAX_PARALLEL", 2)
    case_timeout = _env_int("PG_COMPOSE_HARNESS_CASE_TIMEOUT_S", 2400)
    total_timeout = _env_int("PG_COMPOSE_HARNESS_TOTAL_TIMEOUT_S", 7200)

    run_dir = _OUTPUT_ROOT / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    try:
        results = run_all(cases, cfg, run_dir, args.profile, bridge_index,
                          args.allow_unbridged, max_parallel, case_timeout, total_timeout)
    except Exception as exc:  # noqa: BLE001
        print(f"RESULT ERROR - harness crashed: {exc}", file=sys.stderr)
        return 3

    summary = write_outputs(results, flag_states, cfg, args.profile, bridge_info, run_dir)
    for r in results:
        print(f"[{r['verdict']:<11}] {r['name']:<26} expect={r.get('expect','')}")
    print(f"\ntally={summary['tally']}  clean_controls_pass={summary['clean_controls_pass']}  "
          f"authorize={summary['authorize_full_pipeline']}")
    print(f"report: {run_dir / 'report_index.md'}")
    if any(r["verdict"] == VOID for r in results):
        return 2
    return 0 if summary["no_fail"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
