RULE NOW — emit the YAML verdict block FIRST. APPROVE this CONCRETE plan or REQUEST_CHANGES with specifics. Read AT MOST the cited regions. NO SPEND / NO NETWORK / NO LLM in the new screens.

HARD ITERATION CAP: 5. Iter 1 of 5. Front-load ALL findings; reserve P0/P1 for real execution risks.

## Output schema (emit FIRST)
```yaml
verdict: APPROVE | REQUEST_CHANGES
p0: [...]
p1: [...]
p2: [...]
required_changes: [...]
convergence_call: accept_remaining
```

# Codex brief-gate (iter 1) — PR3 analyst-synthesis safety hardening (#953 q1d-c, CLINICAL-SAFETY). NO SPEND / NO NETWORK.

Codex-verified S1 (#950): the Analyst Synthesis layer is ~70% of the SHIPPED `report.md` and is (a) built
from RAW `<<<evidence>>>` blocks with NO `sanitize_evidence_text` (Invariant §9.1.7 delimiter-sanitization
BYPASS — evidence can forge a closing/opening delimiter), and (b) unverified with only `[#ev]`/`[N]`
syntactic scrubs — NO entailment / NO qualitative-negation screen, so the lethal fabrication class already
caught on a real smoke ("did not lead to discontinuation" contradicting 0.2-0.4% evidence) can ship into a
clinical report under an "evidence-grounded" disclosure. Codex flagged this to PROMOTE EARLY.

## GROUNDED FACTS (do not re-explore)
- `src/polaris_graph/generator/analyst_synthesis.py:285-301` `_format_evidence_pool_for_prompt`: builds
  `f"<<<evidence:{ev_id}>>>\n{quote}\n<<<end>>>"` from `row.direct_quote or row.statement` truncated to
  1200 — NO sanitize (grep `sanitize` in file = 0).
- Output assembly `:377-383`: `cleaned = _scrub_ev_tokens(text)` then `_scrub_invalid_n_markers(...)` —
  PURELY SYNTACTIC. No content/negation/entailment screen. Returned + appended to report at
  `run_honest_sweep_r3.py:2637-2644`.
- The VERIFIED multi_section path sanitizes: `multi_section_generator.py:877-885 wrap_evidence_for_prompt`
  → `provenance_generator.py:241 sanitize_evidence_text(text) -> (clean_text, redaction_count)` (redacts
  injection directives AND the `<<<evidence:...>>>`/`<<<end>>>` delimiter literals + NFKD/invisible/
  homoglyph evasions — Invariant §9.1.7). analyst_synthesis does NOT call it.
- Memory `feedback_qualitative_negation_escapes_regex_2026_05_26`: pure regex catches the NEGATION
  PATTERN but cannot verify grounding without an LLM. For the UNVERIFIED analyst layer, the safe
  no-network move is to DROP an unverified qualitative-negation SAFETY claim (fail-closed), not assert it.

## CONCRETE PROPOSAL (APPROVE or correct)
A. **Sanitize evidence (closes the §9.1.7 bypass).** In `_format_evidence_pool_for_prompt`, route `quote`
   through `sanitize_evidence_text(quote)[0]` BEFORE the 1200-char truncation + block build (import from
   provenance_generator). Accumulate the redaction counts into telemetry. Now the analyst layer's evidence
   passes the SAME delimiter/injection sanitization as the verified path.
B. **No-network qualitative-negation safety screen on the synthesis OUTPUT (fail-closed DROP).** New pure
   `_screen_qualitative_negations(text) -> tuple[str, int]`: sentence-split the synthesis; DROP any
   sentence matching a NEGATION cue (`did not|does not|do not|didn't|doesn't|no |never|without|absent|
   not associated|no evidence|did not lead|no increase|no difference|not increase|not cause|not result`)
   AND a SAFETY/clinical-consequence term (`discontinuation|adverse|contraindicat|interaction|mortality|
   death|serious|hospitali|withdrawal|toxicit|side effect|harm|warning|black box|pregnan`). Rejoin the
   survivors. Run AFTER the existing scrubs, BEFORE return. Record `synthesis_negation_dropped_count` in
   telemetry + a distinct WARNING log when >0. Targets EXACTLY the lethal class; a false positive only
   removes an UNVERIFIED sentence (the span-verified core + the rest of the synthesis remain).
C. **Operator kill-switch (Codex's "or default-off" fallback).** Flag `PG_SWEEP_ANALYST_SYNTHESIS` (default
   "1"). When "0", `generate_analyst_synthesis` returns "" (layer omitted) — so the operator can ship the
   span-verified core ONLY if desired. (Confirm the call site at run_honest_sweep_r3.py honors an empty
   return — it already omits an empty synthesis per `:373-375` "empty response — section omitted".)
D. **Tests (offline, socket blocked):** (1) evidence with a forged `<<<end>>>`/`<<<evidence:>>>` delimiter
   or an injection directive is sanitized in the prompt blocks; (2) a synthesis sentence "tirzepatide did
   not lead to treatment discontinuation" is DROPPED; (3) a benign synthesis sentence (no negation+safety)
   is KEPT; (4) a positive safety statement ("discontinuation occurred in 0.3%") is KEPT (no negation cue);
   (5) `PG_SWEEP_ANALYST_SYNTHESIS=0` → empty synthesis; (6) telemetry counts populated; (7) determinism.

## Constraints / frozen
- NO SPEND / NO NETWORK / NO LLM in the new screens (pure string ops + the existing pure
  `sanitize_evidence_text`). snake_case; explicit imports; no except:pass; ≤200 LOC. Untouched:
  strict_verify / provenance_generator's verify path / D8 / runtime lock / the 5 PR-10 contracts / the
  VERIFIED multi_section core. This only HARDENS the unverified layer (sanitize + drop-dangerous), never
  loosens anything.

## The real risks to rule on
1. Is DROP the right action for an unverified qualitative-negation safety claim, vs flag-with-disclaimer?
   (Claim: DROP — fail-closed; the unverified layer must not assert the lethal negation class. Confirm.)
2. Over-drop risk: could the negation+safety pattern gut legitimate synthesis (e.g. "no serious adverse
   events were reported" — a real evidence-backed finding)? Since the layer is UNVERIFIED, dropping such a
   sentence is the SAFE direction (the verified core keeps the real finding). Confirm, or propose a tighter
   pattern.
3. Sentence-splitting robustness: abbreviations/decimals (e.g. "0.3%.") must not shred sentences — reuse a
   conservative splitter (or the existing one if present). Propose the splitter.
4. Does `sanitize_evidence_text` change the evidence enough to break the LLM's ability to cite (it only
   redacts injection/delimiters, not content)? Confirm it's content-preserving for legitimate evidence.

APPROVE iff this sanitizes the analyst evidence (closing §9.1.7), drops the unverified qualitative-negation
safety class fail-closed, adds the operator kill-switch, is pure/no-spend, leaves the verified core + D8
untouched, and is test-proven.
