import type { Metadata } from "next";
import { AppShell } from "@/components/AppShell";
import { ResearchAgentConsole } from "@/components/agents/ResearchAgentConsole";
import { RESEARCH_AGENTS } from "@/lib/researchAgentsConfig";

const config = RESEARCH_AGENTS["due-diligence"];

export const metadata: Metadata = {
  title: "Due Diligence Agent - BITAGENTS",
  description: config.description,
};

export default function DueDiligencePage() {
  return (
    <AppShell
      title={config.name}
      subtitle={`${config.tagline} · ${config.description}`}
    >
      <ResearchAgentConsole config={config} />
    </AppShell>
  );
}
