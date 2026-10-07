import type { Metadata } from "next";
import { AppShell } from "@/components/AppShell";
import { HedgeFundConsole } from "@/components/agents/HedgeFundConsole";
import { HEDGE_FUND } from "@/lib/hedgeFundConfig";

export const metadata: Metadata = {
  title: "Hedge Fund Agent - BITAGENTS",
  description: HEDGE_FUND.description,
  robots: { index: false, follow: false },
};

export default function HedgeFundPage() {
  return (
    <AppShell
      title={HEDGE_FUND.name}
      subtitle={`${HEDGE_FUND.tagline} · Covenant-inspired Solana portfolio analysis`}
    >
      <HedgeFundConsole />
    </AppShell>
  );
}
