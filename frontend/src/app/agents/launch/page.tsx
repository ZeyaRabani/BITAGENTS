import type { Metadata } from "next";
import { AppShell } from "@/components/AppShell";
import { LaunchAgentConsole } from "@/components/agents/LaunchAgentConsole";

export const metadata: Metadata = {
  title: "Launch Agents - BIT Agents",
  description: "Compose and launch a custom agent with modules, connectors, and a 1 SOL fee.",
};

export default function LaunchAgentsPage() {
  return (
    <AppShell
      title="Launch Agents"
      subtitle="Name your agent, define its task, pick modules, then pay 1 SOL to launch."
    >
      <LaunchAgentConsole />
    </AppShell>
  );
}
