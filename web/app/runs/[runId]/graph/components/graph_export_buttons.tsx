"use client";

import type cytoscape from "cytoscape";

import { Button } from "@/components/ui/button";
import type { GraphPayload } from "@/lib/api";

import { exportJSON, exportPNG, triggerDownload } from "./graph_export";

interface GraphExportButtonsProps {
  cy: cytoscape.Core | null;
  payload: GraphPayload;
}

export function GraphExportButtons({ cy, payload }: GraphExportButtonsProps) {
  const onExportPng = async () => {
    const blob = await exportPNG(cy);
    if (!blob) return;
    triggerDownload(blob, `graph-${payload.run_id}.png`);
  };
  const onExportJson = () => {
    const blob = exportJSON(payload);
    triggerDownload(blob, `graph-${payload.run_id}.json`);
  };
  return (
    <>
      <Button
        data-testid="graph-export-png"
        variant="outline"
        size="sm"
        disabled={!cy}
        onClick={onExportPng}
      >
        Download PNG
      </Button>
      <Button
        data-testid="graph-export-json"
        variant="outline"
        size="sm"
        onClick={onExportJson}
      >
        Download JSON
      </Button>
    </>
  );
}
