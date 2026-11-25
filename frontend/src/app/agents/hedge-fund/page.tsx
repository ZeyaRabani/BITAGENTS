import type { Metadata } from "next";
import { AppShell } from "@/components/AppShell";
import { MarketAgentConsole } from "@/components/agents/MarketAgentConsole";

export const metadata: Metadata = {
  title: "Hedge Fund Agent - BIT Agents",
  description: "Buy and sell from a Circle wallet after Aomi simulates the swap.",
};

export default function HedgeFundAgentPage() {
  return (
    <AppShell title="Hedge Fund Agent">
      <MarketAgentConsole
        slug="hedge-fund"
        title="Hedge Fund Agent"
        intro="Connected to the Hedge Fund agent. This chat does SOL ↔ token swaps from its Circle wallet (Jupiter → Aomi simulate → Circle sign). For XOM/JPM-style baskets, use Launch Agent."
        prompts={[
          "Buy 0.01 SOL of JUP",
          "Sell 1 JUP to SOL",
          "Show my hedge fund wallet",
        ]}
      />
    </AppShell>
  );
}
