"""Search-credit / preflight-honesty fixes (I-meta-002-q1d #947). NO network / NO spend.

(a) Exa is Pipeline-B-ONLY (searcher.py); a missing EXA_API_KEY must NOT hard-FAIL the Pipeline-A
benchmark preflight — it is an advisory SKIP. (b) Serper exposes no programmatic prepaid-pool API, so
the credit check is an explicit documented advisory.

`pg_preflight` is imported as a module (NOT `from ... import test_*`) so pytest does not collect the
preflight's own async `test_*` functions as tests in this file.
"""

from __future__ import annotations

import asyncio

import scripts.pg_preflight as pf


def test_exa_missing_is_advisory_skip_not_fail(monkeypatch):
    """#947 core: a missing EXA key is no longer a benchmark FAIL (Exa is Pipeline-B-only)."""
    monkeypatch.setenv("PG_EXA_ENABLED", "1")
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    res = asyncio.run(pf.test_exa_api_key())
    assert res.status == pf.SKIP  # was pf.FAIL before #947
    assert res.status != pf.FAIL
    assert "Pipeline-B-only" in res.message


def test_exa_present_is_pass(monkeypatch):
    monkeypatch.setenv("PG_EXA_ENABLED", "1")
    monkeypatch.setenv("EXA_API_KEY", "exa-key-1234567890")
    res = asyncio.run(pf.test_exa_api_key())
    assert res.status == pf.PASS


def test_exa_disabled_is_skip(monkeypatch):
    monkeypatch.setenv("PG_EXA_ENABLED", "0")
    res = asyncio.run(pf.test_exa_api_key())
    assert res.status == pf.SKIP


def test_serper_credit_pool_is_advisory_skip():
    res = asyncio.run(pf.test_serper_credit_pool())
    assert res.status == pf.SKIP  # advisory, never a hard fail (no programmatic pool API)
    assert "serper.dev" in res.message
    assert "not programmatically queryable" in res.message.lower()


def test_serper_credit_pool_registered_in_tier1():
    names = {n for n, _ in pf.TIER_1_TESTS}
    assert "test_serper_credit_pool" in names
    assert "test_serper_api_key" in names and "test_exa_api_key" in names
