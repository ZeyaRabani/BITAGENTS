import type { Metadata } from "next";
import { AppShell } from "@/components/AppShell";
import { JupiterTradeConsole } from "@/components/agents/JupiterTradeConsole";
import { JUPITER_TRADE } from "@/lib/jupiterTradeConfig";

export const metadata: Metadata = {
  title: `${JUPITER_TRADE.name} - BIT Agents`,
  description: JUPITER_TRADE.description,
};

export default function JupiterTradePage() {
  return (
    <AppShell title={JUPITER_TRADE.name}>
      <JupiterTradeConsole />
    </AppShell>
  );
}
