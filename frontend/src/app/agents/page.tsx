import type { Metadata } from "next";
import { AgentMarketplace } from "@/components/agents/AgentMarketplace";

export const metadata: Metadata = {
  title: "Agent Marketplace - BITAGENTS",
  description: "Discover and deploy autonomous AI agents on the BITAGENTS marketplace.",
};

export default function AgentsPage() {
  return <AgentMarketplace />;
}
