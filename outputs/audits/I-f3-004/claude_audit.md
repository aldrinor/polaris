# Claude Architect Audit — I-f3-004 (sovereignty CI)

**Branch:** bot/I-f3-004 / **Diff SHA256:** `5179db8512d3c9736df6333007bd8f51d4d812e58f93d8dfeb0ffc4045496c6d`
**LOC:** 64 net (under CHARTER §1 200-cap by 136; under breakdown 80 budget by 16)
**Tests:** 19/19 PASS in `tests/polaris_graph/sovereignty/` (incl. 3 new red-team tests)

## Files

```
.github/workflows/sovereignty.yml                    NEW +24
tests/polaris_graph/sovereignty/test_red_team.py     NEW +40
```

## Architecture review

1. **Workflow triggers.** `pull_request` + `push: branches: [polaris, main]` — gates every PR + defends against direct push.
2. **Python 3.11.** Matches existing project workflow convention.
3. **`pip install pytest`.** Minimal install (sovereignty modules have zero external deps).
4. **`PYTHONPATH=src` env var.** Per project convention.
5. **3 red-team tests cover all forbidden classifications:** CLIENT, CAN_REAL, UNKNOWN-default-deny. Each asserts the SovereigntyViolationError message contains the specific classification — proves the gate identifies WHICH classification triggered.
6. **`assert_safe_for_external` used directly.** Strict mode. If anyone weakens it, red-team tests fail in CI.

## Verdict

APPROVE for Codex diff review.
