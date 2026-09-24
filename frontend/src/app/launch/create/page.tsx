import { AgentBuilderChat } from "@/components/launch/AgentBuilderChat";

export default async function CreateAgentPage({
  searchParams,
}: {
  searchParams: Promise<{ agentId?: string }>;
}) {
  const { agentId } = await searchParams;

  return (
    <div className="mx-auto max-w-5xl px-4 py-10 sm:px-6">
      <div className="mb-8 border-b border-grid pb-6">
        <h1 className="font-display text-3xl font-bold leading-tight md:text-4xl">
          {agentId ? "Resume your agent" : "Launch an agent"}
        </h1>
        <p className="mt-2 max-w-xl text-sm text-muted-foreground">
          {agentId
            ? "Picking up where you left off — the full conversation is loaded below."
            : "No form — just talk to the agent builder. Describe what you want, it asks the right follow-up questions and writes the actual instructions your agent runs on."}
        </p>
      </div>

      <AgentBuilderChat resumeAgentId={agentId} />
    </div>
  );
}
