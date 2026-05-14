# I-carney-010 Claude architect audit

**Issue:** GH#490 — Serper stays: revert search-provider-deferred edits
**Branch:** `bot/I-carney-010-serper-stays`
**Codex diff verdict:** APPROVE iter 2 of 5 (zero P0/P1, convergence_call: accept_remaining)

## What

Revert the I-carney-008 (PR #488) edits that deferred the web search provider and removed `google.serper.dev` from the egress allowlist. Per user directive 2026-05-13: Serper stays — search queries carry no confidential content; the sovereignty constraint protects the LLM inference path + report-data jurisdiction, not the keyword query.

## Surface — config + docs ONLY, zero `src/` change

| File | Change |
|---|---|
| `config/egress_allowlist.txt` | re-add `google.serper.dev`; header + section comments disclose Serper as US, user-accepted |
| `infra/vexxhost/.env.example` | `SERPER_API_KEY` documented as the active REQUIRED search backend |
| `docs/transparency.md` §4 | `google.serper.dev` added to allowlist list; "Web search provider" rewritten as a plain disclosed exception incl. what Serper does/doesn't receive |
| `docs/carney_demo_runbook.md` | stack table + §0/§1 prereqs: Serper (US, disclosed) |
| `infra/vexxhost/README.md` | search line, prereq, architecture diagram, sovereignty audit table; "No US company anywhere" scoped |

`src/polaris_graph/retrieval/*` Serper code was never removed by I-carney-008 — only the allowlist + docs. So this revert is also config + docs only.

## Codex iteration trail

| Iter | Verdict | Findings | Resolution |
|---|---|---|---|
| 1 | REQUEST_CHANGES | P1-1 README "No US company anywhere" contradicts Serper exception; P2-2 §4 understates what Serper logs; P2-3 README asserted unverified entity "thatware LLC"; P2-1 /transparency JSON lacks machine-readable provider field | P1 + 2 doc-P2 fixed iter-2; P2-1 deferred (Codex: "docs are enough to avoid blocking") |
| 2 | **APPROVE** | zero P0/P1; 2 residual non-blocking P2 (transparency.md:70 wording tightening + deferred P2-1); convergence_call: accept_remaining | both P2 folded into follow-up task #320 |

Codex verified against serper.dev/privacy + serper.dev/terms in iter 2.

## P2-3 note — fabrication caught + corrected

Iter-1 P2-3: my iter-1 diff asserted `US (Serper / thatware LLC)` as Serper's legal entity. I had not verified "thatware LLC" — it was an unverified assertion. Corrected iter-2 to "US-based search API (legal entity not independently verified; Serper's Terms specify the governing law)." This is the §-1.1 "do not overclaim" standard applied: state what is known, explicitly flag what is not.

## Residual (follow-up task #320 — non-blocking per Codex)

1. `/transparency` JSON: add a machine-readable `egress_providers` / `provider_jurisdiction` field so Serper shows as a US disclosed-exception, not a bare hostname (`src/` change + test).
2. `docs/transparency.md` §4 wording: "does not receive any operator-entered content" is imprecise — the raw research question/search terms DO transit Serper (`live_retriever.py:1108,1130`); tighten to "...beyond the query terms."

## Verdict

READY TO MERGE. All Codex-required artifacts present:
- `.codex/I-carney-010/brief.md`
- `.codex/I-carney-010/codex_brief_verdict.txt` (APPROVE)
- `.codex/I-carney-010/codex_diff.patch` (canonical-diff-sha256 trailer)
- `.codex/I-carney-010/codex_diff_audit.txt` (iter-2 APPROVE)
- `outputs/audits/I-carney-010/claude_audit.md` (this file)

GH#487 (I-carney-009 "replace Serper") was closed as user-directive-WONTFIX.
