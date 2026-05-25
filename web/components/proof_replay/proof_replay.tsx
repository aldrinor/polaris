// I-ux-001c (#878) sub-PR 1: Proof Replay v6 rebuild.
//
// THE CENTERPIECE per plan §14: every sentence proves itself, with the
// source span as the unforgettable climax. Click any verified sentence
// (left) → the proof panel (right on desktop, bottom-sheet on mobile)
// reveals the 6-beat choreography.
//
// Spatial+temporal order (LOCKED Codex iter-3 TRACK 1 sub-track A direction):
//   Beat 1  Claim echo (CHALLENGED SENTENCE label + claim text + ① marker)
//   Beat 2  Faithfulness  ("Verified" + 3-item check list)
//   Beat 3  Evidence Strength (Very low / Low / Moderate / High ladder)
//   Beat 4  Source (climax) — Sealed evidence block (2px green left rule
//                              through source-card + span + matched-N stamp)
//   Beat 5  Signature pill (gpg_verified green only) + verify-offline link
//   Beat 6  "what this verification does NOT prove" disclosure
//
// Motion: opacity-reveal per beat via design-tokens-v2 §5 cadence
// (--duration-fast 120ms / --duration-base 200ms / --duration-slow 320ms).
// `prefers-reduced-motion: reduce` → all beats appear at once.
//
// Keyboard: Enter on a sentence = select; Esc = clear selection + focus
// returns to the clicked sentence; J/K (or arrows) = next/previous claim.
//
// Mobile: <768px swaps the right rail for a shadcn Sheet (bottom slide-up)
// with a handle bar; sheet's built-in dismiss gestures work.
//
// Data honesty: ALL displayed fields come from `proof_replay_adapter`'s
// `ProofReplayClaim` shape — when a bundle field is missing, the row is
// omitted, not fabricated (LAW II).
"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronRight, ShieldCheck } from "lucide-react";

import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import {
  SignatureBadge,
  type SignatureState,
} from "@/components/inspector/bundle_header";
import {
  flattenToClaimList,
  type ProofReplayClaim,
} from "@/lib/proof_replay_adapter";
import type { BundleManifest } from "@/lib/signed_bundle";
import type {
  VerifiedReportSectionShape,
  VerifiedReportShape,
} from "@/lib/inspector_bundle_loader";

interface ProofReplayProps {
  sections: VerifiedReportSectionShape[];
  evidencePool: unknown;
  verifiedReport: VerifiedReportShape;
  manifest: BundleManifest;
  signatureState: SignatureState;
  signatureKeyFingerprint?: string;
}

const CERTAINTY_LABEL: Record<
  ProofReplayClaim["evidence_strength"]["level"],
  string
> = {
  very_low: "Very low",
  low: "Low",
  moderate: "Moderate",
  high: "High",
};

const CERTAINTY_ORDER: ProofReplayClaim["evidence_strength"]["level"][] = [
  "very_low",
  "low",
  "moderate",
  "high",
];

function usePrefersReducedMotion(): boolean {
  // Lazy initializer reads the matchMedia value synchronously so the effect
  // never has to call setReduced for the initial state (avoids the
  // react-hooks/set-state-in-effect lint warning).
  const [reduced, setReduced] = useState(() =>
    typeof window !== "undefined" && window.matchMedia
      ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
      : false,
  );
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const handler = (e: MediaQueryListEvent) => setReduced(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);
  return reduced;
}

function useIsMobile(): boolean {
  const [mobile, setMobile] = useState(() =>
    typeof window !== "undefined" && window.matchMedia
      ? window.matchMedia("(max-width: 767px)").matches
      : false,
  );
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia("(max-width: 767px)");
    const handler = (e: MediaQueryListEvent) => setMobile(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);
  return mobile;
}

/* ============================================================
 * Sub-components — one per beat
 * ============================================================ */

function ChallengedLabel({ visible }: { visible: boolean }) {
  return (
    <p
      data-testid="challenged-sentence-label"
      className={`text-muted-foreground text-[10px] font-medium tracking-[0.08em] uppercase transition-opacity ${
        visible ? "opacity-100" : "opacity-0"
      }`}
      style={{ transitionDuration: "var(--duration-fast, 120ms)" }}
    >
      Challenged sentence
    </p>
  );
}

function ClaimEcho({ claim, visible }: { claim: ProofReplayClaim; visible: boolean }) {
  return (
    <div
      data-testid="claim-echo"
      className={`flex items-start gap-3 transition-opacity ${
        visible ? "opacity-100" : "opacity-0"
      }`}
      style={{ transitionDuration: "var(--duration-base, 200ms)" }}
    >
      <span
        aria-hidden
        className="bg-verified text-background mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-bold"
      >
        1
      </span>
      <p className="text-foreground text-sm italic leading-relaxed">
        “{claim.sentence_text}”
      </p>
    </div>
  );
}

function FaithfulnessBlock({
  claim,
  visible,
}: {
  claim: ProofReplayClaim;
  visible: boolean;
}) {
  const f = claim.faithfulness;
  // Codex diff iter-1 P1-002 fix: verdict-aware headline + check colors.
  // Partial/unsupported must NEVER render as a verified green proof.
  const verdictLabel =
    f.verdict === "verified"
      ? "Verified"
      : f.verdict === "partial"
        ? "Partial — not fully verified"
        : "Unsupported — could not verify";
  const verdictColorClass =
    f.verdict === "verified"
      ? "text-verified"
      : f.verdict === "partial"
        ? "text-amber-700"
        : "text-contradiction-foreground";
  // Codex diff iter-1 P1-001 fix: omit the content-word-overlap row when the
  // bundle did not carry the metric (content_words_overlap === null).
  const checks: Array<[string, boolean]> = [
    [
      `Every number in the claim appears in the cited span (${f.matched_numbers.matched} of ${f.matched_numbers.total}).`,
      f.matched_numbers.total > 0 &&
        f.matched_numbers.matched === f.matched_numbers.total,
    ],
  ];
  if (f.content_words_overlap !== null) {
    checks.push([
      `Claim and span share ${f.content_words_overlap} content words (threshold ≥ 2).`,
      f.content_words_overlap >= 2,
    ]);
  }
  checks.push(["Evidence span sits inside the source bounds.", f.span_in_bounds]);

  return (
    <div
      data-testid="faithfulness-block"
      data-verdict={f.verdict}
      className={`flex flex-col gap-3 transition-opacity ${
        visible ? "opacity-100" : "opacity-0"
      }`}
      style={{
        transitionDuration: "var(--duration-base, 200ms)",
        transitionDelay: visible ? "130ms" : "0ms",
      }}
    >
      <div className="flex items-baseline gap-2">
        <h3 className={`${verdictColorClass} text-2xl font-bold`}>
          {verdictLabel}
        </h3>
        <p className="text-muted-foreground text-sm italic">
          by an independent model family
        </p>
      </div>
      <ul className="flex flex-col gap-1.5">
        {checks.map(([label, pass], i) => (
          <li
            key={i}
            className="text-foreground flex items-start gap-2 text-sm"
            data-pass={pass ? "true" : "false"}
          >
            <Check
              aria-hidden
              className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${
                pass ? "text-verified" : "text-muted-foreground"
              }`}
            />
            <span>{label}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function EvidenceStrengthBlock({
  claim,
  visible,
}: {
  claim: ProofReplayClaim;
  visible: boolean;
}) {
  const es = claim.evidence_strength;
  return (
    <div
      data-testid="evidence-strength-block"
      className={`flex flex-col gap-3 transition-opacity ${
        visible ? "opacity-100" : "opacity-0"
      }`}
      style={{
        transitionDuration: "var(--duration-base, 200ms)",
        transitionDelay: visible ? "280ms" : "0ms",
      }}
    >
      <p className="text-foreground text-sm font-medium">
        How strong is the evidence base for this claim?
      </p>
      <div role="group" aria-label="Evidence strength" className="flex gap-1">
        {CERTAINTY_ORDER.map((level) => {
          const selected = es.level === level;
          return (
            <div
              key={level}
              aria-current={selected ? "true" : undefined}
              className={`flex-1 rounded-md py-2 text-center text-[11px] font-medium tracking-tight ${
                selected
                  ? "text-background"
                  : "bg-muted/40 text-muted-foreground"
              }`}
              style={
                selected
                  ? {
                      backgroundColor: `var(--certainty-${level.replace("_", "-")}-fg, oklch(0.32 0.14 250))`,
                    }
                  : undefined
              }
            >
              {CERTAINTY_LABEL[level]}
            </div>
          );
        })}
      </div>
      {(es.study_type || es.n_participants !== null) && (
        <p className="text-muted-foreground text-xs">
          {es.study_type ?? "—"}
          {es.n_participants !== null
            ? ` · n=${es.n_participants.toLocaleString()}`
            : ""}
          {es.downgrade_reasons.length > 0
            ? ` · downgrades: ${es.downgrade_reasons.join(", ")}`
            : ""}
        </p>
      )}
    </div>
  );
}

function SourceClimax({
  claim,
  visible,
}: {
  claim: ProofReplayClaim;
  visible: boolean;
}) {
  const s = claim.source;
  // Render the span with the matched numerics in semibold green.
  const spanNodes = useMemo(() => {
    if (!s.span_text) return null;
    if (s.matched_numbers_in_span.length === 0) return s.span_text;
    const escaped = s.matched_numbers_in_span
      .map((n) => n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
      .join("|");
    const re = new RegExp(`(${escaped})`, "g");
    const parts = s.span_text.split(re);
    return parts.map((part, i) =>
      s.matched_numbers_in_span.includes(part) ? (
        <span key={i} className="text-verified font-semibold">
          {part}
        </span>
      ) : (
        part
      ),
    );
  }, [s.span_text, s.matched_numbers_in_span]);

  return (
    <div
      data-testid="source-climax"
      className={`flex flex-col gap-2 transition-opacity ${
        visible ? "opacity-100" : "opacity-0"
      }`}
      style={{
        transitionDuration: "var(--duration-base, 200ms)",
        transitionDelay: visible ? "430ms" : "0ms",
      }}
    >
      <p className="text-foreground text-sm font-semibold">
        The exact passage that supports this claim
      </p>
      {/* Sealed evidence block — continuous 2px verified-green left rule
          spans source-card top + span body bottom */}
      <div className="border-verified/20 bg-card flex overflow-hidden rounded-lg border">
        <div aria-hidden className="bg-verified w-[2px] shrink-0" />
        <div className="flex flex-1 flex-col">
          {/* Source-card top row */}
          <div className="border-border/60 flex items-center gap-2 border-b px-4 py-3 text-xs">
            <span className="text-foreground font-medium">
              {s.journal ?? "—"}
            </span>
            {s.year !== null && (
              <span className="text-muted-foreground">· {s.year}</span>
            )}
            {s.authors && (
              <span className="text-muted-foreground">· {s.authors}</span>
            )}
            {s.tier && (
              <span className="border-verified/30 bg-verified/10 text-verified ml-auto rounded-full border px-2 py-0.5 text-[10px] font-semibold tracking-wider">
                {s.tier}
              </span>
            )}
          </div>
          {/* Span quote body */}
          <div className="relative px-4 py-3">
            <blockquote className="text-foreground text-sm leading-relaxed">
              {s.span_text ? (
                <>“{spanNodes}”</>
              ) : (
                <span className="text-muted-foreground italic">
                  No span text available in this bundle.
                </span>
              )}
            </blockquote>
            {s.matched_numbers_in_span.length > 0 && (
              <p
                data-testid="matched-numbers-stamp"
                className="text-verified mt-2 flex items-center justify-end gap-1 text-[11px] font-medium"
              >
                <Check aria-hidden className="h-3 w-3" />
                matched {s.matched_numbers_in_span.length} of{" "}
                {claim.faithfulness.matched_numbers.total} numbers
              </p>
            )}
          </div>
        </div>
      </div>
      {s.doi && (
        <a
          href={s.doi}
          target="_blank"
          rel="noopener noreferrer"
          className="text-verified text-xs underline-offset-2 hover:underline"
        >
          → Open the full source
        </a>
      )}
    </div>
  );
}

function SignatureBlock({
  signatureState,
  manifest,
  visible,
}: {
  signatureState: SignatureState;
  manifest: BundleManifest;
  visible: boolean;
}) {
  return (
    <div
      data-testid="signature-block"
      className={`flex flex-col gap-1.5 transition-opacity ${
        visible ? "opacity-100" : "opacity-0"
      }`}
      style={{
        transitionDuration: "var(--duration-base, 200ms)",
        transitionDelay: visible ? "580ms" : "0ms",
      }}
    >
      <SignatureBadge state={signatureState} />
      {signatureState === "gpg_verified" && (
        <p className="text-muted-foreground text-xs">
          → Verify this offline (no POLARIS server needed):{" "}
          <code className="font-mono">
            gpg --verify manifest.yaml.asc manifest.yaml
          </code>{" "}
          using the published trust-root pubkey ·{" "}
          <span className="text-foreground/70 font-mono">
            bundle {manifest.bundle_id.slice(0, 12)}
          </span>
        </p>
      )}
    </div>
  );
}

function DisclosureBlock({ visible }: { visible: boolean }) {
  return (
    <details
      data-testid="disclosure-block"
      className={`group/disclosure text-xs transition-opacity ${
        visible ? "opacity-100" : "opacity-0"
      }`}
      style={{
        transitionDuration: "var(--duration-base, 200ms)",
        transitionDelay: visible ? "680ms" : "0ms",
      }}
    >
      <summary className="text-muted-foreground hover:text-foreground inline-flex w-fit cursor-pointer items-center gap-1 rounded-md py-1 transition-colors [&::-webkit-details-marker]:hidden">
        <ChevronRight
          aria-hidden
          className="h-3 w-3 transition-transform group-open/disclosure:rotate-90"
        />
        what this verification does NOT prove
      </summary>
      <ul className="text-muted-foreground mt-2 list-disc space-y-1 pl-7">
        <li>
          Verification confirms the sentence follows from the cited source span,
          NOT that the source itself is correct.
        </li>
        <li>
          Evidence strength reflects literature quality, NOT applicability to a
          specific patient.
        </li>
        <li>
          POLARIS is a research-decision-support tool — it does NOT replace
          independent clinical judgment and is NOT for individual-patient or
          time-sensitive decisions.
        </li>
      </ul>
    </details>
  );
}

/* ============================================================
 * Proof panel (right rail / bottom sheet content)
 * ============================================================ */

interface ProofPanelProps {
  claim: ProofReplayClaim | null;
  manifest: BundleManifest;
  signatureState: SignatureState;
  reducedMotion: boolean;
}

// Beat schedule per design_tokens_v2 §5 + i_ux_001d_motion_still_convention.md
// row 1 timestamps. Each beat ramps to opacity 1 at its scheduled t (ms).
const BEAT_SCHEDULE = [
  { beat: 1, t: 0 },     // claim echo + challenged label (immediate)
  { beat: 2, t: 130 },   // faithfulness
  { beat: 3, t: 280 },   // evidence strength
  { beat: 4, t: 430 },   // source (climax)
  { beat: 5, t: 580 },   // signature
  { beat: 6, t: 680 },   // disclosure
] as const;

function ProofPanel({
  claim,
  manifest,
  signatureState,
  reducedMotion,
}: ProofPanelProps) {
  // Empty state is structurally distinct (no claim selected). Bail early so
  // the staged-reveal hook below only runs when a claim is actually being
  // shown.
  if (!claim) {
    return (
      <div
        data-testid="proof-panel-empty"
        className="text-muted-foreground flex h-full min-h-[300px] flex-col items-center justify-center gap-2 p-6 text-sm"
      >
        <ShieldCheck aria-hidden className="text-muted-foreground/40 h-6 w-6" />
        <p>Click any sentence to see its proof.</p>
      </div>
    );
  }
  // The inner component receives a stable claim and runs the staged reveal
  // hook. Keyed on (claim_id + reducedMotion) so React fully resets state
  // on claim-change — avoids setRevealedBeat-in-effect (eslint
  // react-hooks/set-state-in-effect).
  return (
    <StagedProofPanel
      key={`${claim.claim_id}-${reducedMotion ? "rm" : "full"}`}
      claim={claim}
      manifest={manifest}
      signatureState={signatureState}
      reducedMotion={reducedMotion}
    />
  );
}

interface StagedProofPanelProps {
  claim: ProofReplayClaim;
  manifest: BundleManifest;
  signatureState: SignatureState;
  reducedMotion: boolean;
}

function StagedProofPanel({
  claim,
  manifest,
  signatureState,
  reducedMotion,
}: StagedProofPanelProps) {
  // Codex diff iter-1 P1-003 fix: ACTUAL staged reveal. The initial value
  // is set via the lazy initializer (so it's correct at first render
  // without any setState in an effect); subsequent advances come from the
  // setTimeout chain.
  const [revealedBeat, setRevealedBeat] = useState<number>(() =>
    reducedMotion ? 6 : 0,
  );

  useEffect(() => {
    if (reducedMotion) return;
    const timers = BEAT_SCHEDULE.map((b) =>
      window.setTimeout(() => setRevealedBeat(b.beat), b.t),
    );
    return () => {
      for (const t of timers) window.clearTimeout(t);
    };
  }, [reducedMotion]);

  return (
    <div
      data-testid="proof-panel"
      data-claim-id={claim.claim_id}
      data-revealed-beat={revealedBeat}
      role="region"
      aria-label={`Proof for the ${claim.faithfulness.verdict} claim`}
      className="flex flex-col gap-5 p-6"
    >
      <ChallengedLabel visible={revealedBeat >= 1} />
      <ClaimEcho claim={claim} visible={revealedBeat >= 1} />
      <FaithfulnessBlock claim={claim} visible={revealedBeat >= 2} />
      <hr className="border-border/60" />
      <EvidenceStrengthBlock claim={claim} visible={revealedBeat >= 3} />
      <hr className="border-border/60" />
      <SourceClimax claim={claim} visible={revealedBeat >= 4} />
      <hr className="border-border/60" />
      <SignatureBlock
        signatureState={signatureState}
        manifest={manifest}
        visible={revealedBeat >= 5}
      />
      <DisclosureBlock visible={revealedBeat >= 6} />
    </div>
  );
}

/* ============================================================
 * Claims list (left rail) + main orchestrator
 * ============================================================ */

export function ProofReplay({
  sections,
  evidencePool,
  verifiedReport,
  manifest,
  signatureState,
  signatureKeyFingerprint: _signatureKeyFingerprint,
}: ProofReplayProps) {
  void _signatureKeyFingerprint; // reserved for the receipt subview in a later sub-PR

  // Use the adapter to derive v6 claims.
  const claims = useMemo(
    () =>
      flattenToClaimList(
        { ...verifiedReport, sections: verifiedReport.sections ?? sections },
        evidencePool,
      ),
    [verifiedReport, sections, evidencePool],
  );

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const reducedMotion = usePrefersReducedMotion();
  const isMobile = useIsMobile();
  const buttonRefs = useRef<Map<string, HTMLButtonElement>>(new Map());

  const selected = selectedId
    ? (claims.find((c) => c.claim_id === selectedId) ?? null)
    : null;

  const selectClaim = useCallback(
    (id: string | null) => {
      const wasSelected = selectedId;
      setSelectedId(id);
      if (id === null && wasSelected !== null) {
        const btn = buttonRefs.current.get(wasSelected);
        btn?.focus();
      }
    },
    [selectedId],
  );

  // Keyboard navigation
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement
      ) {
        return;
      }
      if (e.key === "Escape" && selectedId !== null) {
        e.preventDefault();
        selectClaim(null);
        return;
      }
      if (claims.length === 0) return;
      const currentIdx = selectedId
        ? claims.findIndex((c) => c.claim_id === selectedId)
        : -1;
      if (e.key === "j" || e.key === "ArrowDown") {
        e.preventDefault();
        const nextIdx = (currentIdx + 1) % claims.length;
        selectClaim(claims[nextIdx].claim_id);
      }
      if (e.key === "k" || e.key === "ArrowUp") {
        e.preventDefault();
        const prevIdx = currentIdx <= 0 ? claims.length - 1 : currentIdx - 1;
        selectClaim(claims[prevIdx].claim_id);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [claims, selectedId, selectClaim]);

  if (claims.length === 0) {
    return (
      <p className="text-muted-foreground text-sm">
        No verified claims in this report.
      </p>
    );
  }

  const claimsList = (
    <div
      role="list"
      aria-label="Verified claims"
      data-testid="claims-list"
      className="flex flex-col gap-0.5"
    >
      {claims.map((claim, i) => {
        const isSelected = claim.claim_id === selectedId;
        const showHeading =
          i === 0 || claims[i - 1].section_id !== claim.section_id;
        return (
          <div key={claim.claim_id} role="listitem">
            {showHeading && claim.section_title && (
              <p className="text-muted-foreground mt-3 mb-1 px-2 text-[10px] font-medium tracking-[0.08em] uppercase">
                {claim.section_title}
              </p>
            )}
            <button
              ref={(el) => {
                if (el) buttonRefs.current.set(claim.claim_id, el);
                else buttonRefs.current.delete(claim.claim_id);
              }}
              type="button"
              data-testid={`claim-${claim.claim_id}`}
              aria-current={isSelected ? "true" : undefined}
              aria-label={`${claim.faithfulness.verdict} claim: ${claim.sentence_text}`}
              onClick={() => selectClaim(claim.claim_id)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  selectClaim(claim.claim_id);
                }
              }}
              className={`focus-visible:ring-verified/60 flex w-full items-start gap-2 rounded-md border-l-2 px-3 py-2 text-left text-sm leading-relaxed transition-colors focus-visible:ring-2 focus-visible:outline-none ${
                isSelected
                  ? "border-verified bg-verified/5 text-foreground"
                  : "text-foreground/85 hover:bg-muted/50 border-transparent"
              }`}
            >
              <span
                aria-hidden
                className={`mt-1.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full ${
                  claim.faithfulness.verdict === "verified"
                    ? "bg-verified"
                    : claim.faithfulness.verdict === "partial"
                      ? "bg-amber-500"
                      : "bg-muted-foreground"
                }`}
              />
              <span>{claim.sentence_text}</span>
            </button>
          </div>
        );
      })}
    </div>
  );

  // Mobile: bottom sheet
  if (isMobile) {
    return (
      <div data-testid="proof-replay" data-viewport="mobile">
        <div className="border-border rounded-md border p-3">{claimsList}</div>
        <Sheet
          open={selected !== null}
          onOpenChange={(open) => {
            if (!open) selectClaim(null);
          }}
        >
          <SheetContent
            side="bottom"
            className="max-h-[85vh] overflow-y-auto"
            data-testid="proof-replay-sheet"
          >
            <SheetHeader className="sr-only">
              <SheetTitle>Proof for the selected claim</SheetTitle>
              <SheetDescription>
                Reveals the 6-beat verification chain for the claim you tapped.
              </SheetDescription>
            </SheetHeader>
            <ProofPanel
              claim={selected}
              manifest={manifest}
              signatureState={signatureState}
              reducedMotion={reducedMotion}
            />
          </SheetContent>
        </Sheet>
      </div>
    );
  }

  // Desktop: split-view grid
  return (
    <div
      data-testid="proof-replay"
      data-viewport="desktop"
      className="grid gap-6 md:grid-cols-[1fr_minmax(360px,440px)]"
    >
      <div className="border-border rounded-md border p-3">{claimsList}</div>
      <aside
        aria-live="polite"
        aria-label="Proof for the selected claim"
        className="border-border rounded-md border"
      >
        <ProofPanel
          claim={selected}
          manifest={manifest}
          signatureState={signatureState}
          reducedMotion={reducedMotion}
        />
      </aside>
    </div>
  );
}
