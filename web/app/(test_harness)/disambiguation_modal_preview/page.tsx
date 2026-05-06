import { DisambiguationModalHarnessClient } from "./_client";

export const metadata = {
  robots: { index: false, follow: false },
};

export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ n?: string }>;
}) {
  const { n } = await searchParams;
  const count = n === "5" ? 5 : n === "3" ? 3 : 2;
  return <DisambiguationModalHarnessClient count={count} />;
}
