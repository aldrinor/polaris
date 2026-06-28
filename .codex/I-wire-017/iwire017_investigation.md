# I-wire-017 (#1339) — truncation/orphan investigation (recovered after stream timeout)

Scope: render-seam / composer-WITHHOLD only. Faithfulness engine UNCHANGED. All fixes withhold-only.

## A — truncation leg misses SINGLE-LETTER mid-word cuts
`_boundary_token_is_span_cut` (src/polaris_graph/generator/key_findings.py:149), guard at 161-162:
`t = token.lower(); if t in known_words: return False`.
For "At t.[2]" / "...restricted to s.[89]" the boundary token is the single letter "t"/"s", which OCCURS as a
standalone token in the corpus (footnote/stat markers) → in known_words → returns False (not a cut). The
completion gate (167-173) is never reached. Multi-letter cuts ("er concept", "technolo") ARE caught.
FIX A: special-case len-1 boundary tokens BEFORE the `t in known_words` early-out — a single-letter boundary
token immediately before a `[N]` marker (mode=end, ends_before_marker=True), NOT in {"a","i"}, that `completes`
(a longer corpus word starts with it) is a span cut even if the bare letter is a known token. Keep the
`completes` requirement so "grade B"/"type 2 … a" survive. Truncation leg only.
(Subjectless "a chatbot developed by OpenAI." is a COMPLETE sentence — only the require_sentence_form lowercase-
start leg catches it; enabling that seam-wide is over-strip-unsafe → leave to canary, out of scope for A.)

## B — withheld unit orphans adjacent continuation markers ([6][7][5])
`_sanitize_report_line` (src/polaris_graph/generator/weighted_enrichment.py:1303). `_CITATION_SPLIT_RE` (1222)
splits "prose[6][7][5]" → segments ("prose","[6]"),("","[7]"),("","[5]"). Line 1320 skip only fires when BOTH
text and marker empty; marker-only segments fall through to 1333 `kept.append(seg_text+seg_marker)`. So when the
prose seg drops as chrome, [7][5] survive orphaned.
FIX B: when a prose segment is dropped as chrome, also drop the contiguous marker-only segments that follow it
(same dropped claim's continuation run). ~5 lines, withhold-only.

## C1 — section renders as orphaned-marker body / empty header
Section prose all chrome → dropped; continuation markers orphan (B bug); sanitize_rendered_report (1343/1377)
keeps the line because clean_line.strip() is truthy (markers non-whitespace). `### Comparative Assessment` body
collapses to "[6][7][5]" and the content-empty ### header stays.
FIX C1: (a) the B fix reduces the line to empty → dropped at 1377; (b) ADD a post-pass in sanitize_rendered_report
to drop a NON-scaffolding `###` header whose body, after sanitization, has no claim-bearing prose (blank/bare-marker
only). Withhold-only.

## C2 — phase7 [quantified] SILENT NO-OP — SEPARATE, NOT render-seam (out of scope for #1339)
quantified_analysis.py:477 firing_status=spec_validation_rejected; spec rejected by build_quantified_spec
(tradeoff_modeler.py ~720), reason input_both_modeled_and_sourced:productivity_gain. The section produced no prose
because the spec was fail-closed-rejected (CORRECT faithfulness behavior, not fabrication). This is I-wire-014
#1336 / I-fix-001 / tradeoff_modeler territory — a separate composer-PRODUCER fix. #1339 render-seam only ensures
the empty quantified section doesn't render as orphaned-marker/empty-header (C1 covers that). Leave C2 as a
separate follow-up issue (disclosed, not a bug).

## R1 (recommended IN-SCOPE) — K-span fallback BYPASSES the chrome screen (the producer of the leaks)
`build_verified_span_draft` (src/polaris_graph/generator/verified_compose.py:303) emits raw verbatim spans when
the abstractive writer skips/fails a basket; it screens each unit with `_compose_junk_screen` (277) → calls
`is_render_chrome_or_unrenderable` WITHOUT known_words AND WITHOUT require_sentence_form (_make_junk_screen, 289).
So the truncation leg + subjectless leg are inert on this PRODUCER path — the render-seam is only the net.
FIX R1: in build_verified_span_draft / _compose_junk_screen, build known_words once from the run evidence_pool and
pass it (+ require_sentence_form=True — safe here since K-span units are whole lifted source sentences, unlike the
render-seam's mid-clause [N] segments). Highest-leverage; closes the reconfirm3 "R1" audit finding. Withhold-only.

## Files ALSO checked, clean
abstractive_writer.py (§3.1 input screen correct; comment over-claims K-span screens with known_words — it does not),
multi_section_generator.py (_remap_section_markers_to_global faithful), quantified_analysis.py (telemetry honest),
tradeoff_modeler.py (C2 surface, separate), run_honest_sweep_r3.py:12322-12337 (seam wiring correct; gap is in the
predicate A + splitter B), _screen_rollup_finding_units (12260-12281, rollup-only).

## Tests
tests/polaris_graph/test_i_wire_013_render_seam_iter3a.py (A/B/C1 home), test_i_wire_013_iter3b_quant_gatep1.py +
iter3b2 ([N]-split coverage), scripts/iwire013_sec11_forensic_audit.py + scripts/iwire016_acceptance_test.py
(precision/recall yardsticks).

## Fix summary (3 files, withhold-only): A=key_findings.py:149; B+C1=weighted_enrichment.py:1303/1343;
## R1=verified_compose.py:277/303. C2=tradeoff_modeler.py (SEPARATE issue).
