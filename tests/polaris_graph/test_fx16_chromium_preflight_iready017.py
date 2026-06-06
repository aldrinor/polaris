"""FX-16 (I-ready-017 #1131): fail-closed chromium preflight probe (code half).

The AccessBypass browser-fetch tier (Playwright/Crawl4AI) needs a chromium binary. drb_72 fetched at
success_rate 0.51 because chromium was absent on the VM and the cascade SILENTLY degraded to
httpx-naive (LAW II). FX-16 adds a probe to pg_preflight: present → PASS; absent + cascade-on → FAIL
in LIVE/paid mode (SKIP-with-remediation in DRY so dev/CI don't break); cascade off → SKIP.
`_find_chromium_binary` is pure + cross-platform → unit testable with a synthetic cache_root.
The VM `playwright install chromium --with-deps` (Q5) + the post-install live fetch are operator-gated.
Offline, no network, no real browser.
"""
from __future__ import annotations

import asyncio

import scripts.pg_preflight as pf


def test_find_chromium_none_when_cache_absent(tmp_path):
    assert pf._find_chromium_binary(tmp_path / "does-not-exist") is None


def test_find_chromium_none_when_cache_empty(tmp_path):
    (tmp_path / "ms-playwright").mkdir()
    assert pf._find_chromium_binary(tmp_path / "ms-playwright") is None


def test_find_chromium_detects_linux_layout(tmp_path):
    root = tmp_path / "ms-playwright"
    binp = root / "chromium-1187" / "chrome-linux" / "chrome"
    binp.parent.mkdir(parents=True)
    binp.write_text("#!/bin/sh\n", encoding="utf-8")
    found = pf._find_chromium_binary(root)
    assert found is not None and found.endswith("chrome")


def test_find_chromium_detects_windows_layout(tmp_path):
    root = tmp_path / "ms-playwright"
    binp = root / "chromium-1187" / "chrome-win" / "chrome.exe"
    binp.parent.mkdir(parents=True)
    binp.write_text("MZ", encoding="utf-8")
    found = pf._find_chromium_binary(root)
    assert found is not None and found.endswith("chrome.exe")


def test_probe_skips_when_access_bypass_disabled(monkeypatch):
    monkeypatch.setenv("PG_DISABLE_ACCESS_BYPASS", "1")
    monkeypatch.setattr(pf, "_find_chromium_binary", lambda cache_root=None: None)
    r = asyncio.run(pf.test_chromium_browser_available())
    assert r.status == pf.SKIP and "intentionally off" in r.message


def test_probe_pass_when_chromium_present(monkeypatch):
    monkeypatch.setenv("PG_DISABLE_ACCESS_BYPASS", "0")
    monkeypatch.setattr(pf, "_find_chromium_binary", lambda cache_root=None: "/x/chrome")
    r = asyncio.run(pf.test_chromium_browser_available())
    assert r.status == pf.PASS and "/x/chrome" in r.message


def test_probe_fails_closed_in_live_mode_when_absent(monkeypatch):
    monkeypatch.setenv("PG_DISABLE_ACCESS_BYPASS", "0")
    monkeypatch.setattr(pf, "_find_chromium_binary", lambda cache_root=None: None)
    monkeypatch.setattr(pf, "LIVE_MODE", True)
    r = asyncio.run(pf.test_chromium_browser_available())
    assert r.status == pf.FAIL and "playwright install chromium" in r.message


def test_probe_skips_with_remediation_in_dry_mode_when_absent(monkeypatch):
    """DRY mode must NOT hard-fail (dev/CI), but must surface the would-fail remediation."""
    monkeypatch.setenv("PG_DISABLE_ACCESS_BYPASS", "0")
    monkeypatch.setattr(pf, "_find_chromium_binary", lambda cache_root=None: None)
    monkeypatch.setattr(pf, "LIVE_MODE", False)
    r = asyncio.run(pf.test_chromium_browser_available())
    assert r.status == pf.SKIP and "would FAIL in LIVE" in r.message
