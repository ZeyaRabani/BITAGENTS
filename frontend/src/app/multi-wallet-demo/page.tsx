import type { Metadata } from "next";
import { AppShell } from "@/components/AppShell";
import { MultiWalletDemo } from "@/components/agents/MultiWalletDemo";

export const metadata: Metadata = {
  title: "Operation Multi-wallet — BIT Agents",
  description: "Demo: each user gets their own dedicated deposit wallet instead of one shared pool.",
};

export default function MultiWalletDemoPage() {
  return (
    <AppShell
      title="Operation Multi-wallet"
      subtitle="Demo — connect your wallet to see your own dedicated deposit address, generated on the spot. Not live yet: research/demo only, running on serverless-dca-prototype."
    >
      <MultiWalletDemo />
    </AppShell>
  );
}
