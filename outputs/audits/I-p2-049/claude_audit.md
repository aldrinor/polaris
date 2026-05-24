# Claude architect audit — I-p2-049 (#845): Sign-in S-rebuild

## Goal
Push /sign-in (the last public page) from B- to A — primarily by fixing 3 present-tense
sovereignty overclaims (LAW II) on an otherwise-clean institutional split-screen.

## What changed (1 file + doc, +14/-5) — text only
- `web/app/sign-in/page.tsx`: three "Sovereign…" overclaims narrowed so NONE can be read as
  covering US-routed LLM inference (Codex brief P1): trust point → "Canadian-hosted evidence
  records, integrity-hashed."; left strip → "Canadian-hosted research workspace · auditable
  evidence"; mobile lockup → "Canadian-hosted Workspace".
- `docs/web/s_tier_design_system.md`: Sign-in grade + the all-7-public-pages summary.

## LAW II / honesty (the precise win)
Codex flagged that even "Canadian-hosted processing" could imply inference runs in Canada (it
doesn't — OpenRouter-US). Narrowed to claims that are unambiguously true: the evidence
records/workspace ARE Canadian-hosted + integrity-hashed; nothing claims where inference runs.
The footer (every page) discloses "LLM inference is currently routed via OpenRouter (US),
disclosed at /transparency". grep confirms ZERO "Sovereign" remains in the file.

## Preserved (no logic change)
Auth handleSubmit / JWT / redirect / `?next=` validation; testids sign-in-form, Username/
Password labels, sign-in-submit, sign-in-error; the lg:hidden mobile brand lockup.

## e2e
sign_in 4/8 pass (render + bad-creds → sign-in-error). The 4 valid-creds → JWT/redirect +
`?next=` specs need the auth backend (not up in dev) — this is a text-only change (no auth
logic), so those are environmental, not a regression.

## Dual Codex gate
- Brief APPROVE (iter 2; iter-1 P1 narrowed "processing" → "evidence records"). Visual `-i`
  APPROVE (iter 1: desktop A / mobile A). Code diff APPROVE (iter 1, zero findings).

## Constraints honored
Brand `#c8102e` untouched; auth logic/testids preserved; honest sovereignty wording; no test
relaxation.

canonical-diff-sha256: 824b3eb3350439e161e6ef9f14af1d93b01d8b31febb60a9304b3780a7ae90e3
