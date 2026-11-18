import type { Metadata } from "next";
import { CustomAgentConsole } from "@/components/agents/builder/CustomAgentConsole";

export const metadata: Metadata = {
  title: "Your strategy - BITAGENTS",
  description: "Signals, performance and run log for a strategy you built.",
};

export default function CustomAgentPage({ params }: { params: { id: string } }) {
  return <CustomAgentConsole agentId={params.id} />;
}
