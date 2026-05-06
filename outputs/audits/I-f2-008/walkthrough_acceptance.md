# I-f2-008 — F2 Walkthrough Acceptance

**Reframe:** per user directive 2026-05-06 ("Codex is the guy who signs, not me"), the original "product-owner walkthrough; record-screen 3 sessions × 22-input corpus" is replaced by an automated Playwright walkthrough. This document IS the durable deliverable Codex reviews for the "all 22 handled correctly" verdict.

**Run command:**
```
cd web && npx playwright test --project=chromium tests/e2e/f2_walkthrough.spec.ts
```

The runtime artifact `outputs/audits/I-f2-008/walkthrough_transcript.md` is gitignored; this static table below is the authoritative deliverable.

## 22-scenario corpus

| # | Description | Expected | Surface tested |
|---|---|---|---|
| 1 | Ambiguous: BPEI / 3 clusters | 3 cluster cards visible | F2 modal positive path |
| 2 | Ambiguous: MS treatment options / 2 clusters | 2 cards | F2 modal positive path |
| 3 | Ambiguous: PR campaign metrics / 5 clusters | 5 cards | F2 modal positive path |
| 4 | Unambiguous: tirzepatide... | no modal, no /api/disambiguation call | needs_disambiguation=false short-circuit |
| 5 | Unambiguous: metformin... | no modal, no /api/disambiguation call | needs_disambiguation=false short-circuit |
| 6 | Unambiguous: aspirin... | no modal, no /api/disambiguation call | needs_disambiguation=false short-circuit |
| 7 | Guard: is_ambiguous=false case 0 | modal hidden | is_ambiguous guard |
| 8 | Guard: is_ambiguous=false case 1 | modal hidden | is_ambiguous guard |
| 9 | Guard: is_ambiguous=false case 2 | modal hidden | is_ambiguous guard |
| 10 | French: Quels sont les effets secondaires... | English-only error, no API call | French heuristic |
| 11 | French: Est-ce que l'aspirine... | English-only error, no API call | French heuristic |
| 12 | French: La thérapie physique... | English-only error, no API call | French heuristic |
| 13 | PDF drop: test.pdf (mime) | banner shown | PDF drop banner |
| 14 | PDF drop: test.PDF (extension only) | banner shown | PDF drop banner |
| 15 | Non-PDF drop: test.txt | no banner | PDF drop filter |
| 16 | Edge: empty input | 3-character gate error | client-side validation |
| 17 | Edge: pure whitespace | 3-character gate error | client-side trim + validation |
| 18 | Edge: very-long input (2500 chars) | input length capped at 2000, no submit | maxLength={2000} |
| 19 | Pick cluster_id=0 | label_0 in disambig-picked-label | post-pick state flow |
| 20 | Pick cluster_id=1 | label_1 in disambig-picked-label | post-pick state flow |
| 21 | Pick cluster_id=2 | label_2 in disambig-picked-label | post-pick state flow |
| 22 | Cancel (Escape) | disambig-picked-label empty | cancel does not write |

## Coverage map

- **F2 modal positive (BPEI ambiguous):** 1, 2, 3, 19, 20, 21
- **F2 negative (no modal):** 4, 5, 6, 7, 8, 9
- **F2 cancel (no state write):** 22
- **French heuristic:** 10, 11, 12
- **PDF drop banner:** 13, 14, 15
- **Client-side validation:** 16, 17, 18

## Codex acceptance criteria

APPROVE iff:
1. The 22 scenarios in `f2_walkthrough.spec.ts` map 1:1 to this table.
2. Each scenario asserts the correct observable surface (modal-Popup-element, error message text, request-call counter, input-value-length, etc.).
3. The latest transcript run shows 22/22 PASS.

## Out of scope

- Real human screen recordings — user-driven if they wish to also record; not gating Codex sign-off.
- Backend writer for `needs_disambiguation` + `candidate_snippets` → I-f2-005a follow-up.
