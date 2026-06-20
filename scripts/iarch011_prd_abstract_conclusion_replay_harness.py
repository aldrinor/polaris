#!/usr/bin/env python3
"""I-arch-011 PR-d behavioral replay-harness — the abstract/exec-summary (front) + conclusion
(end) layer, drafted LAST from the ALREADY-strict_verify-PASSED body (§-1.4, FAIL LOUD).

WHAT THIS PROVES (behaviorally, on a REAL banked corpus_snapshot — not a synthetic fixture)
-------------------------------------------------------------------------------------------
PR-d adds the front Abstract + end Conclusion as VERBATIM re-presentations of already-verified
body sentences — faithful BY IDENTITY (byte-equal to sentences that already passed strict_verify in
the body). It introduces NO new claim and NO new LLM call. (A deterministic cross-claim
author-summary gate was DESIGNED then CUT — see abstract_conclusion.py module docstring: bag-of-atoms
presence-checking provably cannot reject a RECOMBINATION of the body's own atoms, which is the exact
clinical-lethal class the gate targeted; rather than ship a green harness over an unsound gate, PR-d
ships verbatim-only and the synthesis machinery was removed. This harness therefore tests only what
SHIPS.) The harness drives the REAL production builders (``build_abstract`` / ``build_conclusion``)
over REAL SectionResult-shaped verified bodies derived from REAL banked corpus evidence, plus the REAL
frozen ``strict_verify`` and the REAL ``reconcile_report_against_verdicts`` / refilter — NOTHING is
monkeypatched. The corpus evidence text is loaded from a banked ``corpus_snapshot.json``
(``outputs/corpus_backups/extracted/*/`` resolved against the repo root + ancestors so it is found
from an isolated git worktree, or ``PG_PRD_CORPUS_DIR``); on a bare CI checkout it falls back to a
synthetic real-shaped fixture with a LOUD WARNING (never a silent pass-as-if-real).

The assertions (non-zero exit on any miss):
  1. FAITHFUL BY IDENTITY: every sentence rendered in the abstract/conclusion is a VERBATIM body
     sentence (no fabricated/synthesized prose enters the summary), AND that body sentence re-passes
     the REAL strict_verify on its pre-resolve ``[#ev:]`` form (the path is genuinely verified).
  3. WEAK/UNVERIFIED EXCLUSION: a section that is NOT verified (gap-stub / sentences_verified=0 /
     dropped) contributes NO sentence to the abstract/conclusion — only verified body prose is lifted.
  4. FLAG-OFF BYTE-IDENTITY: ``PG_SYNTHESIS_ABSTRACT_CONCLUSION`` unset -> build_abstract/
     build_conclusion return "" so the assembled report.md is BYTE-IDENTICAL to the pre-PR-d render.
  5. EMPTY BODY -> the disclosed "insufficient verified evidence" line renders, NEVER fabricated filler.

PLUS the post-gate REDACTION DUPLICATE landmine (brief P2-2): a verbatim abstract sentence whose
underlying body claim is flipped non-VERIFIED is redacted by the REAL
``reconcile_report_against_verdicts`` in the SAME pass as the body copy, and the REAL
``refilter_abstract_conclusion_block`` then drops the gap-stub'd block (no orphan, no empty heading).

BOUNDED DEADLINE (§-1.4 hard requirement; the PR-c harness lacked this): the strict_verify leg runs
under an EXPLICIT internal wall-clock deadline in a worker thread. If the entailment judge is
UNREACHABLE and strict_verify would hang on the judge socket, the harness FAILS LOUD with a clear
non-zero exit + "judge unreachable" message — it NEVER hangs. It runs the assertions once on the
live-judge path (enforce) and once hermetically under ``PG_STRICT_VERIFY_ENTAILMENT=off`` (reproducible
offline).

Run: ``python scripts/iarch011_prd_abstract_conclusion_replay_harness.py`` -> exit 0 if every
assertion fires, non-zero + the failing assertion on any miss.
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

# Make the repo root importable so the harness runs standalone (§-1.4). scripts/ is one level under it.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Load C:/POLARIS/.env so the live judge runs when a key is present (brief: load_dotenv at startup).
try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(_REPO_ROOT / ".env")
except Exception:  # noqa: BLE001 — dotenv is optional; env may already be exported
    pass

from src.polaris_graph.generator.abstract_conclusion import (  # noqa: E402
    _INSUFFICIENT_EVIDENCE,
    _harvest_abstract_sentences,
    _harvest_conclusion_sentences,
    build_abstract,
    build_conclusion,
    refilter_abstract_conclusion_block,
)
from src.polaris_graph.generator.provenance_generator import strict_verify  # noqa: E402
from src.polaris_graph.roles.report_redactor import (  # noqa: E402
    reconcile_report_against_verdicts,
)

# Bounded internal deadline (seconds) for the single strict_verify leg that may call the live judge.
_STRICT_VERIFY_DEADLINE_S = 90.0


def _fail(case: str, detail: str) -> None:
    print(f"FAIL [{case}]: {detail}", file=sys.stderr)
    sys.exit(1)


# ── A minimal SectionResult stand-in (the builders read getattr fields only). ────────────────
@dataclass
class _FakeSection:
    title: str
    verified_text: str
    sentences_verified: int
    is_gap_stub: bool = False
    dropped_due_to_failure: bool = False


# ── SYNTHETIC REAL-SHAPED FALLBACK (LAW VI): only on a bare CI checkout with NO banked corpus.
# Real numeric clinical sentences (each carries a digit so strict_verify's decimal check fires).
_SYN = [
    ("Efficacy", "Semaglutide reduced major cardiovascular events by 20 percent in adults with obesity."),
    ("Glycaemic control", "Tirzepatide lowered HbA1c by 2.1 percentage points at 40 weeks versus placebo."),
    ("Heart failure", "Empagliflozin reduced heart failure hospitalization by 35 percent in adults."),
]


def _candidate_corpus_paths() -> list[Path]:
    """Banked corpus_snapshot.json candidate paths (LAW VI): ``PG_PRD_CORPUS_DIR``, the repo root, and
    EVERY ancestor of the repo root (so an isolated worktree finds the banked corpus in the main
    checkout above it), then ANY ``extracted/*/corpus_snapshot.json`` under each base."""
    bases: list[Path] = []
    env_dir = os.environ.get("PG_PRD_CORPUS_DIR")
    if env_dir:
        bases.append(Path(env_dir))
    bases.append(_REPO_ROOT)
    bases.extend(_REPO_ROOT.parents)
    out: list[Path] = []
    seen: set[str] = set()
    for base in bases:
        glob_root = base / "outputs" / "corpus_backups" / "extracted"
        try:
            globbed = sorted(glob_root.glob("*/corpus_snapshot.json"))
        except OSError:
            globbed = []
        for p in globbed:
            key = str(p)
            if key not in seen:
                seen.add(key)
                out.append(p)
    return out


def _load_corpus_rows(n: int = 3):
    """Load the first ``n`` SUBSTANTIVE evidence rows from a banked corpus_snapshot.json as
    ``[(evidence_id, direct_quote), ...]``. "Substantive" = quote >= 80 chars AND has a digit AND is
    distinct. Returns ``(rows, path)`` or ``(None, None)`` if none found / too few usable rows."""
    for path in _candidate_corpus_paths():
        try:
            if not path.is_file():
                continue
            with path.open(encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        ev_rows = data.get("evidence_for_gen")
        if not isinstance(ev_rows, list) or not ev_rows:
            ev_rows = data.get("evidence")
        if not isinstance(ev_rows, list) or not ev_rows:
            continue
        picked: list[tuple[str, str]] = []
        seen_quotes: set[str] = set()
        for row in ev_rows:
            if not isinstance(row, dict):
                continue
            eid = row.get("evidence_id") or row.get("id")
            quote = (row.get("direct_quote") or row.get("quote") or "").strip()
            if not eid or not quote:
                continue
            if len(quote) < 80 or not any(ch.isdigit() for ch in quote):
                continue
            if quote in seen_quotes:
                continue
            seen_quotes.add(quote)
            picked.append((str(eid), quote))
            if len(picked) >= n:
                break
        if len(picked) >= n:
            return picked, path
    return None, None


def _resolve_bodies():
    """Build the verified-body inputs. Prefer REAL banked corpus rows; on a bare checkout fall back
    to the synthetic real-shaped fixture with a LOUD warning. Returns
    ``(sections, evidence_pool, body_sentences_no_marker, source_kind, path)``.

    Each section carries ONE verified sentence (the source's own words) + a rendered ``[N]`` citation
    (what the builders harvest); the matching ``evidence_pool`` row lets the harness drive the REAL
    strict_verify on the pre-resolve ``[#ev:eid:start-end]`` form and prove the re-presentation
    re-passes."""
    rows, path = _load_corpus_rows(3)
    if rows is not None:
        source_kind = "real"
        titles = ["Section A", "Section B", "Section C"]
        triples = [(titles[i], rows[i][0], rows[i][1]) for i in range(3)]
    else:
        print(
            "WARNING: no banked corpus found; using synthetic real-shaped fixture "
            "(set PG_PRD_CORPUS_DIR or run from a checkout with "
            "outputs/corpus_backups/extracted/*/corpus_snapshot.json to replay REAL evidence).",
            file=sys.stderr,
        )
        source_kind = "synthetic"
        path = None
        triples = [(_SYN[i][0], f"ev_b{i + 1}", _SYN[i][1]) for i in range(3)]

    sections: list[_FakeSection] = []
    evidence_pool: dict[str, dict] = {}
    body_sentences_no_marker: list[str] = []
    for idx, (title, eid, quote) in enumerate(triples, start=1):
        body_sentence = f"{quote} [{idx}]"
        sections.append(
            _FakeSection(title=title, verified_text=body_sentence, sentences_verified=1)
        )
        evidence_pool[eid] = {
            "source_url": f"https://example.org/{eid}",
            "tier": "T1",
            "direct_quote": quote,
            "statement": quote,
            "evidence_id": eid,
        }
        body_sentences_no_marker.append(quote)
    return sections, evidence_pool, body_sentences_no_marker, source_kind, path


def _strict_verify_with_deadline(draft_text: str, evidence_pool: dict):
    """Run strict_verify under an EXPLICIT internal wall-clock deadline in a worker thread. If the
    entailment judge is UNREACHABLE and strict_verify would HANG on the judge socket, this returns a
    timeout marker so the caller FAILS LOUD (non-zero exit + "judge unreachable") — it NEVER hangs
    (§-1.4 hard requirement). Returns (report, error) where exactly one is non-None; ("__timeout__"
    error on deadline)."""
    box: dict[str, object] = {}

    def _worker() -> None:
        try:
            box["report"] = strict_verify(draft_text, evidence_pool)
        except Exception as exc:  # noqa: BLE001 — surface, never swallow
            box["error"] = exc

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(_STRICT_VERIFY_DEADLINE_S)
    if t.is_alive():
        return None, "__timeout__"
    if "error" in box:
        return None, box["error"]
    return box.get("report"), None


def _run_assertions(entailment_mode: str, sections, evidence_pool, body_sentences) -> dict:
    """Run the assertions + the redaction landmine under a given PG_STRICT_VERIFY_ENTAILMENT mode.
    Returns a status dict; calls _fail (non-zero exit) on any miss."""
    os.environ["PG_STRICT_VERIFY_ENTAILMENT"] = entailment_mode
    os.environ["PG_SYNTHESIS_ABSTRACT_CONCLUSION"] = "1"

    abstract_md = build_abstract(sections)
    conclusion_md = build_conclusion(sections)
    if not abstract_md.strip() or not conclusion_md.strip():
        _fail("build", f"[{entailment_mode}] build_abstract/build_conclusion returned empty under "
                       "PG_SYNTHESIS_ABSTRACT_CONCLUSION=1 (the feature did not fire).")
    if "## Abstract" not in abstract_md or "## Conclusion" not in conclusion_md:
        _fail("build", f"[{entailment_mode}] abstract/conclusion block headers absent.")

    # ── ASSERTION 1a — FAITHFUL BY IDENTITY: every sentence the builders lift into the abstract/
    # conclusion is a VERBATIM substring of the verified body (the builders harvest sentence-pieces of
    # SectionResult.verified_text). If any rendered sentence is NOT a body substring, synthesized/
    # fabricated prose entered the summary. Whitespace-normalize both sides; drop the trailing [N]. ──
    nbody = " ".join(" ".join(s.verified_text.split()) for s in sections)
    for block_name, block_md, harvested in (
        ("abstract", abstract_md, _harvest_abstract_sentences(sections)),
        ("conclusion", conclusion_md, _harvest_conclusion_sentences(sections)),
    ):
        if not harvested:
            _fail("assert1_identity", f"[{entailment_mode}] the {block_name} harvested NO verified "
                  "body sentence (the feature did not lift any finding).")
        # (a) every harvested sentence is a verbatim body substring (no fabricated/synthesized prose).
        for sent in harvested:
            core = " ".join(sent.split(" [")[0].split())  # drop trailing [N] citation + normalize ws
            if core and core not in nbody:
                _fail("assert1_identity", f"[{entailment_mode}] a rendered {block_name} sentence is "
                      f"NOT a verbatim body substring (synthesized/fabricated content): {sent!r}")
        # (b) the FINAL RENDERED block findings line equals EXACTLY the harvested verbatim sentences
        #     joined — i.e. nothing other than verbatim body sentences reaches the rendered artifact
        #     (parses the actual abstract_md/conclusion_md, not just the harvester output). ──
        rendered_findings = " ".join(
            ln.strip() for ln in block_md.splitlines()
            if ln.strip() and not ln.strip().startswith("#") and not ln.strip().startswith("_")
        )
        if " ".join(rendered_findings.split()) != " ".join(" ".join(harvested).split()):
            _fail("assert1_identity", f"[{entailment_mode}] the rendered {block_name} findings line is "
                  "NOT exactly the harvested verbatim body sentences (extra/synthesized content reached "
                  f"the rendered artifact): rendered={rendered_findings!r}")

    # ── ASSERTION 1b — GENUINELY verified: EVERY rendered (harvested) abstract/conclusion sentence
    # re-passes the REAL strict_verify on its pre-resolve provenance form (Codex iter-2 P2-2: every
    # rendered sentence, not just the first). Each harvested sentence is located at its EXACT span in the
    # source evidence quote, and the [#ev:] token is attached with NO space — the PRODUCTION token format
    # ("...trial.[#ev:...]"); a space lets strict_verify's splitter cut at the sentence-final period and
    # orphan the token. Bounded-deadline so it FAILS LOUD if the judge is unreachable, never hangs. ──
    _rendered: list[str] = []
    _seen_r: set[str] = set()
    for sent in _harvest_abstract_sentences(sections) + _harvest_conclusion_sentences(sections):
        core = re.sub(r"\s*\[\d+\]\s*$", "", sent).strip()  # drop the trailing [N] citation
        if core and core not in _seen_r:
            _seen_r.add(core)
            _rendered.append(core)
    if not _rendered:
        _fail("assert1_verbatim_repass", f"[{entailment_mode}] no rendered sentence to re-verify "
              "(the abstract/conclusion lifted nothing).")
    for core in _rendered:
        draft = None
        for eid, row in evidence_pool.items():
            pos = row["direct_quote"].find(core)
            if pos >= 0:
                draft = f"{core}[#ev:{eid}:{pos}-{pos + len(core)}]"  # NO space (production token format)
                break
        if draft is None:  # identity (1a) already guarantees this; defensive
            _fail("assert1_verbatim_repass", f"[{entailment_mode}] a rendered sentence is not a verbatim "
                  f"span of any evidence quote (identity broken): {core!r}")
        report, err = _strict_verify_with_deadline(draft, evidence_pool)
        if err == "__timeout__":
            _fail("judge_unreachable", f"[{entailment_mode}] strict_verify exceeded the "
                  f"{_STRICT_VERIFY_DEADLINE_S}s internal deadline on a rendered sentence — the "
                  "entailment judge is UNREACHABLE and strict_verify hung. FAIL LOUD (never hang).")
        if err is not None:
            _fail("strict_verify", f"[{entailment_mode}] strict_verify raised on a rendered sentence: {err!r}")
        if report.total_kept < 1 or not any(sv.is_verified for sv in report.kept_sentences):
            _fail("assert1_verbatim_repass", f"[{entailment_mode}] a rendered verbatim sentence did NOT "
                  f"re-pass strict_verify: {core!r}")

    # ── ASSERTION 3 — WEAK/UNVERIFIED EXCLUSION: a section that is NOT verified (gap-stub /
    # sentences_verified=0 / dropped) contributes NO sentence to the abstract/conclusion. Only
    # already-verified body prose is lifted (the I-arch-010 weak-candidate seam, applied to PR-d's
    # verbatim path). ──
    weak_text = "An unverified weak-candidate claim about a different entity at 99 percent. [9]"
    mixed_sections = list(sections) + [
        _FakeSection(title="Weak", verified_text=weak_text, sentences_verified=0,
                     is_gap_stub=True),
        _FakeSection(title="Dropped", verified_text="A dropped claim at 88 percent. [8]",
                     sentences_verified=1, dropped_due_to_failure=True),
    ]
    mixed_abstract = build_abstract(mixed_sections)
    mixed_conclusion = build_conclusion(mixed_sections)
    for leaked in ("weak-candidate", "different entity at 99 percent", "dropped claim at 88 percent"):
        if leaked in mixed_abstract or leaked in mixed_conclusion:
            _fail("assert3_weak_excluded", f"[{entailment_mode}] an UNVERIFIED (gap-stub/dropped) "
                  f"section leaked into the summary ({leaked!r}) — only verified body prose may be "
                  "carried up.")

    # ── REDACTION DUPLICATE LANDMINE (brief P2-2): a verbatim abstract sentence whose underlying body
    # claim is flipped non-VERIFIED is redacted by the REAL reconcile in the SAME pass as the body
    # copy, then refilter_abstract_conclusion_block drops the gap-stub'd block (no orphan). ──
    _check_redaction_landmine(entailment_mode)

    # ── REPORT.MD ASSEMBLY (Codex PR-d diff-gate P1 iter1+iter2, §-1.4 artifact-level): drive the REAL
    # production assemble_report_md and assert flag-OFF BYTE-IDENTITY (== pre-PR-d dedup(title+body))
    # AND flag-ON copy-survival (BODY-only dedup + sandwich keeps body+abstract+conclusion). ──
    _check_report_assembly(entailment_mode)

    # ── ASSERTION 5 — empty verified body -> disclosed insufficient-evidence line, NEVER fabricated. ──
    empty_sections = [
        _FakeSection(title="Empty", verified_text="(no verified findings available).",
                     sentences_verified=0, is_gap_stub=True)
    ]
    empty_abstract = build_abstract(empty_sections)
    empty_conclusion = build_conclusion(empty_sections)
    if _INSUFFICIENT_EVIDENCE not in empty_abstract or _INSUFFICIENT_EVIDENCE not in empty_conclusion:
        _fail("assert5_empty", f"[{entailment_mode}] an empty verified body did NOT render the "
              "disclosed insufficient-evidence line (fabricated-filler / silent-drop regression).")
    for sentence in body_sentences:
        if sentence in empty_abstract or sentence in empty_conclusion:
            _fail("assert5_empty", f"[{entailment_mode}] the empty-body abstract/conclusion contains "
                  "a body finding — it fabricated content from somewhere (must be disclosure only).")

    # ── ASSERTION 4 — flag-OFF -> build_abstract/build_conclusion return "" (byte-identical). The
    # report.md assembled WITHOUT the abstract/conclusion equals the pre-PR-d render. ──
    os.environ.pop("PG_SYNTHESIS_ABSTRACT_CONCLUSION", None)
    off_abstract = build_abstract(sections)
    off_conclusion = build_conclusion(sections)
    if off_abstract != "" or off_conclusion != "":
        _fail("assert4_flag_off", f"[{entailment_mode}] flag-OFF did NOT return empty "
              f"(abstract={off_abstract!r}, conclusion={off_conclusion!r}) — the default-OFF "
              "byte-identity is broken.")

    return {
        "entailment_mode": entailment_mode,
        "abstract_rendered_chars": len(abstract_md),
        "conclusion_rendered_chars": len(conclusion_md),
    }


def _check_redaction_landmine(entailment_mode) -> None:
    """Drive the REAL reconcile_report_against_verdicts + refilter_abstract_conclusion_block over a
    report.md containing the body copy AND the verbatim abstract copy of a claim that the 4-role seam
    flips non-VERIFIED. The redactor's multi-occurrence loop must remove BOTH copies (no orphan), and
    refilter must drop the gap-stub'd abstract block (no empty heading).

    Uses an ATOMIC single-sentence claim — the REAL production granularity for this landmine: a body
    claim is ONE sentence carrying ONE citation, the builder lifts that exact sentence verbatim into
    the abstract, and reconcile keys per-sentence — so the abstract copy is BYTE-IDENTICAL to the
    redaction-keyed body claim (the duplicate the redactor must co-remove). A multi-sentence corpus
    quote would harvest only its first sentence, decoupling the abstract copy from a whole-quote key —
    not the duplicate-claim scenario this landmine tests."""
    os.environ["PG_SYNTHESIS_ABSTRACT_CONCLUSION"] = "1"
    claim = "Aspirin reduced major vascular events by 20 percent in the randomized trial. [1]"
    atomic = [_FakeSection(title="Section A", verified_text=claim, sentences_verified=1)]
    abstract_md = build_abstract(atomic)
    stem = claim.split(" [")[0]
    if stem not in abstract_md:
        _fail("redaction_landmine", f"[{entailment_mode}] the atomic claim was not harvested verbatim "
              "into the abstract (the landmine fixture is broken).")
    report_md = "# Research report: q\n\n" + abstract_md + f"## Section A\n\n{claim}\n\n"
    # The 4-role seam flips this claim non-VERIFIED. audit_map carries the verbatim body sentence.
    final_verdicts = {"c1": "UNSUPPORTED"}
    audit_map = {"c1": {"sentence": claim, "severity": "S1"}}
    result = reconcile_report_against_verdicts(report_md, final_verdicts, audit_map)
    reconciled = result.report_text
    # The claim prose must be ABSENT from BOTH copies (body AND abstract) after the multi-occurrence pass.
    if stem in reconciled:
        _fail("redaction_landmine", f"[{entailment_mode}] after reconcile, the non-VERIFIED claim "
              "prose is STILL present (the redactor did not remove every occurrence — the abstract "
              "copy orphaned the body redaction, the brief-P2-2 duplicate landmine).")
    # refilter must drop the now-gap-stub'd abstract block (no empty heading left behind).
    refiltered = refilter_abstract_conclusion_block(reconciled)
    if "## Abstract" in refiltered:
        # An Abstract heading may remain ONLY if it still has a real (cited) finding; here the single
        # abstract sentence was redacted, so the block must be gone.
        _fail("redaction_landmine", f"[{entailment_mode}] refilter_abstract_conclusion_block left an "
              "empty '## Abstract' heading after its only sentence was redacted (empty-heading leak).")


def _check_report_assembly(entailment_mode) -> None:
    """§-1.4 ARTIFACT-LEVEL (Codex PR-d diff-gate P1, iter1 + iter2). Drive the REAL production
    ``assemble_report_md`` (the function run_honest_sweep_r3 uses to build report.md — tested directly,
    not a replica) and assert:
      (A) FLAG-OFF BYTE-IDENTITY: with NO summary (abstract == conclusion == ""), the assembly equals
          the EXACT pre-PR-d ``dedup_identical_paragraphs(title + body)`` — including the pass-2
          orphaned-title-header drop when the body starts with ``## Key Findings`` (the iter-2
          regression); and dedup-disabled OFF == ``title + body`` unchanged.
      (B) FLAG-ON COPY-SURVIVAL: when the verbatim Abstract/Conclusion render, the BODY-only dedup +
          sandwich keeps ALL THREE copies (body + abstract + conclusion) of a single-section finding —
          the paragraph-dedup can neither empty the ## Conclusion nor delete the body copy."""
    from scripts.run_honest_sweep_r3 import (  # lazy: heavy module
        assemble_report_md,
        dedup_identical_paragraphs,
    )

    finding = "Aspirin cut major vascular events by 20 percent in the randomized trial."
    title = "# Research report: q\n\n"
    # Body STARTS with a header (## Key Findings) — the iter-2 orphaned-title-header trigger.
    body = f"## Key Findings\n\n- {finding} [1]\n\n## Section A\n\n{finding} [1]\n\n"

    # (A) flag-OFF byte identity vs the EXACT pre-PR-d path.
    off_dedup = assemble_report_md(title, "", body, "", dedup_enabled=True)
    if off_dedup != dedup_identical_paragraphs(title + body):
        _fail("flag_off_artifact", f"[{entailment_mode}] flag-OFF report.md assembly is NOT byte-"
              "identical to the pre-PR-d dedup(title+body) — the default-OFF contract is broken.")
    off_nodedup = assemble_report_md(title, "", body, "", dedup_enabled=False)
    if off_nodedup != title + body:
        _fail("flag_off_artifact", f"[{entailment_mode}] flag-OFF, dedup-disabled assembly != "
              "title+body (default-OFF, dedup-off contract broken).")

    # (B) flag-ON: verbatim abstract/conclusion exempt from dedup; all 3 copies survive.
    abstract = f"## Abstract\n\n_summary_\n\n{finding} [1]\n\n"
    conclusion = f"## Conclusion\n\n_closing_\n\n{finding} [1]\n\n"
    on = assemble_report_md(title, abstract, body, conclusion, dedup_enabled=True)
    if on.count(finding) < 3:
        _fail("flag_on_artifact", f"[{entailment_mode}] the flag-ON report.md assembly lost a verbatim "
              f"copy of the finding (count={on.count(finding)}, expected body+abstract+conclusion=3) — "
              "paragraph-dedup deleted a summary copy.")
    if "## Conclusion" not in on or finding not in on.split("## Conclusion", 1)[1]:
        _fail("flag_on_artifact", f"[{entailment_mode}] the Conclusion block lost its only finding in "
              "the flag-ON assembly (empty ## Conclusion — the P1 regression).")


def main() -> int:
    sections, evidence_pool, body_sentences, source_kind, path = _resolve_bodies()
    if source_kind != "real" and os.environ.get("PG_PRD_REQUIRE_REAL", "").strip().lower() in (
        "1", "true", "yes", "on"
    ):
        _fail("require_real", "PG_PRD_REQUIRE_REAL is set but NO banked corpus_snapshot.json was found "
              "— the replay did NOT run on real evidence (acceptance requires real corpus). Unset "
              "PG_PRD_REQUIRE_REAL to allow the synthetic real-shaped fallback on a bare CI checkout.")
    if source_kind == "real":
        print(f"real corpus: {path} (rows used: {list(evidence_pool.keys())})")
    else:
        print("synthetic fallback in use (no banked corpus found) — see WARNING above.",
              file=sys.stderr)

    # Run the assertions once on the live-judge path (enforce, bounded so it FAILS LOUD if the judge
    # is unreachable) and once hermetically under entailment=off (reproducible offline).
    live_mode = os.environ.get("PG_STRICT_VERIFY_ENTAILMENT", "enforce") or "enforce"
    if live_mode == "off":
        live_mode = "enforce"
    status_live = _run_assertions(live_mode, sections, evidence_pool, body_sentences)
    status_off = _run_assertions("off", sections, evidence_pool, body_sentences)

    print(json.dumps({
        "status": "PASS",
        "harness": "iarch011_prd_abstract_conclusion_replay_harness",
        "evidence_source": source_kind,
        "corpus_snapshot": str(path) if path else None,
        "rows_used": list(evidence_pool.keys()),
        "drove": "REAL build_abstract/build_conclusion + REAL strict_verify + REAL "
                 "reconcile_report_against_verdicts/refilter — nothing monkeypatched; the rendered "
                 "abstract/conclusion are verbatim re-presentations, faithful by identity (no synthesis)",
        "live_judge_run": status_live,
        "hermetic_entailment_off_run": status_off,
        "bounded_deadline_s": _STRICT_VERIFY_DEADLINE_S,
        "assertions_fired": {
            "1_faithful_by_identity": "every rendered abstract/conclusion sentence is a VERBATIM body "
                "sentence (no synthesized prose), and that sentence re-passes the REAL strict_verify "
                "on its pre-resolve [#ev:] form",
            "3_weak_unverified_excluded": "a gap-stub / dropped / sentences_verified=0 section "
                "contributes NO sentence to the summary — only verified body prose is lifted",
            "4_flag_off_byte_identical": "PG_SYNTHESIS_ABSTRACT_CONCLUSION unset -> build_abstract/"
                "build_conclusion return '' (default-OFF byte-identity)",
            "5_empty_body_disclosed": "empty verified body -> disclosed insufficient-evidence line, "
                "never fabricated filler",
            "P2-2_redaction_duplicate_landmine": "a verbatim abstract copy of a non-VERIFIED claim is "
                "redacted in the SAME reconcile pass as the body copy; refilter drops the gap-stub'd "
                "block (no orphan, no empty heading)",
            "P1_report_assembly": "the REAL assemble_report_md: flag-OFF is BYTE-IDENTICAL to the "
                "pre-PR-d dedup(title+body) (incl. the orphaned-title-header case); flag-ON dedups the "
                "BODY only + sandwiches the verbatim abstract/conclusion so all 3 copies survive (the "
                "BB5-P03 paragraph-dedup cannot empty the Conclusion or delete the body — Codex P1 "
                "iter1+iter2)",
        },
        "faithfulness": "untouched (strict_verify + I-arch-010 tail unmodified; the render is "
                        "deterministic verbatim re-presentation — no new LLM call, no synthesis)",
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
