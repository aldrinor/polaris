"use client";

import { SplitScreen } from "@/app/generation/components/split_screen";

export default function SplitScreenFixturePage() {
  return (
    <main className="bg-background text-foreground h-screen w-screen">
      <SplitScreen
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
    </main>
  );
}
