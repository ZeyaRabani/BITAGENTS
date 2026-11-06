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
        intro="Connected to the Hedge Fund agent. Ask for a SOL buy or a token sell. Each swap is simulated on Aomi before this agent's Circle wallet signs."
        prompts={[
          "Buy 0.01 SOL of JUP",
          "Sell 1 JUP to SOL",
          "Show my hedge fund wallet",
        ]}
      />
    </AppShell>
  );
}
