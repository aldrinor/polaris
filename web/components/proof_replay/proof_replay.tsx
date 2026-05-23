// I-p2-007 (#746): Proof Replay split-view — POLARIS's centerpiece. Click a
// verified claim (left) → see the EXACT cited source span (right). Composes the
// shared resolveSpan (#743) + SourceCard (#745) + VerdictChip (#744). Honest:
// malformed/missing/empty provenance never crashes — it shows an honest note,
// never synthetic proof.
"use client";

import { useMemo, useState } from "react";

import {
  SourceCard,
  type SourceCardSource,
} from "@/components/source/source_card";
import { VerdictChip } from "@/components/verdict/verdict_chip";
import { resolveSpan, spanInContext } from "@/lib/evidence_span";
import type { VerifiedReportSectionShape } from "@/lib/inspector_bundle_loader";

interface ProofReplayProps {
  sections: VerifiedReportSectionShape[];
  evidencePool: unknown;
}

interface FlatClaim {
  key: string;
  sectionId: string;
  sectionTitle: string | null;
  text: string;
  tokens: string[];
  verified: boolean;
}

function flatten(sections: VerifiedReportSectionShape[]): FlatClaim[] {
  const out: FlatClaim[] = [];
  sections.forEach((section, si) => {
    const title =
      (typeof section.section_title === "string" && section.section_title) ||
      null;
    section.verified_sentences?.forEach((s, i) => {
      out.push({
        key: `${si}:${i}`,
        sectionId: section.section_id,
        sectionTitle: title,
        text: s.sentence_text,
        tokens: Array.isArray(s.provenance_tokens)
          ? s.provenance_tokens.filter(
              (t): t is string => typeof t === "string",
            )
          : [],
        verified: s.verifier_pass === true,
      });
    });
  });
  return out;
}

function UnverifiedBadge() {
  return (
    <span className="bg-muted text-foreground border-border inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium">
      Unverified
    </span>
  );
}

function ProofPane({
  claim,
  evidencePool,
}: {
  claim: FlatClaim;
  evidencePool: unknown;
}) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-start justify-between gap-3">
        <p className="text-foreground text-sm leading-snug">{claim.text}</p>
        {claim.verified ? (
          <VerdictChip verdict="VERIFIED" />
        ) : (
          <UnverifiedBadge />
        )}
      </div>

      {claim.tokens.length === 0 ? (
        <p className="text-muted-foreground text-xs">
          No provenance tokens recorded for this claim.
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          {claim.tokens.map((token, i) => {
            const span = resolveSpan(token, evidencePool);
            if (span === null) {
              return (
                <p
                  key={`${token}-${i}`}
                  className="text-muted-foreground text-xs"
                >
                  Unresolvable provenance token:{" "}
                  <span className="font-mono">{token}</span>
                </p>
              );
            }
            if (span.source === null) {
              return (
                <p
                  key={`${token}-${i}`}
                  className="text-muted-foreground text-xs"
                >
                  Source <span className="font-mono">{span.sourceId}</span> not
                  in this bundle — verify via the signed bundle.
                </p>
              );
            }
            const cardSource: SourceCardSource = {
              source_id: span.source.source_id,
              title: span.source.title,
              url: span.source.url,
              tier: span.source.tier,
            };
            return (
              <div key={`${token}-${i}`} className="flex flex-col gap-1">
                <SourceCard source={cardSource} />
                {span.quote != null ? (
                  (() => {
                    // I-p2-038 (#821): show the EXACT cited span highlighted in
                    // its real source context (the raw span often starts
                    // mid-token and reads as broken). Faithful: <mark> === the
                    // exact full_text[start:end]; context is real adjacent text.
                    const ctx = spanInContext(
                      span.source?.full_text,
                      span.start,
                      span.end,
                    );
                    return (
                      <blockquote className="border-primary text-muted-foreground max-h-48 overflow-auto border-l-2 pl-3 text-xs leading-relaxed">
                        {ctx ? (
                          <>
                            {ctx.leadingEllipsis ? "… " : "“"}
                            {ctx.before}
                            <mark className="bg-primary/10 text-foreground rounded-[3px] box-decoration-clone px-0.5 font-medium">
                              {ctx.span}
                            </mark>
                            {ctx.after}
                            {ctx.trailingEllipsis ? " …" : "”"}
                          </>
                        ) : (
                          <span className="text-foreground italic">
                            &ldquo;{span.quote}&rdquo;
                          </span>
                        )}
                      </blockquote>
                    );
                  })()
                ) : (
                  <p className="text-muted-foreground text-xs">
                    Span not renderable from this bundle.
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function ProofReplay({ sections, evidencePool }: ProofReplayProps) {
  const claims = useMemo(() => flatten(sections), [sections]);
  const [selectedKey, setSelectedKey] = useState<string | null>(
    claims[0]?.key ?? null,
  );
  // Fall back to the first claim if the selected key is stale (e.g. sections
  // changed after mount), so the proof pane keeps its default-first behavior.
  const selected =
    claims.find((c) => c.key === selectedKey) ?? claims[0] ?? null;

  if (claims.length === 0) {
    return (
      <p className="text-muted-foreground text-sm">
        No verified claims in this report.
      </p>
    );
  }

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div
        role="list"
        aria-label="Claims"
        className="border-border flex max-h-[32rem] flex-col gap-1 overflow-auto rounded-md border p-2"
      >
        {claims.map((claim, i) => {
          const isSelected = claim.key === selectedKey;
          const showHeading =
            i === 0 || claims[i - 1].sectionId !== claim.sectionId;
          return (
            <div key={claim.key} role="listitem">
              {showHeading && claim.sectionTitle && (
                <p className="text-muted-foreground mt-2 mb-1 px-2 text-[11px] font-medium tracking-wide uppercase">
                  {claim.sectionTitle}
                </p>
              )}
              <button
                type="button"
                aria-current={isSelected ? "true" : undefined}
                aria-label={`${claim.verified ? "Verified" : "Unverified"} claim: ${claim.text}`}
                onClick={() => setSelectedKey(claim.key)}
                className={`focus-visible:ring-ring/70 flex w-full items-start gap-2 rounded px-2 py-1.5 text-left text-xs leading-snug transition-colors focus-visible:ring-2 focus-visible:outline-none ${
                  isSelected
                    ? "bg-primary/10 text-foreground border-primary border-l-2"
                    : "text-muted-foreground hover:bg-muted border-l-2 border-transparent"
                }`}
              >
                <span
                  aria-hidden
                  className={`mt-1 inline-block h-1.5 w-1.5 shrink-0 rounded-full ${
                    claim.verified ? "bg-verified" : "bg-muted-foreground"
                  }`}
                />
                <span className="line-clamp-2">{claim.text}</span>
              </button>
            </div>
          );
        })}
      </div>

      <div
        aria-live="polite"
        aria-label="Proof for the selected claim"
        className="border-border rounded-md border p-4"
      >
        {selected ? (
          <ProofPane claim={selected} evidencePool={evidencePool} />
        ) : (
          <p className="text-muted-foreground text-sm">
            Select a claim to see its proof.
          </p>
        )}
      </div>
    </div>
  );
}
