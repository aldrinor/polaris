HARD ITERATION CAP: 5 (this is the iter-5 fix re-verification; the prior iter-5 finding is addressed below). APPROVE iff zero NOVEL/continuing P0 and zero P1.

# Diff review — Lane B (#1178 C06/C07) FINAL. F02 (#1176) DEFERRED to bakeoff #1180.

## ADDRESSING your last finding (V30 contract gap pointer is CITED, so the citation filter missed it)
You correctly found the V30 contract-runner gap disclosure is a FIXED two-sentence template whose 2nd sentence ("See manifest.frame_coverage_report and human_gap_tasks.json for per-entity detail.[N]") carries a [N] pointing at the gap-task SIDECAR (not an evidence span), so the citation filter alone let it surface as a Key Finding. FIX: _first_verified_sentences now ALSO excludes any sentence matching _GAP_MARKER_RE — the canonical gap-disclosure boilerplate phrases (curator-actionable gap | did not survive strict/4-role verification | frame_coverage_report | human_gap_tasks). These are generated from FIXED constants (contract_section_runner / _GAP_STUB_SENTENCE), never free-form prose, so this is a deterministic RENDERING filter, not a §-1.1 quality-by-pattern judgement. A Key Finding now requires: a citation AND no gap-marker. New test test_c07_key_findings_excludes_cited_v30_contract_gap_pointer uses your EXACT shape (gap disclosure + cited gap-task pointer + a later real cited finding) and asserts the gap pointer is absent while "hazard ratio of 0.82 [2]" is present. 19 Lane B + 7 key_findings tests pass.

## Full C07 defense-in-depth (recap)
- Section level: filter_verified_sections + build_key_findings skip 0-verified gap sections (is_gap_stub OR sentences_verified==0) — catches pure-gap legacy + V30 sections.
- Sentence level: Key Findings requires a citation AND excludes gap-boilerplate — catches MIXED sections where a section has both a gap slot and real prose.
- C06 (full-text entity expansion) + the dropped-section gap stub render are unchanged.

## VERIFY (final, adversarial)
1. The V30 cited-gap pointer is excluded from Key Findings; a real cited finding in the same section IS surfaced.
2. No false-drop of a legitimate cited finding (the 7 existing key_findings tests are green).
3. abort_no_verified_sections still correctly aborts an all-gap report.
4. Faithfulness gate authority not weakened; F02 strict_verify untouched.

----- BEGIN DIFF -----
diff --git a/scripts/dr_benchmark/run_gate_b.py b/scripts/dr_benchmark/run_gate_b.py
index bdc0d3fd..ae367265 100644
--- a/scripts/dr_benchmark/run_gate_b.py
+++ b/scripts/dr_benchmark/run_gate_b.py
@@ -767,6 +767,28 @@ _BENCHMARK_PREFLIGHT_REQUIRED_OFF_FLAGS = (
 # is NOT required here (rescue widening is out of scope; judge_error fail-closed keys on the entailment mode).
 _BENCHMARK_PREFLIGHT_ENFORCE_MODES = ("PG_STRICT_VERIFY_ENTAILMENT",)
 
+# BB5-C06 (#1178): entity types that KEEP the OA full-text path even under PG_FRAME_PREFER_ABSTRACT.
+# frame_fetcher's default `_FULLTEXT_ENTITY_TYPES` is trial/review-only (pivotal_trial,clinical_trial,
+# rct,systematic_review,meta_analysis), so under prefer-abstract EVERY narrative / source-critical entity
+# (economic working paper, policy/CBO report, court decision, statute, regulatory label, mechanism study,
+# cohort study, technical standard) skipped its OA full text and read only the ~500-char abstract
+# (`skipped:prefer_abstract` in run 5; e.g. drb_72 frey_osborne OA full text on the Oxford repo was
+# skipped). The substantive claims of those entities live in the BODY, not the abstract — so the benchmark
+# must never skip an OA full text such an entity needs. We BROADEN the set to the full distinct entity-type
+# inventory of the locked scope templates that need full text (verified via
+# `grep "type: " config/scope_templates/*.yaml`). The clinical full-text types (already in the default) are
+# RE-INCLUDED because PG_FRAME_FULLTEXT_ENTITY_TYPES replaces the whole value — dropping them would regress
+# the M-66b-T clinical trial-roster path. prefer-abstract STAYS on (the clean deterministic abstract is the
+# right source for the entities NOT in this set); this only stops the full-text SKIP for entities that need it.
+_BENCHMARK_FULLTEXT_ENTITY_TYPES = ",".join((
+    # original clinical full-text types (frame_fetcher default) — re-included; whole-value replacement
+    "pivotal_trial", "clinical_trial", "rct", "systematic_review", "meta_analysis",
+    # narrative / source-critical types that ALSO need full text (BB5-C06 broadening)
+    "economic_report", "cbo_report", "policy_report", "mechanism_primary", "cohort_primary",
+    "regulatory", "regulatory_ruling", "regulation", "court_decision", "legal_case", "statute",
+    "technical_standard", "agency_report", "authoritative_source",
+))
+
 # Codex diff-gate iter-2 P1: import-time module CONSTANTS that the slate must have raised before the
 # owning module was imported (env-only validation would miss a too-late slate). The preflight reads the
 # LIVE constant and fails closed if it is below the floor. (module_path, attr, floor)
@@ -1071,6 +1093,15 @@ async def run_gate_b_query(
     # clean, deterministic abstract (CrossRef/OpenAlex) is the correct source — contract fields
     # are abstract-level claims. Prefer it over the scrape; setdefault keeps the operator override.
     os.environ.setdefault("PG_FRAME_PREFER_ABSTRACT", "1")
+    # BB5-C06 (#1178): prefer-abstract is RIGHT for entities whose contract fields are abstract-level, but
+    # it was ALSO skipping the OA full text of narrative / source-critical entities whose substantive claims
+    # live in the body (economic/policy/mechanism/cohort/regulatory/legal). Broaden the keep-full-text set so
+    # those entities keep the OA full-text path even under prefer-abstract — "never skip an OA full text an
+    # entity needs". MUST be set before the lazy frame_fetcher import (run_honest_sweep_r3.py:4567, inside the
+    # per-query V30 block) freezes `_FULLTEXT_ENTITY_TYPES` from this env — that import fires AFTER this line,
+    # so this placement (next to PG_FRAME_PREFER_ABSTRACT, both before the per-query import) is effective.
+    # setdefault keeps an explicit operator override (LAW VI).
+    os.environ.setdefault("PG_FRAME_FULLTEXT_ENTITY_TYPES", _BENCHMARK_FULLTEXT_ENTITY_TYPES)
     os.environ.setdefault("PG_OPENALEX_FRAME_FALLBACK", "1")
     # I-cap-002 feature 2/4 (#1060): turn on the ADVISORY analytical-depth annotation for the
     # benchmark/paid run ONLY here (gate-B entry), never globally — so manifest['analytical_depth_
diff --git a/scripts/run_honest_sweep_r3.py b/scripts/run_honest_sweep_r3.py
index a84131ae..5193f25c 100644
--- a/scripts/run_honest_sweep_r3.py
+++ b/scripts/run_honest_sweep_r3.py
@@ -1165,12 +1165,25 @@ def write_per_run_cost_ledger(run_dir: Path, run_id: str) -> int:
 def filter_verified_sections(sections) -> list:
     """Codex round 1 B-3: the single-source-of-truth predicate for
     "did this section survive Phase-4 strict_verify?". A section
-    qualifies only if it was NOT dropped AND has non-empty verified_text.
+    qualifies only if it was NOT dropped AND has non-empty verified_text
+    AND is not a gap-stub.
+
+    I-gen-006 (#1178) BB5-C07: a section that produced ZERO verified sentences is a
+    gap DISCLOSURE, not verified prose — whether it is the new legacy gap stub
+    (``is_gap_stub=True``) or a V30 contract slot's gap disclosure (``is_gap_stub``
+    stays False but ``sentences_verified == 0``). Both render for display with
+    ``dropped_due_to_failure=False`` + non-empty ``verified_text`` (the disclosure
+    text), so the UNIVERSAL survivor signal is ``sentences_verified > 0``. Excluding
+    every 0-verified gap here ensures a report whose every section is a gap
+    disclosure correctly hits ``abort_no_verified_sections`` instead of shipping as
+    success (Codex iter-3 P1: is_gap_stub alone missed the V30 gap class).
     """
     return [
         sr for sr in sections
         if not getattr(sr, "dropped_due_to_failure", True)
         and getattr(sr, "verified_text", "")
+        and getattr(sr, "sentences_verified", 1) > 0
+        and not getattr(sr, "is_gap_stub", False)
     ]
 
 
diff --git a/src/polaris_graph/generator/key_findings.py b/src/polaris_graph/generator/key_findings.py
index 91e31f0b..94e1867b 100644
--- a/src/polaris_graph/generator/key_findings.py
+++ b/src/polaris_graph/generator/key_findings.py
@@ -20,6 +20,29 @@ from typing import Any
 # diff-gate iter-1 P2).
 _SENTENCE_RE = re.compile(r".+?[.!?](?:\s*\[\d+\])*(?=\s+[A-Z(\[\d]|\s*$)", re.DOTALL)
 
+# A Key Finding is a SPAN-VERIFIED statement — by definition it carries its `[N]` / `[#ev:`
+# citation (module docstring). This is the robust per-SENTENCE gap filter (I-gen-006 #1178
+# C07/P07): a gap-disclosure sentence ("... did not survive strict verification; curator-
+# actionable gap.") carries NO citation, so in a MIXED V30 section (a leading gap slot +
+# later verified prose, where the SECTION still has sentences_verified>0) the uncited gap
+# sentence is skipped and the first CITED sentence is lifted instead. Keys on the citation
+# invariant, never on matching gap-disclosure text.
+_CITATION_RE = re.compile(r"\[\d+\]|\[#ev:")
+
+# Gap-disclosure boilerplate (I-gen-006 #1178 C07/P07, Codex iter-5): the V30 contract-runner
+# gap disclosure is a FIXED two-sentence template — "Contract-bound content ... curator-actionable
+# gap. See manifest.frame_coverage_report and human_gap_tasks.json for per-entity detail.[N]" — and
+# its SECOND sentence DOES carry a `[N]` (a pointer to the gap-task sidecar, NOT an evidence span),
+# so the citation filter alone cannot exclude it. A Key Finding must be a span-verified CLAIM, never
+# a gap pointer; exclude any sentence carrying a canonical gap-disclosure marker. Robust because the
+# disclosure text is generated from fixed constants (contract_section_runner / _GAP_STUB_SENTENCE),
+# never free-form prose — this is a rendering filter, not a §-1.1 quality-by-pattern judgement.
+_GAP_MARKER_RE = re.compile(
+    r"curator-actionable gap|did not survive strict verification|"
+    r"did not survive (?:4-role )?verification|frame_coverage_report|human_gap_tasks",
+    re.IGNORECASE,
+)
+
 _OFF_VALUES = frozenset({"0", "false", "no", "off", ""})
 
 # How many leading verified sentences to lift from each section (default 1 — the headline finding).
@@ -35,7 +58,14 @@ def key_findings_enabled() -> bool:
 
 def _first_verified_sentences(verified_text: str, n: int) -> list[str]:
     matches = [m.group(0).strip() for m in _SENTENCE_RE.finditer(verified_text or "")]
-    return [s for s in matches if s][:n]
+    # A Key Finding is a span-verified CLAIM: it must carry a citation AND must NOT be
+    # gap-disclosure boilerplate (whose 2nd sentence is cited to the gap-task sidecar, not
+    # an evidence span). Both filters together exclude every gap shape in a mixed section
+    # (I-gen-006 #1178 C07/P07, Codex iter-5).
+    return [
+        s for s in matches
+        if s and _CITATION_RE.search(s) and not _GAP_MARKER_RE.search(s)
+    ][:n]
 
 
 def build_key_findings(sections: list[Any]) -> str:
@@ -48,6 +78,12 @@ def build_key_findings(sections: list[Any]) -> str:
     for sr in sections or []:
         if getattr(sr, "dropped_due_to_failure", False):
             continue
+        # I-gen-006 (#1178) BB5-C07/P07: a 0-verified gap DISCLOSURE renders disclosure
+        # text in verified_text (the legacy is_gap_stub or a V30 contract gap) but is NOT
+        # span-verified prose — it must never surface as a Key-Findings "span-verified
+        # statement". Skip every gap disclosure (universal signal: sentences_verified == 0).
+        if getattr(sr, "is_gap_stub", False) or getattr(sr, "sentences_verified", 1) == 0:
+            continue
         verified_text = getattr(sr, "verified_text", "") or ""
         if not verified_text.strip():
             continue
diff --git a/src/polaris_graph/generator/multi_section_generator.py b/src/polaris_graph/generator/multi_section_generator.py
index 2266e181..db09e632 100644
--- a/src/polaris_graph/generator/multi_section_generator.py
+++ b/src/polaris_graph/generator/multi_section_generator.py
@@ -96,6 +96,35 @@ def _allowed_sections_for_domain(domain: str | None) -> list[str]:
     )
 
 
+# BB5-C07 (#1178): explicit gap-disclosure stub body for a legacy (non-V30) section whose every
+# generated sentence failed strict verification. Pre-fix the section silently VANISHED at render
+# (run_honest_sweep_r3.py:5232 skips `dropped_due_to_failure or not verified_text`; the assembly
+# at multi_section_generator.py:5363 excludes `dropped_due_to_failure` sections), so on a
+# clinical-safety question a planned "Safety" section could disappear with no trace (drb_75). This
+# stub mirrors the V30 slot path's gap disclosure (contract_section_runner.py:1006-1009): an honest,
+# curator-actionable disclosure that NO claim survived, NOT silence. It carries NO `[#ev:...]` /
+# `[N]` citation marker — fabricating a citation for a non-claim would be a faithfulness defect; a
+# marker-less disclosure is the faithful choice (the section renderer prepends the `### <title>`
+# heading, so the rendered line reads "### <title> ... no claim survived strict verification;
+# curator-actionable gap.").
+_GAP_STUB_SENTENCE = (
+    "No claim in this section survived strict verification against the retrieved "
+    "source text; this section is a curator-actionable gap. See the verification "
+    "details and frame-coverage report for per-claim disposition."
+)
+
+# BB5-C07 (#1178): the sibling vanish path. When a planned section has NO evidence rows assigned
+# in the pool at all (a starved corpus can route even a clinical Safety section here), the legacy
+# early-return marked it dropped_due_to_failure=True with empty verified_text — the SAME silent
+# vanish, same harm class. Render a distinct no-evidence gap stub so "a planned section never
+# silently disappears" is actually true. Marker-less for the same reason as _GAP_STUB_SENTENCE.
+_NO_EVIDENCE_GAP_STUB_SENTENCE = (
+    "No evidence was available in the retrieved corpus to ground this section; it is a "
+    "curator-actionable gap. The corpus did not yield any source assigned to this section "
+    "(see the retrieval and frame-coverage telemetry for the assignment trail)."
+)
+
+
 # Field-invariant section archetypes (I-meta-005 Phase 1 #985, brief §2.3).
 # These TAGS are the on-path control-flow key — a non-clinical question gets a
 # question-specific TITLE plus one of these tags, and on-mode audit routing
@@ -274,6 +303,16 @@ class SectionResult:
     # SectionResult is never `asdict`-ed in any OFF artifact path. Appended
     # LAST to preserve positional construction at the existing call sites.
     archetype: str = ""
+    # BB5-C07 (#1178): True ONLY for a legacy (non-V30) section that produced ZERO verified
+    # sentences and is rendered as an explicit gap-disclosure stub instead of silently vanishing.
+    # The stub section ships with `dropped_due_to_failure=False` so the body + assembly render it
+    # (mirroring the V30 slot path), but it carries ZERO verified sentences. This flag is the
+    # explicit skip signal for any consumer that must NOT treat a gap stub as verified prose —
+    # e.g. the Key-Findings exec-summary (BB5-P07, separate lane) which must skip gap-placeholder
+    # sections so the stub never surfaces as a "span-verified statement". `sentences_verified == 0`
+    # is the equivalent implicit signal. Default False -> every real / V30 / legacy-with-content
+    # section is byte-identical.
+    is_gap_stub: bool = False
 
 
 @dataclass
@@ -2103,17 +2142,22 @@ async def _run_section(
         if ev_id in evidence_pool
     ]
     if not ev_subset:
+        # BB5-C07 (#1178) sibling vanish path: a planned section with NO assigned evidence must
+        # NOT silently disappear either. Render the no-evidence gap stub and ship the section
+        # (dropped_due_to_failure=False, is_gap_stub=True) so the gap is visible + curator-actionable.
+        # `error="no_evidence_in_pool"` is preserved for telemetry so the cause stays auditable.
         return SectionResult(
             title=section.title, focus=section.focus,
             ev_ids_assigned=section.ev_ids,
             raw_draft="", rewritten_draft="",
-            verified_text="", biblio_slice=[],
+            verified_text=_NO_EVIDENCE_GAP_STUB_SENTENCE, biblio_slice=[],
             sentences_verified=0, sentences_dropped=0,
-            regen_attempted=False, dropped_due_to_failure=True,
+            regen_attempted=False, dropped_due_to_failure=False,
             error="no_evidence_in_pool",
             # I-meta-005 Phase 1 (#985, P2 note B): carry the plan's archetype
             # onto the result so on-mode audit routing keys on the tag.
             archetype=getattr(section, "archetype", ""),
+            is_gap_stub=True,
         )
 
     total_in_tok = 0
@@ -2284,7 +2328,21 @@ async def _run_section(
     # IDs are byte-preserved (see _normalize_citation_punctuation).
     verified_text = _normalize_citation_punctuation(verified_text)
 
-    dropped_due_to_failure = len(report.kept_sentences) == 0
+    # BB5-C07 (#1178): a section that produced ZERO verified sentences must NOT silently vanish.
+    # Pre-fix, `dropped_due_to_failure=True` + empty `verified_text` caused the section to be
+    # skipped at every render/assembly site (run_honest_sweep_r3.py:5232 + assembly:5363), so a
+    # planned clinical-safety section could disappear with no trace (drb_75 "Safety" vanished).
+    # Mirror the V30 slot path: render an explicit gap-disclosure stub and ship the section so it
+    # appears in the body + assembly. The section is tagged `is_gap_stub=True` (and carries zero
+    # verified sentences) so a consumer that must not treat a gap stub as verified prose can skip
+    # it (e.g. Key Findings, BB5-P07, separate lane). The stub is marker-less (no fabricated
+    # citation for a non-claim — faithful disclosure, not a claim). With the stub always rendered,
+    # `dropped_due_to_failure` is now never True from this legacy path (the zero-kept case becomes
+    # a rendered gap stub; the non-zero case was never dropped) — every section ships with a trace.
+    is_gap_stub = len(report.kept_sentences) == 0
+    if is_gap_stub:
+        verified_text = _GAP_STUB_SENTENCE
+    dropped_due_to_failure = False
 
     # I-gen-005 Step 1.5 iter-2 (Codex P1 #2): include M-41c policy
     # drops in sentences_dropped so the section-level total matches
@@ -2327,6 +2385,9 @@ async def _run_section(
         # I-meta-005 Phase 1 (#985, P2 note B): carry the plan's archetype
         # onto the result so on-mode M-44/M-47 route on the tag, not title.
         archetype=getattr(section, "archetype", ""),
+        # BB5-C07 (#1178): tag the rendered gap-disclosure stub so a consumer that must not
+        # treat it as verified prose (Key Findings, BB5-P07) can skip it.
+        is_gap_stub=is_gap_stub,
     )
 
 
diff --git a/tests/dr_benchmark/test_lane_b_gen_faithfulness_completeness_beatboth5.py b/tests/dr_benchmark/test_lane_b_gen_faithfulness_completeness_beatboth5.py
new file mode 100644
index 00000000..36cf5029
--- /dev/null
+++ b/tests/dr_benchmark/test_lane_b_gen_faithfulness_completeness_beatboth5.py
@@ -0,0 +1,709 @@
+"""Lane B_gen — beat-both run-5 generation faithfulness + completeness fixes.
+
+Covers three bugs from outputs/audits/beatboth5/FULL_BUG_LIST.md, all OFFLINE and
+deterministic (no network, no spend — judge + LLM + retrieval are monkeypatched):
+
+  BB5-F02 (#1176, faithfulness) — clinical overgeneralization: a sentence that DROPS a
+    scope-narrowing qualifier (strain/subgroup/timepoint) from its cited span is NOT entailed
+    by that span, so the BINDING entailment gate must DROP it under enforce mode. The drb_76
+    example: span "S. cerevisiae var. boulardii probiotics are not recommended ..." widened to
+    "current evidence advises against routine probiotic use ..." (strain dropped). These tests
+    exercise the REAL benchmark binding gate (generator/provenance_generator.strict_verify ->
+    verify_sentence_provenance, the verifier scripts/run_honest_sweep_r3.py actually uses) with a
+    FakeJudge returning NEUTRAL. They prove the GATE MECHANICS: a NEUTRAL verdict on a widened
+    sentence is dropped fail-closed (incl. the local-window re-judge). They do NOT prove the real
+    Gemma model returns NEUTRAL for boulardii->probiotics — empirically it returned ENTAILED
+    (drb_76 manifest: the poster sentence is in entailed_count, and the rendered report kept it).
+
+    PRODUCTION FIX DEFERRED to the prompt/model bake-off #1180 (Codex iter-1 REQUEST_CHANGES on
+    #1178): making the real entailment judge return NEUTRAL for boulardii->probiotics is a model/
+    prompt lever (entailment_judge._ENTAILMENT_PROMPT, whose NEUTRAL examples are narrowing-only),
+    NOT a strict_verify change. strict_verify / verify_sentence_provenance are UNTOUCHED in this
+    lane. The tests below remain as GATE-MECHANICS documentation only — they assert the binding
+    gate drops a NEUTRAL-judged widening; they do NOT claim F02 is fixed in production. The real
+    boulardii->probiotics catch lands in #1180.
+
+  BB5-C06 (#1178, completeness) — run_gate_b forced PG_FRAME_PREFER_ABSTRACT=1 with
+    frame_fetcher's _FULLTEXT_ENTITY_TYPES being trial/review-only, so EVERY narrative /
+    source-critical entity (economic/policy/mechanism/cohort/regulatory/legal) skipped its OA
+    full text and read only the ~500-char abstract. Fix broadens the keep-full-text set via
+    PG_FRAME_FULLTEXT_ENTITY_TYPES (set before the lazy frame_fetcher import freezes it).
+
+  BB5-C07 (#1178, completeness) — a legacy (non-V30) section that yields ZERO verified sentences
+    was marked dropped_due_to_failure=True with empty verified_text and SILENTLY VANISHED at
+    render (drb_75 "Safety" disappeared on a clinical-safety question). Fix renders an explicit
+    gap-disclosure stub (mirroring the V30 slot path) tagged is_gap_stub=True so the section ships
+    with a trace and downstream verified-prose consumers can still skip it.
+"""
+
+from __future__ import annotations
+
+import asyncio
+
+import pytest
+
+from src.polaris_graph.clinical_generator import strict_verify as _judge_home
+from src.polaris_graph.generator import multi_section_generator as _msg
+from src.polaris_graph.generator.provenance_generator import (
+    verify_sentence_provenance,
+)
+
+
+# ---------------------------------------------------------------------------
+# Shared FakeJudge — mirrors tests/polaris_graph/test_provenance_generator_entailment.py
+# ---------------------------------------------------------------------------
+
+class _FakeJudge:
+    """Returns a fixed verdict on EVERY judge call (so the binding gate's narrow-span
+    judge AND its local-window re-judge both see the same verdict)."""
+
+    def __init__(self, verdict: str, reason: str = "fake") -> None:
+        self.verdict = verdict
+        self.reason = reason
+        self.calls: list[tuple[str, str]] = []
+
+    def judge(self, sentence: str, span: str) -> tuple[str, str]:
+        self.calls.append((sentence, span))
+        return self.verdict, self.reason
+
+
+def _install_judge(monkeypatch, fake: _FakeJudge) -> None:
+    """Replace the judge singleton + factory on the judge's canonical home module so
+    verify_sentence_provenance (which lazy-imports _get_judge from there) picks up the fake."""
+    monkeypatch.setattr(_judge_home, "_JUDGE_SINGLETON", fake, raising=False)
+    monkeypatch.setattr(_judge_home, "_get_judge", lambda: fake)
+
+
+@pytest.fixture(autouse=True)
+def _reset_judge_telemetry():
+    _judge_home.reset_judge_telemetry()
+    yield
+
+
+def _pool(direct_quote: str, evidence_id: str = "ev_strain") -> dict:
+    return {
+        evidence_id: {
+            "evidence_id": evidence_id,
+            "direct_quote": direct_quote,
+            "url": "https://example.org/finnish-registry",
+            "tier": "T1",
+        },
+    }
+
+
+# ===========================================================================
+# BB5-F02 — strain-generalization (clinical overgeneralization) drop regression
+# ===========================================================================
+
+# The cited SPAN names the SPECIFIC strain (S. cerevisiae var. boulardii). Verbatim from the
+# drb_76 source (outputs/audits/beatboth5/drb_76_polaris.md:44).
+_BOULARDII_SPAN = (
+    "The authors conclude that S. cerevisiae var. boulardii probiotics are not "
+    "recommended for patients with indwelling catheters, who are immunocompromised, "
+    "or who are critically ill."
+)
+
+# The SHIPPED sentence DROPS the strain qualifier and widens to a blanket "probiotic" caution.
+# Verbatim widened claim from the same report. It shares >=2 content words with the span
+# (probiotic / patients / immunocompromised|immunosuppression / catheters|catheter / critical),
+# carries no decimals, so the mechanical checks pass and the sentence REACHES the entailment judge.
+def _widened_sentence(evidence_id: str = "ev_strain") -> str:
+    span_len = len(_BOULARDII_SPAN)
+    return (
+        "Current evidence advises against routine probiotic use in patients with "
+        "central venous catheters, immunosuppression, or critical illness "
+        f"[#ev:{evidence_id}:0-{span_len}]."
+    )
+
+
+def test_f02_strain_widening_dropped_under_enforce(monkeypatch):
+    """The binding benchmark gate MUST drop the strain-widened sentence on a NEUTRAL verdict.
+
+    Proves gate mechanics: a sentence the cited span does NOT entail (dropped strain qualifier)
+    is dropped fail-closed in enforce mode. Does NOT prove the real model returns NEUTRAL here.
+    """
+    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
+    fake = _FakeJudge("NEUTRAL", "span specifies S. boulardii; sentence generalizes to 'probiotics'")
+    _install_judge(monkeypatch, fake)
+
+    pool = _pool(_BOULARDII_SPAN)
+    result = verify_sentence_provenance(_widened_sentence(), pool)
+
+    assert result.is_verified is False, (
+        "a strain-widened (qualifier-dropped) sentence judged NEUTRAL must be dropped"
+    )
+    assert any(
+        r.startswith("entailment_failed:") for r in result.failure_reasons
+    ), f"expected entailment_failed drop reason, got {result.failure_reasons}"
+    # The judge must actually have been reached (mechanical checks did not pre-empt it).
+    assert fake.calls, "entailment judge must run (mechanical checks must not pre-empt it)"
+
+
+def test_f02_faithful_paraphrase_kept_when_entailed(monkeypatch):
+    """Positive control: a strain-PRESERVING paraphrase the span entails must be KEPT —
+    the gate strengthening must not false-drop faithful clinical prose."""
+    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
+    fake = _FakeJudge("ENTAILED")
+    _install_judge(monkeypatch, fake)
+
+    pool = _pool(_BOULARDII_SPAN)
+    span_len = len(_BOULARDII_SPAN)
+    faithful = (
+        "S. cerevisiae var. boulardii probiotics are not recommended for "
+        "immunocompromised patients or those with indwelling catheters "
+        f"[#ev:ev_strain:0-{span_len}]."
+    )
+    result = verify_sentence_provenance(faithful, pool)
+    assert result.is_verified is True, (
+        f"strain-preserving faithful paraphrase must pass, got {result.failure_reasons}"
+    )
+
+
+def test_f02_off_mode_does_not_drop_widening(monkeypatch):
+    """Honest scope boundary: with the gate OFF the widened sentence is NOT dropped and the
+    judge never runs — confirms the drop is the ENFORCE gate's doing, not a mechanical check."""
+    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
+    fake = _FakeJudge("NEUTRAL")
+    _install_judge(monkeypatch, fake)
+
+    pool = _pool(_BOULARDII_SPAN)
+    result = verify_sentence_provenance(_widened_sentence(), pool)
+    assert result.is_verified is True, "off mode must keep the sentence (no entailment gate)"
+    assert fake.calls == [], "off mode must not invoke the judge"
+
+
+# ===========================================================================
+# BB5-C06 — broadened keep-full-text entity types for the benchmark
+# ===========================================================================
+
+def test_c06_fulltext_entity_types_cover_narrative_and_source_critical():
+    """The broadened keep-full-text set must include the narrative / source-critical entity types
+    whose substantive claims live in the body, NOT just the original trial/review types.
+
+    Grounded in the distinct `type:` inventory of config/scope_templates/*.yaml."""
+    from scripts.dr_benchmark.run_gate_b import _BENCHMARK_FULLTEXT_ENTITY_TYPES
+
+    types = {t.strip() for t in _BENCHMARK_FULLTEXT_ENTITY_TYPES.split(",") if t.strip()}
+
+    # Original clinical full-text types MUST be re-included (the env var replaces the whole value,
+    # so dropping them would regress the clinical trial-roster path).
+    for original in ("pivotal_trial", "clinical_trial", "rct", "systematic_review", "meta_analysis"):
+        assert original in types, f"clinical full-text type {original!r} dropped (regression)"
+
+    # The narrative / source-critical types that drb_72/75/76/78/90 contracts bind and that
+    # silently read abstract-only under the pre-fix config.
+    for narrative in (
+        "economic_report", "policy_report", "cbo_report",
+        "mechanism_primary", "cohort_primary",
+        "regulatory", "court_decision", "legal_case", "statute",
+    ):
+        assert narrative in types, (
+            f"narrative/source-critical type {narrative!r} missing — its OA full text would "
+            f"still be skipped under prefer-abstract (BB5-C06)"
+        )
+
+
+def test_c06_run_gate_b_sets_fulltext_env_before_prefer_abstract():
+    """run_gate_b_query must set PG_FRAME_FULLTEXT_ENTITY_TYPES (via setdefault, operator-override
+    safe) so the broadened set is in os.environ before the lazy frame_fetcher import freezes it.
+    Static source check (the live call path is operator-gated + spends money)."""
+    import inspect
+
+    from scripts.dr_benchmark import run_gate_b
+
+    src = inspect.getsource(run_gate_b.run_gate_b_query)
+    assert 'setdefault("PG_FRAME_FULLTEXT_ENTITY_TYPES"' in src, (
+        "run_gate_b_query must setdefault PG_FRAME_FULLTEXT_ENTITY_TYPES"
+    )
+    # Must be wired to the named constant (LAW VI — no inline magic comma-string).
+    assert "_BENCHMARK_FULLTEXT_ENTITY_TYPES" in src
+    # Ordering guard: the FULLTEXT env set must appear at/after PG_FRAME_PREFER_ABSTRACT (both
+    # before the per-query frame_fetcher import) so broadening cannot be a no-op.
+    assert src.index('setdefault("PG_FRAME_PREFER_ABSTRACT"') <= src.index(
+        'setdefault("PG_FRAME_FULLTEXT_ENTITY_TYPES"'
+    )
+
+
+# ---------------------------------------------------------------------------
+# Offline frame_fetcher harness for the BEHAVIORAL C06 test (Codex iter-1 P2:
+# the import-freeze / constant-membership check is INSUFFICIENT — call
+# fetch_frame_entity and assert the decision PATH does not emit
+# skipped:prefer_abstract for a newly-included entity type). Mirrors the proven
+# offline pattern in tests/polaris_graph/test_m56_frame_fetcher.py: a programmable
+# httpx.MockTransport feeds canned CrossRef (with abstract) + Unpaywall (is_oa,
+# so an oa_locator exists) responses so the prefer-abstract SKIP branch is
+# REACHABLE; the assertion is that it is NOT taken for the broadened type. No
+# network, no spend. frame_fetcher is NOT edited.
+# ---------------------------------------------------------------------------
+
+def _frame_binding(entity_type: str):
+    """Minimal DOI-primary EvidenceBinding for the frame fetcher (offline)."""
+    from src.polaris_graph.nodes.frame_compiler import EvidenceBinding
+
+    return EvidenceBinding(
+        entity_id=f"{entity_type}_primary",
+        entity_type=entity_type,
+        primary_identifier="doi:10.1056/NEJMoa2107519",
+        secondary_identifiers=("pmid:34010531",),
+        rendering_slot=f"slot_{entity_type}",
+        required_fields=("primary_finding",),
+        min_fields_for_completion=1,
+    )
+
+
+def _frame_crossref_with_abstract() -> dict:
+    """CrossRef /works payload carrying an abstract (so ABSTRACT_ONLY is a valid fallback)."""
+    return {
+        "status": "ok",
+        "message": {
+            "DOI": "10.1056/NEJMoa2107519",
+            "title": ["A working-paper-style economic analysis"],
+            "container-title": ["NBER Working Paper"],
+            "published-print": {"date-parts": [[2021, 6, 10]]},
+            "author": [{"family": "Acemoglu", "given": "Daron"}],
+            "abstract": "<jats:p>We estimate the effect on output and employment.</jats:p>",
+        },
+    }
+
+
+def _frame_unpaywall_is_oa() -> dict:
+    """Unpaywall payload advertising an OA PDF -> an oa_locator EXISTS, so the
+    prefer-abstract SKIP branch (oa_locator and entity_prefers_abstract) is reachable."""
+    return {
+        "doi": "10.1056/NEJMoa2107519",
+        "is_oa": True,
+        "best_oa_location": {"url_for_pdf": "https://oa.example/econ.pdf"},
+    }
+
+
+def _frame_mock_client():
+    """httpx.Client backed by a MockTransport that answers CrossRef + Unpaywall by URL substring."""
+    import httpx
+
+    def _handler(request: "httpx.Request") -> "httpx.Response":
+        url = str(request.url)
+        if "api.crossref.org" in url:
+            return httpx.Response(200, json=_frame_crossref_with_abstract())
+        if "api.unpaywall.org" in url:
+            return httpx.Response(200, json=_frame_unpaywall_is_oa())
+        return httpx.Response(404, json={"error": "no_rule"})
+
+    return httpx.Client(transport=httpx.MockTransport(_handler), timeout=5.0)
+
+
+def test_c06_broadened_type_does_not_skip_prefer_abstract_when_called(monkeypatch):
+    """BEHAVIORAL (Codex iter-1 P2): call the REAL fetch_frame_entity for a newly-included
+    narrative type (economic_report) with prefer-abstract ON and the broadened keep-full-text
+    set applied, and assert the decision path emits NO 'skipped:prefer_abstract' attempt — i.e.
+    the OA full-text path is actually KEPT, not just that the constant contains the type.
+
+    The OA scrape (_fetch_url_pattern) is monkeypatched to a deterministic clean full text so the
+    kept-full-text branch resolves offline; CrossRef/Unpaywall are MockTransport-fed. The control
+    below (a NOT-included type) proves the same harness DOES skip, so this is a real decision-path
+    assertion, not a tautology."""
+    import importlib
+
+    from scripts.dr_benchmark.run_gate_b import _BENCHMARK_FULLTEXT_ENTITY_TYPES
+
+    monkeypatch.setenv("PG_FRAME_PREFER_ABSTRACT", "1")
+    monkeypatch.setenv("PG_FRAME_FULLTEXT_ENTITY_TYPES", _BENCHMARK_FULLTEXT_ENTITY_TYPES)
+
+    import src.polaris_graph.retrieval.frame_fetcher as ff
+    ff = importlib.reload(ff)
+    try:
+        # Sanity: the broadened env actually froze into the module constant + prefer-abstract is ON.
+        assert "economic_report" in ff._FULLTEXT_ENTITY_TYPES
+        assert ff._FRAME_PREFER_ABSTRACT is True
+
+        clean_full = "Clean genuine OA full text body for the economic working paper. " * 60
+        monkeypatch.setattr(ff, "_fetch_url_pattern", lambda url: (clean_full, url))
+
+        with _frame_mock_client() as client:
+            row = ff.fetch_frame_entity(_frame_binding("economic_report"), client=client)
+
+        skip_attempts = [
+            a for a in row.retrieval_attempts
+            if str(a.outcome).startswith("skipped:prefer_abstract")
+        ]
+        assert skip_attempts == [], (
+            "economic_report is in the broadened keep-full-text set -> fetch_frame_entity must NOT "
+            f"skip its OA full text, but got skip attempts: {[a.outcome for a in skip_attempts]}"
+        )
+        # And the kept full text is what reached direct_quote (not the ~500-char abstract).
+        assert row.quote_source == "oa_full_text", (
+            f"broadened type must keep the OA full-text path, got quote_source={row.quote_source!r}"
+        )
+        assert "economic working paper" in row.direct_quote
+    finally:
+        monkeypatch.undo()
+        importlib.reload(ff)
+
+
+def test_c06_control_excluded_type_still_skips_prefer_abstract(monkeypatch):
+    """Control proving the harness is not a tautology: under the SAME prefer-abstract env but the
+    DEFAULT (un-broadened) keep-full-text set, a narrative type that is NOT in the default
+    (economic_report) DOES emit 'skipped:prefer_abstract'. So the broadened-type assertion above
+    is a genuine decision-path change, not a harness that can never skip."""
+    import importlib
+
+    monkeypatch.setenv("PG_FRAME_PREFER_ABSTRACT", "1")
+    # NOTE: no PG_FRAME_FULLTEXT_ENTITY_TYPES override -> frame_fetcher uses its trial/review-only
+    # default, which does NOT contain economic_report.
+    monkeypatch.delenv("PG_FRAME_FULLTEXT_ENTITY_TYPES", raising=False)
+
+    import src.polaris_graph.retrieval.frame_fetcher as ff
+    ff = importlib.reload(ff)
+    try:
+        assert "economic_report" not in ff._FULLTEXT_ENTITY_TYPES, (
+            "control precondition: economic_report must be ABSENT from the default keep-full-text set"
+        )
+        assert ff._FRAME_PREFER_ABSTRACT is True
+
+        def _boom(url):  # pragma: no cover - the skip must pre-empt any scrape
+            raise AssertionError("scrape must be skipped for an excluded type under prefer-abstract")
+        monkeypatch.setattr(ff, "_fetch_url_pattern", _boom)
+
+        with _frame_mock_client() as client:
+            row = ff.fetch_frame_entity(_frame_binding("economic_report"), client=client)
+
+        assert any(
+            str(a.outcome).startswith("skipped:prefer_abstract") for a in row.retrieval_attempts
+        ), "an excluded narrative type under prefer-abstract MUST skip the OA full text (control)"
+    finally:
+        monkeypatch.undo()
+        importlib.reload(ff)
+
+
+# ===========================================================================
+# BB5-C07 — dropped section renders an explicit gap stub instead of vanishing
+# ===========================================================================
+
+def test_c07_gap_stub_sentence_is_marker_less():
+    """The gap-disclosure stub must carry NO provenance/citation marker — fabricating a citation
+    for a non-claim would be a faithfulness defect (it is a disclosure, not a verified claim)."""
+    stub = _msg._GAP_STUB_SENTENCE
+    assert "[#ev:" not in stub and "[#calc:" not in stub, "stub must not carry a provenance token"
+    import re
+    assert not re.search(r"\[\d+\]", stub), "stub must not carry a numbered citation marker"
+    assert "curator-actionable gap" in stub
+    assert "did not" not in stub.lower() or "survive" in stub.lower()  # honest disclosure wording
+
+
+def test_c07_section_result_is_gap_stub_defaults_false():
+    """Byte-identical default: a normal SectionResult is not a gap stub."""
+    sr = _msg.SectionResult(
+        title="Efficacy", focus="", ev_ids_assigned=[], raw_draft="", rewritten_draft="",
+        verified_text="A verified claim [1].", biblio_slice=[],
+        sentences_verified=1, sentences_dropped=0, regen_attempted=False,
+        dropped_due_to_failure=False,
+    )
+    assert sr.is_gap_stub is False
+
+
+def test_c07_gap_stub_section_survives_render_and_assembly_skip():
+    """A gap-stub section must NOT be skipped by the render/assembly predicate
+    (`dropped_due_to_failure or not verified_text`) — that is exactly what made it vanish — while
+    a verified-prose consumer can still skip it via is_gap_stub / sentences_verified==0."""
+    stub_sr = _msg.SectionResult(
+        title="Safety", focus="", ev_ids_assigned=[], raw_draft="", rewritten_draft="",
+        verified_text=_msg._GAP_STUB_SENTENCE, biblio_slice=[],
+        sentences_verified=0, sentences_dropped=5, regen_attempted=True,
+        dropped_due_to_failure=False, is_gap_stub=True,
+    )
+    # Render/assembly skip predicate used at run_honest_sweep_r3.py:5232 + assembly:5363.
+    render_skipped = stub_sr.dropped_due_to_failure or not stub_sr.verified_text
+    assert render_skipped is False, "gap-stub section must render (not vanish)"
+    # Verified-prose consumer (Key Findings / BB5-P07) skip signals.
+    assert stub_sr.is_gap_stub is True
+    assert stub_sr.sentences_verified == 0
+
+
+def test_c07_run_section_renders_stub_when_zero_verified(monkeypatch):
+    """Exercise the REAL _run_section line-2287 logic: when strict_verify keeps ZERO sentences,
+    the returned SectionResult must (a) NOT be dropped_due_to_failure, (b) carry the gap stub as
+    verified_text, (c) be tagged is_gap_stub=True, (d) report sentences_verified == 0.
+
+    Fully offline: _call_section (LLM), strict_verify, the rewrite, the repair loop, the M-41c
+    filter, and the citation resolver are all monkeypatched to force the zero-verified path."""
+
+    class _ZeroReport:
+        def __init__(self) -> None:
+            self.kept_sentences: list = []
+            self.dropped_sentences: list = ["s1", "s2", "s3"]
+            self.total_kept = 0
+            self.total_dropped = 3
+            self.total_in = 3
+
+    async def _fake_call_section(*args, **kwargs):
+        return ("raw draft prose", 10, 20, {})
+
+    def _fake_strict_verify(rewritten, evidence_pool):
+        return _ZeroReport()
+
+    def _fake_rewrite(raw, evidence_pool):
+        return (raw, [], [])
+
+    def _fake_m41c(kept):
+        # No kept sentences -> nothing to filter; no policy drops.
+        return (list(kept), [])
+
+    def _fake_resolve(kept_sentences, evidence_pool):
+        # Zero kept -> empty resolved text + empty bibliography. The stub OVERRIDES this.
+        return ("", [])
+
+    def _fake_normalize(text):
+        return text
+
+    async def _fake_repair(*args, **kwargs):
+        # Repair recovers nothing (keep zero). Telemetry object with attempts==0 short-circuits
+        # the logging branch in _run_section.
+        class _Tel:
+            attempts = 0
+            successes = 0
+            recovery_rate = 0.0
+            null_drops = 0
+            token_set_violations = 0
+            re_verify_failures = 0
+            api_failures = 0
+            input_tokens = 0
+            output_tokens = 0
+        return ([], ["s1", "s2", "s3"], _Tel())
+
+    monkeypatch.setattr(_msg, "_call_section", _fake_call_section)
+    monkeypatch.setattr(_msg, "strict_verify", _fake_strict_verify)
+    monkeypatch.setattr(_msg, "_rewrite_draft_with_spans", _fake_rewrite)
+    monkeypatch.setattr(_msg, "filter_underframed_trial_sentences", _fake_m41c)
+    monkeypatch.setattr(_msg, "resolve_provenance_to_citations", _fake_resolve)
+    monkeypatch.setattr(_msg, "_normalize_citation_punctuation", _fake_normalize)
+    # The repair loop lazy-imports from this module; patch the source symbol.
+    import src.polaris_graph.generator.sentence_repair as _sr_mod
+    monkeypatch.setattr(_sr_mod, "repair_dropped_section_sentences", _fake_repair)
+
+    section = _msg.SectionPlan(title="Safety", focus="adverse events", ev_ids=["ev_a"])
+    pool = {"ev_a": {"evidence_id": "ev_a", "direct_quote": "Some safety text.", "tier": "T1"}}
+
+    result = asyncio.run(
+        _msg._run_section(
+            section, pool,
+            model="x", temperature=0.2, max_tokens_per_section=500,
+            min_kept_fraction=0.4,
+        )
+    )
+
+    assert result.is_gap_stub is True, "zero-verified section must be tagged a gap stub"
+    assert result.dropped_due_to_failure is False, "gap stub must NOT be dropped (would vanish)"
+    assert result.verified_text == _msg._GAP_STUB_SENTENCE, "gap stub text must be rendered"
+    assert result.sentences_verified == 0, "gap stub carries zero verified sentences"
+    assert result.title == "Safety", "the planned section title is preserved"
+
+
+def test_c07_no_evidence_section_renders_stub_not_vanish():
+    """Sibling vanish path: a planned section with NO assigned evidence in the pool must render
+    the no-evidence gap stub (dropped_due_to_failure=False, is_gap_stub=True) instead of silently
+    disappearing. Hits the early-return before any LLM/strict_verify, so it is trivially offline."""
+    section = _msg.SectionPlan(title="Safety", focus="adverse events", ev_ids=["ev_missing"])
+    # The pool does NOT contain ev_missing -> ev_subset is empty -> early-return path.
+    pool = {"ev_other": {"evidence_id": "ev_other", "direct_quote": "Unrelated text.", "tier": "T1"}}
+
+    result = asyncio.run(
+        _msg._run_section(
+            section, pool,
+            model="x", temperature=0.2, max_tokens_per_section=500,
+            min_kept_fraction=0.4,
+        )
+    )
+    assert result.is_gap_stub is True
+    assert result.dropped_due_to_failure is False, "no-evidence section must NOT vanish"
+    assert result.verified_text == _msg._NO_EVIDENCE_GAP_STUB_SENTENCE
+    assert result.sentences_verified == 0
+    assert result.error == "no_evidence_in_pool", "cause preserved for telemetry"
+    assert result.title == "Safety"
+
+
+def test_c07_no_evidence_stub_is_marker_less():
+    """The no-evidence stub must also be marker-less (faithful disclosure, not a fabricated claim)."""
+    import re
+    stub = _msg._NO_EVIDENCE_GAP_STUB_SENTENCE
+    assert "[#ev:" not in stub and "[#calc:" not in stub
+    assert not re.search(r"\[\d+\]", stub)
+    assert "curator-actionable gap" in stub
+
+
+# ---------------------------------------------------------------------------
+# BB5-C07 (#1178) — cross-lane abort_no_verified_sections invariant contract.
+#
+# Codex iter-1 REQUEST_CHANGES (NOVEL P1, faithfulness-critical): the gap-stub
+# fix above sets dropped_due_to_failure=False + non-empty verified_text on a
+# zero-verified section so it RENDERS instead of vanishing. But that exact
+# field shape ALSO satisfies the runner's verified-survivor predicate
+# `filter_verified_sections` (scripts/run_honest_sweep_r3.py:1074-1078:
+# `not dropped_due_to_failure and verified_text`). So a report whose ONLY
+# surviving sections are gap stubs (0 verified sentences) would NO LONGER trip
+# the abort_no_verified_sections invariant — a report of all gap-stubs would
+# ship as a success instead of aborting. That is a faithfulness regression
+# introduced by the C07 render fix.
+#
+# THE FIX IS A TWO-LANE SPLIT. The render-skip predicate
+# (`dropped_due_to_failure or not verified_text` -> skip) and the
+# verified-survivor predicate (`not dropped_due_to_failure and verified_text`)
+# read the SAME two fields with inverse logic, so any SectionResult-field
+# change in THIS lane that drops the stub from the survivor count ALSO drops it
+# from render — re-opening the vanish bug. Distinguishing "renders but is NOT a
+# verified survivor" requires a THIRD signal (is_gap_stub / sentences_verified
+# == 0), and that signal must be consulted INSIDE filter_verified_sections,
+# which lives in run_honest_sweep_r3.py — owned by Lane C, NOT editable here.
+#
+# Lane B ships the SIGNAL (is_gap_stub=True, sentences_verified=0 on the stub —
+# already done above) + this executable CONTRACT. Lane C must add a third
+# clause to filter_verified_sections, recommended surgical form:
+#     and not getattr(sr, "is_gap_stub", False)
+# (targets exactly the new gap-stub construct; zero risk of false-excluding a
+# real section — preferred over `sentences_verified > 0`, which could
+# false-drop a legitimate section that renders prose with a zero count).
+#
+# I-gen-006 (#1178) BB5-C07: the cross-lane fix has LANDED — filter_verified_sections
+# in run_honest_sweep_r3.py now excludes gap-stub-only sections
+# (`and not getattr(sr, "is_gap_stub", False)`), so this contract test passes normally
+# and locks the invariant against silent regression.
+def test_c07_gap_stub_section_is_not_a_verified_survivor():
+    """A section whose ONLY content is a gap stub (0 verified sentences) must NOT
+    count as a verified/surviving section for the abort_no_verified_sections
+    predicate. Otherwise a report of ALL gap-stubs ships as success, bypassing
+    the 'at least one section has verified prose' invariant (CLAUDE.md §9.1 #4)."""
+    from scripts.run_honest_sweep_r3 import filter_verified_sections
+
+    gap_stub = _msg.SectionResult(
+        title="Safety", focus="", ev_ids_assigned=[], raw_draft="", rewritten_draft="",
+        verified_text=_msg._GAP_STUB_SENTENCE, biblio_slice=[],
+        sentences_verified=0, sentences_dropped=5, regen_attempted=True,
+        dropped_due_to_failure=False, is_gap_stub=True,
+    )
+    survivors = filter_verified_sections([gap_stub])
+    assert survivors == [], (
+        "a gap-stub-only section (0 verified sentences) must NOT survive the "
+        "verified-section predicate, or a report of all gap-stubs would ship as "
+        "success instead of abort_no_verified_sections"
+    )
+
+
+def test_c07_real_section_still_survives_alongside_gap_stub():
+    """Companion control (Lane-B-side, NOT xfail): a real verified-prose section
+    in the SAME list must STILL be a survivor regardless of the gap-stub clause —
+    the future Lane-C exclusion must drop ONLY the gap stub, never a real section.
+    Locks against an over-broad Lane-C predicate that would false-drop real prose."""
+    from scripts.run_honest_sweep_r3 import filter_verified_sections
+
+    real = _msg.SectionResult(
+        title="Efficacy", focus="", ev_ids_assigned=["ev_a"], raw_draft="", rewritten_draft="",
+        verified_text="## Efficacy\n\nA verified claim [1].", biblio_slice=[],
+        sentences_verified=3, sentences_dropped=0, regen_attempted=False,
+        dropped_due_to_failure=False, is_gap_stub=False,
+    )
+    gap_stub = _msg.SectionResult(
+        title="Safety", focus="", ev_ids_assigned=[], raw_draft="", rewritten_draft="",
+        verified_text=_msg._GAP_STUB_SENTENCE, biblio_slice=[],
+        sentences_verified=0, sentences_dropped=5, regen_attempted=True,
+        dropped_due_to_failure=False, is_gap_stub=True,
+    )
+    survivors = filter_verified_sections([real, gap_stub])
+    # The real section is a survivor today and after the Lane-C clause lands.
+    assert real in survivors, "a real verified-prose section must always survive the predicate"
+
+
+def test_c07_v30_contract_gap_disclosure_is_not_a_verified_survivor():
+    """Codex iter-3 P1: a V30 contract gap disclosure (sentences_verified==0,
+    is_gap_stub=False) is the SAME 0-verified gap class and must ALSO be excluded
+    from the abort_no_verified_sections survivor predicate via the universal
+    sentences_verified>0 signal — not only the legacy is_gap_stub stub."""
+    from scripts.run_honest_sweep_r3 import filter_verified_sections
+
+    v30_gap = _msg.SectionResult(
+        title="Contraindications", focus="", ev_ids_assigned=[], raw_draft="", rewritten_draft="",
+        verified_text="Contract-bound content did not survive strict verification; "
+        "curator-actionable gap.", biblio_slice=[],
+        sentences_verified=0, sentences_dropped=4, regen_attempted=True,
+        dropped_due_to_failure=False, is_gap_stub=False,
+    )
+    real = _msg.SectionResult(
+        title="Efficacy", focus="", ev_ids_assigned=["ev_a"], raw_draft="", rewritten_draft="",
+        verified_text="## Efficacy\n\nA verified claim [1].", biblio_slice=[],
+        sentences_verified=3, sentences_dropped=0, regen_attempted=False,
+        dropped_due_to_failure=False, is_gap_stub=False,
+    )
+    survivors = filter_verified_sections([v30_gap, real])
+    assert v30_gap not in survivors, "V30 gap disclosure (0 verified) wrongly counts as a survivor"
+    assert real in survivors, "real verified section false-dropped by the universal gap exclusion"
+
+
+def test_c07_key_findings_skips_gap_disclosures():
+    """Codex iter-3 P1: a 0-verified gap disclosure (here a V30-style gap with
+    is_gap_stub=False, sentences_verified=0) must NEVER surface in the verified-only
+    Key Findings block as a 'span-verified statement'; a real verified sentence still does."""
+    import os
+    os.environ["PG_SWEEP_KEY_FINDINGS"] = "1"
+    from src.polaris_graph.generator.key_findings import build_key_findings
+
+    gap = _msg.SectionResult(
+        title="Safety", focus="", ev_ids_assigned=[], raw_draft="", rewritten_draft="",
+        verified_text="No claim survived strict verification; curator-actionable gap.",
+        biblio_slice=[], sentences_verified=0, sentences_dropped=5, regen_attempted=True,
+        dropped_due_to_failure=False, is_gap_stub=False,
+    )
+    real = _msg.SectionResult(
+        title="Efficacy", focus="", ev_ids_assigned=["ev_a"], raw_draft="", rewritten_draft="",
+        verified_text="The trial reported HR 0.82 [1].", biblio_slice=[],
+        sentences_verified=1, sentences_dropped=0, regen_attempted=False,
+        dropped_due_to_failure=False, is_gap_stub=False,
+    )
+    out = build_key_findings([gap, real])
+    assert "curator-actionable gap" not in out, "gap disclosure leaked into Key Findings as span-verified"
+    assert "HR 0.82" in out, "real verified sentence missing from Key Findings"
+
+
+def test_c07_key_findings_skips_uncited_gap_sentence_in_mixed_section():
+    """Codex iter-4 P1: a MIXED V30 section (sentences_verified>0 because it has SOME
+    verified prose, but verified_text LEADS with an uncited gap-disclosure sentence) must
+    surface the first CITED sentence as the Key Finding, never the uncited gap disclosure."""
+    import os
+    os.environ["PG_SWEEP_KEY_FINDINGS"] = "1"
+    from src.polaris_graph.generator.key_findings import build_key_findings
+
+    mixed = _msg.SectionResult(
+        title="Treatment", focus="", ev_ids_assigned=["ev_a"], raw_draft="", rewritten_draft="",
+        verified_text=(
+            "The dosing sub-slot did not survive strict verification; curator-actionable gap. "
+            "The trial reported a hazard ratio of 0.82 [1]."
+        ),
+        biblio_slice=[], sentences_verified=1, sentences_dropped=2, regen_attempted=True,
+        dropped_due_to_failure=False, is_gap_stub=False,
+    )
+    out = build_key_findings([mixed])
+    assert "curator-actionable gap" not in out, "uncited gap sentence leaked into Key Findings"
+    assert "hazard ratio of 0.82" in out, "first cited sentence missing from Key Findings"
+
+
+def test_c07_key_findings_excludes_cited_v30_contract_gap_pointer():
+    """Codex iter-5 P1: the V30 contract-runner gap disclosure's SECOND sentence carries a
+    [N] pointer to the gap-task sidecar (not an evidence span). The citation filter alone
+    lets it through; the gap-marker boilerplate filter must exclude it so a gap pointer never
+    surfaces as a Key Finding, even in a mixed section."""
+    import os
+    os.environ["PG_SWEEP_KEY_FINDINGS"] = "1"
+    from src.polaris_graph.generator.key_findings import build_key_findings
+
+    mixed = _msg.SectionResult(
+        title="Slot A", focus="", ev_ids_assigned=["ev_a"], raw_draft="", rewritten_draft="",
+        verified_text=(
+            "Contract-bound content for this slot did not survive strict verification; "
+            "curator-actionable gap. See manifest.frame_coverage_report and "
+            "human_gap_tasks.json for per-entity detail.[1] "
+            "The trial reported a hazard ratio of 0.82 [2]."
+        ),
+        biblio_slice=[], sentences_verified=1, sentences_dropped=3, regen_attempted=True,
+        dropped_due_to_failure=False, is_gap_stub=False,
+    )
+    out = build_key_findings([mixed])
+    assert "curator-actionable gap" not in out, "gap disclosure sentence leaked into Key Findings"
+    assert "frame_coverage_report" not in out, "gap-task pointer leaked into Key Findings"
+    assert "human_gap_tasks" not in out
+    assert "hazard ratio of 0.82" in out, "real cited finding missing from Key Findings"
----- END DIFF -----
