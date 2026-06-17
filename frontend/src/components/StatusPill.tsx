import { STATUS_LABELS, type TaskStatus } from "@bitagents/shared";
import { cn } from "@/lib/utils";

const styles: Record<TaskStatus, string> = {
  created: "border-border bg-surface-2 text-muted-foreground",
  paid: "border-signal/50 bg-signal/10 text-signal",
  assigned: "border-warn/50 bg-warn/10 text-warn",
  computing: "border-signal/60 bg-signal/15 text-signal-soft",
  completed: "border-success/60 bg-success/10 text-success",
  failed: "border-danger/70 bg-danger/10 text-danger"
};

export function StatusPill({ status, className }: { status: TaskStatus; className?: string }) {
  const isComputing = status === "computing";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 border px-2.5 py-1 font-mono text-[11px] font-semibold uppercase tracking-[0.12em]",
        styles[status],
        className
      )}
    >
      {isComputing ? <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-current" /> : null}
      {STATUS_LABELS[status]}
    </span>
  );
}
