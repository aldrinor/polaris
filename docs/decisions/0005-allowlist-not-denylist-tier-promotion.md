# 0005. Promote source tiers by allowlist; default everything else to the safe tier

Status: accepted

Date: 2026-04-19

## Context

The tier classifier tried to earn the top tier (T1) by blocklisting low-provenance domains. Across passes 9-13 (2026-04-19) that never converged: an adversarial reviewer kept finding new domains the classifier wrongly promoted to T1 — Facebook, Reddit, UpToDate, CMS.gov, think-tanks, trade press. A denylist assumes the set of bad inputs is finite and enumerable; the open web breaks that assumption, so blocklisting is unwinnable whack-a-mole.

Separately, Serper truncated result titles, hiding "Systematic Review and Meta-Analysis" suffixes; full titles were recovered from OpenAlex `display_name` plus DOI extraction (M-12/M-13).

## Decision

Stop enumerating bad domains. Require membership in a known-good allowlist to earn the high tier: a domain gets T1 only if it is on `PEER_REVIEWED_JOURNAL_DOMAINS` or NIH hosts, otherwise it defaults to T4 (M-11). Default every unknown domain to the safe (narrative) tier rather than trusting it.

## Consequences

- False promotions are eliminated: an unknown domain can never sneak into T1, which is the failure mode that could put a bot page or a press release next to a randomized trial.
- The trade is rare false demotions — a genuinely authoritative but not-yet-listed host lands at T4 until added. Under a WEIGHT-not-FILTER pipeline (ADR 0006) that source still flows through, just at lower weight, so the cost is bounded.
- This convergence took five blocked reviewer passes; the lesson is general — when a denylist will not converge, flip to default-deny.
- The allowlist is data, not code, so it can be extended per field without touching logic. Note that ADR 0010 later generalizes credibility scoring away from any fixed host list; this allowlist is the clinical-view floor, not the whole credibility model.
