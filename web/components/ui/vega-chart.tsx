"use client";

import vegaEmbed from "vega-embed";
import { useEffect, useRef } from "react";

import type { VegaLiteSpec } from "@/lib/api";

interface VegaChartProps {
  spec: VegaLiteSpec;
  className?: string;
  onPointClick?: (datum: Record<string, unknown>) => void;
}

/**
 * F10 Vega-Lite v5 client renderer (Phase 2B Task 2B.2 frontend half).
 *
 * Renders a Vega-Lite spec via vega-embed. The spec arrives from the
 * backend `/runs/{run_id}/charts/{chart_type}` endpoint with the
 * polaris_provenance extension. Click events on datums fire onPointClick
 * with the datum (which includes evidence_id) so the host page can
 * surface the source span.
 */
export function VegaChart({ spec, className, onPointClick }: VegaChartProps) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    let cancelled = false;
    let viewToFinalize: { finalize: () => void } | null = null;

    // VegaLiteSpec from our API types is intentionally permissive; vega-embed
    // narrows to its full TopLevelSpec type. Casting through unknown is the
    // documented bridge.
    vegaEmbed(ref.current, spec as unknown as Parameters<typeof vegaEmbed>[1], {
      actions: false,
      renderer: "svg",
    })
      .then((result) => {
        if (cancelled) {
          result.view.finalize();
          return;
        }
        viewToFinalize = result.view;
        if (onPointClick) {
          result.view.addEventListener("click", (_event, item) => {
            if (item?.datum) {
              onPointClick(item.datum as Record<string, unknown>);
            }
          });
        }
      })
      .catch((err) => {
        console.error("vega-embed render failed", err);
      });

    return () => {
      cancelled = true;
      viewToFinalize?.finalize();
    };
  }, [spec, onPointClick]);

  return (
    <div
      ref={ref}
      className={className ?? "polaris-vega-chart w-full overflow-x-auto"}
    />
  );
}
