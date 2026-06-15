import { STATUS_LABELS, STATUS_ORDER, type AgentTask } from "@bitagents/shared";

export function TaskTimeline({ task }: { task: AgentTask }) {
  const historyStatuses = new Set(task.history.map((item) => item.status));

  return (
    <div className="grid gap-2 sm:grid-cols-6">
      {STATUS_ORDER.map((status) => {
        const done = historyStatuses.has(status);
        const active = task.status === status;
        return (
          <div key={status} className="min-w-0">
            <div
              className={`h-2 rounded-full ${
                done ? "bg-ember" : active ? "bg-coral" : "bg-slate-700"
              }`}
            />
            <p className={`mt-2 truncate text-xs font-bold ${done || active ? "text-foreground" : "text-muted-foreground"}`}>
              {STATUS_LABELS[status]}
            </p>
          </div>
        );
      })}
    </div>
  );
}
