import type { Metadata } from "next";
import { AppShell } from "@/components/AppShell";
import { VolumeAgentConsole } from "@/components/agents/VolumeAgentConsole";
import { VOLUME_AGENT } from "@/lib/volumeAgentSimulation";

export const metadata: Metadata = {
  title: "Volume Agent - BITAGENTS",
  description:
    "Run Meteora DLMM volume campaigns — pool infrastructure, scheduled buy/sell cycles, 0.25% per leg.",
};

export default function VolumeAgentPage() {
  return (
    <AppShell
      title={VOLUME_AGENT.name}
      subtitle={`${VOLUME_AGENT.tagline} · ${VOLUME_AGENT.description}`}
    >
      <VolumeAgentConsole />
    </AppShell>
  );
}
