"""GPG detached-signature signer for the bundle manifest.

Per `.codex/slices/slice_004/architecture_proposal.md` §"gpg_signer".

Wraps python-gnupg to produce a detached, ASCII-armored signature
over the manifest YAML. Uses the system gpg binary; the keyring is
either the OS-default (~/.gnupg) or a custom directory pointed to by
GNUPGHOME env var.

Fail-loud per LAW II:
- gpg binary missing → RuntimeError at construction
- Signing key missing or wrong passphrase → RuntimeError with code
- Signing failure → RuntimeError with surfaced gpg stderr

External verifiers run:
    gpg --verify manifest.yaml.asc manifest.yaml
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

try:
    import gnupg
except ImportError as e:  # pragma: no cover
    raise RuntimeError(
        "python-gnupg is required for slice 004 audit-bundle GPG signing"
    ) from e


_LOG = logging.getLogger(__name__)


@dataclass
class GPGSignerConfig:
    key_id: str                        # 'aldrinor@c-polarbiotech.com' or fingerprint
    passphrase: str | None = None      # for non-empty key passphrase
    gnupghome: str | None = None       # custom keyring dir; None = ~/.gnupg
    armor: bool = True


def load_config_from_env() -> GPGSignerConfig:
    """Build config from POLARIS_GPG_KEY_ID + optional POLARIS_GPG_PASSPHRASE.

    Raises RuntimeError if POLARIS_GPG_KEY_ID is unset.
    """
    key_id = os.environ.get("POLARIS_GPG_KEY_ID", "").strip()
    if not key_id:
        raise RuntimeError(
            "POLARIS_GPG_KEY_ID is required to sign audit bundles. Set it "
            "in .env to a key id or fingerprint that exists in the gpg "
            "keyring. Per CLAUDE.md LAW II, this MUST fail loudly."
        )
    passphrase = os.environ.get("POLARIS_GPG_PASSPHRASE", "").strip() or None
    gnupghome = os.environ.get("GNUPGHOME", "").strip() or None
    return GPGSignerConfig(
        key_id=key_id,
        passphrase=passphrase,
        gnupghome=gnupghome,
    )


@dataclass
class GPGSigner:
    """Stateful signer; reuses one gnupg.GPG instance per process."""

    config: GPGSignerConfig

    def __post_init__(self):
        kwargs = {}
        if self.config.gnupghome:
            kwargs["gnupghome"] = self.config.gnupghome
        self._gpg = gnupg.GPG(**kwargs)
        # Sanity check: gpg binary is callable
        try:
            _ = self._gpg.version
        except Exception as exc:
            raise RuntimeError(
                f"gpg binary unavailable or unreadable: {exc!r}"
            ) from exc

    def list_secret_keys(self) -> list[dict]:
        """Useful for diagnostics — what private keys can we sign with."""
        return self._gpg.list_keys(secret=True)

    def sign(self, payload: bytes) -> bytes:
        """Produce detached, ASCII-armored signature over `payload`.

        Returns the .asc bytes (the signature itself, not concatenated
        with the payload). Raises RuntimeError on any signing failure.
        """
        sig = self._gpg.sign(
            payload,
            keyid=self.config.key_id,
            passphrase=self.config.passphrase,
            detach=True,
            clearsign=False,
            binary=not self.config.armor,
        )
        # python-gnupg's Sign object stringifies to the signature; check
        # status to detect failures (sig.status / sig.returncode).
        if not sig:
            raise RuntimeError(
                f"GPG sign returned empty signature for key "
                f"{self.config.key_id!r}; status={getattr(sig, 'status', None)!r}"
            )
        signature = str(sig)
        if "BEGIN PGP SIGNATURE" not in signature:
            raise RuntimeError(
                f"GPG sign produced output without ASCII-armor headers; "
                f"likely passphrase or key issue. status="
                f"{getattr(sig, 'status', None)!r}"
            )
        return signature.encode("utf-8")


def build_gpg_signer() -> GPGSigner:
    """Factory: read env, instantiate signer."""
    return GPGSigner(config=load_config_from_env())
