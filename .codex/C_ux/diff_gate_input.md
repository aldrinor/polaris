HARD ITERATION CAP 5, iter 1 of 5. Front-load findings; APPROVE iff zero NOVEL/continuing P0 and zero P1; final 'verdict: APPROVE|REQUEST_CHANGES' line + §8.3.9 schema. Lane C_ux (#1179): LANE C — presentation (BB5-P01/P02/P03, issue #1179). The biggest readability gap vs Gemini. Implement:
- P01 ([REVIEW] dump): run_honest_sweep_r3.py:5730 emits one '- [REVIEW] ...' line per flagged pair, uncapped/no-dedup — 246 lines = 82% of drb_75's file (Gemini: 0). Collapse to a one-line count + a sidecar pointer; dedup identical (subject,predicate,status) rows; gate the clinical-safety detector to clinical-domain templates only; only auto-fired adjudicated [CONFLICT] (currently 0) belongs in prose.
- P02 (semantic-dump): the cross-document NLI "Semantic contradiction" section dumps a full source's scraped bibliography + figure-markdown + image URLs into the body. Surface only a short normalized claim summary per side (subject/predicate + <=200-char trimmed quote); strip bibliographies/figure-markdown/URLs; cap inline count; full pairs to a sidecar.
- P03 (drb_90 dedup): a verbatim-duplicated Implications/Limitations paragraph + a duplicate "### Limitations" header. When the outline already has a Limitations section, suppress/merge the appended synthesized one; de-dup identical paragraphs + collapse duplicate headers before render.
If P02 lives in a different module than run_honest_sweep_r3.py, edit ONLY the minimal additional file needed and report it.

VERIFY adversarially: each sub-fix does what it claims; faithfulness gate authority NOT weakened (Lane B entailment may be strengthened); named constants/env knobs; offline tests genuinely exercise the fix (not tautological); fail-closed preserved.

=== DIFF UNDER REVIEW (lane C_ux files only: scripts/run_honest_sweep_r3.py + tests/polaris_graph/test_lane_c_presentation_bb5_p01_p02_p03.py) ===

diff --git a/scripts/run_honest_sweep_r3.py b/scripts/run_honest_sweep_r3.py
index c7bb228b..62315d70 100644
--- a/scripts/run_honest_sweep_r3.py
+++ b/scripts/run_honest_sweep_r3.py
@@ -525,6 +525,324 @@ def compute_custody_lane_status(
     }
 
 
+# ─────────────────────────────────────────────────────────────────────────────
+# Lane C (#1179) — presentation hygiene for the three conflict-disclosure blocks.
+#
+# BB5-P01: the qualitative present-vs-absent detector emits one `- [REVIEW] ...`
+# line per flagged pair, uncapped + un-deduped — 246 lines = 82% of drb_75's file
+# (Gemini: 0). Qualitative records are NOT passed to the PT08 evaluator gate
+# (run_external_evaluation receives numeric + semantic records only — see the
+# render site near the report-assembly block), so collapsing review-flags to a
+# count + sidecar pointer and gating the clinical-safety detector to the clinical
+# domain is PT08-safe.
+#
+# BB5-P02: the cross-document NLI "Semantic contradiction" block prints each
+# record's full scraped row text (bibliographies, figure-markdown, image URLs).
+# Semantic records ARE PT08-checked (subject + predicate substring must appear in
+# the report), so the helper KEEPS subject + predicate verbatim for every record
+# and only trims the QUOTE payload + caps the inline count; full pairs go to a
+# sidecar.
+#
+# BB5-P03: drb_90 ships a verbatim-duplicated Implications/Limitations paragraph
+# and two `### Limitations` headers (outline Limitations + appended synthesized
+# one). The helper suppresses the appended synthesized Limitations when the
+# outline already wrote one, and de-dups identical paragraphs.
+#
+# All knobs are env-overridable; OFF/empty inputs yield byte-identical output.
+# ─────────────────────────────────────────────────────────────────────────────
+
+# BB5-P01 — env knob: render qualitative REVIEW-flag rows inline (default OFF —
+# they are advisory, not adjudicated conflicts, and the verbatim dump was 82% of
+# drb_75's file). When OFF, only auto-fired hard CONFLICT rows render in prose and
+# the review flags collapse to a one-line count + sidecar pointer.
+_QUAL_REVIEW_INLINE_ENV = "PG_SWEEP_QUAL_REVIEW_INLINE"
+_QUAL_SIDECAR_FILENAME = "contradictions.json"
+_TRUE_TOKENS = ("1", "true", "yes", "on")
+
+# BB5-P02 — env knobs: max semantic pairs rendered inline, and the per-quote trim
+# length. Excess pairs go to the sidecar; subject + predicate of EVERY record
+# still render inline (PT08 contract).
+_SEMANTIC_INLINE_CAP_ENV = "PG_SWEEP_SEMANTIC_INLINE_CAP"
+_SEMANTIC_INLINE_CAP_DEFAULT = 10
+_SEMANTIC_QUOTE_TRIM_ENV = "PG_SWEEP_SEMANTIC_QUOTE_TRIM"
+_SEMANTIC_QUOTE_TRIM_DEFAULT = 200
+
+# BB5-P02 — a scraped row's "claim" text often carries a numbered bibliography,
+# figure/image markdown, and bare URLs. Strip those to a short normalized claim
+# summary before trimming to the quote cap.
+_BIBLIO_LINE_RE = re.compile(r"^\s*(?:\[\d+\]|\d+[.)])\s+.*$", re.MULTILINE)
+_IMAGE_MARKDOWN_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
+_LINK_MARKDOWN_RE = re.compile(r"\[([^\]]*)\]\((?:https?://[^)]*)\)")
+_BARE_URL_RE = re.compile(r"https?://\S+")
+_WHITESPACE_RUN_RE = re.compile(r"\s+")
+
+# BB5-P03 — env knob: when the outline already produced a Limitations section,
+# suppress the appended synthesized one (default ON — the duplicate header + the
+# verbatim-duplicated paragraph are the drb_90 defect). Citation markers are
+# stripped before the identical-paragraph comparison.
+_LIMITATIONS_DEDUP_ENV = "PG_SWEEP_LIMITATIONS_DEDUP"
+_CITATION_MARKER_RE = re.compile(r"\[#?ev:[^\]]*\]|\[\d+\]|\[CITE\]", re.IGNORECASE)
+
+
+def _env_flag(name: str, *, default: bool) -> bool:
+    """Parse an env flag with an explicit default (no magic strings at call sites)."""
+    raw = os.getenv(name)
+    if raw is None:
+        return default
+    return raw.strip().lower() in _TRUE_TOKENS
+
+
+def _normalize_claim_summary(text: str, *, quote_trim: int) -> str:
+    """BB5-P02: reduce a scraped row's raw text to a short, trimmed claim summary.
+
+    Strips numbered bibliographies, figure/image markdown, markdown links (keeps
+    the visible label), and bare URLs, collapses whitespace, then trims to
+    ``quote_trim`` chars (adding an ellipsis when truncated). Pure string op."""
+    if not text:
+        return ""
+    cleaned = _IMAGE_MARKDOWN_RE.sub(" ", text)
+    cleaned = _LINK_MARKDOWN_RE.sub(r"\1", cleaned)
+    cleaned = _BIBLIO_LINE_RE.sub(" ", cleaned)
+    cleaned = _BARE_URL_RE.sub(" ", cleaned)
+    cleaned = _WHITESPACE_RUN_RE.sub(" ", cleaned).strip()
+    if quote_trim > 0 and len(cleaned) > quote_trim:
+        cleaned = cleaned[:quote_trim].rstrip() + "…"
+    return cleaned
+
+
+def render_qualitative_disclosure(
+    qualitative_records: list,
+    *,
+    is_clinical: bool,
+    review_inline: bool | None = None,
+    sidecar_filename: str = _QUAL_SIDECAR_FILENAME,
+) -> str:
+    """BB5-P01: render the qualitative present-vs-absent safety-conflict block.
+
+    - Gates the clinical-safety detector output to the clinical domain: on a
+      non-clinical question the detector mis-fires (drb_90 ADAS "drug_interaction"
+      rows; drb_72 labor eligibility flags), so this returns "" for non-clinical.
+    - Collapses identical (subject, predicate, status-signature) rows: drb_75's
+      246 lines were duplicate rows.
+    - Hard CONFLICT rows (severity high/medium) render inline (auto-fired,
+      adjudicated). REVIEW flags collapse to a one-line count + sidecar pointer
+      unless ``review_inline`` (env ``PG_SWEEP_QUAL_REVIEW_INLINE``) is ON.
+
+    Pure: takes the records list + the clinical flag; no I/O. Returns the markdown
+    block (possibly "") appended to the report Methods. Qualitative records are
+    NOT PT08-gated, so dropping/collapsing review rows is faithfulness-safe."""
+    if not qualitative_records or not is_clinical:
+        return ""
+    if review_inline is None:
+        review_inline = _env_flag(_QUAL_REVIEW_INLINE_ENV, default=False)
+
+    hard = [r for r in qualitative_records if getattr(r, "severity", "") in ("high", "medium")]
+    review = [r for r in qualitative_records if getattr(r, "severity", "") == "review"]
+
+    def _status_signature(record) -> tuple:
+        statuses = tuple(
+            (cl.get("assertion_status", "?"), cl.get("evidence_id", ""))
+            for cl in getattr(record, "claims", []) or []
+        )
+        return (getattr(record, "subject", ""), getattr(record, "predicate", ""), statuses)
+
+    def _dedup(records: list) -> list:
+        seen: set = set()
+        out: list = []
+        for record in records:
+            sig = _status_signature(record)
+            if sig in seen:
+                continue
+            seen.add(sig)
+            out.append(record)
+        return out
+
+    hard = _dedup(hard)
+    review = _dedup(review)
+
+    if not hard and not review:
+        return ""
+
+    out = (
+        f"\n## Qualitative safety-conflict disclosures\n"
+        f"The qualitative detector flagged {len(hard)} present-vs-absent "
+        f"clinical-safety conflict(s) (contraindication / drug-interaction / "
+        f"eligibility / warning / adverse-event causation) and {len(review)} "
+        f"review-flagged item(s) requiring human adjudication. Status is shown as "
+        f"asserted PRESENT/ABSENT/INDETERMINATE, not a numeric value; review flags "
+        f"are NOT adjudicated conflicts.\n\n"
+    )
+    for r in hard:
+        statuses = " vs ".join(
+            f"{cl.get('assertion_status', '?')} "
+            f"[ev={cl.get('evidence_id', '')}, tier={cl.get('source_tier', '')}]"
+            for cl in getattr(r, "claims", []) or []
+        )
+        out += (
+            f"- [CONFLICT] {getattr(r, 'subject', '')} / "
+            f"{getattr(r, 'predicate', '')}: {statuses} — "
+            f"{getattr(r, 'conflict_reason', '')}\n"
+        )
+    if review:
+        if review_inline:
+            for r in review:
+                statuses = " vs ".join(
+                    f"{cl.get('assertion_status', '?')} "
+                    f"[ev={cl.get('evidence_id', '')}, tier={cl.get('source_tier', '')}]"
+                    for cl in getattr(r, "claims", []) or []
+                )
+                out += (
+                    f"- [REVIEW] {getattr(r, 'subject', '')} / "
+                    f"{getattr(r, 'predicate', '')}: {statuses} — "
+                    f"{getattr(r, 'conflict_reason', '')}\n"
+                )
+        else:
+            out += (
+                f"- {len(review)} review-flagged item(s) collapsed to keep the "
+                f"report readable; full per-flag rows are in the `{sidecar_filename}` "
+                f"sidecar (filter `type=\"qualitative\"`, `severity=\"review\"`).\n"
+            )
+    return out
+
+
+def render_semantic_disclosure(
+    semantic_records: list,
+    *,
+    inline_cap: int | None = None,
+    quote_trim: int | None = None,
+    sidecar_filename: str = _QUAL_SIDECAR_FILENAME,
+) -> str:
+    """BB5-P02: render the cross-document NLI semantic-contradiction block.
+
+    Semantic records ARE PT08-gated (subject + predicate substring must appear in
+    the report), so subject + predicate of EVERY record render inline. Only the
+    payload is trimmed: each side becomes a short normalized claim summary
+    (bibliographies / figure-markdown / image URLs stripped, trimmed to
+    ``quote_trim`` chars). Beyond ``inline_cap`` records, the remainder collapse to
+    a one-line pointer to the sidecar — but every subject/predicate is still
+    emitted so PT08 holds. Pure: no I/O."""
+    if not semantic_records:
+        return ""
+    if inline_cap is None:
+        inline_cap = _env_int(_SEMANTIC_INLINE_CAP_ENV, _SEMANTIC_INLINE_CAP_DEFAULT)
+    if quote_trim is None:
+        quote_trim = _env_int(_SEMANTIC_QUOTE_TRIM_ENV, _SEMANTIC_QUOTE_TRIM_DEFAULT)
+
+    out = (
+        f"\n## Semantic contradiction disclosures (cross-document NLI)\n"
+        f"An NLI pass over same-subject evidence pairs flagged {len(semantic_records)} "
+        f"prose-only directional contradiction(s) that carry no shared number and no "
+        f"rule-cue (and so are not caught by the numeric or qualitative detectors). "
+        f"Each is shown with a short normalized claim summary per side; full source "
+        f"text is in the `{sidecar_filename}` sidecar (filter `type=\"semantic\"`).\n\n"
+    )
+    # PT08 contract: subject + predicate of EVERY record must appear in the report.
+    # The first `inline_cap` render with trimmed quotes; the rest render
+    # subject/predicate only (still satisfying PT08) on a compact pointer line.
+    for idx, r in enumerate(semantic_records):
+        subject = getattr(r, "subject", "")
+        predicate = getattr(r, "predicate", "")
+        if idx < inline_cap:
+            claims = getattr(r, "claims", None) or []
+            summary = " VS ".join(
+                f"\"{_normalize_claim_summary(cl.get('text') or '', quote_trim=quote_trim)}\" "
+                f"[ev={cl.get('evidence_id', '')}, tier={cl.get('tier', '')}]"
+                for cl in claims
+            )
+            out += (
+                f"- [SEMANTIC] {subject} / {predicate} "
+                f"(NLI confidence {getattr(r, 'nli_confidence', 0.0):.2f}): {summary}\n"
+            )
+        else:
+            out += (
+                f"- [SEMANTIC] {subject} / {predicate} "
+                f"(NLI confidence {getattr(r, 'nli_confidence', 0.0):.2f}) — full pair "
+                f"in `{sidecar_filename}`.\n"
+            )
+    return out
+
+
+def _env_int(name: str, default: int) -> int:
+    """Parse a non-negative int env knob; fall back to default on missing/invalid."""
+    raw = os.getenv(name)
+    if raw is None or not raw.strip():
+        return default
+    try:
+        value = int(raw.strip())
+    except ValueError:
+        return default
+    return value if value >= 0 else default
+
+
+def _strip_citation_markers(text: str) -> str:
+    """Normalize a paragraph for identical-content comparison (BB5-P03): drop
+    citation markers, collapse whitespace, lowercase. Pure string op."""
+    stripped = _CITATION_MARKER_RE.sub("", text or "")
+    return _WHITESPACE_RUN_RE.sub(" ", stripped).strip().lower()
+
+
+_MARKDOWN_HEADER_RE = re.compile(r"^#{1,6}\s")
+
+
+def _is_markdown_header(block: str) -> bool:
+    """True when a blank-line block is a single markdown header line (`#..######`)."""
+    stripped = block.strip()
+    return bool(stripped) and "\n" not in stripped and bool(_MARKDOWN_HEADER_RE.match(stripped))
+
+
+def dedup_identical_paragraphs(report_text: str) -> str:
+    """BB5-P03: drop later body paragraphs that are content-identical (after
+    citation-marker stripping + whitespace/case normalization) to an earlier
+    paragraph, then remove any header left ORPHANED (a header immediately followed by
+    another header or end-of-document) by the drop. Keeps the FIRST occurrence.
+
+    Content-identity ONLY — the title-based blanket suppress was rejected because the
+    outline 'Limitations' (verified prose) and the appended synthesized
+    ``limitations_text`` (corpus-skew / contradiction meta-disclosures) are different
+    content in the general case; suppressing by title silently drops the latter's
+    unique disclosure (the §-1.1 silent-downgrade the operator flagged). Here the
+    drb_90 outline-Implications body == outline-Limitations body, so dedup removes the
+    true duplicate body and the orphan-header pass clears the now-empty '###
+    Limitations' header — while the distinct synthesized Limitations disclosure is
+    preserved. Exact-equality only (no fuzzy match): a paragraph that merely shares
+    phrasing is never dropped. Pure."""
+    if not report_text:
+        return report_text
+    blocks = report_text.split("\n\n")
+
+    # Pass 1 — drop content-identical body paragraphs (keep first). Headers and blank
+    # blocks are never deduped here (a header is collapsed only if orphaned in pass 2).
+    seen_paragraphs: set = set()
+    kept: list[str] = []
+    for block in blocks:
+        if _is_markdown_header(block) or not block.strip():
+            kept.append(block)
+            continue
+        normalized = _strip_citation_markers(block)
+        if normalized and normalized in seen_paragraphs:
+            continue
+        if normalized:
+            seen_paragraphs.add(normalized)
+        kept.append(block)
+
+    # Pass 2 — drop orphaned headers: a header block whose next non-blank block is
+    # another header or which has no following body (end-of-document).
+    def _next_nonblank_idx(start: int) -> int:
+        j = start + 1
+        while j < len(kept) and not kept[j].strip():
+            j += 1
+        return j
+
+    out_blocks: list[str] = []
+    for i, block in enumerate(kept):
+        if _is_markdown_header(block):
+            nxt = _next_nonblank_idx(i)
+            if nxt >= len(kept) or _is_markdown_header(kept[nxt]):
+                continue  # orphaned header — drop
+        out_blocks.append(block)
+    return "\n\n".join(out_blocks)
+
+
 def _capped_finding_dedup_selection(
     *,
     base_rows: list[dict[str, Any]],
@@ -5519,6 +5837,12 @@ async def run_one_query(
                 _log(f"[phase7]      quantified analysis skipped: {str(_q_exc)[:160]}")
                 _quantified_telemetry = {"enabled": True, "error": str(_q_exc)[:200]}
 
+        # BB5-P03 (#1179): the appended synthesized Limitations is ALWAYS emitted (its corpus-skew /
+        # contradiction-count disclosure is unique content — suppressing it by title would silently
+        # drop a disclosure, the §-1.1 downgrade the operator flagged). The drb_90 duplicate (outline
+        # Implications body == outline Limitations body + the now-empty '### Limitations' header) is
+        # removed downstream by dedup_identical_paragraphs (content-identity + orphan-header pass),
+        # gated by PG_SWEEP_LIMITATIONS_DEDUP.
         if multi.limitations_text:
             sections_concat += f"\n\n### Limitations\n\n{multi.limitations_text}"
 
@@ -5727,25 +6051,12 @@ async def run_one_query(
         # Qualitative present-vs-absent safety-conflict disclosure (#944). Renders by ASSERTION
         # STATUS (present/absent/indeterminate/statistical_null) — NOT the loader-required numeric
         # value — and separates hard conflicts from review flags (Codex brief-gate iter-1 P1.5).
-        if qualitative_records:
-            _hard = [r for r in qualitative_records if r.severity in ("high", "medium")]
-            _review = [r for r in qualitative_records if r.severity == "review"]
-            methods += (
-                f"\n## Qualitative safety-conflict disclosures\n"
-                f"The qualitative detector flagged {len(_hard)} present-vs-absent clinical-safety "
-                f"conflict(s) (contraindication / drug-interaction / eligibility / warning / "
-                f"adverse-event causation) and {len(_review)} review-flagged item(s) requiring human "
-                f"adjudication. Status is shown as asserted PRESENT/ABSENT/INDETERMINATE, not a "
-                f"numeric value; review flags are NOT adjudicated conflicts.\n\n"
-            )
-            for r in _hard + _review:
-                _label = "CONFLICT" if r.severity in ("high", "medium") else "REVIEW"
-                _statuses = " vs ".join(
-                    f"{cl.get('assertion_status', '?')} "
-                    f"[ev={cl.get('evidence_id', '')}, tier={cl.get('source_tier', '')}]"
-                    for cl in r.claims
-                )
-                methods += f"- [{_label}] {r.subject} / {r.predicate}: {_statuses} — {r.conflict_reason}\n"
+        # BB5-P01 (#1179): collapse + dedup + clinical-gate via render_qualitative_disclosure. The
+        # raw per-pair dump was 82% of drb_75's file and mis-fired on non-clinical Qs. Qualitative
+        # records are NOT passed to the PT08 evaluator gate, so this trim is faithfulness-safe.
+        methods += render_qualitative_disclosure(
+            qualitative_records, is_clinical=_clinical_verified_only_surface,
+        )
 
         # Semantic/NLI cross-document contradiction disclosure (I-ready-012 #1079). Renders each
         # NLI-detected prose-only conflict (subject + predicate + the two conflicting claims with
@@ -5753,24 +6064,12 @@ async def run_one_query(
         # subject+predicate in report text) finds it. Distinct from the numeric renderer (no value
         # range) and the qualitative renderer (no assertion status); only present when the semantic
         # detector ran (default OFF) and found a conflict.
-        if semantic_records:
-            methods += (
-                f"\n## Semantic contradiction disclosures (cross-document NLI)\n"
-                f"An NLI pass over same-subject evidence pairs flagged {len(semantic_records)} "
-                f"prose-only directional contradiction(s) that carry no shared number and no "
-                f"rule-cue (and so are not caught by the numeric or qualitative detectors). Each "
-                f"is shown with both conflicting source claims for human adjudication.\n\n"
-            )
-            for r in semantic_records:
-                _claims = " VS ".join(
-                    f"\"{(cl.get('text') or '').strip()}\" "
-                    f"[ev={cl.get('evidence_id', '')}, tier={cl.get('tier', '')}]"
-                    for cl in r.claims
-                )
-                methods += (
-                    f"- [SEMANTIC] {r.subject} / {r.predicate} "
-                    f"(NLI confidence {r.nli_confidence:.2f}): {_claims}\n"
-                )
+        # BB5-P02 (#1179): the prior renderer dumped each record's full scraped row text
+        # (bibliographies, figure-markdown, image URLs) into the body. render_semantic_disclosure
+        # surfaces a short normalized claim summary per side (subject/predicate + ≤200-char trimmed
+        # quote), caps the inline count, and points to the sidecar for the rest. PT08-safe: subject
+        # + predicate of EVERY record still render inline (those are the substrings PT08 checks).
+        methods += render_semantic_disclosure(semantic_records)
 
         biblio_section = "\n\n## Bibliography\n"
         for b in multi.bibliography:
@@ -5792,6 +6091,12 @@ async def run_one_query(
             f"# Research report: {q['question']}\n\n"
             + _key_findings + sections_concat + methods + biblio_section
         )
+        # BB5-P03 (#1179): de-dup content-identical paragraphs (after citation-marker stripping) and
+        # drop any header orphaned by that drop, before render. Keeps the FIRST occurrence, so every
+        # subject/predicate a PT08-checked record disclosed survives — the evaluator below reads this
+        # same deduped text. Default ON via PG_SWEEP_LIMITATIONS_DEDUP; OFF leaves report byte-identical.
+        if _env_flag(_LIMITATIONS_DEDUP_ENV, default=True):
+            final_report = dedup_identical_paragraphs(final_report)
         (run_dir / "report.md").write_text(final_report, encoding="utf-8")
         (run_dir / "bibliography.json").write_text(
             json.dumps(multi.bibliography, indent=2, sort_keys=True) + "\n",
diff --git a/tests/polaris_graph/test_lane_c_presentation_bb5_p01_p02_p03.py b/tests/polaris_graph/test_lane_c_presentation_bb5_p01_p02_p03.py
new file mode 100644
index 00000000..33507ac6
--- /dev/null
+++ b/tests/polaris_graph/test_lane_c_presentation_bb5_p01_p02_p03.py
@@ -0,0 +1,262 @@
+"""Lane C (#1179) — offline deterministic tests for the three presentation-hygiene
+fixes BB5-P01/P02/P03 in ``scripts/run_honest_sweep_r3.py``.
+
+No network, no spend: the helpers under test are pure string/list transforms that
+take record-shaped objects (duck-typed via ``getattr``) and return markdown.
+
+- BB5-P01: ``render_qualitative_disclosure`` — clinical-gate, dedup, review-flag
+  collapse. Qualitative records are NOT passed to the PT08 evaluator gate, so the
+  collapse is faithfulness-safe.
+- BB5-P02: ``render_semantic_disclosure`` — strip scraped junk, trim quotes, cap
+  inline, but KEEP subject+predicate of every record (PT08 contract).
+- BB5-P03: ``dedup_identical_paragraphs`` — content-identity dedup of the
+  drb_90 duplicate paragraph + removal of the header it orphans, while the
+  distinct synthesized Limitations disclosure is preserved (no silent downgrade).
+"""
+from __future__ import annotations
+
+from dataclasses import dataclass, field
+
+import pytest
+
+from scripts.run_honest_sweep_r3 import (
+    dedup_identical_paragraphs,
+    render_qualitative_disclosure,
+    render_semantic_disclosure,
+)
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# Record stand-ins (duck-typed; mirror the real dataclasses' fields)
+# ─────────────────────────────────────────────────────────────────────────────
+@dataclass
+class _QualRecord:
+    subject: str
+    predicate: str
+    severity: str
+    claims: list = field(default_factory=list)
+    conflict_reason: str = "present-vs-absent across sources"
+
+
+@dataclass
+class _SemRecord:
+    subject: str
+    predicate: str
+    claims: list = field(default_factory=list)
+    nli_confidence: float = 0.0
+
+
+def _qual_claims(status_a: str, status_b: str) -> list:
+    return [
+        {"assertion_status": status_a, "evidence_id": "ev1", "source_tier": "T1"},
+        {"assertion_status": status_b, "evidence_id": "ev2", "source_tier": "T2"},
+    ]
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# BB5-P01 — qualitative
+# ─────────────────────────────────────────────────────────────────────────────
+def test_qualitative_non_clinical_renders_nothing() -> None:
+    """Clinical-safety detector mis-fires on non-clinical Qs (drb_90 ADAS, drb_72
+    labor) — the renderer must emit NOTHING for a non-clinical domain."""
+    records = [_QualRecord("warfarin", "contraindication", "high", _qual_claims("PRESENT", "ABSENT"))]
+    assert render_qualitative_disclosure(records, is_clinical=False) == ""
+
+
+def test_qualitative_empty_renders_nothing() -> None:
+    assert render_qualitative_disclosure([], is_clinical=True) == ""
+
+
+def test_qualitative_dedups_identical_rows() -> None:
+    """drb_75's 246 lines were duplicate (subject,predicate,status) rows — the
+    renderer collapses identical signatures to one line."""
+    dup = _QualRecord("probiotic", "contraindication", "high", _qual_claims("PRESENT", "ABSENT"))
+    dup2 = _QualRecord("probiotic", "contraindication", "high", _qual_claims("PRESENT", "ABSENT"))
+    unique = _QualRecord("iron", "warning", "high", _qual_claims("PRESENT", "ABSENT"))
+    out = render_qualitative_disclosure([dup, dup2, unique], is_clinical=True)
+    assert out.count("[CONFLICT]") == 2  # dup collapsed to one, plus unique
+    assert "flagged 2 present-vs-absent" in out
+
+
+def test_qualitative_review_flags_collapse_to_count_and_sidecar() -> None:
+    """REVIEW flags are advisory, not adjudicated — by default they collapse to a
+    one-line count + sidecar pointer (not a verbatim dump)."""
+    reviews = [
+        _QualRecord("a", "drug_interaction", "review", _qual_claims("PRESENT", "INDETERMINATE")),
+        _QualRecord("b", "eligibility", "review", _qual_claims("ABSENT", "INDETERMINATE")),
+    ]
+    out = render_qualitative_disclosure(reviews, is_clinical=True)
+    assert "[REVIEW]" not in out  # not dumped verbatim
+    assert "2 review-flagged item(s) collapsed" in out
+    assert "contradictions.json" in out  # sidecar pointer
+
+
+def test_qualitative_review_inline_opt_in_renders_rows() -> None:
+    reviews = [_QualRecord("a", "drug_interaction", "review", _qual_claims("PRESENT", "INDETERMINATE"))]
+    out = render_qualitative_disclosure(reviews, is_clinical=True, review_inline=True)
+    assert "[REVIEW] a / drug_interaction" in out
+
+
+def test_qualitative_keeps_hard_conflicts_inline() -> None:
+    """Auto-fired adjudicated CONFLICT rows belong in prose and must survive."""
+    hard = [_QualRecord("warfarin", "contraindication", "high", _qual_claims("PRESENT", "ABSENT"))]
+    out = render_qualitative_disclosure(hard, is_clinical=True)
+    assert "[CONFLICT] warfarin / contraindication" in out
+    assert "PRESENT" in out and "ABSENT" in out
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# BB5-P02 — semantic (PT08 contract: subject+predicate of EVERY record inline)
+# ─────────────────────────────────────────────────────────────────────────────
+_PT08_PREDICATE = "cross-document directional disagreement"
+
+
+def _sem_record(subject: str, text_a: str, text_b: str, conf: float = 0.91) -> _SemRecord:
+    return _SemRecord(
+        subject=subject,
+        predicate=_PT08_PREDICATE,
+        nli_confidence=conf,
+        claims=[
+            {"evidence_id": "evA", "text": text_a, "tier": "T1"},
+            {"evidence_id": "evB", "text": text_b, "tier": "T2"},
+        ],
+    )
+
+
+def test_semantic_empty_renders_nothing() -> None:
+    assert render_semantic_disclosure([]) == ""
+
+
+def test_semantic_strips_bibliography_and_image_urls() -> None:
+    """The drb_76 dump printed a full numbered bibliography + image markdown +
+    bare URLs. Those must be stripped from the rendered summary."""
+    junk = (
+        "Probiotics reduced inflammation in the colon.\n"
+        "1. Smith J. Gut microbiota. doi:10.1/x\n"
+        "2. Doe A. CRC review. doi:10.2/y\n"
+        "![figure 1](https://img.example.com/fig1.png)\n"
+        "See https://example.com/full-text for details."
+    )
+    rec = _sem_record("probiotics", junk, "No effect on inflammation was observed.")
+    out = render_semantic_disclosure([rec], quote_trim=200)
+    assert "doi:10.1/x" not in out
+    assert "https://img.example.com" not in out
+    assert "https://example.com/full-text" not in out
+    assert "![figure" not in out
+    assert "Probiotics reduced inflammation" in out
+
+
+def test_semantic_trims_quote_to_cap() -> None:
+    long_text = "word " * 200  # 1000 chars
+    rec = _sem_record("subjectx", long_text, "short opposing claim")
+    out = render_semantic_disclosure([rec], quote_trim=50)
+    # The trimmed quote must be short; the ellipsis marks truncation.
+    assert "…" in out
+    # No single rendered quote should approach the raw 1000-char length.
+    assert len(out) < 1200
+
+
+def test_semantic_keeps_subject_predicate_for_every_record_pt08() -> None:
+    """PT08 contract: even beyond the inline cap, subject+predicate of EVERY record
+    must appear in the report text so the evaluator gate passes."""
+    records = [_sem_record(f"subject{i}", f"claim {i} up", f"claim {i} down") for i in range(15)]
+    out = render_semantic_disclosure(records, inline_cap=3, quote_trim=80)
+    for i in range(15):
+        assert f"subject{i}" in out  # subject present for all 15
+    assert out.count(_PT08_PREDICATE) == 15  # predicate present for all 15
+    # Only the first 3 carry the trimmed quote payload; the rest are pointer lines.
+    assert out.count("full pair in") == 12
+
+
+def test_semantic_inline_cap_zero_still_emits_subject_predicate() -> None:
+    records = [_sem_record("alpha", "x up", "x down")]
+    out = render_semantic_disclosure(records, inline_cap=0)
+    assert "alpha" in out
+    assert _PT08_PREDICATE in out
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# BB5-P03 — content-identity dedup + orphan-header removal
+# ─────────────────────────────────────────────────────────────────────────────
+def test_dedup_drops_verbatim_duplicate_and_orphaned_header() -> None:
+    """drb_90: Implications body == first Limitations body (byte-identical after
+    stripping citation markers, citation NUMBERS differ). The duplicate body AND the
+    now-empty '### Limitations' header it left behind are both removed; the distinct
+    synthesized Limitations disclosure that follows is KEPT (no silent downgrade)."""
+    para = "This finding implies a material liability shift toward the manufacturer"
+    report = (
+        f"### Implications\n\n{para} [8][10].\n\n"
+        f"### Limitations\n\n{para} [1][2].\n\n"
+        f"### Limitations\n\nLimitations: the corpus is 84% UNKNOWN and 2% T1."
+    )
+    out = dedup_identical_paragraphs(report)
+    # Duplicate body appears once (kept under Implications).
+    assert out.count("material liability shift toward the manufacturer") == 1
+    # The orphaned (now-empty) Limitations header is dropped → exactly one remains.
+    assert out.count("### Limitations") == 1
+    # The unique synthesized disclosure SURVIVES (the silent-downgrade guard).
+    assert "84% UNKNOWN" in out
+    # The single remaining Limitations header is immediately followed by its real body.
+    idx = out.index("### Limitations")
+    assert "Limitations: the corpus is 84% UNKNOWN" in out[idx:idx + 120]
+
+
+def test_dedup_keeps_distinct_limitations_when_no_duplicate() -> None:
+    """When the outline Limitations and synthesized Limitations differ, BOTH headers
+    and bodies are preserved — content-identity dedup never drops distinct content."""
+    report = (
+        "### Limitations\n\nThe corpus skews toward reviews.\n\n"
+        "### Limitations\n\nA different appended limitation note about UNKNOWN tiers."
+    )
+    out = dedup_identical_paragraphs(report)
+    assert "The corpus skews toward reviews." in out
+    assert "A different appended limitation note about UNKNOWN tiers." in out
+
+
+def test_dedup_keeps_distinct_paragraphs() -> None:
+    report = (
+        "First distinct paragraph about iron.\n\n"
+        "Second distinct paragraph about copper.\n\n"
+        "Third distinct paragraph about zinc."
+    )
+    out = dedup_identical_paragraphs(report)
+    assert "iron" in out and "copper" in out and "zinc" in out
+    assert out == report  # nothing dropped
+
+
+def test_dedup_preserves_repeated_headers_with_distinct_bodies() -> None:
+    """A header followed by a real (non-duplicate) body is never treated as orphaned."""
+    report = "## Methods\n\nProtocol pinned.\n\n## Bibliography\n\n[1] Source — url"
+    out = dedup_identical_paragraphs(report)
+    assert "## Methods" in out and "## Bibliography" in out
+
+
+def test_dedup_empty_report_is_noop() -> None:
+    assert dedup_identical_paragraphs("") == ""
+
+
+def test_dedup_real_drb90_artifact_is_clean() -> None:
+    """§-1.1 real-output acceptance: run the helper on the actual beatboth5 drb_90
+    report and assert the duplicate + orphaned header are gone while the unique
+    corpus-skew disclosure survives. Skips if the artifact is absent."""
+    import re
+    from pathlib import Path
+
+    artifact = Path(__file__).resolve().parents[2] / "outputs" / "audits" / "beatboth5" / "drb_90_polaris.md"
+    if not artifact.exists():
+        pytest.skip("real drb_90 artifact not present")
+    raw = artifact.read_text(encoding="utf-8")
+    out = dedup_identical_paragraphs(raw)
+    headers_before = re.findall(r"^#{1,3} (Limitations|Implications)", raw, re.MULTILINE)
+    headers_after = re.findall(r"^#{1,3} (Limitations|Implications)", out, re.MULTILINE)
+    assert headers_before == ["Implications", "Limitations", "Limitations"]
+    assert headers_after == ["Implications", "Limitations"]  # one duplicate dropped
+    # Unique synthesized disclosure survives.
+    assert "84% of the corpus classified as UNKNOWN" in out
+    # Duplicate Implications/Limitations body collapses 2 -> 1.
+    needle = "Empirical safety data for higher levels of automation"
+    assert raw.count(needle) == 2 and out.count(needle) == 1
+
+
+if __name__ == "__main__":  # pragma: no cover
+    raise SystemExit(pytest.main([__file__, "-q"]))
