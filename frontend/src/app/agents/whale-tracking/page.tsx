import type { Metadata } from "next";
import { AppShell } from "@/components/AppShell";
import { ResearchAgentConsole } from "@/components/agents/ResearchAgentConsole";
import { RESEARCH_AGENTS } from "@/lib/researchAgentsConfig";

const config = RESEARCH_AGENTS["whale-tracking"];

export const metadata: Metadata = {
  title: "Whale Tracking Agent - BITAGENTS",
  description: config.description,
};

export default function WhaleTrackingPage() {
  return (
    <AppShell
      title={config.name}
      subtitle={`${config.tagline} · ${config.description}`}
    >
      <ResearchAgentConsole config={config} />
    </AppShell>
  );
}
