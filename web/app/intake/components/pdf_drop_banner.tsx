"use client";

import { useEffect, useState } from "react";

function isPdf(file: File): boolean {
  return (
    file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf")
  );
}

export function PdfDropBanner() {
  const [shown, setShown] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const handleDragOver = (e: DragEvent) => e.preventDefault();
    const handleDrop = (e: DragEvent) => {
      const files = e.dataTransfer?.files;
      if (!files || files.length === 0) return;
      let pdfFound = false;
      for (let i = 0; i < files.length; i++) {
        const f = files.item(i);
        if (f && isPdf(f)) {
          pdfFound = true;
          break;
        }
      }
      if (pdfFound) {
        e.preventDefault();
        setShown(true);
      }
    };
    window.addEventListener("dragover", handleDragOver);
    window.addEventListener("drop", handleDrop);
    setReady(true);
    return () => {
      window.removeEventListener("dragover", handleDragOver);
      window.removeEventListener("drop", handleDrop);
    };
  }, []);

  if (!shown)
    return (
      <span
        data-testid="pdf-drop-ready"
        data-ready={ready ? "1" : "0"}
        className="sr-only"
      />
    );

  return (
    <div
      data-testid="pdf-drop-banner"
      className="flex items-center justify-between gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-900 dark:text-amber-200"
    >
      <span>PDFs go through the upload flow (coming soon).</span>
      <button
        type="button"
        data-testid="pdf-drop-dismiss"
        onClick={() => setShown(false)}
        className="text-xs font-medium underline-offset-2 hover:underline"
      >
        Dismiss
      </button>
    </div>
  );
}
