# POLARIS web — canonical route map (I-cd-004, locked)

Codex-APPROVED brief `.codex/I-cd-004/brief.md` (iter 1, all P2s = confirmations).
This is the locked prod route map the I-cd-013..030 rebuild series must respect.
Test-harness prod-exclusion is owned separately by **I-cd-015**.

## Prod routes (10 kept, surfaced in the AppShell nav as 8 primary + 2 contextual)

| Route | In top nav? | Rebuild issue | Note |
|---|---|---|---|
| `/` | Home | I-cd-022 (I-A-05) | Landing |
| `/intake` | Intake | I-cd-023 (I-A-06) | Research-question intake |
| `/dashboard` | Dashboard | I-cd-024 (I-A-07) | Run overview; deep-links into `/runs/[runId]` and `/inspector/[runId]` |
| `/upload` | Upload | I-cd-026 (I-A-09) | Document upload |
| `/benchmark` | Benchmark | I-cd-027 (I-A-10) | BEAT-BOTH benchmark UI |
| `/contracts` | Contracts | I-cd-028 (I-A-11) | Signed bundle / contracts |
| `/pin_replay` | Pin Replay | I-cd-029 (I-A-12) | Replay a pinned run |
| `/memory` | Memory | I-cd-030 (I-A-13) | Campaign memory. Codex iter-1 P2 confirmed KEEP-prod (campaign memory is real substrate; coordination risk to cut). |
| `/inspector/[runId]` | (contextual, deep-link) | I-cd-013 (I-A-03) | Gold per-run inspector |
| `/runs/[runId]` (+ `/graph` sub-route) | (contextual, deep-link) | I-cd-025 (I-A-08) | Run detail. **ABSORBS `/audit_live` (the standalone route is RETIRED at I-cd-025, not merely hidden from nav — per Codex P2).** |
| `/sign-in` | (auth — not in nav) | I-cd-014 (I-A-04) | static_accounts auth |

## CUT-from-prod (3)

These routes don't appear in any I-A-NN rebuild row. They are in-progress dev
test surfaces (SSE smoke, retrieval inspector, generator probe). Removed from
the prod nav. Codex iter-1 P2: "Do not keep these as operator diagnostics
unless a later issue adds explicit auth/role gating and ownership."

- `/generation`
- `/retrieval`
- `/sse`

Prod-build exclusion of these (alongside the 17 harness routes) is **I-cd-015**.

## Test-harness routes (17, excluded from prod build by I-cd-015)

| Group | Count |
|---|---|
| `(test_harness)/disambiguation_modal_preview` | 1 |
| `charts_test/*` | 5 |
| `sentence_hover_test/*` | 11 |

Kept in dev for component testing; never reachable in prod.
