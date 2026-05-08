"use client";

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import type { PinSnapshot } from "@/lib/pin_replay_demo";

type FieldKind = "numeric" | "string";

const FIELDS: { key: keyof PinSnapshot; label: string; kind: FieldKind }[] = [
  { key: "query", label: "Query", kind: "string" },
  { key: "verdict", label: "Verdict", kind: "string" },
  { key: "section_count_kept", label: "Sections kept", kind: "numeric" },
  { key: "section_count_dropped", label: "Sections dropped", kind: "numeric" },
  {
    key: "verified_sentence_count",
    label: "Verified sentences",
    kind: "numeric",
  },
  { key: "pass_rate", label: "Pass rate (%)", kind: "numeric" },
];

function formatValue(value: unknown, kind: FieldKind, key: string): string {
  if (kind === "numeric" && typeof value === "number") {
    if (key === "pass_rate") return `${Math.round(value * 100)}%`;
    return String(value);
  }
  return String(value ?? "");
}

function computeDelta(
  a: unknown,
  b: unknown,
  kind: FieldKind,
  key: string,
): string {
  if (kind === "numeric" && typeof a === "number" && typeof b === "number") {
    const delta =
      key === "pass_rate" ? Math.round(b * 100) - Math.round(a * 100) : b - a;
    const prefix = delta > 0 ? "+" : "";
    return key === "pass_rate" ? `${prefix}${delta}%` : `${prefix}${delta}`;
  }
  // String/categorical: report changed/unchanged.
  return a === b ? "(unchanged)" : "(changed)";
}

export function DiffSidePanel({
  open,
  onOpenChange,
  snapshot_a,
  snapshot_b,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  snapshot_a: PinSnapshot | null;
  snapshot_b: PinSnapshot | null;
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        data-testid="pin-diff-pane"
        side="right"
        className="data-[side=right]:w-full data-[side=right]:sm:w-2/5 data-[side=right]:sm:max-w-none"
      >
        <SheetHeader>
          <SheetTitle>Snapshot diff (B − A)</SheetTitle>
          <SheetDescription>
            Per-field comparison of snapshot A and snapshot B.
          </SheetDescription>
        </SheetHeader>
        {snapshot_a && snapshot_b ? (
          <div className="px-4 pb-4 text-sm">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-border border-b">
                  <th className="py-1 text-left">Field</th>
                  <th className="py-1 text-left">A</th>
                  <th className="py-1 text-left">B</th>
                  <th className="py-1 text-left">Δ</th>
                </tr>
              </thead>
              <tbody>
                {FIELDS.map(({ key, label, kind }) => (
                  <tr
                    key={key}
                    data-testid={`pin-diff-row-${String(key)}`}
                    className="border-border border-b"
                  >
                    <td className="py-1 font-medium">{label}</td>
                    <td className="truncate py-1">
                      {formatValue(snapshot_a[key], kind, String(key))}
                    </td>
                    <td className="truncate py-1">
                      {formatValue(snapshot_b[key], kind, String(key))}
                    </td>
                    <td
                      data-testid={`pin-diff-delta-${String(key)}`}
                      className="py-1"
                    >
                      {computeDelta(
                        snapshot_a[key],
                        snapshot_b[key],
                        kind,
                        String(key),
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p
            data-testid="pin-diff-pane-empty"
            className="text-muted-foreground px-4 pb-4 text-sm italic"
          >
            Select both snapshots to view diff.
          </p>
        )}
      </SheetContent>
    </Sheet>
  );
}
