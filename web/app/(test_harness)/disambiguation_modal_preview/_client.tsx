"use client";

import { useState } from "react";

import {
  DisambiguationModal,
  type DisambiguationCluster,
} from "@/app/intake/components/disambiguation_modal";

const FIXTURE_CLUSTERS: DisambiguationCluster[] =
  "syndrome,institute,chemical,company,course".split(",").map((label, i) => ({
    cluster_id: i,
    label,
    sample_snippets: [`sample ${label} snippet`],
  }));

export function DisambiguationModalHarnessClient({ count }: { count: number }) {
  const [open, setOpen] = useState(true);
  const [lastPicked, setLastPicked] = useState<number | null>(null);
  return (
    <>
      <DisambiguationModal
        open={open}
        clusters={FIXTURE_CLUSTERS.slice(0, count)}
        onSelectCluster={(cid) => {
          setLastPicked(cid);
          setOpen(false);
        }}
        onCancel={() => setOpen(false)}
      />
      <output data-testid="last-picked">
        {lastPicked === null ? "" : String(lastPicked)}
      </output>
      <button
        type="button"
        data-testid="reopen"
        onClick={() => {
          setLastPicked(null);
          setOpen(true);
        }}
      >
        Reopen
      </button>
    </>
  );
}
