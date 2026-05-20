#!/usr/bin/env bash
# I-cd-036 (#636) acceptance: redeploy keeps TLS; https://polarisresearch.ca
# resolves, valid cert, no mixed-content, server-side smoke OK.
# Codex iter-1 P2 note: this script does NOT run a headless browser, so
# console-error coverage is OUT-OF-SCOPE here. Browser console-error
# coverage is the Playwright G1-G8 suite (web/tests/e2e/*_g1_g8.spec.ts
# each assert zero console errors per route via page.on('console')).
#
# Run this against the live production domain after operator deploys
# Caddy + DNS-points polarisresearch.ca at polaris-orchestrator VM.
#
# Usage:  bash scripts/verify_production_tls.sh [domain]
#         POLARIS_DOMAIN=polarisresearch.ca bash scripts/verify_production_tls.sh
#
# Exit codes:
#   0   all TLS + smoke checks pass
#   1   any check failed (see stderr)
set -euo pipefail

DOMAIN="${1:-${POLARIS_DOMAIN:-polarisresearch.ca}}"
echo "[verify_production_tls] target: https://${DOMAIN}"

fail=0
check() {
    local label="$1"
    shift
    if "$@"; then
        echo "OK:   $label"
    else
        echo "FAIL: $label" >&2
        fail=1
    fi
}

# 1. DNS A record resolves.
check "DNS A record resolves" bash -c "dig +short ${DOMAIN} | head -1 | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' >/dev/null"

# 2. TLS certificate is valid + not expired + hostname-verified.
# Codex iter-1 P1 fix: -servername only sets SNI; it does NOT verify the
# cert's CN/SAN matches the hostname. Adding -verify_hostname forces
# openssl to enforce hostname verification, which is what we actually
# want for a TLS-correctness check.
check "TLS cert valid + hostname-verified for ${DOMAIN}" bash -c \
    "echo | openssl s_client -servername ${DOMAIN} -connect ${DOMAIN}:443 \
         -verify_hostname ${DOMAIN} -verify_return_error 2>/dev/null \
     | openssl x509 -noout -checkend 86400 2>/dev/null"

# 3. /health returns 200.
check "/health -> 200" bash -c \
    "curl -fsS -o /dev/null -w '%{http_code}' --max-time 10 https://${DOMAIN}/health | grep -q 200"

# 4. / (home) returns 200.
check "/ (home) -> 200" bash -c \
    "curl -fsS -o /dev/null -w '%{http_code}' --max-time 10 https://${DOMAIN}/ | grep -q 200"

# 5. No mixed-content: home HTML must not contain http:// references in
# src/href attributes (excluding XML namespaces + Schema.org URIs).
# Codex iter-1 P1 fix: replaced grep -E (POSIX ERE) with grep -P (PCRE)
# so the negative lookahead '(?!www\\.w3\\.org|schema\\.org)' is actually
# parsed. POSIX ERE rejected the lookahead silently and the leading '!'
# in '! grep ...' made the whole pipeline always succeed.
check "no mixed-content in / (home)" bash -c \
    "! curl -fsS --max-time 10 https://${DOMAIN}/ \
     | grep -P '(src|href)=\"http://(?!www\\.w3\\.org|schema\\.org)' >/dev/null"

# 6. HTTP-on-80 redirects to HTTPS (Caddy default).
check "HTTP/80 redirects to HTTPS" bash -c \
    "curl -sS -o /dev/null -w '%{http_code}' --max-time 10 http://${DOMAIN}/ | grep -qE '^(301|308)$'"

# 7. /transparency reachable (Carney handover acceptance).
check "/transparency -> 200" bash -c \
    "curl -fsS -o /dev/null -w '%{http_code}' --max-time 10 https://${DOMAIN}/transparency | grep -q 200"

if [ "$fail" -eq 1 ]; then
    echo ""
    echo "PRODUCTION TLS VERIFICATION FAILED" >&2
    exit 1
fi
echo ""
echo "PRODUCTION TLS VERIFICATION PASSED"
