M-43 pass-2 audit — closes pass-1 BLOCKED findings.

## Pass-1 verdict (commit `e7829d5`)

BLOCKED. Four failures in `tests/polaris_graph/test_m28_regulatory_expander.py`
under `PYTHONPATH=src python -m pytest`:

1. `test_module_contains_no_agency_or_host_strings` — M-43 doc
   comment in regulatory_expander.py contained "nice" and "clinical"
2. `test_default_cap_truncates_to_ten` — expected 10, now 12
3. `test_invalid_env_falls_back_to_default` — expected fallback 10
4. `test_clinical_template_expansion_end_to_end` — expected `<= 10`

These tests had been hidden from earlier runs by a stale module
import path (`from polaris_graph...` without PYTHONPATH). Codex
was the first to actually execute them.

## Pass-2 changes (commit `e01bf9f`)

1. `src/polaris_graph/retrieval/regulatory_expander.py`:
   Rewrote the M-43 comment to avoid every token on the
   module-hygiene guard's banned list. No agency names, no
   domain names, no drug/trial tokens. Explains: "a prior
   retrieval sweep silently truncated the final anchor in an
   11-entry template, dropping downstream bibliography coverage
   to zero for that jurisdiction. 12 fits the current template
   with one future-addition headroom."

2. `tests/polaris_graph/test_m28_regulatory_expander.py`:
   - Renamed `test_default_cap_truncates_to_ten` →
     `_to_twelve`. Assertion `== 10` → `== 12`. Index
     expectations updated.
   - `test_invalid_env_falls_back_to_default`: fallback now 12.
   - `test_clinical_template_expansion_end_to_end`: `<= 10` →
     `<= 12` AND added a standing regression guard:
     `len(result) == len(declared_anchors)` so any future cap/
     anchor-list mismatch fails immediately.

## Verification

Narrow scope (Codex's original test contract):
`PYTHONPATH=src python -m pytest tests/polaris_graph/test_m43_anchor_cap.py
tests/polaris_graph/test_m28_regulatory_expander.py -q`
→ 36 passed.

Wide scope note: the full test suite with PYTHONPATH=src surfaces
10 additional pre-existing failures (M-29 rule-block scoping
picks up M-37 rule #11b; M-36 async coroutine never-awaited).
These are NOT caused by M-43 and were already failing before this
change — they are stale tests that the broken import path had
been hiding. Tracked as follow-up hygiene debt, out of scope for
M-43.

## What to verify

1. Are all four pass-1 blockers closed?
2. Does the revised comment pass the no-hard-coded-hosts guard?
3. The new invariant (`len(result) == len(declared_anchors)`)
   stands as a permanent regression guard. Acceptable?
4. Is the scope-separation rationale sound — M-43 closes its own
   blockers without sweeping the pre-existing M-29/M-36 debt?

## Deliverable

Write `outputs/codex_findings/m43_code_audit_pass2/findings.md`.
Verdict (READY | BLOCKED | CONDITIONAL). Under 500 words.
