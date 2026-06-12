# I-perm-022 (#1214) — verifier span normalization: forensic plan (durable record)

Forensic by the parallel Claude agent (2026-06-11), persisted here so it is not lost.

## 1. Root cause (grounded in code + the real drb_76 run)

**The seam:** the cited span enters the four-role second evaluator via
`EvidenceDocument.text`, built in `src/polaris_graph/roles/native_gate_b_inputs.py`:
- `_resolve_evidence` (582-611) builds one `EvidenceDocument(doc_id=evidence_id,
  text=_cited_window_text(text, token))` per token (607-609).
- `_cited_window_text` (547-579) slices a bounded window but applies NO de-hyphenation /
  ligature / NFKD normalization — only `.strip()`.
- That `doc.text` is inlined verbatim as `{span}` into the Sentinel decomposition prompt
  (`sentinel_adapter.py:280-281`) and joined into the Judge `evidence_text`
  (`role_pipeline.py:333`). Both are LLM evaluators that read span TEXT.

A non-VERIFIED four-role verdict → `[confidence:low]` via `confidence_bucket`
(`generator/claim_labeler.py:29-53`), keyed on `is_verified` (four-role `final_verdict ==
"VERIFIED"`). This is the four-role seam, NOT a strict_verify Gemma drop.

**Mirror is NOT the target** — `mirror_adapter.py` binds on `doc_id`
(`_validate_citation_binding` 107-130), never on span text. Only the Sentinel
atom-by-atom span-coverage matcher and the Judge are artifact-sensitive.

## 2. HONEST empirical finding (the load-bearing correction)
From the real run `outputs/audits/I-perm-010/run_drb76_jun11/...`:
- The 58-row evidence pool DOES carry the artifacts: 12 ligature codepoints (U+FB01 `ﬁ`,
  U+FB02 `ﬂ`) + 5 line-break hyphens — ALL concentrated in ONE row `ev_206` (`bioﬁlms`,
  `inﬂammatory`, `dehy-\ndrogenase`, `pro-\nteins`, `oxaliplatin-\ninduced`).
- BUT `ev_206` is cited by exactly ONE claim (`04-000`), whose Sentinel verdict was
  SUPPORTED → ZERO of the 8 Sentinel-unsupported claims were ligature/hyphen-driven in this
  captured run.
- Most of the 8 Sentinel-unsupported claims are GENUINE semantic negatives ("span doesn't
  label the organism a pathogen"; "registry" vs "retrospective records"; "central-line" vs
  "indwelling catheters"). These MUST stay negative.
- ONE IS a real extraction-artifact surface mismatch: claim `05-007` — span "natural kill
  cell activity" vs claim "natural killer cell activity" (dropped "er" from PDF extraction).

**Honest root_cause:** un-normalized PDF-extraction artifacts (ligatures, line-break
hyphenation, truncation/whitespace) in the cited span reach the LLM evaluators verbatim and
can flip a genuinely-supported atom to "unsupported." Real, demonstrated CLASS of FN, but
"drb_76 = 12 FN" is NOT proven artifact-driven. **The fix must recover only true positives
the artifacts hid; it must NOT be tuned to "recover 12" (that would force-pass genuine
negatives).** Per-claim causal proof is the DoD paid §-1.1 smoke.

## 3. Design — normalize the SPAN only, grade the CLAIM as-authored
Artifacts are source-side. The generator's claim prose is clean; normalizing it would grade
a rewritten claim. So:
- SPAN: apply new `_normalize_span_text()` right before `EvidenceDocument(...)` (607-609).
- CLAIM: unchanged into the evaluator.
- Cache key only: normalize both for key identity (does not change what is evaluated).

`_normalize_span_text` — strictly meaning-preserving, ZERO digit modification:
1. Ligatures (the clean win): explicit map `ﬁ→fi ﬂ→fl ﬀ→ff ﬃ→ffi ﬄ→ffl ﬅ→ft ﬆ→st` OR NFKD
   restricted to the ligature range. Reuse `provenance_generator.py:195-238`
   (`_build_normalized_view` already does NFKD + ligature decomposition).
2. Line-break de-hyphenation, ALPHABETIC-ONLY: join `[a-z]-\n[a-z]`. Document the residual
   ambiguity (`oxaliplatin-\ninduced`→`oxaliplatininduced` cosmetically wrong;
   `dehy-\ndrogenase`→`dehydrogenase` right) — `TEXT_DEHYPHENATE` is a PyMuPDF
   extraction-time flag, unavailable at the seam. Restrict to alphabetic so digits untouched.
3. Whitespace: collapse runs, NBSP/zero-width → space.
4. NEVER touch digits or dashes between digits (I-gen-005 range/negative corruption lesson):
   every regex matches alphabetic context only.

Verdict cache (scope-limited under the 200-LOC cap): the in-run dedup at
`sweep_integration.py:283 _dedup_key` already keys on `(claim_text, sorted((doc_id, d.text)),
severity, s0_categories)`. Because we normalize UPSTREAM of `EvidenceDocument`, `d.text` is
already normalized → the existing dedup inherits the normalized `(claim, evidence_id, span)`
identity for free, no new cache code. A PERSISTENT cross-run verdict store is a larger build →
SPLIT to a follow-up issue.

## 4. Faithfulness (the critical argument)
Repair, not rewrite: maps a garbled token to its true form, adds NO content. If the span
genuinely doesn't state the atom (the 8 genuine negatives), the repaired span STILL doesn't
→ stays unsupported. Zero digit modification (testable invariant): `"reduced 2%"` and
`"reduced 20%"` can never collapse. Gate untouched (D8, `_compose_final_verdict` fail-closed,
Mirror doc_id binding, Sentinel UNGROUNDED override, VERIFIED coverage credit all unchanged).
No recovery target — accepts whatever recovers (possibly ≪12).

## 5. Edits (default-OFF flag `PG_GATE_B_SPAN_NORMALIZE`, default "0" → byte-identical)
- `src/polaris_graph/roles/native_gate_b_inputs.py`: add `_GATE_B_SPAN_NORMALIZE_ENV` +
  ligature map; add `_normalize_span_text(text)` (OFF-guarded → returns input unchanged);
  wrap the windowed text at `_resolve_evidence` (607-609):
  `text=_normalize_span_text(_cited_window_text(text, token))`. Records keep FULL
  un-normalized text (entity coverage matching unaffected — matches DOI/PMID/URL).
- Wire `PG_GATE_B_SPAN_NORMALIZE=1` into the Gate-B slate.

## 6. Tests (`tests/polaris_graph/test_span_normalize_iperm022.py`, mirror test_fx03)
- flag-off byte-identical; ligature repaired when on (real `ev_206` strings); line-break
  hyphen joined (alphabetic) + document `oxaliplatin-` residual; recovers a TP the artifact
  hid; **numeric difference does NOT collapse (adversarial: 2% vs 20% keys differ)**; genuine
  negative stays negative (repair adds no content).

## 6b. Honesty caveats
- "12 FN" NOT artifact-confirmed in the captured run; ligatures are the clean win, hyphenation
  best-effort/alphabetic-only/documented; truncation ("natural kill[er]") is NOT fixed by
  ligature/hyphen (needs fuzzy/edit-distance = different, riskier; out of scope). Persistent
  cross-run cache deferred. Paid §-1.1 smoke = the causal per-claim proof.

Key files: `native_gate_b_inputs.py` (547-611), `sentinel_adapter.py:280-281`,
`role_pipeline.py:333`, `mirror_adapter.py` (ruled out), `claim_labeler.py:29-53`,
`sweep_integration.py:283`, `provenance_generator.py:195-238`. Test pattern:
`tests/polaris_graph/test_fx03_gate_b_cited_span_iready017.py`.
