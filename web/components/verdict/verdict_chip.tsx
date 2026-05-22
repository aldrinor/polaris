// I-p2-005 (#744): per-claim verdict chip. THREE signals (state color + icon +
// label) so a verdict is never distinguished by color alone (WCAG 1.4.1).
// Consumes the #742 state tokens. Display-only (non-interactive). Honest
// labels — FABRICATED and UNREACHABLE are real, distinct, serious verdicts.
import {
  BadgeCheck,
  Ban,
  CircleHelp,
  CircleSlash,
  Minus,
  TriangleAlert,
  X,
  type LucideIcon,
} from "lucide-react";

export type VerdictKind =
  | "VERIFIED"
  | "PARTIAL"
  | "UNSUPPORTED"
  | "FABRICATED"
  | "UNREACHABLE"
  | "contradiction"
  | "refusal";

interface VerdictMeta {
  label: string;
  Icon: LucideIcon;
  /** Tint bg + readable text + border, all AA from #742 tokens. */
  className: string;
}

const VERDICT_META: Record<VerdictKind, VerdictMeta> = {
  VERIFIED: {
    label: "Verified",
    Icon: BadgeCheck,
    className: "bg-verified/10 text-verified border-verified/30",
  },
  PARTIAL: {
    label: "Partial",
    Icon: CircleSlash,
    className:
      "bg-contradiction/15 text-contradiction-foreground border-contradiction/40",
  },
  UNSUPPORTED: {
    label: "Unsupported",
    Icon: Minus,
    className: "bg-muted text-muted-foreground border-border",
  },
  FABRICATED: {
    label: "Fabricated",
    Icon: X,
    className: "bg-destructive/10 text-destructive border-destructive/40",
  },
  UNREACHABLE: {
    label: "Unreachable",
    Icon: CircleHelp,
    className: "bg-muted text-muted-foreground border-border border-dashed",
  },
  contradiction: {
    label: "Contradiction",
    Icon: TriangleAlert,
    className:
      "bg-contradiction/15 text-contradiction-foreground border-contradiction/40",
  },
  refusal: {
    label: "Refusal",
    Icon: Ban,
    className: "bg-refusal/10 text-refusal border-refusal/30",
  },
};

export function VerdictChip({ verdict }: { verdict: VerdictKind }) {
  const meta = VERDICT_META[verdict];
  return (
    <span
      data-testid="verdict-chip"
      data-verdict={verdict}
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium ${meta.className}`}
    >
      <meta.Icon aria-hidden className="h-3 w-3 shrink-0" />
      {meta.label}
    </span>
  );
}
