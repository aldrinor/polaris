// I-ux-001c (#878) sub-PR 1: Proof Replay data adapter.
//
// Bridges the real bundle's `VerifiedSentenceShape` + evidence-pool entries to
// the v6 hero's `ProofReplayClaim` shape. The adapter NEVER fabricates clinical
// metadata — fields missing from the bundle render as `null` (the UI shows `—`
// or omits the row). This honors LAW II "No Fake Working" and the I-ux-001
// plan §6 intended-use posture (literature synthesis, not clinical advice).
//
// The bundle schema (see `web/lib/signed_bundle.ts` + the canonical fixture
// under `web/public/canonical_bundles/v1_canonical_success/`) does NOT carry
// per-sentence GRADE certainty or per-source DOI/authors/study-type. Those
// are derived heuristically here (tier-based certainty, evidence-pool
// metadata lookup) with honest fallbacks.
//
// Codex iter-2 approval pinned: T4-T7 tiers render with the same pill grammar
// as T1-T3, just with the letter changed. The adapter outputs the literal
// tier string ("T1"..."T7" or null) and lets ProofReplay's TierPill render
// it uniformly.
import type {
  VerifiedReportShape,
  VerifiedSentenceShape,
} from "@/lib/inspector_bundle_loader";
import { resolveSpan } from "@/lib/evidence_span";

/** A sentence in the brief, augmented with v6 display fields. */
export interface ProofReplayClaim {
  /** Stable identifier composed of section index + sentence index. */
  claim_id: string;
  section_id: string;
  section_title: string | null;
  /** The exact sentence the verifier evaluated. */
  sentence_text: string;
  /** Provenance tokens as recorded in the bundle (`[#ev:<id>:<start>-<end>]`). */
  provenance_tokens: string[];
  /** Faithfulness verdict (binary check; checklist grammar). */
  faithfulness: {
    /** Tri-state per the §-1.1 audit standard. */
    verdict: "verified" | "partial" | "unsupported";
    /** Number of numerics in the claim that also appear in the cited span. */
    matched_numbers: { matched: number; total: number };
    /** Content-word overlap (the §9.1 invariant, threshold ≥2).
     * `null` when the bundle does NOT carry this metric — the UI MUST then
     * omit the row rather than display a synthesized value (LAW II per
     * Codex diff iter-1 P1-001). */
    content_words_overlap: number | null;
    /** Whether the cited evidence span sits inside the source's bounds. */
    span_in_bounds: boolean;
  };
  /** Evidence-strength assessment (ordinal; certainty ladder grammar). */
  evidence_strength: {
    level: "very_low" | "low" | "moderate" | "high";
    /** e.g. "RCT, Phase 3" or "—" when the bundle didn't carry it. */
    study_type: string | null;
    /** e.g. 1879. Null when missing — UI omits the row. */
    n_participants: number | null;
    /** GRADE downgrade reasons (risk of bias, inconsistency, indirectness,
     * imprecision, publication bias). Empty array = "no recorded downgrades"
     * (NOT "no risk of bias" — the absence of the field is honestly empty). */
    downgrade_reasons: string[];
  };
  /** The cited evidence span + its source metadata. */
  source: {
    /** The exact passage text the verifier matched against. */
    span_text: string;
    /** e.g. "N Engl J Med" — pulled from evidence-pool entry; null if missing. */
    journal: string | null;
    year: number | null;
    /** "Frías et al." or "Smith et al. 2021". Null if missing. */
    authors: string | null;
    /** Resolvable DOI URL or null. */
    doi: string | null;
    /** "T1"..."T7" or null. */
    tier: string | null;
    /** The actual numeric tokens (e.g. "−0.15", "−0.39") matched in the span,
     * used for inline bolding in the rendered quote. */
    matched_numbers_in_span: string[];
  };
}

/** Map a tier letter to the GRADE-equivalent certainty default.
 * This is a heuristic for the v6 prototype — production code SHOULD read
 * per-outcome certainty from the bundle (when the bundle carries it). The
 * heuristic is honest: T1 RCT → high; T2 systematic review → moderate;
 * T3 guideline → moderate (guidelines don't replace primary evidence); T4+
 * non-clinical/grey → low. Never returns "very_low" — that requires explicit
 * downgrade reasons, which the bundle should carry directly. */
function tierToCertainty(
  tier: string | null,
): "very_low" | "low" | "moderate" | "high" {
  if (tier === "T1") return "high";
  if (tier === "T2") return "moderate";
  if (tier === "T3") return "moderate";
  return "low";
}

/** Extract numeric tokens from a sentence (matches integers, decimals,
 * negatives, percentages). Used to compute matched_numbers vs cited span. */
function extractNumerics(text: string): string[] {
  // Includes Unicode minus (−), ASCII minus (-), and percentage tokens.
  const matches = text.match(/[−-]?\d+(?:\.\d+)?(?:%|\s*percentage\s+points?)?/g);
  return matches ? matches : [];
}

/** Count how many of `needles` appear in `haystack` (string-contains). */
function countMatches(needles: string[], haystack: string): number {
  let n = 0;
  for (const needle of needles) {
    if (needle.length > 0 && haystack.includes(needle)) n += 1;
  }
  return n;
}

/** Pull a metadata field off an evidence-pool entry. The pool is `unknown` at
 * the loader level; we narrow defensively. Returns `null` if the entry doesn't
 * have the field or the pool isn't shaped as expected.
 *
 * The real canonical fixture (web/public/canonical_bundles/v1_canonical_success/
 * evidence_pool.json) uses `.sources[]` as the entry array. Older drafts used
 * `.entries[]`. We accept both (Codex diff iter-1 P2-001). */
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
      // Some pools put the field at the top level
      const top = e[field];
      return top === undefined ? null : top;
    }
  }
  return null;
}

/** Adapt a single VerifiedSentenceShape into a v6 ProofReplayClaim. */
export function adaptToClaim(
  sentence: VerifiedSentenceShape,
  section: { section_id: string; section_title?: string | null },
  sectionIndex: number,
  sentenceIndex: number,
  evidencePool: unknown,
  verifiedReport: VerifiedReportShape,
): ProofReplayClaim {
  void verifiedReport; // reserved for future per-claim certainty override

  // Take the first provenance token (the primary cited span). The v6 design
  // shows ONE proof span per claim as the climax; multi-token claims are still
  // rendered, but only the first drives the source-card display.
  const primaryToken =
    sentence.provenance_tokens && sentence.provenance_tokens[0];
  const span = primaryToken
    ? resolveSpan(primaryToken, evidencePool)
    : null;

  const tier =
    (span && span.source && (span.source.tier as string | null)) || null;
  const spanText = (span && span.quote) || "";

  // Faithfulness signals (real, derived from bundle):
  const sentenceNumerics = extractNumerics(sentence.sentence_text);
  const matchedNumerics = countMatches(sentenceNumerics, spanText);
  const totalNumerics = sentenceNumerics.length;

  // Content-word overlap (the §9.1 invariant). The real value is computed by
  // src/polaris_graph/generator/provenance/strict_verify.py during the
  // verifier pass — if the bundle CARRIES that value, surface it. Otherwise
  // return null and let the UI omit the row (Codex diff iter-1 P1-001 +
  // LAW II honest-fail rule).
  const sentenceWithExtras = sentence as VerifiedSentenceShape & {
    content_words_overlap?: number;
  };
  const contentWordsOverlap =
    typeof sentenceWithExtras.content_words_overlap === "number"
      ? sentenceWithExtras.content_words_overlap
      : null;

  // Source metadata — best-effort lookup against the evidence pool.
  const sourceId = (span && span.sourceId) || "";
  const journal = (lookupPoolField(evidencePool, sourceId, "venue") as string) || null;
  const yearRaw = lookupPoolField(evidencePool, sourceId, "year");
  const year = typeof yearRaw === "number" ? yearRaw : null;
  const authorsRaw = lookupPoolField(evidencePool, sourceId, "authors");
  const authors =
    typeof authorsRaw === "string"
      ? authorsRaw
      : Array.isArray(authorsRaw) && authorsRaw.length > 0
        ? `${authorsRaw[0]}${authorsRaw.length > 1 ? " et al." : ""}`
        : null;
  const doi = (lookupPoolField(evidencePool, sourceId, "doi") as string) || null;
  const studyType =
    (lookupPoolField(evidencePool, sourceId, "study_type") as string) || null;
  const nRaw = lookupPoolField(evidencePool, sourceId, "n_participants");
  const nParticipants = typeof nRaw === "number" ? nRaw : null;
  const downgradeRaw = lookupPoolField(evidencePool, sourceId, "quality_notes");
  const downgradeReasons = Array.isArray(downgradeRaw)
    ? downgradeRaw.filter((d): d is string => typeof d === "string")
    : [];

  return {
    claim_id: `${sectionIndex}:${sentenceIndex}`,
    section_id: section.section_id,
    section_title:
      (typeof section.section_title === "string" && section.section_title) ||
      null,
    sentence_text: sentence.sentence_text,
    provenance_tokens: Array.isArray(sentence.provenance_tokens)
      ? sentence.provenance_tokens.filter(
          (t): t is string => typeof t === "string",
        )
      : [],
    faithfulness: {
      // Codex diff iter-2 P2: verifier_pass=true non-numeric claims were
      // mis-classified as "partial" (no numbers to match → matchedNumerics
      // === 0 ≠ totalNumerics === 0). Correct logic: if the bundle says
      // verifier_pass, the claim is "verified" UNLESS it has numerics that
      // didn't match. Pure-prose verified claims (no numbers) → verified.
      verdict: sentence.verifier_pass === true
        ? totalNumerics === 0 || matchedNumerics === totalNumerics
          ? "verified"
          : "partial"
        : "unsupported",
      matched_numbers: { matched: matchedNumerics, total: totalNumerics },
      content_words_overlap: contentWordsOverlap,
      span_in_bounds: span !== null && span.source !== null,
    },
    evidence_strength: {
      level: tierToCertainty(tier),
      study_type: studyType,
      n_participants: nParticipants,
      downgrade_reasons: downgradeReasons,
    },
    source: {
      span_text: spanText,
      journal,
      year,
      authors,
      doi,
      tier,
      matched_numbers_in_span: sentenceNumerics.filter((n) => spanText.includes(n)),
    },
  };
}

/** Flatten a VerifiedReport's sections into an ordered list of ProofReplayClaims.
 * Stable order matches the bundle's section + sentence order so per-claim
 * navigation (J/K keyboard) is deterministic. */
export function flattenToClaimList(
  report: VerifiedReportShape,
  evidencePool: unknown,
): ProofReplayClaim[] {
  const out: ProofReplayClaim[] = [];
  const sections = report.sections || [];
  sections.forEach((section, si) => {
    const sentences = section.verified_sentences || [];
    sentences.forEach((sentence, sj) => {
      out.push(
        adaptToClaim(
          sentence,
          section,
          si,
          sj,
          evidencePool,
          report,
        ),
      );
    });
  });
  return out;
}
