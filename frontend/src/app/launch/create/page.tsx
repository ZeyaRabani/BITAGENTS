import { AgentBuilderChat } from "@/components/launch/AgentBuilderChat";

export default function CreateAgentPage() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
      <div className="mb-8 border-b border-grid pb-6">
        <h1 className="font-display text-3xl font-bold leading-tight md:text-4xl">Launch an agent</h1>
        <p className="mt-2 max-w-xl text-sm text-muted-foreground">
          No form — just talk to the agent builder. Describe what you want, it asks the right
          follow-up questions and writes the actual instructions your agent runs on.
        </p>
      </div>

      <AgentBuilderChat />
    </div>
  );
}
