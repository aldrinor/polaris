"""I-cred-013 (#1163) preflight — REGRESSION LOCKS for the 5 recurring false alarms.

Each test FAILS if a previously-killed false alarm resurfaces. Offline, deterministic, no spend.
These exist because the operator flagged these five as repeat-offenders he never wants to see again:
the durable kill is a regression test, not a one-off fix.

The check LOGIC lives in ``scripts/dr_benchmark/false_alarm_checks.py`` (a NON-test module) so the live
super-heavy pre-spend preflight can RUNTIME-assert the SAME five checks WITHOUT importing ``tests/`` on
the paid VM. This module is the thin pytest wrapper over that shared logic (one test per check)."""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.dr_benchmark.false_alarm_checks import (  # noqa: E402  (sys.path bootstrap above)
    check_fa1_crlf_gitattributes_rule_committed,
    check_fa2_competitor_outputs_present,
    check_fa3_run_health_fail_loud_guard_present,
    check_fa4_empty_response_failover_present,
    check_fa5_journal_only_gated_by_source_restriction,
)


def test_fa1_crlf_gitattributes_rule_committed():
    check_fa1_crlf_gitattributes_rule_committed()


def test_fa2_competitor_outputs_present():
    check_fa2_competitor_outputs_present()


def test_fa3_run_health_fail_loud_guard_present():
    check_fa3_run_health_fail_loud_guard_present()


def test_fa4_empty_response_failover_present():
    check_fa4_empty_response_failover_present()


def test_fa5_journal_only_gated_by_source_restriction():
    check_fa5_journal_only_gated_by_source_restriction()
