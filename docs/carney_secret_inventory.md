# Carney demo — secret inventory, custody, rotation, teardown

**G13 / 7-day-prep.** Single-page registry of every secret the Carney demo
touches. Custodian + storage + rotation + revocation + post-demo teardown
per secret. Read before the deploy; execute the teardown column after the
demo window closes.

**Demo window:** 2026-06-05 to 2026-06-09. **Teardown target:** by 2026-06-15.

---

## Secrets

| # | Secret | What it is | Where it lives | Custodian | Rotation / revocation | Post-demo teardown |
|---|---|---|---|---|---|---|
| 1 | `POLARIS_GPG_KEY_ID` + private key | ed25519 demo bundle-signing key (`POLARIS Carney Demo <signing@polaris.local>`) | Operator workstation `~/.gnupg-polaris`; imported into Vexxhost VM `/var/lib/polaris/gpg` by `provision.sh`; private armored copy in the encrypted offline bundle (#7) | Ops | Single-purpose demo key, 1y expiry. If leaked: `gpg --gen-revoke`, publish revocation, re-bootstrap via `scripts/bootstrap_gpg_demo_key.sh`, re-sign any live bundles | `gpg --delete-secret-keys` on VM + workstation; shred the offline bundle copy. Public key may stay published (it's public). |
| 2 | `POLARIS_JWT_SECRET` | HS256 signing secret for the 12h session JWTs | Vexxhost VM `/root/.env` → `/opt/polaris/.env`; NOT in git (.env gitignored) | Ops | 64-byte url-safe random (`secrets.token_urlsafe(48)`). Rotating invalidates all live sessions — fine between demo days, not mid-session. If leaked: rotate + restart `api`+`worker` | Delete `/opt/polaris/.env` when the VM is destroyed |
| 3 | `static_accounts.yaml` | bcrypt-hashed (rounds=12) reviewer + ops credentials (`carney_office`, `ops`) | Vexxhost VM `/etc/polaris/static_accounts.yaml` (640 root:root); bcrypt hashes only — plaintext passwords never stored | Ops | Plaintext demo passwords held by Ops out-of-band (password manager). If leaked: re-hash new passwords, `scp` new file, restart `api` | Delete `/etc/polaris/static_accounts.yaml` on VM destroy |
| 4 | `OPENROUTER_API_KEY` | OpenRouter LLM API key (transition backend until OVH H200 vLLM lands) | `/opt/polaris/.env` on VM; operator workstation `.env` for the fallback laptop | Ops | OpenRouter dashboard → revoke + reissue. **Rotate after the demo** — it was exposed in a Codex audit file during I-carney-008 review (commit later redacted; key still live until rotated). | Revoke the key in the OpenRouter dashboard at teardown |
| 5 | `SERPER_API_KEY` | Serper web-search API key (US provider, disclosed per I-carney-010) | `/opt/polaris/.env` on VM; operator workstation `.env` | Ops | serper.dev dashboard → regenerate. Low blast radius (search only, no confidential data) | Optionally revoke at teardown; low urgency |
| 6 | `SEMANTIC_SCHOLAR_API_KEY` | Semantic Scholar bib API key (optional; blank-able) | `/opt/polaris/.env` on VM | Ops | Optional key — if absent, retrieval still works at a lower rate limit | n/a |
| 7 | `polaris_demo_secrets.tar.gz.gpg` | Encrypted offline bundle: `.env` + `static_accounts.yaml` + GPG private key, for the §5 fallback-laptop path | Operator YubiKey + a paper backup; decrypted only transiently on the fallback laptop, then `shred`-ed | Ops | Encrypted with the operator's PERSONAL GPG key (not the demo signing key — different keyring). If the YubiKey is lost: regenerate every secret inside it (#1-#3) | Shred the bundle + the YubiKey copy after the demo window |
| 8 | OVH Canada account + API token | OVH Manager login + (if used) OVH API token for the H200 server | OVH Manager; operator password manager | Ops | OVH Manager → API token revocation; account password rotation per OVH policy | Keep the account; cancel the H200 server lease per §8 teardown if not doing Phase-2 |
| 9 | Vexxhost account + OpenStack creds | Vexxhost Manager login + OpenStack `clouds.yaml` / app credentials | Vexxhost Manager; operator password manager | Ops | Vexxhost console → rotate app credentials | `openstack server delete polaris-carney`; keep or close the account |
| 10 | DNS registrar account | easyDNS / CIRA-registrar login for the demo domain | Registrar; operator password manager | Ops | Registrar console password rotation | Keep the domain; remove the `polaris.<domain>` A/AAAA records at teardown |
| 11 | GitHub PATs (`sotaleung-wec`, `aldrinor`) | Bot push + admin-merge tokens for the autonomous PR flow | `gh` keyring on the build machine | Ops | GitHub → Settings → Developer settings → revoke + reissue | Not demo-window-scoped; rotate on the normal cadence |

---

## Rotation priority after the demo

1. **`OPENROUTER_API_KEY` (#4) — rotate first.** It was briefly exposed in a Codex audit artifact during the I-carney-008 review. The leak commit was history-rewritten before push (the key never reached origin), but the key itself is still live. Revoke + reissue in the OpenRouter dashboard.
2. Everything else is single-purpose demo material — rotate or destroy per the teardown column; no urgency unless leaked.

## What is NOT a secret (do not treat as one)

- `outputs/polaris_demo_pubkey.asc` — the GPG **public** key. It is meant to be published (served from `/transparency/pubkey.asc`); reviewers need it to verify bundles.
- `config/egress_allowlist.txt`, `config/static_accounts.example.yaml` — templates with placeholders, safe to commit.
- The demo `git_commit` SHA, `provider`, `region` surfaced by `/transparency` — public deploy provenance by design.

## Teardown checklist (run after 2026-06-15)

- [ ] Revoke `OPENROUTER_API_KEY` (#4) in the OpenRouter dashboard
- [ ] `openstack server delete polaris-carney` (Vexxhost)
- [ ] Cancel or retain the OVH H200 lease (retain only for Phase-2 work)
- [ ] Remove `polaris.<domain>` A/AAAA DNS records
- [ ] `gpg --delete-secret-keys` for the demo signing key on VM + workstation
- [ ] `shred` the `polaris_demo_secrets.tar.gz.gpg` bundle + YubiKey copy
- [ ] Confirm `/opt/polaris/.env` + `/etc/polaris/` are gone with the VM
