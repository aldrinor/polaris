# Codex — adversarial review of my proposed verifier fix (NOT for approval)

## Operator instruction to me (verbatim 2026-05-25 night)

> "Did Codex also run a very deep investigation? What is the finding from
> Codex?"

Honest answer: NO, your prior consultation (`.codex/I-gen-005/codex_root_cause_verdict_iter1.txt`)
evaluated MY pre-set hypothesis ("V4 Pro hallucinates") and approved
ship-as-is. **You were wrong.** Subsequent local investigation found
the failure mode was actually in our verifier, not in V4 Pro. The
"fabrications" are mostly the verifier rejecting grounded sentences
due to (a) unicode-minus mismatch and (b) span-narrowness false
positives.

This brief gives you the empirical evidence (NOT a pre-set hypothesis)
and asks you to:
1. Verify whether my new diagnosis is correct
2. Find holes in my fix
3. Predict additional verifier bugs of similar nature I haven't yet found

## Iteration cap directive (verbatim §8.3.1)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE; do not bank for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Empirical evidence (read these files directly)

You have local file access. **Open and read these. Don't trust my summary.**

1. **`outputs/honest_sweep_r3/clinical/clinical_tirzepatide_t2dm/reasoning_trace.jsonl`** —
   V4 Pro's literal thinking per LLM call. Specifically read entry 12
   (Efficacy regen, 26774 chars) where V4 Pro reasons through which
   evidence to cite for SURPASS-2 through SURPASS-6 stats.

2. **`outputs/v4_reasoning_traces/efficacy_regen.txt`** — same trace,
   extracted to file. Read at least the first 5000 chars to see V4 Pro
   correctly identifying that ev_017 contains "SURPASS-3: HbA1c -1.93%
   to -2.37% vs -1.34% (insulin degludec)" — these are REAL numbers
   from ev_017's table.

3. **`outputs/honest_sweep_r3/clinical/clinical_tirzepatide_t2dm/verification_details.json`** —
   per-sentence drop reasons + byte tokens. Look at any sentence with
   `number_not_in_any_cited_span` and inspect the cited `tokens[].start`
   and `tokens[].end` values.

4. **`outputs/honest_sweep_r3/clinical/clinical_tirzepatide_t2dm/evidence_pool.json`** —
   the actual evidence text. Confirm that the numbers V4 Pro wrote ARE
   present in the cited evidence document (but at different byte offsets
   than V4 Pro's narrow span).

## Local empirical proof of the unicode-minus bug

```python
# Run this yourself if you want to verify:
import json
ev = {e['evidence_id']: e for e in json.load(open(
    'outputs/honest_sweep_r3/clinical/clinical_tirzepatide_t2dm/evidence_pool.json'
))}
dq = ev['ev_001'].get('direct_quote', '')
for n in ['1.07', '1.44', '0.56', '11.36', '4.62']:
    idx = dq.find(n)
    prev = dq[idx-1] if idx > 0 else ''
    print(f'  {n!r}: prev-char={prev!r} (U+{ord(prev):04X})')
```

Result on my machine:
```
  '1.07':  prev-char='-' (U+002D)
  '1.44':  prev-char='−' (U+2212)
  '0.56':  prev-char='−' (U+2212)
  '11.36': prev-char='−' (U+2212)
  '4.62':  prev-char='−' (U+2212)
```

The evidence text mixes ASCII minus (U+002D) and unicode minus (U+2212).
The regex `-?\d+\.\d+` in `provenance_generator.py:397` only matches
U+002D. So `_decimals_in("−1.44")` returns `{'1.44'}` (without the
minus, because U+2212 isn't in the character class).

When V4 Pro writes `-1.44` (ASCII) and the evidence has `−1.44`
(unicode), set comparison sees `{'-1.44'}` vs `{'1.44'}` — set
difference says `'-1.44'` is missing. False fabrication report.

## Local empirical proof of the span-narrowness bug

```python
import json
d = json.load(open('outputs/honest_sweep_r3/clinical/clinical_tirzepatide_t2dm/verification_details.json'))
ev = {e['evidence_id']: e for e in json.load(open(
    'outputs/honest_sweep_r3/clinical/clinical_tirzepatide_t2dm/evidence_pool.json'
))}
for sec in d['sections']:
    for drop in sec['dropped']:
        if any('number_not_in_any_cited_span' in r for r in drop.get('failure_reasons', [])):
            tok = drop['tokens'][0]
            eid, start, end = tok['evidence_id'], tok['start'], tok['end']
            dq = ev[eid].get('direct_quote', '')
            span = dq[start:end]
            print(f'[#ev:{eid}:{start}-{end}] span={len(span)}/{len(dq)} chars')
            for r in drop['failure_reasons']:
                if 'missing=' in r:
                    missing = eval(r.split('missing=')[1])
                    for n in missing:
                        bare = n.lstrip('-−')
                        print(f'  {n!r}  in_span={bare in span}  in_full={bare in dq}')
            break
    break
```

Result on my machine:
```
[#ev:ev_001:0-500] span=500/7395 chars
  '0.56'   in_span=False  in_full=True
  '1.07'   in_span=False  in_full=True
  '1.44'   in_span=False  in_full=True
  '11.36'  in_span=False  in_full=True
  '4.62'   in_span=False  in_full=True
```

V4 Pro cited 500-char span of a 7395-char document. The numbers it
wrote are at offset 500+ in that same document. **V4 Pro is grounded;
the verifier was rejecting valid citations because the byte range was
too narrow.**

## My proposed fix (just landed locally; smoke running)

`src/polaris_graph/generator/provenance_generator.py` edits:

1. Added `_normalize_unicode_minus()` that maps U+2212/U+2013/U+2014/U+2012
   → ASCII '-'. Called inside `_numbers_in` + `_decimals_in` before regex.

2. In `verify_sentence_provenance`, when number-in-narrow-span fails,
   fall back to checking number-in-full-direct_quote of the same
   cited evidence_id. If found in full → log
   `span_imprecise_but_grounded` warning, **pass the sentence** (don't
   add to `failures`).

3. Same span-narrow fallback for the entailment judge: when narrow-span
   judge returns NEUTRAL/CONTRADICTED, re-judge with full evidence
   text. If full-evidence verdict is OK → log + pass.

4. **Trial-name check stays STRICT** (intentionally). Prior history
   (`_trial_names_in_evidence` docstring at line 579) explicitly
   rejected full-evidence trial-name scanning because review papers
   cite OTHER trials as context, which would enable true
   wrong-citation fabrications. Keep that.

## Questions for you (Codex)

Don't rubber-stamp this. Find holes:

1. **Is my unicode-minus list complete?** I covered U+2212, U+2013,
   U+2014, U+2012. Are there other dash codepoints in PubMed/PMC HTML
   evidence text that I missed? Hyphen-minus variants? Hebrew/Arabic
   dashes if multilingual? Specifically search the evidence_pool.json
   for non-ASCII characters near numbers.

2. **Is the span-narrow fallback safe?** Could it ENABLE fabrication?
   Example to consider: V4 Pro writes "tirzepatide reduces cancer 50%
   [#ev:ev_X:0-100]" — the 100-char abstract doesn't mention 50% or
   cancer, but the full document somewhere has "50% of patients had no
   cancer in their family history." Fallback might accept this. Walk
   the failure case and tell me if the fix is too permissive.

3. **Are there OTHER verifier bugs in the same code path?** Look at
   `_strip_dose_patterns`, `_PLACEBO_COMPARATOR_RE`, `_THRESHOLD_RE`
   — could those have the same unicode-mismatch problem? Could the
   `_content_words` overlap check have similar narrow-span bias?

4. **My unit test passed on ONE sentence.** Predict at least 3
   additional sentences in `verification_details.json` that should
   ALSO now pass with the fix but might still fail for unrelated
   reasons.

5. **The trial-name check stays strict — is that right?** I followed
   the DR-pass-7 (2026-04-20) reasoning that scanning full evidence
   for trial names enables fabrication. But: 24 of 73 drops in the
   smoke are trial_name_mismatch. Some of those V4 Pro sentences ARE
   correctly attributing review-paper-cited-trial-numbers but failing
   because the review's `statement+title` doesn't authoritatively name
   those trials. Is there a middle ground (e.g., allow trial name if
   evidence has BOTH the trial name in direct_quote AND matching
   numbers in direct_quote)?

6. **What other empirical investigations should I have done before
   shipping this fix?** Beyond the smoke I'm running now.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
diagnosis_correct: TRUE | FALSE | PARTIAL
  with_evidence: |
    (cite which local file/lines you read to verify)
holes_in_fix:
  - p0_or_p1_finding: |
      (specific bug or risk; quote code if applicable)
predicted_residual_failures: |
  (3+ sentences from the existing smoke that should now pass per the
  fix logic but might still fail; be specific)
other_verifier_bugs_to_investigate:
  - (location + nature of bug)
trial_name_middle_ground_proposal: ACCEPT | REJECT | REFINE
  rationale: |
    (your reasoning)
additional_investigations_i_should_have_done: [...]
convergence_call: continue | accept_remaining
```

EMIT YAML ONLY. Don't drip-feed. The operator's standing complaint is
that you echoed my last bad framing; this round, push back hard.
