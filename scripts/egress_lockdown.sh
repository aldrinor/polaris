#!/bin/bash
# I-carney-003 — install iptables egress lockdown on the host.
#
# Reads /etc/polaris/egress_allowlist.txt and installs rules in BOTH OUTPUT
# (host) and DOCKER-USER (container forwarded traffic) chains so neither
# host nor containers can reach off-allowlist destinations on 80/443.
#
# Idempotent: flushes the POLARIS_EGRESS_HOST + POLARIS_EGRESS_DOCKER chains
# before reapplying. Per Codex iter-2 P1-003: covers BOTH host outbound
# AND Docker-bridge-forwarded container traffic.
#
# Run AFTER the first `docker compose build` (build-time hosts in
# config/egress_allowlist.txt are deb.debian.org / pypi.org / etc).

set -eo pipefail

ALLOWLIST_PATH="${POLARIS_EGRESS_ALLOWLIST:-/etc/polaris/egress_allowlist.txt}"
LOG_FILE="${POLARIS_EGRESS_LOG:-/var/log/polaris-egress.log}"

if [ ! -f "$ALLOWLIST_PATH" ]; then
    echo "[egress] ERROR: allowlist file not found at $ALLOWLIST_PATH" >&2
    echo "[egress] copy config/egress_allowlist.txt → $ALLOWLIST_PATH first" >&2
    exit 1
fi

if [ "$(id -u)" -ne 0 ]; then
    echo "[egress] ERROR: must run as root (uses iptables)" >&2
    exit 1
fi

log() {
    local ts
    ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    echo "[$ts] $*" | tee -a "$LOG_FILE"
}

# Resolve allowlist domains to unique A records.
resolve_allowlist() {
    local domain ip
    while IFS= read -r domain; do
        # Skip blanks + comments.
        [[ -z "$domain" || "$domain" =~ ^# ]] && continue
        # getent returns "ip canonical alias" lines; awk picks the first column.
        while IFS= read -r ip; do
            [ -n "$ip" ] && echo "$ip"
        done < <(getent ahostsv4 "$domain" 2>/dev/null | awk '{print $1}' | sort -u)
    done < "$ALLOWLIST_PATH" | sort -u
}

install_chain() {
    local chain_name="$1"
    local parent_chain="$2"
    local resolved="$3"

    log "installing chain $chain_name into $parent_chain"

    # (Re)create the chain.
    iptables -F "$chain_name" 2>/dev/null || iptables -N "$chain_name"

    # Allow loopback + established + related.
    iptables -A "$chain_name" -o lo -j ACCEPT || true
    iptables -A "$chain_name" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

    # Allow DNS (53), NTP (123), AWS instance metadata (169.254.169.254).
    iptables -A "$chain_name" -p udp --dport 53 -j ACCEPT
    iptables -A "$chain_name" -p tcp --dport 53 -j ACCEPT
    iptables -A "$chain_name" -p udp --dport 123 -j ACCEPT
    iptables -A "$chain_name" -d 169.254.169.254/32 -j ACCEPT

    # Allow allowlisted IPs on 443 + 80.
    while IFS= read -r ip; do
        [ -z "$ip" ] && continue
        iptables -A "$chain_name" -d "$ip" -p tcp --dport 443 -j ACCEPT
        iptables -A "$chain_name" -d "$ip" -p tcp --dport 80 -j ACCEPT
    done <<< "$resolved"

    # Drop everything else on 80/443.
    iptables -A "$chain_name" -p tcp --dport 443 -j LOG --log-prefix "[POLARIS-EGRESS-DROP] "
    iptables -A "$chain_name" -p tcp --dport 443 -j DROP
    iptables -A "$chain_name" -p tcp --dport 80 -j LOG --log-prefix "[POLARIS-EGRESS-DROP] "
    iptables -A "$chain_name" -p tcp --dport 80 -j DROP

    # Wire the chain into the parent if not already done.
    if ! iptables -C "$parent_chain" -j "$chain_name" 2>/dev/null; then
        iptables -I "$parent_chain" 1 -j "$chain_name"
    fi

    log "chain $chain_name installed with $(echo "$resolved" | wc -l) allowed IPs"
}

main() {
    log "egress lockdown starting (allowlist=$ALLOWLIST_PATH)"
    local resolved
    resolved=$(resolve_allowlist)
    if [ -z "$resolved" ]; then
        echo "[egress] ERROR: allowlist resolved to zero IPs" >&2
        exit 1
    fi

    # Host outbound.
    install_chain "POLARIS_EGRESS_HOST" "OUTPUT" "$resolved"

    # Container forwarded (Docker bridge). DOCKER-USER may not exist on
    # systems without Docker; create it as a no-op if absent.
    if ! iptables -L DOCKER-USER >/dev/null 2>&1; then
        iptables -N DOCKER-USER 2>/dev/null || true
        iptables -I FORWARD 1 -j DOCKER-USER 2>/dev/null || true
    fi
    install_chain "POLARIS_EGRESS_DOCKER" "DOCKER-USER" "$resolved"

    log "egress lockdown complete"
}

main "$@"
