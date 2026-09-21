import type { Metadata } from "next";
import { AppShell } from "@/components/AppShell";
import { LaunchedAgentDetail } from "@/components/agents/LaunchedAgentDetail";

export const metadata: Metadata = {
  title: "Community Agent - BIT Agents",
  description: "View a community-launched agent on the BIT Agents marketplace.",
};

export default function LaunchedAgentPage({
  params,
}: {
  params: { id: string };
}) {
  return (
    <AppShell title="Community agent" subtitle="Public agent listed on the marketplace.">
      <LaunchedAgentDetail agentId={params.id} />
    </AppShell>
  );
}
