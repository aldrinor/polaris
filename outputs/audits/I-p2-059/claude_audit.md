# Claude architect audit — I-p2-059 (#865): Audit & export page S-audit

## Goal
Third secondary page in the post-journey frontier pass: /runs/[runId]/audit — the compliance/export
surface (integrity manifest + pipeline gate ledger + two-family provenance + download). It is a
SERVER component that renders the REAL canonical signed bundle from web/public via loadBundle, so —
unlike the API-gated pages — its populated state is genuinely live-verifiable at
/runs/v1-canonical/audit. Audited by rendering that route directly (no mock).

## What looking-at-it found
The page was already well-built and exemplary on honesty (LAW II): it never claims a GPG seal that
isn't on disk (presence check → "verify with gpg", not "signed"); the gate ledger is composed only
from real verified_report fields; the export copy is honest about the JSON snapshot vs the
byte-preserving signed package. Gaps were purely presentation: the section cards + the two tables
were flat `rounded-lg border`; and on mobile the gate-ledger detail column + the manifest bytes/SHA
columns clipped under horizontal scroll — unacceptable for a COMPLIANCE surface where the gate
reason + the integrity hash must be readable (Codex visual iter-1 P1).

## What changed (1 page file + tracker)
- brand-tinted `shadow-card` + `rounded-xl` on the section cards + both table wrappers.
- Both tables made RESPONSIVE: dense table on sm+ (hidden < sm), stacked cards on mobile. Gate
  ledger mobile card = gate name + status pill + FULL detail (abort reason, threshold, lineage
  wrapping). Manifest mobile card = file path + type/bytes + the FULL SHA-256 (the integrity proof)
  wrapping. Nothing clipped.

## Honest data note
The real canonical demo bundle is an ABORT bundle (abort_no_verified_sections), so the gate ledger
honestly renders Pipeline verdict FAIL / Strict-verify FAIL (0%) / Two-family segregation PASS —
the correct, honest story: the gates caught the unverified claims and refused to ship them. The UI
faithfully renders the bundle; no fabricated gate data.

## Dual Codex gate
- Brief APPROVE. Visual `-i` APPROVE iter-2 (desktop A / mobile A-). Code diff APPROVE.

## Verification state
The populated state is LIVE-verifiable (server-rendered from the public canonical bundle); it was
verified at /runs/v1-canonical/audit. (Per-run audit pages for a fresh real run still need a bundle
on disk + creds — that path is the deferred one.)

## Constraints honored
Brand `#c8102e` (download CTA only); StatusPill = verified/refusal tokens; tokens only; loadBundle +
honest signature branch + gate composition + testid preserved; no fabricated SHIPPED data.

canonical-diff-sha256: e908040528abbb64a345d305dabf2ffb540f3f5a149c776751e9557aa378838a
