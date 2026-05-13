#!/bin/bash
# I-carney-005 — bootstrap the POLARIS Carney demo GPG signing key.
#
# Idempotent: detects existing key under stable UID and exits 0 without
# duplicating it. Generates an ed25519 signing-only subkey suitable for
# signing audit bundles (no encryption, no certification).
#
# On success:
#   - writes the fingerprint to state/polaris_gpg_keyid.txt
#   - exports the public key to outputs/polaris_demo_pubkey.asc
#   - prints the env var the operator must export

set -euo pipefail

KEY_UID="POLARIS Carney Demo <signing@polaris.local>"
KEY_NAME_SHORT="POLARIS Carney Demo"
GNUPGHOME="${GNUPGHOME:-$HOME/.gnupg-polaris}"
STATE_FILE="state/polaris_gpg_keyid.txt"
PUBKEY_FILE="outputs/polaris_demo_pubkey.asc"

mkdir -p "$GNUPGHOME"
chmod 700 "$GNUPGHOME"
export GNUPGHOME

# Idempotence check: does a key with our UID already exist?
EXISTING_FPR=$(gpg --list-keys --with-colons "$KEY_NAME_SHORT" 2>/dev/null \
    | awk -F: '/^fpr:/ {print $10; exit}')

if [ -n "$EXISTING_FPR" ]; then
    echo "[bootstrap_gpg] key already present (fpr=$EXISTING_FPR); skipping generation"
else
    echo "[bootstrap_gpg] generating ed25519 signing-only key for ${KEY_UID}"
    BATCH_FILE=$(mktemp)
    cat > "$BATCH_FILE" <<EOF
%no-protection
Key-Type: EDDSA
Key-Curve: ed25519
Key-Usage: sign
Name-Real: POLARIS Carney Demo
Name-Email: signing@polaris.local
Name-Comment: Carney demo bundle signing
Expire-Date: 1y
%commit
EOF
    gpg --batch --gen-key "$BATCH_FILE"
    rm -f "$BATCH_FILE"
    EXISTING_FPR=$(gpg --list-keys --with-colons "$KEY_NAME_SHORT" \
        | awk -F: '/^fpr:/ {print $10; exit}')
    if [ -z "$EXISTING_FPR" ]; then
        echo "[bootstrap_gpg] ERROR: key generation succeeded but fingerprint not found" >&2
        exit 2
    fi
    echo "[bootstrap_gpg] generated key fpr=$EXISTING_FPR"
fi

# Write fingerprint + public key (idempotent overwrite).
mkdir -p "$(dirname "$STATE_FILE")" "$(dirname "$PUBKEY_FILE")"
echo "$EXISTING_FPR" > "$STATE_FILE"
gpg --armor --export "$EXISTING_FPR" > "$PUBKEY_FILE"

echo ""
echo "=================================================================="
echo "POLARIS Carney demo signing key ready."
echo ""
echo "  Fingerprint : $EXISTING_FPR"
echo "  GNUPGHOME   : $GNUPGHOME"
echo "  Fingerprint file : $STATE_FILE"
echo "  Public key        : $PUBKEY_FILE"
echo ""
echo "Next steps:"
echo "  1. Add to .env:"
echo "       POLARIS_GPG_KEY_ID=$EXISTING_FPR"
echo "       POLARIS_GPG_HOMEDIR=$GNUPGHOME"
echo "  2. Bring up the stack:"
echo "       docker compose -f docker-compose.v6.yml up -d"
echo "  3. Verify:"
echo "       curl http://localhost:8000/health"
echo "=================================================================="
