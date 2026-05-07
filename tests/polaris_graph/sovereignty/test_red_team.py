"""Red-team tests proving the sovereignty gate fires on violation (I-f3-004).

If anyone weakens EXTERNAL_LEAK_FORBIDDEN or removes the assert_safe_for_external
gate, these tests fail in CI per .github/workflows/sovereignty.yml.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from polaris_graph.sovereignty.router import (
    SovereigntyViolationError,
    assert_safe_for_external,
)


@dataclass
class _Item:
    text: str
    classification: str | None


def test_red_team_client_doc_blocked():
    payload = [_Item("public sample", "PUBLIC_SYNTHETIC"), _Item("client trade secret", "CLIENT")]
    with pytest.raises(SovereigntyViolationError, match="CLIENT"):
        assert_safe_for_external(payload)


def test_red_team_can_real_blocked():
    payload = [_Item("Canadian PII", "CAN_REAL")]
    with pytest.raises(SovereigntyViolationError, match="CAN_REAL"):
        assert_safe_for_external(payload)


def test_red_team_unknown_default_deny_blocked():
    payload = [_Item("missing classification", None)]
    with pytest.raises(SovereigntyViolationError, match="UNKNOWN"):
        assert_safe_for_external(payload)
