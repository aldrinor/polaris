#!/usr/bin/env bash
# POLARIS Codex Egress Firewall — restricts a Docker network to a single host:port.
#
# Plan v13 §C-rerun. Used by .github/workflows/codex_verdict_check.yml Phase B
# to lock down the polaris-egress Docker network so the Caddy proxy can ONLY
# reach api.openai.com:443. Even if Codex were prompt-injected to attempt
# exfiltration, network egress is restricted at the iptables layer.
#
# Usage:
#   sudo /usr/local/bin/polaris_egress_firewall.sh <docker_network_name> <allowed_host> <allowed_port>
#
# Example:
#   sudo /usr/local/bin/polaris_egress_firewall.sh polaris-egress api.openai.com 443
#
# Idempotent: re-running with same args is a no-op (rules tagged with
# `--comment polaris-egress-<network>`).

set -euo pipefail

NETWORK="${1:?missing docker network name}"
HOST="${2:?missing allowed host}"
PORT="${3:?missing allowed port}"

# Resolve Docker network bridge name
BRIDGE=$(docker network inspect "$NETWORK" -f '{{ range $k, $v := .Options }}{{ if eq $k "com.docker.network.bridge.name" }}{{ $v }}{{ end }}{{ end }}' 2>/dev/null || true)
if [[ -z "$BRIDGE" ]]; then
    # Fallback: docker auto-generates a bridge name like br-<id>
    NETWORK_ID=$(docker network inspect "$NETWORK" -f '{{ .Id }}' | head -c 12)
    BRIDGE="br-${NETWORK_ID}"
fi

if [[ ! -d "/sys/class/net/${BRIDGE}" ]]; then
    echo "ERROR bridge interface ${BRIDGE} not found for network ${NETWORK}" >&2
    exit 1
fi

# Resolve allowed IPs (host may have multiple A/AAAA records)
ALLOWED_IPS=$(getent ahosts "$HOST" | awk '{print $1}' | sort -u)
if [[ -z "$ALLOWED_IPS" ]]; then
    echo "ERROR cannot resolve $HOST" >&2
    exit 1
fi

COMMENT="polaris-egress-${NETWORK}"

# Clear prior rules with same tag (idempotent)
iptables -S | grep -- "$COMMENT" | sed 's/^-A /-D /' | while read -r rule; do
    # shellcheck disable=SC2086
    iptables $rule 2>/dev/null || true
done

# Default-deny outbound on this bridge (FORWARD chain — packets transiting Docker)
iptables -I FORWARD -i "$BRIDGE" -m comment --comment "$COMMENT" -j DROP

# Allow each resolved IP for the specified port
for ip in $ALLOWED_IPS; do
    iptables -I FORWARD -i "$BRIDGE" -d "$ip" -p tcp --dport "$PORT" \
        -m comment --comment "$COMMENT" -j ACCEPT
done

# Allow established/related (return traffic)
iptables -I FORWARD -i "$BRIDGE" -m state --state ESTABLISHED,RELATED \
    -m comment --comment "$COMMENT" -j ACCEPT

# Allow DNS (UDP 53 to local resolver) — required for Codex to look up api.openai.com
iptables -I FORWARD -i "$BRIDGE" -p udp --dport 53 \
    -m comment --comment "$COMMENT" -j ACCEPT

echo "polaris_egress_firewall: $NETWORK -> $HOST:$PORT enforced"
echo "  bridge: $BRIDGE"
echo "  allowed IPs: $ALLOWED_IPS"
echo "  comment tag: $COMMENT"
