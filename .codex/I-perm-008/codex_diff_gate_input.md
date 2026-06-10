HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings. Same quality bar regardless of iteration count.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex DIFF review — I-perm-008 (#1202) Key-Findings fix — ITER 2 of 5

Iter-1 verdict: REQUEST_CHANGES, ZERO P0, ONE P1 + one P2. Both RESOLVED. VERIFY.

## P1 (B was ineffective in production) — RESOLVED
You were right: the real `reconcile_report_against_verdicts` replaces the WHOLE KF bullet (prefix + sentence) with a BARE stub line, so the old `- `-prefix check missed it. FIX: `refilter_key_findings_block` now drops ANY line inside the bounded KF block that matches `_GAP_MARKER_RE` (regardless of a `- ` prefix). The block's only other lines are the `## Key Findings` heading + the italic preamble, neither of which matches `_GAP_MARKER_RE`, so no legitimate line is dropped.
NEW integration test `test_build_then_real_redact_then_refilter_is_clean` uses the ACTUAL `reconcile_report_against_verdicts` (not `report.replace`): it asserts the stub IS present in the KF block before refilter (the production leak you flagged) and GONE after. EVIDENCE: I reproduced exactly your scenario — before refilter the KF block contains "A claim previously stated here did not survive 4-role verification..."; after refilter it does not.

## P2 (ATX-only header detection) — RESOLVED
`_strip_leading_markdown_headers` + `_first_verified_sentences` now use `_ATX_HEADER_RE = re.compile(r"#{1,6}\s")` (hash + whitespace), not a bare `startswith("#")`, so hash-leading prose like "#1 ranked therapy" is NOT mis-stripped. NEW test `test_hash_leading_prose_is_not_stripped_as_a_header`.

## Evidence pack (ran this session)
- `pytest tests/polaris_graph/generator/test_key_findings_iperm008.py tests/polaris_graph/test_key_findings.py` → **15 passed** (8 new incl. the real-redactor integration + the hash-prose P2 guard; 7 existing no-regression).
- `pytest tests/polaris_graph/replay/` → **20 passed, 1 xfailed** (no regression).

## HONEST SCOPE (unchanged)
The committed saved drb_76 report.md is a frozen PRE-(A) artifact; full end-to-end real-data validation is a canary re-run. The "curator-actionable gap" WORDING is unchanged here (test-coupled; deferred to I-perm-008b).

VERIFY both fixes close the iter-1 findings and nothing novel. APPROVE if so.

## Output schema (REQUIRED — last `verdict:` line parsed by CI)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

========== THE UPDATED DIFF UNDER REVIEW ==========

diff --git a/scripts/run_honest_sweep_r3.py b/scripts/run_honest_sweep_r3.py
index 9a14d492..e14e98d7 100644
--- a/scripts/run_honest_sweep_r3.py
+++ b/scripts/run_honest_sweep_r3.py
@@ -7258,8 +7258,20 @@ async def run_one_query(
                         # Write the reconciled body back BEFORE the V30 append so the disclosure
                         # reflects the redacted report. Emit one redacted_unsupported gap per
                         # removed claim into gaps.json (append; never overwrite curator gaps).
+                        _reconciled_report = _redaction.report_text
+                        if _redaction.redacted:
+                            # I-perm-008 (#1202) R7: Key Findings is assembled PRE-four-role, so a
+                            # lifted headline the four-role seam later marks non-VERIFIED was just
+                            # redacted into a "- **Section.** <gap stub>" pseudo-finding. Drop those
+                            # stub bullets from the KF block (no-op when no KF bullet was redacted).
+                            from src.polaris_graph.generator.key_findings import (
+                                refilter_key_findings_block,
+                            )
+                            _reconciled_report = refilter_key_findings_block(
+                                _reconciled_report
+                            )
                         _redact_report_path.write_text(
-                            _redaction.report_text, encoding="utf-8"
+                            _reconciled_report, encoding="utf-8"
                         )
                         manifest["report_redaction"] = {
                             "redacted_count": _redaction.redacted_count,
diff --git a/src/polaris_graph/generator/key_findings.py b/src/polaris_graph/generator/key_findings.py
index 94e1867b..fd88d0d9 100644
--- a/src/polaris_graph/generator/key_findings.py
+++ b/src/polaris_graph/generator/key_findings.py
@@ -43,6 +43,10 @@ _GAP_MARKER_RE = re.compile(
     re.IGNORECASE,
 )
 
+# An ATX markdown header: 1-6 '#' followed by whitespace ("### Section"). Used to detect a
+# leaked section header WITHOUT mis-classifying hash-leading prose like "#1 ranked" (Codex P2).
+_ATX_HEADER_RE = re.compile(r"#{1,6}\s")
+
 _OFF_VALUES = frozenset({"0", "false", "no", "off", ""})
 
 # How many leading verified sentences to lift from each section (default 1 — the headline finding).
@@ -56,18 +60,81 @@ def key_findings_enabled() -> bool:
     return os.getenv("PG_SWEEP_KEY_FINDINGS", "1").strip().lower() not in _OFF_VALUES
 
 
+def _strip_leading_markdown_headers(text: str) -> str:
+    """Drop leading markdown header lines (and blanks) from a section's verified_text
+    (I-perm-008 #1202). A section header that leaked into ``verified_text`` (e.g.
+    "### Pathogenic bacteria...") would otherwise be lifted AS the headline finding via the
+    DOTALL sentence regex, producing a "- **Section.** ### <header> ..." bullet that breaks the
+    Key-Findings block boundary. Stripping leading headers makes the lift a clean prose sentence."""
+    lines = (text or "").split("\n")
+    i = 0
+    while i < len(lines) and (not lines[i].strip() or _ATX_HEADER_RE.match(lines[i].lstrip())):
+        i += 1
+    return "\n".join(lines[i:])
+
+
 def _first_verified_sentences(verified_text: str, n: int) -> list[str]:
     matches = [m.group(0).strip() for m in _SENTENCE_RE.finditer(verified_text or "")]
-    # A Key Finding is a span-verified CLAIM: it must carry a citation AND must NOT be
+    # A Key Finding is a span-verified CLAIM: it must carry a citation, must NOT be
     # gap-disclosure boilerplate (whose 2nd sentence is cited to the gap-task sidecar, not
-    # an evidence span). Both filters together exclude every gap shape in a mixed section
-    # (I-gen-006 #1178 C07/P07, Codex iter-5).
+    # an evidence span), and must NOT be a markdown header line (I-perm-008 — a leaked "###"
+    # header is never a finding). The filters together exclude every gap/header shape in a
+    # mixed section (I-gen-006 #1178 C07/P07, Codex iter-5).
     return [
         s for s in matches
-        if s and _CITATION_RE.search(s) and not _GAP_MARKER_RE.search(s)
+        if s
+        and not _ATX_HEADER_RE.match(s.lstrip())
+        and _CITATION_RE.search(s)
+        and not _GAP_MARKER_RE.search(s)
     ][:n]
 
 
+def refilter_key_findings_block(report_text: str) -> str:
+    """Drop Key-Findings bullets that became a redaction STUB after the four-role seam
+    (I-perm-008 #1202, blueprint R7).
+
+    ``build_key_findings`` is assembled PRE-four-role on strict_verify-passed prose, so a lifted
+    headline finding the four-role seam later marks non-VERIFIED is redacted in report.md into a
+    "- **Section.** <gap stub>" pseudo-finding. The redactor runs AFTER Key Findings is built, so
+    it cannot prevent the stub bullet; this post-redaction pass removes any KF bullet whose body
+    now matches the gap-disclosure boilerplate (``_GAP_MARKER_RE``). With the leaked-header strip
+    in ``build_key_findings`` each bullet is a clean single line, so a line-scoped drop is exact.
+    If no genuine finding remains, the whole block is dropped (no empty heading). Idempotent +
+    byte-identical when no KF bullet was redacted.
+    """
+    if not key_findings_enabled():
+        return report_text
+    header_match = re.search(r"(?m)^##\s*Key Findings\s*$", report_text)
+    if not header_match:
+        return report_text
+    block_start = header_match.start()
+    rest = report_text[header_match.end():]
+    next_header = re.search(r"(?m)^#{1,6}\s", rest)
+    block_end = header_match.end() + (next_header.start() if next_header else len(rest))
+
+    kept_lines: list[str] = []
+    dropped_any = False
+    for line in report_text[block_start:block_end].splitlines():
+        # Within the bounded KF block, ANY gap-disclosure line is a redacted finding — the real
+        # `reconcile_report_against_verdicts` replaces the WHOLE bullet (including the
+        # "- **Section.**" prefix) with a BARE stub line, so a `- `-prefix check misses it
+        # (Codex iter-1 P1). The block's only other lines are the heading + the italic preamble,
+        # neither of which matches `_GAP_MARKER_RE`, so this never drops a legitimate line.
+        if _GAP_MARKER_RE.search(line):
+            dropped_any = True
+            continue
+        kept_lines.append(line)
+    if not dropped_any:
+        return report_text  # byte-identical when nothing was a stub
+    new_block = "\n".join(kept_lines)
+    if not re.search(r"(?m)^\s*-\s+\S", new_block):
+        trimmed = report_text[:block_start] + report_text[block_end:]
+        return re.sub(r"^\n+", "", trimmed) if block_start == 0 else trimmed
+    if not new_block.endswith("\n"):
+        new_block += "\n"
+    return report_text[:block_start] + new_block + report_text[block_end:]
+
+
 def build_key_findings(sections: list[Any]) -> str:
     """Return a markdown "## Key Findings" block: the first verified sentence (verbatim, citation intact)
     from each non-dropped section with verified_text. Verified-only + extractive — never a new claim.
@@ -84,7 +151,9 @@ def build_key_findings(sections: list[Any]) -> str:
         # statement". Skip every gap disclosure (universal signal: sentences_verified == 0).
         if getattr(sr, "is_gap_stub", False) or getattr(sr, "sentences_verified", 1) == 0:
             continue
-        verified_text = getattr(sr, "verified_text", "") or ""
+        # I-perm-008: strip any leaked leading section header so it is never lifted as the
+        # headline finding (a "### ..." header would otherwise break the KF block boundary).
+        verified_text = _strip_leading_markdown_headers(getattr(sr, "verified_text", "") or "")
         if not verified_text.strip():
             continue
         title = getattr(sr, "title", "") or ""
diff --git a/tests/polaris_graph/generator/test_key_findings_iperm008.py b/tests/polaris_graph/generator/test_key_findings_iperm008.py
new file mode 100644
index 00000000..3ac7df55
--- /dev/null
+++ b/tests/polaris_graph/generator/test_key_findings_iperm008.py
@@ -0,0 +1,175 @@
+"""I-perm-008 (#1202) — Key-Findings leaked-header strip + post-redaction stub re-filter.
+
+Offline, deterministic. Proves the two-part fix on synthetic sections/reports:
+(A) `build_key_findings` strips a leaked "### header" from a section's verified_text so it is
+    never lifted as the headline finding (clean single-line bullet).
+(B) `refilter_key_findings_block` drops a KF bullet that the four-role seam redacted into a gap
+    stub after Key Findings was assembled (with (A) the bullet is single-line, so the line-scoped
+    drop is exact). My first slice-1 (B alone) was a no-op on the real drb_76 report BECAUSE the
+    leaked header made the bullet multi-line — (A) is the enabler.
+
+HONEST SCOPE: the committed saved drb_76 report.md was rendered PRE-(A), so its broken multi-line
+Mechanism bullet is a frozen pre-fix artifact; full end-to-end real-data validation is a canary
+re-run (RE-RUN-REQUIRED per the blueprint). These tests prove the FIX LOGIC.
+"""
+
+from __future__ import annotations
+
+from types import SimpleNamespace
+
+from src.polaris_graph.generator.key_findings import (
+    build_key_findings,
+    refilter_key_findings_block,
+)
+
+_REDACTION_STUB = (
+    "A claim previously stated here did not survive 4-role verification and was redacted; "
+    "this is a curator-actionable gap."
+)
+
+
+def _section(title, verified_text, sentences_verified=2):
+    return SimpleNamespace(
+        title=title,
+        verified_text=verified_text,
+        dropped_due_to_failure=False,
+        is_gap_stub=False,
+        sentences_verified=sentences_verified,
+    )
+
+
+# --- (A) leaked-header strip ----------------------------------------------------------------
+
+
+def test_leaked_header_is_not_lifted_as_a_finding():
+    sections = [
+        _section("Efficacy", "Exposure: intake of dietary fibre and whole grains.[1]"),
+        # Mechanism's verified_text has a leaked "### " section header before the prose.
+        _section(
+            "Mechanism",
+            "### Pathogenic bacteria and their genotoxic metabolites\n\n"
+            "The pathogenic bacterium pks+ E. coli has been linked to colorectal cancer.[2]",
+        ),
+    ]
+    kf = build_key_findings(sections)
+    assert "###" not in kf, f"a leaked header leaked into Key Findings:\n{kf}"
+    # The Mechanism bullet is the clean prose sentence, not the header.
+    assert "- **Mechanism.** The pathogenic bacterium pks+ E. coli" in kf
+    assert "- **Efficacy.** Exposure: intake of dietary fibre" in kf
+
+
+def test_header_only_section_yields_no_bullet():
+    # A section whose verified_text is ONLY a header (no real cited prose) contributes nothing.
+    sections = [_section("Mechanism", "### Just a header with no prose")]
+    assert build_key_findings(sections) == ""
+
+
+# --- (B) post-redaction stub re-filter ------------------------------------------------------
+
+
+def _report(bullets):
+    body = "\n".join(bullets)
+    return (
+        "# Research report: q\n\n"
+        "## Key Findings\n\n"
+        "_preamble._\n\n"
+        f"{body}\n\n"
+        "### Efficacy\n\nbody prose.[1]\n\n"
+        "## Bibliography\n[1] x\n"
+    )
+
+
+def test_refilter_drops_stub_bullet_keeps_real_finding():
+    report = _report([
+        "- **Efficacy.** Exposure: intake of dietary fibre.[1]",
+        f"- **Mechanism.** {_REDACTION_STUB}",
+    ])
+    out = refilter_key_findings_block(report)
+    assert "## Key Findings" in out
+    assert "- **Efficacy.** Exposure: intake of dietary fibre.[1]" in out
+    assert _REDACTION_STUB not in out.split("### Efficacy")[0]  # stub gone from the KF block
+    assert "did not survive" not in out.split("### Efficacy")[0]
+    # Body + bibliography preserved.
+    assert "### Efficacy" in out and "## Bibliography" in out
+
+
+def test_refilter_drops_whole_block_when_no_finding_survives():
+    report = _report([f"- **Mechanism.** {_REDACTION_STUB}"])
+    out = refilter_key_findings_block(report)
+    assert "## Key Findings" not in out  # no empty heading
+    assert "### Efficacy" in out  # body untouched
+
+
+def test_refilter_byte_identical_when_no_stub():
+    report = _report([
+        "- **Efficacy.** Exposure: intake of dietary fibre.[1]",
+        "- **Mechanism.** The bacterium is linked to cancer.[2]",
+    ])
+    assert refilter_key_findings_block(report) == report
+
+
+def test_refilter_is_idempotent():
+    report = _report([
+        "- **Efficacy.** Exposure: intake of dietary fibre.[1]",
+        f"- **Mechanism.** {_REDACTION_STUB}",
+    ])
+    once = refilter_key_findings_block(report)
+    assert refilter_key_findings_block(once) == once
+
+
+# --- (A-P2) ATX-only header detection (do not strip hash-leading prose) ----------------------
+
+
+def test_hash_leading_prose_is_not_stripped_as_a_header():
+    # "#1 ..." is prose, not an ATX header (no space after the hashes); it must survive.
+    sections = [_section("Comparative", "#1 ranked therapy improved outcomes in the cohort.[3]")]
+    kf = build_key_findings(sections)
+    assert "#1 ranked therapy improved outcomes" in kf
+
+
+# --- (A)+(B) together via the REAL redactor (not a string replace) ---------------------------
+
+
+def test_build_then_real_redact_then_refilter_is_clean():
+    # Codex iter-1 P1: the integration must use the ACTUAL reconcile_report_against_verdicts,
+    # which replaces the WHOLE bullet (prefix + sentence) with a bare stub line.
+    from src.polaris_graph.roles.report_redactor import reconcile_report_against_verdicts
+
+    sections = [
+        _section("Efficacy", "Exposure: intake of dietary fibre.[1]"),
+        # (A): leaked header before the prose finding the four-role seam will reject.
+        _section(
+            "Mechanism",
+            "### Pathogenic bacteria\n\n"
+            "The bacterium has been strongly linked to colorectal cancer.[2]",
+        ),
+    ]
+    kf = build_key_findings(sections)
+    # (A) sanity: no leaked header reached a bullet.
+    assert "###" not in kf
+    report = (
+        "# Research report: q\n\n"
+        + kf
+        + "### Efficacy\n\nExposure: intake of dietary fibre.[1]\n\n"
+        + "### Mechanism\n\nThe bacterium has been strongly linked to colorectal cancer.[2]\n\n"
+        + "## Bibliography\n[1] a\n[2] b\n"
+    )
+    audit_map = {
+        "01-002": {
+            "sentence": "The bacterium has been strongly linked to colorectal cancer.[2]",
+            "severity": "S2",
+            "verdict": "UNSUPPORTED",
+        }
+    }
+    redaction = reconcile_report_against_verdicts(report, {"01-002": "UNSUPPORTED"}, audit_map)
+    assert redaction.redacted_count == 1
+    # Before refilter, the real redactor leaves a bare stub line in the KF block.
+    kf_before = redaction.report_text.split("### Efficacy")[0]
+    assert "did not survive" in kf_before  # the leak Codex flagged exists in production
+    # (B): refilter removes it even though the redactor stripped the "- **Mechanism.**" prefix.
+    out = refilter_key_findings_block(redaction.report_text)
+    kf_after = out.split("### Efficacy")[0]
+    assert "did not survive" not in kf_after  # the stub is gone from Key Findings
+    assert "curator-actionable gap" not in kf_after
+    assert "- **Efficacy.** Exposure: intake of dietary fibre.[1]" in out  # real finding kept
+    assert "### Mechanism" in out and "## Bibliography" in out  # body untouched
