"""Tests for gpg_signer.

Generates a temporary RSA keypair in a fresh keyring (per-test tmp_path),
signs a payload, verifies the signature, and asserts the .asc format
matches what `gpg --verify` expects.

Skips if the system gpg binary is not callable.
"""

from __future__ import annotations

from pathlib import Path

import gnupg
import pytest

from polaris_graph.audit_bundle.gpg_signer import (
    GPGSigner,
    GPGSignerConfig,
    build_gpg_signer,
    load_config_from_env,
)


# ---------- Skip when gpg unavailable ----------

def _gpg_callable() -> bool:
    try:
        gpg = gnupg.GPG()
        _ = gpg.version
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _gpg_callable(),
    reason="system gpg binary not available — skipping GPG-signer tests",
)


# ---------- Fixtures: temporary keyring + test keypair ----------

@pytest.fixture
def temp_keyring(tmp_path: Path) -> Path:
    keyring_dir = tmp_path / "gnupg"
    keyring_dir.mkdir(mode=0o700)
    return keyring_dir


@pytest.fixture
def test_keypair(temp_keyring: Path) -> tuple[gnupg.GPG, str]:
    gpg = gnupg.GPG(gnupghome=str(temp_keyring))
    input_data = gpg.gen_key_input(
        name_real="POLARIS Test Signer",
        name_email="test@polaris.local",
        key_type="RSA",
        key_length=2048,
        passphrase="test-passphrase",
        expire_date=0,
    )
    key = gpg.gen_key(input_data)
    if not key.fingerprint:
        # gpg-agent or environment issue (common on Windows when the
        # gpg config has a hardcoded agent path). Skip rather than fail
        # so CI on a properly-configured host still exercises this; the
        # integration tests rely on a pre-existing key in the OS keyring.
        pytest.skip(
            f"gpg key generation unavailable in this env "
            f"(gpg-agent issue?); skipping signer round-trip tests. "
            f"stderr={key.stderr!r}"
        )
    return gpg, str(key.fingerprint)


# ---------- Config / env handling ----------

def test_load_config_requires_key_id(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("POLARIS_GPG_KEY_ID", raising=False)
    with pytest.raises(RuntimeError, match="POLARIS_GPG_KEY_ID is required"):
        load_config_from_env()


def test_load_config_blank_key_id_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("POLARIS_GPG_KEY_ID", "   ")
    with pytest.raises(RuntimeError, match="POLARIS_GPG_KEY_ID is required"):
        load_config_from_env()


def test_load_config_with_key_only(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("POLARIS_GPG_KEY_ID", "fingerprint-here")
    monkeypatch.delenv("POLARIS_GPG_PASSPHRASE", raising=False)
    cfg = load_config_from_env()
    assert cfg.key_id == "fingerprint-here"
    assert cfg.passphrase is None


def test_load_config_full(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("POLARIS_GPG_KEY_ID", "fp")
    monkeypatch.setenv("POLARIS_GPG_PASSPHRASE", "secret")
    monkeypatch.setenv("GNUPGHOME", str(tmp_path))
    cfg = load_config_from_env()
    assert cfg.passphrase == "secret"
    assert cfg.gnupghome == str(tmp_path)


# ---------- Signing ----------

def test_signer_lists_secret_keys(test_keypair: tuple[gnupg.GPG, str], temp_keyring: Path):
    _gpg, fingerprint = test_keypair
    signer = GPGSigner(
        config=GPGSignerConfig(
            key_id=fingerprint,
            passphrase="test-passphrase",
            gnupghome=str(temp_keyring),
        )
    )
    keys = signer.list_secret_keys()
    assert any(k["fingerprint"] == fingerprint for k in keys)


def test_signer_produces_armored_signature(
    test_keypair: tuple[gnupg.GPG, str], temp_keyring: Path
):
    _gpg, fingerprint = test_keypair
    signer = GPGSigner(
        config=GPGSignerConfig(
            key_id=fingerprint,
            passphrase="test-passphrase",
            gnupghome=str(temp_keyring),
        )
    )
    payload = b"manifest_yaml_content_placeholder"
    sig_bytes = signer.sign(payload)
    sig_text = sig_bytes.decode("utf-8")
    assert "BEGIN PGP SIGNATURE" in sig_text
    assert "END PGP SIGNATURE" in sig_text


def test_signer_signature_verifies_with_gpg(
    test_keypair: tuple[gnupg.GPG, str], temp_keyring: Path, tmp_path: Path
):
    """Round-trip: sign → write to disk → verify with gpg."""
    gpg, fingerprint = test_keypair
    signer = GPGSigner(
        config=GPGSignerConfig(
            key_id=fingerprint,
            passphrase="test-passphrase",
            gnupghome=str(temp_keyring),
        )
    )
    payload = b"manifest contents go here\n"
    sig_bytes = signer.sign(payload)

    payload_path = tmp_path / "manifest.yaml"
    sig_path = tmp_path / "manifest.yaml.asc"
    payload_path.write_bytes(payload)
    sig_path.write_bytes(sig_bytes)

    # Verify via python-gnupg (calls underlying gpg --verify)
    with sig_path.open("rb") as f:
        verified = gpg.verify_file(f, str(payload_path))
    assert verified, f"verify failed: status={getattr(verified, 'status', None)!r}"
    assert verified.fingerprint == fingerprint


def test_signer_wrong_passphrase_fails(
    test_keypair: tuple[gnupg.GPG, str], temp_keyring: Path
):
    _gpg, fingerprint = test_keypair
    signer = GPGSigner(
        config=GPGSignerConfig(
            key_id=fingerprint,
            passphrase="WRONG-PASSPHRASE",
            gnupghome=str(temp_keyring),
        )
    )
    with pytest.raises(RuntimeError, match="passphrase|empty signature|without ASCII"):
        signer.sign(b"payload")


def test_signer_unknown_key_fails(temp_keyring: Path):
    """Reference a key that doesn't exist in the keyring."""
    signer = GPGSigner(
        config=GPGSignerConfig(
            key_id="nonexistent-fingerprint-deadbeef",
            passphrase="anything",
            gnupghome=str(temp_keyring),
        )
    )
    with pytest.raises(RuntimeError):
        signer.sign(b"payload")


def test_build_gpg_signer_from_env(
    monkeypatch: pytest.MonkeyPatch, temp_keyring: Path
):
    monkeypatch.setenv("POLARIS_GPG_KEY_ID", "ANY")
    monkeypatch.setenv("GNUPGHOME", str(temp_keyring))
    signer = build_gpg_signer()
    assert isinstance(signer, GPGSigner)
    assert signer.config.key_id == "ANY"
