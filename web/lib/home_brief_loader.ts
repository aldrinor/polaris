// I-ux-001c (#878) sub-PR 2: server-side loader for the Home page's
// proof-as-CTA card.
//
// Returns the FIRST verified sentence from the canonical signed bundle that:
//   1. The verifier actually passed (s.verifier_pass === true)
//   2. Resolves to a real, non-trivial source span (quote.trim().length > 40)
//
// Honest-fail rules (LAW II):
//   - If the bundle file doesn't load (missing fixture / FS error), returns
//     { bundle_loaded: false, ... } with empty fields. The UI MUST render the
//     "bundle still loading" fallback copy, NOT a fabricated number stamp.
//   - If the bundle loads but NO sentence resolves to a real span, also
//     returns bundle_loaded: false (the home page must not lie about a
//     verified claim that doesn't actually exist).
//   - Numerics shown in the footer are the bundle's actual matched-numerics
//     count, never a synthesized total.
//
// Mirrors the data-fetch logic from `web/app/components/proof_showcase.tsx`
// (I-p2-037 #794), but returns plain data (not JSX) so the v6 visual
// treatment in `proof_as_cta.tsx` is a pure renderer.
import { resolveSpan } from "@/lib/evidence_span";
import { loadBundle } from "@/lib/inspector_bundle_loader";

const DEMO_RUN_ID = "v1-canonical-success";

/** Per-certainty foreground/background pair for the verified-claim card. */
export interface HomeBrief {
  bundle_loaded: boolean;
  /** Stable demo run id; used to deep-link the proof-as-CTA card. */
  run_id: string;
  /** The research question the brief is answering, e.g. "What did the SURPASS
   * trial show on HbA1c reduction for tirzepatide?" — null when no bundle. */
  research_question: string | null;
  /** The verified sentence (the claim). null when no claim resolves. */
  claim: string | null;
  /** The cited primary-source passage exactly as it appears in the source. */
  span_quote: string | null;
  /** Source metadata. All fields nullable — honest-fail (LAW II). */
  source: {
    journal: string | null;
    year: number | null;
    title: string | null;
    url: string | null;
    tier: string | null;
  };
  /** Numerics extracted from the claim sentence (the "of <total>" denominator). */
  total_numerics: number;
  /** Numerics that actually appear in the cited span (the "matched <N>"
   * numerator). 0 when the claim has no numerics — UI renders a
   * non-numeric verified copy in that case. */
  matched_numerics: number;
  /** Tri-state signature state from the bundle loader.
   * `gpg_verified` is the ONLY state that may render the green
   * "Signed bundle" pill (Codex iter-1 P1-002 on the Inspector sub-PR
   * carry-forward; reapplied here on the Home card per design_tokens_v2
   * §2.2 — faithfulness greens are reserved for the verified state). */
  signature_state: "missing" | "present_unverified" | "gpg_verified";
}

function tierLabel(tier: unknown): string | null {
  if (typeof tier === "string" && tier) return tier;
  if (typeof tier === "number") return `T${tier}`;
  return null;
}

function lookupPoolField(
  pool: unknown,
  sourceId: string,
  field: string,
): unknown {
  if (!pool || typeof pool !== "object") return null;
  const p = pool as { entries?: unknown[]; sources?: unknown[] };
  const arr: unknown[] = Array.isArray(p.sources)
    ? p.sources
    : Array.isArray(p.entries)
      ? p.entries
      : [];
  for (const entry of arr) {
    if (!entry || typeof entry !== "object") continue;
    const e = entry as Record<string, unknown>;
    if (e.source_id === sourceId) {
      const md = e.metadata;
      if (md && typeof md === "object") {
        const v = (md as Record<string, unknown>)[field];
        if (v !== undefined) return v;
      }
      const top = e[field];
      return top === undefined ? null : top;
    }
  }
  return null;
}

function extractNumerics(text: string): string[] {
  const matches = text.match(
    /[−-]?\d+(?:\.\d+)?(?:%|\s*percentage\s+points?)?/g,
  );
  return matches ? matches : [];
}

function countMatchesIn(needles: string[], haystack: string): number {
  let n = 0;
  for (const needle of needles) {
    if (needle.length > 0 && haystack.includes(needle)) n += 1;
  }
  return n;
}

/** Empty/honest-fail shape returned when no real verified claim can be shown. */
function emptyBrief(): HomeBrief {
  return {
    bundle_loaded: false,
    run_id: DEMO_RUN_ID,
    research_question: null,
    claim: null,
    span_quote: null,
    source: { journal: null, year: null, title: null, url: null, tier: null },
    total_numerics: 0,
    matched_numerics: 0,
    signature_state: "missing",
  };
}

export async function loadHomeBrief(): Promise<HomeBrief> {
  const bundle = await loadBundle(DEMO_RUN_ID);
  if (!bundle) return emptyBrief();

  const sections = bundle.verifiedReport?.sections ?? [];
  for (const section of sections) {
    for (const s of section.verified_sentences ?? []) {
      // Honest-fail: only feature a sentence the verifier actually passed.
      if (s.verifier_pass !== true) continue;
      const tokens = (s.provenance_tokens ?? []).filter(
        (t): t is string => typeof t === "string",
      );
      for (const token of tokens) {
        const span = resolveSpan(token, bundle.evidencePool);
        const spanText = span?.quote;
        // Verified-gate selection (Codex diff iter-2 P1 elevation, real
        // §-1.1 clinical-safety concern): the Home hero renders the
        // featured claim under a "VERIFIED CLAIM" label with
        // verified-green styling and NO PARTIAL variant. If we picked a
        // sentence whose verifier_pass=true rested on content-word
        // overlap but with mismatched numerics, the user would read
        // "✓ matched 2 of 5 numbers" under VERIFIED CLAIM — the lethal
        // pattern in clinical context. The Inspector has a tri-state
        // (verified / partial / unsupported) per-sentence verdict to
        // honestly render partial; the Home does not. So the Home gate
        // is STRICTER than the Inspector's: a claim is hero-eligible
        // iff (a) verifier_pass AND (b) the span is real (>40 chars
        // resolved) AND (c) EITHER pure-prose (totalNumerics === 0)
        // OR every numeric in the sentence appears in the span
        // (matchedNumerics === totalNumerics). Failing this, we
        // continue searching; if no eligible sentence exists, the
        // loader returns bundle_loaded: false (honest-fail).
        if (spanText && spanText.trim().length > 40) {
          const candidateNumerics = extractNumerics(s.sentence_text);
          const candidateMatched = countMatchesIn(candidateNumerics, spanText);
          const numericGatePassed =
            candidateNumerics.length === 0 ||
            candidateMatched === candidateNumerics.length;
          if (!numericGatePassed) continue;
          const sourceId = span.sourceId ?? "";
          const journal =
            (lookupPoolField(bundle.evidencePool, sourceId, "venue") as
              | string
              | null) ?? null;
          const yearRaw = lookupPoolField(
            bundle.evidencePool,
            sourceId,
            "year",
          );
          const year = typeof yearRaw === "number" ? yearRaw : null;
          const totalNumerics = candidateNumerics.length;
          const matchedNumerics = candidateMatched;
          return {
            bundle_loaded: true,
            run_id: DEMO_RUN_ID,
            research_question: bundle.verifiedReport?.research_question ?? null,
            claim: s.sentence_text,
            span_quote: spanText,
            source: {
              journal,
              year,
              title: span.source?.title ?? null,
              url: span.source?.url ?? null,
              tier: tierLabel(span.source?.tier),
            },
            total_numerics: totalNumerics,
            matched_numerics: matchedNumerics,
            signature_state: bundle.signatureState,
          };
        }
      }
    }
  }
  return emptyBrief();
}
