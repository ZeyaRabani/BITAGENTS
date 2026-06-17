import { AgentRunner } from "@/components/AgentRunner";
import { LinkButton, PageShell } from "@/components/primitives";
import { TaskList } from "@/components/TaskList";

export default function AppWorkspacePage() {
  return (
    <PageShell
      eyebrow="Workspace"
      title="Run an agent"
      description="Connect Phantom, pick an agent, and submit a task. Devnet Demo Mode pays a 0.001 SOL fee to the treasury; mainnet is read-only. No wallet? Run a free demo."
      actions={
        <LinkButton href="/agents" variant="outline" size="sm">
          Agent catalog
        </LinkButton>
      }
    >
      <div className="space-y-10">
        <AgentRunner />
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="font-display text-lg font-semibold text-foreground">Recent tasks</h2>
            <LinkButton href="/tasks" variant="ghost" size="sm">
              View all →
            </LinkButton>
          </div>
          <TaskList limit={5} />
        </section>
      </div>
    </PageShell>
  );
}
