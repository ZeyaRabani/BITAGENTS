import type { Metadata } from "next";
import { AppShell } from "@/components/AppShell";
import { AgentsDashboardConsole } from "@/components/agents/AgentsDashboardConsole";

export const metadata: Metadata = {
  title: "Agent Dashboard - BIT Agents",
  description: "See agents you listed for sale, private launches, and subscriptions you bought.",
};

export default function AgentsDashboardPage() {
  return (
    <AppShell
      title="Dashboard"
      subtitle="Your listings, private agents, purchases, and sales."
    >
      <AgentsDashboardConsole />
    </AppShell>
  );
}
