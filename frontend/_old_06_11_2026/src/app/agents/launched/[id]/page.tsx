import type { Metadata } from "next";
import { LaunchedAgentDetail } from "@/components/agents/LaunchedAgentDetail";

export const metadata: Metadata = {
  title: "Community Agent - BIT Agents",
  description: "Chat with a community-launched agent on the BIT Agents marketplace.",
};

export default function LaunchedAgentPage({
  params,
}: {
  params: { id: string };
}) {
  return <LaunchedAgentDetail agentId={params.id} />;
}
