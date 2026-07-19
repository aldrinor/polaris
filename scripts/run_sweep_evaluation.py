#!/usr/bin/env python3
"""FAIL-LOUD offline replay-harness for the I-arch-011 #1289 render-boundary screen.

Proves defects #2(render side) / #3 / #5 / #9 / #10 are GONE in the REAL output of the
banked drb_72_ai_labor corpus — by running the PATCHED helpers in scripts/run_honest_sweep_r3.py
against the real bibliography.json / report.md body / contradictions.json. Non-zero exit on any
regression (§-1.4 behavioral acceptance: the effect APPEARS in the real output, not "tests green").

Run:  python scripts/harness_render_boundary_screen.py
Exit: 0 == all defects gone; 1 == at least one regression.

This is a RENDER-LAYER harness only. It NEVER touches strict_verify / NLI / 4-role / span-
grounding (the faithfulness engine, §-1.3 crown jewel) — the audit confirmed zero fabricated
findings; all 12 defects are render/consolidation/composition/disclosure layer.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import tempfile

# The owned file lives in this worktree; the src/ tree (access_bypass etc.) lives in the
# shared checkout. Add the shared checkout to the path so the lazy access_bypass import resolves.
_REPO = r"C:/POLARIS"
_WT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

# Banked corpus (gitignored — read from the shared checkout's outputs).
_RUN_DIR = os.path.join(_REPO, "outputs", "p6_postfix_resume", "workforce", "drb_72_ai_labor")
_BIB = os.path.join(_RUN_DIR, "bibliography.json")
_REPORT = os.path.join(_RUN_DIR, "report.md")
_CONTRA = os.path.join(_RUN_DIR, "contradictions.json")

_FAILURES: list[str] = []


def _fail(defect: str, msg: str) -> None:
    _FAILURES.append(f"[{defect}] {msg}")
    print(f"  FAIL {defect}: {msg}")


def _ok(defect: str, msg: str) -> None:
    print(f"  ok   {defect}: {msg}")


def _load_patched():
    """Import the PATCHED owned module from this worktree (not the shared checkout)."""
    path = os.path.join(_WT, "scripts", "run_honest_sweep_r3.py")
    if not os.path.exists(path):
        raise SystemExit(f"FATAL: owned file not found at {path}")
    spec = importlib.util.spec_from_file_location("rhsr_patched", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["rhsr_patched"] = mod
    spec.loader.exec_module(mod)
    return mod


def _report_body() -> str:
    with open(_REPORT, encoding="utf-8", errors="replace") as f:
        return f.read()


def _bibliography() -> list:
    with open(_BIB, encoding="utf-8") as f:
        bib = json.load(f)
    return bib if isinstance(bib, list) else []


# ─────────────────────────────────────────────────────────────────────────────
def test_9_empty_url_not_cited(m) -> None:
    """#9: a bibliography entry with an EMPTY url (and no DOI) must NOT render as a resolvable
    [N] T1 citation; it must be relabeled to a disclosed evidence gap (locator kept-as-gap)."""
    bib = _bibliography()
    empty = [b for b in bib if not str(b.get("url") or "").strip() and not str(b.get("doi") or "").strip()]
    if not empty:
        _fail("#9", "fixture invariant broken: expected >=1 empty-url/empty-doi entry (11/12/13)")
        return
    rendered = m._render_bibliography_lines(bib, require_locator=True)
    lines = rendered.split("\n")
    bad = []
    for b in empty:
        num = str(b.get("num"))
        for ln in lines:
            if ln.startswith(f"[{num}] "):
                # MUST be the disclosed-gap form, NOT "... — (tier T1)" with a blank locator.
                if "disclosed evidence gap" not in ln and "no resolvable URL/DOI locator" not in ln:
                    bad.append((num, ln[:90]))
    if bad:
        _fail("#9", f"empty-url entry still rendered as a resolvable cite: {bad}")
    else:
        _ok("#9", f"all {len(empty)} empty-locator entries ([{','.join(str(b.get('num')) for b in empty)}]) "
                  "render as disclosed evidence gaps, not resolvable T1 cites")
    # Negative control: a real-URL entry must still render its URL.
    real = next((b for b in bib if str(b.get("url") or "").strip()), None)
    if real is not None:
        num = str(real.get("num"))
        line = next((ln for ln in lines if ln.startswith(f"[{num}] ")), "")
        if "disclosed evidence gap" in line:
            _fail("#9", f"FALSE POSITIVE: real-URL entry [{num}] was wrongly relabeled a gap")
        else:
            _ok("#9", f"negative control: real-URL entry [{num}] still renders its locator")


def test_5_contradiction_range(m) -> None:
    """#5: the Limitations magnitude-range must show the REAL min/max from contradictions.json,
    not the wrong '155.4% to over 165 million percent'."""
    # Ground truth from the sidecar.
    with open(_CONTRA, encoding="utf-8") as f:
        entries = json.load(f)
    rels = [e["relative_difference"] for e in entries
            if isinstance(e, dict) and isinstance(e.get("relative_difference"), (int, float))]
    gt_min, gt_max = min(rels) * 100.0, max(rels) * 100.0
    body = _report_body()
    if "155.4% to over 165 million percent" not in body:
        _fail("#5", "fixture invariant broken: expected the wrong '155.4% to over 165 million percent' string")
        return
    fixed = m._correct_contradiction_magnitude_range(body, _CONTRA)
    if "155.4% to over 165 million percent" in fixed:
        _fail("#5", "the wrong magnitude range was NOT corrected")
        return
    # The corrected range must reflect the true endpoints. min ~33.3%, max ~96.9 trillion %.
    if "165 million" in fixed:
        _fail("#5", "the hallucinated '165 million' max survived")
    # min endpoint
    if "33.3%" not in fixed:
        _fail("#5", f"corrected min endpoint missing (expected 33.3% from gt_min={gt_min:.2f})")
    # max endpoint magnitude word
    if "trillion" not in fixed:
        _fail("#5", f"corrected max endpoint magnitude word missing (expected trillion from gt_max={gt_max:.3e})")
    if not _FAILURES or all("#5" not in fl for fl in _FAILURES):
        # adjacent numbers preserved (30 contradictions, 15%, T4 31%)
        for adj in ("30 contradictions", "only 15% of sources", "T4 sources at 31%"):
            if adj not in fixed:
                _fail("#5", f"adjacent number clobbered: '{adj}' lost")
        if all("#5" not in fl for fl in _FAILURES):
            mfix = re.search(r"ranging from [^—–.\n]+", fixed)
            _ok("#5", f"range corrected to: {mfix.group(0) if mfix else '?'} (gt min {gt_min:.1f}% max {gt_max:.3e}%)")


def test_2_key_findings_chrome(m) -> None:
    """#2 (render side): EVERY audit-named chrome Key-Findings bullet must drop; EVERY real
    finding bullet must survive. Tests the CLASS, not just one shape (the journal masthead, the
    ILO 'same series', AND the OECD topics-nav left-rail)."""
    body = _report_body()
    m_kf = re.search(r"## Key Findings\n.*?(?=\n#|\Z)", body, re.DOTALL)
    if not m_kf:
        _fail("#2-render", "fixture invariant broken: no '## Key Findings' block found")
        return
    kf_block = m_kf.group(0)
    # Audit-named chrome substrings that MUST be gone after the screen.
    chrome_markers = {
        "journal-masthead (Volume 33 / Pages 3-30)": "Volume 33",
        "ILO 'same series' nav": "same series",
        "OECD topics left-rail nav": "The listed topics include",
    }
    for label, marker in chrome_markers.items():
        if marker not in kf_block:
            _fail("#2-render", f"fixture invariant broken: expected chrome bullet '{label}' ({marker!r})")
    screened = m._screen_key_findings_chrome(kf_block)
    for label, marker in chrome_markers.items():
        if marker in screened:
            _fail("#2-render", f"chrome bullet '{label}' ({marker!r}) survived the screen")
        else:
            _ok("#2-render", f"chrome bullet dropped: {label}")
    # EVERY real underscore-slug finding bullet must survive (negative control — the full class).
    real_markers = ["Foundational_Theory", "Empirical_Displacement", "Generative_AI_Evidence"]
    for marker in real_markers:
        if marker in kf_block and marker not in screened:
            _fail("#2-render", f"FALSE POSITIVE: real finding bullet '{marker}' was dropped")
        elif marker in kf_block:
            _ok("#2-render", f"negative control: real finding bullet '{marker}' preserved")
    # #1289 P1 negative controls: a real finding that merely CONTAINS the words "same series" or
    # "topics include" mid-sentence (no nav follow-on) MUST survive the screen. The prior bare
    # "\bsame series\b" / "(?:listed\s+)?topics?\s+include\b" predicates over-stripped these real
    # spans; the tightened nav-shape patterns ("same series - working paper" / "listed topics
    # include") must NOT match them. Run them through the PRODUCTION _screen_key_findings_chrome
    # path as real ``- **...**`` bullets (a block of only-real bullets must survive byte-identical;
    # the screen returns "" only if it judges ALL bullets chrome, so survival is a strong check).
    p1_neg_controls = [
        "- **Wage Series.** papers in the same series show declining wages [12]",
        "- **Survey Scope.** survey topics include automation and employment effects [7]",
    ]
    neg_block = "## Key Findings\nThe following findings emerged:\n" + "\n".join(p1_neg_controls)
    neg_screened = m._screen_key_findings_chrome(neg_block)
    for ctrl in p1_neg_controls:
        if ctrl not in neg_screened:
            _fail("#2-render", f"FALSE POSITIVE (#1289 P1): real finding over-stripped: {ctrl!r}")
        else:
            _ok("#2-render", f"#1289 P1 negative control preserved: {ctrl.split('**')[1]}")


def test_3_offtopic_section(m) -> None:
    """#3: the off-topic WEF water-security '### Background' section must not render as a finding."""
    body = _report_body()
    if "Five technologies are reshaping water security" not in body:
        _fail("#3", "fixture invariant broken: expected the WEF water-security span")
        return
    bib = _bibliography()
    placeholder = m._placeholder_bib_nums(bib)
    if "7" not in placeholder:
        _fail("#3", f"provenance discriminator broken: bib[7] not a placeholder (got {sorted(placeholder)})")
        return
    screened = m._screen_offtopic_chrome_sections(body, placeholder)
    # The orphaned header is cleared by dedup; run dedup to mimic the real assembly.
    final = m.dedup_identical_paragraphs(screened)
    if "Five technologies are reshaping water security" in final:
        _fail("#3", "the off-topic WEF water-security span survived")
    else:
        _ok("#3", "off-topic WEF water-security '### Background' span dropped + header cleared")
    # Negative control: a real section's verified prose must survive.
    real_span = "At the center of their framework is the allocation of tasks to capital and labor"
    if real_span in body and real_span not in final:
        _fail("#3", "FALSE POSITIVE: a real Acemoglu/Restrepo section was dropped")
    elif real_span in body:
        _ok("#3", "negative control: real Acemoglu/Restrepo section preserved")


def test_10_dangling_crossref(m) -> None:
    """#10: the dangling 'See manifest.frame_coverage_report and human_gap_tasks.json ...' pointer
    must be stripped when those files do not exist for the run."""
    body = _report_body()
    if "frame_coverage_report and human_gap_tasks.json" not in body:
        _fail("#10", "fixture invariant broken: expected the dangling cross-ref")
        return
    # Use a temp run dir with NO human_gap_tasks.json / no manifest frame_coverage_report.
    with tempfile.TemporaryDirectory() as td:
        stripped = m._strip_dangling_gap_crossref(body, td)
    if "See manifest.frame_coverage_report and human_gap_tasks.json" in stripped:
        _fail("#10", "the dangling cross-ref pointer survived when target files are absent")
    else:
        _ok("#10", "dangling 'See manifest.frame_coverage_report ...' pointer stripped (files absent)")
    # The gap disclosure itself must survive (we only strip the pointer sentence).
    if "curator-actionable gap" not in stripped:
        _fail("#10", "FALSE POSITIVE: the gap disclosure itself was removed (only the pointer should go)")
    else:
        _ok("#10", "the 'curator-actionable gap' disclosure is preserved (only the pointer removed)")
    # Negative control: when both target files exist, the pointer is preserved.
    with tempfile.TemporaryDirectory() as td2:
        with open(os.path.join(td2, "human_gap_tasks.json"), "w", encoding="utf-8") as f:
            json.dump([{"x": 1}], f)
        with open(os.path.join(td2, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"frame_coverage_report": {"a": 1}}, f)
        kept = m._strip_dangling_gap_crossref(body, td2)
    if "See manifest.frame_coverage_report and human_gap_tasks.json" not in kept:
        _fail("#10", "FALSE POSITIVE: pointer stripped even though both target files EXIST")
    else:
        _ok("#10", "negative control: pointer preserved when both target files exist")


def test_wired_chain(m) -> None:
    """End-to-end (§-1.4): run ALL screens in production order on the real body, then
    dedup_identical_paragraphs + assemble_report_md (the exact assembly path), and assert all five
    defects are gone in the SINGLE final report string — not just in isolated helper calls."""
    body = _report_body()
    bib = _bibliography()
    placeholder = m._placeholder_bib_nums(bib)
    # The real body interleaves Key-Findings + sections; run the same screens the call site runs.
    screened = m._screen_key_findings_chrome(body)
    screened = m._screen_offtopic_chrome_sections(screened, placeholder)
    import tempfile as _tf
    with _tf.TemporaryDirectory() as td:
        screened = m._strip_dangling_gap_crossref(screened, td)
    screened = m._correct_contradiction_magnitude_range(screened, _CONTRA)
    # Bibliography re-rendered with require_locator ON (defect #9) + assemble path (dedup ON).
    biblio = m._render_bibliography_lines(bib, require_locator=True)
    final = m.assemble_report_md("# Research report: x\n\n", "", screened + biblio, "", dedup_enabled=True)
    # #2 render-side contract: chrome must not render AS a Key-Findings BULLET (the audit's defect).
    # Inline chrome buried in an otherwise-real multi-paragraph SECTION BODY is the separate
    # "chrome BEFORE span-grounding" task owned by the consolidation/composition agent — NOT this
    # render-boundary fix — so we assert on the bullet shape, not on every substring in the report.
    bullet_lines = [ln for ln in final.split("\n") if ln.lstrip().startswith("- **")]
    bullet_blob = "\n".join(bullet_lines)
    checks = {
        "#2-render masthead bullet gone": "Volume 33" not in bullet_blob,
        "#2-render OECD-nav bullet gone": "The listed topics include" not in bullet_blob,
        "#2-render ILO-nav bullet gone": "same series" not in bullet_blob,
        "#3 WEF water-security": "Five technologies are reshaping water security" not in final,
        "#5 wrong-range": "155.4% to over 165 million percent" not in final,
        "#5 corrected-min": "33.3%" in final,
        "#9 hollow [11] not resolvable-cite": (
            "[11] Robots and Jobs: Evidence from US Labor Markets — no resolvable URL/DOI locator" in final
        ),
        "#10 dangling-crossref": "See manifest.frame_coverage_report and human_gap_tasks.json" not in final,
    }
    for label, passed in checks.items():
        if passed:
            _ok("wired", label)
        else:
            _fail("wired", f"{label} STILL PRESENT/MISSING in the final assembled report")
    # The real findings must still be present end-to-end (no over-deletion).
    for keep in ("Foundational_Theory", "Empirical_Displacement",
                 "At the center of their framework is the allocation of tasks"):
        if keep not in final:
            _fail("wired", f"FALSE POSITIVE end-to-end: real finding '{keep[:40]}...' lost")
        else:
            _ok("wired", f"real finding preserved end-to-end: {keep[:40]}")


def main() -> int:
    for p in (_BIB, _REPORT, _CONTRA):
        if not os.path.exists(p):
            print(f"FATAL: banked fixture missing: {p}")
            return 2
    print("Loading PATCHED owned module from worktree ...")
    m = _load_patched()
    print(f"Replaying banked corpus: {_RUN_DIR}\n")
    print("Defect #9 — empty-url bibliography entry not cited as resolvable T1:")
    test_9_empty_url_not_cited(m)
    print("Defect #5 — contradiction-magnitude range computed from contradictions.json:")
    test_5_contradiction_range(m)
    print("Defect #2 (render) — Key-Findings masthead bullet screened:")
    test_2_key_findings_chrome(m)
    print("Defect #3 — off-topic WEF water-security Background section routed to gap path:")
    test_3_offtopic_section(m)
    print("Defect #10 — dangling manifest/human_gap_tasks cross-ref guarded:")
    test_10_dangling_crossref(m)
    print("Wired chain — all screens + dedup + assemble in production order:")
    test_wired_chain(m)
    print()
    if _FAILURES:
        print(f"HARNESS RED — {len(_FAILURES)} regression(s):")
        for fl in _FAILURES:
            print(f"  - {fl}")
        return 1
    print("HARNESS GREEN — all assigned render-boundary defects gone in the real output.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
