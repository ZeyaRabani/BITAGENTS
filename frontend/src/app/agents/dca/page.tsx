import type { Metadata } from "next";
import { AppShell } from "@/components/AppShell";
import { DcaAgentConsole } from "@/components/agents/DcaAgentConsole";
import { DCA_AGENT } from "@/lib/dcaAgentSimulation";

export const metadata: Metadata = {
  title: "DCA Agent - BIT Agents",
  description:
    "Aomi strategy-app style DCA UI on Next.js. Live Solana schedules via the Python /strategies API.",
};

export default function DcaAgentPage() {
  return (
    <AppShell
      title={DCA_AGENT.name}
      subtitle={`${DCA_AGENT.tagline} · ${DCA_AGENT.description}`}
    >
      <DcaAgentConsole />
    </AppShell>
  );
}
