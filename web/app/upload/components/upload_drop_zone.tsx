"use client";

import { useEffect, useId, useRef, useState } from "react";

import { UploadCloud } from "lucide-react";

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
  included?: boolean;
};

type UploadDropZoneProps = {
  onSelectionChange?: (docIds: string[]) => void;
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

export function UploadDropZone({
  onSelectionChange,
}: UploadDropZoneProps = {}) {
  const baseId = useId();
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [openPreviewDocId, setOpenPreviewDocId] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  // Drag-depth counter (Codex P2): naive onDragLeave flickers when the pointer
  // crosses child elements inside the zone; count enter/leave so active is true
  // iff the pointer is genuinely within the zone subtree.
  const dragDepth = useRef(0);
  const inputRef = useRef<HTMLInputElement>(null);
  let counter = 0;

  useEffect(() => {
    if (!onSelectionChange) return;
    const ids = files
      .filter((f) => f.included && f.parse_status === "completed" && f.response)
      .map((f) => f.response!.document_id);
    onSelectionChange(ids);
  }, [files, onSelectionChange]);

  const toggleIncluded = (id: string) => {
    setFiles((p) =>
      p.map((e) =>
        e.id === id ? { ...e, included: !(e.included ?? true) } : e,
      ),
    );
  };

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
                  included: true,
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
        data-drag-active={dragActive}
        onDragEnter={(e) => {
          e.preventDefault();
          dragDepth.current += 1;
          setDragActive(true);
        }}
        onDragOver={(e) => e.preventDefault()}
        onDragLeave={(e) => {
          e.preventDefault();
          dragDepth.current = Math.max(0, dragDepth.current - 1);
          if (dragDepth.current === 0) setDragActive(false);
        }}
        onDrop={(e) => {
          e.preventDefault();
          dragDepth.current = 0;
          setDragActive(false);
          if (e.dataTransfer?.files) handleFiles(e.dataTransfer.files);
        }}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
        }}
        className={`ease-standard focus-visible:ring-ring/70 flex min-h-40 cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-8 text-center transition-colors duration-150 outline-none focus-visible:ring-2 ${
          dragActive
            ? "border-primary bg-primary/10"
            : "border-border bg-muted/10 hover:border-primary/40 hover:bg-muted/30"
        }`}
      >
        <span
          className={`ease-standard flex h-11 w-11 items-center justify-center rounded-full transition-colors duration-150 ${
            dragActive
              ? "bg-primary/15 text-primary"
              : "bg-muted text-muted-foreground"
          }`}
        >
          <UploadCloud aria-hidden className="h-5 w-5" />
        </span>
        <p className="text-foreground text-sm font-medium">
          {dragActive ? "Drop to upload" : "Drop files here"}
        </p>
        <p className="text-muted-foreground text-xs">
          or click to browse · PDF, DOCX, MD, TXT · max 50MB
        </p>
      </div>
      {/* The file input is a SIBLING of the role=button dropzone (not nested) —
          nesting two interactive controls fails WCAG nested-interactive (axe).
          The dropzone's onClick/onKeyDown drives inputRef.click(). */}
      <input
        ref={inputRef}
        type="file"
        multiple
        accept=".pdf,.docx,.md,.txt"
        aria-label="Upload documents (PDF, DOCX, MD, TXT)"
        onChange={(e) => e.target.files && handleFiles(e.target.files)}
        className="sr-only"
      />
      {files.length > 0 && (
        <ul className="flex flex-col gap-2">
          {files.map((f) => (
            <li
              key={f.id}
              data-testid={`upload-file-${f.id}`}
              data-status={f.status}
              className="border-border bg-muted/20 flex items-center justify-between gap-2 rounded-lg border p-3 text-sm"
            >
              <span className="flex items-center gap-2">
                {f.status === "completed" && f.parse_status === "completed" && (
                  <input
                    type="checkbox"
                    data-testid={`include-toggle-${f.id}`}
                    checked={f.included ?? true}
                    onChange={() => toggleIncluded(f.id)}
                    aria-label={`Include ${f.name} in evidence pool`}
                  />
                )}
                <span className="text-foreground truncate">{f.name}</span>
              </span>
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
                  <span className="text-destructive">{f.error}</span>
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
