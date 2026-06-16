HARD ITERATION CAP: 5 per document. This is iter 2 of 5 (re-gate confirmation).
- Front-load ALL real findings now. No drip-feeding.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Task: confirm the 4 residual P0s + 1 P1 from your prior re-gate (w82clbwhk) are now CLOSED

This is a STATIC review. DO NOT run pytest or any command. Read the committed diff off disk:
`.codex/iarch007_regate/iter2/residual_fixes.diff` (git commit 201613e2 on branch bot/I-arch-002-no-dumping).
Read the touched source files directly at C:/POLARIS if you need surrounding context.

Your prior re-gate returned REQUEST_CHANGES on all 4 units with EXACTLY these residual P0s (+1 P1).
Verify each is closed, in the STRICTER direction, with NO faithfulness relaxation (no strict_verify /
NLI / 4-role threshold weakened; no un-judged content marked verified; consolidate-keep-all honored).

1. RELEASE P0 #3 — `scripts/run_honest_sweep_r3.py` ~line 10980. Prior defect: the manifest-write
   release-invariant reconstruction did `adjudicated=bool(_rd.get("adjudicated", True)) if _rd else True`,
   defaulting MISSING/malformed release proof to adjudicated=True (fail-OPEN). CONFIRM it now defaults
   to False (fail-CLOSED). Note legit releases serialize release_disclosure["adjudicated"] at ~9889-9904,
   so the new default only bites the missing-proof case (no false-hold on real releases). CONFIRM that.

2. GEN P0 — `src/polaris_graph/generator/fact_dedup.py`. Prior defect: rewrite fallbacks (JSON-fail,
   shape-mismatch, per-item null) returned None per redundant -> DROPPED corroborating cited sentences,
   violating §-1.3 CONSOLIDATE-keep-all. CONFIRM the fallbacks now emit NO drop key (return {} / omit the
   key) so apply_rewrites KEEPS the original corroborating sentence. CONFIRM no corroborator is deleted.

3. FETCH P0 (A17) — `src/polaris_graph/retrieval/contradiction_detector.py`. Prior defect: grouping by
   (subject,predicate,unit,dose) with NO same-source guard, so two numbers from the SAME evidence/source
   could be emitted as a cross-source contradiction. CONFIRM the added same-source guard: when the group
   resolves to < 2 distinct sources (source_url or evidence_id), it is labeled not_comparable, kept OUT of
   the headline count, and every claim DISCLOSED (never dropped). CONFIRM it only suppresses when < 2
   distinct sources (a genuine 2+-source disagreement is never suppressed) — i.e. faithfulness-safe.

4. SWEEP P0 — `scripts/iarch007_release_invariant_check.py` ~line 208+. Prior defect: D8/seam proof was
   demanded only on _STRICT_RELEASE_STATUSES, so partial_saturation + release_allowed=true + empty
   final_verdicts slipped through. CONFIRM the new check (6) demands D8 proof OR proven seam rescue on
   EVERY non-abort release that is neither strict nor disclosed (partial_*/unknown included), while leaving
   the disclosed family to checks (2)/(3) and abort to check (4) — no double-flag, no relaxation.

5. SWEEP P1 — `tests/polaris_graph/test_iarch007_regression.py`. Prior defect: two A4 tests asserted
   source-TEXT presence (grepped .py files), a §-1.1-banned string-presence check. CONFIRM both are now
   behavioral: one calls the real pure helper `build_attempted_zero_emit_section_stub` (extracted in
   run_honest_sweep_r3.py) and asserts the dict; the other calls the real resolver
   `resolve_provenance_to_citations_with_count([], {})` and asserts emitted_count==0 (the is_gap_stub
   trigger). CONFIRM no remaining source-text-grep proxy in the A4 block.

Also sanity-check the test fixture changes are faithful (NOT a quality dodge): the contradiction `_ev`
helpers now default source_url distinct-per-evidence_id (real cross-source) instead of one shared
placeholder; the fact_dedup drop-on-failure tests were rewritten to assert keep-all. These align tests to
the corrected behavior; flag if any masks a real defect.

Output ONLY this schema as the LAST lines (machine-parsed on the final `verdict:` line):

```yaml
verdict: APPROVE | REQUEST_CHANGES
release_p0_closed: yes | no
gen_p0_closed: yes | no
fetch_p0_closed: yes | no
sweep_p0_closed: yes | no
sweep_p1_closed: yes | no
faithfulness_relaxation_found: yes | no
novel_p0: [...]
p1: [...]
convergence_call: continue | accept_remaining
```
