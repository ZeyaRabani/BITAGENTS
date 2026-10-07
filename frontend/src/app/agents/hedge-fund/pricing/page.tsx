import type { Metadata } from "next";
import { AppShell } from "@/components/AppShell";
import { HedgeFundPricingPage } from "@/components/agents/HedgeFundPricingPage";

export const metadata: Metadata = {
  title: "Hedge Fund Pricing - BITAGENTS",
  description: "1/10 fee model — 1% management and 10% performance vs traditional 2/20.",
  robots: { index: false, follow: false },
};

export default function HedgeFundPricingRoute() {
  return (
    <AppShell title="Hedge Fund Pricing" subtitle="1% management · 10% performance · vs 2/20">
      <HedgeFundPricingPage />
    </AppShell>
  );
}
