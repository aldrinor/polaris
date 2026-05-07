"use client";

import { useState } from "react";

import { SelectedDocsIndicator } from "./selected_docs_indicator";
import { UploadDropZone } from "./upload_drop_zone";

export function UploadWorkspace() {
  const [selectedDocIds, setSelectedDocIds] = useState<string[]>([]);
  return (
    <div className="flex flex-col gap-4">
      <UploadDropZone onSelectionChange={setSelectedDocIds} />
      <SelectedDocsIndicator ids={selectedDocIds} />
    </div>
  );
}
