import type { Metadata } from "next";
import { AppShell } from "@/components/AppShell";
import { CustomAgentConsole } from "@/components/agents/CustomAgentConsole";

export const metadata: Metadata = {
  title: "Custom Agent - BIT Agents",
  description: "Chat with your custom AI agent.",
};

export default async function CustomAgentChatPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <AppShell title="Custom Agent" subtitle="Chat with the agent you created.">
      <CustomAgentConsole agentId={id} />
    </AppShell>
  );
}
