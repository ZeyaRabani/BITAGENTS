import { STATUS_LABELS, STATUS_ORDER, type AgentTask } from "@bitagents/shared";
import { cn } from "@/lib/utils";

export function TaskTimeline({ task }: { task: AgentTask }) {
  const historyStatuses = new Set(task.history.map((item) => item.status));
  const failed = task.status === "failed";

  return (
    <div className="grid grid-cols-5 gap-2">
      {STATUS_ORDER.map((status) => {
        const done = historyStatuses.has(status);
        const active = task.status === status;
        return (
          <div key={status} className="min-w-0">
            <div
              className={cn(
                "h-1.5 w-full",
                done ? "bg-signal" : active ? "bg-signal-soft" : "bg-border",
                failed && !done && "bg-danger/40"
              )}
            />
            <p
              className={cn(
                "mt-2 truncate font-mono text-[10px] uppercase tracking-[0.1em]",
                done || active ? "text-foreground" : "text-muted-foreground/60"
              )}
            >
              {STATUS_LABELS[status]}
            </p>
          </div>
        );
      })}
    </div>
  );
}
