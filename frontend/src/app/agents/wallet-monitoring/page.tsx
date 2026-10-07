import type { Metadata } from "next";
import { AppShell } from "@/components/AppShell";
import { ResearchAgentConsole } from "@/components/agents/ResearchAgentConsole";
import { RESEARCH_AGENTS } from "@/lib/researchAgentsConfig";

const config = RESEARCH_AGENTS["wallet-monitoring"];

export const metadata: Metadata = {
  title: "Wallet Monitoring Agent - BITAGENTS",
  description: config.description,
};

export default function WalletMonitoringPage() {
  return (
    <AppShell
      title={config.name}
      subtitle={`${config.tagline} · ${config.description}`}
    >
      <ResearchAgentConsole config={config} />
    </AppShell>
  );
}
