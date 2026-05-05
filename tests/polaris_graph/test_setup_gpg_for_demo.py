"""Tests for scripts/setup_gpg_for_demo.py.

Most paths exercise argparse + flow logic via monkeypatching the gpg
binary check and key-list subprocess calls. We do NOT actually generate a
real GPG key here; that would require gpg-agent on the test runner and is
covered by the live runbook.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make scripts/ importable
SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import setup_gpg_for_demo as helper  # noqa: E402


def test_parse_args_defaults():
    args = helper.parse_args([])
    assert args.name == "POLARIS Demo"
    assert args.email == "demo@polaris-canada.local"
    assert args.reuse_existing is False


def test_parse_args_custom_name_and_email():
    args = helper.parse_args(["--name", "Carney", "--email", "x@y.z"])
    assert args.name == "Carney"
    assert args.email == "x@y.z"


def test_parse_args_reuse_existing_flag():
    args = helper.parse_args(["--reuse-existing"])
    assert args.reuse_existing is True


def test_main_returns_2_when_gpg_missing(monkeypatch, capsys):
    monkeypatch.setattr(helper, "_check_gpg_binary", lambda: None)
    rc = helper.main([])
    assert rc == 2
    err = capsys.readouterr().err
    assert "gpg binary not on PATH" in err
    assert "GnuPG" in err  # install instructions


def test_main_returns_3_when_key_exists_without_reuse_flag(
    monkeypatch, capsys,
):
    monkeypatch.setattr(helper, "_check_gpg_binary", lambda: "/usr/bin/gpg")
    monkeypatch.setattr(
        helper, "_existing_key_id",
        lambda name, email: "ABCDEF0123456789",
    )
    rc = helper.main([])
    assert rc == 3
    err = capsys.readouterr().err
    assert "already exists" in err
    assert "ABCDEF0123456789" in err
    assert "--reuse-existing" in err


def test_main_returns_0_with_reuse_existing_when_key_exists(
    monkeypatch, capsys,
):
    monkeypatch.setattr(helper, "_check_gpg_binary", lambda: "/usr/bin/gpg")
    monkeypatch.setattr(
        helper, "_existing_key_id",
        lambda name, email: "ABCDEF0123456789",
    )
    rc = helper.main(["--reuse-existing"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Reusing existing key" in out
    assert "POLARIS_GPG_KEY_ID=ABCDEF0123456789" in out


def test_main_generates_key_and_prints_id(monkeypatch, capsys):
    monkeypatch.setattr(helper, "_check_gpg_binary", lambda: "/usr/bin/gpg")
    monkeypatch.setattr(helper, "_existing_key_id", lambda n, e: None)
    monkeypatch.setattr(
        helper, "_generate_key",
        lambda n, e: "FEEDBEEF12345678",
    )
    rc = helper.main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "POLARIS_GPG_KEY_ID=FEEDBEEF12345678" in out
    assert "Append this line to your .env" in out


def test_main_returns_4_when_key_generation_fails(monkeypatch, capsys):
    monkeypatch.setattr(helper, "_check_gpg_binary", lambda: "/usr/bin/gpg")
    monkeypatch.setattr(helper, "_existing_key_id", lambda n, e: None)

    def boom(n, e):
        raise RuntimeError("gpg crashed")

    monkeypatch.setattr(helper, "_generate_key", boom)
    rc = helper.main([])
    assert rc == 4
    err = capsys.readouterr().err
    assert "gpg crashed" in err


def test_main_warns_about_missing_python_gnupg_but_continues(
    monkeypatch, capsys,
):
    """LAW II: if the runtime dep is missing, surface it as a warning
    even when key generation otherwise succeeds — operator must know
    they need to pip install before booting the backend."""
    monkeypatch.setattr(helper, "_check_gpg_binary", lambda: "/usr/bin/gpg")
    monkeypatch.setattr(helper, "_existing_key_id", lambda n, e: None)
    monkeypatch.setattr(helper, "_generate_key", lambda n, e: "F1NG3RPR1NT")

    # Force the gnupg import to fail
    real_import = __builtins__["__import__"] if isinstance(
        __builtins__, dict
    ) else __import__

    def fake_import(name, *args, **kwargs):
        if name == "gnupg":
            raise ImportError("not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    rc = helper.main([])
    assert rc == 0
    err = capsys.readouterr().err
    assert "python-gnupg not installed" in err
