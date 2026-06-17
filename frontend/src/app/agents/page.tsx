import { AgentRunner } from "@/components/AgentRunner";
import { PageShell, Panel } from "@/components/primitives";
import { AGENTS } from "@/lib/agents";

export default function AgentsPage() {
  return (
    <PageShell
      eyebrow="Agents"
      title="Crypto AI agents"
      description="Three working agents backed by real Solana RPC compute. Pick one, submit a task, and pay a small devnet fee or run a free demo."
    >
      <div className="space-y-10">
        <AgentRunner />

        <section className="space-y-4">
          <h2 className="font-display text-lg font-semibold text-foreground">What each agent does</h2>
          <div className="grid gap-4 md:grid-cols-3">
            {AGENTS.map((agent) => {
              const Icon = agent.icon;
              return (
                <Panel key={agent.type} title={agent.type}>
                  <div className="space-y-3">
                    <span className="pixel-corners flex h-10 w-10 items-center justify-center border border-signal/40 bg-signal/10 text-signal">
                      <Icon size={18} />
                    </span>
                    <h3 className="font-display text-base font-semibold text-foreground">{agent.label}</h3>
                    <p className="text-sm text-muted-foreground">{agent.description}</p>
                    <div>
                      <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">input</p>
                      <p className="mt-1 text-sm text-foreground/80">{agent.inputLabel}</p>
                    </div>
                    <div>
                      <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">output</p>
                      <ul className="mt-1 space-y-1">
                        {agent.outputs.map((output) => (
                          <li key={output} className="flex items-center gap-2 text-sm text-foreground/80">
                            <span className="h-1 w-1 bg-signal" />
                            {output}
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </Panel>
              );
            })}
          </div>
        </section>
      </div>
    </PageShell>
  );
}
