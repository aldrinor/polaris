You are auditing M-41 BUNDLE pass-2. Pass-1 verdict: BLOCKED (2
blockers + 4 mediums). Pass-2 addresses both blockers + 2 of the 4
mediums; narrow scope.

## Pass-1 Codex findings recap

Blockers (both addressed in pass-2):
1. **M-41a retry prompt / OUTPUT FORMAT** still pinned to 5
   sections in three places, contradicting the new 6-section rule.
2. **M-41c retry selection** compared pre-filter strict_verify
   totals, so a retry with many under-framed trial-name claims
   could win over a first pass with fewer but properly-framed
   claims → net fewer final sentences.

Mediums:
- M1 (addressed): M-41c trial-name regex matches standards codes
  (ISO-9001, IEC-62109).
- M3 (addressed): M-41d substring `h in url` matching too loose —
  `not-fda.gov.example` path classified as FDA.
- M2 (deferred): frame-element pattern permissiveness — acceptable
  per pass-1 note "acceptable as deterministic smoke guard".
- M4 (deferred): dash-placeholder coverage — threshold 2/7
  acceptable per pass-1 note "defensible".

## Pass-2 changes

1. **M-41a prompt/retry** (`src/polaris_graph/generator/multi_section_generator.py`):
   - line ~150: OUTPUT FORMAT now says "4-6 objects"
   - line ~162: M-40 rule now says "5 by default, 6 when
     regulatory evidence is also present per M-41a above"
   - lines ~462-480: retry prompt now says "5 OR 6 sections per
     M-25b + M-41a; Mechanism must be ADDITIVE, must not displace
     Regulatory / Safety / Efficacy / Comparative / Dose Response"

2. **M-41c retry-selection wiring**
   (`src/polaris_graph/generator/multi_section_generator.py`):
   - First-pass M-41c filter now runs BEFORE the retry decision.
   - Retry comparison uses `len(report2_kept_after_m41c) >
     post_filter_kept`, not strict_verify pre-filter totals.
   - `report.total_kept` is adjusted to reflect the post-filter
     count so downstream telemetry is honest.

3. **M-41c trial-name denylist**: added `_M41C_TRIAL_NAME_DENYLIST`
   covering ISO, IEC, DIN, ASTM, ANSI, IEEE, SAE, NCT, ICH, OECD,
   USP, EP, USC, CFR, EU, US, UN, WHO, FDA, EMA. Updated
   `_m41c_sentence_names_trial` to iterate regex matches and skip
   tokens whose prefix is in the denylist.

4. **M-41d host-suffix match**
   (`src/polaris_graph/retrieval/evidence_selector.py`):
   - Uses `urllib.parse.urlparse` to extract the actual host.
   - Matches `host == h OR host.endswith("." + h)`.
   - Removed bare "europa.eu" from EMA hosts.

## Files to read

```
src/polaris_graph/generator/multi_section_generator.py
  - OUTPUT FORMAT line (~150)
  - M-40 rule (~162)
  - Retry prompt (~462-480)
  - _M41C_TRIAL_NAME_DENYLIST + _m41c_sentence_names_trial (~680-720)
  - _run_section post-filter placement (~893-935)

src/polaris_graph/retrieval/evidence_selector.py
  - _M41D_JURISDICTION_HOSTS (removed europa.eu)
  - _row_jurisdiction (urlparse-based host match)

tests/polaris_graph/test_m41_v24_regression_fixes.py
  - 5 new pass-2 tests added at end of existing test classes
```

## What to verify

1. **M-41a blocker-1 closure**: All three previously-5-pinned spots
   now accommodate 6. Retry prompt no longer forbids the additive-
   Mechanism outline. Any other spot in the module that still says
   "5 sections" as a hard requirement?

2. **M-41c blocker-2 closure**: The first-pass filter runs
   UNCONDITIONALLY before the retry decision (previously only after
   the comparison). The retry path also applies the filter before
   comparing. Post-filter counts drive both the retry trigger
   (`post_filter_fraction < min_kept_fraction`) and the retry-vs-
   first-pass selection (`len(report2_kept_after_m41c) >
   post_filter_kept`).

3. **M-41c denylist completeness**: does the pass-2 denylist cover
   the known standards-body prefixes that would pattern-match the
   hyphen-digit shape? Consider additional candidates: GB, JIS, UL,
   BS, EN (British Standards), CAS (Chemical Abstracts Service),
   MIL (military standards). Currently the denylist has GB, JIS, BS,
   UL, CAS, EN, and more; is anything else likely to false-positive?

4. **M-41d host-suffix match correctness**: For `https://
   not-fda.gov.example/path`, `urlparse().hostname` is
   `not-fda.gov.example`. The check `host == "fda.gov" or
   host.endswith(".fda.gov")` returns False. Verify.
   For `https://accessdata.fda.gov/path`, hostname is
   `accessdata.fda.gov` which ends with `.fda.gov` → matches.
   Verify.

5. **Telemetry honesty**: `report.total_kept` now reflects
   post-M-41c count. Does any downstream consumer read
   `total_kept` and make decisions that would be altered by this
   change (e.g., a "zero kept = drop section" check)? Grep
   `total_kept` in the module.

6. **Post-M-41c zero-count handling**: If first-pass M-41c drops
   all sentences (e.g. all 5 were under-framed trial names),
   `post_filter_kept = 0` → `post_filter_fraction = 0` →
   retry triggered. Retry could also have 0 post-filter. Does the
   section then correctly flag `dropped_due_to_failure=True`?
   The original check was `report.total_kept == 0`; now it's
   `len(report.kept_sentences) == 0` which after assignment
   equals `report.total_kept`. Equivalent.

## What counts as a blocker vs medium

- **BLOCKER**: any path that reintroduces the pass-1 regressions;
  inconsistent prompt/parser/retry behavior; a scenario where
  M-41c wiring still lets a worse retry win.
- **MEDIUM**: further tightening (additional denylist entries,
  broader host list coverage).
- **LOW**: wording.

## Deliverable

Write `outputs/codex_findings/m41_code_audit_pass2/findings.md`:
- Final verdict (READY | BLOCKED | CONDITIONAL)
- Blockers (zero if READY)
- Mediums
- One-line confirmation per pass-1 blocker that it is closed.
