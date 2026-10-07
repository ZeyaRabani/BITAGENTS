import type { Metadata } from "next";
import { AppShell } from "@/components/AppShell";
import { DcaAgentConsole } from "@/components/agents/DcaAgentConsole";
import { DCA_AGENT } from "@/lib/dcaAgentSimulation";

export const metadata: Metadata = {
  title: "DCA Agent - BITAGENTS",
  description: "Run the Solana DCA Agent - recurring buys, and plan management.",
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
