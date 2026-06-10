# I-complete-003 (#1189) — provenance re-anchor CLAIMS LEDGER

Source file: `src/polaris_graph/generator/provenance_generator.py` (1968 lines, read in full).

## (1) drop_site
- The per-sentence DROP happens in `strict_verify` at **L1841-1850** (findings loop): `verify_sentence_provenance(...)` returns `v`; `if v.is_verified: kept.append(v) else: dropped.append(v)` — L1847-1850. This is the OUTER drop.
- The DROP DECISION (is_verified True/False) is computed INSIDE `verify_sentence_provenance` at **L1647** `is_verified = len(failures) == 0`, returned L1648-1655.
- Real re-anchor insertion point is BEFORE that verdict crystallizes: the numeric/content/trial/entailment checks append to `failures` across **L1300-1616**. The cited-span failure modes a re-anchor must rescue are:
  - `number_not_in_any_cited_span` (L1334), `no_integer_overlap_any_cited_span` (L1350/1361)
  - `no_content_word_overlap_any_cited_span` (L1429)
  - `trial_name_mismatch` (L1453), `entailment_failed` (L1593/1613)
- Cleanest BEFORE-the-drop hook: after the full check block completes and `failures` is populated for a single cited token's span, BUT BEFORE L1647. Re-anchor enumerates alternative spans within the SAME cited row and re-runs `verify_sentence_provenance` per-candidate; first candidate yielding `is_verified=True` re-binds the token; else fall through to existing L1647 drop.

## (2) verify_fns — what "passes verify" is
Single entry point: **`verify_sentence_provenance(sentence, evidence_pool, *, require_number_match=True, quantified_models=None) -> SentenceVerification`** (L1164). is_verified == (failures empty). The acceptance test the re-anchor MUST REUSE = call this same function on the candidate-rebound sentence. Its internal gates:
- **Content-word overlap**: `_content_words(text)` (L883, alpha tokens >=3 chars minus `_STOPWORDS_FOR_GROUNDING`). Floor = `MIN_CONTENT_WORD_OVERLAP = int(os.getenv("PG_PROVENANCE_MIN_CONTENT_OVERLAP","2"))` (L900-902). Check at L1373-1432: `overlap = sentence_content & span_content; if len(overlap) < MIN_CONTENT_WORD_OVERLAP -> fail` (over aggregated cited-span text, L1374).
- **Numeric span-scoped match**: `_decimals_in(text)` (L688, regex `-?\d+\.\d+`), `_numbers_in(text)` (L683, `-?\d+(?:\.\d+)?` superset), `_INTEGER_PERCENT_RE` (L477). Span aggregate built from `direct_quote[tok.start:tok.end]` (L1271-1274, 1313-1319). Gate L1331-1364: every sentence decimal AND every %-expressed standalone integer (and, in the no-decimal branch, every standalone integer) must appear in a cited span. Helpers strip dose/placebo/threshold (`_strip_dose_patterns` L549, `_PLACEBO_COMPARATOR_RE` L492, `_THRESHOLD_RE` L504). NOTE: FIX-A3 REMOVED the old whole-direct_quote local-window numeric rescue (L1327-1330 comment) — a number must be IN the cited span.
- **NLI entailment gate** (6th check, L1471-1616), gated by `PG_STRICT_VERIFY_ENTAILMENT` via `_entailment_mode()` (`src/polaris_graph/clinical_generator/strict_verify.py:176`, values off/warn/enforce, default enforce). Judge: `_get_judge().judge(sentence_clean, combined_span) -> (verdict, reason)` from `src/polaris_graph/llm/entailment_judge.py:142,324`; verdict in {ENTAILED, NEUTRAL, CONTRADICTED}, fails OPEN as `("ENTAILED","judge_error: ...")`. On NEUTRAL/CONTRADICTED it re-judges against a BOUNDED local window (`_find_local_support_window` L693 / `_find_local_content_window` L816, window=400). enforce-mode appends `entailment_failed` (L1593/1613). judge_error sentinel → fail-closed at L1633-1645 keyed on entailment mode.
- **Trial-name gate** (M-25a, L1434-1457): `extract_trial_names` (L954), `_trial_names_for_cited_row` (L1007, title-authority then cited-span fallback under `PG_VERIFY_TRIAL_NAME_SPAN_FALLBACK` default ON).
- Also: `no_provenance_token` (L1231-1238), `evidence_not_in_pool` (L1257), `span_out_of_bounds` (L1260-1263), `span_invalid` (L1265-1268), `empty_or_contentless_sentence` (BUG-03 floor, L1284-1298).

## (3) row_model — row + full text + token→offset
- Token grammar: `[#ev:<evidence_id>:<start>-<end>]`, regex `_PROVENANCE_TOKEN_RE` (L343-345); parsed by `parse_provenance_tokens` (L444) into `ProvenanceToken(evidence_id, start, end, raw)` (L406-415).
- Row text resolution: `direct_quote = ev.get("direct_quote") or ev.get("statement") or ""` (L1259, also L1317). The span text = `direct_quote[tok.start:tok.end]` (L1271). So a candidate span for re-anchor = any `(s,e)` substring of the SAME row's `direct_quote`, and a re-bound token = `[#ev:<same evidence_id>:<s>-<e>]`.
- gap-#18 full-row rescue window: confirmed at **L1401-1428** (content-floor branch) and L1538-1568/L1581-1604 (entailment branch). It does NOT re-bind the token — it only proposes a bounded <=400-char window and defers to the entailment bind. It is gated by `_verification_mode()` == "enforce" AND `_entailment_mode()` == "enforce". So gap-#18 is a PASS/FAIL rescue, NOT a span re-anchor; I-complete-003 re-anchor is the missing complement (re-bind the token to a new in-row span).
- `PG_VERIFICATION_MODE`: `_verification_mode()` at **L905-918**, reads env, default "off", values off/shadow/enforce (off byte-identical pre-0b). Confirmed L917.

## (4) insertion_plan
When `verify_sentence_provenance` would DROP a sentence whose failures are span-localized (number_not_in_any_cited_span / no_content_word_overlap / trial_name_mismatch / entailment_failed) and the row IS in pool with valid bounds:
1. For each cited `ProvenanceToken`, take its `evidence_id`'s `direct_quote` (the SAME row, no cross-row, no whole-doc).
2. Generate a BOUNDED set of candidate spans within that row by tokenizing the row text into sentences/sliding windows (bounded count — e.g. window=400 sliding/sentence boundaries, cap N candidates to keep enumeration bounded, mirroring `_find_local_support_window` discipline).
3. For each candidate `(s,e)`: rebuild the sentence with the token rewritten to `[#ev:<evidence_id>:<s>-<e>]` and re-run the SAME acceptance test — `verify_sentence_provenance(rebound_sentence, evidence_pool, require_number_match=..., quantified_models=...)`. REUSE, do not reimplement the checks.
4. First candidate returning `is_verified=True` → re-bind the token (keep the new span), keep the sentence.
5. No candidate passes → fall through to the EXISTING drop (L1847-1850 / L1647). Faithfulness-only-tightening: a re-anchor can only ever move a token to a span that PASSES the full strict_verify, so it cannot launder an out-of-span/unsupported claim.

Default-OFF flag recommended (e.g. PG_PROVENANCE_REANCHOR) so off-mode is byte-identical, matching the gap-#18 / PG_VERIFICATION_MODE precedent.
