"""Make src/ importable for crown-jewel tests so deep modules in
src.polaris_graph.* can resolve their own `from polaris_graph...` imports.

I-bug-095 also defaults PG_STRICT_VERIFY_ENTAILMENT=off for crown-jewel
tests that exercise verify_sentence without the entailment gate, so
lazy-constructing the OpenRouter judge does not happen accidentally
in CI. Crown-jewel tests that explicitly test the entailment invariant
(e.g. test_cj_008) override per-test via monkeypatch.setenv.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


@pytest.fixture(autouse=True)
def _disable_strict_verify_entailment_by_default(monkeypatch):
    """I-bug-095: keep crown-jewel tests network-free.

    Force off unconditionally (per Codex iter-1 diff P2 — stricter
    hermeticity vs an inherited shell env). Tests that exercise the
    entailment gate (cj-008) override explicitly via monkeypatch.setenv
    inside the test body.
    """
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    yield
