"""Per-role output contracts for the POLARIS 4-role architecture (I-meta-002 sub-PR-2).

Pure parsers/normalizers over a raw role-output string + minimal context, returning a
typed result. NO network, NO spend — each role is exercised here ONLY via fixtures.

Roles (operator-LOCKED, NOT consultable):
- Generator: deepseek/deepseek-v4-pro
- Mirror:    cohere/command-a-plus      -> mirror_contract
- Sentinel:  ibm-granite/granite-guardian-4.1-8b -> sentinel_contract (fail-CLOSED)
- Judge:     qwen/qwen3.6-35b-a3b       -> judge_contract (5-enum reuse, hard-fail)

This is the contract layer only. Adapter wiring is sub-PR-4; spend is sub-PR-5; the
release-gate wiring of the source_missing split is sub-PR-3.
"""

from __future__ import annotations
