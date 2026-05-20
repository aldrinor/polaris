// I-cd-013a (GH#609) — manifest.files[] table (path + content_type + size + sha256 head).
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { BundleManifest } from "@/lib/signed_bundle";

interface HashChainPanelProps {
  manifest: BundleManifest;
}

export function HashChainPanel({ manifest }: HashChainPanelProps) {
  return (
    <Card data-testid="hash-chain-panel">
      <CardHeader>
        <CardTitle>Hash chain ({manifest.files.length} files)</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-border text-muted-foreground border-b text-xs tracking-wide uppercase">
              <tr>
                <th className="px-2 py-2">Path</th>
                <th className="px-2 py-2">Content type</th>
                <th className="px-2 py-2 text-right">Size (bytes)</th>
                <th className="px-2 py-2">SHA256 (head)</th>
              </tr>
            </thead>
            <tbody>
              {manifest.files.map((f) => (
                <tr
                  key={f.path}
                  className="border-border border-b last:border-0"
                  data-testid="hash-chain-row"
                  data-content-type={f.content_type}
                >
                  <td className="px-2 py-2 align-top font-mono text-xs">
                    {f.path}
                  </td>
                  <td className="px-2 py-2 align-top">
                    <span className="bg-muted inline-flex items-center rounded-md px-2 py-0.5 text-xs">
                      {f.content_type}
                    </span>
                  </td>
                  <td className="px-2 py-2 text-right align-top font-mono text-xs">
                    {f.size_bytes.toLocaleString()}
                  </td>
                  <td className="px-2 py-2 align-top font-mono text-xs">
                    {f.sha256.slice(0, 16)}&hellip;
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
