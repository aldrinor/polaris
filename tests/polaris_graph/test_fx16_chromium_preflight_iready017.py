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


def test_probe_disable_semantics_match_production_exactly(monkeypatch):
    """Codex iter-1 P1: PG_DISABLE_ACCESS_BYPASS=true must NOT SKIP — production
    (live_retriever.py:1764) disables the cascade only on exactly '1'. A non-'1' truthy value means
    production STILL runs the cascade, so the probe must proceed (FAIL in LIVE when chromium absent),
    not skip — otherwise the gate green-lights a run that production won't actually bypass."""
    monkeypatch.setattr(pf, "_find_chromium_binary", lambda cache_root=None: None)
    monkeypatch.setattr(pf, "LIVE_MODE", True)
    for val in ("true", "True", "yes", "on", "0", "", "  1  "):
        monkeypatch.setenv("PG_DISABLE_ACCESS_BYPASS", val)
        r = asyncio.run(pf.test_chromium_browser_available())
        assert r.status == pf.FAIL, f"value {val!r} should NOT skip (only exact '1' bypasses prod)"
    # exact '1' DOES skip
    monkeypatch.setenv("PG_DISABLE_ACCESS_BYPASS", "1")
    assert asyncio.run(pf.test_chromium_browser_available()).status == pf.SKIP


def test_find_chromium_honors_playwright_browsers_path(monkeypatch, tmp_path):
    """Codex iter-1 P2: PLAYWRIGHT_BROWSERS_PATH (resolved FIRST) prevents a false-FAIL on a non-default
    install location."""
    root = tmp_path / "custom-pw"
    binp = root / "chromium-1187" / "chrome-win" / "chrome.exe"
    binp.parent.mkdir(parents=True)
    binp.write_text("MZ", encoding="utf-8")
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(root))
    found = pf._find_chromium_binary()  # no cache_root -> uses the root list (env first)
    assert found is not None and str(root) in found


def test_find_chromium_ignores_non_file_match(tmp_path):
    """Codex iter-1 P2: a matching PATH that is a directory (partial cache) must NOT pass — only a real
    file counts."""
    root = tmp_path / "ms-playwright"
    # create the launcher path as a DIRECTORY, not a file
    (root / "chromium-1187" / "chrome-linux" / "chrome").mkdir(parents=True)
    assert pf._find_chromium_binary(root) is None
