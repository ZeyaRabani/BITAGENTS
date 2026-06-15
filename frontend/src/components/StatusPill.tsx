import { STATUS_LABELS, type TaskStatus } from "@bitagents/shared";

const styles: Record<TaskStatus, string> = {
  created: "border-slate-500/50 bg-slate-500/10 text-foreground",
  paid_pending: "border-skybit/50 bg-skybit/10 text-skybit",
  assigned: "border-mint/50 bg-mint/10 text-mint",
  computing: "border-coral/60 bg-coral/10 text-coral",
  completed: "border-emerald-400/60 bg-emerald-400/10 text-emerald-300",
  paid_out: "border-ember/70 bg-ember/15 text-ember",
  failed: "border-red-400/70 bg-red-400/10 text-red-300"
};

export function StatusPill({ status }: { status: TaskStatus }) {
  return (
    <span className={`inline-flex items-center rounded-md border px-2.5 py-1 text-xs font-black uppercase ${styles[status]}`}>
      {STATUS_LABELS[status]}
    </span>
  );
}
