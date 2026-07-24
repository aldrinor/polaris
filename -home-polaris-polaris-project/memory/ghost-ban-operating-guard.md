---
name: ghost-ban-operating-guard
description: Standing guard so Sol/Fable never drift into overfit/faith-ghost/post-gen-fix again; two-model rule + mechanical audit
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 21e87760-8436-4090-870d-99ef2121882e
---

Standing operating guard (established 2026-07-24 after the Wave-1 drift). The Wave-1 build gates ran SOLO-SOL for
5 rounds and drifted into the HARD-BANNED apparatus (runtime licensed-inference admission canary + OPERATOR_LICENSE
entailment predicate + exact emitted==admitted binding across ~27 routes + non-scoreable-on-mismatch suppression).
Operator caught it. Root causes: (1) I consolidated a Sol escalation into a charter clause that CONTRADICTED
Fable's own "no entailment machinery" rule; (2) I dropped Fable from the build gate, so nobody invoked the ban.

**Why:** Sol is a correctness-maximizer with no scar tissue — it will re-derive the entailment/admission/post-gen
apparatus every time "for correctness" unless actively fenced. The bans ([[no-entailment-ever-rule]],
[[no-post-generation-fix-rule]]) cost the operator months and damage RACE.

**How to apply (every time, going forward):**
- **TWO-MODEL always.** Every design AND every code diff is gated by BOTH Fable and Sol — NEVER solo. Fable
  authored "no entailment machinery" and is the counterweight to Sol's drift.
- **Prepend `docs/race_fact_initiative/GHOST_BAN.md`** to every Sol/Fable brief. It enumerates the 3 banned
  families (overfit / faith-ghost / post-gen-fix), the positive pre-generation-only rule, the drop-lever default,
  and the audit.
- **Opus runs the mechanical audit on EVERY verdict/spec/diff before accepting:**
  `grep -inE 'admission|canary|entail|nli|licens|binding|premise|operator[_ -]?licen|non[_ -]?scoreable|scoreab|suppress|fail[_ -]?closed|admitted|emitted[_ =]|reasoning operator|analyticalcontract'`
  — every hit must be a REJECTION/naming-to-exclude, never a proposal — plus 5 structural checks (no emitted-vs-
  stored-text compare; no content-dropping predicate between producer and render except the token-identity layout
  normalizer; no engine import; deterministic checks live under tests/ and no generation-path reader; no dataclass
  with premise-IDs/admitted-tokens/marker-bindings/reasoning-operators).
- **Opus HOLDS THE BAN over Sol's correctness pushback** — if Sol proposes an apparatus "for correctness", REJECT
  and apply the clean pre-gen form or DROP the lever. Never gate-obey ([[two-way-iteration-rule]]).
- **Clean lever = pre-generation prompt/scope/plan-text change reaching the active writer + the EXISTING
  faithfulness engine untouched + deterministic TESTS (ship decision, not runtime gates). If not clean → DROP.**

Verified working 2026-07-24: with GHOST_BAN in the brief, BOTH Fable and Sol phase4b verdicts audited clean and
independently built their own reviewer grep-audits. Part of [[race-fact-investigation-initiative]].
