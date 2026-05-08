# Claude architect audit — I-f6-005

**Issue:** F6 perf — 100x hover consistent <100ms
**Branch:** bot/I-f6-005
**Canonical-diff-sha256:** 9e66fb37113d43d78527a5689a571631f7b721c82eabc7c0a5ace9e8404d8140
**Brief verdict:** APPROVE iter 5 (force-APPROVE'd at cap; iter-5 schema returned APPROVE with 2 P2)
**Diff verdict:** APPROVE iter 1 (0/0/0/0, accept_remaining)

## Substrate honesty
- New `openOverride?: boolean` prop on `EvidenceTooltip` is fully opt-in (default `undefined` → byte-equivalent to pre-I-f6-005 component for all existing callers; the only consumer is the perf harness).
- `PerfHarness` mounts the REAL production `EvidenceTooltip`, not a clone — production-component perf regression IS locked.
- MutationObserver scan checks self-or-descendant per Codex iter-2 P2; popup-removed poll handles Base UI's async unmount per Codex iter-2 P1.
- Sentinel `-1` for stuck-popup is excluded by the spec's `t >= 0` filter per Codex iter-3 P1 — stuck-popup cannot pass as false green.
- New CI step `run_e2e_evidence_tooltip_perf` in `web_ci.yml` ensures the new gate executes per Codex iter-4 P1.

## §9.4 N/A frontend.

## CHARTER §1 LOC cap
- 180 net. Under 200. (Brief estimate ~110; final 180 includes JSDoc + helper functions).

## Verdict
APPROVE.
