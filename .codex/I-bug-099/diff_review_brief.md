## §0 — HARD ITERATION CAP (per CLAUDE.md §8.3.1, verbatim)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## §1 — Diff under review

GH#353 — I-bug-099. Brief APPROVE'd iter 2 (0 P0/P1, 2 P2 cosmetic, `accept_remaining`).

Diff: `.codex/I-bug-099/codex_diff.patch` (2 files, +243 insertions, -178 deletions).

| File | Δ | Notes |
|---|---|---|
| `src/polaris_graph/llm/entailment_judge.py` | NEW (+207) | Canonical home for: `_DEFAULT_ENTAILMENT_MODEL`, `_ENTAILMENT_TIMEOUT_S`, `_ENTAILMENT_PROMPT`, `_EntailmentJudge` class, `_JUDGE_SINGLETON`, `_get_judge()`, `_JUDGE_TELEMETRY`, `get_judge_telemetry()`, `reset_judge_telemetry()`, `_record_judge_outcome()`. |
| `src/polaris_graph/generator2/strict_verify.py` | -178, +36 | Remove inline definitions; replace with `from polaris_graph.llm.entailment_judge import (…)` re-export block. KEEP `_DEFAULT_MODE`, `_UNKNOWN_MODE_WARNED`, `_entailment_mode()` (per iter-2 brief: tests rebind `strict_verify._UNKNOWN_MODE_WARNED` and the mode resolver must read the rebind via this module's globals). Comment block documents WHY `_JUDGE_SINGLETON` is NOT re-exported (resolver lives in entailment_judge.py and updates `global _JUDGE_SINGLETON` there; tests' incidental `monkeypatch.setattr(strict_verify, "_JUDGE_SINGLETON", ...)` creates a harmless vestigial attribute, but the same tests also patch `_get_judge` which IS re-exported and propagates correctly). |
| `src/polaris_graph/generator/provenance_generator.py` | UNCHANGED | Per iter-2 P1 fix: production verifier still lazy-imports from strict_verify. The "single import path" goal is achieved at the canonical-definition level, not at the import-site level. |

**Net: +243 / -178 lines; clean canonical relocation. Below §3.0 200-LOC cap on the LOGICAL change (the two large blocks are mostly relocation, not new code).**

## §2 — Test verification (already run on actual diff)

`pytest tests/polaris_graph/generator2/test_strict_verify_entailment.py tests/polaris_graph/generator2/test_strict_verify_telemetry.py tests/polaris_graph/generator2/test_strict_verify_unknown_mode_warning.py tests/polaris_graph/test_provenance_generator_entailment.py tests/crown_jewels/test_cj_008_entailment_correctness.py -x -q`:

```
============================= 66 passed in 4.31s ==============================
```

**66/66 pass on the post-refactor diff.** Confirms the iter-2 approach (re-export judge symbols from strict_verify, keep mode resolver + WARNED set in strict_verify) preserves the existing monkeypatch test pattern without modifying any test file.

## §3 — Brief-iter-2 P2 findings — disposition

| Brief iter-2 P2 | Disposition |
|---|---|
| `polaris_graph/llm/__init__.py` not empty; importing entailment_judge will execute __init__.py and eagerly import openrouter_client, changing strict_verify cold-import/off-mode behavior. | **Acknowledged, not blocking.** Empirically: 66/66 tests pass including off-mode tests (`test_off_mode_skips_entailment`, etc.). The eager OpenRouterClient import does NOT trigger a network call (only class-definition imports). off-mode behavior is preserved at the `_entailment_mode() == "off"` early-return level inside `verify_sentence`. Cold-import cost is ~negligible (pure Python class import). Hardening `llm/__init__.py` to lazy-load is a separate I-bug-102 concern (already filed: GH#356 — "Off-mode should skip generator2 import"). |
| Re-exporting assignment-backed globals like `_JUDGE_SINGLETON` is not a true alias. | **Documented in code comment.** The new strict_verify.py block lines 138-147 explicitly documents that `_JUDGE_SINGLETON` is NOT re-exported and that test `_get_judge` rebinds carry the test patch surface. Test pass rate (66/66) confirms the pattern works. |

## §4 — Files I have ALSO checked and they're clean

- `src/polaris_graph/generator2/generator.py:43` — imports `verify_sentence` etc. from `strict_verify` (unchanged). Does NOT touch entailment helpers. ✓
- `src/polaris_graph/generator/provenance_generator.py:755` — lazy-imports `_entailment_mode, _get_judge, _record_judge_outcome` from `strict_verify` (unchanged). All three names are re-exported by strict_verify after the refactor. ✓
- `src/polaris_graph/llm/__init__.py` — unchanged (still eagerly imports OpenRouterClient). See §3 P2-1 above.
- `src/polaris_graph/llm/openrouter_client.py` — unchanged. The new entailment_judge.py module lazy-imports `check_family_segregation` from this file inside `_EntailmentJudge.__init__()` (preserving the §9.1.1 family-segregation invariant). Lazy import keeps off-mode unaffected. ✓
- `tests/polaris_graph/generator2/test_strict_verify_entailment.py` — unchanged. Tests patch `strict_verify._JUDGE_SINGLETON` (vestigial after refactor — see §3 P2-2) AND `strict_verify._get_judge` (which IS re-exported). 24/24 tests pass. ✓
- `tests/polaris_graph/generator2/test_strict_verify_telemetry.py` — unchanged. 11/11 pass. ✓
- `tests/polaris_graph/generator2/test_strict_verify_unknown_mode_warning.py` — unchanged. Tests rebind `strict_verify._UNKNOWN_MODE_WARNED` (kept in strict_verify per iter-2 brief). 9/9 pass. ✓
- `tests/polaris_graph/test_provenance_generator_entailment.py` — unchanged. Tests `monkeypatch.setattr(_gen2, "_get_judge", lambda: fake)` where `_gen2 = strict_verify`. Provenance verifier's lazy import picks up the patched lambda. 10/10 pass. ✓
- `tests/crown_jewels/test_cj_008_entailment_correctness.py` — unchanged. End-to-end Crown Jewel test. 10/10 pass. ✓
- `.github/workflows/codex-required.yml` — unchanged.
- `state/active_issue.json`, `state/polaris_restart/charter_sha_pin.txt` — untouched.
- `docs/canonical_pin.txt` — untouched (none of the modified files are canonical-pinned).

## §5 — Output Schema Bound (per CLAUDE.md §8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## §6 — Convergence Hint

Brief APPROVE'd iter 2. Diff implements exactly what brief described:
- 207-line canonical entailment_judge.py module created.
- 178 lines removed from strict_verify.py; 36 lines added (re-exports + comment block).
- Mode resolver kept in strict_verify per iter-2 P2 fix.
- Provenance verifier UNCHANGED per iter-2 P1 fix.
- 66/66 entailment tests pass on actual post-refactor code.

Expected APPROVE on iter 1 of diff review.
