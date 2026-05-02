# Phase 1 End-of-Phase Walkthrough — Evaluator Briefing

**Task:** `1.8` per `docs/task_acceptance_matrix.yaml`
**Substrate-prep:** `1.8_prep_briefing_pack` (orchestrator-completed 2026-05-02)
**Walkthrough deadline:** 2026-06-04 (latest, per Plan v13 §G #7)
**Scope:** Phase 1 BPEI spine + Evidence Contract Gate (features F1, F2, F3, F4, F15)

## What you'll be evaluating

3 features that landed in Phase 1:

| Feature | What it does | What to test |
|---|---|---|
| **F1 Scope discovery** | Dashboard surfaces 8 templates with in-scope examples; live template suggestion as user types | Type "tirzepatide" → expect Clinical drug audit suggestion within 200ms |
| **F2 BPEI ambiguity** | When a query has multiple plausible meanings, modal asks which entity user means | Type "What is BPEI?" → expect modal with at least 3 candidate meanings (syndrome/institute/chemical) |
| **F3a/F3b Document upload** | Drag-and-drop PDF, doc gets parsed, used as evidence in next query | Drop a PDF, ask a question that references its content, expect the answer to cite the uploaded doc |
| **F15 Audit bundle export** | Click "Export bundle" on completed run → ZIP with report + evidence + trace + provenance | Click export, unzip, verify all 4 components present |

## Prerequisites (you don't need to set up — orchestrator handles)

- Fresh browser session (no cached state)
- 22-input adversarial test corpus in `docs/walkthroughs/1.8/test_inputs.md`
- Recording template at `docs/walkthroughs/1.8/recording_template.md`
- Backend running locally OR on dev cluster (task 0.3 — gate)

## What I (the evaluator) need to do

1. **Open the recording app** of your choice (Loom, OBS, QuickTime, etc.)
2. **Open `docs/walkthroughs/1.8/test_inputs.md`** — your 22-input script
3. **Start recording** (full screen + audio narration if you can)
4. **Walk through every input** in the script, narrate observations
5. **Stop recording** and save the file
6. **Save the recording to `.private/walkthroughs/1.8_<your_initials>_<YYYY-MM-DD>.mp4`** (gitignored — your machine only)
7. **Generate a GPG-signed attestation file** (the autoloop will guide you through this) at `outputs/audits/attestations/1.8_<your_name>.md.asc`
8. **Optional**: attach short notes to `outputs/audits/walkthroughs/1.8_findings.md` if anything stuck out

## What POLARIS is supposed to do (so you know when something's broken)

- F1 template browse: <200ms suggestion latency
- F2 BPEI ambiguity: modal appears within 1s of submit; offers 2-5 candidate meanings; refusing to disambiguate is not allowed (POLARIS must ask, not silently guess)
- F3 upload: PDF up to 50MB accepts; progress bar; chunks visible after parse
- F15 export: ZIP downloads within 5s; bundle includes report.md, evidence/, trace.jsonl, provenance.json

## What to specifically NOT trust

- The phrase "[#ev:...]" appearing in body text but not clickable → broken citation
- Any silent fallback (e.g., "I couldn't disambiguate so here's a generic answer") → BPEI failure
- Any answer that reads like ChatGPT (no citations, no tier markers) → missing strict_verify gate
- Any error message that's just a stack trace (vs. user-friendly explanation) → UX gap

## How long it'll take

~30-45 min for one full pass of the 22-input corpus. Budget 1 hour.

## Compensation (per Plan v13 §G #7)

If you're a paid evaluator: $300/session. If you're a friend: thank-you note.

## Questions during walkthrough

If something doesn't work as described → that's a finding, write it down. If something is unclear about WHAT to test → ping the user (`msn`); they'll iterate the briefing.

## Success criterion

Walkthrough is "passed" when:
1. Recording saved
2. GPG-signed attestation written
3. No P0 findings (broken core feature)

P1/P2/P3 findings are acceptable; orchestrator will land fixes in Phase 2 buffer.
