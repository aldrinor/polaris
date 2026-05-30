## Codex review brief — I-bug-945 (GH#931) Path-B gate model identity check

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Output schema (bound)

```yaml
verdict: APPROVE | REQUEST_CHANGES
choice: A | B | C
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Context (LOCKED — do not relitigate)

- Clinical-grade DR benchmark POLARIS vs ChatGPT 5.5 Pro vs Gemini 3.1 Pro on 5 frozen DRB-EN questions (#925).
- §-1.1 audit standard binding: claim-by-claim against fetched cited spans; STRICTLY BANNED = pattern/metadata/string-presence audits.
- Generator pinned to `deepseek/deepseek-v4-pro` (locked, do not propose alternative).
- Path-B gate is the integrity surface — it must catch real drift and not false-fail on identity-equivalent surface.
- Smoke #14 pipeline ran fully (manifest status=success, 144 calls, $0.40); only the gate's post_run_assert failed on model slug compare.

## The decision

OpenRouter API confirms:
```
GET /api/v1/models
{"id": "deepseek/deepseek-v4-pro", "canonical_slug": "deepseek/deepseek-v4-pro-20260423"}
```

Chat-completions returns `model="deepseek/deepseek-v4-pro-20260423"` (the canonical_slug).
Our pin is sourced from `PG_GENERATOR_MODEL=deepseek/deepseek-v4-pro` (the alias).

The compare at `scripts/dr_benchmark/pathB_run_gate.py:301-302` raises GateError on strict `!=`.

### Three honest paths

**A** — Pin env to dated snapshot `PG_GENERATOR_MODEL=deepseek/deepseek-v4-pro-20260423`.
- Implementation: operator-side env change. Zero code diff.
- Pros: Strictest possible identity — env literally names the dated weights.
- Cons: (i) Every DeepSeek refresh requires env edit + memory/CLAUDE.md update + risk of stale-pin-in-docs. (ii) The alias→snapshot translation lives in operator's head, not in the codebase. (iii) The principle "always pin V4 Pro" lives in `feedback_top_tier_model_only_2026_05_25.md` as a model-family directive, NOT a dated-snapshot directive — A inverts that semantics.

**B** — Relax compare to base-prefix tolerance: accept `<base>-<date>` ≡ `<base>` (strip suffix-after-base).
- Implementation: ~3 LOC in pathB_run_gate.py compare.
- Pros: Minimal diff, matches the I-bug-944 case-insensitive-provider precedent.
- Cons: **BREAKS PRE-REGISTRATION INTEGRITY.** If DeepSeek silently rolls `<base>` to a new snapshot mid-run, the gate would not catch it — that's exactly the drift the gate exists to catch. Inverts the gate's purpose.

**C (Claude's recommendation)** — Preflight resolves pin via `GET /api/v1/models/<id>`, stores BOTH `id` and `canonical_slug` in the RolePin record. assert_post_run accepts served `model` matching EITHER field.
- Implementation: ~25 LOC. preflight() does one extra API call per role (cheap, runs once); RolePin gains a `canonical_slug: str | None` field; assert_post_run compares served model against `(id, canonical_slug)` tuple. Pin record (`pathB_gate_pin.json`) records BOTH — that artifact IS the pre-registration anchor.
- Pros: (i) Env stays human-friendly (alias). (ii) Pin record captures the actual dated snapshot at preflight time — strict identity preserved IN THE ARTIFACT. (iii) Catches the real drift case: if DeepSeek rolls `<base>` to `-20260601` between preflight and a later call, served model differs from BOTH pinned values → gate FAILs correctly. (iv) Reproducibility: re-running with the same `pathB_gate_pin.json` requires the exact `-20260423` snapshot, even if `<base>` has since moved.
- Cons: (i) One extra HTTPS call per role at preflight (~100ms). (ii) Adds API dependency to preflight (already there for reachability ping). (iii) If `/api/v1/models/<id>` returns no canonical_slug for some model, fallback path needed.

## Claude's choice

**C**. The pin record is the right pre-registration anchor — that's what gets archived alongside the run for audit. Env-as-pin (A) is fragile to docs drift; prefix-tolerance (B) defeats the gate's purpose. C captures the actual served identity at preflight while keeping the env human-readable.

## Files to be touched (under C)

- `scripts/dr_benchmark/pathB_run_gate.py` — add `canonical_slug: str | None` to RolePin dataclass; preflight() resolves via OpenRouter; assert_post_run accepts EITHER `model_slug` OR `canonical_slug`.
- `src/polaris_graph/benchmark/pathB_runner.py` — no change to _role_pins() shape (canonical_slug gets populated by preflight, not env).
- `tests/dr_benchmark/test_pathB_run_gate.py` — regression: `test_post_run_passes_when_served_model_is_canonical_slug` (served `<base>-<date>` while pin is `<base>` + canonical_slug `<base>-<date>` → PASS); `test_post_run_fails_when_served_model_differs_from_both` (served `<different-base>-<date>` → FAIL).
- `scripts/dr_benchmark/score_run.py:51` and `scripts/dr_benchmark/aggregate_systems.py:149,153` — already consume RolePin record; will surface canonical_slug if Claude opts to expose it in the final report (low-priority).

## Files checked clean (Claude verified pre-brief)

- `scripts/dr_benchmark/score_run.py:51` — pin consumer, no compare logic.
- `scripts/dr_benchmark/aggregate_systems.py:149,153` — final-report rendering only.
- `src/polaris_graph/llm/openrouter_client.py` — already records `model` from served response correctly; no compare.
- No other strict-slug-compare sites outside pathB_run_gate.py:301-302.

## Required from Codex

1. Verdict APPROVE/REQUEST_CHANGES on Claude's choice C (or counter-propose A or B with rationale).
2. If APPROVE on C: any P0/P1 implementation concerns Claude should address before diff (e.g., fallback when canonical_slug absent, caching, telemetry surface).
3. If counter-propose A or B: full rationale tied to §-1.1 pre-registration integrity, not just diff-size.

Question: A, B, or C?
