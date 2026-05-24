// I-cd-021 (#631) — Offline Inspector page. Renders a v1.0 signed bundle
// in-browser from a `.tar.gz` file dropped by a disconnected reviewer.
// No GPU, no backend, no API call.
"use client";

import { FileCheck2, UploadCloud } from "lucide-react";
import { useState } from "react";

import { InspectorView } from "@/app/inspector/[runId]/inspector_view";
import { ErrorState } from "@/components/states/state_kit";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  BundleClientLoaderError,
  loadBundleFromTarGz,
} from "@/lib/inspector_bundle_client_loader";
import type { LoadedBundle } from "@/lib/inspector_bundle_loader";

export default function InspectorOfflinePage() {
  const [bundle, setBundle] = useState<LoadedBundle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  async function handleFile(file: File) {
    setLoading(true);
    setError(null);
    setBundle(null);
    try {
      const loaded = await loadBundleFromTarGz(file);
      setBundle(loaded);
    } catch (exc) {
      const message =
        exc instanceof BundleClientLoaderError
          ? `${exc.code}: ${exc.message}`
          : (exc as Error).message;
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  function onInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  }

  function onDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  }

  if (bundle) {
    return (
      <InspectorView
        bundle={bundle}
        signaturePresent={bundle.signaturePresent}
      />
    );
  }

  return (
    <main
      className="mx-auto flex max-w-3xl flex-col gap-6 p-6"
      data-testid="inspector-offline"
    >
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Offline Inspector</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          <p className="text-muted-foreground">
            Drop or pick a signed POLARIS audit bundle (<code>.tar.gz</code>).
            The bundle is verified and rendered entirely in your browser — no
            backend or GPU required. SHA-256 of every file is checked against
            the manifest. GPG cryptographic verify is out of scope (the
            bundle&apos;s <code>.asc</code> presence is detected, but full
            key-trust verification needs a CLI).
          </p>
          <div
            data-testid="inspector-offline-dropzone"
            role="button"
            tabIndex={0}
            aria-label="Drop bundle tar.gz or click to pick a file"
            onDrop={onDrop}
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                document.getElementById("inspector-offline-input")?.click();
              }
            }}
            onClick={() =>
              document.getElementById("inspector-offline-input")?.click()
            }
            className={`focus-visible:ring-ring/70 ease-standard flex min-h-40 cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-8 text-center transition-colors duration-150 focus-visible:ring-2 focus-visible:outline-none ${
              dragOver
                ? "border-primary/50 bg-primary/5"
                : "border-border bg-muted/20 hover:border-primary/30 hover:bg-muted/40"
            }`}
          >
            {loading ? (
              <>
                <FileCheck2
                  aria-hidden
                  className="text-muted-foreground h-7 w-7 animate-pulse motion-reduce:animate-none"
                />
                <span className="text-foreground text-sm font-medium">
                  Verifying bundle…
                </span>
                <span className="text-muted-foreground text-xs">
                  Checking SHA-256 of every file against the manifest
                </span>
              </>
            ) : (
              <>
                <UploadCloud
                  aria-hidden
                  className={`h-7 w-7 ${dragOver ? "text-primary" : "text-muted-foreground"}`}
                />
                <span className="text-foreground text-sm font-medium">
                  {dragOver ? "Drop to verify" : "Drop a signed bundle"}
                </span>
                <span className="text-muted-foreground text-xs">
                  <code className="font-mono">.tar.gz</code> — or press Enter /
                  click to pick a file
                </span>
              </>
            )}
          </div>
          <input
            id="inspector-offline-input"
            data-testid="inspector-offline-file-input"
            type="file"
            accept=".tar.gz,.tgz,application/gzip,application/x-gzip"
            className="sr-only"
            onChange={onInputChange}
          />
          {error ? (
            <div data-testid="inspector-offline-error">
              <ErrorState title="Bundle could not be loaded" message={error} />
            </div>
          ) : null}
        </CardContent>
      </Card>
    </main>
  );
}
