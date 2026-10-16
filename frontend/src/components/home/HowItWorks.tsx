const steps = [
  {
    n: "01",
    title: "Users request agent tasks",
    body: "Choose an agent, define the task, and submit it.",
    code: ["> agent.run('wallet-watch')", "✓ task accepted", "→ agent: assigned"],
  },
  {
    n: "02",
    title: "Agents execute the task",
    body: "Your chosen agent runs the workload and streams results in real time.",
    code: ["> agent.execute()", "✓ task running", "→ status: online"],
  },
  {
    n: "03",
    title: "Results return on-chain-ready",
    body: "Users receive structured outputs while payments and settlement are handled through Solana.",
    code: ["> agent.result()", "✓ output verified", "→ settled · solana"],
  },
];

export function HowItWorks() {
  return (
    <section id="how" >
      <div className="mx-auto max-w-7xl px-6 py-20 md:py-28">
        <div className="flex flex-col items-start justify-between gap-6 md:flex-row md:items-end">
          <div className="max-w-2xl">
            <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-signal">Flow</div>
            <h2 className="mt-4 font-display text-4xl font-bold leading-tight md:text-5xl">
              How it works
            </h2>
          </div>
          <div className="font-mono text-xs text-muted-foreground">
            <span className="text-signal">●</span> end-to-end on Solana
          </div>
        </div>

        <ol className="mt-14 grid gap-px bg-[color:var(--border)] md:grid-cols-3">
          {steps.map((s) => (
            <li key={s.n} className="bg-background p-6">
              <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">Step {s.n}</div>
              <h3 className="mt-4 font-display text-lg font-bold">{s.title}</h3>
              <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{s.body}</p>
              <div className="mt-5 border-2 border-grid bg-background p-3 font-mono text-[10.5px] leading-relaxed text-muted-foreground">
                {s.code.map((line, i) => (
                  <div key={i} className={line.startsWith("✓") ? "text-signal" : line.startsWith("→") ? "text-warn" : ""}>
                    {line}
                  </div>
                ))}
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}