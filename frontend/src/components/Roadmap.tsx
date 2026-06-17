import { ROADMAP, type RoadmapPhase } from "@/lib/content";
import { cn } from "@/lib/utils";

const STATUS_STYLES: Record<RoadmapPhase["status"], string> = {
  live: "border-success/50 bg-success/10 text-success",
  "in-progress": "border-signal/50 bg-signal/10 text-signal",
  planned: "border-border bg-surface-2 text-muted-foreground"
};

const STATUS_LABEL: Record<RoadmapPhase["status"], string> = {
  live: "Live",
  "in-progress": "In progress",
  planned: "Planned"
};

export function Roadmap() {
  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
      {ROADMAP.map((phase) => (
        <div key={phase.phase} className="pixel-corners flex flex-col border border-border bg-surface p-5">
          <div className="flex items-center justify-between gap-2">
            <span className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">{phase.phase}</span>
            <span
              className={cn(
                "border px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.1em]",
                STATUS_STYLES[phase.status]
              )}
            >
              {STATUS_LABEL[phase.status]}
            </span>
          </div>
          <h3 className="mt-2 font-display text-lg font-semibold text-foreground">{phase.title}</h3>
          <ul className="mt-3 space-y-1.5">
            {phase.items.map((item) => (
              <li key={item} className="flex gap-2 text-sm text-foreground/80">
                <span className="text-signal">—</span>
                {item}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
