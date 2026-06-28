HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd on remaining-non-P0/P1; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

REVIEW MODE: STATIC only. Do NOT run pytest / pipeline / broad exploration. Read the diff `.codex/I-wire-017/iwire017_diff.patch` and the changed sources (key_findings.py, weighted_enrichment.py, verified_compose.py) + the test. Emit the verdict schema at the end.

# I-wire-017 (#1339) — render-seam/composer truncation + orphan-citation fix (4 withhold-only fixes)

## Problem (confirmed on the #1338 paid back-half run, 23k-word report)
The render-seam screen fired but the body still leaked: mid-word truncation fragments ("...over the recent past.[1] At t.", "er concept...advancing other technolo."), orphaned-citation-only sections ("### Comparative Assessment" body = just [6][7][5]), and the phase7 [quantified] silent-no-op. Full root cause: .codex/I-wire-017/iwire017_investigation.md.

## The 4 changes (the ONLY diff — all WITHHOLD-ONLY; faithfulness engine UNCHANGED)
- **FIX A (key_findings.py `_boundary_token_is_span_cut`)**: the truncation leg missed SINGLE-LETTER mid-word cuts ("At t.[2]", "restricted to s.[89]") because the bare letter "t"/"s" is itself a known corpus token, so `if t in known_words: return False` fired before the len==1 completion gate. Fix adds a len==1 branch BEFORE that early-out that flags a cut ONLY when: mode=='end' AND `token[:1].islower()` (ORIGINAL case) AND token not in {"a","i"} AND `completes` (a longer known corpus word starts with it). **PRECISION (this is §-1.1-lethal — verify hard):** the lowercase gate means a single-CAPITAL-letter label finding — "vitamin C [5]", "hepatitis B [8]", "grade B [12]" — is NOT flagged (uppercase boundary token skips the new branch and falls through to the unchanged logic). Confirm there is NO legitimate finding that ends in a *lowercase* single letter (other than a/i) immediately before a [N] that would be wrongly withheld.
- **FIX B (weighted_enrichment.py `_sanitize_report_line`)**: when a prose segment is dropped as chrome, its trailing continuation markers ([7][5] after the dropped [6]) were left orphaned. Fix drops the contiguous marker-only segments that follow a dropped prose segment; a marker run after a KEPT segment stays.
- **FIX C1 (weighted_enrichment.py `sanitize_rendered_report`)**: after sanitizing, a non-scaffolding section header (level>=3, `_MIN_DROPPABLE_EMPTY_HEADER_LEVEL`) whose body reduced to no claim-bearing prose (blank/bare-markers) is dropped. Scaffolding is protected by own-title OR immediate-parent-scaffolding (NOT any-ancestor — because the H1 "# Research report:" echo is itself scaffolding, an any-ancestor rule would protect the whole report). Confirm a real section is never dropped and a scaffolding subsection (e.g. a refs list under ## Bibliography) survives.
- **FIX R1 (verified_compose.py `_compose_junk_screen` / `build_verified_span_draft`)**: the K-span fallback screened spans via the predicate WITHOUT known_words and WITHOUT require_sentence_form, so the truncation + subjectless legs were inert on this PRODUCER path (the actual source of the leaks). Fix builds known_words once from the run evidence_pool and passes it + require_sentence_form=True. A TypeError fallback to the positional single-arg call preserves the other callers (access_bypass/no-op screens). `_known_words_for_compose` is lazy + fail-conservative (returns None on any failure -> truncation leg simply skipped, never a wrong drop).

NOT in scope: C2 (the Phase-7 quantified spec rejection in tradeoff_modeler.py / quantified_analysis.py) — a separate composer-producer issue; the section legitimately produced nothing (correct fail-closed), and C1 handles the empty-render.

## Validation (offline; I ran it — you do NOT need to)
- New tests (tests/polaris_graph/test_iwire017_truncation_orphan.py): 10 pass — fix-A recall ("At t.[2]"/"restricted to s.[89]" flagged), fix-A precision ("vitamin C [5]"/"hepatitis B [8]"/"grade B [12]" KEPT), fix-A fires through is_render_chrome_or_unrenderable, fix-B orphan removal, fix-C1 empty-section drop + scaffolding-keep, fix-R1 K-span screen.
- Regression: render-seam suites 19 pass; iarch007 + release-invariant 53 pass. All 3 modules py_compile.

## Things to verify (be adversarial — precision is the §-1.1 line)
1. FIX A: can ANY legitimate finding be wrongly withheld? Walk the lowercase+completes+{a,i}+mode==end gate. Especially: lowercase single-letter ending before a [N] that is a real word fragment vs a real one-letter token.
2. FIX C1: can a REAL content section ever be dropped (e.g. a section whose only prose is short but real)? Confirm the "no claim-bearing prose after sanitize" test is correct and the scaffolding protection (own + immediate-parent) is sound.
3. FIX B: does dropping the trailing marker run ever remove markers belonging to a KEPT following segment? Confirm "contiguous marker-only AFTER a dropped prose segment" only.
4. FIX R1: the TypeError fallback + fail-conservative None — confirm it never produces a WRONG drop, only a skip.
5. Confirm every change is withhold-only (suppress from rendered rollup; source stays in evidence) — NO strict_verify/NLI/4-role/span/provenance change. LAW VI named constants.

## Output schema (REQUIRED, last lines)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
