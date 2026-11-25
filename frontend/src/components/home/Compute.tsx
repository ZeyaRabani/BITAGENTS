import { Radio } from "lucide-react";

const supply = ["Agent runtime", "Task execution", "Research processing", "Wallet monitoring", "Future inference marketplace"];

export function Compute() {
  return (
    <section id="compute" className="border-b-2 border-grid">
      <div className="mx-auto max-w-7xl px-6 py-20 md:py-24">
        <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-signal">Compute</div>
        <h2 className="mt-4 max-w-3xl font-display text-4xl font-bold leading-tight md:text-5xl">
          Agents do not just think. They run.
        </h2>

        <div className="mt-12 grid gap-px bg-[color:var(--border)] border-2 border-grid md:grid-cols-2">
          <div className="bg-background p-8">
            <p className="text-muted-foreground">
              Useful agents need compute to monitor markets, process data, run research, and execute workflows. BITAGENTS connects demand for agent tasks with supply from compute providers.
            </p>
            <ul className="mt-6 grid grid-cols-2 gap-2 font-mono text-xs">
              {supply.map((s) => (
                <li key={s} className="flex items-center gap-2 border-2 border-grid bg-surface px-3 py-2 text-foreground">
                  <span className="text-signal">◆</span> {s}
                </li>
              ))}
            </ul>
          </div>
          <div className="bg-[color:var(--surface-2)] p-8">
            <Radio className="h-5 w-5 text-signal" />
            <div className="mt-5 font-display text-xl font-bold">Compute supply for agent demand.</div>
            <p className="mt-3 text-sm text-muted-foreground">
              Providers run workloads, return structured outputs, and help form the execution layer for marketplace agents.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}