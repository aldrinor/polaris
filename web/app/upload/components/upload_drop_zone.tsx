"use client";

import { useId, useRef, useState } from "react";

import { getUpload, uploadDocument, type UploadResponse } from "@/lib/api";

import { DocumentPreview } from "./document_preview";

const MAX_BYTES = 50 * 1024 * 1024;
const ALLOWED_EXT = new Set([".pdf", ".docx", ".md", ".txt"]);

type Status = "uploading" | "completed" | "error";
type ParseStatus = "queued" | "completed" | "failed";
type FileEntry = {
  id: string;
  name: string;
  status: Status;
  error?: string;
  response?: UploadResponse;
  parse_status?: ParseStatus;
  chunk_preview_count?: number;
};

const POLL_MAX = 10;
const POLL_INTERVAL_MS = 1000;

async function pollParseStatus(
  document_id: string,
  onUpdate: (status: ParseStatus, count: number) => void,
): Promise<void> {
  for (let i = 0; i < POLL_MAX; i++) {
    await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
    try {
      const fresh = await getUpload(document_id);
      onUpdate(fresh.parse_status as ParseStatus, fresh.chunk_preview.length);
      if (fresh.parse_status !== "queued") return;
    } catch {
      return;
    }
  }
}

const extOf = (n: string) => {
  const i = n.lastIndexOf(".");
  return i === -1 ? "" : n.slice(i).toLowerCase();
};

export function UploadDropZone() {
  const baseId = useId();
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [openPreviewDocId, setOpenPreviewDocId] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  let counter = 0;

  const handleFiles = async (incoming: FileList | File[]) => {
    for (const f of Array.from(incoming)) {
      const id = `${baseId}-${counter++}-${Date.now()}`;
      const ext = extOf(f.name);
      if (!ALLOWED_EXT.has(ext)) {
        setFiles((p) => [
          ...p,
          {
            id,
            name: f.name,
            status: "error",
            error: `unsupported extension ${ext}`,
          },
        ]);
        continue;
      }
      if (f.size > MAX_BYTES) {
        setFiles((p) => [
          ...p,
          {
            id,
            name: f.name,
            status: "error",
            error: `exceeds 50MB limit (${(f.size / 1024 / 1024).toFixed(1)}MB)`,
          },
        ]);
        continue;
      }
      setFiles((p) => [...p, { id, name: f.name, status: "uploading" }]);
      try {
        const response = await uploadDocument(f, "UNKNOWN");
        const ps = response.parse_status as ParseStatus;
        setFiles((p) =>
          p.map((e) =>
            e.id === id
              ? {
                  ...e,
                  status: "completed",
                  response,
                  parse_status: ps,
                  chunk_preview_count: response.chunk_preview.length,
                }
              : e,
          ),
        );
        if (ps === "queued") {
          pollParseStatus(response.document_id, (status, count) => {
            setFiles((p) =>
              p.map((e) =>
                e.id === id
                  ? { ...e, parse_status: status, chunk_preview_count: count }
                  : e,
              ),
            );
          });
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : "upload failed";
        setFiles((p) =>
          p.map((e) =>
            e.id === id ? { ...e, status: "error", error: msg } : e,
          ),
        );
      }
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div
        data-testid="upload-dropzone"
        role="button"
        tabIndex={0}
        aria-label="Drop files here or click to browse"
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          if (e.dataTransfer?.files) handleFiles(e.dataTransfer.files);
        }}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
        }}
        className="border-border bg-muted/10 flex min-h-32 flex-col items-center justify-center rounded-xl border-2 border-dashed p-8 text-center"
      >
        <p className="text-foreground text-sm font-medium">Drop files here</p>
        <p className="text-muted-foreground text-xs">
          or click to browse · PDF, DOCX, MD, TXT · max 50MB
        </p>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".pdf,.docx,.md,.txt"
          onChange={(e) => e.target.files && handleFiles(e.target.files)}
          className="sr-only"
        />
      </div>
      {files.length > 0 && (
        <ul className="flex flex-col gap-2">
          {files.map((f) => (
            <li
              key={f.id}
              data-testid={`upload-file-${f.id}`}
              data-status={f.status}
              className="border-border bg-muted/20 flex items-center justify-between gap-2 rounded-lg border p-3 text-sm"
            >
              <span className="text-foreground truncate">{f.name}</span>
              <span className="text-muted-foreground text-xs">
                {f.status === "uploading" && "uploading…"}
                {f.status === "completed" && f.response && (
                  <span className="flex flex-col items-end gap-0.5">
                    <span data-testid="upload-doc-id">
                      {f.response.document_id}
                    </span>
                    <span
                      data-testid={`upload-parse-${f.id}`}
                      data-parse-status={f.parse_status}
                    >
                      {f.parse_status === "queued" &&
                        `parsing… (${f.chunk_preview_count ?? 0} chunks so far)`}
                      {f.parse_status === "completed" &&
                        `completed · ${f.chunk_preview_count ?? 0} chunks`}
                      {f.parse_status === "failed" && "parse failed"}
                    </span>
                    {f.parse_status === "completed" &&
                      (f.chunk_preview_count ?? 0) > 0 && (
                        <button
                          type="button"
                          data-testid={`open-preview-${f.id}`}
                          onClick={() =>
                            setOpenPreviewDocId(
                              openPreviewDocId === f.response!.document_id
                                ? null
                                : f.response!.document_id,
                            )
                          }
                          className="text-xs underline"
                        >
                          {openPreviewDocId === f.response.document_id
                            ? "Close preview"
                            : "Open preview"}
                        </button>
                      )}
                  </span>
                )}
                {f.status === "error" && (
                  <span className="text-rose-700">{f.error}</span>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
      {openPreviewDocId && <DocumentPreview documentId={openPreviewDocId} />}
    </div>
  );
}
