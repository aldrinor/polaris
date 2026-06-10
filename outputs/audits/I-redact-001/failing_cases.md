# I-redact-001 (#1181) — report_redactor fail-closed abort: the 3 real failing cases

**Source run:** beat-both re-run @454b7652 (branch `bot/I-ready-017-faithfulness`),
`~/polaris_run/outputs/honest_sweep_r3/` on `ubuntu@51.79.90.35`.
**Module under investigation:** `src/polaris_graph/roles/report_redactor.py` →
`reconcile_report_against_verdicts()`.
**Fixture (offline, self-contained):** `outputs/audits/I-redact-001/redaction_fixture.json`.

---

## Which questions actually hit the redaction abort (correction to the issue grouping)

The issue groups the failures as "drb_72/78: claim 05-006; drb_75/90: claim 07-002; drb_76: claim 04-004."
That grouping is **misleading**. Per-question manifest status:

| Question | manifest.status | Failing claim | This investigation |
|---|---|---|---|
| drb_76 | `abort_report_redaction_failed` | 04-004 (UNSUPPORTED/S1) | **REAL redaction abort** |
| drb_78 | `abort_report_redaction_failed` | 05-006 (UNSUPPORTED/S3) | **REAL redaction abort** |
| drb_90 | `abort_report_redaction_failed` | 07-002 (UNSUPPORTED/S3) | **REAL redaction abort** |
| drb_72 | `abort_four_role_release_held` | (n/a) | held on the RELEASE LATCH; redaction never raised. `report_redaction_error=None` |
| drb_75 | `abort_four_role_release_held` | (n/a) | held on the RELEASE LATCH; redaction never raised. `report_redaction_error=None` |

So the **3 distinct claims that aborted via `report_redactor`** are exactly `drb_76/04-004`,
`drb_78/05-006`, `drb_90/07-002`. drb_72 and drb_75 aborted earlier (release latch); their
non-VERIFIED claims redacted cleanly. A fix author should NOT spend time on drb_72/75 for this bug.

---

## mismatch_kind (dominant): COVERAGE < 0.6 caused by sentence-boundary UNDER-SPLIT

In all 3 cases the failing claim's normalized stem **IS contained inside exactly one rendered
sentence span** (`stem_in_single_span = True` for all 3). So this is **NOT** a multi-span /
straddle case (issue option b). It is option (a): the stem is a sub-clause of a LONGER rendered
"sentence" span, so coverage < `_MIN_REDACTION_COVERAGE` (0.6), `_sentence_matches_stem` returns
`False`, no span is redacted, the stem is still present in the full report → `reconcile()` raises
`ReportRedactionError` → `abort_report_redaction_failed`.

The span is "longer" because **`_SENTENCE_BOUNDARY_RE` failed to split two real sentences**:

```python
_SENTENCE_BOUNDARY_RE = re.compile(r"[.!?](?:\s*\[\d+\])*\s+(?=[A-Z\"'(#])")
_MIN_REDACTION_COVERAGE = 0.6
```

It requires (1) a terminator `[.!?]`, then (2) optional `[N]` markers, then whitespace, then
(3) a lookahead at an uppercase/quote/paren/hash. Two boundary patterns in real rendered prose
defeat it:

- **Subtype A — missing terminal period before the citation marker.** The renderer emits
  `...risk[1] Cereal...` and `...recovery[17][22] Legal...` with **no period before `[N]`**.
  No `[.!?]` terminator → no split. (drb_76, drb_90.)
- **Subtype B — next sentence starts with a digit.** A real boundary `...adherence.[16] 87.3% of
  DBS...` exists, but `87.3%` starts with a **digit**; the lookahead `(?=[A-Z"'(#])` rejects
  digits → no split. (drb_78.)

Either way two real sentences merge into one span, the stem covers < 0.6 of the merged span, and
the claim is "present but unpinnable" → fail-closed abort.

**Load-bearing for the fix shape:** in EACH merged span the UNSUPPORTED failing sentence is paired
with a **VERIFIED neighbor** (see per-case table). The issue's option "redact the minimal containing
unit (the span / line)" would therefore **delete a VERIFIED sentence and its `[N]` citations** —
the exact over-redaction invariant (c) forbids, and a §-1.1-lethal pattern in clinical context. The
correct fix is to **improve boundary splitting** so the failing sentence is isolated (coverage → ~1.0)
and redacted alone, not to lower the threshold or redact the whole span/line.

---

## Per-case detail (stored audit sentence vs rendered span + coverage)

### Case 1 — drb_76 / 04-004-ca78d74d (UNSUPPORTED / S1, clinical)

- **Stored audit sentence** (`four_role_claim_audit.json["04-004-ca78d74d"].sentence`):
  > Cereal fiber demonstrated a similar protective dose-response: each 10 g/day increase yielded an RR of 0.90 (0.83 to 0.97) based on 8 studies with 9,487 cases among 1,471,756 participants `[#ev:prebiotic_fiber_scfa_meta:19300-20100]`.
- **Rendered report.md line 34** — `_sentence_spans` yields 5 spans; the stem lands in **span 3**,
  a MERGED span (2 real sentences):
  > A systematic review and meta-analysis of 25 prospective studies examined the association between dietary fiber and whole grain intake and colorectal cancer (CRC) risk**[1]** Cereal fiber demonstrated a similar protective dose-response: … among 1,471,756 participants.[1]
- **Coverage = 186 / 353 = 0.527** (< 0.6) → `_sentence_matches_stem` = False → no span redacted.
- **Missed boundary:** `...colorectal cancer (CRC) risk[1] Cereal...` — no period before `[1]` (Subtype A).
- **VERIFIED neighbor in the same span:** `04-003-8b21fdf9` (VERIFIED / S1) — "A systematic review and
  meta-analysis of 25 prospective studies…". Must survive redaction with its `[1]`.

### Case 2 — drb_78 / 05-006-961e7d90 (UNSUPPORTED / S3, clinical)

- **Stored audit sentence:**
  > However, a meta‑synthesis of wearable device experiences identified barriers including discomfort, emotional distress, and interface difficulties that hinder long‑term adherence `[#ev:ev_719:100-900]`.
- **Rendered report.md line 32** — 9 spans; stem lands in **span 6**, a MERGED span:
  > However, a meta‑synthesis … hinder long‑term adherence.**[16]** 87.3% of DBS patients used rechargeable IPGs (r-IPGs), … the mean recharge interval was 4.3 days.[10]
- **Coverage = 177 / 444 = 0.399** (< 0.6) → no span redacted.
- **Missed boundary:** `...adherence.[16] 87.3% of DBS...` — next sentence starts with digit `8` (Subtype B).
- **VERIFIED neighbor in the same span:** `05-007-27b6f2db` (VERIFIED / S3) — "87.3% of DBS patients used
  rechargeable IPGs…". Must survive with its `[10]`. (Note: this is the unicode case — the stem carries
  non-breaking hyphens `‑` in "meta‑synthesis"/"long‑term"; `_normalize` does NOT change them, and they
  match byte-for-byte against the rendered line, so unicode is NOT the proximate cause here.)

### Case 3 — drb_90 / 07-002-6bfb4290 (UNSUPPORTED / S3, policy)

- **Stored audit sentence:**
  > Legal scholars debate whether the human driver or the manufacturer bears responsibility when supervised autonomy fails in semi-autonomous vehicles `[#ev:ev_008:0-800]`.
- **Rendered report.md line 53** — 2 spans; stem lands in **span 1**, a MERGED span:
  > Under U.S. products liability law, automakers may face primary liability for ADAS failures, though the driver's comparative fault can reduce recovery**[17][22]** Legal scholars debate whether the human driver or the manufacturer bears responsibility when supervised autonomy fails in semi-autonomous vehicles.[17]
- **Coverage = 146 / 296 = 0.493** (< 0.6) → no span redacted.
- **Missed boundary:** `...can reduce recovery[17][22] Legal...` — no period before the `[17][22]` markers (Subtype A).
- **VERIFIED neighbor in the same span:** `07-001-b3fea61d` (VERIFIED / S3) — "Under U.S. products liability
  law, automakers may face primary liability…". Must survive with its `[17][22]`.

---

## Verification (round-tripped through the REAL function)

`reconcile_report_against_verdicts(report_text, final_verdicts, audit_map)` was run on each case
with the unmodified module. All 3 raise `ReportRedactionError` on exactly the expected claim_id,
with a message byte-identical to the manifest's recorded `report_redaction_error`:

```
drb_76 -> raises on 04-004-ca78d74d   coverage 0.527
drb_78 -> raises on 05-006-961e7d90   coverage 0.399
drb_90 -> raises on 07-002-6bfb4290   coverage 0.493
```

This is the **red test**. The fixture `redaction_fixture.json` stores the FULL runner-equivalent
inputs (`report_text`, `final_verdicts`, `audit_map`) per case, so an offline pytest can:
1. assert the current module RAISES on the target claim (red), and
2. after the fix, assert the target sentence is redacted AND the VERIFIED neighbor (sentence + its
   `[N]` markers) is preserved byte-for-byte AND the report ships.

---

## Notes for the fix author (do not over-fit to this run)

- **No TRUE multi-span case exists in this run.** All 3 are merged-span / coverage-below-threshold.
  Issue acceptance (b) ("claim spanning 2 rendered sentences → both redacted") is NOT exhibited by
  this data and must be added as a **synthetic** fixture, not derived from these 3.
- **Fix direction:** harden `_SENTENCE_BOUNDARY_RE` (and/or `_sentence_spans`) so it splits on
  (A) a citation marker `[N]` followed by whitespace + a sentence-start even with no preceding
  period, and (B) a sentence start that begins with a digit — while keeping decimals (`0.90`,
  `4.3 days`, `No. 157`) and `U.S.` from becoming false boundaries. Isolating the failing sentence
  drives its coverage to ~1.0 so it redacts alone.
- **fail-closed-ABORT must still fire** when the prose is genuinely ABSENT from the report (a real
  inconsistency) — the SAFE state, not a hard-to-pin state.
- **Invariants to keep:** every non-VERIFIED claim's prose removed (no leak); VERIFIED neighbor keeps
  its `[N]` byte-for-byte; no over-redaction beyond the minimal safe unit; multilingual/decimal-safe.
