# Claude audit — I-cd-036 (#636)

`scripts/verify_production_tls.sh`: 7 mechanical TLS + smoke checks (DNS A, cert valid + hostname-verified, /health, /, mixed-content PCRE, HTTP→HTTPS redirect, /transparency). Codex iter-1 P1 fixes folded in (hostname verify via -verify_hostname; mixed-content via grep -P PCRE; console-error scope clarified). Caddy + Let's Encrypt substrate is already in repo (I-rdy-015 / #511). Operator-action follow-up #699 holds domain procurement + DNS + cert provisioning.
