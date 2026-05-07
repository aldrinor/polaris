"use client";

import { useEffect, useRef, useState } from "react";

import { getUpload, type UploadResponse } from "@/lib/api";

type Props = { documentId: string };

function clearMarks(doc: Document) {
  const marks = doc.querySelectorAll("mark[data-polaris-mark]");
  marks.forEach((m) => {
    const text = doc.createTextNode(m.textContent ?? "");
    m.replaceWith(text);
    m.parentNode?.normalize();
  });
}

function highlightFirstMatch(
  doc: Document,
  snippet: string,
): HTMLElement | null {
  if (!snippet) return null;
  clearMarks(doc);
  const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT);
  let node: Node | null = walker.nextNode();
  while (node) {
    const text = node.textContent ?? "";
    const idx = text.indexOf(snippet);
    if (idx !== -1) {
      const before = text.slice(0, idx);
      const matched = text.slice(idx, idx + snippet.length);
      const after = text.slice(idx + snippet.length);
      const parent = node.parentNode;
      if (!parent) return null;
      const beforeNode = doc.createTextNode(before);
      const mark = doc.createElement("mark");
      mark.setAttribute("data-polaris-mark", "1");
      mark.textContent = matched;
      const afterNode = doc.createTextNode(after);
      parent.insertBefore(beforeNode, node);
      parent.insertBefore(mark, node);
      parent.insertBefore(afterNode, node);
      parent.removeChild(node);
      return mark;
    }
    node = walker.nextNode();
  }
  return null;
}

export function DocumentPreview({ documentId }: Props) {
  const [response, setResponse] = useState<UploadResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  useEffect(() => {
    let cancelled = false;
    getUpload(documentId)
      .then((r) => {
        if (!cancelled) {
          setResponse(r);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [documentId]);

  const handleChunkClick = (snippet: string) => {
    const doc = iframeRef.current?.contentDocument;
    if (!doc) return;
    const mark = highlightFirstMatch(doc, snippet);
    if (mark) mark.scrollIntoView({ block: "center" });
  };

  if (loading) return <div data-testid="preview-loading">Loading…</div>;
  if (!response) return <div data-testid="preview-error">Failed to load</div>;

  return (
    <div
      className="border-border flex h-96 gap-2 rounded-lg border p-2"
      data-testid="document-preview"
    >
      <iframe
        ref={iframeRef}
        sandbox="allow-same-origin"
        srcDoc={response.html ?? ""}
        title={`preview-${documentId}`}
        className="border-border bg-background flex-1 rounded border"
        data-testid="preview-iframe"
      />
      <ul className="border-border flex w-64 flex-col gap-1 overflow-y-auto rounded border p-2">
        {response.chunk_preview.map((c, i) => (
          <li key={i}>
            <button
              type="button"
              data-testid={`chunk-${i}`}
              onClick={() => handleChunkClick(c)}
              className="hover:bg-muted/40 w-full truncate rounded p-1 text-left text-xs"
            >
              {c.slice(0, 80)}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
