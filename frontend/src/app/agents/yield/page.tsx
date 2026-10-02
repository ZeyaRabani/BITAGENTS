import type { Metadata } from "next";
import { AppShell } from "@/components/AppShell";
import { YieldAgentConsole } from "@/components/agents/YieldAgentConsole";

export const metadata: Metadata = {
  title: "Yield Agent - BIT Agents",
  description:
    "Deposit into Kamino, Jupiter JLP, MarginFi, Drift, or Save based on yield type.",
};

export default function YieldAgentPage() {
  return (
    <AppShell
      title="Yield Agent"
      subtitle="Kamino, Jupiter JLP, MarginFi, Drift, and Save. Pick a yield type."
    >
      <YieldAgentConsole />
    </AppShell>
  );
}
