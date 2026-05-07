import { StressHarness } from "../_demo_stress";

export default async function StressPage({
  searchParams,
}: {
  searchParams: Promise<{ n?: string }>;
}) {
  const params = await searchParams;
  const n = Number.parseInt(params.n ?? "50", 10);
  const safe_n = Number.isFinite(n) && n > 0 && n <= 1000 ? n : 50;
  return <StressHarness n={safe_n} />;
}
