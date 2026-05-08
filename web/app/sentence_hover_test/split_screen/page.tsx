"use client";

import { SplitScreen } from "@/app/generation/components/split_screen";

export default function SplitScreenFixturePage() {
  return (
    <main
      data-testid="page-root"
      className="bg-background text-foreground h-screen w-screen"
    >
      <div className="h-1/2">
        <SplitScreen
          initialPercent={50}
          left={
            <div data-testid="left-content" className="p-6">
              LEFT-CONTENT
            </div>
          }
          right={
            <div data-testid="right-content" className="p-6">
              RIGHT-CONTENT
            </div>
          }
        />
      </div>
    </main>
  );
}
