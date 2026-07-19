#!/usr/bin/env python3
"""I-arch-011 #1269 B11 — FAIL-LOUD behavioral replay harness for the compose-repetition fix.

§-1.4 acceptance: the effect must ACTUALLY APPEAR in real output, not "tests green / Codex approved".
This harness loads the BANKED drb_72 verified-sentence output (the §-1.1 DO_NOT_SHIP report) and the
real evidence_pool, replays the two fix call sites, and FAILS LOUD (non-zero exit) if any of the B11
effects did not fire OR a faithfulness/breadth regression appears:

  CHECK 1 (degenerate repetition collapses): the 18x ``brynjolfsson_genai_at_work:0-800`` same-span
          restatements in section ``Generative_AI_Evidence`` collapse to a SMALL bound (<=3). This is
          the headline B11 defect (one span re-stated 18x with zero added breadth).
  CHECK 2 (distinct-work breadth PRESERVED): a section whose repetition is across DISTINCT spans
          (``Foundational_Theory`` — 7 distinct Autor spans) loses NO distinct span; every distinct
          (ev_id,start,end) footprint that was rendered before is still rendered after. Guards against
          the dedup over-collapsing genuine corroboration (the §-1.3 violation).
  CHECK 3 (faithfulness-neutral): every collapsed sentence's footprint is STILL present in a kept
          sibling — the dedup never removes the last rendering of any span (no claim is lost).
  CHECK 4 (verified_compose idx8 footprint-equality): the shared ``_compose_section_per_basket`` idx8
          key drops a SECOND unit citing the identical footprint with no new number (the ON-path that
          a Wave-2 slate may flip on). Proven on a synthetic 2-unit section.

Pure offline: no LLM, no network, no model. Reads the banked artifacts by absolute path so it runs
against the REAL output regardless of the (gitignored) worktree state.

Exit 0 iff every effect fired AND no regression; non-zero (with a loud reason) otherwise.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Run against the real banked output in the canonical checkout (gitignored, never in the worktree).
BANKED_RUN_DIR = Path(
    r"C:\POLARIS\outputs\p6_postfix_resume\workforce\drb_72_ai_labor"
)
_VD_PATH = BANKED_RUN_DIR / "verification_details.json"

_SPAN_RE = re.compile(r"\[#ev:([A-Za-z0-9_]+):(\d+)-(\d+)\]")


def _footprint(text: str) -> frozenset:
    return frozenset(
        (m.group(1), int(m.group(2)), int(m.group(3))) for m in _SPAN_RE.finditer(text or "")
    )


def _fail(msg: str) -> "NoReturn":  # type: ignore[name-defined]
    print(f"\n[B11-HARNESS] FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def _load_kept_by_section() -> dict[str, list[str]]:
    if not _VD_PATH.is_file():
        _fail(f"banked verification_details.json not found at {_VD_PATH} (cannot replay real output)")
    vd = json.loads(_VD_PATH.read_text(encoding="utf-8"))
    out: dict[str, list[str]] = {}
    for s in vd.get("sections", []):
        texts: list[str] = []
        for k in (s.get("kept") or []):
            if isinstance(k, str):
                texts.append(k)
            elif isinstance(k, dict):
                texts.append(str(k.get("sentence") or k.get("final_sentence") or k.get("text") or ""))
        out[s.get("title", "")] = texts
    return out


class _SV:
    """Minimal SentenceVerification stand-in (the production dedup reads only ``.sentence``)."""

    def __init__(self, sentence: str) -> None:
        self.sentence = sentence


def main() -> None:
    # Import the PRODUCTION fix code (the worktree's edited modules).
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from src.polaris_graph.generator.verified_compose import (
        _compose_section_per_basket,
        dedup_same_span_sentences,
    )

    kept_by_section = _load_kept_by_section()

    # ── CHECK 1 — the 18x Brynjolfsson same-span repetition collapses ──────────────────────────────
    gen_section = "Generative_AI_Evidence"
    if gen_section not in kept_by_section:
        _fail(f"banked output missing section {gen_section!r} — cannot prove the B11 collapse")
    gen_kept = kept_by_section[gen_section]
    gen_in = len(gen_kept)
    bryn_in = sum(1 for t in gen_kept if ("brynjolfsson_genai_at_work", 0, 800) in _footprint(t))
    if bryn_in < 10:
        _fail(
            f"fixture drift: section {gen_section!r} had only {bryn_in} brynjolfsson:0-800 restatements "
            f"(expected the ~18x degenerate-repetition defect) — harness no longer exercises B11"
        )
    gen_dk, gen_dd = dedup_same_span_sentences([_SV(t) for t in gen_kept])
    bryn_out = sum(
        1 for sv in gen_dk if ("brynjolfsson_genai_at_work", 0, 800) in _footprint(sv.sentence)
    )
    if bryn_out > 3:
        _fail(
            f"degenerate repetition NOT collapsed: {bryn_out} brynjolfsson:0-800 sentences survive "
            f"(was {bryn_in}); the same-span dedup did not fire on the real output"
        )
    print(
        f"[B11-HARNESS] CHECK 1 PASS: {gen_section} {gen_in}->{len(gen_dk)} kept; "
        f"brynjolfsson:0-800 {bryn_in}->{bryn_out} (degenerate repetition collapsed)"
    )

    # ── CHECK 2 — distinct-work breadth preserved (no distinct span lost) ──────────────────────────
    distinct_section = "Foundational_Theory"
    if distinct_section not in kept_by_section:
        _fail(f"banked output missing section {distinct_section!r} — cannot prove breadth preservation")
    dist_kept = kept_by_section[distinct_section]
    dist_footprints_in = {fp for t in dist_kept for fp in [_footprint(t)] if fp}
    if len(dist_footprints_in) < 5:
        _fail(
            f"fixture drift: {distinct_section!r} has only {len(dist_footprints_in)} distinct footprints "
            f"(expected the multi-distinct-span Autor section) — harness no longer proves breadth"
        )
    dist_dk, _dist_dd = dedup_same_span_sentences([_SV(t) for t in dist_kept])
    dist_footprints_out = {fp for sv in dist_dk for fp in [_footprint(sv.sentence)] if fp}
    lost = dist_footprints_in - dist_footprints_out
    if lost:
        _fail(
            f"BREADTH REGRESSION (§-1.3 violation): dedup dropped {len(lost)} distinct span(s) from "
            f"{distinct_section!r}: {sorted(lost)[:5]} — distinct works must NEVER collapse"
        )
    print(
        f"[B11-HARNESS] CHECK 2 PASS: {distinct_section} preserved all "
        f"{len(dist_footprints_in)} distinct Autor span(s) ({len(dist_kept)}->{len(dist_dk)} sentences)"
    )

    # ── CHECK 3 — faithfulness-neutral: no span loses its LAST rendering ──────────────────────────
    for title, kept in kept_by_section.items():
        dk, dd = dedup_same_span_sentences([_SV(t) for t in kept])
        kept_footprints = {fp for sv in dk for fp in [_footprint(sv.sentence)] if fp}
        for sv in dd:
            fp = _footprint(sv.sentence)
            if fp and fp not in kept_footprints:
                _fail(
                    f"FAITHFULNESS regression in {title!r}: collapsed a sentence whose footprint {fp} "
                    f"is NOT present in any kept sibling — a claim was lost, not consolidated"
                )
    print("[B11-HARNESS] CHECK 3 PASS: every collapsed sentence's span still rendered by a kept sibling")

    # ── CHECK 4 — verified_compose idx8 footprint-equality collapse (the ON-path) ─────────────────
    # Two baskets composing the IDENTICAL verified span with no new number -> the second collapses.
    ev_id = "harness_same_span_src"
    quote = "AI adoption rose sharply across the sample population in the study period."
    pool = {ev_id: {"direct_quote": quote, "statement": quote}}

    class _Member:
        def __init__(self) -> None:
            self.evidence_id = ev_id
            self.direct_quote = quote
            self.span_verdict = "SUPPORTS"
            self.credibility_weight = 1.0
            self.origin_cluster_id = ev_id

    class _Basket:
        def __init__(self, cid: str) -> None:
            self.claim_cluster_id = cid
            self.supporting_members = [_Member()]
            self.subject = "AI adoption"

    def _writer(_b, _p):  # noqa: ANN001 — stub writer: force the verbatim K-span path
        return ""

    class _Res:
        def __init__(self, sentence: str) -> None:
            self.sentence = sentence
            self.is_verified = True

    def _verify(sentence, _pool):  # noqa: ANN001 — accept the verbatim K-span as verified
        return _Res(sentence)

    units = _compose_section_per_basket(
        [_Basket("c1"), _Basket("c2")], pool, writer_fn=_writer, verify_fn=_verify,
    )
    if len(units) != 1:
        _fail(
            f"verified_compose idx8 footprint-equality did NOT collapse: produced {len(units)} units "
            f"for two identical same-span baskets (expected 1) -> the ON-path repetition guard is dead"
        )
    print("[B11-HARNESS] CHECK 4 PASS: verified_compose idx8 collapsed two identical same-span units to 1")

    print("\n[B11-HARNESS] ALL CHECKS PASS — compose-repetition B11 fix fired in real banked output.")
    sys.exit(0)


if __name__ == "__main__":
    main()
