"""GPG detached-signature path for the v6 orchestrator-state backup
(GH #547, I-rdy-016-followup).

Subprocess-drives `scripts/v6/backup_orchestrator_state.py` end-to-end against
an ephemeral GPG keyring (throwaway keys generated per test), the same
hermetic pattern as `tests/polaris_graph/audit_bundle/test_gpg_signer.py`.
Skips cleanly when the host gpg binary / gpg-agent is unavailable.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import gnupg
import pytest

from polaris_v6.queue import run_store

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "v6" / "backup_orchestrator_state.py"

# GPG-related env vars stripped from every subprocess env so a parent-process
# / .env value can never leak into a test that expects them unset.
_GPG_ENV = ("POLARIS_GPG_KEY_ID", "POLARIS_GPG_PASSPHRASE", "GNUPGHOME")
_PASSPHRASE = "test-passphrase"


# ---------- Skip when gpg unavailable ----------

def _gpg_callable() -> bool:
    try:
        _ = gnupg.GPG().version
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _gpg_callable(),
    reason="system gpg binary not available — skipping GPG backup-signing tests",
)


# ---------- Fixtures ----------

def _gen_key(gpg: gnupg.GPG, email: str) -> str:
    """Generate one throwaway RSA key in `gpg`'s keyring; return its fingerprint."""
    key = gpg.gen_key(
        gpg.gen_key_input(
            name_real="POLARIS Backup Test",
            name_email=email,
            key_type="RSA",
            key_length=2048,
            passphrase=_PASSPHRASE,
            expire_date=0,
        )
    )
    if not key.fingerprint:
        pytest.skip(
            f"gpg key generation unavailable in this env (gpg-agent issue?); "
            f"stderr={key.stderr!r}"
        )
    return str(key.fingerprint)


@pytest.fixture
def keyring(tmp_path: Path) -> tuple[Path, str]:
    """An ephemeral GNUPGHOME holding one test signing key — (home, fingerprint)."""
    home = tmp_path / "gnupg"
    home.mkdir(mode=0o700)
    gpg = gnupg.GPG(gnupghome=str(home))
    return home, _gen_key(gpg, "backup-signer@polaris.local")


# ---------- Helpers ----------

def _build_db(db: Path, artifact_root: Path, run_ids: list[str]) -> None:
    """Build a genuine run-store DB + artifact dirs via the real run_store API."""
    db.parent.mkdir(parents=True, exist_ok=True)
    for run_id in run_ids:
        run_store.insert_run(
            run_id, "clinical_efficacy", f"Question {run_id}", path=str(db)
        )
        adir = artifact_root / run_id
        adir.mkdir(parents=True)
        (adir / "manifest.json").write_text(
            json.dumps({"run_id": run_id}), encoding="utf-8"
        )
        run_store.set_pipeline_meta(run_id, artifact_dir=str(adir), path=str(db))
        run_store.mark_completed(run_id, {"ok": True}, path=str(db))


def _run(
    *args: str,
    extra_env: dict[str, str] | None = None,
    drop_env: tuple[str, ...] = (),
) -> subprocess.CompletedProcess[str]:
    """Subprocess-drive the backup script with an explicitly-built child env."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    for key in drop_env:
        env.pop(key, None)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _backup(
    tmp_path: Path,
    *,
    extra_env: dict[str, str] | None = None,
    drop_env: tuple[str, ...] = (),
) -> Path:
    """Run `backup` against a fresh fixture DB; return the produced archive."""
    db = tmp_path / "state" / "v6_runs.sqlite"
    artifact_root = tmp_path / "outputs" / "v6_runs"
    dest = tmp_path / "backups"
    _build_db(db, artifact_root, ["run-aaa"])
    result = _run(
        "backup",
        "--db", str(db),
        "--artifact-root", str(artifact_root),
        "--dest", str(dest),
        extra_env=extra_env,
        drop_env=drop_env,
    )
    assert result.returncode == 0, f"backup failed: {result.stderr}"
    archives = list(dest.glob("polaris_v6_state_*.tar.gz"))
    assert len(archives) == 1, archives
    return archives[0]


def _restore_db(tmp_path: Path) -> Path:
    return tmp_path / "state" / "v6_runs.sqlite"


def _wipe_live_state(tmp_path: Path) -> None:
    shutil.rmtree(tmp_path / "state", ignore_errors=True)
    shutil.rmtree(tmp_path / "outputs", ignore_errors=True)


# ---------- Tests ----------

def test_backup_signs_when_key_set(tmp_path: Path, keyring: tuple[Path, str]):
    """`backup` writes `<archive>.asc` when POLARIS_GPG_KEY_ID is set."""
    home, fingerprint = keyring
    archive = _backup(
        tmp_path,
        extra_env={
            "POLARIS_GPG_KEY_ID": fingerprint,
            "GNUPGHOME": str(home),
            "POLARIS_GPG_PASSPHRASE": _PASSPHRASE,
        },
    )
    asc = archive.parent / f"{archive.name}.asc"
    assert asc.is_file(), "backup did not write the .asc detached signature"
    assert asc.read_bytes(), ".asc signature file is empty"
    assert b"PGP SIGNATURE" in asc.read_bytes()


def test_backup_no_asc_when_key_unset(tmp_path: Path):
    """`backup` no-ops to sha256-only when POLARIS_GPG_KEY_ID is unset."""
    archive = _backup(tmp_path, drop_env=_GPG_ENV)
    asc = archive.parent / f"{archive.name}.asc"
    assert not asc.exists(), "an unsigned backup must not produce a .asc"
    # sha256 tamper-evidence is still present.
    assert (archive.parent / f"{archive.name}.sha256").is_file()


def test_restore_verify_sig_passes_on_good_signature(
    tmp_path: Path, keyring: tuple[Path, str]
):
    """`restore --verify-sig` succeeds against a genuine signature."""
    home, fingerprint = keyring
    archive = _backup(
        tmp_path,
        extra_env={
            "POLARIS_GPG_KEY_ID": fingerprint,
            "GNUPGHOME": str(home),
            "POLARIS_GPG_PASSPHRASE": _PASSPHRASE,
        },
    )
    _wipe_live_state(tmp_path)
    # POLARIS_GPG_KEY_ID intentionally unset for restore — any valid signature
    # from a public key in the keyring is accepted.
    result = _run(
        "restore", "--archive", str(archive), "--db", str(_restore_db(tmp_path)),
        "--verify-sig",
        extra_env={"GNUPGHOME": str(home)},
        drop_env=_GPG_ENV,
    )
    assert result.returncode == 0, (
        f"restore --verify-sig failed on a good signature: {result.stderr}"
    )


def test_restore_verify_sig_fails_on_absent_signature(tmp_path: Path):
    """`restore --verify-sig` fails loud when no `.asc` accompanies the archive."""
    archive = _backup(tmp_path, drop_env=_GPG_ENV)  # unsigned — no .asc
    _wipe_live_state(tmp_path)
    result = _run(
        "restore", "--archive", str(archive), "--db", str(_restore_db(tmp_path)),
        "--verify-sig",
        drop_env=_GPG_ENV,
    )
    assert result.returncode != 0, "must fail when the .asc is absent"
    assert ".asc" in result.stderr or "signature" in result.stderr.lower()


def test_restore_verify_sig_fails_on_bad_signature(
    tmp_path: Path, keyring: tuple[Path, str]
):
    """`restore --verify-sig` fails loud on a corrupted signature file."""
    home, fingerprint = keyring
    archive = _backup(
        tmp_path,
        extra_env={
            "POLARIS_GPG_KEY_ID": fingerprint,
            "GNUPGHOME": str(home),
            "POLARIS_GPG_PASSPHRASE": _PASSPHRASE,
        },
    )
    asc = archive.parent / f"{archive.name}.asc"
    # Truncate the armored signature to half — guaranteed unverifiable.
    original = asc.read_bytes()
    asc.write_bytes(original[: len(original) // 2])
    _wipe_live_state(tmp_path)
    result = _run(
        "restore", "--archive", str(archive), "--db", str(_restore_db(tmp_path)),
        "--verify-sig",
        extra_env={"GNUPGHOME": str(home)},
        drop_env=_GPG_ENV,
    )
    assert result.returncode != 0, "must fail on a corrupted .asc"
    assert (
        "verif" in result.stderr.lower() or "fail" in result.stderr.lower()
    ), result.stderr


def test_restore_verify_sig_fails_on_wrong_key(
    tmp_path: Path, keyring: tuple[Path, str]
):
    """A valid signature from an unexpected key is rejected when
    POLARIS_GPG_KEY_ID pins a different key."""
    home, fingerprint_a = keyring
    # A second key in the same keyring.
    gpg = gnupg.GPG(gnupghome=str(home))
    fingerprint_b = _gen_key(gpg, "other-signer@polaris.local")
    assert fingerprint_b != fingerprint_a

    archive = _backup(
        tmp_path,
        extra_env={
            "POLARIS_GPG_KEY_ID": fingerprint_a,
            "GNUPGHOME": str(home),
            "POLARIS_GPG_PASSPHRASE": _PASSPHRASE,
        },
    )
    _wipe_live_state(tmp_path)
    # Restore expecting key B — the signature is cryptographically valid but
    # from key A, so the expected-key check must reject it.
    result = _run(
        "restore", "--archive", str(archive), "--db", str(_restore_db(tmp_path)),
        "--verify-sig",
        extra_env={"GNUPGHOME": str(home), "POLARIS_GPG_KEY_ID": fingerprint_b},
        drop_env=_GPG_ENV,
    )
    assert result.returncode != 0, (
        "restore --verify-sig must reject a valid signature from an unexpected key"
    )
    assert "unexpected key" in result.stderr.lower(), result.stderr
