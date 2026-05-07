import { EvaluatorEdgeHarness } from "../_demo_evaluator_edge";

export default async function EvaluatorEdgePage({
  searchParams,
}: {
  searchParams: Promise<{ mode?: string }>;
}) {
  const params = await searchParams;
  const mode: "all" | "none" =
    params.mode === "all" || params.mode === "none" ? params.mode : "none";
  return <EvaluatorEdgeHarness mode={mode} />;
}
