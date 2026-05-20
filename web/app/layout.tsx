import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { AppShellGate } from "@/components/app_shell_gate";
import { Toaster } from "@/components/ui/sonner";

import "./globals.css";

const geist_sans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geist_mono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "POLARIS Canada — Sovereign Deep Research",
  description:
    "Two-family verified evidence pipelines for Government of Canada policy work.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geist_sans.variable} ${geist_mono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col">
        <AppShellGate>{children}</AppShellGate>
        <Toaster />
      </body>
    </html>
  );
}
