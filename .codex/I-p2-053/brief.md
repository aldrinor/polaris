# Codex brief — I-p2-053 (#853): Memory page S-audit

HARD ITERATION CAP: 5. iter 1. Front-load findings; reserve P0/P1 for real risks. APPROVE iff the
plan is sound + doesn't break the contract.

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Context
/memory (cred-gated) is the workspace-memory surface. Live it 401-redirects without a real
reviewer JWT. Audited by rendering locally (seeded session + route-mocked /workspaces/ws_demo/
memory fixture — visual-audit-only, never shipped).

## Plan (assess-first — page built but raw)
The page was the rawest cred-gated page: raw controls, raw enum strings as labels, raw bg-blue/
bg-rose, NO loading/error/empty states. Rebuild to the design system:
1. Card form (labelled select w/ human labels but raw option VALUES, textarea, Button).
2. state-kit loading/error/empty + try/catch (none existed).
3. rows = meaning-tinted kind chip + 3-line layout + tokenized Forget + "SAVED MEMORY · N".
Preserve WS, the >=4-char save gate, all testids, and the raw option values (e2e selects by value).

## Note
Already gated downstream: visual `-i` APPROVE iter-2 (desktop A / mobile A- / empty A); code diff
under review in parallel. This brief records acceptance for the artifact set.
