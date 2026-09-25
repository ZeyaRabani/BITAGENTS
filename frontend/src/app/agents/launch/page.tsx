import type { Metadata } from "next";
import { AppShell } from "@/components/AppShell";
import { LaunchAgentConsole } from "@/components/agents/LaunchAgentConsole";

export const metadata: Metadata = {
  title: "Launch Agents - BIT Agents",
  description: "Compose and launch a custom agent with modules and connectors.",
};

export default function LaunchAgentsPage({
  searchParams,
}: {
  searchParams?: { edit?: string };
}) {
  const editing = Boolean(searchParams?.edit);
  return (
    <AppShell
      title={editing ? "Edit agent" : "Launch Agents"}
      subtitle={
        editing
          ? "Update this agent and relaunch it. No extra launch fee."
          : "Name your agent, define its task, pick modules, then launch."
      }
    >
      <LaunchAgentConsole editId={searchParams?.edit} />
    </AppShell>
  );
}
