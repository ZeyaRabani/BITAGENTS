import { LinkButton, PageShell } from "@/components/primitives";
import { TaskList } from "@/components/TaskList";

export default function TasksPage() {
  return (
    <PageShell
      eyebrow="Tasks"
      title="Task history"
      description="Every agent run is recorded with its status, assigned provider, devnet payment signature, runtime, and full result. Expand a row to inspect the output."
      actions={
        <LinkButton href="/app" size="sm">
          Run an agent
        </LinkButton>
      }
    >
      <TaskList showFilters />
    </PageShell>
  );
}
