import type { Metadata } from "next";
import { AppShell } from "@/components/AppShell";
import { YieldAgentConsole } from "@/components/agents/YieldAgentConsole";

export const metadata: Metadata = {
  title: "Yield Agent - BIT Agents",
  description:
    "Deposit SOL, USDC, or USDT, compare yields for your capital and duration, and stake the best protocol.",
};

export default function YieldAgentPage() {
  return (
    <AppShell
      title="Yield Agent"
      subtitle="Compare yields for your asset, capital, and duration, then stake the best protocol"
    >
      <YieldAgentConsole />
    </AppShell>
  );
}
