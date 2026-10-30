import type { Metadata } from "next";
import { AppShell } from "@/components/AppShell";
import { VolumeAgentSimpleConsole } from "@/components/agents/VolumeAgentSimpleConsole";

export const metadata: Metadata = {
  title: "BITAGENTS Volume - BIT Agents",
  description: "Start a BITAGENTS volume campaign in one click — deposit SOL, pick a size, go.",
};

export default function VolumeAgentSimplePage() {
  return (
    <AppShell title="BITAGENTS Volume">
      <VolumeAgentSimpleConsole />
    </AppShell>
  );
}
