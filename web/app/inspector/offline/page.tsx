// I-cd-021 (#631) — Offline Inspector page. Renders a v1.0 signed bundle
// in-browser from a `.tar.gz` file dropped by a disconnected reviewer.
// No GPU, no backend, no API call.
"use client";

import { useState } from "react";

import { InspectorView } from "@/app/inspector/[runId]/inspector_view";
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
            className={`border-border focus-visible:ring-ring flex min-h-32 cursor-pointer items-center justify-center rounded border-2 border-dashed px-6 py-8 text-center text-sm focus-visible:ring-2 focus-visible:outline-none ${
              dragOver ? "bg-muted/60" : "bg-muted/20"
            }`}
          >
            {loading
              ? "Loading bundle…"
              : "Drop bundle.tar.gz here or press Enter to pick a file"}
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
            <div
              data-testid="inspector-offline-error"
              role="alert"
              className="rounded border border-rose-500/40 bg-rose-500/5 p-3 text-sm text-rose-700 dark:text-rose-300"
            >
              <strong className="block">Bundle could not be loaded</strong>
              <code className="mt-1 block text-xs">{error}</code>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </main>
  );
}
