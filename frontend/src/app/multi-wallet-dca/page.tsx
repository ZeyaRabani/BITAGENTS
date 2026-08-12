import type { Metadata } from "next";
import { AppShell } from "@/components/AppShell";
import { MultiWalletDcaConsole } from "@/components/agents/MultiWalletDcaConsole";

export const metadata: Metadata = {
  title: "Multi-wallet DCA — BIT Agents",
  description: "Real DCA deposits, plans, and withdrawals through your own dedicated wallet.",
};

export default function MultiWalletDcaPage() {
  return (
    <AppShell
      title="Multi-wallet DCA"
      subtitle="Real integration — each connected wallet gets its own dedicated DCA wallet. Running alongside the existing pooled DCA Agent, not replacing it."
    >
      <MultiWalletDcaConsole />
    </AppShell>
  );
}
