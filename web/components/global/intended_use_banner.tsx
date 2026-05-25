// I-ux-001c (#878) sub-PR 1: IntendedUseBanner.
//
// The amber INTENDED USE band that appears above the page chrome on every
// route showing clinical content. Required by:
//   - I-ux-001 plan §6 (intended-use posture; FDA CDS non-device logic)
//   - I-ux-001d TRACK 2 Codex iter-1 P1 (added to every clinical-content frame)
//   - components_catalogue.md §IntendedUseBanner contract
//
// Two breakpoints (per Codex iter-3 mobile audit — full copy clipped at
// 390px width):
//   - desktop / ≥768px : full copy
//   - mobile  / <768px : truncated copy ("NOT clinical decision-support ·
//                                       independent judgment required")
//
// Color: amber (`oklch(~0.85 0.15 80)` band background at 0.18 alpha on
// desktop / 0.50 alpha on mobile per the design-tokens-v2 + the iter-3
// legibility fix) with `--certainty-low-fg` (dark amber) text.
//
// This is presentation only — it does NOT gate anything. The legal weight
// comes from the operator-merge process plus the dedicated /transparency
// page (page #12 in the route map). The banner is a constant reminder
// during a clinical workflow.
"use client";

const FULL_COPY =
  "INTENDED USE · literature synthesis for healthcare decision-makers · NOT a clinical decision-support tool · NOT for individual-patient or time-sensitive decisions · independent clinical judgment required";

const MOBILE_COPY =
  "NOT clinical decision-support · independent judgment required";

interface IntendedUseBannerProps {
  /** When set, overrides the default copy. Tests use this. */
  copy?: string;
  /** When set, overrides the default mobile copy. */
  mobileCopy?: string;
  /** Optional className for layout overrides. */
  className?: string;
}

export function IntendedUseBanner({
  copy = FULL_COPY,
  mobileCopy = MOBILE_COPY,
  className,
}: IntendedUseBannerProps) {
  return (
    <div
      role="region"
      aria-label="Intended use"
      data-testid="intended-use-banner"
      className={[
        // Amber band; opacity boosted on mobile per Codex iter-3 P1
        "bg-amber-200/40 sm:bg-amber-200/30",
        "border-y border-amber-800/20",
        "px-4 py-2 sm:px-6 sm:py-1.5",
        "text-amber-900",
        "text-[10px] font-medium tracking-[0.02em] sm:text-[10px]",
        // Left-aligned text; on very wide screens, cap at content max-width
        className ?? "",
      ].join(" ")}
    >
      {/* Desktop / ≥sm */}
      <span className="hidden sm:inline">{copy}</span>
      {/* Mobile / <sm */}
      <span className="inline sm:hidden">{mobileCopy}</span>
    </div>
  );
}
