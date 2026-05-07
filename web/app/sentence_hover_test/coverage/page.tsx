import { CoverageHarness } from "../_demo_coverage";

function clamp_non_negative_int(raw: string | undefined, dflt: number): number {
  if (raw === undefined) return dflt;
  const n = Number.parseInt(raw, 10);
  if (!Number.isFinite(n) || n < 0) return dflt;
  return Math.min(n, 100);
}

export default async function CoveragePage({
  searchParams,
}: {
  searchParams: Promise<{ covered?: string; gap_count?: string }>;
}) {
  const params = await searchParams;
  const covered = clamp_non_negative_int(params.covered, 14);
  const gap_count = clamp_non_negative_int(params.gap_count, 1);
  return <CoverageHarness covered={covered} gap_count={gap_count} />;
}
