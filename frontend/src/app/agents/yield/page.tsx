import type { Metadata } from "next";
import { AppShell } from "@/components/AppShell";
import { YieldAgentConsole } from "@/components/agents/YieldAgentConsole";

export const metadata: Metadata = {
  title: "Yield Agent - BIT Agents",
  description:
    "Deposit SOL into Kamino, Jupiter JLP, or Save.",
};

export default function YieldAgentPage() {
  return (
    <AppShell
      title="Yield Agent"
      subtitle="Kamino, Jupiter JLP, and Save. Ask in chat or pick a yield type."
    >
      <YieldAgentConsole />
    </AppShell>
  );
}
