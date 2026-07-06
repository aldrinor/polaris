# Wave 2b — Minimal independently-entailing citation set (`citation_set_minimizer.py`)

**Issue:** I-deepfix-001 (#1344). **Branch:** `bot/I-wire-001-integration`.
**Scope:** MODULE ONLY. This brief covers the new pure module + its offline tests. Wiring the
module into the render path is a SEPARATE Batch-2 step (`2b-wiring`) and is **not** in this diff.

Grounding: `.codex/I-deepfix-001/REAL_PLAN_2026.md` → `traceability` item 1 ("Minimal
independently-entailing inline set") + item 2 (the corroboration WEIGHT channel) + `gap_vs_polaris`
keep-all-vs-DeepTRACE tension. Reuses the existing `entails_directional` primitive
(`src/polaris_graph/synthesis/consolidation_nli.py:346`) and mirrors the member-shape accessor
conventions of the sibling render-policy module `generator/citation_layer_policy.py`.

---

## 1. What this module decides (and, just as important, what it does NOT)

Given ONE already-verified sentence and the basket members currently cited inline on it, decide
**which members render as inline `[N]` citations and which move to the corroboration WEIGHT
channel** (`_basket_corroboration_block` / CWF surface). It does this in two legs:

1. **PRUNE (Citation-Accuracy leg).** For each member, run
   `entails_directional(premise=member_span, hypothesis=sentence)`. A **confident `False`**
   (the span does not itself carry that sentence) demotes the member out of the inline set into
   the weight channel. A `True` **or** a `None` (infra-unavailable verdict) **KEEPS** the member —
   fail-open: we never drop a citation on model uncertainty. Empty span => KEEP (cannot judge).

2. **MVC-DEMOTE (Source-Necessity leg).** Among the pruning survivors, run a deterministic greedy
   **set-cover / min-vertex-cover** over the statement×source support matrix. The minimal COVER
   set (the load-bearing sources — each uniquely covers a support atom) always stays inline. The
   remaining **same-statement corroborators are MVC-redundant**: their support is already covered.
   A tunable threshold (`PG_MIN_CITE_SET_MAX_INLINE`) decides how many redundant corroborators to
   keep inline; the rest move to the weight channel.

**NOT decided / NOT touched:** no verdict is changed, no source is deleted, no basket is shrunk,
strict_verify / NLI / 4-role D8 / provenance / span-grounding are neither imported nor invoked.
This is a **render-channel placement decision only** — inline-cite vs weight-channel. §-1.3
CONSOLIDATE-keep-all is preserved: the basket keeps ALL members; we only relabel where each renders.

## 2. The keep-all / weight-channel invariant (HARD guarantee, fail-loud test)

The two returned member lists **PARTITION the full input member list**:

```
inline_members  ⊎  weight_members  ==  input members      (multiset equality, nothing lost)
inline_members  ∩  weight_members  ==  ∅
weight_members  ==  pruned_members  ++  demoted_members    (the two demotion reasons)
```

Nothing is deleted. A member demoted to `weight_members` is still a real corroborator that the
CWF surface renders as count + tier weight (§-1.3 WEIGHT-not-citation). This is the ONLY behavioural
contract callers may rely on.

## 3. Faithfulness-neutral argument

- The prune leg only ever **tightens** the inline set (removes a span that does not entail the
  claim) — a pure DeepTRACE Citation-Accuracy win, and it can only REMOVE an inline `[N]`, never
  add one, never change whether the sentence itself is verified.
- The MVC leg never demotes a **load-bearing** source (one in the greedy cover) — dropping a cover
  member would leave a support atom uncited. It only ever demotes members whose support is already
  covered.
- Both demotion classes land in the weight channel (kept + disclosed), never deleted.
- `None`/empty/uncertain => KEEP. Uncertainty never removes a citation.

## 4. The honest DeepTRACE tradeoff (encoded as a tunable, not a hardcode)

Removing a TRUE independent supporter from the inline set **lowers DeepTRACE Citation-Thoroughness
(#8)** while raising Source-Necessity (#6) / precision. So the MVC demotion is **threshold-tuned**,
never forced to a strict singleton:

- `PG_MIN_CITE_SET_MAX_INLINE` = max inline citations kept per sentence when demotion is active.
  **Default `0` = demotion DISABLED (prune-only)** — the safest default: zero thoroughness loss.
  A positive value enables MVC demotion capped at that many inline (`1` = strict singleton-ish;
  the load-bearing cover is always kept, so effective inline ≥ |cover|). Tuned against the offline
  DeepTRACE self-scorer per the plan, NOT a fixed policy.

## 5. Flags (LAW VI — zero hard-coding; env-overridable)

| Env var | Default | Meaning |
|---|---|---|
| `PG_MIN_CITE_SET` | **OFF** (`0`) | Master gate. OFF => identity no-op: `inline == all input members`, `weight == []`, so wiring later is byte-identical when OFF. |
| `PG_MIN_CITE_SET_PRUNE` | ON (when master ON) | The prune-non-entailing leg. OFF => skip pruning (survivors == all members). |
| `PG_MIN_CITE_SET_MAX_INLINE` | `0` | MVC demotion cap. `<=0` => demotion disabled (prune-only). Positive => keep at most this many inline (cover always kept). |
| `PG_MIN_CITE_SET_MARGIN` | blank | Entailment-logit margin forwarded to `entails_directional`; blank => the consolidation-NLI default margin. |

## 6. API (pure functions, no I/O, no LLM except the injectable `entail_fn` seam)

```python
@dataclass(frozen=True)
class MinCiteResult:
    inline_members: list      # the minimal independently-entailing inline citation set
    weight_members: list      # demoted-to-weight-channel members (pruned ++ demoted)
    pruned_members: list      # transparency: span did NOT entail the sentence
    demoted_members: list     # transparency: entailing survivors demoted as MVC-redundant
    enabled: bool
    @property
    def all_members(self) -> list: ...   # inline ++ weight (== input, keep-all)

def minimize_citation_set(
    sentence, members, *,
    spans=None,            # Mapping[ev_id -> span_text]; fallback member.direct_quote
    support_of=None,       # Callable[member -> frozenset[str]] statement×source atoms;
                           #   default = single synthetic atom (whole-statement) -> cover size 1
    entail_fn=None,        # Callable[(premise_span, hypothesis_sentence) -> Optional[bool]];
                           #   default lazily wraps consolidation_nli.entails_directional
    max_inline=None,       # override PG_MIN_CITE_SET_MAX_INLINE for one call
) -> MinCiteResult
```

- Member shape reuses the sibling accessors: `evidence_id`, `origin_cluster_id`,
  `credibility_weight`/`authority_score`, `direct_quote`. Dict- AND object-aware.
- The default `entail_fn` does a **lazy local import** of `entails_directional`, so importing this
  module stays cheap and the OFF identity path imports/loads nothing.
- Greedy set-cover is index-based + deterministic (max-gain, tie-break credibility-weight desc,
  then lowest index) — order-independent and never uses dict `==` for membership.

## 7. Tests (`tests/polaris_graph/generator/test_citation_set_minimizer_wave2b.py`)

Offline. Entailment stub keyed on span text; no GPU, no model download, no OpenRouter spend.

1. **OFF => identity no-op.** `PG_MIN_CITE_SET` unset: `inline == input` (same objects, same order),
   `weight == []`, `enabled is False`. Entail stub asserted NEVER called.
2. **ON prune-non-entailing.** Stub returns `False` for the off-topic span, `True` for the entailing
   one: the non-entailing member lands in `pruned_members`/`weight_members`; the entailing one stays
   inline.
3. **ON `None`-verdict => KEEP (fail-open).** Stub returns `None` (infra unavailable): member stays
   inline, not pruned.
4. **ON MVC-redundant demotion.** 3 entailing same-statement corroborators, `MAX_INLINE=2`:
   the top-weight load-bearing cover member + one kept corroborator stay inline; the lowest-weight
   redundant corroborator moves to `demoted_members`/`weight_members`.
5. **Keep-all invariant.** Across every ON scenario: multiset-by-identity of
   `inline ++ weight == input`, and `inline ∩ weight == ∅`. Nothing lost.
6. **Fail-open on a RAISING entail seam (P1).** An injected `entail_fn` that raises => the member
   is KEPT inline (verdict treated as `None`), the call never propagates the crash.
7. **Default seam swallows a runtime fault (P1).** `entails_directional` monkeypatched to raise:
   `_default_entail_fn` returns `None` (KEEP) — covers the default seam's call path directly.

**P1 fail-open hardening (2b dual-gate REQUEST_CHANGES, Codex+Fable converged).** The prune leg is
fail-open on BOTH seams, defense-in-depth: (a) in `_default_entail_fn` the `entails_directional`
CALL is inside the same `try` as the lazy import, so a runtime fault (malformed-logits IndexError /
signature drift) returns `None`; (b) the `efn(span, sentence)` call in `minimize_citation_set` is
wrapped in `try/except` that logs loud and treats a raise as `None` (KEEP), covering a raising
INJECTED `entail_fn` too. Never `except: pass`. Once wired onto the render path, one uncaught
entailment fault can no longer kill the whole render (the drb_75 crash class).

## 8. Files (this diff)

- NEW `src/polaris_graph/generator/citation_set_minimizer.py`
- NEW `tests/polaris_graph/generator/test_citation_set_minimizer_wave2b.py`

No existing file is edited. No wiring. `git diff --stat` shows only the two new files.
