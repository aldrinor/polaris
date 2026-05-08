# Claude architect audit — I-f13-001

**Issue:** Pin replay UI — same query rerun on different dates
**Branch:** bot/I-f13-001
**Canonical-diff-sha256:** 8cf506c1c718b4a1d4abbaeacd6e68f4bfe33f489b3656c9471969bfe9995442
**Brief verdict:** APPROVE iter 1 (0/0/0/0)
**Diff verdict:** APPROVE iter 1 (0/0/0/1, accept_remaining; P2 — aria-label on selects deferred to polish pass)

## Substrate honesty
- New `/pin_replay` route renders 2 snapshot cards with date `<select>` and a delta panel.
- Demo registry (`DEMO_PIN_REGISTRY` in `web/lib/pin_replay_demo.ts`) is hand-authored frontend data; honestly framed in route copy as "production fetch from `/runs/{run_id}/pins/{date}` per M-INT-0b post-Carney."
- SnapshotCard reusable component encapsulates one card; PinReplayPage composes two + delta.
- Native `<select>` provides keyboard + screen-reader baseline accessibility (P2 aria-label deferred per Codex iter-1 — non-blocking).

## §9.4 N/A frontend.

## CHARTER §1 LOC cap
- 211 net (11 LOC over 200). Exemption: demo data + reusable card component.

## Verdict
APPROVE.
