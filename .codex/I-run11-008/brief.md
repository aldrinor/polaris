# I-run11-008 — GLM Mirror blank fix (implementation brief)

Issue #1053. Branch off bot/I-run11-007 (stacked; #1052 provider routing is the base). Root cause +
sources in logs/session_log.md [2026-06-04 09:35 / 09:38].

## The 3 changes (src/polaris_graph/roles/openrouter_role_transport.py + openai_compatible_transport.py + mirror_adapter.py)

### 1. Disable reasoning for the Mirror + give it a PROPER non-reasoning max_tokens (HIGHEST IMPACT)
- `_ROLE_REASONING_DEFAULT` (openrouter_role_transport.py ~line near role_reasoning_enabled): set
  `"mirror": False` (was True). Rationale: GLM's OpenRouter providers do NOT support `effort`, so
  reasoning.effort=xhigh was a silent no-op AND GLM's runaway thinking ate the budget → 47 blanks.
  A short `<co>`+JSON verdict needs no thinking.
- BUT the non-reasoning branch of `_build_openrouter_body` currently sets
  `max_tokens = PG_SENTINEL_MAX_TOKENS` (default 256) — TOO LOW for the Mirror's citation+answer
  (this is the run-16 trap). FIX: the non-reasoning Mirror must get its own budget, e.g.
  `PG_MIRROR_MAX_TOKENS` default ~6000 (NOT the Sentinel's 256). Add a per-role max_tokens resolution
  so mirror!=sentinel on the non-reasoning path.
- Keep provider routing (#1052) + require_parameters in the block.

### 2. Salvage the verdict from reasoning_content (parse path)
- In `_parse_openrouter_response` (openrouter_role_transport.py ~line 559-592): when `bare` content is
  empty BUT `reasoning`/`reasoning_content` is populated, return the reasoning text AS the bare verdict
  ONLY IF it contains a parseable complete verdict (the downstream mirror_adapter/sentinel parsers will
  validate `<co>`+JSON; if they fail it still fails closed). Do NOT raise BlankVerdictError when the
  answer is recoverable from reasoning_content. Keep BlankVerdictError when BOTH are empty.
- Guard: only salvage when the content channel is genuinely empty (not when there's a real bare verdict).

### 3. Transport / connection-error retry in complete()
- The seam HELD on `RoleTransportError: WinError 10054` (OpenRouter forcibly closed the connection) —
  currently only `BlankVerdictError` is retried. In `complete()`, catch `RoleTransportError` /
  httpx.HTTPError (connection reset/timeout) and retry with bounded attempts + backoff (env
  PG_TRANSPORT_RETRIES default 2). A shorter call (reasoning off) already reduces resets. Keep the
  generous timeout (180s).

## Tests
- Update the tests that assert the Mirror reasoning block (test_openrouter_role_transport_meta007.py:
  test_sends_pinned_slug_and_max_reasoning asserts `reasoning={"enabled":True,"effort":"xhigh"}` for
  mirror — mirror is now reasoning-OFF, so update the mirror case + the non-reasoning max_tokens
  assertion). The decomposition/classifier Sentinel tests are unaffected (sentinel reasoning unchanged).
- New tests: (a) non-reasoning Mirror builds with PG_MIRROR_MAX_TOKENS not 256; (b) salvage returns the
  reasoning_content as the verdict when content empty + reasoning populated; (c) RoleTransportError
  (connection reset) triggers a retry then succeeds.

## Validate
- Offline: full tests/roles + tests/dr_benchmark green.
- Empirical bake-test (research caveat — GLM may not honor a hard reasoning cap): a few live run_mirror
  calls reasoning-OFF on real claims → confirm non-blank + bound. (scripts/diagnostics/)
- Then re-run drb_72 → expect RELEASE (coverage > 0) → §-1.1 audit + beat-both benchmark → verdict.

## Codex gate
Standard diff-gate (§8.3.1 cap directive verbatim at top). Then queue PR for operator merge (stacked).
